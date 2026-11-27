"""Reward shaping profiles for personality-driven reinforcement learning.

Personality emerges naturally from the reward signal:
  - Crimson: Rewards aggressive advancing pressure, combos; penalizes retreating.
  - Steel: Rewards parries, blocks, and block-punishes; penalizes whiffed attacks.
  - Shadow: Rewards spacing at preferred distance, evades, whiff punishes; penalizes being cornered.
  - Golden: Rewards correct predictive reads, round wins, and balanced tactical versatility.

Every term is tracked separately per episode to catch and prevent reward hacking.

Anti-reward-hacking rules (engine contract: ``FighterState.last_hit_effect`` and
``read_success`` are ONE-FRAME events):
  * Event bonuses (parry, block, read) are edge-triggered per engine frame. The
    env calls ``observe_frame`` for every simulated frame of a macro-step so a
    one-frame event is never missed, and a sticky value is never paid twice.
  * Crimson's aggression bonus pays for *results* (damage dealt, enemy forced
    to block while in range), never for pressing FORWARD.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from backend.ai.actions import ATTACKS, Action
from backend.engine.state import FightState
from backend.learning.config import (
    CRIMSON_BACKING_PENALTY,
    CRIMSON_COMBO_HIT_BONUS,
    CRIMSON_DAMAGE_BONUS,
    CRIMSON_PRESSURE_BONUS,
    CRIMSON_PRESSURE_RANGE,
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


READ_EFFECTS = ("read", "golden_read")   # "golden_read" kept for older engines
PUNISH_WINDOW_FRAMES = 30


def _sides(state: FightState, player: int):
    return (state.fighter1, state.fighter2) if player == 1 else (state.fighter2, state.fighter1)


def _new_effect(prev_f, curr_f) -> str:
    """Edge-triggered hit effect for one engine frame ("none" if nothing new)."""
    eff = getattr(curr_f, "last_hit_effect", "none") or "none"
    if eff == "none" or eff == (getattr(prev_f, "last_hit_effect", "none") or "none"):
        return "none"
    return eff


def extract_frame_events(prev_state: FightState, curr_state: FightState, player: int = 1) -> Dict[str, float]:
    """Edge-triggered events between two consecutive engine frames."""
    me_p, en_p = _sides(prev_state, player)
    me_c, en_c = _sides(curr_state, player)
    my_eff = _new_effect(me_p, me_c)
    en_eff = _new_effect(en_p, en_c)
    read_edge = bool(getattr(me_c, "read_success", False)) and not bool(getattr(me_p, "read_success", False))
    return {
        "parry": float(my_eff == "parry"),
        "block": float(my_eff == "block" or (my_eff != "parry" and me_p.blockstun == 0 and me_c.blockstun > 0)),
        "read": float(my_eff in READ_EFFECTS or read_edge),
        "enemy_block": float(en_eff == "block" or (en_p.blockstun == 0 and en_c.blockstun > 0)),
        "dmg_dealt": max(0.0, en_p.health - en_c.health),
        "dist": abs(me_c.x - en_c.x),
        "frames": float(max(1, curr_state.frame - prev_state.frame)),
    }


class RewardCalculator:
    """Calculates composite shaped rewards based on fighter state transitions."""

    def __init__(self, personality: str = "Crimson", use_personality_bonus: bool = True):
        self.personality = personality
        self.use_personality_bonus = use_personality_bonus
        self.tracker = RewardTracker()
        self.frames_since_last_block = 999
        self._pending: List[Dict[str, float]] = []
        self._pending_punish_dmg = 0.0

    def reset(self) -> None:
        self.tracker.reset()
        self.frames_since_last_block = 999
        self._pending.clear()
        self._pending_punish_dmg = 0.0

    def observe_frame(self, prev_state: FightState, curr_state: FightState, player: int = 1) -> None:
        """Record one engine frame's events (called by the env inside a macro-step)."""
        ev = extract_frame_events(prev_state, curr_state, player)
        self._consume_punish_window(ev)
        self._pending.append(ev)

    def _consume_punish_window(self, ev: Dict[str, float]) -> None:
        if ev["block"] or ev["parry"]:
            self.frames_since_last_block = 0
        else:
            self.frames_since_last_block += int(ev["frames"])
        if ev["dmg_dealt"] > 0 and self.frames_since_last_block <= PUNISH_WINDOW_FRAMES:
            self._pending_punish_dmg += ev["dmg_dealt"]

    def calculate(
        self,
        prev_state: FightState,
        curr_state: FightState,
        action: Action,
        player: int = 1,
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate reward for one macro-step and return (total_reward, breakdown_dict)."""
        f1_prev, f2_prev = _sides(prev_state, player)
        f1_curr, f2_curr = _sides(curr_state, player)

        if self._pending:
            events = self._pending
        else:
            # Called without per-frame observation (unit tests / single-frame use):
            # treat the pair as one transition.
            ev = extract_frame_events(prev_state, curr_state, player)
            self._consume_punish_window(ev)
            events = [ev]
        punish_dmg = self._pending_punish_dmg
        self._pending = []
        self._pending_punish_dmg = 0.0

        # 1. Base Damage Reward
        dmg_dealt = max(0.0, f2_prev.health - f2_curr.health)
        dmg_taken = max(0.0, f1_prev.health - f1_curr.health)
        net_damage_reward = (dmg_dealt * DAMAGE_DEALT_WEIGHT) - (dmg_taken * DAMAGE_TAKEN_WEIGHT)

        # 2. Round Outcome
        round_reward = 0.0
        my_win_key = "p1" if player == 1 else "p2"
        enemy_win_key = "p2" if player == 1 else "p1"
        if curr_state.round_over:
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
        bonus_dict: Dict[str, float] = {}
        dist = abs(f1_curr.x - f2_curr.x)
        n_parry = sum(e["parry"] for e in events)
        n_block = sum(e["block"] for e in events)
        n_read = sum(e["read"] for e in events)
        n_pressure = sum(e["enemy_block"] for e in events if e["dist"] <= CRIMSON_PRESSURE_RANGE)

        if self.personality == "Crimson":
            if dmg_dealt > 0:
                bonus_dict["damage_aggression"] = CRIMSON_DAMAGE_BONUS * dmg_dealt * 100.0
            if n_pressure > 0:
                bonus_dict["pressure"] = CRIMSON_PRESSURE_BONUS * n_pressure
            if action in (Action.BACK, Action.BACKDASH):
                bonus_dict["retreat_penalty"] = CRIMSON_BACKING_PENALTY
            if f1_curr.combo_hits > f1_prev.combo_hits:
                bonus_dict["combo_hits"] = CRIMSON_COMBO_HIT_BONUS * f1_curr.combo_hits

        elif self.personality == "Steel":
            if n_parry > 0:
                bonus_dict["perfect_parry"] = STEEL_PARRY_BONUS * n_parry
            if n_block > 0:
                bonus_dict["clean_block"] = STEEL_BLOCK_BONUS * n_block
            if punish_dmg > 0:
                bonus_dict["block_punish"] = STEEL_PUNISH_BONUS * (punish_dmg * 100.0)
            if whiff_pen < 0:
                bonus_dict["steel_whiff_penalty"] = STEEL_WHIFF_PENALTY

        elif self.personality == "Shadow":
            if SHADOW_PREFERRED_DIST_MIN <= dist <= SHADOW_PREFERRED_DIST_MAX:
                bonus_dict["preferred_spacing"] = SHADOW_PREFERRED_DIST_BONUS
            # Whiff punish: dealt damage while enemy was in recovery or cooldown
            if dmg_dealt > 0 and (f2_prev.recovery > 0 or f2_prev.cooldown > 0):
                bonus_dict["whiff_punish"] = SHADOW_WHIFF_PUNISH_BONUS
            # Evade: backdash / shadow step while the enemy's attack is recovering
            if action in (Action.BACKDASH, Action.SPECIAL_NEUTRAL) and f2_curr.recovery > 0 and dmg_taken <= 0:
                bonus_dict["evade_success"] = SHADOW_EVADE_BONUS
            room_behind = f1_curr.x if f1_curr.x < f2_curr.x else (800.0 - f1_curr.x)
            if room_behind < 75.0:
                bonus_dict["cornered_penalty"] = SHADOW_CORNER_PENALTY

        elif self.personality == "Golden":
            if curr_state.round_over and curr_state.round_result == my_win_key:
                bonus_dict["golden_round_win"] = GOLDEN_ROUND_WIN_BONUS
            if n_read > 0:
                bonus_dict["golden_read_hit"] = GOLDEN_READ_HIT_BONUS * n_read
            if dmg_dealt > 0 and dmg_taken <= 0:
                bonus_dict["tactical_advantage"] = GOLDEN_BALANCED_BONUS

        if not self.use_personality_bonus:
            bonus_dict = {}
        bonus = float(sum(bonus_dict.values()))

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
