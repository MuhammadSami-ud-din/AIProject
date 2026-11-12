"""Each fighter's character card: what it likes and how it behaves, as numbers."""

import dataclasses
from dataclasses import dataclass

from backend.ai.zones import ARENA_WIDTH

# The six things a fighter can care about. Used by the scoring code later.
LIKE_FIELDS = (
    "health_lead",
    "closeness",
    "safe_distance",
    "block_punish",
    "corner_avoid",
    "time_pressure",
)

# The style numbers. Together with LIKE_FIELDS they are the fighter's "genome".
STYLE_FIELDS = (
    "preferred_distance",
    "panic_health",
    "panic_aggression",
    "variety",
)

# The full "genome": every number that makes a fighter different.
GENOME_FIELDS = LIKE_FIELDS + STYLE_FIELDS

# Lowest and highest allowed value for each genome number (used by mutate).
GENOME_LIMITS = {
    **{field: (0, 10) for field in LIKE_FIELDS},
    "preferred_distance": (10, ARENA_WIDTH),
    "panic_health": (0, 1),
    "panic_aggression": (0.1, 3),
    "variety": (0, 1),
}


@dataclass(frozen=True)
class Personality:
    name: str          # short name used in code, like "Crimson"
    full_name: str     # name shown on screen, like "Crimson Brawler"
    description: str   # one line for the character-select screen

    # What this fighter likes, from 0 (doesn't care) to 10 (cares a lot)
    health_lead: float     # having more health than the enemy
    closeness: float       # being near the enemy
    safe_distance: float   # staying at its favourite distance
    block_punish: float    # blocking, then hitting back
    corner_avoid: float    # staying away from the walls (not getting trapped)
    time_pressure: float   # playing safe when ahead and the timer is low

    # Style settings
    preferred_distance: float  # favourite distance from the enemy, in pixels
    panic_health: float        # panic mode starts below this health (0.25 = 25%)
    panic_aggression: float    # in panic: above 1 attacks more, below 1 plays safer
    variety: float             # 0 = always the best move, 1 = mixes moves a lot

    adapts: bool = False       # True only for Golden: changes its likes during a fight
    adapt_speed: float = 0.0   # how fast Golden changes (0 to 1)

    def __post_init__(self):
        for field in LIKE_FIELDS:
            value = getattr(self, field)
            if not 0 <= value <= 10:
                raise ValueError(f"{self.name}: {field} must be between 0 and 10, got {value}")
        if self.preferred_distance <= 0:
            raise ValueError(f"{self.name}: preferred_distance must be above 0")
        if not 0 <= self.panic_health <= 1:
            raise ValueError(f"{self.name}: panic_health must be between 0 and 1")
        if self.panic_aggression <= 0:
            raise ValueError(f"{self.name}: panic_aggression must be above 0")
        if not 0 <= self.variety <= 1:
            raise ValueError(f"{self.name}: variety must be between 0 and 1")
        if not 0 <= self.adapt_speed <= 1:
            raise ValueError(f"{self.name}: adapt_speed must be between 0 and 1")
        if self.adapts and self.adapt_speed == 0:
            raise ValueError(f"{self.name}: a fighter that adapts needs adapt_speed above 0")

    def likes(self):
        """Return the six likes as a dictionary, like {"closeness": 9, ...}."""
        return {field: getattr(self, field) for field in LIKE_FIELDS}

    def genome(self):
        """All of this fighter's numbers as one list, in GENOME_FIELDS order."""
        return [getattr(self, field) for field in GENOME_FIELDS]


# Starting numbers. They will be tuned later by testing.
CRIMSON = Personality(
    name="Crimson",
    full_name="Crimson Brawler",
    description="Aggressive rusher: high damage, short range.",
    health_lead=8, closeness=9, safe_distance=1,
    block_punish=1, corner_avoid=2, time_pressure=3,
    preferred_distance=60, panic_health=0.25, panic_aggression=1.5, variety=0.2,
)

STEEL = Personality(
    name="Steel",
    full_name="Steel Guardian",
    description="Defensive counter-fighter: blocks and punishes.",
    health_lead=5, closeness=2, safe_distance=3,
    block_punish=9, corner_avoid=6, time_pressure=7,
    preferred_distance=120, panic_health=0.30, panic_aggression=0.7, variety=0.1,
)

SHADOW = Personality(
    name="Shadow",
    full_name="Shadow Striker",
    description="Fast, evasive hit-and-run fighter.",
    health_lead=5, closeness=1, safe_distance=9,
    block_punish=3, corner_avoid=9, time_pressure=5,
    preferred_distance=200, panic_health=0.30, panic_aggression=0.8, variety=0.3,
)

GOLDEN = Personality(
    name="Golden",
    full_name="Golden Tactician",
    description="Balanced fighter that adapts its style to the opponent.",
    health_lead=6, closeness=5, safe_distance=5,
    block_punish=5, corner_avoid=5, time_pressure=5,
    preferred_distance=130, panic_health=0.25, panic_aggression=1.0, variety=0.4,
    adapts=True, adapt_speed=0.1,
)

ALL_PERSONALITIES = {p.name: p for p in (CRIMSON, STEEL, SHADOW, GOLDEN)}


def mix(a, b, share_of_a=0.5, name=None):
    """Make a new fighter by blending two cards (the "personality genome" idea).
    share_of_a = 0.5 is half and half; 0.8 is mostly a."""
    if not 0 <= share_of_a <= 1:
        raise ValueError(f"share_of_a must be between 0 and 1, got {share_of_a}")

    def blend(field):
        return share_of_a * getattr(a, field) + (1 - share_of_a) * getattr(b, field)

    numbers = {field: blend(field) for field in LIKE_FIELDS + STYLE_FIELDS}
    adapt_speed = blend("adapt_speed")
    return Personality(
        name=name or f"{a.name}-{b.name}",
        full_name=f"{a.full_name} x {b.full_name}",
        description=f"A mix of {a.name} and {b.name}.",
        adapts=adapt_speed > 0,
        adapt_speed=adapt_speed,
        **numbers,
    )


def from_genome(numbers, name="Custom", adapt_speed=0.0):
    """Build a fighter from a list of numbers (the opposite of genome())."""
    if len(numbers) != len(GENOME_FIELDS):
        raise ValueError(f"a genome needs {len(GENOME_FIELDS)} numbers, got {len(numbers)}")
    return Personality(
        name=name,
        full_name=name,
        description="Made from a genome.",
        adapts=adapt_speed > 0,
        adapt_speed=adapt_speed,
        **dict(zip(GENOME_FIELDS, numbers, strict=True)),
    )


def mutate(personality, rng, amount=0.1, name=None):
    """A copy with small random changes to every genome number.
    Used by the genetic algorithm / co-evolution: change a little,
    keep the change if the new fighter wins more.
    amount 0.1 = changes of about 10% of each number's allowed range."""
    if not 0 <= amount <= 1:
        raise ValueError(f"amount must be between 0 and 1, got {amount}")
    changes = {}
    for field in GENOME_FIELDS:
        low, high = GENOME_LIMITS[field]
        new_value = getattr(personality, field) + rng.gauss(0, amount * (high - low))
        changes[field] = max(low, min(high, new_value))
    return dataclasses.replace(personality, name=name or personality.name, **changes)
