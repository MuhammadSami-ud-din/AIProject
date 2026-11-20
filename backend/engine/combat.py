"""Attack logic: starting moves, phase advance, hit/block detection, high/low rules, throws, cancels."""

from backend.ai.actions import Action
from backend.engine.moves import CancelType, HitLevel, MoveData, get_move
from backend.engine.state import FighterState


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
        meter_cost = min(60.0, meter_cost)

    if meter_cost > 0.0:
        if fighter.meter < meter_cost:
            return False
        fighter.meter -= meter_cost

    # Stance handling for Golden Tactician (cycles rush -> guard -> evade -> rush)
    if fighter.character_name == "Golden" and move.action == Action.SPECIAL_DOWN:
        stances = ["rush", "guard", "evade"]
        idx = (stances.index(fighter.stance) + 1) % len(stances) if fighter.stance in stances else 0
        fighter.stance = stances[idx]

    # Counter stance
    fighter.counter_stance = move.is_counter_stance

    # Armor
    fighter.armor_hits = move.armor

    # Set crouching posture if low move
    if move.is_crouching:
        fighter.is_crouching = True

    # Handle invulnerability (e.g. backdash first 4 frames, shadow step)
    if move.invulnerable_frames > 0:
        fighter.invulnerable_frames = move.invulnerable_frames

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
            fighter.attack_phase = "recovery"
            fighter.attack_frames_left = move.recovery
            fighter.recovery = move.recovery
            fighter.cooldown = move.recovery + 2
            fighter.counter_stance = False

        elif fighter.attack_phase == "recovery":
            fighter.attack_phase = "none"
            fighter.attack_frames_left = 0
            fighter.attack_type = "none"
            fighter.current_action = Action.IDLE
            fighter.cancel_available = False
            fighter.counter_stance = False


def is_guarding(defender: FighterState, defender_action: Action, hit_level: HitLevel) -> bool:
    """Check if the defender successfully blocks an incoming hit based on hit level."""
    # Cannot block in the air
    if defender.in_air:
        return False

    # Cannot block while stunned, knocked down, or grabbed
    if defender.hitstun > 0 or defender.is_knocked_down or defender.is_thrown:
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


def check_hit(attacker: FighterState, defender: FighterState, move: MoveData) -> bool:
    """Return True if the attacker's hit connects this frame."""
    if attacker.attack_phase != "active":
        return False
    if attacker.has_hit:
        return False

    # Invulnerable opponents cannot be hit
    if defender.invulnerable_frames > 0 or defender.is_knocked_down:
        return False

    # Check distance reach
    distance = abs(attacker.x - defender.x)
    if distance > move.reach:
        return False

    # Throw specifics:
    if move.hit_level == HitLevel.THROW:
        # Throws miss airborne opponents
        if defender.in_air:
            return False
        # Normal throw loses to attack startup; command grabs beat normal attacks
        if move.action == Action.THROW and defender.attack_phase in ("startup", "active"):
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
