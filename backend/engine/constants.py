"""All the numbers that define how the game works.

Every rule, speed, damage value and timing lives here.
The engine reads these; nothing else should hard-code a game number.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------
# Arena and timing
# ---------------------------------------------------------------
ARENA_WIDTH = 800          # pixels wide
FPS = 60                   # frames per second (fixed timestep)
ROUND_SECONDS = 60         # how long one round lasts
ROUND_FRAMES = FPS * ROUND_SECONDS   # total frames in a round (3600)
WINS_NEEDED = 2            # rounds needed to win the match
MAX_ROUNDS = 3             # play at most this many rounds

# ---------------------------------------------------------------
# Movement
# ---------------------------------------------------------------
WALK_SPEED = 4             # pixels per frame when walking

# ---------------------------------------------------------------
# Jumping
# ---------------------------------------------------------------
JUMP_DURATION = 40         # total frames a jump lasts (up + down)

# ---------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------
BLOCK_DAMAGE_RATIO = 0.10  # a blocked hit does 10% of its full damage

# ---------------------------------------------------------------
# Attack data
# ---------------------------------------------------------------
# Each attack has: damage, reach, startup, active, recovery, cooldown.
# Startup  = frames before the hit can connect (wind-up animation).
# Active   = frames during which the hit box is live.
# Recovery = frames after the active part where the attacker is stuck.
# Cooldown = total frames before the same attack can be used again.


@dataclass(frozen=True)
class AttackData:
    """Numbers for one type of attack (light or heavy)."""
    damage: float      # how much health it removes (0 to 1 scale)
    reach: float       # how far it reaches, in pixels
    startup: int       # frames of wind-up before the hit
    active: int        # frames the hit box is live
    recovery: int      # frames the attacker is stuck afterwards
    cooldown: int      # frames before this attack can be used again


# Base values — character multipliers are applied on top of these.
LIGHT_ATTACK = AttackData(
    damage=0.05,
    reach=70,
    startup=4,
    active=3,
    recovery=8,
    cooldown=12,
)

HEAVY_ATTACK = AttackData(
    damage=0.12,
    reach=90,
    startup=10,
    active=4,
    recovery=18,
    cooldown=30,
)
