"""Tests for Phase 1: Gymnasium Training Environment & Action Masking."""

import numpy as np
import pytest

from backend.ai.actions import ALL_ACTIONS, Action
from backend.engine.state import FighterState
from backend.learning.config import ACTION_DIM, OBS_DIM
from backend.learning.env import ArenaEnv, get_action_mask


def test_env_reset_shapes_and_types():
    """Verify reset returns float32 observation vector of length 30 and info dict."""
    env = ArenaEnv(fighter_character="Crimson", opponent_character="Steel", seed=42)
    obs, info = env.reset(seed=42)

    assert isinstance(obs, np.ndarray)
    assert obs.shape == (OBS_DIM,)
    assert obs.dtype == np.float32

    assert "action_mask" in info
    assert info["action_mask"].shape == (ACTION_DIM,)
    assert info["action_mask"].dtype == bool
    assert bool(info["action_mask"][Action.IDLE.value]) is True


def test_action_masks_always_contain_at_least_one_legal_action():
    """The mask must never be all False (at least IDLE is always legal)."""
    env = ArenaEnv(fighter_character="Crimson", opponent_character="Steel", seed=10)
    obs, info = env.reset(seed=10)

    for _ in range(50):
        mask = info["action_mask"]
        assert mask.sum() >= 1
        assert bool(mask[Action.IDLE.value]) is True
        legal_actions = np.where(mask)[0]
        action = int(np.random.choice(legal_actions))
        obs, reward, term, trunc, info = env.step(action)
        if term or trunc:
            obs, info = env.reset()


def test_action_masking_enforces_rules():
    """Super move is masked out when meter is 0; aerial moves masked when grounded."""
    f1 = FighterState(character_name="Crimson", in_air=False)
    f1.meter = 0.0
    f2 = FighterState(character_name="Steel", in_air=False)

    mask = get_action_mask(f1, f2, player=1)
    # Super requires 100 meter (or 60 in Fury)
    assert not mask[Action.SUPER.value]
    # Jump punch requires fighter to be in air
    assert not mask[Action.JUMP_PUNCH.value]
    # Ground attacks like Jab are legal
    assert bool(mask[Action.LIGHT.value]) is True

    # When airborne, ground attacks are masked out, aerial attacks legal
    f1_air = FighterState(character_name="Crimson", in_air=True)
    mask_air = get_action_mask(f1_air, f2, player=1)
    assert not mask_air[Action.LIGHT.value]
    assert bool(mask_air[Action.JUMP_PUNCH.value]) is True


def test_deterministic_reproducibility():
    """Identical seeds must produce identical state trajectories."""
    env1 = ArenaEnv(fighter_character="Crimson", opponent_character="Steel", seed=99)
    env2 = ArenaEnv(fighter_character="Crimson", opponent_character="Steel", seed=99)

    obs1, info1 = env1.reset(seed=99)
    obs2, info2 = env2.reset(seed=99)
    np.testing.assert_allclose(obs1, obs2)

    fixed_actions = [Action.FORWARD.value, Action.LIGHT.value, Action.HEAVY.value, Action.BLOCK.value]
    for act in fixed_actions:
        o1, r1, term1, trunc1, _ = env1.step(act)
        o2, r2, term2, trunc2, _ = env2.step(act)
        np.testing.assert_allclose(o1, o2)
        assert r1 == pytest.approx(r2, abs=1e-5)
        assert term1 == term2


def test_thousand_random_steps_run_without_errors():
    """Run 1,000 steps selecting from legal masked actions without crashing."""
    env = ArenaEnv(fighter_character="Shadow", opponent_character="Golden", seed=777)
    obs, info = env.reset(seed=777)

    for _ in range(1000):
        mask = info["action_mask"]
        legal_actions = np.where(mask)[0]
        action = int(env.np_random.choice(legal_actions))
        obs, reward, term, trunc, info = env.step(action)
        assert isinstance(reward, float)
        assert obs.shape == (OBS_DIM,)
        if term or trunc:
            obs, info = env.reset()
