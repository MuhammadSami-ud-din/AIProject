"""Movement and jumping: how fighters walk, jump, crouch, dash, and stay inside the arena."""

from backend.ai.actions import Action
from backend.engine.constants import JUMP_DURATION
from backend.engine.state import FighterState


def apply_movement(fighter: FighterState, action: Action, speed: float,
                   arena_width: float, enemy_x: float) -> None:
    """Move the fighter left or right based on their action.

    Fighters always face each other:
      - FORWARD walks toward the enemy.
      - BACK walks away from the enemy.
      - DASH moves quickly forward.
      - BACKDASH moves backward.
      - CROUCH keeps the fighter low and stationary.
    """
    # Cannot move while stuck, stunned, attacking, or knocked down
    if (fighter.recovery > 0 or fighter.hitstun > 0 or fighter.blockstun > 0 or
            fighter.is_knocked_down or fighter.is_thrown):
        return

    # Update crouching posture
    if action in (Action.CROUCH, Action.BLOCK_LOW, Action.LOW_SWEEP, Action.CROUCH_JAB, Action.CROUCH_KICK):
        fighter.is_crouching = True
    elif not fighter.in_air and action not in (Action.CROUCH, Action.BLOCK_LOW):
        fighter.is_crouching = False

    # Cannot move horizontally while in the air
    if fighter.in_air:
        return

    # Cannot walk while attacking (unless move handles its own movement)
    if fighter.attack_phase != "none" and action != Action.BACKDASH:
        return

    if action not in (Action.FORWARD, Action.BACK, Action.DASH, Action.BACKDASH):
        return

    # Which direction is "forward" depends on where the enemy is.
    facing_right = enemy_x >= fighter.x

    move_speed = speed
    if action == Action.DASH:
        move_speed = speed * 1.8
        direction = 1 if facing_right else -1
    elif action == Action.BACKDASH:
        move_speed = speed * 1.6
        direction = -1 if facing_right else 1
    elif action == Action.FORWARD:
        direction = 1 if facing_right else -1
    else:  # Action.BACK
        direction = -1 if facing_right else 1

    fighter.x += direction * move_speed

    # Clamp to arena walls
    fighter.x = max(0.0, min(arena_width, fighter.x))


def apply_jump(fighter: FighterState, action: Action) -> None:
    """Start or continue a jump. Supports double jump and air dash for Shadow."""
    # In air: handle double jump and air dash
    if fighter.in_air:
        if action == Action.JUMP and fighter.character_name == "Shadow" and fighter.air_jumps_left > 0:
            fighter.jump_frame = 1  # reset jump apex
            fighter.air_jumps_left -= 1
            return

        if action == Action.DASH and fighter.character_name == "Shadow" and fighter.air_dash_left > 0:
            fighter.air_dash_left -= 1
            # Dash forward horizontally in air
            return

        fighter.jump_frame += 1
        if fighter.jump_frame >= JUMP_DURATION:
            # Landed
            fighter.in_air = False
            fighter.jump_frame = 0
            fighter.is_crouching = False
            fighter.air_jumps_left = 1
            fighter.air_dash_left = 1
        return

    # Cannot jump while stuck or stunned
    if (fighter.recovery > 0 or fighter.hitstun > 0 or fighter.blockstun > 0 or
            fighter.is_knocked_down or fighter.is_thrown or fighter.attack_phase != "none"):
        return

    # Start a new jump
    if action == Action.JUMP:
        fighter.in_air = True
        fighter.jump_frame = 1
        fighter.is_crouching = False
        fighter.air_jumps_left = 1
        fighter.air_dash_left = 1


def apply_pushback(attacker: FighterState, defender: FighterState,
                   amount: float, arena_width: float) -> None:
    """Push fighters apart upon hit or block.

    Defender is pushed away from attacker. If defender is blocked by a wall,
    the remaining pushback pushes the attacker backward.
    """
    if amount <= 0:
        return

    # Direction away from attacker (1 if defender is right of attacker, -1 if left)
    away_dir = 1 if defender.x >= attacker.x else -1

    target_defender_x = defender.x + away_dir * amount
    clamped_defender_x = max(0.0, min(arena_width, target_defender_x))

    # How much defender could not move because of the wall
    wall_bounce = abs(target_defender_x - clamped_defender_x)

    defender.x = clamped_defender_x

    # Push attacker back in the opposite direction
    if wall_bounce > 0:
        attacker.x = max(0.0, min(arena_width, attacker.x - away_dir * wall_bounce))
