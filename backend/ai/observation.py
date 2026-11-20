"""What a fighter sees in one frame, from its own point of view."""

from dataclasses import dataclass, replace

from backend.ai import zones
from backend.ai.actions import ATTACKS, DEFENCE, Action

# ---------------------------------------------------------------
# Settings. Check these with Haseeb.
# ---------------------------------------------------------------
FRAMES_PER_SECOND = 60
ROUND_SECONDS = 60     # length of one round
LOW_TIME = 10          # seconds left that count as "time is running out"
WINS_NEEDED = 2        # rounds needed to win the match

LOG_SCHEMA_VERSION = 3

# The numbers given to the learning code, always in this order.
FEATURE_NAMES = (
    "distance",
    "my_health",
    "enemy_health",
    "health_lead",
    "my_cooldown",
    "enemy_cooldown",
    "my_recovery",
    "enemy_recovery",
    "my_in_air",
    "enemy_in_air",
    "my_last_action",
    "enemy_last_action",
    "time_left",
    "room_behind_me",
    "room_behind_enemy",
    "enemy_direction",
    "my_is_crouching",
    "enemy_is_crouching",
    "my_hitstun",
    "enemy_hitstun",
    "my_blockstun",
    "enemy_blockstun",
    "my_is_knocked_down",
    "enemy_is_knocked_down",
    "my_meter",
    "enemy_meter",
    "my_guard_meter",
    "enemy_guard_meter",
    "my_combo_count",
    "enemy_combo_count",
)

# Pairs of "my" and "enemy" parts, used to look from the enemy's side.
_MIRROR_PAIRS = (
    ("my_x", "enemy_x"),
    ("my_health", "enemy_health"),
    ("my_cooldown", "enemy_cooldown"),
    ("my_recovery", "enemy_recovery"),
    ("my_in_air", "enemy_in_air"),
    ("my_last_action", "enemy_last_action"),
    ("my_reach", "enemy_reach"),
    ("my_rounds_won", "enemy_rounds_won"),
    ("my_is_crouching", "enemy_is_crouching"),
    ("my_hitstun", "enemy_hitstun"),
    ("my_blockstun", "enemy_blockstun"),
    ("my_is_knocked_down", "enemy_is_knocked_down"),
    ("my_meter", "enemy_meter"),
    ("my_guard_meter", "enemy_guard_meter"),
    ("my_combo_count", "enemy_combo_count"),
    ("my_build_charges", "enemy_build_charges"),
    ("my_shield", "enemy_shield"),
    ("my_speed_boost", "enemy_speed_boost"),
    ("my_power_boost", "enemy_power_boost"),
    ("my_shield_wall_up", "enemy_shield_wall_up"),
    ("my_shield_wall_hp", "enemy_shield_wall_hp"),
    ("my_shield_energy", "enemy_shield_energy"),
    ("my_shield_cooldown", "enemy_shield_cooldown"),
)


