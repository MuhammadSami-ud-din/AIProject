"""Checks that all AI settings make sense together. The game calls
check_settings() once at startup, so a bad number is found before a fight,
not in the middle of a demo."""

from backend.ai import observation, zones
from backend.ai.personalities import ALL_PERSONALITIES


def find_problems():
    """Return a list of problems in plain words (empty list = all good)."""
    problems = []

    # Distances
    if not 0 < zones.CLOSE_LIMIT < zones.FAR_LIMIT < zones.ARENA_WIDTH:
        problems.append("need 0 < CLOSE_LIMIT < FAR_LIMIT < ARENA_WIDTH")
    if zones.CORNER_MARGIN * 2 >= zones.ARENA_WIDTH:
        problems.append("CORNER_MARGIN is so big that the whole arena counts as a corner")
    if zones.STICKY_BUFFER * 2 >= zones.FAR_LIMIT - zones.CLOSE_LIMIT:
        problems.append("STICKY_BUFFER is too big for the MID zone; zones would never change")

    # Fighters
    for key, fighter in ALL_PERSONALITIES.items():
        if key != fighter.name:
            problems.append(f"ALL_PERSONALITIES key {key!r} does not match name {fighter.name!r}")
        if fighter.preferred_distance > zones.ARENA_WIDTH:
            problems.append(f"{fighter.name} wants to stand farther away than the arena is wide")

    # Time
    if observation.FRAMES_PER_SECOND <= 0:
        problems.append("FRAMES_PER_SECOND must be above 0")
    if not 0 < observation.LOW_TIME < observation.ROUND_SECONDS:
        problems.append("need 0 < LOW_TIME < ROUND_SECONDS")
    if observation.WINS_NEEDED < 1:
        problems.append("WINS_NEEDED must be at least 1")

    return problems


def check_settings():
    """Stop with a clear message if any setting is wrong."""
    problems = find_problems()
    if problems:
        raise ValueError("AI settings problems:\n- " + "\n- ".join(problems))
    return True
