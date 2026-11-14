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
