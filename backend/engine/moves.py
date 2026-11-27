"""Move system data: frame data, damage, hit levels, strings, and per-character movesets.

ALL move data lives in this file. Balancing means editing numbers here.
Damage is expressed in HP (out of 100 max health). In the engine, health is 0..1,
so health damage is damage / 100.0.
"""

from dataclasses import dataclass, replace
from enum import Enum

from backend.ai.actions import Action


class HitLevel(Enum):
    """Guard level required to block an attack.

    MID:   Can be blocked standing (Action.BLOCK) or crouching (Action.BLOCK_LOW).
    HIGH:  Overhead strike; must be blocked standing (Action.BLOCK). Hits crouching opponents.
    LOW:   Sweep / low strike; must be blocked crouching (Action.BLOCK_LOW). Hits standing opponents.
    THROW: Unblockable by standard guards; beats blocking; loses to attack startup.
    """
    MID = "mid"
    HIGH = "high"
    LOW = "low"
    THROW = "throw"


class CancelType(Enum):
    """Cancel windows for combo chains."""
    CHAIN = "chain"           # Normal into Normal / String
    SPECIAL = "special"       # Normal into Special
    SUPER = "super"           # Special/Normal into Super


@dataclass(frozen=True)
class MoveData:
    """Frame data and combat attributes for a single move."""

    name: str
    action: Action
    damage: float             # In HP (100 HP = full health)
    startup: int              # Frames of wind-up before active hitbox
    active: int               # Frames hitbox is live
    recovery: int             # Recovery frames after active window on whiff
    on_block: int             # Frame advantage on block
    hitstun: int              # Frames victim is stunned on hit
    blockstun: int            # Frames victim is stunned on block
    reach: float              # Reach in pixels
    hit_level: HitLevel       # MID, HIGH, LOW, or THROW
    knockdown: bool = False   # Knocks opponent down to floor
    launch: bool = False      # Launches opponent into air for juggles
    wall_bounce: bool = False # Pops opponent off arena wall for follow-up
    ground_bounce: bool = False # Bounces opponent off floor
    pushback_hit: float = 24.0    # Pixels of separation on hit
    pushback_block: float = 28.0  # Pixels of separation on block
    invulnerable_frames: int = 0  # Invulnerable frames during startup/active
    cancel_windows: tuple[CancelType, ...] = ()
    meter_gain_hit: float = 6.0   # Meter gained on hit
    meter_gain_block: float = 2.0 # Meter gained on block
    meter_cost: float = 0.0       # Meter cost to use move (e.g. 25, 50, 100)
    is_air: bool = False          # Air-only move
    is_crouching: bool = False    # Executed from crouch stance
    is_projectile: bool = False   # Creates a projectile
    projectile_speed: float = 0.0 # Velocity of projectile in px/frame
    projectile_lifetime: int = 0  # Lifetime of projectile in frames
    armor: int = 0                # Hits absorbed without flinching
    is_counter_stance: bool = False # Active counter stance
    # Vertical hitbox (min, max) in px above the attacker's own height (y).
    # None = default for the hit level (see vertical_range).
    hitbox_y: tuple[float, float] | None = None
    anti_air: bool = False        # Beats air attacks during startup/active

    @property
    def health_damage(self) -> float:
        """Damage as a fraction of 1.0 health."""
        return self.damage / 100.0

    @property
    def vertical_range(self) -> tuple[float, float]:
        """Vertical extent of the hitbox, relative to the attacker's height."""
        if self.hitbox_y is not None:
            return self.hitbox_y
        if self.hit_level == HitLevel.LOW:
            return LOW_HITBOX_Y
        return DEFAULT_HITBOX_Y


# Vertical hitbox defaults (px above the attacker's feet).
# Lows hug the floor, so they whiff on anyone who has left the ground.
LOW_HITBOX_Y: tuple[float, float] = (0.0, 30.0)
# Mids / overheads / throws cover the whole standing body and low air.
DEFAULT_HITBOX_Y: tuple[float, float] = (10.0, 120.0)
# "High" attacks aim above a crouching body (60 px) and whiff on crouchers.
HIGH_AIMED_HITBOX_Y: tuple[float, float] = (65.0, 140.0)
# Anti-airs reach far up.
ANTI_AIR_HITBOX_Y: tuple[float, float] = (40.0, 220.0)
# Jump attacks reach down from the attacker's height.
AIR_ATTACK_HITBOX_Y: tuple[float, float] = (-60.0, 40.0)


