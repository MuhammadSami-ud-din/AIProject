"""Tests for Phase 3: Behaviour-Cloning Warm Start & Data Augmentation."""

import json
import os
import numpy as np
import pytest
import torch

from backend.ai.actions import ALL_ACTIONS
from backend.learning.bc import (
    augment_features,
    collect_dataset,
    split_by_match,
    train_bc_model,
)
from backend.learning.config import ACTION_DIM, OBS_DIM, RESULTS_DIR
from backend.learning.network import ActorCritic


def test_split_by_match_is_strictly_disjoint():
    """Verify that train and test splits share no match IDs."""
    fake_data = [
        (1, np.zeros(OBS_DIM, dtype=np.float32), 0),
        (1, np.zeros(OBS_DIM, dtype=np.float32), 1),
        (2, np.zeros(OBS_DIM, dtype=np.float32), 2),
        (3, np.zeros(OBS_DIM, dtype=np.float32), 3),
        (4, np.zeros(OBS_DIM, dtype=np.float32), 4),
        (5, np.zeros(OBS_DIM, dtype=np.float32), 0),
    ]

    train_data, test_data = split_by_match(fake_data, test_split=0.4, seed=42)
    train_mids = set(row[0] for row in train_data)
    test_mids = set(row[0] for row in test_data)

    assert len(train_data) > 0
    assert len(test_data) > 0
    assert train_mids.isdisjoint(test_mids)


def test_data_augmentation_expands_training_set():
    """Augmentation adds jittered copies without altering original data shape."""
    X = np.ones((10, OBS_DIM), dtype=np.float32)
    y = np.arange(10, dtype=np.int64)

    aug_X, aug_y = augment_features(X, y, seed=123)
    assert aug_X.shape[0] == 20  # Original + jittered copy
    assert aug_y.shape[0] == 20
    assert aug_X.shape[1] == OBS_DIM


def test_bc_training_produces_weights_and_confusion_matrix(tmp_path):
    """Train BC model for 3 epochs, verifying model checkpoint, accuracy, and confusion matrix."""
    model_path = str(tmp_path / "test_bc_model.pt")
    model, metrics = train_bc_model(
        personality="Crimson",
        epochs=3,
        batch_size=32,
        seed=42,
        save_path=model_path,
        num_matches=4,
    )

    assert isinstance(model, ActorCritic)
    assert os.path.exists(model_path)
    assert os.path.exists(model_path.replace(".pt", ".json"))

    assert "test_accuracy" in metrics
    assert 0.0 <= metrics["test_accuracy"] <= 1.0
    assert "confusion_matrix" in metrics
    conf = np.array(metrics["confusion_matrix"])
    assert conf.shape == (ACTION_DIM, ACTION_DIM)

    # Check that saved weights reload cleanly (strict) through the safe loader
    from backend.learning.checkpoints import load_compatible_state_dict
    reloaded = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM)
    reloaded.load_state_dict(load_compatible_state_dict(model_path), strict=True)
    dummy_input = torch.zeros((1, OBS_DIM), dtype=torch.float32)
    with torch.no_grad():
        logits, val = reloaded(dummy_input)
    assert logits.shape == (1, ACTION_DIM)


def test_bc_demonstrations_use_macro_step_granularity():
    """Each demo row is one ArenaEnv.step decision with its mask and discounted return."""
    from backend.learning.bc import generate_demonstrations
    rows = generate_demonstrations("Steel", num_matches=1, seed=3)
    assert len(rows) > 10
    mid, vec, action, ret, mask, won = rows[0]
    assert vec.shape == (OBS_DIM,)
    assert mask.shape == (ACTION_DIM,) and mask[action]
    # macro-steps: a round of up to 3600 frames gives far fewer decisions than frames
    assert len(rows) < 3600 / 4


def test_bc_initialises_critic_and_does_not_touch_repo(tmp_path):
    """The critic is fitted (explained variance reported) and nothing is written to docs/results."""
    before = set(os.listdir(RESULTS_DIR)) if os.path.isdir(RESULTS_DIR) else set()
    model_path = str(tmp_path / "bc.pt")
    _, metrics = train_bc_model("Golden", epochs=2, num_matches=4, save_path=model_path,
                                results_dir=str(tmp_path / "res"))
    assert "critic_explained_variance" in metrics
    assert os.path.exists(tmp_path / "res" / "bc_golden_metrics.json")
    after = set(os.listdir(RESULTS_DIR)) if os.path.isdir(RESULTS_DIR) else set()
    assert before == after


def test_policy_vector_one_hot_actions_and_attack_phase():
    from backend.ai.actions import Action
    from backend.ai.observation import example_observation
    from backend.learning.features import POLICY_FEATURE_NAMES, policy_vector
    obs = example_observation(enemy_last_action=Action.HEAVY, my_last_action=Action.BLOCK)
    vec = policy_vector(obs)
    names = list(POLICY_FEATURE_NAMES)
    assert vec[names.index("enemy_last_action==5")] == 1.0
    assert vec[names.index("my_last_action==6")] == 1.0
    assert sum(vec[names.index(f"enemy_last_action=={i}")] for i in range(28)) == 1.0
    assert sum(vec[names.index(f"enemy_attack_phase=={p}")] for p in ("none", "startup", "active", "recovery")) == 1.0
