"""Draw fighters as simple shapes — no sprites, no copyrighted art.

Each fighter is drawn as: a circle head, a rectangle body, two line arms,
two line legs. Colours come from FIGHTER_COLOURS in colours.py.
"""

import math

import pygame

from backend.engine.constants import JUMP_DURATION
from frontend.colours import (
    ARM_LENGTH,
    BODY_HEIGHT,
    BODY_WIDTH,
    FIGHTER_COLOURS,
    HEAD_RADIUS,
    LEG_LENGTH,
    WHITE,
)


def draw_fighter(surface, fighter_state, facing_right, arena_offset_x=0,
                 ground_y=450):
    """Draw one fighter on the screen.

    fighter_state: a FighterState from the engine.
    facing_right: True if this fighter faces right (toward the enemy).
    arena_offset_x: pixel offset to centre the arena on screen.
    ground_y: Y pixel position of the ground.
    """
    name = fighter_state.character_name
    body_colour, trim_colour = FIGHTER_COLOURS.get(name, (WHITE, WHITE))

    # X position on screen
    screen_x = arena_offset_x + fighter_state.x

    # Y position: jump makes the fighter go up and come back down
    jump_y = 0
    if fighter_state.in_air and fighter_state.jump_frame > 0:
        # Simple arc: sin curve over the jump duration
        progress = fighter_state.jump_frame / JUMP_DURATION
        jump_y = math.sin(progress * math.pi) * 120  # 120 px max height

    body_top = ground_y - BODY_HEIGHT - jump_y
    body_centre_x = int(screen_x)
    body_centre_y = int(body_top + BODY_HEIGHT // 2)

    # --- Head (circle) ---
    head_y = int(body_top - HEAD_RADIUS)
    pygame.draw.circle(surface, body_colour, (body_centre_x, head_y), HEAD_RADIUS)
    pygame.draw.circle(surface, trim_colour, (body_centre_x, head_y), HEAD_RADIUS, 2)

    # --- Body (rectangle) ---
    body_rect = pygame.Rect(
        body_centre_x - BODY_WIDTH // 2,
        int(body_top),
        BODY_WIDTH,
        BODY_HEIGHT,
    )
    pygame.draw.rect(surface, body_colour, body_rect)
    pygame.draw.rect(surface, trim_colour, body_rect, 2)

    # --- Arms ---
    arm_dir = 1 if facing_right else -1
    shoulder_y = int(body_top + 10)

    # Attack animation: arm extends during active phase
    arm_extend = 0
    if fighter_state.attack_phase == "active":
        arm_extend = 20
    elif fighter_state.attack_phase == "startup":
        arm_extend = -10  # pull back before striking

    # Front arm (the one that punches)
    front_arm_end_x = body_centre_x + arm_dir * (ARM_LENGTH + arm_extend)
    front_arm_end_y = shoulder_y + 5
    pygame.draw.line(surface, trim_colour,
                     (body_centre_x + arm_dir * (BODY_WIDTH // 2), shoulder_y),
                     (int(front_arm_end_x), front_arm_end_y), 4)

    # Back arm (hangs down)
    back_arm_end_x = body_centre_x - arm_dir * 10
    back_arm_end_y = shoulder_y + ARM_LENGTH
    pygame.draw.line(surface, trim_colour,
                     (body_centre_x - arm_dir * (BODY_WIDTH // 2), shoulder_y),
                     (int(back_arm_end_x), int(back_arm_end_y)), 3)

    # --- Legs ---
    hip_y = int(body_top + BODY_HEIGHT)
    # Left leg
    pygame.draw.line(surface, trim_colour,
                     (body_centre_x - 8, hip_y),
                     (body_centre_x - 14, hip_y + LEG_LENGTH), 4)
    # Right leg
    pygame.draw.line(surface, trim_colour,
                     (body_centre_x + 8, hip_y),
                     (body_centre_x + 14, hip_y + LEG_LENGTH), 4)

    # --- Block indicator (shield shape when blocking) ---
    if fighter_state.last_action.name == "BLOCK":
        shield_x = body_centre_x + arm_dir * (BODY_WIDTH // 2 + 5)
        shield_rect = pygame.Rect(int(shield_x) - 6, int(body_top + 15), 12, 40)
        pygame.draw.rect(surface, (100, 200, 255), shield_rect)
        pygame.draw.rect(surface, WHITE, shield_rect, 2)
