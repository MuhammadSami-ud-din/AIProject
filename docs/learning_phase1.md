# Learning Pipeline: Phase 1 — Training Environment & Action Masking

## Overview
Phase 1 encapsulates the headless deterministic combat engine into a standard Gymnasium reinforcement learning environment (`ArenaEnv`). Decision points are based on macro-actions rather than raw frame inputs, with intelligent frame-skipping and strict action masking.

## Key Features

1. **Gymnasium Interface (`ArenaEnv`)**:
   - `reset(seed)`: Initializes a deterministic match, returning a 30-element float32 observation vector (`Observation.features()`) and an `info` dictionary containing the legal `action_mask`.
   - `step(action)`: Accepts a macro-action index (0 to 26), applies the action, and advances the simulation forward until the agent is actionable again or the round concludes. Returns `(obs, reward, terminated, truncated, info)`.

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
   - The opponent can be any `Agent`: `RandomAgent`, rule-based FSMs (`CrimsonAgent`, `SteelAgent`, etc.), search agents, or another learned neural policy.
   - Fully reproducible: identical seeds produce bit-identical fight trajectories.

## Verification
Run the Phase 1 test suite:
```bash
uv run pytest tests/test_learning_phase1.py
```
Tests verify observation shapes, mask validity, rule enforcement, determinism, and 1,000 continuous random steps.