# ---------------------------------------------------------------------------
# Universal Baseline Moves (Phase 1 & 2)
# ---------------------------------------------------------------------------

UNIVERSAL_MOVES: dict[Action, MoveData] = {
    Action.LIGHT: MoveData(
        name="Jab",
        action=Action.LIGHT,
        damage=2.0,
        startup=3,
        active=2,
        recovery=7,
        on_block=2,
        hitstun=12,
        blockstun=10,  # (2-1) + 7 + 2 = 10 (+2 on block)
        reach=82.0,
        hit_level=HitLevel.MID,
        pushback_hit=16.0,
        pushback_block=20.0,
        cancel_windows=(CancelType.CHAIN, CancelType.SPECIAL, CancelType.SUPER),
        meter_gain_hit=5.0,
        meter_gain_block=2.0,
    ),
    Action.HEAVY: MoveData(
        name="Heavy Punch",
        action=Action.HEAVY,
        damage=8.0,
        startup=10,
        active=4,
        recovery=18,
        on_block=-5,
        hitstun=23,
        blockstun=16,  # (4-1) + 18 - 5 = 16 (-5 on block)
        reach=104.0,
        hit_level=HitLevel.MID,
        pushback_hit=28.0,
        pushback_block=32.0,
        cancel_windows=(CancelType.SPECIAL, CancelType.SUPER),
        meter_gain_hit=10.0,
        meter_gain_block=3.0,
    ),
    Action.LIGHT_KICK: MoveData(
        name="Light Kick",
        action=Action.LIGHT_KICK,
        damage=4.0,
        startup=5,
        active=3,
        recovery=9,
        on_block=0,
        hitstun=14,
        blockstun=11,  # (3-1) + 9 + 0 = 11 (0 on block)
        reach=92.0,
        hit_level=HitLevel.MID,
        pushback_hit=18.0,
        pushback_block=22.0,
        cancel_windows=(CancelType.CHAIN, CancelType.SPECIAL, CancelType.SUPER),
        meter_gain_hit=6.0,
        meter_gain_block=2.0,
    ),
    Action.HEAVY_KICK: MoveData(
        name="Heavy Kick",
        action=Action.HEAVY_KICK,
        damage=10.0,
        startup=12,
        active=4,
        recovery=22,
        on_block=-8,
        hitstun=26,
        blockstun=17,  # (4-1) + 22 - 8 = 17 (-8 on block)
        reach=118.0,
        hit_level=HitLevel.MID,
        pushback_hit=32.0,
        pushback_block=36.0,
        wall_bounce=True,
        hitbox_y=HIGH_AIMED_HITBOX_Y,  # high roundhouse: whiffs on crouchers
        cancel_windows=(CancelType.SPECIAL, CancelType.SUPER),
        meter_gain_hit=12.0,
        meter_gain_block=4.0,
    ),
    Action.LOW_SWEEP: MoveData(
        name="Low Sweep",
        action=Action.LOW_SWEEP,
        damage=6.0,
        startup=8,
        active=3,
        recovery=20,
        on_block=-12,
        hitstun=30,
        blockstun=10,  # (3-1) + 20 - 12 = 10 (-12 on block)
        reach=100.0,
        hit_level=HitLevel.LOW,
        knockdown=True,
        is_crouching=True,
        pushback_hit=24.0,
        pushback_block=26.0,
        cancel_windows=(CancelType.SUPER,),
        meter_gain_hit=8.0,
        meter_gain_block=2.0,
    ),
    Action.OVERHEAD: MoveData(
        name="Overhead Strike",
        action=Action.OVERHEAD,
        damage=7.0,
        startup=14,
        active=3,
        recovery=18,
        on_block=-4,
        hitstun=22,
        blockstun=16,  # (3-1) + 18 - 4 = 16 (-4 on block)
        reach=96.0,
        hit_level=HitLevel.HIGH,
        pushback_hit=22.0,
        pushback_block=26.0,
        cancel_windows=(CancelType.SUPER,),
        meter_gain_hit=9.0,
        meter_gain_block=3.0,
    ),
    Action.CROUCH_JAB: MoveData(
        name="Crouching Jab",
        action=Action.CROUCH_JAB,
        damage=2.0,
        startup=4,
        active=2,
        recovery=8,
        on_block=1,
        hitstun=12,
        blockstun=10,  # (2-1) + 8 + 1 = 10 (+1 on block)
        reach=78.0,
        hit_level=HitLevel.LOW,
        is_crouching=True,
        pushback_hit=14.0,
        pushback_block=18.0,
        cancel_windows=(CancelType.CHAIN, CancelType.SPECIAL, CancelType.SUPER),
        meter_gain_hit=4.0,
        meter_gain_block=1.5,
    ),
    Action.CROUCH_KICK: MoveData(
        name="Crouching Kick",
        action=Action.CROUCH_KICK,
        damage=3.5,
        startup=6,
        active=3,
        recovery=11,
        on_block=-2,
        hitstun=15,
        blockstun=11,  # (3-1) + 11 - 2 = 11 (-2 on block)
        reach=90.0,
        hit_level=HitLevel.LOW,
        is_crouching=True,
        pushback_hit=18.0,
        pushback_block=22.0,
        cancel_windows=(CancelType.CHAIN, CancelType.SPECIAL, CancelType.SUPER),
        meter_gain_hit=5.0,
        meter_gain_block=2.0,
    ),
    Action.JUMP_PUNCH: MoveData(
        name="Jump Punch",
        action=Action.JUMP_PUNCH,
        damage=4.0,
        startup=4,
        active=6,
        recovery=8,
        on_block=2,
        hitstun=16,
        blockstun=15,  # (6-1) + 8 + 2 = 15 (+2 on block)
        reach=86.0,
        hit_level=HitLevel.HIGH,
        is_air=True,
        hitbox_y=AIR_ATTACK_HITBOX_Y,
        pushback_hit=18.0,
        pushback_block=22.0,
        meter_gain_hit=5.0,
        meter_gain_block=2.0,
    ),
    Action.JUMP_KICK: MoveData(
        name="Jump Kick",
        action=Action.JUMP_KICK,
        damage=6.0,
        startup=7,
        active=6,
        recovery=10,
        on_block=0,
        hitstun=18,
        blockstun=15,  # (6-1) + 10 + 0 = 15 (0 on block)
        reach=96.0,
        hit_level=HitLevel.HIGH,
        is_air=True,
        hitbox_y=AIR_ATTACK_HITBOX_Y,
        pushback_hit=22.0,
        pushback_block=26.0,
        meter_gain_hit=7.0,
        meter_gain_block=2.5,
    ),
    Action.ANTI_AIR: MoveData(
        name="Anti-Air Uppercut",
        action=Action.ANTI_AIR,
        damage=8.0,
        startup=6,
        active=4,
        recovery=22,
        on_block=-10,
        hitstun=26,
        blockstun=15,  # (4-1) + 22 - 10 = 15 (-10 on block)
        reach=92.0,
        hit_level=HitLevel.MID,
        launch=True,
        anti_air=True,
        hitbox_y=ANTI_AIR_HITBOX_Y,
        pushback_hit=24.0,
        pushback_block=28.0,
        cancel_windows=(CancelType.SUPER,),
        meter_gain_hit=10.0,
        meter_gain_block=3.0,
    ),
    Action.THROW: MoveData(
        name="Normal Throw",
        action=Action.THROW,
        damage=10.0,
        startup=4,
        active=2,
        recovery=16,
        on_block=0,
        hitstun=30,
        blockstun=0,
        reach=60.0,
        hit_level=HitLevel.THROW,
        knockdown=True,
        pushback_hit=45.0,
        pushback_block=0.0,
        meter_gain_hit=12.0,
        meter_gain_block=0.0,
    ),
    Action.BACKDASH: MoveData(
        name="Backdash",
        action=Action.BACKDASH,
        damage=0.0,
        startup=0,
        active=4,
        recovery=12,
        on_block=0,
        hitstun=0,
        blockstun=0,
        reach=0.0,
        hit_level=HitLevel.MID,
        invulnerable_frames=4,
        pushback_hit=0.0,
        pushback_block=0.0,
    ),
}

