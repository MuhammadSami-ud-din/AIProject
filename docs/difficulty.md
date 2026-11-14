# Difficulty, Evaluation & Search — M5

## Difficulty Wrapper (`backend/ai/difficulty.py`)

Wraps any fighter agent to make it easier or harder by adding three
handicaps:

| Difficulty | Reaction Delay | Mistake Chance | Search Depth |
|------------|---------------|----------------|-------------|
| LOW        | 24 frames     | 30%            | 1 ply       |
| MEDIUM     | 15 frames     | 15%            | 2 plies     |
| HIGH       | 7 frames      | 5%             | 3 plies     |
| HELL       | 1 frame       | 1%             | 4 plies     |

- **Reaction delay:** The AI sees an observation from N frames ago,
  simulating slow human reactions.
- **Mistake chance:** Sometimes picks the 2nd or 3rd best move
  (using `choice.pick()`), never a silly one.
- **Feature switches:** `use_search`, `use_opponent_model`,
  `use_learned_policy` for ablation studies.

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
6. **Branch limiting:** Only considers top 3 actions per ply.
