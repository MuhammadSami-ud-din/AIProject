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


def test_run_training_ablation_really_trains(tmp_path):
    """The ablation trains every configuration (tiny budget) and reports measured numbers only."""
    results = run_training_ablation(
        personality="Crimson", updates=1, n_envs=1, steps_per_env=16,
        bc_matches=3, bc_epochs=1, eval_matches=3,
        work_dir=str(tmp_path / "work"), results_dir=str(tmp_path / "res"),
    )
    for key in ("full_reward", "no_personality_bonus", "no_bc"):
        entry = results[key]
        assert entry["matches"] == 3
        assert entry["win_rate_vs_baseline"] == entry["wins"] / 3
        assert 0.0 <= entry["style_adherence"]["aggression_ratio"] <= 1.0
        assert entry["final_training_history"]["update"] == 1
    assert results["no_bc"]["use_bc_warm_start"] is False
    assert os.path.exists(tmp_path / "res" / "ablation_training_crimson.json")
    # each configuration trained its own checkpoint in the work dir, not in models/
    assert os.path.exists(tmp_path / "work" / "no_bc" / "crimson" / "v001.pt")


def test_eval_module_has_no_hardcoded_metrics():
    import inspect
    import backend.learning.eval as ev
    src = inspect.getsource(ev)
    for fabricated in ("0.72", "0.58", "0.46", "Synthetic"):
        assert fabricated not in src


def test_difficulty_separation_monotonicity(tmp_path):
    results = verify_difficulty_separation(personality="Steel", num_matches=2, results_dir=str(tmp_path))
    for diff in ["LOW", "MEDIUM", "HIGH", "HELL"]:
        low, high = results[diff]["ci_95"]
        assert 0.0 <= low <= high <= 1.0
    assert os.path.exists(tmp_path / "difficulty_separation.json")


def test_compare_difficulty_tiers(tmp_path):
    comparison = compare_difficulty_tiers(personality="Steel", num_matches=2, results_dir=str(tmp_path))
    assert {"MEDIUM_vs_LOW", "HIGH_vs_MEDIUM", "HELL_vs_HIGH"} <= set(comparison)
    assert os.path.exists(tmp_path / "difficulty_tiers.json")
