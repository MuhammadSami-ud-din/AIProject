"""Rendering functions for Arena Rumble visual elements.

Handles drawing:
- Shrinking zone barrier (energy beam, outside tint, warning ghost lines, particles)
- Player-built cover walls (crack stages at 66% and 33% HP, health bar, owner coloring)
- Ground loot pickups (glowing icons: medkit, shield cell, meter orb, build kit, speed boots, power fist)
- Supply drop (falling crate, floor shadow warning, landing beacon)
- Arena objects (destructible wooden crates, jump pads with arrows, spike traps with pressure plates)
- Rumble HUD (shield bar, build charge diamonds, active buff timers, zone stage, kill feed)
"""

import math
import pygame
from typing import Optional

from backend.engine.rumble_config import (
    ARENA_LAYOUTS,
    CRATE_HEIGHT,
    CRATE_WIDTH,
    JUMP_PAD_HEIGHT,
    JUMP_PAD_WIDTH,
    LOOT_PICKUP_RADIUS,
    SHIELD_MAX_HP,
    SUPPLY_DROP_HEIGHT,
    SUPPLY_DROP_WIDTH,
    TRAP_HEIGHT,
    TRAP_WIDTH,
    WALL_HEIGHT,
    WALL_MAX_HP,
    WALL_WIDTH,
)
from backend.engine.rumble_state import (
    ArenaObjectState,
    ItemState,
    KillFeedMessage,
    SupplyDropState,
    WallState,
    ZoneState,
)
from backend.engine.state import FightState
from frontend.theme import (
    FLOOR_HEIGHT,
    HEALTH_BAR_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WHITE,
)


# ---------------------------------------------------------------------------
# Phase 1: Zone ("The Squeeze")
# ---------------------------------------------------------------------------

def draw_rumble_zone(surface: pygame.Surface, zone: ZoneState,
                     arena_offset_x: int, floor_height: int, frame: int) -> None:
    """Draw the glowing energy barrier, outside tint, and warning ghost lines."""
    zone_l = arena_offset_x + int(zone.left)
    zone_r = arena_offset_x + int(zone.right)

    # 1. Outside Tint
    if zone_l > 0:
        tint_l = pygame.Surface((zone_l, SCREEN_HEIGHT), pygame.SRCALPHA)
        tint_l.fill((180, 20, 60, 65))
        surface.blit(tint_l, (0, 0))

    if zone_r < SCREEN_WIDTH:
        tint_w = SCREEN_WIDTH - zone_r
        tint_r = pygame.Surface((tint_w, SCREEN_HEIGHT), pygame.SRCALPHA)
        tint_r.fill((180, 20, 60, 65))
        surface.blit(tint_r, (zone_r, 0))

    # 2. Warning Ghost Lines (5s before close)
    if zone.is_warning:
        target_l = arena_offset_x + int(zone.target_left)
        target_r = arena_offset_x + int(zone.target_right)
        pulse = int(128 + 127 * math.sin(frame * 0.2))
        ghost_color = (255, 220, 0, pulse)

        ghost_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        for y in range(0, SCREEN_HEIGHT, 16):
            pygame.draw.line(ghost_surf, ghost_color, (target_l, y), (target_l, y + 8), 2)
            pygame.draw.line(ghost_surf, ghost_color, (target_r, y), (target_r, y + 8), 2)
        surface.blit(ghost_surf, (0, 0))

    # 3. Energy Barrier Walls (Vertical glowing beams)
    glow_pulse = int(200 + 55 * math.sin(frame * 0.15))
    barrier_outer = (255, 50, 100, 180)
    barrier_core = (255, 230, 240)

    # Left barrier
    pygame.draw.line(surface, barrier_outer, (zone_l, 0), (zone_l, floor_height + 20), 6)
    pygame.draw.line(surface, barrier_core, (zone_l, 0), (zone_l, floor_height + 20), 2)

    # Right barrier
    pygame.draw.line(surface, barrier_outer, (zone_r, 0), (zone_r, floor_height + 20), 6)
    pygame.draw.line(surface, barrier_core, (zone_r, 0), (zone_r, floor_height + 20), 2)

    # Energy spark particles
    for i in range(5):
        spark_y = int((frame * 4 + i * 110) % floor_height)
        spark_size = 3 + (i % 2)
        pygame.draw.circle(surface, (255, 255, 255), (zone_l + (i % 3 - 1), spark_y), spark_size)
        pygame.draw.circle(surface, (255, 255, 255), (zone_r + (i % 3 - 1), spark_y), spark_size)


