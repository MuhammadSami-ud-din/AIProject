"""SQLite database for storing fight logs.

One row per frame: match_id, frame, round, agent names and difficulties,
seed, all feature columns, chosen actions, and the round result.
"""

import os
import sqlite3
import uuid

from backend.ai.observation import FEATURE_NAMES

# Default database path (inside backend/data/)
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "fights.db")

# The columns that come from observation.features()
_FEATURE_COLUMNS = ", ".join(f"{name} REAL" for name in FEATURE_NAMES)

# Full CREATE TABLE statement
_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    frame INTEGER NOT NULL,
    round INTEGER NOT NULL,
    agent1_name TEXT NOT NULL,
    agent1_difficulty TEXT NOT NULL,
    agent2_name TEXT NOT NULL,
    agent2_difficulty TEXT NOT NULL,
    seed INTEGER,
    action1 TEXT NOT NULL,
    action2 TEXT NOT NULL,
    match_result TEXT,
    {_FEATURE_COLUMNS}
);
"""

# Index on match_id for fast lookups
_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_match_id ON frames (match_id);
"""


def get_connection(db_path=None):
    """Open (or create) the database and return a connection."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")  # faster for many writes
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_INDEX)
    # Ensure all feature columns exist even if table was created previously
    cursor = conn.execute("PRAGMA table_info(frames);")
    existing_cols = {row[1] for row in cursor.fetchall()}
    for name in FEATURE_NAMES:
        if name not in existing_cols:
            conn.execute(f"ALTER TABLE frames ADD COLUMN {name} REAL DEFAULT 0.0;")
    conn.commit()
    return conn


def save_match(conn, match_data):
    """Save all frames from one match to the database.

    match_data is the dictionary returned by run_match().
    Returns the match_id that was assigned.
    """
    match_id = str(uuid.uuid4())
    frames = match_data["frames"]
    match_result = match_data["match_result"]

    if not frames:
        return match_id

    # Build the column names from the first frame's keys
    # (all frames have the same keys)
    first = frames[0]

    # Columns in the order we will insert them
    columns = ["match_id", "frame", "round",
                "agent1_name", "agent1_difficulty",
                "agent2_name", "agent2_difficulty",
                "seed", "action1", "action2", "match_result"]
    columns.extend(FEATURE_NAMES)

    placeholders = ", ".join("?" for _ in columns)
    column_names = ", ".join(columns)
    sql = f"INSERT INTO frames ({column_names}) VALUES ({placeholders})"

    # Build rows
    rows = []
    for record in frames:
        row = [
            match_id,
            record["frame"],
            record["round"],
            record["agent1_name"],
            record["agent1_difficulty"],
            record["agent2_name"],
            record["agent2_difficulty"],
            record["seed"],
            record["action1"],
            record["action2"],
            match_result,
        ]
        # Add feature values in the agreed order
        for name in FEATURE_NAMES:
            row.append(record[name])
        rows.append(row)

    conn.executemany(sql, rows)
    conn.commit()
    return match_id


def count_matches(conn):
    """How many distinct matches are in the database."""
    cursor = conn.execute("SELECT COUNT(DISTINCT match_id) FROM frames")
    return cursor.fetchone()[0]


def count_frames(conn):
    """Total number of frame rows in the database."""
    cursor = conn.execute("SELECT COUNT(*) FROM frames")
    return cursor.fetchone()[0]


def get_match_ids(conn, limit=100):
    """Return a list of match_ids, newest first."""
    cursor = conn.execute(
        "SELECT DISTINCT match_id FROM frames ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    return [row[0] for row in cursor.fetchall()]


def get_match_frames(conn, match_id):
    """Return all frame rows for a given match as a list of dicts."""
    cursor = conn.execute(
        "SELECT * FROM frames WHERE match_id = ? ORDER BY frame",
        (match_id,)
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
