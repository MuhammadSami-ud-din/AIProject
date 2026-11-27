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
# Pushboxes (body collision): two grounded fighters can never overlap.
# Half-width in pixels per character; min separation = sum of both.
# ---------------------------------------------------------------
PUSHBOX_HALF_WIDTH = {
    "Crimson": 16.0,
    "Steel": 18.0,
    "Shadow": 14.0,
    "Golden": 15.0,
}
PUSHBOX_DEFAULT_HALF_WIDTH = 15.0

# ---------------------------------------------------------------
# Projectile limits: shooting is a spice, not the whole game.
# ---------------------------------------------------------------
PROJECTILE_COOLDOWN_FRAMES = 150   # 2.5 s before the same fighter may shoot again
PROJECTILE_MAX_ACTIVE = 1          # at most one of your shots flying at a time
PROJECTILE_MAX_PER_ROUND = 4       # at most 4 shots per fighter per round

# ---------------------------------------------------------------
# Jumping
# ---------------------------------------------------------------
JUMP_DURATION = 40         # total frames a jump lasts (up + down)

# ---------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------
BLOCK_DAMAGE_RATIO = 0.10  # a blocked hit does 10% of its full damage

# ---------------------------------------------------------------
# Health Regeneration (Campaign & Human vs AI matches only)
# ---------------------------------------------------------------
REGEN_DELAY_FRAMES = 120        # ~2.0 seconds without taking damage
REGEN_RATE_PER_SECOND = 0.015   # 1.5% max health recovered per second
REGEN_RATE_PER_FRAME = REGEN_RATE_PER_SECOND / FPS  # ~0.00025 per frame


# ---------------------------------------------------------------
# Jump arc and air movement
# ---------------------------------------------------------------
JUMP_HEIGHT = 110.0             # apex height of a jump, in pixels
AIR_CONTROL_SPEED_MULT = 0.5    # Classic: small air control (x walk speed)
RUMBLE_AIR_SPEED_MULT = 1.0     # Rumble / Shield Wall: full-speed air movement

# ---------------------------------------------------------------
# Hurtboxes (vertical axis). Heights in pixels above the floor.
# ---------------------------------------------------------------
STAND_HURTBOX_HEIGHT = 100.0    # standing body
CROUCH_HURTBOX_HEIGHT = 60.0    # crouching body (high-aimed attacks whiff)
AIR_HURTBOX_HEIGHT = 80.0       # airborne body, starting at the fighter's y

# ---------------------------------------------------------------
# Dashes
# ---------------------------------------------------------------
DASH_FRAMES = 14                # forward dash: burst of speed, then decel
DASH_START_SPEED_MULT = 3.2     # first-frame dash speed (x walk speed)
BACKDASH_FRAMES = 14            # backdash travel frames (the move lasts 16)
BACKDASH_START_SPEED_MULT = 3.0
AIR_DASH_FRAMES = 8             # Shadow air dash: constant-speed hover
AIR_DASH_SPEED = 10.0           # px per frame

# ---------------------------------------------------------------
# Defense: guard meter, parry, throws, wakeup
# ---------------------------------------------------------------
GUARD_METER_MAX = 100.0
GUARD_DRAIN_PER_BLOCK = 18.0    # every blocked melee hit
GUARD_REGEN_PER_FRAME = 0.25    # when not holding block
GUARD_BREAK_STUN_FRAMES = 40
GUARD_AFTER_BREAK = 50.0        # guard meter refilled to this after a break

PARRY_WINDOW_FRAMES = 4         # a fresh block press parries for this many frames
PARRY_STAGGER_FRAMES = 22       # attacker stuck after being parried
PARRY_METER_GAIN = 12.0
PARRY_LOCKOUT_FRAMES = 24       # after a failed parry, fresh taps only block

THROW_TECH_WINDOW = 7           # frames the victim has to tech a throw
THROW_TECH_RECOVERY = 8         # both fighters stuck after a tech / throw clash
THROW_TECH_PUSHBACK = 40.0
THROW_LAND_PUSHBACK = 50.0
THROW_METER_GAIN = 12.0
WAKEUP_INVULN_FRAMES = 6        # strike invulnerability on wakeup
WAKEUP_THROW_INVULN_FRAMES = 10 # throw invulnerability on wakeup
POST_STUN_THROW_INVULN_FRAMES = 5  # throw invuln after leaving hit/blockstun

BURST_METER_COST = 50.0
BURST_PUSHBACK = 140.0
BURST_STAGGER_FRAMES = 20

