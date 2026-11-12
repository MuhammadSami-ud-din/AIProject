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


# --- Light attack data ----------------------------------------------

def test_light_damage():
    assert LIGHT_ATTACK.damage == 0.05


def test_light_reach():
    assert LIGHT_ATTACK.reach == 70


def test_light_startup():
    assert LIGHT_ATTACK.startup == 4


def test_light_active():
    assert LIGHT_ATTACK.active == 3


def test_light_recovery():
    assert LIGHT_ATTACK.recovery == 8


def test_light_cooldown():
    assert LIGHT_ATTACK.cooldown == 12


# --- Heavy attack data ----------------------------------------------

def test_heavy_damage():
    assert HEAVY_ATTACK.damage == 0.12


def test_heavy_reach():
    assert HEAVY_ATTACK.reach == 90


def test_heavy_startup():
    assert HEAVY_ATTACK.startup == 10


def test_heavy_active():
    assert HEAVY_ATTACK.active == 4


def test_heavy_recovery():
    assert HEAVY_ATTACK.recovery == 18


def test_heavy_cooldown():
    assert HEAVY_ATTACK.cooldown == 30


# --- Attack data is frozen ------------------------------------------

def test_attack_data_cannot_be_changed():
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        LIGHT_ATTACK.damage = 999
