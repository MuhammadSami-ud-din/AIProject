"""Evaluation: real ablation studies, difficulty separation, and style benchmarking.

Everything reported here is measured by actually playing matches (and, for
the training ablation, actually training). Nothing is hard-coded.

  - Training ablation: trains PPO for each configuration (full reward with BC
    warm start / no personality bonus / no BC warm start) with a configurable
    budget, then evaluates each resulting policy against the league pool.
  - Component ablation: DifficultyWrapper with/without learned policy,
    opponent model and in-game search (search is only active at HELL).
  - Difficulty separation: LOW < MEDIUM < HIGH < HELL with Wilson intervals
    and one-sided binomial tests for head-to-head tiers.

Results are written only when an output directory is given (the CLI defaults
to docs/results/); library calls and tests never write into the repository.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.ai.difficulty import DifficultyWrapper
from backend.ai.random_agent import RandomAgent
from backend.engine.step import make_initial_state, step
from backend.learning.config import DEFAULT_SEED, RESULTS_DIR, get_character_agent as get_agent
from backend.learning.features import full_observation_for

logger = logging.getLogger(__name__)


def wilson_score_interval(successes: int, trials: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Wilson score 95% confidence interval for a binomial proportion."""
    if trials == 0:
        return 0.0, 0.0
    z = 1.95996
    p = successes / trials
    denominator = 1.0 + (z ** 2) / trials
    centre = (p + (z ** 2) / (2.0 * trials)) / denominator
    margin = (z * math.sqrt((p * (1.0 - p) + (z ** 2) / (4.0 * trials)) / trials)) / denominator
    return max(0.0, float(centre - margin)), min(1.0, float(centre + margin))


def binomial_test_greater(k: int, n: int, p0: float = 0.5) -> float:
    """One-sided p-value for H0: p <= p0 vs H1: p > p0."""
    from math import comb
    return float(sum(comb(n, i) * (p0 ** i) * ((1.0 - p0) ** (n - i)) for i in range(k, n + 1)))


def _write_json(directory: Optional[str], name: str, payload: Any) -> Optional[str]:
    if not directory:
        return None
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def run_benchmark_matches(agent_a, agent_b, num_matches: int = 20, char_a: str = "Crimson",
                          char_b: str = "Steel") -> Tuple[int, int, int]:
    """Play ``num_matches`` single rounds; return (wins_a, wins_b, draws)."""
    wins_a = wins_b = draws = 0
    for _ in range(num_matches):
        for a in (agent_a, agent_b):
            a.reset()
        state = make_initial_state(char_a, char_b)
        while not (state.round_over or state.match_over or state.round_frames_left <= 0):
            obs1 = full_observation_for(state, 1)
            obs2 = full_observation_for(state, 2)
            act1 = agent_a.choose_action(obs1)
            act1 = act1[0] if isinstance(act1, tuple) else act1
            act2 = agent_b.choose_action(obs2)
            act2 = act2[0] if isinstance(act2, tuple) else act2
            state = step(state, act1, act2)
            agent_a.observe(full_observation_for(state, 1), act1, act2)
            agent_b.observe(full_observation_for(state, 2), act2, act1)

        result = state.round_result
        if result not in ("p1", "p2"):
            h1, h2 = state.fighter1.health, state.fighter2.health
            result = "p1" if h1 > h2 else ("p2" if h2 > h1 else "draw")
        if result == "p1":
            wins_a += 1
        elif result == "p2":
            wins_b += 1
        else:
            draws += 1
    return wins_a, wins_b, draws


def _rate_entry(wins: int, n: int, **extra) -> Dict[str, Any]:
    lo, hi = wilson_score_interval(wins, n)
    return {"wins": wins, "total": n, "win_rate": wins / max(1, n), "ci_95": [lo, hi], **extra}


