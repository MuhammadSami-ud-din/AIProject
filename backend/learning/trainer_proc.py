"""Separate process worker for running background model training.

Runs in a separate OS process via multiprocessing (NOT a thread), preventing GIL
lockups and ensuring the game rendering loop never freezes.
"""

import multiprocessing as mp
import time
from typing import Optional

from backend.learning.bc import train_bc_model
from backend.learning.config import DEFAULT_SEED
from backend.learning.league import LeagueManager
from backend.learning.policy_agent import PolicyAgent
from backend.learning.ppo import PPOTrainer


def background_train_worker(
    personality: str,
    total_updates: int,
    quick_mode: bool,
    progress_queue: mp.Queue,
    seed: int = DEFAULT_SEED,
) -> None:
    """Worker target executed inside a multiprocessing.Process."""
    try:
        progress_queue.put({"step": 1, "max_steps": total_updates + 2, "msg": "Phase 3: Behaviour Cloning warm-up...", "reward": 0.0})
        # 1. Warm start with BC
        bc_model, bc_metrics = train_bc_model(personality=personality, epochs=5 if quick_mode else 12, seed=seed)
        progress_queue.put({"step": 2, "max_steps": total_updates + 2, "msg": "BC warm-up complete. Initializing PPO...", "reward": 0.0})

        # 2. PPO training
        trainer = PPOTrainer(
            personality=personality,
            n_envs=2 if quick_mode else 8,
            steps_per_env=64 if quick_mode else 256,
            seed=seed,
        )
        trainer.model.load_state_dict(bc_model.state_dict())
        for u in range(1, total_updates + 1):
            res = trainer.train(total_updates=1, quick_mode=False)
            reward = res.get("final_reward", 0.0)
            progress_queue.put({
                "step": u + 2,
                "max_steps": total_updates + 2,
                "msg": f"PPO Update {u}/{total_updates} | Reward: {reward:.2f}",
                "reward": reward,
            })

        # 3. Checkpoint & Promotion tournament
        league = LeagueManager(learner_personality=personality)
        existing_models = league.registry.list_models(personality=personality)
        next_ver = len(existing_models) + 1
        latest_pt = trainer.save_checkpoint(update_num=next_ver)
        progress_queue.put({"step": total_updates + 2, "max_steps": total_updates + 2, "msg": "Running League Promotion Tournament...", "reward": 0.0})

        candidate_agent = PolicyAgent(personality, model_path=latest_pt)
        promoted, status_msg, metrics = league.attempt_promotion(
            candidate_agent,
            model_path=latest_pt,
            version_tag=f"v{next_ver:03d}",
            num_matches=4 if quick_mode else 25,
            quick_mode=quick_mode,
        )

        progress_queue.put({
            "step": total_updates + 2,
            "max_steps": total_updates + 2,
            "msg": f"Complete: {status_msg} (WinRate: {metrics.get('win_rate', 0.0)*100:.1f}%)",
            "done": True,
            "promoted": promoted,
            "metrics": metrics,
        })
    except Exception as e:
        progress_queue.put({"error": str(e), "done": True, "msg": f"Training failed: {e}"})


class BackgroundTrainingManager:
    """Manages the background training process and progress communication."""

    def __init__(self):
        self.process: Optional[mp.Process] = None
        self.queue: Optional[mp.Queue] = None
        self.last_status: str = "Idle"
        self.progress: float = 0.0
        self.is_running: bool = False

    def start_training(self, personality: str = "Crimson", total_updates: int = 6, quick_mode: bool = True) -> bool:
        """Spawn the background training process."""
        if self.is_alive():
            return False

        self.queue = mp.Queue()
        self.process = mp.Process(
            target=background_train_worker,
            args=(personality, total_updates, quick_mode, self.queue),
            daemon=True,
        )
        self.process.start()
        self.is_running = True
        self.progress = 0.0
        self.last_status = f"Started training {personality}..."
        return True

    def poll(self) -> None:
        """Poll the progress queue without blocking."""
        if not self.queue:
            return

        while not self.queue.empty():
            try:
                data = self.queue.get_nowait()
                if "msg" in data:
                    self.last_status = data["msg"]
                if "step" in data and "max_steps" in data:
                    self.progress = float(data["step"] / max(1, data["max_steps"]))
                if data.get("done", False):
                    self.is_running = False
            except Exception:
                break

        if self.process and not self.process.is_alive():
            self.is_running = False

    def is_alive(self) -> bool:
        if self.process and self.process.is_alive():
            return True
        self.is_running = False
        return False


# Global manager singleton
training_manager = BackgroundTrainingManager()
