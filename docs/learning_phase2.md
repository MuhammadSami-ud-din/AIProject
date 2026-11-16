# Learning Pipeline: Phase 2 — Reward Profiles & Personality Shaping

## Overview
Phase 2 shapes distinct fighting styles purely through the reinforcement learning reward function (`RewardCalculator` in `backend/learning/rewards.py`). Rather than hardcoding behavior rules, each personality receives bespoke incentives designed to promote authentic combat archetypes while deterring reward-hacking.

## Reward Structure

### 1. Shared Base Rewards & Penalties
- **Net Damage**: $+100 \times \Delta\text{Enemy HP} - 100 \times \Delta\text{My HP}$ (equivalent to $+1.0$ per 1 HP dealt, $-1.0$ per 1 HP taken).
- **Round Outcomes**: $+10.0$ for winning a round, $-10.0$ for losing a round.
- **Time Stalling Penalty**: $-0.005$ per frame to discourage passive stalling.
- **Whiff Penalty**: $-0.30$ when an attack completes without contacting or being blocked by the opponent.

### 2. Personality-Shaped Incentives
- **Crimson Brawler (Rushdown)**:
  - Advancing Pressure: $+0.20$ for moving forward or dashing.
  - Retreat Penalty: $-0.25$ for walking backward or backdashing.
  - Combo Strings: $+0.50 \times \text{combo\_count}$ for chaining consecutive hits.
- **Steel Guardian (Counter-Fighter)**:
  - Clean Blocks: $+0.80$ on absorbing attacks in high/low block.
  - Perfect Parry: $+2.50$ on successfully parrying within the 4-frame window.
  - Block Punish: $+1.50 \times \text{damage}$ for landing counter-hits within 30 frames of blocking.
  - Wild Whiff Penalty: $-0.60$ for reckless swinging.
- **Shadow Striker (Agile Hit-and-Run)**:
  - Preferred Spacing: $+0.25$ when maintaining distance between 180px and 320px.
  - Whiff Punish: $+1.60$ for punishing an opponent during their attack recovery.
  - Evade: $+0.80$ for successful evasive backdashes or shadow steps.
  - Cornered Penalty: $-0.50$ when trapped within 75px of the corner wall.
- **Golden Tactician (Adaptive Master)**:
  - Tactical Victory: $+3.0$ bonus on round wins.
  - Golden Read Counters: $+3.0$ on landing a counter through the read stance.
  - Clean Trades: $+0.20$ bonus on landing unreturned clean hits.

## Verification
Run the Phase 2 test suite:
```bash
uv run pytest tests/test_learning_phase2.py
```
Tests verify that all individual reward terms trigger under controlled scenarios and that cumulative breakdown totals balance.