# ---------------------------------------------------------------------------
# Phase 2: Cover Walls
# ---------------------------------------------------------------------------

def draw_rumble_walls(surface: pygame.Surface, walls: list[WallState],
                      arena_offset_x: int, floor_height: int) -> None:
    """Draw player-built cover walls with crack stages and health indicators."""
    for w in walls:
        wx = arena_offset_x + int(w.x)
        wy = floor_height - int(w.height)
        rect = pygame.Rect(wx - int(w.width / 2), wy, int(w.width), int(w.height))

        # Color based on builder
        base_col = (55, 120, 200) if w.owner == 1 else (210, 100, 45)
        border_col = (130, 190, 255) if w.owner == 1 else (255, 170, 100)

        # Base block
        pygame.draw.rect(surface, base_col, rect, border_radius=4)
        pygame.draw.rect(surface, border_col, rect, 2, border_radius=4)

        # Inner cross support lines
        pygame.draw.line(surface, border_col, (rect.left, rect.top), (rect.right, rect.bottom), 1)
        pygame.draw.line(surface, border_col, (rect.left, rect.bottom), (rect.right, rect.top), 1)

        # Crack stages (66% and 33% HP)
        if w.crack_stage >= 1:
            # First crack: diagonal fissure
            cx = rect.centerx
            cy = rect.centery
            pygame.draw.lines(surface, (30, 30, 35), False, [
                (cx - 8, cy - 25), (cx + 4, cy - 10), (cx - 2, cy + 15), (cx + 6, cy + 30)
            ], 2)

        if w.crack_stage >= 2:
            # Heavy damage cracks
            cx = rect.centerx
            cy = rect.centery
            pygame.draw.lines(surface, (20, 20, 25), False, [
                (rect.left + 5, cy - 35), (cx - 4, cy - 20), (rect.right - 6, cy - 5)
            ], 2)
            pygame.draw.lines(surface, (20, 20, 25), False, [
                (rect.left + 4, cy + 10), (cx + 2, cy + 25), (rect.right - 5, cy + 45)
            ], 2)

        # Mini Wall Health Bar above block
        hp_ratio = max(0.0, min(1.0, w.hp / w.max_hp))
        bar_w = int(w.width)
        bar_rect = pygame.Rect(rect.left, rect.top - 8, bar_w, 4)
        pygame.draw.rect(surface, (20, 20, 30), bar_rect)
        hp_col = (0, 230, 100) if hp_ratio > 0.5 else ((240, 200, 30) if hp_ratio > 0.25 else (240, 50, 50))
        pygame.draw.rect(surface, hp_col, (rect.left, rect.top - 8, int(bar_w * hp_ratio), 4))


# ---------------------------------------------------------------------------
# Phase 3: Loot and Supply Drops
# ---------------------------------------------------------------------------

def draw_rumble_items(surface: pygame.Surface, items: list[ItemState],
                      supply_drop: Optional[SupplyDropState],
                      arena_offset_x: int, floor_height: int, frame: int) -> None:
    """Draw ground items with glow and falling/landed supply drops."""
    pulse = 0.5 + 0.5 * math.sin(frame * 0.1)

    # 1. Ground items
    for it in items:
        ix = arena_offset_x + int(it.x)
        # Slight float hover
        iy = floor_height - 24 + int(3.0 * math.sin(frame * 0.12 + it.id))

        _draw_item_icon(surface, ix, iy, it.item_type, pulse)

    # 2. Supply Drop
    if supply_drop is not None:
        sx = arena_offset_x + int(supply_drop.x)

        if not supply_drop.is_landed:
            # Landing warning shadow on floor
            shadow_radius = int(24 + 6 * pulse)
            shadow_surf = pygame.Surface((shadow_radius * 2, 14), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow_surf, (255, 215, 0, 120), (0, 0, shadow_radius * 2, 14))
            surface.blit(shadow_surf, (sx - shadow_radius, floor_height - 7))

            # Falling Crate
            crate_y = floor_height - 35 + int(supply_drop.y)
            crate_rect = pygame.Rect(sx - 20, crate_y, 40, 36)
            pygame.draw.rect(surface, (220, 170, 30), crate_rect, border_radius=4)
            pygame.draw.rect(surface, (255, 235, 120), crate_rect, 2, border_radius=4)

            # Parachute above falling crate
            chute_rect = pygame.Rect(sx - 26, crate_y - 25, 52, 20)
            pygame.draw.arc(surface, (255, 255, 255), chute_rect, 0, math.pi, 3)
            pygame.draw.line(surface, (200, 200, 200), (chute_rect.left + 5, crate_y - 15), (crate_rect.left + 4, crate_y), 1)
            pygame.draw.line(surface, (200, 200, 200), (chute_rect.right - 5, crate_y - 15), (crate_rect.right - 4, crate_y), 1)
        else:
            # Landed Supply Crate (Golden crate with beacon)
            crate_rect = pygame.Rect(sx - 24, floor_height - 40, 48, 40)
            pygame.draw.rect(surface, (230, 180, 20), crate_rect, border_radius=5)
            pygame.draw.rect(surface, (255, 245, 140), crate_rect, 3, border_radius=5)

            # Cross strapping
            pygame.draw.line(surface, (80, 50, 10), (crate_rect.left, crate_rect.top), (crate_rect.right, crate_rect.bottom), 2)
            pygame.draw.line(surface, (80, 50, 10), (crate_rect.left, crate_rect.bottom), (crate_rect.right, crate_rect.top), 2)

            # Glowing beacon on top
            beacon_color = (255, 230, 50, int(150 + 100 * pulse))
            beacon_surf = pygame.Surface((30, 30), pygame.SRCALPHA)
            pygame.draw.circle(beacon_surf, beacon_color, (15, 15), int(10 + 4 * pulse))
            surface.blit(beacon_surf, (sx - 15, floor_height - 54))


