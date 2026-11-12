"""The 7 moves a fighter can make, and handy groups of them."""

from enum import Enum


class Action(Enum):
    IDLE = 0
    FORWARD = 1
    BACK = 2
    JUMP = 3
    LIGHT = 4
    HEAVY = 5
    BLOCK = 6


# Every move (tuples cannot be changed by accident)
ALL_ACTIONS = tuple(Action)

# Groups of moves
ATTACKS = (Action.LIGHT, Action.HEAVY)
MOVEMENT = (Action.FORWARD, Action.BACK, Action.JUMP)
DEFENCE = (Action.BLOCK,)
