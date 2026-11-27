# Engine

## What it does
The engine is the **referee** of every fight. It knows the rules: how fighters
move, how attacks work, when a round ends, who wins the match. It lives in
`backend/engine/` and has **no pygame imports** — it runs entirely in memory and
is fully deterministic (no randomness outside the seeded Rumble loot RNG).

## Files

### constants.py
Every game number in one place (named constants, no magic numbers in step.py):
- **Arena / timing**: 800 px wide, 60 FPS, 60-second rounds (3600 frames).
- **Movement**: walk 4 px/frame; jump 40 frames with a 110 px parabolic apex;
  Classic air control 0.5x walk speed (Rumble / Shield Wall 1.0x); dash and
  backdash bursts; Shadow air dash.
- **Hurtboxes**: standing 100 px, crouching 60 px, airborne 80 px.
- **Defense**: guard meter (drain 18 per blocked hit, regen 0.25/frame, break
  stun 40), parry window 4 / stagger 22 / lockout 24, throw tech window 7,
  wakeup and post-stun throw invulnerability, burst cost / pushback / stagger.
- **Hits**: combo scaling, counter-hit, Fury, juggle cap, bounces, projectiles,
  Golden stance / Read and Shadow Step numbers.
- **Base data**: `LIGHT_ATTACK` and `HEAVY_ATTACK` (`AttackData`) are *derived*
  from the universal Jab and Heavy Punch `MoveData` in moves.py — the frame data
  exists in exactly one place.

### moves.py
All frame data (`MoveData`): damage, startup, active, recovery, `on_block`,
hitstun, blockstun, reach, hit level (MID/HIGH/LOW/THROW), launch / bounces,
armor, invulnerability, projectile data, plus the vertical axis:
- `hitbox_y` — `(min, max)` height of the hitbox above the attacker's own
  height (`None` = default for the hit level: LOW 0–30 px, others 10–120 px).
  Heavy Kick is aimed high (65–140) and whiffs on crouchers; anti-airs reach
  40–220; jump attacks reach 60 px below the jumper.
- `anti_air` — during startup/active the move beats incoming air attacks.
- Data invariant (tested): `blockstun = (active - 1) + recovery + on_block`.

Per-character movesets scale damage and reach (Crimson 1.2x / 0.9x, Shadow
0.85x / 1.15x) with `dataclasses.replace`, then add the character specials.

### characters.py
Body stats as multipliers: damage, reach, walk speed, blocked-damage ratio
(Steel 5% instead of 10%). Helpers `light_attack_for`, `heavy_attack_for`,
`walk_speed`. (The real per-character reach is `get_move(char, action).reach`;
the AI adapter reads it from there.)

### state.py
- **FighterState**: position, health, timers, attack phase, posture, jump,
  throws, dashes, combos, meters, stances, one-frame events, mode attributes.
  `y` (property) is the height above the floor from the jump arc.
  `copy()` copies every dataclass field generically (tested against
  `dataclasses.fields`, so new fields cannot be forgotten).
- **ProjectileState**: x, vx, owner, lifetime, damage, hit level, reach,
  `height` (centre height, default 50 px; flies from 35 to 65 px).
- **FightState**: both fighters, projectiles, round/match bookkeeping, super
  freeze, buffered inputs, Rumble state.

### physics.py
- `apply_movement`: walking, crouch posture, starting a forward dash.
- `apply_air_control`: drift while airborne (not while juggled / air dashing).
- `apply_jump`: parabolic jump; Shadow double jump and air dash.
- `start_dash` / `apply_dash_motion`: dashes are a burst of speed that
  decelerates linearly (forward dash 14 frames at 3.2x walk speed; backdash
  14 frames at 3.0x, started by the BACKDASH move, which keeps its 4 invulnerable
  frames); Shadow's air dash is 10 px/frame for 8 frames and pauses the arc.
- `apply_pushback`: pushes the defender away; wall overflow pushes the attacker.

### combat.py
- `can_act`, `can_cancel_into`, `start_attack`, `advance_attack`.
- `is_guarding`: no blocking in the air, in hitstun, while thrown, during a
  guard break, or **during your own move (startup / active / recovery)**.
