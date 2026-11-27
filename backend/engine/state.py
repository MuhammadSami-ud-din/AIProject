"""The complete snapshot of a fight at one moment in time.

FighterState holds one fighter's body (position, health, timers, posture, stuns, meters).
FightState holds both fighters, projectiles, plus the round/match bookkeeping.
Both are plain dataclasses so the step() function can copy and update them.
"""

from dataclasses import dataclass, field
from typing import Optional

from backend.ai.actions import Action
from backend.engine.constants import (
    ARENA_WIDTH,
    FURY_HEALTH_THRESHOLD,
    JUMP_DURATION,
    JUMP_HEIGHT,
    PROJECTILE_HEIGHT,
    ROUND_FRAMES,
)
from backend.engine.rules import ModeRules
from backend.engine.rumble_state import (
    ArenaObjectState,
    ItemState,
    KillFeedMessage,
    SupplyDropState,
    WallState,
    ZoneState,
)
from backend.engine.shield_state import ShieldWallState


@dataclass
class ProjectileState:
    """A deterministic projectile flying across the arena."""

    x: float
    y: float
    vx: float
    owner: int                   # 1 for P1, 2 for P2
    lifetime: int                # frames left before expiring
    damage: float                # health fraction (e.g. 0.05 = 5 HP)
    hit_level: str = "mid"       # "mid", "high", "low"
    reach: float = 24.0
    reflected: bool = False
    height: float = PROJECTILE_HEIGHT  # centre height above the floor (jump over it)

    def copy(self):
        new = object.__new__(ProjectileState)
        new.__dict__.update(self.__dict__)
        return new


# ---------------------------------------------------------------
# One fighter's body
# ---------------------------------------------------------------

