# Headless Matches and Logging (M2)

## What it does
Runs complete AI-vs-AI matches with no graphics and saves every frame to a
SQLite database. This data is used later for training, statistics, and replays.

## Files

### match_runner.py
`run_match(agent1, agent2, seed)` runs a full match (up to 3 rounds):
1. Creates the initial engine state.
2. Each frame: builds an Observation for each agent, asks them to `decide()`,
   steps the engine, lets agents `observe()` the result.
3. When a round ends, calls `new_round()` and `agent.reset()`.
4. Returns a dictionary with all frame records, match result, seed, and rounds.

Each frame record contains: frame number, round number, both agent names
and difficulties, seed, all 16 feature values from `observation.features()`,
and both players' chosen actions.

### database.py
SQLite storage with one row per frame:
- **get_connection(path)**: opens or creates the database with WAL mode.
- **save_match(conn, match_data)**: inserts all frames with a UUID match_id.
- **count_matches/count_frames**: quick counts.
- **get_match_ids**: list of match IDs (newest first).
- **get_match_frames**: all rows for one match as dicts.

The table columns are: id, match_id, frame, round, agent names/difficulties,
seed, action1, action2, match_result, and all 16 FEATURE_NAMES columns.

### simulate.py
Command-line tool to run many matches:
```
uv run python -m backend.data.simulate --matches 100
uv run python -m backend.data.simulate --matches 50 --seed 42
```
Each match uses a different seed (seed+0, seed+1, …) so every match can be
replayed by using the same seed. Prints progress every 10 matches.

## Why seeds matter
Every match stores its seed. To replay match #7 exactly:
use seed=7 with the same two agents. The engine is deterministic, and
RandomAgent uses a seeded RNG, so the replay is frame-perfect.
