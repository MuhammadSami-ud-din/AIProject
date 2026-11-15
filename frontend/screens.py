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
from frontend.theme import P1_COLOUR, P2_COLOUR, PRIMARY_PALETTES, get_fighter_palette


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
    """Show the game title on intro image, blinking 'PRESS ANY KEY'.

    On keypress/click, cross-fades smoothly over 0.5s into intro_blur.
    """
    font_title = pygame.font.Font(None, 72)
    font_subtitle = pygame.font.Font(None, 28)
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

        # Title with drop shadow in top third
        title_text = "ARENA-AI"
        shadow = font_title.render(title_text, True, BLACK)
        surface.blit(shadow, shadow.get_rect(midtop=(SCREEN_WIDTH // 2 + 3, 63)))
        title = font_title.render(title_text, True, WHITE)
        surface.blit(title, title.get_rect(midtop=(SCREEN_WIDTH // 2, 60)))

        sub = font_subtitle.render("A 2D Fighting Game with AI Fighters", True, LIGHT_GREY)
        surface.blit(sub, sub.get_rect(midtop=(SCREEN_WIDTH // 2, 135)))

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

    while True:
        card_rects = []

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
        inst = font_small.render("← → to browse  |  Enter / Click to confirm  |  Esc to go back",
                                 True, LIGHT_GREY)
        surface.blit(inst, inst.get_rect(midtop=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 32)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def mode_select(surface, clock):
    """Pick match type and difficulty on the blurry intro background."""
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)
    font_small = pygame.font.Font(None, FONT_SIZE_SMALL)

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))

    # Step 1: pick match type
    types = ["Human vs AI", "Human vs Random AI", "AI vs AI"]
    type_keys = ["human_vs_selected", "human_vs_random", "ai_vs_ai"]
    selected = 0

    while True:
        type_rects = []
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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(type_rects):
                    if r.collidepoint(event.pos):
                        match_type = type_keys[i]
                        break
                else:
                    continue
                break
        else:
            surface.blit(bg_img, (0, 0))
            scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            scrim.fill((0, 0, 0, 110))
            surface.blit(scrim, (0, 0))

            _draw_title(surface, "Match Type", font_large, y=60)
            type_rects = _draw_menu_items_clickable(surface, types, selected, font_medium, start_y=180)
            pygame.display.flip()
            clock.tick(30)
            continue
        break

    # Step 2: pick difficulty
    difficulties = ["LOW", "MEDIUM", "HIGH", "HELL"]
    selected = 0

    while True:
        diff_rects = []
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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(diff_rects):
                    if r.collidepoint(event.pos):
                        return match_type, difficulties[i]

        surface.blit(bg_img, (0, 0))
        scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 110))
        surface.blit(scrim, (0, 0))

        _draw_title(surface, "Difficulty", font_large, y=60)
        diff_rects = _draw_menu_items_clickable(surface, difficulties, selected, font_medium, start_y=180)

        # Difficulty description
        descs = {
            "LOW": "Slow reactions (24f delay), 30% mistakes, basic 1-ply search",
            "MEDIUM": "Moderate reactions (15f delay), 15% mistakes, 2-ply search",
            "HIGH": "Fast reactions (7f delay), 5% mistakes, 3-ply search",
            "HELL": "Instant reactions (1f delay), 1% mistakes, Expectimax & Opponent Model on Sky Colosseum!",
        }
        desc = font_small.render(descs[difficulties[selected]], True, (255, 230, 130))
        surface.blit(desc, desc.get_rect(midtop=(SCREEN_WIDTH // 2, 420)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def pause_screen(surface, clock):
    """Show pause overlay with Resume, Restart match, and Quit to menu options.

    Returns: 'resume', 'restart', or 'quit'.
    """
    font_large = pygame.font.Font(None, FONT_SIZE_LARGE)
    font_medium = pygame.font.Font(None, FONT_SIZE_MEDIUM)

    items = ["Resume", "Restart Match", "Quit to Menu"]
    keys = ["resume", "restart", "quit"]
    selected = 0

    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))

    base_frame = surface.copy()

    while True:
        menu_rects = []
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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(menu_rects):
                    if r.collidepoint(event.pos):
                        return keys[i]
            if event.type == pygame.MOUSEMOTION:
                for i, r in enumerate(menu_rects):
                    if r.collidepoint(event.pos):
                        selected = i

        temp = base_frame.copy()
        temp.blit(overlay, (0, 0))
        _draw_title(temp, "PAUSED", font_large, y=140)
        menu_rects = _draw_menu_items_clickable(temp, items, selected, font_medium, start_y=250)

        pygame.display.get_surface().blit(temp, (0, 0))
        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def results_screen(surface, clock, stats_or_result, p1_name=None, p2_name=None,
                   lockout_s=3.0, ai_timeout_s=10.0):
    """Result screen after a deciding round.

    Specification (Addendum B):
    - Title: Human vs AI shows "YOU WIN", "YOU LOSE" or "DRAW".
             AI vs AI shows "<FULL NAME> WINS" or "DRAW".
    - Background: victory.png/jpeg for win, defeat.png/jpeg for loss, victory dimmed for draw.
    - Show: winner portrait, round score (e.g. 2-1), how each round ended (KO, time-up, draw),
            damage dealt, hits landed, blocks, longest combo, match time, difficulty, arena name.
    - Input lockout for first 3 seconds, so held fight keys don't skip it.
      Then: Rematch (R), Character Select (C), Main Menu (Enter/Esc).
    - AI vs AI returns to AI Model Fight menu automatically after 10 seconds.
    - Returns: "rematch", "character_select", or "menu".
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
            "damage_dealt_p1": 100.0 if res == "p1" else 50.0,
            "damage_dealt_p2": 100.0 if res == "p2" else 50.0,
            "hits_landed_p1": 6 if res == "p1" else 3,
            "hits_landed_p2": 6 if res == "p2" else 3,
            "blocks_p1": 2,
            "blocks_p2": 2,
            "longest_combo_p1": 3,
            "longest_combo_p2": 2,
            "rounds_history": [
                {"round_number": 1, "winner_side": 1 if res == "p1" else 2, "ended_by": "KO", "duration_s": 15.0},
                {"round_number": 2, "winner_side": 1 if res == "p1" else 2, "ended_by": "KO", "duration_s": 16.0},
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

    font_title = pygame.font.Font(None, 52)
    font_large = pygame.font.Font(None, 38)
    font_medium = pygame.font.Font(None, 24)
    font_small = pygame.font.Font(None, 20)

    # Determine Title, Title Colour, and Background
    if is_human_match:
        if winner_side == 1:
            bg = assets.get_victory((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "YOU WIN"
            title_colour = (241, 196, 15)  # Gold
        elif winner_side == 2:
            bg = assets.get_defeat((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "YOU LOSE"
            title_colour = (231, 76, 60)   # Crimson red
        else:
            bg = assets.get_draw_screen((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "DRAW"
            title_colour = (189, 195, 199) # Light grey
    else:  # AI vs AI
        if winner_side in (1, 2):
            bg = assets.get_victory((SCREEN_WIDTH, SCREEN_HEIGHT))
            w_char = stats.get("p1_character" if winner_side == 1 else "p2_character", "Golden")
            full_name = PRIMARY_PALETTES.get(w_char, {}).get("title", w_char)
            title_text = f"{full_name.upper()} WINS"
            title_colour = PRIMARY_PALETTES.get(w_char, {}).get("accent", (241, 196, 15))
        else:
            bg = assets.get_draw_screen((SCREEN_WIDTH, SCREEN_HEIGHT))
            title_text = "DRAW"
            title_colour = (189, 195, 199)

    # Winner Portrait
    winner_portrait = None
    if winner_side == 1:
        w_char = stats.get("p1_character", "Golden")
        winner_portrait = assets.get_portrait(w_char, size=(140, 180), flip_h=False)
    elif winner_side == 2:
        w_char = stats.get("p2_character", "Crimson")
        winner_portrait = assets.get_portrait(w_char, size=(140, 180), flip_h=True)

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

    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        locked = (elapsed < lockout_s)

        # AI vs AI auto-return after ai_timeout_s
        if is_ai_vs_ai and elapsed >= ai_timeout_s:
            return "menu"

        # Button Rects
        btn_rematch = pygame.Rect(130, 480, 210, 44)
        btn_char = pygame.Rect(400, 480, 230, 44)
        btn_menu = pygame.Rect(690, 480, 210, 44)
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "menu"

            if not locked:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        return "rematch"
                    elif event.key == pygame.K_c:
                        return "character_select"
                    elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                        return "menu"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if btn_rematch.collidepoint(event.pos):
                        return "rematch"
                    elif btn_char.collidepoint(event.pos):
                        return "character_select"
                    elif btn_menu.collidepoint(event.pos):
                        return "menu"

        # --- Draw scene ---
        surface.blit(bg, (0, 0))

        # Main Scrim Box
        scrim = pygame.Surface((900, 530), pygame.SRCALPHA)
        scrim.fill((12, 14, 25, 230))
        surface.blit(scrim, (62, 35))
        pygame.draw.rect(surface, (70, 85, 125), pygame.Rect(62, 35, 900, 530), width=2, border_radius=12)

        # Title with drop shadow
        shadow = font_title.render(title_text, True, (0, 0, 0))
        surface.blit(shadow, shadow.get_rect(center=(SCREEN_WIDTH // 2 + 2, 67)))
        title_surf = font_title.render(title_text, True, title_colour)
        surface.blit(title_surf, title_surf.get_rect(center=(SCREEN_WIDTH // 2, 65)))

        # Round Score
        score_str = f"ROUNDS:   {stats.get('rounds_p1', 0)}   -   {stats.get('rounds_p2', 0)}"
        score_surf = font_large.render(score_str, True, WHITE)
        surface.blit(score_surf, score_surf.get_rect(center=(SCREEN_WIDTH // 2, 108)))

        # Round End Breakdown
        round_history = stats.get("rounds_history", [])
        if round_history:
            breakdown_items = []
            for r in round_history:
                r_num = r.get("round_number", 1)
                w_side = r.get("winner_side", 0)
                ended = r.get("ended_by", "KO")
                w_tag = "P1" if w_side == 1 else ("P2" if w_side == 2 else "DRAW")
                breakdown_items.append(f"Round {r_num}: {w_tag} ({ended})")
            breakdown_text = "   •   ".join(breakdown_items)
        else:
            breakdown_text = "Final Match Score"
        breakdown_surf = font_small.render(breakdown_text, True, (190, 205, 235))
        surface.blit(breakdown_surf, breakdown_surf.get_rect(center=(SCREEN_WIDTH // 2, 142)))

        # Divider
        pygame.draw.line(surface, (50, 60, 90), (90, 165), (SCREEN_WIDTH - 90, 165), 1)

        # Portrait Box (Left)
        p_box = pygame.Rect(95, 185, 170, 240)
        pygame.draw.rect(surface, (25, 30, 48), p_box, border_radius=8)
        pygame.draw.rect(surface, (60, 75, 110), p_box, width=1, border_radius=8)
        if winner_portrait:
            surface.blit(winner_portrait, (110, 195))
            w_tag = "MATCH WINNER"
            w_surf = font_small.render(w_tag, True, (241, 196, 15))
            surface.blit(w_surf, w_surf.get_rect(center=(p_box.centerx, 398)))
        else:
            d_surf = font_large.render("TIED", True, (180, 180, 180))
            surface.blit(d_surf, d_surf.get_rect(center=p_box.center))

        # Stats Table (Right)
        p1_title = f"{stats.get('p1_name', 'P1')} ({stats.get('p1_character', 'Fighter')})"
        p2_title = f"{stats.get('p2_name', 'P2')} ({stats.get('p2_character', 'Fighter')})"

        # Header Row
        p1_head = font_medium.render(p1_title, True, P1_COLOUR)
        surface.blit(p1_head, p1_head.get_rect(center=(480, 195)))

        vs_surf = font_small.render("VS", True, (130, 140, 165))
        surface.blit(vs_surf, vs_surf.get_rect(center=(610, 195)))

        p2_head = font_medium.render(p2_title, True, P2_COLOUR)
        surface.blit(p2_head, p2_head.get_rect(center=(740, 195)))

        # Stat Rows
        stat_rows = [
            ("Damage Dealt", f"{stats.get('damage_dealt_p1', 0.0):.0f} dmg", f"{stats.get('damage_dealt_p2', 0.0):.0f} dmg"),
            ("Hits Landed", str(stats.get("hits_landed_p1", 0)), str(stats.get("hits_landed_p2", 0))),
            ("Blocks", str(stats.get("blocks_p1", 0)), str(stats.get("blocks_p2", 0))),
            ("Longest Combo", f"{stats.get('longest_combo_p1', 0)} hits", f"{stats.get('longest_combo_p2', 0)} hits"),
        ]

        row_y = 230
        for label, val1, val2 in stat_rows:
            bg_bar = pygame.Rect(300, row_y - 4, 620, 28)
            pygame.draw.rect(surface, (20, 24, 40), bg_bar, border_radius=4)

            lbl_surf = font_small.render(label, True, (170, 180, 200))
            surface.blit(lbl_surf, (315, row_y + 2))

            v1_surf = font_medium.render(val1, True, WHITE)
            surface.blit(v1_surf, v1_surf.get_rect(center=(480, row_y + 10)))

            v2_surf = font_medium.render(val2, True, WHITE)
            surface.blit(v2_surf, v2_surf.get_rect(center=(740, row_y + 10)))

            row_y += 36

        # Match Info Line
        diff_label = stats.get("p2_difficulty", "MEDIUM")
        dur_label = f"{stats.get('duration_s', 0.0):.1f}s"
        info_str = f"Duration: {dur_label}   |   Difficulty: {diff_label}   |   Arena: {arena_clean}"
        info_surf = font_small.render(info_str, True, (150, 165, 190))
        surface.blit(info_surf, info_surf.get_rect(center=(SCREEN_WIDTH // 2, 435)))

        # Divider
        pygame.draw.line(surface, (50, 60, 90), (90, 458), (SCREEN_WIDTH - 90, 458), 1)

        # Bottom Buttons or Lockout
        if locked:
            rem = max(0.0, lockout_s - elapsed)
            lock_box = pygame.Rect(SCREEN_WIDTH // 2 - 170, 480, 340, 44)
            pygame.draw.rect(surface, (35, 38, 55), lock_box, border_radius=8)
            pygame.draw.rect(surface, (80, 90, 120), lock_box, width=1, border_radius=8)
            lock_txt = font_medium.render(f"Input Locked... ({rem:.1f}s)", True, (180, 180, 180))
            surface.blit(lock_txt, lock_txt.get_rect(center=lock_box.center))
        else:
            buttons = [
                (btn_rematch, "[R] Rematch", (46, 125, 50)),
                (btn_char, "[C] Character Select", (33, 97, 140)),
                (btn_menu, "[Esc] Main Menu", (70, 80, 100)),
            ]
            for rect, text, base_col in buttons:
                hover = rect.collidepoint((mx, my))
                col = tuple(min(255, c + 35) for c in base_col) if hover else base_col
                pygame.draw.rect(surface, col, rect, border_radius=8)
                pygame.draw.rect(surface, (200, 220, 255) if hover else (100, 120, 150), rect, width=2 if hover else 1, border_radius=8)
                btn_txt = font_medium.render(text, True, WHITE)
                surface.blit(btn_txt, btn_txt.get_rect(center=rect.center))

            if is_ai_vs_ai:
                auto_rem = max(0, int(round(ai_timeout_s - elapsed)))
                auto_txt = font_small.render(f"Auto-returning to AI menu in {auto_rem}s...", True, (160, 170, 190))
                surface.blit(auto_txt, auto_txt.get_rect(center=(SCREEN_WIDTH // 2, 538)))

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


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

        surface.blit(bg_img, (0, 0))
        scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 110))
        surface.blit(scrim, (0, 0))

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

        if pygame.display.get_surface() is not None:
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

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    scrim.fill((0, 0, 0, 110))

    # Show "calculating..." while running the tournament
    surface.blit(bg_img, (0, 0))
    surface.blit(scrim, (0, 0))
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

        surface.blit(bg_img, (0, 0))
        surface.blit(scrim, (0, 0))
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

        if pygame.display.get_surface() is not None:
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

    bg_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    scrim.fill((0, 0, 0, 110))

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

        surface.blit(bg_img, (0, 0))
        surface.blit(scrim, (0, 0))
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

        if pygame.display.get_surface() is not None:
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