@dataclass
class FighterState:
    """Everything about one fighter's body right now."""

    x: float = 0.0                # position in pixels (0 = left wall)
    health: float = 1.0           # 0.0 = dead, 1.0 = full

    # Timers (in frames, 0 = free)
    cooldown: int = 0             # frames until this fighter can attack again
    recovery: int = 0             # frames this fighter is stuck after attacking
    hitstun: int = 0              # frames stuck in hitstun
    blockstun: int = 0            # frames stuck in blockstun

    # Attack phase tracking
    # phase: "none", "startup", "active", "recovery"
    attack_phase: str = "none"
    attack_frames_left: int = 0   # frames left in the current attack phase
    attack_type: str = "none"     # "light", "heavy", "low_sweep", etc.
    current_action: Action = Action.IDLE
    has_hit: bool = False         # True once an attack has connected during active phase

    # Posture & Stances
    is_crouching: bool = False
    in_air: bool = False
    jump_frame: int = 0           # which frame of the jump we are on (0 = on ground)
    air_jumps_left: int = 1       # for double-jump passives (Shadow)
    air_dash_left: int = 1        # for air-dash passives (Shadow)
    is_knocked_down: bool = False
    knockdown_frames: int = 0     # frames until standing back up

    # Invulnerability & Throws & Armor
    invulnerable_frames: int = 0  # invulnerable to hits (e.g. backdash, wakeup)
    throw_tech_frames: int = 0    # frames remaining to tech/break a throw (7 frames)
    is_thrown: bool = False       # currently being grabbed in a throw
    throw_damage_pending: float = 0.0
    armor_hits: int = 0           # armor points (absorbs hits without flinching)
    throw_invuln_frames: int = 0  # cannot be thrown (wakeup, just left hit/blockstun)
    pending_throw_bounce: bool = False  # the throw that grabbed us ground-bounces on landing

    # Dashes (forward dash, backdash, Shadow air dash)
    dash_frames_left: int = 0     # frames of dash travel remaining
    dash_total_frames: int = 0    # length of the current dash
    dash_dir: int = 0             # +1 = right, -1 = left
    dash_speed: float = 0.0       # first-frame speed of the current dash (px/frame)
    dash_in_air: bool = False     # True for Shadow's air dash (constant speed, hover)

    # Combos & Juggles (Phase 2)
    combo_hits: int = 0           # hits landed in current combo
    combo_damage: float = 0.0     # total damage in current combo
    juggle_count: int = 0         # air hits in current combo (capped at 4)
    wall_bounced: bool = False    # wall bounce used in current combo
    ground_bounced: bool = False  # ground bounce used in current combo
    cancel_available: bool = False# True during hit-cancel window
    is_counter_hit: bool = False  # True if last landed hit was a counter-hit
    # ONE-FRAME event (reset to "none" at the start of every step()):
    # "none", "hit", "block", "counter", "parry", "guard_break", "burst",
    # "tech", "ground_bounce", "wall_bounce", "read". See docs/engine.md.
    last_hit_effect: str = "none"

    # Meters & Defense (Phase 3)
    meter: float = 0.0            # Super meter: 0.0 to 100.0
    guard_meter: float = 100.0    # Guard meter: 0.0 to 100.0 (breaks at 0)
    guard_break_stun: int = 0     # Guard break stun timer
    block_held_frames: int = 0    # How many frames block has been held (for 4f parry)
    is_parrying: bool = False     # Parry active (reserved; not set by the engine)
    parry_armed: bool = False     # This block press can still parry (fresh press, no lockout)
    parry_lockout: int = 0        # Frames during which a fresh block press cannot parry
    burst_used_this_round: bool = False # Burst limited to once per round

    # Character Stance & Special States (Phase 4)
    stance: str = "neutral"       # Golden: "rush", "guard", "evade"
    counter_stance: bool = False  # Steel Iron Wall / Fortress Crush counter active
    read_action: Action = Action.IDLE # Golden predicted action
    read_frames_left: int = 0     # Frames remaining for Golden read prediction
    read_success: bool = False    # ONE-FRAME event: Golden prediction landed this frame
    read_bonus_frames: int = 0    # After a successful read: next clean hit is boosted

    # What this fighter did last frame
    last_action: Action = Action.IDLE

    # Which character this fighter is (for looking up body stats)
    character_name: str = "Golden"

    # Arena Rumble Attributes (Phase 1-6)
    build_charges: int = 3        # Build energy (starts at 3, max 3, +1 per 8s)
    build_recharge_timer: int = 0 # Frame timer towards next build charge
    building_frames: int = 0      # 12-frame placement lock during Action.BUILD
    shield: float = 0.0           # Shield HP (absorbs damage first, max 20 HP)
    speed_boost_timer: int = 0    # Speed Boots boost timer (frames)
    power_boost_timer: int = 0    # Power Fist damage boost timer (frames)

    # Rumble Statistics tracking (per-match)
    walls_built: int = 0
    walls_broken: int = 0
    items_collected: int = 0
    zone_damage_taken: float = 0.0

    # Shield Wall Ability (Steps 1-5)
    shield_wall: Optional[ShieldWallState] = None
    shield_energy: float = 100.0
    shield_cooldown_frames: int = 0
    shield_startup_frames: int = 0
    shield_startup_side: str = "none"
    shield_break_stun: int = 0
    shield_walls_raised: int = 0
    shield_walls_broken: int = 0
    shield_time_behind_frames: int = 0

    # Projectile limits (shoot cooldown and per-round shot count)
    projectile_cooldown: int = 0
    shots_fired: int = 0

    # Level & Progression Attributes (modest stat scaling)
    level: int = 1
    health_mult: float = 1.0
    damage_mult: float = 1.0
    speed_mult: float = 1.0
    block_mult: float = 1.0

    # Health Regeneration (only active when enabled for player)
    regen_enabled: bool = False
    no_hit_timer: int = 0


    @property
    def is_fury(self) -> bool:
        """Fury mode activates when health is below 25%."""
        return self.health < FURY_HEALTH_THRESHOLD

    @property
    def y(self) -> float:
        """Height above the floor in pixels (parabolic jump arc; 0 on the ground)."""
        if not self.in_air:
            return 0.0
        p = min(max(self.jump_frame / float(JUMP_DURATION), 0.0), 1.0)
        return JUMP_HEIGHT * 4.0 * p * (1.0 - p)

    @property
    def is_dashing(self) -> bool:
        """True while dashing (forward dash, backdash or air dash)."""
        return (
            self.dash_frames_left > 0
            or self.last_action in (Action.DASH, Action.BACKDASH)
            or self.current_action in (Action.DASH, Action.BACKDASH)
        )

    @property
    def busy(self) -> bool:
        """True while the fighter cannot freely act (read-only).

        Busy means: in attack startup/active/recovery, hitstun, blockstun,
        knocked down or getting up, being thrown, or raising a shield.
        """
        return (
            self.attack_phase in ("startup", "active", "recovery")
            or self.recovery > 0
            or self.hitstun > 0
            or self.blockstun > 0
            or self.is_knocked_down
            or self.knockdown_frames > 0
            or self.is_thrown
            or self.shield_startup_frames > 0
        )

    def copy(self):
        """A fresh copy that can be changed without touching the original.

        Copies every dataclass field generically (so new fields can never be
        forgotten); the only mutable field, shield_wall, is copied deeply.
        """
        new = object.__new__(FighterState)
        new.__dict__.update(self.__dict__)
        if self.shield_wall is not None:
            new.shield_wall = self.shield_wall.copy()
        return new


