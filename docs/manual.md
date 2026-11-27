# Arena-AI: Complete Game Manual & Combat Guide

Welcome to **Arena-AI**, a competitive, 2D deterministic fighting game combining classic frame-based martial arts combat with autonomous AI agents. This manual covers all rules, controls, combat systems, meters, character movesets, and training features.

---

## 1. Match Rules & Structure

- **Arena**: 800 pixels wide, bounded by walls on both sides. Hard wall collisions trigger a **Wall Bounce**, allowing follow-up juggle attacks.
- **Match Format**: Best of 3 rounds. The first fighter to win 2 rounds wins the match.
- **Round Duration**: 60 seconds (3,600 frames at 60 FPS).
- **Victory Conditions**:
  - **Knockout (KO)**: Reduce the opponent's health to 0 HP.
  - **Timeout**: The fighter with more remaining HP wins when the clock expires.
  - **Draw**: If both fighters have identical HP at timeout, a draw is awarded (neither player receives a round point). If no fighter reaches 2 wins after 3 rounds, the fighter with the most round wins claims the match.

---

## 2. Complete Controls Reference

All keys are rebindable in the Settings menu. The standard defaults are:

### Movement & Agility
| Input | Action | Details |
| :--- | :--- | :--- |
| `A` / `D` | **Walk Backward / Forward** | Standard ground movement. |
| **Double-tap** `D` (toward) | **Forward Dash** | A burst of speed (about 3x walk speed) that decelerates over 14 frames (~95 px). Attacking, blocking or jumping ends the dash early. |
| **Double-tap** `A` (away) | **Backdash** | A committed 16-frame move that travels back ~90 px with a decelerating burst and grants **4 frames of full invulnerability** for whiff punishing. |
| `W` | **Jump** | Parabolic jump arc (40 frames, apex ~110 px). Holding `A`/`D` in the air gives small air control (half walk speed; full speed in Rumble / Shield Wall). |
| `S` | **Crouch** | Shrinks the hurtbox (60 px instead of 100 px) so high-aimed attacks such as Heavy Kick whiff; enables crouching normals and low blocking. |

### Universal Attacks & Normals
| Input | Attack | Damage | Startup | On block | Properties |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `J` | **Light Punch (Jab)** | 2 HP | 3 frames | +2 | Fastest move in the game; primary combo starter. |
| `K` | **Heavy Punch** | 8 HP | 10 frames | -5 | High hitstun. |
| `U` | **Light Kick** | 4 HP | 5 frames | 0 | Safe mid-range poke. |
| `I` | **Heavy Kick** | 10 HP | 12 frames | -8 | Longest normal; aimed **high** — whiffs on crouching opponents; wall bounce. |
| `D + K` | **Overhead Strike** | 7 HP | 14 frames | -4 | Hits **HIGH**: must be blocked standing. |
| `S + J` | **Crouching Jab** | 2 HP | 4 frames | +1 | Hits **LOW**. |
| `S + U` | **Crouching Kick** | 3.5 HP | 6 frames | -2 | Hits **LOW**. |
| `S + I` | **Low Sweep** | 6 HP | 8 frames | -12 | Hits **LOW**; knocks down. Lows hug the floor and whiff on airborne opponents. |
| `S + K` | **Anti-Air Uppercut** | 8 HP | 6 frames | -10 | Reaches high and **beats jump attacks** during its startup/active frames; launches. |
| `J` / `K` / `U` / `I` in the air | **Jump Punch / Kick** | 4–6 HP | 4–7 frames | +2 / 0 | Hits **HIGH**; reaches down from the jumper's height. |
| `J + U` | **Normal Throw** | 10 HP | 4 frames | Unblockable | Beats standing and crouching guard; loses to attack startup; misses airborne opponents. |

(Damage values are the base values; Crimson deals 1.2x, Shadow 0.85x. Startup counts the first active frame.)

