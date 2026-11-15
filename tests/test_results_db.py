"""Tests for ResultsDB (Addendum D)."""

import os
import tempfile
import pytest

from backend.data.results_db import ResultsDB


@pytest.fixture
def temp_db():
    """Create a fresh in-memory or temporary ResultsDB for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_results.db")
        db = ResultsDB(db_path=db_path)
        yield db


def test_player_creation(temp_db):
    """Test creating and retrieving player profiles."""
    p1_id = temp_db.get_or_create_player("Alice")
    assert p1_id > 0
    # Re-fetching returns same id
    p1_id_again = temp_db.get_or_create_player("Alice")
    assert p1_id == p1_id_again

    default_player = temp_db.get_default_player()
    assert default_player is not None
    assert default_player["name"] == "Alice"
    assert default_player["player_id"] == p1_id


def test_save_finished_match_and_rounds(temp_db):
    """Test saving a finished match adds one row to matches and rows to rounds."""
    p_id = temp_db.get_or_create_player("Hero")

    match_data = {
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Crimson",
        "p2_difficulty": "MEDIUM",
        "winner_side": 1,
        "rounds_p1": 2,
        "rounds_p2": 0,
        "duration_s": 35.5,
        "arena": "arena_volcanic_forge.jpeg",
        "seed": 42,
        "player_id": p_id,
        "status": "finished",
        "rounds_history": [
            {
                "round_number": 1,
                "winner_side": 1,
                "ended_by": "KO",
                "p1_health_left": 0.45,
                "p2_health_left": 0.0,
                "duration_s": 18.0,
            },
            {
                "round_number": 2,
                "winner_side": 1,
                "ended_by": "KO",
                "p1_health_left": 0.60,
                "p2_health_left": 0.0,
                "duration_s": 17.5,
            },
        ],
    }

    match_id = temp_db.save_match(match_data)
    assert match_id is not None

    with temp_db.connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,))
        m_row = cur.fetchone()
        assert m_row is not None
        assert m_row["status"] == "finished"
        assert m_row["winner_side"] == 1
        assert m_row["rounds_p1"] == 2

        cur.execute("SELECT * FROM rounds WHERE match_id = ? ORDER BY round_number ASC", (match_id,))
        r_rows = cur.fetchall()
        assert len(r_rows) == 2
        assert r_rows[0]["ended_by"] == "KO"
        assert r_rows[1]["p1_health_left"] == 0.60


def test_human_record_and_streaks(temp_db):
    """Verify human records, wins/losses, and current/best streak tracking."""
    p_id = temp_db.get_or_create_player("Player1")

    # Match 1: Win against Crimson (HARD)
    temp_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Crimson",
        "p2_difficulty": "HARD",
        "winner_side": 1,
        "player_id": p_id,
        "status": "finished",
    })

    # Match 2: Win again against Crimson (HARD)
    temp_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Crimson",
        "p2_difficulty": "HARD",
        "winner_side": 1,
        "player_id": p_id,
        "status": "finished",
    })

    records = temp_db.get_human_record(player_id=p_id)
    assert len(records) == 1
    assert records[0]["opponent"] == "Crimson"
    assert records[0]["difficulty"] == "HARD"
    assert records[0]["played"] == 2
    assert records[0]["wins"] == 2
    assert records[0]["losses"] == 0
    assert records[0]["current_streak"] == 2
    assert records[0]["best_streak"] == 2

    # Match 3: Loss against Crimson (HARD) -> streak breaks
    temp_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Crimson",
        "p2_difficulty": "HARD",
        "winner_side": 2,
        "player_id": p_id,
        "status": "finished",
    })

    records_after_loss = temp_db.get_human_record(player_id=p_id)
    assert records_after_loss[0]["played"] == 3
    assert records_after_loss[0]["wins"] == 2
    assert records_after_loss[0]["losses"] == 1
    assert records_after_loss[0]["current_streak"] == 0  # reset to 0
    assert records_after_loss[0]["best_streak"] == 2     # preserved best streak


def test_abandoned_match_does_not_change_wins_or_streak(temp_db):
    """An abandoned match must not count as a win or loss."""
    p_id = temp_db.get_or_create_player("Player1")

    # Finished win
    temp_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Shadow",
        "p2_difficulty": "MEDIUM",
        "winner_side": 1,
        "player_id": p_id,
        "status": "finished",
    })

    # Abandoned match (quit halfway)
    temp_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Shadow",
        "p2_difficulty": "MEDIUM",
        "winner_side": 1,
        "player_id": p_id,
        "status": "abandoned",
    })

    records = temp_db.get_human_record(player_id=p_id)
    assert len(records) == 1
    assert records[0]["played"] == 1  # only 1 finished match counted
    assert records[0]["wins"] == 1
    assert records[0]["losses"] == 0
    assert records[0]["current_streak"] == 1


def test_ai_record_and_history(temp_db):
    """Verify AI record split by 'vs human' and 'vs AI' and history formatting."""
    # AI vs Human match
    temp_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Steel",
        "p2_difficulty": "HIGH",
        "winner_side": 2,  # Steel wins
        "status": "finished",
    })

    # AI vs AI match
    temp_db.save_match({
        "mode": "AI vs AI",
        "p1_kind": "ai",
        "p1_character": "Crimson",
        "p1_difficulty": "HELL",
        "p2_kind": "ai",
        "p2_character": "Steel",
        "p2_difficulty": "HIGH",
        "winner_side": 1,  # Crimson wins
        "rounds_p1": 2,
        "rounds_p2": 1,
        "played_at": "2026-11-12 17:20:00",
        "status": "finished",
    })

    ai_records = temp_db.get_ai_record()
    assert len(ai_records) >= 2

    # Check Steel vs human
    steel_vs_human = next(r for r in ai_records if r["character"] == "Steel" and r["opponent_type"] == "vs human")
    assert steel_vs_human["played"] == 1
    assert steel_vs_human["wins"] == 1
    assert steel_vs_human["win_pct"] == 100.0

    # Check Crimson vs AI
    crimson_vs_ai = next(r for r in ai_records if r["character"] == "Crimson" and r["opponent_type"] == "vs AI")
    assert crimson_vs_ai["played"] == 1
    assert crimson_vs_ai["wins"] == 1

    # Check AI History formatting
    history = temp_db.get_ai_history()
    assert len(history) == 2
    # Example format check: "Crimson (HELL) beat Steel (HIGH), 2-1, 12 Nov 17:20"
    matches_found = [h for h in history if "Crimson (HELL) beat Steel (HIGH), 2-1" in h["summary"]]
    assert len(matches_found) == 1
    assert "12 Nov 17:20" in matches_found[0]["summary"]


def test_csv_export_and_reset(temp_db):
    """Test exporting results to CSV and resetting results."""
    p_id = temp_db.get_or_create_player("TestUser")
    temp_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Crimson",
        "winner_side": 1,
        "player_id": p_id,
        "status": "finished",
    })

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = os.path.join(tmpdir, "exported.csv")
        out_path = temp_db.export_results_to_csv(csv_file)
        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Golden" in content
            assert "Crimson" in content

    # Test Reset Results
    temp_db.reset_results()
    assert len(temp_db.get_human_record()) == 0
    # Player profile still exists after resetting matches
    assert temp_db.get_default_player() is not None
