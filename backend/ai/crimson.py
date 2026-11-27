"""Crimson Brawler AI: rushes in and chains attacks.

Crimson loves being close to the enemy and hitting hard.
In panic mode (low health), Crimson gets even MORE aggressive.
"""

from backend.ai.actions import Action
from backend.ai.fsm_base import (
    DISABLED, HEAVY_FAMILY, LIGHT_FAMILY, OUT_OF_RANGE, THROW_RANGE,
    FighterTuning, FSMFighter, heavy_variant, light_variant, super_cost,
)
from backend.ai.observation import Observation
from backend.ai.personalities import CRIMSON
from backend.ai.zones import Zone

HEAVY_REACH = 85.0          # Crimson's heavies connect within this distance
DASH_MULT = 1.3             # Crimson prefers dashing in over walking


class CrimsonAgent(FSMFighter):
    """Aggressive rush-down fighter."""

    TUNING = FighterTuning(
        anti_air_hit=9.5, anti_air_close=7.0, anti_air_range=65.0,
        throw_vs_block=9.6, throw_normal=8.6,
        jump_kick=8.8, jump_punch=8.5, jump_far=1.5,
        burst_health=0.40, idle=0.1,
    )

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__("Crimson", CRIMSON, player=player, difficulty=difficulty, seed=seed)

    def score_special(self, action: Action, obs: Observation, zone):
        if action in (Action.FORWARD, Action.DASH):
            mult = DASH_MULT if action == Action.DASH else 1.0
            if zone == Zone.FAR:
                return 9.0 * mult
            if zone == Zone.MID:
                return 7.0 * mult
            return 4.0 * mult if not obs.i_can_hit else 1.0
        if action in (Action.BACK, Action.BACKDASH):
            return 0.3
        if action == Action.JUMP:
            if zone == Zone.FAR:
                return 3.0
            return 2.0 if obs.enemy_is_attacking and obs.distance <= 60 else 0.3
        if action in HEAVY_FAMILY:
            in_reach = obs.distance <= HEAVY_REACH
            base = (10.0 if obs.enemy_is_stuck else 9.5) if in_reach else 0.5
            return heavy_variant(base, action, obs)
        if action in LIGHT_FAMILY:
            if obs.i_can_hit:
                base = 9.5 if obs.enemy_is_stuck else 8.8
            else:
                base = 4.0 if zone == Zone.CLOSE else 0.5
            return light_variant(base, action, obs)
        if action in (Action.BLOCK, Action.BLOCK_LOW):
            if obs.my_in_air:
                return DISABLED
            if obs.enemy_can_hit and obs.enemy_is_attacking:
                return 7.0 if action == Action.BLOCK else 6.2
            return 0.5 if action == Action.BLOCK else 0.3
        if action == Action.SUPER:          # Blood Fury 8-hit finisher
            if obs.my_meter >= super_cost(obs) and obs.distance <= 110:
                return 10.5 if obs.enemy_hitstun > 0 else 9.2
            return DISABLED
        if action == Action.SPECIAL_FORWARD:  # Crimson Rush (dash punch / combo confirm)
            if obs.distance <= 98:
                return 9.8 if obs.enemy_hitstun > 0 else 8.9
            return 1.2
        if action == Action.SPECIAL_NEUTRAL:  # Rising Uppercut (anti-air launcher)
            if obs.enemy_in_air and obs.distance <= 75:
                return 10.0
            return 8.7 if obs.distance <= 68 else 0.5
        if action == Action.SPECIAL_BACK:     # Berserker Charge (armored rushdown)
            if obs.enemy_is_attacking and obs.distance <= 90:
                return 9.2
            return 8.4 if obs.distance <= 85 else 3.5
        if action == Action.SPECIAL_DOWN:     # Clinch Slam (command grab, beats block)
            if obs.distance <= THROW_RANGE + 4:
                return 9.8 if obs.enemy_is_blocking else 8.5
            return OUT_OF_RANGE
        return None

    def panic_multiplier(self, action: Action) -> float:
        # Panic: even MORE aggressive
        if action in (Action.HEAVY, Action.HEAVY_KICK, Action.LIGHT, Action.FORWARD, Action.DASH):
            return self.personality.panic_aggression
        if action in (Action.BLOCK, Action.BLOCK_LOW):
            return 0.5
        return 1.0
