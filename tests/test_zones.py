import pytest

from backend.ai.personalities import CRIMSON, SHADOW
from backend.ai.zones import (
    CLOSE_LIMIT,
    FAR_LIMIT,
    Gap,
    Spacing,
    Zone,
    ZoneTracker,
    distance_between,
    distance_ratio,
    gap_change,
    in_range,
    is_cornered,
    is_safe_poke,
    room_behind,
    spacing_for,
    zone_of,
)


# --- Distance ---------------------------------------------------
def test_distance_is_the_same_from_both_sides():
    assert distance_between(100, 300) == 200
    assert distance_between(300, 100) == 200


def test_distance_ratio():
    assert distance_ratio(0) == 0
    assert distance_ratio(400) == 0.5
    assert distance_ratio(5000) == 1.0  # never above 1


def test_limits_come_from_arena_width():
    assert CLOSE_LIMIT == 80
    assert FAR_LIMIT == 220


# --- Question 1: zones -------------------------------------------
@pytest.mark.parametrize(("distance", "zone"), [
    (0, Zone.CLOSE),
    (79, Zone.CLOSE),
    (80, Zone.MID),
    (220, Zone.MID),
    (221, Zone.FAR),
    (700, Zone.FAR),
])
def test_zone_of(distance, zone):
    assert zone_of(distance) == zone


def test_tracker_does_not_flicker_on_the_limit():
    tracker = ZoneTracker(buffer=10)
    labels = [tracker.update(d) for d in (75, 81, 79, 82, 78, 84)]
    assert labels == [Zone.CLOSE] * 6   # plain zone_of would flip CLOSE/MID every frame


def test_tracker_changes_when_clearly_in_the_new_zone():
    tracker = ZoneTracker(buffer=10)
    tracker.update(75)
    assert tracker.update(95) == Zone.MID
    assert tracker.update(65) == Zone.CLOSE


def test_tracker_follows_big_jumps():
    tracker = ZoneTracker(buffer=10)
    tracker.update(30)
    assert tracker.update(600) == Zone.FAR  # knocked across the arena


def test_tracker_reset():
    tracker = ZoneTracker()
    tracker.update(30)
    tracker.reset()
    assert tracker.current is None


# --- Question 2: spacing -----------------------------------------
def test_same_distance_different_feeling():
    assert spacing_for(200, CRIMSON) == Spacing.TOO_FAR    # Crimson wants to be close
    assert spacing_for(200, SHADOW) == Spacing.JUST_RIGHT  # Shadow likes it here


def test_too_close_for_shadow():
    assert spacing_for(60, SHADOW) == Spacing.TOO_CLOSE


def test_crimson_happy_up_close():
    assert spacing_for(60, CRIMSON) == Spacing.JUST_RIGHT


# --- Question 3: gap change -----------------------------------
def test_gap_change():
    assert gap_change(200, 190) == Gap.CLOSING
    assert gap_change(200, 210) == Gap.OPENING
    assert gap_change(200, 200.5) == Gap.STEADY


# --- Question 4: attack range ------------------------------------
def test_in_range():
    assert in_range(50, attack_range=60)
    assert in_range(60, attack_range=60)
    assert not in_range(61, attack_range=60)


def test_safe_poke_is_between_the_two_ranges():
    # My attack reaches 150, the enemy's reaches 80.
    assert is_safe_poke(120, my_range=150, enemy_range=80)       # I hit, they can't
    assert not is_safe_poke(60, my_range=150, enemy_range=80)    # both can hit
    assert not is_safe_poke(200, my_range=150, enemy_range=80)   # nobody can hit


# --- Question 5: walls -------------------------------------------
def test_room_behind():
    assert room_behind(my_x=100, enemy_x=300, arena_left=0, arena_right=800) == 100
    assert room_behind(my_x=700, enemy_x=300, arena_left=0, arena_right=800) == 100


def test_cornered_against_left_wall():
    assert is_cornered(my_x=30, enemy_x=200, arena_left=0, arena_right=800)


def test_cornered_against_right_wall():
    assert is_cornered(my_x=770, enemy_x=500, arena_left=0, arena_right=800)


def test_near_a_wall_but_facing_it_is_not_cornered():
    assert not is_cornered(my_x=50, enemy_x=10, arena_left=0, arena_right=800)


def test_middle_of_arena_is_not_cornered():
    assert not is_cornered(my_x=400, enemy_x=500, arena_left=0, arena_right=800)


def test_check_if_enemy_is_cornered_by_swapping():
    me, enemy = 300, 30
    assert is_cornered(enemy, me, arena_left=0, arena_right=800)


# --- Bad inputs ---------------------------------------------------
@pytest.mark.parametrize("bad_call", [
    lambda: zone_of(-5),
    lambda: spacing_for(-5, CRIMSON),
    lambda: distance_ratio(-1),
    lambda: gap_change(-1, 10),
    lambda: in_range(10, attack_range=-1),
    lambda: room_behind(10, 20, arena_left=800, arena_right=0),
    lambda: ZoneTracker(buffer=-1),
])
def test_bad_inputs_are_rejected(bad_call):
    with pytest.raises(ValueError):
        bad_call()
