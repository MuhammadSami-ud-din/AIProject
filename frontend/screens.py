"""Menu screens: intro, main menu, character select, mode select, results.

Each screen is a function that takes the pygame screen surface and returns
the player's choice (or None to go back). All rendering uses pygame shapes
and fonts — no image files.
"""

import math
import sys
import time
import pygame

from backend.ai.personalities import ALL_PERSONALITIES
from backend.ai.random_agent import RandomAgent
from backend.engine.characters import CHARACTER_STATS
from frontend.assets import assets
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
from frontend.theme import P1_COLOUR, P2_COLOUR, PRIMARY_PALETTES, ALTERNATE_PALETTES, get_fighter_palette
from backend.data.results_db import results_db


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


def _cross_fade(surface, clock, from_surf, to_surf, duration_s=0.5):
    """Smooth cross-fade between two full-screen surfaces."""
    frames = max(1, int(30 * duration_s))
    for f in range(frames + 1):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
        t = f / frames
        surface.blit(from_surf, (0, 0))
        blend_surf = to_surf.copy()
        blend_surf.set_alpha(int(255 * t))
        surface.blit(blend_surf, (0, 0))
        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def intro_screen(surface, clock):
    """Show the intro image with blinking 'PRESS ANY KEY'.

    On keypress/click, cross-fades smoothly over 0.5s into intro_blur.
    The background artwork already features 'ARENA-AI' on the left side.
    """
    font_prompt = pygame.font.Font(None, 30)

    intro_img = assets.get_intro((SCREEN_WIDTH, SCREEN_HEIGHT))
    blur_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))

    start_time = time.time()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                # Smooth 0.5-second cross-fade to blurry menu background
                _cross_fade(surface, clock, intro_img, blur_img, duration_s=0.5)
                return

        surface.blit(intro_img, (0, 0))

        # Blinking "PRESS ANY KEY" near the bottom (fades in and out ~1/s)
        alpha = int(128 + 127 * math.sin((time.time() - start_time) * 3.5))
        prompt_surf = font_prompt.render("PRESS ANY KEY TO START", True, WHITE)
        prompt_alpha = pygame.Surface(prompt_surf.get_size(), pygame.SRCALPHA)
        prompt_alpha.blit(prompt_surf, (0, 0))
        prompt_alpha.set_alpha(max(0, min(255, alpha)))
        rect = prompt_alpha.get_rect(midtop=(SCREEN_WIDTH // 2, 535))
        surface.blit(prompt_alpha, rect)

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def main_menu(surface, clock):
    """Show the main menu on the blurry intro image and return the chosen option.

    Returns: "start", "ai_fight", "settings", "statistics", "manual", "quit", or "intro".
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))

    items = ["Start Match", "AI Model Fight", "Model Insights", "Settings", "Statistics", "Manual", "Quit"]
    keys = ["start", "ai_fight", "insights", "settings", "statistics", "manual", "quit"]
    selected = 0
    item_rects = []

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
                    # Esc returns to the normal intro screen
                    return "intro"
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

        # Background image with a dark readability scrim
        surface.blit(bg_img, (0, 0))
        scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 95))
        surface.blit(scrim, (0, 0))

        _draw_title(surface, "ARENA-AI", font_large, y=55)

        # Draw menu items and collect their rects
        item_rects = _draw_menu_items_clickable(
            surface, items, selected, font_medium, start_y=145
        )

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def character_select(surface, clock, is_p2=False):
    """Let the player pick a fighter. Returns the personality name or 'Random'.

    Displays character portraits loaded from frontend/assets/portraits/.
    If is_p2 is True, portraits are flipped horizontally.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))

    fighters = list(ALL_PERSONALITIES.keys()) + ["Random"]
    selected = 0

    card_width = 170
    card_height = 240
    total_width = len(fighters) * card_width
    start_x = (SCREEN_WIDTH - total_width) // 2
    top_y = 120
    card_rects = []

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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(card_rects):
                    if r.collidepoint(event.pos):
                        if selected == i:
                            return fighters[selected]
                        selected = i
            if event.type == pygame.MOUSEMOTION:
                for i, r in enumerate(card_rects):
                    if r.collidepoint(event.pos):
                        selected = i

        # Background image with a dark readability scrim
        surface.blit(bg_img, (0, 0))
        scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 110))
        surface.blit(scrim, (0, 0))

        title_text = "Choose Player 2" if is_p2 else "Choose Your Fighter"
        _draw_title(surface, title_text, font_large, y=35)

        card_rects = []
        for i, name in enumerate(fighters):
            cx = start_x + i * card_width + card_width // 2
            card_rect = pygame.Rect(cx - 75, top_y, 150, card_height)
            card_rects.append(card_rect)

            is_sel = (i == selected)
            bg_col = (45, 55, 80) if is_sel else (25, 25, 35)
            pygame.draw.rect(surface, bg_col, card_rect, border_radius=8)

            # Portrait area
            p_rect = pygame.Rect(cx - 65, top_y + 10, 130, 170)
            if name in ALL_PERSONALITIES:
                portrait = assets.get_portrait(name, size=(130, 170), flip_h=is_p2)
                surface.blit(portrait, p_rect)
            else:
                # Random portrait card with gradient and question mark
                pygame.draw.rect(surface, (35, 40, 55), p_rect, border_radius=4)
                q_text = font_large.render("?", True, WHITE)
                surface.blit(q_text, q_text.get_rect(center=p_rect.center))

            # Inner portrait border
            pygame.draw.rect(surface, (60, 70, 95), p_rect, 1, border_radius=4)

            # Character name label below portrait
            name_label = font_medium.render(name, True, WHITE if is_sel else LIGHT_GREY)
            surface.blit(name_label, name_label.get_rect(midtop=(cx, top_y + 195)))

            # Card outer highlight border
            border_col = (255, 215, 0) if is_sel else (70, 75, 90)
            border_width = 3 if is_sel else 1
            pygame.draw.rect(surface, border_col, card_rect, border_width, border_radius=8)

        # Description of selected fighter
        sel_name = fighters[selected]
        if sel_name in ALL_PERSONALITIES:
            p = ALL_PERSONALITIES[sel_name]
            full = font_medium.render(p.full_name, True, (255, 230, 120))
            surface.blit(full, full.get_rect(midtop=(SCREEN_WIDTH // 2, top_y + card_height + 25)))

            desc = font_small.render(p.description, True, LIGHT_GREY)
            surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, top_y + card_height + 58)))
        elif sel_name == "Random":
            full = font_medium.render("Mystery Fighter", True, (255, 230, 120))
            surface.blit(full, full.get_rect(midtop=(SCREEN_WIDTH // 2, top_y + card_height + 25)))

            desc = font_small.render("Randomly picks one of the four fighters for this match.", True, LIGHT_GREY)
            surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, top_y + card_height + 58)))

        # Instructions
        inst = font_small.render("< / > to browse  |  Enter / Click to confirm  |  Esc to go back",
                                 True, LIGHT_GREY)
        surface.blit(inst, inst.get_rect(midtop=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 32)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def match_type_select(surface, clock):
    """Pick match mode on the blurry intro background.

    Options: 'Me vs AI', 'Random AI', 'AI vs AI'.
    Returns: 'me_vs_ai', 'random_ai', 'ai_vs_ai', or None if cancelled.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))

    types = ["Me vs AI", "Random AI", "AI vs AI"]
    type_keys = ["me_vs_ai", "random_ai", "ai_vs_ai"]
    selected = 0

    descs = {
        "me_vs_ai": "Pick your fighter, choose an AI opponent, and test your skills",
        "random_ai": "Pick your fighter and battle a randomly chosen AI opponent",
        "ai_vs_ai": "Pit two autonomous AI models against each other and watch them battle",
    }
    type_rects = []

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(types)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(types)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return type_keys[selected]
                elif event.key == pygame.K_ESCAPE:
                    return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(type_rects):
                    if r.collidepoint(event.pos):
                        return type_keys[i]
            if event.type == pygame.MOUSEMOTION:
                for i, r in enumerate(type_rects):
                    if r.collidepoint(event.pos):
                        selected = i

        surface.blit(bg_img, (0, 0))
        scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 110))
        surface.blit(scrim, (0, 0))

        _draw_title(surface, "Select Match Mode", font_large, y=60)
        type_rects = _draw_menu_items_clickable(surface, types, selected, font_medium, start_y=180)

        desc = font_small.render(descs[type_keys[selected]], True, (255, 230, 130))
        surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 420)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def difficulty_select(surface, clock):
    """Pick AI difficulty directly without match type selection.

    Returns: 'LOW', 'MEDIUM', 'HIGH', 'HELL', or None if cancelled.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))

    difficulties = ["LOW", "MEDIUM", "HIGH", "HELL"]
    selected = 0

    descs = {
        "LOW": "Slow reactions (24f delay), 30% mistakes, basic 1-ply search",
        "MEDIUM": "Moderate reactions (15f delay), 15% mistakes, 2-ply search",
        "HIGH": "Fast reactions (7f delay), 5% mistakes, 3-ply search",
        "HELL": "Instant reactions (1f delay), 1% mistakes, Expectimax & Opponent Model on Sky Colosseum!",
    }
    diff_rects = []

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(difficulties)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(difficulties)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return difficulties[selected]
                elif event.key == pygame.K_ESCAPE:
                    return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(diff_rects):
                    if r.collidepoint(event.pos):
                        return difficulties[i]
            if event.type == pygame.MOUSEMOTION:
                for i, r in enumerate(diff_rects):
                    if r.collidepoint(event.pos):
                        selected = i

        surface.blit(bg_img, (0, 0))
        scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 110))
        surface.blit(scrim, (0, 0))

        _draw_title(surface, "Select Difficulty", font_large, y=60)
        diff_rects = _draw_menu_items_clickable(surface, difficulties, selected, font_medium, start_y=180)

        desc = font_small.render(descs[difficulties[selected]], True, (255, 230, 130))
        surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 420)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def mode_select(surface, clock):
    """Backwards-compatible helper: pick match type then difficulty."""
    m_type = match_type_select(surface, clock)
    if m_type is None:
        return None, None
    diff = difficulty_select(surface, clock)
    if diff is None:
        return None, None
    return m_type, diff


