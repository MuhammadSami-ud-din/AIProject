"""Pushboxes: the body collision box of each fighter.

Two grounded pushboxes can never overlap. When they touch they are pushed
apart evenly; when one fighter is against the arena wall the free fighter
takes the whole push. Pushboxes only collide on the ground, so jumping over
the opponent is still allowed (they are separated the moment the jumper lands).
"""

from backend.engine.constants import PUSHBOX_DEFAULT_HALF_WIDTH, PUSHBOX_HALF_WIDTH


def pushbox_half_width(char_or_fighter) -> float:
    """Half the width of this character's body box, in pixels."""
    name = getattr(char_or_fighter, "character_name", char_or_fighter)
    return PUSHBOX_HALF_WIDTH.get(str(name), PUSHBOX_DEFAULT_HALF_WIDTH)


def min_separation(a, b) -> float:
    """Smallest allowed distance between the centres of two grounded fighters."""
    return pushbox_half_width(a) + pushbox_half_width(b)


def resolve_pushboxes(f1, f2, arena_width: float = 800.0, **kwargs) -> None:
    """Push two overlapping grounded fighters apart (in place)."""
    if f1.in_air or f2.in_air:
        return

    left_bound = float(kwargs.get("left_bound", 0.0))
    right_bound = float(kwargs.get("right_bound", arena_width))

    min_sep = min_separation(f1.character_name, f2.character_name)
    dx = f2.x - f1.x
    if abs(dx) >= min_sep:
        return

    # Work out who is on the left. Exactly on top of each other: P1 goes left.
    left, right = (f1, f2) if dx >= 0.0 else (f2, f1)
    shift = (min_sep - abs(dx)) / 2.0
    left.x -= shift
    right.x += shift

    # Near a wall the free fighter absorbs the rest of the push.
    if left.x < left_bound:
        right.x += (left_bound - left.x)
        left.x = left_bound
    if right.x > right_bound:
        left.x -= (right.x - right_bound)
        right.x = right_bound
        if left.x < left_bound:
            left.x = left_bound