def _draw_item_icon(surface: pygame.Surface, cx: int, cy: int, item_type: str, pulse: float) -> None:
    """Draw a specialized glowing icon for each loot type."""
    # Outer glow
    r = int(14 + 3 * pulse)
    glow_colors = {
        "medkit": (50, 230, 80, 90),
        "shield_cell": (0, 200, 255, 90),
        "meter_orb": (210, 60, 255, 90),
        "build_kit": (255, 170, 0, 90),
        "speed_boots": (0, 255, 190, 90),
        "power_fist": (255, 60, 60, 90),
        "big_medkit": (0, 255, 120, 110),
        "overcharge": (255, 220, 40, 110),
    }
    glow_col = glow_colors.get(item_type, (255, 255, 255, 80))
    glow_surf = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
    pygame.draw.circle(glow_surf, glow_col, (r + 4, r + 4), r)
    surface.blit(glow_surf, (cx - r - 4, cy - r - 4))

    # Base item circle
    base_col = (20, 25, 35)
    pygame.draw.circle(surface, base_col, (cx, cy), 13)
    border_col = glow_col[:3]
    pygame.draw.circle(surface, border_col, (cx, cy), 13, 2)

    # Symbol inside
    if "medkit" in item_type:
        # Cross '+'
        pygame.draw.rect(surface, (50, 255, 80), (cx - 2, cy - 7, 4, 14))
        pygame.draw.rect(surface, (50, 255, 80), (cx - 7, cy - 2, 14, 4))
    elif item_type == "shield_cell":
        # Shield polygon
        pts = [(cx - 6, cy - 6), (cx + 6, cy - 6), (cx + 5, cy + 2), (cx, cy + 7), (cx - 5, cy + 2)]
        pygame.draw.polygon(surface, (0, 220, 255), pts)
    elif item_type == "meter_orb":
        # Purple gem
        pygame.draw.circle(surface, (220, 80, 255), (cx, cy), 6)
        pygame.draw.circle(surface, (255, 255, 255), (cx - 2, cy - 2), 2)
    elif item_type == "build_kit":
        # Brick shape
        pygame.draw.rect(surface, (255, 180, 30), (cx - 7, cy - 5, 14, 10), border_radius=2)
    elif item_type == "speed_boots":
        # Wing / lightning bolt
        pts = [(cx - 5, cy - 6), (cx + 2, cy - 2), (cx - 2, cy + 1), (cx + 5, cy + 6)]
        pygame.draw.lines(surface, (0, 255, 200), False, pts, 2)
    elif item_type == "power_fist":
        # Fist / flame
        pygame.draw.circle(surface, (255, 70, 70), (cx, cy), 6)
        pygame.draw.line(surface, (255, 200, 50), (cx, cy - 7), (cx, cy + 6), 2)
    elif item_type == "overcharge":
        # Sunburst / star
        pygame.draw.circle(surface, (255, 230, 50), (cx, cy), 7)
        pygame.draw.line(surface, (255, 255, 255), (cx - 8, cy), (cx + 8, cy), 2)
        pygame.draw.line(surface, (255, 255, 255), (cx, cy - 8), (cx, cy + 8), 2)