# ---------------------------------------------------------------------------
# Character-Specific Signature Moves (Phase 4)
# ---------------------------------------------------------------------------

CRIMSON_SPECIALS: dict[Action, MoveData] = {
    Action.SPECIAL_FORWARD: MoveData(
        name="Crimson Rush",
        action=Action.SPECIAL_FORWARD,
        damage=12.0,
        startup=8,
        active=6,
        recovery=16,
        on_block=-6,
        hitstun=24,
        blockstun=15,
        reach=115.0,
        hit_level=HitLevel.MID,
        pushback_hit=36.0,
        pushback_block=28.0,
        cancel_windows=(CancelType.SUPER,),
        meter_gain_hit=12.0,
        meter_gain_block=4.0,
    ),
    Action.SPECIAL_NEUTRAL: MoveData(
        name="Rising Uppercut",
        action=Action.SPECIAL_NEUTRAL,
        damage=11.0,
        startup=5,
        active=5,
        recovery=24,
        on_block=-13,
        hitstun=28,
        blockstun=15,
        reach=95.0,
        hit_level=HitLevel.MID,
        launch=True,
        anti_air=True,
        hitbox_y=ANTI_AIR_HITBOX_Y,
        pushback_hit=28.0,
        pushback_block=32.0,
        cancel_windows=(CancelType.SUPER,),
        meter_gain_hit=10.0,
        meter_gain_block=3.0,
    ),
    Action.SPECIAL_BACK: MoveData(
        name="Berserker Charge",
        action=Action.SPECIAL_BACK,
        damage=9.0,
        startup=11,
        active=8,
        recovery=18,
        on_block=-7,
        hitstun=22,
        blockstun=18,
        reach=108.0,
        hit_level=HitLevel.MID,
        armor=1,
        pushback_hit=32.0,
        pushback_block=28.0,
        meter_gain_hit=10.0,
        meter_gain_block=3.0,
    ),
    Action.SPECIAL_DOWN: MoveData(
        name="Clinch Slam",
        action=Action.SPECIAL_DOWN,
        damage=14.0,
        startup=7,
        active=3,
        recovery=20,
        on_block=0,
        hitstun=32,
        blockstun=0,
        reach=68.0,
        hit_level=HitLevel.THROW,
        knockdown=True,
        ground_bounce=True,
        pushback_hit=50.0,
        pushback_block=0.0,
        meter_gain_hit=14.0,
        meter_gain_block=0.0,
    ),
    Action.SUPER: MoveData(
        name="Blood Fury",
        action=Action.SUPER,
        damage=32.0,
        startup=5,
        active=12,
        recovery=28,
        on_block=-19,
        hitstun=45,
        blockstun=20,
        reach=128.0,
        hit_level=HitLevel.MID,
        knockdown=True,
        pushback_hit=60.0,
        pushback_block=45.0,
        meter_cost=100.0,
    ),
}

