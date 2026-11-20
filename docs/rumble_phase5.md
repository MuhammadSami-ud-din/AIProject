# Arena Rumble - Phase 5: AI Support for Rumble

## Overview
Phase 5 empowers all AI fighters (Crimson, Steel, Shadow, Golden) to perceive and actively exploit rumble mechanics through specialized macro-actions and personality heuristics.

## Mechanics & Specifications
- **Perception & State Observation**:
  - Observation extended with: `is_rumble`, `zone_left`, `zone_right`, `zone_time_to_close`, `zone_is_closing`, `zone_is_warning`, `my_build_charges`, `my_shield`, `my_speed_boost`, `my_power_boost`, `nearest_item_type`, `nearest_item_dist`, `nearest_item_dir`, `wall_between`, `wall_between_hp`, `nearest_crate_dist`, `nearest_pad_dist`, `nearest_trap_dist`.
- **Rumble Macro-Action Priorities**:
  1. **Zone Safety (Highest Priority)**:
     - Detects when outside the energy barrier or within 45px of a closing edge.
     - Forces immediate movement toward the center of the safe zone.
  2. **Wall Destruction**:
     - When a wall separates fighters, attacks with heavy/light strikes to clear the path.
  3. **Cover Building**:
     - Deploys walls defensively when at low health (< 35%), at distance, or under pressure.
  4. **Item Navigation**:
     - Navigates toward high-value items and contested supply drops when safe.
- **Personality Adaptations**:
  - **Crimson**: Aggressive wall crusher, rushes crates and drop zones.
  - **Steel**: Builds protective bastions, defends the center of the safe zone.
  - **Shadow**: Utilizes jump pads for aerial escapes, baits opponents into spike traps.
  - **Golden**: Balanced tactician, snatches health items and deploys tactical cover.
- **Difficulty Attentiveness Scaling**:
  - LOW: 35% attentiveness (often ignores zone warnings and items).
  - MEDIUM: 65% attentiveness.
  - HIGH: 90% attentiveness.
  - HELL: 99% attentiveness (near-instant tactical reactions).

## Tests & Verification
- Unit test suite: `tests/test_rumble_phase5.py` (6 tests, all passing).
- Zero regression on Classic mode: `evaluate_rumble_macro` returns None immediately when `is_rumble=False`.