# ======================================================================
# Component ablation (DifficultyWrapper features)
# ======================================================================
def run_ablation_study(personality: str = "Crimson", num_matches: int = 15, difficulty: str = "HELL",
                       opponent_character: str = "Golden", opponent_difficulty: str = "MEDIUM",
                       results_dir: Optional[str] = None, seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    """Win rate of the wrapped fighter with individual components switched off."""
    configs = {
        "full": {"use_search": True, "use_opponent_model": True, "use_learned_policy": True},
        "no_policy": {"use_search": True, "use_opponent_model": True, "use_learned_policy": False},
        "no_opponent_model": {"use_search": True, "use_opponent_model": False, "use_learned_policy": True},
        "no_search": {"use_search": False, "use_opponent_model": True, "use_learned_policy": True},
    }
    results: Dict[str, Any] = {"difficulty": difficulty, "opponent": f"{opponent_character} FSM {opponent_difficulty}"}
    for name, cfg in configs.items():
        wrapped = DifficultyWrapper(get_agent(personality, player=1, seed=seed), difficulty=difficulty, **cfg)
        opponent = DifficultyWrapper(get_agent(opponent_character, player=2, seed=seed + 1),
                                     difficulty=opponent_difficulty, use_learned_policy=False, use_search=False)
        t0 = time.perf_counter()
        wins, losses, draws = run_benchmark_matches(wrapped, opponent, num_matches, personality, opponent_character)
        results[name] = _rate_entry(wins, num_matches, losses=losses, draws=draws,
                                    policy_loaded=wrapped._policy_agent is not None,
                                    search_calls=wrapped.search_calls,
                                    seconds=time.perf_counter() - t0, **cfg)
    _write_json(results_dir, f"ablation_components_{personality.lower()}.json", results)
    return results


# ======================================================================
# Difficulty separation
# ======================================================================
def verify_difficulty_separation(personality: str = "Steel", num_matches: int = 15,
                                 results_dir: Optional[str] = None,
                                 seed: int = 123) -> Dict[str, Any]:
    """Win rate of each tier vs RandomAgent; checks LOW <= MEDIUM <= HIGH <= HELL (5% slack)."""
    separation: Dict[str, Any] = {}
    prev_rate, monotonic = -1.0, True
    for diff in ("LOW", "MEDIUM", "HIGH", "HELL"):
        agent = DifficultyWrapper(get_agent(personality, player=1, seed=seed), difficulty=diff)
        wins, _, _ = run_benchmark_matches(agent, RandomAgent(player=2, seed=seed), num_matches, personality, "Steel")
        separation[diff] = _rate_entry(wins, num_matches)
        rate = separation[diff]["win_rate"]
        if rate < prev_rate - 0.05:
            monotonic = False
        prev_rate = rate
    separation["strictly_monotonic"] = monotonic
    _write_json(results_dir, "difficulty_separation.json", separation)
    return separation


def compare_difficulty_tiers(personality: str = "Steel", num_matches: int = 20,
                             results_dir: Optional[str] = None) -> Dict[str, Any]:
    """Head-to-head adjacent tiers with one-sided binomial tests."""
    out: Dict[str, Any] = {}
    for lower_tier, higher_tier in (("LOW", "MEDIUM"), ("MEDIUM", "HIGH"), ("HIGH", "HELL")):
        lower = DifficultyWrapper(get_agent(personality, player=2, seed=100), difficulty=lower_tier)
        higher = DifficultyWrapper(get_agent(personality, player=1, seed=200), difficulty=higher_tier)
        w_hi, w_lo, draws = run_benchmark_matches(higher, lower, num_matches, personality, personality)
        p_val = binomial_test_greater(w_hi, num_matches, p0=0.5)
        rate = w_hi / max(1, num_matches)
        out[f"{higher_tier}_vs_{lower_tier}"] = {
            "higher_tier": higher_tier, "lower_tier": lower_tier,
            "wins_higher": w_hi, "wins_lower": w_lo, "draws": draws,
            "win_rate": rate, "ci_95": list(wilson_score_interval(w_hi, num_matches)),
            "p_value": p_val, "statistically_superior": bool(rate > 0.5 and p_val < 0.05),
        }
    _write_json(results_dir, "difficulty_tiers.json", out)
    return out


# ======================================================================
# Training ablation (REAL: trains each configuration)
# ======================================================================
def evaluate_policy(personality: str, checkpoint: str, num_matches: int, seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    """Evaluate a checkpoint against the full league pool (same protocol as the promotion gate)."""
    from backend.learning.league import LeagueManager
    from backend.learning.policy_agent import PolicyAgent

    league = LeagueManager(personality, seed=seed)
    agent = PolicyAgent(personality, player=1, model_path=checkpoint, seed=seed, use_registry=False)
    if agent.model is None:
        raise RuntimeError(f"checkpoint {checkpoint} could not be loaded")
    win_rate, style = league.run_validation_tournament(agent, num_matches=num_matches)
    wins = int(round(win_rate * num_matches))
    return {
        **_rate_entry(wins, num_matches),
        "style": style,
        "passed_style_constraint": bool(league.evaluate_style(style)),
    }


def run_training_ablation(
    personality: str = "Crimson",
    episodes: Optional[int] = None,
    seed: int = DEFAULT_SEED,
    updates: int = 2,
    n_envs: int = 2,
    steps_per_env: int = 64,
    bc_matches: int = 6,
    bc_epochs: int = 4,
    eval_matches: int = 8,
    work_dir: Optional[str] = None,
    results_dir: Optional[str] = None,
    configurations: Optional[List[Tuple[str, bool, bool]]] = None,
) -> Dict[str, Any]:
    """Train and evaluate (1) full reward + BC, (2) no personality bonus, (3) no BC warm start.

    ``episodes`` is accepted for backwards compatibility and means ``updates``.
    Checkpoints go to ``work_dir`` (a temporary directory by default), never to models/.
    """
    from backend.learning.bc import train_bc_model
    from backend.learning.ppo import PPOTrainer

    if episodes is not None:
        updates = int(episodes)
    configurations = configurations or [
        ("full_reward", True, True),
        ("no_personality_bonus", False, True),
        ("no_bc", True, False),
    ]
    tmp = None
    if work_dir is None:
        tmp = tempfile.TemporaryDirectory(prefix="ablation_")
        work_dir = tmp.name
    try:
        bc_path = os.path.join(work_dir, "bc", personality.lower(), "bc_model.pt")
        bc_metrics = None
        if any(use_bc for _, _, use_bc in configurations):
            _, bc_metrics = train_bc_model(personality, epochs=bc_epochs, seed=seed,
                                           save_path=bc_path, num_matches=bc_matches)
        results: Dict[str, Any] = {
            "_protocol": {
                "personality": personality, "seed": seed, "ppo_updates": updates, "n_envs": n_envs,
                "steps_per_env": steps_per_env, "bc_demo_rounds": bc_matches, "bc_epochs": bc_epochs,
                "eval_matches": eval_matches,
                "evaluation": "round-robin vs the full league pool (promotion-gate protocol)",
                "bc_test_accuracy": bc_metrics["test_accuracy"] if bc_metrics else None,
            }
        }
        for name, use_bonus, use_bc in configurations:
            t0 = time.perf_counter()
            trainer = PPOTrainer(
                personality=personality, n_envs=n_envs, steps_per_env=steps_per_env, seed=seed,
                warm_start_weights=bc_path if use_bc else None,
                models_dir=os.path.join(work_dir, name), results_dir=None,
                use_personality_bonus=use_bonus,
            )
            res = trainer.train(total_updates=updates)
            ev = evaluate_policy(personality, res["latest_checkpoint"], eval_matches, seed=seed)
            results[name] = {
                "use_personality_bonus": use_bonus,
                "use_bc_warm_start": use_bc,
                "win_rate_vs_baseline": ev["win_rate"],
                "wins": ev["wins"],
                "matches": ev["total"],
                "ci_95": ev["ci_95"],
                "style_adherence": {
                    "aggression_ratio": ev["style"]["aggression"],
                    "defense_per_min": ev["style"]["defense"],
                    "avg_distance": ev["style"]["avg_distance"],
                    "passed_style_constraint": ev["passed_style_constraint"],
                },
                "final_training_history": res["history"][-1] if res["history"] else {},
                "train_seconds": time.perf_counter() - t0,
            }
        _write_json(results_dir, f"ablation_training_{personality.lower()}.json", results)
        return results
    finally:
        if tmp is not None:
            tmp.cleanup()


# ======================================================================
# CLI
# ======================================================================
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluation and ablation studies (all results measured).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ablation", help="train + evaluate reward/BC ablation configurations")
    a.add_argument("--character", default="Crimson")
    a.add_argument("--updates", type=int, default=4)
    a.add_argument("--n-envs", type=int, default=2)
    a.add_argument("--steps-per-env", type=int, default=128)
    a.add_argument("--bc-matches", type=int, default=10)
    a.add_argument("--bc-epochs", type=int, default=6)
    a.add_argument("--eval-matches", type=int, default=16)

    c = sub.add_parser("components", help="difficulty-wrapper component ablation")
    c.add_argument("--character", default="Crimson")
    c.add_argument("--matches", type=int, default=10)
    c.add_argument("--difficulty", default="HELL")

    s = sub.add_parser("separation", help="difficulty tiers vs RandomAgent")
    s.add_argument("--character", default="Steel")
    s.add_argument("--matches", type=int, default=15)

    t = sub.add_parser("tiers", help="adjacent tiers head-to-head")
    t.add_argument("--character", default="Steel")
    t.add_argument("--matches", type=int, default=20)

    for p in (a, c, s, t):
        p.add_argument("--seed", type=int, default=DEFAULT_SEED)
        p.add_argument("--results-dir", default=RESULTS_DIR, help="'' to print only")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    import torch
    torch.set_num_threads(1)   # tiny networks: threads only add contention
    out_dir = args.results_dir or None

    if args.cmd == "ablation":
        res = run_training_ablation(args.character, seed=args.seed, updates=args.updates, n_envs=args.n_envs,
                                    steps_per_env=args.steps_per_env, bc_matches=args.bc_matches,
                                    bc_epochs=args.bc_epochs, eval_matches=args.eval_matches,
                                    results_dir=out_dir)
    elif args.cmd == "components":
        res = run_ablation_study(args.character, num_matches=args.matches, difficulty=args.difficulty,
                                 results_dir=out_dir, seed=args.seed)
    elif args.cmd == "separation":
        res = verify_difficulty_separation(args.character, num_matches=args.matches, results_dir=out_dir)
    else:
        res = compare_difficulty_tiers(args.character, num_matches=args.matches, results_dir=out_dir)
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