STEEL_SPECIALS: dict[Action, MoveData] = {
    Action.SPECIAL_DOWN: MoveData(
        name="Iron Wall",
        action=Action.SPECIAL_DOWN,
        damage=16.0,
        startup=2,
        active=24,
        recovery=18,
        on_block=-41,
        hitstun=30,
        blockstun=0,
        reach=98.0,
        hit_level=HitLevel.MID,
        is_counter_stance=True,
        knockdown=True,
        pushback_hit=55.0,
        pushback_block=0.0,
        meter_gain_hit=15.0,
    ),
    Action.SPECIAL_FORWARD: MoveData(
        name="Shield Bash",
        action=Action.SPECIAL_FORWARD,
        damage=8.0,
        startup=7,
        active=4,
        recovery=14,
        on_block=-1,
        hitstun=22,
        blockstun=16,
        reach=104.0,
        hit_level=HitLevel.MID,
        pushback_hit=95.0,
        pushback_block=80.0,
        meter_cost=25.0,
        meter_gain_hit=5.0,
    ),
    Action.SPECIAL_NEUTRAL: MoveData(
        name="Punisher Grip",
        action=Action.SPECIAL_NEUTRAL,
        damage=16.0,
        startup=14,
        active=3,
        recovery=24,
        on_block=0,
        hitstun=35,
        blockstun=0,
        reach=72.0,
        hit_level=HitLevel.THROW,
        knockdown=True,
        pushback_hit=60.0,
        pushback_block=0.0,
        meter_gain_hit=15.0,
    ),
    Action.SPECIAL_BACK: MoveData(
        name="Reflector",
        action=Action.SPECIAL_BACK,
        damage=0.0,
        startup=2,
        active=20,
        recovery=16,
        on_block=0,
        hitstun=0,
        blockstun=0,
        reach=75.0,
        hit_level=HitLevel.MID,
        invulnerable_frames=3,
    ),
    Action.SUPER: MoveData(
        name="Fortress Crush",
        action=Action.SUPER,
        damage=35.0,
        startup=3,
        active=30,
        recovery=25,
        on_block=-54,
        hitstun=50,
        blockstun=0,
        reach=110.0,
        hit_level=HitLevel.MID,
        is_counter_stance=True,
        knockdown=True,
        pushback_hit=70.0,
        pushback_block=0.0,
        meter_cost=100.0,
    ),
}

