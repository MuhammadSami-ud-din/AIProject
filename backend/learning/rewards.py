"""Reward shaping profiles for personality-driven reinforcement learning.

Personality emerges naturally from the reward signal:
  - Crimson: Rewards aggressive advancing pressure, combos; penalizes retreating.
  - Steel: Rewards parries, blocks, and block-punishes; penalizes whiffed attacks.
  - Shadow: Rewards spacing at preferred distance, evades, whiff punishes; penalizes being cornered.
  - Golden: Rewards correct predictive reads, round wins, and balanced tactical versatility.

Every term is tracked separately per episode to catch and prevent reward hacking.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import numpy as np

from backend.ai.actions import ATTACKS, Action
from backend.engine.state import FightState
from backend.learning.config import (
    CRIMSON_BACKING_PENALTY,
    CRIMSON_COMBO_HIT_BONUS,
    CRIMSON_FORWARD_BONUS,
    DAMAGE_DEALT_WEIGHT,
    DAMAGE_TAKEN_WEIGHT,
    GOLDEN_BALANCED_BONUS,
    GOLDEN_READ_HIT_BONUS,
    GOLDEN_ROUND_WIN_BONUS,
    ROUND_LOSS_PENALTY,
    ROUND_WIN_REWARD,
    SHADOW_CORNER_PENALTY,
    SHADOW_EVADE_BONUS,
    SHADOW_PREFERRED_DIST_BONUS,
    SHADOW_PREFERRED_DIST_MAX,
    SHADOW_PREFERRED_DIST_MIN,
    SHADOW_WHIFF_PUNISH_BONUS,
    STEEL_BLOCK_BONUS,
    STEEL_PARRY_BONUS,
    STEEL_PUNISH_BONUS,
    STEEL_WHIFF_PENALTY,
    TIME_PENALTY_PER_STEP,
    WHIFF_PENALTY,
)


@dataclass
class RewardTracker:
    """Accumulates detailed breakdowns of rewards earned across an episode."""
    base_damage: float = 0.0
    round_win_loss: float = 0.0
    time_penalty: float = 0.0
    whiff_penalty: float = 0.0
    personality_bonus: float = 0.0
    details: Dict[str, float] = field(default_factory=dict)

    def total(self) -> float:
        return (
            self.base_damage
            + self.round_win_loss
            + self.time_penalty
            + self.whiff_penalty
            + self.personality_bonus
        )

    def reset(self) -> None:
        self.base_damage = 0.0
        self.round_win_loss = 0.0
        self.time_penalty = 0.0
        self.whiff_penalty = 0.0
        self.personality_bonus = 0.0
        self.details.clear()


class RewardCalculator:
    """Calculates composite shaped rewards based on fighter state transitions."""

    def __init__(self, personality: str = "Crimson"):
        self.personality = personality
        self.tracker = RewardTracker()
        self.frames_since_last_block = 999

    def reset(self) -> None:
        self.tracker.reset()
        self.frames_since_last_block = 999

    def calculate(
        self,
        prev_state: FightState,
        curr_state: FightState,
        action: Action,
        player: int = 1,
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate reward and return (total_reward, breakdown_dict)."""
        f1_prev = prev_state.fighter1 if player == 1 else prev_state.fighter2
        f2_prev = prev_state.fighter2 if player == 1 else prev_state.fighter1
        f1_curr = curr_state.fighter1 if player == 1 else curr_state.fighter2
        f2_curr = curr_state.fighter2 if player == 1 else curr_state.fighter1

        # 1. Base Damage Reward
        dmg_dealt = max(0.0, f2_prev.health - f2_curr.health)
        dmg_taken = max(0.0, f1_prev.health - f1_curr.health)
        net_damage_reward = (dmg_dealt * DAMAGE_DEALT_WEIGHT) - (dmg_taken * DAMAGE_TAKEN_WEIGHT)

        # 2. Round Outcome
        round_reward = 0.0
        if curr_state.round_over:
            my_win_key = "p1" if player == 1 else "p2"
            enemy_win_key = "p2" if player == 1 else "p1"
            if curr_state.round_result == my_win_key:
                round_reward = ROUND_WIN_REWARD
            elif curr_state.round_result == enemy_win_key:
                round_reward = ROUND_LOSS_PENALTY

        # 3. Time and Whiff Penalties
        time_pen = -TIME_PENALTY_PER_STEP * max(1, curr_state.frame - prev_state.frame)
        whiff_pen = 0.0
        if action in ATTACKS and dmg_dealt <= 0 and f1_curr.recovery > 0 and f2_curr.blockstun <= 0:
            whiff_pen = -WHIFF_PENALTY

        # 4. Personality-Specific Bonus
        bonus = 0.0
        bonus_dict: Dict[str, float] = {}

        # Track block frames for punish window
        if f1_curr.last_hit_effect == "block" or f1_curr.blockstun > 0:
            self.frames_since_last_block = 0
        else:
            self.frames_since_last_block += (curr_state.frame - prev_state.frame)

        dist = abs(f1_curr.x - f2_curr.x)

        if self.personality == "Crimson":
            # Rewards forward pressure & combo strings
            if action in (Action.FORWARD, Action.DASH):
                bonus += CRIMSON_FORWARD_BONUS
                bonus_dict["forward_pressure"] = CRIMSON_FORWARD_BONUS
            elif action in (Action.BACK, Action.BACKDASH):
                bonus += CRIMSON_BACKING_PENALTY
                bonus_dict["retreat_penalty"] = CRIMSON_BACKING_PENALTY

            if f1_curr.combo_hits > f1_prev.combo_hits:
                combo_bonus = CRIMSON_COMBO_HIT_BONUS * (f1_curr.combo_hits)
                bonus += combo_bonus
                bonus_dict["combo_hits"] = combo_bonus

        elif self.personality == "Steel":
            # Rewards defensive blocks, perfect parries, and block punishes
            if f1_curr.last_hit_effect == "parry":
                bonus += STEEL_PARRY_BONUS
                bonus_dict["perfect_parry"] = STEEL_PARRY_BONUS
            elif f1_curr.last_hit_effect == "block" or (f1_curr.blockstun > 0 and f1_prev.blockstun == 0):
                bonus += STEEL_BLOCK_BONUS
                bonus_dict["clean_block"] = STEEL_BLOCK_BONUS

            if dmg_dealt > 0 and self.frames_since_last_block <= 30:
                punish_reward = STEEL_PUNISH_BONUS * (dmg_dealt * 100.0)
                bonus += punish_reward
                bonus_dict["block_punish"] = punish_reward

            if whiff_pen < 0:
                extra_whiff = STEEL_WHIFF_PENALTY
                bonus += extra_whiff
                bonus_dict["steel_whiff_penalty"] = extra_whiff

        elif self.personality == "Shadow":
            # Rewards maintaining preferred distance, evading, and whiff punishes
            if SHADOW_PREFERRED_DIST_MIN <= dist <= SHADOW_PREFERRED_DIST_MAX:
                bonus += SHADOW_PREFERRED_DIST_BONUS
                bonus_dict["preferred_spacing"] = SHADOW_PREFERRED_DIST_BONUS

            # Whiff punish: dealt damage while enemy was in recovery or cooldown
            if dmg_dealt > 0 and (f2_prev.recovery > 0 or f2_prev.cooldown > 0):
                wp_bonus = SHADOW_WHIFF_PUNISH_BONUS
                bonus += wp_bonus
                bonus_dict["whiff_punish"] = wp_bonus

            # Evade bonus: backdash, air dash, or shadow step
            if action in (Action.BACKDASH, Action.SPECIAL_NEUTRAL) and f2_curr.recovery > 0:
                bonus += SHADOW_EVADE_BONUS
                bonus_dict["evade_success"] = SHADOW_EVADE_BONUS

            # Corner penalty
            room_behind = f1_curr.x if f1_curr.x < f2_curr.x else (800.0 - f1_curr.x)
            if room_behind < 75.0:
                bonus += SHADOW_CORNER_PENALTY
                bonus_dict["cornered_penalty"] = SHADOW_CORNER_PENALTY

        elif self.personality == "Golden":
            # Rewards round wins, read counter-hits, and tactical balance
            if curr_state.round_over and curr_state.round_result == ("p1" if player == 1 else "p2"):
                bonus += GOLDEN_ROUND_WIN_BONUS
                bonus_dict["golden_round_win"] = GOLDEN_ROUND_WIN_BONUS

            if f1_curr.last_hit_effect == "golden_read" or getattr(f1_curr, "read_success", False):
                bonus += GOLDEN_READ_HIT_BONUS
                bonus_dict["golden_read_hit"] = GOLDEN_READ_HIT_BONUS

            if dmg_dealt > 0 and dmg_taken <= 0:
                bonus += GOLDEN_BALANCED_BONUS
                bonus_dict["tactical_advantage"] = GOLDEN_BALANCED_BONUS

        total_step_reward = net_damage_reward + round_reward + time_pen + whiff_pen + bonus

        # Update cumulative tracker
        self.tracker.base_damage += net_damage_reward
        self.tracker.round_win_loss += round_reward
        self.tracker.time_penalty += time_pen
        self.tracker.whiff_penalty += whiff_pen
        self.tracker.personality_bonus += bonus
        for k, v in bonus_dict.items():
            self.tracker.details[k] = self.tracker.details.get(k, 0.0) + v

        breakdown = {
            "net_damage": net_damage_reward,
            "round_outcome": round_reward,
            "time_penalty": time_pen,
            "whiff_penalty": whiff_pen,
            "personality_bonus": bonus,
            **bonus_dict,
        }

        return float(total_step_reward), breakdown
