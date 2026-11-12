"""Body stats for each of the four fighters.

The engine uses these to adjust base attack damage, reach, and walk speed.
Each fighter is just a set of multipliers applied to the constants.
"""

from dataclasses import dataclass

from backend.engine.constants import (
    BLOCK_DAMAGE_RATIO,
    HEAVY_ATTACK,
    LIGHT_ATTACK,
    WALK_SPEED,
    AttackData,
)


@dataclass(frozen=True)
class CharacterStats:
    """How a fighter's body differs from the default.

    Every number is a multiplier: 1.0 means 'normal'.
    blocked_damage_ratio overrides the global BLOCK_DAMAGE_RATIO
    so Steel can take less chip damage from blocked hits.
    """
    name: str
    damage_mult: float = 1.0       # multiplied with attack damage
    reach_mult: float = 1.0        # multiplied with attack reach
    speed_mult: float = 1.0        # multiplied with walk speed
    blocked_damage_ratio: float = BLOCK_DAMAGE_RATIO  # how much damage gets through a block


# ---------------------------------------------------------------
# The four original fighters
# ---------------------------------------------------------------

# Crimson Brawler: hits harder but has shorter arms.
CRIMSON_STATS = CharacterStats(
    name="Crimson",
    damage_mult=1.2,
    reach_mult=0.9,
)

# Steel Guardian: takes half damage when blocking.
STEEL_STATS = CharacterStats(
    name="Steel",
    blocked_damage_ratio=BLOCK_DAMAGE_RATIO * 0.5,  # 5% instead of 10%
)

# Shadow Striker: faster and longer arms, but hits softer.
SHADOW_STATS = CharacterStats(
    name="Shadow",
    damage_mult=0.85,
    reach_mult=1.15,
    speed_mult=1.3,
)

# Golden Tactician: perfectly average in every way.
GOLDEN_STATS = CharacterStats(
    name="Golden",
)

# Look up a fighter's body stats by name.
CHARACTER_STATS = {
    "Crimson": CRIMSON_STATS,
    "Steel": STEEL_STATS,
    "Shadow": SHADOW_STATS,
    "Golden": GOLDEN_STATS,
}


# ---------------------------------------------------------------
# Helper: apply a character's multipliers to a base attack
# ---------------------------------------------------------------

def adjusted_attack(base_attack: AttackData, stats: CharacterStats) -> AttackData:
    """Return a copy of the attack with this character's multipliers applied.

    For example, Crimson's light attack does 0.05 * 1.2 = 0.06 damage
    and reaches 70 * 0.9 = 63 pixels.
    """
    return AttackData(
        damage=base_attack.damage * stats.damage_mult,
        reach=base_attack.reach * stats.reach_mult,
        startup=base_attack.startup,
        active=base_attack.active,
        recovery=base_attack.recovery,
        cooldown=base_attack.cooldown,
    )


def walk_speed(stats: CharacterStats) -> float:
    """How fast this character walks, in pixels per frame."""
    return WALK_SPEED * stats.speed_mult


def light_attack_for(stats: CharacterStats) -> AttackData:
    """This character's light attack with multipliers applied."""
    return adjusted_attack(LIGHT_ATTACK, stats)


def heavy_attack_for(stats: CharacterStats) -> AttackData:
    """This character's heavy attack with multipliers applied."""
    return adjusted_attack(HEAVY_ATTACK, stats)
