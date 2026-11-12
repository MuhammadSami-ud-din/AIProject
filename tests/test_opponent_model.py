"""Tests for the opponent model."""

import pytest

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.observation import example_observation
from backend.ai.opponent_model import OpponentModel


def test_predict_returns_all_actions():
    model = OpponentModel()
    obs = example_observation()
    probs = model.predict(obs)
    assert set(probs.keys()) == set(ALL_ACTIONS)
    assert abs(sum(probs.values()) - 1.0) < 0.001


def test_predictions_improve_with_data():
    """After seeing the enemy use LIGHT many times, LIGHT should be predicted."""
    model = OpponentModel()
    obs = example_observation()

    # Feed the model: enemy always does LIGHT
    for _ in range(50):
        model.update(obs, Action.LIGHT)

    probs = model.predict(obs)
    # LIGHT should be the most likely
    assert probs[Action.LIGHT] > probs[Action.HEAVY]
    assert probs[Action.LIGHT] > probs[Action.BLOCK]


def test_laplace_smoothing():
    """Even unseen actions should have non-zero probability."""
    model = OpponentModel()
    obs = example_observation()

    # Only see LIGHT
    for _ in range(10):
        model.update(obs, Action.LIGHT)

    probs = model.predict(obs)
    # Every action should be > 0 (Laplace smoothing)
    for action in ALL_ACTIONS:
        assert probs[action] > 0


def test_accuracy_tracking():
    model = OpponentModel()
    obs = example_observation()

    # Predict, then check if correct
    model.predict(obs)
    model.update(obs, model.last_prediction)  # correct

    # After 1 correct prediction, accuracy should be 1.0
    assert model.accuracy == 1.0


def test_reset_keeps_counts():
    """reset() should keep learned counts (for between rounds)."""
    model = OpponentModel()
    obs = example_observation()
    for _ in range(20):
        model.update(obs, Action.LIGHT)

    model.reset()
    # Counts should still be there
    assert sum(sum(c.values()) for c in model.counts.values()) > 0


def test_full_reset_clears_everything():
    model = OpponentModel()
    obs = example_observation()
    for _ in range(20):
        model.update(obs, Action.LIGHT)

    model.full_reset()
    assert len(model.counts) == 0
    assert model.total_predictions == 0


def test_model_not_confident_initially():
    model = OpponentModel()
    assert not model.is_confident


def test_decay_reduces_old_counts():
    """After many frames, old counts should be smaller."""
    from backend.ai.opponent_model import DECAY_INTERVAL
    model = OpponentModel()
    obs = example_observation()

    # Add a big count
    for _ in range(20):
        model.update(obs, Action.LIGHT)

    # Get the count before decay
    key = list(model.counts.keys())[0]
    count_before = model.counts[key][Action.LIGHT]

    # Force enough frames for decay to trigger
    model.frames_seen = DECAY_INTERVAL - 1
    model.update(obs, Action.IDLE)  # triggers decay at DECAY_INTERVAL

    # Count should be smaller now
    count_after = model.counts[key][Action.LIGHT]
    assert count_after < count_before
