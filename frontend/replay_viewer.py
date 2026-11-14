"""Replay viewer: replay a logged match from the database.

Loads a match's frames from the database and replays them
on screen, frame by frame. Useful for studying what happened.
"""

import pygame

from backend.ai.actions import Action
from backend.ai.observation import FEATURE_NAMES
from backend.data.database import get_connection, get_match_frames
from backend.engine.constants import ARENA_WIDTH, FPS
from frontend.colours import (
    DARK_GREY,
    LIGHT_GREY,
    MENU_BG,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TIMER_COLOUR,
    WHITE,
)


# Layout
ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2
GROUND_Y = 400


def run_replay(surface, clock, match_id, db_path=None):
    """Replay a logged match on screen.

    match_id: which match to replay (from the database).
    db_path: path to the database file. None uses default.

    Returns when the replay is done or the user presses Esc.
    """
    # Load frames from the database
    if db_path is None:
        import os
        db_path = os.path.join(os.path.dirname(__file__), "..", "backend",
                               "data", "fights.db")

    conn = get_connection(db_path)
    frames = get_match_frames(conn, match_id)
    conn.close()

    if not frames:
        _show_message(surface, clock, "No frames found for this match.")
        return

    font_medium = pygame.font.Font(None, 32)
    font_small = pygame.font.Font(None, 22)
    font_tiny = pygame.font.Font(None, 18)

    # Replay settings
    speed = 1.0         # 1.0 = normal speed
    frame_idx = 0
    paused = False
    total_frames = len(frames)

    while frame_idx < total_frames:
        # --- Handle events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_LEFT:
                    # Slow down or step back
                    if paused:
                        frame_idx = max(0, frame_idx - 1)
                    else:
                        speed = max(0.25, speed * 0.5)
                elif event.key == pygame.K_RIGHT:
                    # Speed up or step forward
                    if paused:
                        frame_idx = min(total_frames - 1, frame_idx + 1)
                    else:
                        speed = min(4.0, speed * 2.0)

        if paused:
            _draw_replay_frame(surface, frames[frame_idx], frame_idx,
                               total_frames, speed, paused,
                               font_medium, font_small, font_tiny)
            pygame.display.flip()
            clock.tick(30)
            continue

        # Draw the current frame
        _draw_replay_frame(surface, frames[frame_idx], frame_idx,
                           total_frames, speed, paused,
                           font_medium, font_small, font_tiny)
        pygame.display.flip()
        clock.tick(int(FPS * speed))

        frame_idx += 1

    # Show "Replay Complete"
    _show_message(surface, clock, "Replay Complete — Press any key")


def _draw_replay_frame(surface, frame_data, idx, total, speed, paused,
                       font_medium, font_small, font_tiny):
    """Draw one frame of the replay."""
    surface.fill(MENU_BG)

    # Arena floor and walls
    floor_rect = pygame.Rect(ARENA_OFFSET_X, GROUND_Y, ARENA_WIDTH, 4)
    pygame.draw.rect(surface, DARK_GREY, floor_rect)
    pygame.draw.line(surface, DARK_GREY,
                     (ARENA_OFFSET_X, GROUND_Y - 200),
                     (ARENA_OFFSET_X, GROUND_Y + 4), 2)
    pygame.draw.line(surface, DARK_GREY,
                     (ARENA_OFFSET_X + ARENA_WIDTH, GROUND_Y - 200),
                     (ARENA_OFFSET_X + ARENA_WIDTH, GROUND_Y + 4), 2)

    # Fighter positions from features
    distance_ratio = frame_data.get("distance", 0.5)
    my_health = frame_data.get("my_health", 1.0)
    enemy_health = frame_data.get("enemy_health", 1.0)

    # Approximate fighter positions
    distance_px = distance_ratio * ARENA_WIDTH
    f1_x = ARENA_WIDTH / 2 - distance_px / 2
    f2_x = ARENA_WIDTH / 2 + distance_px / 2

    # Draw simple rectangles for fighters
    f1_screen_x = ARENA_OFFSET_X + max(0, min(ARENA_WIDTH, f1_x))
    f2_screen_x = ARENA_OFFSET_X + max(0, min(ARENA_WIDTH, f2_x))

    # Fighter 1 (blue)
    pygame.draw.rect(surface, (60, 100, 200),
                     (f1_screen_x - 15, GROUND_Y - 60, 30, 60))
    pygame.draw.circle(surface, (60, 100, 200),
                       (int(f1_screen_x), GROUND_Y - 72), 12)

    # Fighter 2 (red)
    pygame.draw.rect(surface, (200, 60, 60),
                     (f2_screen_x - 15, GROUND_Y - 60, 30, 60))
    pygame.draw.circle(surface, (200, 60, 60),
                       (int(f2_screen_x), GROUND_Y - 72), 12)

    # Health bars
    _draw_simple_health_bar(surface, 30, 20, my_health, "P1", font_small)
    _draw_simple_health_bar(surface, SCREEN_WIDTH - 330, 20, enemy_health,
                            "P2", font_small)

    # Frame counter and speed
    info = f"Frame {idx + 1}/{total}  Speed: {speed:.1f}x"
    if paused:
        info += "  [PAUSED]"
    info_text = font_small.render(info, True, TIMER_COLOUR)
    surface.blit(info_text, info_text.get_rect(midtop=(SCREEN_WIDTH // 2, 15)))

    # Actions
    action1 = frame_data.get("action1", "?")
    action2 = frame_data.get("action2", "?")
    act_text = font_tiny.render(f"P1: {action1}   P2: {action2}", True, LIGHT_GREY)
    surface.blit(act_text, act_text.get_rect(midtop=(SCREEN_WIDTH // 2, 45)))

    # Round info
    round_num = frame_data.get("round", 1)
    round_text = font_tiny.render(f"Round {round_num}", True, WHITE)
    surface.blit(round_text, round_text.get_rect(midtop=(SCREEN_WIDTH // 2, 65)))

    # Controls hint
    hint = font_tiny.render(
        "Space: pause | ←/→: speed/step | Esc: exit", True, LIGHT_GREY
    )
    surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30)))


def _draw_simple_health_bar(surface, x, y, health, label, font):
    """Draw a simple health bar for the replay."""
    bar_width = 300
    bar_height = 20

    # Label
    text = font.render(f"{label}: {health:.0%}", True, WHITE)
    surface.blit(text, (x, y))

    # Background
    bg = pygame.Rect(x, y + 24, bar_width, bar_height)
    pygame.draw.rect(surface, (60, 60, 60), bg, border_radius=3)

    # Fill
    fill_width = int(bar_width * max(0, health))
    if fill_width > 0:
        colour = (30, 200, 60) if health > 0.3 else (200, 30, 30)
        fill = pygame.Rect(x, y + 24, fill_width, bar_height)
        pygame.draw.rect(surface, colour, fill, border_radius=3)

    pygame.draw.rect(surface, WHITE, bg, 2, border_radius=3)


def _show_message(surface, clock, text):
    """Show a message and wait for any key."""
    font = pygame.font.Font(None, 32)
    surface.fill(MENU_BG)
    rendered = font.render(text, True, WHITE)
    surface.blit(rendered, rendered.get_rect(center=(SCREEN_WIDTH // 2,
                                                      SCREEN_HEIGHT // 2)))
    pygame.display.flip()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return
        clock.tick(30)
