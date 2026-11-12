"""Tests for round-robin, Elo ratings, and statistics."""

import pytest

from backend.data.statistics import (
    compute_elo,
    run_round_robin,
    win_rate_with_ci,
    ELO_START,
)


def test_round_robin_runs():
    """A small round-robin should complete without errors."""
    results = run_round_robin(
        fighters=["Crimson", "Steel"],
        difficulties=["LOW"],
        matches_per_pair=3,
    )
    assert len(results) == 1  # 2 fighters = 1 pair
    r = results[0]
    assert r["wins1"] + r["wins2"] + r["draws"] == 3


def test_round_robin_all_pairs():
    """4 fighters should produce 6 pairs."""
    results = run_round_robin(
        fighters=["Crimson", "Steel", "Shadow", "Golden"],
        difficulties=["LOW"],
        matches_per_pair=2,
    )
    assert len(results) == 6  # C(4,2) = 6


def test_elo_ratings():
    """Elo ratings should reflect who wins more."""
    # Fake results: fighter1 always wins
    results = [{
        "fighter1": "A",
        "fighter2": "B",
        "difficulty": "LOW",
        "wins1": 10,
        "wins2": 0,
        "draws": 0,
        "total": 10,
    }]
    elo = compute_elo(results)
    assert elo["A"] > ELO_START
    assert elo["B"] < ELO_START


def test_elo_draw():
    """Equal results should keep ratings near the start."""
    results = [{
        "fighter1": "X",
        "fighter2": "Y",
        "difficulty": "LOW",
        "wins1": 5,
        "wins2": 5,
        "draws": 0,
        "total": 10,
    }]
    elo = compute_elo(results)
    # Both should be close to start
    assert abs(elo["X"] - ELO_START) < 50
    assert abs(elo["Y"] - ELO_START) < 50


def test_win_rate_with_ci():
    rate, lower, upper = win_rate_with_ci(80, 100)
    assert rate == pytest.approx(0.8)
    assert lower < rate
    assert upper > rate
    assert lower >= 0
    assert upper <= 1


def test_win_rate_zero_total():
    rate, lower, upper = win_rate_with_ci(0, 0)
    assert rate == 0.0
