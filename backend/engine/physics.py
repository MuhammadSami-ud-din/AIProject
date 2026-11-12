"""Movement and jumping: how fighters walk, jump, and stay inside the arena."""

from backend.ai.actions import Action
from backend.engine.constants import JUMP_DURATION
from backend.engine.state import FighterState


def apply_movement(fighter: FighterState, action: Action, speed: float,
                   arena_width: float, enemy_x: float) -> None:
    """Move the fighter left or right based on their action.

    Fighters always face each other:
      - FORWARD walks toward the enemy.
      - BACK walks away from the enemy.
    The fighter is clamped to stay inside the arena (0 to arena_width).
    A fighter in recovery (stuck after attacking) cannot move.
    """
    # Cannot move while stuck after an attack
    if fighter.recovery > 0:
        return

    # Cannot move while in the air (horizontal movement locked during jump)
    if fighter.in_air:
        return

    if action not in (Action.FORWARD, Action.BACK):
        return

    # Which direction is "forward" depends on where the enemy is.
    if enemy_x >= fighter.x:
        # Enemy is to my right: forward = right (+), back = left (-)
        direction = 1 if action == Action.FORWARD else -1
    else:
        # Enemy is to my left: forward = left (-), back = right (+)
        direction = -1 if action == Action.FORWARD else 1

    fighter.x += direction * speed

    # Clamp to arena walls
    fighter.x = max(0.0, min(arena_width, fighter.x))


def apply_jump(fighter: FighterState, action: Action) -> None:
    """Start a jump if the fighter presses JUMP while on the ground.

    A jump lasts JUMP_DURATION frames. The fighter is marked as in_air
    for the whole jump. The actual Y position is calculated by the
    renderer (frontend) using jump_frame — the engine only tracks
    whether the fighter is airborne and how far through the jump they are.
    """
    # Already in the air: keep going
    if fighter.in_air:
        fighter.jump_frame += 1
        if fighter.jump_frame >= JUMP_DURATION:
            # Landed
            fighter.in_air = False
            fighter.jump_frame = 0
        return

    # Cannot jump while stuck after an attack
    if fighter.recovery > 0:
        return

    # Start a new jump
    if action == Action.JUMP:
        fighter.in_air = True
        fighter.jump_frame = 1
