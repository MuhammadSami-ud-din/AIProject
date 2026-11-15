"""The complete snapshot of a fight at one moment in time.

FighterState holds one fighter's body (position, health, timers, posture, stuns, meters).
FightState holds both fighters, projectiles, plus the round/match bookkeeping.
Both are plain dataclasses so the step() function can copy and update them.
"""

from dataclasses import dataclass, field

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH, ROUND_FRAMES


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

    def copy(self):
        return ProjectileState(
            x=self.x,
            y=self.y,
            vx=self.vx,
            owner=self.owner,
            lifetime=self.lifetime,
            damage=self.damage,
            hit_level=self.hit_level,
            reach=self.reach,
            reflected=self.reflected,
        )


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

    # Combos & Juggles (Phase 2)
    combo_hits: int = 0           # hits landed in current combo
    combo_damage: float = 0.0     # total damage in current combo
    juggle_count: int = 0         # air hits in current combo (capped at 4)
    wall_bounced: bool = False    # wall bounce used in current combo
    ground_bounced: bool = False  # ground bounce used in current combo
    cancel_available: bool = False# True during hit-cancel window
    is_counter_hit: bool = False  # True if last landed hit was a counter-hit
    last_hit_effect: str = "none" # "none", "counter", "parry", "guard_break", "burst"

    # Meters & Defense (Phase 3)
    meter: float = 0.0            # Super meter: 0.0 to 100.0
    guard_meter: float = 100.0    # Guard meter: 0.0 to 100.0 (breaks at 0)
    guard_break_stun: int = 0     # Guard break stun timer
    block_held_frames: int = 0    # How many frames block has been held (for 4f parry)
    is_parrying: bool = False     # Parry active
    burst_used_this_round: bool = False # Burst limited to once per round

    # Character Stance & Special States (Phase 4)
    stance: str = "neutral"       # Golden: "rush", "guard", "evade"
    counter_stance: bool = False  # Steel Iron Wall / Fortress Crush counter active
    read_action: Action = Action.IDLE # Golden predicted action
    read_frames_left: int = 0     # Frames remaining for Golden read prediction
    read_success: bool = False    # Golden prediction landed successfully

    # What this fighter did last frame
    last_action: Action = Action.IDLE

    # Which character this fighter is (for looking up body stats)
    character_name: str = "Golden"

    @property
    def is_fury(self) -> bool:
        """Fury mode activates when health is below 25%."""
        return self.health < 0.25

    def copy(self):
        """A fresh copy that can be changed without touching the original."""
        return FighterState(
            x=self.x,
            health=self.health,
            cooldown=self.cooldown,
            recovery=self.recovery,
            hitstun=self.hitstun,
            blockstun=self.blockstun,
            attack_phase=self.attack_phase,
            attack_frames_left=self.attack_frames_left,
            attack_type=self.attack_type,
            current_action=self.current_action,
            has_hit=self.has_hit,
            is_crouching=self.is_crouching,
            in_air=self.in_air,
            jump_frame=self.jump_frame,
            air_jumps_left=self.air_jumps_left,
            air_dash_left=self.air_dash_left,
            is_knocked_down=self.is_knocked_down,
            knockdown_frames=self.knockdown_frames,
            invulnerable_frames=self.invulnerable_frames,
            throw_tech_frames=self.throw_tech_frames,
            is_thrown=self.is_thrown,
            throw_damage_pending=self.throw_damage_pending,
            armor_hits=self.armor_hits,
            combo_hits=self.combo_hits,
            combo_damage=self.combo_damage,
            juggle_count=self.juggle_count,
            wall_bounced=self.wall_bounced,
            ground_bounced=self.ground_bounced,
            cancel_available=self.cancel_available,
            is_counter_hit=self.is_counter_hit,
            last_hit_effect=self.last_hit_effect,
            meter=self.meter,
            guard_meter=self.guard_meter,
            guard_break_stun=self.guard_break_stun,
            block_held_frames=self.block_held_frames,
            is_parrying=self.is_parrying,
            burst_used_this_round=self.burst_used_this_round,
            stance=self.stance,
            counter_stance=self.counter_stance,
            read_action=self.read_action,
            read_frames_left=self.read_frames_left,
            read_success=self.read_success,
            last_action=self.last_action,
            character_name=self.character_name,
        )


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
        )
