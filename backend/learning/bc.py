"""Behaviour-Cloning (BC) warm start for PPO.

Demonstrations are recorded at the SAME macro-step granularity PPO uses: the
character's rule-based FSM "expert" drives the learner side of an ``ArenaEnv``
(one decision per env.step, executed with the env's macro-action rules), so
every sample is an (observation, action-mask, executed action, reward) tuple
exactly like a PPO transition.

  - Actor: masked cross-entropy on the expert's actions from rounds it won.
  - Critic: initialised too (not left random): after the actor is trained, the
    value head is fitted to the discounted returns of ALL recorded rounds with
    the shared layers frozen, so PPO starts with a meaningful baseline.
  - Match-level splitting (never splits a round across train/test).
  - Jitter augmentation applied exclusively to the training split.
  - Optional extra data from the fight-log DB (backend/data/fights.db, written
    by ``python -m backend.data.simulate``), sub-sampled to decision points.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import subprocess
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from backend.ai.actions import Action
from backend.ai.difficulty import DifficultyWrapper
from backend.ai.random_agent import RandomAgent
from backend.learning.checkpoints import save_named
from backend.learning.config import (
    ACTION_DIM,
    ACTION_EXECUTION_FRAMES,
    BC_BATCH_SIZE,
    BC_EPOCHS,
    BC_LEARNING_RATE,
    BC_TEST_SPLIT,
    DEFAULT_SEED,
    FIGHT_LOGS_DB_PATH,
    MODELS_DIR,
    OBS_DIM,
    PPO_GAMMA,
    RESULTS_DIR,
    get_character_agent as get_agent,
)
from backend.learning.features import vector_from_log_row
from backend.learning.network import ActorCritic

logger = logging.getLogger(__name__)

CHARACTERS = ("Crimson", "Steel", "Shadow", "Golden")

# A demonstration row: (match_id, obs_vector, action_index, discounted_return, mask, use_for_policy)
Row = Tuple


def get_git_commit_hash() -> str:
    """Return the current short git commit hash, or 'unknown'."""
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode("utf-8").strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _demo_opponent(personality: str, idx: int, seed: int):
    """Rotate demo opponents: random, then other characters' FSMs at LOW/MEDIUM."""
    others = [c for c in CHARACTERS if c != personality]
    kind = idx % 4
    if kind == 0:
        return RandomAgent(player=2, seed=seed + idx), "Steel"
    char = others[idx % len(others)]
    diff = "LOW" if kind in (1, 2) else "MEDIUM"
    agent = DifficultyWrapper(get_agent(char, player=2, seed=seed + idx), difficulty=diff,
                              use_learned_policy=False, use_search=False)
    return agent, char


def _discounted(rewards: List[float], gamma: float) -> List[float]:
    out, g = [], 0.0
    for r in reversed(rewards):
        g = r + gamma * g
        out.append(g)
    return out[::-1]


def generate_demonstrations(
    personality: str, num_matches: int = 15, seed: int = DEFAULT_SEED, gamma: float = PPO_GAMMA,
) -> List[Row]:
    """Record the FSM expert playing ``num_matches`` rounds through ArenaEnv."""
    from backend.learning.env import ArenaEnv
    from backend.learning.rewards import RewardCalculator

    rows: List[Row] = []
    for mid in range(num_matches):
        expert = get_agent(personality, player=1, seed=seed + mid)
        opponent, opp_char = _demo_opponent(personality, mid, seed)
        env = ArenaEnv(personality, opp_char, opponent_agent=opponent,
                       reward_calculator=RewardCalculator(personality), seed=seed + mid)
        vec, info = env.reset(seed=seed + mid)
        expert.reset()
        obs_list, masks, acts, rews = [], [], [], []
        while True:
            mask = info["action_mask"]
            act = expert.choose_action(env.current_observation())
            act = act[0] if isinstance(act, tuple) else act
            a_idx = act.value if act.value < ACTION_DIM and mask[act.value] else Action.IDLE.value
            obs_list.append(vec)
            masks.append(mask.copy())
            acts.append(a_idx)
            vec, r, term, trunc, info = env.step(a_idx)
            rews.append(r)
            if term or trunc:
                break
        won = info.get("round_winner") == "p1"
        for o, m, a, g in zip(obs_list, masks, acts, _discounted(rews, gamma)):
            rows.append((mid, o, a, float(g), m, won))
    return rows


