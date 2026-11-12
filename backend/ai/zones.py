"""Distance and wall questions: how far, is that comfortable, who can hit whom, am I trapped."""

from enum import Enum

# ---------------------------------------------------------------
# Settings. Change ARENA_WIDTH to Haseeb's real arena width (in pixels)
# and the other distances adjust themselves.
# ---------------------------------------------------------------
ARENA_WIDTH = 800

CLOSE_LIMIT = round(ARENA_WIDTH * 0.10)     # closer than this = CLOSE   (80)
FAR_LIMIT = round(ARENA_WIDTH * 0.275)      # farther than this = FAR    (220)
TOLERANCE = round(ARENA_WIDTH * 0.025)      # "just right" if this near the favourite distance (20)
CORNER_MARGIN = round(ARENA_WIDTH * 0.075)  # this near the wall behind you = cornered (60)
STICKY_BUFFER = 10    # how far past a limit before the zone label changes
MOVE_THRESHOLD = 1    # gap must change by more than this (pixels per frame) to count


class Zone(Enum):
    CLOSE = 0
    MID = 1
    FAR = 2


class Spacing(Enum):
    TOO_CLOSE = 0
    JUST_RIGHT = 1
    TOO_FAR = 2


class Gap(Enum):
    CLOSING = 0    # fighters getting nearer
    STEADY = 1     # about the same distance
    OPENING = 2    # fighters getting farther apart


# ---------------------------------------------------------------
# Distance
# ---------------------------------------------------------------
def distance_between(my_x, enemy_x):
    """How far apart the two fighters are, in pixels."""
    return abs(my_x - enemy_x)


def distance_ratio(distance, arena_width=ARENA_WIDTH):
    """Distance as a number from 0 (touching) to 1 (whole arena apart).
    Used by the scoring code and the learning code."""
    _check_distance(distance)
    return min(distance / arena_width, 1.0)


# ---------------------------------------------------------------
# Question 1: is the enemy CLOSE, MID or FAR?
# ---------------------------------------------------------------
def zone_of(distance):
    """Same answer for every fighter."""
    _check_distance(distance)
    if distance < CLOSE_LIMIT:
        return Zone.CLOSE
    if distance > FAR_LIMIT:
        return Zone.FAR
    return Zone.MID


class ZoneTracker:
    """Like zone_of, but the label does not flicker when the distance
    hovers right on a limit. It only changes when the distance is
    clearly inside the new zone."""

    def __init__(self, buffer=STICKY_BUFFER):
        if buffer < 0:
            raise ValueError("buffer cannot be negative")
        self.buffer = buffer
        self.current = None

    def update(self, distance):
        new_zone = zone_of(distance)
        if self.current is None or new_zone == self.current:
            self.current = new_zone
        else:
            a_bit_closer = zone_of(max(0, distance - self.buffer))
            a_bit_farther = zone_of(distance + self.buffer)
            if a_bit_closer == new_zone == a_bit_farther:
                self.current = new_zone
        return self.current

    def reset(self):
        self.current = None


# ---------------------------------------------------------------
# Question 2: is this the distance THIS fighter likes?
# ---------------------------------------------------------------
def spacing_for(distance, personality, tolerance=TOLERANCE):
    _check_distance(distance)
    gap = distance - personality.preferred_distance
    if gap < -tolerance:
        return Spacing.TOO_CLOSE
    if gap > tolerance:
        return Spacing.TOO_FAR
    return Spacing.JUST_RIGHT


# ---------------------------------------------------------------
# Question 3: is the gap getting smaller or bigger?
# ---------------------------------------------------------------
def gap_change(previous_distance, distance, threshold=MOVE_THRESHOLD):
    _check_distance(previous_distance)
    _check_distance(distance)
    change = distance - previous_distance
    if change < -threshold:
        return Gap.CLOSING
    if change > threshold:
        return Gap.OPENING
    return Gap.STEADY


# ---------------------------------------------------------------
# Question 4: can I hit them? can they hit me?
# (attack ranges come from Haseeb's engine)
# ---------------------------------------------------------------
def in_range(distance, attack_range):
    """True if an attack with this range would reach."""
    _check_distance(distance)
    if attack_range < 0:
        raise ValueError(f"attack_range cannot be negative, got {attack_range}")
    return distance <= attack_range


def is_safe_poke(distance, my_range, enemy_range):
    """True if I can hit them but they cannot hit me back.
    This is Shadow's favourite spot."""
    return in_range(distance, my_range) and not in_range(distance, enemy_range)


# ---------------------------------------------------------------
# Question 5: am I trapped against the wall behind me?
# ---------------------------------------------------------------
def room_behind(my_x, enemy_x, arena_left, arena_right):
    """How many pixels I can still back away before hitting the wall."""
    if arena_left >= arena_right:
        raise ValueError("arena_left must be smaller than arena_right")
    if my_x <= enemy_x:
        # Enemy is on my right, so the wall behind me is the left wall.
        return max(0, my_x - arena_left)
    # Enemy is on my left, so the wall behind me is the right wall.
    return max(0, arena_right - my_x)


def is_cornered(my_x, enemy_x, arena_left, arena_right, margin=CORNER_MARGIN):
    """To check if the ENEMY is cornered, swap the first two numbers."""
    return room_behind(my_x, enemy_x, arena_left, arena_right) < margin


# ---------------------------------------------------------------
# Helper
# ---------------------------------------------------------------
def _check_distance(distance):
    if distance < 0:
        raise ValueError(f"distance cannot be negative, got {distance}")
