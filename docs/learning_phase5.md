# Learning Pipeline: Phase 5 — Self-Play League, Curriculum & Promotion Gate

## Overview
Phase 5 introduces a league ecosystem (`LeagueManager` in `backend/learning/league.py`) with progressive curriculum tiers, prioritized matchmaking, Elo ratings, and a promotion tournament gate equipped with stylistic identity constraints.

## System Architecture

1. **Self-Play League Pool**:
   - Holds RandomAgent, difficulty-wrapped Steel FSMs (LOW..HELL; learned-policy blending and search disabled inside the league for speed), the other characters' FSMs, and past learner checkpoints (`add_checkpoint_opponent`). Each entry has a factory so parallel envs never share mutable agent state.
   - Elo rating system ($K=32.0$, baseline $1000.0$) dynamically ranks pool competitors following every match.

2. **Prioritized Matchup Sampling**:
   - $80\%$ of matchups are sampled with weights proportional to the learner's loss rate against that specific pool member (`LeagueOpponent.wins` counts the learner's wins), focusing training where weaknesses exist. Only opponents of the unlocked curriculum tiers are sampled.
   - $20\%$ of matchups are sampled uniformly at random to safeguard against catastrophic forgetting.

3. **Curriculum Progression**:
   - Tier 1: Random & basic FSM opponents.
   - Tier 2: MEDIUM Steel & the other characters' FSMs.
   - Tier 3: HIGH/HELL Steel & past neural checkpoints.
   - The learner automatically advances tiers when maintaining a win rate $\ge 75\%$ over the curriculum evaluation window.

4. **Promotion Gate & Style Constraints**:
   - Candidate models must win $\ge 55\%$ of a validation tournament (round-robin over the whole pool, PolicyAgent with its training macro-step granularity). **Quick mode only plays fewer matches (8); the thresholds and the reported win rate/Elo are the measured ones** (the old `or quick_mode` bypass, `max(0.55, win_rate)` and +35 Elo were removed).
   - **Style Verification**: Even if a candidate achieves high win rates, it is automatically rolled back if it loses its character identity:
     * **Crimson**: pressure ratio $\ge 0.20$ = share of frames the enemy is in hitstun/blockstun/knockdown while Crimson is within 140 px (the same notion the reward pays for; pressing FORWARD does not count). Calibration: Crimson FSM 0.35, RandomAgent 0.09, always-FORWARD 0.00.
     * **Steel**: $\ge 1.0$ successful blocks/parries per minute (one-frame engine events).
     * **Shadow**: average distance $\ge 110$ px AND $\ge 250$ %HP damage per minute (a flailing random agent also keeps its distance).
     * **Golden**: action entropy $\ge 1.5$ bits AND $\ge 250$ %HP damage per minute.
   - All promotions, rollbacks, style metrics, and git commit hashes are recorded in the SQLite Model Registry (`data/model_registry.db`).

## CLI
```bash
uv run python -m backend.learning.league --character crimson --matches 24        # newest checkpoint
uv run python -m backend.learning.league --character crimson --checkpoint models/crimson/v009.pt --quick
```

## Verification
Run the Phase 5 test suite:
```bash
uv run pytest tests/test_learning_phase5.py
```
Tests verify Elo mathematics, curriculum advancement, opponent sampling distributions, style metric bounds, and registry rollback behavior.
