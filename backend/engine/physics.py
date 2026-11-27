"""Movement and jumping: how fighters walk, jump, crouch, dash, and stay inside the arena."""

from backend.ai.actions import Action
from backend.engine.constants import (
    AIR_DASH_FRAMES,
    AIR_DASH_SPEED,
    ARENA_WIDTH,
    BACKDASH_FRAMES,
    BACKDASH_START_SPEED_MULT,
    DASH_FRAMES,
    DASH_START_SPEED_MULT,
    JUMP_DURATION,
)
from backend.engine.state import FighterState

CROUCH_ACTIONS = (Action.CROUCH, Action.BLOCK_LOW, Action.LOW_SWEEP,
                  Action.CROUCH_JAB, Action.CROUCH_KICK)


def _facing_dir(fighter: FighterState, enemy_x: float) -> int:
    """+1 if the enemy is to the right (or level), else -1."""
    return 1 if enemy_x >= fighter.x else -1


def _clamp_x(x: float, arena_width: float) -> float:
    return max(0.0, min(float(arena_width), x))


def _is_stuck(fighter: FighterState) -> bool:
    """Stunned, recovering, knocked down or grabbed: no voluntary movement."""
    return (fighter.recovery > 0 or fighter.hitstun > 0 or fighter.blockstun > 0 or
            fighter.is_knocked_down or fighter.is_thrown)


# ---------------------------------------------------------------
# Dashes
# ---------------------------------------------------------------

def start_dash(fighter: FighterState, direction: int, frames: int,
               start_speed: float, in_air: bool = False) -> None:
    """Begin a dash: a burst of speed that then decelerates (or hovers in the air)."""
    fighter.dash_frames_left = frames
    fighter.dash_total_frames = frames
    fighter.dash_dir = direction
    fighter.dash_speed = start_speed
    fighter.dash_in_air = in_air


def stop_dash(fighter: FighterState) -> None:
    fighter.dash_frames_left = 0
    fighter.dash_total_frames = 0
    fighter.dash_dir = 0
    fighter.dash_speed = 0.0
    fighter.dash_in_air = False


def start_backdash(fighter: FighterState, base_speed: float, enemy_x: float) -> None:
    """Backdash travel (called when the BACKDASH move starts)."""
    start_dash(fighter, -_facing_dir(fighter, enemy_x), BACKDASH_FRAMES,
               base_speed * BACKDASH_START_SPEED_MULT)


def apply_dash_motion(fighter: FighterState, arena_width: float) -> None:
    """Move a dashing fighter one frame. Ground dashes decelerate linearly;
    air dashes travel at constant speed. Getting hit or grabbed ends the dash."""
    if fighter.dash_frames_left <= 0:
        return
    if fighter.hitstun > 0 or fighter.is_knocked_down or fighter.is_thrown:
        stop_dash(fighter)
        return
    if fighter.dash_in_air:
        speed = fighter.dash_speed
    else:
        speed = fighter.dash_speed * fighter.dash_frames_left / float(max(1, fighter.dash_total_frames))
    fighter.x = _clamp_x(fighter.x + fighter.dash_dir * speed, arena_width)
    fighter.dash_frames_left -= 1
    if fighter.dash_frames_left <= 0:
        stop_dash(fighter)


# ---------------------------------------------------------------
# Walking, crouching, ground dash
# ---------------------------------------------------------------

def apply_movement(fighter: FighterState, action: Action, speed: float,
                   arena_width: float, enemy_x: float) -> None:
    """Move the fighter left or right based on their action.

    Fighters always face each other:
      - FORWARD walks toward the enemy, BACK walks away.
      - DASH starts a forward dash (burst of speed, then deceleration).
        A new dash can start only once the previous one has finished.
      - BACKDASH travel is started by the BACKDASH move itself (see step.py).
      - CROUCH keeps the fighter low and stationary.
    Air movement is handled by apply_air_control().
    """
    if _is_stuck(fighter):
        return

    # Update crouching posture
    if action in CROUCH_ACTIONS:
        fighter.is_crouching = True
    elif not fighter.in_air:
        fighter.is_crouching = False

    if fighter.in_air or fighter.attack_phase != "none":
        return

    if action == Action.DASH:
        if fighter.dash_frames_left <= 0:
            start_dash(fighter, _facing_dir(fighter, enemy_x), DASH_FRAMES,
                       speed * DASH_START_SPEED_MULT)
        return

    # A dash keeps its momentum; walking input does not add to it.
    if fighter.dash_frames_left > 0:
        return

    if action == Action.FORWARD:
        direction = _facing_dir(fighter, enemy_x)
    elif action == Action.BACK:
        direction = -_facing_dir(fighter, enemy_x)
    else:
        return

    fighter.x = _clamp_x(fighter.x + direction * speed, arena_width)


