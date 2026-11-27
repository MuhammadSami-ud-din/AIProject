"""Shared building blocks for the four rule-based fighters (Crimson/Steel/Shadow/Golden).

Every fighter used to repeat the same long if/elif chain with the same guards
and magic numbers. The template and the shared rules live here; each fighter
only supplies its own numbers (``FighterTuning``) and the moves that really
differ (movement, signature specials, panic behaviour).
"""

from dataclasses import dataclass
from typing import Dict, Optional

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.observation import Observation
from backend.ai.zones import ZoneTracker

# ---------------------------------------------------------------
# Shared constants (pixels / frames / meter)
# ---------------------------------------------------------------
THROW_RANGE = 48.0              # throws and command grabs only connect this close
JUMP_ATTACK_RANGE = 95.0        # air normals connect within this distance
SUPER_COST = 100.0
FURY_SUPER_COST = 60.0          # below FURY_HEALTH the super is cheaper
FURY_HEALTH = 0.25
BURST_METER = 50.0
BURST_MIN_HITSTUN = 10          # only burst out of real combos
DISABLED = 0.0                  # score for a move that makes no sense now
HEIGHT_WHIFF_MULT = 0.3         # move that cannot connect at the enemy's height
OUT_OF_RANGE = 0.2              # small score so a move is never exactly impossible

LIGHT_FAMILY = (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB, Action.CROUCH_KICK)
HEAVY_FAMILY = (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD)
JUMP_ATTACKS = (Action.JUMP_PUNCH, Action.JUMP_KICK)
SPECIALS = (Action.SPECIAL_NEUTRAL, Action.SPECIAL_FORWARD, Action.SPECIAL_BACK,
            Action.SPECIAL_DOWN, Action.SUPER)


GROUND_ATTACKS = LIGHT_FAMILY + HEAVY_FAMILY + (Action.ANTI_AIR, Action.THROW) + SPECIALS


class _Skip(float):
    """Sentinel returned by score_special meaning "move not available"."""


SKIP = _Skip(-1.0)


# ---------------------------------------------------------------
# Shared guards / helpers
# ---------------------------------------------------------------
def can_ground_attack(obs: Observation) -> bool:
    """Ground attacks need: attack ready and feet on the floor."""
    return obs.can_attack and not obs.my_in_air


def super_cost(obs: Observation) -> float:
    return FURY_SUPER_COST if obs.my_health < FURY_HEALTH else SUPER_COST


def can_burst(obs: Observation, max_health: float) -> bool:
    """Burst out of a real combo when low on health and meter allows."""
    return obs.my_hitstun > BURST_MIN_HITSTUN and obs.my_meter >= BURST_METER and obs.my_health < max_health


def light_variant(base: float, action: Action, obs: Observation) -> float:
    """The four light normals share a base score with small situational tweaks."""
    if action == Action.LIGHT:
        return base
    if action == Action.LIGHT_KICK:
        return base * 0.97
    if action == Action.CROUCH_KICK:   # low hit beats a standing block
        return base * (1.02 if obs.enemy_is_blocking and not obs.enemy_is_crouching else 0.94)
    return base * 0.93                 # CROUCH_JAB


def heavy_variant(base: float, action: Action, obs: Observation) -> float:
    """Heavy normals: sweep beats standing block, overhead beats crouching.

    Engine height axis: sweeps miss airborne enemies and Heavy Kick whiffs over
    crouchers, so those cases are scored down hard.
    """
    if action == Action.HEAVY:
        return base
    if action == Action.HEAVY_KICK:
        return base * (HEIGHT_WHIFF_MULT if obs.enemy_is_crouching else 0.97)
    if action == Action.LOW_SWEEP:
        if obs.enemy_in_air:
            return base * HEIGHT_WHIFF_MULT
        return base * (1.03 if obs.enemy_is_blocking and not obs.enemy_is_crouching else 0.94)
    return base * (1.03 if obs.enemy_is_crouching else 0.93)   # OVERHEAD


