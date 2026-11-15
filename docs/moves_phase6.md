# Arena-AI Phase 6: Polish, VFX, Training Mode, Move List & Matchup Balance

## 1. Overview

Phase 6 delivers visual impact, training tools, accessibility, and competitive balance to Arena-AI:
- **Super Flash & Screen Freeze**
- **Floating Combat Text Popups**
- **Dynamic Combo Counters**
- **In-Fight Training Mode (Hitboxes / Hurtboxes / Dummy Settings)**
- **Move List & Frame Data Screen**
- **Matchup Balance Verification**

---

## 2. Visual Effects & Feedback

### Super Flash Screen Darken
- When a fighter triggers a Super (`P`), the arena darkens with a semi-transparent black overlay for 15 frames while a golden "SUPER!" title pulses in the center.

### Popup Combat Text
Floating combat popups rise above fighters and fade away dynamically:
- **"COUNTER!"**: Bright Red (#FF4444) — awarded when hitting an attacker during their startup.
- **"PARRY!"**: Bright Cyan (#00E5FF) — awarded on frame-perfect 4-frame parries.
- **"GUARD BREAK!"**: Purple/Magenta (#E040FB) — awarded when depleting an opponent's guard meter.
- **"BURST!"**: Golden Yellow (#FFD700) — awarded on combo-breaking defensive bursts.
- **"TECH!"**: Emerald Green (#00E676) — awarded on successful 7-frame throw breaks.
- **"WALL BOUNCE!"** / **"GROUND BOUNCE!"**: Amber/Orange (#FFAB00 / #FF9100).

### Dynamic Combo Counter
- Shows consecutive hit counts and damage in real-time in the HUD (`X HITS!`).
- Pulses on each additional strike and fades smoothly once the combo ends.

---

## 3. Training Mode & Move List

### Training Mode (F1 / F2)
Accessible directly during matches:
- **`F1` Key**: Toggles hitbox and hurtbox visualization:
  - **Green Boxes**: Fighter body hurtboxes.
  - **Red Boxes**: Active attack strike hitboxes.
  - **Frame Advantage Tag**: Real-time `+` / `-` frame advantage numbers displayed directly above fighters.
- **`F2` Key**: Cycles Dummy AI behaviors:
  - `STAND`: Stationary target.
  - `CROUCH`: Low crouching target.
  - `BLOCK ALL`: Defends against all incoming attacks.
  - `RANDOM`: Unpredictable testing behavior.

### Move List Screen
- Accessible from the in-game Pause Menu (`Esc` -> "Move List") or main menu.
- Displays full frame data, damage in HP, inputs, startup times, on-block advantage, and special properties across all 5 categories: Universal, Crimson, Steel, Shadow, and Golden.

---

## 4. Matchup Balance Check

- Character baseline attributes are calibrated in [`backend/engine/moves.py`](file:///c:/Users/Muhammad%20Abdul%20Wahid/PycharmProjects/AIProject/backend/engine/moves.py) with symmetric scaling ratios.
- Automated balance verification tests simulate cross-character matchups to ensure no character dominates above a 60% win rate threshold in mirror and cross matches.
