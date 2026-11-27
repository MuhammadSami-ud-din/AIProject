"""Shadow Striker AI: fast movement, long reach, poke and retreat.

Shadow is a hit-and-run fighter.
Shadow uses superior speed and reach to stay at the edge of attack range,
poking with safe attacks and escaping before the enemy can hit back.
In panic mode, Shadow runs away and looks for long-range pokes.
"""

from backend.ai.actions import Action
from backend.ai.fsm_base import (
    DISABLED, HEAVY_FAMILY, LIGHT_FAMILY, FighterTuning, FSMFighter,
    heavy_variant, light_variant, super_cost,
)
from backend.ai.observation import Observation
from backend.ai.personalities import SHADOW
from backend.ai.zones import Zone

HEAVY_REACH = 115.0         # Shadow's long limbs
SUPER_REACH = 180.0         # Vanishing Arts teleports in


class ShadowAgent(FSMFighter):
    """Fast hit-and-run fighter."""

    TUNING = FighterTuning(
        anti_air_hit=9.2, anti_air_close=6.8, anti_air_range=70.0,
        throw_vs_block=8.8, throw_normal=7.6,
        jump_kick=8.8, jump_punch=8.5, jump_far=1.0, jump_attack_range=98.0,
        crouch_far=0.3, burst_health=0.40, idle=0.1,
    )

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__("Shadow", SHADOW, player=player, difficulty=difficulty, seed=seed)

    def score_special(self, action: Action, obs: Observation, zone):
        if action in (Action.FORWARD, Action.DASH):
            mult = 1.2 if action == Action.DASH else 1.0
            if obs.enemy_is_stuck and not obs.i_can_hit:
                return 8.0 * mult     # rush in to punish
            if zone == Zone.FAR:
                return 9.0 * mult
            if zone == Zone.MID:
                return 7.0 * mult
            return 5.0 * mult if not obs.i_can_hit else 1.0
        if action in (Action.BACK, Action.BACKDASH):
            mult = 1.3 if action == Action.BACKDASH else 1.0
            if obs.my_recovery > 0:
                return 0.3
            if obs.i_am_cornered:
                return 0.2
            return (4.0 if zone == Zone.CLOSE and obs.my_cooldown > 0 else 0.8) * mult
        if action == Action.JUMP:
            if obs.i_am_cornered:
                return 7.0
            return 3.0 if obs.enemy_is_attacking and zone == Zone.CLOSE else 0.5
        if action in LIGHT_FAMILY:
            if obs.is_safe_poke or (obs.i_can_hit and obs.enemy_is_stuck):
                base = 10.0
            elif obs.i_can_hit:
                base = 9.0
            elif obs.enemy_is_open and zone == Zone.MID:
                base = 4.0
            else:
                base = 0.5
            return light_variant(base, action, obs)
        if action in HEAVY_FAMILY:
            in_reach = obs.distance <= HEAVY_REACH
            if not in_reach:
                base = 0.2
            elif obs.enemy_is_stuck:
                base = 9.8
            else:
                base = 8.8 if obs.enemy_is_open else 8.4
            return heavy_variant(base, action, obs)
        if action in (Action.BLOCK, Action.BLOCK_LOW):
            if obs.my_in_air:
                return DISABLED
            if obs.enemy_can_hit and obs.enemy_is_attacking:
                return 7.0 if action == Action.BLOCK else 6.2
            return 0.5 if action == Action.BLOCK else 0.3
        if action == Action.SPECIAL_NEUTRAL:   # Energy Dart: projectile zoner
            return 9.5 if zone in (Zone.FAR, Zone.MID) else 6.5
        if action == Action.SPECIAL_FORWARD:   # Shadow Step: cross-up / corner escape
            if obs.i_am_cornered and obs.distance <= 130:
                return 9.5
            if zone == Zone.CLOSE and obs.enemy_is_attacking:
                return 8.8
            return 8.2 if obs.distance <= HEAVY_REACH else 0.8
        if action == Action.SPECIAL_DOWN:      # Phantom Kick: low string mixup
            return 8.9 if obs.distance <= 90 else 0.5
        if action == Action.SPECIAL_BACK:      # Feint Strike: bait and reposition
            return 8.2 if zone == Zone.CLOSE else 0.5
        if action == Action.SUPER:             # Vanishing Arts
            if obs.my_meter >= super_cost(obs) and obs.distance <= SUPER_REACH:
                return 10.5 if obs.enemy_is_stuck or obs.enemy_hitstun > 0 else 7.0
            return DISABLED
        return None

    def panic_multiplier(self, action: Action) -> float:
        # Panic: run away!
        if action in (Action.BACK, Action.BACKDASH):
            return 2.0
        if action in (Action.FORWARD, Action.DASH):
            return 0.3
        return 1.0
