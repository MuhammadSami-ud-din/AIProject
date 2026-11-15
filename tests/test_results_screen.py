"""Tests for the match result screen (Addendum B)."""

import os
import pygame
import pytest

# Ensure headless pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"

from frontend.screens import results_screen


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


def test_results_screen_human_win_rematch(mock_surface_clock):
    """Human win produces 'YOU WIN', and pressing 'r' returns 'rematch'."""
    surface, clock = mock_surface_clock

    stats = {
        "p1_name": "Player",
        "p2_name": "Crimson Brawler",
        "p1_character": "Golden",
        "p2_character": "Crimson",
        "p1_kind": "human",
        "p2_kind": "ai",
        "p1_difficulty": "LOW",
        "p2_difficulty": "HARD",
        "arena": "arena_neon_rooftop.jpeg",
        "damage_dealt_p1": 185.0,
        "damage_dealt_p2": 95.0,
        "hits_landed_p1": 12,
        "hits_landed_p2": 6,
        "blocks_p1": 4,
        "blocks_p2": 2,
        "longest_combo_p1": 3,
        "longest_combo_p2": 1,
        "winner_side": 1,
        "rounds_p1": 2,
        "rounds_p2": 1,
        "duration_s": 42.5,
        "status": "finished",
        "match_result": "p1",
        "rounds_history": [
            {"round_number": 1, "winner_side": 1, "ended_by": "KO", "duration_s": 12.0},
            {"round_number": 2, "winner_side": 2, "ended_by": "TIME", "duration_s": 18.0},
            {"round_number": 3, "winner_side": 1, "ended_by": "KO", "duration_s": 12.5},
        ],
    }

    # Queue an 'r' key event to test rematch
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r}))

    action = results_screen(surface, clock, stats, lockout_s=0.0)
    assert action == "rematch"


def test_results_screen_human_loss_char_select(mock_surface_clock):
    """Human loss produces 'YOU LOSE', and pressing 'c' returns 'character_select'."""
    surface, clock = mock_surface_clock

    stats = {
        "p1_name": "Player",
        "p2_name": "Steel",
        "p1_character": "Shadow",
        "p2_character": "Steel",
        "p1_kind": "human",
        "p2_kind": "ai",
        "p2_difficulty": "MEDIUM",
        "winner_side": 2,
        "rounds_p1": 0,
        "rounds_p2": 2,
        "duration_s": 25.0,
        "match_result": "p2",
    }

    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_c}))
    action = results_screen(surface, clock, stats, lockout_s=0.0)
    assert action == "character_select"


def test_results_screen_menu_escape(mock_surface_clock):
    """Pressing ESC returns 'menu'."""
    surface, clock = mock_surface_clock

    stats = {
        "p1_name": "Player",
        "p2_name": "Steel",
        "p1_character": "Shadow",
        "p2_character": "Steel",
        "p1_kind": "human",
        "p2_kind": "ai",
        "winner_side": 0,
        "rounds_p1": 1,
        "rounds_p2": 1,
        "match_result": "draw",
    }

    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    action = results_screen(surface, clock, stats, lockout_s=0.0)
    assert action == "menu"


def test_results_screen_ai_auto_timeout(mock_surface_clock):
    """AI vs AI automatically times out and returns 'menu'."""
    surface, clock = mock_surface_clock

    stats = {
        "p1_name": "Crimson",
        "p2_name": "Steel",
        "p1_character": "Crimson",
        "p2_character": "Steel",
        "p1_kind": "ai",
        "p2_kind": "ai",
        "winner_side": 1,
        "rounds_p1": 2,
        "rounds_p2": 0,
    }

    # Set lockout_s=0 and ai_timeout_s=0 so it times out immediately
    action = results_screen(surface, clock, stats, lockout_s=0.0, ai_timeout_s=0.0)
    assert action == "menu"


def test_results_screen_backwards_compatibility(mock_surface_clock):
    """Old call signature results_screen(surface, clock, match_result, p1_name, p2_name) works."""
    surface, clock = mock_surface_clock

    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    action = results_screen(surface, clock, "p1", "Player", "Shadow", lockout_s=0.0)
    assert action == "menu"


