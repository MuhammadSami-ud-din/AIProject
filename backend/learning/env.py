"""Gymnasium environment wrapping the headless deterministic Arena-AI engine.

Features:
  - Action masking: returns boolean mask of legal macro-actions at every step.
  - Frame-skip: decision points occur only when the fighter is actionable.
  - Pluggable opponent agent: random, FSM personalities, search agents, or policies.
  - Deterministic and seeded reset.
"""

from typing import Any, Dict, Optional, Tuple
import gymnasium as gym
from gymnasium import spaces
import numpy as np

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.adapter import observation_for
from backend.ai.base_agent import Agent
from backend.ai.random_agent import RandomAgent
from backend.engine.combat import can_act, can_cancel_into, get_move
from backend.engine.state import FightState, FighterState
from backend.engine.step import make_initial_state, step
from backend.learning.config import (
    ACTION_DIM,
    DEFAULT_SEED,
    MAX_ROUND_FRAMES,
    OBS_DIM,
)


def get_action_mask(fighter: FighterState, enemy: FighterState, player: int = 1) -> np.ndarray:
    """Return a boolean mask of shape (ACTION_DIM,) of valid actions for the fighter."""
    mask = np.zeros(ACTION_DIM, dtype=bool)
    # Action.IDLE is always legal as a safe fallback
    mask[Action.IDLE.value] = True

    # Check hitstun: only Burst is allowed if conditions met
    if fighter.hitstun > 0:
        if fighter.meter >= 50.0 and not fighter.burst_used_this_round:
            mask[Action.BURST.value] = True
        return mask

    # If thrown: only Throw tech is allowed within 7 frames
    if fighter.is_thrown:
        if fighter.throw_tech_frames > 0:
            mask[Action.THROW.value] = True
        return mask

    # If knocked down or guard broken, only IDLE is legal
    if fighter.is_knocked_down or fighter.guard_break_stun > 0:
        return mask

    # If currently in blockstun, can continue holding high or low block
    if fighter.blockstun > 0:
        if not fighter.in_air:
            mask[Action.BLOCK.value] = True
            mask[Action.BLOCK_LOW.value] = True
        return mask

    actionable = can_act(fighter)

    for act in ALL_ACTIONS:
        if act.value >= ACTION_DIM:
            continue
        if act == Action.IDLE:
            continue

        # Check Burst: only legal during hitstun (already handled above)
        if act == Action.BURST:
            continue

        # Check cancels if fighter is currently in an attack cancel window
        valid_cancel = can_cancel_into(fighter, act)

        if not actionable and not valid_cancel:
            continue

        # Movement rules
        if act in (Action.FORWARD, Action.BACK, Action.DASH, Action.BACKDASH, Action.CROUCH):
            if not fighter.in_air:
                mask[act.value] = True
            continue

        if act == Action.JUMP:
            if not fighter.in_air:
                mask[act.value] = True
            elif fighter.character_name == "Shadow" and fighter.jump_frame < 22:
                # Shadow double jump passive
                mask[act.value] = True
            continue

        # Guard rules
        if act in (Action.BLOCK, Action.BLOCK_LOW):
            if not fighter.in_air:
                mask[act.value] = True
            continue

        # Aerial attacks only in air
        if act in (Action.JUMP_PUNCH, Action.JUMP_KICK):
            if fighter.in_air:
                mask[act.value] = True
            continue

        # Ground-only attacks (must NOT be in air)
        if fighter.in_air:
            continue

        # Super move meter check (100 standard, 60 in Fury)
        if act == Action.SUPER:
            req_meter = 60.0 if fighter.is_fury else 100.0
            if fighter.meter >= req_meter:
                mask[act.value] = True
            continue

        # Steel Shield Bash meter check (costs 25 meter)
        if act == Action.SPECIAL_FORWARD and fighter.character_name == "Steel":
            if fighter.meter >= 25.0:
                mask[act.value] = True
            continue

        # General attacks and specials
        move = get_move(fighter.character_name, act)
        if move is not None:
            if move.meter_cost > 0 and fighter.meter < move.meter_cost:
                continue
            mask[act.value] = True
        else:
            # Universal basic move
            mask[act.value] = True

    return mask


