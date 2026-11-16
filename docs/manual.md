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
| **Double-tap** `A` / `D` | **Dash / Backdash** | Forward dash closes space quickly; backdash grants **4 frames of full invulnerability** for whiff punishing. |
| `W` | **Jump** | Vertical leap. Airborne attacks become active while in mid-air. |
| `S` | **Crouch** | Shrinks hurtbox height; enables crouching normals and low blocking. |

### Universal Attacks & Normals
| Input | Attack | Damage | Startup | Advantage | Properties |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `J` | **Light Punch (Jab)** | 2 HP | 3 frames | +2 on block | Fastest move in the game; primary combo starter. |
| `K` | **Heavy Punch** | 8 HP | 10 frames | -5 on block | High hitstun; staggers the opponent. |
| `U` | **Light Kick** | 4 HP | 5 frames | 0 on block | Safe mid-range poke. |
| `I` | **Heavy Kick** | 10 HP | 12 frames | -8 on block | Longest reaching normal attack. |
| `S + U` / `S + I` | **Low Sweep** | 6 HP | 8 frames | -12 on block | Hits **LOW**; knocks opponent down to the ground. |
| `S + K` | **Anti-Air Uppercut** | 7 HP | 6 frames | -6 on block | High vertical priority; launches jumping enemies into the air. |
| `W + J` / `W + U` | **Jump Punch / Kick** | 4–6 HP | 4–6 frames | +1 on block | Airborne strikes that can start combos upon landing. |
| `J + U` | **Normal Throw** | 10 HP | 5 frames | Unblockable | Beats standing and crouching guard. |

### Defensive Actions
| Input | Action | Details |
| :--- | :--- | :--- |
| `L` (hold) | **Standing High Block** | Blocks **High** and **Mid** attacks. Vulnerable to Low Sweeps and Throws. |
| `S + L` (hold) | **Crouching Low Block** | Blocks **Low** and **Mid** attacks. Vulnerable to Overhead strikes and Throws. |
| `L` (tap 1–4f before hit) | **Perfect Parry** | Negates **100% of damage**, staggers the attacker for 22 frames, and grants **+12 Super Meter**! |
| `J + U` (within 7f) | **Throw Tech** | Press Throw within 7 frames of being grabbed to break free and push opponent away. |
| `L + O` (while being hit) | **Burst** | Costs **50 Super Meter**; breaks out of an enemy combo and blasts them across the arena. Once per round. |

### Special Moves & Super Attacks
| Input | Move Type | Cost | Details |
| :--- | :--- | :--- | :--- |
| `O` | **Special Neutral** | Free | Signature special move 1 (e.g. projectile, stance, dash punch). |
| `D + O` | **Special Forward** | Free | Signature special move 2 (advancing attack or launcher). |
| `A + O` | **Special Back** | Free | Signature special move 3 (defensive counter, feint, or reflector). |
| `S + O` | **Special Down** | Free | Signature special move 4 (command grab or ground strike). |
| `P` | **Super Move** | 100 Meter *(60 in Fury)* | Triggers a **15-frame cinematic freeze** before unleashing a devastating finisher. |

---

## 3. Combat Mechanics

### High, Low, and Mid Guard Rules
- **High Attacks** (Overheads, aerial strikes): Must be blocked standing (`L`). Crouching guard will be hit.
- **Low Attacks** (Sweeps, crouching kicks): Must be blocked crouching (`S + L`). Standing guard will be hit.
- **Mid Attacks** (Jabs, punches, basic kicks): Can be blocked either standing or crouching.
- **Throws**: Unblockable by both standing and crouching guards. Throws beat blocking, but lose to any attack active during throw startup.

### Frame Advantage & Recovery
- **Startup**: The frames before a move hits. You cannot block during startup.
- **Active**: The frames during which the attack's hitbox can deal damage.
- **Recovery**: The vulnerable frames after the attack finishes. If an attack misses (whiffs), you can be punished!
- **Plus on Block**: A move like Jab (+2 on block) leaves the attacker able to act before the defender recovers from blockstun.

### Counter-Hits
Striking an opponent during the startup frames of their attack scores a **Counter-Hit**. A counter-hit displays `"COUNTER!"` on screen and increases hitstun by **+50%**, opening up unique combo links that are normally impossible.

