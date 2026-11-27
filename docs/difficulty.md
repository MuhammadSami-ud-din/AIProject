# Difficulty, Evaluation & Search — M5

## Difficulty Wrapper (`backend/ai/difficulty.py`)

Wraps any fighter agent and changes only decision quality (never health or damage).
All numbers live in `DIFFICULTY_PROFILES` (one frozen dataclass per tier).

| Tier | Mean reaction | Jitter (sd) | Mistake | Dropped input | Late input | Learned policy weight | In-game search |
|------|---------------|-------------|---------|---------------|------------|-----------------------|----------------|
| LOW    | 24 f | 6 f   | 35% | 6%   | 10% | – | no |
| MEDIUM | 15 f | 4 f   | 18% | 3%   | 6%  | – | no |
| HIGH   | 8 f  | 2.5 f | 7%  | 1.2% | 3%  | 0.5 | no |
| HELL   | 2 f  | 1 f   | 1%  | 0.3% | 1%  | 0.7 | yes (3 ms budget) |

- **Reaction time (human-like):** the AI acts on the observation from
  `current_reaction_delay` frames ago; that delay is re-sampled from
  N(mean, jitter) at every decision and after every newly seen attack, so it
  varies like a human's. Attacks are only "seen" through this delay.
- **Execution errors:** after a move is chosen it is occasionally dropped
  (nothing happens this tick) or pressed 1-3 frames late.
- **Mistakes:** rolled exactly ONCE per decision; a mistake picks one of the
  2nd-5th best sensible moves.
- **Learned policy (HIGH/HELL):** the newest compatible PPO checkpoint is
  loaded (registry "live" row first, else the newest `models/<char>/vNNN.pt`,
  else `bc_model.pt`; incompatible files are skipped). Its action
  distribution is blended with the FSM scores:
  `final = max_s * ((1-w)*fsm/max_s + w*p/max_p)` and the policy's top move is
  always kept in the candidate pool. The lookup is cached with invalidation
  (registry row ids + checkpoint file mtimes) and re-checked every round, so a
  newly trained model is picked up without restarting. With no model, or if
  loading fails (logged), the FSM personality alone plays.
- **In-game search (HELL):** within 220 px, a depth-1 *simultaneous-move*
  search over the top-5 candidate moves runs on a state rebuilt from the
  observation (`search.state_from_observation`), with a hard 3 ms budget.
  It uses **expectimax** over the opponent model's predicted distribution once
  that model has ≥30 predictions at ≥35% accuracy, otherwise cautious
  **minimax** over a small threat set (IDLE / LIGHT / BLOCK). The best move
  gets a score boost and is kept in the candidate pool.
- **Feature switches:** `use_search`, `use_opponent_model`, `use_learned_policy`
  (constructor arguments or attributes) for ablation studies.

### Match-flow API (Dynamic Difficulty Adjustment)

```python
wrapper = DifficultyWrapper(inner, "HELL", adaptive_difficulty=True)
...
wrapper.on_round_end(state.round_result)   # "p1"/"p2"/"draw" or "win"/"loss" (AI's view)
wrapper.on_match_end(state.match_result)   # also re-checks for a newly promoted model
```

With `adaptive_difficulty` on (HIGH/HELL), `on_round_end` feeds `update_dda`,
which nudges the mistake chance up when the human keeps losing and down when
the human keeps winning (target 45-55% human win rate over the last 5 rounds).

## Evaluation (`backend/ai/evaluation.py`)

Scores how good a situation is for a fighter by multiplying
each personality "like" by the matching feature value:

```
total_score = Σ (personality.likes[name] × feature_value[name])
```

Features: `health_lead`, `closeness`, `safe_distance`,
`block_punish`, `corner_avoid`, `time_pressure`.

Returns `(total_score, contributions)` where contributions
is a dict showing each part's individual contribution.

## Search (`backend/ai/search.py`)

Minimax with alpha-beta pruning adapted for fighting games:

1. **Not turn-based:** Decide every 6 frames (FRAMES_PER_PLY).
2. **Simultaneous actions:** Both fighters act at once.
3. **Iterative deepening:** Try depth 1, then 2, then 3...
4. **5ms time budget:** Stop when time runs out.
5. **Engine copy:** Uses `state.copy()` to simulate, never touches
   the live game state.
6. **Branch limiting:** Only considers top 4 actions per ply.

`search_best_action` (sequential minimax) is kept for analysis/tests; the game
uses `simultaneous_search` (expectimax / minimax over joint actions) at HELL.
