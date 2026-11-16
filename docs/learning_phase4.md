# Learning Pipeline: Phase 4 — Proximal Policy Optimization (PPO)

## Overview
Phase 4 implements a vectorized Actor-Critic PPO algorithm (`PPOTrainer` in `backend/learning/ppo.py`) tailored specifically for 2D fighting games. It features invalid action masking, Generalized Advantage Estimation (GAE), parallel environment execution, and automated checkpointing with companion metadata.

## Implementation Details

1. **Action Masking in PPO**:
   - Illegal actions are masked out before computing softmax: $\text{masked\_logits} = \text{logits} \text{ where } \text{mask is True else } -10^9$.
   - Ensures the categorical policy distribution assigns $0.0\%$ probability to unavailable actions while preserving smooth gradients across legal choices.

2. **Clipped Surrogate Loss & Value Function**:
   - Policy probability ratio: $r_t(\theta) = \frac{\pi_\theta(a_t|s_t)}{\pi_{\theta_{\text{old}}}(a_t|s_t)}$.
   - Clipped surrogate objective with $\epsilon = 0.20$:
     $$L^{\text{CLIP}}(\theta) = \hat{\mathbb{E}}_t \left[ \min\left(r_t(\theta)\hat{A}_t, \, \text{clip}(r_t(\theta), 1-\epsilon, 1+\epsilon)\hat{A}_t\right) \right]$$
   - Combined objective: $L^{\text{TOTAL}} = L^{\text{CLIP}} - c_1 L^{\text{VF}} + c_2 S[\pi_\theta]$, with entropy coefficient $c_2 = 0.01$ and value coefficient $c_1 = 0.50$.

3. **Generalized Advantage Estimation (GAE)**:
   - Temporal difference residual: $\delta_t^V = r_t + \gamma V(s_{t+1}) - V(s_t)$.
   - Advantage: $\hat{A}_t^{\text{GAE}(\gamma, \lambda)} = \sum_{l=0}^{\infty} (\gamma \lambda)^l \delta_{t+l}^V$, with $\gamma = 0.99$ and $\lambda = 0.95$.

4. **Vectorized Rollouts & Checkpoints**:
   - Gathers trajectories in parallel across $N$ environments (`PPO_N_ENVS`).
   - Checkpoints saved every $N$ updates to `models/<personality>/vNNN.pt` with companion JSON metadata files (`vNNN.json`).
   - Learning curves and update logs are written to `docs/results/ppo_<personality>_curve.json`.

## Verification
Run the Phase 4 test suite:
```bash
uv run pytest tests/test_learning_phase4.py
```
Tests verify strict 0-probability action masking, metadata checkpoint generation, and PPO training convergence.