def pause_screen(surface, clock):
    """Show pause overlay with Resume, Move List, Restart match, and Quit to menu options.

    Returns: 'resume', 'restart', or 'quit'.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)

    items = ["Resume", "Move List", "Restart Match", "Quit to Menu"]
    keys = ["resume", "movelist", "restart", "quit"]
    selected = 0

    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))

    base_frame = surface.copy()
    menu_rects = []

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
                    res = keys[selected]
                    if res == "movelist":
                        move_list_screen(surface, clock)
                        continue
                    return res
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(menu_rects):
                    if r.collidepoint(event.pos):
                        res = keys[i]
                        if res == "movelist":
                            move_list_screen(surface, clock)
                            continue
                        return res
            if event.type == pygame.MOUSEMOTION:
                for i, r in enumerate(menu_rects):
                    if r.collidepoint(event.pos):
                        selected = i

        temp = base_frame.copy()
        temp.blit(overlay, (0, 0))
        _draw_title(temp, "PAUSED", font_large, y=140)
        menu_rects = _draw_menu_items_clickable(temp, items, selected, font_medium, start_y=240)

        surface.blit(temp, (0, 0))
        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def move_list_screen(surface, clock):
    """Display comprehensive move list, inputs, and frame data (Phase 6)."""
    font_title = pygame.font.Font(None, 40)
    font_header = pygame.font.Font(None, 24)
    font_body = pygame.font.Font(None, 19)

    tabs = ["Universal", "Crimson", "Steel", "Shadow", "Golden"]
    current_tab = 0

    from backend.engine.moves import UNIVERSAL_MOVES, CHARACTER_MOVES

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    return
                elif event.key == pygame.K_LEFT:
                    current_tab = (current_tab - 1) % len(tabs)
                elif event.key == pygame.K_RIGHT:
                    current_tab = (current_tab + 1) % len(tabs)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Tab clicking
                for idx, tab_name in enumerate(tabs):
                    tab_rect = pygame.Rect(80 + idx * 130, 75, 120, 30)
                    if tab_rect.collidepoint(event.pos):
                        current_tab = idx
                # Back button
                back_rect = pygame.Rect(SCREEN_WIDTH // 2 - 60, SCREEN_HEIGHT - 45, 120, 32)
                if back_rect.collidepoint(event.pos):
                    return

        surface.fill((18, 20, 30))

        # Title
        _draw_title(surface, "MOVE LIST & FRAME DATA", font_title, y=25)

        # Tabs
        for idx, tab_name in enumerate(tabs):
            tab_rect = pygame.Rect(80 + idx * 130, 75, 120, 30)
            is_active = (idx == current_tab)
            bg_col = (50, 70, 110) if is_active else (30, 35, 50)
            pygame.draw.rect(surface, bg_col, tab_rect, border_radius=4)
            pygame.draw.rect(surface, (100, 140, 200) if is_active else (60, 65, 80), tab_rect, 1, border_radius=4)
            t_col = (255, 255, 255) if is_active else (160, 170, 190)
            txt = font_header.render(tab_name, True, t_col)
            surface.blit(txt, txt.get_rect(center=tab_rect.center))

        # Table Header
        header_y = 125
        headers = [("MOVE", 80), ("INPUT", 220), ("DMG", 360), ("STARTUP", 440), ("ON BLOCK", 530), ("PROPERTIES", 630)]
        for h_text, h_x in headers:
            h_surf = font_header.render(h_text, True, (255, 215, 0))
            surface.blit(h_surf, (h_x, header_y))
        pygame.draw.line(surface, (70, 80, 105), (70, header_y + 24), (SCREEN_WIDTH - 70, header_y + 24), 2)

        # Move list entries
        active_name = tabs[current_tab]
        if active_name == "Universal":
            moves = list(UNIVERSAL_MOVES.values())[:9]
        else:
            char_dict = CHARACTER_MOVES.get(active_name, {})
            # Get specials and supers
            moves = [m for m in char_dict.values() if "Special" in m.name or "Super" in m.name or m.action.name.startswith("SPECIAL") or m.action.name == "SUPER"]
            if not moves:
                moves = list(char_dict.values())[:8]

        row_y = 160
        input_map = {
            "Jab": "J", "Heavy Punch": "K", "Light Kick": "U", "Heavy Kick": "I",
            "Low Sweep": "S + I", "Overhead Strike": "Fwd + K", "Crouching Jab": "S + J",
            "Crouching Kick": "S + U", "Anti-Air Uppercut": "S + K", "Normal Throw": "J + U",
            "Crimson Rush": "Fwd + O", "Rising Uppercut": "O", "Berserker Charge": "Back + O",
            "Clinch Slam": "Down + O", "Blood Fury": "P",
            "Iron Wall": "Down + O", "Shield Bash": "Fwd + O", "Punisher Grip": "O",
            "Reflector": "Back + O", "Fortress Crush": "P",
            "Shadow Step": "Fwd + O", "Phantom Kick": "Down + O", "Feint Strike": "Back + O",
            "Energy Dart": "O", "Vanishing Arts": "P",
            "Tactician Stance": "Down + O", "Golden Read": "O", "Gambit Strike": "Fwd + O",
            "Tactical Step": "Back + O", "Checkmate": "P",
        }

        for m in moves:
            inp = input_map.get(m.name, m.action.name)
            adv = f"{'+' if m.on_block > 0 else ''}{m.on_block}"
            prop = m.hit_level.name
            if m.knockdown:
                prop += ", Knockdown"
            if m.launch:
                prop += ", Launch"
            if m.meter_cost > 0:
                prop += f", Cost {int(m.meter_cost)}"

            surface.blit(font_body.render(m.name, True, WHITE), (80, row_y))
            surface.blit(font_body.render(inp, True, (0, 229, 255)), (220, row_y))
            surface.blit(font_body.render(f"{m.damage:.1f} HP", True, (255, 100, 100)), (360, row_y))
            surface.blit(font_body.render(f"{m.startup}f", True, (220, 220, 220)), (440, row_y))
            surface.blit(font_body.render(adv, True, (100, 255, 100) if m.on_block >= 0 else (255, 120, 120)), (530, row_y))
            surface.blit(font_body.render(prop, True, (200, 200, 200)), (630, row_y))
            row_y += 26

        # Back instruction
        back_rect = pygame.Rect(SCREEN_WIDTH // 2 - 60, SCREEN_HEIGHT - 45, 120, 30)
        pygame.draw.rect(surface, (40, 45, 60), back_rect, border_radius=4)
        pygame.draw.rect(surface, (100, 110, 130), back_rect, 1, border_radius=4)
        b_txt = font_body.render("Back (Esc)", True, (255, 255, 255))
        surface.blit(b_txt, b_txt.get_rect(center=back_rect.center))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def format_hp_stat(val) -> str:
    """Format damage or health as health points out of 100 per round.

    Damage and health are stored 0..1 (per round).
    If val <= 10.0, it is scaled by 100 and rounded (e.g. 2.12 -> '212 HP').
    If val > 10.0, it is treated as already in HP and rounded (e.g. 185.0 -> '185 HP').
    Never returns '... dmg'.
    """
    if val is None:
        return "0 HP"
    v = float(val)
    if v <= 10.0:
        hp = int(round(v * 100.0))
    else:
        hp = int(round(v))
    return f"{hp} HP"


def results_screen(surface, clock, stats_or_result, p1_name=None, p2_name=None,
                   lockout_s=3.0, ai_timeout_s=10.0):
    """Result screen after a deciding round.

    Specification (Addendum B + Result Screen Enhancements):
    - One font family (Pygame default) in three sizes: title (52), header (24), body (18).
    - Damage & health shown as HP (e.g. '212 HP', never 'dmg').
    - Stat row 'Health left (last round)' in HP.
    - Names: Header left 'YOU' + full name, Right AI with difficulty (or Alt in mirror).
    - Round results as 3 chips with winner colour and KO/TIME/DRAW badge.
    - Both portraits: Winner on left (gold border, soft glow, 'WINNER'),
      Loser on right (smaller, 50% dark, grey border, 'DEFEATED'), facing each other.
    - Stats table between portraits with 3 fixed columns, bold/coloured better values,
      and proportional comparison bars.
    - Title with drop shadow, soft glow, scaling animation (130% -> 100% in 0.3s).
    - Semi-transparent scrim (~75% opacity) with result border.
    - Buttons with 3s lockout progress bar, arrow key selection, hover/click, and direct R/C/Esc.
    - Returns: 'rematch', 'character_select', or 'menu'.
    """
    if isinstance(stats_or_result, dict):
        stats = stats_or_result
    else:
        res = str(stats_or_result)
        stats = {
            "p1_name": p1_name or "Player",
            "p2_name": p2_name or "AI",
            "p1_character": "Golden",
            "p2_character": "Crimson",
            "p1_kind": "human" if (p1_name == "Player" or not p1_name) else "ai",
            "p2_kind": "ai",
            "p1_difficulty": "MEDIUM",
            "p2_difficulty": "MEDIUM",
            "arena": "Neon Rooftop",
            "damage_dealt_p1": 1.0 if res == "p1" else 0.5,
            "damage_dealt_p2": 1.0 if res == "p2" else 0.5,
            "hits_landed_p1": 6 if res == "p1" else 3,
            "hits_landed_p2": 6 if res == "p2" else 3,
            "blocks_p1": 2,
            "blocks_p2": 2,
            "longest_combo_p1": 3,
            "longest_combo_p2": 2,
            "rounds_history": [
                {"round_number": 1, "winner_side": 1 if res == "p1" else 2, "ended_by": "KO", "duration_s": 15.0, "p1_health_left": 0.4, "p2_health_left": 0.0},
                {"round_number": 2, "winner_side": 1 if res == "p1" else 2, "ended_by": "KO", "duration_s": 16.0, "p1_health_left": 0.55, "p2_health_left": 0.0},
            ],
            "winner_side": 1 if res == "p1" else (2 if res == "p2" else 0),
            "rounds_p1": 2 if res == "p1" else 0,
            "rounds_p2": 2 if res == "p2" else 0,
            "duration_s": 31.0,
            "status": "finished",
            "match_result": res,
        }

    winner_side = stats.get("winner_side", 0)
    p1_kind = stats.get("p1_kind", "human")
    p2_kind = stats.get("p2_kind", "ai")
    is_human_match = (p1_kind == "human" or p2_kind == "human")
    is_ai_vs_ai = (p1_kind == "ai" and p2_kind == "ai")

    # Font: Exactly one font family across 3 sizes only
    font_title = pygame.font.Font(None, 52)
    font_header = pygame.font.Font(None, 24)
    font_body = pygame.font.Font(None, 18)

    # Characters & Mirror check
    p1_char = stats.get("p1_character", "Golden")
    p2_char = stats.get("p2_character", "Crimson")
    is_mirror = (str(p1_char).strip().lower() == str(p2_char).strip().lower())

    p2_palette = ALTERNATE_PALETTES.get(p2_char, {}) if is_mirror else PRIMARY_PALETTES.get(p2_char, {})
    p2_color = p2_palette.get("body", P2_COLOUR) if is_mirror else P2_COLOUR
    p2_suffix = " (Alt)" if is_mirror else ""

    p1_full = PRIMARY_PALETTES.get(p1_char, {}).get("title", p1_char)
    p2_full = PRIMARY_PALETTES.get(p2_char, {}).get("title", p2_char) + p2_suffix

    # Determine Title, Title Colour, Glow Colour, and Background
    if is_human_match:
        if winner_side == 1:
            bg = assets.get_victory((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "YOU WIN"
            result_col = (241, 196, 15)   # Gold
            glow_col = (241, 196, 15)
        elif winner_side == 2:
            bg = assets.get_defeat((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "YOU LOSE"
            result_col = (231, 76, 60)    # Crimson red
            glow_col = (231, 76, 60)
        else:
            bg = assets.get_draw_screen((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "DRAW"
            result_col = (189, 195, 199)  # Light grey
            glow_col = (189, 195, 199)
    else:  # AI vs AI
        if winner_side in (1, 2):
            bg = assets.get_victory((SCREEN_WIDTH, SCREEN_HEIGHT))
            w_char = p1_char if winner_side == 1 else p2_char
            full_w_name = PRIMARY_PALETTES.get(w_char, {}).get("title", w_char)
            title_text = f"{full_w_name.upper()} WINS"
            result_col = PRIMARY_PALETTES.get(w_char, {}).get("accent", (241, 196, 15))
            glow_col = result_col
        else:
            bg = assets.get_draw_screen((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "DRAW"
            result_col = (189, 195, 199)
            glow_col = (189, 195, 199)

    # Portrait assignments
    # Winner portrait on left (gold border, soft glow, 'WINNER')
    # Loser portrait on right (smaller, 50% dark, grey border, 'DEFEATED')
    # Portraits face each other: left faces right (flip_h=False), right faces left (flip_h=True)
    if winner_side == 1:
        left_char = p1_char
        right_char = p2_char
        left_status = "WINNER"
        right_status = "DEFEATED"
        left_is_winner = True
        right_is_winner = False
        left_border = (241, 196, 15)
        right_border = (110, 115, 125)
    elif winner_side == 2:
        left_char = p2_char
        right_char = p1_char
        left_status = "WINNER"
        right_status = "DEFEATED"
        left_is_winner = True
        right_is_winner = False
        left_border = (241, 196, 15)
        right_border = (110, 115, 125)
    else:  # Draw
        left_char = p1_char
        right_char = p2_char
        left_status = "DRAW"
        right_status = "DRAW"
        left_is_winner = False
        right_is_winner = False
        left_border = (160, 165, 175)
        right_border = (160, 165, 175)

    # Header titles
    if is_human_match:
        p1_head_top = "YOU"
        p1_head_sub = p1_full
    else:
        p1_diff = str(stats.get("p1_difficulty", "MEDIUM")).upper()
        p1_head_top = p1_full
        p1_head_sub = f"(AI, {p1_diff})"

    p2_diff = str(stats.get("p2_difficulty", "MEDIUM")).upper()
    p2_head_top = p2_full
    p2_head_sub = f"({p2_kind.upper()}, {p2_diff})"

    # Round results chips
    round_history = stats.get("rounds_history", [])
    chips_data = []
    if round_history:
        for idx, r in enumerate(round_history):
            r_num = r.get("round_number", idx + 1)
            w_side = r.get("winner_side", 0)
            ended = str(r.get("ended_by", "KO")).upper()
            if w_side == 1:
                w_lbl = "YOU" if p1_kind == "human" else p1_char
                c_col = P1_COLOUR
            elif w_side == 2:
                w_lbl = f"{p2_char} (AI)" if p2_kind == "ai" else ("YOU" if p2_kind == "human" else p2_char)
                c_col = p2_color
            else:
                w_lbl = "DRAW"
                c_col = (160, 165, 175)
            chips_data.append((f"R{r_num}  {w_lbl}  {ended}", c_col))
    else:
        r1 = stats.get("rounds_p1", 0)
        r2 = stats.get("rounds_p2", 0)
        total_r = max(1, r1 + r2)
        for i in range(total_r):
            if i < r1:
                chips_data.append((f"R{i+1}  {'YOU' if p1_kind == 'human' else p1_char}  KO", P1_COLOUR))
            else:
                chips_data.append((f"R{i+1}  {p2_char} (AI)  KO", p2_color))

    # Stats table calculations
    dmg1_val = float(stats.get("damage_dealt_p1", 0.0))
    dmg2_val = float(stats.get("damage_dealt_p2", 0.0))
    num_dmg1 = dmg1_val * 100.0 if dmg1_val <= 10.0 else dmg1_val
    num_dmg2 = dmg2_val * 100.0 if dmg2_val <= 10.0 else dmg2_val

    # Health left (last round)
    if round_history:
        last_r = round_history[-1]
        hl1_raw = float(last_r.get("p1_health_left", stats.get("p1_health_left", 0.0)))
        hl2_raw = float(last_r.get("p2_health_left", stats.get("p2_health_left", 0.0)))
    else:
        hl1_raw = float(stats.get("p1_health_left", 1.0 if winner_side == 1 else 0.0))
        hl2_raw = float(stats.get("p2_health_left", 1.0 if winner_side == 2 else 0.0))
    num_hl1 = hl1_raw * 100.0 if hl1_raw <= 10.0 else hl1_raw
    num_hl2 = hl2_raw * 100.0 if hl2_raw <= 10.0 else hl2_raw

    stat_rows = [
        ("Damage dealt (HP)", num_dmg1, num_dmg2, format_hp_stat(dmg1_val), format_hp_stat(dmg2_val)),
        ("Hits landed", float(stats.get("hits_landed_p1", 0)), float(stats.get("hits_landed_p2", 0)),
         str(stats.get("hits_landed_p1", 0)), str(stats.get("hits_landed_p2", 0))),
        ("Blocks", float(stats.get("blocks_p1", 0)), float(stats.get("blocks_p2", 0)),
         str(stats.get("blocks_p1", 0)), str(stats.get("blocks_p2", 0))),
        ("Longest combo", float(stats.get("longest_combo_p1", 0)), float(stats.get("longest_combo_p2", 0)),
         str(stats.get("longest_combo_p1", 0)), str(stats.get("longest_combo_p2", 0))),
        ("Health left (last round)", num_hl1, num_hl2, format_hp_stat(hl1_raw), format_hp_stat(hl2_raw)),
    ]

    # Clean arena name
    arena_raw = str(stats.get("arena", "Neon Rooftop"))
    arena_clean = (
        arena_raw.replace("arena_", "")
        .replace(".jpeg", "")
        .replace(".png", "")
        .replace(".jpg", "")
        .replace("_", " ")
        .title()
    )

    # Info line
    dur_s = float(stats.get("duration_s", 0.0))
    dur_min = int(dur_s) // 60
    dur_sec = int(dur_s) % 60
    info_str = f"Time {dur_min}:{dur_sec:02d}  ·  Difficulty {p2_diff}  ·  Arena {arena_clean}"

    # Buttons definition (default selection is 2: Main Menu, matching Enter/Esc spec)
    btn_rematch = pygame.Rect(100, 450, 230, 44)
    btn_char = pygame.Rect(397, 450, 230, 44)
    btn_menu = pygame.Rect(694, 450, 230, 44)
    buttons_info = [
        (btn_rematch, "[R] Rematch", (38, 115, 52), "rematch"),
        (btn_char, "[C] Character Select", (32, 92, 142), "character_select"),
        (btn_menu, "[Esc] Main Menu", (65, 75, 95), "menu"),
    ]
    selected_idx = 2

    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        locked = (elapsed < lockout_s)

        # AI vs AI auto-return after ai_timeout_s
        if is_ai_vs_ai and elapsed >= ai_timeout_s:
            return "menu"

        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "menu"

            if not locked:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:
                        selected_idx = (selected_idx - 1) % len(buttons_info)
                    elif event.key == pygame.K_RIGHT:
                        selected_idx = (selected_idx + 1) % len(buttons_info)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        return buttons_info[selected_idx][3]
                    elif event.key == pygame.K_r:
                        return "rematch"
                    elif event.key == pygame.K_c:
                        return "character_select"
                    elif event.key == pygame.K_ESCAPE:
                        return "menu"
                elif event.type == pygame.MOUSEMOTION:
                    for i, (b_rect, _, _, _) in enumerate(buttons_info):
                        if b_rect.collidepoint(event.pos):
                            selected_idx = i
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for i, (b_rect, _, _, action) in enumerate(buttons_info):
                        if b_rect.collidepoint(event.pos):
                            return action

        # --- Draw scene ---
        surface.blit(bg, (0, 0))

        # Main Scrim Panel: ~80% opacity, rounded corners, result colour glowing border
        scrim_rect = pygame.Rect(48, 16, 928, 568)
        scrim = pygame.Surface(scrim_rect.size, pygame.SRCALPHA)
        # Fill only inside the rounded rect so outside remains 100% transparent (no black corner artifacts)
        pygame.draw.rect(scrim, (12, 15, 26, 210), scrim.get_rect(), border_radius=16)
        surface.blit(scrim, scrim_rect.topleft)

        # Soft outer ambient glow border (smooth 3px expansion)
        glow_box = scrim_rect.inflate(6, 6)
        glow_border = pygame.Surface(glow_box.size, pygame.SRCALPHA)
        pygame.draw.rect(glow_border, (*result_col, 50), glow_border.get_rect(), width=3, border_radius=19)
        surface.blit(glow_border, glow_box.topleft)

        # Crisp primary border
        pygame.draw.rect(surface, result_col, scrim_rect, width=2, border_radius=16)

        # Subtle inner highlight line
        inner_box = scrim_rect.inflate(-4, -4)
        inner_border = pygame.Surface(inner_box.size, pygame.SRCALPHA)
        pygame.draw.rect(inner_border, (*result_col, 75), inner_border.get_rect(), width=1, border_radius=14)
        surface.blit(inner_border, inner_box.topleft)

        # Title animation: scale from 130% down to 100% in 0.3s
        anim_t = min(1.0, elapsed / 0.3)
        scale = 1.0 + 0.30 * (1.0 - anim_t)
        title_y = 50

        base_title = font_title.render(title_text, True, result_col)
        base_shadow = font_title.render(title_text, True, (0, 0, 0))
        base_glow = font_title.render(title_text, True, glow_col)

        if scale > 1.005:
            nw = max(1, int(round(base_title.get_width() * scale)))
            nh = max(1, int(round(base_title.get_height() * scale)))
            title_render = pygame.transform.smoothscale(base_title, (nw, nw_h := nh))
            shadow_render = pygame.transform.smoothscale(base_shadow, (nw, nw_h))
            glow_render = pygame.transform.smoothscale(base_glow, (nw, nw_h))
        else:
            title_render = base_title
            shadow_render = base_shadow
            glow_render = base_glow

        # Soft glow
        glow_copy = glow_render.copy()
        glow_copy.set_alpha(55)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            surface.blit(glow_copy, glow_copy.get_rect(center=(SCREEN_WIDTH // 2 + dx, title_y + dy)))

        # Dark drop shadow
        surface.blit(shadow_render, shadow_render.get_rect(center=(SCREEN_WIDTH // 2 + 2, title_y + 3)))
        # Title text
        surface.blit(title_render, title_render.get_rect(center=(SCREEN_WIDTH // 2, title_y)))

        # Score line: "ROUNDS: 2 - 1" with winner's number in player colour
        r1_val = stats.get("rounds_p1", 0)
        r2_val = stats.get("rounds_p2", 0)
        c1_score = P1_COLOUR if winner_side == 1 else WHITE
        c2_score = p2_color if winner_side == 2 else WHITE

        s_prefix = font_header.render("ROUNDS:   ", True, LIGHT_GREY)
        s_p1 = font_header.render(str(r1_val), True, c1_score)
        s_mid = font_header.render("   -   ", True, LIGHT_GREY)
        s_p2 = font_header.render(str(r2_val), True, c2_score)

        score_w = s_prefix.get_width() + s_p1.get_width() + s_mid.get_width() + s_p2.get_width()
        cur_sx = SCREEN_WIDTH // 2 - score_w // 2
        score_y = 82
        for s_part in (s_prefix, s_p1, s_mid, s_p2):
            surface.blit(s_part, (cur_sx, score_y))
            cur_sx += s_part.get_width()

        # Round results chips: "R1  Golden (AI)  KO", "R2  YOU  KO", etc.
        chip_count = len(chips_data)
        if chip_count > 0:
            chip_w = 175
            chip_h = 24
            spacing = 16
            total_chip_w = chip_count * chip_w + (chip_count - 1) * spacing
            c_start_x = SCREEN_WIDTH // 2 - total_chip_w // 2
            chip_y = 108
            for i, (chip_txt, chip_col) in enumerate(chips_data):
                c_rect = pygame.Rect(c_start_x + i * (chip_w + spacing), chip_y, chip_w, chip_h)
                pygame.draw.rect(surface, (18, 22, 34), c_rect, border_radius=6)
                pygame.draw.rect(surface, chip_col, c_rect, width=1, border_radius=6)
                c_surf = font_body.render(chip_txt, True, chip_col)
                surface.blit(c_surf, c_surf.get_rect(center=c_rect.center))

        # Divider line
        pygame.draw.line(surface, (45, 52, 75), (68, 138), (956, 138), 1)

        # --- Both Portraits ---
        # Left Portrait (Winner on left when win/loss, or P1 on draw)
        left_w, left_h = (128, 160)
        left_box = pygame.Rect(66, 154, 144, 234)
        if left_is_winner:
            glow_box = left_box.inflate(10, 10)
            glow_card = pygame.Surface(glow_box.size, pygame.SRCALPHA)
            pygame.draw.rect(glow_card, (241, 196, 15, 40), glow_card.get_rect(), border_radius=14)
            surface.blit(glow_card, glow_box.topleft)

        pygame.draw.rect(surface, (18, 22, 34), left_box, border_radius=10)
        pygame.draw.rect(surface, left_border, left_box, width=2 if left_is_winner else 1, border_radius=10)

        # Framed inner portrait slot
        left_slot = pygame.Rect(left_box.x + 8, left_box.y + 10, left_w, left_h)
        pygame.draw.rect(surface, (10, 12, 20), left_slot, border_radius=6)
        left_surf = assets.get_portrait(left_char, size=(left_w, left_h), flip_h=False)
        surface.blit(left_surf, left_slot.topleft)
        pygame.draw.rect(surface, (100, 110, 130), left_slot, width=1, border_radius=6)

        left_lbl = font_header.render(left_status, True, left_border)
        surface.blit(left_lbl, left_lbl.get_rect(center=(left_box.centerx, left_box.bottom - 18)))

        # Right Portrait (Loser on right, smaller, darkened ~50%, flipped horizontally)
        if winner_side in (1, 2):
            right_w, right_h = (104, 130)
            right_box = pygame.Rect(814, 172, 124, 204)
        else:
            right_w, right_h = (128, 160)
            right_box = pygame.Rect(814, 154, 144, 234)

        pygame.draw.rect(surface, (15, 18, 28), right_box, border_radius=10)
        pygame.draw.rect(surface, right_border, right_box, width=1, border_radius=10)

        # Framed inner portrait slot
        right_slot = pygame.Rect(right_box.centerx - right_w // 2, right_box.top + 10, right_w, right_h)
        pygame.draw.rect(surface, (8, 10, 16), right_slot, border_radius=6)

        right_surf = assets.get_portrait(right_char, size=(right_w, right_h), flip_h=True).copy()
        if not right_is_winner and winner_side in (1, 2):
            dark_overlay = pygame.Surface((right_w, right_h), pygame.SRCALPHA)
            dark_overlay.fill((0, 0, 0, 128))
            right_surf.blit(dark_overlay, (0, 0))

        surface.blit(right_surf, right_slot.topleft)
        pygame.draw.rect(surface, (70, 75, 85), right_slot, width=1, border_radius=6)

        right_lbl = font_body.render(right_status, True, (140, 145, 155))
        surface.blit(right_lbl, right_lbl.get_rect(center=(right_box.centerx, right_box.bottom - 16)))

        # --- Stats Table (Between portraits) ---
        col1_x = 238
        col2_center = 490
        col3_center = 695

        # Table Header
        h_stats = font_header.render("MATCH STATS", True, LIGHT_GREY)
        surface.blit(h_stats, (col1_x, 154))

        # P1 Header
        p1_top_surf = font_header.render(p1_head_top, True, P1_COLOUR)
        surface.blit(p1_top_surf, p1_top_surf.get_rect(center=(col2_center, 154)))
        p1_sub_surf = font_body.render(p1_head_sub, True, LIGHT_GREY)
        surface.blit(p1_sub_surf, p1_sub_surf.get_rect(center=(col2_center, 174)))

        # P2 Header
        p2_top_surf = font_header.render(p2_head_top, True, p2_color)
        surface.blit(p2_top_surf, p2_top_surf.get_rect(center=(col3_center, 154)))
        p2_sub_surf = font_body.render(p2_head_sub, True, LIGHT_GREY)
        surface.blit(p2_sub_surf, p2_sub_surf.get_rect(center=(col3_center, 174)))

        # Table Rows
        row_y = 196
        for lbl, n1, n2, str1, str2 in stat_rows:
            row_box = pygame.Rect(230, row_y, 564, 34)
            pygame.draw.rect(surface, (18, 22, 34), row_box, border_radius=5)

            # Label
            lbl_surf = font_body.render(lbl, True, LIGHT_GREY)
            surface.blit(lbl_surf, (col1_x, row_y + 6))

            # Values styling: better is bold in player colour, worse is grey, equal is white
            if n1 > n2:
                c1, b1 = P1_COLOUR, True
                c2, b2 = (140, 140, 140), False
            elif n2 > n1:
                c1, b1 = (140, 140, 140), False
                c2, b2 = p2_color, True
            else:
                c1, b1 = WHITE, False
                c2, b2 = WHITE, False

            font_body.set_bold(b1)
            v1_surf = font_body.render(str1, True, c1)
            surface.blit(v1_surf, v1_surf.get_rect(center=(col2_center, row_y + 13)))

            font_body.set_bold(b2)
            v2_surf = font_body.render(str2, True, c2)
            surface.blit(v2_surf, v2_surf.get_rect(center=(col3_center, row_y + 13)))
            font_body.set_bold(False)

            # Thin proportional comparison bar under each row
            bar_total_w = 548
            bar_x = 238
            bar_y = row_y + 27
            if n1 + n2 > 0:
                frac = max(0.04, min(0.96, n1 / (n1 + n2)))
                w1 = int(round(bar_total_w * frac))
            else:
                w1 = bar_total_w // 2

            pygame.draw.rect(surface, P1_COLOUR, pygame.Rect(bar_x, bar_y, w1, 3))
            pygame.draw.rect(surface, p2_color, pygame.Rect(bar_x + w1, bar_y, bar_total_w - w1, 3))

            row_y += 40

        # Divider line
        pygame.draw.line(surface, (45, 52, 75), (68, 404), (956, 404), 1)

        # Match Info Line: "Time 0:21 · Difficulty LOW · Arena Iron Foundry"
        info_surf = font_body.render(info_str, True, LIGHT_GREY)
        surface.blit(info_surf, info_surf.get_rect(center=(SCREEN_WIDTH // 2, 422)))

        # --- Buttons ---
        for i, (b_rect, text, base_col, _) in enumerate(buttons_info):
            if locked:
                pygame.draw.rect(surface, (32, 36, 48), b_rect, border_radius=8)
                pygame.draw.rect(surface, (55, 60, 75), b_rect, width=1, border_radius=8)
                btn_txt = font_header.render(text, True, (120, 125, 140))
                surface.blit(btn_txt, btn_txt.get_rect(center=b_rect.center))
            else:
                is_selected = (selected_idx == i)
                col = tuple(min(255, c + 45) for c in base_col) if is_selected else base_col
                pygame.draw.rect(surface, col, b_rect, border_radius=8)
                border_col = (255, 255, 255) if is_selected else (90, 100, 125)
                border_width = 2 if is_selected else 1
                pygame.draw.rect(surface, border_col, b_rect, width=border_width, border_radius=8)
                btn_txt = font_header.render(text, True, WHITE if is_selected else (220, 225, 235))
                surface.blit(btn_txt, btn_txt.get_rect(center=b_rect.center))

        # Progress bar / Status under buttons
        if locked:
            prog_bg = pygame.Rect(100, 506, 824, 4)
            pygame.draw.rect(surface, (28, 32, 45), prog_bg, border_radius=2)
            fill_w = int(round(824 * min(1.0, elapsed / lockout_s)))
            if fill_w > 0:
                pygame.draw.rect(surface, result_col, pygame.Rect(100, 506, fill_w, 4), border_radius=2)
            rem = max(0.0, lockout_s - elapsed)
            lock_txt = font_body.render(f"Input locked... ({rem:.1f}s)", True, (130, 135, 150))
            surface.blit(lock_txt, lock_txt.get_rect(center=(SCREEN_WIDTH // 2, 524)))
        else:
            if is_ai_vs_ai:
                auto_rem = max(0, int(round(ai_timeout_s - elapsed)))
                auto_txt = font_body.render(f"Auto-returning to AI menu in {auto_rem}s...", True, (150, 160, 180))
                surface.blit(auto_txt, auto_txt.get_rect(center=(SCREEN_WIDTH // 2, 520)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def player_name_prompt(surface, clock) -> str:
    """Prompt the user for their player name on first launch."""
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    player_name = "Player"

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return player_name
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return player_name.strip() or "Player"
                elif event.key == pygame.K_ESCAPE:
                    return player_name.strip() or "Player"
                elif event.key == pygame.K_BACKSPACE:
                    player_name = player_name[:-1]
                else:
                    if len(player_name) < 16 and (event.unicode.isalnum() or event.unicode in " _-"):
                        player_name += event.unicode

        surface.blit(bg_img, (0, 0))

        # Modal box
        modal_rect = pygame.Rect(SCREEN_WIDTH // 2 - 250, 180, 500, 240)
        modal_surf = pygame.Surface((500, 240), pygame.SRCALPHA)
        modal_surf.fill((15, 20, 35, 235))
        surface.blit(modal_surf, modal_rect)
        pygame.draw.rect(surface, (80, 100, 150), modal_rect, width=2, border_radius=10)

        t1 = font_large.render("WELCOME TO ARENA-AI", True, (241, 196, 15))
        surface.blit(t1, t1.get_rect(center=(SCREEN_WIDTH // 2, 220)))

        t2 = font_small.render("Enter Your Player Callsign:", True, LIGHT_GREY)
        surface.blit(t2, t2.get_rect(center=(SCREEN_WIDTH // 2, 260)))

        # Text input box
        input_rect = pygame.Rect(SCREEN_WIDTH // 2 - 160, 290, 320, 44)
        pygame.draw.rect(surface, (30, 35, 55), input_rect, border_radius=6)
        pygame.draw.rect(surface, (100, 130, 200), input_rect, width=2, border_radius=6)

        cursor = "_" if (int(time.time() * 2) % 2 == 0) else ""
        txt_surf = font_medium.render(player_name + cursor, True, WHITE)
        surface.blit(txt_surf, txt_surf.get_rect(center=input_rect.center))

        t3 = font_small.render("Press Enter to Confirm  |  Esc for Default", True, (160, 175, 200))
        surface.blit(t3, t3.get_rect(center=(SCREEN_WIDTH // 2, 380)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def settings_screen(surface, clock, settings):
    """Settings screen with options, CSV export, and results reset.

    settings: {"log_fights": bool, "speed": float, "show_ai": bool}
    Returns updated settings dict.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    # Ensure all settings exist with defaults
    settings.setdefault("log_fights", False)
    settings.setdefault("speed", 1.0)
    settings.setdefault("show_ai", True)

    SPEED_OPTIONS = [0.5, 1.0, 2.0, 3.0]
    SPEED_LABELS = ["0.5x", "1x", "2x", "3x"]

    if settings["speed"] in SPEED_OPTIONS:
        speed_index = SPEED_OPTIONS.index(settings["speed"])
    else:
        speed_index = 1
        settings["speed"] = 1.0

    items = ["log_fights", "speed", "show_ai", "export_csv", "reset_results"]
    labels = {
        "log_fights": "Log Human Fights",
        "speed": "Game Speed",
        "show_ai": "Show AI Thinking",
        "export_csv": "Export Results to CSV",
        "reset_results": "Reset Match Results",
    }
    selected = 0
    confirming_reset = False
    status_msg = ""
    status_timer = 0.0

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    row_rects = []

    while True:
        now = time.time()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return settings

            if confirming_reset:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_y:
                        results_db.reset_results()
                        status_msg = "Match results reset successfully!"
                        status_timer = now + 3.0
                        confirming_reset = False
                    elif event.key in (pygame.K_ESCAPE, pygame.K_n):
                        confirming_reset = False
                continue

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
                        speed_index = (speed_index + 1) % len(SPEED_OPTIONS)
                        settings["speed"] = SPEED_OPTIONS[speed_index]
                    elif key == "export_csv":
                        path = results_db.export_results_to_csv()
                        status_msg = f"Exported to {path}!"
                        status_timer = now + 3.0
                    elif key == "reset_results":
                        confirming_reset = True
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
                        elif key == "export_csv":
                            path = results_db.export_results_to_csv()
                            status_msg = f"Exported to {path}!"
                            status_timer = now + 3.0
                        elif key == "reset_results":
                            confirming_reset = True

            if event.type == pygame.MOUSEMOTION:
                for i, rect in enumerate(row_rects):
                    if rect.collidepoint(event.pos):
                        selected = i

        surface.blit(bg_img, (0, 0))
        scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 130))
        surface.blit(scrim, (0, 0))

        _draw_title(surface, "Settings", font_large, y=50)

        row_rects = []
        for i, key in enumerate(items):
            if key == "log_fights":
                val = "ON" if settings["log_fights"] else "OFF"
                text = f"{labels[key]}:  {val}"
            elif key == "speed":
                val = f"<  {SPEED_LABELS[speed_index]}  >"
                text = f"{labels[key]}:  {val}"
            elif key == "show_ai":
                val = "ON" if settings["show_ai"] else "OFF"
                text = f"{labels[key]}:  {val}"
            elif key == "export_csv":
                text = f"[ {labels[key]} ]"
            elif key == "reset_results":
                text = f"[ {labels[key]} ]"
            else:
                text = f"{labels[key]}"

            colour = WHITE if i == selected else LIGHT_GREY
            bg = MENU_HIGHLIGHT if i == selected else None

            rendered = font_medium.render(text, True, colour)
            rect = rendered.get_rect(midtop=(SCREEN_WIDTH // 2, 140 + i * 55))
            click_rect = rect.inflate(60, 14)

            if bg:
                pygame.draw.rect(surface, bg, click_rect, border_radius=6)

            surface.blit(rendered, rect)
            row_rects.append(click_rect)

        # Confirmation Modal
        if confirming_reset:
            confirm_box = pygame.Rect(SCREEN_WIDTH // 2 - 250, 440, 500, 60)
            pygame.draw.rect(surface, (180, 40, 40), confirm_box, border_radius=8)
            pygame.draw.rect(surface, (255, 100, 100), confirm_box, width=2, border_radius=8)
            c_txt = font_small.render("Are you sure? Press [Y] to confirm reset, [Esc] to cancel", True, WHITE)
            surface.blit(c_txt, c_txt.get_rect(center=confirm_box.center))
        elif now < status_timer and status_msg:
            # Status / Notification toast
            toast_box = pygame.Rect(SCREEN_WIDTH // 2 - 250, 440, 500, 45)
            pygame.draw.rect(surface, (40, 120, 60), toast_box, border_radius=8)
            toast_txt = font_small.render(status_msg, True, WHITE)
            surface.blit(toast_txt, toast_txt.get_rect(center=toast_box.center))
        else:
            speed_desc = {
                0.5: "0.5x: Half speed — slower animations & movement",
                1.0: "1x: Normal speed (default starting value)",
                2.0: "2x: Double speed — fast paced combat",
                3.0: "3x: Triple speed — ultra fast simulation",
            }
            desc = font_small.render(speed_desc.get(settings["speed"], ""), True, LIGHT_GREY)
            surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 450)))

        hint = font_small.render(
            "Up/Down navigate  |  Enter/Click activate  |  Left/Right change speed  |  Esc back",
            True, LIGHT_GREY,
        )
        surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, 530)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def statistics_screen(surface, clock, player_id: Optional[int] = None):
    """Show match statistics with two tabs:

    Tab 1 - 'You': Your record per opponent character & difficulty,
                   current and best streaks, last 10 matches.
    Tab 2 - 'AI':  AI character records (W/L/D and win %), split into
                   'vs human' and 'vs AI', plus chronological AI history.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, 20)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    active_tab = 0  # 0 = You, 1 = AI

    tab_you_rect = pygame.Rect(180, 75, 300, 36)
    tab_ai_rect = pygame.Rect(544, 75, 300, 36)

    while True:
        human_records = results_db.get_human_record(player_id)
        last_matches = results_db.get_last_matches(player_id, limit=7)
        ai_records = results_db.get_ai_record()
        ai_history = results_db.get_ai_history(limit=7)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                elif event.key == pygame.K_1:
                    active_tab = 0
                elif event.key == pygame.K_2:
                    active_tab = 1
                elif event.key in (pygame.K_TAB, pygame.K_LEFT, pygame.K_RIGHT):
                    active_tab = 1 - active_tab
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if tab_you_rect.collidepoint(event.pos):
                    active_tab = 0
                elif tab_ai_rect.collidepoint(event.pos):
                    active_tab = 1

        surface.blit(bg_img, (0, 0))

        # Main Scrim Box
        scrim = pygame.Surface((920, 550), pygame.SRCALPHA)
        scrim.fill((12, 14, 25, 230))
        surface.blit(scrim, (52, 25))
        pygame.draw.rect(surface, (70, 85, 125), pygame.Rect(52, 25, 920, 550), width=2, border_radius=12)

        _draw_title(surface, "STATISTICS & RECORDS", font_large, y=35)

        # Tab Buttons
        for idx, (rect, label) in enumerate([(tab_you_rect, "[1] YOU (Human Record)"), (tab_ai_rect, "[2] AI (Model Stats & History)")]):
            is_active = (active_tab == idx)
            bg_col = (45, 65, 110) if is_active else (25, 30, 48)
            border_col = (120, 160, 240) if is_active else (60, 70, 95)
            pygame.draw.rect(surface, bg_col, rect, border_radius=6)
            pygame.draw.rect(surface, border_col, rect, width=2 if is_active else 1, border_radius=6)
            tab_txt = font_medium.render(label, True, WHITE if is_active else LIGHT_GREY)
            surface.blit(tab_txt, tab_txt.get_rect(center=rect.center))

        # Divider
        pygame.draw.line(surface, (50, 60, 90), (75, 122), (SCREEN_WIDTH - 75, 122), 1)

        # Tab Content
        if active_tab == 0:
            # === TAB 1: YOU ===
            sec1 = font_medium.render("Career Record vs Opponents", True, (241, 196, 15))
            surface.blit(sec1, (80, 130))

            # Headers
            headers = [
                ("Opponent", 100),
                ("Difficulty", 240),
                ("Played", 360),
                ("Record (W-L-D)", 480),
                ("Win %", 630),
                ("Cur Streak", 740),
                ("Best Streak", 850),
            ]
            for h_text, h_x in headers:
                h_surf = font_small.render(h_text, True, (160, 175, 200))
                surface.blit(h_surf, (h_x, 155))

            y_pos = 180
            if not human_records:
                empty_msg = font_small.render("No human matches recorded yet. Start a match to build your record!", True, LIGHT_GREY)
                surface.blit(empty_msg, empty_msg.get_rect(center=(SCREEN_WIDTH // 2, 215)))
            else:
                for r in human_records[:4]:
                    opp_color = PRIMARY_PALETTES.get(r["opponent"], {}).get("body", WHITE)
                    w_l_d = f"{r['wins']} - {r['losses']} - {r['draws']}"
                    pct = round((r["wins"] / r["played"]) * 100, 1) if r["played"] > 0 else 0.0

                    surface.blit(font_small.render(r["opponent"], True, opp_color), (100, y_pos))
                    surface.blit(font_small.render(r["difficulty"], True, WHITE), (240, y_pos))
                    surface.blit(font_small.render(str(r["played"]), True, WHITE), (360, y_pos))
                    surface.blit(font_small.render(w_l_d, True, WHITE), (480, y_pos))
                    pct_color = (46, 204, 113) if pct >= 50 else (231, 76, 60)
                    surface.blit(font_small.render(f"{pct:.1f}%", True, pct_color), (630, y_pos))
                    surface.blit(font_small.render(str(r["current_streak"]), True, WHITE), (740, y_pos))
                    surface.blit(font_small.render(str(r["best_streak"]), True, WHITE), (850, y_pos))
                    y_pos += 26

            # Divider
            pygame.draw.line(surface, (50, 60, 90), (75, 295), (SCREEN_WIDTH - 75, 295), 1)

            # Recent Matches
            sec2 = font_medium.render("Recent Match History (Last 7)", True, (241, 196, 15))
            surface.blit(sec2, (80, 305))

            m_headers = [
                ("Date", 90),
                ("Opponent", 220),
                ("Difficulty", 360),
                ("Score", 480),
                ("Result", 600),
                ("Arena", 720),
            ]
            for h_text, h_x in m_headers:
                h_surf = font_small.render(h_text, True, (160, 175, 200))
                surface.blit(h_surf, (h_x, 330))

            m_y = 355
            if not last_matches:
                empty_m = font_small.render("No match history available.", True, LIGHT_GREY)
                surface.blit(empty_m, empty_m.get_rect(center=(SCREEN_WIDTH // 2, 400)))
            else:
                for m in last_matches:
                    dt_short = m["played_at"][:16] if m.get("played_at") else ""
                    opp = m.get("p2_character", "Fighter")
                    diff = m.get("p2_difficulty", "MEDIUM")
                    score = f"{m.get('rounds_p1', 0)} - {m.get('rounds_p2', 0)}"
                    w_side = m.get("winner_side", 0)
                    if w_side == 1:
                        res_str = "WIN"
                        res_col = (46, 204, 113)
                    elif w_side == 2:
                        res_str = "LOSS"
                        res_col = (231, 76, 60)
                    else:
                        res_str = "DRAW"
                        res_col = LIGHT_GREY

                    arena_raw = str(m.get("arena", "Neon Rooftop")).replace("arena_", "").replace(".jpeg", "").replace(".png", "").replace("_", " ").title()

                    surface.blit(font_small.render(dt_short, True, LIGHT_GREY), (90, m_y))
                    surface.blit(font_small.render(opp, True, WHITE), (220, m_y))
                    surface.blit(font_small.render(diff, True, WHITE), (360, m_y))
                    surface.blit(font_small.render(score, True, WHITE), (480, m_y))
                    surface.blit(font_small.render(res_str, True, res_col), (600, m_y))
                    surface.blit(font_small.render(arena_raw[:18], True, LIGHT_GREY), (720, m_y))
                    m_y += 24

        else:
            # === TAB 2: AI ===
            sec1 = font_medium.render("AI Fighter Records by Difficulty", True, (241, 196, 15))
            surface.blit(sec1, (80, 130))

            ai_headers = [
                ("Fighter", 100),
                ("Difficulty", 250),
                ("Opponent Type", 410),
                ("Played", 570),
                ("Record (W-L-D)", 690),
                ("Win %", 840),
            ]
            for h_text, h_x in ai_headers:
                h_surf = font_small.render(h_text, True, (160, 175, 200))
                surface.blit(h_surf, (h_x, 155))

            y_pos = 180
            if not ai_records:
                empty_ai = font_small.render("No AI matches recorded yet.", True, LIGHT_GREY)
                surface.blit(empty_ai, empty_ai.get_rect(center=(SCREEN_WIDTH // 2, 215)))
            else:
                for r in ai_records[:4]:
                    f_col = PRIMARY_PALETTES.get(r["character"], {}).get("body", WHITE)
                    wld = f"{r['wins']} - {r['losses']} - {r['draws']}"
                    surface.blit(font_small.render(r["character"], True, f_col), (100, y_pos))
                    surface.blit(font_small.render(r["difficulty"], True, WHITE), (250, y_pos))
                    surface.blit(font_small.render(r["opponent_type"], True, LIGHT_GREY), (410, y_pos))
                    surface.blit(font_small.render(str(r["played"]), True, WHITE), (570, y_pos))
                    surface.blit(font_small.render(wld, True, WHITE), (690, y_pos))
                    pct = r.get("win_pct", 0.0)
                    pct_col = (46, 204, 113) if pct >= 50 else (231, 76, 60)
                    surface.blit(font_small.render(f"{pct:.1f}%", True, pct_col), (840, y_pos))
                    y_pos += 26

            # Divider
            pygame.draw.line(surface, (50, 60, 90), (75, 295), (SCREEN_WIDTH - 75, 295), 1)

            # Chronological AI Results
            sec2 = font_medium.render("Latest AI Match Results (Chronological)", True, (241, 196, 15))
            surface.blit(sec2, (80, 305))

            h_y = 340
            if not ai_history:
                empty_h = font_small.render("No AI match history recorded yet.", True, LIGHT_GREY)
                surface.blit(empty_h, empty_h.get_rect(center=(SCREEN_WIDTH // 2, 400)))
            else:
                for h in ai_history:
                    line_surf = font_small.render(f"•  {h['summary']}", True, WHITE)
                    surface.blit(line_surf, (95, h_y))
                    h_y += 24

        # Footer Hint
        hint = font_small.render("[1/2] or [Tab] Switch Tab   |   [Esc] Return to Menu", True, (150, 165, 190))
        surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, 545)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


# ------------------------------------------------------------------
# Manual / How to Play
# ------------------------------------------------------------------
def manual_screen(surface, clock):
    """Show the game manual: rules, controls, and special moves.

    Has three pages — use ←/→ or click tabs to switch. Press Esc or click
    'Back' to return to the main menu.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, 24)
    font_small = pygame.font.Font(None, 18)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    scrim.fill((0, 0, 0, 110))

    page = 0   # 0 = How to Play, 1 = Controls, 2 = Special Moves
    pages = ["How to Play", "Controls", "Special Moves"]
    tab_rects = []

    while True:
        # Back button rect (drawn every frame, checked on click)
        back_rect = pygame.Rect(20, SCREEN_HEIGHT - 50, 100, 36)
        tab_w = 170
        tab_gap = 20
        total_tab_w = len(pages) * tab_w + (len(pages) - 1) * tab_gap
        start_tab_x = (SCREEN_WIDTH - total_tab_w) // 2

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
                    # Cycle to next page
                    page = (page + 1) % len(pages)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_rect.collidepoint(event.pos):
                    return
                for i, rect in enumerate(tab_rects):
                    if rect.collidepoint(event.pos):
                        page = i

        surface.blit(bg_img, (0, 0))
        surface.blit(scrim, (0, 0))
        _draw_title(surface, "Manual & Combat Guide", font_large, y=16)

        # --- Page tabs ---
        tab_rects = []
        for i, tab_name in enumerate(pages):
            tx = start_tab_x + i * (tab_w + tab_gap)
            ty = 64
            tab_rect = pygame.Rect(tx, ty, tab_w, 34)
            tab_rects.append(tab_rect)
            bg_col = MENU_HIGHLIGHT if i == page else DARK_GREY
            pygame.draw.rect(surface, bg_col, tab_rect, border_radius=6)
            if i == page:
                pygame.draw.rect(surface, WHITE, tab_rect, 2, border_radius=6)
            col = WHITE if i == page else LIGHT_GREY
            label = font_medium.render(tab_name, True, col)
            surface.blit(label, label.get_rect(center=tab_rect.center))

        # --- Page content ---
        if page == 0:
            _draw_rules_page(surface, font_medium, font_small)
        elif page == 1:
            _draw_controls_page(surface, font_medium, font_small)
        else:
            _draw_specials_page(surface, font_medium, font_small)

        # --- Back button ---
        pygame.draw.rect(surface, DARK_GREY, back_rect, border_radius=5)
        pygame.draw.rect(surface, LIGHT_GREY, back_rect, 2, border_radius=5)
        back_label = font_medium.render("< Back", True, WHITE)
        surface.blit(back_label, back_label.get_rect(center=back_rect.center))

        # Navigation hint
        hint = font_small.render(
            "< / > or click tabs to switch  |  Esc or click Back to return",
            True, LIGHT_GREY
        )
        surface.blit(hint, hint.get_rect(midtop=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 28)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def _draw_manual_card(surface, rect, border_color=(70, 80, 110), bg_color=(18, 22, 34, 215)):
    """Draw a semi-transparent panel with a rounded colored border."""
    panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    panel.fill(bg_color)
    surface.blit(panel, (rect.x, rect.y))
    pygame.draw.rect(surface, border_color, rect, 1, border_radius=6)


def _draw_rules_page(surface, font_medium, font_small):
    """Draw the 'How to Play' rules page covering rules, guard levels, combos, and meters."""
    col_w = 445
    card_bg = (18, 22, 34, 215)

    # --- Left Column: Match Rules & Combat System ---
    c1_x = 50

    # 1. Match & Arena Rules
    r1 = pygame.Rect(c1_x, 110, col_w, 126)
    _draw_manual_card(surface, r1, border_color=(130, 150, 190), bg_color=card_bg)
    surface.blit(font_medium.render("Match & Arena Rules", True, (240, 215, 90)), (c1_x + 14, 118))
    rules_c1 = [
        "• 800px arena with walls (supports hard Wall Bounce juggles).",
        "• Best of 3 rounds, 60 seconds per round.",
        "• Win a round by KO (0 HP) or timeout (highest remaining health).",
        "• Equal health at time-out results in a drawn round.",
    ]
    for idx, line in enumerate(rules_c1):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c1_x + 14, 146 + idx * 21))

    # 2. High / Low Guard & Throws
    r2 = pygame.Rect(c1_x, 246, col_w, 136)
    _draw_manual_card(surface, r2, border_color=(90, 160, 230), bg_color=card_bg)
    surface.blit(font_medium.render("High / Low Guard & Throws", True, (100, 205, 255)), (c1_x + 14, 254))
    guard_lines = [
        "• Standing Block (L): Blocks High & Mid attacks. Vulnerable to Lows!",
        "• Crouching Block (S+L): Blocks Low & Mid attacks. Vulnerable to Highs!",
        "• Throw (J+U): Unblockable grip that breaks turtling defenders.",
        "• Throw Tech: Press Throw within 7 frames of being grabbed to escape.",
    ]
    for idx, line in enumerate(guard_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c1_x + 14, 282 + idx * 21))

    # 3. Combos, Juggle Cap & Cancels
    r3 = pygame.Rect(c1_x, 392, col_w, 136)
    _draw_manual_card(surface, r3, border_color=(230, 130, 90), bg_color=card_bg)
    surface.blit(font_medium.render("Combos & Cancels", True, (255, 145, 95)), (c1_x + 14, 400))
    combo_lines = [
        "• Canned Strings: Character chains (e.g. Jab->Jab->Heavy) advance on hit.",
        "• Cancels: Normal attacks cancel into Specials; Specials cancel into Super.",
        "• Counter-Hit: Striking during opponent startup grants +50% hitstun!",
        "• Juggle Cap: Air juggles max out at 4 hits before victim drops safely.",
    ]
    for idx, line in enumerate(combo_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c1_x + 14, 428 + idx * 21))

    # --- Right Column: Meters, Defense & Resources ---
    c2_x = 525

    # 4. Guard Meter & Guard Break
    r4 = pygame.Rect(c2_x, 110, col_w, 126)
    _draw_manual_card(surface, r4, border_color=(230, 90, 90), bg_color=card_bg)
    surface.blit(font_medium.render("Guard Meter & Guard Break", True, (255, 105, 105)), (c2_x + 14, 118))
    guard_meter_lines = [
        "• Blocking attacks drains Guard Meter. Regenerates when idle.",
        "• At 0 Guard: GUARD BREAK! Stunned for 40 frames and helpless to combos.",
        "• Prevents turtling and rewards continuous offensive pressure.",
        "• Every block generates pushback to naturally reset fighter spacing.",
    ]
    for idx, line in enumerate(guard_meter_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c2_x + 14, 146 + idx * 21))

    # 5. Super Meter & Burst
    r5 = pygame.Rect(c2_x, 246, col_w, 136)
    _draw_manual_card(surface, r5, border_color=(170, 110, 240), bg_color=card_bg)
    surface.blit(font_medium.render("Super Meter (0–100) & Burst", True, (190, 135, 255)), (c2_x + 14, 254))
    super_lines = [
        "• Build meter by landing attacks, absorbing damage, and parrying.",
        "• Enhanced Specials / Shield Bash: Costs 25 meter.",
        "• Burst (L+O): Costs 50 meter in hitstun. Blasts the enemy away!",
        "• Super Move (P): Costs 100 meter with a 15-frame cinematic freeze.",
    ]
    for idx, line in enumerate(super_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c2_x + 14, 282 + idx * 21))

    # 6. Fury Mode & Perfect Parry
    r6 = pygame.Rect(c2_x, 392, col_w, 136)
    _draw_manual_card(surface, r6, border_color=(90, 200, 140), bg_color=card_bg)
    surface.blit(font_medium.render("Fury Mode & Perfect Parry", True, (110, 245, 160)), (c2_x + 14, 400))
    fury_lines = [
        "• FURY (< 25% HP): +10% attack damage; Super cost drops to 60 meter!",
        "• Perfect Parry: Tap Block within 4 frames before an incoming hit.",
        "• Parry Effect: 0 damage taken, staggers attacker for 22f, grants +12m.",
        "• Turns patient defensive reads into high-damage counter opportunities.",
    ]
    for idx, line in enumerate(fury_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c2_x + 14, 428 + idx * 21))


