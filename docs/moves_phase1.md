# Arena-AI Phase 1: Normals, High/Low, Throws & Defense

## 1. Overview

Phase 1 introduces the core fighting game move engine to Arena-AI. All moves are completely original and defined in a single source of truth data file: [`backend/engine/moves.py`](file:///c:/Users/Muhammad%20Abdul%20Wahid/PycharmProjects/AIProject/backend/engine/moves.py).

Health is stored internally as `0.0` to `1.0` and shown on screen as **100 HP**. Damage in the data file is specified directly in HP (e.g. `2 HP = 0.02` health).

---

## 2. Universal Move List & Frame Data Table

| Move | Input | Damage (HP) | Startup | Active | Recovery | On Block | Hit Level | Reach (px) | Effect / Properties |
|---|---|---|---|---|---|---|---|---|---|
| **Jab** | `J` | 2.0 | 3f | 2f | 7f | **+2** | MID | 55.0 | Fast combo starter. Plus on block. |
| **Heavy Punch** | `K` | 8.0 | 10f | 4f | 18f | **-5** | MID | 85.0 | Hard hit, staggers on hit. |
| **Light Kick** | `U` | 4.0 | 5f | 3f | 9f | **0** | MID | 70.0 | Mid-range check. Neutral on block. |
| **Heavy Kick** | `I` | 10.0 | 12f | 4f | 22f | **-8** | MID | 105.0 | Longest reach normal attack. |
| **Low Sweep** | `S + I` | 6.0 | 8f | 3f | 20f | **-12** | LOW | 80.0 | Hits LOW; trips opponent into a knockdown. |
| **Overhead Strike** | `Forward + K` | 7.0 | 14f | 3f | 18f | **-4** | HIGH | 75.0 | Hits HIGH; crushes crouching defenders. |
| **Crouching Jab** | `S + J` | 2.0 | 4f | 2f | 8f | **+1** | LOW | 50.0 | Fast crouching poke. Hits LOW. |
| **Crouching Kick** | `S + U` | 3.5 | 6f | 3f | 11f | **-2** | LOW | 68.0 | Low poke under standing guards. |
| **Jump Punch** | `In Air + J` | 4.0 | 4f | 6f | 8f | **+2** | HIGH | 50.0 | Aerial attack; hits HIGH. |
| **Jump Kick** | `In Air + U/I` | 6.0 | 7f | 6f | 10f | **0** | HIGH | 65.0 | Long aerial kick; hits HIGH. |
| **Anti-Air Uppercut** | `S + K` | 8.0 | 6f | 4f | 22f | **-10** | MID | 65.0 | Upward strike; launches airborne foes. |
| **Normal Throw** | `J + U` | 10.0 | 4f | 2f | 16f | **Unblockable** | THROW | 38.0 | Beats blocking. 7-frame tech window. |
| **Backdash** | Double-tap `A/D` (away) | 0.0 | 0f | 4f | 12f | **0** | MID | — | Invulnerable for the first 4 frames. |

---

## 3. Combat Rules & Mechanics

### Guard & Blocking (High / Low / Mid)
- **MID Attacks** (Jab, Heavy Punch, Light Kick, Heavy Kick, Anti-Air):
  - Can be blocked either standing (`L`) or crouching (`S + L`).
- **HIGH Attacks / Overheads** (Overhead Strike, Jump Punch, Jump Kick):
  - **Must be blocked standing** (`L`).
  - Hits crouching opponents cleanly even if they hold low block.
- **LOW Attacks** (Low Sweep, Crouching Jab, Crouching Kick):
  - **Must be blocked crouching** (`S + L`).
  - Hits standing opponents cleanly even if they hold high block.
- **THROWS** (`J + U`):
  - Completely bypass standard blocking. If the opponent is turtling in guard, a throw connects.
  - **Loses to attack startup**: if the defender is in the startup of any attack, the throw fails and is beaten by the attack.
  - **Throw Tech (Break)**: when grabbed, the victim has **7 frames** to input `Throw` (`J + U`). Teching pushes both fighters apart with zero damage dealt.

### Simultaneous Trades
- If both fighters have active attack hitboxes connect on the exact same frame, **both take damage and hitstun simultaneously**. Neither hit is discarded.

### Pushback
- Every connected hit and blocked attack pushes the two fighters apart.
- When a defender is pinned against an arena wall, the remaining pushback displacement naturally transfers back to the attacker.

### 6-Frame Input Buffer
- Inputs pressed up to **6 frames early** (while finishing recovery, hitstun, or blockstun) are stored in an input buffer and automatically execute on the very first frame the fighter becomes actionable.

---

## 4. Human Controls

- **Movement**:
  - `A` / `D`: Walk left / right (automatically maps to Forward / Back based on where the opponent is)
  - Double-tap `A` or `D`: Dash forward or Backdash (first 4 frames of backdash are invulnerable)
  - `W`: Jump
  - `S`: Crouch
- **Attacks & Defense**:
  - `J`: Light Punch (Jab)
  - `K`: Heavy Punch (`Forward + K` = Overhead Strike)
  - `U`: Light Kick
  - `I`: Heavy Kick
  - `S + J`: Crouching Jab (hits low)
  - `S + U`: Crouching Kick (hits low)
  - `S + I`: Low Sweep (hits low, knocks down)
  - `S + K`: Anti-Air Uppercut
  - `L`: High Block (standing)
  - `S + L`: Low Block (crouching)
  - `J + U`: Throw (unblockable grab)
