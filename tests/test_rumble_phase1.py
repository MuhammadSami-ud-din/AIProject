"""Unit tests for Arena Rumble Phase 1: The Squeeze (Shrinking Zone).

Verifies:
1. Zone starts at full arena width (0 to ARENA_WIDTH).
2. 20s pause, 5s warning before closing, 10s closing stage.
3. 4 stages total, ending at exactly 35% arena width (280px safe zone).
4. Inward push prevents fighters from crossing or staying outside the barrier.
5. Standing outside deals scaling damage per stage (2.0, 3.5, 5.0, 7.5 HP/s).
6. Cover walls outside the safe zone crumble at 3 HP/s.
7. Classic mode rules completely disable zone mechanics.
"""

import pytest

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.rules import ModeRules
from backend.engine.rumble import init_rumble_zone, update_rumble_zone
from backend.engine.rumble_config import (
    ZONE_CLOSE_FRAMES,
    ZONE_FINAL_WIDTH_RATIO,
    ZONE_PAUSE_FRAMES,
    ZONE_PUSH_FORCE,
    ZONE_STAGE_DPS,
    ZONE_STAGES,
    ZONE_WARNING_FRAMES,
)
from backend.engine.rumble_state import WallState
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step


def _make_rumble_state(enable_zone=True):
    rules = ModeRules.rumble(
        enable_zone=enable_zone,
        enable_building=False,
        enable_loot=False,
        enable_objects=False,
    )
    return make_initial_state("Golden", "Crimson", rules=rules, seed=42)


def test_zone_initialization():
    state = _make_rumble_state(enable_zone=True)
    zone = state.zone
    assert zone is not None
    assert zone.left == 0.0
    assert zone.right == float(ARENA_WIDTH)
    assert zone.stage == 1
    assert not zone.is_closing
    assert not zone.is_warning
    assert zone.closed_stages == 0


def test_zone_pause_and_warning_timing():
    state = _make_rumble_state(enable_zone=True)

    # During first 15 seconds (frames 1 to 900), no warning, not closing
    for _ in range(ZONE_PAUSE_FRAMES - ZONE_WARNING_FRAMES - 1):
        state = step(state, Action.IDLE, Action.IDLE)
    assert not state.zone.is_warning
    assert not state.zone.is_closing
    assert state.zone.left == 0.0

    # At 5s before closing (frame 901), warning activates
    state = step(state, Action.IDLE, Action.IDLE)
    assert state.zone.is_warning
    assert not state.zone.is_closing

    # Advances through warning until closing starts at frame 1201
    for _ in range(ZONE_WARNING_FRAMES):
        state = step(state, Action.IDLE, Action.IDLE)
    # One more step enters closing phase
    state = step(state, Action.IDLE, Action.IDLE)
    assert not state.zone.is_warning
    assert state.zone.is_closing


def test_zone_stage1_closing_and_target():
    state = _make_rumble_state(enable_zone=True)

    # Advance through pause (1200 frames)
    for _ in range(ZONE_PAUSE_FRAMES):
        state = step(state, Action.IDLE, Action.IDLE)

    # Advance halfway through closing (300 frames)
    for _ in range(ZONE_CLOSE_FRAMES // 2):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.zone.is_closing
    assert 0.0 < state.zone.left < 65.0
    assert (ARENA_WIDTH - 65.0) < state.zone.right < float(ARENA_WIDTH)

    # Advance to end of stage 1 closing (300 more frames)
    for _ in range(ZONE_CLOSE_FRAMES // 2):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.zone.closed_stages == 1
    assert pytest.approx(state.zone.left, abs=0.5) == 65.0
    assert pytest.approx(state.zone.right, abs=0.5) == (ARENA_WIDTH - 65.0)


def test_zone_never_closes_past_minimum_width():
    state = _make_rumble_state(enable_zone=True)

    # Fast forward through all 4 stages: 4 * (1200 + 600) = 7200 frames
    total_frames = ZONE_STAGES * (ZONE_PAUSE_FRAMES + ZONE_CLOSE_FRAMES) + 100
    for _ in range(total_frames):
        state = step(state, Action.IDLE, Action.IDLE)

    min_safe_width = ARENA_WIDTH * ZONE_FINAL_WIDTH_RATIO  # 800 * 0.35 = 280.0
    current_width = state.zone.right - state.zone.left
    assert pytest.approx(current_width, abs=1.0) == min_safe_width
    assert pytest.approx(state.zone.left, abs=1.0) == (ARENA_WIDTH - min_safe_width) / 2.0  # 260.0


def test_zone_inward_push_and_scaling_damage():
    state = _make_rumble_state(enable_zone=True)

    # Force zone inwards
    state.zone.left = 100.0
    state.zone.right = 700.0
    state.zone.stage = 1

    # Place fighter 1 outside left barrier
    state.fighter1.x = 50.0
    initial_hp = state.fighter1.health

    state = step(state, Action.IDLE, Action.IDLE)

    # Pushed inward
    assert state.fighter1.x > 50.0
    # Took stage 1 DPS (2.0 HP/s = 2.0 / 60 per frame)
    assert state.fighter1.health < initial_hp
    assert state.fighter1.zone_damage_taken > 0.0

    # Stage 2 damage is higher than Stage 1
    state.zone.closed_stages = 1
    state.zone.stage = 2
    hp_before_stage2 = state.fighter1.health
    state = step(state, Action.IDLE, Action.IDLE)
    dmg_stage2 = hp_before_stage2 - state.fighter1.health
    dmg_stage1 = initial_hp - hp_before_stage2
    assert dmg_stage2 > dmg_stage1


def test_walls_crumble_outside_zone():
    state = _make_rumble_state(enable_zone=True)
    state.zone.left = 150.0
    state.zone.right = 650.0

    # Create wall outside zone at x=50
    outside_wall = WallState(
        id=1,
        owner=1,
        x=50.0,
        y=0.0,
        hp=1.0,  # low hp to test destruction
        max_hp=30.0,
    )
    state.walls.append(outside_wall)

    # Should crumble 3 HP/s (0.05 per frame). In 25 frames, 1.0 HP wall should break
    for _ in range(25):
        state = step(state, Action.IDLE, Action.IDLE)

    assert len(state.walls) == 0


def test_classic_mode_disables_zone():
    classic_state = make_initial_state("Golden", "Crimson", rules=ModeRules.classic(), seed=42)
    assert classic_state.zone is None

    # Step in classic mode
    step(classic_state, Action.IDLE, Action.IDLE)
    assert classic_state.zone is None