def test_results_screen_lockout_ignores_early_input(mock_surface_clock, monkeypatch):
    """Inputs sent while locked are ignored; after unlock, input is accepted."""
    import time

    surface, clock = mock_surface_clock
    stats = {
        "p1_name": "Player",
        "p2_name": "Crimson",
        "p1_character": "Golden",
        "p2_character": "Crimson",
        "p1_kind": "human",
        "p2_kind": "ai",
        "winner_side": 1,
    }

    simulated_time = 100.0

    def mock_time():
        return simulated_time

    class MockClock:
        def tick(self, fps=30):
            nonlocal simulated_time
            simulated_time += 1.5
            if simulated_time >= 103.0:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_c}))

    monkeypatch.setattr(time, "time", mock_time)
    mock_clock = MockClock()

    # First event posted during locked time (should be ignored)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r}))

    action = results_screen(surface, mock_clock, stats, lockout_s=3.0)
    assert action == "character_select"


def test_damage_212_shown_as_212_hp():
    """Requirement 1: Health is stored 0..1. Show damage as HP (2.12 -> '212 HP'). Never 'dmg'."""
    from frontend.screens import format_hp_stat

    assert format_hp_stat(2.12) == "212 HP"
    assert format_hp_stat(0.45) == "45 HP"
    assert format_hp_stat(1.0) == "100 HP"
    assert format_hp_stat(0.0) == "0 HP"
    assert format_hp_stat(185.0) == "185 HP"
    assert "dmg" not in format_hp_stat(2.12)


def test_results_screen_damage_and_health_left_hp(mock_surface_clock):
    """Test results screen with 2.12 damage and health left row."""
    surface, clock = mock_surface_clock
    stats = {
        "p1_name": "Player",
        "p2_name": "Crimson",
        "p1_character": "Golden",
        "p2_character": "Crimson",
        "p1_kind": "human",
        "p2_kind": "ai",
        "p2_difficulty": "LOW",
        "damage_dealt_p1": 2.12,
        "damage_dealt_p2": 1.45,
        "hits_landed_p1": 15,
        "hits_landed_p2": 8,
        "blocks_p1": 5,
        "blocks_p2": 2,
        "longest_combo_p1": 4,
        "longest_combo_p2": 2,
        "winner_side": 1,
        "rounds_p1": 2,
        "rounds_p2": 1,
        "duration_s": 42.0,
        "rounds_history": [
            {"round_number": 1, "winner_side": 1, "ended_by": "KO", "p1_health_left": 0.55, "p2_health_left": 0.0},
            {"round_number": 2, "winner_side": 2, "ended_by": "KO", "p1_health_left": 0.0, "p2_health_left": 0.30},
            {"round_number": 3, "winner_side": 1, "ended_by": "KO", "p1_health_left": 0.72, "p2_health_left": 0.0},
        ],
    }

    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    action = results_screen(surface, clock, stats, lockout_s=0.0)
    assert action in ("rematch", "character_select", "menu")


def test_results_screen_arrow_selection_and_enter(mock_surface_clock):
    """Arrow keys change button selection, and Enter activates the selected button."""
    surface, clock = mock_surface_clock
    stats = {
        "p1_name": "Player",
        "p2_name": "Crimson",
        "p1_character": "Golden",
        "p2_character": "Crimson",
        "p1_kind": "human",
        "p2_kind": "ai",
        "winner_side": 1,
    }

    # Default is Main Menu (index 2). Left arrow -> Character Select (1), Left arrow -> Rematch (0)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_LEFT}))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_LEFT}))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))

    action = results_screen(surface, clock, stats, lockout_s=0.0)
    assert action == "rematch"


def test_results_screen_mirror_match(mock_surface_clock):
    """Mirror match handles (Alt) suffix and alternate palette styling without error."""
    surface, clock = mock_surface_clock
    stats = {
        "p1_name": "Player",
        "p2_name": "AI Mirror",
        "p1_character": "Golden",
        "p2_character": "Golden",
        "p1_kind": "human",
        "p2_kind": "ai",
        "winner_side": 2,
        "rounds_p1": 1,
        "rounds_p2": 2,
    }

    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
    action = results_screen(surface, clock, stats, lockout_s=0.0)
    assert action == "menu"


def test_match_type_select_and_difficulty_select(mock_surface_clock):
    """Test match_type_select and difficulty_select flows."""
    from frontend.screens import match_type_select, difficulty_select

    surface, clock = mock_surface_clock

    # First option is 'me_vs_ai'
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    m_type = match_type_select(surface, clock)
    assert m_type == "me_vs_ai"

    # Arrow down -> 'random_ai'
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN}))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    m_type2 = match_type_select(surface, clock)
    assert m_type2 == "random_ai"

    # Difficulty select default is LOW
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
    diff = difficulty_select(surface, clock)
    assert diff == "LOW"



