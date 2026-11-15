"""Tests for the match result screen (Addendum B)."""

import os
import pygame
import pytest

# Ensure headless pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from frontend.screens import results_screen


@pytest.fixture
def mock_surface_clock():
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

    # Simulate time: start at 100.0, first frame at 101.0 (locked), next frame at 104.0 (unlocked)
    times = [100.0, 101.0, 101.0, 104.0, 104.0, 104.0, 105.0]
    time_idx = 0

    def mock_time():
        nonlocal time_idx
        t = times[min(time_idx, len(times) - 1)]
        time_idx += 1
        return t

    monkeypatch.setattr(time, "time", mock_time)

    # First event posted during locked time (should be ignored)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r}))
    # Second event posted for when it unlocks
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_c}))

    action = results_screen(surface, clock, stats, lockout_s=3.0)
    # The first 'r' was discarded during lockout; the 'c' was accepted after unlock!
    assert action == "character_select"

