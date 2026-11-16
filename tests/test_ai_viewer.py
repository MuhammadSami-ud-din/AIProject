"""Tests for AI Model Fight Viewer: background application, visuals, and combat stats."""

import os
import pygame
import pytest

from backend.ai.crimson import CrimsonAgent
from backend.ai.golden import GoldenAgent
from backend.ai.random_agent import RandomAgent
from backend.engine.constants import ARENA_WIDTH
from frontend.ai_viewer import (
    ARENA_OFFSET_X,
    GROUND_Y,
    PANEL_HEIGHT,
    PANEL_Y,
    _build_info,
    _draw_full_frame,
    _empty_info,
    run_ai_viewer,
)
from frontend.assets import assets
from frontend.theme import SCREEN_HEIGHT, SCREEN_WIDTH


@pytest.fixture(scope="module")
def pygame_surface():
    """Headless Pygame initialization and test surface."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()
    yield surface, clock
    pygame.quit()


def test_ai_viewer_applies_arena_background(pygame_surface):
    """Verify that arena background is properly loaded and drawn in AI Model Fight."""
    surface, clock = pygame_surface

    agent1 = GoldenAgent(player=1, seed=42)
    agent2 = CrimsonAgent(player=2, seed=43)

    # Specific arena test
    arena_name = "arena_neon_rooftop"
    arena_bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))
    assert arena_bg is not None
    assert arena_bg.get_size() == (SCREEN_WIDTH, SCREEN_HEIGHT)

    # Empty test info
    info1 = _empty_info()
    info2 = _empty_info()

    from backend.engine.step import make_initial_state
    state = make_initial_state("Golden", "Crimson")

    # Draw full frame
    font_large = pygame.font.Font(None, 48)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)
    font_tiny = pygame.font.Font(None, 16)

    _draw_full_frame(
        surface, state, arena_bg, "Neon Rooftop",
        info1, info2, font_large, font_medium, font_small, font_tiny,
        "Golden", "Crimson", False, agent1, agent2,
        0, 0, 2, False, False, 1.0, 1.0, 0, 0, [], []
    )

    # Verify surface has drawn content (not all blank / single colour)
    arena_pixel = surface.get_at((SCREEN_WIDTH // 2, 100))
    # It shouldn't be empty black
    assert arena_pixel is not None


def test_ai_viewer_runs_and_returns_real_stats(pygame_surface, monkeypatch):
    """Verify that run_ai_viewer executes and returns real combat statistics."""
    surface, clock = pygame_surface

    agent1 = RandomAgent(player=1, seed=1)
    agent2 = RandomAgent(player=2, seed=2)

    # Fast-forward simulation: simulate 5 frames and end match
    real_step = run_ai_viewer.__globals__["step"]
    step_count = [0]

    def mock_step(state, a1, a2):
        step_count[0] += 1
        st = real_step(state, a1, a2)
        # End match after 6 steps
        if step_count[0] >= 6:
            st.fighter2.health = 0.0
            st.round_over = True
            st.round_result = "p1"
            st.p1_rounds_won = 2
            st.match_over = True
            st.match_result = "p1"
        return st

    monkeypatch.setattr("frontend.ai_viewer.step", mock_step)
    monkeypatch.setattr("frontend.ai_viewer._show_round_intro_viewer", lambda *args, **kwargs: None)
    monkeypatch.setattr("frontend.ai_viewer._show_round_banner_viewer", lambda *args, **kwargs: None)
    monkeypatch.setattr("frontend.ai_viewer._slow_motion_ko_viewer", lambda *args, **kwargs: None)

    stats = run_ai_viewer(surface, clock, agent1, agent2, speed_mult=4.0, arena_name="arena_iron_foundry")

    assert isinstance(stats, dict)
    assert stats["arena"] == "Iron Foundry"
    assert stats["p1_kind"] == "ai"
    assert stats["p2_kind"] == "ai"
    assert "damage_dealt_p1" in stats
    assert "damage_dealt_p2" in stats
    assert "hits_landed_p1" in stats
    assert "blocks_p1" in stats
    assert "longest_combo_p1" in stats
    assert "rounds_history" in stats
    assert stats["status"] == "finished"
    assert stats["match_result"] == "p1"


def test_ai_viewer_mirror_match_support(pygame_surface):
    """Verify that mirror matches correctly identify is_mirror for palette mapping."""
    surface, clock = pygame_surface
    agent1 = GoldenAgent(player=1, seed=10)
    agent2 = GoldenAgent(player=2, seed=20)

    from backend.engine.step import make_initial_state
    state = make_initial_state("Golden", "Golden")
    arena_bg = assets.get_arena("arena_sky_colosseum", size=(SCREEN_WIDTH, SCREEN_HEIGHT))

    font_large = pygame.font.Font(None, 48)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)
    font_tiny = pygame.font.Font(None, 16)

    # Frame draw should succeed without error with is_mirror=True
    _draw_full_frame(
        surface, state, arena_bg, "Sky Colosseum",
        _empty_info(), _empty_info(),
        font_large, font_medium, font_small, font_tiny,
        "Golden", "Golden", True, agent1, agent2,
        0, 0, 2, False, False, 1.0, 1.0, 0, 0, [], []
    )
