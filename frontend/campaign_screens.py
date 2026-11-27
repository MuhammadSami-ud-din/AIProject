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

from backend.data.campaign import (
    CAMPAIGN_BATTLES,
    format_story_paragraphs,
    get_battle,
    get_battle_dialogue,
)
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
from frontend.draw_fighter import get_fighter_sprite_seamless
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
    draw_hint_bar,
    draw_button,
)


def _draw_star(surface: pygame.Surface, cx: int, cy: int, r: int, filled: bool = True) -> None:
    """Five-point vector star (fonts may lack the ★ glyph)."""
    pts = []
    for k in range(10):
        ang = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    if filled:
        pygame.draw.polygon(surface, (255, 215, 60), pts)
    pygame.draw.polygon(surface, (255, 235, 150) if filled else (95, 100, 120), pts, 1)


# ----------------------------------------------------------------------
# 1. Story Screen (Visual Novel / Comic-Style Face-Off)
# ----------------------------------------------------------------------
SPEAKER_THEMES: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "Crimson": {
        "border": (235, 78, 58),
        "badge_bg": (165, 34, 28),
        "badge_text": (255, 228, 135),
        "glow": (255, 95, 45),
    },
    "Steel": {
        "border": (155, 195, 235),
        "badge_bg": (48, 76, 112),
        "badge_text": (225, 242, 255),
        "glow": (95, 175, 255),
    },
    "Shadow": {
        "border": (178, 108, 245),
        "badge_bg": (78, 38, 126),
        "badge_text": (165, 250, 255),
        "glow": (170, 90, 255),
    },
    "Golden": {
        "border": (245, 200, 72),
        "badge_bg": (138, 98, 24),
        "badge_text": (255, 246, 200),
        "glow": (255, 210, 65),
    },
}


