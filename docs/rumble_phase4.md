# Arena Rumble - Phase 4: Destructible Crates & Arena Objects

## Overview
Phase 4 enriches the arena layout with symmetrical physical objects: destructible wooden crates, vertical jump pads, and concealed spike traps.

## Mechanics & Specifications
- **Destructible Wooden Crates**:
  - Dimensions: 36 px wide by 48 px tall.
  - Health: 25.0 HP.
  - Physics: Blocks horizontal ground movement; jumping over crates is possible.
  - Destruction: Damaged by melee attacks and projectiles; crumbles into debris at 0 HP.
  - Loot Drop: 50% probability to spawn standard ground loot upon destruction.
- **Kinetic Jump Pads**:
  - Dimensions: 52 px wide by 16 px tall.
  - Launch Force: Stepping onto the pad propels the fighter upward with vertical velocity (-18.0 px/frame).
  - Cooldown: 3.0s (180 frames) recharge timer between activations.
- **Spike Traps**:
  - Dimensions: 44 px wide by 12 px tall.
  - Pressure Plate Trigger: Arms when stepped on by a grounded fighter.
  - Trigger Delay: 0.5s (30 frames) warning window before spikes deploy.
  - Damage & Knockup: Deals 8.0 HP damage, launches the victim into air stun (15 frames hitstun).
  - Cooldown: 10.0s (600 frames) re-arm cooldown.
- **Arena Layouts**:
  - Predefined symmetrical placements tailored for 4 distinct environments:
    - Dojo: 2 crates, 2 jump pads, 1 center trap.
    - Rooftop: 4 crates, 1 center jump pad, 2 flank traps.
    - Colosseum: 2 crates, 2 jump pads, 2 inner traps.
    - Neon Alley: 3 crates, 2 flank jump pads, 1 center trap.

## Tests & Verification
- Unit test suite: `tests/test_rumble_phase4.py` (4 tests, all passing).
- Zero regression on Classic mode: arena objects list empty in classic.
