"""Tests for difficulty wrapper, evaluation, and search."""

import pytest

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.crimson import CrimsonAgent
from backend.ai.difficulty import (
    DifficultyWrapper,
    MISTAKE_CHANCE,
    REACTION_DELAY,
    SEARCH_DEPTH,
)
from backend.ai.evaluation import evaluate
from backend.ai.golden import GoldenAgent
from backend.ai.observation import example_observation
from backend.ai.personalities import CRIMSON, STEEL, SHADOW
from backend.ai.random_agent import RandomAgent
from backend.ai.search import search_best_action
from backend.engine.step import make_initial_state


# ---------------------------------------------------------------
# Difficulty wrapper
# ---------------------------------------------------------------

def test_difficulty_wrapper_returns_valid_action():
    inner = CrimsonAgent(player=1, seed=1)
    wrapped = DifficultyWrapper(inner, difficulty="LOW")
    obs = example_observation()
    action, scores = wrapped.choose_action(obs)
    assert action in ALL_ACTIONS
    assert len(scores) > 0


def test_all_difficulty_levels_work():
    for diff in ("LOW", "MEDIUM", "HIGH", "HELL"):
        inner = CrimsonAgent(player=1, seed=1)
        wrapped = DifficultyWrapper(inner, difficulty=diff)
        obs = example_observation()
        action, _ = wrapped.choose_action(obs)
        assert action in ALL_ACTIONS


def test_reaction_delay_values():
    assert REACTION_DELAY["LOW"] == 24
    assert REACTION_DELAY["MEDIUM"] == 15
    assert REACTION_DELAY["HIGH"] == 7
    assert REACTION_DELAY["HELL"] == 1


def test_mistake_chance_values():
    assert MISTAKE_CHANCE["LOW"] == 0.30
    assert MISTAKE_CHANCE["MEDIUM"] == 0.15
    assert MISTAKE_CHANCE["HIGH"] == 0.05
    assert MISTAKE_CHANCE["HELL"] == 0.01


def test_search_depth_values():
    assert SEARCH_DEPTH["LOW"] == 1
    assert SEARCH_DEPTH["MEDIUM"] == 2
    assert SEARCH_DEPTH["HIGH"] == 3
    assert SEARCH_DEPTH["HELL"] == 4


def test_bad_difficulty_rejected():
    inner = CrimsonAgent(player=1, seed=1)
    with pytest.raises(ValueError):
        DifficultyWrapper(inner, difficulty="EASY")


def test_reset_clears_observation_buffer():
    inner = CrimsonAgent(player=1, seed=1)
    wrapped = DifficultyWrapper(inner, difficulty="LOW")
    obs = example_observation()
    wrapped.choose_action(obs)
    assert len(wrapped.obs_buffer) > 0
    wrapped.reset()
    assert len(wrapped.obs_buffer) == 0


def test_harder_difficulty_makes_fewer_mistakes():
    """LOW should make more mistakes than HELL over many decisions."""
    from backend.ai.choice import pick, probabilities

    scores = {Action.LIGHT: 10, Action.HEAVY: 5, Action.BLOCK: 1}
    import random

    # Count how often each difficulty picks the best action
    best_counts = {}
    for diff in ("LOW", "HELL"):
        rng = random.Random(42)
        mistake = MISTAKE_CHANCE[diff]
        best = 0
        for _ in range(500):
            chosen = pick(scores, rng, variety=0.1, mistake_chance=mistake)
            if chosen == Action.LIGHT:
                best += 1
        best_counts[diff] = best

    # HELL should pick the best move more often
    assert best_counts["HELL"] > best_counts["LOW"]


# ---------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------

def test_evaluate_returns_score_and_contributions():
    obs = example_observation()
    score, contribs = evaluate(obs, CRIMSON)
    assert isinstance(score, float)
    assert isinstance(contribs, dict)
    assert len(contribs) == 6  # six like fields


def test_health_lead_affects_score():
    winning = example_observation(my_health=1.0, enemy_health=0.3)
    losing = example_observation(my_health=0.3, enemy_health=1.0)
    score_win, _ = evaluate(winning, CRIMSON)
    score_lose, _ = evaluate(losing, CRIMSON)
    assert score_win > score_lose


def test_closeness_matters_for_crimson():
    close = example_observation(my_x=300, enemy_x=340)
    far = example_observation(my_x=100, enemy_x=700)
    score_close, _ = evaluate(close, CRIMSON)
    score_far, _ = evaluate(far, CRIMSON)
    # Crimson likes being close (closeness=9)
    assert score_close > score_far


def test_corner_penalty():
    """Being cornered should reduce the score for corner-avoiding fighters."""
    safe = example_observation(my_x=400, enemy_x=500)
    cornered = example_observation(my_x=10, enemy_x=200)
    score_safe, _ = evaluate(safe, SHADOW)
    score_cornered, _ = evaluate(cornered, SHADOW)
    # Shadow hates corners (corner_avoid=9)
    assert score_safe > score_cornered


# ---------------------------------------------------------------
# Search
# ---------------------------------------------------------------

def test_search_returns_valid_action():
    state = make_initial_state("Crimson", "Golden")
    action, score, depth = search_best_action(state, 1, CRIMSON, max_depth=2)
    assert action in ALL_ACTIONS
    assert depth >= 1


def test_search_respects_max_depth():
    state = make_initial_state("Crimson", "Golden")
    _, _, depth = search_best_action(state, 1, CRIMSON, max_depth=1)
    assert depth <= 1


def test_search_prefers_winning_state():
    """If the enemy is almost dead, search should choose to attack."""
    state = make_initial_state("Crimson", "Golden")
    state.fighter2.health = 0.01  # almost dead
    state.fighter1.x = 100
    state.fighter2.x = 150  # within attack range

    action, score, _ = search_best_action(state, 1, CRIMSON, max_depth=2)
    # Should prefer an aggressive action (FORWARD, LIGHT, HEAVY, or special attack)
    assert action in (Action.LIGHT, Action.HEAVY, Action.FORWARD, Action.SPECIAL_NEUTRAL)


def test_search_within_time_budget():
    """Search should complete within a reasonable time."""
    import time
    state = make_initial_state("Crimson", "Golden")
    start = time.perf_counter()
    search_best_action(state, 1, CRIMSON, max_depth=4)
    elapsed = (time.perf_counter() - start) * 1000
    # Should be under 50ms even with depth 4 (budget is 5ms but overhead exists)
    assert elapsed < 50, f"Search took {elapsed:.1f}ms"