def _wrap_text_lines(text: str, font: pygame.font.Font, max_width: int) -> List[str]:
    """Word-wrap text string to fit within max_width pixels."""
    words = text.split(" ")
    lines: List[str] = []
    cur = ""
    for w in words:
        if not w:
            continue
        candidate = f"{cur} {w}".strip()
        if font.size(candidate)[0] <= max_width:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_story_fighter_standee(
    surface: pygame.Surface,
    char_name: str,
    cx: int,
    floor_y: int,
    facing_right: bool,
    is_active_speaker: bool,
    is_narration: bool,
    is_mirror: bool,
    frame_counter: int,
    role_tag: str,
    pose: str = "idle",
) -> Tuple[int, int]:
    """Render one full-body fighter in the face-off layout with speaker spotlight or dimming.

    Returns (head_x, head_y) for aiming comic speech bubble pointer tails.
    """
    theme = SPEAKER_THEMES.get(char_name, SPEAKER_THEMES["Golden"])
    glow_col = theme["glow"]
    border_col = theme["border"]

    base_h = 286
    if is_active_speaker:
        target_h = int(base_h * 1.05)
    elif is_narration:
        target_h = base_h
    else:
        target_h = int(base_h * 0.94)

    breath = math.sin(frame_counter * 0.06 + (0.0 if facing_right else 1.8)) * 2.5
    draw_h = max(60, int(target_h + breath))

    raw_sprite = get_fighter_sprite_seamless(
        char_name,
        height=draw_h,
        is_mirror=is_mirror,
        pose=pose,
    )
    oriented = pygame.transform.flip(raw_sprite, not facing_right, False).copy()
    sw, sh = oriented.get_size()

    # Dim non-speaking fighter during character dialogue so active speaker pops
    if not is_active_speaker and not is_narration:
        dim_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim_surf.fill((112, 118, 136, 255))
        oriented.blit(dim_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # Ground contact shadow
    shadow_w = max(84, int(sw * 0.95))
    shadow_h = 24
    shadow_surf = pygame.Surface((shadow_w + 24, shadow_h + 12), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow_surf, (0, 0, 0, 155), (8, 4, shadow_w, shadow_h))
    surface.blit(shadow_surf, (cx - (shadow_w + 24) // 2, floor_y - shadow_h // 2 - 2))

    # Active speaker ground ring & backlight aura
    if is_active_speaker:
        pulse = int(140 + 45 * math.sin(frame_counter * 0.12))
        ring_surf = pygame.Surface((shadow_w + 32, shadow_h + 16), pygame.SRCALPHA)
        pygame.draw.ellipse(ring_surf, (*glow_col, pulse), (4, 3, shadow_w + 24, shadow_h + 10), 3)
        pygame.draw.ellipse(ring_surf, (255, 255, 255, pulse // 2), (12, 6, shadow_w + 8, shadow_h + 4), 1)
        surface.blit(ring_surf, (cx - (shadow_w + 32) // 2, floor_y - (shadow_h + 16) // 2 + 2))

    topleft = (cx - sw // 2, floor_y - sh)
    surface.blit(oriented, topleft)

    # Engraved fighter nameplate pill below feet
    plate_w, plate_h = 166, 26
    plate_rect = pygame.Rect(cx - plate_w // 2, floor_y + 6, plate_w, plate_h)
    plate_bg = theme["badge_bg"] if is_active_speaker else (20, 22, 34)
    plate_border = GOLD_BRIGHT if is_active_speaker else (85, 78, 68)
    pygame.draw.rect(surface, plate_bg, plate_rect, border_radius=6)
    pygame.draw.rect(surface, plate_border, plate_rect, width=2 if is_active_speaker else 1, border_radius=6)

    font_tag = _get_font(15, bold=True)
    label_col = theme["badge_text"] if is_active_speaker else TEXT_MUTED
    tag_surf = font_tag.render(f"{role_tag}: {char_name.upper()}", True, label_col)
    surface.blit(tag_surf, tag_surf.get_rect(center=plate_rect.center))

    head_dir = 1 if facing_right else -1
    head_x = cx + head_dir * (sw // 3)
    head_y = floor_y - int(sh * 0.80)
    return head_x, head_y


def _draw_narration_banner(
    surface: pygame.Surface,
    typed_text: str,
    is_done_typing: bool,
    frame_counter: int,
    compact_text: Optional[str] = None,
) -> None:
    """Draw the sleek stage-setting narrator banner at the top of the arena."""
    if compact_text is not None:
        # Compact stage-setting strip kept visible above comic speech bubbles
        strip_rect = pygame.Rect(226, 88, SCREEN_WIDTH - 452, 32)
        strip_surf = pygame.Surface(strip_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(strip_surf, (16, 18, 30, 195), strip_surf.get_rect(), border_radius=8)
        pygame.draw.rect(strip_surf, (140, 106, 63, 210), strip_surf.get_rect(), width=1, border_radius=8)
        surface.blit(strip_surf, strip_rect.topleft)

        font_strip = _get_font(14)
        short = compact_text if len(compact_text) <= 72 else compact_text[:69] + "..."
        s_surf = font_strip.render(short, True, (215, 205, 180))
        surface.blit(s_surf, s_surf.get_rect(center=strip_rect.center))
        return

    banner_rect = pygame.Rect(226, 98, SCREEN_WIDTH - 452, 152)

    # Drop shadow
    shadow_rect = banner_rect.move(0, 6)
    sh_surf = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(sh_surf, (0, 0, 0, 150), sh_surf.get_rect(), border_radius=12)
    surface.blit(sh_surf, shadow_rect.topleft)

    # Translucent dark chronicle card so arena and both fighters remain completely unobstructed
    card_surf = pygame.Surface(banner_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(card_surf, (18, 21, 35, 232), card_surf.get_rect(), border_radius=12)
    surface.blit(card_surf, banner_rect.topleft)
    pygame.draw.rect(surface, GOLD_TEXT, banner_rect, width=2, border_radius=12)
    pygame.draw.rect(surface, PANEL_BORDER, banner_rect.inflate(-8, -8), width=1, border_radius=9)

    # Top-left "SCENE NARRATION" header pill
    tag_rect = pygame.Rect(banner_rect.x + 20, banner_rect.y - 14, 178, 26)
    pygame.draw.rect(surface, (115, 82, 32), tag_rect, border_radius=6)
    pygame.draw.rect(surface, GOLD_BRIGHT, tag_rect, width=2, border_radius=6)
    font_tag = _get_font(14, bold=True)
    tag_surf = font_tag.render("SCENE NARRATION", True, (255, 245, 205))
    surface.blit(tag_surf, tag_surf.get_rect(center=tag_rect.center))

    font_body = _get_font(18)
    lines = _wrap_text_lines(typed_text, font_body, banner_rect.width - 44)
    y_cur = banner_rect.y + 22
    for ln in lines[:4]:
        ln_surf = font_body.render(ln, True, (240, 235, 220))
        surface.blit(ln_surf, (banner_rect.x + 22, y_cur))
        y_cur += 25

    if is_done_typing:
        pulse_y = int(math.sin(frame_counter * 0.16) * 2)
        font_prompt = _get_font(14, bold=True)
        p_surf = font_prompt.render("SPACE / ENTER", True, GOLD_BRIGHT)
        px = banner_rect.right - p_surf.get_width() - 32
        py = banner_rect.bottom - 24 + pulse_y
        surface.blit(p_surf, (px, py))
        tri_x = banner_rect.right - 20
        tri_y = py + p_surf.get_height() // 2
        pygame.draw.polygon(surface, GOLD_BRIGHT, [(tri_x - 5, tri_y - 3), (tri_x + 5, tri_y - 3), (tri_x, tri_y + 4)])


def _draw_comic_speech_bubble(
    surface: pygame.Surface,
    speaker_char: str,
    speaker_label: str,
    side: str,
    typed_text: str,
    target_head: Tuple[int, int],
    is_done_typing: bool,
    frame_counter: int,
) -> None:
    """Draw a comic-style speech bubble with a directional pointer tail aimed at the speaker."""
    theme = SPEAKER_THEMES.get(speaker_char, SPEAKER_THEMES["Golden"])
    border_col = theme["border"]
    badge_bg = theme["badge_bg"]
    badge_text_col = theme["badge_text"]

    bubble_w, bubble_h = 444, 142
    if side == "left":
        bubble_rect = pygame.Rect(274, 142, bubble_w, bubble_h)
        tail_tip = (max(218, target_head[0] + 10), min(255, max(185, target_head[1] + 12)))
        tail_base_top = (bubble_rect.left + 3, bubble_rect.y + 52)
        tail_base_bot = (bubble_rect.left + 3, bubble_rect.y + 84)
        seam_top = (bubble_rect.left, bubble_rect.y + 54)
        seam_bot = (bubble_rect.left, bubble_rect.y + 82)
        badge_rect = pygame.Rect(bubble_rect.x + 18, bubble_rect.y - 16, 172, 30)
    else:
        bubble_rect = pygame.Rect(SCREEN_WIDTH - 274 - bubble_w, 142, bubble_w, bubble_h)
        tail_tip = (min(SCREEN_WIDTH - 218, target_head[0] - 10), min(255, max(185, target_head[1] + 12)))
        tail_base_top = (bubble_rect.right - 3, bubble_rect.y + 52)
        tail_base_bot = (bubble_rect.right - 3, bubble_rect.y + 84)
        seam_top = (bubble_rect.right - 1, bubble_rect.y + 54)
        seam_bot = (bubble_rect.right - 1, bubble_rect.y + 82)
        badge_rect = pygame.Rect(bubble_rect.right - 190, bubble_rect.y - 16, 172, 30)

    tail_pts = [tail_base_top, tail_tip, tail_base_bot]

    # 1. Soft drop shadow for bubble and pointer tail
    shadow_offset = (6, 8)
    shadow_rect = bubble_rect.move(*shadow_offset)
    shadow_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(shadow_surf, (0, 0, 0, 155), shadow_rect, border_radius=14)
    shadow_tail = [(x + shadow_offset[0], y + shadow_offset[1]) for (x, y) in tail_pts]
    pygame.draw.polygon(shadow_surf, (0, 0, 0, 155), shadow_tail)
    surface.blit(shadow_surf, (0, 0))

    # 2. Speech bubble body & pointer tail fill
    bubble_fill = (25, 28, 46)
    pygame.draw.rect(surface, bubble_fill, bubble_rect, border_radius=14)
    pygame.draw.polygon(surface, bubble_fill, tail_pts)

    # 3. Crisp 3px character-colored border + seamless tail outline
    pygame.draw.rect(surface, border_col, bubble_rect, width=3, border_radius=14)
    pygame.draw.line(surface, bubble_fill, seam_top, seam_bot, 5)
    pygame.draw.line(surface, border_col, tail_base_top, tail_tip, 3)
    pygame.draw.line(surface, border_col, tail_tip, tail_base_bot, 3)

    # Subtle inner highlight border
    pygame.draw.rect(surface, (55, 62, 92), bubble_rect.inflate(-10, -10), width=1, border_radius=10)

    # 4. Color-coded Speaker Nameplate Tab
    pygame.draw.rect(surface, badge_bg, badge_rect, border_radius=7)
    pygame.draw.rect(surface, border_col, badge_rect, width=2, border_radius=7)
    font_badge = _get_font(16, bold=True)
    b_surf = font_badge.render(speaker_label, True, badge_text_col)
    surface.blit(b_surf, b_surf.get_rect(center=badge_rect.center))
    # Small diamond emblem inside speaker tab
    dia_x = badge_rect.x + 16 if side == "left" else badge_rect.right - 16
    dia_y = badge_rect.centery
    pygame.draw.polygon(
        surface,
        badge_text_col,
        [(dia_x, dia_y - 5), (dia_x + 5, dia_y), (dia_x, dia_y + 5), (dia_x - 5, dia_y)],
    )

    # 5. Wrapped dialogue text inside speech bubble
    font_quote = _get_font(21, bold=True)
    display_quote = f'"{typed_text}"' if typed_text else ""
    lines = _wrap_text_lines(display_quote, font_quote, bubble_rect.width - 44)
    y_cur = bubble_rect.y + 26
    for ln in lines[:3]:
        q_surf = font_quote.render(ln, True, TEXT_WHITE)
        surface.blit(q_surf, (bubble_rect.x + 22, y_cur))
        y_cur += 29

    # 6. Continue prompt indicator inside bubble bottom-right
    if is_done_typing:
        pulse_y = int(math.sin(frame_counter * 0.16) * 2)
        font_prompt = _get_font(15, bold=True)
        p_surf = font_prompt.render("NEXT", True, border_col)
        px = bubble_rect.right - p_surf.get_width() - 32
        py = bubble_rect.bottom - 26 + pulse_y
        surface.blit(p_surf, (px, py))
        tri_x = bubble_rect.right - 20
        tri_y = py + p_surf.get_height() // 2
        pygame.draw.polygon(surface, border_col, [(tri_x - 5, tri_y - 3), (tri_x + 5, tri_y - 3), (tri_x, tri_y + 4)])


def render_story_faceoff_frame(
    surface: pygame.Surface,
    bg: pygame.Surface,
    battle: Dict[str, Any],
    warrior_name: str,
    dialogue_steps: List[Dict[str, str]],
    step_index: int,
    char_index: int,
    frame_counter: int,
) -> None:
    """Render one complete frame of the visual-novel / comic face-off story screen."""
    # 1. Visible Arena Background with subtle edge vignette
    surface.blit(bg, (0, 0))
    stage_tint = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    stage_tint.fill((10, 12, 22, 65))
    surface.blit(stage_tint, (0, 0))

    # Top and bottom cinematic bars
    top_bar = pygame.Surface((SCREEN_WIDTH, 80), pygame.SRCALPHA)
    top_bar.fill((12, 14, 24, 215))
    surface.blit(top_bar, (0, 0))
    pygame.draw.line(surface, PANEL_BORDER, (0, 80), (SCREEN_WIDTH, 80), 2)

    bot_bar = pygame.Surface((SCREEN_WIDTH, 44), pygame.SRCALPHA)
    bot_bar.fill((12, 14, 24, 220))
    surface.blit(bot_bar, (0, SCREEN_HEIGHT - 44))
    pygame.draw.line(surface, PANEL_BORDER, (0, SCREEN_HEIGHT - 44), (SCREEN_WIDTH, SCREEN_HEIGHT - 44), 1)

    # 2. Header Title & Matchup Info
    b_num = battle.get("id", 1)
    b_title = battle.get("title", "Battle")
    opp = battle.get("opponent", "Crimson")
    diff = battle.get("difficulty", "LOW")

    font_title = _get_font(30, bold=True)
    font_sub = _get_font(17)
    font_hint = _get_font(17)

    t_surf = font_title.render(f"BATTLE {b_num}: {b_title.upper()}", True, GOLD_TEXT)
    surface.blit(t_surf, (SCREEN_WIDTH // 2 - t_surf.get_width() // 2, 12))

    sub_text = (
        f"Challenger: {warrior_name}   vs   Guardian: {opp}   |   "
        f"Tier: {diff}   |   Dialogue {step_index + 1} / {len(dialogue_steps)}"
    )
    s_surf = font_sub.render(sub_text, True, TEXT_MUTED)
    surface.blit(s_surf, (SCREEN_WIDTH // 2 - s_surf.get_width() // 2, 49))

    # 3. Current Step Resolution
    step = dialogue_steps[min(step_index, len(dialogue_steps) - 1)]
    cur_side = step.get("side", "center")
    is_narration = (step.get("type") == "narration" or cur_side == "center")
    full_text = step.get("text", "")
    typed_text = full_text[:char_index]
    is_done_typing = (char_index >= len(full_text))

    # 4. Split Face-Off Fighters (Left Challenger vs Right Opponent)
    floor_y = 514
    left_cx = 175
    right_cx = SCREEN_WIDTH - 175
    is_mirror = (warrior_name == opp)

    left_head = _draw_story_fighter_standee(
        surface,
        char_name=warrior_name,
        cx=left_cx,
        floor_y=floor_y,
        facing_right=True,
        is_active_speaker=(cur_side == "left"),
        is_narration=is_narration,
        is_mirror=False,
        frame_counter=frame_counter,
        role_tag="P1",
        pose=step.get("pose_left", "idle"),
    )
    right_head = _draw_story_fighter_standee(
        surface,
        char_name=opp,
        cx=right_cx,
        floor_y=floor_y,
        facing_right=False,
        is_active_speaker=(cur_side == "right"),
        is_narration=is_narration,
        is_mirror=is_mirror,
        frame_counter=frame_counter,
        role_tag="FOE",
        pose=step.get("pose_right", "idle"),
    )

    # 5. Scene Narration Banner OR Comic Speech Bubble
    narration_text = dialogue_steps[0].get("text", "") if dialogue_steps else ""
    if is_narration:
        _draw_narration_banner(surface, typed_text, is_done_typing, frame_counter)
    else:
        _draw_narration_banner(surface, "", True, frame_counter, compact_text=narration_text)
        speaker_char = warrior_name if cur_side == "left" else opp
        speaker_label = warrior_name.upper() if cur_side == "left" else opp.upper()
        target_head = left_head if cur_side == "left" else right_head
        _draw_comic_speech_bubble(
            surface,
            speaker_char=speaker_char,
            speaker_label=speaker_label,
            side=cur_side,
            typed_text=typed_text,
            target_head=target_head,
            is_done_typing=is_done_typing,
            frame_counter=frame_counter,
        )

    # 6. Sequential Step Progress Dots & Bottom Controls
    dot_y = SCREEN_HEIGHT - 60
    total_steps = len(dialogue_steps)
    dot_spacing = 22
    start_x = SCREEN_WIDTH // 2 - ((total_steps - 1) * dot_spacing) // 2
    for idx in range(total_steps):
        dx = start_x + idx * dot_spacing
        col = GOLD_BRIGHT if idx == step_index else ((130, 110, 70) if idx < step_index else (55, 60, 80))
        r = 6 if idx == step_index else 4
        pygame.draw.circle(surface, col, (dx, dot_y), r)
        pygame.draw.circle(surface, BLACK, (dx, dot_y), r, 1)

    draw_hint_bar(surface, [("Space", "Next line"), ("Esc", "Skip to fight")])


def story_screen(
    surface: pygame.Surface,
    clock: pygame.time.Clock,
    battle: Dict[str, Any],
    warrior_name: str,
) -> bool:
    """Visual-novel / comic-style face-off intro screen shown before each campaign battle."""
    audio.play_music("music_menu")
    dialogue_steps = get_battle_dialogue(battle, warrior_name)
    arena_name = battle.get("arena", "arena_sky_colosseum")
    bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT), brightness=0.92, dark_overlay=True)

    step_index = 0
    char_index = 0
    typewriter_speed = 3
    frame_counter = 0

    while True:
        clock.tick(60)
        frame_counter += 1

        cur_text = dialogue_steps[step_index]["text"] if step_index < len(dialogue_steps) else ""

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return True
                elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    if char_index < len(cur_text):
                        char_index = len(cur_text)
                    else:
                        audio.play_sfx("menu_select")
                        step_index += 1
                        char_index = 0
                        if step_index >= len(dialogue_steps):
                            return True
                        cur_text = dialogue_steps[step_index]["text"]
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if char_index < len(cur_text):
                    char_index = len(cur_text)
                else:
                    audio.play_sfx("menu_select")
                    step_index += 1
                    char_index = 0
                    if step_index >= len(dialogue_steps):
                        return True
                    cur_text = dialogue_steps[step_index]["text"]

        # Advance Typewriter
        if step_index < len(dialogue_steps):
            cur_text = dialogue_steps[step_index]["text"]
            char_index = min(len(cur_text), char_index + typewriter_speed)
            if char_index < len(cur_text) and frame_counter % 6 == 0:
                audio.play_sfx("menu_hover")

        render_story_faceoff_frame(
            surface,
            bg,
            battle,
            warrior_name,
            dialogue_steps,
            step_index,
            char_index,
            frame_counter,
        )

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

        # 8 nodes laid out in 2 rows of 4, sized from the screen dimensions
        margin, gap = 48, 18
        card_w = (SCREEN_WIDTH - 2 * margin - 3 * gap) // 4
        card_h = int(SCREEN_HEIGHT * 0.25)
        top = int(SCREEN_HEIGHT * 0.26)
        for i in range(8):
            row, col = divmod(i, 4)
            node_rects.append(pygame.Rect(margin + col * (card_w + gap),
                                          top + row * (card_h + gap + 12), card_w, card_h))

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

            if is_unlocked:
                draw_obsidian_card(surface, r, is_selected=is_hover, border_radius=12,
                                   border_color=SUCCESS_GREEN if is_comp else PANEL_BORDER)
                # Opponent portrait strip on the right of the card
                p_h = r.height - 20
                p_w = int(p_h * 0.8)
                portrait = assets.get_portrait(battle["opponent"], size=(p_w, p_h), flip_h=True)
                p_rect = pygame.Rect(r.right - p_w - 10, r.y + 10, p_w, p_h)
                surface.blit(portrait, p_rect)
                pygame.draw.rect(surface, GOLD_TEXT if is_hover else (70, 75, 95), p_rect, 1, border_radius=4)

                b_num_surf = font_node.render(f"BATTLE {b_id}", True, GOLD_TEXT if is_hover else WHITE)
                opp_surf = font_sub.render(f"vs {battle['opponent']}", True, TEXT_WHITE)
                surface.blit(b_num_surf, (r.x + 14, r.y + 14))
                surface.blit(opp_surf, (r.x + 14, r.y + 42))
                _draw_tier_badge(surface, r.x + 14, r.y + 66, battle["difficulty"])

                if is_comp:
                    stars_count = stars_dict.get(str(b_id), 3)
                    for si in range(3):
                        _draw_star(surface, r.x + 22 + si * 22, r.bottom - 24, 8,
                                   filled=si < stars_count)
                else:
                    ready_badge = font_sub.render("READY", True, SUCCESS_GREEN)
                    surface.blit(ready_badge, (r.x + 14, r.bottom - 32))
            else:
                draw_obsidian_card(surface, r, border_radius=12, bg_color=(14, 15, 24),
                                   border_color=(45, 48, 65))
                _draw_emblem_icon(surface, r.centerx, r.centery - 10, "lock", is_active=False)
                lock_text = font_sub.render(f"BATTLE {b_id}  ·  LOCKED", True, (90, 95, 115))
                surface.blit(lock_text, (r.centerx - lock_text.get_width() // 2, r.bottom - 32))

        # Bottom Helper Bar
        draw_hint_bar(surface, [("← → ↑ ↓", "Select battle"), ("Enter", "Fight"),
                                ("U", "Upgrades"), ("Esc", "Back")])

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
            surface, frame_counter, "WARRIOR UPGRADES", player_id,
            sub_title="Empower combat attributes with earned tournament gold"
        )

        # Character Selector Carousel
        bar_text = f"<   {char.upper()} (LEVEL {current_lvl}/{MAX_LEVEL})   >"
        b_surf = font_large.render(bar_text, True, GOLD_TEXT)
        surface.blit(b_surf, (SCREEN_WIDTH // 2 - b_surf.get_width() // 2, 106))

        # Comparison Card Panel
        card_rect = pygame.Rect(SCREEN_WIDTH // 2 - 250, 150, 640, 310)
        draw_obsidian_card(surface, card_rect, border_radius=12)
        # Fighter portrait beside the comparison card
        port_rect = pygame.Rect(card_rect.x - 196, card_rect.y, 180, card_rect.height)
        draw_obsidian_card(surface, port_rect, is_selected=True, border_radius=12)
        port = assets.get_portrait(char, size=(port_rect.width - 16, port_rect.height - 16))
        surface.blit(port, (port_rect.x + 8, port_rect.y + 8))

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
        btn_str = "MAX LEVEL REACHED" if current_lvl >= MAX_LEVEL else f"UPGRADE  ·  {upgrade_cost:,} G"
        if not can_afford and current_lvl < MAX_LEVEL:
            btn_str = f"NEED {upgrade_cost:,} G  (HAVE {coins:,})"
        draw_button(surface, buy_btn_rect, btn_str, selected=is_buy_hover and can_afford,
                    disabled=not can_afford, accent=SUCCESS_GREEN, primary=can_afford)

        draw_hint_bar(surface, [("← →", "Switch warrior"), ("Enter", "Upgrade"), ("Esc", "Back")])

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
            surface, frame_counter, "TROPHY ROOM", player_id,
            sub_title=f"Achievements Unlocked: {unlocked_count} / {total_trophies} ({int(unlocked_count / total_trophies * 100)}%)"
        )

        # Molten Gold Global Progress Bar
        bar_w = 460
        bar_rect = pygame.Rect(SCREEN_WIDTH // 2 - bar_w // 2, 108, bar_w, 12)
        _draw_segmented_bar(surface, bar_rect, unlocked_count, total_trophies, GOLD_TEXT, segments=18)

        # 3 columns x 6 rows of Trophy Cards
        start_y = 134 - scroll_y
        for i, trophy in enumerate(ALL_TROPHIES):
            col = i % 3
            row = i // 3
            t_gap, t_side = 16, 40
            t_w = (SCREEN_WIDTH - 2 * t_side - 2 * t_gap) // 3
            x = t_side + col * (t_w + t_gap)
            y = start_y + row * 92
            if y < 126 or y + 80 > SCREEN_HEIGHT - 44:
                continue

            card_rect = pygame.Rect(x, y, t_w, 80)
            is_unlocked = (trophy["id"] in unlocked_ids)

            bg_col = PANEL_DARK if is_unlocked else (18, 19, 30)
            border_col = PANEL_BORDER if is_unlocked else (45, 48, 65)

            draw_obsidian_card(surface, card_rect, border_radius=10, bg_color=bg_col, border_color=border_col)

            # Emblem Badge
            icon_type = "swords" if is_unlocked else "lock"
            _draw_emblem_icon(surface, card_rect.x + 36, card_rect.centery, icon_type, is_active=is_unlocked, radius=22)

            # Trophy Title & Description
            t_col = GOLD_BRIGHT if is_unlocked else (110, 115, 130)
            d_col = TEXT_MUTED if is_unlocked else (80, 85, 100)

            t_name = font_name.render(trophy["name"], True, t_col)
            t_desc = font_desc.render(trophy["desc"], True, d_col)
            surface.blit(t_name, (card_rect.x + 72, card_rect.y + 18))
            surface.blit(t_desc, (card_rect.x + 72, card_rect.y + 46))

            # Unlocked tick (locked state is already shown by the padlock emblem)
            if is_unlocked:
                _draw_tier_badge(surface, card_rect.right - 74, card_rect.y + 8, "UNLOCKED")

        draw_hint_bar(surface, [("↑ ↓", "Browse"), ("Wheel", "Scroll"), ("Esc", "Back")])

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
        col_gap, side = 20, 40
        card_w, card_h = (SCREEN_WIDTH - 2 * side - col_gap) // 2, 94
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
            cx = side + col * (card_w + col_gap)
            cy = start_y + row * 102
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
        draw_hint_bar(surface, [("Esc", "Back"), ("Enter", "Claim"), ("Tab", "Switch tab")],
                      y=SCREEN_HEIGHT - 30)

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
