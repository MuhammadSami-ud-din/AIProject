# Arena Rumble - Phase 1: The Squeeze (Shrinking Zone)

## Overview
Phase 1 introduces **The Squeeze**, an original shrinking energy barrier mechanic for 2D fighting games. The barrier closes in from both arena boundaries inward, forcing fighters into an increasingly claustrophobic combat pocket.

## Mechanics & Specifications
- **Timing & Stages**:
  - 4 closing stages total.
  - Each stage begins with a 20.0s pause (1200 frames).
  - A flashing warning appears 5.0s before closing ("ZONE CLOSING" with a ghost trajectory line).
  - The barrier moves inward over 10.0s (600 frames).
  - Total reduction: arena width shrinks from 800px down to 35% (280px safe zone width).
- **Physical Push & Damage**:
  - Inward push force: 4.0 px/frame prevents fighters from clipping outside.
  - Outside zone damage scales per stage:
    - Stage 1: 2.0 HP/s (0.033 HP/f)
    - Stage 2: 3.5 HP/s (0.058 HP/f)
    - Stage 3: 5.0 HP/s (0.083 HP/f)
    - Stage 4: 7.5 HP/s (0.125 HP/f)
- **Object Crumbling**:
  - Cover walls trapped outside the safe barrier crumble at 3.0 HP/s until destroyed.
- **Victory Condition**:
  - If the round timer expires, the fighter with higher HP wins as standard.

## Tests & Verification
- Unit test suite: `tests/test_rumble_phase1.py` (7 tests, all passing).
- Zero regression on Classic mode: `ModeRules.classic()` completely disables all zone logic.
