# Fighters — M4

Each of the four AI fighters is a small state machine that
turns the `Observation` into scores for each allowed move.

## How a fighter picks a move

1. Look at the `Observation` (distance, health, cooldowns, etc.).
2. Give every legal action a score from 0 to 10.
3. Pass the scores to `choice.pick()`, which uses the personality's
   `variety` and the difficulty's `mistake_chance` to choose.

## The Four Fighters

### Crimson — The Rusher
- **File:** `backend/ai/crimson.py`
- **Personality:** high `closeness`, high `health_lead`
- **Strategy:** Rush in and chain attacks. Always wants to be close.
  When panicking (low health), gets MORE aggressive, not less.
- **Panic mode:** `is_panicking()` returns True → increase attack scores.

### Steel — The Defender
- **File:** `backend/ai/steel.py`
- **Personality:** high `block_punish`, high `safe_distance`
- **Strategy:** Block and wait for the enemy to attack, then punish
  during their recovery frames (`enemy_is_stuck`).
  Under time pressure, Steel becomes more aggressive to avoid losing
  by timeout.

### Shadow — The Hit-and-Run
- **File:** `backend/ai/shadow.py`
- **Personality:** high `safe_distance`, moderate `closeness`
- **Strategy:** Stay at preferred distance and poke from `is_safe_poke`
  range. Darts in to attack, then retreats. Fastest fighter.
  Uses corners aggressively to trap enemies.

### Golden — The Adapter
- **File:** `backend/ai/golden.py`
- **Personality:** neutral base, `adapts=True`, moderate `adapt_speed`
- **Strategy:** Counts the opponent's habits and shifts likes over time.
  Starts neutral, then specialises against each opponent.
  Uses `ZoneTracker` to avoid flickering between decisions.

## Engine mechanics the fighters can use

These are engine rules (see `docs/engine.md` and `docs/manual.md`), listed here
so AI behaviour and docs stay consistent:

- **Crimson**: Rising Uppercut (`SPECIAL_NEUTRAL`) is an anti-air: it beats jump
  attacks. Berserker Charge (`SPECIAL_BACK`) has 1 hit of armor.
- **Steel**: Iron Wall (`SPECIAL_DOWN`) / Fortress Crush (`SUPER`) are counter
  stances; Reflector (`SPECIAL_BACK`) turns projectiles around.
- **Shadow**: Shadow Step (`SPECIAL_FORWARD`) works on the ground only. In the
  air, `JUMP` is a double jump and `DASH` / `BACKDASH` is a real horizontal air
  dash (10 px/frame for 8 frames, once per jump). Energy Dart
  (`SPECIAL_NEUTRAL`) can be jumped over.
- **Golden**: Tactician Stance (`SPECIAL_DOWN`) cycles Rush (+8% damage) →
  Guard (half chip, 40% less guard drain) → Evade (+10% walk speed, longer
  invulnerability on evasive moves). Golden Read (`SPECIAL_NEUTRAL`) succeeds
  when the enemy repeats the predicted attack within 30 frames; Golden's next
  clean hit within 60 frames is then a counter-hit with +25% damage. The
  success shows as the one-frame event `last_hit_effect == "read"` /
  `read_success == True`.
- Everyone: blocking is impossible during your own move, a fresh block press
  parries for 4 frames but a failed parry locks parrying out for 24 frames,
  and `last_hit_effect` (`"hit"`, `"block"`, `"parry"`, ...) is a one-frame event.

## Testing

Each fighter must beat `RandomAgent` in at least 80% of 50 headless matches.
The test is in `tests/test_fighters.py`.

## Key imports used by all fighters

```python
from backend.ai.actions import Action
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.zones import zone_of, ZoneTracker
from backend.ai.observation import Observation
```
