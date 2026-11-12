"""Tests for the four fighter AIs: each must beat RandomAgent most of the time."""

import pytest

from backend.ai.crimson import CrimsonAgent
from backend.ai.golden import GoldenAgent
from backend.ai.random_agent import RandomAgent
from backend.ai.shadow import ShadowAgent
from backend.ai.steel import SteelAgent
from backend.data.match_runner import run_match


# Number of matches and win-rate threshold
NUM_MATCHES = 50
WIN_RATE_THRESHOLD = 0.80  # must win at least 80%


def _win_rate(agent_class, num_matches=NUM_MATCHES):
    """Run the fighter against RandomAgent and return the win rate."""
    wins = 0
    for i in range(num_matches):
        fighter = agent_class(player=1, seed=i * 100)
        random_agent = RandomAgent(player=2, seed=i * 100 + 50)
        result = run_match(fighter, random_agent, seed=i)
        if result["match_result"] == "p1":
            wins += 1
    return wins / num_matches


# --- Individual fighter tests ---

def test_crimson_beats_random():
    """Crimson should beat RandomAgent at least 80% of the time."""
    rate = _win_rate(CrimsonAgent)
    assert rate >= WIN_RATE_THRESHOLD, f"Crimson win rate: {rate:.0%}"


def test_steel_beats_random():
    """Steel should beat RandomAgent at least 80% of the time."""
    rate = _win_rate(SteelAgent)
    assert rate >= WIN_RATE_THRESHOLD, f"Steel win rate: {rate:.0%}"


def test_shadow_beats_random():
    """Shadow should beat RandomAgent at least 80% of the time."""
    rate = _win_rate(ShadowAgent)
    assert rate >= WIN_RATE_THRESHOLD, f"Shadow win rate: {rate:.0%}"


def test_golden_beats_random():
    """Golden should beat RandomAgent at least 80% of the time."""
    rate = _win_rate(GoldenAgent)
    assert rate >= WIN_RATE_THRESHOLD, f"Golden win rate: {rate:.0%}"


# --- Basic sanity tests ---

def test_crimson_returns_valid_action():
    from backend.ai.actions import ALL_ACTIONS
    from backend.ai.observation import example_observation
    agent = CrimsonAgent(seed=1)
    action, scores = agent.choose_action(example_observation())
    assert action in ALL_ACTIONS
    assert len(scores) > 0


def test_steel_returns_valid_action():
    from backend.ai.actions import ALL_ACTIONS
    from backend.ai.observation import example_observation
    agent = SteelAgent(seed=1)
    action, scores = agent.choose_action(example_observation())
    assert action in ALL_ACTIONS


def test_shadow_returns_valid_action():
    from backend.ai.actions import ALL_ACTIONS
    from backend.ai.observation import example_observation
    agent = ShadowAgent(seed=1)
    action, scores = agent.choose_action(example_observation())
    assert action in ALL_ACTIONS


def test_golden_returns_valid_action():
    from backend.ai.actions import ALL_ACTIONS
    from backend.ai.observation import example_observation
    agent = GoldenAgent(seed=1)
    action, scores = agent.choose_action(example_observation())
    assert action in ALL_ACTIONS


def test_golden_adapts_over_time():
    """Golden's current_likes should change after observing many attacks."""
    from backend.ai.actions import Action
    from backend.ai.observation import example_observation
    agent = GoldenAgent(seed=1)
    obs = example_observation()
    initial_punish = agent.current_likes["block_punish"]

    # Feed it observations where the enemy attacks a lot
    for _ in range(50):
        agent.observe(obs, Action.IDLE, Action.LIGHT)

    # block_punish should have increased
    assert agent.current_likes["block_punish"] > initial_punish