# ---------------------------------------------------------------------------
# Phase 4: Arena Objects
# ---------------------------------------------------------------------------

def draw_rumble_objects(surface: pygame.Surface, objects: list[ArenaObjectState],
                        arena_offset_x: int, floor_height: int, frame: int) -> None:
    """Draw destructible crates, jump pads, and spike traps."""
    for obj in objects:
        ox = arena_offset_x + int(obj.x)

        if obj.object_type == "crate" and obj.hp > 0:
            # Wooden destructible crate
            c_rect = pygame.Rect(ox - int(obj.width / 2), floor_height - int(obj.height),
                                 int(obj.width), int(obj.height))
            pygame.draw.rect(surface, (140, 95, 45), c_rect, border_radius=3)
            pygame.draw.rect(surface, (80, 50, 25), c_rect, 2, border_radius=3)
            # Diagonal braces
            pygame.draw.line(surface, (100, 65, 30), (c_rect.left, c_rect.top), (c_rect.right, c_rect.bottom), 2)
            pygame.draw.line(surface, (100, 65, 30), (c_rect.left, c_rect.bottom), (c_rect.right, c_rect.top), 2)

            # Mini health bar if damaged
            if obj.hp < obj.max_hp:
                ratio = max(0.0, obj.hp / obj.max_hp)
                pygame.draw.rect(surface, (30, 30, 30), (c_rect.left, c_rect.top - 6, c_rect.width, 3))
                pygame.draw.rect(surface, (240, 160, 30), (c_rect.left, c_rect.top - 6, int(c_rect.width * ratio), 3))

        elif obj.object_type == "jump_pad":
            # Jump pad on floor with glowing upward arrows
            pad_rect = pygame.Rect(ox - int(obj.width / 2), floor_height - int(obj.height),
                                   int(obj.width), int(obj.height))
            pad_ready = (obj.cooldown == 0)
            col = (0, 210, 255) if pad_ready else (70, 85, 95)
            pygame.draw.rect(surface, (30, 35, 45), pad_rect, border_radius=3)
            pygame.draw.rect(surface, col, pad_rect, 2, border_radius=3)

            # Glowing arrows
            if pad_ready:
                arrow_pulse = int(180 + 75 * math.sin(frame * 0.25))
                arrow_col = (0, arrow_pulse, 255)
                # Upward chevron
                pygame.draw.lines(surface, arrow_col, False, [
                    (ox - 10, pad_rect.centery + 3), (ox, pad_rect.centery - 3), (ox + 10, pad_rect.centery + 3)
                ], 2)

        elif obj.object_type == "trap":
            # Spike trap on floor
            trap_rect = pygame.Rect(ox - int(obj.width / 2), floor_height - int(obj.height),
                                    int(obj.width), int(obj.height))
            # Base plate
            pygame.draw.rect(surface, (50, 50, 55), trap_rect, border_radius=2)
            pygame.draw.rect(surface, (100, 100, 110), trap_rect, 1, border_radius=2)

            if obj.is_triggered:
                # Warning glow (blinking yellow/red before spikes deploy)
                flash = (255, 50, 50) if (frame % 6 < 3) else (255, 215, 0)
                pygame.draw.rect(surface, flash, trap_rect.inflate(-4, -4), border_radius=2)
            elif obj.cooldown > 550:
                # Spikes are currently extended up!
                spike_top = floor_height - 24
                for sx in range(trap_rect.left + 5, trap_rect.right - 4, 8):
                    pygame.draw.polygon(surface, (200, 200, 210), [
                        (sx - 3, floor_height - 2), (sx, spike_top), (sx + 3, floor_height - 2)
                    ])


# ---------------------------------------------------------------------------
# Phase 6: Rumble HUD & Kill Feed
# ---------------------------------------------------------------------------

