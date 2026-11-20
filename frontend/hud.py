"""Modern 2D Fighting Game HUD: slanted parallelogram health bars, framed portraits,
diamond round counters, 3-segment super meters, hexagonal timer badge, and starburst sparks.
"""

import math
import time
from typing import Dict, Tuple
import pygame

from frontend.assets import assets
from frontend.theme import (
    BLACK,
    HEALTH_BAR_HEIGHT,
    HEALTH_BAR_WIDTH,
    HEALTH_BG,
    HEALTH_GREEN,
    HEALTH_RED,
    HEALTH_TRAIL,
    HEALTH_YELLOW,
    LIGHT_GREY,
    P1_COLOUR,
    P2_COLOUR,
    PRIMARY_PALETTES,
    SCREEN_WIDTH,
    SPARK_BLOCK,
    SPARK_COUNTER,
    SPARK_HIT,
    TIMER_COLOUR,
    WHITE,
)

# Per-player white damage-drop hold timer (holds for 15 frames before catching down)
_TRAIL_HOLD_FRAMES: Dict[int, int] = {1: 0, 2: 0}
_LAST_SEEN_HEALTH: Dict[int, float] = {1: 1.0, 2: 1.0}
_INTERNAL_TRAIL: Dict[int, float] = {1: 1.0, 2: 1.0}
_FONT_CACHE: Dict[int, pygame.font.Font] = {}


def _get_font(size: int) -> pygame.font.Font:
    f = _FONT_CACHE.get(size)
    if f is not None:
        try:
            f.get_height()
            return f
        except pygame.error:
            pass
    f = pygame.font.Font(None, size)
    _FONT_CACHE[size] = f
    return f


def _parallelogram_pts(x: int, y: int, w: int, h: int, skew: int) -> list:
    """Return 4 vertices of a slanted parallelogram bar."""
    return [
        (x + skew, y),
        (x + w + skew, y),
        (x + w, y + h),
        (x, y + h),
    ]


def _health_color(hp: float, now: float) -> Tuple[int, int, int]:
    """Return green (>60%), yellow (25-60%), or pulsing red (<25%)."""
    if hp > 0.60:
        # Smooth green gradient tone
        t = (hp - 0.60) / 0.40
        return (int(40 - 15 * t), int(205 + 30 * t), int(75 + 20 * t))
    if hp >= 0.25:
        return HEALTH_YELLOW
    pulse = 0.5 + 0.5 * math.sin(now * 14.0)
    return (
        int(200 + 55 * pulse),
        int(25 + 45 * pulse),
        int(25 + 35 * pulse),
    )


def update_damage_trail(player_num: int, current_hp: float, external_trail: float) -> float:
    """Hold white damage bar for 15 frames on hit, then quickly catch down to current HP."""
    prev_hp = _LAST_SEEN_HEALTH.get(player_num, 1.0)
    trail = _INTERNAL_TRAIL.get(player_num, external_trail)

    # Reset on new round
    if current_hp > prev_hp + 0.2:
        _INTERNAL_TRAIL[player_num] = current_hp
        _TRAIL_HOLD_FRAMES[player_num] = 0
        _LAST_SEEN_HEALTH[player_num] = current_hp
        return current_hp

    if current_hp < prev_hp - 0.001:
        # Just took damage: start 15-frame hold
        _TRAIL_HOLD_FRAMES[player_num] = max(_TRAIL_HOLD_FRAMES.get(player_num, 0), 15)
        trail = max(trail, prev_hp)
    _LAST_SEEN_HEALTH[player_num] = current_hp

    hold = _TRAIL_HOLD_FRAMES.get(player_num, 0)
    if hold > 0:
        _TRAIL_HOLD_FRAMES[player_num] = hold - 1
    else:
        trail = max(current_hp, trail - 0.018)

    _INTERNAL_TRAIL[player_num] = trail
    return max(current_hp, trail, external_trail)


