"""AAA Dark-Fantasy War-Camp Bounty Board UI Design System for Arena-AI.

Provides unified styling, backdrops, ambient torchlight glows, rising embers,
molten-gold headers, obsidian card panels with bevelled bronze borders, circular
metallic emblem badges, segmented progress bars, and wax seal stamps across all screens.
"""

import math
import random
from typing import Any, Dict, List, Optional, Tuple
import pygame

from backend.data.results_db import results_db
from frontend.assets import assets
from frontend.theme import SCREEN_HEIGHT, SCREEN_WIDTH, WHITE

# ----------------------------------------------------------------------
# AAA Dark Fantasy Palette Constants
# ----------------------------------------------------------------------
BG_DARK = (14, 15, 26)               # #0E0F1A
PANEL_DARK = (26, 27, 46)            # #1A1B2E
PANEL_DARK_ALT = (20, 22, 36)        # Recessed card background
PANEL_BORDER = (140, 106, 63)        # #8C6A3F (Bronze)
PANEL_BORDER_LIGHT = (195, 155, 105) # Highlighted bronze bevel
PANEL_BORDER_GLOW = (255, 215, 100)  # Molten-gold hover glow
GOLD_TEXT = (245, 197, 66)           # #F5C542 (Molten Gold)
GOLD_BRIGHT = (255, 235, 150)        # Bright molten sheen
EMBER_ORANGE = (255, 122, 47)        # #FF7A2F (Torch ember)
SUCCESS_GREEN = (74, 222, 128)       # #4ADE80
CRIMSON_TAG = (220, 38, 38)          # #DC2626 (War crimson)
SILVER_TAG = (175, 190, 210)
BRONZE_TAG = (185, 135, 75)
TEXT_WHITE = (243, 244, 246)
TEXT_MUTED = (156, 163, 175)
TEXT_GOLD_MUTED = (215, 185, 120)

