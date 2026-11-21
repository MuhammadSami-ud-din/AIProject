"""Draw fighters as jointed 2D martial artists with keyframe pose blending.

Each fighter is drawn purely with code using rounded jointed limbs (head, torso,
upper/lower arms, hands, upper/lower legs, feet) with a 2-px dark outline,
directional shading, and a light rim highlight.

Unique character visual signatures:
  - Crimson: spiked red hair, sleeveless gi, taped fists, black belt with trailing ends,
             faint flame wisps when in Fury.
  - Steel:   heavy square shoulders, glowing blue visor slit, mechanical elbow/knee joints,
             arm-mounted shield plates.
  - Shadow:  cowl/hood, floating trailing scarf, wrapped limbs, glowing teal eyes,
             dark mist dissolution on dash.
  - Golden:  flowing martial artist robe, open chest, gold prayer beads around neck,
             reactive sash, faint golden compass circle under feet.
"""

import math
import time
from typing import Dict, Tuple
import pygame

from backend.ai.actions import Action
from backend.engine.constants import JUMP_DURATION
from frontend.assets import assets
from frontend.theme import (
    DEFAULT_PROPORTIONS,
    FIGHTER_PROPORTIONS,
    FLOOR_HEIGHT,
    P1_COLOUR,
    P2_COLOUR,
    WHITE,
    get_fighter_palette,
)

OUTLINE_DARK = (16, 18, 26)

# Realistic full-body sprite base dimensions anchored to floor
SPRITE_BASE_SIZES = {
    "Crimson": (78, 226),
    "Steel": (145, 226),
    "Shadow": (121, 226),
    "Golden": (91, 226),
}

# Mirror match palette tint multipliers (RGB) for P2 duplicate picks
MIRROR_TINT_FACTORS = {
    "Crimson": (255, 145, 60),    # Fiery orange/amber
    "Steel": (175, 215, 150),     # Bronze/patina green
    "Shadow": (120, 185, 255),    # Cyan/frost blue
    "Golden": (195, 210, 240),    # Silver/platinum
}

# Proportional height multipliers per pose relative to standing height (226 px)
POSE_HEIGHT_RATIOS: Dict[str, float] = {
    "idle": 1.00,
    "kick": 0.93,
    "punch": 0.92,
    "run": 0.89,
    "jump": 0.93,
    "crouch": 0.72,
}

# Horizontal center-of-mass compensation (fraction of sprite width along facing direction)
POSE_X_OFFSET_RATIOS: Dict[str, float] = {
    "idle": 0.00,
    "kick": 0.16,
    "punch": 0.08,
    "run": 0.02,
    "jump": 0.00,
    "crouch": 0.00,
}

_SPRITE_CACHE: Dict[Tuple[str, int, bool, str], pygame.Surface] = {}


def resolve_fighter_pose(fighter_state) -> str:
    """Determine the canonical visual pose key ('idle', 'kick', 'punch', 'run', 'jump', 'crouch') for a fighter."""
    if fighter_state.is_knocked_down or fighter_state.hitstun > 0:
        return "idle"

    last_act = fighter_state.last_action
    cur_act = fighter_state.current_action
    phase = fighter_state.attack_phase
    atk_type = (fighter_state.attack_type or "none").lower()

    kick_actions = (
        Action.LIGHT_KICK,
        Action.HEAVY_KICK,
        Action.LOW_SWEEP,
        Action.CROUCH_KICK,
        Action.JUMP_KICK,
    )

    if phase in ("startup", "active", "recovery"):
        if "kick" in atk_type or "sweep" in atk_type or cur_act in kick_actions or last_act in kick_actions:
            return "kick"
        return "punch"

    if fighter_state.in_air or cur_act == Action.JUMP or last_act == Action.JUMP:
        return "jump"

    if (
        fighter_state.is_crouching
        or cur_act in (Action.CROUCH, Action.BLOCK_LOW)
        or last_act in (Action.CROUCH, Action.BLOCK_LOW)
    ):
        return "crouch"

    if cur_act == Action.BLOCK or last_act == Action.BLOCK or fighter_state.blockstun > 0:
        return "idle"

    move_actions = (Action.FORWARD, Action.BACK, Action.DASH, Action.BACKDASH)
    if fighter_state.is_dashing or cur_act in move_actions or last_act in move_actions:
        return "run"

    return "idle"


def get_fighter_sprite_seamless(
    name: str,
    height: int = 226,
    is_mirror: bool = False,
    pose: str = "idle",
) -> pygame.Surface:
    """Return cleanly cropped, seamlessly scaled character sprite for the given pose with optional mirror tint."""
    canon_pose = assets.normalize_pose(pose)
    key = (name, height, is_mirror, canon_pose)
    if key in _SPRITE_CACHE:
        return _SPRITE_CACHE[key]

    raw = assets.get_fighter_sprite(name, pose=canon_pose)
    if raw is None:
        raw = pygame.Surface((70, height), pygame.SRCALPHA)

    # Auto-crop transparent margins so feet anchor precisely at bottom
    br = raw.get_bounding_rect()
    if br.width > 0 and br.height > 0:
        cropped = raw.subsurface(br)
    else:
        cropped = raw

    cw, ch = cropped.get_size()
    scale = height / float(max(1, ch))
    target_w = max(4, int(cw * scale))
    scaled = pygame.transform.smoothscale(cropped, (target_w, height))

    if is_mirror:
        tint_rgb = MIRROR_TINT_FACTORS.get(name, (200, 200, 200))
        tint_surf = pygame.Surface(scaled.get_size(), pygame.SRCALPHA)
        tint_surf.fill((*tint_rgb, 255))
        scaled.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    _SPRITE_CACHE[key] = scaled
    return scaled


