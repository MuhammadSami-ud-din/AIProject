# Shield Wall - Step 2: Balance Controls & Counterplay

## Overview
All Shield Wall balance parameters are centralized in `backend/engine/shield_config.py` as a frozen dataclass `ShieldBalance`.

## Anti-OP Counterplay Rules
1. **Throws & Grabs**: Ignore shields completely, remove the active shield ("THROW THROUGH!"), and grab the defender.
2. **Heavy Attacks**: Deal **2x damage** to shields (2.5x for Crimson) and inflict **15% chip damage** through the shield (0% for light strikes).
3. **Overheads & Jump-ins**: Arc over the 130 px standing shield height and hit the defender directly.
4. **Attack Self-Drain**: Attacking while a shield is active drains **3 HP** per attack from the shield.
5. **Turtle Penalty**: Shield energy regen (8/sec) halts completely while blocking with an active shield.
6. **Cooldown & Cost**: 35/100 energy cost, 3.0s duration, and 6.0s cooldown make back-to-back shields impossible.

## Character Balance Tweaks
- **Steel**: Shield HP x1.3 (defensive anchor).
- **Crimson**: Duration x0.7, Heavy attacks deal x2.5 damage vs shields.
- **Shadow**: Startup reduced to 5 frames, Shield HP x0.7.
- **Golden**: Standard baseline values.
