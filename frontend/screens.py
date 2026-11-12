"""Menu screens: intro, main menu, character select, mode select, results.

Each screen is a function that takes the pygame screen surface and returns
the player's choice (or None to go back). All rendering uses pygame shapes
and fonts — no image files.
"""

import pygame
import sys

from backend.ai.personalities import ALL_PERSONALITIES
from backend.ai.random_agent import RandomAgent
from backend.engine.characters import CHARACTER_STATS
from frontend.colours import (
    BLACK,
    DARK_GREY,
    FIGHTER_COLOURS,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    LIGHT_GREY,
    MENU_BG,
    MENU_HIGHLIGHT,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WHITE,
)


def _wait_for_key_or_click():
    """Block until the user presses a key or clicks the mouse."""
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return


def _draw_title(surface, text, font, y=50):
    """Draw a centred title at the top of the screen."""
    title = font.render(text, True, WHITE)
    surface.blit(title, title.get_rect(midtop=(SCREEN_WIDTH // 2, y)))


def _draw_menu_items(surface, items, selected, font, start_y=180):
    """Draw a vertical list of menu items, highlighting the selected one."""
    for i, item in enumerate(items):
        colour = WHITE if i == selected else LIGHT_GREY
        bg = MENU_HIGHLIGHT if i == selected else None

        text = font.render(item, True, colour)
        rect = text.get_rect(midtop=(SCREEN_WIDTH // 2, start_y + i * 50))

        if bg:
            bg_rect = rect.inflate(40, 10)
            pygame.draw.rect(surface, bg, bg_rect, border_radius=5)

        surface.blit(text, rect)


def intro_screen(surface, clock):
    """Show the game title and 'Press any key to start'."""
    font_large = pygame.font.Font(None, 64)
    font_small = pygame.font.Font(None, 28)

    surface.fill(MENU_BG)
    _draw_title(surface, "ARENA-AI", font_large, y=180)

    subtitle = font_small.render("A 2D Fighting Game with AI Fighters", True, LIGHT_GREY)
    surface.blit(subtitle, subtitle.get_rect(midtop=(SCREEN_WIDTH // 2, 260)))

    prompt = font_small.render("Press any key to start", True, WHITE)
    surface.blit(prompt, prompt.get_rect(midtop=(SCREEN_WIDTH // 2, 400)))

    pygame.display.flip()
    _wait_for_key_or_click()


def main_menu(surface, clock):
    """Show the main menu and return the chosen option.

    Returns: "start", "ai_fight", "settings", "statistics", or "quit".
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)

    items = ["Start Match", "AI Model Fight", "Settings", "Statistics", "Quit"]
    keys = ["start", "ai_fight", "settings", "statistics", "quit"]
    selected = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(items)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(items)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return keys[selected]
                elif event.key == pygame.K_ESCAPE:
                    return "quit"

        surface.fill(MENU_BG)
        _draw_title(surface, "ARENA-AI", font_large, y=60)
        _draw_menu_items(surface, items, selected, font_medium, start_y=170)

        pygame.display.flip()
        clock.tick(30)


def character_select(surface, clock):
    """Let the player pick a fighter. Returns the personality name or 'Random'."""
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    fighters = list(ALL_PERSONALITIES.keys()) + ["Random"]
    selected = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    selected = (selected - 1) % len(fighters)
                elif event.key == pygame.K_RIGHT:
                    selected = (selected + 1) % len(fighters)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return fighters[selected]
                elif event.key == pygame.K_ESCAPE:
                    return None

        surface.fill(MENU_BG)
        _draw_title(surface, "Choose Your Fighter", font_large, y=40)

        # Draw fighter cards horizontally
        card_width = 160
        total_width = len(fighters) * card_width
        start_x = (SCREEN_WIDTH - total_width) // 2

        for i, name in enumerate(fighters):
            cx = start_x + i * card_width + card_width // 2
            cy = 250

            # Card background
            card_rect = pygame.Rect(cx - 65, cy - 80, 130, 200)
            bg_colour = MENU_HIGHLIGHT if i == selected else DARK_GREY
            pygame.draw.rect(surface, bg_colour, card_rect, border_radius=8)
            pygame.draw.rect(surface, WHITE if i == selected else LIGHT_GREY,
                             card_rect, 2, border_radius=8)

            # Fighter preview (coloured circle)
            if name in FIGHTER_COLOURS:
                body_col, trim_col = FIGHTER_COLOURS[name]
                pygame.draw.circle(surface, body_col, (cx, cy - 20), 30)
                pygame.draw.circle(surface, trim_col, (cx, cy - 20), 30, 3)
            else:
                # Random: question mark
                q = font_large.render("?", True, WHITE)
                surface.blit(q, q.get_rect(center=(cx, cy - 20)))

            # Name
            label = font_medium.render(name, True, WHITE)
            surface.blit(label, label.get_rect(midtop=(cx, cy + 30)))

            # Description (only for the selected fighter)
            if i == selected and name in ALL_PERSONALITIES:
                p = ALL_PERSONALITIES[name]
                desc = font_small.render(p.description, True, LIGHT_GREY)
                surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 420)))
                full = font_small.render(p.full_name, True, WHITE)
                surface.blit(full, full.get_rect(midtop=(SCREEN_WIDTH // 2, 390)))
            elif i == selected and name == "Random":
                desc = font_small.render("A random AI opponent", True, LIGHT_GREY)
                surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 420)))

        # Instructions
        inst = font_small.render("← → to browse, Enter to select, Esc to go back",
                                 True, LIGHT_GREY)
        surface.blit(inst, inst.get_rect(midtop=(SCREEN_WIDTH // 2, 540)))

        pygame.display.flip()
        clock.tick(30)


def mode_select(surface, clock):
    """Pick match type and difficulty.

    Returns (match_type, difficulty) or (None, None) to go back.
    match_type: "human_vs_selected", "human_vs_random", "ai_vs_ai"
    difficulty: "LOW", "MEDIUM", "HIGH", "HELL"
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    # Step 1: pick match type
    types = ["Human vs AI", "Human vs Random AI", "AI vs AI"]
    type_keys = ["human_vs_selected", "human_vs_random", "ai_vs_ai"]
    selected = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None, None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(types)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(types)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    match_type = type_keys[selected]
                    break
                elif event.key == pygame.K_ESCAPE:
                    return None, None
        else:
            surface.fill(MENU_BG)
            _draw_title(surface, "Match Type", font_large, y=60)
            _draw_menu_items(surface, types, selected, font_medium, start_y=180)
            pygame.display.flip()
            clock.tick(30)
            continue
        break

    # Step 2: pick difficulty
    difficulties = ["LOW", "MEDIUM", "HIGH", "HELL"]
    selected = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None, None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(difficulties)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(difficulties)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return match_type, difficulties[selected]
                elif event.key == pygame.K_ESCAPE:
                    return None, None

        surface.fill(MENU_BG)
        _draw_title(surface, "Difficulty", font_large, y=60)
        _draw_menu_items(surface, difficulties, selected, font_medium, start_y=180)

        # Difficulty description
        descs = {
            "LOW": "Slow reactions, many mistakes",
            "MEDIUM": "Moderate reactions, some mistakes",
            "HIGH": "Fast reactions, few mistakes",
            "HELL": "Near-instant reactions, almost no mistakes",
        }
        desc = font_small.render(descs[difficulties[selected]], True, LIGHT_GREY)
        surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 420)))

        pygame.display.flip()
        clock.tick(30)


def pause_screen(surface, clock):
    """Show pause overlay. Returns 'resume' or 'quit'."""
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)

    items = ["Resume", "Quit to Menu"]
    keys = ["resume", "quit"]
    selected = 0

    # Semi-transparent overlay
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))
    surface.blit(overlay, (0, 0))

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "resume"
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(items)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(items)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return keys[selected]

        # Re-draw overlay on the frozen game frame
        temp = surface.copy()
        temp.blit(overlay, (0, 0))
        _draw_title(temp, "PAUSED", font_large, y=150)
        _draw_menu_items(temp, items, selected, font_medium, start_y=280)

        # Copy to actual display
        pygame.display.get_surface().blit(temp, (0, 0))
        pygame.display.flip()
        clock.tick(30)


def results_screen(surface, clock, match_result, p1_name, p2_name):
    """Show the match result and wait for the player to continue."""
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    if match_result == "p1":
        result_text = f"{p1_name} WINS!"
        colour = FIGHTER_COLOURS.get(p1_name, (WHITE, WHITE))[0]
    elif match_result == "p2":
        result_text = f"{p2_name} WINS!"
        colour = FIGHTER_COLOURS.get(p2_name, (WHITE, WHITE))[0]
    else:
        result_text = "DRAW!"
        colour = LIGHT_GREY

    surface.fill(MENU_BG)
    title = font_large.render(result_text, True, colour)
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 200)))

    prompt = font_small.render("Press any key to continue", True, WHITE)
    surface.blit(prompt, prompt.get_rect(midtop=(SCREEN_WIDTH // 2, 400)))

    pygame.display.flip()
    _wait_for_key_or_click()


def settings_screen(surface, clock, settings):
    """Simple settings screen. Returns updated settings dict.

    settings: {"log_fights": bool}
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return settings
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return settings
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    settings["log_fights"] = not settings["log_fights"]

        surface.fill(MENU_BG)
        _draw_title(surface, "Settings", font_large, y=60)

        status = "ON" if settings["log_fights"] else "OFF"
        label = font_medium.render(f"Log Human Fights: {status}", True, WHITE)
        surface.blit(label, label.get_rect(midtop=(SCREEN_WIDTH // 2, 200)))

        hint = font_small.render("Enter to toggle, Esc to go back", True, LIGHT_GREY)
        surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, 300)))

        pygame.display.flip()
        clock.tick(30)


def statistics_screen(surface, clock):
    """Placeholder statistics screen."""
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    surface.fill(MENU_BG)
    _draw_title(surface, "Statistics", font_large, y=60)

    msg = font_small.render("Statistics will be available after M9.", True, LIGHT_GREY)
    surface.blit(msg, msg.get_rect(midtop=(SCREEN_WIDTH // 2, 250)))

    prompt = font_small.render("Press any key to go back", True, WHITE)
    surface.blit(prompt, prompt.get_rect(midtop=(SCREEN_WIDTH // 2, 400)))

    pygame.display.flip()
    _wait_for_key_or_click()