def draw_rumble_hud_extras(surface: pygame.Surface, state: FightState,
                           font_medium: pygame.font.Font, font_small: pygame.font.Font) -> None:
    """Draw shield bars, build charges, active buffs, supply drop arrow, and kill feed."""
    f1 = state.fighter1
    f2 = state.fighter2

    # 1. Shield Bar overlay on health bar
    # Player 1 Shield
    if f1.shield > 0.0:
        shield_w = int((HEALTH_BAR_WIDTH * (f1.shield / SHIELD_MAX_HP)))
        s_rect1 = pygame.Rect(30, 36, shield_w, 4)
        pygame.draw.rect(surface, (0, 220, 255), s_rect1, border_radius=2)

    # Player 2 Shield
    if f2.shield > 0.0:
        shield_w = int((HEALTH_BAR_WIDTH * (f2.shield / SHIELD_MAX_HP)))
        s_rect2 = pygame.Rect(SCREEN_WIDTH - 30 - shield_w, 36, shield_w, 4)
        pygame.draw.rect(surface, (0, 220, 255), s_rect2, border_radius=2)

    # 2. Build Charges (3 diamonds below health bar)
    _draw_build_charges(surface, 30, 48, f1.build_charges, left_aligned=True)
    _draw_build_charges(surface, SCREEN_WIDTH - 30 - 55, 48, f2.build_charges, left_aligned=False)

    # 3. Active Buff Badges (Speed Boots & Power Fist)
    _draw_buff_badges(surface, 100, 48, f1, font_small, left_aligned=True)
    _draw_buff_badges(surface, SCREEN_WIDTH - 100, 48, f2, font_small, left_aligned=False)

    # 4. Zone Warning Banner in Top Center
    if state.zone.is_warning:
        warn_pulse = int(200 + 55 * math.sin(state.frame * 0.3))
        warn_surf = font_medium.render("! ZONE CLOSING !", True, (255, warn_pulse, 0))
        warn_rect = warn_surf.get_rect(midtop=(SCREEN_WIDTH // 2, 85))
        pygame.draw.rect(surface, (40, 20, 10), warn_rect.inflate(20, 8), border_radius=4)
        pygame.draw.rect(surface, (255, 180, 0), warn_rect.inflate(20, 8), 2, border_radius=4)
        surface.blit(warn_surf, warn_rect)

    # 5. Supply Drop Arrow Indicator
    if state.supply_drop is not None and not state.supply_drop.is_landed:
        drop_screen_x = (SCREEN_WIDTH - 800) // 2 + int(state.supply_drop.x)
        arrow_surf = font_small.render("V SUPPLY DROP V", True, (255, 215, 0))
        arrow_rect = arrow_surf.get_rect(midtop=(drop_screen_x, 10))
        surface.blit(arrow_surf, arrow_rect)

    # 6. Corner Kill Feed (Top right beneath P2 health bar)
    feed_y = 75
    for msg in reversed(state.kill_feed):
        alpha = min(255, msg.lifetime * 4)
        feed_surf = font_small.render(msg.text, True, msg.color)
        feed_rect = feed_surf.get_rect(topright=(SCREEN_WIDTH - 30, feed_y))

        bg_surf = pygame.Surface((feed_rect.width + 12, feed_rect.height + 6), pygame.SRCALPHA)
        bg_surf.fill((15, 18, 25, int(180 * (alpha / 255.0))))
        surface.blit(bg_surf, (feed_rect.left - 6, feed_rect.top - 3))
        surface.blit(feed_surf, feed_rect)
        feed_y += 20


def _draw_build_charges(surface: pygame.Surface, x: int, y: int, charges: int, left_aligned: bool) -> None:
    """Draw 3 build energy diamonds."""
    for i in range(3):
        cx = x + i * 14 if left_aligned else x + (2 - i) * 14
        cy = y
        pts = [(cx, cy - 5), (cx + 5, cy), (cx, cy + 5), (cx - 5, cy)]
        if charges > i:
            pygame.draw.polygon(surface, (0, 190, 255), pts)
            pygame.draw.polygon(surface, (200, 240, 255), pts, 1)
        else:
            pygame.draw.polygon(surface, (45, 50, 60), pts)
            pygame.draw.polygon(surface, (90, 95, 110), pts, 1)


def _draw_buff_badges(surface: pygame.Surface, x: int, y: int, f, font_small: pygame.font.Font, left_aligned: bool) -> None:
    """Draw active buff timer badges."""
    cur_x = x
    if f.speed_boost_timer > 0:
        sec = max(1, f.speed_boost_timer // 60)
        surf = font_small.render(f"SPD {sec}s", True, (0, 255, 180))
        surface.blit(surf, (cur_x, y - 6) if left_aligned else (cur_x - surf.get_width(), y - 6))
        cur_x += (surf.get_width() + 10) if left_aligned else -(surf.get_width() + 10)

    if f.power_boost_timer > 0:
        sec = max(1, f.power_boost_timer // 60)
        surf = font_small.render(f"PWR {sec}s", True, (255, 80, 80))
        surface.blit(surf, (cur_x, y - 6) if left_aligned else (cur_x - surf.get_width(), y - 6))
