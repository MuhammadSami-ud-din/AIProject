# Engine (M1)

## What it does
The engine is the **referee** of every fight. It knows the rules: how fighters
move, how attacks work, when a round ends, who wins the match. It lives in
`backend/engine/` and has **no pygame imports** — it runs entirely in memory.

## Files

### constants.py
Every game number in one place:
- **Arena**: 800 px wide.
- **Timing**: 60 FPS, 60-second rounds (3600 frames per round).
- **Movement**: walk speed 4 px/frame, jump lasts 40 frames.
- **Blocking**: blocked hits do 10% of their normal damage.
- **Attacks**: `AttackData` dataclass holds damage, reach, startup, active,
  recovery, and cooldown for each attack type (LIGHT and HEAVY).

### characters.py
Body stats for each fighter as multipliers on top of the base values:
- **Crimson**: 1.2× damage, 0.9× reach (hits hard, short arms).
- **Steel**: blocked damage only 5% instead of 10% (strong shield).
- **Shadow**: 0.85× damage, 1.15× reach, 1.3× speed (fast and long, but soft).
- **Golden**: all 1.0× (perfectly average).

Helper functions: `light_attack_for(stats)`, `heavy_attack_for(stats)`,
`walk_speed(stats)` apply the multipliers and return the final numbers.

### state.py
Two dataclasses that hold the complete snapshot of a fight:
- **FighterState**: position, health, cooldown, recovery, attack phase
  (none/startup/active/recovery), jump state, last action, character name.
- **FightState**: two FighterStates plus frame counter, round number,
  round timer, wins for each player, and round/match results.

Both have `.copy()` so the step function can work on a fresh copy.

### physics.py
- **apply_movement**: walks toward or away from the enemy, clamps to arena walls.
  Cannot move during recovery or while airborne.
- **apply_jump**: starts a jump on JUMP press, counts frames, lands after
  JUMP_DURATION. Cannot jump during recovery.

### combat.py
- **start_attack**: begins the startup phase if cooldown and recovery are clear.
- **advance_attack**: moves through startup → active → recovery → none.
- **check_hit**: returns True if the attacker is in active phase and in range.
- **apply_damage**: reduces defender health; blocking (on ground) reduces damage.

### step.py
The heart of the engine:
- **step(state, action1, action2) → new FightState**: one frame update.
  Pure function — never changes the input. Order: tick timers → jump → move →
  start attacks → advance attacks → check hits → record actions → advance frame →
  check round end.
- **Round end**: KO (health ≤ 0), time-out (higher health wins), equal health = draw.
- **Match end**: first to 2 round wins. Max 3 rounds. If nobody has 2 after round 3,
  more wins takes the match; equal = match draw.
- **new_round(state)**: resets fighters for the next round, keeps the score.
- **make_initial_state(char1, char2)**: starting positions at 25%/75% of arena.

## adapter.py (in backend/ai/)
Bridges engine → AI: `observation_for(state, player)` converts a `FightState`
into an `Observation` from that player's point of view.

## Key design decisions
1. **Pure functions**: `step()` returns a new state, never mutates the input.
   This makes determinism automatic and lets the AI search ahead safely.
2. **No pygame**: the engine can run millions of frames per second in tests
   and simulations.
3. **Imports Action from backend.ai.actions**: the engine and AI share the
   same Action enum, nothing else.
