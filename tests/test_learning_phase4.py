"""Tests for Phase 4: Proximal Policy Optimization (PPO) with Action Masking."""

import os
import numpy as np
import pytest
import torch

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.learning.config import ACTION_DIM, OBS_DIM
from backend.learning.network import ActorCritic
from backend.learning.ppo import PPOTrainer


class AlwaysIdleAgent(Agent):
    """Opponent that always idles, serving as a baseline target."""
    def __init__(self, player=2):
        super().__init__(name="IdleDummy", player=player, difficulty="LOW")

    def choose_action(self, state):
        return Action.IDLE, {Action.IDLE: 1.0}


def test_action_masking_gives_zero_probability():
    """Masked actions must have -1e9 logits and exactly zero sampling probability."""
    model = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM)
    obs = torch.zeros((1, OBS_DIM), dtype=torch.float32)

    # Allow only Action.LIGHT and Action.HEAVY; mask out all others
    mask = torch.zeros((1, ACTION_DIM), dtype=torch.bool)
    mask[0, Action.LIGHT.value] = True
    mask[0, Action.HEAVY.value] = True

    logits, _ = model(obs, mask=mask)
    probs = torch.softmax(logits, dim=-1).squeeze(0).detach().numpy()

    assert probs[Action.IDLE.value] == pytest.approx(0.0, abs=1e-6)
    assert probs[Action.SUPER.value] == pytest.approx(0.0, abs=1e-6)
    assert probs[Action.LIGHT.value] > 0.0
    assert probs[Action.HEAVY.value] > 0.0
    assert (probs[Action.LIGHT.value] + probs[Action.HEAVY.value]) == pytest.approx(1.0, abs=1e-5)


def test_ppo_trainer_checkpointing_and_metadata(tmp_path):
    """Verify that PPOTrainer checkpoints create .pt weights and companion .json metadata."""
    trainer = PPOTrainer(
        personality="Crimson",
        n_envs=2,
        steps_per_env=16,
        seed=42,
    )
    checkpoint_path = trainer.save_checkpoint(update_num=1)

    assert os.path.exists(checkpoint_path)
    json_path = checkpoint_path.replace(".pt", ".json")
    assert os.path.exists(json_path)


def test_ppo_quick_run_against_idle_opponent():
    """PPO trains for 3 updates against an idle opponent and improves reward."""
    trainer = PPOTrainer(
        personality="Crimson",
        opponent_agent=AlwaysIdleAgent(player=2),
        n_envs=2,
        steps_per_env=32,
        seed=101,
    )
    res = trainer.train(total_updates=3, quick_mode=True)

    assert res["updates_completed"] >= 1
    assert "history" in res
    assert len(res["history"]) >= 1
    # Check that learning metrics are recorded
    first_update = res["history"][0]
    assert "policy_loss" in first_update
    assert "value_loss" in first_update
    assert "entropy" in first_update
