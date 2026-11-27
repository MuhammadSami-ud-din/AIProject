# Learning Pipeline: Phase 2 — Reward Profiles & Personality Shaping

## Overview
Phase 2 shapes distinct fighting styles purely through the reinforcement learning reward function (`RewardCalculator` in `backend/learning/rewards.py`). Rather than hardcoding behavior rules, each personality receives bespoke incentives designed to promote authentic combat archetypes while deterring reward-hacking.

## Reward Structure

### 1. Shared Base Rewards & Penalties
- **Net Damage**: $+100 \times \Delta\text{Enemy HP} - 100 \times \Delta\text{My HP}$ (equivalent to $+1.0$ per 1 HP dealt, $-1.0$ per 1 HP taken).
- **Round Outcomes**: $+10.0$ for winning a round, $-10.0$ for losing a round.
- **Time Stalling Penalty**: $-0.005$ per frame to discourage passive stalling.
- **Whiff Penalty**: $-0.30$ when an attack completes without contacting or being blocked by the opponent.

### Anti-reward-hacking rules
- The engine reports `last_hit_effect` ("block", "hit", "parry", "counter", "read", ...) and `read_success` as **one-frame events**. `ArenaEnv.step` passes every simulated frame of a macro-step to `RewardCalculator.observe_frame`, and event bonuses are **edge-triggered** (paid only on the frame the event appears), so a one-frame event is never missed and a sticky value is never paid twice. (Before: Steel earned +2.5 on every step after its first parry, Golden +3 every step after a read.)
- Golden's read uses the engine's `"read"` effect (legacy `"golden_read"` still accepted).
- Crimson is no longer paid per FORWARD step (that was farmable by walking into a wall); its aggression bonus pays for results, and the promotion style gate measures the same thing.
- `RewardCalculator(personality, use_personality_bonus=False)` keeps only the shared terms (used by the ablation).

### 2. Personality-Shaped Incentives
- **Crimson Brawler (Rushdown)**:
  - Damage aggression: $+0.50$ per 1% HP dealt (on top of the shared damage term).
  - Pressure: $+0.40$ each time the enemy is forced into blockstun while Crimson is within 140 px.
  - Retreat Penalty: $-0.25$ for walking backward or backdashing.
  - Combo Strings: $+0.50 \times \text{combo\_count}$ for chaining consecutive hits.
- **Steel Guardian (Counter-Fighter)**:
  - Clean Blocks: $+0.80$ per block event (engine "block" effect or blockstun starting).
  - Perfect Parry: $+2.50$ per parry event.
  - Block Punish: $+1.50 \times \text{damage}$ for landing counter-hits within 30 frames of blocking.
  - Wild Whiff Penalty: $-0.60$ for reckless swinging.
- **Shadow Striker (Agile Hit-and-Run)**:
  - Preferred Spacing: $+0.25$ when maintaining distance between 180px and 320px.
  - Whiff Punish: $+1.60$ for punishing an opponent during their attack recovery.
  - Evade: $+0.80$ for successful evasive backdashes or shadow steps.
  - Cornered Penalty: $-0.50$ when trapped within 75px of the corner wall.
- **Golden Tactician (Adaptive Master)**:
  - Tactical Victory: $+3.0$ bonus on round wins.
  - Golden Read Counters: $+3.0$ per "read" event (or `read_success` turning true).
  - Clean Trades: $+0.20$ bonus on landing unreturned clean hits.

## Verification
Run the Phase 2 test suite:
```bash
uv run pytest tests/test_learning_phase2.py
```
Tests verify that all individual reward terms trigger under controlled scenarios and that cumulative breakdown totals balance.
