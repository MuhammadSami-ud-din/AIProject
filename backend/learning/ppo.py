"""Proximal Policy Optimization (PPO) with action masking and league opponents.

Key components:
  - Action masking: illegal actions receive -1e9 logits (0 probability).
  - GAE (lambda=0.95, gamma=0.99). Time-limit truncation is NOT treated as a
    terminal state: the value of the final observation is bootstrapped.
  - Clipped surrogate objective (clip_eps=0.20) with entropy bonus. The value
    loss is plain MSE on returns (no value clipping: a 0.2 clip on unnormalised
    returns of magnitude ~10 effectively froze the critic).
  - Opponents: by default sampled per episode from the self-play league
    (curriculum tiers, prioritized sampling, Elo updated after every episode).
    Passing ``opponent_agent`` pins a fixed opponent (tests / ablations).
  - Warm start from Behaviour Cloning weights (actor AND critic).
  - Checkpoints get unique, increasing version numbers (never overwritten) in
    ``models_dir/<character>/`` with companion metadata JSON.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from backend.ai.base_agent import Agent
from backend.learning.bc import get_git_commit_hash
from backend.learning.checkpoints import (
    character_dir,
    find_latest_checkpoint,
    load_compatible_state_dict,
    next_version,
    save_checkpoint,
)
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

logger = logging.getLogger(__name__)


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
        models_dir: Optional[str] = None,
        results_dir: Optional[str] = None,
        league: Any = None,
        use_league: Optional[bool] = None,
        use_personality_bonus: bool = True,
        registry_path: Optional[str] = None,
        checkpoint_interval: int = PPO_CHECKPOINT_INTERVAL,
    ):
        self.personality = personality.capitalize()
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
        self.models_dir = models_dir or MODELS_DIR
        self.results_dir = results_dir  # None -> don't write a learning curve
        self.checkpoint_interval = max(1, checkpoint_interval)
        self.rng = np.random.default_rng(seed)

        torch.manual_seed(seed)
        np.random.seed(seed)

        # Opponents: a fixed agent if given, otherwise the self-play league.
        if use_league is None:
            use_league = opponent_agent is None
        self.league = None
        if use_league:
            if league is None:
                from backend.learning.league import LeagueManager

                league = LeagueManager(self.personality, registry_path=registry_path, seed=seed)
            self.league = league
        self._fixed_opponent = opponent_agent
        self._env_opponent_names: List[str] = ["fixed"] * self.n_envs

        self.envs = []
        for i in range(self.n_envs):
            if self.league is not None:
                opp = self.league.sample_opponent(self.rng)
                agent, char = opp.make_agent(), opp.character
                self._env_opponent_names[i] = opp.name
            else:
                from backend.ai.random_agent import RandomAgent

                agent = opponent_agent or RandomAgent(player=2, seed=seed + i * 10)
                char = opponent_character
            self.envs.append(
                ArenaEnv(
                    fighter_character=self.personality,
                    opponent_character=char,
                    opponent_agent=agent,
                    reward_calculator=RewardCalculator(self.personality, use_personality_bonus),
                    seed=seed + i,
                )
            )

        self.model = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM).to(self.device)
        self.warm_started_from: Optional[str] = None
        if warm_start_weights:
            self.load_weights(warm_start_weights)

        self.optimizer = optim.Adam(self.model.parameters(), lr=lr, eps=1e-5)
        self.total_steps = 0
        self.update_count = 0
        self.history: List[Dict[str, Any]] = []
        self.episode_returns: List[float] = []
        self.episode_wins: List[float] = []
        self.saved_checkpoints: List[str] = []
        self._episode_seed = seed * 1000

    def load_weights(self, path: str) -> bool:
        """Load compatible weights (BC warm start or a previous checkpoint)."""
        if not path or not os.path.exists(path):
            logger.warning("warm start weights %s not found; starting from scratch", path)
            return False
        state = load_compatible_state_dict(path)
        if state is None:
            logger.warning("warm start weights %s incompatible; starting from scratch", path)
            return False
        self.model.load_state_dict(state, strict=True)
        self.warm_started_from = path
        return True

    # ------------------------------------------------------------------
    def _reset_env(self, i: int):
        """Reset env i, sampling a fresh league opponent for the new episode."""
        env = self.envs[i]
        if self.league is not None:
            opp = self.league.sample_opponent(self.rng)
            env.set_opponent(opp.make_agent(), opp.character)
            self._env_opponent_names[i] = opp.name
        self._episode_seed += 1
        return env.reset(seed=self._episode_seed)

    def train(
        self,
        total_updates: int = 10,
        max_duration_seconds: Optional[float] = None,
        quick_mode: bool = False,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Run ``total_updates`` PPO updates in ONE call (envs persist across updates).

        quick_mode caps the run at 5 updates. ``progress_callback(entry)`` is
        called after every update (used by the background trainer).
        """
        start_time = time.time()
        effective_updates = min(5, total_updates) if quick_mode else total_updates

        obs_list, mask_list = [], []
        for i in range(self.n_envs):
            o, info = self._reset_env(i)
            obs_list.append(o)
            mask_list.append(info["action_mask"])
        ep_return = np.zeros(self.n_envs, dtype=np.float64)

        current_obs = torch.tensor(np.array(obs_list), dtype=torch.float32, device=self.device)
        current_masks = torch.tensor(np.array(mask_list), dtype=torch.bool, device=self.device)
        current_dones = torch.zeros(self.n_envs, dtype=torch.float32, device=self.device)

        for update in range(1, effective_updates + 1):
            if max_duration_seconds and (time.time() - start_time) >= max_duration_seconds:
                break

            T, N = self.steps_per_env, self.n_envs
            obs_buf = torch.zeros((T, N, OBS_DIM), device=self.device)
            act_buf = torch.zeros((T, N), device=self.device, dtype=torch.long)
            logprob_buf = torch.zeros((T, N), device=self.device)
            rew_buf = torch.zeros((T, N), device=self.device)
            done_buf = torch.zeros((T, N), device=self.device)
            val_buf = torch.zeros((T, N), device=self.device)
            mask_buf = torch.zeros((T, N, ACTION_DIM), device=self.device, dtype=torch.bool)
            ep_rewards: List[float] = []
            ep_wins: List[float] = []

            # 1. Rollout
            for t in range(T):
                self.total_steps += N
                obs_buf[t] = current_obs
                mask_buf[t] = current_masks
                done_buf[t] = current_dones

                with torch.no_grad():
                    action, logprob, _, value = self.model.get_action_and_value(current_obs, mask=current_masks)
                val_buf[t] = value
                act_buf[t] = action
                logprob_buf[t] = logprob

                next_obs, next_masks, next_dones, rewards = [], [], [], []
                for i, env in enumerate(self.envs):
                    n_o, r, term, trunc, info = env.step(int(action[i].item()))
                    ep_return[i] += r
                    if trunc and not term:
                        # Bootstrap: the episode was cut by the time limit, not finished.
                        with torch.no_grad():
                            v_last = self.model.get_value(
                                torch.tensor(n_o, dtype=torch.float32, device=self.device).unsqueeze(0)
                            ).item()
                        r = r + self.gamma * v_last
                    rewards.append(r)
                    done = term or trunc
                    next_dones.append(float(done))
                    if done:
                        won = info.get("round_winner") == "p1"
                        ep_rewards.append(float(ep_return[i]))
                        ep_wins.append(float(won))
                        ep_return[i] = 0.0
                        if self.league is not None:
                            self.league.record_match_result(self._env_opponent_names[i], won)
                        n_o, reset_info = self._reset_env(i)
                        next_masks.append(reset_info["action_mask"])
                    else:
                        next_masks.append(info["action_mask"])
                    next_obs.append(n_o)

                rew_buf[t] = torch.tensor(rewards, dtype=torch.float32, device=self.device)
                current_obs = torch.tensor(np.array(next_obs), dtype=torch.float32, device=self.device)
                current_masks = torch.tensor(np.array(next_masks), dtype=torch.bool, device=self.device)
                current_dones = torch.tensor(next_dones, dtype=torch.float32, device=self.device)

            # 2. GAE. done_buf[t+1] marks that the transition at t ended an episode.
            with torch.no_grad():
                next_value = self.model.get_value(current_obs)
                advantages = torch.zeros_like(rew_buf)
                lastgaelam = torch.zeros(N, device=self.device)
                for t in reversed(range(T)):
                    if t == T - 1:
                        nextnonterminal = 1.0 - current_dones
                        nextvals = next_value
                    else:
                        nextnonterminal = 1.0 - done_buf[t + 1]
                        nextvals = val_buf[t + 1]
                    delta = rew_buf[t] + self.gamma * nextvals * nextnonterminal - val_buf[t]
                    lastgaelam = delta + self.gamma * self.gae_lambda * nextnonterminal * lastgaelam
                    advantages[t] = lastgaelam
                returns = advantages + val_buf

            b_obs = obs_buf.reshape(-1, OBS_DIM)
            b_logprobs = logprob_buf.reshape(-1)
            b_actions = act_buf.reshape(-1)
            b_masks = mask_buf.reshape(-1, ACTION_DIM)
            b_advantages = advantages.reshape(-1)
            b_returns = returns.reshape(-1)
            b_advantages = (b_advantages - b_advantages.mean()) / (b_advantages.std() + 1e-8)

            # 3. Optimisation epochs
            b_inds = np.arange(self.batch_size)
            sums = {"pg": 0.0, "v": 0.0, "ent": 0.0, "clipfrac": 0.0, "approx_kl": 0.0}
            n_batches = 0
            for _ in range(int(PPO_EPOCHS_PER_UPDATE)):
                self.rng.shuffle(b_inds)
                for start in range(0, self.batch_size, PPO_BATCH_SIZE):
                    mb = b_inds[start:start + PPO_BATCH_SIZE]
                    _, newlogprob, entropy, newvalue = self.model.get_action_and_value(
                        b_obs[mb], mask=b_masks[mb], action=b_actions[mb]
                    )
                    logratio = newlogprob - b_logprobs[mb]
                    ratio = logratio.exp()
                    mb_adv = b_advantages[mb]
                    pg_loss = torch.max(
                        -mb_adv * ratio,
                        -mb_adv * torch.clamp(ratio, 1 - self.clip_eps, 1 + self.clip_eps),
                    ).mean()
                    v_loss = 0.5 * ((newvalue - b_returns[mb]) ** 2).mean()
                    entropy_loss = entropy.mean()
                    loss = pg_loss - self.ent_coef * entropy_loss + self.val_coef * v_loss

                    self.optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.model.parameters(), PPO_MAX_GRAD_NORM)
                    self.optimizer.step()

                    with torch.no_grad():
                        sums["clipfrac"] += ((ratio - 1.0).abs() > self.clip_eps).float().mean().item()
                        sums["approx_kl"] += ((ratio - 1) - logratio).mean().item()
                    sums["pg"] += pg_loss.item()
                    sums["v"] += v_loss.item()
                    sums["ent"] += entropy_loss.item()
                    n_batches += 1

            self.update_count += 1
            self.episode_returns.extend(ep_rewards)
            self.episode_wins.extend(ep_wins)
            nb = max(1, n_batches)
            log_entry = {
                "update": self.update_count,
                "total_steps": self.total_steps,
                "mean_reward": float(rew_buf.mean().item()),
                "episodes_finished": len(ep_rewards),
                "mean_episode_return": float(np.mean(ep_rewards)) if ep_rewards else None,
                "episode_win_rate": float(np.mean(ep_wins)) if ep_wins else None,
                "policy_loss": sums["pg"] / nb,
                "value_loss": sums["v"] / nb,
                "entropy": sums["ent"] / nb,
                "clipfrac": sums["clipfrac"] / nb,
                "approx_kl": sums["approx_kl"] / nb,
                "elapsed_time": time.time() - start_time,
            }
            if self.league is not None:
                log_entry["league_elo"] = self.league.learner_elo
                log_entry["curriculum_tier"] = self.league.curriculum_tier
            self.history.append(log_entry)
            logger.info("PPO %s update %d: reward/step=%.3f ep_return=%s win=%s",
                        self.personality, self.update_count, log_entry["mean_reward"],
                        log_entry["mean_episode_return"], log_entry["episode_win_rate"])
            if progress_callback is not None:
                progress_callback(log_entry)

            is_last = update == effective_updates
            if self.update_count % self.checkpoint_interval == 0 or is_last:
                self.saved_checkpoints.append(self.save_checkpoint())

        if self.results_dir:
            self._save_training_summary()
        return {
            "total_steps": self.total_steps,
            "updates_completed": self.update_count,
            "final_reward": self.history[-1]["mean_reward"] if self.history else 0.0,
            "history": self.history,
            "checkpoints": list(self.saved_checkpoints),
            "latest_checkpoint": self.saved_checkpoints[-1] if self.saved_checkpoints else None,
        }

    def save_checkpoint(self, update_num: Optional[int] = None) -> str:
        """Save weights + metadata under the next free version number.

        ``update_num`` is recorded in the metadata only; it never selects the
        filename, so checkpoints are never overwritten.
        """
        directory = character_dir(self.personality, self.models_dir)
        recent = [h for h in self.history[-10:] if h.get("episode_win_rate") is not None]
        meta = {
            "type": "ppo",
            "personality": self.personality,
            "update": update_num if update_num is not None else self.update_count,
            "total_steps": self.total_steps,
            "git_commit": get_git_commit_hash(),
            "seed": self.seed,
            "warm_start": self.warm_started_from,
            "league_elo": self.league.learner_elo if self.league is not None else None,
            "recent_training_win_rate": (float(np.mean([h["episode_win_rate"] for h in recent]))
                                         if recent else None),
            "latest_metrics": self.history[-1] if self.history else {},
        }
        return save_checkpoint(self.model, directory, version=next_version(directory), meta=meta)

    def _save_training_summary(self) -> str:
        os.makedirs(self.results_dir, exist_ok=True)
        out_file = os.path.join(self.results_dir, f"ppo_{self.personality.lower()}_curve.json")
        with open(out_file, "w") as f:
            json.dump(
                {
                    "personality": self.personality,
                    "seed": self.seed,
                    "git_commit": get_git_commit_hash(),
                    "n_envs": self.n_envs,
                    "steps_per_env": self.steps_per_env,
                    "warm_start": self.warm_started_from,
                    "checkpoints": self.saved_checkpoints,
                    "history": self.history,
                },
                f,
                indent=2,
            )
        return out_file


