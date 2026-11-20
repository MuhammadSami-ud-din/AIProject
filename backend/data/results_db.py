"""Results database manager (Addendum D).

Stores match results separately from frame-by-frame training logs:
- data/results.db: holds who won, match scores, round outcomes, human/AI records.
- data/fight_logs.db: holds per-frame logs for ML training.

All writes to results.db happen in ONE atomic transaction per match.
Parameterised SQL is strictly enforced.
"""

from contextlib import contextmanager
import csv
import datetime
import json
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_RESULTS_DB_PATH = os.path.join("data", "results.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mode TEXT NOT NULL,
    p1_kind TEXT CHECK(p1_kind IN ('human', 'ai')) NOT NULL,
    p1_character TEXT NOT NULL,
    p1_difficulty TEXT,
    p2_kind TEXT CHECK(p2_kind IN ('human', 'ai')) NOT NULL,
    p2_character TEXT NOT NULL,
    p2_difficulty TEXT,
    winner_side INTEGER CHECK(winner_side IN (0, 1, 2)) NOT NULL,
    rounds_p1 INTEGER NOT NULL DEFAULT 0,
    rounds_p2 INTEGER NOT NULL DEFAULT 0,
    duration_s REAL NOT NULL DEFAULT 0.0,
    arena TEXT NOT NULL,
    seed INTEGER,
    player_id INTEGER,
    status TEXT CHECK(status IN ('finished', 'abandoned')) NOT NULL,
    shield_enabled INTEGER NOT NULL DEFAULT 0,
    shield_preset TEXT DEFAULT 'Normal',
    shield_balance_json TEXT DEFAULT '{}',
    FOREIGN KEY(player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    winner_side INTEGER CHECK(winner_side IN (0, 1, 2)) NOT NULL,
    ended_by TEXT CHECK(ended_by IN ('KO', 'TIME', 'DRAW')) NOT NULL,
    p1_health_left REAL NOT NULL DEFAULT 0.0,
    p2_health_left REAL NOT NULL DEFAULT 0.0,
    duration_s REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_player_id ON matches(player_id);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_rounds_match_id ON rounds(match_id);

CREATE TABLE IF NOT EXISTS progress (
    player_id INTEGER PRIMARY KEY,
    coins INTEGER NOT NULL DEFAULT 0,
    crimson_level INTEGER NOT NULL DEFAULT 1,
    steel_level INTEGER NOT NULL DEFAULT 1,
    shadow_level INTEGER NOT NULL DEFAULT 1,
    golden_level INTEGER NOT NULL DEFAULT 1,
    campaign_unlocked_battle INTEGER NOT NULL DEFAULT 1,
    campaign_completed_battles TEXT NOT NULL DEFAULT '[]',
    campaign_stars TEXT NOT NULL DEFAULT '{}',
    total_coins_spent INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS trophies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    trophy_id TEXT NOT NULL,
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, trophy_id),
    FOREIGN KEY(player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    mission_id TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    target INTEGER NOT NULL DEFAULT 1,
    completed INTEGER NOT NULL DEFAULT 0,
    claimed INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, mission_id),
    FOREIGN KEY(player_id) REFERENCES players(player_id)
);
"""


class ResultsDB:
    """Manages the SQLite database for player profiles, match results, and stats."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = DEFAULT_RESULTS_DB_PATH
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        """Ensure parent directory exists if not an in-memory database."""
        if self.db_path != ":memory:":
            dirname = os.path.dirname(self.db_path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and return a configured sqlite3 connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def connection(self):
        """Context manager that manages connection lifecycle and closes on exit."""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database tables and indexes."""
        with self.connection() as conn:
            with conn:
                conn.executescript(SCHEMA_SQL)
                cols = {row["name"] for row in conn.execute("PRAGMA table_info(matches)").fetchall()}
                if "shield_enabled" not in cols:
                    conn.execute("ALTER TABLE matches ADD COLUMN shield_enabled INTEGER NOT NULL DEFAULT 0;")
                if "shield_preset" not in cols:
                    conn.execute("ALTER TABLE matches ADD COLUMN shield_preset TEXT DEFAULT 'Normal';")
                if "shield_balance_json" not in cols:
                    conn.execute("ALTER TABLE matches ADD COLUMN shield_balance_json TEXT DEFAULT '{}';")

    # ------------------------------------------------------------------
    # Player Management
    # ------------------------------------------------------------------
    def get_or_create_player(self, name: str = "Player") -> int:
        """Fetch or insert a player by name and return player_id."""
        clean_name = name.strip() or "Player"
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT player_id FROM players WHERE name = ?", (clean_name,))
            row = cur.fetchone()
            if row:
                return int(row["player_id"])
            with conn:
                cur.execute("INSERT INTO players (name) VALUES (?)", (clean_name,))
                return int(cur.lastrowid)

    def get_default_player(self) -> Optional[Dict[str, Any]]:
        """Get the primary/first registered player profile."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT player_id, name, created_at FROM players ORDER BY player_id ASC LIMIT 1")
            row = cur.fetchone()
            if row:
                return dict(row)
            return None

    def list_players(self) -> List[Dict[str, Any]]:
        """List all registered players."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT player_id, name, created_at FROM players ORDER BY player_id ASC")
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Match Saving (Single Atomic Transaction)
    # ------------------------------------------------------------------
    def save_match(self, match_data: Dict[str, Any]) -> str:
        """Save a match and its rounds in ONE atomic database transaction.

        match_data required keys:
        - mode: "Human vs AI" or "AI vs AI"
        - p1_kind: 'human' | 'ai'
        - p1_character: str
        - p1_difficulty: Optional[str]
        - p2_kind: 'human' | 'ai'
        - p2_character: str
        - p2_difficulty: Optional[str]
        - winner_side: 0 (draw), 1 (p1), 2 (p2)
        - rounds_p1: int
        - rounds_p2: int
        - duration_s: float
        - arena: str
        - seed: Optional[int]
        - player_id: Optional[int]
        - status: 'finished' | 'abandoned'
        - rounds_history: list of dicts (round_number, winner_side, ended_by, p1_health_left, p2_health_left, duration_s)
        """
        match_id = match_data.get("match_id") or str(uuid.uuid4())
        status = match_data.get("status", "finished")
        if status not in ("finished", "abandoned"):
            status = "finished"

        winner_side = int(match_data.get("winner_side", 0))
        # Abandoned matches count as no winner side for safety
        if status == "abandoned":
            winner_side = 0

        played_at = match_data.get("played_at") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        insert_match_sql = """
        INSERT INTO matches (
            match_id, played_at, mode, p1_kind, p1_character, p1_difficulty,
            p2_kind, p2_character, p2_difficulty, winner_side, rounds_p1, rounds_p2,
            duration_s, arena, seed, player_id, status,
            shield_enabled, shield_preset, shield_balance_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        insert_round_sql = """
        INSERT INTO rounds (
            match_id, round_number, winner_side, ended_by,
            p1_health_left, p2_health_left, duration_s
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        rounds_history = match_data.get("rounds_history", [])
        rounds_rows = []
        for r in rounds_history:
            ended_by = r.get("ended_by", "KO")
            if ended_by not in ("KO", "TIME", "DRAW"):
                ended_by = "KO"
            rounds_rows.append((
                match_id,
                int(r.get("round_number", 1)),
                int(r.get("winner_side", 0)),
                ended_by,
                float(r.get("p1_health_left", 0.0)),
                float(r.get("p2_health_left", 0.0)),
                float(r.get("duration_s", 0.0)),
            ))

        # Atomic transaction
        with self.connection() as conn:
            with conn:
                conn.execute(
                    insert_match_sql,
                    (
                        match_id,
                        played_at,
                        match_data.get("mode", "Human vs AI"),
                        match_data.get("p1_kind", "human"),
                        match_data.get("p1_character", "Golden"),
                        match_data.get("p1_difficulty"),
                        match_data.get("p2_kind", "ai"),
                        match_data.get("p2_character", "Crimson"),
                        match_data.get("p2_difficulty"),
                        winner_side,
                        int(match_data.get("rounds_p1", 0)),
                        int(match_data.get("rounds_p2", 0)),
                        float(match_data.get("duration_s", 0.0)),
                        str(match_data.get("arena", "Neon Rooftop")),
                        match_data.get("seed"),
                        match_data.get("player_id"),
                        status,
                        int(bool(match_data.get("shield_enabled", False))),
                        str(match_data.get("shield_preset", "Normal")),
                        json.dumps(match_data.get("shield_balance", {})),
                    )
                )
                if rounds_rows:
                    conn.executemany(insert_round_sql, rounds_rows)

        return match_id

    # ------------------------------------------------------------------
    # Statistics: Human Records & Streaks
    # ------------------------------------------------------------------
    def get_human_record(self, player_id: Optional[int] = None, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return human record per opponent character and difficulty:

        played, wins, losses, draws, current streak, best streak.
        Only 'finished' matches count. Optionally filtered by game mode.
        """
        with self.connection() as conn:
            cur = conn.cursor()

            # Query all finished human matches in chronological order
            query = """
            SELECT match_id, played_at, mode, p1_kind, p2_kind, p2_character, p2_difficulty,
                   winner_side, player_id
            FROM matches
            WHERE status = 'finished' AND (p1_kind = 'human' OR p2_kind = 'human')
            """
            params: List[Any] = []
            if player_id is not None:
                query += " AND player_id = ?"
                params.append(player_id)
            if mode is not None:
                query += " AND (mode = ? OR mode LIKE ?)"
                params.extend([mode, f"%{mode}%"])
            query += " ORDER BY played_at ASC, rowid ASC"

            cur.execute(query, params)
            matches = cur.fetchall()

        # Group matches by (opponent_character, difficulty)
        groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for row in matches:
            m = dict(row)
            opp_char = m["p2_character"]
            opp_diff = m["p2_difficulty"] or "UNKNOWN"
            key = (opp_char, opp_diff)
            if key not in groups:
                groups[key] = []
            groups[key].append(m)

        results: List[Dict[str, Any]] = []
        for (opp_char, diff), match_list in sorted(groups.items()):
            played = len(match_list)
            wins = 0
            losses = 0
            draws = 0
            cur_streak = 0
            best_streak = 0

            for m in match_list:
                w_side = m["winner_side"]
                # P1 is human
                if m["p1_kind"] == "human":
                    if w_side == 1:
                        wins += 1
                        cur_streak += 1
                        if cur_streak > best_streak:
                            best_streak = cur_streak
                    elif w_side == 2:
                        losses += 1
                        cur_streak = 0
                    else:
                        draws += 1
                        cur_streak = 0
                else:  # P2 is human
                    if w_side == 2:
                        wins += 1
                        cur_streak += 1
                        if cur_streak > best_streak:
                            best_streak = cur_streak
                    elif w_side == 1:
                        losses += 1
                        cur_streak = 0
                    else:
                        draws += 1
                        cur_streak = 0

            results.append({
                "opponent": opp_char,
                "difficulty": diff,
                "played": played,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "current_streak": cur_streak,
                "best_streak": best_streak,
            })

        return results

    def get_last_matches(self, player_id: Optional[int] = None, limit: int = 10, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return the last N finished matches for the player. Optionally filtered by mode."""
        with self.connection() as conn:
            cur = conn.cursor()
            query = """
            SELECT match_id, played_at, mode, p1_character, p2_character, p2_difficulty,
                   winner_side, rounds_p1, rounds_p2, duration_s, arena
            FROM matches
            WHERE status = 'finished' AND (p1_kind = 'human' OR p2_kind = 'human')
            """
            params: List[Any] = []
            if player_id is not None:
                query += " AND player_id = ?"
                params.append(player_id)
            if mode is not None:
                query += " AND (mode = ? OR mode LIKE ?)"
                params.extend([mode, f"%{mode}%"])
            query += " ORDER BY played_at DESC, rowid DESC LIMIT ?"
            params.append(limit)

            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Statistics: AI Records & History
    # ------------------------------------------------------------------
    def get_ai_record(self, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return record per AI character and difficulty:

        played, wins, losses, draws, split into 'vs human' and 'vs AI'.
        Only 'finished' matches count. Optionally filtered by game mode.
        """
        with self.connection() as conn:
            cur = conn.cursor()
            query = """
            SELECT match_id, mode, p1_kind, p1_character, p1_difficulty,
                   p2_kind, p2_character, p2_difficulty, winner_side
            FROM matches
            WHERE status = 'finished'
            """
            params: List[Any] = []
            if mode is not None:
                query += " AND (mode = ? OR mode LIKE ?)"
                params.extend([mode, f"%{mode}%"])

            cur.execute(query, params)
            matches = [dict(r) for r in cur.fetchall()]

        # Key: (ai_character, difficulty, opponent_type) -> stats
        records: Dict[Tuple[str, str, str], Dict[str, int]] = {}

        def record_ai(char: str, diff: str, opp_type: str, result: str):
            diff = diff or "LOW"
            k = (char, diff, opp_type)
            if k not in records:
                records[k] = {"played": 0, "wins": 0, "losses": 0, "draws": 0}
            records[k]["played"] += 1
            if result == "win":
                records[k]["wins"] += 1
            elif result == "loss":
                records[k]["losses"] += 1
            else:
                records[k]["draws"] += 1

        for m in matches:
            w_side = m["winner_side"]
            p1_kind = m["p1_kind"]
            p2_kind = m["p2_kind"]

            # If P1 was AI
            if p1_kind == "ai":
                opp_type = "vs human" if p2_kind == "human" else "vs AI"
                if w_side == 1:
                    res = "win"
                elif w_side == 2:
                    res = "loss"
                else:
                    res = "draw"
                record_ai(m["p1_character"], m["p1_difficulty"], opp_type, res)

            # If P2 was AI
            if p2_kind == "ai":
                opp_type = "vs human" if p1_kind == "human" else "vs AI"
                if w_side == 2:
                    res = "win"
                elif w_side == 1:
                    res = "loss"
                else:
                    res = "draw"
                record_ai(m["p2_character"], m["p2_difficulty"], opp_type, res)

        results: List[Dict[str, Any]] = []
        for (char, diff, opp_type), s in sorted(records.items()):
            win_pct = round((s["wins"] / s["played"]) * 100, 1) if s["played"] > 0 else 0.0
            results.append({
                "character": char,
                "difficulty": diff,
                "opponent_type": opp_type,
                "played": s["played"],
                "wins": s["wins"],
                "losses": s["losses"],
                "draws": s["draws"],
                "win_pct": win_pct,
            })
        return results

    def get_ai_history(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Return chronological history of AI match results.

        Example string format:
        "Crimson (HELL) beat Steel (HIGH), 2-1, 12 Nov 17:20"
        """
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT match_id, played_at, mode, p1_kind, p1_character, p1_difficulty,
                   p2_kind, p2_character, p2_difficulty, winner_side, rounds_p1, rounds_p2
            FROM matches
            WHERE status = 'finished'
            ORDER BY played_at DESC, rowid DESC
            LIMIT ?
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]

        history: List[Dict[str, Any]] = []
        for r in rows:
            # Parse datetime for nice string representation
            dt_str = r["played_at"]
            try:
                dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                nice_date = dt.strftime("%d %b %H:%M")
            except Exception:
                nice_date = str(dt_str)

            p1_desc = f"{r['p1_character']}" + (f" ({r['p1_difficulty']})" if r["p1_kind"] == "ai" and r["p1_difficulty"] else "")
            p2_desc = f"{r['p2_character']}" + (f" ({r['p2_difficulty']})" if r["p2_kind"] == "ai" and r["p2_difficulty"] else "")

            w_side = r["winner_side"]
            if w_side == 1:
                summary = f"{p1_desc} beat {p2_desc}, {r['rounds_p1']}-{r['rounds_p2']}, {nice_date}"
            elif w_side == 2:
                summary = f"{p2_desc} beat {p1_desc}, {r['rounds_p2']}-{r['rounds_p1']}, {nice_date}"
            else:
                summary = f"{p1_desc} drew {p2_desc}, {r['rounds_p1']}-{r['rounds_p2']}, {nice_date}"

            history.append({
                "match_id": r["match_id"],
                "summary": summary,
                "played_at": r["played_at"],
                "winner_side": w_side,
            })
        return history

    # ------------------------------------------------------------------
    # Settings Operations: Export CSV & Reset
    # ------------------------------------------------------------------
    def export_results_to_csv(self, output_path: str = "data/results_export.csv") -> str:
        """Export all matches and rounds to a CSV file."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT m.match_id, m.played_at, m.mode, m.status,
                   m.p1_kind, m.p1_character, m.p1_difficulty,
                   m.p2_kind, m.p2_character, m.p2_difficulty,
                   m.winner_side, m.rounds_p1, m.rounds_p2,
                   m.duration_s, m.arena, m.seed,
                   p.name AS player_name
            FROM matches m
            LEFT JOIN players p ON m.player_id = p.player_id
            ORDER BY m.played_at ASC
            """)
            rows = [dict(r) for r in cur.fetchall()]

        if not rows:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["match_id", "status", "message"])
                writer.writerow(["none", "empty", "No matches recorded yet"])
            return output_path

        fieldnames = list(rows[0].keys())
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return output_path

    def reset_results(self, player_id: Optional[int] = None):
        """Reset match results. If player_id is given, reset only for that player."""
        with self.connection() as conn:
            with conn:
                if player_id is not None:
                    # Find matches for this player
                    cur = conn.cursor()
                    cur.execute("SELECT match_id FROM matches WHERE player_id = ?", (player_id,))
                    m_ids = [r["match_id"] for r in cur.fetchall()]
                    if m_ids:
                        placeholders = ", ".join("?" for _ in m_ids)
                        conn.execute(f"DELETE FROM rounds WHERE match_id IN ({placeholders})", m_ids)
                        conn.execute(f"DELETE FROM matches WHERE match_id IN ({placeholders})", m_ids)
                else:
                    conn.execute("DELETE FROM rounds")
                    conn.execute("DELETE FROM matches")

    # ------------------------------------------------------------------
    # Economy & Progression (Campaign, Levels, Currency, Trophies)
    # ------------------------------------------------------------------
    def get_or_create_progress(self, player_id: int) -> Dict[str, Any]:
        """Fetch player progression row, creating default row if nonexistent."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM progress WHERE player_id = ?", (player_id,))
            row = cur.fetchone()
            if row is None:
                with conn:
                    cur.execute(
                        "INSERT INTO progress (player_id, coins) VALUES (?, 0)",
                        (player_id,),
                    )
                cur.execute("SELECT * FROM progress WHERE player_id = ?", (player_id,))
                row = cur.fetchone()
            res = dict(row)
            if isinstance(res.get("campaign_completed_battles"), str):
                try:
                    res["campaign_completed_battles"] = json.loads(res["campaign_completed_battles"])
                except Exception:
                    res["campaign_completed_battles"] = []
            if isinstance(res.get("campaign_stars"), str):
                try:
                    res["campaign_stars"] = json.loads(res["campaign_stars"])
                except Exception:
                    res["campaign_stars"] = {}
            return res

    def add_coins(self, player_id: int, amount: int) -> int:
        """Add coins to a player's balance and return new total."""
        self.get_or_create_progress(player_id)
        with self.connection() as conn:
            with conn:
                conn.execute(
                    "UPDATE progress SET coins = coins + ? WHERE player_id = ?",
                    (amount, player_id),
                )
            cur = conn.cursor()
            cur.execute("SELECT coins FROM progress WHERE player_id = ?", (player_id,))
            row = cur.fetchone()
            return int(row["coins"]) if row else 0

    def spend_coins(self, player_id: int, amount: int) -> bool:
        """Deduct coins if balance is sufficient. Returns True on success."""
        prog = self.get_or_create_progress(player_id)
        if prog["coins"] < amount:
            return False
        with self.connection() as conn:
            with conn:
                conn.execute(
                    """UPDATE progress 
                       SET coins = coins - ?, total_coins_spent = total_coins_spent + ?
                       WHERE player_id = ?""",
                    (amount, amount, player_id),
                )
        return True

    def get_character_level(self, player_id: int, character_name: str) -> int:
        """Get character level (1-20) for a given player."""
        prog = self.get_or_create_progress(player_id)
        col = f"{character_name.lower()}_level"
        return int(prog.get(col, 1))

    def set_character_level(self, player_id: int, character_name: str, level: int) -> None:
        """Set character level for a player."""
        self.get_or_create_progress(player_id)
        col = f"{character_name.lower()}_level"
        with self.connection() as conn:
            with conn:
                conn.execute(f"UPDATE progress SET {col} = ? WHERE player_id = ?", (level, player_id))

    def get_campaign_progress(self, player_id: int) -> Dict[str, Any]:
        """Get campaign state: unlocked battle, completed battles list, stars dict."""
        prog = self.get_or_create_progress(player_id)
        return {
            "unlocked_battle": prog.get("campaign_unlocked_battle", 1),
            "completed_battles": prog.get("campaign_completed_battles", []),
            "stars": prog.get("campaign_stars", {}),
        }

    def save_campaign_battle_result(self, player_id: int, battle_id: int, stars: int) -> None:
        """Record victory in a campaign battle, updating stars and unlocking next."""
        camp = self.get_campaign_progress(player_id)
        unlocked = max(camp["unlocked_battle"], battle_id + 1)
        completed = list(set(camp["completed_battles"] + [battle_id]))
        star_dict = camp["stars"]
        star_dict[str(battle_id)] = max(star_dict.get(str(battle_id), 0), stars)

        with self.connection() as conn:
            with conn:
                conn.execute(
                    """UPDATE progress 
                       SET campaign_unlocked_battle = ?,
                           campaign_completed_battles = ?,
                           campaign_stars = ?
                       WHERE player_id = ?""",
                    (unlocked, json.dumps(completed), json.dumps(star_dict), player_id),
                )

    def unlock_trophy(self, player_id: int, trophy_id: str) -> bool:
        """Unlock a trophy for a player. Returns True if freshly unlocked."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM trophies WHERE player_id = ? AND trophy_id = ?", (player_id, trophy_id))
            if cur.fetchone():
                return False
            with conn:
                conn.execute("INSERT OR IGNORE INTO trophies (player_id, trophy_id) VALUES (?, ?)", (player_id, trophy_id))
            return True

    def get_unlocked_trophy_ids(self, player_id: int) -> set[str]:
        """Return set of unlocked trophy IDs for a player."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT trophy_id FROM trophies WHERE player_id = ?", (player_id,))
            return {row["trophy_id"] for row in cur.fetchall()}

    def get_missions(self, player_id: int) -> List[Dict[str, Any]]:
        """Fetch all mission records for a player."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM missions WHERE player_id = ?", (player_id,))
            return [dict(r) for r in cur.fetchall()]

    def update_mission(self, player_id: int, mission_id: str, delta: int, target: int) -> Tuple[bool, bool]:
        """Update progress on a mission. Returns (is_completed, is_newly_completed)."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM missions WHERE player_id = ? AND mission_id = ?", (player_id, mission_id))
            row = cur.fetchone()
            if row is None:
                new_prog = min(target, delta)
                completed = 1 if new_prog >= target else 0
                with conn:
                    conn.execute(
                        """INSERT INTO missions (player_id, mission_id, progress, target, completed)
                           VALUES (?, ?, ?, ?, ?)""",
                        (player_id, mission_id, new_prog, target, completed),
                    )
                return bool(completed), bool(completed)
            else:
                old_comp = bool(row["completed"])
                new_prog = min(target, row["progress"] + delta)
                new_comp = 1 if new_prog >= target else 0
                with conn:
                    conn.execute(
                        """UPDATE missions 
                           SET progress = ?, target = ?, completed = ?, updated_at = CURRENT_TIMESTAMP
                           WHERE player_id = ? AND mission_id = ?""",
                        (new_prog, target, new_comp, player_id, mission_id),
                    )
                return bool(new_comp), (not old_comp and bool(new_comp))

    def claim_mission(self, player_id: int, mission_id: str) -> bool:
        """Mark a completed mission as claimed. Returns True if successfully claimed."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM missions WHERE player_id = ? AND mission_id = ?", (player_id, mission_id))
            row = cur.fetchone()
            if not row or not row["completed"] or row["claimed"]:
                return False
            with conn:
                conn.execute(
                    "UPDATE missions SET claimed = 1 WHERE player_id = ? AND mission_id = ?",
                    (player_id, mission_id),
                )
            return True



# Singleton instance pointing to data/results.db
results_db = ResultsDB()


def __getattr__(name: str):
    """Delegate module-level attribute lookups to the singleton `results_db` instance.

    Prevents AttributeError if a caller does:
        from backend.data import results_db
        results_db.get_player(...)
    instead of:
        from backend.data.results_db import results_db
    """
    if hasattr(results_db, name):
        return getattr(results_db, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

