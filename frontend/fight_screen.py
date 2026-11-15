"""The fight screen: runs one full match with rendering.

Handles both human-vs-AI and AI-vs-AI matches.
"""

import pygame

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.engine.constants import ARENA_WIDTH, FPS
from backend.engine.step import make_initial_state, new_round, step
from frontend.colours import (
    BLACK,
    DARK_GREY,
    MENU_BG,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WHITE,
)
from frontend.draw_fighter import draw_fighter
from frontend.hud import draw_hud
from frontend.input_handler import get_human_action
from frontend.screens import pause_screen


# How far from the left edge of the screen the arena starts
ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2
GROUND_Y = 450


def run_fight(surface, clock, agent1, agent2, human_player=None,
              speed_mult=1.0):
    """Run a full match on screen.

    agent1, agent2: the two fighters (Agent objects).
    human_player: 1 or 2 if a human is playing, None for AI vs AI.
    speed_mult: game speed multiplier from Settings (0.5, 1.0, 2.0, 3.0).

    Returns the match result: "p1", "p2", or "draw".
    """
    # Figure out character names from the agents
    char1 = agent1.personality.name if agent1.personality else "Golden"
    char2 = agent2.personality.name if agent2.personality else "Golden"

    state = make_initial_state(char1, char2)
    agent1.reset()
    agent2.reset()

    font_medium = pygame.font.Font(None, 32)
    font_small = pygame.font.Font(None, 22)
    font_large = pygame.font.Font(None, 56)

    hit_flash = 0          # frames of white flash when someone gets hit
    prev_health1 = 1.0     # to detect hits
    prev_health2 = 1.0

    while not state.match_over:
        # --- Handle events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    result = pause_screen(surface, clock)
                    if result == "quit":
                        return "quit"

        # --- Get actions ---
        if human_player == 1:
            action1 = get_human_action(state.fighter2.x, state.fighter1.x)
            obs2 = observation_for(state, 2)
            action2, _ = agent2.decide(obs2)
        elif human_player == 2:
            obs1 = observation_for(state, 1)
            action1, _ = agent1.decide(obs1)
            action2 = get_human_action(state.fighter1.x, state.fighter2.x)
        else:
            obs1 = observation_for(state, 1)
            obs2 = observation_for(state, 2)
            action1, _ = agent1.decide(obs1)
            action2, _ = agent2.decide(obs2)

        # --- Step engine ---
        state = step(state, action1, action2)

        # --- Detect hits for flash effect ---
        if state.fighter1.health < prev_health1 or state.fighter2.health < prev_health2:
            hit_flash = 4
        prev_health1 = state.fighter1.health
        prev_health2 = state.fighter2.health
        hit_flash = max(0, hit_flash - 1)

        # --- Let agents observe ---
        if human_player != 1:
            obs1 = observation_for(state, 1)
            agent1.observe(obs1, action1, action2)
        if human_player != 2:
            obs2 = observation_for(state, 2)
            agent2.observe(obs2, action2, action1)

        # --- Draw ---
        _draw_frame(surface, state, font_medium, font_small, hit_flash)
        pygame.display.flip()
        clock.tick(int(FPS * speed_mult))

        # --- Round transition ---
        if state.round_over and not state.match_over:
            _show_round_result(surface, state, font_large, clock)
            state = new_round(state)
            agent1.reset()
            agent2.reset()
            prev_health1 = 1.0
            prev_health2 = 1.0

    return state.match_result


def _draw_frame(surface, state, font_medium, font_small, hit_flash):
    """Draw one frame of the fight: background, fighters, HUD."""
    # Background
    surface.fill(MENU_BG)

    # Arena floor
    floor_rect = pygame.Rect(ARENA_OFFSET_X, GROUND_Y, ARENA_WIDTH, 4)
    pygame.draw.rect(surface, DARK_GREY, floor_rect)

    # Arena walls (thin lines)
    pygame.draw.line(surface, DARK_GREY,
                     (ARENA_OFFSET_X, GROUND_Y - 200),
                     (ARENA_OFFSET_X, GROUND_Y + 4), 2)
    pygame.draw.line(surface, DARK_GREY,
                     (ARENA_OFFSET_X + ARENA_WIDTH, GROUND_Y - 200),
                     (ARENA_OFFSET_X + ARENA_WIDTH, GROUND_Y + 4), 2)

    # Fighters
    f1 = state.fighter1
    f2 = state.fighter2
    facing1 = f1.x < f2.x  # fighter 1 faces right if fighter 2 is to the right
    facing2 = f2.x < f1.x

    draw_fighter(surface, f1, facing1, ARENA_OFFSET_X, GROUND_Y)
    draw_fighter(surface, f2, facing2, ARENA_OFFSET_X, GROUND_Y)

    # HUD
    draw_hud(surface, state, font_medium, font_small, hit_flash)


def _show_round_result(surface, state, font_large, clock):
    """Brief pause to show who won the round."""
    if state.round_result == "p1":
        text = f"{state.fighter1.character_name} wins the round!"
    elif state.round_result == "p2":
        text = f"{state.fighter2.character_name} wins the round!"
    else:
        text = "Round draw!"

    label = font_large.render(text, True, WHITE)
    rect = label.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))

    # Show for about 2 seconds
    for _ in range(120):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        surface.fill(MENU_BG)
        surface.blit(label, rect)
        pygame.display.flip()
        clock.tick(FPS)
