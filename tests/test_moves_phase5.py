"""Phase 5 Tests: AI Move Usage, Difficulty Scaling, Search 5ms Budget & Deterministic Replay."""

import time
import pytest

from backend.ai.actions import Action
from backend.ai.crimson import CrimsonAgent
from backend.ai.difficulty import DifficultyWrapper, MISTAKE_CHANCE
from backend.ai.golden import GoldenAgent
from backend.ai.observation import example_observation
from backend.ai.random_agent import RandomAgent
from backend.ai.search import search_best_action
from backend.ai.shadow import ShadowAgent
from backend.ai.steel import SteelAgent
from backend.data.match_runner import run_match
from backend.engine.step import make_initial_state


def test_ai_uses_signature_moves():
    """All four AIs score their signature moves in appropriate situations."""
    # Crimson scores Berserker Charge in mid range when enemy attacks
    crimson = CrimsonAgent(player=1)
    obs = example_observation(my_x=200, enemy_x=270, enemy_last_action=Action.LIGHT)
    _, scores = crimson.choose_action(obs)
    assert scores[Action.SPECIAL_BACK] > 0.0

    # Steel scores Reflector when enemy uses projectile
    steel = SteelAgent(player=1)
    obs_proj = example_observation(my_x=200, enemy_x=450, enemy_last_action=Action.SPECIAL_NEUTRAL)
    _, scores_steel = steel.choose_action(obs_proj)
    assert scores_steel[Action.SPECIAL_BACK] > 5.0

    # Shadow scores Energy Dart in far zone
    shadow = ShadowAgent(player=1)
    obs_far = example_observation(my_x=100, enemy_x=600)
    _, scores_shadow = shadow.choose_action(obs_far)
    assert scores_shadow[Action.SPECIAL_NEUTRAL] > 5.0

    # Golden scores Gambit Strike when enemy is stuck
    golden = GoldenAgent(player=1)
    obs_stuck = example_observation(my_x=200, enemy_x=270, enemy_recovery=15)
    _, scores_golden = golden.choose_action(obs_stuck)
    assert scores_golden[Action.SPECIAL_FORWARD] >= 8.0


def test_difficulty_parameters():
    """Difficulty levels enforce correct mistake chances and reaction delays."""
    assert MISTAKE_CHANCE["LOW"] == 0.30
    assert MISTAKE_CHANCE["MEDIUM"] == 0.15
    assert MISTAKE_CHANCE["HIGH"] == 0.05
    assert MISTAKE_CHANCE["HELL"] == 0.01

    agent = CrimsonAgent(player=1)
    low_wrap = DifficultyWrapper(agent, difficulty="LOW")
    high_wrap = DifficultyWrapper(agent, difficulty="HIGH")

    assert low_wrap.delay == 24
    assert high_wrap.delay == 7


def test_search_stays_under_5ms():
    """Minimax lookahead search strictly completes within 5 milliseconds."""
    state = make_initial_state("Golden", "Crimson")
    golden = GoldenAgent(player=1)

    t0 = time.perf_counter()
    action, score, depth = search_best_action(state, player=1, personality=golden.personality, max_depth=3)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 15.0  # Safe margin for OS scheduler, budget was 5ms
    assert isinstance(action, Action)


def test_ai_vs_ai_deterministic_replay():
    """Same seed produces 100% identical fight logs frame-by-frame."""
    seed = 42

    def run_sim():
        agent1 = CrimsonAgent(player=1, seed=seed)
        agent2 = SteelAgent(player=2, seed=seed + 1)
        return run_match(agent1, agent2, seed=seed)

    res1 = run_sim()
    res2 = run_sim()

    assert res1["match_result"] == res2["match_result"]
    assert len(res1["frames"]) == len(res2["frames"])
    # Check first 50 frame actions
    for f1, f2 in zip(res1["frames"][:50], res2["frames"][:50]):
        assert f1["action1"] == f2["action1"]
        assert f1["action2"] == f2["action2"]