@dataclass(frozen=True)
class FighterTuning:
    """Per-fighter numbers for the moves every fighter scores the same way."""
    anti_air_hit: float          # enemy jumping and in reach
    anti_air_close: float        # close but enemy grounded
    anti_air_range: float
    throw_vs_block: float
    throw_normal: float
    jump_kick: float
    jump_punch: float
    jump_far: float
    jump_attack_range: float = JUMP_ATTACK_RANGE
    crouch_far: float = 0.2
    burst_health: float = 0.40
    idle: float = 0.1


class FSMFighter(Agent):
    """Template: rumble/shield checks -> score every action -> RL-adjusted pick."""

    TUNING: FighterTuning

    def __init__(self, name, personality, player=1, difficulty="LOW", seed=None):
        super().__init__(name=name, player=player, difficulty=difficulty,
                         personality=personality, seed=seed)
        self.zone_tracker = ZoneTracker()

    def reset(self):
        super().reset()
        self.zone_tracker.reset()

    # ---- hooks ---------------------------------------------------
    def shield_prediction(self, obs: Observation) -> Optional[bool]:
        """Golden passes its attack prediction to the shield AI; others don't."""
        return None

    def score_special(self, action: Action, obs: Observation, zone) -> Optional[float]:
        """Fighter-specific movement / specials. Return None to use the shared rule."""
        return None

    def panic_multiplier(self, action: Action) -> float:
        return 1.0

    # ---- shared rules ---------------------------------------------
    def score_common(self, action: Action, obs: Observation, zone) -> Optional[float]:
        """Shared scoring. Returns None when the move is not available (skip it)."""
        t = self.TUNING
        if action == Action.ANTI_AIR:
            if obs.enemy_in_air and obs.i_can_hit:
                return t.anti_air_hit
            return t.anti_air_close if obs.distance <= t.anti_air_range else OUT_OF_RANGE
        if action == Action.THROW:
            if obs.distance > THROW_RANGE:
                return OUT_OF_RANGE
            return t.throw_vs_block if obs.enemy_is_blocking else t.throw_normal
        if action in JUMP_ATTACKS:
            if not obs.my_in_air or not obs.can_attack:
                return None
            if obs.distance > t.jump_attack_range:
                return t.jump_far
            return t.jump_kick if action == Action.JUMP_KICK else t.jump_punch
        if action == Action.CROUCH:
            if obs.my_in_air:
                return None
            return 1.0 if obs.i_can_hit else t.crouch_far
        if action == Action.BURST:
            return 10.0 if can_burst(obs, t.burst_health) else DISABLED
        if action == Action.IDLE:
            return t.idle
        return DISABLED

    def score_action(self, action: Action, obs: Observation, zone) -> Optional[float]:
        if action in GROUND_ATTACKS and not can_ground_attack(obs):
            return None
        special = self.score_special(action, obs, zone)
        if special is not None:
            return None if special is SKIP else special
        return self.score_common(action, obs, zone)

    def choose_action(self, obs: Observation):
        """Score every allowed action, then pick one."""
        from backend.ai.rumble_ai import evaluate_rumble_macro

        rumble_act = evaluate_rumble_macro(obs, self.name, self.difficulty, self.rng)
        if rumble_act is not None:
            return rumble_act, {rumble_act: 10.0}

        if obs.enable_shield_wall:
            from backend.ai.shield_ai import evaluate_shield_action

            pred = self.shield_prediction(obs)
            kwargs = {} if pred is None else {"predicted_enemy_attack": pred}
            shield_act = evaluate_shield_action(obs, self.name, self.difficulty, self.rng, **kwargs)
            if shield_act is not None:
                return shield_act, {shield_act: 10.0}

        zone = self.zone_tracker.update(obs.distance)
        panicking = obs.is_panicking(self.personality)
        scores: Dict[Action, float] = {}
        for action in ALL_ACTIONS:
            score = self.score_action(action, obs, zone)
            if score is None:
                continue
            if panicking:
                score *= self.panic_multiplier(action)
            scores[action] = score

        return self._select_action_with_rl_and_diversity(scores, obs, variety=self.personality.variety)