### Defensive Actions
| Input | Action | Details |
| :--- | :--- | :--- |
| `L` (hold) | **Standing High Block** | Blocks **High** and **Mid** attacks. Vulnerable to Low attacks and Throws. |
| `S + L` (hold) | **Crouching Low Block** | Blocks **Low** and **Mid** attacks. Vulnerable to Overheads and Throws. |
| `L` (fresh press 1–4f before hit) | **Perfect Parry** | Negates **100% of damage**, staggers the attacker for 22 frames and grants **+12 Super Meter**. Works against projectiles too (no stagger). A press that does not parry starts a **24-frame parry lockout**: during it a new press still blocks but cannot parry, so mashing block does not parry everything. |
| `J + U` (within 7f) | **Throw Tech** | Press Throw within 7 frames of being grabbed to break free; both fighters are pushed apart. Two throws on the same frame also clash as a tech. |
| `L + O` (while being hit) | **Burst** | Costs **50 Super Meter**; breaks out of an enemy combo, pushes the attacker 140 px away and staggers them for 20 frames. Once per round. |

You **cannot block or parry during your own move** (startup, active or recovery frames).
You **cannot be thrown** for 10 frames after waking up, while in hitstun/blockstun, and for 5 frames after leaving hitstun/blockstun.

### Special Moves & Super Attacks
| Input | Move slot | Engine action |
| :--- | :--- | :--- |
| `O` | **Special Neutral** | `SPECIAL_NEUTRAL` |
| `D + O` (toward) | **Special Forward** | `SPECIAL_FORWARD` |
| `A + O` (away) | **Special Back** | `SPECIAL_BACK` |
| `S + O` | **Special Down** | `SPECIAL_DOWN` |
| `P` | **Super Move** | `SUPER` — 100 Meter *(60 in Fury)*; triggers a **15-frame cinematic freeze**. Buttons pressed during the freeze are buffered and come out on the first frame after it. |

Each character's moves for these slots are listed in section 5.

---

## 3. Combat Mechanics

### Height: Standing, Crouching and Airborne
- Every fighter has a hurtbox height: **standing 100 px**, **crouching 60 px**, **airborne 80 px** starting at the current jump height.
- Every move has a vertical hitbox: lows reach 0–30 px (they whiff on jumpers), mids/overheads 10–120 px, Heavy Kick 65–140 px (whiffs on crouchers), anti-airs 40–220 px, jump attacks reach 60 px below the jumper.
- The Energy Dart flies at 35–65 px: jump over it.

### High, Low, and Mid Guard Rules
- **High Attacks** (Overheads, aerial strikes): Must be blocked standing (`L`). Crouching guard will be hit.
- **Low Attacks** (Sweeps, crouching kicks): Must be blocked crouching (`S + L`). Standing guard will be hit.
- **Mid Attacks** (Jabs, punches, basic kicks): Can be blocked either standing or crouching.
- **Throws**: Unblockable by both standing and crouching guards. Throws beat blocking, but lose to any attack active during throw startup.

### Frame Advantage & Recovery
- **Startup**: The frames before a move hits (the listed number includes the first active frame). You cannot block during startup, active or recovery frames.
- **Active**: The frames during which the attack's hitbox can deal damage.
- **Recovery**: The vulnerable frames after the attack finishes. If an attack misses (whiffs), you can be punished!
- **Plus on Block**: A move like Jab (+2 on block) leaves the attacker able to act 2 frames before the defender recovers from blockstun. The engine's measured advantage always equals the listed value (this is tested by simulation).

### Counter-Hits
Striking an opponent during the startup frames of their attack scores a **Counter-Hit**. A counter-hit displays `"COUNTER!"` on screen and increases hitstun by **+50%**, opening up unique combo links that are normally impossible.