### Combos, Cancels, and Wall Bounces
- **Strings**: Characters possess built-in chain combos (e.g. Jab → Jab → Heavy) that automatically connect if the previous strike landed.
- **Cancels**: Normals can be cancelled into Special Moves during their active/cancel windows. Special Moves can be cancelled directly into Super Moves.
- **Air Juggle Cap**: Airborne juggles are strictly capped at **4 hits**. On the 4th air hit, the victim gains knockdown invulnerability and drops safely to the floor.
- **Wall Bounce**: Knocking an opponent hard into the arena corner triggers a wall bounce, allowing an immediate follow-up attack.
- **Damage Scaling & Infinite Protection**: Every extra hit in a combo scales incoming damage: 100% → 90% → 80% ... down to a 30% floor. Hitstun decays as combo length grows to prevent infinite loops.

---

## 4. Meters & Resources

### Guard Meter & Guard Break
- Guard Meter starts at 100.
- Blocking attacks drains guard meter based on the strength of the incoming strike.
- Guard meter regenerates smoothly when the fighter is idle or moving without blocking.
- **Guard Break**: If the guard meter hits 0, the defender is **stunned for 40 frames** (`"GUARD BREAK"`), leaving them completely defenseless to a full combo!

### Super Meter (0–100)
- Built by landing attacks (+8–15), taking damage (+3–5), and performing Perfect Parries (+12).
- **25 Meter**: Spend on enhanced signature moves (e.g. Steel Guardian's Shield Bash to escape the corner).
- **50 Meter**: Spend on **Burst** (`L + O`) while trapped in hitstun to end the combo and reset the fight to neutral.
- **100 Meter**: Spend to execute your character's ultimate **Super Move** (`P`).

### Fury Mode (< 25% Health)
When a fighter's health drops below 25 HP:
1. An animated **FURY** indicator lights up on their HUD.
2. All attacks deal **+10% bonus damage**.
3. Super Move cost drops from 100 meter to **60 meter**, giving fighters dramatic comeback potential!

---

## 5. Character Movesets

### Crimson Brawler (Archetype: Rushdown Berserker)
High-damage fighter specializing in relentless forward pressure and corner trapping.
- `O`: **Crimson Rush** — 3-hit forward dash punch string that continues automatically if the first hit connects.
- `D + O`: **Rising Uppercut** — Invulnerable anti-air launcher.
- `A + O`: **Berserker Charge** — Forward charge with 1 hit of armor (absorbs attack while taking only 50% damage).
- `S + O`: **Clinch Slam** — Short-range command grab that slams the opponent to the ground.
- `P`: **Blood Fury** — 8-hit cinematic super combo dealing massive damage.

### Steel Guardian (Archetype: Counter & Defense)
Sturdy, armored fighter with projectile reflection and counter stances.
- `O`: **Iron Wall** — Counter stance; parries any incoming melee strike and automatically strikes back.
- `D + O`: **Shield Bash** — Pushback move from block (costs 25 meter) that shoves opponents out of the corner.
- `A + O`: **Reflector** — Projects an energy barrier that reflects projectiles back at the sender.
- `S + O`: **Punisher Grip** — Slow, armored command grab that breaks through enemy guards.
- `P`: **Fortress Crush** — Counter super that triggers upon being struck during its stance.
- *Passive*: Takes 50% less chip damage when blocking.

### Shadow Striker (Archetype: High-Mobility Hit-and-Run)
Agile, evasive fighter with teleportation, projectiles, and midair mobility.
- `O`: **Shadow Step** — Instant teleport that reappears behind the opponent.
- `D + O`: **Phantom Kick** — Low-Mid-Mid deceptive kick sequence.
- `A + O`: **Feint Strike** — Fake strike that cancels immediately into a backdash or throw.
- `S + O`: **Energy Dart** — Fast horizontal projectile.
- `P`: **Vanishing Arts** — Multi-angle teleport assault super.
- *Passives*: **Double Jump** (`W` in air) and **Air Dash** (double-tap `A`/`D` while airborne).

### Golden Tactician (Archetype: Adaptive Stance Master)
Intelligent stance-switcher whose AI dynamically learns and counters opponent habits.
- `O`: **Tactician's Stance** — Cycles between 3 stances:
  - **Rush Stance**: Fast attack startup and aggressive cancel windows.
  - **Guard Stance**: High block defense and reinforced guard meter.
  - **Evade Stance**: Fast movement and longer invulnerable backdash.
- `D + O`: **Gambit Strike** — Advancing tactical thrust.
- `A + O`: **Golden Read** — Predicts an enemy action; if the enemy performs that action within 30 frames, Golden delivers a devastating counter-strike.
- `S + O`: **Checkmate** — Tactical ground control finisher.
- `P`: **Grandmaster Finisher** — Calculated full-board ultimate strike.

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
