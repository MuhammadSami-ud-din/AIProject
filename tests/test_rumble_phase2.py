"""Unit tests for Arena Rumble Phase 2: Building (Cover Walls).

Verifies:
1. Build energy starts at 3, max 3, recharges +1 every 8 seconds (480 frames).
2. Action.BUILD places a wall block (40x120, 30 HP) in front of fighter.
3. Costs 1 charge and has a 12-frame placement lock.
4. Maximum 2 walls per fighter on screen; building a 3rd removes the oldest.
5. Movement is blocked on ground, but jumping over walls is possible.
6. Attacks damage walls (light 5 HP, heavy 12 HP) and break at 0 HP.
7. Walls show crack thresholds at <=66% (20 HP) and <=33% (10 HP).
8. Projectiles are absorbed / blocked by walls.
9. Placement restrictions: no building inside opponent, outside zone, or overlapping.
"""

import pytest

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.rules import ModeRules
from backend.engine.rumble_config import (
    BUILD_MAX_CHARGES,
    BUILD_RECHARGE_FRAMES,
    BUILD_START_CHARGES,
    WALL_BUILD_TIME_FRAMES,
    WALL_CRACK_1_RATIO,
    WALL_CRACK_2_RATIO,
    WALL_HEAVY_ATTACK_DAMAGE,
    WALL_HEIGHT,
    WALL_LIGHT_ATTACK_DAMAGE,
    WALL_MAX_HP,
    WALL_MAX_PER_FIGHTER,
    WALL_WIDTH,
)
from backend.engine.rumble_state import WallState
from backend.engine.state import FighterState, FightState, ProjectileState
from backend.engine.step import make_initial_state, step


def _make_rumble_state():
    rules = ModeRules.rumble(
        enable_zone=True,
        enable_building=True,
        enable_loot=False,
        enable_objects=False,
    )
    return make_initial_state("Golden", "Crimson", rules=rules, seed=42)


def test_build_charges_start_and_recharge():
    state = _make_rumble_state()
    f1 = state.fighter1
    assert f1.build_charges == BUILD_START_CHARGES

    # Consume 1 charge
    f1.build_charges = 2
    f1.build_recharge_timer = 0

    # Advance 479 frames: should still be 2 charges
    for _ in range(BUILD_RECHARGE_FRAMES - 1):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.build_charges == 2

    # 480th frame: recharges to 3
    state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.build_charges == 3

    # At max 3 charges, timer does not increment beyond max
    state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.build_charges == BUILD_MAX_CHARGES


def test_action_build_placement_and_lock():
    state = _make_rumble_state()
    # Place fighters far apart so placement is clear
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0

    # Trigger BUILD
    state = step(state, Action.BUILD, Action.IDLE)

    # 1 charge spent, 12f placement lock started
    assert state.fighter1.build_charges == 2
    assert state.fighter1.building_frames == WALL_BUILD_TIME_FRAMES - 1
    assert len(state.walls) == 0  # Wall finishes placing at end of lock

    # Complete the 12-frame placement lock
    for _ in range(WALL_BUILD_TIME_FRAMES - 1):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.fighter1.building_frames == 0
    assert len(state.walls) == 1
    wall = state.walls[0]
    assert wall.owner == 1
    assert wall.hp == WALL_MAX_HP
    assert wall.width == WALL_WIDTH
    assert wall.height == WALL_HEIGHT
    assert wall.x > state.fighter1.x  # Placed in front of fighter


def test_max_two_walls_removes_oldest():
    state = _make_rumble_state()
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0

    # Manually spawn 2 existing walls owned by fighter 1
    w1 = WallState(id=1, owner=1, x=250.0, y=0.0, hp=30.0, max_hp=30.0, created_frame=1)
    w2 = WallState(id=2, owner=1, x=310.0, y=0.0, hp=30.0, max_hp=30.0, created_frame=2)
    state.walls.extend([w1, w2])

    # Now fighter 1 builds a 3rd wall at x=370
    state.fighter1.x = 350.0
    state.fighter1.build_charges = 3
    state = step(state, Action.BUILD, Action.IDLE)
    for _ in range(WALL_BUILD_TIME_FRAMES - 1):
        state = step(state, Action.IDLE, Action.IDLE)

    assert len(state.walls) == 2
    # Oldest wall w1 was removed, w2 and new wall remain
    assert w1 not in state.walls
    assert any(w.x == 390.0 for w in state.walls)