### Combos, Cancels, and Wall Bounces
- **Strings**: Characters possess built-in chain combos (e.g. Jab → Jab → Heavy) that automatically connect if the previous strike landed.
- **Cancels**: Normals can be cancelled into Special Moves during their active/cancel windows. Special Moves can be cancelled directly into Super Moves.
- **Air Juggle Cap**: Airborne juggles are strictly capped at **4 hits**. On the 4th air hit, the victim drops into a hard knockdown (cannot be hit while down; 6 frames of strike invulnerability on wakeup).
- **Wall Bounce**: Knocking an opponent hard into the arena corner triggers a wall bounce, allowing an immediate follow-up attack.
- **Damage Scaling & Infinite Protection**: Every extra hit in a combo scales incoming damage: 100% → 90% → 80% ... down to a 30% floor. Hitstun decays as combo length grows to prevent infinite loops.

---

## 4. Meters & Resources

### Guard Meter & Guard Break
- Guard Meter starts at 100.
- Every blocked melee hit drains **18** guard (Golden in Guard stance: ~11); every blocked projectile drains **10**.
- Guard meter regenerates by 0.25 per frame (15 per second) whenever the fighter is not holding block.
- **Guard Break**: If the guard meter hits 0 (from melee **or** projectiles), the defender is **stunned for 40 frames** (`"GUARD BREAK"`), takes the hit's full damage and is defenseless to a full combo. The meter then refills to 50.
- Blocked hits deal chip damage: 10% of the hit (Steel 5%; Golden in Guard stance half of normal).

### Super Meter (0–100)
- Built by landing attacks (+4–20 depending on the move, +5 on a counter-hit), blocked attacks (+1.5–4), taking a hit (+3), blocking (+1.5), landing a throw (+12) and Perfect Parries (+12).
- **25 Meter**: Steel Guardian's Shield Bash costs 25 meter.
- **50 Meter**: Spend on **Burst** (`L + O`) while trapped in hitstun to end the combo and reset the fight to neutral.
- **100 Meter**: Spend to execute your character's ultimate **Super Move** (`P`).

### Fury Mode (< 25% Health)
When a fighter's health drops below 25 HP:
1. An animated **FURY** indicator lights up on their HUD.
2. Clean hits deal **+10% bonus damage** (applied on top of combo scaling; chip damage is unchanged).
3. Super Move cost drops from 100 meter to **60 meter**, giving fighters dramatic comeback potential!

---

## 5. Character Movesets

### Crimson Brawler (Archetype: Rushdown Berserker)
High-damage fighter (1.2x damage, 0.9x reach) specializing in forward pressure and corner trapping.
- `O`: **Rising Uppercut** — Anti-air launcher (beats jump attacks, reaches high). 11 HP, 5f.
- `D + O`: **Crimson Rush** — Long-reach (115 px) rush punch. 12 HP, 8f, -6 on block.
- `A + O`: **Berserker Charge** — Charge with 1 hit of armor (absorbs one attack, taking 50% damage, without flinching). 9 HP, 11f.
- `S + O`: **Clinch Slam** — Short-range command grab that ground-bounces the opponent for a follow-up. 14 HP, 7f.
- `P`: **Blood Fury** — Super. 32 HP, 5f, knockdown.

### Steel Guardian (Archetype: Counter & Defense)
Sturdy fighter with projectile reflection and counter stances. *Passive*: takes 50% less chip damage when blocking.
- `O`: **Punisher Grip** — Slow command grab that beats blocking. 16 HP, 14f.
- `D + O`: **Shield Bash** — Long-reach bash; costs **25 meter**. 8 HP, 7f.
- `A + O`: **Reflector** — Barrier that reflects projectiles back at the sender (new owner: Steel).
- `S + O`: **Iron Wall** — Counter stance; if struck during it, Steel absorbs the hit and strikes back (16 HP counter).
- `P`: **Fortress Crush** — Counter super; triggers when struck during its stance (35 HP counter).

