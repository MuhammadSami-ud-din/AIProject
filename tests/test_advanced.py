"""Tests for ablation study, Q-learning, and MCTS."""

import pytest

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.observation import example_observation
from backend.ai.personalities import CRIMSON
from backend.ai.random_agent import RandomAgent


# ------------------------------------------------------------------
# Ablation study
# ------------------------------------------------------------------
def test_binomial_test():
    """Binomial test should return rate, z-score, and p-value."""
    from backend.data.ablation import binomial_test

    rate, z, p = binomial_test(80, 100, expected_rate=0.5)
    assert 0.0 <= rate <= 1.0
    assert z > 0          # 80% should be above 50%
    assert p < 0.05       # should be significant

    # Edge case: no matches
    rate, z, p = binomial_test(0, 0)
    assert rate == 0.0
    assert p == 1.0


def test_ablation_study():
    """Ablation study should return win rates for each config."""
    from backend.data.ablation import ablation_study

    results = ablation_study(
        fighter_name="Crimson",
        difficulty="LOW",
        matches_per_config=3,
        seed=42
    )
    assert "baseline" in results
    assert "no_search" in results
    assert "no_opponent_model" in results
    assert "no_learned_policy" in results
    for rate in results.values():
        assert 0.0 <= rate <= 1.0


# ------------------------------------------------------------------
# Q-learning
# ------------------------------------------------------------------
def test_state_key():
    """State key should return a hashable tuple."""
    from backend.ai.qlearning import state_key

    obs = example_observation()
    key = state_key(obs)

    assert isinstance(key, tuple)
    assert len(key) == 7  # zone, my_hp, enemy_hp, cornered, enemy_cornered, can_attack, enemy_stuck


def test_q_table():
    """Q-table should store and retrieve values."""
    from backend.ai.qlearning import QTable

    qt = QTable()
    key = ("test",)

    # Default is 0.0
    assert qt.get(key, Action.LIGHT) == 0.0

    # Set and get
    qt.set(key, Action.LIGHT, 5.0)
    assert qt.get(key, Action.LIGHT) == 5.0

    # Best action
    qt.set(key, Action.HEAVY, 10.0)
    assert qt.best_action(key) == Action.HEAVY

    # Size
    assert qt.size == 1


def test_q_table_update():
    """Q-learning update should change the Q-value toward the target."""
    from backend.ai.qlearning import QTable

    qt = QTable()
    key1 = ("state1",)
    key2 = ("state2",)

    # Start at 0
    assert qt.get(key1, Action.LIGHT) == 0.0

    # Update with a positive reward
    qt.update(key1, Action.LIGHT, reward=1.0, next_key=key2)
    assert qt.get(key1, Action.LIGHT) > 0.0  # should have increased


def test_qlearning_agent():
    """Q-learning agent should produce valid actions."""
    from backend.ai.qlearning import QLearningAgent

    agent = QLearningAgent(player=1, seed=42, training=True)
    obs = example_observation()

    action, scores = agent.choose_action(obs)
    assert isinstance(action, Action)
    assert len(scores) == len(ALL_ACTIONS)


def test_train_q_agent():
    """Training should produce a non-empty Q-table."""
    from backend.ai.qlearning import train_q_agent

    q_table, history = train_q_agent(episodes=3, seed=42)
    assert q_table.size > 0
    assert len(history) == 3


# ------------------------------------------------------------------
# MCTS
# ------------------------------------------------------------------
def test_mcts_returns_valid_action():
    """MCTS should return a valid action and score."""
    from backend.ai.mcts import mcts_best_action
    from backend.engine.step import make_initial_state
    import random

    state = make_initial_state("Crimson", "Steel")
    rng = random.Random(42)

    action, score, rollouts = mcts_best_action(
        state, player=1, personality=CRIMSON, rng=rng, budget_s=0.01
    )

    assert isinstance(action, Action)
    assert isinstance(score, float)
    assert rollouts > 0


def test_mcts_multiple_calls():
    """MCTS should be usable across multiple frames."""
    from backend.ai.mcts import mcts_best_action
    from backend.engine.step import make_initial_state, step
    import random

    state = make_initial_state("Crimson", "Steel")
    rng = random.Random(42)

    actions = []
    for _ in range(3):
        action, _, _ = mcts_best_action(
            state, player=1, personality=CRIMSON, rng=rng, budget_s=0.005
        )
        actions.append(action)
        state = step(state, action, Action.IDLE)

    assert len(actions) == 3
    assert all(isinstance(a, Action) for a in actions)
