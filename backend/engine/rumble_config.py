"""Arena Rumble Configuration.

ALL numeric values, sizes, timings, HP values, item effects, and spawn chances
for the ARENA RUMBLE mode live in this single file.
Nothing elsewhere should hard-code any rumble-specific balance number.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Mode Timing
# ---------------------------------------------------------------------------
FPS: int = 60
RUMBLE_ROUND_SECONDS: int = 120
RUMBLE_ROUND_FRAMES: int = FPS * RUMBLE_ROUND_SECONDS  # 7200 frames


# ---------------------------------------------------------------------------
# Phase 1: Shrinking Zone ("The Squeeze")
# ---------------------------------------------------------------------------
ZONE_STAGES: int = 4
ZONE_PAUSE_SECONDS: float = 20.0
ZONE_PAUSE_FRAMES: int = int(ZONE_PAUSE_SECONDS * FPS)  # 1200 frames
ZONE_CLOSE_SECONDS: float = 10.0
ZONE_CLOSE_FRAMES: int = int(ZONE_CLOSE_SECONDS * FPS)  # 600 frames
ZONE_STAGE_CYCLE_FRAMES: int = ZONE_PAUSE_FRAMES + ZONE_CLOSE_FRAMES  # 1800 frames (30s)
ZONE_WARNING_SECONDS: float = 5.0
ZONE_WARNING_FRAMES: int = int(ZONE_WARNING_SECONDS * FPS)  # 300 frames

ZONE_FINAL_WIDTH_RATIO: float = 0.35  # Barrier ends at 35% of arena width
ZONE_BASE_DPS: float = 2.0  # HP per second outside barrier in stage 1
# Damage per second for each of the 4 stages (increases each stage)
ZONE_STAGE_DPS: Tuple[float, float, float, float] = (2.0, 3.5, 5.0, 7.5)
ZONE_PUSH_FORCE: float = 4.0  # Inward push speed (pixels per frame)


# ---------------------------------------------------------------------------
# Phase 2: Building (Cover Walls)
# ---------------------------------------------------------------------------
BUILD_START_CHARGES: int = 3
BUILD_MAX_CHARGES: int = 3
BUILD_RECHARGE_SECONDS: float = 8.0
BUILD_RECHARGE_FRAMES: int = int(BUILD_RECHARGE_SECONDS * FPS)  # 480 frames

WALL_WIDTH: float = 40.0
WALL_HEIGHT: float = 120.0
WALL_MAX_HP: float = 30.0
WALL_BUILD_TIME_FRAMES: int = 12  # Time to place wall (fighter can be hit)
WALL_MAX_PER_FIGHTER: int = 2     # Max 2 walls per fighter on screen
WALL_OFFSET_X: float = 40.0       # Distance in front of fighter to place wall

WALL_LIGHT_ATTACK_DAMAGE: float = 5.0
WALL_HEAVY_ATTACK_DAMAGE: float = 12.0
WALL_CRACK_1_RATIO: float = 0.66   # Show first cracks <= 66% HP (20 HP)
WALL_CRACK_2_RATIO: float = 0.33   # Show heavy cracks <= 33% HP (10 HP)
WALL_CRUMBLE_DPS: float = 3.0      # Slowly crumbles outside safe zone (3 HP/s)


# ---------------------------------------------------------------------------
# Phase 3: Loot and Supply Drops
# ---------------------------------------------------------------------------
LOOT_SPAWN_MIN_SECONDS: float = 12.0
LOOT_SPAWN_MIN_FRAMES: int = int(LOOT_SPAWN_MIN_SECONDS * FPS)  # 720 frames
LOOT_SPAWN_MAX_SECONDS: float = 18.0
LOOT_SPAWN_MAX_FRAMES: int = int(LOOT_SPAWN_MAX_SECONDS * FPS)  # 1080 frames
LOOT_MAX_GROUND_ITEMS: int = 2
LOOT_PICKUP_RADIUS: float = 32.0

# Standard ground loot effects (Original mechanics)
MEDKIT_HP: float = 25.0           # +25 HP (cannot exceed starting HP)
SHIELD_CELL_HP: float = 25.0      # +25 Shield (absorbs damage before health)
SHIELD_MAX_HP: float = 25.0       # Max shield capacity
SHIELD_DECAY_FRAMES: int = int(3.0 * FPS)  # Decays 1 per 3s (180 frames)
METER_ORB_AMOUNT: float = 30.0    # +30% special meter
BUILD_KIT_CHARGES: int = 2        # +2 build charges
BUILD_KIT_MAX_EXTRA: int = 1      # Can exceed max by 1 (max 4 charges)
SPEED_BOOTS_MULTIPLIER: float = 1.30  # +30% movement speed for 6s
SPEED_BOOTS_DURATION_FRAMES: int = int(6.0 * FPS)  # 360 frames (6s)
POWER_FIST_MULTIPLIER: float = 1.25   # +25% attack damage for 5s
POWER_FIST_DURATION_FRAMES: int = int(5.0 * FPS)   # 300 frames (5s)

# Supply Drop (arrives at 30s remaining in round)
SUPPLY_DROP_REMAINING_SECONDS: float = 30.0
SUPPLY_DROP_TRIGGER_FRAME: int = int((RUMBLE_ROUND_SECONDS - SUPPLY_DROP_REMAINING_SECONDS) * FPS)  # at 30s left
SUPPLY_DROP_FALL_SECONDS: float = 4.0
SUPPLY_DROP_FALL_SPEED: float = 300.0 / (SUPPLY_DROP_FALL_SECONDS * FPS)  # Drops from y=300 down to 0 in 4s
SUPPLY_DROP_WIDTH: float = 48.0
SUPPLY_DROP_HEIGHT: float = 48.0
BIG_MEDKIT_HP: float = 50.0           # +50 HP
OVERCHARGE_METER: float = 50.0        # +50% meter
OVERCHARGE_CHARGES: int = 3           # +3 build charges


# ---------------------------------------------------------------------------
# Phase 4: Arena Objects (Crates, Jump Pads, Traps)
# ---------------------------------------------------------------------------
CRATE_MAX_HP: float = 25.0
CRATE_DROP_CHANCE: float = 0.50       # 50% chance to drop standard item
CRATE_WIDTH: float = 36.0
CRATE_HEIGHT: float = 48.0

JUMP_PAD_COOLDOWN_FRAMES: int = int(3.0 * FPS)  # 180 frames (3s)
JUMP_PAD_LAUNCH_VY: float = -18.0     # Upward velocity
JUMP_PAD_WIDTH: float = 52.0
JUMP_PAD_HEIGHT: float = 16.0

TRAP_TRIGGER_DELAY_FRAMES: int = int(0.5 * FPS)  # 30 frames (0.5s)
TRAP_COOLDOWN_FRAMES: int = int(10.0 * FPS)     # 600 frames (10s)
TRAP_DAMAGE: float = 8.0              # 8 HP damage
TRAP_KNOCKUP_VY: float = -9.0         # Upward knock-up
TRAP_WIDTH: float = 44.0
TRAP_HEIGHT: float = 12.0

# Predefined arena layouts for destructible crates, jump pads, and spike traps
# Coordinates are relative to arena width 800
ARENA_LAYOUTS: Dict[str, Dict[str, List[float]]] = {
    "Dojo": {
        "crates": [220.0, 580.0],
        "jump_pads": [140.0, 660.0],
        "traps": [400.0],
    },
    "Rooftop": {
        "crates": [180.0, 320.0, 480.0, 620.0],
        "jump_pads": [400.0],
        "traps": [260.0, 540.0],
    },
    "Colosseum": {
        "crates": [250.0, 550.0],
        "jump_pads": [160.0, 640.0],
        "traps": [330.0, 470.0],
    },
    "Neon Alley": {
        "crates": [200.0, 360.0, 600.0],
        "jump_pads": [120.0, 680.0],
        "traps": [400.0],
    },
}
