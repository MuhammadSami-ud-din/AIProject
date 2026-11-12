import dataclasses

import pytest

from backend.ai.actions import Action
from backend.ai.observation import FEATURE_NAMES, Observation, example_observation
from backend.ai.personalities import CRIMSON, STEEL
from backend.ai.zones import Zone


# --- Basics --------------------------------------------------------
def test_example_is_a_normal_moment():
    obs = example_observation()
    assert obs.distance == 200
    assert obs.zone == Zone.MID
    assert obs.health_lead == 0
    assert obs.can_attack
    assert obs.enemy_direction == 1


def test_changing_one_part():
    obs = example_observation(my_health=0.3, enemy_health=0.8)
    assert obs.health_lead == pytest.approx(-0.5)


def test_must_use_names_not_positions():
    with pytest.raises(TypeError):
        Observation(300, 500, 1.0, 1.0, 70, 70, 60)


def test_cannot_be_changed_by_accident():
    obs = example_observation()
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.my_health = 0


# --- Direction ------------------------------------------------------
def test_enemy_on_my_left():
    assert example_observation(my_x=500, enemy_x=300).enemy_direction == -1


# --- What I can do --------------------------------------------------
def test_cooldown_blocks_attacking():
    assert not example_observation(my_cooldown=5).can_attack


def test_being_stuck_blocks_everything():
    obs = example_observation(my_recovery=8)
    assert not obs.can_act
    assert not obs.can_attack


def test_hit_ranges():
    near = example_observation(my_x=300, enemy_x=360)   # 60 apart, reach 70
    far = example_observation(my_x=300, enemy_x=500)    # 200 apart
    assert near.i_can_hit and near.enemy_can_hit
    assert not far.i_can_hit and not far.enemy_can_hit


def test_safe_poke():
    obs = example_observation(my_x=300, enemy_x=400, my_reach=120, enemy_reach=80)
    assert obs.is_safe_poke


# --- What the enemy is doing ----------------------------------------
def test_enemy_attacking_and_stuck():
    obs = example_observation(enemy_last_action=Action.HEAVY, enemy_recovery=12)
    assert obs.enemy_is_attacking
    assert obs.enemy_is_stuck
    assert obs.enemy_is_open
    assert not example_observation().enemy_is_stuck


def test_enemy_blocking():
    assert example_observation(enemy_last_action=Action.BLOCK).enemy_is_blocking


def test_enemy_open_during_cooldown():
    assert example_observation(enemy_cooldown=10).enemy_is_open
    assert not example_observation().enemy_is_open


# --- Health and panic -----------------------------------------------
def test_panic_depends_on_the_fighter():
    obs = example_observation(my_health=0.28)
    assert not obs.is_panicking(CRIMSON)   # Crimson panics below 25%
    assert obs.is_panicking(STEEL)         # Steel panics below 30%


# --- Walls ----------------------------------------------------------
def test_walls():
    obs = example_observation(my_x=30, enemy_x=200)
    assert obs.room_behind_me == 30
    assert obs.i_am_cornered
    assert not obs.enemy_is_cornered


def test_enemy_cornered():
    obs = example_observation(my_x=600, enemy_x=780)
    assert obs.enemy_is_cornered
    assert not obs.i_am_cornered


# --- Time -----------------------------------------------------------
def test_time():
    assert example_observation(time_left=60).time_ratio == 1
    assert example_observation(time_left=30).time_ratio == 0.5
    assert example_observation(time_left=8).time_running_out
    assert not example_observation(time_left=30).time_running_out


# --- Seeing from the enemy's side -------------------------------------
def test_swapped_sees_from_the_enemy_side():
    obs = example_observation(my_health=0.9, enemy_health=0.4,
                              my_cooldown=5, enemy_last_action=Action.LIGHT,
                              my_rounds_won=1)
    enemy_view = obs.swapped()
    assert enemy_view.my_health == 0.4
    assert enemy_view.health_lead == pytest.approx(-0.5)
    assert enemy_view.enemy_cooldown == 5
    assert enemy_view.my_last_action == Action.LIGHT
    assert enemy_view.enemy_rounds_won == 1
    assert enemy_view.enemy_direction == -obs.enemy_direction


def test_swapping_twice_gives_back_the_original():
    obs = example_observation(my_x=120, my_health=0.7, enemy_in_air=True)
    assert obs.swapped().swapped() == obs


# --- Numbers for learning -------------------------------------------
def test_features_have_the_agreed_names_in_order():
    assert tuple(example_observation().features()) == FEATURE_NAMES


def test_features_are_numbers_in_a_small_range():
    obs = example_observation(my_cooldown=500, enemy_in_air=True, time_left=0)
    for name, value in obs.features().items():
        assert isinstance(value, (int, float)), name
        assert -1 <= value <= 6, name   # actions are 0-6, everything else -1 to 1


# --- Bad values -----------------------------------------------------
@pytest.mark.parametrize("bad_change", [
    {"my_health": 1.5},
    {"enemy_health": -0.1},
    {"my_cooldown": -1},
    {"enemy_recovery": -1},
    {"time_left": -3},
    {"time_left": 90},
    {"round_length": 0},
    {"my_x": 900},
    {"arena_left": 800, "arena_right": 0},
    {"round_number": 0},
    {"my_rounds_won": 3},
    {"frame": -1},
])
def test_bad_values_are_rejected(bad_change):
    with pytest.raises(ValueError):
        example_observation(**bad_change)


@pytest.mark.parametrize("bad_change", [
    {"enemy_last_action": "LIGHT"},
    {"my_in_air": "yes"},
])
def test_wrong_kind_of_value_is_rejected(bad_change):
    with pytest.raises(TypeError):
        example_observation(**bad_change)


# --- Mirror (data augmentation) --------------------------------------
def test_mirror_flips_left_and_right():
    obs = example_observation(my_x=100, enemy_x=300)
    flipped = obs.mirrored()
    assert flipped.my_x == 700 and flipped.enemy_x == 500
    assert flipped.distance == obs.distance
    assert flipped.enemy_direction == -obs.enemy_direction
    assert flipped.room_behind_me == obs.room_behind_me


def test_mirroring_twice_gives_back_the_original():
    obs = example_observation(my_x=120, enemy_x=640)
    assert obs.mirrored().mirrored() == obs


# --- Noise (data augmentation) ---------------------------------------
def test_jitter_makes_small_changes_only():
    import random
    rng = random.Random(1)
    obs = example_observation(my_x=300, enemy_x=500, my_health=0.5)
    for _ in range(200):
        noisy = obs.jittered(rng, pixels=5, health=0.02)
        assert abs(noisy.my_x - 300) <= 5
        assert abs(noisy.my_health - 0.5) <= 0.02 + 1e-9
        assert noisy.my_last_action == obs.my_last_action


def test_jitter_never_leaves_the_arena_or_breaks_health():
    import random
    rng = random.Random(2)
    edge = example_observation(my_x=0, enemy_x=800, my_health=1.0, enemy_health=0.0)
    for _ in range(200):
        edge.jittered(rng, pixels=50, health=0.5)   # would raise if out of bounds


def test_jitter_rejects_negative_amounts():
    import random
    with pytest.raises(ValueError):
        example_observation().jittered(random.Random(), pixels=-1)
