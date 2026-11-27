"""PolicyAgent: neural-network agent used in gameplay (HIGH/HELL) and evaluation.

Train/inference consistency:
  * Same observation vector as training (``features.policy_vector``).
  * Same action mask as training: built with ``env.get_action_mask`` from a
    FighterState reconstructed from ALL mask inputs carried by the Observation
    (thrown, throw-tech, guard-break stun, burst used, jump frame, attack phase).
  * Same decision granularity as training: the policy is queried once per
    macro-step and the chosen action is executed exactly like ``ArenaEnv.step``
    (sustained actions held, discrete actions pressed on the first frame), the
    next decision comes when ``macro_step_done`` says so.
  * Sampling at temperature 1.0 (the training distribution) by default, or
    greedy (argmax) when ``greedy=True`` -- no personality-dependent temperature.

Model resolution order: explicit ``model_path`` -> registry "live" row ->
newest compatible checkpoint in ``models/<character>/`` -> ``bc_model.pt``.
If nothing loads, the rule-based FSM for the character is used.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.observation import Observation
from backend.ai.personalities import ALL_PERSONALITIES
from backend.engine.state import FighterState
from backend.learning.checkpoints import find_latest_checkpoint, load_compatible_state_dict
from backend.learning.config import ACTION_DIM, OBS_DIM, get_character_agent as get_agent
from backend.learning.env import get_action_mask, macro_frame_action, macro_step_done
from backend.learning.features import policy_vector
from backend.learning.network import ActorCritic

logger = logging.getLogger(__name__)


def fighter_from_observation(obs: Observation, character: str) -> FighterState:
    """Rebuild the learner's FighterState fields that the action mask reads."""
    f = FighterState(character_name=getattr(obs, "my_character", "") or character)
    f.in_air = obs.my_in_air
    f.meter = obs.my_meter
    f.health = obs.my_health
    f.hitstun = obs.my_hitstun
    f.blockstun = obs.my_blockstun
    f.cooldown = obs.my_cooldown
    f.recovery = obs.my_recovery
    f.is_knocked_down = obs.my_is_knocked_down
    f.is_crouching = obs.my_is_crouching
    f.is_thrown = getattr(obs, "my_is_thrown", False)
    f.throw_tech_frames = getattr(obs, "my_throw_tech_frames", 0)
    f.guard_break_stun = getattr(obs, "my_guard_break_stun", 0)
    f.burst_used_this_round = getattr(obs, "my_burst_used", False)
    f.jump_frame = getattr(obs, "my_jump_frame", 0)
    phase = getattr(obs, "my_attack_phase", "none")
    f.attack_phase = phase if getattr(obs, "has_engine_detail", False) else "none"
    return f


