"""Arena-AI menu design system ("obsidian & molten gold").

Every menu screen (main menu, match setup, settings, campaign, HQ, results)
is drawn with the helpers in this module so the whole game shares one look:

  * draw_backdrop()        - art background + cached vignette, torch glow, embers,
                             gradient gold title and optional coin/level capsule
  * draw_obsidian_card()   - translucent dark panel with bronze / gold border
  * draw_menu_cards()      - vertical list of selectable cards (+ icons)
  * run_menu()             - complete keyboard/mouse/gamepad menu loop (MenuItem list)
  * draw_option_rows()     - label/value rows for settings-style screens
  * draw_button()          - pill buttons
  * draw_hint_bar()        - key-cap hints at the bottom of the screen
  * confirm_dialog()       - modal yes/no

Expensive surfaces (scrims, glows, gradient titles, card fills) are built once
and cached; fonts come from frontend.fonts (also cached).
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pygame

from backend.data.results_db import results_db
from frontend import fonts
from frontend.assets import assets
from frontend.theme import SCREEN_HEIGHT, SCREEN_WIDTH, WHITE

# ----------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------
BG_DARK = (14, 15, 26)
PANEL_DARK = (22, 23, 40)
PANEL_DARK_ALT = (17, 19, 32)
PANEL_BORDER = (140, 106, 63)          # bronze
PANEL_BORDER_LIGHT = (195, 155, 105)   # highlighted bronze bevel
PANEL_BORDER_GLOW = (255, 215, 100)    # molten-gold hover
GOLD_TEXT = (245, 197, 66)
GOLD_BRIGHT = (255, 235, 150)
GOLD_DEEP = (196, 128, 32)
EMBER_ORANGE = (255, 122, 47)
SUCCESS_GREEN = (74, 222, 128)
CRIMSON_TAG = (220, 38, 38)
SILVER_TAG = (175, 190, 210)
BRONZE_TAG = (185, 135, 75)
TEXT_WHITE = (243, 244, 246)
TEXT_MUTED = (156, 163, 175)
TEXT_GOLD_MUTED = (215, 185, 120)
P1_ACCENT = (64, 160, 235)
P2_ACCENT = (235, 80, 70)

# Layout helpers derived from the screen size
CENTER_X = SCREEN_WIDTH // 2
HEADER_H = int(SCREEN_HEIGHT * 0.15)           # title band height
FOOTER_Y = SCREEN_HEIGHT - 26                  # hint bar centre line
DESC_Y = SCREEN_HEIGHT - 66                    # description pill centre line

# Global ember particle system state: [x, y, speed_y, wobble_freq, alpha, size]
_EMBERS: List[List[float]] = []
_SURF_CACHE: Dict[tuple, pygame.Surface] = {}


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Cached font sized like the old pygame.font.Font(None, size) calls."""
    return fonts.legacy_font(size, bold=bold)


def _cached(key: tuple, builder: Callable[[], pygame.Surface]) -> pygame.Surface:
    surf = _SURF_CACHE.get(key)
    if surf is None:
        surf = builder()
        if len(_SURF_CACHE) > 400:
            _SURF_CACHE.clear()
        _SURF_CACHE[key] = surf
    return surf


# ----------------------------------------------------------------------
# Cached atmospheric layers
# ----------------------------------------------------------------------
def _build_vignette(w: int, h: int, base_alpha: int, edge_alpha: int,
                    tint: Tuple[int, int, int] = (8, 9, 18)) -> pygame.Surface:
    """Radial darkening: base_alpha in the centre rising to edge_alpha at corners."""
    sw, sh = 64, 40
    small = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for y in range(sh):
        dy = (y + 0.5) / sh * 2.0 - 1.0
        for x in range(sw):
            dx = (x + 0.5) / sw * 2.0 - 1.0
            d = min(1.0, math.sqrt(dx * dx * 0.85 + dy * dy) / 1.25)
            t = d * d * (3 - 2 * d)
            a = int(base_alpha + (edge_alpha - base_alpha) * t)
            small.set_at((x, y), (*tint, a))
    return pygame.transform.smoothscale(small, (w, h))


def get_vignette(base_alpha: int = 150, edge_alpha: int = 235) -> pygame.Surface:
    return _cached(("vignette", SCREEN_WIDTH, SCREEN_HEIGHT, base_alpha, edge_alpha),
                   lambda: _build_vignette(SCREEN_WIDTH, SCREEN_HEIGHT, base_alpha, edge_alpha))


def _build_glow(radius: int, colour: Tuple[int, int, int], strength: float) -> pygame.Surface:
    """Additive light blob: RGB surface on black, blitted with BLEND_RGB_ADD."""
    n = 48
    small = pygame.Surface((n, n))
    small.fill((0, 0, 0))
    c = (n - 1) / 2.0
    for y in range(n):
        for x in range(n):
            d = math.hypot(x - c, y - c) / c
            if d >= 1.0:
                continue
            f = (1.0 - d) ** 2.2 * strength
            small.set_at((x, y), tuple(min(255, int(ch * f)) for ch in colour))
    return pygame.transform.smoothscale(small, (radius * 2, radius * 2))


def get_glow(radius: int, colour: Tuple[int, int, int] = EMBER_ORANGE,
             strength: float = 0.35) -> pygame.Surface:
    return _cached(("glow", radius, colour, strength), lambda: _build_glow(radius, colour, strength))


def blit_glow(surface: pygame.Surface, center: Tuple[int, int], radius: int,
              colour: Tuple[int, int, int] = EMBER_ORANGE, strength: float = 0.35) -> None:
    glow = get_glow(radius, colour, strength)
    surface.blit(glow, (center[0] - radius, center[1] - radius), special_flags=pygame.BLEND_RGB_ADD)