- `check_hit`: horizontal reach + pushbox radius, **vertical overlap** of
  hitbox and hurtbox, anti-air beats air attacks, throw rules (no throwing
  airborne / throw-invulnerable / stunned fighters; a normal throw loses to a
  strike's startup, but two throws meet and clash). Moves with 0 damage
  (backdash, stance, teleport, feint) have no hitbox.
- `apply_damage`: multipliers, chip, armor, Rumble shield.

### step.py
`step(state, action1, action2) -> FightState` — pure, never mutates the input.

## Step order
1. Clear both fighters' one-frame events (`last_hit_effect`, `read_success`).
2. **Super freeze**: if active, count it down, buffer each player's last
   non-IDLE input and return. On the first frame after the freeze a buffered
   input replaces an IDLE input.
3. Snapshot frame timers; tick strike invulnerability; wake up fighters whose
   knockdown finished (6 frames strike + 10 frames throw invulnerability).
4. Mode systems: Rumble (zone, building, loot, arena objects) and Shield Wall.
5. Reset combo counters for attackers whose victim is back in neutral.
6. **Advance attacks already in progress** by one frame (so a move whose last
   recovery frame was the previous frame lets the fighter act on this frame).
7. **Inputs** (read with the timers as they were at the start of the frame):
   bursts (both resolved together), throw techs / throw landing, jump, walking,
   dashes, air control, then new moves. A move started this frame plays its
   first frame immediately. Block presses update the parry window / lockout.
8. Projectiles spawn, move and hit (reflector, shield walls and Rumble walls
   first); then melee hits are computed for both fighters and applied
   simultaneously (throw vs throw = clash/tech, throw vs strike = strike wins,
   strike vs strike = trade).
9. Pushboxes, Rumble wall / crate collisions, shield wall collisions.
10. Golden Read check.
11. **Tick frame timers** (cooldown, recovery, hitstun, blockstun, guard break,
    knockdown, parry lockout, throw invulnerability, ...). A timer changed during
    this frame is not ticked until next frame, so blockstun N = N full frames
    after the hit. Leaving hit/blockstun grants 5 frames of throw invulnerability.
    Guard meter and (if enabled) health regenerate.
12. Record actions, advance the frame and round clock, check round/match end.

With this order the **measured** on-block advantage of every strike equals
`MoveData.on_block` (tests simulate it for every normal and special).

## Per-frame events
`FighterState.last_hit_effect` and `FighterState.read_success` are
**one-frame events**: they are reset at the start of every `step()` and set
only on the frame the event happens. Read them right after each `step()`.

| Value | Set on | When |
| :--- | :--- | :--- |
| `"hit"` | defender | a clean (unblocked) melee or projectile hit |
| `"block"` | defender | the defender blocks a melee hit or projectile |
| `"parry"` | defender | perfect parry (melee or projectile) |
| `"guard_break"` | defender | a blocked hit empties the guard meter (also: shield wall broken) |
| `"counter"` | attacker | counter-hit (victim was in startup, or a Golden Read bonus hit) |
| `"counter"` | defender | Steel's counter stance absorbed the hit |
| `"wall_bounce"` | attacker | the hit wall-bounced the victim |
| `"ground_bounce"` | attacker | the hit or throw ground-bounced the victim |
| `"burst"` | burster | burst used (both fighters on a simultaneous burst) |
| `"tech"` | both | throw tech or simultaneous-throw clash |
| `"read"` | Golden | Golden Read prediction came true (`read_success` is also True) |

If several events hit the same fighter on one frame, the last one wins
(e.g. a counter-hit that also wall-bounces reports `"wall_bounce"`; the
defender still reports `"hit"`).

## Rules summary
- **Round end**: KO, or time-out (higher health wins; equal = draw).
- **Match end**: first to 2 round wins, max 3 rounds.
- **new_round(state)**: resets fighters (health, timers, posture, guard, dash,
  parry/throw state, shield wall), clears projectiles, super freeze and the
  input buffer; keeps the score, super meter and Golden's stance.
- **Defense**: a fresh block press parries for 4 frames; if it does not parry,
  a 24-frame lockout starts during which a fresh press only blocks.
- **Throws**: 7-frame tech window; the ground bounce is decided when the grab
  connects. No throws on wakeup (10 f), during hit/blockstun or 5 f after.
- **Projectiles** follow the same guard rules as melee using the target's
  input on the impact frame, drain 10 guard (and can guard break), and pass
  over knocked-down fighters and anything above/below their 35–65 px band.
- **Golden**: Rush stance +8% damage; Guard stance half chip, 40% less guard
  drain; Evade stance +10% walk speed and +2 invulnerable frames on evasive
  moves. A successful Read makes the next clean hit (within 60 f) a counter-hit
  with +25% damage.
- **Rumble / Shield Wall air movement**: airborne fighters drift at full walk
  speed (FORWARD/DASH toward, BACK/BACKDASH away) so they can jump over walls
  and shields; Classic uses 0.5x. Juggled fighters have no air control.

## adapter.py (in backend/ai/)
Bridges engine → AI: `observation_for(state, player)` converts a `FightState`
into an `Observation`. Reach values are the real per-character Jab reach from
`MoveData` (e.g. 82 px base, 73.8 Crimson, 94.3 Shadow).

## Key design decisions
1. **Pure functions**: `step()` returns a new state, never mutates the input.
2. **No pygame**: the engine runs headless for tests, search and training.
3. **Data-driven**: frame data and hitbox heights live in moves.py, tuning
   numbers in constants.py.
4. **Symmetric**: P1 and P2 are resolved from the same pre-frame state
   (movement, bursts, throws, trades).