# ---------------------------------------------------------------
# The whole fight
# ---------------------------------------------------------------

@dataclass
class FightState:
    """Everything about the fight right now: both fighters plus bookkeeping."""

    fighter1: FighterState = field(default_factory=FighterState)
    fighter2: FighterState = field(default_factory=FighterState)
    projectiles: list[ProjectileState] = field(default_factory=list)

    frame: int = 0                         # current frame number in this round
    round_number: int = 1                  # which round we are in (starts at 1)
    round_frames_left: int = ROUND_FRAMES  # frames left in this round

    p1_rounds_won: int = 0
    p2_rounds_won: int = 0

    round_over: bool = False       # True when the current round just ended
    match_over: bool = False       # True when the whole match is done
    round_result: str = "none"     # "p1", "p2", "draw", or "none"
    match_result: str = "none"     # "p1", "p2", "draw", or "none"

    # Polish & VFX signals (Phase 6)
    super_freeze_frames: int = 0   # Super flash freeze counter (15f)
    super_attacker: int = 0        # 1 or 2 (which player initiated super)
    # Last non-idle input pressed during a super freeze; applied on the first
    # frame after the freeze (unless a new input is pressed on that frame).
    buffered_action1: Action = Action.IDLE
    buffered_action2: Action = Action.IDLE

    # Arena Rumble Game Mode State (Phase 1-6)
    rules: ModeRules = field(default_factory=ModeRules.classic)
    zone: Optional[ZoneState] = None
    walls: list[WallState] = field(default_factory=list)
    items: list[ItemState] = field(default_factory=list)
    supply_drop: Optional[SupplyDropState] = None
    arena_objects: list[ArenaObjectState] = field(default_factory=list)
    kill_feed: list[KillFeedMessage] = field(default_factory=list)
    next_loot_timer: int = 720
    next_object_id: int = 1
    match_seed: int = 42

    def copy(self):
        """A fresh copy of the entire fight state."""
        return FightState(
            fighter1=self.fighter1.copy(),
            fighter2=self.fighter2.copy(),
            projectiles=[p.copy() for p in self.projectiles],
            frame=self.frame,
            round_number=self.round_number,
            round_frames_left=self.round_frames_left,
            p1_rounds_won=self.p1_rounds_won,
            p2_rounds_won=self.p2_rounds_won,
            round_over=self.round_over,
            match_over=self.match_over,
            round_result=self.round_result,
            match_result=self.match_result,
            super_freeze_frames=self.super_freeze_frames,
            super_attacker=self.super_attacker,
            buffered_action1=self.buffered_action1,
            buffered_action2=self.buffered_action2,
            rules=self.rules.copy(),
            zone=self.zone.copy() if self.zone is not None else None,
            walls=[w.copy() for w in self.walls],
            items=[it.copy() for it in self.items],
            supply_drop=self.supply_drop.copy() if self.supply_drop else None,
            arena_objects=[obj.copy() for obj in self.arena_objects],
            kill_feed=[msg.copy() for msg in self.kill_feed],
            next_loot_timer=self.next_loot_timer,
            next_object_id=self.next_object_id,
            match_seed=self.match_seed,
        )
