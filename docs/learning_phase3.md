# Learning Pipeline: Phase 3 — Behaviour-Cloning Warm Start

## Overview
Phase 3 bootstraps the policy with Behaviour Cloning (BC). Demonstrations are recorded at the **same macro-step granularity PPO uses**: the character's FSM "expert" drives the learner side of an `ArenaEnv`, one decision per `env.step`, against a rotation of opponents (RandomAgent, other characters' FSMs at LOW/MEDIUM). Each sample stores the policy vector, the action mask, the executed action and the discounted return. Optional extra data: `--use-logs` reads winning player-1 rows from the fight-log DB (`backend/data/fights.db`, written by `python -m backend.data.simulate`), sub-sampled to decision points (attack phase is approximated there because it is not logged).

## Implementation Details

1. **Match-Level Split**:
   - `split_by_match()` partitions demonstrations by distinct `match_id` (80% training, 20% validation).
   - Entire fight sequences stay together; frames from the same fight never cross the train/test split boundary, preventing data leakage.

2. **Data Augmentation**:
   - `augment_features()` creates jittered feature vectors with small Gaussian noise ($\sigma = 0.015$).
   - Augmentation is strictly applied only to the training set, keeping the validation test set authentic.

3. **Actor and critic are both initialised**:
   - Actor: masked cross-entropy on the expert's actions from rounds the expert won.
   - Critic: afterwards the value head is fitted (shared layers frozen) to the discounted returns of all recorded rounds, so PPO does not start from a random baseline. `critic_explained_variance` on held-out rounds is reported.

4. **Neural Policy Architecture (`ActorCritic`)**:
   - Two hidden layers of 128 units with Tanh activation.
   - Dual-head design: Policy logits ($27$ macro-actions) and State Value estimation ($1$).
   - CPU-optimized inference taking $<1$ ms per evaluation.

5. **Metrics and Confusion Matrix**:
   - Held-out accuracy (with the majority-class baseline for comparison) and a $27 \times 27$ confusion matrix, written to `docs/results/bc_<personality>_metrics.json` only by the CLI (library calls/tests write nowhere unless `results_dir` is given).
   - Saves checkpoint weights to `models/<personality>/bc_model.pt` alongside metadata JSON (seed, git commit hash, test accuracy).

## CLI
```bash
uv run python -m backend.learning.bc --character crimson --matches 24 --epochs 12
```

## Verification
Run the Phase 3 test suite:
```bash
uv run pytest tests/test_learning_phase3.py
```
Tests confirm disjoint match splits, training augmentation, model training, confusion matrix generation, and weight reloadability.
