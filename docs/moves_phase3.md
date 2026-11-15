# Arena-AI Phase 3: Meters & Defensive Mechanics

## 1. Overview

Phase 3 introduces the resource economy to Arena-AI: the **Super Meter (0 to 100)**, the **Guard Meter (0 to 100)** with **Guard Break**, the **Fury** comeback mechanic, frame-perfect **Parry**, and defensive **Burst**.

All numerical costs, gains, and timing windows are centralized in [`backend/engine/moves.py`](file:///c:/Users/Muhammad%20Abdul%20Wahid/PycharmProjects/AIProject/backend/engine/moves.py).

---

## 2. Super Meter (0 – 100)

Both fighters track a Super Meter displayed beneath their guard bars in the HUD.

### Meter Generation
- **Attacking on Hit**: +5.0 to +12.0 meter depending on the move.
- **Attacking on Block**: +2.0 to +4.0 meter.
- **Taking Damage**: +3.0 to +4.0 meter.
- **Counter-Hits & Whiff Punishes**: Extra +5.0 meter.
- **Perfect Parry**: +12.0 meter.

### Meter Spending
- **Enhanced Specials / EX Attacks (e.g. Shield Bash)**: Costs 25 meter.
- **Defensive Burst**: Costs 50 meter.
- **Super Finisher**: Costs 100 meter (discounted to 60 meter in Fury).

---

## 3. Guard Meter & Guard Break

Turtling indefinitely behind high or low block is impossible thanks to the Guard Meter.
- Both fighters start with **100 Guard Points**.
- Each blocked attack drains approximately 18 guard points.
- Guard meter automatically recharges (+0.25 points/frame) when not holding block.

### Guard Break
- When a fighter's guard meter reaches **0**:
  - The defender suffers a **Guard Break**!
  - The defender is completely stunned for **40 frames**, unable to act or block.
  - Guard meter resets to 50 points.
  - A purple "GUARD BREAK!" notification flashes on screen.

---

## 4. Fury Mode

When a fighter's health drops below **25%** (`health < 0.25`):
- The fighter enters **Fury Mode** (indicated by glowing red outlines and a `[FURY!]` tag in the HUD).
- **+10% Damage Boost**: All attacks deal 10% more damage (`damage * 1.10`).
- **Super Discount**: Super moves unlock and can be executed at **60 Meter** instead of 100.

---

## 5. Perfect Parry

- **Input**: Pressing Block (`L` or `S + L`) within **4 frames** before an incoming attack connects.
- **Effect**:
  - **Zero Damage**: Defender absorbs the strike with 0 damage.
  - **Zero Blockstun**: Defender is instantly actionable.
  - **Attacker Staggered**: The attacker is put into 22 frames of stagger recovery.
  - **Resource**: Defender gains +12 bonus super meter.
  - **Visual Alert**: Triggers a bright cyan "PARRY!" popup.

---

## 6. Defensive Burst

- **Input**: Press `L + O` simultaneously (or `Action.BURST`) while trapped in hitstun.
- **Cost**: 50 Super Meter.
- **Limitation**: **Once per round**.
- **Effect**:
  - Instantly clears hitstun and breaks the opponent's combo.
  - Unleashes a massive golden blast wave that pushes the attacker back 140 pixels and staggers them for 20 frames.
  - Triggers a golden "BURST!" popup.