def _draw_controls_page(surface, font_medium, font_small):
    """Draw the 'Controls' page with combat, defensive, special, and shortcut keys."""
    col_w = 445
    card_bg = (18, 22, 34, 215)

    # --- Left Column: Movement & Universal Normals ---
    c1_x = 50

    # 1. Movement Card
    r1 = pygame.Rect(c1_x, 110, col_w, 136)
    _draw_manual_card(surface, r1, border_color=(130, 150, 190), bg_color=card_bg)
    surface.blit(font_medium.render("Movement & Agility", True, (240, 215, 90)), (c1_x + 14, 118))
    moves = [
        ("A / D", "Walk Backward / Forward"),
        ("Double-tap A / D", "Dash / Backdash (4f invulnerability window)"),
        ("W", "Jump (Shadow has Double Jump & Air Dash)"),
        ("S", "Crouch (reduces hurtbox, enables low attacks & low block)"),
    ]
    for idx, (k, desc) in enumerate(moves):
        surface.blit(font_small.render(k, True, WHITE), (c1_x + 14, 146 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c1_x + 140, 146 + idx * 21))

    # 2. Universal Normals Card
    r2 = pygame.Rect(c1_x, 256, col_w, 272)
    _draw_manual_card(surface, r2, border_color=(90, 160, 230), bg_color=card_bg)
    surface.blit(font_medium.render("Normals & Universal Attacks", True, (100, 205, 255)), (c1_x + 14, 264))
    attacks = [
        ("J", "Light Punch / Jab (3f startup, +2 on block, starter)"),
        ("K", "Heavy Punch (10f startup, 8 HP damage, staggers)"),
        ("U", "Light Kick (5f startup, 4 HP damage, mid-range poke)"),
        ("I", "Heavy Kick (12f startup, 10 HP damage, longest reach)"),
        ("S + U / S + I", "Low Sweep (hits LOW, knocks down opponent)"),
        ("S + K", "Anti-Air Uppercut (6f startup, launches jumpers)"),
        ("W + J / W + U", "Jump Punch / Jump Kick (airborne priority)"),
        ("J + U", "Throw (unblockable close grip; tech with J+U in 7f)"),
    ]
    for idx, (k, desc) in enumerate(attacks):
        surface.blit(font_small.render(k, True, WHITE), (c1_x + 14, 292 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c1_x + 120, 292 + idx * 21))

    # --- Right Column: Defense, Specials & Training Shortcuts ---
    c2_x = 525

    # 3. Defense & Specials Card
    r3 = pygame.Rect(c2_x, 110, col_w, 230)
    _draw_manual_card(surface, r3, border_color=(90, 200, 140), bg_color=card_bg)
    surface.blit(font_medium.render("Defense, Specials & Super", True, (110, 245, 160)), (c2_x + 14, 118))
    specials = [
        ("L (hold)", "Standing High Block (blocks High & Mid attacks)"),
        ("S + L (hold)", "Crouching Low Block (blocks Low & Mid attacks)"),
        ("L (tap)", "Perfect Parry (within 4f of hit: 0 dmg, staggers foe)"),
        ("L + O", "Burst (costs 50 meter in hitstun: ends enemy combo)"),
        ("O", "Special Neutral (character signature move 1)"),
        ("D + O / A + O", "Special Forward / Special Back"),
        ("S + O", "Special Down (command grab / ground slam)"),
        ("P", "Super Move (costs 100 meter, or 60 in Fury)"),
    ]
    for idx, (k, desc) in enumerate(specials):
        surface.blit(font_small.render(k, True, WHITE), (c2_x + 14, 146 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c2_x + 120, 146 + idx * 21))

    # 4. Training Mode & Replay Controls Card
    r4 = pygame.Rect(c2_x, 350, col_w, 178)
    _draw_manual_card(surface, r4, border_color=(170, 110, 240), bg_color=card_bg)
    surface.blit(font_medium.render("Training Mode & Replay Controls", True, (190, 135, 255)), (c2_x + 14, 358))
    shortcuts = [
        ("F1", "Toggle Training Mode (Hitboxes, Frame Data & Dummy AI)"),
        ("F2", "Cycle Dummy AI (Stand -> Crouch -> Block All -> Random)"),
        ("F3", "Toggle profiling & performance HUD overlay"),
        ("Esc", "Pause match (open options and Move List screen)"),
        ("Left / Right", "Change match replay speed (0.25x – 4x in AI Viewer)"),
        ("Space", "Pause / resume fight replay"),
    ]
    for idx, (k, desc) in enumerate(shortcuts):
        surface.blit(font_small.render(k, True, WHITE), (c2_x + 14, 386 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c2_x + 110, 386 + idx * 21))


