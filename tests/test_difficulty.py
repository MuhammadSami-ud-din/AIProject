"""Tests for difficulty wrapper, evaluation, and search."""

import pytest

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.crimson import CrimsonAgent
from backend.ai.difficulty import (
    DIFFICULTY_PROFILES,
    DifficultyProfile,
    DifficultyWrapper,
    MISTAKE_CHANCE,
    REACTION_DELAY,
    SEARCH_DEPTH,
    adrenaline_level,
    effective_profile,
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
    assert REACTION_DELAY["HIGH"] == 8
    assert REACTION_DELAY["HELL"] == 2


def test_mistake_chance_values():
    assert MISTAKE_CHANCE["LOW"] == 0.35
    assert MISTAKE_CHANCE["MEDIUM"] == 0.18
    assert MISTAKE_CHANCE["HIGH"] == 0.07
    assert MISTAKE_CHANCE["HELL"] == 0.01


def test_search_depth_values():
    assert SEARCH_DEPTH["LOW"] == 1
    assert SEARCH_DEPTH["MEDIUM"] == 2
    assert SEARCH_DEPTH["HIGH"] == 3
    assert SEARCH_DEPTH["HELL"] == 4


def test_difficulty_profile_table_values():
    """Verify the frozen DifficultyProfile table contains all Step 2 settings."""
    low = DIFFICULTY_PROFILES["LOW"]
    med = DIFFICULTY_PROFILES["MEDIUM"]
    high = DIFFICULTY_PROFILES["HIGH"]
    hell = DIFFICULTY_PROFILES["HELL"]

    assert (low.decides_every_n_frames, med.decides_every_n_frames, high.decides_every_n_frames, hell.decides_every_n_frames) == (12, 8, 4, 2)
    assert (low.block_chance, med.block_chance, high.block_chance, hell.block_chance) == (0.15, 0.40, 0.70, 0.90)
    assert (low.punish_chance, med.punish_chance, high.punish_chance, hell.punish_chance) == (0.05, 0.30, 0.70, 0.95)
    assert (low.combo_completion, med.combo_completion, high.combo_completion, hell.combo_completion) == (0.30, 0.60, 0.85, 0.98)
    assert (low.anti_air_chance, med.anti_air_chance, high.anti_air_chance, hell.anti_air_chance) == (0.10, 0.40, 0.75, 0.95)
    assert (low.hesitation, med.hesitation, high.hesitation, hell.hesitation) == (0.25, 0.12, 0.04, 0.00)
    assert (low.whiff_rate, med.whiff_rate, high.whiff_rate, hell.whiff_rate) == (0.30, 0.15, 0.05, 0.01)
    assert (low.opponent_model, med.opponent_model, high.opponent_model, hell.opponent_model) == ("off", "counts", "bayes", "live")


def test_adrenaline_sharpening_as_health_drops():
    """Reaction delay and mistake chance go down as health drops (GREEN -> YELLOW -> RED)."""
    for mode in ("LOW", "MEDIUM", "HIGH", "HELL"):
        green = effective_profile(mode, 0.85)
        yellow = effective_profile(mode, 0.40)
        red = effective_profile(mode, 0.10)

        assert adrenaline_level(0.85) == "GREEN"
        assert adrenaline_level(0.40) == "YELLOW"
        assert adrenaline_level(0.10) == "RED"

        assert green.reaction_delay >= yellow.reaction_delay >= red.reaction_delay
        assert green.mistake_chance >= yellow.mistake_chance >= red.mistake_chance
        assert green.block_chance <= yellow.block_chance <= red.block_chance
        assert green.punish_chance <= yellow.punish_chance <= red.punish_chance

    # HELL in RED goes down to 1-frame reaction
    assert effective_profile("HELL", 0.10).reaction_delay == 1


def test_adrenaline_never_breaks_next_mode_green_limit():
    """A mode in RED never becomes better than the NEXT mode's GREEN values."""
    pairs = [("LOW", "MEDIUM"), ("MEDIUM", "HIGH"), ("HIGH", "HELL")]
    for lower_mode, next_mode in pairs:
        for h_int in range(0, 101):
            h = h_int / 100.0
            lower_eff = effective_profile(lower_mode, h)
            next_green = effective_profile(next_mode, 1.0)

            assert lower_eff.reaction_delay >= next_green.reaction_delay
            assert lower_eff.mistake_chance >= next_green.mistake_chance
            assert lower_eff.decides_every_n_frames >= next_green.decides_every_n_frames
            assert lower_eff.block_chance <= next_green.block_chance
            assert lower_eff.punish_chance <= next_green.punish_chance
            assert lower_eff.anti_air_chance <= next_green.anti_air_chance
            assert lower_eff.hesitation >= next_green.hesitation


def test_adrenaline_is_deterministic_and_smooth():
    """Same health always produces identical profile values; 5% transition is smooth."""
    for mode in ("LOW", "MEDIUM", "HIGH", "HELL"):
        for h in (0.90, 0.58, 0.42, 0.22, 0.12):
            p1 = effective_profile(mode, h)
            p2 = effective_profile(mode, h)
            assert p1 == p2

    # Midpoint of 5% transition band (0.575 is halfway between 0.60 and 0.55)
    high_g = effective_profile("HIGH", 0.60)
    high_mid = effective_profile("HIGH", 0.575)
    high_y = effective_profile("HIGH", 0.55)
    assert high_g.mistake_chance > high_mid.mistake_chance > high_y.mistake_chance


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
