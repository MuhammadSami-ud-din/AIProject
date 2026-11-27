# Phase 7: Evaluation, Confidence Intervals, & Ablation Studies

Every number in this document was produced by actually running the code listed
next to it (2026-11-27, seed 42, CPU laptop). Nothing is hard-coded: the old
`run_training_ablation` returned fixed 0.72 / 0.58 / 0.46 "synthetic" win rates;
that code and its JSON output were removed. Budgets are small, so treat the
results as a pilot study, not as definitive evidence.

## Methods
- **Wilson score 95% intervals** for every win rate, one-sided **binomial
  tests** for head-to-head tiers (`backend/learning/eval.py`).
- **Evaluation protocol for policies** = the promotion gate: round-robin
  single rounds against the full league pool (Random, Steel FSM LOW/MEDIUM/
  HIGH/HELL, Crimson/Shadow/Golden FSMs), PolicyAgent at its training
  macro-step granularity.

## 1. Training run per character
```bash
uv run python -m backend.learning.bc --character <c> --matches 24 --epochs 12
uv run python -m backend.learning.ppo --character <c> --updates 80 --n-envs 4 --steps-per-env 128 --checkpoint-interval 25
uv run python -m backend.learning.league --character <c> --matches 24
```
Full output: `docs/results/training_run_summary.json`, `bc_<c>_metrics.json`,
`ppo_<c>_curve.json`. New checkpoints: crimson v009-v012, steel/shadow/golden
v007-v010 (the old v001-v006 30-feature checkpoints are kept but skipped by
the loader because their input size no longer matches).

| Character | BC held-out acc. (majority baseline) | PPO training win rate, last 10 updates | Gate win rate (24 matches) | Gate result |
|-----------|------|------|------|------|
| Crimson | 0.58 (0.38) | 0.49 | 11/24 = 0.46 | rolled back (win rate; aggression 0.16 < 0.20) |
| Steel   | 0.47 (0.20) | 0.95 | 24/24 = 1.00 | **promoted** (defense 1.11/min) |
| Shadow  | 0.49 (0.30) | 0.76 | 23/24 = 0.96 | **promoted** (avg distance 164 px, 439 %HP/min) |
| Golden  | 0.58 (0.31) | 0.25 | 8/24 = 0.33 | rolled back (win rate; 130 %HP/min) |

Observations: BC beats the majority-class baseline for every character, but
the fitted critic explains little variance (EV between -0.23 and 0.05) with
only 24 demonstration rounds. Golden's PPO run degraded late in training
(training win rate 0.25 over the last 10 updates, 0 in the final one) — 80 updates is far too few for a
stable result, and the gate correctly refused it. In gameplay HIGH/HELL use
the live model (Steel, Shadow) or else the newest checkpoint the gate has not
rejected (Crimson v011, Golden v009).

## 2. Training ablation (Crimson)
```bash
uv run python -m backend.learning.eval ablation --character crimson --updates 12 \
    --n-envs 4 --steps-per-env 128 --bc-matches 16 --bc-epochs 10 --eval-matches 24
```
Each configuration is trained from scratch with the same budget (12 PPO
updates = 6,144 macro-steps; BC test accuracy 0.49), then evaluated over 24
league matches. Output: `docs/results/ablation_training_crimson.json`.

| Configuration | Wins / 24 | Win rate | 95% CI | Aggression | Style gate |
|---------------|-----------|----------|--------|------------|------------|
| Full reward + BC warm start | 19 | 0.79 | [0.60, 0.91] | 0.17 | fail (< 0.20) |
| No personality bonus + BC | 14 | 0.58 | [0.39, 0.76] | 0.19 | fail |
| No BC warm start (full reward) | 13 | 0.54 | [0.35, 0.72] | 0.12 | fail |

The full configuration has the highest point estimate, but all intervals
overlap, so with 24 matches the differences are **not statistically
significant**. No configuration reached Crimson's pressure threshold within
this budget, and removing the personality bonus did not lower aggression in
this run. Larger budgets (`--updates`, `--eval-matches`) are needed for firm
conclusions.

## 3. Difficulty separation (Steel vs RandomAgent, 16 rounds per tier)
```bash
uv run python -m backend.learning.eval separation --character steel --matches 16
```
LOW 3/16, MEDIUM 11/16, HIGH 16/16, HELL 16/16 — monotonic
(`docs/results/difficulty_separation.json`). HIGH and HELL both hit the
ceiling against a random opponent; `eval tiers` runs the head-to-head
binomial tests.

## 4. Component ablation (Steel HELL vs Golden FSM MEDIUM, 10 rounds each)
```bash
uv run python -m backend.learning.eval components --character steel --matches 10
```
full 10/10, no_policy 10/10, no_opponent_model 10/10, no_search 10/10
(`docs/results/ablation_components_steel.json`). The switches are real (search
ran ~2,800-3,600 times per configuration and 0 times with `no_search`; the
policy was loaded except with `no_policy`), but this opponent is too weak to
separate the components — a ceiling effect, not evidence that they matter or
don't. A stronger opponent is needed.

## Tests
```bash
uv run pytest tests/test_learning_phase7.py
```
Tests check the statistics helpers, that the ablation really trains each
configuration (tiny budget, temporary directories), and that `eval.py`
contains no hard-coded metrics. Tests never write to `models/` or `docs/results/`.