def _build_gradient_text(text: str, size: int, top: Tuple[int, int, int],
                         bottom: Tuple[int, int, int], role: str, shadow: bool) -> pygame.Surface:
    f = fonts.font(role, size)
    mask = f.render(text, True, (255, 255, 255))
    w, h = mask.get_size()
    grad = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(grad, (*col, 255), (0, y), (w, y))
    text_surf = mask.copy()
    text_surf.blit(grad, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if not shadow:
        return text_surf
    pad = 4
    out = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    dark = f.render(text, True, (0, 0, 0))
    dark.set_alpha(150)
    for ox, oy in ((0, 3), (2, 3), (-2, 3), (0, 2)):
        out.blit(dark, (pad + ox, pad + oy))
    out.blit(text_surf, (pad, pad))
    return out


def render_title(text: str, size: int = 46, top: Tuple[int, int, int] = GOLD_BRIGHT,
                 bottom: Tuple[int, int, int] = GOLD_DEEP, role: str = "display",
                 shadow: bool = True) -> pygame.Surface:
    """Molten-gold vertical-gradient title text with soft drop shadow (cached)."""
    return _cached(("title", text, size, top, bottom, role, shadow),
                   lambda: _build_gradient_text(text, size, top, bottom, role, shadow))


def render_text(text: str, size: int, colour, role: str = "body") -> pygame.Surface:
    """Cached plain text render (for static labels drawn every frame)."""
    return _cached(("text", text, size, tuple(colour), role),
                   lambda: fonts.font(role, size).render(text, True, colour))


def draw_text(surface: pygame.Surface, text: str, size: int, colour, *, role: str = "body",
              center: Optional[Tuple[int, int]] = None, midleft: Optional[Tuple[int, int]] = None,
              midright: Optional[Tuple[int, int]] = None, topleft: Optional[Tuple[int, int]] = None,
              midtop: Optional[Tuple[int, int]] = None, shadow: bool = False,
              max_width: Optional[int] = None) -> pygame.Rect:
    """Render + blit text with one anchor; optional 1px shadow and width clamp."""
    surf = render_text(text, size, colour, role)
    if max_width and surf.get_width() > max_width:
        while len(text) > 4 and render_text(text + "…", size, colour, role).get_width() > max_width:
            text = text[:-1]
        surf = render_text(text.rstrip() + "…", size, colour, role)
    anchor = {}
    for name, val in (("center", center), ("midleft", midleft), ("midright", midright),
                      ("topleft", topleft), ("midtop", midtop)):
        if val is not None:
            anchor[name] = val
    rect = surf.get_rect(**(anchor or {"topleft": (0, 0)}))
    if shadow:
        sh = render_text(text, size, (0, 0, 0), role)
        surface.blit(sh, rect.move(1, 2))
    surface.blit(surf, rect)
    return rect


def init_embers_if_needed():
    """Seed floating ambient ember particles."""
    if not _EMBERS:
        rng = random.Random(7)
        for _ in range(36):
            _EMBERS.append([
                rng.uniform(15, SCREEN_WIDTH - 15), rng.uniform(40, SCREEN_HEIGHT),
                rng.uniform(0.4, 1.4), rng.uniform(0.02, 0.05),
                rng.randint(120, 230), rng.choice([1, 2, 2, 3]),
            ])


def _draw_embers(surface: pygame.Surface, frame_counter: int) -> None:
    init_embers_if_needed()
    for p in _EMBERS:
        p[1] -= p[2]
        p[0] += math.sin(frame_counter * p[3]) * 0.4
        if p[1] < 30:
            p[1] = SCREEN_HEIGHT + random.uniform(5, 30)
            p[0] = random.uniform(15, SCREEN_WIDTH - 15)
        flicker = 0.75 + 0.25 * math.sin(frame_counter * 0.2 + p[0])
        col = (255, int(130 * flicker + 20), int(40 * flicker))
        x, y, r = int(p[0]), int(p[1]), int(p[5])
        if r >= 2:
            blit_glow(surface, (x, y), r * 4, EMBER_ORANGE, 0.25)
        pygame.draw.circle(surface, col, (x, y), r)


_ECON_CACHE = {"t": 0.0, "pid": None, "coins": 0, "lvl": 1}


def _economy_values(player_id: Optional[int]) -> Tuple[int, int]:
    """Coins and best fighter level, re-read from the DB at most once a second."""
    now = time.time()
    if now - _ECON_CACHE["t"] < 1.0 and _ECON_CACHE["pid"] == player_id:
        return _ECON_CACHE["coins"], _ECON_CACHE["lvl"]
    coins, lvl = 0, 1
    p_id = player_id
    try:
        if p_id is None:
            def_p = results_db.get_default_player()
            if def_p:
                p_id = int(def_p["player_id"])
        if p_id is not None:
            prog = results_db.get_or_create_progress(p_id)
            coins = prog.get("coins", 0)
            lvl = max(prog.get(f"{c}_level", 1) for c in ("crimson", "steel", "shadow", "golden"))
    except Exception:
        pass
    _ECON_CACHE.update(t=now, pid=player_id, coins=coins, lvl=lvl)
    return coins, lvl


def invalidate_economy_cache() -> None:
    _ECON_CACHE["t"] = 0.0


def _draw_economy(surface: pygame.Surface, player_id: Optional[int]) -> None:
    coins, max_lvl = _economy_values(player_id)
    coin_surf = render_text(f"{coins:,}", 17, WHITE, "ui")
    cap_w, cap_h = coin_surf.get_width() + 46, 30
    badge_cx, badge_cy = SCREEN_WIDTH - 46, 36
    cap = pygame.Rect(badge_cx - 34 - cap_w, badge_cy - cap_h // 2, cap_w, cap_h)
    pygame.draw.rect(surface, (16, 18, 30), cap, border_radius=15)
    pygame.draw.rect(surface, PANEL_BORDER, cap, width=1, border_radius=15)
    ccx, ccy = cap.x + 16, cap.centery
    pygame.draw.circle(surface, GOLD_DEEP, (ccx, ccy), 9)
    pygame.draw.circle(surface, GOLD_TEXT, (ccx, ccy), 7)
    pygame.draw.circle(surface, GOLD_BRIGHT, (ccx - 2, ccy - 2), 2)
    surface.blit(coin_surf, (ccx + 14, ccy - coin_surf.get_height() // 2))

    pygame.draw.circle(surface, (16, 18, 30), (badge_cx, badge_cy), 20)
    arc = pygame.Rect(badge_cx - 20, badge_cy - 20, 40, 40)
    pygame.draw.arc(surface, (40, 50, 75), arc, 0, math.pi * 2, 2)
    pygame.draw.arc(surface, (60, 220, 240), arc, -math.pi / 2, math.pi * 1.1, 2)
    draw_text(surface, "LV", 10, (160, 200, 240), role="ui", center=(badge_cx, badge_cy - 7))
    draw_text(surface, str(max_lvl), 15, WHITE, role="ui", center=(badge_cx, badge_cy + 6))


def draw_header(surface: pygame.Surface, title: str, sub_title: Optional[str] = None,
                y: int = 18, size: int = 46) -> int:
    """Gradient gold title with fading ornament rules. Returns the y below the header."""
    t = render_title(title.upper(), size)
    rect = t.get_rect(midtop=(CENTER_X, y))
    surface.blit(t, rect)
    line_y = rect.centery + 2
    for side in (-1, 1):
        x0 = rect.left - 18 if side < 0 else rect.right + 18
        length = 120
        for i in range(length):
            a = 1.0 - i / length
            col = tuple(int(c * a + 14 * (1 - a)) for c in GOLD_TEXT)
            px = x0 + side * i
            surface.set_at((px, line_y), col)
        d = 5
        pts = [(x0, line_y - d), (x0 + d, line_y), (x0, line_y + d), (x0 - d, line_y)]
        pygame.draw.polygon(surface, GOLD_TEXT, pts)
    bottom = rect.bottom
    if sub_title:
        r = draw_text(surface, sub_title, 15, TEXT_MUTED, role="ui", midtop=(CENTER_X, bottom))
        bottom = r.bottom
    return bottom + 6


def draw_backdrop(surface: pygame.Surface, frame_counter: int = 0, title: Optional[str] = None,
                  sub_title: Optional[str] = None, bg: str = "menu",
                  player_id: Optional[int] = None, show_economy: bool = False,
                  dim: int = 150, embers: bool = True, title_size: int = 46,
                  header_y: int = 18) -> int:
    """Shared screen background. Returns the y coordinate below the header."""
    if bg == "menu":
        surface.blit(assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT)), (0, 0))
    elif bg == "victory":
        surface.blit(assets.get_victory((SCREEN_WIDTH, SCREEN_HEIGHT)), (0, 0))
    elif bg == "defeat":
        surface.blit(assets.get_defeat((SCREEN_WIDTH, SCREEN_HEIGHT)), (0, 0))
    elif bg == "draw":
        surface.blit(assets.get_draw_screen((SCREEN_WIDTH, SCREEN_HEIGHT)), (0, 0))
    else:
        surface.blit(assets.get_arena(bg, size=(SCREEN_WIDTH, SCREEN_HEIGHT)), (0, 0))
    surface.blit(get_vignette(dim, min(250, dim + 85)), (0, 0))
    blit_glow(surface, (-20, SCREEN_HEIGHT - 60), 260, EMBER_ORANGE, 0.22)
    blit_glow(surface, (SCREEN_WIDTH + 20, SCREEN_HEIGHT - 60), 260, EMBER_ORANGE, 0.22)
    if embers:
        _draw_embers(surface, frame_counter)
    if show_economy:
        _draw_economy(surface, player_id)
    if title:
        return draw_header(surface, title, sub_title, y=header_y, size=title_size)
    return 0


def draw_dark_fantasy_backdrop(
    surface: pygame.Surface,
    frame_counter: int = 0,
    title_text: str = "ARENA-AI",
    player_id: Optional[int] = None,
    sub_title: Optional[str] = None,
    show_economy: bool = True,
    arena_bg_name: str = "arena_sky_colosseum",
) -> None:
    """Backwards-compatible wrapper used by the campaign / HQ screens."""
    draw_backdrop(surface, frame_counter, title=title_text, sub_title=sub_title,
                  bg=arena_bg_name, player_id=player_id, show_economy=show_economy,
                  title_size=40)


# ----------------------------------------------------------------------
# Panels & widgets
# ----------------------------------------------------------------------
def _card_fill(w: int, h: int, radius: int, colour: Tuple[int, int, int], alpha: int) -> pygame.Surface:
    def build():
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s, (*colour, alpha), (0, 0, w, h), border_radius=radius)
        # subtle top sheen
        sheen_h = max(2, h // 2)
        sheen = pygame.Surface((w, sheen_h), pygame.SRCALPHA)
        for y in range(sheen_h):
            a = int(18 * (1 - y / sheen_h))
            pygame.draw.line(sheen, (255, 255, 255, a), (0, y), (w, y))
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        sheen_full = pygame.Surface((w, h), pygame.SRCALPHA)
        sheen_full.blit(sheen, (0, 0))
        sheen_full.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        s.blit(sheen_full, (0, 0))
        return s
    return _cached(("card", w, h, radius, colour, alpha), build)


def draw_obsidian_card(
    surface: pygame.Surface,
    rect: pygame.Rect,
    is_selected: bool = False,
    is_hovered: bool = False,
    border_radius: int = 8,
    bg_color: Tuple[int, int, int] = PANEL_DARK,
    border_color: Tuple[int, int, int] = PANEL_BORDER,
) -> None:
    """Dark translucent panel with a thin bronze border, or a gold glow when active."""
    rect = pygame.Rect(rect)
    if rect.width <= 0 or rect.height <= 0:
        return
    active = is_selected or is_hovered
    surface.blit(_card_fill(rect.width, rect.height, border_radius, tuple(bg_color[:3]),
                            235 if active else 205), rect.topleft)
    if active:
        glow_rect = rect.inflate(8, 8)
        ring = _cached(("ring", glow_rect.width, glow_rect.height, border_radius),
                       lambda: _build_ring(glow_rect.width, glow_rect.height, border_radius + 4))
        surface.blit(ring, glow_rect.topleft)
        pygame.draw.rect(surface, PANEL_BORDER_GLOW, rect, width=2, border_radius=border_radius)
    else:
        pygame.draw.rect(surface, border_color, rect, width=1, border_radius=border_radius)
        pygame.draw.line(surface, (*PANEL_BORDER_LIGHT,), (rect.x + border_radius, rect.y + 1),
                         (rect.right - border_radius, rect.y + 1), 1)


def _build_ring(w: int, h: int, radius: int) -> pygame.Surface:
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(s, (245, 197, 66, 60), (0, 0, w, h), width=4, border_radius=radius)
    return s


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
    """Vertical list of obsidian menu cards with hover/selection states."""
    rects: List[pygame.Rect] = []
    for i, item in enumerate(items):
        is_sel = (i == selected)
        rect = pygame.Rect((SCREEN_WIDTH - width) // 2, start_y + i * step_y, width, height)
        rects.append(rect)
        draw_obsidian_card(surface, rect, is_selected=is_sel, border_radius=10)
        text_x = rect.x + 24
        if icons and i < len(icons) and icons[i]:
            draw_emblem_icon(surface, rect.x + 30, rect.centery, icons[i], is_active=is_sel,
                             radius=min(18, height // 2 - 4))
            text_x = rect.x + 60
        text_surf = font.render(item, True, GOLD_BRIGHT if is_sel else TEXT_WHITE)
        surface.blit(text_surf, text_surf.get_rect(midleft=(text_x, rect.centery)))
        if is_sel:
            ax, ay = rect.right - 24, rect.centery
            pygame.draw.polygon(surface, GOLD_TEXT, [(ax - 6, ay - 7), (ax + 1, ay), (ax - 6, ay + 7)])
    return rects


def draw_menu_cards(surface: pygame.Surface, labels: Sequence[str], selected: int, *,
                    top: int, width: int = 440, height: int = 46, gap: int = 10,
                    icons: Optional[Sequence[Optional[str]]] = None, size: int = 21,
                    disabled: Optional[Sequence[bool]] = None,
                    center_x: int = CENTER_X) -> List[pygame.Rect]:
    """Modern menu card list (real-pixel font size). Returns hit rects."""
    rects = []
    f = fonts.font("ui", size)
    for i, label in enumerate(labels):
        is_sel = i == selected
        off = bool(disabled and i < len(disabled) and disabled[i])
        rect = pygame.Rect(center_x - width // 2, top + i * (height + gap), width, height)
        rects.append(rect)
        draw_obsidian_card(surface, rect, is_selected=is_sel and not off, border_radius=10)
        if is_sel and not off:
            bar = pygame.Rect(rect.x + 1, rect.y + 8, 4, rect.height - 16)
            pygame.draw.rect(surface, GOLD_TEXT, bar, border_radius=2)
        text_x = rect.x + 26
        if icons and i < len(icons) and icons[i]:
            draw_emblem_icon(surface, rect.x + 32, rect.centery, icons[i], is_active=is_sel and not off,
                             radius=min(17, height // 2 - 5))
            text_x = rect.x + 62
        col = (110, 112, 125) if off else (GOLD_BRIGHT if is_sel else TEXT_WHITE)
        t = f.render(label, True, col)
        surface.blit(t, t.get_rect(midleft=(text_x, rect.centery)))
        if is_sel and not off:
            ax, ay = rect.right - 24, rect.centery
            pygame.draw.polygon(surface, GOLD_TEXT, [(ax - 6, ay - 7), (ax + 1, ay), (ax - 6, ay + 7)])
    return rects


def draw_description_pill(
    surface: pygame.Surface,
    text: str,
    y: int = DESC_Y,
    font: Optional[pygame.font.Font] = None,
) -> None:
    """Bottom description capsule with a subtle bronze frame."""
    if not text:
        return
    f = font or fonts.font("body", 15)
    desc_surf = f.render(text, True, TEXT_GOLD_MUTED)
    max_w = SCREEN_WIDTH - 80
    if desc_surf.get_width() > max_w:
        desc_surf = pygame.transform.smoothscale(
            desc_surf, (max_w, int(desc_surf.get_height() * max_w / desc_surf.get_width())))
    desc_rect = desc_surf.get_rect(center=(CENTER_X, y))
    pill_rect = desc_rect.inflate(44, 16)
    surface.blit(_card_fill(pill_rect.width, pill_rect.height, pill_rect.height // 2, (12, 13, 24), 215),
                 pill_rect.topleft)
    pygame.draw.rect(surface, PANEL_BORDER, pill_rect, width=1, border_radius=pill_rect.height // 2)
    surface.blit(desc_surf, desc_rect)


_ARROWS = {"↑": 0, "→": 1, "↓": 2, "←": 3}


def _arrow_glyphs(label: str) -> Optional[List[int]]:
    chars = [c for c in label if not c.isspace()]
    if chars and all(c in _ARROWS for c in chars):
        return [_ARROWS[c] for c in chars]
    return None


def _keycap_width(label: str) -> int:
    arrows = _arrow_glyphs(label)
    if arrows:
        return 10 + 12 * len(arrows)
    return max(22, render_text(label, 12, (225, 228, 238), "ui").get_width() + 12)


def _draw_arrow(surface: pygame.Surface, center: Tuple[int, int], direction: int, col) -> None:
    cx, cy = center
    s = 4
    pts = {0: [(cx, cy - s), (cx + s, cy + s - 1), (cx - s, cy + s - 1)],
           2: [(cx, cy + s), (cx + s, cy - s + 1), (cx - s, cy - s + 1)],
           1: [(cx + s, cy), (cx - s + 1, cy - s), (cx - s + 1, cy + s)],
           3: [(cx - s, cy), (cx + s - 1, cy - s), (cx + s - 1, cy + s)]}[direction]
    pygame.draw.polygon(surface, col, pts)


def draw_keycap(surface: pygame.Surface, label: str, midleft: Tuple[int, int]) -> pygame.Rect:
    """Keyboard key-cap. Arrow characters (↑→↓←) are drawn as vector triangles."""
    w = _keycap_width(label)
    rect = pygame.Rect(0, 0, w, 20)
    rect.midleft = midleft
    pygame.draw.rect(surface, (40, 43, 60), rect, border_radius=5)
    pygame.draw.rect(surface, (90, 95, 120), rect, width=1, border_radius=5)
    pygame.draw.line(surface, (25, 27, 40), (rect.x + 3, rect.bottom - 1), (rect.right - 4, rect.bottom - 1))
    arrows = _arrow_glyphs(label)
    if arrows:
        x = rect.x + 11
        for d in arrows:
            _draw_arrow(surface, (x, rect.centery - 1), d, (225, 228, 238))
            x += 12
    else:
        t = render_text(label, 12, (225, 228, 238), "ui")
        surface.blit(t, t.get_rect(center=(rect.centerx, rect.centery - 1)))
    return rect


def draw_hint_bar(surface: pygame.Surface, hints: Sequence[Tuple[str, str]], y: int = FOOTER_Y) -> None:
    """Key-cap hints, e.g. [("↑↓", "Select"), ("Enter", "Confirm"), ("Esc", "Back")]."""
    parts = []
    total = 0
    for key, label in hints:
        kw = _keycap_width(key)
        lt = render_text(label, 13, TEXT_MUTED, "ui")
        parts.append((key, kw, lt))
        total += kw + 6 + lt.get_width() + 18
    total -= 18
    x = CENTER_X - total // 2
    for key, kw, lt in parts:
        draw_keycap(surface, key, (x, y))
        x += kw + 6
        surface.blit(lt, lt.get_rect(midleft=(x, y)))
        x += lt.get_width() + 18


def draw_button(surface: pygame.Surface, rect: pygame.Rect, text: str, selected: bool = False,
                disabled: bool = False, accent: Tuple[int, int, int] = GOLD_TEXT,
                size: int = 17, primary: bool = False) -> None:
    """Rounded pill button. Primary buttons are filled with the accent colour."""
    rect = pygame.Rect(rect)
    radius = rect.height // 2
    if disabled:
        pygame.draw.rect(surface, (30, 33, 46), rect, border_radius=radius)
        pygame.draw.rect(surface, (55, 60, 75), rect, width=1, border_radius=radius)
        draw_text(surface, text, size, (110, 115, 130), role="ui", center=rect.center)
        return
    if primary or selected:
        fill = accent if primary else (36, 38, 58)
        if primary and not selected:
            fill = tuple(int(c * 0.72) for c in accent)
        pygame.draw.rect(surface, fill, rect, border_radius=radius)
        if selected:
            ring = rect.inflate(6, 6)
            pygame.draw.rect(surface, GOLD_BRIGHT, ring, width=2, border_radius=ring.height // 2)
        txt_col = (20, 16, 10) if primary else GOLD_BRIGHT
    else:
        surface.blit(_card_fill(rect.width, rect.height, radius, PANEL_DARK, 225), rect.topleft)
        pygame.draw.rect(surface, PANEL_BORDER, rect, width=1, border_radius=radius)
        txt_col = TEXT_WHITE
    draw_text(surface, text, size, txt_col, role="ui", center=rect.center)


def draw_toggle(surface: pygame.Surface, center: Tuple[int, int], on: bool) -> None:
    track = pygame.Rect(0, 0, 44, 22)
    track.center = center
    pygame.draw.rect(surface, (52, 168, 92) if on else (60, 64, 82), track, border_radius=11)
    knob_x = track.right - 11 if on else track.left + 11
    pygame.draw.circle(surface, (245, 246, 250), (knob_x, track.centery), 8)


def draw_slider(surface: pygame.Surface, rect: pygame.Rect, value: float) -> None:
    value = max(0.0, min(1.0, value))
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, (40, 44, 62), rect, border_radius=rect.height // 2)
    fill = pygame.Rect(rect.x, rect.y, int(rect.width * value), rect.height)
    if fill.width > 0:
        pygame.draw.rect(surface, GOLD_TEXT, fill, border_radius=rect.height // 2)
    pygame.draw.circle(surface, GOLD_BRIGHT, (rect.x + int(rect.width * value), rect.centery), rect.height + 2)


@dataclass
class OptionRow:
    """One settings row. kind: 'toggle' | 'slider' | 'choice' | 'action' | 'header'."""
    key: str
    label: str
    kind: str = "action"
    value: object = None
    note: str = ""


def draw_option_rows(surface: pygame.Surface, rows: Sequence[OptionRow], selected: int, *,
                     top: int, width: int = 620, row_h: int = 38, gap: int = 6,
                     center_x: int = CENTER_X) -> List[Optional[pygame.Rect]]:
    """Label on the left, control on the right. Header rows are not selectable (rect None)."""
    rects: List[Optional[pygame.Rect]] = []
    y = top
    for i, row in enumerate(rows):
        if row.kind == "header":
            draw_text(surface, row.label.upper(), 13, TEXT_GOLD_MUTED, role="ui",
                      midleft=(center_x - width // 2 + 6, y + 12))
            rects.append(None)
            y += 26
            continue
        rect = pygame.Rect(center_x - width // 2, y, width, row_h)
        rects.append(rect)
        is_sel = i == selected
        draw_obsidian_card(surface, rect, is_selected=is_sel, border_radius=8)
        draw_text(surface, row.label, 17, GOLD_BRIGHT if is_sel else TEXT_WHITE, role="ui",
                  midleft=(rect.x + 18, rect.centery))
        right = rect.right - 18
        if row.kind == "toggle":
            draw_toggle(surface, (right - 22, rect.centery), bool(row.value))
        elif row.kind == "slider":
            v = float(row.value or 0.0)
            draw_text(surface, f"{int(round(v * 100))}%", 15, TEXT_WHITE, role="ui",
                      midright=(right, rect.centery))
            draw_slider(surface, pygame.Rect(right - 200, rect.centery - 3, 140, 6), v)
        elif row.kind == "choice":
            txt = str(row.value)
            r = draw_text(surface, txt, 16, GOLD_TEXT if is_sel else TEXT_WHITE, role="ui",
                          midright=(right - 18, rect.centery))
            col = GOLD_TEXT if is_sel else (110, 115, 135)
            ax, ay = right - 6, rect.centery
            pygame.draw.polygon(surface, col, [(ax - 5, ay - 6), (ax + 1, ay), (ax - 5, ay + 6)])
            bx = r.left - 12
            pygame.draw.polygon(surface, col, [(bx + 5, ay - 6), (bx - 1, ay), (bx + 5, ay + 6)])
        elif row.kind == "action":
            if row.value:
                draw_text(surface, str(row.value), 15, TEXT_MUTED, role="ui", midright=(right - 16, rect.centery))
            ax, ay = right - 2, rect.centery
            pygame.draw.polygon(surface, GOLD_TEXT if is_sel else (110, 115, 135),
                                [(ax - 6, ay - 6), (ax, ay), (ax - 6, ay + 6)])
        elif row.kind == "key":
            cap = str(row.value)
            t = render_text(cap, 14, (20, 16, 10) if is_sel else TEXT_WHITE, "ui")
            box = pygame.Rect(0, 0, max(56, t.get_width() + 20), row_h - 12)
            box.midright = (right, rect.centery)
            pygame.draw.rect(surface, GOLD_TEXT if is_sel else (44, 47, 66), box, border_radius=6)
            pygame.draw.rect(surface, (95, 100, 125), box, width=1, border_radius=6)
            surface.blit(t, t.get_rect(center=box.center))
        y += row_h + gap
    return rects


def first_selectable(rows: Sequence[OptionRow], start: int = 0, step: int = 1) -> int:
    n = len(rows)
    i = start % n
    for _ in range(n):
        if rows[i].kind != "header":
            return i
        i = (i + step) % n
    return 0


# ----------------------------------------------------------------------
# Generic menu loop
# ----------------------------------------------------------------------
@dataclass
class MenuItem:
    key: str
    label: str
    desc: str = ""
    icon: Optional[str] = None
    enabled: bool = True


def safe_set_cursor(cursor) -> None:
    try:
        pygame.mouse.set_cursor(cursor)
    except Exception:
        pass


def _play(name: str) -> None:
    try:
        from frontend.audio import audio
        audio.play_sfx(name)
    except Exception:
        pass


MENU_HINTS = [("↑ ↓", "Select"), ("Enter", "Confirm"), ("Esc", "Back")]


def run_menu(surface: pygame.Surface, clock, title: str, items: Sequence[MenuItem], *,
             subtitle: Optional[str] = None, esc_value: Optional[str] = "back",
             on_escape: Optional[Callable[[], Optional[str]]] = None,
             bg: str = "menu", player_id: Optional[int] = None, show_economy: bool = False,
             hints: Optional[Sequence[Tuple[str, str]]] = None, width: int = 440,
             initial: int = 0, card_h: int = 46, gap: int = 10,
             overlay: Optional[Callable[[pygame.Surface, int], None]] = None,
             quit_value: Optional[str] = None) -> Optional[str]:
    """Shared vertical menu (keyboard, mouse, gamepad d-pad via SDL key events).

    Returns the selected item's key, `esc_value` on Esc (or whatever
    `on_escape()` returns, if given; returning None keeps the menu open), or
    `quit_value` (default esc_value) when the window is closed.
    """
    try:
        from frontend.audio import audio
        audio.play_music("music_menu")
    except Exception:
        pass
    if quit_value is None:
        quit_value = esc_value
    selected = max(0, min(initial, len(items) - 1))
    frame = 0
    n = len(items)
    content_top = HEADER_H + 20
    content_bottom = DESC_Y - 30
    stack_h = n * card_h + (n - 1) * gap
    top = content_top + max(0, (content_bottom - content_top - stack_h) // 2)
    rects = [pygame.Rect(CENTER_X - width // 2, top + i * (card_h + gap), width, card_h) for i in range(n)]
    hints = hints or MENU_HINTS
    last_mouse = pygame.mouse.get_pos()

    def move(delta: int) -> int:
        idx = selected
        for _ in range(n):
            idx = (idx + delta) % n
            if items[idx].enabled:
                break
        return idx

    while True:
        frame += 1
        mouse_pos = pygame.mouse.get_pos()
        if mouse_pos != last_mouse:
            last_mouse = mouse_pos
            for i, r in enumerate(rects):
                if r.collidepoint(mouse_pos) and items[i].enabled and i != selected:
                    selected = i
                    _play("menu_hover")
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return quit_value
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    _play("menu_hover")
                    selected = move(-1)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    _play("menu_hover")
                    selected = move(1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    if items[selected].enabled:
                        _play("menu_select")
                        return items[selected].key
                    _play("menu_error")
                elif event.key == pygame.K_ESCAPE:
                    _play("menu_back")
                    if on_escape is not None:
                        res = on_escape()
                        if res is not None:
                            return res
                    else:
                        return esc_value
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(event.pos) and items[i].enabled:
                        _play("menu_select")
                        return items[i].key

        draw_backdrop(surface, frame, title=title, sub_title=subtitle, bg=bg,
                      player_id=player_id, show_economy=show_economy)
        if overlay is not None:
            overlay(surface, frame)
        rects = draw_menu_cards(surface, [it.label for it in items], selected, top=top,
                                width=width, height=card_h, gap=gap,
                                icons=[it.icon for it in items],
                                disabled=[not it.enabled for it in items])
        draw_description_pill(surface, items[selected].desc)
        draw_hint_bar(surface, hints)
        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def confirm_dialog(surface: pygame.Surface, clock, title: str, message: str,
                   confirm_label: str = "Yes", cancel_label: str = "Cancel",
                   default_confirm: bool = False, danger: bool = False) -> bool:
    """Modal yes/no over a frozen, darkened copy of the current frame."""
    base = surface.copy()
    shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    shade.fill((5, 6, 12, 170))
    base.blit(shade, (0, 0))
    choice = 0 if default_confirm else 1  # 0 = confirm, 1 = cancel
    box = pygame.Rect(0, 0, 460, 210)
    box.center = (CENTER_X, SCREEN_HEIGHT // 2)
    btn_w, btn_h = 150, 42
    b_yes = pygame.Rect(box.centerx - btn_w - 12, box.bottom - btn_h - 24, btn_w, btn_h)
    b_no = pygame.Rect(box.centerx + 12, box.bottom - btn_h - 24, btn_w, btn_h)
    accent = (225, 70, 60) if danger else GOLD_TEXT
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB, pygame.K_a, pygame.K_d):
                    choice = 1 - choice
                    _play("menu_hover")
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    _play("menu_select" if choice == 0 else "menu_back")
                    return choice == 0
                elif event.key in (pygame.K_y,):
                    return True
                elif event.key in (pygame.K_ESCAPE, pygame.K_n):
                    _play("menu_back")
                    return False
            if event.type == pygame.MOUSEMOTION:
                if b_yes.collidepoint(event.pos):
                    choice = 0
                elif b_no.collidepoint(event.pos):
                    choice = 1
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if b_yes.collidepoint(event.pos):
                    return True
                if b_no.collidepoint(event.pos):
                    return False
        surface.blit(base, (0, 0))
        draw_obsidian_card(surface, box, is_selected=True, border_radius=14, bg_color=(18, 19, 32))
        t = render_title(title.upper(), 34)
        surface.blit(t, t.get_rect(midtop=(box.centerx, box.y + 14)))
        draw_text(surface, message, 16, TEXT_WHITE, role="body", center=(box.centerx, box.y + 92),
                  max_width=box.width - 40)
        draw_button(surface, b_yes, confirm_label, selected=choice == 0, accent=accent, primary=True)
        draw_button(surface, b_no, cancel_label, selected=choice == 1)
        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


# ----------------------------------------------------------------------
# Bars, emblems, stamps
# ----------------------------------------------------------------------
def draw_segmented_bar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    current: int,
    target: int,
    fill_color: Tuple[int, int, int] = GOLD_TEXT,
    bg_color: Tuple[int, int, int] = (30, 32, 48),
    segments: int = 8,
) -> None:
    """Segmented progress bar."""
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
        pygame.draw.line(surface, (255, 245, 180), (s_rect.x, s_rect.y), (s_rect.right - 1, s_rect.y), 1)


def draw_emblem_icon(
    surface: pygame.Surface,
    cx: int,
    cy: int,
    icon_name: str,
    is_active: bool = True,
    radius: int = 24,
) -> None:
    """Circular metallic emblem badge with a vector glyph."""
    ring_col = PANEL_BORDER_LIGHT if is_active else (70, 75, 95)
    bg_col = (20, 22, 34) if is_active else (15, 16, 24)
    glow_col = GOLD_TEXT if is_active else (120, 125, 140)

    pygame.draw.circle(surface, bg_col, (cx, cy), radius)
    pygame.draw.circle(surface, ring_col, (cx, cy), radius, 2)
    pygame.draw.circle(surface, (bg_col[0] + 15, bg_col[1] + 15, bg_col[2] + 20), (cx, cy), radius - 3, 1)

    r = max(4, radius - 8)
    if icon_name in ("swords", "wins", "combat", "start", "quick"):
        pygame.draw.line(surface, glow_col, (cx - r, cy - r), (cx + r, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx + r, cy - r), (cx - r, cy + r), 2)
        pygame.draw.circle(surface, GOLD_BRIGHT if is_active else ring_col, (cx, cy), 3)
    elif icon_name in ("shield", "blocks", "guard", "hq"):
        pts = [(cx, cy - r), (cx + r, cy - r // 2), (cx + r * 2 // 3, cy + r), (cx, cy + r + 2),
               (cx - r * 2 // 3, cy + r), (cx - r, cy - r // 2)]
        pygame.draw.polygon(surface, glow_col, pts, 2)
    elif icon_name in ("flame", "specials", "rumble"):
        pts = [(cx, cy + r), (cx + r, cy + r // 2), (cx + r // 2, cy), (cx, cy - r),
               (cx - r // 2, cy - r // 4), (cx - r, cy + r // 2)]
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
        pts = [(cx - r, cy + r - 2), (cx - r, cy - r // 3), (cx - r // 2, cy + 2), (cx, cy - r),
               (cx + r // 2, cy + 2), (cx + r, cy - r // 3), (cx + r, cy + r - 2)]
        pygame.draw.polygon(surface, GOLD_TEXT if is_active else ring_col, pts, 2)
    elif icon_name in ("tutorial", "target"):
        pygame.draw.circle(surface, glow_col, (cx, cy), r, 2)
        pygame.draw.circle(surface, glow_col, (cx, cy), max(2, r // 2), 2)
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
        pygame.draw.circle(surface, glow_col, (cx, cy), max(3, r - 2), 2)
        pygame.draw.circle(surface, glow_col, (cx, cy), 3)
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            pygame.draw.circle(surface, glow_col, (cx + int((r - 2) * math.cos(rad)),
                                                   cy + int((r - 2) * math.sin(rad))), 2)
    elif icon_name in ("manual", "book"):
        pygame.draw.line(surface, glow_col, (cx, cy - r + 2), (cx, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx - r, cy - r // 2), (cx - r, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx + r, cy - r // 2), (cx + r, cy + r), 2)
        pygame.draw.line(surface, glow_col, (cx - r, cy - r // 2), (cx, cy - r + 2), 2)
        pygame.draw.line(surface, glow_col, (cx + r, cy - r // 2), (cx, cy - r + 2), 2)
        pygame.draw.line(surface, glow_col, (cx - r, cy + r), (cx, cy + r - 2), 2)
        pygame.draw.line(surface, glow_col, (cx + r, cy + r), (cx, cy + r - 2), 2)
    elif icon_name in ("insights", "ai", "brain"):
        pts = [(cx, cy - r), (cx + r, cy - r // 3), (cx + r * 2 // 3, cy + r * 2 // 3), (cx, cy + r),
               (cx - r * 2 // 3, cy + r * 2 // 3), (cx - r, cy - r // 3)]
        pygame.draw.polygon(surface, (140, 200, 255) if is_active else ring_col, pts, 2)
        pygame.draw.circle(surface, GOLD_BRIGHT if is_active else ring_col, (cx, cy), 3)
    elif icon_name in ("versus", "local", "duo"):
        pygame.draw.circle(surface, P1_ACCENT if is_active else ring_col, (cx - r // 2, cy - 2), max(3, r // 2), 2)
        pygame.draw.circle(surface, P2_ACCENT if is_active else ring_col, (cx + r // 2, cy - 2), max(3, r // 2), 2)
        pygame.draw.line(surface, glow_col, (cx - r, cy + r - 2), (cx + r, cy + r - 2), 2)
    elif icon_name in ("controls", "gamepad", "keys"):
        body = pygame.Rect(cx - r, cy - r // 2, r * 2, r)
        pygame.draw.rect(surface, glow_col, body, 2, border_radius=r // 2)
        pygame.draw.line(surface, glow_col, (cx - r // 2 - 3, cy), (cx - r // 2 + 3, cy), 2)
        pygame.draw.line(surface, glow_col, (cx - r // 2, cy - 3), (cx - r // 2, cy + 3), 2)
        pygame.draw.circle(surface, glow_col, (cx + r // 2, cy), 2)
    elif icon_name in ("skull", "hell"):
        pygame.draw.circle(surface, glow_col, (cx, cy - 2), max(3, r - 3))
        pygame.draw.rect(surface, glow_col, (cx - 5, cy + 3, 10, 6))
        pygame.draw.circle(surface, bg_col, (cx - 4, cy - 2), 3)
        pygame.draw.circle(surface, bg_col, (cx + 4, cy - 2), 3)
    elif icon_name in ("star",):
        pygame.draw.circle(surface, GOLD_TEXT if is_active else ring_col, (cx, cy), 4)
    elif icon_name in ("back", "exit", "quit"):
        pygame.draw.line(surface, glow_col, (cx + r - 2, cy), (cx - r + 2, cy), 2)
        pygame.draw.line(surface, glow_col, (cx - r + 2, cy), (cx - 2, cy - r // 2), 2)
        pygame.draw.line(surface, glow_col, (cx - r + 2, cy), (cx - 2, cy + r // 2), 2)
    else:
        pygame.draw.circle(surface, glow_col, (cx, cy), 4)


def draw_wax_seal_stamp(surface: pygame.Surface, cx: int, cy: int, text: str = "CLAIMED") -> None:
    """Rotated crimson wax-seal stamp."""
    text_surf = fonts.font("ui", 13).render(f"[{text}]", True, (255, 95, 95))
    stamp_w = text_surf.get_width() + 24
    stamp_h = 32
    stamp_surf = pygame.Surface((stamp_w, stamp_h), pygame.SRCALPHA)
    pygame.draw.rect(stamp_surf, (190, 30, 30, 230), (0, 0, stamp_w, stamp_h), width=2, border_radius=4)
    pygame.draw.rect(stamp_surf, (150, 20, 20, 160), (3, 3, stamp_w - 6, stamp_h - 6), width=1, border_radius=3)
    stamp_surf.blit(text_surf, text_surf.get_rect(center=(stamp_w // 2, stamp_h // 2)))
    rot_surf = pygame.transform.rotate(stamp_surf, -12.0)
    surface.blit(rot_surf, rot_surf.get_rect(center=(cx, cy)))


def draw_tier_badge(surface: pygame.Surface, x: int, y: int, tier_text: str,
                    is_battle_tag: bool = False) -> None:
    """Small tier chip (Bronze I, Silver II, Gold III) or crimson BATTLE tag."""
    if is_battle_tag:
        bg_col, text_col = CRIMSON_TAG, WHITE
    elif "Gold" in tier_text:
        bg_col, text_col = (195, 145, 30), (255, 245, 190)
    elif "Silver" in tier_text:
        bg_col, text_col = (120, 135, 155), (240, 245, 255)
    else:
        bg_col, text_col = (145, 95, 45), (245, 215, 190)
    t_surf = render_text(tier_text, 10, text_col, "ui")
    b_rect = pygame.Rect(x, y, t_surf.get_width() + 10, 16)
    pygame.draw.rect(surface, bg_col, b_rect, border_radius=3)
    surface.blit(t_surf, t_surf.get_rect(center=b_rect.center))
