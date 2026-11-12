"""Tests for the learning module (behaviour cloning)."""

import os
import tempfile

import pytest

from backend.ai.observation import FEATURE_NAMES
from backend.ai.random_agent import RandomAgent
from backend.data.database import get_connection, save_match
from backend.data.learning import (
    extract_training_data,
    features_to_array,
    load_model,
    model_exists,
    predict_action,
    save_model,
    split_by_match,
    train_model,
    TrainingThread,
    MODELS_DIR,
)
from backend.data.match_runner import run_match


@pytest.fixture
def populated_db():
    """Create a temp DB with several matches."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)

    # Run 20 matches to get enough data
    for i in range(20):
        a1 = RandomAgent(player=1, seed=i)
        a2 = RandomAgent(player=2, seed=i + 100)
        result = run_match(a1, a2, seed=i)
        save_match(conn, result)

    yield conn, path
    conn.close()
    os.unlink(path)


def test_extract_training_data(populated_db):
    conn, _ = populated_db
    X, y, ids = extract_training_data(conn)
    assert len(X) > 0
    assert len(y) == len(X)
    assert len(ids) > 0
    # Each feature dict should have all feature names
    assert set(X[0].keys()) == set(FEATURE_NAMES)


def test_split_by_match():
    ids = list(range(100))
    train, val, test = split_by_match(ids)
    # No overlap
    assert len(set(train) & set(val)) == 0
    assert len(set(train) & set(test)) == 0
    assert len(set(val) & set(test)) == 0
    # All ids accounted for
    assert len(train) + len(val) + len(test) == 100


def test_features_to_array():
    dicts = [{name: 0.5 for name in FEATURE_NAMES}]
    arr = features_to_array(dicts)
    assert len(arr) == 1
    assert len(arr[0]) == len(FEATURE_NAMES)


def test_train_model(populated_db):
    conn, _ = populated_db
    X, y, _ = extract_training_data(conn)
    model = train_model(X, y)
    assert model is not None
    # Model should be able to predict
    from backend.ai.actions import Action
    pred = predict_action(model, X[0])
    assert isinstance(pred, Action)


def test_save_and_load_model(populated_db, tmp_path):
    conn, _ = populated_db
    X, y, _ = extract_training_data(conn)
    model = train_model(X, y)

    # Override MODELS_DIR for this test
    import backend.data.learning as learning_mod
    old_dir = learning_mod.MODELS_DIR
    learning_mod.MODELS_DIR = str(tmp_path)
    try:
        save_model(model, "test_v1")
        loaded = load_model()
        assert loaded is not None
        # Should predict the same thing
        pred1 = predict_action(model, X[0])
        pred2 = predict_action(loaded, X[0])
        assert pred1 == pred2
    finally:
        learning_mod.MODELS_DIR = old_dir


def test_training_thread(populated_db):
    conn, path = populated_db

    # Override models dir
    import backend.data.learning as learning_mod
    import tempfile
    tmp = tempfile.mkdtemp()
    old_dir = learning_mod.MODELS_DIR
    learning_mod.MODELS_DIR = tmp
    try:
        t = TrainingThread(path)
        t.start()
        t.join(timeout=30)
        assert t.done
        assert t.success, f"Training failed: {t.error}"
        assert t.model is not None
    finally:
        learning_mod.MODELS_DIR = old_dir


def test_training_thread_not_enough_data():
    """Should fail gracefully with too few frames."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)
    conn.close()

    t = TrainingThread(path)
    t.start()
    t.join(timeout=5)
    assert t.done
    assert not t.success
    assert "Not enough" in t.error

    os.unlink(path)
