# Arena Rumble - Phase 2: Building (Cover Walls)

## Overview
Phase 2 introduces **Cover Walls**, enabling fighters to deploy physical cover blocks on the arena floor to block movement, absorb incoming projectiles, and trap or isolate opponents.

## Mechanics & Specifications
- **Build Energy**:
  - Starts with 3 charges at round start (max 3).
  - Passive recharge: +1 charge every 8.0s (480 frames).
- **Placement & Action.BUILD**:
  - B key triggers `Action.BUILD`.
  - Costs 1 charge immediately upon initiating placement.
  - 12-frame placement lock: fighter is vulnerable and cannot move or attack.
  - Spawns a vertical wall block: 40 px wide, 120 px tall, 30.0 HP, offset 40 px in front of the fighter.
- **Physical Collision & Destruction**:
  - Blocks horizontal movement on the ground for both fighters.
  - Jumping over walls is fully supported with airborne air-drift movement.
  - Destructible by melee attacks:
    - Light attacks deal 5.0 HP damage.
    - Heavy attacks deal 12.0 HP damage.
    - Power Fist buff boosts damage by +25%.
  - Visual crack stages:
    - Minor cracks at <= 66% HP (20.0 HP).
    - Heavy structural cracks at <= 33% HP (10.0 HP).
  - Completely removed upon reaching 0 HP.
- **Placement Restrictions & Limits**:
  - Maximum 2 walls per fighter on screen; building a 3rd removes the oldest wall.
  - Cannot build inside the opponent (minimum separation enforced).
  - Cannot build overlapping another wall or outside the safe zone.

## Tests & Verification
- Unit test suite: `tests/test_rumble_phase2.py` (7 tests, all passing).
- Zero regression on Classic mode: build charges and keys ignored in classic.
