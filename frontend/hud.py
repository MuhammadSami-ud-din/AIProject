"""HUD: health bars with damage trail, timer, round dots, emblems, and combo feedback."""

import pygame

from frontend.theme import (
    HEALTH_BAR_HEIGHT,
    HEALTH_BAR_WIDTH,
    HEALTH_BG,
    HEALTH_GREEN,
    HEALTH_RED,
    HEALTH_TRAIL,
    PRIMARY_PALETTES,
    SCREEN_WIDTH,
    TIMER_COLOUR,
    WHITE,
    BLACK,
    LIGHT_GREY,
    SPARK_HIT,
    SPARK_BLOCK,
)


def draw_hud(surface, state, font_medium, font_small, hit_flash=0,
             trail1=1.0, trail2=1.0, combo1=0, combo2=0,
             diff1=None, diff2=None, sparks=None):
    """Draw health bars with sliding damage trails, guard/super meters, timer, and combo feedback."""
    f1 = state.fighter1
    f2 = state.fighter2

    # --- Health & Meter bars ---
    _draw_fighter_hud(surface, 30, 20, f1, trail1, f1.character_name,
                      diff1, state.p1_rounds_won, font_small, left_aligned=True)

    _draw_fighter_hud(surface, SCREEN_WIDTH - 30 - HEALTH_BAR_WIDTH, 20,
                      f2, trail2, f2.character_name,
                      diff2, state.p2_rounds_won, font_small, left_aligned=False)

    # --- Timer in center ---
    from backend.engine.constants import FPS
    seconds_left = max(0, state.round_frames_left // FPS)
    timer_text = font_medium.render(str(seconds_left), True, TIMER_COLOUR)
    timer_rect = timer_text.get_rect(midtop=(SCREEN_WIDTH // 2, 16))
    pygame.draw.rect(surface, (25, 25, 45),
                     timer_rect.inflate(24, 12), border_radius=6)
    pygame.draw.rect(surface, (80, 85, 110), timer_rect.inflate(24, 12), 2, border_radius=6)
    surface.blit(timer_text, timer_rect)

    # --- Round indicator ---
    round_text = f"ROUND {state.round_number}"
    rt = font_small.render(round_text, True, (220, 220, 220))
    surface.blit(rt, rt.get_rect(midtop=(SCREEN_WIDTH // 2, 58)))

    # --- Combo counters ---
    font_combo = pygame.font.Font(None, 36)
    if combo1 >= 2 or f1.combo_hits >= 2:
        hits = max(combo1, f1.combo_hits)
        c1_surf = font_combo.render(f"{hits} HITS!", True, (255, 215, 0))
        surface.blit(c1_surf, (50, 95))
    if combo2 >= 2 or f2.combo_hits >= 2:
        hits = max(combo2, f2.combo_hits)
        c2_surf = font_combo.render(f"{hits} HITS!", True, (255, 215, 0))
        surface.blit(c2_surf, (SCREEN_WIDTH - 160, 95))

    # --- Hit Sparks ---
    if sparks:
        for s in sparks:
            _draw_spark(surface, s["x"], s["y"], s["colour"], s["frame"])

    # --- Hit flash ---
    if hit_flash > 0:
        flash_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        alpha = min(90, hit_flash * 25)
        flash_surface.fill((255, 255, 255, alpha))
        surface.blit(flash_surface, (0, 0))


def _draw_fighter_hud(surface, x, y, fighter, trail_health, name,
                      difficulty, rounds_won, font, left_aligned=True):
    """Draw one health bar, guard bar, super meter, name, emblem, and round-win dots."""
    health = fighter.health
    guard = fighter.guard_meter / 100.0
    super_meter = fighter.meter / 100.0

    palette = PRIMARY_PALETTES.get(name, {})
    title = palette.get("title", name)
    accent_col = palette.get("accent", (255, 215, 0))
    emblem = palette.get("emblem", "compass")

    # Name label (with difficulty if AI and FURY badge if low health)
    label_text = f"{title}"
    if difficulty:
        label_text += f" [{difficulty}]"
    if fighter.is_fury:
        label_text += " [FURY!]"
    label_col = (255, 80, 80) if fighter.is_fury else WHITE
    label = font.render(label_text, True, label_col)

    # Emblem icon
    emblem_x = x if left_aligned else x + HEALTH_BAR_WIDTH - 12
    emblem_y = y + 8
    _draw_small_emblem(surface, emblem_x, emblem_y, emblem, accent_col)

    if left_aligned:
        surface.blit(label, (x + 20, y))
    else:
        surface.blit(label, (x + HEALTH_BAR_WIDTH - 20 - label.get_width(), y))

    bar_y = y + 24
    bg_rect = pygame.Rect(x, bar_y, HEALTH_BAR_WIDTH, HEALTH_BAR_HEIGHT)

    # 1. Background
    pygame.draw.rect(surface, HEALTH_BG, bg_rect, border_radius=4)

    # 2. White sliding damage trail
    trail_w = int(HEALTH_BAR_WIDTH * max(0.0, min(1.0, trail_health)))
    if trail_w > 0:
        if left_aligned:
            trail_rect = pygame.Rect(x, bar_y, trail_w, HEALTH_BAR_HEIGHT)
        else:
            trail_rect = pygame.Rect(x + HEALTH_BAR_WIDTH - trail_w, bar_y, trail_w, HEALTH_BAR_HEIGHT)
        pygame.draw.rect(surface, (230, 230, 230), trail_rect, border_radius=4)

    # 3. Main health fill
    fill_w = int(HEALTH_BAR_WIDTH * max(0.0, min(1.0, health)))
    if fill_w > 0:
        col = HEALTH_GREEN if health > 0.3 else HEALTH_RED
        if left_aligned:
            fill_rect = pygame.Rect(x, bar_y, fill_w, HEALTH_BAR_HEIGHT)
        else:
            fill_rect = pygame.Rect(x + HEALTH_BAR_WIDTH - fill_w, bar_y, fill_w, HEALTH_BAR_HEIGHT)
        pygame.draw.rect(surface, col, fill_rect, border_radius=4)

    # 4. Health bar border (pulsing gold/red if FURY)
    border_col = (255, 60, 60) if fighter.is_fury else (200, 205, 220)
    pygame.draw.rect(surface, border_col, bg_rect, 2, border_radius=4)

    # 5. Guard meter bar (under health bar, height 4)
    guard_y = bar_y + HEALTH_BAR_HEIGHT + 2
    guard_w = int(HEALTH_BAR_WIDTH * max(0.0, min(1.0, guard)))
    guard_bg = pygame.Rect(x, guard_y, HEALTH_BAR_WIDTH, 4)
    pygame.draw.rect(surface, (30, 30, 45), guard_bg)
    if guard_w > 0:
        g_col = (80, 200, 255) if guard > 0.3 else (255, 60, 60)
        if left_aligned:
            g_rect = pygame.Rect(x, guard_y, guard_w, 4)
        else:
            g_rect = pygame.Rect(x + HEALTH_BAR_WIDTH - guard_w, guard_y, guard_w, 4)
        pygame.draw.rect(surface, g_col, g_rect)

    # 6. Super Meter bar (under guard bar, height 8)
    meter_y = guard_y + 6
    meter_w = int(HEALTH_BAR_WIDTH * max(0.0, min(1.0, super_meter)))
    meter_bg = pygame.Rect(x, meter_y, HEALTH_BAR_WIDTH, 7)
    pygame.draw.rect(surface, (20, 25, 40), meter_bg, border_radius=2)
    if meter_w > 0:
        m_col = (255, 215, 0) if super_meter >= 1.0 or (fighter.is_fury and super_meter >= 0.6) else (0, 190, 255)
        if left_aligned:
            m_rect = pygame.Rect(x, meter_y, meter_w, 7)
        else:
            m_rect = pygame.Rect(x + HEALTH_BAR_WIDTH - meter_w, meter_y, meter_w, 7)
        pygame.draw.rect(surface, m_col, m_rect, border_radius=2)
    pygame.draw.rect(surface, (100, 110, 130), meter_bg, 1, border_radius=2)

    # 7. Round-win dots (two dots below super meter)
    dot_y = meter_y + 13
    for dot_idx in range(2):
        dot_offset = dot_idx * 16
        dot_x = (x + 8 + dot_offset) if left_aligned else (x + HEALTH_BAR_WIDTH - 8 - dot_offset)
        is_won = rounds_won > dot_idx
        if is_won:
            pygame.draw.circle(surface, (255, 215, 0), (dot_x, dot_y), 5)
            pygame.draw.circle(surface, WHITE, (dot_x, dot_y), 5, 1)
        else:
            pygame.draw.circle(surface, (60, 65, 80), (dot_x, dot_y), 5)
            pygame.draw.circle(surface, (120, 125, 140), (dot_x, dot_y), 5, 1)


def _draw_small_emblem(surface, cx, cy, emblem_type, color):
    """Draw small 12x12 icon next to character name."""
    if emblem_type == "flame":
        pts = [(cx, cy - 6), (cx + 5, cy + 4), (cx, cy + 1), (cx - 5, cy + 4)]
        pygame.draw.polygon(surface, color, pts)
    elif emblem_type == "shield":
        pts = [(cx - 5, cy - 5), (cx + 5, cy - 5), (cx + 5, cy), (cx, cy + 6), (cx - 5, cy)]
        pygame.draw.polygon(surface, color, pts)
    elif emblem_type == "crescent":
        pygame.draw.circle(surface, color, (cx, cy), 5)
        pygame.draw.circle(surface, (20, 20, 30), (cx + 2, cy - 1), 4)
    else:  # compass
        pygame.draw.line(surface, color, (cx - 6, cy), (cx + 6, cy), 2)
        pygame.draw.line(surface, color, (cx, cy - 6), (cx, cy + 6), 2)


def _draw_spark(surface, x, y, colour, frame):
    """Draw dynamic multi-ray hit spark."""
    size = max(2, (8 - frame) * 3)
    # 4-point sparkle
    pygame.draw.line(surface, colour, (x - size, y), (x + size, y), 2)
    pygame.draw.line(surface, colour, (x, y - size), (x, y + size), 2)
    diag = int(size * 0.7)
    pygame.draw.line(surface, WHITE, (x - diag, y - diag), (x + diag, y + diag), 1)
    pygame.draw.line(surface, WHITE, (x - diag, y + diag), (x + diag, y - diag), 1)
