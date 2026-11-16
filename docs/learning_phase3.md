# Learning Pipeline: Phase 3 — Behaviour-Cloning Warm Start

## Overview
Phase 3 bootstraps policy neural networks using Behaviour Cloning (BC) from winning fights. Rather than initializing reinforcement learning from purely random weights, this warm-start provides an immediate baseline understanding of legal movement, spacing, and attack execution.

## Implementation Details

1. **Match-Level Split**:
   - `split_by_match()` partitions demonstrations by distinct `match_id` (80% training, 20% validation).
   - Entire fight sequences stay together; frames from the same fight never cross the train/test split boundary, preventing data leakage.

2. **Data Augmentation**:
   - `augment_features()` creates jittered feature vectors with small Gaussian noise ($\sigma = 0.015$).
   - Augmentation is strictly applied only to the training set, keeping the validation test set authentic.

3. **Neural Policy Architecture (`ActorCritic`)**:
   - Two hidden layers of 128 units with Tanh activation.
   - Dual-head design: Policy logits ($27$ macro-actions) and State Value estimation ($1$).
   - CPU-optimized inference taking $<1$ ms per evaluation.

4. **Metrics and Confusion Matrix**:
   - Evaluates multiclass accuracy and outputs a $27 \times 27$ confusion matrix to `docs/results/bc_<personality>_metrics.json`.
   - Saves checkpoint weights to `models/<personality>/bc_model.pt` alongside metadata JSON (seed, git commit hash, test accuracy).

## Verification
Run the Phase 3 test suite:
```bash
uv run pytest tests/test_learning_phase3.py
```
Tests confirm disjoint match splits, training augmentation, model training, confusion matrix generation, and weight reloadability.
