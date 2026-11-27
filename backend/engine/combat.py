"""Attack logic: starting moves, phase advance, hit/block detection, high/low rules, throws, cancels."""

from backend.ai.actions import Action
from backend.engine.constants import (
    AIR_HURTBOX_HEIGHT,
    CROUCH_HURTBOX_HEIGHT,
    FURY_SUPER_COST,
    GOLDEN_EVADE_EXTRA_INVULN,
    STAND_HURTBOX_HEIGHT,
)
from backend.engine.moves import CancelType, HitLevel, MoveData, get_move
from backend.engine.pushbox import pushbox_half_width
from backend.engine.state import FighterState

GOLDEN_STANCES = ("rush", "guard", "evade")


def can_act(fighter: FighterState) -> bool:
    """True if the fighter is currently free to start an action."""
    return (
        fighter.cooldown <= 0
        and fighter.attack_phase == "none"
        and fighter.recovery <= 0
        and fighter.hitstun <= 0
        and fighter.blockstun <= 0
        and not fighter.is_knocked_down
        and not fighter.is_thrown
    )


def can_cancel_into(fighter: FighterState, next_action: Action) -> bool:
    """True if the fighter is in a hit-cancel window and next_action is a valid cancel."""
    if not fighter.cancel_available:
        return False

    current_move = get_move(fighter.character_name, fighter.current_action)
    if current_move is None:
        return False

    windows = current_move.cancel_windows
    next_move = get_move(fighter.character_name, next_action)
    if next_move is None:
        return False

    # Check CancelType.CHAIN (Normal -> Normal / String)
    if CancelType.CHAIN in windows and next_action in (
        Action.LIGHT, Action.HEAVY, Action.LIGHT_KICK, Action.HEAVY_KICK,
        Action.CROUCH_JAB, Action.CROUCH_KICK, Action.LOW_SWEEP, Action.OVERHEAD,
    ):
        return True

    # Check CancelType.SPECIAL (Normal -> Special)
    if CancelType.SPECIAL in windows and next_action in (
        Action.SPECIAL_NEUTRAL, Action.SPECIAL_FORWARD, Action.SPECIAL_BACK, Action.SPECIAL_DOWN,
    ):
        return True

    # Check CancelType.SUPER (Normal/Special -> Super)
    if CancelType.SUPER in windows and next_action == Action.SUPER:
        return True

    return False


def start_attack(fighter: FighterState, move: MoveData) -> bool:
    """Try to start an attack or move. Returns True if the move began."""
    # Check if free or cancelling
    cancelling = can_cancel_into(fighter, move.action)
    if not can_act(fighter) and not cancelling:
        return False

    # Air moves must be done in air; ground moves on ground
    if move.is_air and not fighter.in_air:
        return False
    if not move.is_air and fighter.in_air:
        return False

    # Check meter cost (Super costs 60 in Fury, 100 normally)
    meter_cost = move.meter_cost
    if move.action == Action.SUPER and fighter.is_fury:
        meter_cost = min(FURY_SUPER_COST, meter_cost)

    if meter_cost > 0.0:
        if fighter.meter < meter_cost:
            return False
        fighter.meter -= meter_cost

    # Stance handling for Golden Tactician (cycles rush -> guard -> evade -> rush).
    # Effects: see step.py (rush = more damage, guard = less chip/guard drain,
    # evade = faster walk and longer invulnerability on evasive moves).
    if fighter.character_name == "Golden" and move.action == Action.SPECIAL_DOWN:
        idx = ((GOLDEN_STANCES.index(fighter.stance) + 1) % len(GOLDEN_STANCES)
               if fighter.stance in GOLDEN_STANCES else 0)
        fighter.stance = GOLDEN_STANCES[idx]

    # Counter stance
    fighter.counter_stance = move.is_counter_stance

    # Armor
    fighter.armor_hits = move.armor

    # Set crouching posture if low move
    if move.is_crouching:
        fighter.is_crouching = True

    # Handle invulnerability (e.g. backdash first 4 frames, shadow step)
    if move.invulnerable_frames > 0:
        extra = GOLDEN_EVADE_EXTRA_INVULN if (
            fighter.character_name == "Golden" and fighter.stance == "evade") else 0
        fighter.invulnerable_frames = move.invulnerable_frames + extra

    # Clear previous cancel availability
    fighter.cancel_available = False

    # Begin attack phase
    fighter.has_hit = False
    if move.startup == 0:
        fighter.attack_phase = "active"
        fighter.attack_frames_left = move.active
    else:
        fighter.attack_phase = "startup"
        fighter.attack_frames_left = move.startup

    fighter.attack_type = move.action.name.lower()
    fighter.current_action = move.action
    return True


