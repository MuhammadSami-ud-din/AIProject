# Arena Rumble - Phase 3: Loot & Supply Drops

## Overview
Phase 3 introduces procedural battle-royale style loot pickups and timed celestial supply drops, creating high-stakes map objectives inside the shrinking safe zone.

## Mechanics & Specifications
- **Ground Loot Spawns**:
  - Spawn interval: Every 12.0s to 18.0s (720 to 1080 frames).
  - Ground limit: Strict maximum of 2 active items on the arena floor simultaneously.
  - Placement: Always spawned securely inside the current safe zone, avoiding existing walls.
- **Original Loot Types & Effects**:
  1. **Medkit**: Instantly restores +25.0 HP (capped at max starting HP 1.0).
  2. **Shield Cell**: Grants +25.0 Shield HP. Shield absorbs damage before health, decaying at 1 HP per 3.0s (180 frames).
  3. **Meter Orb**: Grants +30.0% super meter instantly.
  4. **Build Kit**: Grants +2 build charges (allows exceeding the standard cap by 1, up to 4 charges total).
  5. **Speed Boots**: Grants a +30% movement speed multiplier for 6.0s (360 frames).
  6. **Power Fist**: Grants a +25% attack damage multiplier for 5.0s (300 frames).
- **The Golden Supply Drop**:
  - Drops from the sky when 30.0s remain in the round (frame 5400).
  - Takes 4.0s (240 frames) to descend slowly to the floor, casting a dynamic landing shadow.
  - Contains game-changing rare supply items:
    - **Big Medkit**: Restores +50.0 HP.
    - **Overcharge**: Instantly grants +50% meter and +3 build charges.
- **Collection**:
  - Walk-over auto-pickup by default, or manual pickup via Action.PICKUP ('E' key).

## Tests & Verification
- Unit test suite: `tests/test_rumble_phase3.py` (7 tests, all passing).
- Zero regression on Classic mode: loot timers and pickups disabled.
