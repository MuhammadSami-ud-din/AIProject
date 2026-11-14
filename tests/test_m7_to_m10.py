"""Tests for the AI viewer, charts, tuning, and ghost modules."""

import os
import tempfile

import pytest

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.observation import example_observation, FEATURE_NAMES
from backend.ai.personalities import CRIMSON, STEEL, GOLDEN
from backend.ai.random_agent import RandomAgent


# ------------------------------------------------------------------
# M7: AI explanation (already tested), plus augmentation
# ------------------------------------------------------------------
def test_augment_training_data():
    """Augmentation should produce more data than the input."""
    from backend.data.learning import augment_training_data

    # Create some fake training data
    obs = example_observation()
    features = obs.features()
    X = [features] * 10
    y = ["LIGHT"] * 10

    aug_X, aug_y = augment_training_data(X, y)

    # Should have original + mirrored + jittered = 3x
    assert len(aug_X) >= len(X) * 2  # at least 2x (original + some augmented)
    assert len(aug_y) == len(aug_X)


def test_features_to_observation():
    """Should be able to convert features back to an observation."""
    from backend.data.learning import _features_to_observation

    obs = example_observation()
    features = obs.features()
    result = _features_to_observation(features)

    assert result is not None
    # The health values should be close
    assert abs(result.my_health - obs.my_health) < 0.1
    assert abs(result.enemy_health - obs.enemy_health) < 0.1


# ------------------------------------------------------------------
# M8: Model versioning
# ------------------------------------------------------------------
def test_model_versioning(tmp_path):
    """Version history should track all saved models."""
    from backend.data.learning import (
        save_model, load_model, list_model_versions, rollback_model
    )
    import backend.data.learning as learning_mod

    old_dir = learning_mod.MODELS_DIR
    learning_mod.MODELS_DIR = str(tmp_path)
    try:
        # Create a fake "model" (just a dict for testing)
        model_v1 = {"version": 1, "type": "test"}
        model_v2 = {"version": 2, "type": "test"}

        save_model(model_v1, "v1")
        save_model(model_v2, "v2")

        versions = list_model_versions()
        assert len(versions) == 2
        assert versions[0]["version"] == "v1"
        assert versions[1]["version"] == "v2"

        # Latest should be v2
        latest = load_model()
        assert latest["version"] == 2

        # Rollback to v1
        success = rollback_model("v1")
        assert success
        latest = load_model()
        assert latest["version"] == 1

        # Rollback to nonexistent version should fail
        assert not rollback_model("nonexistent")
    finally:
        learning_mod.MODELS_DIR = old_dir


# ------------------------------------------------------------------
# M9: Statistics (already tested), charts
# ------------------------------------------------------------------
def test_elo_chart(tmp_path):
    """Should generate an Elo chart image."""
    # matplotlib may not render on all systems, so check import
    try:
        import matplotlib
    except ImportError:
        pytest.skip("matplotlib not available")

    from backend.data.statistics import run_round_robin
    from backend.data.charts import generate_elo_chart

    results = run_round_robin(matches_per_pair=2)
    output = str(tmp_path / "elo.png")
    path = generate_elo_chart(results, output_path=output)

    assert os.path.exists(path)
    assert os.path.getsize(path) > 100  # not an empty file


def test_winrate_heatmap(tmp_path):
    """Should generate a win rate heatmap image."""
    try:
        import matplotlib
    except ImportError:
        pytest.skip("matplotlib not available")

    from backend.data.statistics import run_round_robin
    from backend.data.charts import generate_winrate_heatmap

    results = run_round_robin(matches_per_pair=2)
    output = str(tmp_path / "heatmap.png")
    path = generate_winrate_heatmap(results, output_path=output)

    assert os.path.exists(path)
    assert os.path.getsize(path) > 100


# ------------------------------------------------------------------
# M10: Tuning
# ------------------------------------------------------------------
def test_evaluate_personality():
    """Should return a win rate between 0 and 1."""
    from backend.ai.tuning import evaluate_personality
    from backend.ai.crimson import CrimsonAgent

    rate = evaluate_personality(
        CRIMSON, CrimsonAgent, RandomAgent, trials=5, seed=0
    )
    assert 0.0 <= rate <= 1.0


def test_hill_climb():
    """Hill climbing should return a personality and history."""
    from backend.ai.tuning import hill_climb
    from backend.ai.crimson import CrimsonAgent

    best_p, best_rate, history = hill_climb(
        CRIMSON, CrimsonAgent, RandomAgent,
        steps=2, trials=3, seed=42
    )
    assert best_p is not None
    assert 0.0 <= best_rate <= 1.0
    assert len(history) == 3  # step 0 + 2 steps


# ------------------------------------------------------------------
# M10: Ghost
# ------------------------------------------------------------------
def test_ghost_agent_no_model():
    """Ghost should work even without a trained model."""
    from backend.ai.ghost import GhostAgent

    ghost = GhostAgent(player=1, seed=42)
    obs = example_observation()
    action, scores = ghost.choose_action(obs)

    assert isinstance(action, Action)
    assert len(scores) > 0


def test_ghost_agent_with_frequency():
    """Ghost should learn from logged action frequencies."""
    from backend.ai.ghost import GhostAgent

    ghost = GhostAgent(player=1, seed=42)
    ghost.model = None  # force frequency mode

    # Feed it some fake logs: always LIGHT at distance 0.2
    obs = example_observation()
    features = obs.features()
    log = [(features, "LIGHT")] * 20

    ghost.learn_from_logs(log)

    action, scores = ghost.choose_action(obs)
    assert isinstance(action, Action)
    # LIGHT should have the highest score
    assert scores[Action.LIGHT] >= scores[Action.HEAVY]
