"""Tests for headless match runner and SQLite logging."""

import os
import sqlite3
import tempfile

import pytest

from backend.ai.observation import FEATURE_NAMES
from backend.ai.random_agent import RandomAgent
from backend.data.database import (
    count_frames,
    count_matches,
    get_connection,
    get_match_frames,
    get_match_ids,
    save_match,
)
from backend.data.match_runner import run_match


# ---------------------------------------------------------------
# Headless match runner
# ---------------------------------------------------------------

def test_run_match_completes():
    """A match between two random agents should finish."""
    a1 = RandomAgent(player=1, seed=1)
    a2 = RandomAgent(player=2, seed=2)
    result = run_match(a1, a2, seed=1)

    assert result["match_result"] in ("p1", "p2", "draw")
    assert len(result["frames"]) > 0
    assert result["seed"] == 1
    assert len(result["rounds"]) >= 1


def test_run_match_has_correct_frame_keys():
    """Each frame record should have all the expected keys."""
    a1 = RandomAgent(player=1, seed=10)
    a2 = RandomAgent(player=2, seed=20)
    result = run_match(a1, a2, seed=10)

    frame = result["frames"][0]
    # Check required keys
    assert "frame" in frame
    assert "round" in frame
    assert "agent1_name" in frame
    assert "agent2_name" in frame
    assert "action1" in frame
    assert "action2" in frame
    assert "seed" in frame

    # Check all feature columns are present
    for name in FEATURE_NAMES:
        assert name in frame, f"missing feature: {name}"


def test_run_match_deterministic():
    """Same seed and same agents should give the same result."""
    def play(seed):
        a1 = RandomAgent(player=1, seed=seed)
        a2 = RandomAgent(player=2, seed=seed + 100)
        return run_match(a1, a2, seed=seed)

    r1 = play(42)
    r2 = play(42)

    assert r1["match_result"] == r2["match_result"]
    assert len(r1["frames"]) == len(r2["frames"])
    assert r1["rounds"] == r2["rounds"]


def test_run_match_round_count():
    """A match should have 1 to 3 rounds."""
    a1 = RandomAgent(player=1, seed=5)
    a2 = RandomAgent(player=2, seed=6)
    result = run_match(a1, a2, seed=5)
    assert 1 <= len(result["rounds"]) <= 3


# ---------------------------------------------------------------
# SQLite database
# ---------------------------------------------------------------

@pytest.fixture
def tmp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)
    yield conn, path
    conn.close()
    os.unlink(path)


def test_database_creates_table(tmp_db):
    conn, path = tmp_db
    # The frames table should exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='frames'"
    )
    assert cursor.fetchone() is not None


def test_save_and_count_match(tmp_db):
    conn, path = tmp_db
    a1 = RandomAgent(player=1, seed=1)
    a2 = RandomAgent(player=2, seed=2)
    result = run_match(a1, a2, seed=1)

    match_id = save_match(conn, result)
    assert match_id is not None
    assert count_matches(conn) == 1
    assert count_frames(conn) == len(result["frames"])


def test_save_multiple_matches(tmp_db):
    conn, path = tmp_db
    for i in range(3):
        a1 = RandomAgent(player=1, seed=i)
        a2 = RandomAgent(player=2, seed=i + 100)
        result = run_match(a1, a2, seed=i)
        save_match(conn, result)

    assert count_matches(conn) == 3


def test_get_match_ids(tmp_db):
    conn, path = tmp_db
    ids = []
    for i in range(3):
        a1 = RandomAgent(player=1, seed=i)
        a2 = RandomAgent(player=2, seed=i + 100)
        result = run_match(a1, a2, seed=i)
        mid = save_match(conn, result)
        ids.append(mid)

    retrieved = get_match_ids(conn)
    assert len(retrieved) == 3
    # All our match ids should be in the list
    for mid in ids:
        assert mid in retrieved


def test_get_match_frames(tmp_db):
    conn, path = tmp_db
    a1 = RandomAgent(player=1, seed=7)
    a2 = RandomAgent(player=2, seed=8)
    result = run_match(a1, a2, seed=7)
    match_id = save_match(conn, result)

    frames = get_match_frames(conn, match_id)
    assert len(frames) == len(result["frames"])
    # Each frame should have the match_id
    assert all(f["match_id"] == match_id for f in frames)


def test_frame_has_feature_columns(tmp_db):
    """Every feature from FEATURE_NAMES should be a column in the database."""
    conn, path = tmp_db
    a1 = RandomAgent(player=1, seed=1)
    a2 = RandomAgent(player=2, seed=2)
    result = run_match(a1, a2, seed=1)
    match_id = save_match(conn, result)

    frames = get_match_frames(conn, match_id)
    first_frame = frames[0]
    for name in FEATURE_NAMES:
        assert name in first_frame, f"missing column: {name}"


def test_match_result_stored(tmp_db):
    """The match_result should be stored in every frame row."""
    conn, path = tmp_db
    a1 = RandomAgent(player=1, seed=1)
    a2 = RandomAgent(player=2, seed=2)
    result = run_match(a1, a2, seed=1)
    match_id = save_match(conn, result)

    frames = get_match_frames(conn, match_id)
    for f in frames:
        assert f["match_result"] == result["match_result"]


def test_seed_stored(tmp_db):
    """The seed should be stored so matches can be replayed."""
    conn, path = tmp_db
    a1 = RandomAgent(player=1, seed=42)
    a2 = RandomAgent(player=2, seed=43)
    result = run_match(a1, a2, seed=42)
    match_id = save_match(conn, result)

    frames = get_match_frames(conn, match_id)
    assert frames[0]["seed"] == 42
