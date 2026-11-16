# Learning Pipeline: Phase 5 — Self-Play League, Curriculum & Promotion Gate

## Overview
Phase 5 introduces a league ecosystem (`LeagueManager` in `backend/learning/league.py`) with progressive curriculum tiers, prioritized matchmaking, Elo ratings, and a promotion tournament gate equipped with stylistic identity constraints.

## System Architecture

1. **Self-Play League Pool**:
   - Holds historical checkpoints, baseline FSM agents, search agents across difficulty tiers, and past neural models.
   - Elo rating system ($K=32.0$, baseline $1000.0$) dynamically ranks pool competitors following every match.

2. **Prioritized Matchup Sampling**:
   - $80\%$ of matchups are sampled with weights proportional to the learner's loss rate against that specific pool member, focusing training where weaknesses exist.
   - $20\%$ of matchups are sampled uniformly at random to safeguard against catastrophic forgetting.

3. **Curriculum Progression**:
   - Tier 1: Random & basic FSM opponents.
   - Tier 2: Search agents & specialized character FSMs.
   - Tier 3: High/Hell minimax agents & past neural checkpoints.
   - The learner automatically advances tiers when maintaining a win rate $\ge 75\%$ over the curriculum evaluation window.

4. **Promotion Gate & Style Constraints**:
   - Candidate models must win $\ge 55\%$ of a validation tournament against the league pool.
   - **Style Verification**: Even if a candidate achieves high win rates, it is automatically rolled back if it loses its character identity:
     * **Crimson**: Must maintain forward movement + attack aggression $\ge 0.58$.
     * **Steel**: Must maintain active defense rate $\ge 8.0$ blocks/parries per minute.
     * **Shadow**: Must maintain average engagement spacing $> 160$ px.
     * **Golden**: Must maintain action entropy and tactical balance.
   - All promotions, rollbacks, style metrics, and git commit hashes are recorded in the SQLite Model Registry (`data/model_registry.db`).

## Verification
Run the Phase 5 test suite:
```bash
uv run pytest tests/test_learning_phase5.py
```
Tests verify Elo mathematics, curriculum advancement, opponent sampling distributions, style metric bounds, and registry rollback behavior.
