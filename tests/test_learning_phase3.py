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
    )

    assert isinstance(model, ActorCritic)
    assert os.path.exists(model_path)
    assert os.path.exists(model_path.replace(".pt", ".json"))

    assert "test_accuracy" in metrics
    assert 0.0 <= metrics["test_accuracy"] <= 1.0
    assert "confusion_matrix" in metrics
    conf = np.array(metrics["confusion_matrix"])
    assert conf.shape == (ACTION_DIM, ACTION_DIM)

    # Check that saved weights reload cleanly
    reloaded = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM)
    reloaded.load_state_dict(torch.load(model_path))
    dummy_input = torch.zeros((1, OBS_DIM), dtype=torch.float32)
    with torch.no_grad():
        logits, val = reloaded(dummy_input)
    assert logits.shape == (1, ACTION_DIM)
