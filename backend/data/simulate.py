"""Run many headless matches and save them to the database.

Usage:
    uv run python -m backend.data.simulate --matches 100
    uv run python -m backend.data.simulate --matches 50 --seed 42
"""

import argparse
import time

from backend.ai.random_agent import RandomAgent
from backend.data.database import count_frames, count_matches, get_connection, save_match
from backend.data.match_runner import run_match


def main():
    parser = argparse.ArgumentParser(
        description="Run headless AI matches and log them to SQLite."
    )
    parser.add_argument(
        "--matches", type=int, default=10,
        help="How many matches to run (default: 10)."
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Starting seed. Each match uses seed, seed+1, seed+2, etc."
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to the SQLite database file (default: backend/data/fights.db)."
    )
    args = parser.parse_args()

    conn = get_connection(args.db)
    start_time = time.time()
    total_frames = 0

    print(f"Running {args.matches} matches...")

    for i in range(args.matches):
        # Each match gets its own seed so it can be replayed
        if args.seed is not None:
            seed = args.seed + i
        else:
            seed = i

        # Create fresh agents for each match
        agent1 = RandomAgent(player=1, seed=seed)
        agent2 = RandomAgent(player=2, seed=seed + 10000)

        # Run the match
        result = run_match(agent1, agent2, seed=seed)

        # Save to database
        save_match(conn, result)
        total_frames += len(result["frames"])

        # Print progress every 10 matches
        if (i + 1) % 10 == 0 or i == args.matches - 1:
            elapsed = time.time() - start_time
            print(f"  {i + 1}/{args.matches} matches done "
                  f"({total_frames} frames, {elapsed:.1f}s)")

    conn.close()
    elapsed = time.time() - start_time

    print(f"\nDone! {args.matches} matches, {total_frames} frames "
          f"in {elapsed:.1f} seconds.")
    print(f"Database: {count_matches(get_connection(args.db))} total matches, "
          f"{count_frames(get_connection(args.db))} total frames.")


if __name__ == "__main__":
    main()