SHADOW_SPECIALS: dict[Action, MoveData] = {
    Action.SPECIAL_FORWARD: MoveData(
        name="Shadow Step",
        action=Action.SPECIAL_FORWARD,
        damage=0.0,
        startup=4,
        active=6,
        recovery=10,
        on_block=0,
        hitstun=0,
        blockstun=0,
        reach=125.0,
        hit_level=HitLevel.MID,
        invulnerable_frames=6,
    ),
    Action.SPECIAL_DOWN: MoveData(
        name="Phantom Kick",
        action=Action.SPECIAL_DOWN,
        damage=11.0,
        startup=6,
        active=7,
        recovery=18,
        on_block=-8,
        hitstun=24,
        blockstun=16,
        reach=105.0,
        hit_level=HitLevel.LOW,
        cancel_windows=(CancelType.SUPER,),
        pushback_hit=32.0,
        pushback_block=26.0,
        meter_gain_hit=12.0,
        meter_gain_block=4.0,
    ),
    Action.SPECIAL_BACK: MoveData(
        name="Feint Strike",
        action=Action.SPECIAL_BACK,
        damage=0.0,
        startup=4,
        active=6,
        recovery=10,
        on_block=0,
        hitstun=0,
        blockstun=0,
        reach=70.0,
        hit_level=HitLevel.MID,
        cancel_windows=(CancelType.CHAIN,),
    ),
    Action.SPECIAL_NEUTRAL: MoveData(
        name="Energy Dart",
        action=Action.SPECIAL_NEUTRAL,
        damage=6.0,
        startup=9,
        active=4,
        recovery=18,
        on_block=-4,
        hitstun=18,
        blockstun=14,
        reach=350.0,
        hit_level=HitLevel.MID,
        is_projectile=True,
        projectile_speed=12.0,
        projectile_lifetime=60,
        cancel_windows=(CancelType.SUPER,),
        pushback_hit=25.0,
        pushback_block=20.0,
        meter_gain_hit=8.0,
        meter_gain_block=2.5,
    ),
    Action.SUPER: MoveData(
        name="Vanishing Arts",
        action=Action.SUPER,
        damage=28.0,
        startup=4,
        active=10,
        recovery=26,
        on_block=-15,
        hitstun=42,
        blockstun=20,
        reach=185.0,
        hit_level=HitLevel.MID,
        knockdown=True,
        pushback_hit=55.0,
        pushback_block=40.0,
        meter_cost=100.0,
    ),
}

