"""Tests for Phase 6: In-Game Model Deployment, DDA, and Decision Explanations."""

import pytest

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.difficulty import DifficultyWrapper
from backend.ai.observation import Observation, example_observation
from backend.ai.opponent_model import OpponentModel
from backend.learning.policy_agent import PolicyAgent
from backend.learning.trainer_proc import BackgroundTrainingManager


def test_policy_agent_fallback_when_no_model():
    """PolicyAgent falls back gracefully to rule-based agent if no model exists."""
    agent = PolicyAgent(personality="Crimson", model_path="nonexistent_model.pt", player=1)
    assert agent.model is None

    obs = example_observation(my_health=0.8, enemy_health=0.5)
    action, scores = agent.choose_action(obs)

    assert action in ALL_ACTIONS
    assert isinstance(scores, dict)
    assert len(scores) > 0


def test_policy_agent_timing_stage():
    """Decisions are timed and recorded via stage('policy')."""
    agent = PolicyAgent(personality="Steel", player=1)
    obs = example_observation()
    action, _ = agent.choose_action(obs)

    assert agent.last_inference_time_ms >= 0.0
    assert "policy" in agent.stages


def test_dynamic_difficulty_adjustment_adapts_mistakes():
    """DDA adjusts mistake chance based on player win rate without modifying damage."""
    from backend.ai.crimson import CrimsonAgent
    inner = CrimsonAgent(player=2)
    wrapper = DifficultyWrapper(inner, difficulty="HIGH")
    wrapper.adaptive_difficulty = True
    initial_mistake = wrapper.mistake_chance

    # Player losing consecutively -> AI becomes more forgiving (higher mistake chance)
    for _ in range(5):
        wrapper.update_dda(human_won=False)
    assert wrapper.mistake_chance > initial_mistake

    # Player winning consecutively -> AI sharpens (lower mistake chance)
    for _ in range(10):
        wrapper.update_dda(human_won=True)
    assert wrapper.mistake_chance < 0.40


def test_opponent_model_predict_distribution():
    """OpponentModel outputs a valid normalized distribution with temperature scaling."""
    model = OpponentModel()
    obs = example_observation(my_x=200, enemy_x=250)

    # Observe an attack
    model.observe(obs, my_action=Action.IDLE, enemy_action=Action.LIGHT)

    dist = model.predict_distribution(obs, temperature=0.8)
    assert isinstance(dist, dict)
    assert len(dist) == len(ALL_ACTIONS)
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-5)
    assert dist[Action.LIGHT] > 0.0


def test_background_training_manager_non_blocking_polling():
    """Training manager handles start, poll, and state querying without blocking."""
    mgr = BackgroundTrainingManager()
    assert mgr.is_running is False
    assert mgr.progress == 0.0
    # Polling while idle is a safe no-op
    mgr.poll()
    assert mgr.last_status == "Idle"


def _train_tiny_checkpoint(tmp_path, character="Crimson"):
    from backend.learning.ppo import PPOTrainer
    from backend.ai.random_agent import RandomAgent
    trainer = PPOTrainer(personality=character, opponent_agent=RandomAgent(player=2, seed=1),
                         n_envs=1, steps_per_env=16, seed=3, models_dir=str(tmp_path))
    return trainer.train(total_updates=1)["latest_checkpoint"]


def test_difficulty_falls_back_to_checkpoint_and_picks_up_new_models(tmp_path):
    """HIGH/HELL load the newest checkpoint when the registry has no live row,
    and a model saved later is picked up (no stale 'none' cache)."""
    from backend.ai.crimson import CrimsonAgent
    empty_reg = str(tmp_path / "reg.db")
    w = DifficultyWrapper(CrimsonAgent(player=2), difficulty="HELL",
                          models_dir=str(tmp_path), registry_path=empty_reg)
    assert w._policy_agent is None          # nothing trained yet -> FSM only
    action, _ = w.choose_action(example_observation())
    assert action in ALL_ACTIONS

    ckpt = _train_tiny_checkpoint(tmp_path)
    w.reset()                                # next round re-checks the model folder
    assert w._policy_agent is not None
    assert w._learned_model == ckpt
    w2 = DifficultyWrapper(CrimsonAgent(player=2), difficulty="HIGH",
                           models_dir=str(tmp_path), registry_path=empty_reg)
    assert w2._policy_agent is not None
    for _ in range(20):
        action, scores = w2.choose_action(example_observation(my_x=300, enemy_x=360))
        assert action in ALL_ACTIONS


def test_policy_agent_mask_uses_real_state_fields(tmp_path):
    """Thrown / guard-broken fighters only get the actions the training mask allowed."""
    from dataclasses import replace
    ckpt = _train_tiny_checkpoint(tmp_path)
    agent = PolicyAgent("Crimson", model_path=ckpt, greedy=True)
    assert agent.model is not None
    obs = replace(example_observation(), has_engine_detail=True, my_guard_break_stun=20)
    probs, mask = agent.policy_distribution(obs)
    assert mask.sum() == 1 and mask[Action.IDLE.value]
    obs_thrown = replace(example_observation(), has_engine_detail=True, my_is_thrown=True,
                         my_throw_tech_frames=4)
    _, mask_t = agent.policy_distribution(obs_thrown)
    assert set(mask_t.nonzero()[0]) == {Action.IDLE.value, Action.THROW.value}


def test_policy_agent_decides_once_per_macro_step(tmp_path):
    """Like ArenaEnv.step: a discrete attack is pressed on the first frame, then IDLE."""
    ckpt = _train_tiny_checkpoint(tmp_path)
    agent = PolicyAgent("Crimson", model_path=ckpt, greedy=True)
    calls = []
    original = agent._decide

    def spy(obs):
        calls.append(1)
        return original(obs)

    agent._decide = spy
    obs = example_observation()
    for _ in range(5):
        agent.choose_action(obs)
    # 5 frames < ACTION_EXECUTION_FRAMES (6): only one network query
    assert len(calls) == 1


def test_round_end_hook_drives_dda():
    from backend.ai.steel import SteelAgent
    w = DifficultyWrapper(SteelAgent(player=2), difficulty="HELL", adaptive_difficulty=True,
                          use_learned_policy=False)
    start = w._dda_mistake_offset
    for _ in range(4):
        w.on_round_end("p1")       # human (player 1) keeps winning... AI is player 2
    assert w._dda_mistake_offset < start or w._dda_mistake_offset == -0.05
    w2 = DifficultyWrapper(SteelAgent(player=2), difficulty="HELL", adaptive_difficulty=True,
                           use_learned_policy=False)
    for _ in range(4):
        w2.on_round_end("win")     # AI keeps winning -> becomes more forgiving
    assert w2._dda_mistake_offset > 0


def test_mirror_match_sides_have_separate_q_tables():
    from backend.ai.crimson import CrimsonAgent
    a = DifficultyWrapper(CrimsonAgent(player=1), difficulty="LOW")
    b = DifficultyWrapper(CrimsonAgent(player=2), difficulty="LOW")
    assert a.rl_learner is not b.rl_learner


def test_human_like_reaction_time_varies():
    from backend.ai.crimson import CrimsonAgent
    w = DifficultyWrapper(CrimsonAgent(player=1, seed=4), difficulty="MEDIUM")
    samples = {w._sample_delay(15, w.base_profile.reaction_jitter) for _ in range(50)}
    assert len(samples) > 3 and min(samples) >= 1
    assert w.delay == 15     # nominal (mean) delay is still the profile value