### Shadow Striker (Archetype: High-Mobility Hit-and-Run)
Agile fighter (0.85x damage, 1.15x reach, 1.3x speed).
- `O`: **Energy Dart** — Horizontal projectile (6 HP base, 12 px/frame). Limits: one in flight, 2.5 s cooldown, 4 per round. Can be jumped over.
- `D + O`: **Shadow Step** — Ground-only teleport: slips behind a close opponent (within 140 px) or steps 75 px forward, with 6 invulnerable frames.
- `A + O`: **Feint Strike** — Fake strike (no hitbox) that can chain into normals.
- `S + O`: **Phantom Kick** — Low-hitting kick. 11 HP, 6f.
- `P`: **Vanishing Arts** — Super. 28 HP, 4f, knockdown.
- *Passives*: **Double Jump** (`W` in air) and **Air Dash** (double-tap `A`/`D` while airborne): a horizontal burst of 10 px/frame for 8 frames that pauses the jump arc. One of each per jump.

### Golden Tactician (Archetype: Adaptive Stance Master)
- `O`: **Golden Read** — Predicts the enemy's next attack (their last action). If the enemy performs that attack within 30 frames, the read succeeds (`"READ"`): Golden's next clean hit within 60 frames is a **counter-hit** (+50% hitstun) with **+25% damage**. The move itself is a long-active strike (18 HP).
- `D + O`: **Gambit Strike** — Long-reach (110 px) tactical thrust. 14 HP, 11f, -10 on block.
- `A + O`: **Tactical Step** — Evasive step with 4 invulnerable frames (6 in Evade stance).
- `S + O`: **Tactician's Stance** — Cycles Rush → Guard → Evade:
  - **Rush Stance**: +8% damage on clean hits.
  - **Guard Stance**: half chip damage and 40% less guard drain when blocking.
  - **Evade Stance**: +10% walk speed and +2 invulnerable frames on backdash / Tactical Step.
- `P`: **Checkmate** — Super. 30 HP, 6f, knockdown.

---

## 6. Training Mode & Shortcuts

Arena-AI includes an integrated training mode for practicing combos, defense, and frame data:
- `F1`: **Reset Positions** — Instantly resets both fighters to neutral center positions and clears meters.
- `F2`: **Dummy Behavior** — Cycles dummy AI between:
  - `Idle`: Dummy stands still.
  - `Stand Block`: Dummy holds standing high block.
  - `Crouch Block`: Dummy holds crouching low block.
  - `Jump`: Dummy jumps continuously for practicing anti-air timing.
  - `Random`: Dummy acts unpredictably.
- `F3`: **Performance & Profiler HUD** — Toggles the internal frame timing and profiling overlay.
- `Esc`: **Pause Menu** — Pause the match to view the full in-game **Move List** with startup and frame advantage tables.


---

## 7. Autonomous AI & Deep Learning Pipeline

Arena-AI features a state-of-the-art autonomous AI learning pipeline that trains neural combat policies on CPU using Proximal Policy Optimization (PPO) and self-play leagues.

### Architecture Overview
1. **Gymnasium Environment (`backend/learning/env.py`)**:
   - Encapsulates the deterministic 60 FPS combat engine in a standard `gymnasium.Env` interface.
   - **Action Masking**: Prevents illegal or suicidal choices (e.g. attacking in recovery, spending nonexistent meter, using grounded moves in midair).
   - **Frame-Skip**: Evaluates decisions only at actionable decision points, committing to multi-frame macro-actions.
2. **Actor-Critic Neural Network (`backend/learning/network.py`)**:
   - Ultra-compact multi-layer perceptron (2 hidden layers of 128 units, CPU inference $<1$ ms).
   - Dual policy (action probabilities) and value (expected state outcome) heads.
3. **Behavioural Cloning (BC) Warm Start (`backend/learning/bc.py`)**:
   - Pretrains initial weights from high-level heuristic and search gameplay logs, bypassing early random exploration.
4. **PPO Training Engine (`backend/learning/ppo.py`)**:
   - Generalized Advantage Estimation ($\text{GAE } \lambda=0.95, \gamma=0.99$).
   - Clipped surrogate loss ($\epsilon = 0.20$), entropy regularization for exploration.