def advance_attack(fighter: FighterState, move: MoveData | None) -> None:
    """Move the attack forward by one frame through its phases."""
    if fighter.attack_phase == "none":
        return

    if move is None:
        fighter.attack_phase = "none"
        fighter.attack_frames_left = 0
        fighter.attack_type = "none"
        fighter.current_action = Action.IDLE
        fighter.counter_stance = False
        return

    fighter.attack_frames_left -= 1

    if fighter.attack_frames_left <= 0:
        if fighter.attack_phase == "startup":
            fighter.attack_phase = "active"
            fighter.attack_frames_left = move.active

        elif fighter.attack_phase == "active":
            # This frame is the first recovery frame (attack_frames_left counts it);
            # the recovery/cooldown timers count the frames AFTER this one.
            fighter.attack_phase = "recovery"
            fighter.attack_frames_left = move.recovery
            fighter.recovery = max(0, move.recovery - 1)
            fighter.cooldown = max(0, move.recovery - 1)
            fighter.counter_stance = False

        elif fighter.attack_phase == "recovery":
            fighter.attack_phase = "none"
            fighter.attack_frames_left = 0
            fighter.attack_type = "none"
            fighter.current_action = Action.IDLE
            fighter.cancel_available = False
            fighter.counter_stance = False


def is_busy_with_own_move(fighter: FighterState) -> bool:
    """True while the fighter is committed to their own move (startup/active/recovery)."""
    return fighter.attack_phase != "none" or fighter.recovery > 0


def is_guarding(defender: FighterState, defender_action: Action, hit_level: HitLevel) -> bool:
    """Check if the defender successfully blocks an incoming hit based on hit level.

    `defender_action` is the defender's input on THIS frame (melee and projectiles alike).
    """
    # Cannot block in the air
    if defender.in_air:
        return False

    # Cannot block while stunned, knocked down, or grabbed
    if defender.hitstun > 0 or defender.is_knocked_down or defender.is_thrown:
        return False

    # Cannot block during your own move's startup, active or recovery frames
    if is_busy_with_own_move(defender):
        return False

    # Throws cannot be blocked
    if hit_level == HitLevel.THROW:
        return False

    # Guard broken defenders cannot block
    if defender.guard_break_stun > 0 or defender.guard_meter <= 0:
        return False

    # Is the defender holding a block button or currently in blockstun?
    holding_high_block = (defender_action == Action.BLOCK and not defender.is_crouching)
    holding_low_block = (
        defender_action == Action.BLOCK_LOW
        or (defender.is_crouching and defender_action == Action.BLOCK)
    )

    # In blockstun, maintain the block posture that entered it
    if defender.blockstun > 0:
        if defender.is_crouching:
            holding_low_block = True
        else:
            holding_high_block = True

    if hit_level == HitLevel.MID:
        # Mids can be blocked standing or crouching
        return holding_high_block or holding_low_block

    if hit_level == HitLevel.HIGH:
        # Highs / Overheads must be blocked standing
        return holding_high_block

    if hit_level == HitLevel.LOW:
        # Lows must be blocked crouching
        return holding_low_block

    return False


# ---------------------------------------------------------------
# Vertical axis: hurtboxes and hitboxes
# ---------------------------------------------------------------

def hurtbox_range(fighter: FighterState) -> tuple[float, float]:
    """Vertical extent (bottom, top) of the fighter's body in px above the floor."""
    if fighter.in_air:
        y = fighter.y
        return (y, y + AIR_HURTBOX_HEIGHT)
    if fighter.is_crouching:
        return (0.0, CROUCH_HURTBOX_HEIGHT)
    return (0.0, STAND_HURTBOX_HEIGHT)