def _get_anchored_transform(surface: pygame.Surface, angle_deg: float, scale_x: float, scale_y: float, target_x: float, target_y: float) -> Tuple[pygame.Surface, Tuple[int, int]]:
    """Scale and rotate surface anchored at bottom-center (feet) so feet stay locked to (target_x, target_y)."""
    orig_w, orig_h = surface.get_size()
    sw = max(2, int(orig_w * scale_x))
    sh = max(2, int(orig_h * scale_y))
    scaled = pygame.transform.smoothscale(surface, (sw, sh)) if (sw != orig_w or sh != orig_h) else surface

    if abs(angle_deg) < 0.05:
        topleft = (int(target_x - sw // 2), int(target_y - sh))
        return scaled, topleft

    rotated = pygame.transform.rotate(scaled, angle_deg)
    rad = math.radians(angle_deg)
    dx_rot = (sh / 2.0) * math.sin(rad)
    dy_rot = (sh / 2.0) * math.cos(rad)
    rcx, rcy = rotated.get_width() / 2.0, rotated.get_height() / 2.0
    anchor_x = rcx + dx_rot
    anchor_y = rcy + dy_rot
    topleft = (int(target_x - anchor_x), int(target_y - anchor_y))
    return rotated, topleft


def _draw_crescent_slash(surface, cx, cy, reach, arc_dir, color, is_heavy=False, is_kick=False):
    """Draw a high-intensity glowing crescent slash effect for punches and kicks."""
    curve_h = 32 if is_heavy else 22
    w = reach + 40
    h = curve_h * 2 + 30
    slash_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cy_local = h // 2

    outer = []
    inner = []
    num_pts = 16
    for i in range(num_pts):
        t = (i / float(num_pts - 1)) * math.pi - (math.pi / 2.0)
        ox = int(math.cos(t) * reach) + 8
        oy = int(cy_local + math.sin(t) * curve_h)
        inner_r = max(4, int(reach * (0.58 if is_heavy else 0.68)))
        ix = int(math.cos(t) * inner_r) + 8
        iy = int(cy_local + math.sin(t) * (curve_h * 0.60))
        outer.append((ox, oy))
        inner.append((ix, iy))

    poly = outer + inner[::-1]
    glow_col = (*color[:3], 215 if is_heavy else 165)
    pygame.draw.polygon(slash_surf, glow_col, poly)

    core_outer = outer[2:-2]
    core_inner = inner[2:-2]
    if core_outer and core_inner:
        pygame.draw.polygon(slash_surf, (255, 255, 255, 250 if is_heavy else 205), core_outer + core_inner[::-1])

    if is_heavy:
        for s in range(3):
            sp_y = cy_local - 10 + s * 10
            pygame.draw.line(slash_surf, (255, 255, 255, 190), (12, sp_y), (reach - 6, sp_y), 2)

    if arc_dir < 0:
        slash_surf = pygame.transform.flip(slash_surf, True, False)
        surface.blit(slash_surf, (cx - w, cy - cy_local))
    else:
        surface.blit(slash_surf, (cx, cy - cy_local))


def _draw_realistic_fighter(
    surface: pygame.Surface,
    fighter_state,
    facing_right: bool,
    arena_offset_x: int = 0,
    ground_y: int = FLOOR_HEIGHT,
    player_num: int = 1,
    is_mirror: bool = False,
    is_human: bool = False,
    hurt_flash_active: bool = False,
) -> bool:
    """Render pristine, high-fidelity character with dynamic combat physics and visual effects."""
    name = fighter_state.character_name
    palette = get_fighter_palette(name, is_p2_mirror=(player_num == 2 and is_mirror))
    accent_col = palette.get("accent", (240, 200, 50))

    arm_dir = 1 if facing_right else -1
    cx = int(arena_offset_x + fighter_state.x)
    anim_frame = getattr(fighter_state, "jump_frame", 0) or int(time.time() * 60) % 3600

    base_h = 226
    pose = resolve_fighter_pose(fighter_state)
    has_dedicated_pose = assets.has_fighter_pose(name, pose)
    target_h = int(base_h * POSE_HEIGHT_RATIOS.get(pose, 1.0)) if has_dedicated_pose else base_h
    active_pose = pose if has_dedicated_pose else "idle"

    sprite = get_fighter_sprite_seamless(
        name,
        height=target_h,
        is_mirror=(player_num == 2 and is_mirror),
        pose=active_pose,
    )
    flip = not facing_right
    oriented = pygame.transform.flip(sprite, flip, False)
    bw, bh = oriented.get_size()
    base_shadow_w = SPRITE_BASE_SIZES.get(name, (80, 226))[0]

    # 1. Knockdown (prone on floor)
    if fighter_state.is_knocked_down:
        rot_prone = pygame.transform.rotate(oriented, arm_dir * 88.0)
        # Soft elongated ground shadow
        sh_w = int(bh * 0.90)
        sh_surf = pygame.Surface((sh_w, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(sh_surf, (0, 0, 0, 140), (0, 0, sh_w, 20))
        surface.blit(sh_surf, (cx - sh_w // 2, ground_y - 8))
        r_rect = rot_prone.get_rect(midbottom=(cx - arm_dir * 10, ground_y + 12))
        surface.blit(rot_prone, r_rect)
        if hurt_flash_active:
            mask = pygame.mask.from_surface(rot_prone)
            flash = mask.to_surface(setcolor=(255, 255, 255, 245), unsetcolor=(0, 0, 0, 0))
            surface.blit(flash, r_rect)
        return True

    # 2. Dynamic Jump / in-air
    jump_y = 0.0
    if fighter_state.in_air and getattr(fighter_state, "jump_frame", 0) > 0:
        progress = fighter_state.jump_frame / float(JUMP_DURATION)
        jump_y = math.sin(progress * math.pi) * 135.0

    # Realistic ground contact shadow (anchored to arena floor)
    _draw_shadow(surface, cx, ground_y, jump_y, player_num=player_num, base_w=base_shadow_w)

    # Golden Grandmaster compass mandala aura
    if name == "Golden" and not fighter_state.in_air:
        _draw_golden_compass_aura(surface, cx, ground_y, anim_frame, accent_col)

    # 3. Action State & Pose Parameters
    last_act = getattr(fighter_state, "last_action", Action.IDLE)
    cur_act = getattr(fighter_state, "current_action", None)
    phase = getattr(fighter_state, "attack_phase", "none")
    atk_type = getattr(fighter_state, "attack_type", "none")

    breath = math.sin(time.time() * 3.6 + player_num * 1.5)

    torso_lean = 0.0
    scale_x = 1.0
    scale_y = 1.0
    lunge_x = arm_dir * (bw * POSE_X_OFFSET_RATIOS.get(active_pose, 0.0)) if has_dedicated_pose else 0.0

    is_kick = False
    is_punch = False
    is_dashing = False

    # A. HITSTUN RECOIL
    if fighter_state.hitstun > 0:
        recoil = min(18.0, fighter_state.hitstun * 1.8)
        shudder = (int(anim_frame * 3) % 2 * 6 - 3)
        torso_lean = -recoil * 0.95
        lunge_x = -arm_dir * (recoil * 0.7) + shudder
        scale_x = 0.98
        scale_y = 1.02

    # B. BLOCK
    elif last_act in (Action.BLOCK, Action.BLOCK_LOW) or cur_act in (Action.BLOCK, Action.BLOCK_LOW) or getattr(fighter_state, "blockstun", 0) > 0:
        is_low = getattr(fighter_state, "is_crouching", False) or last_act == Action.BLOCK_LOW or cur_act == Action.BLOCK_LOW
        if has_dedicated_pose and is_low:
            torso_lean = -2.0
            scale_y = 1.0
            scale_x = 1.0
        else:
            torso_lean = -6.0
            if is_low:
                scale_y = 0.75
                scale_x = 1.08
            else:
                scale_y = 0.96
                scale_x = 1.02

    # C. ATTACKS (Punches & Kicks)
    elif phase in ("startup", "active", "recovery"):
        is_startup = (phase == "startup")
        is_active = (phase == "active")

        if pose == "kick" or "kick" in atk_type or "sweep" in atk_type:
            is_kick = True
            is_heavy = "heavy" in atk_type or "sweep" in atk_type
            if has_dedicated_pose:
                if is_startup:
                    scale_x = 0.96
                    scale_y = 0.99
                    lunge_x += arm_dir * 2.0
                elif is_active:
                    scale_x = 1.02 if is_heavy else 1.0
                    scale_y = 1.0
                    lunge_x += arm_dir * (14.0 if is_heavy else 8.0)
                else:
                    scale_x = 0.98
                    lunge_x += arm_dir * 4.0
            else:
                if is_startup:
                    torso_lean = 2.0
                    scale_y = 0.98
                elif is_active:
                    torso_lean = -14.0 if is_heavy else -10.0
                    scale_x = 0.96
                    scale_y = 1.06
                    lunge_x = arm_dir * (22.0 if is_heavy else 14.0)
                else:
                    torso_lean = -4.0
                    lunge_x = arm_dir * 6.0
        else:
            is_punch = True
            is_heavy = "heavy" in atk_type or "special" in atk_type or "super" in atk_type
            if has_dedicated_pose:
                if is_startup:
                    scale_x = 0.96
                    scale_y = 0.99
                    lunge_x += arm_dir * 2.0
                elif is_active:
                    scale_x = 1.03 if is_heavy else 1.0
                    scale_y = 1.0
                    lunge_x += arm_dir * (16.0 if is_heavy else 10.0)
                else:
                    scale_x = 0.98
                    lunge_x += arm_dir * 4.0
            else:
                if is_startup:
                    torso_lean = -4.0
                    scale_x = 0.98
                elif is_active:
                    torso_lean = 14.0 if is_heavy else 10.0
                    scale_x = 1.08
                    scale_y = 0.96
                    lunge_x = arm_dir * (26.0 if is_heavy else 16.0)
                else:
                    torso_lean = 4.0
                    lunge_x = arm_dir * 8.0

    # D. CROUCH
    elif fighter_state.is_crouching or cur_act in (Action.CROUCH, Action.BLOCK_LOW):
        if has_dedicated_pose:
            scale_y = 1.0 + breath * 0.008
            scale_x = 1.0
            torso_lean = 0.0
        else:
            scale_y = 0.74
            scale_x = 1.08
            torso_lean = 2.0

    # E. DASH / BACKDASH
    elif last_act == Action.DASH or cur_act == Action.DASH or (getattr(fighter_state, "is_dashing", False) and last_act != Action.BACKDASH and cur_act != Action.BACKDASH):
        is_dashing = True
        if has_dedicated_pose:
            torso_lean = 2.0
            scale_y = 0.99
            scale_x = 1.02
            lunge_x += arm_dir * 6.0
        else:
            torso_lean = 14.0
            scale_y = 0.94
            scale_x = 1.05
            lunge_x = arm_dir * 8.0
        if name == "Shadow":
            _draw_shadow_mist(surface, cx, ground_y - 25, arm_dir, anim_frame)
    elif last_act == Action.BACKDASH or cur_act == Action.BACKDASH:
        if has_dedicated_pose:
            torso_lean = -4.0
            scale_y = 0.99
            lunge_x -= arm_dir * 6.0
        else:
            torso_lean = -10.0
            scale_y = 0.96
            lunge_x = -arm_dir * 6.0

    # F. WALKING STRIDE
    elif last_act in (Action.FORWARD, Action.BACK) or cur_act in (Action.FORWARD, Action.BACK):
        is_fwd = (last_act == Action.FORWARD or cur_act == Action.FORWARD)
        stride_bob = abs(math.sin(anim_frame * 0.38)) * 3.5
        jump_y += stride_bob
        if has_dedicated_pose:
            torso_lean = 0.0 if is_fwd else -3.0
            scale_x = 1.0
            scale_y = 1.0
        else:
            torso_lean = 6.0 if is_fwd else -4.0
            scale_x = 1.01
            scale_y = 0.99

    # G. IDLE READY STANCE
    else:
        scale_y = 1.0 + breath * 0.012
        scale_x = 1.0 - breath * 0.006
        torso_lean = 0.0 if (has_dedicated_pose and active_pose == "jump") else 1.8

    # In midair jump adjustment
    if fighter_state.in_air:
        if has_dedicated_pose and active_pose in ("jump", "kick", "punch"):
            torso_lean = 0.0
            scale_y = 1.0
        else:
            torso_lean = 4.0
            scale_y = 1.04

    # 4. GHOST AFTERIMAGES FOR DASH
    foot_x = int(cx + lunge_x)
    foot_y = int(ground_y - jump_y)

    if is_dashing:
        dash_steps = [16, 32, 48]
        dash_alphas = [80, 45, 20]
        for step_d, alpha in zip(dash_steps, dash_alphas):
            ghost_tx = foot_x - arm_dir * step_d
            ghost_surf, ghost_tl = _get_anchored_transform(oriented, torso_lean * arm_dir, scale_x, scale_y, ghost_tx, foot_y)
            ghost_tinted = ghost_surf.copy()
            ghost_tinted.fill((*accent_col[:3], alpha), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(ghost_tinted, ghost_tl)

    # 5. DRAW FULL-BODY CHARACTER
    transformed, topleft = _get_anchored_transform(oriented, torso_lean * arm_dir, scale_x, scale_y, foot_x, foot_y)
    surface.blit(transformed, topleft)

    # 6. PURE WHITE HIT FLASH SILHOUETTE
    if hurt_flash_active:
        mask = pygame.mask.from_surface(transformed)
        flash_surf = mask.to_surface(setcolor=(255, 255, 255, 245), unsetcolor=(0, 0, 0, 0))
        surface.blit(flash_surf, topleft)

    # 7. ATTACK CRESCENT SLASH / STRIKE BURST
    if phase == "active":
        if is_kick:
            is_heavy = "heavy" in atk_type or "sweep" in atk_type
            is_sweep = "sweep" in atk_type
            reach = 64 if is_heavy else 46
            x_mult = 0.42 if has_dedicated_pose else 0.55
            y_mult = 0.22 if is_sweep else (0.78 if has_dedicated_pose else 0.48)
            strike_x = foot_x + arm_dir * int(bw * x_mult)
            strike_y = foot_y - int(bh * y_mult)
            _draw_crescent_slash(surface, strike_x, strike_y, reach, arm_dir, accent_col, is_heavy=is_heavy, is_kick=True)
        elif is_punch:
            is_heavy = "heavy" in atk_type or "special" in atk_type or "super" in atk_type
            reach = 68 if is_heavy else 48
            x_mult = 0.42 if has_dedicated_pose else 0.50
            y_mult = 0.75 if has_dedicated_pose else 0.65
            strike_x = foot_x + arm_dir * int(bw * x_mult)
            strike_y = foot_y - int(bh * y_mult)
            _draw_crescent_slash(surface, strike_x, strike_y, reach, arm_dir, accent_col, is_heavy=is_heavy, is_kick=False)

    # 8. BLOCK HEXAGONAL ENERGY SHIELD
    if last_act in (Action.BLOCK, Action.BLOCK_LOW) or cur_act in (Action.BLOCK, Action.BLOCK_LOW) or getattr(fighter_state, "blockstun", 0) > 0:
        is_low = getattr(fighter_state, "is_crouching", False) or last_act == Action.BLOCK_LOW or cur_act == Action.BLOCK_LOW
        bx = foot_x + arm_dir * (bw // 2 + 16)
        sh_h = 52 if is_low else 82
        by = int(ground_y - sh_h - 4) if is_low else int(foot_y - bh * 0.70)
        shield_surf = pygame.Surface((40, sh_h), pygame.SRCALPHA)
        hex_pts = [(10, 0), (30, 0), (39, sh_h // 2), (30, sh_h - 1), (10, sh_h - 1), (1, sh_h // 2)]
        pygame.draw.polygon(shield_surf, (*accent_col[:3], 155), hex_pts)
        pygame.draw.polygon(shield_surf, (240, 250, 255, 245), hex_pts, 2)
        in_pts = [(13, 8), (27, 8), (34, sh_h // 2), (27, sh_h - 9), (13, sh_h - 9), (6, sh_h // 2)]
        pygame.draw.polygon(shield_surf, (255, 255, 255, 190), in_pts, 1)
        surface.blit(shield_surf, (bx - 20, by))

    # 9. CRIMSON FURY FLAMES
    if name == "Crimson" and getattr(fighter_state, "is_fury", False):
        flame_surf = pygame.Surface((bw + 36, bh + 40), pygame.SRCALPHA)
        for i in range(6):
            f_phase = anim_frame * 0.22 + i * 1.3
            fx = 18 + int((i / 5.0) * bw) + int(math.sin(f_phase) * 5)
            fy = bh + 20 - int(((anim_frame * 2 + i * 17) % 65))
            r = max(3, 9 - int(((anim_frame * 2 + i * 17) % 65) / 8))
            pygame.draw.circle(flame_surf, (255, 90, 20, 140), (fx, fy), r + 2)
            pygame.draw.circle(flame_surf, (255, 210, 50, 190), (fx, fy - 2), max(2, r - 1))
        surface.blit(flame_surf, (foot_x - bw // 2 - 18, foot_y - bh - 16))

    # 10. PARRY RADIANT BURST
    if getattr(fighter_state, "is_parrying", False) or getattr(fighter_state, "last_hit_effect", "") == "parry":
        parry_surf = pygame.Surface((72, 72), pygame.SRCALPHA)
        pygame.draw.circle(parry_surf, (0, 230, 255, 220), (36, 36), 32, 3)
        pygame.draw.circle(parry_surf, (255, 255, 255, 250), (36, 36), 22, 2)
        surface.blit(parry_surf, (foot_x + arm_dir * 30 - 36, foot_y - int(bh * 0.6) - 36))

    return True

# Per-player pose blending state: maps player_num -> dict of blended pose values
_POSE_BLEND_STATE: Dict[int, Dict[str, float]] = {}
_PREV_HEALTH_STATE: Dict[int, float] = {}
_HURT_FLASH_TIMER: Dict[int, int] = {}


def _shade(col: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    """Multiply RGB by factor and clamp to 0..255."""
    return (
        max(0, min(255, int(col[0] * factor))),
        max(0, min(255, int(col[1] * factor))),
        max(0, min(255, int(col[2] * factor))),
    )


def _tint_white(col: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    """Blend RGB toward pure white by amount in [0, 1]."""
    return (
        max(0, min(255, int(col[0] + (255 - col[0]) * amount))),
        max(0, min(255, int(col[1] + (255 - col[1]) * amount))),
        max(0, min(255, int(col[2] + (255 - col[2]) * amount))),
    )


def _target_pose_for(fighter_state, anim_frame: float) -> Dict[str, float]:
    """Return keyframe joint offsets (in px, relative to facing_right=+1) for current action."""
    act = getattr(fighter_state, "current_action", Action.IDLE)
    last_act = getattr(fighter_state, "last_action", Action.IDLE)
    phase = getattr(fighter_state, "attack_phase", "none")
    atk_type = getattr(fighter_state, "attack_type", "none")

    # Default fighting stance with subtle breathing
    breath = math.sin(anim_frame * 0.12) * 2.2
    guard_bob = math.cos(anim_frame * 0.12) * 1.5

    pose = {
        "torso_lean": 2.0,
        "torso_drop": breath,
        # Front arm (shoulder -> elbow -> hand)
        "f_elb_x": 8.0,
        "f_elb_y": 14.0 + guard_bob,
        "f_hand_x": 20.0,
        "f_hand_y": 4.0 + guard_bob,
        # Back arm
        "b_elb_x": -10.0,
        "b_elb_y": 13.0 - guard_bob,
        "b_hand_x": 6.0,
        "b_hand_y": 8.0 - guard_bob,
        # Front leg (hip -> knee -> foot)
        "f_knee_x": 10.0,
        "f_knee_y": 15.0,
        "f_foot_x": 14.0,
        "f_foot_y": 30.0,
        # Back leg
        "b_knee_x": -10.0,
        "b_knee_y": 15.0,
        "b_foot_x": -14.0,
        "b_foot_y": 30.0,
    }

    # 1. Hit reaction
    if fighter_state.hitstun > 0:
        recoil = min(14.0, fighter_state.hitstun * 1.4)
        pose.update({
            "torso_lean": -10.0,
            "torso_drop": 4.0,
            "f_elb_x": -6.0, "f_elb_y": 8.0,
            "f_hand_x": -2.0, "f_hand_y": -4.0,
            "b_elb_x": -16.0, "b_elb_y": 10.0,
            "b_hand_x": -18.0, "b_hand_y": 0.0,
            "f_knee_x": 6.0, "f_foot_x": 10.0 - recoil * 0.2,
            "b_knee_x": -12.0, "b_foot_x": -16.0,
        })
        return pose

    # 2. Block stance
    if last_act in (Action.BLOCK, Action.BLOCK_LOW) or fighter_state.blockstun > 0:
        crouch_add = 14.0 if (fighter_state.is_crouching or last_act == Action.BLOCK_LOW) else 0.0
        pose.update({
            "torso_lean": -3.0,
            "torso_drop": 3.0 + crouch_add,
            "f_elb_x": 12.0, "f_elb_y": 8.0,
            "f_hand_x": 16.0, "f_hand_y": -8.0,
            "b_elb_x": 6.0, "b_elb_y": 10.0,
            "b_hand_x": 12.0, "b_hand_y": -6.0,
        })
        return pose

    # 3. Active / Startup / Recovery Attacks
    if phase in ("startup", "active", "recovery"):
        is_startup = (phase == "startup")
        is_active = (phase == "active")
        ext = -0.35 if is_startup else (1.0 if is_active else 0.45)

        if atk_type in ("light_kick", "heavy_kick", "low_sweep", "crouch_kick", "jump_kick"):
            is_heavy_k = ("heavy" in atk_type or "sweep" in atk_type)
            reach_x = (50.0 if is_heavy_k else 38.0) * ext
            kick_y = 26.0 if ("sweep" in atk_type or "crouch" in atk_type) else (6.0 if is_heavy_k else 14.0)
            pose.update({
                "torso_lean": -6.0 * ext,
                "torso_drop": 12.0 if ("sweep" in atk_type or "crouch" in atk_type) else 2.0,
                "f_knee_x": max(8.0, reach_x * 0.55),
                "f_knee_y": kick_y * 0.6,
                "f_foot_x": max(12.0, reach_x),
                "f_foot_y": kick_y if is_active else 24.0,
                "b_knee_x": -10.0,
                "b_foot_x": -14.0,
                "f_hand_x": 14.0, "f_hand_y": 2.0,
                "b_hand_x": -12.0, "b_hand_y": 6.0,
            })
            return pose
        else:
            # Punch / Uppercut / Overhead / Special
            is_heavy_p = ("heavy" in atk_type or "overhead" in atk_type or "special" in atk_type or "super" in atk_type)
            reach_x = (48.0 if is_heavy_p else 34.0) * ext
            punch_y = -18.0 if atk_type == "anti_air" else (-6.0 if atk_type == "overhead" else 2.0)
            pose.update({
                "torso_lean": (9.0 if is_heavy_p else 5.0) * ext,
                "torso_drop": 14.0 if "crouch" in atk_type else 2.0,
                "f_elb_x": max(4.0, reach_x * 0.55),
                "f_elb_y": punch_y * 0.5 + 6.0,
                "f_hand_x": max(10.0, reach_x),
                "f_hand_y": punch_y,
                "b_elb_x": -14.0, "b_elb_y": 12.0,
                "b_hand_x": -8.0, "b_hand_y": 8.0,
                "f_knee_x": 14.0, "f_foot_x": 18.0,
            })
            return pose

    # 4. Jumping arc pose
    if fighter_state.in_air:
        pose.update({
            "torso_lean": 5.0,
            "torso_drop": -2.0,
            "f_elb_x": 10.0, "f_elb_y": 8.0,
            "f_hand_x": 18.0, "f_hand_y": -4.0,
            "b_elb_x": -12.0, "b_elb_y": 8.0,
            "b_hand_x": -6.0, "b_hand_y": -2.0,
            "f_knee_x": 14.0, "f_knee_y": 10.0,
            "f_foot_x": 10.0, "f_foot_y": 20.0,
            "b_knee_x": -8.0, "b_knee_y": 12.0,
            "b_foot_x": -14.0, "b_foot_y": 22.0,
        })
        return pose

    # 5. Crouch pose
    if fighter_state.is_crouching:
        pose.update({
            "torso_lean": 4.0,
            "torso_drop": 18.0,
            "f_elb_x": 10.0, "f_elb_y": 12.0,
            "f_hand_x": 20.0, "f_hand_y": 6.0,
            "f_knee_x": 16.0, "f_knee_y": 8.0,
            "f_foot_x": 16.0, "f_foot_y": 16.0,
            "b_knee_x": -12.0, "b_knee_y": 10.0,
            "b_foot_x": -14.0, "b_foot_y": 16.0,
        })
        return pose

    # 6. Dash / Backdash lean
    if last_act == Action.DASH or getattr(fighter_state, "is_dashing", False):
        pose.update({
            "torso_lean": 14.0,
            "torso_drop": 5.0,
            "f_elb_x": 6.0, "f_elb_y": 12.0,
            "f_hand_x": 22.0, "f_hand_y": 6.0,
            "b_elb_x": -18.0, "b_elb_y": 8.0,
            "b_hand_x": -26.0, "b_hand_y": 12.0,
            "f_knee_x": 18.0, "f_knee_y": 12.0,
            "f_foot_x": 22.0, "f_foot_y": 28.0,
            "b_knee_x": -14.0, "b_knee_y": 16.0,
            "b_foot_x": -24.0, "b_foot_y": 26.0,
        })
        return pose

    if last_act == Action.BACKDASH:
        pose.update({
            "torso_lean": -11.0,
            "torso_drop": 4.0,
            "f_elb_x": 8.0, "f_elb_y": 10.0,
            "f_hand_x": 18.0, "f_hand_y": 2.0,
            "b_elb_x": -12.0, "b_elb_y": 10.0,
            "b_hand_x": -6.0, "b_hand_y": 4.0,
            "f_knee_x": 14.0, "f_foot_x": 20.0,
            "b_knee_x": -14.0, "b_foot_x": -20.0,
        })
        return pose

    # 7. Walk cycle
    if last_act in (Action.FORWARD, Action.BACK) or act in (Action.FORWARD, Action.BACK):
        stride = math.sin(anim_frame * 0.42) * 13.0
        arm_swing = math.cos(anim_frame * 0.42) * 6.0
        pose.update({
            "torso_lean": 4.0 if last_act == Action.FORWARD else -2.0,
            "torso_drop": abs(math.sin(anim_frame * 0.42)) * 2.5,
            "f_knee_x": 8.0 + stride * 0.6,
            "f_foot_x": 10.0 + stride,
            "f_foot_y": 30.0 - max(0.0, stride * 0.25),
            "b_knee_x": -8.0 - stride * 0.6,
            "b_foot_x": -10.0 - stride,
            "b_foot_y": 30.0 - max(0.0, -stride * 0.25),
            "f_hand_x": 20.0 + arm_swing * 0.5,
            "b_hand_x": 6.0 - arm_swing * 0.5,
        })
        return pose

    return pose


def _get_blended_pose(player_num: int, target: Dict[str, float]) -> Dict[str, float]:
    """Blend current pose toward target over ~3-4 frames (lerp factor 0.35)."""
    prev = _POSE_BLEND_STATE.get(player_num)
    if prev is None:
        _POSE_BLEND_STATE[player_num] = dict(target)
        return dict(target)

    alpha = 0.35
    blended = {}
    for k, v in target.items():
        old_v = prev.get(k, v)
        blended[k] = old_v + (v - old_v) * alpha
    _POSE_BLEND_STATE[player_num] = blended
    return blended


def _draw_capsule_limb(
    surface: pygame.Surface,
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    radius: int,
    base_col: Tuple[int, int, int],
    arm_dir: int = 1,
    wrapped: bool = False,
    mech_joint: bool = False,
):
    """Draw a rounded anatomical limb segment with 2px dark outline, shade, and rim light."""
    x1, y1 = int(p1[0]), int(p1[1])
    x2, y2 = int(p2[0]), int(p2[1])
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    r = max(3, int(radius))

    dark_col = _shade(base_col, 0.72)
    rim_col = _tint_white(base_col, 0.28)

    if length < 1.0:
        pygame.draw.circle(surface, OUTLINE_DARK, (x1, y1), r + 2)
        pygame.draw.circle(surface, base_col, (x1, y1), r)
        return

    nx = -dy / length
    ny = dx / length

    # 1. Outer 2px dark outline
    ro = r + 2
    pts_out = [
        (x1 + nx * ro, y1 + ny * ro),
        (x2 + nx * ro, y2 + ny * ro),
        (x2 - nx * ro, y2 - ny * ro),
        (x1 - nx * ro, y1 - ny * ro),
    ]
    pygame.draw.polygon(surface, OUTLINE_DARK, pts_out)
    pygame.draw.circle(surface, OUTLINE_DARK, (x1, y1), ro)
    pygame.draw.circle(surface, OUTLINE_DARK, (x2, y2), ro)

    # 2. Base fill
    pts_base = [
        (x1 + nx * r, y1 + ny * r),
        (x2 + nx * r, y2 + ny * r),
        (x2 - nx * r, y2 - ny * r),
        (x1 - nx * r, y1 - ny * r),
    ]
    pygame.draw.polygon(surface, base_col, pts_base)
    pygame.draw.circle(surface, base_col, (x1, y1), r)
    pygame.draw.circle(surface, base_col, (x2, y2), r)

    # 3. Darker shade on back side & light rim on front side
    shade_sign = -1 if (nx * arm_dir < 0) else 1
    pygame.draw.line(
        surface,
        dark_col,
        (int(x1 - nx * shade_sign * (r - 1)), int(y1 - ny * shade_sign * (r - 1))),
        (int(x2 - nx * shade_sign * (r - 1)), int(y2 - ny * shade_sign * (r - 1))),
        2,
    )
    pygame.draw.line(
        surface,
        rim_col,
        (int(x1 + nx * shade_sign * (r - 1)), int(y1 + ny * shade_sign * (r - 1))),
        (int(x2 + nx * shade_sign * (r - 1)), int(y2 + ny * shade_sign * (r - 1))),
        1,
    )

    # Optional ninja limb wraps (Shadow)
    if wrapped and length >= 8:
        for t in (0.33, 0.66):
            wx = x1 + dx * t
            wy = y1 + dy * t
            pygame.draw.line(
                surface,
                _shade(base_col, 0.55),
                (int(wx - nx * r), int(wy - ny * r)),
                (int(wx + nx * r), int(wy + ny * r)),
                1,
            )

    # Optional mechanical joint ring (Steel)
    if mech_joint:
        pygame.draw.circle(surface, (45, 55, 70), (x1, y1), max(3, r - 1))
        pygame.draw.circle(surface, (160, 210, 240), (x1, y1), max(2, r - 2), 1)


def draw_fighter(surface, fighter_state, facing_right, arena_offset_x=0,
                 ground_y=FLOOR_HEIGHT, player_num=1, is_mirror=False,
                 is_human=False):
    """Draw one jointed fighter with keyframe animation blending and character gear."""
    name = fighter_state.character_name
    palette = get_fighter_palette(name, is_p2_mirror=(player_num == 2 and is_mirror))
    body_col = palette["body"]
    trim_col = palette["secondary"]
    accent_col = palette.get("accent", (240, 200, 50))
    skin_col = palette.get("skin", (230, 190, 160))
    emblem_type = palette.get("emblem", "compass")

    # Detect 2-frame white hurt flash only when actively taking hit damage
    prev_key = (player_num, name)
    prev_hp = _PREV_HEALTH_STATE.get(prev_key, fighter_state.health)
    if fighter_state.health < prev_hp - 0.001 and (fighter_state.hitstun > 0 or fighter_state.is_knocked_down):
        _HURT_FLASH_TIMER[player_num] = 2
    _PREV_HEALTH_STATE[prev_key] = fighter_state.health

    hurt_flash = _HURT_FLASH_TIMER.get(player_num, 0)
    if hurt_flash > 0:
        _HURT_FLASH_TIMER[player_num] = hurt_flash - 1
        body_col = (255, 255, 255)
        trim_col = (240, 245, 255)
        accent_col = (255, 255, 255)
        skin_col = (255, 255, 255)

    # Use realistic full-body fighter rendering when available
    if name in SPRITE_BASE_SIZES:
        rendered = _draw_realistic_fighter(
            surface,
            fighter_state,
            facing_right,
            arena_offset_x=arena_offset_x,
            ground_y=ground_y,
            player_num=player_num,
            is_mirror=is_mirror,
            is_human=is_human,
            hurt_flash_active=(hurt_flash > 0),
        )
        if rendered:
            return

    props = FIGHTER_PROPORTIONS.get(name, DEFAULT_PROPORTIONS)
    b_width = props["body_width"]
    b_height = props["body_height"]
    h_radius = props["head_radius"]
    leg_len = props["leg_length"]

    screen_x = arena_offset_x + fighter_state.x
    cx = int(screen_x)
    arm_dir = 1 if facing_right else -1

    anim_frame = getattr(fighter_state, "jump_frame", 0) or int(time.time() * 60) % 3600

    # --- 1. Ground Shadow & Golden Compass Circle ---
    jump_y = 0.0
    if fighter_state.in_air and fighter_state.jump_frame > 0:
        progress = fighter_state.jump_frame / JUMP_DURATION
        jump_y = math.sin(progress * math.pi) * 120.0

    _draw_shadow(surface, cx, ground_y, jump_y, player_num)
    if name == "Golden" and not fighter_state.in_air:
        _draw_golden_compass_aura(surface, cx, ground_y, anim_frame, accent_col)

    # --- 2. Knockdown Pose ---
    if fighter_state.is_knocked_down:
        prone_w = b_height + leg_len - 10
        prone_h = max(18, b_width // 2)
        prone_rect = pygame.Rect(cx - prone_w // 2, ground_y - prone_h - 2, prone_w, prone_h)
        pygame.draw.rect(surface, OUTLINE_DARK, prone_rect.inflate(4, 4), border_radius=8)
        pygame.draw.rect(surface, body_col, prone_rect, border_radius=6)
        pygame.draw.rect(surface, _shade(body_col, 0.72), (prone_rect.x, prone_rect.centery, prone_rect.w, prone_rect.h // 2), border_radius=6)
        head_x = cx - arm_dir * (prone_w // 2 - h_radius + 4)
        head_y = ground_y - prone_h // 2 - 4
        pygame.draw.circle(surface, OUTLINE_DARK, (head_x, head_y), h_radius + 2)
        pygame.draw.circle(surface, skin_col if name != "Steel" else body_col, (head_x, head_y), h_radius)
        _draw_overhead_tag(surface, cx, ground_y - prone_h - 26, player_num, is_human)
        return

    # --- 3. Pose Keyframes & 3-4 Frame Blending ---
    target_pose = _target_pose_for(fighter_state, anim_frame)
    pose = _get_blended_pose(player_num, target_pose)

    torso_lean = pose["torso_lean"] * arm_dir
    torso_drop = pose["torso_drop"]
    eff_b_height = int(b_height - torso_drop * 0.45)

    hip_x = cx - int(torso_lean * 0.25)
    hip_y = int(ground_y - leg_len - jump_y + torso_drop * 0.35)
    torso_top_y = int(hip_y - eff_b_height)
    shoulder_x = cx + int(torso_lean * 0.65)
    shoulder_y = int(torso_top_y + 11)

    # --- 4. Dash Ghosts (3 faded after-images ONLY during DASH / BACKDASH) ---
    is_dashing = (
        fighter_state.last_action in (Action.DASH, Action.BACKDASH)
        or fighter_state.current_action in (Action.DASH, Action.BACKDASH)
        or getattr(fighter_state, "is_dashing", False)
    )
    if is_dashing and not fighter_state.is_knocked_down:
        dash_dir = arm_dir if fighter_state.last_action != Action.BACKDASH else -arm_dir
        for g_idx, (dist, alpha) in enumerate(((18, 95), (34, 60), (50, 30))):
            gx = cx - dash_dir * dist
            _draw_ghost_afterimage(
                surface, gx, torso_top_y + g_idx * 2, b_width, eff_b_height, h_radius,
                accent_col if name == "Shadow" else body_col, alpha
            )
        if name == "Shadow":
            _draw_shadow_mist(surface, cx, hip_y, dash_dir, anim_frame)

    # --- 5. Crimson Fury Flame Wisps (Behind Fighter) ---
    if name == "Crimson" and fighter_state.is_fury:
        _draw_fury_flames(surface, cx, torso_top_y, b_width, eff_b_height, anim_frame)

    # --- 6. Background Cape / Trailing Scarf (Shadow) ---
    if name == "Shadow":
        _draw_trailing_scarf(surface, shoulder_x, shoulder_y - 2, arm_dir, accent_col, anim_frame)

    # --- 7. Back Arm & Back Leg ---
    is_wrapped = (name == "Shadow")
    is_mech = (name == "Steel")
    limb_r_leg = max(5, b_width // 7)
    limb_r_arm = max(4, b_width // 8)

    # Back Leg (hip -> knee -> foot)
    b_hip = (hip_x - arm_dir * (b_width // 5), hip_y)
    b_knee = (hip_x + arm_dir * pose["b_knee_x"], hip_y + pose["b_knee_y"] - torso_drop * 0.2)
    b_foot = (hip_x + arm_dir * pose["b_foot_x"], hip_y + pose["b_foot_y"] - torso_drop * 0.35)
    _draw_capsule_limb(surface, b_hip, b_knee, limb_r_leg, _shade(trim_col, 0.85), arm_dir, wrapped=is_wrapped)
    _draw_capsule_limb(surface, b_knee, b_foot, limb_r_leg - 1, _shade(trim_col, 0.78), arm_dir, wrapped=is_wrapped, mech_joint=is_mech)
    _draw_foot(surface, b_foot, arm_dir, _shade(body_col, 0.8), limb_r_leg)

    # Back Arm (shoulder -> elbow -> hand)
    b_sh = (shoulder_x - arm_dir * (b_width // 2 - 4), shoulder_y)
    b_elb = (b_sh[0] + arm_dir * pose["b_elb_x"], b_sh[1] + pose["b_elb_y"])
    b_hand = (b_sh[0] + arm_dir * pose["b_hand_x"], b_sh[1] + pose["b_hand_y"])
    arm_base_col = skin_col if name == "Crimson" else _shade(body_col, 0.85)
    _draw_capsule_limb(surface, b_sh, b_elb, limb_r_arm, arm_base_col, arm_dir, wrapped=is_wrapped)
    _draw_capsule_limb(surface, b_elb, b_hand, limb_r_arm - 1, arm_base_col, arm_dir, wrapped=is_wrapped, mech_joint=is_mech)
    _draw_hand(surface, b_hand, name, accent_col, trim_col, limb_r_arm)

    # --- 8. Torso (Rounded anatomical torso with 2px dark outline, shade & rim) ---
    _draw_torso(
        surface, cx, torso_top_y, b_width, eff_b_height, int(torso_lean),
        arm_dir, name, body_col, trim_col, accent_col, skin_col,
        emblem_type, fighter_state, is_human, anim_frame
    )

    # --- 9. Head & Character Headgear ---
    head_x = shoulder_x + int(torso_lean * 0.2)
    head_y = int(torso_top_y - h_radius + 2)
    _draw_head(
        surface, head_x, head_y, h_radius, arm_dir, name,
        body_col, trim_col, accent_col, skin_col, anim_frame
    )

    # --- 10. Front Leg (hip -> knee -> foot) ---
    f_hip = (hip_x + arm_dir * (b_width // 5), hip_y)
    f_knee = (hip_x + arm_dir * pose["f_knee_x"], hip_y + pose["f_knee_y"] - torso_drop * 0.2)
    f_foot = (hip_x + arm_dir * pose["f_foot_x"], hip_y + pose["f_foot_y"] - torso_drop * 0.35)
    is_kicking = (
        fighter_state.attack_phase == "active"
        and fighter_state.attack_type in ("light_kick", "heavy_kick", "low_sweep", "crouch_kick", "jump_kick")
    )
    f_leg_col = accent_col if is_kicking else trim_col
    _draw_capsule_limb(surface, f_hip, f_knee, limb_r_leg, f_leg_col, arm_dir, wrapped=is_wrapped)
    _draw_capsule_limb(surface, f_knee, f_foot, limb_r_leg - 1, f_leg_col, arm_dir, wrapped=is_wrapped, mech_joint=is_mech)
    _draw_foot(surface, f_foot, arm_dir, accent_col if is_kicking else body_col, limb_r_leg)

    # --- 11. Front Arm (shoulder -> elbow -> hand) ---
    f_sh = (shoulder_x + arm_dir * (b_width // 2 - 4), shoulder_y)
    f_elb = (f_sh[0] + arm_dir * pose["f_elb_x"], f_sh[1] + pose["f_elb_y"])
    f_hand = (f_sh[0] + arm_dir * pose["f_hand_x"], f_sh[1] + pose["f_hand_y"])
    f_arm_col = skin_col if name == "Crimson" else body_col
    _draw_capsule_limb(surface, f_sh, f_elb, limb_r_arm, f_arm_col, arm_dir, wrapped=is_wrapped)
    _draw_capsule_limb(surface, f_elb, f_hand, limb_r_arm, f_arm_col, arm_dir, wrapped=is_wrapped, mech_joint=is_mech)
    _draw_hand(surface, f_hand, name, accent_col, trim_col, limb_r_arm + 1, is_front=True)

    # --- 12. Curved Attack Motion Arcs (Step 3) ---
    if fighter_state.attack_phase == "active":
        atk_t = fighter_state.attack_type
        if is_kicking:
            is_heavy_k = ("heavy" in atk_t or "sweep" in atk_t)
            _draw_curved_motion_arc(
                surface, int(f_hip[0]), int(f_foot[1]), arm_dir,
                int(abs(f_foot[0] - f_hip[0]) + 18), accent_col, heavy=is_heavy_k
            )
        else:
            is_heavy_p = ("heavy" in atk_t or "overhead" in atk_t or "special" in atk_t or "super" in atk_t or "anti_air" in atk_t)
            _draw_curved_motion_arc(
                surface, int(f_sh[0]), int(f_hand[1]), arm_dir,
                int(abs(f_hand[0] - f_sh[0]) + 18), accent_col, heavy=is_heavy_p
            )

    # --- 13. Block Shield Effect (Hexagonal Energy Ripple) ---
    is_blocking = (
        fighter_state.last_action in (Action.BLOCK, Action.BLOCK_LOW)
        or fighter_state.blockstun > 0
    )
    if is_blocking:
        is_low = fighter_state.is_crouching or fighter_state.last_action == Action.BLOCK_LOW
        bx = cx + arm_dir * (b_width // 2 + 14)
        sh_h = 40 if is_low else 58
        by = int(ground_y - sh_h - 4) if is_low else int(torso_top_y + 2)
        shield_surf = pygame.Surface((32, sh_h), pygame.SRCALPHA)
        hex_pts = [(8, 0), (24, 0), (31, sh_h // 2), (24, sh_h - 1), (8, sh_h - 1), (1, sh_h // 2)]
        pygame.draw.polygon(shield_surf, (45, 165, 255, 155), hex_pts)
        pygame.draw.polygon(shield_surf, (210, 245, 255, 245), hex_pts, 2)
        # Inner hexagonal ripple
        in_pts = [(11, 8), (21, 8), (26, sh_h // 2), (21, sh_h - 9), (11, sh_h - 9), (6, sh_h // 2)]
        pygame.draw.polygon(shield_surf, (255, 255, 255, 190), in_pts, 1)
        surface.blit(shield_surf, (bx - 16, by))

    # --- 14. Parry Radiant Burst ---
    if getattr(fighter_state, "is_parrying", False) or getattr(fighter_state, "last_hit_effect", "") == "parry":
        parry_surf = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.circle(parry_surf, (0, 230, 255, 210), (32, 32), 28, 3)
        pygame.draw.circle(parry_surf, (255, 255, 255, 250), (32, 32), 18, 2)
        surface.blit(parry_surf, (cx + arm_dir * 25 - 32, int(torso_top_y + eff_b_height * 0.4) - 32))

    # --- 15. Overhead Tag ---
    _draw_overhead_tag(surface, head_x, head_y - h_radius - 14, player_num, is_human)


def _draw_torso(
    surface: pygame.Surface,
    cx: int,
    top_y: int,
    b_width: int,
    b_height: int,
    lean: int,
    arm_dir: int,
    name: str,
    body_col: Tuple[int, int, int],
    trim_col: Tuple[int, int, int],
    accent_col: Tuple[int, int, int],
    skin_col: Tuple[int, int, int],
    emblem_type: str,
    fighter_state,
    is_human: bool,
    anim_frame: float,
):
    """Draw rounded anatomical torso with 2px dark outline, side shading, rim light, and costume."""
    body_rect = pygame.Rect(cx - b_width // 2 + lean // 2, top_y, b_width, b_height)
    dark_col = _shade(body_col, 0.72)
    rim_col = _tint_white(body_col, 0.30)

    # Outer 2px dark outline
    pygame.draw.rect(surface, OUTLINE_DARK, body_rect.inflate(4, 4), border_radius=9)
    # Main torso fill
    pygame.draw.rect(surface, body_col, body_rect, border_radius=7)

    # Darker shade on back half
    shade_w = b_width // 3
    shade_x = body_rect.left if arm_dir > 0 else (body_rect.right - shade_w)
    pygame.draw.rect(surface, dark_col, (shade_x, top_y + 2, shade_w, b_height - 4), border_radius=5)

    # Light rim on front edge
    rim_x = (body_rect.right - 3) if arm_dir > 0 else (body_rect.left + 1)
    pygame.draw.line(surface, rim_col, (rim_x, top_y + 5), (rim_x, body_rect.bottom - 5), 2)

    # Character-specific torso costume details
    if name == "Crimson":
        # Sleeveless gi V-collar & black martial arts belt with trailing ends
        pygame.draw.polygon(
            surface, skin_col,
            [(body_rect.centerx - 6, top_y + 1), (body_rect.centerx + 6, top_y + 1), (body_rect.centerx + arm_dir * 2, top_y + 18)]
        )
        belt_y = int(top_y + b_height * 0.68)
        belt_rect = pygame.Rect(body_rect.left - 1, belt_y, b_width + 2, 7)
        pygame.draw.rect(surface, (20, 20, 25), belt_rect, border_radius=2)
        pygame.draw.rect(surface, OUTLINE_DARK, belt_rect, 1, border_radius=2)
        # Trailing belt ends
        sway = int(math.sin(anim_frame * 0.25) * 4)
        knot_x = body_rect.centerx - arm_dir * 4
        pygame.draw.line(surface, (24, 24, 30), (knot_x, belt_y + 3), (knot_x - arm_dir * 12, belt_y + 18 + sway), 4)
        pygame.draw.line(surface, (24, 24, 30), (knot_x, belt_y + 3), (knot_x - arm_dir * 7, belt_y + 21 - sway), 4)

    elif name == "Steel":
        # Heavy square shoulder pauldrons & armor chest seams
        for side in (-1, 1):
            sh_x = body_rect.centerx + side * (b_width // 2 - 3) - 8
            sh_rect = pygame.Rect(sh_x, top_y - 3, 16, 18)
            pygame.draw.rect(surface, OUTLINE_DARK, sh_rect.inflate(4, 4), border_radius=4)
            pygame.draw.rect(surface, body_col, sh_rect, border_radius=3)
            pygame.draw.rect(surface, accent_col, sh_rect, 2, border_radius=3)
        #Glowing core reactor strip
        pygame.draw.line(surface, accent_col, (body_rect.left + 6, top_y + 22), (body_rect.right - 6, top_y + 22), 2)

    elif name == "Shadow":
        # Crisscross shinobi chest harness & dark waist sash
        pygame.draw.line(surface, trim_col, (body_rect.left + 4, top_y + 4), (body_rect.right - 4, top_y + b_height - 10), 3)
        pygame.draw.line(surface, trim_col, (body_rect.right - 4, top_y + 4), (body_rect.left + 4, top_y + b_height - 10), 3)
        waist = pygame.Rect(body_rect.left, int(top_y + b_height * 0.72), b_width, 6)
        pygame.draw.rect(surface, accent_col, waist, border_radius=2)

    elif name == "Golden":
        # Open chest martial artist robe, gold prayer beads around neck, flowing sash
        pygame.draw.polygon(
            surface, skin_col,
            [(body_rect.centerx - 7, top_y + 2), (body_rect.centerx + 7, top_y + 2), (body_rect.centerx + arm_dir * 3, top_y + 24)]
        )
        # Gold prayer beads necklace
        for b_ang in range(-3, 4):
            bx = body_rect.centerx + b_ang * 3
            by = top_y + 5 + (3 - abs(b_ang)) * 2
            pygame.draw.circle(surface, OUTLINE_DARK, (bx, by), 3)
            pygame.draw.circle(surface, (255, 215, 40), (bx, by), 2)
        # Flowing sash at waist
        sash_y = int(top_y + b_height * 0.65)
        sash_rect = pygame.Rect(body_rect.left - 1, sash_y, b_width + 2, 8)
        pygame.draw.rect(surface, trim_col, sash_rect, border_radius=2)
        pygame.draw.rect(surface, accent_col, sash_rect, 1, border_radius=2)
        sway = int(math.cos(anim_frame * 0.22) * 6)
        pygame.draw.polygon(
            surface, trim_col,
            [
                (body_rect.centerx - arm_dir * 4, sash_y + 6),
                (body_rect.centerx - arm_dir * 16, sash_y + 24 + sway),
                (body_rect.centerx - arm_dir * 9, sash_y + 26 + sway),
            ]
        )

    # Chest emblem
    _draw_emblem(surface, body_rect.centerx + arm_dir * 2, int(top_y + b_height * 0.40), emblem_type, accent_col)

    # Adrenaline pulsing glow when AI is below 25% HP
    if not is_human and fighter_state.health < 0.25:
        pulse = 0.5 + 0.5 * math.sin(time.time() * 14.0)
        glow_rect = body_rect.inflate(8, 8)
        glow_surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            glow_surf,
            (255, 70, 50, int(80 + 90 * pulse)),
            glow_surf.get_rect(),
            width=2,
            border_radius=10,
        )
        surface.blit(glow_surf, glow_rect.topleft)


def _draw_head(
    surface: pygame.Surface,
    head_x: int,
    head_y: int,
    h_radius: int,
    arm_dir: int,
    name: str,
    body_col: Tuple[int, int, int],
    trim_col: Tuple[int, int, int],
    accent_col: Tuple[int, int, int],
    skin_col: Tuple[int, int, int],
    anim_frame: float,
):
    """Draw character head with 2px dark outline, directional rim light, and headgear."""
    head_fill = skin_col if name in ("Crimson", "Golden") else body_col

    # 2px dark outline + base head circle
    pygame.draw.circle(surface, OUTLINE_DARK, (head_x, head_y), h_radius + 2)
    pygame.draw.circle(surface, head_fill, (head_x, head_y), h_radius)
    # Rim highlight on front arc
    pygame.draw.circle(surface, _tint_white(head_fill, 0.25), (head_x + arm_dir * 3, head_y - 2), max(2, h_radius - 4))
    pygame.draw.circle(surface, head_fill, (head_x + arm_dir * 1, head_y), max(2, h_radius - 3))

    eye_x = head_x + arm_dir * (h_radius // 2)

    if name == "Crimson":
        # Spiked red/crimson hair + headband
        hair_col = (210, 35, 30)
        spikes = [
            [(head_x - 12, head_y - 6), (head_x - 16 - arm_dir * 4, head_y - 20), (head_x - 4, head_y - 12)],
            [(head_x - 6, head_y - 10), (head_x - 4 - arm_dir * 5, head_y - 25), (head_x + 4, head_y - 12)],
            [(head_x + 1, head_y - 10), (head_x + 8 - arm_dir * 3, head_y - 23), (head_x + 11, head_y - 8)],
            [(head_x + 6, head_y - 6), (head_x + 16, head_y - 16), (head_x + 12, head_y - 3)],
        ]
        for sp in spikes:
            pygame.draw.polygon(surface, OUTLINE_DARK, sp, 3)
            pygame.draw.polygon(surface, hair_col, sp)
        # Black headband
        pygame.draw.line(surface, (20, 20, 25), (head_x - h_radius, head_y - 5), (head_x + h_radius, head_y - 5), 4)
        pygame.draw.circle(surface, (25, 25, 30), (eye_x, head_y - 1), 2)

    elif name == "Steel":
        # Armored helmet crest & glowing blue visor slit
        pygame.draw.polygon(
            surface, trim_col,
            [(head_x - 6, head_y - h_radius - 3), (head_x + 6, head_y - h_radius - 3), (head_x + arm_dir * 4, head_y - 4)]
        )
        visor_rect = pygame.Rect(eye_x - 6, head_y - 4, 12, 5)
        pygame.draw.rect(surface, OUTLINE_DARK, visor_rect.inflate(2, 2), border_radius=2)
        pygame.draw.rect(surface, (40, 210, 255), visor_rect, border_radius=2)
        pygame.draw.line(surface, WHITE, (visor_rect.left + 2, head_y - 2), (visor_rect.right - 2, head_y - 2), 1)

    elif name == "Shadow":
        # Pointed cowl/hood & glowing teal eyes
        hood_pts = [
            (head_x - arm_dir * (h_radius + 5), head_y - h_radius - 4),
            (head_x + arm_dir * (h_radius + 2), head_y - h_radius + 2),
            (head_x + arm_dir * h_radius, head_y + 4),
            (head_x - arm_dir * h_radius, head_y + 6),
        ]
        pygame.draw.polygon(surface, OUTLINE_DARK, hood_pts, 3)
        pygame.draw.polygon(surface, body_col, hood_pts)
        # Face mask over lower half
        pygame.draw.rect(surface, trim_col, (head_x - h_radius + 2, head_y, h_radius * 2 - 4, h_radius - 1), border_radius=4)
        # Glowing teal eye
        pygame.draw.circle(surface, accent_col, (eye_x, head_y - 2), 4)
        pygame.draw.circle(surface, WHITE, (eye_x + arm_dir, head_y - 2), 2)

    else:  # Golden
        # Martial master topknot / gold headband circlet
        pygame.draw.circle(surface, OUTLINE_DARK, (head_x - arm_dir * 4, head_y - h_radius - 3), 6)
        pygame.draw.circle(surface, (40, 35, 30), (head_x - arm_dir * 4, head_y - h_radius - 3), 5)
        pygame.draw.line(surface, accent_col, (head_x - h_radius, head_y - 5), (head_x + h_radius, head_y - 5), 3)
        pygame.draw.circle(surface, (35, 30, 25), (eye_x, head_y - 1), 2)


def _draw_hand(
    surface: pygame.Surface,
    pos: Tuple[float, float],
    name: str,
    accent_col: Tuple[int, int, int],
    trim_col: Tuple[int, int, int],
    radius: int,
    is_front: bool = False,
):
    """Draw a fighter's hand/fist with character-specific gloves or forearm shield plates."""
    hx, hy = int(pos[0]), int(pos[1])
    r = max(4, radius)

    if name == "Crimson":
        # Taped white fists with red wrap outline
        pygame.draw.circle(surface, OUTLINE_DARK, (hx, hy), r + 2)
        pygame.draw.circle(surface, (245, 245, 250), (hx, hy), r + 1)
        pygame.draw.circle(surface, (200, 35, 30), (hx, hy), r + 1, 2)
    elif name == "Steel" and is_front:
        # Arm-mounted shield plate
        plate = pygame.Rect(hx - 6, hy - 11, 12, 22)
        pygame.draw.rect(surface, OUTLINE_DARK, plate.inflate(4, 4), border_radius=3)
        pygame.draw.rect(surface, accent_col, plate, border_radius=2)
        pygame.draw.rect(surface, trim_col, plate, 2, border_radius=2)
    else:
        pygame.draw.circle(surface, OUTLINE_DARK, (hx, hy), r + 2)
        pygame.draw.circle(surface, accent_col, (hx, hy), r)


def _draw_foot(
    surface: pygame.Surface,
    pos: Tuple[float, float],
    arm_dir: int,
    col: Tuple[int, int, int],
    radius: int,
):
    """Draw a rounded martial arts boot/foot."""
    fx, fy = int(pos[0]), int(pos[1])
    foot_rect = pygame.Rect(fx - 5 if arm_dir > 0 else fx - 9, fy - 4, 14, 8)
    pygame.draw.rect(surface, OUTLINE_DARK, foot_rect.inflate(4, 4), border_radius=4)
    pygame.draw.rect(surface, col, foot_rect, border_radius=3)


def _draw_curved_motion_arc(
    surface: pygame.Surface,
    sx: int,
    sy: int,
    arm_dir: int,
    reach: int,
    colour: Tuple[int, int, int],
    heavy: bool = False,
):
    """Draw a smooth curved polygon attack trail crescent."""
    reach = max(28, reach)
    h = 54 if heavy else 36
    arc_surf = pygame.Surface((reach + 28, h), pygame.SRCALPHA)
    cy = h // 2
    outer_pts = []
    inner_pts = []
    steps = 10
    for i in range(steps + 1):
        t = (i / steps) * math.pi - (math.pi / 2)
        ox = int(math.cos(t) * (reach + 14))
        oy = int(cy + math.sin(t) * (cy - 2))
        ix = int(math.cos(t) * max(8, reach - (16 if heavy else 10)))
        iy = int(cy + math.sin(t) * max(4, cy - (10 if heavy else 6)))
        outer_pts.append((ox, oy))
        inner_pts.append((ix, iy))

    poly_pts = outer_pts + list(reversed(inner_pts))
    alpha = 210 if heavy else 155
    pygame.draw.polygon(arc_surf, (*colour[:3], alpha), poly_pts)
    if heavy:
        pygame.draw.polygon(arc_surf, (255, 255, 255, 230), outer_pts[:4] + inner_pts[:4][::-1])

    if arm_dir < 0:
        arc_surf = pygame.transform.flip(arc_surf, True, False)
        surface.blit(arc_surf, (sx - reach - 18, sy - cy))
    else:
        surface.blit(arc_surf, (sx - 10, sy - cy))


def _draw_ghost_afterimage(
    surface: pygame.Surface,
    gx: int,
    body_top: float,
    b_width: int,
    b_height: int,
    h_radius: int,
    body_col: Tuple[int, int, int],
    alpha: int,
):
    """Render a faded jointed silhouette behind a dashing fighter."""
    w = b_width + 16
    h = b_height + h_radius * 2 + 28
    ghost_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    col = (body_col[0], body_col[1], body_col[2], alpha)
    pygame.draw.circle(ghost_surf, col, (w // 2, h_radius + 2), h_radius)
    pygame.draw.rect(ghost_surf, col, (8, h_radius * 2 + 2, b_width, b_height), border_radius=7)
    pygame.draw.line(ghost_surf, col, (w // 2 - 6, h_radius * 2 + b_height), (w // 2 - 12, h - 2), 6)
    pygame.draw.line(ghost_surf, col, (w // 2 + 6, h_radius * 2 + b_height), (w // 2 + 12, h - 2), 6)
    surface.blit(ghost_surf, (gx - w // 2, int(body_top) - h_radius * 2))


def _draw_fury_flames(
    surface: pygame.Surface,
    cx: int,
    top_y: int,
    b_width: int,
    b_height: int,
    anim_frame: float,
):
    """Draw rising crimson/gold flame wisps around Crimson when in Fury."""
    flame_surf = pygame.Surface((b_width + 36, b_height + 40), pygame.SRCALPHA)
    for i in range(5):
        phase = anim_frame * 0.22 + i * 1.3
        fx = 18 + int((i / 4.0) * b_width) + int(math.sin(phase) * 5)
        fy = b_height + 20 - int(((anim_frame * 2 + i * 17) % 55))
        r = max(3, 8 - int(((anim_frame * 2 + i * 17) % 55) / 8))
        pygame.draw.circle(flame_surf, (255, 90, 20, 135), (fx, fy), r + 2)
        pygame.draw.circle(flame_surf, (255, 210, 50, 185), (fx, fy - 2), max(2, r - 1))
    surface.blit(flame_surf, (cx - b_width // 2 - 18, top_y - 16))


def _draw_shadow_mist(
    surface: pygame.Surface,
    cx: int,
    hip_y: int,
    dash_dir: int,
    anim_frame: float,
):
    """Draw dark purple/teal mist particles when Shadow dashes."""
    mist_surf = pygame.Surface((90, 70), pygame.SRCALPHA)
    for i in range(6):
        mx = 45 - dash_dir * (i * 7) + int(math.sin(anim_frame * 0.3 + i) * 4)
        my = 15 + (i * 8) % 45
        pygame.draw.circle(mist_surf, (45, 20, 65, 130 - i * 16), (mx, my), 9 - i)
        pygame.draw.circle(mist_surf, (23, 210, 225, 90 - i * 12), (mx, my), max(2, 4 - i // 2))
    surface.blit(mist_surf, (cx - 45, hip_y - 45))


def _draw_golden_compass_aura(
    surface: pygame.Surface,
    cx: int,
    ground_y: int,
    anim_frame: float,
    accent_col: Tuple[int, int, int],
):
    """Draw a faint golden geometric compass circle under Golden's feet."""
    aura_surf = pygame.Surface((88, 26), pygame.SRCALPHA)
    col = (*accent_col[:3], 85)
    pygame.draw.ellipse(aura_surf, col, (4, 3, 80, 20), 2)
    pygame.draw.ellipse(aura_surf, (*accent_col[:3], 45), (16, 6, 56, 14), 1)
    ang = anim_frame * 0.04
    for k in range(4):
        a = ang + k * (math.pi / 2)
        x1 = int(44 + math.cos(a) * 38)
        y1 = int(13 + math.sin(a) * 9)
        x2 = int(44 - math.cos(a) * 38)
        y2 = int(13 - math.sin(a) * 9)
        pygame.draw.line(aura_surf, col, (x1, y1), (x2, y2), 1)
    surface.blit(aura_surf, (cx - 44, ground_y - 11))


def _draw_shadow(surface, cx: int, ground_y: int, jump_y: float, player_num: int = 1, base_w: int = 80):
    """Draw soft multi-layered oval ground contact shadow that scales realistically with height."""
    scale = max(0.35, 1.0 - (jump_y / 180.0))
    sw = int(max(44, base_w * 0.82) * scale)
    sh = max(8, int(18 * scale))
    base_alpha = int(140 * scale)

    shadow_surf = pygame.Surface((sw + 20, sh + 12), pygame.SRCALPHA)
    # Soft outer blur
    pygame.draw.ellipse(shadow_surf, (0, 0, 0, base_alpha // 3), (0, 0, sw + 20, sh + 12))
    # Core contact shadow
    pygame.draw.ellipse(shadow_surf, (0, 0, 0, base_alpha), (8, 4, sw + 4, sh + 4))
    surface.blit(shadow_surf, (cx - (sw + 20) // 2, ground_y - (sh + 12) // 2 + 1))


def _draw_trailing_scarf(surface, cx: int, top_y: float, arm_dir: int, colour, anim_frame: float = 0.0):
    """Draw Shadow Striker's multi-segment floating scarf."""
    wave1 = int(math.sin(anim_frame * 0.24) * 5)
    wave2 = int(math.cos(anim_frame * 0.24) * 7)
    pts = [
        (cx - arm_dir * 6, int(top_y)),
        (cx - arm_dir * 26, int(top_y + 5 + wave1)),
        (cx - arm_dir * 44, int(top_y + 14 + wave2)),
        (cx - arm_dir * 38, int(top_y + 22 + wave2)),
        (cx - arm_dir * 20, int(top_y + 13 + wave1)),
        (cx - arm_dir * 6, int(top_y + 8)),
    ]
    pygame.draw.polygon(surface, OUTLINE_DARK, pts, 3)
    pygame.draw.polygon(surface, colour, pts)


def _draw_emblem(surface, cx: int, cy: int, emblem_type: str, colour):
    """Draw character chest emblem."""
    if emblem_type == "flame":
        pts = [(cx, cy - 8), (cx + 6, cy + 4), (cx + 2, cy + 2), (cx, cy + 7), (cx - 6, cy + 4)]
        pygame.draw.polygon(surface, colour, pts)
    elif emblem_type == "shield":
        pts = [(cx - 7, cy - 6), (cx + 7, cy - 6), (cx + 7, cy + 1), (cx, cy + 8), (cx - 7, cy + 1)]
        pygame.draw.polygon(surface, colour, pts, 2)
    elif emblem_type == "crescent":
        pygame.draw.circle(surface, colour, (cx, cy), 6)
        pygame.draw.circle(surface, (74, 35, 90), (cx + 3, cy - 2), 5)
    elif emblem_type == "compass":
        pygame.draw.line(surface, colour, (cx - 7, cy), (cx + 7, cy), 2)
        pygame.draw.line(surface, colour, (cx, cy - 7), (cx, cy + 7), 2)
        pygame.draw.circle(surface, colour, (cx, cy), 3)


_TAG_FONT = None


def _draw_overhead_tag(surface, cx: int, top_y: int, player_num: int, is_human: bool):
    """Clean, unobtrusive presentation that keeps in-game fighters clear and unobstructed."""
    # Top HUD already cleanly displays portraits, names, titles, and health bars.
    # We keep in-game fighting character visuals clean, unobstructed, and pristine.
    return