class ArenaEnv(gym.Env):
    """Gymnasium environment wrapping the deterministic Arena-AI engine."""

    metadata = {"render_modes": ["human", "rgb_array"]}

    def __init__(
        self,
        fighter_character: str = "Crimson",
        opponent_character: str = "Steel",
        opponent_agent: Optional[Agent] = None,
        reward_calculator: Optional[Any] = None,
        seed: int = DEFAULT_SEED,
    ):
        super().__init__()
        self.fighter_character = fighter_character
        self.opponent_character = opponent_character
        self.reward_calculator = reward_calculator
        self.initial_seed = seed
        self.np_random = np.random.default_rng(seed)

        # Set opponent agent (defaults to RandomAgent if None)
        self.opponent_agent = opponent_agent or RandomAgent(player=2, seed=seed + 100)

        # Spaces
        self.action_space = spaces.Discrete(ACTION_DIM)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(OBS_DIM,), dtype=np.float32
        )

        self.state: Optional[FightState] = None
        self.prev_state: Optional[FightState] = None
        self.current_step = 0

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Reset the environment to the beginning of a match."""
        super().reset(seed=seed)
        effective_seed = seed if seed is not None else self.initial_seed
        self.np_random = np.random.default_rng(effective_seed)

        # Re-seed opponent if supported
        if hasattr(self.opponent_agent, "rng"):
            import random
            if isinstance(self.opponent_agent.rng, random.Random):
                self.opponent_agent.rng = random.Random(effective_seed + 100)
            else:
                self.opponent_agent.rng = np.random.default_rng(effective_seed + 100)
        if hasattr(self.opponent_agent, "reset"):
            self.opponent_agent.reset()

        self.state = make_initial_state(self.fighter_character, self.opponent_character)
        self.prev_state = self.state.copy()
        self.current_step = 0

        if self.reward_calculator is not None and hasattr(self.reward_calculator, "reset"):
            self.reward_calculator.reset()

        obs_vector = self._get_obs()
        action_mask = get_action_mask(self.state.fighter1, self.state.fighter2, player=1)

        info = {
            "action_mask": action_mask,
            "frame": self.state.frame,
            "round": self.state.round_number,
            "f1_health": self.state.fighter1.health,
            "f2_health": self.state.fighter2.health,
        }
        return obs_vector, info

    def step(
        self, action: int
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """Execute one macro-action step with frame-skip until actionable again."""
        if self.state is None:
            raise RuntimeError("Environment called step() before reset().")

        # Action masking safety: ensure chosen action is legal; fallback to IDLE
        mask = get_action_mask(self.state.fighter1, self.state.fighter2, player=1)
        action_idx = int(action)
        if not mask[action_idx]:
            action_idx = Action.IDLE.value

        chosen_action = ALL_ACTIONS[action_idx]
        self.prev_state = self.state.copy()

        # Step frame by frame until learner can act again, or round ends
        frames_advanced = 0
        max_frame_skip = 30  # Safety upper bound for one macro step

        while frames_advanced < max_frame_skip:
            # Query opponent action
            obs_opponent = observation_for(self.state, player=2)
            opp_action = self.opponent_agent.choose_action(obs_opponent)
            if isinstance(opp_action, tuple):
                opp_action = opp_action[0]

            # Sustained movement/defense actions hold across the macro-step;
            # discrete attacks/jumps initiate on the first frame and resolve
            if chosen_action in (
                Action.FORWARD, Action.BACK, Action.DASH,
                Action.CROUCH, Action.BLOCK, Action.BLOCK_LOW,
            ):
                f1_action = chosen_action
            else:
                f1_action = chosen_action if frames_advanced == 0 else Action.IDLE

            self.state = step(self.state, f1_action, opp_action)
            frames_advanced += 1

            if self.state.round_over or self.state.match_over or self.state.round_frames_left <= 0:
                break

            # If fighter is ready to act again and finished the initial commitment
            if frames_advanced >= 6 and can_act(self.state.fighter1):
                break

        self.current_step += 1

        # Calculate step reward
        if self.reward_calculator is not None:
            reward, reward_breakdown = self.reward_calculator.calculate(
                self.prev_state, self.state, chosen_action, player=1
            )
        else:
            # Shared base reward fallback
            damage_dealt = max(0.0, self.prev_state.fighter2.health - self.state.fighter2.health)
            damage_taken = max(0.0, self.prev_state.fighter1.health - self.state.fighter1.health)
            reward = (damage_dealt - damage_taken) * 100.0
            if self.state.round_over:
                if self.state.round_result == "p1":
                    reward += 10.0
                elif self.state.round_result == "p2":
                    reward -= 10.0
            reward -= 0.005 * frames_advanced
            reward_breakdown = {"base": reward}

        terminated = bool(self.state.round_over or self.state.match_over)
        truncated = bool(self.state.frame >= MAX_ROUND_FRAMES)

        obs_vector = self._get_obs()
        next_mask = get_action_mask(self.state.fighter1, self.state.fighter2, player=1)

        info = {
            "action_mask": next_mask,
            "frame": self.state.frame,
            "frames_advanced": frames_advanced,
            "reward_breakdown": reward_breakdown,
            "f1_health": self.state.fighter1.health,
            "f2_health": self.state.fighter2.health,
            "round_winner": self.state.round_result,
        }

        return obs_vector, float(reward), terminated, truncated, info

    def _get_obs(self) -> np.ndarray:
        """Convert engine state into normalized float32 observation vector."""
        obs = observation_for(self.state, player=1)
        feat_dict = obs.features()
        from backend.ai.observation import FEATURE_NAMES
        feat_vec = [float(feat_dict[k]) for k in FEATURE_NAMES]
        return np.array(feat_vec, dtype=np.float32)