# ======================================================================
# CLI
# ======================================================================
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Train a fighter policy with PPO.")
    parser.add_argument("--character", default="Crimson")
    parser.add_argument("--updates", type=int, default=10)
    parser.add_argument("--n-envs", type=int, default=PPO_N_ENVS)
    parser.add_argument("--steps-per-env", type=int, default=PPO_STEPS_PER_ENV)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--results-dir", default=RESULTS_DIR,
                        help="where the learning curve JSON goes ('' to skip)")
    parser.add_argument("--warm-start", default="auto",
                        help="'auto' = models/<char>/bc_model.pt or newest checkpoint, 'none', or a path")
    parser.add_argument("--opponent", default="league", help="'league' or 'random'")
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--checkpoint-interval", type=int, default=PPO_CHECKPOINT_INTERVAL)
    parser.add_argument("--registry", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    import torch
    torch.set_num_threads(1)   # tiny networks: threads only add contention

    warm = None
    if args.warm_start == "auto":
        warm = find_latest_checkpoint(args.character, args.models_dir, include_bc=True)
    elif args.warm_start not in ("", "none"):
        warm = args.warm_start

    opponent = None
    if args.opponent == "random":
        from backend.ai.random_agent import RandomAgent

        opponent = RandomAgent(player=2, seed=args.seed)

    trainer = PPOTrainer(
        personality=args.character,
        opponent_agent=opponent,
        n_envs=args.n_envs,
        steps_per_env=args.steps_per_env,
        seed=args.seed,
        warm_start_weights=warm,
        models_dir=args.models_dir,
        results_dir=args.results_dir or None,
        registry_path=args.registry,
        checkpoint_interval=args.checkpoint_interval,
    )
    res = trainer.train(total_updates=args.updates, max_duration_seconds=args.max_seconds)
    print(json.dumps({k: v for k, v in res.items() if k != "history"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