def _log_rows(personality: str, db_path: str, max_matches: int = 200) -> List[Row]:
    """Winning player-1 rows of ``personality`` from the fight-log DB at decision points."""
    import sqlite3

    rows: List[Row] = []
    conn = sqlite3.connect(db_path)
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT match_id FROM frames WHERE agent1_name = ? AND match_result = 'p1' LIMIT ?",
            (personality, max_matches),
        ).fetchall()]
        for n, mid in enumerate(ids):
            cur = conn.execute("SELECT * FROM frames WHERE match_id = ? ORDER BY frame", (mid,))
            cols = [d[0] for d in cur.description]
            last_action = None
            since = ACTION_EXECUTION_FRAMES
            for data in cur.fetchall():
                row = dict(zip(cols, data))
                try:
                    act = Action[row["action1"]]
                except KeyError:
                    continue
                since += 1
                # decision points: the action changed, or one macro-step elapsed
                if act == last_action and since < ACTION_EXECUTION_FRAMES:
                    continue
                last_action, since = act, 0
                vec = vector_from_log_row(row, my_side=1)
                if vec is None or act.value >= ACTION_DIM:
                    continue
                mask = np.ones(ACTION_DIM, dtype=bool)
                rows.append((f"log{n}", vec, act.value, 0.0, mask, True))
    finally:
        conn.close()
    return rows


def collect_dataset(
    personality: str,
    db_path: Optional[str] = None,
    seed: int = DEFAULT_SEED,
    num_matches: int = 20,
    use_logs: bool = False,
) -> List[Row]:
    """Simulated macro-step demonstrations, plus fight-log rows if ``use_logs``."""
    records = generate_demonstrations(personality, num_matches=num_matches, seed=seed)
    if use_logs:
        path = db_path or FIGHT_LOGS_DB_PATH
        if os.path.exists(path):
            try:
                records.extend(_log_rows(personality, path))
            except Exception:
                logger.warning("could not read fight logs from %s", path, exc_info=True)
        else:
            logger.info("fight-log DB %s not found; using simulated demonstrations only", path)
    return records


def split_by_match(
    dataset: List[Row], test_split: float = BC_TEST_SPLIT, seed: int = DEFAULT_SEED
) -> Tuple[List[Row], List[Row]]:
    """Split dataset by match_id so frames from the same match never leak across splits."""
    match_ids = sorted({row[0] for row in dataset}, key=str)
    rng = random.Random(seed)
    rng.shuffle(match_ids)

    n_test = max(1, int(len(match_ids) * test_split))
    test_ids = set(match_ids[:n_test])
    train_data = [row for row in dataset if row[0] not in test_ids]
    test_data = [row for row in dataset if row[0] in test_ids]
    return train_data, test_data


def augment_features(X: np.ndarray, y: np.ndarray, seed: int = DEFAULT_SEED) -> Tuple[np.ndarray, np.ndarray]:
    """Append a jittered copy of the training data (training split only)."""
    rng = np.random.default_rng(seed)
    jitter = rng.normal(0.0, 0.015, size=X.shape).astype(np.float32)
    jittered_X = np.clip(X + jitter, -5.0, 5.0)
    return np.vstack([X, jittered_X]), np.concatenate([y, y])


def _stack(rows: List[Row]):
    X = np.array([r[1] for r in rows], dtype=np.float32).reshape(-1, OBS_DIM)
    y = np.array([r[2] for r in rows], dtype=np.int64)
    G = np.array([r[3] if len(r) > 3 else 0.0 for r in rows], dtype=np.float32)
    M = np.array([r[4] if len(r) > 4 else np.ones(ACTION_DIM, bool) for r in rows], dtype=bool).reshape(-1, ACTION_DIM)
    P = np.array([bool(r[5]) if len(r) > 5 else True for r in rows], dtype=bool)
    return X, y, G, M, P


def _round_win_rate(dataset: List[Row]) -> float:
    rounds = {r[0]: bool(r[5]) for r in dataset if len(r) > 5 and not str(r[0]).startswith("log")}
    return float(np.mean(list(rounds.values()))) if rounds else 0.0


