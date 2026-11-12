import dataclasses

import pytest

from backend.ai.personalities import (
    ALL_PERSONALITIES,
    CRIMSON,
    GOLDEN,
    LIKE_FIELDS,
    SHADOW,
    STEEL,
    Personality,
)


def test_there_are_four_fighters():
    assert set(ALL_PERSONALITIES) == {"Crimson", "Steel", "Shadow", "Golden"}


def test_full_names_match_the_proposal():
    names = {p.full_name for p in ALL_PERSONALITIES.values()}
    assert names == {"Crimson Brawler", "Steel Guardian", "Shadow Striker", "Golden Tactician"}


def test_each_fighter_has_its_own_style():
    fighters = ALL_PERSONALITIES.values()
    assert CRIMSON.closeness == max(p.closeness for p in fighters)
    assert STEEL.block_punish == max(p.block_punish for p in fighters)
    assert SHADOW.safe_distance == max(p.safe_distance for p in fighters)
    assert SHADOW.corner_avoid == max(p.corner_avoid for p in fighters)


def test_only_golden_adapts():
    assert [p.name for p in ALL_PERSONALITIES.values() if p.adapts] == ["Golden"]
    assert GOLDEN.adapt_speed > 0


def test_likes_returns_all_six():
    likes = CRIMSON.likes()
    assert list(likes) == list(LIKE_FIELDS)
    assert likes["closeness"] == 9


def test_numbers_cannot_be_changed_by_accident():
    with pytest.raises(dataclasses.FrozenInstanceError):
        CRIMSON.closeness = 0


@pytest.mark.parametrize("bad_change", [
    {"closeness": 15},
    {"corner_avoid": -1},
    {"panic_health": 2},
    {"preferred_distance": 0},
    {"panic_aggression": 0},
    {"variety": 1.5},
    {"adapt_speed": 2},
    {"adapts": True, "adapt_speed": 0},
])
def test_bad_numbers_are_rejected(bad_change):
    with pytest.raises(ValueError):
        dataclasses.replace(CRIMSON, **bad_change)


def test_a_tuned_copy_can_be_made():
    tuned = dataclasses.replace(CRIMSON, closeness=7)
    assert tuned.closeness == 7
    assert CRIMSON.closeness == 9


def test_can_be_saved_and_loaded():
    saved = dataclasses.asdict(STEEL)
    assert Personality(**saved) == STEEL


# --- mix ("personality genome") --------------------------------------
def test_half_and_half_mix():
    from backend.ai.personalities import mix
    child = mix(CRIMSON, SHADOW)
    assert child.name == "Crimson-Shadow"
    assert child.closeness == 5            # (9 + 1) / 2
    assert child.safe_distance == 5        # (1 + 9) / 2
    assert child.preferred_distance == 130 # (60 + 200) / 2
    assert not child.adapts


def test_mix_with_golden_adapts():
    from backend.ai.personalities import mix
    assert mix(STEEL, GOLDEN).adapts


def test_mostly_one_parent():
    from backend.ai.personalities import mix
    child = mix(CRIMSON, STEEL, share_of_a=1.0)
    assert child.likes() == CRIMSON.likes()
    assert not child.adapts


def test_bad_share_is_rejected():
    from backend.ai.personalities import mix
    with pytest.raises(ValueError):
        mix(CRIMSON, STEEL, share_of_a=1.5)


# --- Genome: list form, rebuilding, mutation ---------------------------
def test_genome_round_trip():
    from backend.ai.personalities import GENOME_FIELDS, from_genome
    numbers = CRIMSON.genome()
    assert len(numbers) == len(GENOME_FIELDS)
    rebuilt = from_genome(numbers, name="Crimson")
    assert rebuilt.genome() == numbers


def test_genome_with_wrong_length_is_rejected():
    from backend.ai.personalities import from_genome
    with pytest.raises(ValueError):
        from_genome([1, 2, 3])


def test_mutate_changes_numbers_but_stays_valid():
    import random

    from backend.ai.personalities import GENOME_FIELDS, GENOME_LIMITS, mutate
    rng = random.Random(5)
    child = CRIMSON
    for _ in range(300):                       # many generations in a row
        child = mutate(child, rng, amount=0.3)
    assert child.genome() != CRIMSON.genome()
    for field in GENOME_FIELDS:
        low, high = GENOME_LIMITS[field]
        assert low <= getattr(child, field) <= high


def test_mutate_is_repeatable_with_the_same_seed():
    import random

    from backend.ai.personalities import mutate
    a = mutate(STEEL, random.Random(9))
    b = mutate(STEEL, random.Random(9))
    assert a == b


def test_mutate_with_zero_amount_changes_nothing():
    import random

    from backend.ai.personalities import mutate
    assert mutate(SHADOW, random.Random(1), amount=0).genome() == SHADOW.genome()
