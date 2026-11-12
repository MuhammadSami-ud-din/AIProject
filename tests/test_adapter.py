"""Tests for the adapter: observation_for(state, player) -> Observation."""

import pytest

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.engine.characters import CHARACTER_STATS, light_attack_for
from backend.engine.constants import ARENA_WIDTH, FPS, ROUND_FRAMES, ROUND_SECONDS
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state


# ---------------------------------------------------------------
# Basic adapter correctness
# ---------------------------------------------------------------

def test_player_1_sees_fighter_1_as_me():
    s = make_initial_state("Crimson", "Shadow")
    obs = observation_for(s, 1)
    assert obs.my_x == s.fighter1.x
    assert obs.enemy_x == s.fighter2.x


def test_player_2_sees_fighter_2_as_me():
    s = make_initial_state("Crimson", "Shadow")
    obs = observation_for(s, 2)
    assert obs.my_x == s.fighter2.x
    assert obs.enemy_x == s.fighter1.x


def test_health_mapped_correctly():
    s = make_initial_state()
    s.fighter1.health = 0.7
    s.fighter2.health = 0.4

    obs1 = observation_for(s, 1)
    assert obs1.my_health == 0.7
    assert obs1.enemy_health == 0.4

    obs2 = observation_for(s, 2)
    assert obs2.my_health == 0.4
    assert obs2.enemy_health == 0.7


def test_cooldowns_mapped():
    s = make_initial_state()
    s.fighter1.cooldown = 5
    s.fighter2.recovery = 10

    obs1 = observation_for(s, 1)
    assert obs1.my_cooldown == 5
    assert obs1.enemy_recovery == 10

    obs2 = observation_for(s, 2)
    assert obs2.enemy_cooldown == 5
    assert obs2.my_recovery == 10


def test_in_air_mapped():
    s = make_initial_state()
    s.fighter1.in_air = True

    obs1 = observation_for(s, 1)
    assert obs1.my_in_air is True
    assert obs1.enemy_in_air is False

    obs2 = observation_for(s, 2)
    assert obs2.enemy_in_air is True
    assert obs2.my_in_air is False


def test_last_actions_mapped():
    s = make_initial_state()
    s.fighter1.last_action = Action.LIGHT
    s.fighter2.last_action = Action.BLOCK

    obs1 = observation_for(s, 1)
    assert obs1.my_last_action == Action.LIGHT
    assert obs1.enemy_last_action == Action.BLOCK

    obs2 = observation_for(s, 2)
    assert obs2.my_last_action == Action.BLOCK
    assert obs2.enemy_last_action == Action.LIGHT


def test_rounds_won_mapped():
    s = make_initial_state()
    s.p1_rounds_won = 1
    s.p2_rounds_won = 0

    obs1 = observation_for(s, 1)
    assert obs1.my_rounds_won == 1
    assert obs1.enemy_rounds_won == 0

    obs2 = observation_for(s, 2)
    assert obs2.my_rounds_won == 0
    assert obs2.enemy_rounds_won == 1


def test_time_left_in_seconds():
    """The adapter converts frames to seconds for time_left."""
    s = make_initial_state()
    s.round_frames_left = FPS * 30  # 30 seconds left

    obs = observation_for(s, 1)
    assert obs.time_left == pytest.approx(30.0)


def test_reach_uses_light_attack():
    """The reach in the observation is the light attack reach for that character."""
    s = make_initial_state("Crimson", "Shadow")
    obs = observation_for(s, 1)

    crimson_reach = light_attack_for(CHARACTER_STATS["Crimson"]).reach
    shadow_reach = light_attack_for(CHARACTER_STATS["Shadow"]).reach

    assert obs.my_reach == pytest.approx(crimson_reach)
    assert obs.enemy_reach == pytest.approx(shadow_reach)


def test_arena_bounds():
    obs = observation_for(make_initial_state(), 1)
    assert obs.arena_left == 0
    assert obs.arena_right == ARENA_WIDTH


def test_frame_and_round_mapped():
    s = make_initial_state()
    s.frame = 42
    s.round_number = 2

    obs = observation_for(s, 1)
    assert obs.frame == 42
    assert obs.round_number == 2


# ---------------------------------------------------------------
# Bad input
# ---------------------------------------------------------------

def test_bad_player_rejected():
    s = make_initial_state()
    with pytest.raises(ValueError):
        observation_for(s, 3)


# ---------------------------------------------------------------
# Symmetry: player 1's view is the swap of player 2's view
# ---------------------------------------------------------------

def test_observations_are_each_others_swap():
    """Player 1's observation swapped should match player 2's observation."""
    s = make_initial_state("Crimson", "Shadow")
    s.fighter1.health = 0.6
    s.fighter2.health = 0.9
    s.fighter1.cooldown = 3
    s.fighter2.recovery = 7
    s.p1_rounds_won = 1
    s.frame = 100

    obs1 = observation_for(s, 1)
    obs2 = observation_for(s, 2)
    obs1_swapped = obs1.swapped()

    assert obs1_swapped.my_x == obs2.my_x
    assert obs1_swapped.enemy_x == obs2.enemy_x
    assert obs1_swapped.my_health == obs2.my_health
    assert obs1_swapped.enemy_health == obs2.enemy_health
    assert obs1_swapped.my_cooldown == obs2.my_cooldown
    assert obs1_swapped.enemy_cooldown == obs2.enemy_cooldown
    assert obs1_swapped.my_rounds_won == obs2.my_rounds_won
    assert obs1_swapped.enemy_rounds_won == obs2.enemy_rounds_won
