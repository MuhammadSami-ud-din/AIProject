# Opponent Model — M6

## File: `backend/ai/opponent_model.py`

Predicts what the enemy will do next, so HELL-mode fighters
can use expectimax instead of worst-case minimax.

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

When `is_confident` is True, the search switches from minimax
(assume the worst) to expectimax (weight enemy moves by predicted
probabilities). This gives a more realistic and stronger opponent.

## Key properties

| Property | Meaning |
|----------|---------|
| `accuracy` | 0 to 1, how often the prediction was right |
| `is_confident` | True if accuracy ≥ 0.70 |
| `time_to_model` | Frames until accuracy > 50%, or -1 |
