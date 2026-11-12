"""Tests for explanation and commentary."""

from backend.ai.actions import Action
from backend.ai.explain import commentary, explain_action
from backend.ai.observation import example_observation
from backend.ai.personalities import CRIMSON, SHADOW, STEEL


def test_explain_light_attack_in_range():
    obs = example_observation(my_x=300, enemy_x=340)  # in range
    text = explain_action(Action.LIGHT, obs, personality=CRIMSON)
    assert "Crimson" in text
    assert "range" in text.lower() or "attack" in text.lower()


def test_explain_light_punish():
    obs = example_observation(enemy_recovery=5)
    text = explain_action(Action.LIGHT, obs, personality=STEEL)
    assert "stuck" in text.lower() or "punish" in text.lower() or "attack" in text.lower()


def test_explain_block():
    obs = example_observation(enemy_last_action=Action.HEAVY)
    text = explain_action(Action.BLOCK, obs, personality=STEEL)
    assert "block" in text.lower() or "guard" in text.lower()


def test_explain_forward_far():
    obs = example_observation(my_x=100, enemy_x=700)
    text = explain_action(Action.FORWARD, obs, personality=CRIMSON)
    assert "far" in text.lower() or "forward" in text.lower()


def test_explain_jump_cornered():
    obs = example_observation(my_x=10, enemy_x=200)
    text = explain_action(Action.JUMP, obs, personality=SHADOW)
    assert "corner" in text.lower() or "jump" in text.lower()


def test_commentary_low_health():
    obs = example_observation(my_health=0.15)
    text = commentary(obs, personality=CRIMSON)
    assert "critical" in text.lower() or "low" in text.lower()


def test_commentary_cornered():
    obs = example_observation(my_x=10, enemy_x=200)
    text = commentary(obs, personality=SHADOW)
    assert "cornered" in text.lower()


def test_commentary_time_pressure():
    obs = example_observation(time_left=5, my_health=0.8, enemy_health=0.5)
    text = commentary(obs, personality=CRIMSON)
    assert "time" in text.lower()


def test_commentary_normal():
    obs = example_observation()
    text = commentary(obs, personality=CRIMSON)
    assert len(text) > 0