def draw_hud(surface, state, font_medium, font_small, hit_flash=0,
             trail1=1.0, trail2=1.0, combo1=0, combo2=0,
             diff1=None, diff2=None, sparks=None):
    """Draw modern fighting game HUD: portraits, slanted bars, diamond dots, hex timer, sparks."""
    f1 = state.fighter1
    f2 = state.fighter2
    now = time.time()

    eff_trail1 = update_damage_trail(1, f1.health, trail1)
    eff_trail2 = update_damage_trail(2, f2.health, trail2)

    enable_sw = getattr(getattr(state, "rules", None), "enable_shield_wall", False)

    # --- Fighter 1 & Fighter 2 HUD Clusters ---
    _draw_fighter_hud(
        surface, 14, 12, f1, eff_trail1, f1.character_name,
        diff1, state.p1_rounds_won, font_small, left_aligned=True,
        now=now, enable_shield_wall=enable_sw
    )
    _draw_fighter_hud(
        surface, SCREEN_WIDTH - 14, 12, f2, eff_trail2, f2.character_name,
        diff2, state.p2_rounds_won, font_small, left_aligned=False,
        now=now, enable_shield_wall=enable_sw
    )

    # --- Hexagonal Center Timer Badge ---
    from backend.engine.constants import FPS
    seconds_left = max(0, state.round_frames_left // FPS)
    _draw_hex_timer(surface, seconds_left, state.round_number, font_medium, font_small, now)

    # --- Combo Counters ---
    font_combo = _get_font(36)
    if combo1 >= 2 or f1.combo_hits >= 2:
        hits = max(combo1, f1.combo_hits)
        _draw_combo_badge(surface, 84, 96, hits, font_combo, font_small, left_aligned=True)
    if combo2 >= 2 or f2.combo_hits >= 2:
        hits = max(combo2, f2.combo_hits)
        _draw_combo_badge(surface, SCREEN_WIDTH - 84, 96, hits, font_combo, font_small, left_aligned=False)

    # --- Starburst Hit Sparks ---
    if sparks:
        for s in sparks:
            _draw_spark(
                surface,
                s["x"],
                s["y"],
                s["colour"],
                s["frame"],
                kind=s.get("kind", "hit"),
            )

    # --- Full-screen Hit / Counter Flash ---
    if hit_flash > 0:
        flash_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        alpha = min(80, hit_flash * 22)
        flash_col = (255, 70, 70, alpha) if hit_flash >= 4 else (255, 255, 255, alpha)
        flash_surface.fill(flash_col)
        surface.blit(flash_surface, (0, 0))


def _draw_fighter_hud(
    surface: pygame.Surface,
    outer_x: int,
    y: int,
    fighter,
    trail_health: float,
    name: str,
    difficulty,
    rounds_won: int,
    font: pygame.font.Font,
    left_aligned: bool = True,
    now: float = 0.0,
    enable_shield_wall: bool = False,
):
    """Draw portrait frame, slanted health bar, white drop, guard bar, 3-seg super meter, and diamond dots."""
    health = max(0.0, min(1.0, fighter.health))
    guard = max(0.0, min(1.0, fighter.guard_meter / 100.0))
    super_meter = max(0.0, min(1.0, fighter.meter / 100.0))

    palette = PRIMARY_PALETTES.get(name, {})
    subtitle = palette.get("subtitle", palette.get("title", name))
    accent_col = palette.get("accent", (255, 215, 0))
    p_col = P1_COLOUR if left_aligned else P2_COLOUR

    # 1. Stylized Portrait Frame at outer edge (54 x 54)
    port_size = 54
    port_x = outer_x if left_aligned else (outer_x - port_size)
    port_y = y + 4
    port_rect = pygame.Rect(port_x, port_y, port_size, port_size)

    pygame.draw.rect(surface, (14, 18, 30), port_rect.inflate(4, 4), border_radius=8)
    port_img = assets.get_portrait(name, size=(port_size, port_size), flip_h=(not left_aligned))
    surface.blit(port_img, port_rect.topleft)
    pygame.draw.rect(surface, p_col, port_rect.inflate(2, 2), 2, border_radius=7)
    pygame.draw.rect(surface, accent_col, port_rect.inflate(-2, -2), 1, border_radius=5)

    # 2. Bar geometry
    bar_w = HEALTH_BAR_WIDTH + 20  # 340 px
    bar_h = 22
    bar_y = y + 20
    skew = -10 if left_aligned else 10
    bar_x = (port_rect.right + 10) if left_aligned else (port_rect.left - 10 - bar_w)

    # 3. Fighter Name (bold uppercase above bar) + small title
    font_name = _get_font(21)
    font_sub = _get_font(16)
    lvl = getattr(fighter, "level", 1)
    lvl_str = f" [Lv.{lvl}]" if lvl > 1 else ""
    upper_name = f"{name.upper()}{lvl_str} — {subtitle}"
    if difficulty:
        upper_name += f" [{difficulty}]"
    if fighter.is_fury:
        upper_name += " [FURY]"

    name_col = (255, 95, 95) if fighter.is_fury else WHITE
    name_surf = font_name.render(upper_name, True, name_col)
    name_shadow = font_name.render(upper_name, True, BLACK)
    if left_aligned:
        nx = bar_x + 4
    else:
        nx = bar_x + bar_w - name_surf.get_width() - 4
    surface.blit(name_shadow, (nx + 1, y + 2))
    surface.blit(name_surf, (nx, y + 1))

    # 4. Angled/Slanted Parallelogram Health Bar
    bg_pts = _parallelogram_pts(bar_x, bar_y, bar_w, bar_h, skew)
    pygame.draw.polygon(surface, (12, 14, 22), _parallelogram_pts(bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4, skew))
    pygame.draw.polygon(surface, HEALTH_BG, bg_pts)

    # White sliding damage trail
    trail_clamped = max(health, min(1.0, trail_health))
    trail_w = int(bar_w * trail_clamped)
    if trail_w > 0:
        tx = bar_x if left_aligned else (bar_x + bar_w - trail_w)
        t_pts = _parallelogram_pts(tx, bar_y + 1, trail_w, bar_h - 2, skew)
        pygame.draw.polygon(surface, HEALTH_TRAIL, t_pts)

    # Main health fill (green >60%, yellow 25-60%, pulsing red <25%)
    fill_w = int(bar_w * health)
    if fill_w > 0:
        hp_col = _health_color(health, now)
        top_shine = (
            min(255, hp_col[0] + 45),
            min(255, hp_col[1] + 45),
            min(255, hp_col[2] + 45),
        )
        fx = bar_x if left_aligned else (bar_x + bar_w - fill_w)
        f_pts = _parallelogram_pts(fx, bar_y + 1, fill_w, bar_h - 2, skew)
        pygame.draw.polygon(surface, hp_col, f_pts)
        # Top gradient highlight strip
        shine_pts = _parallelogram_pts(fx, bar_y + 2, fill_w, max(4, bar_h // 3), int(skew * 0.35))
        pygame.draw.polygon(surface, top_shine, shine_pts)

    # Slanted border with soft green pulse during active health regeneration
    is_regenerating = (
        getattr(fighter, "regen_enabled", False)
        and fighter.health < 1.0
        and (getattr(fighter, "no_hit_timer", 0) >= 120 or fighter.is_crouching or getattr(fighter, "is_blocking", False) or fighter.blockstun > 0)
    )
    if is_regenerating:
        pulse = 0.5 + 0.5 * math.sin(now * 8.0)
        border_col = (int(50 + 70 * pulse), int(210 + 45 * pulse), int(90 + 80 * pulse))
        pygame.draw.polygon(surface, border_col, bg_pts, 3)
    else:
        border_col = (255, 70, 70) if fighter.is_fury else (195, 208, 228)
        pygame.draw.polygon(surface, border_col, bg_pts, 2)

    # 5. Guard Meter (slim slanted bar under health bar)
    guard_y = bar_y + bar_h + 3
    guard_h = 5
    g_bg_pts = _parallelogram_pts(bar_x, guard_y, bar_w, guard_h, int(skew * 0.4))
    pygame.draw.polygon(surface, (24, 28, 42), g_bg_pts)
    guard_w = int(bar_w * guard)
    if guard_w > 0:
        if guard > 0.50:
            g_col = (70, 205, 255)
        elif guard > 0.25:
            g_col = (255, 165, 40)  # orange when low
        else:
            flash = int(now * 16) % 2 == 0
            g_col = (255, 50, 50) if flash else (180, 20, 20)
        gx = bar_x if left_aligned else (bar_x + bar_w - guard_w)
        g_pts = _parallelogram_pts(gx, guard_y, guard_w, guard_h, int(skew * 0.4))
        pygame.draw.polygon(surface, g_col, g_pts)

    # 6. 3-Segment Super Meter with metallic borders & full-bar ripple
    meter_y = guard_y + guard_h + 3
    seg_gap = 4
    seg_w = (bar_w - seg_gap * 2) // 3
    seg_h = 8
    is_max = super_meter >= 0.999 or (fighter.is_fury and super_meter >= 0.60)

    for seg_idx in range(3):
        sx = (bar_x + seg_idx * (seg_w + seg_gap)) if left_aligned else (bar_x + bar_w - (seg_idx + 1) * seg_w - seg_idx * seg_gap)
        s_pts = _parallelogram_pts(sx, meter_y, seg_w, seg_h, int(skew * 0.35))
        pygame.draw.polygon(surface, (18, 22, 36), s_pts)

        seg_start = seg_idx / 3.0
        seg_fill = max(0.0, min(1.0, (super_meter - seg_start) * 3.0))
        if seg_fill > 0:
            fw = int(seg_w * seg_fill)
            fx = sx if left_aligned else (sx + seg_w - fw)
            f_pts = _parallelogram_pts(fx, meter_y + 1, fw, seg_h - 2, int(skew * 0.35))
            if is_max:
                pulse = 0.5 + 0.5 * math.sin(now * 15.0 + seg_idx)
                m_col = (int(80 + 175 * pulse), int(225 + 30 * pulse), 255)
            else:
                m_col = (0, int(175 + 45 * seg_fill), 255)
            pygame.draw.polygon(surface, m_col, f_pts)

        pygame.draw.polygon(surface, (130, 145, 170), s_pts, 1)

    if is_max:
        max_lbl = font_sub.render("MAX", True, (255, 230, 80))
        mx = (bar_x + bar_w + 4) if left_aligned else (bar_x - max_lbl.get_width() - 4)
        surface.blit(max_lbl, (mx, meter_y - 2))

    # 7. Stylized Diamond Round-Win Markers
    diam_y = meter_y + seg_h + 9
    for d_idx in range(2):
        dx = (bar_x + 10 + d_idx * 18) if left_aligned else (bar_x + bar_w - 10 - d_idx * 18)
        r = 6
        d_pts = [(dx, diam_y - r), (dx + r, diam_y), (dx, diam_y + r), (dx - r, diam_y)]
        if rounds_won > d_idx:
            # Filled glowing diamond
            glow_pts = [(dx, diam_y - r - 2), (dx + r + 2, diam_y), (dx, diam_y + r + 2), (dx - r - 2, diam_y)]
            pygame.draw.polygon(surface, (255, 190, 40), glow_pts)
            pygame.draw.polygon(surface, (255, 235, 90), d_pts)
            pygame.draw.polygon(surface, WHITE, d_pts, 1)
        else:
            pygame.draw.polygon(surface, (35, 40, 58), d_pts)
            pygame.draw.polygon(surface, (120, 130, 155), d_pts, 1)

    # 8. Adrenaline Boost Badge when active (< 25% HP for AI)
    if difficulty and health < 0.25:
        tag_surf = font_sub.render("ADRENALINE BOOST", True, WHITE)
        tw = tag_surf.get_width() + 12
        th = tag_surf.get_height() + 4
        tx = (bar_x + 48) if left_aligned else (bar_x + bar_w - 48 - tw)
        t_rect = pygame.Rect(tx, diam_y - th // 2, tw, th)
        pygame.draw.rect(surface, (215, 35, 35), t_rect, border_radius=4)
        pygame.draw.rect(surface, (255, 215, 60), t_rect, 1, border_radius=4)
        surface.blit(tag_surf, tag_surf.get_rect(center=t_rect.center))

    # 9. Compact Hexagonal Shield Energy Badge near portrait (if enabled)
    if enable_shield_wall:
        sw_energy = int(round(getattr(fighter, "shield_energy", 100.0)))
        hx = port_rect.centerx
        hy = port_rect.bottom + 14
        hex_r = 11
        h_pts = [
            (hx + int(hex_r * math.cos(math.radians(60 * k - 30))),
             hy + int(hex_r * math.sin(math.radians(60 * k - 30))))
            for k in range(6)
        ]
        pygame.draw.polygon(surface, (16, 24, 40), h_pts)
        ring_col = (0, 225, 255) if sw_energy >= 35 else (255, 110, 80)
        pygame.draw.polygon(surface, ring_col, h_pts, 2)
        sw_txt = font_sub.render(f"{sw_energy}%", True, WHITE)
        surface.blit(sw_txt, sw_txt.get_rect(center=(hx, hy)))


def _draw_hex_timer(
    surface: pygame.Surface,
    seconds_left: int,
    round_num: int,
    font_medium: pygame.font.Font,
    font_small: pygame.font.Font,
    now: float,
):
    """Draw centered hexagonal timer badge that turns red and pulses under 10s."""
    cx = SCREEN_WIDTH // 2
    cy = 34
    rx, ry = 36, 22
    hex_pts = [
        (cx - rx, cy),
        (cx - rx + 10, cy - ry),
        (cx + rx - 10, cy - ry),
        (cx + rx, cy),
        (cx + rx - 10, cy + ry),
        (cx - rx + 10, cy + ry),
    ]
    pygame.draw.polygon(surface, (16, 20, 36), hex_pts)

    is_low = seconds_left < 10
    if is_low:
        pulse = 0.5 + 0.5 * math.sin(now * 12.0)
        border_col = (255, int(60 + 80 * pulse), int(60 + 80 * pulse))
        txt_col = (255, int(50 + 90 * pulse), int(50 + 90 * pulse))
        font_timer = _get_font(int(36 + 5 * pulse))
    else:
        border_col = (95, 175, 245)
        txt_col = TIMER_COLOUR
        font_timer = _get_font(36)

    pygame.draw.polygon(surface, border_col, hex_pts, 2)

    t_surf = font_timer.render(f"{seconds_left:02d}", True, txt_col)
    t_shadow = font_timer.render(f"{seconds_left:02d}", True, BLACK)
    surface.blit(t_shadow, t_surf.get_rect(center=(cx + 1, cy + 1)))
    surface.blit(t_surf, t_surf.get_rect(center=(cx, cy)))

    # Round label under hexagon
    r_surf = font_small.render(f"ROUND {round_num}", True, (210, 220, 240))
    surface.blit(r_surf, r_surf.get_rect(midtop=(cx, cy + ry + 3)))


def _draw_combo_badge(
    surface: pygame.Surface,
    x: int,
    y: int,
    hits: int,
    font_combo: pygame.font.Font,
    font_small: pygame.font.Font,
    left_aligned: bool = True,
):
    """Draw stylized combo counter callout."""
    txt = f"{hits} HIT COMBO!"
    c_surf = font_combo.render(txt, True, (255, 220, 45))
    s_surf = font_combo.render(txt, True, BLACK)
    rx = x if left_aligned else (x - c_surf.get_width())
    surface.blit(s_surf, (rx + 2, y + 2))
    surface.blit(c_surf, (rx, y))


def _draw_spark(surface, x: int, y: int, colour, frame: int, kind: str = "hit"):
    """Draw sharp starburst polygon sparks on hit, hexagonal ripple on block, red burst on counter."""
    cx, cy = int(x), int(y)
    is_block = (kind == "block" or colour == SPARK_BLOCK)
    is_counter = (kind == "counter" or colour == SPARK_COUNTER)

    if is_block:
        # Blue-white hexagonal shield ripple
        rad = 10 + frame * 4
        hex_pts = [
            (cx + int(rad * math.cos(math.radians(60 * k))),
             cy + int(rad * math.sin(math.radians(60 * k))))
            for k in range(6)
        ]
        pygame.draw.polygon(surface, (70, 195, 255), hex_pts, 2)
        in_rad = max(4, rad - 6)
        in_pts = [
            (cx + int(in_rad * math.cos(math.radians(60 * k + 30))),
             cy + int(in_rad * math.sin(math.radians(60 * k + 30))))
            for k in range(6)
        ]
        pygame.draw.polygon(surface, WHITE, in_pts, 1)
        return

    # Starburst polygon (hit or counter-hit)
    num_spikes = 10 if is_counter else 8
    outer_r = (34 if is_counter else 26) - frame * 2
    inner_r = max(4, outer_r // 3)
    if outer_r <= 4:
        return

    edge_col = (255, 55, 55) if is_counter else (255, 215, 45)
    outer_pts = []
    core_pts = []
    for i in range(num_spikes * 2):
        ang = (i * math.pi) / num_spikes + (frame * 0.15)
        r = outer_r if (i % 2 == 0) else inner_r
        outer_pts.append((cx + int(math.cos(ang) * r), cy + int(math.sin(ang) * r)))
        rc = max(2, int(r * 0.55))
        core_pts.append((cx + int(math.cos(ang) * rc), cy + int(math.sin(ang) * rc)))

    pygame.draw.polygon(surface, edge_col, outer_pts)
    pygame.draw.polygon(surface, WHITE, core_pts)