# ---------------------------------------------------------------
# Hits, combos and bounces
# ---------------------------------------------------------------
METER_MAX = 100.0
METER_GAIN_WHEN_HIT = 3.0       # defender meter on taking a clean hit
METER_GAIN_WHEN_BLOCKING = 1.5  # defender meter on blocking
COUNTER_HIT_BONUS_METER = 5.0
COUNTER_HITSTUN_MULT = 1.5      # counter-hit: +50% hitstun
COMBO_SCALING_STEP = 0.10       # 100%, 90%, 80% ...
COMBO_SCALING_MIN = 0.30
HITSTUN_DECAY_PER_HIT = 2       # infinite-combo protection
MIN_HITSTUN = 4
FURY_HEALTH_THRESHOLD = 0.25
FURY_DAMAGE_MULT = 1.10         # +10% damage in Fury
FURY_SUPER_COST = 60.0
JUGGLE_CAP = 4
KNOCKDOWN_FRAMES = 30
WALL_BOUNCE_DISTANCE = 35.0     # px from the wall that counts as "near"
WALL_BOUNCE_MIN_DAMAGE = 8.0    # HP; heavier hits bounce near the wall
WALL_BOUNCE_HITSTUN = 24
GROUND_BOUNCE_HITSTUN = 22
THROW_GROUND_BOUNCE_HITSTUN = 24
SUPER_FREEZE_FRAMES = 15

COUNTER_STANCE_DAMAGE = 0.16        # Steel Iron Wall counter (health fraction)
COUNTER_STANCE_SUPER_DAMAGE = 0.35  # Steel Fortress Crush counter
COUNTER_STANCE_HITSTUN = 35
COUNTER_STANCE_PUSHBACK = 60.0

# ---------------------------------------------------------------
# Projectiles (Energy Dart)
# ---------------------------------------------------------------
PROJECTILE_SPAWN_OFFSET = 30.0
PROJECTILE_REACH = 30.0
PROJECTILE_HEIGHT = 50.0        # centre height above the floor
PROJECTILE_HALF_HEIGHT = 15.0   # so it flies from 35 to 65 px: jump over it
PROJECTILE_HITSTUN = 16
PROJECTILE_BLOCKSTUN = 12
PROJECTILE_GUARD_DRAIN = 10.0
PROJECTILE_METER_GAIN_HIT = 8.0
REFLECTOR_RADIUS = 65.0         # Steel Reflector catch distance
REFLECTED_LIFETIME = 60

# ---------------------------------------------------------------
# Character specials
# ---------------------------------------------------------------
ARENA_EDGE_MARGIN = 20.0
SHADOW_STEP_SLIP_RANGE = 140.0  # closer than this: slip behind the opponent
SHADOW_STEP_BEHIND_OFFSET = 55.0
SHADOW_STEP_FAR_DISTANCE = 75.0 # farther: bounded forward step
SHADOW_STEP_INVULN = 6

GOLDEN_READ_WINDOW = 30         # frames the read prediction stays live
GOLDEN_READ_BONUS_FRAMES = 60   # after a successful read: next hit is boosted
GOLDEN_READ_DAMAGE_MULT = 1.25  # boosted hit: +25% damage and a counter-hit
GOLDEN_RUSH_DAMAGE_MULT = 1.08  # Rush stance: +8% damage on clean hits
GOLDEN_GUARD_CHIP_MULT = 0.5    # Guard stance: half chip damage
GOLDEN_GUARD_DRAIN_MULT = 0.6   # Guard stance: 40% less guard drain
GOLDEN_EVADE_SPEED_MULT = 1.10  # Evade stance: +10% walk speed
GOLDEN_EVADE_EXTRA_INVULN = 2   # Evade stance: +2 invuln frames on evasive moves

SHIELD_THROW_EXTRA_REACH = 45.0 # throws reach past an enemy shield wall


# ---------------------------------------------------------------
# Base attack summary (derived from the real move data)
# ---------------------------------------------------------------
# The real frame data lives in moves.py (MoveData). AttackData is a small
# summary of the universal Jab (LIGHT) and Heavy Punch (HEAVY) that older
# code and the AI adapter use. It is derived, never typed in twice.


@dataclass(frozen=True)
class AttackData:
    """Summary numbers for one base attack."""
    damage: float      # health fraction (0 to 1 scale)
    reach: float       # pixels
    startup: int       # frames of wind-up before the hit
    active: int        # frames the hit box is live
    recovery: int      # frames the attacker is stuck afterwards
    cooldown: int      # total frames before the attack can be used again


def _attack_data_from_move(action_name: str) -> AttackData:
    from backend.ai.actions import Action
    from backend.engine.moves import UNIVERSAL_MOVES

    move = UNIVERSAL_MOVES[Action[action_name]]
    return AttackData(
        damage=move.health_damage,
        reach=move.reach,
        startup=move.startup,
        active=move.active,
        recovery=move.recovery,
        cooldown=move.startup + move.active + move.recovery,
    )


LIGHT_ATTACK = _attack_data_from_move("LIGHT")
HEAVY_ATTACK = _attack_data_from_move("HEAVY")
