"""Tests for Phase 2: Reward Shaping Profiles (edge-triggered, hack-resistant)."""

import pytest

from backend.ai.actions import Action
from backend.engine.state import FighterState, FightState
from backend.learning.config import (
    CRIMSON_BACKING_PENALTY,
    CRIMSON_COMBO_HIT_BONUS,
    CRIMSON_DAMAGE_BONUS,
    CRIMSON_PRESSURE_BONUS,
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


def test_crimson_forward_is_not_rewarded_but_results_are():
    """Pressing FORWARD earns nothing; damage, pressure and combos do."""
    calc = RewardCalculator(personality="Crimson")
    s_prev, s_curr = make_test_states()

    _, b_fwd = calc.calculate(s_prev, s_curr, Action.FORWARD, player=1)
    assert "forward_pressure" not in b_fwd
    assert b_fwd["personality_bonus"] == 0.0

    _, b_back = calc.calculate(s_prev, s_curr, Action.BACK, player=1)
    assert b_back.get("retreat_penalty") == pytest.approx(CRIMSON_BACKING_PENALTY)

    # Damage dealt -> aggression bonus proportional to damage
    s_prev2, s_curr2 = make_test_states()
    s_curr2.fighter2.health = 0.95
    _, b_dmg = calc.calculate(s_prev2, s_curr2, Action.HEAVY, player=1)
    assert b_dmg.get("damage_aggression") == pytest.approx(CRIMSON_DAMAGE_BONUS * 5.0)

    # Forcing a block while in range -> pressure bonus
    s_prev3, s_curr3 = make_test_states(p1_x=200.0, p2_x=260.0)
    s_curr3.fighter2.blockstun = 8
    _, b_pr = calc.calculate(s_prev3, s_curr3, Action.LIGHT, player=1)
    assert b_pr.get("pressure") == pytest.approx(CRIMSON_PRESSURE_BONUS)

    # Combo hits
    s_prev4, s_curr4 = make_test_states()
    s_prev4.fighter1.combo_hits = 2
    s_curr4.fighter1.combo_hits = 3
    _, b_combo = calc.calculate(s_prev4, s_curr4, Action.LIGHT, player=1)
    assert b_combo.get("combo_hits") == pytest.approx(CRIMSON_COMBO_HIT_BONUS * 3)


def test_crimson_cannot_farm_reward_by_walking():
    """1000 FORWARD steps with no contact give zero personality bonus."""
    calc = RewardCalculator(personality="Crimson")
    s_prev, s_curr = make_test_states()
    total_bonus = 0.0
    for _ in range(1000):
        _, b = calc.calculate(s_prev, s_curr, Action.FORWARD, player=1)
        total_bonus += b["personality_bonus"]
    assert total_bonus == 0.0


def test_steel_parry_and_block_are_edge_triggered():
    """A sticky 'parry' value is paid once, not every step."""
    calc = RewardCalculator(personality="Steel")
    s_prev, s_curr = make_test_states()
    s_curr.fighter1.last_hit_effect = "parry"
    _, b1 = calc.calculate(s_prev, s_curr, Action.BLOCK, player=1)
    assert b1.get("perfect_parry") == pytest.approx(STEEL_PARRY_BONUS)

    # Next step: effect still reads "parry" (old sticky engine) -> no new reward
    s_next = s_curr.copy()
    s_next.frame += 6
    _, b2 = calc.calculate(s_curr, s_next, Action.BLOCK, player=1)
    assert "perfect_parry" not in b2

    # Clean block event
    s_prev, s_curr = make_test_states()
    s_curr.fighter1.last_hit_effect = "block"
    _, b_block = calc.calculate(s_prev, s_curr, Action.BLOCK, player=1)
    assert b_block.get("clean_block") == pytest.approx(STEEL_BLOCK_BONUS)


def test_steel_punish_after_block():
    calc = RewardCalculator(personality="Steel")
    s_prev, s_curr = make_test_states()
    calc.frames_since_last_block = 10
    s_curr.fighter2.health = 0.90
    _, b = calc.calculate(s_prev, s_curr, Action.HEAVY, player=1)
    assert b.get("block_punish") == pytest.approx(STEEL_PUNISH_BONUS * 10.0)


def test_per_frame_events_inside_macro_step_are_counted_once():
    """The env reports one-frame events via observe_frame; they are paid exactly once."""
    calc = RewardCalculator(personality="Steel")
    f0, _ = make_test_states()
    frames = [f0]
    for i in range(6):
        nxt = frames[-1].copy()
        nxt.frame += 1
        nxt.fighter1.last_hit_effect = "parry" if i == 2 else "none"   # one-frame contract
        frames.append(nxt)
    for a, b in zip(frames, frames[1:]):
        calc.observe_frame(a, b, 1)
    _, br = calc.calculate(frames[0], frames[-1], Action.BLOCK, player=1)
    assert br.get("perfect_parry") == pytest.approx(STEEL_PARRY_BONUS)
    # nothing pending afterwards
    _, br2 = calc.calculate(frames[-1], frames[-1], Action.BLOCK, player=1)
    assert "perfect_parry" not in br2


def test_shadow_reward_bonuses_and_penalties():
    calc = RewardCalculator(personality="Shadow")
    s_prev, s_curr = make_test_states(p1_x=200.0, p2_x=400.0)
    _, b_space = calc.calculate(s_prev, s_curr, Action.IDLE, player=1)
    assert b_space.get("preferred_spacing") == pytest.approx(SHADOW_PREFERRED_DIST_BONUS)

    s_prev.fighter2.recovery = 10
    s_curr.fighter2.health = 0.95
    _, b_wp = calc.calculate(s_prev, s_curr, Action.LIGHT, player=1)
    assert b_wp.get("whiff_punish") == pytest.approx(SHADOW_WHIFF_PUNISH_BONUS)

    s_prev_c, s_curr_c = make_test_states(p1_x=40.0, p2_x=150.0)
    _, b_corner = calc.calculate(s_prev_c, s_curr_c, Action.IDLE, player=1)
    assert b_corner.get("cornered_penalty") == pytest.approx(SHADOW_CORNER_PENALTY)


def test_golden_read_uses_engine_name_and_is_edge_triggered():
    calc = RewardCalculator(personality="Golden")
    s_prev, s_curr = make_test_states()
    s_curr.fighter1.last_hit_effect = "read"
    s_curr.fighter1.read_success = True
    _, b_read = calc.calculate(s_prev, s_curr, Action.SPECIAL_NEUTRAL, player=1)
    assert b_read.get("golden_read_hit") == pytest.approx(GOLDEN_READ_HIT_BONUS)

    # read_success staying True is not paid again
    s_next = s_curr.copy()
    s_next.frame += 6
    _, b_again = calc.calculate(s_curr, s_next, Action.IDLE, player=1)
    assert "golden_read_hit" not in b_again

    s_win = s_next.copy()
    s_win.round_over = True
    s_win.round_result = "p1"
    _, b_win = calc.calculate(s_next, s_win, Action.IDLE, player=1)
    assert b_win.get("round_outcome") == pytest.approx(ROUND_WIN_REWARD)
    assert b_win.get("golden_round_win") == pytest.approx(GOLDEN_ROUND_WIN_BONUS)


def test_personality_bonus_can_be_disabled_for_ablation():
    calc = RewardCalculator(personality="Steel", use_personality_bonus=False)
    s_prev, s_curr = make_test_states()
    s_curr.fighter1.last_hit_effect = "parry"
    _, b = calc.calculate(s_prev, s_curr, Action.BLOCK, player=1)
    assert b["personality_bonus"] == 0.0


def test_reward_breakdown_totals_accumulate_correctly():
    calc = RewardCalculator(personality="Crimson")
    s_prev, s_curr = make_test_states()
    s_curr.fighter2.health = 0.95
    s_curr.fighter1.health = 0.98
    total_r, _ = calc.calculate(s_prev, s_curr, Action.FORWARD, player=1)
    assert calc.tracker.total() == pytest.approx(total_r, abs=1e-5)
    assert calc.tracker.base_damage == pytest.approx(3.0, abs=1e-5)
