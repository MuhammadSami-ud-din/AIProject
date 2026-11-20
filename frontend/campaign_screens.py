"""Campaign, Story, Upgrades, Trophies, and Missions screens for Arena-AI.

AAA Dark-Fantasy War-Camp Bounty Board Aesthetic:
- Dimmed colosseum night ambience with torchlight glow and rising embers.
- Molten-gold engraved titles with heraldic crossed swords.
- Top-right economy status pill (gold coin capsule + player level with XP arc).
- Obsidian card panels (#1A1B2E) with bevelled bronze borders (#8C6A3F).
- Segmented molten-gold progress bars and circular metallic emblem badges.
- Pulsing claim buttons with sparkling coin bursts and authentic crimson wax-seal stamps.
- Full keyboard (Arrow keys, TAB, Enter, Space, Esc) and mouse navigation.
"""

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import pygame

from backend.data.campaign import CAMPAIGN_BATTLES, format_story_paragraphs, get_battle
from backend.data.progression import (
    ALL_MISSIONS,
    ALL_TROPHIES,
    MAX_LEVEL,
    get_level_multipliers,
    get_upgrade_cost,
)
from backend.data.results_db import results_db
from frontend.assets import assets
from frontend.audio import audio
from frontend.theme import (
    BLACK,
    DARK_GREY,
    GREY,
    HEALTH_GREEN,
    HEALTH_RED,
    HEALTH_YELLOW,
    LIGHT_GREY,
    MENU_BG,
    MENU_HIGHLIGHT,
    P1_COLOUR,
    P2_COLOUR,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WHITE,
)

# ----------------------------------------------------------------------
# AAA Dark Fantasy Palette Constants & Visual Primitives
# ----------------------------------------------------------------------
from frontend.fantasy_ui import (
    BG_DARK,
    PANEL_DARK,
    PANEL_BORDER,
    PANEL_BORDER_LIGHT,
    GOLD_TEXT,
    GOLD_BRIGHT,
    EMBER_ORANGE,
    SUCCESS_GREEN,
    CRIMSON_TAG,
    SILVER_TAG,
    BRONZE_TAG,
    TEXT_WHITE,
    TEXT_MUTED,
    get_font as _get_font,
    init_embers_if_needed as _init_embers_if_needed,
    draw_dark_fantasy_backdrop as _draw_dark_fantasy_backdrop,
    draw_segmented_bar as _draw_segmented_bar,
    draw_emblem_icon as _draw_emblem_icon,
    draw_wax_seal_stamp as _draw_wax_seal_stamp,
    draw_tier_badge as _draw_tier_badge,
    draw_obsidian_card,
    draw_dark_fantasy_menu_buttons,
    draw_description_pill,
)