def hitbox_range(attacker: FighterState, move: MoveData) -> tuple[float, float]:
    """Vertical extent of the move's hitbox in px above the floor."""
    lo, hi = move.vertical_range
    y = attacker.y
    return (y + lo, y + hi)


def ranges_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def is_anti_air_active(fighter: FighterState) -> bool:
    """True while the fighter's anti-air move beats incoming air attacks."""
    if fighter.attack_phase not in ("startup", "active"):
        return False
    move = get_move(fighter.character_name, fighter.current_action)
    return move is not None and move.anti_air


def check_hit(attacker: FighterState, defender: FighterState, move: MoveData) -> bool:
    """Return True if the attacker's hit connects this frame."""
    if attacker.attack_phase != "active":
        return False
    if attacker.has_hit:
        return False

    # Utility moves (backdash, stance, teleport, feint) have no hitbox
    if move.damage <= 0.0:
        return False

    # Invulnerable opponents cannot be hit
    if defender.invulnerable_frames > 0 or defender.is_knocked_down:
        return False

    # Horizontal reach (accounting for defender's physical hurtbox radius)
    distance = abs(attacker.x - defender.x)
    if distance > (move.reach + pushbox_half_width(defender)):
        return False

    # Vertical: the hitbox must overlap the defender's hurtbox
    if not ranges_overlap(hitbox_range(attacker, move), hurtbox_range(defender)):
        return False

    # Anti-airs beat air attacks
    if move.is_air and is_anti_air_active(defender):
        return False

    # Throw specifics:
    if move.hit_level == HitLevel.THROW:
        # Throws miss airborne opponents
        if defender.in_air:
            return False
        # Throw invulnerability: wakeup, during and just after hit/blockstun
        if (defender.throw_invuln_frames > 0 or defender.hitstun > 0
                or defender.blockstun > 0 or defender.is_thrown):
            return False
        # Normal throw loses to attack startup; command grabs beat normal attacks.
        # Throw vs throw connects for both and becomes a clash (see step.py).
        if move.action == Action.THROW and defender.attack_phase in ("startup", "active"):
            defender_move = get_move(defender.character_name, defender.current_action)
            if defender_move is None or defender_move.hit_level != HitLevel.THROW:
                return False

    return True


def apply_damage(defender: FighterState, damage: float,
                 is_blocking: bool, blocked_damage_ratio: float,
                 attacker: FighterState | None = None) -> float:
    """Apply damage to the defender and reduce health.

    Takes into account attacker damage multiplier, defender health multiplier,
    and block multiplier in a backward-compatible manner (defaults to 1.0).
    """
    dmg_mult = getattr(attacker, "damage_mult", 1.0) if attacker is not None else 1.0
    h_mult = getattr(defender, "health_mult", 1.0)
    if h_mult <= 0:
        h_mult = 1.0
    b_mult = getattr(defender, "block_mult", 1.0)
    if b_mult <= 0:
        b_mult = 1.0

    scaled_damage = damage * dmg_mult

    if is_blocking and not defender.in_air:
        # Better block_mult reduces blocked chip damage
        effective_ratio = blocked_damage_ratio / b_mult
        actual_damage = scaled_damage * effective_ratio
    else:
        actual_damage = scaled_damage

    # Larger health pool mathematically achieved by dividing incoming damage by health_mult
    actual_damage = actual_damage / h_mult

    # Armor absorbs hit: takes 50% damage
    if defender.armor_hits > 0:
        actual_damage *= 0.5
        defender.armor_hits -= 1

    # Shield absorption (Rumble mode Shield Cell)
    if defender.shield > 0.0:
        damage_hp = actual_damage * 100.0
        absorbed_hp = min(defender.shield, damage_hp)
        defender.shield -= absorbed_hp
        actual_damage = (damage_hp - absorbed_hp) / 100.0

    defender.health = max(0.0, defender.health - actual_damage)
    if actual_damage > 0.0:
        defender.no_hit_timer = 0
    return actual_damage
