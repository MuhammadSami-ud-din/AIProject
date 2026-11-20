# Shield Wall - Step 1: Engine Mechanics

## Overview
Implemented the **Shield Wall** ability in `backend/engine/shield_wall.py` and `backend/engine/shield_state.py`. Both human and AI fighters can deploy a physical energy panel (30 px wide, 130 px tall) on either their **FRONT** (`Q` key) or **BACK** (`E` key).

## Key Mechanics
- **Front Shield**: Blocks melee strikes and projectiles coming from the front.
- **Back Shield**: Protects against cross-ups (e.g. Shadow Step) and corner/zone pushback.
- **Physical Wall**: Blocks horizontal movement for both fighters on the ground; jumping goes over.
- **Startup & Punishment**: Raising takes 8 frames (5 frames for Shadow). Taking a hit during startup cancels deployment. If a shield's HP reaches 0, it shatters and inflicts a **20-frame Shield Break stun** on its owner.
