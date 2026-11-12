"""HUD: health bars, timer, round counter, hit feedback."""

import pygame

from frontend.colours import (
    BLACK,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    HEALTH_BAR_HEIGHT,
    HEALTH_BAR_WIDTH,
    HEALTH_BG,
    HEALTH_GREEN,
    HEALTH_RED,
    SCREEN_WIDTH,
    TIMER_COLOUR,
    WHITE,
)


def draw_hud(surface, state, font_medium, font_small, hit_flash=0):
    """Draw health bars, timer, round counter, and hit flash."""
    f1 = state.fighter1
    f2 = state.fighter2

    # --- Health bars ---
    # Player 1 health bar (left side)
    _draw_health_bar(surface, 30, 20, f1.health, f1.character_name,
                     font_small, left_aligned=True)

    # Player 2 health bar (right side)
    _draw_health_bar(surface, SCREEN_WIDTH - 30 - HEALTH_BAR_WIDTH, 20,
                     f2.health, f2.character_name, font_small,
                     left_aligned=False)

    # --- Timer ---
    from backend.engine.constants import FPS
    seconds_left = max(0, state.round_frames_left // FPS)
    timer_text = font_medium.render(str(seconds_left), True, TIMER_COLOUR)
    timer_rect = timer_text.get_rect(midtop=(SCREEN_WIDTH // 2, 15))
    pygame.draw.rect(surface, (30, 30, 50),
                     timer_rect.inflate(20, 10), border_radius=5)
    surface.blit(timer_text, timer_rect)

    # --- Round counter ---
    round_text = f"Round {state.round_number}"
    wins_text = f"P1: {state.p1_rounds_won}  -  P2: {state.p2_rounds_won}"
    rt = font_small.render(round_text, True, WHITE)
    wt = font_small.render(wins_text, True, WHITE)
    surface.blit(rt, rt.get_rect(midtop=(SCREEN_WIDTH // 2, 55)))
    surface.blit(wt, wt.get_rect(midtop=(SCREEN_WIDTH // 2, 78)))

    # --- Hit flash (white overlay when someone gets hit) ---
    if hit_flash > 0:
        flash_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        alpha = min(80, hit_flash * 20)
        flash_surface.fill((255, 255, 255, alpha))
        surface.blit(flash_surface, (0, 0))


def _draw_health_bar(surface, x, y, health, name, font, left_aligned=True):
    """Draw one health bar with the fighter's name above it."""
    # Name label
    label = font.render(name, True, WHITE)
    if left_aligned:
        surface.blit(label, (x, y - 2))
    else:
        surface.blit(label, (x + HEALTH_BAR_WIDTH - label.get_width(), y - 2))

    bar_y = y + 22

    # Background (grey)
    bg_rect = pygame.Rect(x, bar_y, HEALTH_BAR_WIDTH, HEALTH_BAR_HEIGHT)
    pygame.draw.rect(surface, HEALTH_BG, bg_rect, border_radius=3)

    # Health fill
    fill_width = int(HEALTH_BAR_WIDTH * max(0, health))
    if fill_width > 0:
        colour = HEALTH_GREEN if health > 0.3 else HEALTH_RED
        if left_aligned:
            fill_rect = pygame.Rect(x, bar_y, fill_width, HEALTH_BAR_HEIGHT)
        else:
            # Right-aligned: health drains from the left
            fill_rect = pygame.Rect(
                x + HEALTH_BAR_WIDTH - fill_width, bar_y,
                fill_width, HEALTH_BAR_HEIGHT
            )
        pygame.draw.rect(surface, colour, fill_rect, border_radius=3)

    # Border
    pygame.draw.rect(surface, WHITE, bg_rect, 2, border_radius=3)