class PolicyAgent(Agent):
    """Agent running the PyTorch actor-critic policy with masked sampling."""

    def __init__(
        self,
        personality: str = "Crimson",
        player: int = 1,
        model_path: Optional[str] = None,
        device: str = "cpu",
        seed: Optional[int] = None,
        greedy: bool = False,
        temperature: float = 1.0,
        models_dir: Optional[str] = None,
        registry_path: Optional[str] = None,
        use_registry: bool = True,
    ):
        p_card = ALL_PERSONALITIES.get(personality.capitalize())
        super().__init__(
            name=f"{personality.capitalize()}Policy",
            player=player,
            difficulty="HIGH",
            personality=p_card,
            seed=seed,
        )
        self.personality_name = personality.capitalize()
        self.device = torch.device(device)
        self.model: Optional[ActorCritic] = None
        self.model_path: Optional[str] = None
        self.fallback_agent: Agent = get_agent(self.personality_name, player=player, seed=seed)
        self.greedy = greedy
        self.temperature = float(temperature) if temperature > 0 else 1.0
        self.models_dir = models_dir
        self.registry_path = registry_path
        self.use_registry = use_registry
        self.last_inference_time_ms = 0.0
        self.last_confidence = 0.0
        self.last_probs: Optional[np.ndarray] = None

        # Macro-step execution state (mirrors ArenaEnv.step)
        self._held_action: Optional[Action] = None
        self._frames_in_macro = 0
        self._held_scores: Dict[Action, float] = {Action.IDLE: 1.0}

        self.load_model(model_path)

    @property
    def stages(self) -> Dict[str, float]:
        return self.last_breakdown

    def reset(self) -> None:
        super().reset()
        self._held_action = None
        self._frames_in_macro = 0
        self.fallback_agent.reset()

    def _resolve_path(self, model_path: Optional[str]) -> Optional[str]:
        if model_path:
            return model_path
        if self.use_registry:
            try:
                from backend.learning.league import ModelRegistry

                reg = ModelRegistry(self.registry_path) if self.registry_path else ModelRegistry()
                live = reg.get_live_model(self.personality_name)
                if live and os.path.exists(live["file_path"]):
                    if load_compatible_state_dict(live["file_path"]) is not None:
                        return live["file_path"]
                rejected = [r["file_path"] for r in reg.list_models(self.personality_name)
                            if r["status"] == "rolled_back"]
                return find_latest_checkpoint(self.personality_name, self.models_dir, exclude=rejected)
            except Exception:
                logger.warning("model registry lookup failed for %s", self.personality_name, exc_info=True)
        return find_latest_checkpoint(self.personality_name, self.models_dir)

    def load_model(self, model_path: Optional[str] = None) -> bool:
        """Load trained weights; returns False (FSM fallback) if none are usable."""
        resolved = self._resolve_path(model_path)
        if not resolved or not os.path.exists(resolved):
            self.model = None
            return False
        state = load_compatible_state_dict(resolved)
        if state is None:
            self.model = None
            return False
        try:
            model = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM).to(self.device)
            model.load_state_dict(state, strict=True)
            model.eval()
        except Exception:
            logger.warning("failed to load policy weights from %s", resolved, exc_info=True)
            self.model = None
            return False
        self.model = model
        self.model_path = resolved
        return True

    # ------------------------------------------------------------------
    def policy_distribution(self, obs: Observation) -> Tuple[np.ndarray, np.ndarray]:
        """Masked action probabilities (temperature applied) and the mask."""
        feat = policy_vector(obs)
        obs_tensor = torch.from_numpy(feat).unsqueeze(0).to(self.device)
        mask_np = get_action_mask(
            fighter_from_observation(obs, self.personality_name),
            FighterState(character_name=getattr(obs, "enemy_character", "") or "Golden",
                         in_air=obs.enemy_in_air),
            player=self.player,
        )
        mask_tensor = torch.from_numpy(mask_np).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits, _ = self.model(obs_tensor, mask=mask_tensor)
            probs = F.softmax(logits / self.temperature, dim=-1).squeeze(0).cpu().numpy()
        if not np.isfinite(probs).all() or probs.sum() <= 0:
            probs = mask_np.astype(np.float64) / max(1, mask_np.sum())
        else:
            probs = probs.astype(np.float64)
            probs = probs / probs.sum()
        return probs, mask_np

    def _decide(self, obs: Observation) -> Tuple[Action, Dict[Action, float]]:
        probs, _ = self.policy_distribution(obs)
        if self.greedy:
            idx = int(np.argmax(probs))
        else:
            idx = int(self.rng.choices(range(len(probs)), weights=probs, k=1)[0])
        self.last_probs = probs
        self.last_confidence = float(probs[idx])
        scores = {act: float(probs[act.value]) * 10.0 for act in ALL_ACTIONS if act.value < len(probs)}
        return ALL_ACTIONS[idx], scores

    def choose_action(self, obs: Observation) -> Tuple[Action, Dict[Action, float]]:
        """Per-frame entry point; queries the network once per macro-step."""
        with self.stage("policy"):
            if self.model is None:
                action, scores = self.fallback_agent.choose_action(obs)
                self.last_inference_time_ms = self.last_breakdown.get("policy", 0.0)
                return action, scores

            new_decision = (
                self._held_action is None
                or macro_step_done(self._frames_in_macro, fighter_from_observation(obs, self.personality_name))
            )
            if new_decision:
                self._held_action, self._held_scores = self._decide(obs)
                self._frames_in_macro = 0
            action = macro_frame_action(self._held_action, self._frames_in_macro)
            self._frames_in_macro += 1

        self.last_inference_time_ms = self.last_breakdown.get("policy", 0.0)
        return action, self._held_scores

    def suggest(self, obs: Observation) -> Optional[np.ndarray]:
        """Action probabilities for blending (DifficultyWrapper); None if no model."""
        if self.model is None:
            return None
        probs, _ = self.policy_distribution(obs)
        return probs
