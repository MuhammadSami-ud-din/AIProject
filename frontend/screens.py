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


def _draw_menu_items_clickable(surface, items, selected, font, start_y=180):
    """Draw menu items and return a list of clickable rects (one per item).

    Same look as _draw_menu_items, but returns rects so the caller
    can check mouse clicks against them.
    """
    rects = []
    for i, item in enumerate(items):
        colour = WHITE if i == selected else LIGHT_GREY
        bg = MENU_HIGHLIGHT if i == selected else None

        text = font.render(item, True, colour)
        rect = text.get_rect(midtop=(SCREEN_WIDTH // 2, start_y + i * 50))

        # The clickable area is the inflated background rect
        click_rect = rect.inflate(40, 10)

        if bg:
            pygame.draw.rect(surface, bg, click_rect, border_radius=5)

        surface.blit(text, rect)
        rects.append(click_rect)

    return rects


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

    Returns: "start", "ai_fight", "settings", "statistics", "manual", or "quit".
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)

    items = ["Start Match", "AI Model Fight", "Settings", "Statistics", "Manual", "Quit"]
    keys = ["start", "ai_fight", "settings", "statistics", "manual", "quit"]
    selected = 0

    while True:
        # Build clickable rects for mouse support
        item_rects = []

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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Check if a menu item was clicked
                for i, rect in enumerate(item_rects):
                    if rect.collidepoint(event.pos):
                        return keys[i]
            if event.type == pygame.MOUSEMOTION:
                # Highlight the item under the mouse
                for i, rect in enumerate(item_rects):
                    if rect.collidepoint(event.pos):
                        selected = i

        surface.fill(MENU_BG)
        _draw_title(surface, "ARENA-AI", font_large, y=60)

        # Draw menu items and collect their rects
        item_rects = _draw_menu_items_clickable(
            surface, items, selected, font_medium, start_y=150
        )

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
    """Settings screen with multiple options and mouse + keyboard support.

    settings: {"log_fights": bool, "speed": float, "show_ai": bool}
    Returns updated settings dict.

    Game Speed has exactly 4 options: 0.5x, 1x (default), 2x, 3x.
    Use ←/→ to cycle through them, or click the arrows on screen.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    # Ensure all settings exist with defaults
    settings.setdefault("log_fights", False)
    settings.setdefault("speed", 1.0)
    settings.setdefault("show_ai", True)

    # The four exact speed options
    SPEED_OPTIONS = [0.5, 1.0, 2.0, 3.0]
    SPEED_LABELS = ["0.5x", "1x", "2x", "3x"]

    # Find the current speed index (default to 1x if not in list)
    if settings["speed"] in SPEED_OPTIONS:
        speed_index = SPEED_OPTIONS.index(settings["speed"])
    else:
        speed_index = 1  # default to 1x
        settings["speed"] = 1.0

    items = ["log_fights", "speed", "show_ai"]
    labels = {
        "log_fights": "Log Human Fights",
        "speed": "Game Speed",
        "show_ai": "Show AI Thinking",
    }
    selected = 0

    while True:
        # Build clickable rects for each row
        row_rects = []

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return settings
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return settings
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(items)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(items)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    key = items[selected]
                    if key == "log_fights":
                        settings["log_fights"] = not settings["log_fights"]
                    elif key == "show_ai":
                        settings["show_ai"] = not settings["show_ai"]
                    elif key == "speed":
                        # Enter/Space on speed cycles forward
                        speed_index = (speed_index + 1) % len(SPEED_OPTIONS)
                        settings["speed"] = SPEED_OPTIONS[speed_index]
                elif event.key == pygame.K_LEFT:
                    key = items[selected]
                    if key == "speed":
                        speed_index = (speed_index - 1) % len(SPEED_OPTIONS)
                        settings["speed"] = SPEED_OPTIONS[speed_index]
                elif event.key == pygame.K_RIGHT:
                    key = items[selected]
                    if key == "speed":
                        speed_index = (speed_index + 1) % len(SPEED_OPTIONS)
                        settings["speed"] = SPEED_OPTIONS[speed_index]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Check if any row was clicked
                for i, rect in enumerate(row_rects):
                    if rect.collidepoint(event.pos):
                        selected = i
                        key = items[i]
                        if key == "log_fights":
                            settings["log_fights"] = not settings["log_fights"]
                        elif key == "show_ai":
                            settings["show_ai"] = not settings["show_ai"]
                        elif key == "speed":
                            speed_index = (speed_index + 1) % len(SPEED_OPTIONS)
                            settings["speed"] = SPEED_OPTIONS[speed_index]
            if event.type == pygame.MOUSEMOTION:
                for i, rect in enumerate(row_rects):
                    if rect.collidepoint(event.pos):
                        selected = i

        surface.fill(MENU_BG)
        _draw_title(surface, "Settings", font_large, y=60)

        row_rects = []
        for i, key in enumerate(items):
            # Build the value display
            if key == "log_fights":
                val = "ON" if settings["log_fights"] else "OFF"
            elif key == "speed":
                val = f"◀  {SPEED_LABELS[speed_index]}  ▶"
            elif key == "show_ai":
                val = "ON" if settings["show_ai"] else "OFF"
            else:
                val = str(settings.get(key, "?"))

            text = f"{labels[key]}:  {val}"
            colour = WHITE if i == selected else LIGHT_GREY
            bg = MENU_HIGHLIGHT if i == selected else None

            rendered = font_medium.render(text, True, colour)
            rect = rendered.get_rect(midtop=(SCREEN_WIDTH // 2, 180 + i * 60))
            click_rect = rect.inflate(60, 14)

            if bg:
                pygame.draw.rect(surface, bg, click_rect, border_radius=5)

            surface.blit(rendered, rect)
            row_rects.append(click_rect)

        hint = font_small.render(
            "↑/↓ navigate  |  Enter/click to toggle  |  ←/→ change speed  |  Esc back",
            True, LIGHT_GREY
        )
        surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, 420)))

        # Show a note about the current speed effect
        speed_desc = {
            0.5: "Half speed — everything moves slower",
            1.0: "Normal speed (default)",
            2.0: "Double speed — faster gameplay",
            3.0: "Triple speed — very fast gameplay",
        }
        desc = font_small.render(
            speed_desc.get(settings["speed"], ""), True, LIGHT_GREY
        )
        surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 460)))

        pygame.display.flip()
        clock.tick(30)


def statistics_screen(surface, clock):
    """Show fighter statistics: Elo ratings and win rates.

    Runs a quick round-robin tournament in the background and
    displays the results. Press Esc to go back.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    # Show "calculating..." while running the tournament
    surface.fill(MENU_BG)
    _draw_title(surface, "Statistics", font_large, y=60)
    loading = font_small.render("Running tournament... please wait", True, LIGHT_GREY)
    surface.blit(loading, loading.get_rect(midtop=(SCREEN_WIDTH // 2, 250)))
    pygame.display.flip()

    # Run a quick round-robin (5 matches per pair)
    from backend.data.statistics import (
        run_round_robin, compute_elo, win_rate_with_ci, FIGHTER_NAMES
    )
    results = run_round_robin(matches_per_pair=5)
    elo = compute_elo(results)

    # Sort fighters by Elo
    sorted_fighters = sorted(elo.keys(), key=lambda f: elo[f], reverse=True)

    # Build the display
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return

        surface.fill(MENU_BG)
        _draw_title(surface, "Statistics & Leaderboard", font_large, y=30)

        # Elo leaderboard
        elo_label = font_medium.render("Elo Ratings", True, WHITE)
        surface.blit(elo_label, elo_label.get_rect(midtop=(SCREEN_WIDTH // 4, 90)))

        for i, name in enumerate(sorted_fighters):
            rating = elo[name]
            rank_text = f"#{i+1}  {name}: {rating:.0f}"
            colour = FIGHTER_COLOURS.get(name, (WHITE, WHITE))[0]
            label = font_small.render(rank_text, True, colour)
            surface.blit(label, (SCREEN_WIDTH // 4 - 80, 130 + i * 35))

        # Win rate table
        wr_label = font_medium.render("Win Rates", True, WHITE)
        surface.blit(wr_label, wr_label.get_rect(midtop=(3 * SCREEN_WIDTH // 4, 90)))

        # Table header
        header_x = SCREEN_WIDTH // 2 + 30
        for j, name in enumerate(FIGHTER_NAMES):
            h = font_small.render(name[:3], True, LIGHT_GREY)
            surface.blit(h, (header_x + 70 + j * 60, 130))

        # Table rows
        for i, name1 in enumerate(FIGHTER_NAMES):
            row_label = font_small.render(name1[:3], True, WHITE)
            surface.blit(row_label, (header_x, 160 + i * 30))

            for j, name2 in enumerate(FIGHTER_NAMES):
                if name1 == name2:
                    cell = "-"
                else:
                    # Find the result between these two
                    rate = _find_win_rate(results, name1, name2)
                    cell = f"{rate:.0%}"
                c = font_small.render(cell, True, LIGHT_GREY)
                surface.blit(c, (header_x + 70 + j * 60, 160 + i * 30))

        # Instructions
        hint = font_small.render("Press Esc to go back", True, LIGHT_GREY)
        surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, 550)))

        pygame.display.flip()
        clock.tick(30)


def _find_win_rate(results, name1, name2):
    """Find win rate of name1 against name2 from round-robin results."""
    for r in results:
        if r["fighter1"] == name1 and r["fighter2"] == name2:
            total = r["wins1"] + r["wins2"] + r["draws"]
            return r["wins1"] / total if total > 0 else 0.5
        elif r["fighter1"] == name2 and r["fighter2"] == name1:
            total = r["wins1"] + r["wins2"] + r["draws"]
            return r["wins2"] / total if total > 0 else 0.5
    return 0.5


# ------------------------------------------------------------------
# Manual / How to Play
# ------------------------------------------------------------------
def manual_screen(surface, clock):
    """Show the game manual: rules, controls, and mechanics.

    Has two pages — use ←/→ or click to switch. Press Esc or click
    'Back' to return to the main menu.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)

    page = 0   # 0 = rules, 1 = controls
    pages = ["How to Play", "Controls"]

    while True:
        # Back button rect (drawn every frame, checked on click)
        back_rect = pygame.Rect(20, SCREEN_HEIGHT - 50, 100, 36)
        # Page tab rects
        tab_rects = []

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                elif event.key == pygame.K_LEFT:
                    page = max(0, page - 1)
                elif event.key == pygame.K_RIGHT:
                    page = min(len(pages) - 1, page + 1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # Toggle page
                    page = (page + 1) % len(pages)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_rect.collidepoint(event.pos):
                    return
                for i, rect in enumerate(tab_rects):
                    if rect.collidepoint(event.pos):
                        page = i

        surface.fill(MENU_BG)
        _draw_title(surface, "Manual", font_large, y=20)

        # --- Page tabs ---
        tab_rects = []
        for i, tab_name in enumerate(pages):
            tx = SCREEN_WIDTH // 2 - 120 + i * 240
            ty = 70
            tab_rect = pygame.Rect(tx - 80, ty - 5, 160, 32)
            tab_rects.append(tab_rect)
            bg_col = MENU_HIGHLIGHT if i == page else DARK_GREY
            pygame.draw.rect(surface, bg_col, tab_rect, border_radius=5)
            col = WHITE if i == page else LIGHT_GREY
            label = font_medium.render(tab_name, True, col)
            surface.blit(label, label.get_rect(center=tab_rect.center))

        # --- Page content ---
        if page == 0:
            _draw_rules_page(surface, font_medium, font_small)
        else:
            _draw_controls_page(surface, font_medium, font_small)

        # --- Back button ---
        pygame.draw.rect(surface, DARK_GREY, back_rect, border_radius=5)
        pygame.draw.rect(surface, LIGHT_GREY, back_rect, 2, border_radius=5)
        back_label = font_medium.render("← Back", True, WHITE)
        surface.blit(back_label, back_label.get_rect(center=back_rect.center))

        # Navigation hint
        hint = font_small.render(
            "←/→ switch page  |  Esc or click Back to return",
            True, LIGHT_GREY
        )
        surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28)))

        pygame.display.flip()
        clock.tick(30)


def _draw_rules_page(surface, font_medium, font_small):
    """Draw the 'How to Play' rules page."""
    x = 60
    y = 115
    spacing = 24

    rules = [
        ("Game Rules", True),
        ("", False),
        ("• Arena is 800 pixels wide. Two fighters face each other.", False),
        ("• Each match is best of 3 rounds. First to win 2 rounds wins.", False),
        ("• Each round lasts up to 60 seconds.", False),
        ("• A round ends by KO (health reaches 0) or when time runs out.", False),
        ("• At time-out the fighter with more health wins the round.", False),
        ("• Equal health at time-out = drawn round (no point awarded).", False),
        ("• If nobody has 2 wins after 3 rounds: most round wins takes it.", False),
        ("", False),
        ("Battle Mechanics", True),
        ("", False),
        ("• Light Attack: fast, low damage (5%), short reach.", False),
        ("• Heavy Attack: slow, high damage (12%), longer reach.", False),
        ("• Blocking: reduces incoming damage to 10%. Cannot block in air.", False),
        ("• Attacks have startup → active → recovery frames.", False),
        ("• During recovery you are 'stuck' and can be punished!", False),
        ("• Cooldowns prevent attack spam: wait before attacking again.", False),
        ("", False),
        ("Fighter Traits", True),
        ("", False),
        ("• Crimson: +20% damage, slightly shorter reach.", False),
        ("• Steel: takes 50% less damage when blocking.", False),
        ("• Shadow: +30% speed, +15% reach, slightly less damage.", False),
        ("• Golden: balanced across all stats.", False),
    ]

    for line_text, is_header in rules:
        if is_header:
            font = font_medium
            colour = WHITE
        else:
            font = font_small
            colour = LIGHT_GREY
        if line_text:
            rendered = font.render(line_text, True, colour)
            surface.blit(rendered, (x, y))
        y += spacing


def _draw_controls_page(surface, font_medium, font_small):
    """Draw the 'Controls' page with all keyboard mappings."""
    x = 60
    y = 115
    spacing = 26

    controls = [
        ("Fight Controls", True),
        ("", False),
        ("  A                Move left", False),
        ("  D                Move right", False),
        ("  W                Jump", False),
        ("  J                 Light attack (fast, low damage)", False),
        ("  K                Heavy attack (slow, high damage)", False),
        ("  L                 Block (reduces damage, no air block)", False),
        ("  Esc              Pause the match", False),
        ("", False),
        ("Menu Navigation", True),
        ("", False),
        ("  ↑ / ↓            Move between menu items", False),
        ("  ← / →            Browse fighters / change settings", False),
        ("  Enter / Space   Select / confirm", False),
        ("  Esc              Go back / quit", False),
        ("  Mouse click      Select any menu item directly", False),
        ("", False),
        ("AI Model Fight Viewer", True),
        ("", False),
        ("  ← / →            Slow down / speed up (0.25x – 4x)", False),
        ("  Space             Pause / unpause", False),
        ("  F3                Toggle profiling overlay", False),
        ("  Esc              Pause menu", False),
    ]

    for line_text, is_header in controls:
        if is_header:
            font = font_medium
            colour = WHITE
        else:
            font = font_small
            colour = LIGHT_GREY
        if line_text:
            rendered = font.render(line_text, True, colour)
            surface.blit(rendered, (x, y))
        y += spacing
