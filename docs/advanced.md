# Advanced Features — M10

## Personality Tuning (`backend/ai/tuning.py`)

### Hill Climbing
Finds better personality weights by trial and error:
1. Start with a base personality (e.g. CRIMSON).
2. Mutate it slightly (using `personalities.mutate()`).
3. Run matches against an opponent.
4. Keep the version that wins more.
5. Repeat.

```python
from backend.ai.tuning import hill_climb
from backend.ai.crimson import CrimsonAgent
from backend.ai.random_agent import RandomAgent

best, rate, history = hill_climb(
    CRIMSON, CrimsonAgent, RandomAgent,
    steps=10, trials=20
)
```

### Co-evolution
Two fighters evolve against each other so neither stays fixed:
1. Fighter 1 hill-climbs against current fighter 2.
2. Fighter 2 hill-climbs against updated fighter 1.
3. Repeat for several generations.

## Ghost Fighter (`backend/ai/ghost.py`)

An AI that copies the human player's fighting style.

### How it works
1. **With trained model:** Uses the RandomForest from M8 to predict
   what action the human would choose in each situation.
2. **Without model (fallback):** Counts which actions the human used
   in each `(distance_zone, enemy_stuck)` situation and picks the
   most common one.

```python
from backend.ai.ghost import GhostAgent
ghost = GhostAgent(player=2, seed=42)
# Optional: feed it logged human data
ghost.learn_from_logs(action_log)
```

## Tabular Q-Learning (`backend/ai/qlearning.py`)

Reinforcement learning through self-play.

### How it works
1. **Discretise** the observation into buckets:
   (zone, my_health_bucket, enemy_health_bucket, cornered, etc.)
2. **Q-table** maps (state, action) → value.
3. **Update rule:**
   `Q(s, a) = Q(s, a) + α × (reward + γ × max Q(s') - Q(s, a))`
4. **Epsilon-greedy** exploration: starts at 30%, decays to 5%.
5. **Self-play:** two agents share the same Q-table.

```python
from backend.ai.qlearning import train_q_agent
q_table, history = train_q_agent(episodes=100)
```

Parameters: α=0.1, γ=0.95, ε decays 0.999× per episode.

## MCTS (`backend/ai/mcts.py`)

Open-loop **UCT** tree search (a real tree, not flat Monte-Carlo):

1. Nodes are sequences of our macro-actions (one ply = 6 frames; movement held,
   attacks pressed on the first frame), drawn from a 15-action tactical subset.
2. **Selection** with UCB1 (C = 1.4), **expansion** of one untried action per
   iteration, **rollout** with random macro-actions up to 3 plies, evaluation
   with the personality evaluation function, **back-propagation**.
3. The opponent plays a random macro-action per ply (open-loop MCTS for a
   simultaneous-move game).
4. The time budget is checked before every iteration (the first always runs).
   The move with the most visits is returned.

```python
from backend.ai.mcts import mcts_best_action
action, mean_value, iterations = mcts_best_action(state, player=1, personality=CRIMSON, rng=rng)
```

Honest scope: one iteration costs ~0.5-1 ms of Python engine simulation, so the
default 4 ms budget allows only a few iterations. MCTS is therefore **not used
in gameplay**; HELL uses the cheaper depth-1 simultaneous search described in
`docs/difficulty.md`. MCTS remains an analysis tool for larger budgets.

## Ablation Study (`backend/data/ablation.py`)

Turn off one feature at a time and measure the win-rate drop:
- `baseline` — all features on
- `no_search` — in-game search disabled (only has an effect at HELL, the only tier that searches)
- `no_opponent_model` — prediction disabled
- `no_learned_policy` — learned model disabled

Also includes a binomial test confirming LOW < MEDIUM < HIGH < HELL.

## Replay Viewer (`frontend/replay_viewer.py`)

Replays a logged match frame-by-frame from the database.

| Key | Action |
|-----|--------|
| Space | Pause/unpause |
| ← / → | Step back/forward (paused) or change speed |
| Esc | Exit replay |
