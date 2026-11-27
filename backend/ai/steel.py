"""Steel Guardian AI: waits, blocks, and punishes mistakes.

Steel is a defensive counter-fighter.
Steel prefers to stand at mid range, block incoming attacks,
and counter-hit during the enemy's recovery.
"""

from backend.ai.actions import Action
from backend.ai.fsm_base import (
    DISABLED, HEAVY_FAMILY, LIGHT_FAMILY, OUT_OF_RANGE, FighterTuning, FSMFighter,
    heavy_variant, light_variant, super_cost,
)
from backend.ai.observation import Observation
from backend.ai.personalities import STEEL
from backend.ai.zones import Zone

SHIELD_BASH_COST = 25.0
WARY_RANGE = 160.0           # specials and projectiles reach this far
WHIFF_PUNISH_RANGE = 140.0
LOW_ATTACKS = (Action.LOW_SWEEP, Action.CROUCH_JAB, Action.CROUCH_KICK, Action.SPECIAL_DOWN)
GRAB_RANGE = 55.0


class SteelAgent(FSMFighter):
    """Defensive counter-fighter."""

    TUNING = FighterTuning(
        anti_air_hit=9.0, anti_air_close=6.5, anti_air_range=65.0,
        throw_vs_block=9.0, throw_normal=7.2,
        jump_kick=8.0, jump_punch=7.7, jump_far=1.0,
        burst_health=0.45, idle=0.5,
    )

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__("Steel", STEEL, player=player, difficulty=difficulty, seed=seed)

    def score_special(self, action: Action, obs: Observation, zone):
        if action in (Action.FORWARD, Action.DASH):
            # Steel walks in patiently to its poke range (it does not dash in
            # from far like Crimson, but it no longer dithers at mid range).
            if obs.i_can_hit:
                return 0.5
            if obs.enemy_is_stuck and obs.distance <= WHIFF_PUNISH_RANGE:
                return 6.0 if action == Action.DASH else 5.5   # close in on a whiff
            if obs.enemy_is_attacking and obs.distance <= WARY_RANGE:
                return 1.0                                     # never walk into an active attack
            if zone == Zone.FAR:
                return 4.0
            return 3.5 if zone == Zone.CLOSE else 3.0
        if action in (Action.BACK, Action.BACKDASH):
            # Retreat only from real pressure while Steel cannot answer it.
            under_pressure = obs.enemy_can_hit and obs.enemy_is_attacking and not obs.can_attack
            if obs.i_am_cornered:
                return 0.3
            return 4.0 if zone == Zone.CLOSE and under_pressure and not obs.enemy_is_stuck else 1.0
        if action == Action.JUMP:
            return 4.0 if obs.i_am_cornered and obs.enemy_can_hit else 0.5
        if action in LIGHT_FAMILY:
            if obs.enemy_is_stuck and obs.i_can_hit:
                base = 10.0             # the block-punish!
            elif obs.enemy_is_open and obs.i_can_hit:
                base = 8.8
            else:
                base = 7.8 if obs.i_can_hit else 0.3
            return light_variant(base, action, obs)
        if action in HEAVY_FAMILY:
            if obs.enemy_is_stuck and obs.i_can_hit:
                base = 9.8              # big punish!
            else:
                base = 7.6 if obs.i_can_hit else 0.2
            return heavy_variant(base, action, obs)
        if action in (Action.BLOCK, Action.BLOCK_LOW):
            if obs.my_in_air:
                return DISABLED
            # Guard the right height: low attacks / crouching enemies need a low block.
            low_threat = obs.enemy_is_crouching or obs.enemy_last_action in LOW_ATTACKS
            right_height = (action == Action.BLOCK_LOW) == low_threat
            if obs.enemy_can_hit and obs.enemy_is_attacking:
                # When Steel can answer straight away it prefers the counter-poke;
                # when it cannot (cooldown/recovery) it holds the correct guard.
                strong = 8.0 if not obs.can_attack else 6.0
                return strong if right_height else strong * 0.6
            if obs.enemy_is_attacking and obs.distance <= WARY_RANGE and not obs.enemy_is_stuck:
                return 5.0 if right_height else 3.0           # long-reach specials / projectiles
            if obs.enemy_can_hit:
                return 3.0 if action == Action.BLOCK else 2.5
            return 1.0 if action == Action.BLOCK else 0.7
        if action == Action.SPECIAL_DOWN:      # Iron Wall counter stance
            if obs.enemy_can_hit and obs.enemy_is_attacking and obs.enemy_recovery == 0:
                return 8.8
            return 6.8 if obs.distance <= 78 else OUT_OF_RANGE
        if action == Action.SPECIAL_FORWARD:   # Shield Bash (costs meter)
            if obs.my_meter >= SHIELD_BASH_COST and obs.distance <= 85:
                return 9.8 if obs.i_am_cornered else 7.8
            return OUT_OF_RANGE
        if action == Action.SPECIAL_NEUTRAL:   # Punisher Grip: command grab
            if obs.distance <= GRAB_RANGE:
                return 9.6 if obs.enemy_is_blocking else 7.4
            return OUT_OF_RANGE
        if action == Action.SPECIAL_BACK:      # Reflector
            return 9.5 if obs.enemy_last_action == Action.SPECIAL_NEUTRAL else 0.1
        if action == Action.SUPER:             # Fortress Crush counter super
            if obs.my_meter >= super_cost(obs) and obs.enemy_can_hit and obs.enemy_is_attacking:
                return 10.5
            return DISABLED
        return None

    def panic_multiplier(self, action: Action) -> float:
        # Panic: turtle up
        if action in (Action.BLOCK, Action.BLOCK_LOW):
            return 1.5
        if action in (Action.FORWARD, Action.DASH):
            return 0.5
        return 1.0
