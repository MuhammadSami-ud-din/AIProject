"""Tests for the read-only FighterState.busy property."""

import pytest

from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step
from backend.ai.actions import Action


def test_fresh_fighter_is_not_busy():
    assert FighterState().busy is False


@pytest.mark.parametrize("phase", ["startup", "active", "recovery"])
def test_attack_phases_are_busy(phase):
    assert FighterState(attack_phase=phase).busy is True


def test_attack_phase_none_is_not_busy():
    assert FighterState(attack_phase="none").busy is False


@pytest.mark.parametrize(
    "field, value",
    [
        ("hitstun", 5),
        ("blockstun", 3),
        ("recovery", 4),
        ("is_knocked_down", True),
        ("knockdown_frames", 10),
        ("is_thrown", True),
        ("shield_startup_frames", 6),
    ],
)
def test_each_busy_cause_makes_fighter_busy(field, value):
    assert FighterState(**{field: value}).busy is True


@pytest.mark.parametrize(
    "field, value",
    [
        ("hitstun", 0),
        ("blockstun", 0),
        ("recovery", 0),
        ("is_knocked_down", False),
        ("knockdown_frames", 0),
        ("is_thrown", False),
        ("shield_startup_frames", 0),
    ],
)
def test_zero_values_are_not_busy(field, value):
    assert FighterState(**{field: value}).busy is False


def test_busy_is_read_only():
    f = FighterState()
    assert isinstance(FighterState.busy, property)
    with pytest.raises(AttributeError):
        f.busy = True  # type: ignore[misc]


def test_busy_follows_state_changes_and_copy():
    f = FighterState()
    assert not f.busy
    f.hitstun = 7
    assert f.busy
    assert f.copy().busy
    f.hitstun = 0
    assert not f.busy


def test_busy_is_true_during_a_real_attack_and_false_afterwards():
    state = make_initial_state("Crimson", "Steel")
    assert state.fighter1.busy is False

    state = step(state, Action.LIGHT, Action.IDLE)
    assert state.fighter1.busy is True  # attack has started

    for _ in range(120):  # plenty of time for the jab to finish
        state = step(state, Action.IDLE, Action.IDLE)
        if state.round_over:
            break
    assert state.fighter1.busy is False


def test_fightstate_fighters_have_busy():
    state = FightState()
    assert state.fighter1.busy is False
    assert state.fighter2.busy is False