5. **Self-Play League & Style Gate (`backend/learning/league.py`)**:
   - Maintains an Elo-ranked league in a local SQLite registry (`data/model_registry.db`).
   - Prevents style drift using rigorous behavioral constraints (aggression, defense rate, spacing) before promoting models to the active roster.
6. **Zero-Freeze Background Training**:
   - Spawns via `multiprocessing.Process` from the in-game **Model Insights Screen** (`I` key). Training never blocks the 60 FPS Pygame loop.

---

### Agent Reward Profiles

Every character receives a shared base reward:
$$\text{Base Reward} = 100 \times \Delta\text{HP}_{\text{dealt}} - 100 \times \Delta\text{HP}_{\text{taken}} + 10 \cdot \mathbb{I}_{\text{round\_win}} - 10 \cdot \mathbb{I}_{\text{round\_loss}} - \text{time\_penalty} - \text{whiff\_penalty}$$

Character personalities are deeply shaped through heavy, distinct reward bonuses:

| Character | Archetype | Signature Reward Shaping Bonuses | Style Objective |
| :--- | :--- | :--- | :--- |
| **Crimson** | Rushdown Berserker | `+0.20` Forward movement / pressure<br>`+0.50` Combo hit landed<br>`-0.25` Backing away / passive retreat | Relentless aggression, corner lockdown, close-quarters combos. |
| **Steel** | Counter Tank | `+0.80` Successful block<br>`+2.50` Perfect Parry landed<br>`+1.50` Punish strike within 30f of block<br>`-0.60` Wild whiff penalty | Unbreakable defense, counter-strikes, patient defensive reads. |
| **Shadow** | Agile Hit-and-Run | `+0.25` Spacing within preferred zone (180–320 px)<br>`+1.60` Whiff punish on recovering opponent<br>`+0.80` Evade via backdash/air dash<br>`-0.50` Trapped in corner penalty | Spacing control, bait-and-punish, mobile zoning, evasion. |
| **Golden** | Adaptive Tactician | `+3.00` Round win bonus<br>`+3.00` Successful Golden Read counter<br>`+0.20` High action variety & stance rotation | Reads opponent habit distributions, adapts counters, stance switching. |

---

### Updated Difficulty Table

Arena-AI provides 4 distinct difficulty tiers, cleanly separated in skill and intelligence:

| Difficulty | Brain Architecture | Search Depth | Policy Guidance | Mistake Chance | Combo Reliability | Dynamic Difficulty Adjustment (DDA) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **LOW** | Pure Rule-Based FSM | None (0) | Disabled (FSM only) | 25% | 40% | Inactive |
| **MEDIUM** | Heuristic Minimax Search | 2 frames | Disabled (FSM fallback) | 12% | 70% | Inactive |
| **HIGH** | Hybrid Search + Policy Guidance | 3 frames | Blended Softmax Policy | 0% (Clean) | 90% | Adapts mistake chance if player wins/loses 3 rounds in a row |
| **HELL** | Deep Search + Policy + Opponent Modeling | 4 frames | Full Neural Actor-Critic | 0% (Optimal) | 100% (True Links) | Real-time opponent move prediction & dynamic adaptation |

*Note: LOW and MEDIUM never require trained weights and always operate seamlessly. HIGH and HELL gracefully fall back to heuristic search if no trained model exists.*

---

### Training from the Command Line

You can train and evaluate neural agents directly via terminal scripts:

```powershell
# 1. Warm-start a policy with Behavioural Cloning
uv run python -m backend.learning.bc

# 2. Train a character using PPO reinforcement learning
uv run python -m backend.learning.ppo

# 3. Run Self-Play League tournament and update Elo ratings
uv run python -m backend.learning.league

# 4. Run statistical evaluation, Wilson confidence intervals, and ablation studies
uv run pytest tests/test_learning_phase7.py
```
