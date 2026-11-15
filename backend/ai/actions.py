"""The actions a fighter can make, and handy groups of them."""

from enum import Enum


class Action(Enum):
    IDLE = 0
    FORWARD = 1
    BACK = 2
    JUMP = 3
    LIGHT = 4         # Jab
    HEAVY = 5         # Heavy punch
    BLOCK = 6         # High block

    # Movement & Stances
    CROUCH = 7
    DASH = 8
    BACKDASH = 9

    # New Normals
    LIGHT_KICK = 10
    HEAVY_KICK = 11
    LOW_SWEEP = 12
    OVERHEAD = 13
    CROUCH_JAB = 14
    CROUCH_KICK = 15
    JUMP_PUNCH = 16
    JUMP_KICK = 17
    ANTI_AIR = 18

    # Defense & Throws
    BLOCK_LOW = 19
    THROW = 20

    # Reserved for Phases 2-4 (Specials, Super, Burst)
    SPECIAL_NEUTRAL = 21
    SPECIAL_FORWARD = 22
    SPECIAL_BACK = 23
    SPECIAL_DOWN = 24
    SUPER = 25
    BURST = 26

    # Aliases
    JAB = 4
    HEAVY_PUNCH = 5
    BLOCK_HIGH = 6


# Every move (tuples cannot be changed by accident)
ALL_ACTIONS = tuple(Action)

# Groups of moves
ATTACKS = (
    Action.LIGHT,
    Action.HEAVY,
    Action.LIGHT_KICK,
    Action.HEAVY_KICK,
    Action.LOW_SWEEP,
    Action.OVERHEAD,
    Action.CROUCH_JAB,
    Action.CROUCH_KICK,
    Action.JUMP_PUNCH,
    Action.JUMP_KICK,
    Action.ANTI_AIR,
    Action.THROW,
    Action.SPECIAL_NEUTRAL,
    Action.SPECIAL_FORWARD,
    Action.SPECIAL_BACK,
    Action.SPECIAL_DOWN,
    Action.SUPER,
)

MOVEMENT = (
    Action.FORWARD,
    Action.BACK,
    Action.JUMP,
    Action.CROUCH,
    Action.DASH,
    Action.BACKDASH,
)

DEFENCE = (
    Action.BLOCK,
    Action.BLOCK_LOW,
    Action.BURST,
)
