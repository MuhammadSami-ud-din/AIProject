import random

import pytest

from backend.ai.actions import Action
from backend.ai.choice import pick, probabilities, ranked

SCORES = {
    Action.LIGHT: 9,
    Action.HEAVY: 7,
    Action.FORWARD: 5,
    Action.BLOCK: 2,
    Action.BACK: 0,
}


# --- ranked ---------------------------------------------------------
def test_ranked_best_first():
    assert ranked(SCORES) == [Action.LIGHT, Action.HEAVY, Action.FORWARD, Action.BLOCK, Action.BACK]


# --- probabilities --------------------------------------------------
def test_no_variety_gives_all_chance_to_the_best():
    chances = probabilities(SCORES, variety=0)
    assert chances[Action.LIGHT] == 1
    assert sum(chances.values()) == 1


def test_ties_share_the_chance():
    chances = probabilities({Action.LIGHT: 5, Action.HEAVY: 5, Action.BLOCK: 1}, variety=0)
    assert chances[Action.LIGHT] == chances[Action.HEAVY] == 0.5


def test_variety_spreads_the_chances():
    low = probabilities(SCORES, variety=0.2)
    high = probabilities(SCORES, variety=1.0)
    assert sum(low.values()) == pytest.approx(1)
    assert sum(high.values()) == pytest.approx(1)
    assert high[Action.LIGHT] < low[Action.LIGHT]       # best move less sure
    assert high[Action.BACK] > low[Action.BACK]         # worst move more likely


def test_better_score_always_means_more_chance():
    chances = probabilities(SCORES, variety=0.5)
    order = ranked(SCORES)
    for better, worse in zip(order, order[1:]):
        assert chances[better] > chances[worse]


def test_same_variety_works_for_big_and_small_scores():
    small = probabilities(SCORES, variety=0.3)
    big = probabilities({a: s * 1000 for a, s in SCORES.items()}, variety=0.3)
    for action in SCORES:
        assert small[action] == pytest.approx(big[action])


def test_huge_scores_do_not_crash():
    chances = probabilities({Action.LIGHT: 1e300, Action.BLOCK: -1e300}, variety=0.5)
    assert sum(chances.values()) == pytest.approx(1)


# --- pick -----------------------------------------------------------
def test_pick_with_no_variety_always_picks_the_best():
    rng = random.Random(1)
    assert {pick(SCORES, rng) for _ in range(200)} == {Action.LIGHT}


def test_pick_with_variety_sometimes_picks_others():
    rng = random.Random(1)
    picks = [pick(SCORES, rng, variety=0.5) for _ in range(2000)]
    assert picks.count(Action.LIGHT) > picks.count(Action.HEAVY) > picks.count(Action.BACK)


def test_mistakes_pick_second_or_third_best_never_silly_moves():
    rng = random.Random(2)
    picks = {pick(SCORES, rng, mistake_chance=1.0) for _ in range(500)}
    assert picks == {Action.HEAVY, Action.FORWARD}


def test_mistake_with_only_one_move_still_picks_it():
    rng = random.Random(3)
    assert pick({Action.BLOCK: 1}, rng, mistake_chance=1.0) == Action.BLOCK


def test_same_seed_same_picks():
    a, b = random.Random(7), random.Random(7)
    picks_a = [pick(SCORES, a, variety=0.6, mistake_chance=0.2) for _ in range(300)]
    picks_b = [pick(SCORES, b, variety=0.6, mistake_chance=0.2) for _ in range(300)]
    assert picks_a == picks_b


def test_only_moves_in_the_scores_can_be_picked():
    rng = random.Random(4)
    allowed = {Action.BLOCK: 3, Action.BACK: 1}   # e.g. attacks not allowed right now
    picks = {pick(allowed, rng, variety=1.0, mistake_chance=0.5) for _ in range(300)}
    assert picks <= set(allowed)


# --- bad inputs -----------------------------------------------------
@pytest.mark.parametrize("bad_call", [
    lambda: pick({}, random.Random()),
    lambda: probabilities(SCORES, variety=1.5),
    lambda: pick(SCORES, random.Random(), mistake_chance=-0.1),
    lambda: probabilities({Action.LIGHT: float("nan")}),
    lambda: probabilities({Action.LIGHT: float("inf")}),
])
def test_bad_inputs_are_rejected(bad_call):
    with pytest.raises(ValueError):
        bad_call()


def test_text_instead_of_move_is_rejected():
    with pytest.raises(TypeError):
        probabilities({"LIGHT": 3})


# --- top_choices for the explanation panel ----------------------------
def test_top_choices_best_first():
    from backend.ai.choice import top_choices
    top = top_choices(SCORES, variety=0.5, n=3)
    assert [action for action, _ in top] == [Action.LIGHT, Action.HEAVY, Action.FORWARD]
    assert top[0][1] > top[1][1] > top[2][1]


def test_top_choices_with_fewer_moves_than_n():
    from backend.ai.choice import top_choices
    assert len(top_choices({Action.BLOCK: 1}, n=3)) == 1


def test_top_choices_rejects_zero():
    from backend.ai.choice import top_choices
    with pytest.raises(ValueError):
        top_choices(SCORES, n=0)
