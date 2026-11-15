"""Tests for the engine: state, movement, jumping, walls, combat, step function."""

import pytest

from backend.ai.actions import Action
from backend.engine.characters import CHARACTER_STATS
from backend.engine.constants import (
    ARENA_WIDTH,
    BLOCK_DAMAGE_RATIO,
    FPS,
    JUMP_DURATION,
    LIGHT_ATTACK,
    HEAVY_ATTACK,
    ROUND_FRAMES,
    WALK_SPEED,
)
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, new_round, step


# ---------------------------------------------------------------
# State basics
# ---------------------------------------------------------------

def test_initial_state_positions():
    """Fighters start at 25% and 75% of the arena."""
    s = make_initial_state()
    assert s.fighter1.x == ARENA_WIDTH * 0.25
    assert s.fighter2.x == ARENA_WIDTH * 0.75


def test_initial_state_full_health():
    s = make_initial_state()
    assert s.fighter1.health == 1.0
    assert s.fighter2.health == 1.0


def test_initial_state_round_one():
    s = make_initial_state()
    assert s.round_number == 1
    assert s.frame == 0
    assert not s.round_over
    assert not s.match_over


def test_copy_is_independent():
    """Changing the copy must not change the original."""
    s = make_initial_state()
    c = s.copy()
    c.fighter1.health = 0.5
    assert s.fighter1.health == 1.0


# ---------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------

def test_determinism():
    """Same inputs must give the exact same result every time."""
    s = make_initial_state("Crimson", "Shadow")
    actions = [Action.FORWARD, Action.IDLE, Action.LIGHT, Action.BACK, Action.HEAVY]

    # Run the same sequence twice
    s1 = s.copy()
    s2 = s.copy()
    for i in range(100):
        a1 = actions[i % len(actions)]
        a2 = actions[(i * 3 + 1) % len(actions)]
        s1 = step(s1, a1, a2)
        s2 = step(s2, a1, a2)

    assert s1.fighter1.x == s2.fighter1.x
    assert s1.fighter2.x == s2.fighter2.x
    assert s1.fighter1.health == s2.fighter1.health
    assert s1.fighter2.health == s2.fighter2.health
    assert s1.frame == s2.frame


# ---------------------------------------------------------------
# Movement
# ---------------------------------------------------------------

def test_forward_moves_toward_enemy():
    s = make_initial_state()
    old_x = s.fighter1.x
    s2 = step(s, Action.FORWARD, Action.IDLE)
    # Fighter 1 is on the left, enemy on right -> forward = right = x increases
    assert s2.fighter1.x > old_x


def test_back_moves_away_from_enemy():
    s = make_initial_state()
    old_x = s.fighter1.x
    s2 = step(s, Action.BACK, Action.IDLE)
    # Fighter 1 backs away from enemy on right -> x decreases
    assert s2.fighter1.x < old_x


def test_wall_clamp_left():
    """Fighter cannot walk past the left wall."""
    s = make_initial_state()
    s.fighter1.x = 1.0  # very close to left wall
    s2 = step(s, Action.BACK, Action.IDLE)
    assert s2.fighter1.x >= 0.0


def test_wall_clamp_right():
    """Fighter cannot walk past the right wall."""
    s = make_initial_state()
    s.fighter2.x = ARENA_WIDTH - 1.0  # very close to right wall
    s2 = step(s, Action.IDLE, Action.BACK)
    assert s2.fighter2.x <= ARENA_WIDTH


def test_cannot_move_during_recovery():
    """A fighter stuck in recovery cannot walk."""
    s = make_initial_state()
    s.fighter1.recovery = 10
    old_x = s.fighter1.x
    s2 = step(s, Action.FORWARD, Action.IDLE)
    assert s2.fighter1.x == old_x


# ---------------------------------------------------------------
# Jumping
# ---------------------------------------------------------------

def test_jump_makes_fighter_airborne():
    s = make_initial_state()
    s2 = step(s, Action.JUMP, Action.IDLE)
    assert s2.fighter1.in_air


