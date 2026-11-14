# Evaluation & Statistics — M9

## Statistics (`backend/data/statistics.py`)

Runs tournaments and computes ratings.

### `run_round_robin(fighters, difficulties, matches_per_pair)`
Runs every fighter against every other fighter. Returns a list
of result dicts with wins, draws, and totals.

### `compute_elo(results)`
Computes Elo ratings from round-robin results using:
- Starting Elo: 1000
- K-factor: 32
- Standard expected score formula

### `win_rate_with_ci(wins, total)`
Returns `(rate, lower, upper)` using the normal approximation
for a 95% confidence interval.

### `difficulty_ranking(fighter_name)`
Runs the same fighter at each difficulty against RandomAgent.
Returns `{"LOW": 0.6, "MEDIUM": 0.75, ...}` — should increase.

## Charts (`backend/data/charts.py`)

Generates matplotlib charts saved to `docs/results/`:

| Chart | What it shows |
|-------|--------------|
| `elo_ratings.png` | Bar chart of Elo ratings |
| `winrate_heatmap.png` | Win rate matrix (fighter vs fighter) |
| `difficulty_<name>.png` | Win rate by difficulty level |

### Usage
```python
from backend.data.charts import generate_all_charts
paths = generate_all_charts()  # creates docs/results/
```

## Statistics Screen (`frontend/screens.py`)

The in-game statistics screen:
- Runs a quick round-robin tournament
- Shows Elo leaderboard (sorted by rating)
- Shows win rate table (fighter vs fighter)
- Press Esc to go back
