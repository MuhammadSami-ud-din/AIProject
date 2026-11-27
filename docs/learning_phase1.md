# Learning Pipeline: Phase 1 — Training Environment & Action Masking

## Overview
Phase 1 encapsulates the headless deterministic combat engine into a standard Gymnasium reinforcement learning environment (`ArenaEnv`). Decision points are based on macro-actions rather than raw frame inputs, with intelligent frame-skipping and strict action masking.

## Key Features

1. **Gymnasium Interface (`ArenaEnv`)**:
   - `reset(seed)`: Initializes a deterministic match, returning a 96-element float32 policy vector (`backend/learning/features.py::policy_vector`) and an `info` dictionary containing the legal `action_mask`. The vector holds the 28 numeric base features, one-hot encodings of my/the enemy's last action (raw ids 0..26 are categorical, not magnitudes), one-hot attack phase (none/startup/active/recovery) for both fighters, and the exact action-mask inputs (thrown, guard-break stun, burst used, jump frame). `Observation.features()` (30 values) remains the fight-log / sklearn format.
   - `step(action)`: Accepts a macro-action index (0 to 26), applies the action, and advances the simulation forward until the agent is actionable again (at least `ACTION_EXECUTION_FRAMES`=6 frames, at most 30) or the round concludes. Movement/guard actions are held for the whole macro-step; attacks are pressed on the first frame (`macro_frame_action` / `macro_step_done`, shared with `PolicyAgent` so gameplay uses the same granularity). Every simulated frame is passed to `RewardCalculator.observe_frame` so one-frame engine events are never missed. A round ending is `terminated`; hitting the frame limit without a decided round is `truncated` (PPO bootstraps it). Returns `(obs, reward, terminated, truncated, info)`.

2. **Action Masking**:
   - Computes a boolean mask of legal actions (`(27,)`) at every step:
     * Ground moves cannot be performed while airborne.
     * Aerial strikes (`Jump Punch`, `Jump Kick`) can only be performed while airborne.
     * Supers (`P`) require sufficient Super Meter (100 standard, 60 in Fury mode).
     * Character-specific meter requirements (e.g., Steel's Shield Bash requires 25 meter).
     * Burst (`L + O`) is only legal while trapped in hitstun with $\ge 50$ meter.
     * `Action.IDLE` is always legal as a guaranteed safety action.
   - The policy never executes an illegal move.

3. **Pluggable Opponents & Determinism**:
   - The opponent can be any `Agent`: `RandomAgent`, rule-based FSMs (`CrimsonAgent`, `SteelAgent`, etc.), difficulty-wrapped FSMs, or another learned neural policy. `env.set_opponent(agent, character)` swaps it between episodes (used by league sampling).
   - Fully reproducible: identical seeds produce bit-identical fight trajectories.

## Verification
Run the Phase 1 test suite:
```bash
uv run pytest tests/test_learning_phase1.py
```
Tests verify observation shapes, mask validity, rule enforcement, determinism, and 1,000 continuous random steps.
