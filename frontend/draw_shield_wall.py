"""Rendering functions for the Shield Wall ability and HUD elements (Step 4).

Draws:
- Active energy shield panels in their owner's signature color
- Crack overlays at <= 66% HP and <= 33% HP
- Small HP bar directly on each shield panel
- Shield energy bar under each fighter's health bar
- Cooldown ring icon when a shield is on cooldown
- Feedback event banners ("SHIELD UP", "SHIELD BREAK!", "THROW THROUGH!")
"""

import math
import pygame
from typing import Optional

from backend.engine.shield_state import ShieldWallState
from backend.engine.state import FighterState, FightState
from frontend.theme import HEALTH_BAR_WIDTH, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE


CHARACTER_SHIELD_COLORS = {
    "Golden": (255, 210, 60),
    "Crimson": (240, 60, 75),
    "Steel": (75, 175, 255),
    "Shadow": (190, 85, 255),
}


def draw_shield_wall_panels(surface: pygame.Surface, state: FightState,
                            arena_offset_x: int, floor_height: int) -> None:
    """Draw active shield wall energy panels in the arena."""
    if not state.rules.enable_shield_wall:
        return

    ground_y = SCREEN_HEIGHT - floor_height

    for f in (state.fighter1, state.fighter2):
        sw = f.shield_wall
        if sw is None:
            continue

        color = CHARACTER_SHIELD_COLORS.get(f.character_name, (100, 220, 255))
        sx = arena_offset_x + int(sw.left)
        sy = ground_y - int(sw.height)
        w = int(sw.width)
        h = int(sw.height)

        # Translucent energy panel fill
        panel_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pulse = int(140 + 40 * math.sin(state.frame * 0.2))
        panel_surf.fill((*color, pulse))
        surface.blit(panel_surf, (sx, sy))

        # Bright glowing border
        pygame.draw.rect(surface, color, (sx, sy, w, h), 2, border_radius=3)
        pygame.draw.rect(surface, WHITE, (sx + 2, sy + 2, w - 4, h - 4), 1, border_radius=2)

        # Crack overlays at <= 66% and <= 33% HP
        hp_ratio = max(0.0, sw.hp / max(1.0, sw.max_hp))
        if hp_ratio <= 0.66:
            # First crack lines
            pygame.draw.line(surface, WHITE, (sx + 4, sy + 25), (sx + w // 2, sy + 45), 2)
            pygame.draw.line(surface, WHITE, (sx + w // 2, sy + 45), (sx + w - 5, sy + 35), 2)
        if hp_ratio <= 0.33:
            # Heavy shatter cracks
            pygame.draw.line(surface, (255, 80, 80), (sx + 5, sy + 75), (sx + w - 4, sy + 95), 2)
            pygame.draw.line(surface, (255, 80, 80), (sx + w - 6, sy + 60), (sx + 6, sy + 105), 2)

        # Small HP bar directly above/on the panel
        bar_w = w + 10
        bar_x = sx - 5
        bar_y = sy - 10
        pygame.draw.rect(surface, (20, 20, 25), (bar_x, bar_y, bar_w, 5))
        pygame.draw.rect(surface, color, (bar_x, bar_y, int(bar_w * hp_ratio), 5))


def draw_shield_wall_hud(surface: pygame.Surface, state: FightState,
                         font_small: pygame.font.Font) -> None:
    """Draw shield energy bar under each health bar, cooldown ring, and feedback text."""
    if not state.rules.enable_shield_wall:
        return

    _draw_fighter_shield_hud(surface, state.fighter1, x=30, y=42, left_aligned=True, font_small=font_small)
    _draw_fighter_shield_hud(
        surface,
        state.fighter2,
        x=SCREEN_WIDTH - 30 - HEALTH_BAR_WIDTH,
        y=42,
        left_aligned=False,
        font_small=font_small,
    )

    # Feedback messages (when not already drawn by rumble HUD)
    if not state.rules.is_rumble and state.kill_feed:
        feed_y = 75
        for msg in reversed(state.kill_feed):
            alpha = min(255, msg.lifetime * 4)
            feed_surf = font_small.render(msg.text, True, msg.color)
            feed_rect = feed_surf.get_rect(midtop=(SCREEN_WIDTH // 2, feed_y))
            bg_surf = pygame.Surface((feed_rect.width + 14, feed_rect.height + 6), pygame.SRCALPHA)
            bg_surf.fill((15, 18, 25, int(190 * (alpha / 255.0))))
            surface.blit(bg_surf, (feed_rect.left - 7, feed_rect.top - 3))
            surface.blit(feed_surf, feed_rect)
            feed_y += 22


def _draw_fighter_shield_hud(
    surface: pygame.Surface,
    f: FighterState,
    x: int,
    y: int,
    left_aligned: bool,
    font_small: pygame.font.Font,
) -> None:
    """Draw shield energy bar and cooldown ring icon for one fighter."""
    color = CHARACTER_SHIELD_COLORS.get(f.character_name, (100, 220, 255))
    bar_w = HEALTH_BAR_WIDTH
    bar_h = 5

    # Background bar
    pygame.draw.rect(surface, (25, 30, 40), (x, y, bar_w, bar_h), border_radius=2)

    # Energy fill
    energy_ratio = max(0.0, min(1.0, f.shield_energy / 100.0))
    fill_w = int(bar_w * energy_ratio)
    if left_aligned:
        pygame.draw.rect(surface, color, (x, y, fill_w, bar_h), border_radius=2)
    else:
        pygame.draw.rect(surface, color, (x + bar_w - fill_w, y, fill_w, bar_h), border_radius=2)

    # Cooldown ring icon if on cooldown
    ring_cx = (x + bar_w + 16) if left_aligned else (x - 16)
    ring_cy = y + 2
    if f.shield_cooldown_frames > 0:
        pygame.draw.circle(surface, (40, 40, 50), (ring_cx, ring_cy), 9)
        pygame.draw.circle(surface, (255, 120, 60), (ring_cx, ring_cy), 9, 2)
        cd_sec = int(math.ceil(f.shield_cooldown_frames / 60.0))
        txt = font_small.render(f"{cd_sec}", True, WHITE)
        surface.blit(txt, txt.get_rect(center=(ring_cx, ring_cy)))
    else:
        # Ready indicator dot
        pygame.draw.circle(surface, color, (ring_cx, ring_cy), 5)