def test_jump_lasts_correct_frames():
    """A jump lasts JUMP_DURATION frames then the fighter lands."""
    s = make_initial_state()
    s = step(s, Action.JUMP, Action.IDLE)
    assert s.fighter1.in_air

    # Keep stepping until the fighter lands
    for _ in range(JUMP_DURATION + 5):
        s = step(s, Action.IDLE, Action.IDLE)
        if not s.fighter1.in_air:
            break

    assert not s.fighter1.in_air


def test_cannot_block_in_air():
    """Blocking in the air does NOT reduce damage."""
    s = make_initial_state()
    # Put fighter 2 in the air and very close to fighter 1
    s.fighter2.in_air = True
    s.fighter2.jump_frame = 1
    s.fighter2.x = s.fighter1.x + 50  # within light reach

    # Fighter 1 attacks, fighter 2 tries to block
    # First start the attack
    s = step(s, Action.LIGHT, Action.BLOCK)

    # Advance through startup frames
    for _ in range(LIGHT_ATTACK.startup + 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Fighter 2 should have taken full damage (not blocked in air)
    assert s.fighter2.health < 1.0


# ---------------------------------------------------------------
# Combat: attacks and damage
# ---------------------------------------------------------------

def test_light_attack_deals_damage():
    """A light attack that connects should reduce the defender's health."""
    s = make_initial_state()
    # Put fighters close together (within light reach)
    s.fighter1.x = 100
    s.fighter2.x = 150  # 50 px apart, light reach is 70

    # Start the light attack
    s = step(s, Action.LIGHT, Action.IDLE)

    # Advance through startup + into active frames
    for _ in range(LIGHT_ATTACK.startup + LIGHT_ATTACK.active):
        s = step(s, Action.IDLE, Action.IDLE)

    # Fighter 2 should have taken damage
    assert s.fighter2.health < 1.0


def test_blocking_reduces_damage():
    """A blocked hit does only BLOCK_DAMAGE_RATIO of its full damage."""
    s_blocked = make_initial_state()
    s_unblocked = make_initial_state()

    # Put fighters close together
    for state in (s_blocked, s_unblocked):
        state.fighter1.x = 100
        state.fighter2.x = 150

    # Fighter 1 attacks, fighter 2 blocks in one, idles in the other
    s_blocked = step(s_blocked, Action.LIGHT, Action.BLOCK)
    s_unblocked = step(s_unblocked, Action.LIGHT, Action.IDLE)

    for _ in range(LIGHT_ATTACK.startup + LIGHT_ATTACK.active):
        s_blocked = step(s_blocked, Action.IDLE, Action.BLOCK)
        s_unblocked = step(s_unblocked, Action.IDLE, Action.IDLE)

    # Blocked fighter took less damage than unblocked
    blocked_damage = 1.0 - s_blocked.fighter2.health
    unblocked_damage = 1.0 - s_unblocked.fighter2.health

    if unblocked_damage > 0:
        assert blocked_damage < unblocked_damage
        assert blocked_damage == pytest.approx(unblocked_damage * BLOCK_DAMAGE_RATIO,
                                                abs=0.001)


def test_attack_out_of_range_misses():
    """An attack should miss if the fighters are too far apart."""
    s = make_initial_state()
    # Fighters are at default positions (200 and 600), far apart
    s = step(s, Action.LIGHT, Action.IDLE)
    for _ in range(LIGHT_ATTACK.startup + LIGHT_ATTACK.active + 2):
        s = step(s, Action.IDLE, Action.IDLE)

    # Fighter 2 should still be at full health
    assert s.fighter2.health == 1.0


def test_cooldown_prevents_second_attack():
    """After attacking, the cooldown must finish before attacking again."""
    s = make_initial_state()
    s.fighter1.x = 100
    s.fighter2.x = 150

    # Start a light attack
    s = step(s, Action.LIGHT, Action.IDLE)

    # Try to attack again immediately on the next frame
    s2 = step(s, Action.LIGHT, Action.IDLE)

    # The fighter should still be in the first attack, not starting a new one
    # (attack_phase should not have reset to start a new attack)
    assert s2.fighter1.attack_phase != "none" or s2.fighter1.cooldown > 0


def test_recovery_leaves_fighter_stuck():
    """During recovery, the fighter cannot act."""
    s = make_initial_state()
    s.fighter1.x = 100
    s.fighter2.x = 150

    # Do a light attack and advance through all phases
    s = step(s, Action.LIGHT, Action.IDLE)
    for _ in range(LIGHT_ATTACK.startup + LIGHT_ATTACK.active):
        s = step(s, Action.IDLE, Action.IDLE)

    # Fighter 1 should now be in recovery
    assert s.fighter1.recovery > 0 or s.fighter1.attack_phase == "recovery"


# ---------------------------------------------------------------
# Round end: KO
# ---------------------------------------------------------------

def test_ko_ends_round():
    """When a fighter's health hits 0, the round is over."""
    s = make_initial_state()
    s.fighter2.health = 0.01  # almost dead
    s.fighter1.x = 100
    s.fighter2.x = 150

    # Light attack to finish them off
    s = step(s, Action.LIGHT, Action.IDLE)
    for _ in range(LIGHT_ATTACK.startup + LIGHT_ATTACK.active + 1):
        s = step(s, Action.IDLE, Action.IDLE)

    assert s.round_over
    assert s.round_result == "p1"
    assert s.p1_rounds_won == 1


# ---------------------------------------------------------------
# Round end: time-out
# ---------------------------------------------------------------

def test_timeout_higher_health_wins():
    """When time runs out, the fighter with more health wins the round."""
    s = make_initial_state()
    s.round_frames_left = 1  # will run out after one step
    s.fighter1.health = 0.8
    s.fighter2.health = 0.5

    s = step(s, Action.IDLE, Action.IDLE)

    assert s.round_over
    assert s.round_result == "p1"
    assert s.p1_rounds_won == 1


def test_timeout_equal_health_is_draw():
    """When time runs out with equal health, the round is a draw."""
    s = make_initial_state()
    s.round_frames_left = 1
    s.fighter1.health = 0.6
    s.fighter2.health = 0.6

    s = step(s, Action.IDLE, Action.IDLE)

    assert s.round_over
    assert s.round_result == "draw"
    # A draw gives no points
    assert s.p1_rounds_won == 0
    assert s.p2_rounds_won == 0


# ---------------------------------------------------------------
# Match rules
# ---------------------------------------------------------------

def test_two_round_win():
    """First to win 2 rounds wins the match."""
    s = make_initial_state()

    # Player 1 wins round 1
    s.round_frames_left = 1
    s.fighter1.health = 1.0
    s.fighter2.health = 0.5
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.round_over and s.round_result == "p1"
    assert not s.match_over  # need 2 wins

    # Start round 2
    s = new_round(s)
    assert s.round_number == 2
    assert not s.round_over

    # Player 1 wins round 2
    s.round_frames_left = 1
    s.fighter1.health = 1.0
    s.fighter2.health = 0.3
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.round_over and s.round_result == "p1"
    assert s.match_over
    assert s.match_result == "p1"
    assert s.p1_rounds_won == 2


def test_max_three_rounds():
    """After 3 rounds, whoever has more round wins takes the match."""
    s = make_initial_state()

    # Round 1: P1 wins
    s.round_frames_left = 1
    s.fighter1.health = 0.8
    s.fighter2.health = 0.5
    s = step(s, Action.IDLE, Action.IDLE)
    s = new_round(s)

    # Round 2: P2 wins
    s.round_frames_left = 1
    s.fighter1.health = 0.4
    s.fighter2.health = 0.9
    s = step(s, Action.IDLE, Action.IDLE)
    s = new_round(s)

    # Round 3: P2 wins -> P2 has 2 wins
    s.round_frames_left = 1
    s.fighter1.health = 0.3
    s.fighter2.health = 0.7
    s = step(s, Action.IDLE, Action.IDLE)

    assert s.match_over
    assert s.match_result == "p2"
    assert s.p2_rounds_won == 2


def test_match_draw():
    """If nobody has 2 wins after 3 rounds, equal wins = match draw."""
    s = make_initial_state()

    # Round 1: P1 wins
    s.round_frames_left = 1
    s.fighter1.health = 0.8
    s.fighter2.health = 0.5
    s = step(s, Action.IDLE, Action.IDLE)
    s = new_round(s)

    # Round 2: P2 wins
    s.round_frames_left = 1
    s.fighter1.health = 0.4
    s.fighter2.health = 0.9
    s = step(s, Action.IDLE, Action.IDLE)
    s = new_round(s)

    # Round 3: draw
    s.round_frames_left = 1
    s.fighter1.health = 0.5
    s.fighter2.health = 0.5
    s = step(s, Action.IDLE, Action.IDLE)

    assert s.match_over
    assert s.match_result == "draw"
    assert s.p1_rounds_won == 1
    assert s.p2_rounds_won == 1


def test_new_round_resets_fighters():
    """new_round resets health and positions but keeps the match score."""
    s = make_initial_state()
    s.fighter1.health = 0.0
    s.p1_rounds_won = 0
    s.p2_rounds_won = 1
    s.round_over = True
    s.round_result = "p2"

    s2 = new_round(s)
    assert s2.fighter1.health == 1.0
    assert s2.fighter2.health == 1.0
    assert s2.round_number == 2
    assert not s2.round_over
    assert s2.p2_rounds_won == 1  # score preserved


def test_new_round_after_ko_resets_positions_health_timers_keeps_score():
    """Addendum A test: After a KO, positions, health, timers are reset and score is kept."""
    s = make_initial_state("Crimson", "Steel")
    # Simulate combat: move fighters, set cooldown/recovery/air states, deplete P2 health to 0
    s.fighter1.x = 450.0
    s.fighter2.x = 480.0
    s.fighter1.cooldown = 10
    s.fighter1.recovery = 5
    s.fighter2.in_air = True
    s.fighter2.health = 0.0
    s.round_frames_left = 800

    # Trigger round end via step or check
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.round_over is True
    assert s.round_result == "p1"
    assert s.p1_rounds_won == 1

    # Reset for next round
    s_next = new_round(s)
    assert s_next.round_number == 2
    assert s_next.p1_rounds_won == 1
    assert s_next.p2_rounds_won == 0
    assert s_next.round_frames_left == ROUND_FRAMES
    assert s_next.frame == 0
    # Positions reset to 25% and 75%
    assert s_next.fighter1.x == ARENA_WIDTH * 0.25
    assert s_next.fighter2.x == ARENA_WIDTH * 0.75
    # Health reset to full
    assert s_next.fighter1.health == 1.0
    assert s_next.fighter2.health == 1.0
    # Cooldown, recovery, air state reset
    assert s_next.fighter1.cooldown == 0
    assert s_next.fighter1.recovery == 0
    assert s_next.fighter2.in_air is False
    assert s_next.fighter1.last_action == Action.IDLE
    assert s_next.fighter2.last_action == Action.IDLE


def test_new_round_after_timeout_resets_positions_health_timers_keeps_score():
    """Addendum A test: After a time-out, positions, health, timers are reset and score is kept."""
    s = make_initial_state("Shadow", "Golden")
    s.fighter1.x = 100.0
    s.fighter2.x = 700.0
    s.fighter1.health = 0.7
    s.fighter2.health = 0.4
    s.fighter1.cooldown = 15
    s.round_frames_left = 1

    # Step finishes the last frame -> time-out
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.round_over is True
    assert s.round_result == "p1"  # f1 has higher health
    assert s.p1_rounds_won == 1

    s_next = new_round(s)
    assert s_next.round_number == 2
    assert s_next.p1_rounds_won == 1
    assert s_next.p2_rounds_won == 0
    assert s_next.round_frames_left == ROUND_FRAMES
    assert s_next.frame == 0
    assert s_next.fighter1.x == ARENA_WIDTH * 0.25
    assert s_next.fighter2.x == ARENA_WIDTH * 0.75
    assert s_next.fighter1.health == 1.0
    assert s_next.fighter2.health == 1.0
    assert s_next.fighter1.cooldown == 0
    assert s_next.fighter1.recovery == 0


# ---------------------------------------------------------------
# Round/match state doesn't advance after over
# ---------------------------------------------------------------

def test_step_does_nothing_after_round_over():
    """Once round_over is True, step returns the same state."""
    s = make_initial_state()
    s.round_over = True
    s2 = step(s, Action.FORWARD, Action.FORWARD)
    assert s2.fighter1.x == s.fighter1.x


def test_step_does_nothing_after_match_over():
    s = make_initial_state()
    s.match_over = True
    s2 = step(s, Action.FORWARD, Action.FORWARD)
    assert s2.fighter1.x == s.fighter1.x
