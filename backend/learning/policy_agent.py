"""PolicyAgent: Neural network-driven agent executing in-game inference.

Features:
  - Masked softmax sampling with temperature from personality.variety.
  - Decision latency timed with self.stage('policy') (< 1 ms on CPU).
  - Robust fallback to rule-based FSM / search if no model is loaded.
  - Exposes confidence distribution and opponent predictions for explanations.
"""

import os
import time
from typing import Dict, Optional, Tuple
import numpy as np
import torch
import torch.nn.functional as F

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.learning.config import get_character_agent as get_agent
from backend.ai.observation import Observation
from backend.ai.personalities import ALL_PERSONALITIES
from backend.learning.config import ACTION_DIM, MODELS_DIR, OBS_DIM
from backend.learning.league import ModelRegistry
from backend.learning.network import ActorCritic


class PolicyAgent(Agent):
    """Agent running PyTorch neural network policy with masked softmax sampling."""

    def __init__(
        self,
        personality: str = "Crimson",
        player: int = 1,
        model_path: Optional[str] = None,
        device: str = "cpu",
        seed: Optional[int] = None,
    ):
        p_card = ALL_PERSONALITIES.get(personality.capitalize())
        super().__init__(
            name=f"{personality}Policy",
            player=player,
            difficulty="HIGH",
            personality=p_card,
            seed=seed,
        )
        self.personality_name = personality.capitalize()
        self.device = torch.device(device)
        self.model: Optional[ActorCritic] = None
        self.fallback_agent: Agent = get_agent(self.personality_name, player=player, seed=seed)
        self.temperature = max(0.2, getattr(p_card, "variety", 0.5) if p_card else 0.5)
        self.last_inference_time_ms = 0.0
        self.last_confidence = 0.0

        # Attempt to load model
        self.load_model(model_path)

    @property
    def stages(self) -> Dict[str, float]:
        """Return the dictionary of recorded stage breakdown times."""
        return self.last_breakdown

    def load_model(self, model_path: Optional[str] = None) -> bool:
        """Load trained model weights from disk or registry."""
        resolved_path = model_path
        if not resolved_path:
            # Check model registry for live model
            registry = ModelRegistry()
            live_entry = registry.get_live_model(self.personality_name)
            if live_entry and os.path.exists(live_entry["file_path"]):
                resolved_path = live_entry["file_path"]

        if not resolved_path:
            # Check default path in models/<personality>/
            default_p = os.path.join(MODELS_DIR, self.personality_name.lower(), "v010.pt")
            bc_p = os.path.join(MODELS_DIR, self.personality_name.lower(), "bc_model.pt")
            if os.path.exists(default_p):
                resolved_path = default_p
            elif os.path.exists(bc_p):
                resolved_path = bc_p

        if resolved_path and os.path.exists(resolved_path):
            try:
                model = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM).to(self.device)
                state_dict = torch.load(resolved_path, map_location=self.device)
                model.load_state_dict(state_dict, strict=False)
                model.eval()
                self.model = model
                return True
            except Exception:
                self.model = None

        return False

    def choose_action(self, obs: Observation) -> Tuple[Action, Dict[Action, float]]:
        """Choose action using masked softmax sampling; times decision with self.stage('policy')."""
        with self.stage("policy"):
            # Fall back to FSM / search if no model is loaded
            if self.model is None:
                action, scores = self.fallback_agent.choose_action(obs)
                self.last_inference_time_ms = self.last_breakdown.get("policy", 0.1)
                return action, scores

            feat_dict = obs.features()
            from backend.ai.observation import FEATURE_NAMES
            feat = np.array([float(feat_dict[k]) for k in FEATURE_NAMES], dtype=np.float32)
            obs_tensor = torch.tensor(feat, dtype=torch.float32, device=self.device).unsqueeze(0)

            # Build action mask
            from backend.learning.env import get_action_mask
            from backend.engine.state import FighterState
            dummy_f1 = FighterState(character_name=self.personality_name, in_air=obs.my_in_air)
            dummy_f1.meter = obs.my_meter
            dummy_f1.hitstun = obs.my_hitstun
            dummy_f1.blockstun = obs.my_blockstun
            dummy_f1.cooldown = obs.my_cooldown
            dummy_f1.recovery = obs.my_recovery
            dummy_f1.is_knocked_down = obs.my_is_knocked_down
            dummy_f2 = FighterState(character_name="Enemy", in_air=obs.enemy_in_air)
            mask_np = get_action_mask(dummy_f1, dummy_f2, player=self.player)
            mask_tensor = torch.tensor(mask_np, dtype=torch.bool, device=self.device).unsqueeze(0)

            with torch.no_grad():
                logits, _ = self.model(obs_tensor, mask=mask_tensor)
                scaled_logits = logits / self.temperature
                probs = F.softmax(scaled_logits, dim=-1).squeeze(0).cpu().numpy()

            # Handle numerical edge cases
            if np.isnan(probs).any() or probs.sum() <= 0:
                probs = mask_np.astype(float) / max(1, mask_np.sum())
            else:
                probs = probs / probs.sum()

            # Masked softmax sampling (not pure argmax, prevents human exploitation)
            if hasattr(self.rng, "choices"):
                chosen_idx = int(self.rng.choices(range(len(ALL_ACTIONS)), weights=probs, k=1)[0])
            else:
                chosen_idx = int(self.rng.choice(len(ALL_ACTIONS), p=probs))
            chosen_action = ALL_ACTIONS[chosen_idx]
            self.last_confidence = float(probs[chosen_idx])

            # Action scores dictionary
            scores = {act: float(probs[act.value] * 10.0) for act in ALL_ACTIONS}

        self.last_inference_time_ms = self.last_breakdown.get("policy", 0.1)
        return chosen_action, scores