GOLDEN_SPECIALS: dict[Action, MoveData] = {
    Action.SPECIAL_DOWN: MoveData(
        name="Tactician Stance",
        action=Action.SPECIAL_DOWN,
        damage=0.0,
        startup=3,
        active=2,
        recovery=6,
        on_block=0,
        hitstun=0,
        blockstun=0,
        reach=0.0,
        hit_level=HitLevel.MID,
    ),
    Action.SPECIAL_NEUTRAL: MoveData(
        name="Golden Read",
        action=Action.SPECIAL_NEUTRAL,
        damage=18.0,
        startup=6,
        active=30,
        recovery=20,
        on_block=-49,
        hitstun=32,
        blockstun=0,
        reach=100.0,
        hit_level=HitLevel.MID,
        knockdown=True,
        pushback_hit=50.0,
        pushback_block=0.0,
        meter_gain_hit=20.0,
    ),
    Action.SPECIAL_FORWARD: MoveData(
        name="Gambit Strike",
        action=Action.SPECIAL_FORWARD,
        damage=14.0,
        startup=11,
        active=4,
        recovery=22,
        on_block=-10,
        hitstun=28,
        blockstun=15,
        reach=110.0,
        hit_level=HitLevel.MID,
        cancel_windows=(CancelType.SUPER,),
        pushback_hit=42.0,
        pushback_block=32.0,
        meter_gain_hit=14.0,
        meter_gain_block=4.0,
    ),
    Action.SPECIAL_BACK: MoveData(
        name="Tactical Step",
        action=Action.SPECIAL_BACK,
        damage=0.0,
        startup=0,
        active=4,
        recovery=10,
        on_block=0,
        hitstun=0,
        blockstun=0,
        reach=0.0,
        hit_level=HitLevel.MID,
        invulnerable_frames=4,
    ),
    Action.SUPER: MoveData(
        name="Checkmate",
        action=Action.SUPER,
        damage=30.0,
        startup=6,
        active=8,
        recovery=26,
        on_block=-15,
        hitstun=45,
        blockstun=18,
        reach=120.0,
        hit_level=HitLevel.MID,
        knockdown=True,
        pushback_hit=60.0,
        pushback_block=45.0,
        meter_cost=100.0,
    ),
}

# ---------------------------------------------------------------------------
# Canned Sequences / Strings per Character (Phase 2)
# ---------------------------------------------------------------------------
CHARACTER_STRINGS: dict[str, list[tuple[Action, ...]]] = {
    "Crimson": [
        (Action.LIGHT, Action.LIGHT, Action.HEAVY),
        (Action.LIGHT_KICK, Action.HEAVY_KICK),
        (Action.CROUCH_JAB, Action.CROUCH_KICK, Action.LOW_SWEEP),
    ],
    "Steel": [
        (Action.LIGHT, Action.LIGHT_KICK, Action.HEAVY),
        (Action.CROUCH_JAB, Action.CROUCH_KICK),
        (Action.LIGHT_KICK, Action.HEAVY_KICK),
    ],
    "Shadow": [
        (Action.CROUCH_JAB, Action.LIGHT, Action.LIGHT_KICK),
        (Action.LIGHT, Action.LIGHT, Action.LIGHT_KICK),
        (Action.LIGHT_KICK, Action.HEAVY_KICK),
    ],
    "Golden": [
        (Action.LIGHT, Action.LIGHT_KICK, Action.HEAVY),
        (Action.CROUCH_KICK, Action.LOW_SWEEP),
        (Action.LIGHT, Action.HEAVY),
    ],
}


def _create_character_moveset(
    damage_scale: float,
    reach_scale: float,
    specials: dict[Action, MoveData],
) -> dict[Action, MoveData]:
    """Scale universal baseline moves and add character specials."""
    moveset: dict[Action, MoveData] = {}
    for action, base in UNIVERSAL_MOVES.items():
        if action == Action.BACKDASH:
            moveset[action] = base
            continue

        scaled = replace(
            base,
            damage=round(base.damage * damage_scale, 2),
            reach=round(base.reach * reach_scale, 1),
        )
        moveset[action] = scaled

    # Merge character-specific signature moves and supers
    moveset.update(specials)
    return moveset


# Per-character movesets: one dict per character
CHARACTER_MOVES: dict[str, dict[Action, MoveData]] = {
    "Crimson": _create_character_moveset(
        damage_scale=1.2, reach_scale=0.9, specials=CRIMSON_SPECIALS
    ),
    "Steel": _create_character_moveset(
        damage_scale=1.0, reach_scale=1.0, specials=STEEL_SPECIALS
    ),
    "Shadow": _create_character_moveset(
        damage_scale=0.85, reach_scale=1.15, specials=SHADOW_SPECIALS
    ),
    "Golden": _create_character_moveset(
        damage_scale=1.0, reach_scale=1.0, specials=GOLDEN_SPECIALS
    ),
}


def get_move(character_name: str, action: Action) -> MoveData | None:
    """Retrieve the move data for a character and action."""
    moves = CHARACTER_MOVES.get(character_name, CHARACTER_MOVES["Golden"])
    return moves.get(action)