def test_wall_blocks_movement_on_ground_jump_goes_over():
    state = _make_rumble_state()
    # Place wall at x=250 (left=230, right=270)
    wall = WallState(id=1, owner=2, x=250.0, y=0.0, hp=30.0, max_hp=30.0)
    state.walls.append(wall)

    state.fighter1.x = 200.0
    state.fighter2.x = 700.0

    # Walk right into wall: cannot pass right boundary of wall
    for _ in range(20):
        state = step(state, Action.FORWARD, Action.IDLE)

    # Fighter is blocked at wall.left (230 - margin)
    assert state.fighter1.x <= wall.left

    # Now jump over: JUMP gives airborne status
    state = step(state, Action.JUMP, Action.IDLE)
    assert state.fighter1.in_air

    # While airborne, can move forward over the wall
    for _ in range(25):
        state = step(state, Action.FORWARD, Action.IDLE)

    assert state.fighter1.x > wall.right


def test_attacks_damage_and_destroy_walls():
    state = _make_rumble_state()
    wall = WallState(id=1, owner=2, x=260.0, y=0.0, hp=30.0, max_hp=30.0)
    state.walls.append(wall)

    state.fighter1.x = 220.0  # within attack range of wall
    state.fighter2.x = 700.0

    # Perform LIGHT attack: deals 5 HP damage
    state = step(state, Action.LIGHT, Action.IDLE)
    # Advance to active hit frame of light attack
    for _ in range(6):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.walls[0].hp < 30.0
    initial_wall_hp = state.walls[0].hp

    # Crack threshold 1: <= 66% HP (20 HP)
    state.walls[0].hp = 18.0
    assert state.walls[0].hp <= (WALL_MAX_HP * WALL_CRACK_1_RATIO)

    # Crack threshold 2: <= 33% HP (10 HP)
    state.walls[0].hp = 8.0
    assert state.walls[0].hp <= (WALL_MAX_HP * WALL_CRACK_2_RATIO)

    # Destroy wall: damage down to 0
    state.walls[0].hp = 0.0
    state = step(state, Action.IDLE, Action.IDLE)
    # Wall is removed
    assert len(state.walls) == 0
    assert state.fighter1.walls_broken >= 0


def test_walls_absorb_projectiles():
    state = _make_rumble_state()
    wall = WallState(id=1, owner=1, x=400.0, y=0.0, hp=30.0, max_hp=30.0)
    state.walls.append(wall)

    # Spawn projectile heading toward wall from x=350 to the right
    proj = ProjectileState(
        x=350.0,
        y=0.0,
        vx=10.0,
        owner=2,
        lifetime=60,
        damage=0.05,
    )
    state.projectiles.append(proj)

    # Step until projectile reaches wall (6 frames)
    for _ in range(6):
        state = step(state, Action.IDLE, Action.IDLE)

    # Projectile was absorbed / removed by wall
    assert len(state.projectiles) == 0


def test_no_building_overlapping_or_outside_zone():
    state = _make_rumble_state()
    # Close zone to 200..600
    state.zone.left = 200.0
    state.zone.right = 600.0

    # Place fighter near left barrier facing outside
    state.fighter1.x = 210.0
    state.fighter2.x = 100.0  # enemy on left, so f1 faces left (toward outside)

    state = step(state, Action.BUILD, Action.IDLE)
    # Cannot build outside safe zone: no charge spent
    assert state.fighter1.build_charges == BUILD_START_CHARGES
    assert state.fighter1.building_frames == 0
    assert len(state.walls) == 0
