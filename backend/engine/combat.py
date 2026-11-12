"""Attack logic: starting attacks, advancing through phases, hit detection, damage."""

from backend.ai.actions import Action
from backend.engine.constants import AttackData
from backend.engine.state import FighterState


def start_attack(fighter: FighterState, attack_data: AttackData,
                 attack_type: str) -> bool:
    """Try to start an attack. Returns True if the attack began.

    An attack can only start if:
      - The fighter is not on cooldown.
      - The fighter is not already in an attack phase (startup/active/recovery).
      - The fighter is not stuck from a previous attack's recovery.
    """
    if fighter.cooldown > 0:
        return False
    if fighter.attack_phase != "none":
        return False
    if fighter.recovery > 0:
        return False

    # Begin the startup phase (wind-up before the hit)
    fighter.attack_phase = "startup"
    fighter.attack_frames_left = attack_data.startup
    fighter.attack_type = attack_type
    return True


def advance_attack(fighter: FighterState, attack_data: AttackData) -> None:
    """Move the attack forward by one frame through its phases.

    Phases go: startup -> active -> recovery -> none.
    When we enter recovery, we also set the cooldown timer.
    """
    if fighter.attack_phase == "none":
        return

    fighter.attack_frames_left -= 1

    if fighter.attack_frames_left <= 0:
        # Move to the next phase
        if fighter.attack_phase == "startup":
            # Wind-up done, the hit box is now live
            fighter.attack_phase = "active"
            fighter.attack_frames_left = attack_data.active

        elif fighter.attack_phase == "active":
            # Hit window done, now the attacker is stuck
            fighter.attack_phase = "recovery"
            fighter.attack_frames_left = attack_data.recovery
            fighter.recovery = attack_data.recovery
            fighter.cooldown = attack_data.cooldown

        elif fighter.attack_phase == "recovery":
            # Recovery done, the fighter is free again
            fighter.attack_phase = "none"
            fighter.attack_frames_left = 0
            fighter.attack_type = "none"


def check_hit(attacker: FighterState, defender: FighterState,
              attack_data: AttackData) -> bool:
    """Return True if the attacker's hit connects this frame.

    A hit connects when:
      - The attacker is in the 'active' phase of their attack.
      - The distance between the fighters is within the attack's reach.
    """
    if attacker.attack_phase != "active":
        return False

    distance = abs(attacker.x - defender.x)
    return distance <= attack_data.reach


def apply_damage(defender: FighterState, damage: float,
                 is_blocking: bool, blocked_damage_ratio: float) -> float:
    """Apply damage to the defender. Returns the actual damage dealt.

    If the defender is blocking (and not in the air), damage is reduced.
    Health never goes below 0.
    """
    # You cannot block in the air
    if is_blocking and not defender.in_air:
        actual_damage = damage * blocked_damage_ratio
    else:
        actual_damage = damage

    defender.health = max(0.0, defender.health - actual_damage)
    return actual_damage
