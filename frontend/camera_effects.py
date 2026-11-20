"""Shared visual effects, dynamic camera, 2-layer arena ambience, colour grading,
vignette, and F4 alignment guides for both the fight screen and AI viewer.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
import pygame

from backend.engine.constants import ARENA_WIDTH
from frontend.theme import (
    ARENA_COLOR_GRADE,
    BLACK,
    FLOOR_RATIO,
    SCREEN_WIDTH,
    WHITE,
    get_arena_floor_y,
)

_VIGNETTE_CACHE: Dict[Tuple[str, int, int], pygame.Surface] = {}


class CameraState:
    """Smooth midpoint-tracking camera with dynamic zoom (1.0x - 1.15x) and KO focus."""

    def __init__(self, viewport_w: int = SCREEN_WIDTH, viewport_h: int = 600):
        self.viewport_w = viewport_w
        self.viewport_h = viewport_h
        self.focus_x = viewport_w / 2.0
        self.focus_y = viewport_h / 2.0
        self.zoom = 1.0

    def update(
        self,
        f1_screen_x: float,
        f2_screen_x: float,
        floor_y: float,
        ko_target_x: Optional[float] = None,
        lerp_t: float = 0.10,
    ) -> None:
        """Update camera focus and zoom with lerp(t=0.10) and boundary clamping."""
        if ko_target_x is not None:
            target_x = ko_target_x
            target_y = floor_y - 55.0
            target_zoom = 1.18
        else:
            target_x = (f1_screen_x + f2_screen_x) * 0.5
            target_y = floor_y - 85.0
            dist = abs(f1_screen_x - f2_screen_x)
            # Close (< 140px) -> 1.15x; Far (> 480px) -> 1.0x
            t_dist = max(0.0, min(1.0, (480.0 - dist) / 340.0))
            target_zoom = 1.0 + 0.15 * t_dist

        self.focus_x += (target_x - self.focus_x) * lerp_t
        self.focus_y += (target_y - self.focus_y) * lerp_t
        self.zoom += (target_zoom - self.zoom) * lerp_t

    def get_offset(self) -> Tuple[float, float]:
        """Return (offset_x, offset_y) from center focus for callers expecting camera offset."""
        return (self.focus_x - self.viewport_w / 2.0, self.focus_y - self.viewport_h / 2.0)

    def present(
        self,
        viewport_surf: pygame.Surface,
        dest_surf: pygame.Surface,
        dest_pos: Tuple[int, int] = (0, 0),
    ) -> None:
        """Blit the camera-transformed fight viewport onto dest_surf without moving HUD/panels."""
        vw, vh = viewport_surf.get_size()
        if self.zoom <= 1.004:
            dest_surf.blit(viewport_surf, dest_pos)
            return

        crop_w = max(64, min(vw, int(round(vw / self.zoom))))
        crop_h = max(64, min(vh, int(round(vh / self.zoom))))

        # Clamp camera rectangle so it never shows empty space outside the background
        cx = int(round(self.focus_x))
        cy = int(round(self.focus_y))
        left = max(0, min(vw - crop_w, cx - crop_w // 2))
        top = max(0, min(vh - crop_h, cy - crop_h // 2))

        sub = viewport_surf.subsurface((left, top, crop_w, crop_h))
        scaled = pygame.transform.scale(sub, (vw, vh))
        dest_surf.blit(scaled, dest_pos)


def _normalize_arena_key(arena_name: str) -> str:
    clean = (
        str(arena_name or "arena_neon_rooftop")
        .lower()
        .strip()
        .replace(".jpeg", "")
        .replace(".jpg", "")
        .replace(".png", "")
        .replace(" ", "_")
    )
    if not clean.startswith("arena_"):
        clean = f"arena_{clean}"
    return clean


def draw_arena_ambience(
    surface: pygame.Surface,
    arena_name: str,
    frame: int,
    viewport_h: int,
    layer: str = "back",
) -> None:
    """Draw deterministic code-generated atmospheric particles in two depth layers."""
    key = _normalize_arena_key(arena_name)
    is_front = (layer == "front")
    count = 12 if is_front else 18
    seed_offset = 100 if is_front else 0
    w = surface.get_width()

    if "frozen" in key:
        # Gentle falling snow drifting left-to-right
        for i in range(count):
            idx = i + seed_offset
            speed_y = 1.4 if is_front else 0.85
            speed_x = 0.65 if is_front else 0.35
            x = int((idx * 97 + frame * speed_x + math.sin(frame * 0.04 + idx) * 14) % w)
            y = int((idx * 53 + frame * speed_y) % viewport_h)
            r = (3 if (i % 3 == 0) else 2) if is_front else 2
            col = (240, 248, 255) if is_front else (195, 220, 245)
            pygame.draw.circle(surface, col, (x, y), r)

    elif "neon" in key:
        # Distant rain streaks at a slight angle
        for i in range(count):
            idx = i + seed_offset
            vy = 7.5 if is_front else 5.0
            vx = -1.6 if is_front else -1.0
            x = int((idx * 89 + frame * vx) % w)
            y = int((idx * 61 + frame * vy) % viewport_h)
            length = 14 if is_front else 9
            col = (130, 210, 255) if is_front else (85, 135, 195)
            pygame.draw.line(surface, col, (x, y), (x - 3, y + length), 1)

    elif "golden" in key or "temple" in key:
        # Drifting autumn leaves (orange / red / yellow)
        leaf_cols = [(235, 110, 35), (215, 55, 45), (245, 185, 40)]
        for i in range(count):
            idx = i + seed_offset
            x = int((idx * 103 + frame * (0.9 if is_front else 0.5) + math.sin(frame * 0.05 + idx) * 18) % w)
            y = int((idx * 67 + frame * (1.1 if is_front else 0.7)) % viewport_h)
            c = leaf_cols[i % 3]
            sz = 4 if is_front else 3
            pts = [(x, y - sz), (x + sz + 1, y), (x, y + sz), (x - sz - 1, y)]
            pygame.draw.polygon(surface, c, pts)

    elif "volcanic" in key or "foundry" in key or "underground" in key:
        # Floating orange ember sparks rising from below
        for i in range(count):
            idx = i + seed_offset
            vy = 1.6 if is_front else 1.0
            x = int((idx * 83 + math.sin(frame * 0.06 + idx) * 16) % w)
            y = int((viewport_h - ((idx * 47 + frame * vy) % viewport_h)))
            col = (255, 185, 55) if (i % 2 == 0) else (255, 95, 30)
            r = 3 if is_front else 2
            pygame.draw.circle(surface, col, (x, y), r)

    elif "bamboo" in key or "mystic" in key or "shrine" in key:
        # Slow glowing green/cyan fireflies floating upward
        for i in range(count):
            idx = i + seed_offset
            x = int((idx * 109 + math.sin(frame * 0.03 + idx) * 22) % w)
            y = int((viewport_h - ((idx * 59 + frame * 0.65) % viewport_h)))
            pulse = 0.5 + 0.5 * math.sin(frame * 0.1 + idx)
            col = (int(60 + 80 * pulse), int(215 + 40 * pulse), int(185 + 60 * pulse))
            r = 3 if is_front else 2
            pygame.draw.circle(surface, col, (x, y), r)

    else:
        # Sky Colosseum / Cyber Street / Dojo: floating neon/sunlight motes
        for i in range(count):
            idx = i + seed_offset
            x = int((idx * 97 + frame * 0.4 + math.cos(frame * 0.03 + idx) * 12) % w)
            y = int((idx * 71 + frame * 0.35) % viewport_h)
            col = (140, 225, 255) if (i % 2 == 0) else (245, 220, 140)
            pygame.draw.circle(surface, col, (x, y), 2)


def draw_color_grade_and_vignette(surface: pygame.Surface, arena_name: str) -> None:
    """Apply subtle full-viewport colour grade tint and gentle edge vignette (cached)."""
    w, h = surface.get_size()
    key = _normalize_arena_key(arena_name)
    cache_key = (key, w, h)

    overlay = _VIGNETTE_CACHE.get(cache_key)
    if overlay is None:
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        tint = ARENA_COLOR_GRADE.get(key, (140, 170, 255, 16))
        overlay.fill(tint)

        # Gentle edge vignette bands around the perimeter
        steps = 12
        band_w = 48
        band_h = 36
        for s in range(steps):
            frac = (steps - s) / steps
            alpha = int(58 * (frac * frac))
            rx = int(s * (band_w / steps))
            ry = int(s * (band_h / steps))
            rect = pygame.Rect(rx, ry, w - rx * 2, h - ry * 2)
            pygame.draw.rect(overlay, (0, 0, 0, alpha), rect, width=max(2, band_w // steps))

        _VIGNETTE_CACHE[cache_key] = overlay

    surface.blit(overlay, (0, 0))


def draw_alignment_lines(
    surface: pygame.Surface,
    floor_y: int,
    arena_offset_x: int,
    arena_width: int,
    arena_name: str,
    font: pygame.font.Font,
) -> None:
    """Draw F4 red alignment lines showing floor_y, arena bounds, and FLOOR_RATIO."""
    w, h = surface.get_size()
    red = (255, 45, 45)
    # Horizontal floor line
    pygame.draw.line(surface, red, (0, floor_y), (w, floor_y), 2)
    # Left, center, and right vertical arena guide lines
    pygame.draw.line(surface, red, (arena_offset_x, 0), (arena_offset_x, h), 1)
    pygame.draw.line(surface, red, (arena_offset_x + arena_width // 2, 0), (arena_offset_x + arena_width // 2, h), 1)
    pygame.draw.line(surface, red, (arena_offset_x + arena_width, 0), (arena_offset_x + arena_width, h), 1)

    key = _normalize_arena_key(arena_name)
    ratio = FLOOR_RATIO.get(key, floor_y / max(1, h))
    lbl = font.render(f"F4 ALIGNMENT | {key} | FLOOR_RATIO={ratio:.2f} | floor_y={floor_y}px", True, red)
    bg = pygame.Rect(arena_offset_x + 8, floor_y + 4, lbl.get_width() + 10, lbl.get_height() + 4)
    pygame.draw.rect(surface, (10, 10, 16), bg, border_radius=3)
    pygame.draw.rect(surface, red, bg, 1, border_radius=3)
    surface.blit(lbl, (bg.x + 5, bg.y + 2))


def draw_combat_popups(
    surface: pygame.Surface,
    popups: List[Dict[str, Any]],
    font: pygame.font.Font,
    shake_x: int = 0,
    shake_y: int = 0,
) -> None:
    """Draw floating combat text ('COUNTER!', 'PUNISH!', 'BLOCKED') rising and fading over 20f with 1px dark outline."""
    for pop in popups:
        life = pop.get("lifetime", 1)
        max_life = pop.get("max_lifetime", 20)
        alpha = max(0, min(255, int(255 * (life / max(1, max_life)))))
        if alpha <= 0:
            continue

        txt = pop["text"]
        col = pop["color"]
        cx = int(pop["x"]) + shake_x
        cy = int(pop["y"]) + shake_y

        p_surf = font.render(txt, True, col)
        o_surf = font.render(txt, True, BLACK)
        if alpha < 250:
            p_surf.set_alpha(alpha)
            o_surf.set_alpha(alpha)

        rect = p_surf.get_rect(center=(cx, cy))
        # 1-px dark outline on all 4 sides
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surface.blit(o_surf, (rect.x + ox, rect.y + oy))
        surface.blit(p_surf, rect)