def _draw_specials_page(surface, font_medium, font_small):
    """Draw the 'Special Moves' page detailing each character's unique toolkit without overlaps."""
    fighters_info = [
        {
            "name": "Crimson Brawler",
            "archetype": "Rushdown Berserker",
            "border": (220, 60, 60),
            "accent": (255, 100, 100),
            "moves": [
                ("O", "Crimson Rush", "3-hit advancing dash punch string"),
                ("D+O", "Rising Uppercut", "Anti-air launcher, beats jumps"),
                ("A+O", "Berserker Charge", "Armored dash (takes 50% dmg)"),
                ("S+O", "Clinch Slam", "Close-range command grab"),
                ("P", "Blood Fury (Super)", "8-hit cinematic combo super"),
            ],
            "trait_lines": ["High close-range damage output", "and aggressive cancel pressure."],
        },
        {
            "name": "Steel Guardian",
            "archetype": "Counter & Bulwark",
            "border": (110, 160, 230),
            "accent": (140, 190, 255),
            "moves": [
                ("O", "Iron Wall", "Counter stance; parries & hits"),
                ("D+O", "Shield Bash", "Pushes foe away (costs 25m)"),
                ("A+O", "Reflector", "Reflects projectiles back"),
                ("S+O", "Punisher Grip", "Armored grab; beats blocking"),
                ("P", "Fortress Crush (Super)", "Counter super upon being hit"),
            ],
            "trait_lines": ["Takes 50% less chip damage", "when holding block."],
        },
        {
            "name": "Shadow Striker",
            "archetype": "Agile Hit-and-Run",
            "border": (175, 105, 235),
            "accent": (205, 140, 255),
            "moves": [
                ("O", "Shadow Step", "Teleports behind the opponent"),
                ("D+O", "Phantom Kick", "Low-Mid-Mid deceptive kick"),
                ("A+O", "Feint Strike", "Fake attack into dash / grab"),
                ("S+O", "Energy Dart", "Fast horizontal projectile"),
                ("P", "Vanishing Arts (Super)", "Multi-angle teleport super"),
            ],
            "trait_lines": ["Double Jump (W in air) and", "Air Dash (double-tap A/D in air)."],
        },
        {
            "name": "Golden Tactician",
            "archetype": "Adaptive Stance Master",
            "border": (235, 195, 60),
            "accent": (255, 220, 100),
            "moves": [
                ("O", "Tactician Stance", "Cycles Rush / Guard / Evade"),
                ("D+O", "Gambit Strike", "Advancing tactical thrust"),
                ("A+O", "Golden Read", "Counter read if foe acts in 30f"),
                ("S+O", "Checkmate", "Tactical ground slam finisher"),
                ("P", "Grandmaster (Super)", "Calculated full-screen super"),
            ],
            "trait_lines": ["Tracks enemy attack habits and", "dynamically shifts counters."],
        },
    ]

    col_w = 224
    col_gap = 14
    start_x = 43
    card_bg = (18, 22, 34, 215)

    for i, f_info in enumerate(fighters_info):
        card_x = start_x + i * (col_w + col_gap)
        card_rect = pygame.Rect(card_x, 108, col_w, 428)
        _draw_manual_card(surface, card_rect, border_color=f_info["border"], bg_color=card_bg)

        # Header title & archetype
        title_surf = font_medium.render(f_info["name"], True, f_info["accent"])
        surface.blit(title_surf, (card_x + 10, 118))
        arch_surf = font_small.render(f_info["archetype"], True, LIGHT_GREY)
        surface.blit(arch_surf, (card_x + 10, 142))
        pygame.draw.line(surface, f_info["border"], (card_x + 8, 162), (card_x + col_w - 8, 162), 1)

        # Move list with badge inputs (no text doubling or box overlap)
        cur_y = 172
        for inp, m_name, m_desc in f_info["moves"]:
            badge_w = font_small.size(inp)[0] + 10
            badge_rect = pygame.Rect(card_x + 10, cur_y - 2, badge_w, 18)
            pygame.draw.rect(surface, (45, 55, 75), badge_rect, border_radius=3)
            pygame.draw.rect(surface, (80, 100, 130), badge_rect, 1, border_radius=3)
            inp_surf = font_small.render(inp, True, WHITE)
            surface.blit(inp_surf, inp_surf.get_rect(center=badge_rect.center))

            name_surf = font_small.render(m_name, True, f_info["accent"])
            surface.blit(name_surf, (card_x + 14 + badge_w, cur_y))

            desc_surf = font_small.render(m_desc, True, (170, 180, 200))
            surface.blit(desc_surf, (card_x + 10, cur_y + 19))
            cur_y += 41

        # Passive Trait box (separated clearly at y=380, zero overlap)
        pygame.draw.line(surface, (60, 70, 95), (card_x + 8, 380), (card_x + col_w - 8, 380), 1)
        trait_title = font_small.render("Passive Trait:", True, (240, 215, 90))
        surface.blit(trait_title, (card_x + 10, 390))
        for t_idx, t_line in enumerate(f_info["trait_lines"]):
            t_surf = font_small.render(t_line, True, (210, 220, 240))
            surface.blit(t_surf, (card_x + 10, 410 + t_idx * 18))


