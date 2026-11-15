"""Draw fighters as distinctive shape-based combatants.

Each fighter is recognizable at a glance through distinct body proportions,
costumes, emblems, and accessories:
  - Crimson Brawler: wide stocky body, red gi + black, taped fists, flame chest crest.
  - Steel Guardian: tallest and widest, steel plate + navy, square shoulder plates & forearm shields.
  - Shadow Striker: thinnest body, purple + black, glowing teal eyes, long trailing scarf.
  - Golden Tactician: medium build, gold + white robe, flowing sash, compass emblem.

Includes overhead tags ("YOU", "P1", "P2"), player-coloured floor shadows,
and alternate palettes for mirror matches.
"""

import math
import pygame

from backend.engine.constants import JUMP_DURATION
from frontend.theme import (
    FLOOR_HEIGHT,
    FIGHTER_PROPORTIONS,
    DEFAULT_PROPORTIONS,
    P1_COLOUR,
    P2_COLOUR,
    get_fighter_palette,
    WHITE,
    BLACK,
)


def draw_fighter(surface, fighter_state, facing_right, arena_offset_x=0,
                 ground_y=FLOOR_HEIGHT, player_num=1, is_mirror=False,
                 is_human=False):
    """Draw one fighter on the screen with full personality styling.

    fighter_state: a FighterState from the engine.
    facing_right: True if this fighter faces right (toward the enemy).
    arena_offset_x: pixel offset to centre the arena on screen.
    ground_y: Y pixel position of the arena floor.
    player_num: 1 or 2.
    is_mirror: True if both players chose the same character (P2 gets alternate palette).
    is_human: True if this fighter is human-controlled (shows 'YOU' tag).
    """
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

    # Screen coordinates
    screen_x = arena_offset_x + fighter_state.x

    # Jump offset
    jump_y = 0
    if fighter_state.in_air and fighter_state.jump_frame > 0:
        progress = fighter_state.jump_frame / JUMP_DURATION
        jump_y = math.sin(progress * math.pi) * 120

    body_top = ground_y - b_height - leg_len - jump_y
    cx = int(screen_x)
    arm_dir = 1 if facing_right else -1

    # --- 1. Floor Shadow ---
    _draw_shadow(surface, cx, ground_y, jump_y, player_num)

    # --- 2. Character-Specific Background Accessories (e.g. Shadow's trailing scarf) ---
    if accent_style == "trailing_scarf":
        _draw_trailing_scarf(surface, cx, body_top + 10, arm_dir, accent_col)

    # --- 3. Legs ---
    hip_y = int(body_top + b_height)
    hip_width = b_width // 4
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
        # Golden's waist sash
        sash_rect = pygame.Rect(cx - b_width // 2, int(body_top + b_height * 0.65), b_width, 8)
        pygame.draw.rect(surface, accent_col, sash_rect)
        # Flowing sash ribbons
        pygame.draw.line(surface, accent_col, (cx - arm_dir * 4, int(body_top + b_height * 0.65)),
                         (cx - arm_dir * 12, hip_y + 16), 4)

    elif accent_style == "shoulder_shields":
        # Steel's big shoulder armor plates
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
        # Glowing teal eyes
        pygame.draw.circle(surface, accent_col, (eye_x, head_y - 2), 3)
    elif name == "Steel":
        # Horizontal glowing visor slot
        pygame.draw.line(surface, accent_col, (eye_x - 4, head_y - 2), (eye_x + 4, head_y - 2), 3)
    else:
        # Standard fighter eye indicator
        pygame.draw.line(surface, WHITE, (eye_x - 2, head_y - 2), (eye_x + 2, head_y - 2), 2)

    # --- 6. Arms & Attack Animations ---
    shoulder_y = int(body_top + 10)
    arm_extend = 0
    if fighter_state.attack_phase == "active":
        arm_extend = 28 if fighter_state.attack_type == "heavy" else 20
    elif fighter_state.attack_phase == "startup":
        arm_extend = -12

    # Back arm
    back_arm_x = cx - arm_dir * (b_width // 2)
    pygame.draw.line(surface, trim_col, (back_arm_x, shoulder_y),
                     (back_arm_x - arm_dir * 8, shoulder_y + arm_len - 4), 4)

    # Front arm (punching arm)
    front_shoulder_x = cx + arm_dir * (b_width // 2)
    punch_x = front_shoulder_x + arm_dir * (arm_len + arm_extend)
    punch_y = shoulder_y + 4
    pygame.draw.line(surface, trim_col, (front_shoulder_x, shoulder_y),
                     (int(punch_x), int(punch_y)), 5)

    # Taped fists (Crimson) or Forearm Shields (Steel)
    if accent_style == "taped_fists":
        # Thick wrapped glove on fist
        pygame.draw.circle(surface, (240, 240, 240), (int(punch_x), int(punch_y)), 7)
        pygame.draw.circle(surface, (180, 20, 20), (int(punch_x), int(punch_y)), 7, 2)
    elif accent_style == "shoulder_shields":
        # Shield buckler on front arm
        shield_plate = pygame.Rect(int(punch_x) - 4, int(punch_y) - 10, 10, 20)
        pygame.draw.rect(surface, accent_col, shield_plate, border_radius=2)
        pygame.draw.rect(surface, trim_col, shield_plate, 2, border_radius=2)
    else:
        pygame.draw.circle(surface, accent_col, (int(punch_x), int(punch_y)), 5)

    # --- 7. Block Shield Effect ---
    if fighter_state.last_action.name == "BLOCK":
        bx = cx + arm_dir * (b_width // 2 + 10)
        by = int(body_top + 10)
        shield_surf = pygame.Surface((20, 50), pygame.SRCALPHA)
        shield_surf.fill((60, 160, 240, 180))
        pygame.draw.rect(shield_surf, (220, 245, 255), (0, 0, 20, 50), 2, border_radius=4)
        surface.blit(shield_surf, (bx - 10, by))

    # --- 8. Overhead Tag ("YOU", "P1", "P2") ---
    _draw_overhead_tag(surface, cx, head_y - h_radius - 12, player_num, is_human)


def _draw_shadow(surface, cx, ground_y, jump_y, player_num):
    """Draw a coloured ellipse shadow under the fighter that shrinks when jumping."""
    shrink = max(0.4, 1.0 - (jump_y / 160))
    w = int(60 * shrink)
    h = int(14 * shrink)
    shadow_surf = pygame.Surface((w, h), pygame.SRCALPHA)

    col = (52, 152, 219, 80) if player_num == 1 else (231, 76, 60, 80)
    pygame.draw.ellipse(shadow_surf, col, (0, 0, w, h))
    surface.blit(shadow_surf, (cx - w // 2, ground_y - h // 2))


def _draw_overhead_tag(surface, cx, tag_y, player_num, is_human):
    """Draw 'YOU' (for human) or 'P1' / 'P2' badge above the head."""
    label = "YOU" if is_human else f"P{player_num}"
    tag_col = P1_COLOUR if (is_human or player_num == 1) else P2_COLOUR

    font = pygame.font.Font(None, 18)
    text_surf = font.render(label, True, WHITE)
    rect = text_surf.get_rect(center=(cx, tag_y))

    badge = rect.inflate(12, 4)
    pygame.draw.rect(surface, tag_col, badge, border_radius=3)
    pygame.draw.rect(surface, WHITE, badge, 1, border_radius=3)
    surface.blit(text_surf, rect)


def _draw_trailing_scarf(surface, cx, neck_y, arm_dir, color):
    """Draw Shadow's trailing purple/teal scarf billowing in the wind."""
    tail_dir = -arm_dir
    p1 = (cx, neck_y)
    p2 = (cx + tail_dir * 18, neck_y + 8)
    p3 = (cx + tail_dir * 36, neck_y + 4)
    p4 = (cx + tail_dir * 48, neck_y + 18)
    pygame.draw.lines(surface, color, False, [p1, p2, p3, p4], 4)


def _draw_emblem(surface, cx, cy, emblem_type, color):
    """Draw a tiny emblem shape on the chest."""
    if emblem_type == "flame":
        # Flame: 3-point polygon
        points = [(cx, cy - 6), (cx + 5, cy + 4), (cx, cy + 2), (cx - 5, cy + 4)]
        pygame.draw.polygon(surface, color, points)
    elif emblem_type == "shield":
        # Shield crest
        points = [(cx - 5, cy - 5), (cx + 5, cy - 5), (cx + 5, cy), (cx, cy + 6), (cx - 5, cy)]
        pygame.draw.polygon(surface, color, points)
    elif emblem_type == "crescent":
        # Crescent moon
        pygame.draw.circle(surface, color, (cx, cy), 5)
        pygame.draw.circle(surface, (20, 20, 20), (cx + 2, cy - 1), 4)
    else:  # compass
        # Compass 4-point star
        pygame.draw.line(surface, color, (cx - 6, cy), (cx + 6, cy), 2)
        pygame.draw.line(surface, color, (cx, cy - 6), (cx, cy + 6), 2)
