"""Tests for two-tab statistics screen and updated settings screen options."""

import os
import pygame
import pytest

os.environ["SDL_VIDEODRIVER"] = "dummy"

from backend.data.results_db import ResultsDB
from frontend.screens import player_name_prompt, settings_screen, statistics_screen


@pytest.fixture(autouse=True)
def ensure_pygame_init():
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1024, 600))
    pygame.event.clear()
    yield
    pygame.event.clear()


@pytest.fixture
def mock_surface_clock():
    surface = pygame.display.get_surface()
    if surface is None:
        surface = pygame.Surface((1024, 600))
    clock = pygame.time.Clock()
    return surface, clock


def test_player_name_prompt(mock_surface_clock):
    """Test entering a player name in the first-launch prompt."""
    surface, clock = mock_surface_clock

    # Queue typing 'Ace' followed by Enter
    for char in "Ace":
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": ord(char), "unicode": char}))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "unicode": ""}))

    name = player_name_prompt(surface, clock)
    # Starts with 'Player' and appends 'Ace' -> 'PlayerAce'
    assert "Ace" in name


def test_statistics_screen_you_and_ai_tabs(mock_surface_clock, monkeypatch, tmp_path):
    """Test that statistics screen renders tab 0 ('You') and switches to tab 1 ('AI')."""
    surface, clock = mock_surface_clock

    db_path = str(tmp_path / "test_stats_view.db")
    custom_db = ResultsDB(db_path=db_path)
    p_id = custom_db.get_or_create_player("Champion")

    custom_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Crimson",
        "p2_difficulty": "HIGH",
        "winner_side": 1,
        "rounds_p1": 2,
        "rounds_p2": 0,
        "duration_s": 30.0,
        "arena": "arena_neon_rooftop.jpeg",
        "player_id": p_id,
        "status": "finished",
        "rounds_history": [
            {"round_number": 1, "winner_side": 1, "ended_by": "KO", "duration_s": 15.0},
            {"round_number": 2, "winner_side": 1, "ended_by": "KO", "duration_s": 15.0},
        ],
    })

    import frontend.screens
    monkeypatch.setattr(frontend.screens, "results_db", custom_db)

    # Queue switching to AI tab (key '2') then ESC
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2}))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))

    # Should run and exit without crashing
    statistics_screen(surface, clock, player_id=p_id)


def test_settings_screen_csv_export_and_reset(mock_surface_clock, monkeypatch, tmp_path):
    """Test settings menu CSV export action and reset confirmation."""
    surface, clock = mock_surface_clock

    db_path = str(tmp_path / "test_settings_ops.db")
    custom_db = ResultsDB(db_path=db_path)
    custom_db.save_match({
        "mode": "Human vs AI",
        "p1_kind": "human",
        "p1_character": "Golden",
        "p2_kind": "ai",
        "p2_character": "Shadow",
        "winner_side": 1,
        "status": "finished",
    })

    import frontend.screens
    monkeypatch.setattr(frontend.screens, "results_db", custom_db)

    settings = {"log_fights": False, "speed": 1.0, "show_ai": True}

    # Queue navigating down to 'export_csv' (index 3: down x 3), Enter, then ESC
    for _ in range(3):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN}))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))

    res_settings = settings_screen(surface, clock, settings)
    assert res_settings is not None
    assert os.path.exists("data/results_export.csv")
