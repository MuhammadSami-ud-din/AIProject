# Shield Wall - Step 3: In-Game Player Balance Controls & DB Persistence

## Overview
Added a dedicated **Shield Wall Balance** submenu inside Settings (`frontend/screens.py`), allowing full customization and handicap controls.

## Features
- **Toggle**: Enable or disable Shield Wall cleanly; Classic rules remain untouched when OFF.
- **Presets**: `Weak`, `Normal`, `Strong`, and `Custom`.
- **Custom Sliders** (safely clamped in `shield_config.py`):
  - Shield HP: `10 - 60`
  - Duration: `1.0 - 6.0 s`
  - Cooldown: `3.0 - 15.0 s`
  - Energy Cost: `20 - 60`
  - Energy Regen: `2 - 15 / s`
- **Handicap Option**: `"Same for both fighters"` toggle (default ON). Turning it OFF reveals independent sliders for P1 and P2.
- **Database Tracking**: `backend/data/results_db.py` records `shield_enabled`, `shield_preset`, and `shield_balance_json` with every match in `results.db`.
