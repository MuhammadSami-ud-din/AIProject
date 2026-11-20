# Shield Wall - Step 4: HUD, Visuals & AI Support

## HUD & Visuals (`frontend/draw_shield_wall.py`)
- **Shield Panel**: Rendered in the owner's signature color (Gold, Crimson, Steel Blue, Shadow Purple) with crack overlays at `<= 66%` and `<= 33%` HP and a miniature HP bar directly above the panel.
- **Energy & Cooldown**: Shield energy bar rendered directly beneath each fighter's health bar alongside a cooldown ring timer icon.
- **Feedback Banners**: Displays `"SHIELD UP!"`, `"SHIELD BREAK!"`, and `"THROW THROUGH!"`.

## AI & Observation (`backend/ai/shield_ai.py`, `observation.py`)
- **Observation**: Tracks `my_shield_wall_up`, `enemy_shield_wall_up`, `my_shield_wall_hp`, `my_shield_energy`, `my_shield_cooldown`, and masks shield actions via `obs.can_use_shield()`.
- **Personalities**:
  - **Steel**: Deploys front shields to absorb pressure and set up punishes.
  - **Shadow**: Deploys back shields near corners/walls to prevent traps.
  - **Crimson**: Rarely shields; aggressively counters enemy shields with Throws and Heavy strikes.
  - **Golden**: Raises shields when predicting incoming attacks.
- **Difficulties**: Scales from wasteful/random on `LOW` to optimal threat detection, throw-throughs, and break punishes on `HIGH`/`HELL`.
