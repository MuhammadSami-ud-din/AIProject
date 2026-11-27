"""Separate process worker for running background model training.

Runs in a separate OS process via multiprocessing (NOT a thread), so the game's
render loop never freezes. One ``PPOTrainer.train()`` call runs all updates
(environments persist across updates), checkpoints get unique increasing
version numbers, and the promotion gate is the real one (quick mode only plays
fewer validation matches). All paths are absolute (anchored at the project
root) and the process can be stopped cleanly with ``stop_training()``.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
from typing import Any, Dict, Optional

from backend.learning.config import DEFAULT_SEED, MODELS_DIR, REGISTRY_DB_PATH

logger = logging.getLogger(__name__)


def background_train_worker(
    personality: str,
    total_updates: int,
    quick_mode: bool,
    progress_queue: mp.Queue,
    seed: int = DEFAULT_SEED,
    models_dir: str = MODELS_DIR,
    registry_path: str = REGISTRY_DB_PATH,
    stop_event: Optional[Any] = None,
) -> None:
    """Worker target executed inside a multiprocessing.Process."""
    # Imported inside the child so the game process does not pay for torch at import time.
    from backend.learning.bc import train_bc_model
    from backend.learning.league import LeagueManager
    from backend.learning.policy_agent import PolicyAgent
    from backend.learning.ppo import PPOTrainer
    import torch

    torch.set_num_threads(1)   # keep the game process responsive
    max_steps = total_updates + 3

    def report(step: int, msg: str, **extra) -> None:
        progress_queue.put({"step": step, "max_steps": max_steps, "msg": msg, **extra})

    try:
        report(1, "Phase 3: Behaviour Cloning warm-up...", reward=0.0)
        bc_model, bc_metrics = train_bc_model(
            personality=personality,
            epochs=5 if quick_mode else 12,
            seed=seed,
            num_matches=8 if quick_mode else 20,
            models_dir=models_dir,
        )
        report(2, f"BC complete (acc {bc_metrics['test_accuracy']:.0%}). Initializing PPO...", reward=0.0)

        league = LeagueManager(learner_personality=personality, registry_path=registry_path, seed=seed)
        trainer = PPOTrainer(
            personality=personality,
            n_envs=2 if quick_mode else 8,
            steps_per_env=64 if quick_mode else 256,
            seed=seed,
            models_dir=models_dir,
            league=league,
            checkpoint_interval=max(1, total_updates),   # one checkpoint at the end
        )
        trainer.model.load_state_dict(bc_model.state_dict())
        trainer.warm_started_from = "bc_model (this run)"

        def on_update(entry: Dict[str, Any]) -> None:
            if stop_event is not None and stop_event.is_set():
                raise KeyboardInterrupt("training stopped by user")
            u = entry["update"]
            report(u + 2, f"PPO Update {u}/{total_updates} | Reward/step: {entry['mean_reward']:.3f}",
                   reward=entry["mean_reward"])

        res = trainer.train(total_updates=total_updates, progress_callback=on_update)
        latest_pt = res["latest_checkpoint"] or trainer.save_checkpoint()
        version_tag = latest_pt.rsplit("/", 1)[-1].replace(".pt", "")

        report(max_steps - 1, "Running League Promotion Tournament...", reward=0.0)
        candidate = PolicyAgent(personality, model_path=latest_pt, use_registry=False)
        promoted, status_msg, metrics = league.attempt_promotion(
            candidate,
            model_path=latest_pt,
            version_tag=version_tag,
            num_matches=25,
            quick_mode=quick_mode,
        )
        progress_queue.put({
            "step": max_steps,
            "max_steps": max_steps,
            "msg": f"Complete: {status_msg} (WinRate: {metrics.get('win_rate', 0.0) * 100:.1f}%)",
            "done": True,
            "promoted": promoted,
            "metrics": metrics,
            "checkpoint": latest_pt,
        })
    except KeyboardInterrupt:
        progress_queue.put({"done": True, "stopped": True, "msg": "Training stopped."})
    except Exception as e:  # report to the UI instead of dying silently
        logger.exception("background training failed")
        progress_queue.put({"error": str(e), "done": True, "msg": f"Training failed: {e}"})


class BackgroundTrainingManager:
    """Manages the background training process and progress communication."""

    def __init__(self):
        self.process: Optional[mp.Process] = None
        self.queue: Optional[mp.Queue] = None
        self.stop_event = None
        self.last_status: str = "Idle"
        self.progress: float = 0.0
        self.is_running: bool = False
        self.last_result: Optional[Dict[str, Any]] = None

    def start_training(self, personality: str = "Crimson", total_updates: int = 6, quick_mode: bool = True,
                       models_dir: str = MODELS_DIR, registry_path: str = REGISTRY_DB_PATH) -> bool:
        """Spawn the background training process."""
        if self.is_alive():
            return False

        ctx = mp.get_context("spawn")   # fresh interpreter: no pygame/SDL state is inherited
        self.queue = ctx.Queue()
        self.stop_event = ctx.Event()
        self.process = ctx.Process(
            target=background_train_worker,
            args=(personality, total_updates, quick_mode, self.queue, DEFAULT_SEED,
                  models_dir, registry_path, self.stop_event),
            daemon=True,
        )
        self.process.start()
        self.is_running = True
        self.progress = 0.0
        self.last_result = None
        self.last_status = f"Started training {personality}..."
        return True

    def stop_training(self, timeout: float = 5.0) -> None:
        """Ask the worker to stop after the current update; terminate if it does not."""
        if self.stop_event is not None:
            self.stop_event.set()
        if self.process is not None and self.process.is_alive():
            self.process.join(timeout)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(1.0)
        self.is_running = False
        self.last_status = "Training stopped."

    def poll(self) -> None:
        """Poll the progress queue without blocking."""
        if not self.queue:
            return

        while True:
            try:
                data = self.queue.get_nowait()
            except queue.Empty:
                break
            except (EOFError, OSError):
                logger.warning("training progress queue closed unexpectedly", exc_info=True)
                break
            if "msg" in data:
                self.last_status = data["msg"]
            if "step" in data and "max_steps" in data:
                self.progress = float(data["step"] / max(1, data["max_steps"]))
            if data.get("done", False):
                self.is_running = False
                self.last_result = data

        if self.process and not self.process.is_alive():
            self.is_running = False

    def is_alive(self) -> bool:
        if self.process and self.process.is_alive():
            return True
        self.is_running = False
        return False


# Global manager singleton
training_manager = BackgroundTrainingManager()
