# Arena Rumble - Phase 6: Mode Toggle, Controls & Stats Polish

## Overview
Phase 6 delivers user interface integration, selective mechanic configuration, HUD overlays, post-fight rumble metrics, and database persistence.

## Mechanics & Specifications
- **Main Menu & Mode Selection**:
  - Dedicated "Arena Rumble" mode entry point on the main menu.
  - Submenu allowing full customization of active mechanics:
    - Shrinking Zone (The Squeeze) [Toggle On/Off]
    - Cover Walls & Building [Toggle On/Off]
    - Ground Loot & Supply Drops [Toggle On/Off]
    - Arena Objects (Crates, Pads, Traps) [Toggle On/Off]
    - Arena Selection (Dojo, Rooftop, Colosseum, Neon Alley)
    - Auto-Pickup vs Manual ('E' key) [Toggle]
- **Controls & Keybindings**:
  - `B` key: Place cover wall (`Action.BUILD`).
  - `E` key: Pick up ground loot or supply drop (`Action.PICKUP`).
  - Move list screen updated with dedicated "Rumble Mechanics" tab.
- **In-Fight HUD Overlay**:
  - Top center: Shrinking zone timer, stage counter, and "ZONE CLOSING" flashing banner.
  - Health bar: Layered cyan shield bar overlaid on top of the health bar.
  - Build charges: 3 cyan diamond icons showing ready build energy and recharge progress.
  - Active buffs: Badges for Speed Boots (+30% speed) and Power Fist (+25% damage) with countdown timers.
  - Top right: Real-time kill feed and event banner logging walls built, items collected, crate breaks, and zone alerts.
- **Post-Fight Stats & Database**:
  - Results screen displays: Walls Built, Walls Broken, Items Collected, and Zone Damage Taken.
  - Results SQLite database records the `mode` column ('classic' vs 'rumble') and supports filtered historical queries.

## Tests & Verification
- Unit test suite: `tests/test_rumble_phase6.py` (4 tests, all passing).
- Input handler, results database, and frontend screens fully integrated.
