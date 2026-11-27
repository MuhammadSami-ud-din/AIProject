"""Tests for engine constants: checks every game number is set correctly."""

import pytest

from backend.engine.constants import (
    ARENA_WIDTH,
    BLOCK_DAMAGE_RATIO,
    FPS,
    HEAVY_ATTACK,
    JUMP_DURATION,
    LIGHT_ATTACK,
    MAX_ROUNDS,
    ROUND_FRAMES,
    ROUND_SECONDS,
    WALK_SPEED,
    WINS_NEEDED,
)


# --- Arena and timing -----------------------------------------------

def test_arena_width():
    assert ARENA_WIDTH == 800


def test_fps():
    assert FPS == 60


def test_round_seconds():
    assert ROUND_SECONDS == 60


def test_round_frames_matches():
    """ROUND_FRAMES should be FPS * ROUND_SECONDS."""
    assert ROUND_FRAMES == FPS * ROUND_SECONDS


def test_wins_needed():
    assert WINS_NEEDED == 2


def test_max_rounds():
    assert MAX_ROUNDS == 3


# --- Movement -------------------------------------------------------

def test_walk_speed():
    assert WALK_SPEED == 4


def test_jump_duration():
    assert JUMP_DURATION == 40


# --- Blocking -------------------------------------------------------

def test_block_reduces_to_ten_percent():
    assert BLOCK_DAMAGE_RATIO == 0.10


# --- Base attack summaries are derived from the real move data ---------
# (Old literal values 0.05/70/4/3/8 and 0.12/90/... were a second, stale copy
#  of the frame data; LIGHT_ATTACK / HEAVY_ATTACK now mirror MoveData.)

def test_light_attack_matches_jab_move_data():
    from backend.ai.actions import Action
    from backend.engine.moves import UNIVERSAL_MOVES
    jab = UNIVERSAL_MOVES[Action.LIGHT]
    assert LIGHT_ATTACK.damage == pytest.approx(jab.health_damage)
    assert LIGHT_ATTACK.reach == jab.reach == 82.0
    assert LIGHT_ATTACK.startup == jab.startup == 3
    assert LIGHT_ATTACK.active == jab.active
    assert LIGHT_ATTACK.recovery == jab.recovery
    assert LIGHT_ATTACK.cooldown == jab.startup + jab.active + jab.recovery


def test_heavy_attack_matches_heavy_punch_move_data():
    from backend.ai.actions import Action
    from backend.engine.moves import UNIVERSAL_MOVES
    hp = UNIVERSAL_MOVES[Action.HEAVY]
    assert HEAVY_ATTACK.damage == pytest.approx(hp.health_damage)
    assert HEAVY_ATTACK.reach == hp.reach
    assert HEAVY_ATTACK.startup == hp.startup == 10
    assert HEAVY_ATTACK.active == hp.active
    assert HEAVY_ATTACK.recovery == hp.recovery
    assert HEAVY_ATTACK.cooldown == hp.startup + hp.active + hp.recovery


# --- Attack data is frozen ------------------------------------------

def test_attack_data_cannot_be_changed():
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        LIGHT_ATTACK.damage = 999