@dataclass(frozen=True, kw_only=True)
class Observation:
    """What a fighter sees in one frame, from ITS OWN point of view.
    "my" = this fighter, "enemy" = the other fighter."""

    # Where we are (pixels)
    my_x: float
    enemy_x: float

    # Health: 0 (dead) to 1 (full)
    my_health: float
    enemy_health: float

    # How far each attack reaches (pixels, from Haseeb's engine)
    my_reach: float
    enemy_reach: float

    # Time
    time_left: float                  # seconds left in this round
    round_length: float = ROUND_SECONDS
    frame: int = 0                    # frame number in this round (for logs and replays)

    # Timers in frames (0 = free)
    my_cooldown: int = 0              # frames until I can attack again
    enemy_cooldown: int = 0           # frames until the enemy can attack again
    my_recovery: int = 0              # frames I am stuck after my attack
    enemy_recovery: int = 0           # frames the enemy is stuck after its attack
    my_hitstun: int = 0               # frames I am in hitstun
    enemy_hitstun: int = 0            # frames enemy is in hitstun
    my_blockstun: int = 0             # frames I am in blockstun
    enemy_blockstun: int = 0          # frames enemy is in blockstun

    # Jumping and Stances
    my_in_air: bool = False
    enemy_in_air: bool = False
    my_is_crouching: bool = False
    enemy_is_crouching: bool = False
    my_is_knocked_down: bool = False
    enemy_is_knocked_down: bool = False

    # Meters and Combos (Phases 2 & 3)
    my_meter: float = 0.0             # 0 to 100
    enemy_meter: float = 0.0          # 0 to 100
    my_guard_meter: float = 100.0     # 0 to 100
    enemy_guard_meter: float = 100.0  # 0 to 100
    my_combo_count: int = 0
    enemy_combo_count: int = 0

    # Arena Rumble Perception (Phase 5)
    is_rumble: bool = False
    zone_left: float = 0.0
    zone_right: float = zones.ARENA_WIDTH
    zone_time_to_close: float = 0.0
    zone_is_closing: bool = False
    zone_is_warning: bool = False
    my_build_charges: int = 3
    enemy_build_charges: int = 3
    my_shield: float = 0.0
    enemy_shield: float = 0.0
    my_speed_boost: float = 0.0
    enemy_speed_boost: float = 0.0
    my_power_boost: float = 0.0
    enemy_power_boost: float = 0.0
    nearest_item_type: str = "none"
    nearest_item_dist: float = 999.0
    nearest_item_dir: float = 0.0      # -1.0 left, +1.0 right
    wall_between: bool = False
    wall_between_hp: float = 0.0
    nearest_crate_dist: float = 999.0
    nearest_pad_dist: float = 999.0
    nearest_trap_dist: float = 999.0

    # Shield Wall Perception (Step 4)
    enable_shield_wall: bool = False
    my_shield_wall_up: str = "none"         # "none", "front", "back"
    enemy_shield_wall_up: str = "none"
    my_shield_wall_hp: float = 0.0
    enemy_shield_wall_hp: float = 0.0
    my_shield_energy: float = 100.0
    enemy_shield_energy: float = 100.0
    my_shield_cooldown: float = 0.0         # seconds remaining
    enemy_shield_cooldown: float = 0.0

    # Last frame's moves
    my_last_action: Action = Action.IDLE
    enemy_last_action: Action = Action.IDLE

    # Arena walls (pixels)
    arena_left: float = 0
    arena_right: float = zones.ARENA_WIDTH

    # Match score
    round_number: int = 1
    my_rounds_won: int = 0
    enemy_rounds_won: int = 0

    # ---------------------------------------------------------------
    # Safety checks
    # ---------------------------------------------------------------
    def __post_init__(self):
        if self.arena_left >= self.arena_right:
            raise ValueError("arena_left must be smaller than arena_right")
        for name in ("my_x", "enemy_x"):
            x = getattr(self, name)
            if not self.arena_left <= x <= self.arena_right:
                raise ValueError(f"{name}={x} is outside the arena")
        for name in ("my_health", "enemy_health"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in ("my_reach", "enemy_reach", "frame",
                     "my_cooldown", "enemy_cooldown", "my_recovery", "enemy_recovery",
                     "my_hitstun", "enemy_hitstun", "my_blockstun", "enemy_blockstun"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.round_length <= 0:
            raise ValueError("round_length must be above 0")
        if not 0 <= self.time_left <= self.round_length:
            raise ValueError(f"time_left must be between 0 and {self.round_length}")
        for name in ("my_in_air", "enemy_in_air", "my_is_crouching", "enemy_is_crouching",
                     "my_is_knocked_down", "enemy_is_knocked_down"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be True or False")
        for name in ("my_last_action", "enemy_last_action"):
            if not isinstance(getattr(self, name), Action):
                raise TypeError(f"{name} must be an Action, like Action.LIGHT")
        if self.round_number < 1:
            raise ValueError("round_number starts at 1")
        for name in ("my_rounds_won", "enemy_rounds_won"):
            if not 0 <= getattr(self, name) <= WINS_NEEDED:
                raise ValueError(f"{name} must be between 0 and {WINS_NEEDED}")

    # ---------------------------------------------------------------
    # Distance and direction
    # ---------------------------------------------------------------
    @property
    def distance(self):
        return zones.distance_between(self.my_x, self.enemy_x)

    @property
    def distance_ratio(self):
        """0 = touching, 1 = whole arena apart."""
        return zones.distance_ratio(self.distance, self.arena_right - self.arena_left)

    @property
    def zone(self):
        return zones.zone_of(self.distance)

    @property
    def enemy_direction(self):
        """+1 if the enemy is on my right, -1 if on my left."""
        return 1 if self.enemy_x >= self.my_x else -1

    # ---------------------------------------------------------------
    # Health
    # ---------------------------------------------------------------
    @property
    def health_lead(self):
        """Above 0 = I am winning, below 0 = I am losing (from -1 to 1)."""
        return self.my_health - self.enemy_health

    def is_panicking(self, personality):
        """True when my health is below this fighter's panic level."""
        return self.my_health < personality.panic_health

    # ---------------------------------------------------------------
    # What I can do
    # ---------------------------------------------------------------
    @property
    def can_act(self):
        """False while I am stuck after my own attack, in stun, or knocked down."""
        return (
            self.my_recovery == 0
            and self.my_hitstun == 0
            and self.my_blockstun == 0
            and not self.my_is_knocked_down
        )

    @property
    def can_attack(self):
        return self.can_act and self.my_cooldown == 0

    def can_use_shield(self, energy_cost: float = 55.0) -> bool:
        """Mask shield actions when not possible."""
        return (
            self.enable_shield_wall
            and self.can_act
            and not self.my_in_air
            and self.my_shield_wall_up == "none"
            and self.my_shield_cooldown <= 0.0
            and self.my_shield_energy >= energy_cost
        )

    @property
    def i_can_hit(self):
        return zones.in_range(self.distance, self.my_reach)

    @property
    def is_safe_poke(self):
        """I can hit them, but they cannot hit me back."""
        return zones.is_safe_poke(self.distance, self.my_reach, self.enemy_reach)

    # ---------------------------------------------------------------
    # What the enemy is doing
    # ---------------------------------------------------------------
    @property
    def enemy_can_hit(self):
        return zones.in_range(self.distance, self.enemy_reach)

    @property
    def enemy_is_attacking(self):
        return self.enemy_last_action in ATTACKS

    @property
    def enemy_is_blocking(self):
        return self.enemy_last_action in DEFENCE

    @property
    def enemy_is_stuck(self):
        """True right after the enemy attacked: the best moment to hit back."""
        return self.enemy_recovery > 0

    @property
    def enemy_is_open(self):
        """True when the enemy cannot attack right now: safe to walk in."""
        return self.enemy_recovery > 0 or self.enemy_cooldown > 0

    # ---------------------------------------------------------------
    # Walls
    # ---------------------------------------------------------------
    @property
    def room_behind_me(self):
        return zones.room_behind(self.my_x, self.enemy_x, self.arena_left, self.arena_right)

    @property
    def room_behind_enemy(self):
        return zones.room_behind(self.enemy_x, self.my_x, self.arena_left, self.arena_right)

    @property
    def i_am_cornered(self):
        return self.room_behind_me < zones.CORNER_MARGIN

    @property
    def enemy_is_cornered(self):
        return self.room_behind_enemy < zones.CORNER_MARGIN

    # ---------------------------------------------------------------
    # Time
    # ---------------------------------------------------------------
    @property
    def time_ratio(self):
        """1 = round just started, 0 = time is up."""
        return self.time_left / self.round_length

    @property
    def time_running_out(self):
        return self.time_left <= LOW_TIME

    # ---------------------------------------------------------------
    # Seeing the fight from the other side, or in a mirror
    # ---------------------------------------------------------------
    def swapped(self):
        """The same moment, seen by the ENEMY.
        Used when a fighter imagines what the enemy will do."""
        changes = {}
        for mine, theirs in _MIRROR_PAIRS:
            changes[mine] = getattr(self, theirs)
            changes[theirs] = getattr(self, mine)
        return replace(self, **changes)

    def mirrored(self):
        """The same moment flipped left-to-right, like in a mirror.
        Gives the learning code twice as much data for free
        (called "data augmentation")."""
        def flip(x):
            return self.arena_left + self.arena_right - x
        return replace(self, my_x=flip(self.my_x), enemy_x=flip(self.enemy_x))

    def jittered(self, rng, pixels=5, health=0.02):
        """The same moment with tiny random changes to positions and health.
        More data augmentation: teaches the learning code that a few pixels
        or a little health do not change the right move."""
        if pixels < 0 or health < 0:
            raise ValueError("pixels and health cannot be negative")

        def clamp(value, low, high):
            return max(low, min(high, value))

        def nudge_x(x):
            return clamp(x + rng.uniform(-pixels, pixels), self.arena_left, self.arena_right)

        def nudge_health(h):
            return clamp(h + rng.uniform(-health, health), 0.0, 1.0)

        return replace(
            self,
            my_x=nudge_x(self.my_x),
            enemy_x=nudge_x(self.enemy_x),
            my_health=nudge_health(self.my_health),
            enemy_health=nudge_health(self.enemy_health),
        )

    # ---------------------------------------------------------------
    # Numbers for the learning code and the fight logs
    # ---------------------------------------------------------------
    def features(self):
        """This moment as numbers (mostly 0 to 1), in FEATURE_NAMES order.
        Sami's logger and the learning code must both use this,
        so they always agree."""
        width = self.arena_right - self.arena_left

        def frames(n):
            return min(n / FRAMES_PER_SECOND, 1.0)

        return {
            "distance": self.distance_ratio,
            "my_health": self.my_health,
            "enemy_health": self.enemy_health,
            "health_lead": self.health_lead,
            "my_cooldown": frames(self.my_cooldown),
            "enemy_cooldown": frames(self.enemy_cooldown),
            "my_recovery": frames(self.my_recovery),
            "enemy_recovery": frames(self.enemy_recovery),
            "my_in_air": float(self.my_in_air),
            "enemy_in_air": float(self.enemy_in_air),
            "my_last_action": self.my_last_action.value,
            "enemy_last_action": self.enemy_last_action.value,
            "time_left": self.time_ratio,
            "room_behind_me": self.room_behind_me / width,
            "room_behind_enemy": self.room_behind_enemy / width,
            "enemy_direction": self.enemy_direction,
            "my_is_crouching": float(self.my_is_crouching),
            "enemy_is_crouching": float(self.enemy_is_crouching),
            "my_hitstun": frames(self.my_hitstun),
            "enemy_hitstun": frames(self.enemy_hitstun),
            "my_blockstun": frames(self.my_blockstun),
            "enemy_blockstun": frames(self.enemy_blockstun),
            "my_is_knocked_down": float(self.my_is_knocked_down),
            "enemy_is_knocked_down": float(self.enemy_is_knocked_down),
            "my_meter": self.my_meter / 100.0,
            "enemy_meter": self.enemy_meter / 100.0,
            "my_guard_meter": self.my_guard_meter / 100.0,
            "enemy_guard_meter": self.enemy_guard_meter / 100.0,
            "my_combo_count": float(self.my_combo_count),
            "enemy_combo_count": float(self.enemy_combo_count),
        }


def example_observation(**changes):
    """A normal mid-fight moment, for tests and trying things out.
    Change any part, for example: example_observation(my_health=0.1)"""
    normal = Observation(
        my_x=300, enemy_x=500,
        my_health=1.0, enemy_health=1.0,
        my_reach=70, enemy_reach=70,
        time_left=60,
    )
    return replace(normal, **changes)
