# Opponent Model — M6

## File: `backend/ai/opponent_model.py`

Predicts what the enemy will do next. HIGH/HELL use it to boost counters, and
HELL's in-game search uses its distribution for expectimax.

## How it works

1. **Count table:** For each situation `(distance_zone, last_action,
   2nd_last_action)`, count how many times the enemy did each action.

2. **Laplace smoothing:** Add 1 to every count so no action is ever
   predicted as impossible (avoids division by zero).

3. **Decay:** Every second, multiply all counts by 0.98 so old data
   fades and the model adapts to changing behaviour.

4. **Prediction:** Normalise counts to probabilities. The most likely
   action becomes `last_prediction`.

## Accuracy tracking

- `accuracy`: fraction of predictions that were correct.
- `is_confident`: True when accuracy ≥ 70%.
- `time_to_model`: how many frames until accuracy first passed 50%.

## Usage in HELL mode

`DifficultyWrapper._run_search` (HELL only, within 220 px, 3 ms budget) runs a
depth-1 simultaneous-move search. Once the model has made at least 30
predictions with at least 35% accuracy (`EXPECTIMAX_MIN_PREDICTIONS`,
`EXPECTIMAX_MIN_ACCURACY` in `difficulty.py`) it uses **expectimax**: each
candidate's value is the probability-weighted evaluation over the model's top-3
predicted enemy moves. Before that it uses **minimax** (worst case) over the
threat set IDLE / LIGHT / BLOCK. `wrapper.last_search["mode"]` shows which was
used. (The 70% `is_confident` flag is still reported, but 70% is rarely reached
against humans, so the switch uses the lower threshold.)

## Key properties

| Property | Meaning |
|----------|---------|
| `accuracy` | 0 to 1, how often the prediction was right |
| `is_confident` | True if accuracy ≥ 0.70 |
| `time_to_model` | Frames until accuracy > 50%, or -1 |