# ------------------------------------------------------------------
# Model Insights & Neural League Screen (Phase 6)
# ------------------------------------------------------------------
def model_insights_screen(surface, clock):
    """Display model versions, Elo history, style checks, and live training progress."""
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, 24)
    font_small = pygame.font.Font(None, 18)

    from backend.learning.league import ModelRegistry
    from backend.learning.trainer_proc import training_manager

    registry = ModelRegistry()
    personalities = ["Crimson", "Steel", "Shadow", "Golden"]
    selected_p_idx = 0

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    scrim.fill((0, 0, 0, 110))

    while True:
        training_manager.poll()

        back_rect = pygame.Rect(20, SCREEN_HEIGHT - 50, 100, 36)
        train_btn_rect = pygame.Rect(SCREEN_WIDTH - 220, SCREEN_HEIGHT - 50, 200, 36)
        tab_w = 140
        start_x = (SCREEN_WIDTH - (len(personalities) * tab_w + (len(personalities) - 1) * 16)) // 2

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                elif event.key == pygame.K_LEFT:
                    selected_p_idx = (selected_p_idx - 1) % len(personalities)
                elif event.key == pygame.K_RIGHT:
                    selected_p_idx = (selected_p_idx + 1) % len(personalities)
                elif event.key in (pygame.K_RETURN, pygame.K_t):
                    if not training_manager.is_alive():
                        training_manager.start_training(
                            personality=personalities[selected_p_idx], total_updates=6, quick_mode=True
                        )
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_rect.collidepoint(event.pos):
                    return
                if train_btn_rect.collidepoint(event.pos):
                    if not training_manager.is_alive():
                        training_manager.start_training(
                            personality=personalities[selected_p_idx], total_updates=6, quick_mode=True
                        )
                for i in range(len(personalities)):
                    t_rect = pygame.Rect(start_x + i * (tab_w + 16), 62, tab_w, 32)
                    if t_rect.collidepoint(event.pos):
                        selected_p_idx = i

        surface.blit(bg_img, (0, 0))
        surface.blit(scrim, (0, 0))
        _draw_title(surface, "Model Insights & Neural League", font_large, y=16)

        # Personality selector tabs
        for i, p_name in enumerate(personalities):
            tab_rect = pygame.Rect(start_x + i * (tab_w + 16), 62, tab_w, 32)
            is_sel = (i == selected_p_idx)
            pygame.draw.rect(surface, MENU_HIGHLIGHT if is_sel else DARK_GREY, tab_rect, border_radius=5)
            if is_sel:
                pygame.draw.rect(surface, WHITE, tab_rect, 2, border_radius=5)
            t_col = WHITE if is_sel else LIGHT_GREY
            txt = font_medium.render(p_name, True, t_col)
            surface.blit(txt, txt.get_rect(center=tab_rect.center))

        active_char = personalities[selected_p_idx]
        models = registry.list_models(personality=active_char)

        # Left Panel: Model Registry & Versions
        left_panel = pygame.Rect(45, 108, 450, 360)
        _draw_manual_card(surface, left_panel, border_color=(90, 110, 150))
        surface.blit(font_medium.render(f"Registered Models ({active_char})", True, (240, 215, 90)), (left_panel.x + 14, 118))
        pygame.draw.line(surface, (70, 80, 105), (left_panel.x + 14, 144), (left_panel.x + left_panel.width - 14, 144), 1)

        row_y = 154
        surface.blit(font_small.render("VER", True, (160, 170, 190)), (left_panel.x + 14, row_y))
        surface.blit(font_small.render("STATUS", True, (160, 170, 190)), (left_panel.x + 80, row_y))
        surface.blit(font_small.render("ELO", True, (160, 170, 190)), (left_panel.x + 190, row_y))
        surface.blit(font_small.render("WIN %", True, (160, 170, 190)), (left_panel.x + 270, row_y))
        surface.blit(font_small.render("UPDATED", True, (160, 170, 190)), (left_panel.x + 350, row_y))
        row_y += 24

        if not models:
            surface.blit(
                font_small.render("No trained checkpoints yet. Click 'Train Now' to begin!", True, LIGHT_GREY),
                (left_panel.x + 14, row_y + 40),
            )
        else:
            for m in models[:8]:
                st = m.get("status", "candidate")
                if st == "live":
                    status_color = (100, 255, 120)
                elif st == "promoted":
                    status_color = (100, 200, 255)
                elif st == "archived":
                    status_color = (160, 180, 210)
                else:
                    status_color = (255, 100, 100)
                surface.blit(font_small.render(m.get("version_tag", "v001"), True, WHITE), (left_panel.x + 14, row_y))
                surface.blit(font_small.render(st.upper(), True, status_color), (left_panel.x + 80, row_y))
                surface.blit(font_small.render(f"{m.get('elo', 1000.0):.1f}", True, (240, 220, 100)), (left_panel.x + 190, row_y))
                surface.blit(font_small.render(f"{m.get('win_rate', 0.0)*100:.1f}%", True, WHITE), (left_panel.x + 270, row_y))
                ago_min = max(0, int((time.time() - m.get("timestamp", time.time())) / 60))
                surface.blit(font_small.render(f"{ago_min}m ago", True, LIGHT_GREY), (left_panel.x + 350, row_y))
                row_y += 22

        # Right Panel: Style Constraints & Explanation Preview
        right_panel = pygame.Rect(520, 108, 455, 360)
        _draw_manual_card(surface, right_panel, border_color=(120, 100, 170))
        surface.blit(font_medium.render("Style Check & Neural Explanation", True, (190, 140, 255)), (right_panel.x + 14, 118))
        pygame.draw.line(surface, (70, 80, 105), (right_panel.x + 14, 144), (right_panel.x + right_panel.width - 14, 144), 1)

        # Live model stats
        live_m = registry.get_live_model(active_char)
        s_y = 154
        if live_m:
            surface.blit(font_small.render(f"Live Model: {live_m['version_tag']} (Elo: {live_m['elo']:.1f})", True, (100, 255, 120)), (right_panel.x + 14, s_y))
            s_y += 22
            surface.blit(font_small.render(f"• Aggression Score: {live_m.get('aggression', 0.0):.2f}", True, WHITE), (right_panel.x + 14, s_y))
            s_y += 20
            surface.blit(font_small.render(f"• Defense Rate: {live_m.get('defense', 0.0):.1f} blocks/min", True, WHITE), (right_panel.x + 14, s_y))
            s_y += 20
            surface.blit(font_small.render(f"• Average Spacing: {live_m.get('avg_distance', 0.0):.1f} px", True, WHITE), (right_panel.x + 14, s_y))
        else:
            surface.blit(font_small.render("Live Model: Using Rule-Based FSM / Search fallback", True, (240, 215, 90)), (right_panel.x + 14, s_y))
            s_y += 24
            surface.blit(font_small.render("Style Constraints:", True, LIGHT_GREY), (right_panel.x + 14, s_y))
            s_y += 20
            if active_char == "Crimson":
                surface.blit(font_small.render("• Aggression constraint: > 0.58 forward/attack ratio", True, WHITE), (right_panel.x + 14, s_y))
            elif active_char == "Steel":
                surface.blit(font_small.render("• Defense constraint: > 8.0 blocks/parries per min", True, WHITE), (right_panel.x + 14, s_y))
            elif active_char == "Shadow":
                surface.blit(font_small.render("• Spacing constraint: Spacing > 160 px", True, WHITE), (right_panel.x + 14, s_y))
            else:
                surface.blit(font_small.render("• Adaptive balance: Variety entropy > 1.5", True, WHITE), (right_panel.x + 14, s_y))

        s_y += 30
        pygame.draw.line(surface, (70, 80, 105), (right_panel.x + 14, s_y), (right_panel.x + right_panel.width - 14, s_y), 1)
        s_y += 10
        surface.blit(font_medium.render("Decision Explanation Preview", True, (100, 220, 255)), (right_panel.x + 14, s_y))
        s_y += 24
        surface.blit(font_small.render("Policy Decision: LIGHT PUNCH (Confidence: 68.4%)", True, WHITE), (right_panel.x + 14, s_y))
        s_y += 20
        surface.blit(font_small.render("Opponent Prediction (n-gram): HIGH BLOCK (Prob: 54.1%)", True, (220, 220, 120)), (right_panel.x + 14, s_y))
        s_y += 20
        surface.blit(font_small.render("Decision Latency: 0.38 ms (< 1.0 ms CPU budget)", True, (120, 255, 140)), (right_panel.x + 14, s_y))

        # Bottom Bar: Live Training Progress & Actions
        bottom_box = pygame.Rect(45, 480, SCREEN_WIDTH - 90, 60)
        _draw_manual_card(surface, bottom_box, border_color=(70, 80, 110))

        # Draw progress bar
        p_bar_rect = pygame.Rect(55, 492, SCREEN_WIDTH - 390, 18)
        pygame.draw.rect(surface, (30, 35, 50), p_bar_rect, border_radius=4)
        if training_manager.progress > 0:
            fill_w = int(p_bar_rect.width * min(1.0, training_manager.progress))
            fill_rect = pygame.Rect(55, 492, fill_w, 18)
            pygame.draw.rect(surface, (50, 160, 240), fill_rect, border_radius=4)
        pygame.draw.rect(surface, (70, 90, 130), p_bar_rect, 1, border_radius=4)

        surface.blit(font_small.render(training_manager.last_status, True, WHITE), (55, 516))

        # Train button
        btn_col = (100, 100, 100) if training_manager.is_alive() else (40, 120, 200)
        pygame.draw.rect(surface, btn_col, train_btn_rect, border_radius=5)
        pygame.draw.rect(surface, WHITE, train_btn_rect, 1, border_radius=5)
        btn_text = "Training..." if training_manager.is_alive() else f"Train {active_char} (T)"
        btn_surf = font_medium.render(btn_text, True, WHITE)
        surface.blit(btn_surf, btn_surf.get_rect(center=train_btn_rect.center))

        # Back button
        pygame.draw.rect(surface, DARK_GREY, back_rect, border_radius=5)
        pygame.draw.rect(surface, LIGHT_GREY, back_rect, 2, border_radius=5)
        back_label = font_medium.render("< Back", True, WHITE)
        surface.blit(back_label, back_label.get_rect(center=back_rect.center))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)
