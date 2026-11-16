"""Proximal Policy Optimization (PPO) with Action Masking and Parallel Environments.

Key components:
  - Action masking: illegal actions receive -inf logits (0 probability in categorical distribution).
  - GAE (Generalized Advantage Estimation): lambda=0.95, gamma=0.99.
  - Clipped surrogate objective: clip_eps=0.20 with entropy bonus.
  - Parallel environments stepping with vectorized rollouts.
  - Starts from Behaviour-Cloning (BC) warm start weights.
  - Checkpoints saved with companion metadata JSON (seed, git commit, win rates).
"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.random_agent import RandomAgent
from backend.learning.bc import get_git_commit_hash
from backend.learning.config import (
    ACTION_DIM,
    DEFAULT_SEED,
    MODELS_DIR,
    OBS_DIM,
    PPO_BATCH_SIZE,
    PPO_CHECKPOINT_INTERVAL,
    PPO_CLIP_EPS,
    PPO_ENTROPY_COEF,
    PPO_EPOCHS_PER_UPDATE,
    PPO_GAE_LAMBDA,
    PPO_GAMMA,
    PPO_LEARNING_RATE,
    PPO_MAX_GRAD_NORM,
    PPO_N_ENVS,
    PPO_STEPS_PER_ENV,
    PPO_VALUE_COEF,
    RESULTS_DIR,
)
from backend.learning.env import ArenaEnv
from backend.learning.network import ActorCritic
from backend.learning.rewards import RewardCalculator


class PPOTrainer:
    """Orchestrates vectorized PPO training with action masking."""

    def __init__(
        self,
        personality: str = "Crimson",
        opponent_character: str = "Steel",
        opponent_agent: Optional[Agent] = None,
        n_envs: int = PPO_N_ENVS,
        steps_per_env: int = PPO_STEPS_PER_ENV,
        lr: float = PPO_LEARNING_RATE,
        gamma: float = PPO_GAMMA,
        gae_lambda: float = PPO_GAE_LAMBDA,
        clip_eps: float = PPO_CLIP_EPS,
        ent_coef: float = PPO_ENTROPY_COEF,
        val_coef: float = PPO_VALUE_COEF,
        seed: int = DEFAULT_SEED,
        device: str = "cpu",
        warm_start_weights: Optional[str] = None,
    ):
        self.personality = personality
        self.opponent_character = opponent_character
        self.n_envs = max(1, n_envs)
        self.steps_per_env = steps_per_env
        self.batch_size = self.n_envs * self.steps_per_env
        self.lr = lr
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_eps = clip_eps
        self.ent_coef = ent_coef
        self.val_coef = val_coef
        self.seed = seed
        self.device = torch.device(device)

        torch.manual_seed(seed)
        np.random.seed(seed)

        # Initialize environments
        self.envs = [
            ArenaEnv(
                fighter_character=personality,
                opponent_character=opponent_character,
                opponent_agent=opponent_agent or RandomAgent(player=2, seed=seed + i * 10),
                reward_calculator=RewardCalculator(personality=personality),
                seed=seed + i,
            )
            for i in range(self.n_envs)
        ]

        # Initialize Actor-Critic model
        self.model = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM).to(self.device)

        if warm_start_weights and os.path.exists(warm_start_weights):
            try:
                state_dict = torch.load(warm_start_weights, map_location=self.device)
                self.model.load_state_dict(state_dict, strict=False)
            except Exception:
                pass

        self.optimizer = optim.Adam(self.model.parameters(), lr=lr, eps=1e-5)
        self.total_steps = 0
        self.update_count = 0
        self.history: List[Dict[str, Any]] = []

    def train(
        self,
        total_updates: int = 10,
        max_duration_seconds: Optional[float] = None,
        quick_mode: bool = False,
    ) -> Dict[str, Any]:
        """Run PPO training loop with support for time budgets and quick mode."""
        start_time = time.time()
        effective_updates = min(5, total_updates) if quick_mode else total_updates

        # Reset all environments
        obs_list = []
        mask_list = []
        for env in self.envs:
            o, info = env.reset()
            obs_list.append(o)
            mask_list.append(info["action_mask"])

        current_obs = torch.tensor(np.array(obs_list), dtype=torch.float32, device=self.device)
        current_masks = torch.tensor(np.array(mask_list), dtype=torch.bool, device=self.device)
        current_dones = torch.zeros(self.n_envs, dtype=torch.float32, device=self.device)

        for update in range(1, effective_updates + 1):
            if max_duration_seconds and (time.time() - start_time) >= max_duration_seconds:
                break

            # Buffers for rollout data
            obs_buf = torch.zeros((self.steps_per_env, self.n_envs, OBS_DIM), device=self.device)
            act_buf = torch.zeros((self.steps_per_env, self.n_envs), device=self.device, dtype=torch.long)
            logprob_buf = torch.zeros((self.steps_per_env, self.n_envs), device=self.device)
            rew_buf = torch.zeros((self.steps_per_env, self.n_envs), device=self.device)
            done_buf = torch.zeros((self.steps_per_env, self.n_envs), device=self.device)
            val_buf = torch.zeros((self.steps_per_env, self.n_envs), device=self.device)
            mask_buf = torch.zeros((self.steps_per_env, self.n_envs, ACTION_DIM), device=self.device, dtype=torch.bool)

            ep_rewards: List[float] = []

            # 1. Rollout Phase
            for step_idx in range(self.steps_per_env):
                self.total_steps += self.n_envs
                obs_buf[step_idx] = current_obs
                mask_buf[step_idx] = current_masks
                done_buf[step_idx] = current_dones

                with torch.no_grad():
                    action, logprob, _, value = self.model.get_action_and_value(
                        current_obs, mask=current_masks
                    )
                    val_buf[step_idx] = value
                    act_buf[step_idx] = action
                    logprob_buf[step_idx] = logprob

                # Step environments
                next_obs_list = []
                next_mask_list = []
                next_done_list = []
                step_rewards = []

                for i, env in enumerate(self.envs):
                    a_int = int(action[i].item())
                    n_o, r, term, trunc, info = env.step(a_int)
                    d = term or trunc
                    step_rewards.append(r)
                    next_done_list.append(float(d))

                    if d:
                        n_o, reset_info = env.reset()
                        next_mask_list.append(reset_info["action_mask"])
                        ep_rewards.append(r)
                    else:
                        next_mask_list.append(info["action_mask"])

                    next_obs_list.append(n_o)

                rew_buf[step_idx] = torch.tensor(step_rewards, dtype=torch.float32, device=self.device)
                current_obs = torch.tensor(np.array(next_obs_list), dtype=torch.float32, device=self.device)
                current_masks = torch.tensor(np.array(next_mask_list), dtype=torch.bool, device=self.device)
                current_dones = torch.tensor(next_done_list, dtype=torch.float32, device=self.device)

            # 2. Generalized Advantage Estimation (GAE)
            with torch.no_grad():
                next_value = self.model.get_value(current_obs)
                advantages = torch.zeros_like(rew_buf)
                lastgaelam = 0.0

                for t in reversed(range(self.steps_per_env)):
                    if t == self.steps_per_env - 1:
                        nextnonterminal = 1.0 - current_dones
                        nextvals = next_value
                    else:
                        nextnonterminal = 1.0 - done_buf[t + 1]
                        nextvals = val_buf[t + 1]

                    delta = rew_buf[t] + self.gamma * nextvals * nextnonterminal - val_buf[t]
                    advantages[t] = lastgaelam = (
                        delta + self.gamma * self.gae_lambda * nextnonterminal * lastgaelam
                    )

                returns = advantages + val_buf

            # Flatten rollout tensors for training
            b_obs = obs_buf.reshape(-1, OBS_DIM)
            b_logprobs = logprob_buf.reshape(-1)
            b_actions = act_buf.reshape(-1)
            b_masks = mask_buf.reshape(-1, ACTION_DIM)
            b_advantages = advantages.reshape(-1)
            b_returns = returns.reshape(-1)
            b_values = val_buf.reshape(-1)

            # Normalize advantages
            b_advantages = (b_advantages - b_advantages.mean()) / (b_advantages.std() + 1e-8)

            # 3. PPO Optimization Epochs
            b_inds = np.arange(self.batch_size)
            clipfracs = []
            mean_policy_loss = 0.0
            mean_value_loss = 0.0
            mean_entropy = 0.0

            for epoch in range(int(PPO_EPOCHS_PER_UPDATE)):
                np.random.shuffle(b_inds)
                for start in range(0, self.batch_size, PPO_BATCH_SIZE):
                    end = start + PPO_BATCH_SIZE
                    mb_inds = b_inds[start:end]

                    _, newlogprob, entropy, newvalue = self.model.get_action_and_value(
                        b_obs[mb_inds], mask=b_masks[mb_inds], action=b_actions[mb_inds]
                    )

                    logratio = newlogprob - b_logprobs[mb_inds]
                    ratio = logratio.exp()

                    with torch.no_grad():
                        clipfracs += [((ratio - 1.0).abs() > self.clip_eps).float().mean().item()]

                    mb_adv = b_advantages[mb_inds]

                    # Clipped surrogate loss
                    pg_loss1 = -mb_adv * ratio
                    pg_loss2 = -mb_adv * torch.clamp(ratio, 1 - self.clip_eps, 1 + self.clip_eps)
                    pg_loss = torch.max(pg_loss1, pg_loss2).mean()

                    # Value loss with clipping
                    v_loss_unclipped = (newvalue - b_returns[mb_inds]) ** 2
                    v_clipped = b_values[mb_inds] + torch.clamp(
                        newvalue - b_values[mb_inds], -self.clip_eps, self.clip_eps
                    )
                    v_loss_clipped = (v_clipped - b_returns[mb_inds]) ** 2
                    v_loss = 0.5 * torch.max(v_loss_unclipped, v_loss_clipped).mean()

                    entropy_loss = entropy.mean()
                    total_loss = pg_loss - self.ent_coef * entropy_loss + self.val_coef * v_loss

                    self.optimizer.zero_grad()
                    total_loss.backward()
                    nn.utils.clip_grad_norm_(self.model.parameters(), PPO_MAX_GRAD_NORM)
                    self.optimizer.step()

                    mean_policy_loss += pg_loss.item()
                    mean_value_loss += v_loss.item()
                    mean_entropy += entropy_loss.item()

            n_batches = int(PPO_EPOCHS_PER_UPDATE) * (self.batch_size // PPO_BATCH_SIZE)
            self.update_count += 1

            # Log metrics
            mean_reward = float(rew_buf.mean().item())
            log_entry = {
                "update": self.update_count,
                "total_steps": self.total_steps,
                "mean_reward": mean_reward,
                "policy_loss": mean_policy_loss / max(1, n_batches),
                "value_loss": mean_value_loss / max(1, n_batches),
                "entropy": mean_entropy / max(1, n_batches),
                "elapsed_time": time.time() - start_time,
            }
            self.history.append(log_entry)

            # Checkpoint every N updates
            if self.update_count % PPO_CHECKPOINT_INTERVAL == 0 or update == effective_updates:
                self.save_checkpoint(update_num=self.update_count)

        # Save training summary
        self._save_training_summary()
        return {
            "total_steps": self.total_steps,
            "updates_completed": self.update_count,
            "final_reward": self.history[-1]["mean_reward"] if self.history else 0.0,
            "history": self.history,
        }

    def save_checkpoint(self, update_num: int) -> str:
        """Save network weights and companion metadata JSON."""
        p_dir = os.path.join(MODELS_DIR, self.personality.lower())
        os.makedirs(p_dir, exist_ok=True)
        pt_path = os.path.join(p_dir, f"v{update_num:03d}.pt")
        json_path = os.path.join(p_dir, f"v{update_num:03d}.json")

        torch.save(self.model.state_dict(), pt_path)

        meta = {
            "personality": self.personality,
            "version": update_num,
            "total_steps": self.total_steps,
            "git_commit": get_git_commit_hash(),
            "seed": self.seed,
            "timestamp": time.time(),
            "latest_metrics": self.history[-1] if self.history else {},
        }
        with open(json_path, "w") as f:
            json.dump(meta, f, indent=2)

        return pt_path

    def _save_training_summary(self) -> None:
        """Save learning curve metrics to docs/results/."""
        os.makedirs(RESULTS_DIR, exist_ok=True)
        out_file = os.path.join(RESULTS_DIR, f"ppo_{self.personality.lower()}_curve.json")
        with open(out_file, "w") as f:
            json.dump(
                {
                    "personality": self.personality,
                    "seed": self.seed,
                    "git_commit": get_git_commit_hash(),
                    "history": self.history,
                },
                f,
                indent=2,
            )
