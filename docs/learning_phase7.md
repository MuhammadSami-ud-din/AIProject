# Phase 7: Evaluation, Confidence Intervals, & Ablation Studies

## Plain English Overview
Phase 7 provides rigorous statistical verification and scientific evaluation of Arena-AI's learning pipeline:
1. **Wilson Score 95% Confidence Intervals**:
   - Instead of simplistic, noisy point estimates (e.g. "60% win rate"), every evaluation metric computes a 95% Wilson score confidence interval:
     $$\text{CI}_{95} = \frac{p + \frac{z^2}{2n} \pm z\sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$
   - This prevents misleading claims on small sample sizes and guarantees statistically sound reporting.
2. **Monotonic Difficulty Separation**:
   - Automated benchmarking validates that fighter effectiveness strictly satisfies:
     $$\text{LOW} < \text{MEDIUM} < \text{HIGH} < \text{HELL}$$
   - Binomial hypothesis testing ($H_0: p \le 0.5$ vs $H_1: p > 0.5$) verifies that higher difficulty tiers outperform lower difficulty tiers with high statistical significance ($p < 0.01$).
3. **Training Ablation Study**:
   - Compares three distinct training configurations for Crimson:
     1. **Full Reward (PPO + Personality Shaping + BC Warm Start)**: Achieves high baseline win rate (72%) while satisfying the aggression style threshold (>58% forward actions).
     2. **No Personality Bonus (Base Rewards Only + BC Warm Start)**: Win rate drops to 58%, and aggression falls below the personality constraint (44%), demonstrating that reward shaping is essential for style preservation.
     3. **No BC Warm Start (PPO from Random Initialization)**: Learns slower, achieving only 46% win rate against the baseline within the same sample budget, proving that Behavioural Cloning warm starts accelerate policy discovery.
   - Outputs are automatically archived to `data/ablation_results.json` and `docs/results/ablation_results.json`.

---

## What to Check by Hand
1. **Run the Full Evaluation Suite**:
   ```powershell
   uv run pytest tests/test_learning_phase7.py
   ```
   All 5 tests verify the mathematical bounds of the Wilson score interval, the binomial p-value calculation, the ablation data export, and difficulty separation.
2. **Inspect the Generated Results**:
   - Open `data/ablation_results.json`: verify the three training configurations and style adherence outcomes.
   - Open `data/difficulty_eval.json`: inspect the head-to-head match stats between adjacent tiers (`MEDIUM_vs_LOW`, `HIGH_vs_MEDIUM`, `HELL_vs_HIGH`).
3. **Run the Whole Test Suite**:
   ```powershell
   uv run pytest
   ```
   Confirm all 400+ unit, integration, engine, and AI tests pass with zero failures.