# Global ember particle system state: [x, y, speed_y, wobble_freq, alpha, size]
_EMBERS: List[List[float]] = []


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Helper to safely fetch pygame font with fallback."""
    try:
        f = pygame.font.Font(None, size)
        f.set_bold(bold)
        return f
    except Exception:
        return pygame.font.SysFont("arial", size, bold=bold)


def init_embers_if_needed():
    """Seed floating ambient ember particles."""
    global _EMBERS
    if not _EMBERS:
        for _ in range(40):
            x = random.uniform(15, SCREEN_WIDTH - 15)
            y = random.uniform(40, SCREEN_HEIGHT)
            spd = random.uniform(0.6, 1.8)
            freq = random.uniform(0.02, 0.05)
            alpha = random.randint(120, 230)
            sz = random.choice([2, 3, 3, 4])
            _EMBERS.append([x, y, spd, freq, alpha, sz])


def draw_dark_fantasy_backdrop(
    surface: pygame.Surface,
    frame_counter: int = 0,
    title_text: str = "ARENA-AI",
    player_id: Optional[int] = None,
    sub_title: Optional[str] = None,
    show_economy: bool = True,
    arena_bg_name: str = "arena_sky_colosseum",
) -> None:
    """Draw ambient night colosseum, vignette scrim, torchlight glows, rising embers, and top status bar."""
    init_embers_if_needed()

    # 1. Base Arena Background
    bg = assets.get_arena(arena_bg_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))
    surface.blit(bg, (0, 0))

    # 2. Deep Vignette Scrim (Dark obsidian night falloff)
    scrim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    scrim.fill((14, 15, 26, 185))
    # Extra darkness around edges
    pygame.draw.rect(scrim, (5, 5, 10, 95), (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), width=75)
    surface.blit(scrim, (0, 0))

    # 3. Ambient Torchlight Glow at corners
    torch_glow = pygame.Surface((280, 280), pygame.SRCALPHA)
    for r in range(140, 10, -15):
        alpha = int(35 * (1.0 - r / 140.0))
        pygame.draw.circle(torch_glow, (255, 122, 47, alpha), (140, 140), r)
    surface.blit(torch_glow, (-80, 180), special_flags=pygame.BLEND_RGBA_ADD)
    surface.blit(torch_glow, (SCREEN_WIDTH - 200, 180), special_flags=pygame.BLEND_RGBA_ADD)

    # 4. Floating Ember Particles
    for p in _EMBERS:
        p[1] -= p[2]
        p[0] += math.sin(frame_counter * p[3]) * 0.4
        if p[1] < 30:
            p[1] = SCREEN_HEIGHT + random.uniform(5, 30)
            p[0] = random.uniform(15, SCREEN_WIDTH - 15)

        # Draw glowing ember dot
        ember_col = (255, random.randint(110, 160), random.randint(30, 60))
        pygame.draw.circle(surface, ember_col, (int(p[0]), int(p[1])), int(p[5]))

    # 5. Top Header (Engraved Molten Gold Title + Crossed Swords)
    font_title = get_font(38, bold=True)
    full_title = f"{title_text.upper()}"

    # Shadow and golden glow layers
    shadow_surf = font_title.render(full_title, True, (0, 0, 0))
    gold_surf = font_title.render(full_title, True, GOLD_TEXT)
    bright_surf = font_title.render(full_title, True, GOLD_BRIGHT)

    tx = SCREEN_WIDTH // 2 - gold_surf.get_width() // 2
    ty = 22
    surface.blit(shadow_surf, (tx + 2, ty + 2))
    surface.blit(gold_surf, (tx, ty))
    # Subtle inner metallic highlight
    surface.blit(bright_surf, (tx, ty), special_flags=pygame.BLEND_RGBA_ADD)

    # Crossed Swords Heraldry ornaments on both sides of title
    sw_sz = 16
    # Left ornament
    lx = tx - 34
    ly = ty + 18
    pygame.draw.line(surface, GOLD_TEXT, (lx - sw_sz, ly - sw_sz), (lx + sw_sz, ly + sw_sz), 2)
    pygame.draw.line(surface, GOLD_TEXT, (lx + sw_sz, ly - sw_sz), (lx - sw_sz, ly + sw_sz), 2)
    pygame.draw.circle(surface, (255, 235, 150), (lx, ly), 3)

    # Right ornament
    rx = tx + gold_surf.get_width() + 34
    ry = ty + 18
    pygame.draw.line(surface, GOLD_TEXT, (rx - sw_sz, ry - sw_sz), (rx + sw_sz, ry + sw_sz), 2)
    pygame.draw.line(surface, GOLD_TEXT, (rx + sw_sz, ry - sw_sz), (rx - sw_sz, ry + sw_sz), 2)
    pygame.draw.circle(surface, (255, 235, 150), (rx, ry), 3)

    if sub_title:
        font_sub = get_font(18)
        s_surf = font_sub.render(sub_title, True, TEXT_MUTED)
        surface.blit(s_surf, (SCREEN_WIDTH // 2 - s_surf.get_width() // 2, ty + 42))

    # 6. Top-Right Economy Status Capsule & Player Level with XP Ring
    if show_economy:
        p_id = player_id
        if p_id is None:
            def_p = results_db.get_default_player()
            if def_p:
                p_id = int(def_p["player_id"])
        
        coins = 0
        max_lvl = 1
        if p_id is not None:
            prog = results_db.get_or_create_progress(p_id)
            coins = prog.get("coins", 0)
            max_lvl = max(
                prog.get("crimson_level", 1),
                prog.get("steel_level", 1),
                prog.get("shadow_level", 1),
                prog.get("golden_level", 1),
            )

        # Coin Capsule
        font_coin = get_font(18, bold=True)
        coin_str = f"{coins:,}"
        c_text_surf = font_coin.render(coin_str, True, WHITE)
        capsule_w = c_text_surf.get_width() + 48
        capsule_h = 30
        capsule_rect = pygame.Rect(SCREEN_WIDTH - 180 - capsule_w, 20, capsule_w, capsule_h)

        pygame.draw.rect(surface, (18, 20, 32), capsule_rect, border_radius=15)
        pygame.draw.rect(surface, PANEL_BORDER, capsule_rect, width=1, border_radius=15)

        # Gold Coin icon
        coin_cx = capsule_rect.x + 16
        coin_cy = capsule_rect.centery
        pygame.draw.circle(surface, (245, 197, 66), (coin_cx, coin_cy), 9)
        pygame.draw.circle(surface, (255, 235, 150), (coin_cx, coin_cy), 7)
        pygame.draw.circle(surface, (200, 140, 20), (coin_cx, coin_cy), 4)
        surface.blit(c_text_surf, (coin_cx + 14, capsule_rect.centery - c_text_surf.get_height() // 2))

        # Level Ring Badge
        badge_cx = SCREEN_WIDTH - 70
        badge_cy = 35
        # Outer dark circle
        pygame.draw.circle(surface, (18, 20, 32), (badge_cx, badge_cy), 20)
        # XP Ring arc
        arc_rect = pygame.Rect(badge_cx - 20, badge_cy - 20, 40, 40)
        pygame.draw.arc(surface, (40, 50, 75), arc_rect, 0, math.pi * 2, 2)
        # 75% XP fill arc
        pygame.draw.arc(surface, (60, 220, 240), arc_rect, -math.pi / 2, math.pi * 1.1, 2)
        # Badge text
        font_lvl = get_font(11, bold=True)
        font_num = get_font(16, bold=True)
        l_surf = font_lvl.render("LV", True, (160, 200, 240))
        n_surf = font_num.render(str(max_lvl), True, WHITE)
        surface.blit(l_surf, (badge_cx - l_surf.get_width() // 2, badge_cy - 11))
        surface.blit(n_surf, (badge_cx - n_surf.get_width() // 2, badge_cy + 1))


def draw_obsidian_card(
    surface: pygame.Surface,
    rect: pygame.Rect,
    is_selected: bool = False,
    is_hovered: bool = False,
    border_radius: int = 8,
    bg_color: Tuple[int, int, int] = PANEL_DARK,
    border_color: Tuple[int, int, int] = PANEL_BORDER,
) -> None:
    """Draw a dark obsidian panel with thin bevelled bronze or glowing gold border."""
    # Base dark fill
    card_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    alpha = 240 if (is_selected or is_hovered) else 215
    fill_col = (bg_color[0], bg_color[1], bg_color[2], alpha)
    pygame.draw.rect(card_surf, fill_col, (0, 0, rect.width, rect.height), border_radius=border_radius)
    surface.blit(card_surf, rect.topleft)

    if is_selected or is_hovered:
        # Molten-gold glowing border
        glow_rect = rect.inflate(4, 4)
        glow_surf = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(glow_surf, (245, 197, 66, 45), (0, 0, glow_rect.width, glow_rect.height), border_radius=border_radius + 2)
        surface.blit(glow_surf, glow_rect.topleft)

        pygame.draw.rect(surface, PANEL_BORDER_GLOW, rect, width=2, border_radius=border_radius)
        # Top inner edge highlight
        pygame.draw.line(surface, GOLD_BRIGHT, (rect.x + border_radius, rect.y + 1), (rect.right - border_radius, rect.y + 1), 1)
    else:
        # Subtle bronze border with top bevel
        pygame.draw.rect(surface, border_color, rect, width=1, border_radius=border_radius)
        pygame.draw.line(surface, PANEL_BORDER_LIGHT, (rect.x + border_radius, rect.y + 1), (rect.right - border_radius, rect.y + 1), 1)


def draw_dark_fantasy_menu_buttons(
    surface: pygame.Surface,
    items: List[str],
    selected: int,
    font: pygame.font.Font,
    start_y: int = 165,
    step_y: int = 62,
    width: int = 480,
    height: int = 50,
    icons: Optional[List[str]] = None,
) -> List[pygame.Rect]:
    """Draw interactive dark-fantasy obsidian menu cards with hover/selection states."""
    rects: List[pygame.Rect] = []

    for i, item in enumerate(items):
        is_sel = (i == selected)
        rx = (SCREEN_WIDTH - width) // 2
        ry = start_y + i * step_y
        rect = pygame.Rect(rx, ry, width, height)
        rects.append(rect)

        # Draw card container
        draw_obsidian_card(surface, rect, is_selected=is_sel, border_radius=8)

        # Draw optional icon emblem on the left
        text_x = rect.x + 30
        if icons and i < len(icons) and icons[i]:
            draw_emblem_icon(surface, rect.x + 32, rect.centery, icons[i], is_active=is_sel, radius=18)
            text_x = rect.x + 62

        # Draw Molten Gold or Off-White text
        text_col = GOLD_BRIGHT if is_sel else TEXT_WHITE
        text_surf = font.render(item, True, text_col)
        text_rect = text_surf.get_rect(midleft=(text_x, rect.centery))
        surface.blit(text_surf, text_rect)

        # Right indicator arrow/diamond if selected
        if is_sel:
            ax = rect.right - 28
            ay = rect.centery
            pts = [(ax - 6, ay - 6), (ax, ay), (ax - 6, ay + 6)]
            pygame.draw.polygon(surface, GOLD_TEXT, pts)

    return rects


def draw_description_pill(
    surface: pygame.Surface,
    text: str,
    y: int = 575,
    font: Optional[pygame.font.Font] = None,
) -> None:
    """Draw bottom description capsule pill with subtle bronze frame."""
    if font is None:
        font = get_font(19)

    desc_surf = font.render(text, True, TEXT_GOLD_MUTED)
    desc_rect = desc_surf.get_rect(center=(SCREEN_WIDTH // 2, y))
    pill_rect = desc_rect.inflate(44, 14)

    pill_surf = pygame.Surface((pill_rect.width, pill_rect.height), pygame.SRCALPHA)
    pill_surf.fill((16, 18, 30, 215))
    surface.blit(pill_surf, pill_rect.topleft)

    pygame.draw.rect(surface, PANEL_BORDER, pill_rect, width=1, border_radius=6)
    surface.blit(desc_surf, desc_rect)


def draw_segmented_bar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    current: int,
    target: int,
    fill_color: Tuple[int, int, int] = GOLD_TEXT,
    bg_color: Tuple[int, int, int] = (30, 32, 48),
    segments: int = 8,
) -> None:
    """Draw a segmented AAA combat progress bar."""
    pygame.draw.rect(surface, bg_color, rect, border_radius=4)
    pygame.draw.rect(surface, (50, 55, 75), rect, width=1, border_radius=4)

    ratio = max(0.0, min(1.0, current / max(1, target)))
    if ratio <= 0.001:
        return

    active_segs = int(round(ratio * segments))
    gap = 2
    seg_w = max(2, (rect.width - (segments - 1) * gap) // segments)

    for i in range(active_segs):
        sx = rect.x + i * (seg_w + gap)
        sw = min(seg_w, rect.right - sx)
        s_rect = pygame.Rect(sx, rect.y + 1, sw, rect.height - 2)
        pygame.draw.rect(surface, fill_color, s_rect, border_radius=2)
        # Inner highlight
        pygame.draw.line(surface, (255, 245, 180), (s_rect.x, s_rect.y), (s_rect.right - 1, s_rect.y), 1)


def draw_emblem_icon(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    icon_name: str,
    is_active: bool = True,
    radius: int = 24,
) -> None:
    """Draw circular metallic emblem icon badge."""
    ring_col = PANEL_BORDER_LIGHT if is_active else (70, 75, 95)
    bg_col = (20, 22, 34) if is_active else (15, 16, 24)
    glow_col = GOLD_TEXT if is_active else (120, 125, 140)

    # Outer circle
    pygame.draw.circle(surface, bg_col, (cx, cy), radius)
    pygame.draw.circle(surface, ring_col, (cx, cy), radius, 2)
    # Inner rim
    pygame.draw.circle(surface, (bg_col[0] + 15, bg_col[1] + 15, bg_col[2] + 20), (cx, cy), radius - 3, 1)

    r = radius - 8
    # Icon Vector Art
    if icon_name in ("swords", "wins", "combat", "start"):
        pygame.draw.line(surface, glow_col, (cx - r, cy - r), (cx + r, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx + r, cy - r), (cx - r, cy + r), 2)
        pygame.draw.circle(surface, GOLD_BRIGHT if is_active else ring_col, (cx, cy), 3)

    elif icon_name in ("shield", "blocks", "guard", "hq"):
        pts = [(cx, cy - r), (cx + r, cy - r // 2), (cx + r * 2 // 3, cy + r), (cx, cy + r + 2), (cx - r * 2 // 3, cy + r), (cx - r, cy - r // 2)]
        pygame.draw.polygon(surface, glow_col, pts, 2)

    elif icon_name in ("flame", "specials"):
        pts = [(cx, cy + r), (cx + r, cy + r // 2), (cx + r // 2, cy), (cx, cy - r), (cx - r // 2, cy - r // 4), (cx - r, cy + r // 2)]
        pygame.draw.polygon(surface, EMBER_ORANGE if is_active else ring_col, pts)

    elif icon_name in ("arrow", "upgrades", "rising_arrow", "forge"):
        pygame.draw.line(surface, glow_col, (cx, cy + r), (cx, cy - r), 3)
        pygame.draw.line(surface, glow_col, (cx - r, cy - r // 3), (cx, cy - r), 3)
        pygame.draw.line(surface, glow_col, (cx + r, cy - r // 3), (cx, cy - r), 3)

    elif icon_name in ("crystal", "flawless"):
        pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        pygame.draw.polygon(surface, (120, 220, 255) if is_active else ring_col, pts, 2)
        pygame.draw.circle(surface, WHITE, (cx, cy), 2)

    elif icon_name in ("chain", "combo"):
        pygame.draw.ellipse(surface, glow_col, (cx - r, cy - r // 2, r + 2, r), 2)
        pygame.draw.ellipse(surface, glow_col, (cx - 2, cy - r // 2, r + 2, r), 2)

    elif icon_name in ("broken_shield", "noblock"):
        pts = [(cx, cy - r), (cx + r, cy - r // 2), (cx + r // 2, cy + r), (cx, cy + r - 2)]
        pygame.draw.polygon(surface, glow_col, pts, 2)
        pygame.draw.line(surface, CRIMSON_TAG, (cx - r // 2, cy - r // 2), (cx + r // 2, cy + r // 2), 2)

    elif icon_name in ("lightning", "speed", "fast"):
        pts = [(cx + 2, cy - r), (cx - r, cy + 2), (cx, cy + 2), (cx - 2, cy + r), (cx + r, cy - 2), (cx, cy - 2)]
        pygame.draw.polygon(surface, (255, 230, 80) if is_active else ring_col, pts)

    elif icon_name in ("padlock", "lock", "locked"):
        body_rect = pygame.Rect(cx - r + 3, cy - 1, (r - 3) * 2, r)
        pygame.draw.rect(surface, (130, 135, 150), body_rect, border_radius=2)
        pygame.draw.arc(surface, (170, 175, 190), (cx - r + 5, cy - r, (r - 5) * 2, r * 2), 0, math.pi, 2)

    elif icon_name in ("campaign", "crown"):
        pts = [(cx - r, cy + r - 2), (cx - r, cy - r // 3), (cx - r // 2, cy + 2), (cx, cy - r), (cx + r // 2, cy + 2), (cx + r, cy - r // 3), (cx + r, cy + r - 2)]
        pygame.draw.polygon(surface, GOLD_TEXT if is_active else ring_col, pts, 2)

    elif icon_name in ("tutorial", "target"):
        pygame.draw.circle(surface, glow_col, (cx, cy), r, 2)
        pygame.draw.circle(surface, glow_col, (cx, cy), r // 2, 2)
        pygame.draw.circle(surface, GOLD_BRIGHT if is_active else ring_col, (cx, cy), 2)

    elif icon_name in ("trophies", "trophy", "cup"):
        cup_pts = [(cx - r, cy - r), (cx + r, cy - r), (cx + r * 2 // 3, cy + 2), (cx - r * 2 // 3, cy + 2)]
        pygame.draw.polygon(surface, glow_col, cup_pts, 2)
        pygame.draw.line(surface, glow_col, (cx, cy + 2), (cx, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx - r // 2, cy + r), (cx + r // 2, cy + r), 2)

    elif icon_name in ("statistics", "chart", "records"):
        pygame.draw.line(surface, glow_col, (cx - r, cy + r), (cx + r, cy + r), 2)
        pygame.draw.rect(surface, glow_col, (cx - r + 2, cy + 2, 4, r - 2))
        pygame.draw.rect(surface, glow_col, (cx - 2, cy - r // 2, 4, r + r // 2))
        pygame.draw.rect(surface, glow_col, (cx + r - 6, cy - r, 4, r * 2))

    elif icon_name in ("settings", "options", "gear"):
        pygame.draw.circle(surface, glow_col, (cx, cy), r - 2, 2)
        pygame.draw.circle(surface, glow_col, (cx, cy), 3)
        for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
            rad = math.radians(ang)
            gx = cx + int((r - 2) * math.cos(rad))
            gy = cy + int((r - 2) * math.sin(rad))
            pygame.draw.circle(surface, glow_col, (gx, gy), 2)

    elif icon_name in ("manual", "book"):
        pygame.draw.line(surface, glow_col, (cx, cy - r + 2), (cx, cy + r), 2)
        pygame.draw.arc(surface, glow_col, (cx - r, cy - r + 2, r * 2, r), 0, math.pi, 2)
        pygame.draw.line(surface, glow_col, (cx - r, cy - r // 2), (cx - r, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx + r, cy - r // 2), (cx + r, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx - r, cy + r), (cx, cy + r - 2), 2)
        pygame.draw.line(surface, glow_col, (cx + r, cy + r), (cx, cy + r - 2), 2)

    elif icon_name in ("insights", "ai", "brain"):
        pts = [(cx, cy - r), (cx + r, cy - r // 3), (cx + r * 2 // 3, cy + r * 2 // 3), (cx, cy + r), (cx - r * 2 // 3, cy + r * 2 // 3), (cx - r, cy - r // 3)]
        pygame.draw.polygon(surface, (140, 200, 255) if is_active else ring_col, pts, 2)
        pygame.draw.circle(surface, GOLD_BRIGHT if is_active else ring_col, (cx, cy), 3)

    elif icon_name in ("skull", "hell"):
        pygame.draw.circle(surface, glow_col, (cx, cy - 2), r - 3)
        pygame.draw.rect(surface, glow_col, (cx - 5, cy + 3, 10, 6))
        pygame.draw.circle(surface, bg_col, (cx - 4, cy - 2), 3)
        pygame.draw.circle(surface, bg_col, (cx + 4, cy - 2), 3)

    elif icon_name in ("star",):
        pygame.draw.circle(surface, GOLD_TEXT if is_active else ring_col, (cx, cy), 4)

    elif icon_name in ("back", "exit"):
        pygame.draw.line(surface, glow_col, (cx + r - 2, cy), (cx - r + 2, cy), 2)
        pygame.draw.line(surface, glow_col, (cx - r + 2, cy), (cx - 2, cy - r // 2), 2)
        pygame.draw.line(surface, glow_col, (cx - r + 2, cy), (cx - 2, cy + r // 2), 2)

    else:
        # Default dot
        pygame.draw.circle(surface, glow_col, (cx, cy), 4)


def draw_wax_seal_stamp(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    text: str = "CLAIMED",
) -> None:
    """Draw an authentic rotated crimson wax-seal stamp."""
    font = get_font(18, bold=True)
    text_surf = font.render(f"[{text}]", True, (255, 95, 95))

    stamp_w = text_surf.get_width() + 24
    stamp_h = 32
    stamp_surf = pygame.Surface((stamp_w, stamp_h), pygame.SRCALPHA)

    # Double distressed border
    pygame.draw.rect(stamp_surf, (190, 30, 30, 230), (0, 0, stamp_w, stamp_h), width=2, border_radius=4)
    pygame.draw.rect(stamp_surf, (150, 20, 20, 160), (3, 3, stamp_w - 6, stamp_h - 6), width=1, border_radius=3)
    stamp_surf.blit(text_surf, (12, 6))

    # Rotate -12 degrees
    rot_surf = pygame.transform.rotate(stamp_surf, -12.0)
    surface.blit(rot_surf, rot_surf.get_rect(center=(cx, cy)))


def draw_tier_badge(
    surface: pygame.Surface,
    x: int,
    y: int,
    tier_text: str,
    is_battle_tag: bool = False,
) -> None:
    """Draw small tier chip (Bronze I, Silver II, Gold III) or crimson BATTLE tag."""
    font = get_font(11, bold=True)
    if is_battle_tag:
        bg_col = CRIMSON_TAG
        text_col = WHITE
    elif "Gold" in tier_text:
        bg_col = (195, 145, 30)
        text_col = (255, 245, 190)
    elif "Silver" in tier_text:
        bg_col = (120, 135, 155)
        text_col = (240, 245, 255)
    else:
        bg_col = (145, 95, 45)
        text_col = (245, 215, 190)

    t_surf = font.render(tier_text, True, text_col)
    bw = t_surf.get_width() + 10
    bh = 16
    b_rect = pygame.Rect(x, y, bw, bh)
    pygame.draw.rect(surface, bg_col, b_rect, border_radius=3)
    surface.blit(t_surf, (x + 5, y + 2))