def apply_air_control(fighter: FighterState, action: Action, speed: float,
                      speed_mult: float, arena_width: float, enemy_x: float) -> None:
    """Drift left/right while airborne (FORWARD/DASH toward, BACK/BACKDASH away).

    Not while juggled (hitstun), knocked down, grabbed, or air dashing.
    """
    if not fighter.in_air or speed_mult <= 0.0:
        return
    if fighter.hitstun > 0 or fighter.is_knocked_down or fighter.is_thrown:
        return
    if fighter.dash_frames_left > 0:
        return
    if action in (Action.FORWARD, Action.DASH):
        direction = _facing_dir(fighter, enemy_x)
    elif action in (Action.BACK, Action.BACKDASH):
        direction = -_facing_dir(fighter, enemy_x)
    else:
        return
    fighter.x = _clamp_x(fighter.x + direction * speed * speed_mult, arena_width)


# ---------------------------------------------------------------
# Jumping
# ---------------------------------------------------------------

def _land(fighter: FighterState) -> None:
    fighter.in_air = False
    fighter.jump_frame = 0
    fighter.is_crouching = False
    fighter.air_jumps_left = 1
    fighter.air_dash_left = 1
    if fighter.dash_in_air:
        stop_dash(fighter)


def apply_jump(fighter: FighterState, action: Action, enemy_x: float | None = None) -> None:
    """Start or continue a jump. Supports double jump and air dash for Shadow.

    The jump follows a parabolic arc (see FighterState.y) lasting JUMP_DURATION frames.
    Shadow's air dash (DASH / BACKDASH in the air) travels horizontally at a
    constant speed for AIR_DASH_FRAMES and pauses the jump arc while it lasts.
    """
    if fighter.in_air:
        can_air_act = fighter.hitstun <= 0 and not fighter.is_knocked_down and not fighter.is_thrown
        if (can_air_act and action == Action.JUMP and fighter.character_name == "Shadow"
                and fighter.air_jumps_left > 0):
            fighter.jump_frame = 1  # restart the arc
            fighter.air_jumps_left -= 1
            return

        if (can_air_act and action in (Action.DASH, Action.BACKDASH)
                and fighter.character_name == "Shadow" and fighter.air_dash_left > 0
                and fighter.dash_frames_left <= 0):
            fighter.air_dash_left -= 1
            ex = enemy_x if enemy_x is not None else fighter.x + 1.0
            direction = _facing_dir(fighter, ex)
            if action == Action.BACKDASH:
                direction = -direction
            start_dash(fighter, direction, AIR_DASH_FRAMES, AIR_DASH_SPEED, in_air=True)
            return

        if fighter.dash_in_air and fighter.dash_frames_left > 0:
            return  # hovering during the air dash

        fighter.jump_frame += 1
        if fighter.jump_frame >= JUMP_DURATION:
            _land(fighter)
        return

    # Cannot jump while stuck or stunned
    if _is_stuck(fighter) or fighter.attack_phase != "none":
        return

    if action == Action.JUMP:
        fighter.in_air = True
        fighter.jump_frame = 1
        fighter.is_crouching = False
        fighter.air_jumps_left = 1
        fighter.air_dash_left = 1
        stop_dash(fighter)


def apply_pushback(attacker: FighterState, defender: FighterState,
                   amount: float, arena_width: float = ARENA_WIDTH) -> None:
    """Push fighters apart upon hit or block.

    Defender is pushed away from attacker. If defender is blocked by a wall,
    the remaining pushback pushes the attacker backward.
    """
    if amount <= 0:
        return

    away_dir = 1 if defender.x >= attacker.x else -1

    target_defender_x = defender.x + away_dir * amount
    clamped_defender_x = _clamp_x(target_defender_x, arena_width)

    # How much defender could not move because of the wall
    wall_overflow = abs(target_defender_x - clamped_defender_x)

    defender.x = clamped_defender_x

    if wall_overflow > 0:
        attacker.x = _clamp_x(attacker.x - away_dir * wall_overflow, arena_width)
