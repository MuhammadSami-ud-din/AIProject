"""Tests for Phase 2: Reward Shaping Profiles and Personality Emergence."""

import pytest

from backend.ai.actions import Action
from backend.engine.state import FighterState, FightState
from backend.learning.config import (
    CRIMSON_BACKING_PENALTY,
    CRIMSON_COMBO_HIT_BONUS,
    CRIMSON_FORWARD_BONUS,
    GOLDEN_READ_HIT_BONUS,
    GOLDEN_ROUND_WIN_BONUS,
    ROUND_WIN_REWARD,
    SHADOW_CORNER_PENALTY,
    SHADOW_PREFERRED_DIST_BONUS,
    SHADOW_WHIFF_PUNISH_BONUS,
    STEEL_BLOCK_BONUS,
    STEEL_PARRY_BONUS,
    STEEL_PUNISH_BONUS,
)
from backend.learning.rewards import RewardCalculator


def make_test_states(p1_x=200.0, p2_x=300.0, p1_hp=1.0, p2_hp=1.0):
    s_prev = FightState(
        fighter1=FighterState(character_name="Crimson", x=p1_x, health=p1_hp),
        fighter2=FighterState(character_name="Steel", x=p2_x, health=p2_hp),
    )
    s_curr = s_prev.copy()
    s_curr.frame += 6
    return s_prev, s_curr


def test_crimson_reward_bonuses_and_penalties():
    """Crimson earns bonus for advancing and combos; penalized for retreating."""
    calc = RewardCalculator(personality="Crimson")
    s_prev, s_curr = make_test_states()

    # 1. Advancing forward
    r_fwd, b_fwd = calc.calculate(s_prev, s_curr, Action.FORWARD, player=1)
    assert b_fwd.get("forward_pressure") == pytest.approx(CRIMSON_FORWARD_BONUS)

    # 2. Backing away
    r_back, b_back = calc.calculate(s_prev, s_curr, Action.BACK, player=1)
    assert b_back.get("retreat_penalty") == pytest.approx(CRIMSON_BACKING_PENALTY)

    # 3. Combo hits
    s_curr.fighter1.combo_hits = 3
    s_prev.fighter1.combo_hits = 2
    r_combo, b_combo = calc.calculate(s_prev, s_curr, Action.LIGHT, player=1)
    assert b_combo.get("combo_hits") == pytest.approx(CRIMSON_COMBO_HIT_BONUS * 3)


def test_steel_reward_bonuses():
    """Steel earns bonuses for blocks, parries, and block punishes."""
    calc = RewardCalculator(personality="Steel")
    s_prev, s_curr = make_test_states()

    # 1. Perfect Parry
    s_curr.fighter1.last_hit_effect = "parry"
    r_parry, b_parry = calc.calculate(s_prev, s_curr, Action.BLOCK, player=1)
    assert b_parry.get("perfect_parry") == pytest.approx(STEEL_PARRY_BONUS)

    # 2. Clean Block
    s_curr.fighter1.last_hit_effect = "block"
    r_block, b_block = calc.calculate(s_prev, s_curr, Action.BLOCK, player=1)
    assert b_block.get("clean_block") == pytest.approx(STEEL_BLOCK_BONUS)

    # 3. Punish after block (within 30 frames)
    calc.frames_since_last_block = 10
    s_prev.fighter2.health = 1.0
    s_curr.fighter2.health = 0.90  # dealt 0.10 damage (10 HP)
    r_punish, b_punish = calc.calculate(s_prev, s_curr, Action.HEAVY, player=1)
    expected_punish = STEEL_PUNISH_BONUS * 10.0
    assert b_punish.get("block_punish") == pytest.approx(expected_punish)


def test_shadow_reward_bonuses_and_penalties():
    """Shadow earns bonuses for preferred spacing and whiff punishes; penalized when cornered."""
    calc = RewardCalculator(personality="Shadow")

    # 1. Preferred distance spacing (200px is between 180 and 320)
    s_prev, s_curr = make_test_states(p1_x=200.0, p2_x=400.0)
    r_space, b_space = calc.calculate(s_prev, s_curr, Action.IDLE, player=1)
    assert b_space.get("preferred_spacing") == pytest.approx(SHADOW_PREFERRED_DIST_BONUS)

    # 2. Whiff Punish: opponent in recovery while taking damage
    s_prev.fighter2.recovery = 10
    s_curr.fighter2.health = 0.95
    r_wp, b_wp = calc.calculate(s_prev, s_curr, Action.LIGHT, player=1)
    assert b_wp.get("whiff_punish") == pytest.approx(SHADOW_WHIFF_PUNISH_BONUS)

    # 3. Cornered penalty (less than 75px from back wall)
    s_prev_c, s_curr_c = make_test_states(p1_x=40.0, p2_x=150.0)
    r_corner, b_corner = calc.calculate(s_prev_c, s_curr_c, Action.IDLE, player=1)
    assert b_corner.get("cornered_penalty") == pytest.approx(SHADOW_CORNER_PENALTY)


def test_golden_reward_bonuses():
    """Golden earns bonuses for round wins and successful Golden Read counters."""
    calc = RewardCalculator(personality="Golden")
    s_prev, s_curr = make_test_states()

    # 1. Golden Read hit
    s_curr.fighter1.last_hit_effect = "golden_read"
    r_read, b_read = calc.calculate(s_prev, s_curr, Action.SPECIAL_BACK, player=1)
    assert b_read.get("golden_read_hit") == pytest.approx(GOLDEN_READ_HIT_BONUS)

    # 2. Round win bonus
    s_curr.round_over = True
    s_curr.round_result = "p1"
    r_win, b_win = calc.calculate(s_prev, s_curr, Action.IDLE, player=1)
    assert b_win.get("round_outcome") == pytest.approx(ROUND_WIN_REWARD)
    assert b_win.get("golden_round_win") == pytest.approx(GOLDEN_ROUND_WIN_BONUS)


def test_reward_breakdown_totals_accumulate_correctly():
    """Cumulative tracker totals must match the sum of individual components."""
    calc = RewardCalculator(personality="Crimson")
    s_prev, s_curr = make_test_states()
    s_prev.fighter2.health = 1.0
    s_curr.fighter2.health = 0.95  # +5 reward
    s_prev.fighter1.health = 1.0
    s_curr.fighter1.health = 0.98  # -2 reward

    total_r, b = calc.calculate(s_prev, s_curr, Action.FORWARD, player=1)
    assert calc.tracker.total() == pytest.approx(total_r, abs=1e-5)
    assert calc.tracker.base_damage == pytest.approx(3.0, abs=1e-5)
