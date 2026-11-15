"""Draw fighters as distinctive shape-based combatants.

Each fighter is recognizable at a glance through distinct body proportions,
costumes, emblems, and accessories:
  - Crimson Brawler: wide stocky body, red gi + black, taped fists, flame chest crest.
  - Steel Guardian: tallest and widest, steel plate + navy, square shoulder plates & forearm shields.
  - Shadow Striker: thinnest body, purple + black, glowing teal eyes, long trailing scarf.
  - Golden Tactician: medium build, gold + white robe, flowing sash, compass emblem.

Supports crouching postures, knockdowns, low/high block shields, and kick/punch extensions.
"""

import math
import pygame

from backend.ai.actions import Action
from backend.engine.constants import JUMP_DURATION
from frontend.theme import (
    DEFAULT_PROPORTIONS,
    FIGHTER_PROPORTIONS,
    FLOOR_HEIGHT,
    P1_COLOUR,
    P2_COLOUR,
    WHITE,
    get_fighter_palette,
)


def draw_fighter(surface, fighter_state, facing_right, arena_offset_x=0,
                 ground_y=FLOOR_HEIGHT, player_num=1, is_mirror=False,
                 is_human=False):
    """Draw one fighter on the screen with full personality styling."""
    name = fighter_state.character_name
    palette = get_fighter_palette(name, is_p2_mirror=(player_num == 2 and is_mirror))
    body_col = palette["body"]
    trim_col = palette["secondary"]
    accent_col = palette.get("accent", (240, 200, 50))
    emblem_type = palette.get("emblem", "compass")

    props = FIGHTER_PROPORTIONS.get(name, DEFAULT_PROPORTIONS)
    b_width = props["body_width"]
    b_height = props["body_height"]
    h_radius = props["head_radius"]
    arm_len = props["arm_length"]
    leg_len = props["leg_length"]
    accent_style = props.get("special_accent", "")

    screen_x = arena_offset_x + fighter_state.x
    cx = int(screen_x)
    arm_dir = 1 if facing_right else -1

    # Knockdown pose
    if fighter_state.is_knocked_down:
        _draw_shadow(surface, cx, ground_y, 0, player_num)
        prone_w = b_height + leg_len
        prone_h = b_width // 2
        prone_rect = pygame.Rect(cx - prone_w // 2, ground_y - prone_h, prone_w, prone_h)
        pygame.draw.rect(surface, body_col, prone_rect, border_radius=4)
        pygame.draw.rect(surface, trim_col, prone_rect, 2, border_radius=4)
        head_x = cx - arm_dir * (prone_w // 2 - h_radius)
        pygame.draw.circle(surface, body_col, (head_x, ground_y - prone_h // 2), h_radius)
        pygame.draw.circle(surface, trim_col, (head_x, ground_y - prone_h // 2), h_radius, 2)
        _draw_overhead_tag(surface, cx, ground_y - prone_h - 24, player_num, is_human)
        return

    # Jump offset
    jump_y = 0
    if fighter_state.in_air and fighter_state.jump_frame > 0:
        progress = fighter_state.jump_frame / JUMP_DURATION
        jump_y = math.sin(progress * math.pi) * 120

    # Crouch posture adjustment
    crouch_offset = 0
    if fighter_state.is_crouching and not fighter_state.in_air:
        crouch_offset = 20
        b_height = int(b_height * 0.75)
        leg_len = max(8, leg_len - 16)

    body_top = ground_y - b_height - leg_len - jump_y + (crouch_offset * 0.5)

    # --- 1. Floor Shadow ---
    _draw_shadow(surface, cx, ground_y, jump_y, player_num)

    # --- 2. Background Accessories ---
    if accent_style == "trailing_scarf":
        _draw_trailing_scarf(surface, cx, body_top + 10, arm_dir, accent_col)

    # --- 3. Legs ---
    hip_y = int(body_top + b_height)
    hip_width = b_width // 4
    is_kicking = (
        fighter_state.attack_phase == "active"
        and fighter_state.attack_type in ("light_kick", "heavy_kick", "low_sweep", "crouch_kick", "jump_kick")
    )

    if is_kicking:
        # Front leg kicked out horizontally
        kick_reach = 45 if "heavy" in fighter_state.attack_type or "sweep" in fighter_state.attack_type else 32
        kick_y = hip_y + (leg_len if "sweep" in fighter_state.attack_type or "crouch" in fighter_state.attack_type else leg_len // 2)
        pygame.draw.line(surface, trim_col, (cx - hip_width, hip_y), (cx - hip_width - 4, hip_y + leg_len), 5)
        pygame.draw.line(surface, accent_col, (cx + hip_width, hip_y), (cx + arm_dir * kick_reach, kick_y), 6)
        pygame.draw.circle(surface, trim_col, (cx + arm_dir * kick_reach, kick_y), 6)
    else:
        pygame.draw.line(surface, trim_col, (cx - hip_width, hip_y), (cx - hip_width - 6, hip_y + leg_len), 5)
        pygame.draw.line(surface, trim_col, (cx + hip_width, hip_y), (cx + hip_width + 6, hip_y + leg_len), 5)

    # --- 4. Torso / Body ---
    body_rect = pygame.Rect(cx - b_width // 2, int(body_top), b_width, b_height)
    pygame.draw.rect(surface, body_col, body_rect, border_radius=4)
    pygame.draw.rect(surface, trim_col, body_rect, 2, border_radius=4)

    # Chest emblem
    _draw_emblem(surface, cx, int(body_top + b_height * 0.35), emblem_type, accent_col)

    # Special costume details
    if accent_style == "robe_sash":
        sash_rect = pygame.Rect(cx - b_width // 2, int(body_top + b_height * 0.65), b_width, 8)
        pygame.draw.rect(surface, accent_col, sash_rect)
        pygame.draw.line(surface, accent_col, (cx - arm_dir * 4, int(body_top + b_height * 0.65)),
                         (cx - arm_dir * 12, hip_y + 16), 4)

    elif accent_style == "shoulder_shields":
        sh_left = pygame.Rect(cx - b_width // 2 - 8, int(body_top - 2), 14, 16)
        sh_right = pygame.Rect(cx + b_width // 2 - 6, int(body_top - 2), 14, 16)
        for sh in [sh_left, sh_right]:
            pygame.draw.rect(surface, body_col, sh, border_radius=3)
            pygame.draw.rect(surface, accent_col, sh, 2, border_radius=3)

    # --- 5. Head ---
    head_y = int(body_top - h_radius)
    pygame.draw.circle(surface, body_col, (cx, head_y), h_radius)
    pygame.draw.circle(surface, trim_col, (cx, head_y), h_radius, 2)

    # Eyes / visor
    eye_x = cx + arm_dir * (h_radius // 2)
    if name == "Shadow":
        pygame.draw.circle(surface, accent_col, (eye_x, head_y - 2), 3)
    elif name == "Steel":
        pygame.draw.line(surface, accent_col, (eye_x - 4, head_y - 2), (eye_x + 4, head_y - 2), 3)
    else:
        pygame.draw.line(surface, WHITE, (eye_x - 2, head_y - 2), (eye_x + 2, head_y - 2), 2)

    # --- 6. Arms & Attack Animations ---
    shoulder_y = int(body_top + 10)
    arm_extend = 0
    if fighter_state.attack_phase == "active" and not is_kicking:
        arm_extend = 32 if "heavy" in fighter_state.attack_type or "overhead" in fighter_state.attack_type else 22
    elif fighter_state.attack_phase == "startup":
        arm_extend = -10

    back_arm_x = cx - arm_dir * (b_width // 2)
    pygame.draw.line(surface, trim_col, (back_arm_x, shoulder_y),
                     (back_arm_x - arm_dir * 8, shoulder_y + arm_len - 4), 4)

    front_shoulder_x = cx + arm_dir * (b_width // 2)
    punch_x = front_shoulder_x + arm_dir * (arm_len + arm_extend)
    punch_y = shoulder_y + 4 if fighter_state.attack_type != "anti_air" else shoulder_y - 18
    pygame.draw.line(surface, trim_col, (front_shoulder_x, shoulder_y),
                     (int(punch_x), int(punch_y)), 5)

    if accent_style == "taped_fists":
        pygame.draw.circle(surface, (240, 240, 240), (int(punch_x), int(punch_y)), 7)
        pygame.draw.circle(surface, (180, 20, 20), (int(punch_x), int(punch_y)), 7, 2)
    elif accent_style == "shoulder_shields":
        shield_plate = pygame.Rect(int(punch_x) - 4, int(punch_y) - 10, 10, 20)
        pygame.draw.rect(surface, accent_col, shield_plate, border_radius=2)
        pygame.draw.rect(surface, trim_col, shield_plate, 2, border_radius=2)
    else:
        pygame.draw.circle(surface, accent_col, (int(punch_x), int(punch_y)), 5)

    # --- 7. Block Shield Effect (High & Low) ---
    is_blocking = (
        fighter_state.last_action in (Action.BLOCK, Action.BLOCK_LOW)
        or fighter_state.blockstun > 0
    )
    if is_blocking:
        is_low = fighter_state.is_crouching or fighter_state.last_action == Action.BLOCK_LOW
        bx = cx + arm_dir * (b_width // 2 + 10)
        if is_low:
            by = int(ground_y - 36)
            shield_surf = pygame.Surface((24, 35), pygame.SRCALPHA)
            shield_surf.fill((60, 160, 240, 180))
            pygame.draw.rect(shield_surf, (220, 245, 255), (0, 0, 24, 35), 2, border_radius=4)
            surface.blit(shield_surf, (bx - 12, by))
        else:
            by = int(body_top + 6)
            shield_surf = pygame.Surface((20, 52), pygame.SRCALPHA)
            shield_surf.fill((60, 160, 240, 180))
            pygame.draw.rect(shield_surf, (220, 245, 255), (0, 0, 20, 52), 2, border_radius=4)
            surface.blit(shield_surf, (bx - 10, by))

    # --- 8. Overhead Tag ---
    _draw_overhead_tag(surface, cx, head_y - h_radius - 12, player_num, is_human)


def _draw_shadow(surface, cx, ground_y, jump_y, player_num):
    shrink = max(0.4, 1.0 - (jump_y / 160))
    w = int(60 * shrink)
    h = int(14 * shrink)
    shadow_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    base_col = P1_COLOUR if player_num == 1 else P2_COLOUR
    pygame.draw.ellipse(shadow_surf, (base_col[0] // 4, base_col[1] // 4, base_col[2] // 4, 110),
                        (0, 0, w, h))
    surface.blit(shadow_surf, (cx - w // 2, ground_y - h // 2))


def _draw_trailing_scarf(surface, cx, neck_y, arm_dir, colour):
    trail_dir = -arm_dir
    p1 = (cx, neck_y)
    p2 = (cx + trail_dir * 18, neck_y + 4)
    p3 = (cx + trail_dir * 36, neck_y + 14)
    pygame.draw.lines(surface, colour, False, [p1, p2, p3], 4)


def _draw_emblem(surface, cx, ey, emblem_type, colour):
    if emblem_type == "flame":
        pygame.draw.polygon(surface, colour, [
            (cx, ey - 7), (cx + 5, ey + 3), (cx + 2, ey + 6),
            (cx - 2, ey + 6), (cx - 5, ey + 3)
        ])
    elif emblem_type == "cross":
        pygame.draw.line(surface, colour, (cx - 5, ey), (cx + 5, ey), 3)
        pygame.draw.line(surface, colour, (cx, ey - 5), (cx, ey + 5), 3)
    elif emblem_type == "ring":
        pygame.draw.circle(surface, colour, (cx, ey), 5, 2)
    else:  # compass
        pygame.draw.line(surface, colour, (cx, ey - 5), (cx, ey + 5), 2)
        pygame.draw.line(surface, colour, (cx - 5, ey), (cx + 5, ey), 2)
        pygame.draw.circle(surface, colour, (cx, ey), 3, 1)


def _draw_overhead_tag(surface, cx, tag_y, player_num, is_human):
    text = "YOU" if is_human else f"P{player_num}"
    tag_font = pygame.font.Font(None, 18)
    rendered = tag_font.render(text, True, (255, 255, 255))
    tw, th = rendered.get_size()
    px, py = cx - tw // 2, tag_y - th // 2
    pad_x, pad_y = 6, 2
    bg_rect = pygame.Rect(px - pad_x, py - pad_y, tw + pad_x * 2, th + pad_y * 2)
    col = P1_COLOUR if player_num == 1 else P2_COLOUR
    tag_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
    tag_surf.fill((col[0], col[1], col[2], 220))
    pygame.draw.rect(tag_surf, (255, 255, 255, 120), (0, 0, bg_rect.width, bg_rect.height), 1, border_radius=3)
    surface.blit(tag_surf, (bg_rect.x, bg_rect.y))
    surface.blit(rendered, (px, py))