# ----------------------------------------------------------------------
# 1. Story Screen (Narrative Typewriter & Opponent Intro)
# ----------------------------------------------------------------------
def story_screen(
    surface: pygame.Surface,
    clock: pygame.time.Clock,
    battle: Dict[str, Any],
    warrior_name: str,
) -> bool:
    """Typewriter narrative screen shown before each campaign battle."""
    audio.play_music("music_menu")
    paragraphs = format_story_paragraphs(battle, warrior_name)
    arena_name = battle.get("arena", "arena_sky_colosseum")
    bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))

    font_title = _get_font(36, bold=True)
    font_sub = _get_font(20)
    font_body = _get_font(22)
    font_quote = _get_font(24, bold=True)
    font_hint = _get_font(18)

    dim_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    dim_overlay.fill((12, 14, 24, 220))

    para_index = 0
    char_index = 0
    typewriter_speed = 2
    frame_counter = 0

    while True:
        clock.tick(60)
        frame_counter += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return True
                elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    cur_p = paragraphs[para_index] if para_index < len(paragraphs) else ""
                    if char_index < len(cur_p):
                        char_index = len(cur_p)
                    else:
                        audio.play_sfx("menu_select")
                        para_index += 1
                        char_index = 0
                        if para_index >= len(paragraphs):
                            return True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                cur_p = paragraphs[para_index] if para_index < len(paragraphs) else ""
                if char_index < len(cur_p):
                    char_index = len(cur_p)
                else:
                    audio.play_sfx("menu_select")
                    para_index += 1
                    char_index = 0
                    if para_index >= len(paragraphs):
                        return True

        surface.blit(bg, (0, 0))
        surface.blit(dim_overlay, (0, 0))

        # Header
        b_num = battle.get("id", 1)
        b_title = battle.get("title", "Battle")
        opp = battle.get("opponent", "Crimson")
        diff = battle.get("difficulty", "LOW")

        t_surf = font_title.render(f"BATTLE {b_num}: {b_title.upper()}", True, GOLD_TEXT)
        surface.blit(t_surf, (SCREEN_WIDTH // 2 - t_surf.get_width() // 2, 40))

        sub_text = f"Warrior: {warrior_name}   vs   Opponent: {opp}   |   Tier: {diff}"
        s_surf = font_sub.render(sub_text, True, TEXT_MUTED)
        surface.blit(s_surf, (SCREEN_WIDTH // 2 - s_surf.get_width() // 2, 85))

        # Obsidian Card
        card_rect = pygame.Rect(90, 130, SCREEN_WIDTH - 180, 330)
        pygame.draw.rect(surface, PANEL_DARK, card_rect, border_radius=12)
        pygame.draw.rect(surface, PANEL_BORDER, card_rect, width=2, border_radius=12)

        # Advance Typewriter
        if para_index < len(paragraphs):
            cur_p = paragraphs[para_index]
            char_index = min(len(cur_p), char_index + typewriter_speed)
            if char_index < len(cur_p) and frame_counter % 6 == 0:
                audio.play_sfx("menu_hover")

        y_cursor = card_rect.y + 30
        for i in range(min(para_index + 1, len(paragraphs))):
            p_text = paragraphs[i]
            if i == para_index:
                p_text = p_text[:char_index]
            words = p_text.split(" ")
            line = ""
            for word in words:
                test_line = f"{line} {word}".strip()
                if font_body.size(test_line)[0] < card_rect.width - 60:
                    line = test_line
                else:
                    surface.blit(font_body.render(line, True, TEXT_WHITE), (card_rect.x + 30, y_cursor))
                    y_cursor += 28
                    line = word
            if line:
                surface.blit(font_body.render(line, True, TEXT_WHITE), (card_rect.x + 30, y_cursor))
                y_cursor += 36

        # Opponent Quote
        if para_index >= len(paragraphs) - 1 and char_index >= len(paragraphs[-1]):
            quote_text = f'"{battle.get("intro_quote", "")}"'
            q_surf = font_quote.render(quote_text, True, (255, 120, 120))
            surface.blit(q_surf, (SCREEN_WIDTH // 2 - q_surf.get_width() // 2, card_rect.bottom - 50))

        # Bottom Hint
        hint_str = "[SPACE / ENTER] Continue   |   [ESC] Skip to Fight"
        h_surf = font_hint.render(hint_str, True, (160, 200, 240))
        surface.blit(h_surf, (SCREEN_WIDTH // 2 - h_surf.get_width() // 2, SCREEN_HEIGHT - 45))

        pygame.display.flip()


# ----------------------------------------------------------------------
# 2. Campaign Map / Tournament Roadmap Screen
# ----------------------------------------------------------------------
def campaign_map_screen(
    surface: pygame.Surface,
    clock: pygame.time.Clock,
    player_id: int,
    warrior_name: str,
) -> Optional[int]:
    """Interactive tournament roadmap displaying the 8 campaign battles."""
    audio.play_music("music_menu")
    font_node = _get_font(22, bold=True)
    font_sub = _get_font(18)
    font_hint = _get_font(18)

    selected_index = 0
    frame_counter = 0

    camp_data = results_db.get_campaign_progress(player_id)
    unlocked_max = camp_data["unlocked_battle"]
    completed = set(camp_data["completed_battles"])
    stars_dict = camp_data["stars"]
    char_lvl = results_db.get_character_level(player_id, warrior_name)

    while True:
        clock.tick(60)
        frame_counter += 1
        mouse_pos = pygame.mouse.get_pos()
        node_rects = []

        # 8 nodes laid out in 2 rows of 4 nodes
        for i in range(8):
            row = i // 4
            col = i % 4
            x = 90 + col * 280
            y = 175 + row * 175
            node_rects.append(pygame.Rect(x, y, 260, 140))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return None
                elif event.key == pygame.K_u:
                    audio.play_sfx("menu_select")
                    upgrade_screen(surface, clock, player_id, warrior_name)
                    camp_data = results_db.get_campaign_progress(player_id)
                    unlocked_max = camp_data["unlocked_battle"]
                    completed = set(camp_data["completed_battles"])
                    char_lvl = results_db.get_character_level(player_id, warrior_name)
                elif event.key == pygame.K_RIGHT:
                    audio.play_sfx("menu_hover")
                    selected_index = (selected_index + 1) % 8
                elif event.key == pygame.K_LEFT:
                    audio.play_sfx("menu_hover")
                    selected_index = (selected_index - 1) % 8
                elif event.key == pygame.K_DOWN:
                    audio.play_sfx("menu_hover")
                    selected_index = min(7, selected_index + 4)
                elif event.key == pygame.K_UP:
                    audio.play_sfx("menu_hover")
                    selected_index = max(0, selected_index - 4)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    b_id = selected_index + 1
                    if b_id <= unlocked_max:
                        audio.play_sfx("menu_select")
                        return b_id
                    else:
                        audio.play_sfx("menu_error")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for idx, r in enumerate(node_rects):
                    if r.collidepoint(mouse_pos):
                        b_id = idx + 1
                        if b_id <= unlocked_max:
                            audio.play_sfx("menu_select")
                            return b_id
                        else:
                            audio.play_sfx("menu_error")

        _draw_dark_fantasy_backdrop(
            surface, frame_counter, "SOVEREIGN TOURNAMENT CAMPAIGN", player_id,
            sub_title=f"Champion: {warrior_name} (Lv {char_lvl})   |   Conquered: {len(completed)} / 8 Battles"
        )

        # Connecting Bronze Chains/Lines
        for i in range(7):
            r1 = node_rects[i]
            r2 = node_rects[i + 1]
            line_col = GOLD_TEXT if (i + 2) <= unlocked_max else (50, 55, 75)
            pygame.draw.line(surface, line_col, r1.center, r2.center, 3)

        # Nodes
        for i, r in enumerate(node_rects):
            b_id = i + 1
            battle = CAMPAIGN_BATTLES[i]
            is_unlocked = (b_id <= unlocked_max)
            is_comp = (b_id in completed)
            is_hover = r.collidepoint(mouse_pos) or (selected_index == i)

            # Node card styling
            if not is_unlocked:
                bg_col = (18, 19, 30)
                border_col = (45, 48, 65)
            elif is_hover:
                bg_col = (35, 38, 65)
                border_col = GOLD_TEXT
            elif is_comp:
                bg_col = (24, 38, 32)
                border_col = SUCCESS_GREEN
            else:
                bg_col = PANEL_DARK
                border_col = PANEL_BORDER

            pygame.draw.rect(surface, bg_col, r, border_radius=10)
            pygame.draw.rect(surface, border_col, r, width=2 if not is_hover else 3, border_radius=10)

            if is_unlocked:
                b_num_surf = font_node.render(f"BATTLE {b_id}", True, GOLD_TEXT if is_hover else WHITE)
                opp_surf = font_sub.render(f"vs {battle['opponent']}", True, TEXT_WHITE)
                surface.blit(b_num_surf, (r.x + 16, r.y + 14))
                surface.blit(opp_surf, (r.x + 16, r.y + 44))

                # Tier badge top-right
                _draw_tier_badge(surface, r.right - 80, r.y + 14, battle["difficulty"])

                if is_comp:
                    stars_count = stars_dict.get(str(b_id), 3)
                    star_str = "★" * stars_count + "☆" * (3 - stars_count)
                    star_surf = font_node.render(star_str, True, (255, 220, 50))
                    surface.blit(star_surf, (r.x + 16, r.bottom - 36))
                else:
                    ready_badge = font_sub.render("READY", True, SUCCESS_GREEN)
                    surface.blit(ready_badge, (r.x + 16, r.bottom - 34))
            else:
                _draw_emblem_icon(surface, r.centerx, r.centery - 10, "lock", is_active=False)
                lock_text = font_sub.render("LOCKED", True, (90, 95, 115))
                surface.blit(lock_text, (r.centerx - lock_text.get_width() // 2, r.bottom - 35))

        # Bottom Helper Bar
        h_text = "ARROW KEYS / CLICK: Select Battle   |   [ENTER]: Fight   |   [U]: Upgrades   |   [ESC]: Back"
        h_surf = font_hint.render(h_text, True, (160, 200, 240))
        surface.blit(h_surf, (SCREEN_WIDTH // 2 - h_surf.get_width() // 2, SCREEN_HEIGHT - 38))

        pygame.display.flip()


# ----------------------------------------------------------------------
# 3. Upgrade Screen (Warrior Enhancement Station)
# ----------------------------------------------------------------------
def upgrade_screen(
    surface: pygame.Surface,
    clock: pygame.time.Clock,
    player_id: int,
    warrior_name: str,
) -> None:
    """Character stat enhancement screen with side-by-side comparison previews."""
    audio.play_sfx("menu_select")
    font_large = _get_font(32, bold=True)
    font_sub = _get_font(22)
    font_stat = _get_font(20, bold=True)
    font_val = _get_font(20)
    font_hint = _get_font(18)

    characters = ["Crimson", "Steel", "Shadow", "Golden"]
    current_char_idx = characters.index(warrior_name) if warrior_name in characters else 0
    frame_counter = 0

    while True:
        clock.tick(60)
        frame_counter += 1
        char = characters[current_char_idx]
        current_lvl = results_db.get_character_level(player_id, char)
        prog = results_db.get_or_create_progress(player_id)
        coins = prog.get("coins", 0)
        upgrade_cost = get_upgrade_cost(current_lvl)
        can_afford = (coins >= upgrade_cost and current_lvl < MAX_LEVEL)

        cur_mults = get_level_multipliers(current_lvl)
        next_mults = get_level_multipliers(min(MAX_LEVEL, current_lvl + 1))

        mouse_pos = pygame.mouse.get_pos()
        buy_btn_rect = pygame.Rect(SCREEN_WIDTH // 2 - 130, 485, 260, 52)
        is_buy_hover = buy_btn_rect.collidepoint(mouse_pos)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return
                elif event.key == pygame.K_LEFT:
                    audio.play_sfx("menu_hover")
                    current_char_idx = (current_char_idx - 1) % len(characters)
                elif event.key == pygame.K_RIGHT:
                    audio.play_sfx("menu_hover")
                    current_char_idx = (current_char_idx + 1) % len(characters)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if can_afford:
                        if results_db.spend_coins(player_id, upgrade_cost):
                            results_db.set_character_level(player_id, char, current_lvl + 1)
                            audio.play_sfx("level_up")
                    else:
                        audio.play_sfx("menu_error")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if is_buy_hover:
                    if can_afford:
                        if results_db.spend_coins(player_id, upgrade_cost):
                            results_db.set_character_level(player_id, char, current_lvl + 1)
                            audio.play_sfx("level_up")
                    else:
                        audio.play_sfx("menu_error")

        _draw_dark_fantasy_backdrop(
            surface, frame_counter, "WARRIOR UPGRADES & ENHANCEMENTS", player_id,
            sub_title="Empower combat attributes with earned tournament gold"
        )

        # Character Selector Carousel
        bar_text = f"<   {char.upper()} (LEVEL {current_lvl}/{MAX_LEVEL})   >"
        b_surf = font_large.render(bar_text, True, GOLD_TEXT)
        surface.blit(b_surf, (SCREEN_WIDTH // 2 - b_surf.get_width() // 2, 95))

        # Comparison Card Panel
        card_rect = pygame.Rect(SCREEN_WIDTH // 2 - 320, 150, 640, 310)
        pygame.draw.rect(surface, PANEL_DARK, card_rect, border_radius=12)
        pygame.draw.rect(surface, PANEL_BORDER, card_rect, width=2, border_radius=12)

        # Headers
        h1 = font_stat.render("Attribute", True, TEXT_MUTED)
        h2 = font_stat.render("Current", True, TEXT_MUTED)
        h3 = font_stat.render("Next Level", True, (120, 240, 140))
        surface.blit(h1, (card_rect.x + 35, card_rect.y + 18))
        surface.blit(h2, (card_rect.x + 280, card_rect.y + 18))
        surface.blit(h3, (card_rect.x + 440, card_rect.y + 18))
        pygame.draw.line(surface, (45, 48, 70), (card_rect.x + 25, card_rect.y + 48), (card_rect.right - 25, card_rect.y + 48), 1)

        stat_rows = [
            ("Max Health Pool", f"x{cur_mults['health_mult']:.2f}", f"x{next_mults['health_mult']:.2f} (+5%)", "shield"),
            ("Attack Damage", f"x{cur_mults['damage_mult']:.2f}", f"x{next_mults['damage_mult']:.2f} (+3%)", "swords"),
            ("Movement Speed", f"x{cur_mults['speed_mult']:.2f}", f"x{next_mults['speed_mult']:.2f} (+1%)", "lightning"),
            ("Guard Defense", f"x{cur_mults['block_mult']:.2f}", f"x{next_mults['block_mult']:.2f} (+2%)", "chain"),
        ]

        y_pos = card_rect.y + 65
        for name, cur_val, nxt_val, icon_key in stat_rows:
            _draw_emblem_icon(surface, card_rect.x + 35, y_pos + 18, icon_key, is_active=True, radius=18)
            n_surf = font_stat.render(name, True, TEXT_WHITE)
            cur_surf = font_val.render(cur_val, True, (210, 215, 230))
            nxt_surf = font_val.render(nxt_val if current_lvl < MAX_LEVEL else "MAX", True, (120, 240, 140) if current_lvl < MAX_LEVEL else GOLD_TEXT)

            surface.blit(n_surf, (card_rect.x + 65, y_pos + 8))
            surface.blit(cur_surf, (card_rect.x + 280, y_pos + 8))
            surface.blit(nxt_surf, (card_rect.x + 440, y_pos + 8))

            # Segmented Stat Bar
            bar_r = pygame.Rect(card_rect.x + 65, y_pos + 32, 200, 10)
            _draw_segmented_bar(surface, bar_r, current_lvl, MAX_LEVEL, GOLD_TEXT, segments=10)

            y_pos += 58

        # Purchase Button
        btn_bg = (40, 130, 60) if can_afford else (30, 32, 45)
        if is_buy_hover and can_afford:
            btn_bg = (55, 175, 80)
        pygame.draw.rect(surface, btn_bg, buy_btn_rect, border_radius=10)
        pygame.draw.rect(surface, (100, 240, 140) if can_afford else (60, 65, 85), buy_btn_rect, width=2, border_radius=10)

        btn_str = "MAX LEVEL REACHED" if current_lvl >= MAX_LEVEL else f"UPGRADE ({upgrade_cost:,} G)"
        b_label = font_sub.render(btn_str, True, WHITE if can_afford else GREY)
        surface.blit(b_label, b_label.get_rect(center=buy_btn_rect.center))

        h_surf = font_hint.render("LEFT/RIGHT: Switch Warrior   |   ENTER or CLICK: Upgrade   |   ESC: Back", True, (160, 200, 240))
        surface.blit(h_surf, (SCREEN_WIDTH // 2 - h_surf.get_width() // 2, SCREEN_HEIGHT - 35))

        pygame.display.flip()


# ----------------------------------------------------------------------
# 4. Trophy Room Screen (Achievements Showcase)
# ----------------------------------------------------------------------
def trophy_room_screen(surface: pygame.Surface, clock: pygame.time.Clock, player_id: int) -> None:
    """Trophy showcase displaying all 18 trophies with locked/unlocked states."""
    audio.play_sfx("menu_select")
    font_name = _get_font(18, bold=True)
    font_desc = _get_font(15)
    font_hint = _get_font(18)
    font_prog = _get_font(20, bold=True)

    scroll_y = 0
    max_scroll = 180
    frame_counter = 0

    while True:
        clock.tick(60)
        frame_counter += 1
        unlocked_ids = results_db.get_unlocked_trophy_ids(player_id)
        total_trophies = len(ALL_TROPHIES)
        unlocked_count = len(unlocked_ids)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return
                elif event.key == pygame.K_DOWN:
                    scroll_y = min(max_scroll, scroll_y + 40)
                elif event.key == pygame.K_UP:
                    scroll_y = max(0, scroll_y - 40)
            elif event.type == pygame.MOUSEWHEEL:
                scroll_y = max(0, min(max_scroll, scroll_y - event.y * 30))

        _draw_dark_fantasy_backdrop(
            surface, frame_counter, "TROPHY ROOM & ACCOLADES", player_id,
            sub_title=f"Achievements Unlocked: {unlocked_count} / {total_trophies} ({int(unlocked_count / total_trophies * 100)}%)"
        )

        # Molten Gold Global Progress Bar
        bar_w = 460
        bar_rect = pygame.Rect(SCREEN_WIDTH // 2 - bar_w // 2, 95, bar_w, 14)
        _draw_segmented_bar(surface, bar_rect, unlocked_count, total_trophies, GOLD_TEXT, segments=18)

        # 3 columns x 6 rows of Trophy Cards
        start_y = 135 - scroll_y
        for i, trophy in enumerate(ALL_TROPHIES):
            col = i % 3
            row = i // 3
            x = 80 + col * 380
            y = start_y + row * 92
            if y < 110 or y > SCREEN_HEIGHT - 60:
                continue

            card_rect = pygame.Rect(x, y, 360, 80)
            is_unlocked = (trophy["id"] in unlocked_ids)

            bg_col = PANEL_DARK if is_unlocked else (18, 19, 30)
            border_col = PANEL_BORDER if is_unlocked else (45, 48, 65)

            pygame.draw.rect(surface, bg_col, card_rect, border_radius=10)
            pygame.draw.rect(surface, border_col, card_rect, width=2 if is_unlocked else 1, border_radius=10)

            # Emblem Badge
            icon_type = "swords" if is_unlocked else "lock"
            _draw_emblem_icon(surface, card_rect.x + 36, card_rect.centery, icon_type, is_active=is_unlocked, radius=22)

            # Trophy Title & Description
            t_col = GOLD_BRIGHT if is_unlocked else (110, 115, 130)
            d_col = TEXT_MUTED if is_unlocked else (80, 85, 100)

            t_name = font_name.render(trophy["name"], True, t_col)
            t_desc = font_desc.render(trophy["desc"], True, d_col)
            surface.blit(t_name, (card_rect.x + 72, card_rect.y + 16))
            surface.blit(t_desc, (card_rect.x + 72, card_rect.y + 44))

            # Tier status
            tier_lbl = "UNLOCKED" if is_unlocked else "LOCKED"
            _draw_tier_badge(surface, card_rect.right - 90, card_rect.y + 14, tier_lbl)

        h_surf = font_hint.render("UP / DOWN / SCROLL: Browse Achievements   |   ESC: Return to Main Menu", True, (160, 200, 240))
        surface.blit(h_surf, (SCREEN_WIDTH // 2 - h_surf.get_width() // 2, SCREEN_HEIGHT - 30))

        pygame.display.flip()


# ----------------------------------------------------------------------
# 5. Missions Screen (War-Camp Bounty Board)
# ----------------------------------------------------------------------
def missions_screen(surface: pygame.Surface, clock: pygame.time.Clock, player_id: int) -> None:
    """Full AAA war-camp bounty board styled Missions & Contracts screen."""
    audio.play_sfx("menu_select")
    font_tab = _get_font(22, bold=True)
    font_name = _get_font(21, bold=True)
    font_desc = _get_font(16)
    font_btn = _get_font(18, bold=True)
    font_hint = _get_font(18)
    font_prog = _get_font(17, bold=True)

    tabs = ["BATTLE OBJECTIVES", "GLOBAL CONTRACTS", "COMPLETED"]
    active_tab_idx = 0
    frame_counter = 0

    # Sparkle coin particles for claimable cards
    burst_particles = []

    while True:
        clock.tick(60)
        frame_counter += 1

        user_missions = {m["mission_id"]: m for m in results_db.get_missions(player_id)}
        prog = results_db.get_or_create_progress(player_id)
        coins = prog.get("coins", 0)

        mouse_pos = pygame.mouse.get_pos()
        claim_buttons = []
        all_ready_missions = []

        # Tally claimable missions across the board
        for m_def in ALL_MISSIONS:
            m_data = user_missions.get(m_def["id"], {"progress": 0, "completed": 0, "claimed": 0})
            if m_data.get("completed", 0) and not m_data.get("claimed", 0):
                all_ready_missions.append((m_def["id"], m_def["reward"]))

        # Tab button rectangles
        tab_rects = []
        tab_start_x = 75
        for i, t_name in enumerate(tabs):
            tw = font_tab.size(t_name)[0] + 30
            tab_rects.append(pygame.Rect(tab_start_x, 90, tw, 36))
            tab_start_x += tw + 15

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return
                elif event.key == pygame.K_TAB:
                    audio.play_sfx("menu_hover")
                    active_tab_idx = (active_tab_idx + 1) % len(tabs)
                elif event.key == pygame.K_LEFT:
                    audio.play_sfx("menu_hover")
                    active_tab_idx = (active_tab_idx - 1) % len(tabs)
                elif event.key == pygame.K_RIGHT:
                    audio.play_sfx("menu_hover")
                    active_tab_idx = (active_tab_idx + 1) % len(tabs)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # Enter triggers Claim All or individual claim
                    if all_ready_missions:
                        claimed_count = 0
                        for m_id, r_coins in all_ready_missions:
                            if results_db.claim_mission(player_id, m_id):
                                results_db.add_coins(player_id, r_coins)
                                claimed_count += 1
                        if claimed_count > 0:
                            audio.play_sfx("coin")
                            audio.play_sfx("mission_complete")
                    else:
                        audio.play_sfx("menu_error")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Tab clicks
                for idx, tr in enumerate(tab_rects):
                    if tr.collidepoint(mouse_pos) and active_tab_idx != idx:
                        active_tab_idx = idx
                        audio.play_sfx("menu_hover")

                # Claim single mission button
                for btn_rect, m_id, r_coins in claim_buttons:
                    if btn_rect.collidepoint(mouse_pos):
                        if results_db.claim_mission(player_id, m_id):
                            results_db.add_coins(player_id, r_coins)
                            audio.play_sfx("coin")
                            audio.play_sfx("mission_complete")

                # Claim All button
                claim_all_rect = pygame.Rect(SCREEN_WIDTH - 210, SCREEN_HEIGHT - 48, 145, 36)
                if claim_all_rect.collidepoint(mouse_pos) and all_ready_missions:
                    for m_id, r_coins in all_ready_missions:
                        if results_db.claim_mission(player_id, m_id):
                            results_db.add_coins(player_id, r_coins)
                    audio.play_sfx("coin")
                    audio.play_sfx("mission_complete")

        # 1. Background & Atmospheric Frame
        _draw_dark_fantasy_backdrop(
            surface, frame_counter, "MISSIONS & CONTRACTS", player_id
        )

        # 2. Tabs Bar
        for idx, tr in enumerate(tab_rects):
            is_active = (idx == active_tab_idx)
            t_col = GOLD_BRIGHT if is_active else TEXT_MUTED
            t_surf = font_tab.render(tabs[idx], True, t_col)
            surface.blit(t_surf, t_surf.get_rect(center=tr.center))
            if is_active:
                # Molten gold underline glow
                line_y = tr.bottom - 2
                pygame.draw.line(surface, GOLD_TEXT, (tr.x + 8, line_y), (tr.right - 8, line_y), 3)
                pygame.draw.line(surface, GOLD_BRIGHT, (tr.x + 12, line_y - 1), (tr.right - 12, line_y - 1), 1)

        # Far right refresh countdown
        ref_text = "Refreshes in 06:42:11"
        r_surf = font_desc.render(ref_text, True, TEXT_MUTED)
        rx = SCREEN_WIDTH - 85 - r_surf.get_width()
        surface.blit(r_surf, (rx, 98))
        # Small hourglass icon
        pygame.draw.polygon(surface, GOLD_TEXT, [(rx - 16, 98), (rx - 6, 98), (rx - 16, 114), (rx - 6, 114)], 1)

        # Filter missions based on active tab
        if active_tab_idx == 0:
            # Battle Objectives
            missions_to_display = [m for m in ALL_MISSIONS if m["type"] == "battle"]
            # Fill with extra global missions to make a rich 8-card grid
            missions_to_display += [m for m in ALL_MISSIONS if m["type"] == "global"]
        elif active_tab_idx == 1:
            # Global Contracts
            missions_to_display = [m for m in ALL_MISSIONS if m["type"] == "global"]
            missions_to_display += [m for m in ALL_MISSIONS if m["type"] == "battle"]
        else:
            # Completed & Claimed
            missions_to_display = ALL_MISSIONS

        # 3. Main 8-Card Grid (2 columns x 4 rows)
        card_w, card_h = 550, 94
        start_y = 145

        # Icon mapping
        ICON_MAP = {
            "win_3_matches": "swords",
            "block_30_attacks": "shield",
            "land_15_specials": "flame",
            "reach_level_5": "arrow",
            "flawless_round_obj": "crystal",
            "combo_5_obj": "chain",
            "no_block_win": "broken_shield",
            "speed_win_obj": "lightning",
        }
        TIER_MAP = {
            "win_3_matches": "Bronze I",
            "block_30_attacks": "Gold III",
            "land_15_specials": "Silver II",
            "reach_level_5": "Silver II",
            "flawless_round_obj": "Gold III",
            "combo_5_obj": "Silver II",
            "no_block_win": "Bronze I",
            "speed_win_obj": "Bronze I",
        }

        for i, m_def in enumerate(missions_to_display[:8]):
            col = i % 2
            row = i // 2
            cx = 75 + col * 580
            cy = start_y + row * 106
            card_rect = pygame.Rect(cx, cy, card_w, card_h)

            m_data = user_missions.get(m_def["id"], {"progress": 0, "completed": 0, "claimed": 0})
            curr_prog = min(m_def["target"], m_data.get("progress", 0))
            is_comp = bool(m_data.get("completed", 0))
            is_claimed = bool(m_data.get("claimed", 0))

            # 8th card demonstration: Locked Contract card if uncompleted
            is_locked_slot = (i == 7 and not is_comp and not is_claimed and active_tab_idx == 0)

            # Card panel styling
            if is_claimed:
                card_bg = (18, 19, 28)
                card_border = (60, 65, 80)
            elif is_comp:
                # Pulsing golden claim glow
                pulse = int(math.sin(frame_counter * 0.12) * 25)
                card_bg = (32 + pulse // 4, 30 + pulse // 5, 48 + pulse // 3)
                card_border = (min(255, 245 + pulse), min(255, 197 + pulse), 66)
            else:
                card_bg = PANEL_DARK
                card_border = PANEL_BORDER

            pygame.draw.rect(surface, card_bg, card_rect, border_radius=10)
            border_w = 3 if is_comp and not is_claimed else 2
            pygame.draw.rect(surface, card_border, card_rect, width=border_w, border_radius=10)

            if is_locked_slot:
                # Locked Contract Card
                _draw_emblem_icon(surface, card_rect.x + 48, card_rect.centery, "lock", is_active=False)
                l_title = font_name.render("Locked Contract", True, (130, 135, 150))
                l_desc = font_desc.render("Next tier unlocks after Victory Road", True, (90, 95, 110))
                surface.blit(l_title, (card_rect.x + 90, card_rect.y + 22))
                surface.blit(l_desc, (card_rect.x + 90, card_rect.y + 50))
                continue

            # Circular Emblem Icon
            icon_name = ICON_MAP.get(m_def["id"], "swords")
            _draw_emblem_icon(surface, card_rect.x + 48, card_rect.centery, icon_name, is_active=(not is_claimed))

            # Title & Crimson BATTLE tag
            title_col = TEXT_WHITE if not is_claimed else (120, 125, 140)
            t_surf = font_name.render(m_def["name"], True, title_col)
            surface.blit(t_surf, (card_rect.x + 90, card_rect.y + 12))

            tag_offset_x = card_rect.x + 90 + t_surf.get_width() + 8
            if m_def["type"] == "battle":
                _draw_tier_badge(surface, tag_offset_x, card_rect.y + 12, "BATTLE")
                tag_offset_x += 65

            # Tier Badge Top-Right
            tier_name = TIER_MAP.get(m_def["id"], "Bronze I")
            _draw_tier_badge(surface, card_rect.right - 85, card_rect.y + 12, tier_name)

            # Description
            d_col = TEXT_MUTED if not is_claimed else (90, 95, 110)
            d_surf = font_desc.render(m_def["desc"], True, d_col)
            surface.blit(d_surf, (card_rect.x + 90, card_rect.y + 38))

            # Segmented Progress Bar & Counter
            prog_rect = pygame.Rect(card_rect.x + 90, card_rect.y + 64, 210, 12)
            _draw_segmented_bar(surface, prog_rect, curr_prog, m_def["target"], GOLD_TEXT, segments=8)

            p_str = f"{curr_prog} / {m_def['target']}"
            p_col = SUCCESS_GREEN if is_comp else (210, 215, 230)
            p_surf = font_prog.render(p_str, True, p_col)
            surface.blit(p_surf, (prog_rect.right + 10, prog_rect.y - 2))

            # Right Side: Claim Button, Wax Seal Stamp, or Reward Chip
            if is_claimed:
                # Angled crimson wax-seal stamp
                _draw_wax_seal_stamp(surface, card_rect.right - 75, card_rect.centery)
            elif is_comp:
                # Pulsing Claim Button with Coin Particles
                btn_w, btn_h = 95, 34
                btn_rect = pygame.Rect(card_rect.right - 110, card_rect.centery - 17, btn_w, btn_h)
                is_btn_hover = btn_rect.collidepoint(mouse_pos)

                btn_bg = GOLD_TEXT if not is_btn_hover else GOLD_BRIGHT
                pygame.draw.rect(surface, btn_bg, btn_rect, border_radius=6)
                pygame.draw.rect(surface, (255, 245, 180), btn_rect, width=2, border_radius=6)

                btn_lbl = font_btn.render("CLAIM", True, (20, 22, 34))
                surface.blit(btn_lbl, btn_lbl.get_rect(center=btn_rect.center))
                claim_buttons.append((btn_rect, m_def["id"], m_def["reward"]))

                # Sparkling coin particles
                for _ in range(2):
                    px = btn_rect.x + random.randint(-8, btn_rect.width + 8)
                    py = btn_rect.y + random.randint(-6, btn_rect.height + 6)
                    pygame.draw.circle(surface, (255, 235, 140), (px, py), random.choice([1, 2]))
            else:
                # Reward Chip: Gold coin circle + +150
                r_surf = font_btn.render(f"+{m_def['reward']}", True, GOLD_TEXT)
                rc_rect = pygame.Rect(card_rect.right - 105, card_rect.y + 58, 90, 24)
                pygame.draw.rect(surface, (20, 22, 34), rc_rect, border_radius=12)
                pygame.draw.rect(surface, PANEL_BORDER, rc_rect, width=1, border_radius=12)

                # Small coin
                pygame.draw.circle(surface, (245, 197, 66), (rc_rect.x + 14, rc_rect.centery), 6)
                surface.blit(r_surf, (rc_rect.x + 26, rc_rect.centery - r_surf.get_height() // 2))

        # 4. Bottom Controls Bar
        h_text = "[ESC] Back   |   [ENTER] Claim   |   [TAB] Switch Tab"
        h_surf = font_hint.render(h_text, True, (160, 200, 240))
        surface.blit(h_surf, (80, SCREEN_HEIGHT - 40))

        # Prominent Gold [CLAIM ALL (X)] Button
        ready_count = len(all_ready_missions)
        claim_all_rect = pygame.Rect(SCREEN_WIDTH - 210, SCREEN_HEIGHT - 48, 145, 36)
        is_all_hover = claim_all_rect.collidepoint(mouse_pos)

        ca_bg = GOLD_TEXT if (ready_count > 0 and not is_all_hover) else (GOLD_BRIGHT if ready_count > 0 else (45, 48, 65))
        pygame.draw.rect(surface, ca_bg, claim_all_rect, border_radius=8)
        pygame.draw.rect(surface, (255, 245, 180) if ready_count > 0 else (65, 70, 90), claim_all_rect, width=2, border_radius=8)

        ca_str = f"CLAIM ALL ({ready_count})" if ready_count > 0 else "CLAIM ALL (0)"
        ca_col = (20, 22, 34) if ready_count > 0 else (120, 125, 140)
        ca_lbl = font_btn.render(ca_str, True, ca_col)
        surface.blit(ca_lbl, ca_lbl.get_rect(center=claim_all_rect.center))

        pygame.display.flip()
