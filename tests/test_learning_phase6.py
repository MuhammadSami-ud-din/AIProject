"""Tests for Phase 6: In-Game Model Deployment, DDA, and Decision Explanations."""

import pytest

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.difficulty import DifficultyWrapper
from backend.ai.observation import Observation, example_observation
from backend.ai.opponent_model import OpponentModel
from backend.learning.policy_agent import PolicyAgent
from backend.learning.trainer_proc import BackgroundTrainingManager


def test_policy_agent_fallback_when_no_model():
    """PolicyAgent falls back gracefully to rule-based agent if no model exists."""
    agent = PolicyAgent(personality="Crimson", model_path="nonexistent_model.pt", player=1)
    assert agent.model is None

    obs = example_observation(my_health=0.8, enemy_health=0.5)
    action, scores = agent.choose_action(obs)

    assert action in ALL_ACTIONS
    assert isinstance(scores, dict)
    assert len(scores) > 0


def test_policy_agent_timing_stage():
    """Decisions are timed and recorded via stage('policy')."""
    agent = PolicyAgent(personality="Steel", player=1)
    obs = example_observation()
    action, _ = agent.choose_action(obs)

    assert agent.last_inference_time_ms >= 0.0
    assert "policy" in agent.stages


def test_dynamic_difficulty_adjustment_adapts_mistakes():
    """DDA adjusts mistake chance based on player win rate without modifying damage."""
    from backend.ai.crimson import CrimsonAgent
    inner = CrimsonAgent(player=2)
    wrapper = DifficultyWrapper(inner, difficulty="HIGH")
    wrapper.adaptive_difficulty = True
    initial_mistake = wrapper.mistake_chance

    # Player losing consecutively -> AI becomes more forgiving (higher mistake chance)
    for _ in range(5):
        wrapper.update_dda(human_won=False)
    assert wrapper.mistake_chance > initial_mistake

    # Player winning consecutively -> AI sharpens (lower mistake chance)
    for _ in range(10):
        wrapper.update_dda(human_won=True)
    assert wrapper.mistake_chance < 0.40


def test_opponent_model_predict_distribution():
    """OpponentModel outputs a valid normalized distribution with temperature scaling."""
    model = OpponentModel()
    obs = example_observation(my_x=200, enemy_x=250)

    # Observe an attack
    model.observe(obs, my_action=Action.IDLE, enemy_action=Action.LIGHT)

    dist = model.predict_distribution(obs, temperature=0.8)
    assert isinstance(dist, dict)
    assert len(dist) == len(ALL_ACTIONS)
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-5)
    assert dist[Action.LIGHT] > 0.0


def test_background_training_manager_non_blocking_polling():
    """Training manager handles start, poll, and state querying without blocking."""
    mgr = BackgroundTrainingManager()
    assert mgr.is_running is False
    assert mgr.progress == 0.0
    # Polling while idle is a safe no-op
    mgr.poll()
    assert mgr.last_status == "Idle"
