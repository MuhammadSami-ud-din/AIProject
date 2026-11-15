# Arena-AI Phase 2: Combos, Cancels, Juggle Cap & Infinite Protection

## 1. Overview

Phase 2 builds upon the universal moves from Phase 1 by introducing full combo chain mechanics, cancel windows, air juggle caps, counter-hit bonuses, environmental bounces, and infinite combo protection.

All combo frame windows, cancel tags, and scaling parameters reside in [`backend/engine/moves.py`](file:///c:/Users/Muhammad%20Abdul%20Wahid/PycharmProjects/AIProject/backend/engine/moves.py).

---

## 2. Combo Strings & Cancels

### Canned Strings per Character
Each fighter archetype possesses 2 to 3 signature canned sequences. These continue into their follow-up strikes only if the previous hit connected (hit or block):
- **Crimson Brawler**:
  - `J -> J -> K` (Jab -> Jab -> Heavy Punch)
  - `U -> I` (Light Kick -> Heavy Kick)
  - `S+J -> S+U -> S+I` (Crouch Jab -> Crouch Kick -> Low Sweep)
- **Steel Guardian**:
  - `J -> U -> K` (Jab -> Light Kick -> Heavy Punch)
  - `S+J -> S+U` (Crouch Jab -> Crouch Kick)
  - `U -> I` (Light Kick -> Heavy Kick)
- **Shadow Striker**:
  - `S+J -> J -> U` (Crouch Jab -> Jab -> Light Kick)
  - `J -> J -> U` (Jab -> Jab -> Light Kick)
  - `U -> I` (Light Kick -> Heavy Kick)
- **Golden Tactician**:
  - `J -> U -> K` (Jab -> Light Kick -> Heavy Punch)
  - `S+U -> S+I` (Crouch Kick -> Low Sweep)
  - `J -> K` (Jab -> Heavy Punch)

### Cancel System
When a normal attack connects cleanly or is blocked, an attacker enters a hit-cancel window:
- **Chain (`CancelType.CHAIN`)**: Normal into Normal / canned string.
- **Special (`CancelType.SPECIAL`)**: Normal attacks cancel directly into signature specials.
- **Super (`CancelType.SUPER`)**: Specials and heavy attacks cancel into cinematic Super finishers.

---

## 3. Counter-Hits

Hitting an opponent while they are in the **startup frames** of an attack yields a **Counter-Hit**:
- **+50% Hitstun**: The victim is stunned for `int(base_hitstun * 1.5)` frames.
- **Interruption**: The victim's attack is immediately cancelled and snuffed out.
- **Bonus Meter**: The attacker receives an additional +5.0 super meter.
- **Visual Alert**: Triggers a floating red "COUNTER!" popup on screen.

---

## 4. Air Juggles & Environmental Bounces

### Juggle Cap (Max 4 Hits)
- Anti-air uppercuts (`S + K`) and launchers pop opponents up into the air.
- Attackers can juggle airborne defenders for up to **4 hits**.
- On the 4th air hit, the juggle cap is reached: the victim becomes invulnerable and immediately falls into a hard knockdown.

### Wall Bounce
- Striking an opponent with a heavy attack or launcher while they are near the arena wall (`x <= 35` or `x >= 765`) triggers a **Wall Bounce**.
- The victim rebounds off the arena barrier back into the air with +12 frames of hitstun, granting a free combo follow-up (limited to once per combo).

### Ground Bounce
- Heavy slam attacks (e.g. Crimson's Clinch Slam) slam the opponent against the arena floor, popping them back up for follow-up attacks (limited to once per combo).

---

## 5. Damage Scaling & Infinite Protection

### Combo Damage Scaling
Every consecutive hit in a combo scales damage down to prevent instant-kill touches:
- Hit 1: **100%**
- Hit 2: **90%**
- Hit 3: **80%**
- Hit 4: **70%**
- ...
- Minimum scaling clamp: **30%** (`max(0.30, 1.0 - hits * 0.10)`).

### Hitstun Decay (Infinite Protection)
To mathematically guarantee that no infinite loop can exist:
- Hitstun decays with each hit: `hitstun = max(4, base_hitstun - combo_hits * 2)`.
- As a combo extends, the attacker's recovery begins to exceed the victim's hitstun, causing all loops to naturally drop and allowing the defender to recover to neutral.