def train_bc_model(
    personality: str = "Crimson",
    epochs: int = BC_EPOCHS,
    lr: float = BC_LEARNING_RATE,
    batch_size: int = BC_BATCH_SIZE,
    seed: int = DEFAULT_SEED,
    save_path: Optional[str] = None,
    models_dir: Optional[str] = None,
    results_dir: Optional[str] = None,
    num_matches: int = 20,
    use_logs: bool = False,
    db_path: Optional[str] = None,
    critic_epochs: int = 10,
) -> Tuple[ActorCritic, Dict[str, float]]:
    """Train the BC actor and fit the critic; save to ``save_path``.

    ``save_path`` defaults to ``<models_dir or MODELS_DIR>/<char>/bc_model.pt``.
    Metrics JSON is written to ``results_dir`` only when one is given.
    """
    personality = personality.capitalize()
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    dataset = collect_dataset(personality, db_path=db_path, seed=seed, num_matches=num_matches, use_logs=use_logs)
    train_rows, test_rows = split_by_match(dataset, test_split=BC_TEST_SPLIT, seed=seed)
    X_tr, y_tr, G_tr, M_tr, P_tr = _stack(train_rows)
    X_te, y_te, G_te, M_te, P_te = _stack(test_rows)
    if P_tr.sum() == 0:  # expert never won a training round: imitate all rounds
        P_tr[:] = True
    if P_te.sum() == 0:
        P_te[:] = True

    # ---- Actor: masked cross-entropy on winning rounds (augmented) ----
    Xp, yp = X_tr[P_tr], y_tr[P_tr]
    Mp = M_tr[P_tr]
    Xa, ya = augment_features(Xp, yp, seed=seed)
    Ma = np.vstack([Mp, Mp])
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(torch.tensor(Xa), torch.tensor(ya), torch.tensor(Ma)),
        batch_size=batch_size, shuffle=True,
    )
    model = ActorCritic(obs_dim=OBS_DIM, action_dim=ACTION_DIM)
    ce = nn.CrossEntropyLoss()
    opt = optim.Adam(list(model.shared_net.parameters()) + list(model.actor.parameters()), lr=lr)
    model.train()
    for _ in range(epochs):
        for bx, by, bm in loader:
            logits, _ = model(bx, mask=bm)
            loss = ce(logits, by)
            opt.zero_grad()
            loss.backward()
            opt.step()

    # ---- Critic: fit value head on discounted returns (shared layers frozen) ----
    for p in model.shared_net.parameters():
        p.requires_grad_(False)
    v_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(torch.tensor(X_tr), torch.tensor(G_tr)),
        batch_size=batch_size, shuffle=True,
    )
    v_opt = optim.Adam(model.critic.parameters(), lr=lr * 3)
    for _ in range(critic_epochs):
        for bx, bg in v_loader:
            v = model.get_value(bx)
            v_loss = ((v - bg) ** 2).mean()
            v_opt.zero_grad()
            v_loss.backward()
            v_opt.step()
    for p in model.shared_net.parameters():
        p.requires_grad_(True)

    # ---- Evaluation on held-out rounds ----
    model.eval()
    with torch.no_grad():
        Xt = torch.tensor(X_te[P_te])
        logits, _ = model(Xt, mask=torch.tensor(M_te[P_te]))
        predictions = torch.argmax(logits, dim=-1).numpy()
        truth = y_te[P_te]
        accuracy = float((predictions == truth).mean()) if len(truth) else 0.0
        v_pred = model.get_value(torch.tensor(X_te)).numpy()
        var = float(np.var(G_te))
        value_ev = float(1.0 - np.var(G_te - v_pred) / var) if var > 1e-8 else 0.0
    majority = float(np.mean(truth == np.bincount(yp, minlength=ACTION_DIM).argmax())) if len(truth) else 0.0

    conf_matrix = np.zeros((ACTION_DIM, ACTION_DIM), dtype=int)
    for p_, t_ in zip(predictions, truth):
        conf_matrix[t_, p_] += 1

    metrics = {
        "personality": personality,
        "seed": seed,
        "git_commit": get_git_commit_hash(),
        "granularity": "macro-step (ArenaEnv.step)",
        "demo_rounds": int(num_matches),
        "expert_round_win_rate": _round_win_rate(dataset),
        "train_samples": int(len(Xa)),
        "test_samples": int(len(truth)),
        "test_accuracy": accuracy,
        "majority_class_baseline": majority,
        "critic_explained_variance": value_ev,
        "confusion_matrix": conf_matrix.tolist(),
    }

    if results_dir:
        os.makedirs(results_dir, exist_ok=True)
        with open(os.path.join(results_dir, f"bc_{personality.lower()}_metrics.json"), "w") as f:
            json.dump(metrics, f, indent=2)

    if save_path is None:
        save_path = os.path.join(models_dir or MODELS_DIR, personality.lower(), "bc_model.pt")
    save_named(model, save_path, meta={
        "type": "behaviour_cloning",
        "personality": personality,
        "test_accuracy": accuracy,
        "critic_explained_variance": value_ev,
        "seed": seed,
        "git_commit": get_git_commit_hash(),
    })
    return model, metrics


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Behaviour-cloning warm start from the FSM expert.")
    parser.add_argument("--character", default="Crimson")
    parser.add_argument("--matches", type=int, default=20, help="demonstration rounds")
    parser.add_argument("--epochs", type=int, default=BC_EPOCHS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--models-dir", default=MODELS_DIR)
    parser.add_argument("--results-dir", default=RESULTS_DIR, help="'' to skip writing metrics")
    parser.add_argument("--use-logs", action="store_true", help="also use backend/data/fights.db")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    import torch
    torch.set_num_threads(1)   # tiny networks: threads only add contention
    _, metrics = train_bc_model(
        personality=args.character, epochs=args.epochs, seed=args.seed,
        models_dir=args.models_dir, results_dir=args.results_dir or None,
        num_matches=args.matches, use_logs=args.use_logs, db_path=args.db,
    )
    print(json.dumps({k: v for k, v in metrics.items() if k != "confusion_matrix"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
