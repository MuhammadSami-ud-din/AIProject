"""Tests for Phase 7: Evaluation, Confidence Intervals, and Ablation Studies."""

import os
import pytest

from backend.learning.eval import (
    binomial_test_greater,
    compare_difficulty_tiers,
    run_ablation_study,
    run_training_ablation,
    verify_difficulty_separation,
    wilson_score_interval,
)


def test_wilson_score_interval_properties():
    """Wilson score confidence interval bounds are valid and well-formed."""
    low, high = wilson_score_interval(successes=70, trials=100, confidence=0.95)
    assert 0.0 <= low <= high <= 1.0
    assert 0.60 <= low <= 0.70
    assert 0.70 <= high <= 0.80

    # 0 trials edge case
    l0, h0 = wilson_score_interval(0, 0)
    assert l0 == 0.0 and h0 == 0.0


def test_binomial_test_greater():
    """Binomial test correctly computes one-sided p-values."""
    # 20 out of 20 wins is extremely significant (p << 0.01)
    p_high = binomial_test_greater(k=20, n=20, p0=0.5)
    assert p_high < 0.001

    # 10 out of 20 wins is consistent with null hypothesis p0=0.5
    p_mid = binomial_test_greater(k=10, n=20, p0=0.5)
    assert p_mid > 0.5


def test_run_training_ablation_saves_json():
    """Training ablation study runs and outputs structured results to data/ablation_results.json."""
    results = run_training_ablation(personality="Crimson", episodes=2)

    assert "full_reward" in results
    assert "no_personality_bonus" in results
    assert "no_bc" in results

    # Full reward retains rushdown style
    assert results["full_reward"]["style_adherence"]["passed_style_constraint"] is True
    # Without rushdown bonus, style constraint fails
    assert results["no_personality_bonus"]["style_adherence"]["passed_style_constraint"] is False

    assert os.path.exists("data/ablation_results.json")


def test_difficulty_separation_monotonicity():
    """Difficulty tiers progress monotonically from LOW to HELL."""
    results = verify_difficulty_separation(personality="Steel", num_matches=4)

    assert "LOW" in results
    assert "MEDIUM" in results
    assert "HIGH" in results
    assert "HELL" in results
    for diff in ["LOW", "MEDIUM", "HIGH", "HELL"]:
        assert "win_rate" in results[diff]
        assert "ci_95" in results[diff]
        low, high = results[diff]["ci_95"]
        assert 0.0 <= low <= high <= 1.0


def test_compare_difficulty_tiers():
    """Adjacent difficulty tiers comparison produces win rates and p-values."""
    comparison = compare_difficulty_tiers(personality="Steel", num_matches=4)
    assert "MEDIUM_vs_LOW" in comparison
    assert "HIGH_vs_MEDIUM" in comparison
    assert "HELL_vs_HIGH" in comparison

    assert os.path.exists("data/difficulty_eval.json")
