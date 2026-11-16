"""Tests for Phase 5: Self-Play League, Curriculum, and Promotion Gate with Style Checks."""

import os
import pytest

from backend.ai.actions import Action
from backend.ai.base_agent import Agent
from backend.learning.league import (
    LeagueManager,
    ModelRegistry,
    compute_elo_update,
)


class DummyCandidateAgent(Agent):
    """Candidate agent with controlled aggression and defense behaviors."""
    def __init__(self, action_to_take=Action.FORWARD):
        super().__init__(name="DummyCandidate", player=1, difficulty="HIGH")
        self.action = action_to_take

    def choose_action(self, state):
        return self.action, {self.action: 1.0}


def test_elo_calculation():
    """Verify Elo updates calculate correct rating shifts with K=32."""
    r_a, r_b = 1000.0, 1000.0
    new_a, new_b = compute_elo_update(r_a, r_b, score_a=1.0, k=32.0)
    # Expected score is 0.5, so A gains 16.0, B loses 16.0
    assert new_a == pytest.approx(1016.0)
    assert new_b == pytest.approx(984.0)


def test_curriculum_tier_advancement():
    """Win rate over 75% across recent episodes advances curriculum tier."""
    league = LeagueManager(learner_personality="Crimson")
    assert league.curriculum_tier == 1

    # Simulate 25 consecutive wins
    for _ in range(25):
        league.record_match_result("random", learner_won=True)

    assert league.curriculum_tier == 2


def test_opponent_sampling_distribution():
    """Opponent sampling returns valid opponents from pool."""
    league = LeagueManager(learner_personality="Steel")
    sampled = [league.sample_opponent().name for _ in range(50)]
    assert len(set(sampled)) > 1


def test_style_check_evaluation():
    """Style checks enforce personality boundaries (e.g., Crimson aggression)."""
    league = LeagueManager(learner_personality="Crimson")

    # High aggression passes
    assert league.evaluate_style({"aggression": 0.70, "defense": 2.0, "avg_distance": 120.0}) is True

    # Low aggression fails Crimson style check
    assert league.evaluate_style({"aggression": 0.30, "defense": 2.0, "avg_distance": 120.0}) is False


def test_promotion_gate_and_registry_rollback(tmp_path):
    """Failing style check triggers rollback in the SQLite model registry."""
    db_path = str(tmp_path / "test_registry.db")
    reg = ModelRegistry(db_path=db_path)

    # Register initial live model
    reg.register_model(
        personality="Crimson",
        version_tag="v001",
        file_path="models/crimson/v001.pt",
        elo=1000.0,
        status="live",
        win_rate=0.60,
        style_metrics={"aggression": 0.70},
    )

    league = LeagueManager(learner_personality="Crimson")
    league.registry = reg

    # Passive agent: always IDLE (0.0 aggression -> fails style check)
    passive_agent = DummyCandidateAgent(action_to_take=Action.IDLE)
    promoted, status_msg, metrics = league.attempt_promotion(
        passive_agent, model_path="models/crimson/v002.pt", version_tag="v002"
    )

    assert promoted is False
    assert "ROLLED_BACK" in status_msg

    # Live model should still be v001
    live = reg.get_live_model("Crimson")
    assert live is not None
    assert live["version_tag"] == "v001"
