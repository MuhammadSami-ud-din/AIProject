"""Offscreen moderngl renderer for the fight scene.

Pipeline per frame:
  shadow map (key light, 2048^2)  ->  MSAA HDR scene (backdrop, floor reflection,
  floor, props, fighters, projectiles, afterimages, trails, particles)  ->
  resolve  ->  bloom (bright-pass + separable blur at 1/4 res)  ->  composite
  (ACES tone map, gamma, grade, vignette, super streaks, vertical flip)  ->
  ``fbo.read`` into a reusable buffer  ->  ``pygame.image.frombuffer``.

The pygame window stays a normal software surface; HUD / banners are drawn on
top by the caller.
"""

import math
import os
import time

import numpy as np
import pygame

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.moves import HitLevel, get_move
from frontend.render3d import meshes, shaders
from frontend.render3d.animation import V_SCALE, FighterAnimator, fighter_height_px, get_clip
from frontend.render3d.arena import AMBIENT, WALL_X, get_prop_bytes, get_spec, normalize_arena
from frontend.render3d.camera import FightCamera
from frontend.render3d.characters import get_model, get_vertex_data, srgb
from frontend.render3d.mathutil import PX_TO_M, gl_bytes, look_at, normalize, ortho
from frontend.render3d.skeleton import MAX_GPU_BONES
from frontend.render3d.vfx import Particles, Trail

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "backgrounds")

SHIELD_COLOURS = {
    "Golden": (1.0, 0.75, 0.2),
    "Crimson": (1.0, 0.2, 0.25),
    "Steel": (0.3, 0.65, 1.0),
    "Shadow": (0.7, 0.3, 1.0),
}
ITEM_COLOURS = {
    "medkit": (0.3, 1.0, 0.4), "big_medkit": (0.3, 1.0, 0.4), "shield_cell": (0.3, 0.7, 1.0),
    "meter_orb": (1.0, 0.8, 0.2), "build_kit": (1.0, 0.55, 0.2), "speed_boots": (0.3, 1.0, 1.0),
    "power_fist": (1.0, 0.25, 0.25), "overcharge": (0.85, 0.35, 1.0),
}


def _px_x(x):
    return (x - ARENA_WIDTH / 2.0) * PX_TO_M


class Renderer3D:
    """Owns the GL context and all GPU resources for the 3D fight view."""

    def __init__(self, width: int = 1024, height: int = 600, samples: int = 4, ctx=None):
        import moderngl
        self.mgl = moderngl
        self.width, self.height = int(width), int(height)
        self.ctx = ctx or moderngl.create_standalone_context(require=330)
        ctx = self.ctx
        self.samples = samples
        # --- programs ---
        self.p_char = ctx.program(vertex_shader=shaders.CHAR_VS, fragment_shader=shaders.CHAR_FS)
        self.p_ghost = ctx.program(vertex_shader=shaders.CHAR_VS, fragment_shader=shaders.GHOST_FS)
        self.p_depth = ctx.program(vertex_shader=shaders.DEPTH_VS, fragment_shader=shaders.DEPTH_FS)
        self.p_floor = ctx.program(vertex_shader=shaders.FLOOR_VS, fragment_shader=shaders.FLOOR_FS)
        self.p_back = ctx.program(vertex_shader=shaders.BACKDROP_VS, fragment_shader=shaders.BACKDROP_FS)
        self.p_part = ctx.program(vertex_shader=shaders.PARTICLE_VS, fragment_shader=shaders.PARTICLE_FS)
        self.p_ribbon = ctx.program(vertex_shader=shaders.RIBBON_VS, fragment_shader=shaders.RIBBON_FS)
        self.p_bright = ctx.program(vertex_shader=shaders.QUAD_VS, fragment_shader=shaders.BRIGHT_FS)
        self.p_blur = ctx.program(vertex_shader=shaders.QUAD_VS, fragment_shader=shaders.BLUR_FS)
        self.p_comp = ctx.program(vertex_shader=shaders.QUAD_VS, fragment_shader=shaders.COMPOSITE_FS)
        # --- framebuffers ---
        W, H = self.width, self.height
        self.msaa_col = ctx.renderbuffer((W, H), 4, samples=samples, dtype="f2")
        self.msaa_depth = ctx.depth_renderbuffer((W, H), samples=samples)
        self.fbo_msaa = ctx.framebuffer([self.msaa_col], self.msaa_depth)
        self.scene_tex = ctx.texture((W, H), 4, dtype="f2")
        self.scene_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.fbo_scene = ctx.framebuffer([self.scene_tex])
        bw, bh = max(1, W // 4), max(1, H // 4)
        self.bloom_a = ctx.texture((bw, bh), 4, dtype="f2")
        self.bloom_b = ctx.texture((bw, bh), 4, dtype="f2")
        for t in (self.bloom_a, self.bloom_b):
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            t.repeat_x = t.repeat_y = False
        self.fbo_bloom_a = ctx.framebuffer([self.bloom_a])
        self.fbo_bloom_b = ctx.framebuffer([self.bloom_b])
        self.bloom_size = (bw, bh)
        self.out_tex = ctx.texture((W, H), 4)
        self.fbo_out = ctx.framebuffer([self.out_tex])
        self.shadow_size = 2048
        self.shadow_tex = ctx.depth_texture((self.shadow_size, self.shadow_size))
        self.shadow_tex.compare_func = "<="
        self.shadow_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.shadow_tex.repeat_x = self.shadow_tex.repeat_y = False
        self.fbo_shadow = ctx.framebuffer(depth_attachment=self.shadow_tex)
        self._readbuf = bytearray(W * H * 3)
        # --- static geometry ---
        quad = np.array((-1, -1, 1, -1, -1, 1, 1, 1), dtype="f4")
        self.vbo_quad = ctx.buffer(quad.tobytes())
        self.vao_bright = ctx.vertex_array(self.p_bright, [(self.vbo_quad, "2f", "in_pos")])
        self.vao_blur = ctx.vertex_array(self.p_blur, [(self.vbo_quad, "2f", "in_pos")])
        self.vao_comp = ctx.vertex_array(self.p_comp, [(self.vbo_quad, "2f", "in_pos")])
        floor = np.array((-24, 0, 6, 24, 0, 6, 24, 0, -16, -24, 0, 6, 24, 0, -16, -24, 0, -16), dtype="f4")
        self.vbo_floor = ctx.buffer(floor.tobytes())
        self.vao_floor = ctx.vertex_array(self.p_floor, [(self.vbo_floor, "3f", "in_pos")])
        self._build_backdrop_mesh()
        corners = np.array((-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1), dtype="f4")
        self.vbo_corner = ctx.buffer(corners.tobytes())
        self.vbo_inst = ctx.buffer(reserve=4096 * 48, dynamic=True)
        self.vao_part = ctx.vertex_array(self.p_part, [
            (self.vbo_corner, "2f", "in_corner"),
            (self.vbo_inst, "3f 3f 4f 2f/i", "i_pos", "i_vel", "i_col", "i_size_kind"),
        ])
        self.vbo_ribbon = ctx.buffer(reserve=7 * 4 * 6000, dynamic=True)
        self.vao_ribbon = ctx.vertex_array(self.p_ribbon, [(self.vbo_ribbon, "3f 4f", "in_pos", "in_col")])
        self.vbo_boxes = ctx.buffer(reserve=56 * 36 * 6 * 200, dynamic=True)
        self.vao_boxes = ctx.vertex_array(self.p_char, [
            (self.vbo_boxes, "3f 3f 3f 4f 1f", "in_pos", "in_nrm", "in_col", "in_mat", "in_bone")])
        self.vao_boxes_depth = ctx.vertex_array(self.p_depth, [(self.vbo_boxes, "3f 40x 1f", "in_pos", "in_bone")])
        cube_p, cube_n = meshes.rounded_box(1.0, 1.0, 1.0, 0.06, 2)
        self._cube = (cube_p.astype("f4"), cube_n.astype("f4"))
        sp, sn = meshes.sphere(1.0, 14, 10)
        self._sphere = (sp, sn)
        self._bone_scratch = np.zeros((MAX_GPU_BONES, 4, 4), dtype="f4")
        self._identity_bones = np.tile(np.identity(4, dtype="f4"), (MAX_GPU_BONES, 1, 1)).tobytes()
        # --- state ---
        self.camera = FightCamera(W, H)
        self.particles = Particles()
        self.fighters = {}
        self.char_vaos = {}
        self.arena_key = None
        self.backdrop_tex = None
        self.time = 0.0
        self.trails = {1: Trail(), 2: Trail()}
        self.ghosts = {1: [], 2: []}
        self.screen_flash = 0.0
        self.streak = 0.0
        self.prev_state = None
        self.ko_focus = None
        self.stats_ms = []
        self.surface = None
        self.release_list = []

    # ------------------------------------------------------------------
    def _build_backdrop_mesh(self):
        # a gently curved panorama behind the stage
        segs = 24
        R = 26.0
        width_ang = 1.25  # radians covered
        h = 21.0
        bottom = -4.6
        verts = []
        for i in range(segs):
            a0 = -width_ang / 2 + width_ang * i / segs
            a1 = -width_ang / 2 + width_ang * (i + 1) / segs
            u0, u1 = i / segs, (i + 1) / segs
            p = []
            for a, u in ((a0, u0), (a1, u1)):
                x = math.sin(a) * R
                z = 9.0 - math.cos(a) * R
                p.append((x, z, u))
            (x0, z0, u0), (x1, z1, u1) = p
            verts += [
                (x0, bottom, z0, u0, 0.0), (x1, bottom, z1, u1, 0.0), (x1, bottom + h, z1, u1, 1.0),
                (x0, bottom, z0, u0, 0.0), (x1, bottom + h, z1, u1, 1.0), (x0, bottom + h, z0, u0, 1.0),
            ]
        data = np.asarray(verts, dtype="f4")
        self.vbo_back = self.ctx.buffer(data.tobytes())
        self.vao_back = self.ctx.vertex_array(self.p_back, [(self.vbo_back, "3f 2f", "in_pos", "in_uv")])

    # ------------------------------------------------------------------
    def setup(self, char1: str, char2: str, arena_name: str):
        """Prepare fighters and arena for a match."""
        self.set_arena(arena_name)
        self.fighters = {1: FighterAnimator(char1, 1), 2: FighterAnimator(char2, 2)}
        for name in (char1, char2):
            self._char_vao(name)
        self.camera.reset()
        self.particles.clear()
        self.prev_state = None
        self.trails = {1: Trail(), 2: Trail()}
        self.ghosts = {1: [], 2: []}

    def reset_round(self):
        for a in self.fighters.values():
            a.reset()
        self.camera.reset()
        self.particles.clear()
        self.prev_state = None
        self.ko_focus = None

    def _char_vao(self, name):
        model = get_model(name)
        key = model.name
        if key not in self.char_vaos:
            vbo = self.ctx.buffer(get_vertex_data(key))
            vao = self.ctx.vertex_array(self.p_char, [
                (vbo, "3f 3f 3f 4f 1f", "in_pos", "in_nrm", "in_col", "in_mat", "in_bone")])
            vao_g = self.ctx.vertex_array(self.p_ghost, [
                (vbo, "3f 3f 3f 4f 1f", "in_pos", "in_nrm", "in_col", "in_mat", "in_bone")])
            vao_d = self.ctx.vertex_array(self.p_depth, [(vbo, "3f 40x 1f", "in_pos", "in_bone")])
            self.char_vaos[key] = (vao, vao_g, vao_d)
        return self.char_vaos[key]

    def set_arena(self, arena_name: str):
        key = normalize_arena(arena_name)
        if key == self.arena_key:
            return
        self.arena_key = key
        self.spec = get_spec(key)
        path = os.path.join(ASSET_DIR, key + ".jpeg")
        try:
            img = pygame.image.load(path)
            img = img.convert() if pygame.display.get_init() and pygame.display.get_surface() else img
            data = pygame.image.tobytes(img, "RGB", True)
            size = img.get_size()
        except Exception:
            size = (4, 4)
            col = bytes(int(c ** (1 / 2.2) * 255) for c in self.spec.fog)
            data = col * 16
        if self.backdrop_tex is not None:
            self.backdrop_tex.release()
        self.backdrop_tex = self.ctx.texture(size, 3, data)
        self.backdrop_tex.build_mipmaps()
        self.backdrop_tex.filter = (self.mgl.LINEAR_MIPMAP_LINEAR, self.mgl.LINEAR)
        self.backdrop_tex.repeat_x = self.backdrop_tex.repeat_y = False
        props = get_prop_bytes(key)
        self.vbo_props = self.ctx.buffer(props) if props else None
        if self.vbo_props is not None:
            self.vao_props = self.ctx.vertex_array(self.p_char, [
                (self.vbo_props, "3f 3f 3f 4f 1f", "in_pos", "in_nrm", "in_col", "in_mat", "in_bone")])
            self.vao_props_d = self.ctx.vertex_array(self.p_depth, [(self.vbo_props, "3f 40x 1f", "in_pos", "in_bone")])

    # ------------------------------------------------------------------
    # Simulation-step hooks
    # ------------------------------------------------------------------
    def push_step(self, prev_state, state):
        """Feed a new engine state (call after every step(), before effects are cleared)."""
        if not self.fighters:
            return
        f1, f2 = state.fighter1, state.fighter2
        self.fighters[1].update(f1, f2, state)
        self.fighters[2].update(f2, f1, state)
        if prev_state is None:
            self.prev_state = state
            return
        for idx, (d_prev, d, a_prev, a) in ((2, (prev_state.fighter2, f2, prev_state.fighter1, f1)),
                                          (1, (prev_state.fighter1, f1, prev_state.fighter2, f2))):
            self._detect_events(idx, d_prev, d, a_prev, a, prev_state, state)
        if state.super_freeze_frames > 0 and getattr(prev_state, "super_freeze_frames", 0) == 0:
            att = self.fighters.get(getattr(state, "super_attacker", 1) or 1)
            if att is not None:
                self.particles.burst(att.chest_pos, att.model.accent)
                self.screen_flash = max(self.screen_flash, 0.35)
        self.prev_state = state

    def _detect_events(self, idx, d_prev, d, a_prev, a, prev_state, state):
        anim_d = self.fighters[idx]
        anim_a = self.fighters[3 - idx]
        eff = getattr(d, "last_hit_effect", "none") or "none"
        a_eff = getattr(a, "last_hit_effect", "none") or "none"
        parry = eff == "parry"
        guard_break = eff == "guard_break"
        block = (eff == "block") or (d.blockstun > d_prev.blockstun and eff not in ("hit", "counter"))
        hit = (eff in ("hit", "counter") and not parry) or (d.hitstun > d_prev.hitstun + 1) or \
              (d.health < d_prev.health - 1e-4 and not block)
        if guard_break:
            hit = True
        burst = eff == "burst" or (getattr(d, "burst_used_this_round", False) and
                                   not getattr(d_prev, "burst_used_this_round", False))
        if burst:
            anim_d.on_burst()
            self.particles.burst(anim_d.chest_pos, anim_d.model.accent)
            self.camera.kick(1.2, (1, 0, 0), push=0.4)
            hit = block = False
        if parry:
            anim_d.on_parry()
            pos = self._contact_point(anim_a, anim_d)
            self.particles.parry_flash(pos)
            self.camera.kick(0.6, (1, 0, 0))
            self.screen_flash = max(self.screen_flash, 0.18)
            return
        if not (hit or block):
            # landing / knockdown dust
            if d.is_knocked_down and not d_prev.is_knocked_down and not d.in_air:
                self.particles.dust(anim_d.root_pos, 14, 0.55, strength=1.4)
                self.particles.ground_ring(anim_d.root_pos, (0.8, 0.75, 0.65), 0.3, 6.0, 0.35)
                self.camera.kick(0.8, (0, -1, 0))
            if d_prev.in_air and not d.in_air:
                self.particles.dust(anim_d.root_pos, 6 if not d.is_knocked_down else 14, 0.3)
            if getattr(d, "dash_frames_left", 0) > getattr(d_prev, "dash_frames_left", 0) or \
                    (d.last_action in (Action.DASH, Action.BACKDASH) and d_prev.last_action not in
                     (Action.DASH, Action.BACKDASH)):
                self.particles.dust(anim_d.root_pos, 5, 0.2, strength=0.8)
            if d.is_thrown and not d_prev.is_thrown:
                self.particles.hit_sparks(anim_d.chest_pos, (0, 1, 0), (1.0, 1.0, 1.0), 0.2)
            return
        move = get_move(a.character_name, a.current_action) if a.current_action is not None else None
        dmg = move.damage if move is not None else max(0.0, (d_prev.health - d.health) * 100.0)
        if dmg <= 0.0:
            dmg = max(0.0, (d_prev.health - d.health) * 100.0) or 3.0
        is_super = a.current_action == Action.SUPER
        counter = a_eff == "counter" or eff == "counter"
        strength = min(1.0, max(0.0, (dmg - 2.0) / 13.0))
        if is_super:
            strength = 1.0
        if counter:
            strength = min(1.0, strength + 0.3)
        level = "mid"
        if move is not None:
            if move.hit_level == HitLevel.LOW:
                level = "low"
            elif move.hit_level == HitLevel.HIGH or move.action in (Action.ANTI_AIR, Action.HEAVY_KICK):
                level = "high"
        # projectile hits come from the dart, not a limb
        proj_hit = move is None or getattr(move, "is_projectile", False) or a.attack_phase == "none"
        pos = self._contact_point(anim_a, anim_d, use_limb=not proj_hit)
        direction = np.array((anim_d.root_pos[0] - anim_a.root_pos[0], 0.25, 0.0))
        anim_d.on_hit(strength, level, blocked=block and not guard_break)
        if block and not guard_break:
            self.particles.block_sparks(pos, direction, 0.3 + strength * 0.5)
            self.camera.kick(0.25 + 0.5 * strength, direction)
        else:
            col = anim_a.model.spark
            if counter:
                col = (1.0, 0.35, 0.15)
            self.particles.hit_sparks(pos, direction, col, strength + (0.15 if counter else 0.0))
            self.camera.kick(0.35 + 1.5 * strength, direction,
                             tilt=(2.2 * strength * (1 if direction[0] > 0 else -1)) if strength > 0.45 else 0.0,
                             push=0.6 * strength if strength > 0.45 else 0.0)
            if guard_break:
                self.particles.burst(anim_d.chest_pos, (0.9, 0.3, 1.0))
            if strength > 0.75:
                self.screen_flash = max(self.screen_flash, 0.10)
        if d.health <= 0.0 < d_prev.health:
            self.screen_flash = max(self.screen_flash, 0.3)
            self.particles.burst(anim_d.chest_pos, (1.0, 0.9, 0.7))
            self.camera.kick(2.5, direction, push=1.0)

    def _contact_point(self, anim_a, anim_d, use_limb=True):
        target = anim_d.chest_pos
        if use_limb and anim_a.limb in anim_a.tips:
            tip = anim_a.tips[anim_a.limb]
            # keep the burst between the limb tip and the defender's body
            return tip + (target - tip) * 0.25
        if use_limb:
            clip = get_clip(anim_a.character, anim_a.f.current_action) if anim_a.f is not None else None
            if clip is not None and clip.limb in anim_a.tips:
                tip = anim_a.tips[clip.limb]
                return tip + (target - tip) * 0.25
        return target + np.array((-0.15 * np.sign(target[0] - anim_a.root_pos[0]), 0.0, 0.1))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def world_to_screen(self, x_px: float, height_m: float = 1.9):
        p = self.camera.project((_px_x(x_px), height_m, 0.0), self.width, self.height)
        return p if p is not None else (self.width / 2, self.height / 2)

    def _set(self, prog, name, value):
        try:
            u = prog[name]
        except KeyError:
            return
        u.value = value

    def _write(self, prog, name, data):
        try:
            u = prog[name]
        except KeyError:
            return
        u.write(data)

    def _lighting(self, prog, dim):
        sp = self.spec
        cam = self.camera
        self._set(prog, "u_cam_pos", tuple(float(c) for c in cam.eye))
        kd = self._key_dir()
        self._set(prog, "u_key_dir", tuple(kd))
        self._set(prog, "u_key_col", tuple(c * 0.62 for c in sp.key_col))
        self._set(prog, "u_fill_dir", tuple(normalize((-kd[0], 0.3, 0.9))))
        self._set(prog, "u_fill_col", sp.fill_col)
        self._set(prog, "u_rim_dir", tuple(normalize((-kd[0] * 1.5, 0.5, -1.0))))
        self._set(prog, "u_rim_col", tuple(c * 0.6 for c in sp.rim_col))
        self._set(prog, "u_sky", sp.sky)
        self._set(prog, "u_ground", sp.ground)
        self._set(prog, "u_fog_col", sp.fog)
        self._set(prog, "u_fog", sp.fog_range)
        self._write(prog, "u_point_pos", self._point_pos)
        self._write(prog, "u_point_col", self._point_col)
        self._write(prog, "u_shadow_mat", gl_bytes(self._shadow_mat_tex))
        self._set(prog, "u_shadow_texel", 1.0 / self.shadow_size)
        self._set(prog, "u_dim", dim)
        self._set(prog, "u_shadow", 0)

    def _update_lights(self):
        sp = self.spec
        pos = np.zeros((4, 4), dtype="f4")
        col = np.zeros((4, 4), dtype="f4")
        t = self.time
        for i, L in enumerate(sp.lights[:3]):
            x, y, z, r, cr, cg, cb, inten, flick = L
            k = 1.0
            if flick:
                k = 0.82 + 0.12 * math.sin(t * 13.0 + i * 3.1) + 0.06 * math.sin(t * 29.0 + i)
            pos[i] = (x, y, z, r)
            col[i] = (cr, cg, cb, inten * k)
        # dynamic light from the brightest recent impact
        if self._impact_light[3] > 0.0:
            pos[3] = self._impact_light[:3] + (2.5,)
            c = self._impact_col
            col[3] = (c[0], c[1], c[2], self._impact_light[3] * 4.0)
        self._point_pos = pos.tobytes()
        self._point_col = col.tobytes()

    _impact_light = (0.0, 0.0, 0.0, 0.0)
    _impact_col = (1.0, 0.7, 0.4)

    def _key_dir(self):
        k = self.spec.key_dir
        return normalize((k[0] * 1.8 if abs(k[0]) > 0.1 else -0.6, k[1], k[2] * 0.55))

    def _shadow_matrices(self):
        kd = self._key_dir()
        cx = float(self.camera.cx)
        center = np.array((cx, 0.8, -0.5))
        eye = center + kd * 12.0
        view = look_at(eye, center, (0.0, 1.0, 0.0) if abs(kd[1]) < 0.99 else (0.0, 0.0, 1.0))
        proj = ortho(-7.5, 7.5, -5.0, 5.0, 0.5, 30.0)
        self._shadow_vp = proj @ view
        bias = np.array(((0.5, 0, 0, 0.5), (0, 0.5, 0, 0.5), (0, 0, 0.5, 0.5), (0, 0, 0, 1.0)))
        self._shadow_mat_tex = bias @ self._shadow_vp

    def _box_batch(self, boxes):
        """boxes: list of (center xyz, size xyz, colour linear rgb, material, yaw deg)."""
        if not boxes:
            return 0
        cp, cn = self._cube
        n = len(cp)
        out = np.empty((n * len(boxes), 14), dtype="f4")
        for i, (c, s, col, mat, yaw) in enumerate(boxes):
            seg = out[i * n:(i + 1) * n]
            p = cp * np.asarray(s, dtype="f4")
            if yaw:
                a = math.radians(yaw)
                ca, sa = math.cos(a), math.sin(a)
                x, z = p[:, 0].copy(), p[:, 2].copy()
                p[:, 0] = ca * x + sa * z
                p[:, 2] = -sa * x + ca * z
                nx, nz = cn[:, 0] * ca + cn[:, 2] * sa, -cn[:, 0] * sa + cn[:, 2] * ca
                seg[:, 3], seg[:, 4], seg[:, 5] = nx, cn[:, 1], nz
            else:
                seg[:, 3:6] = cn
            seg[:, 0:3] = p + np.asarray(c, dtype="f4")
            seg[:, 6:9] = col
            seg[:, 9:13] = mat
            seg[:, 13] = 0.0
        data = out.tobytes()
        if len(data) > self.vbo_boxes.size:
            self.vbo_boxes.orphan(len(data) * 2)
        self.vbo_boxes.write(data)
        return len(out)

    def _mode_objects(self, state):
        """Rumble / Shield Wall objects -> (boxes, glow ribbons)."""
        boxes, glow = [], []
        rules = getattr(state, "rules", None)
        t = self.time
        if rules is None:
            return boxes, glow
        if getattr(rules, "is_rumble", False):
            if getattr(rules, "enable_objects", False):
                for o in getattr(state, "arena_objects", []):
                    x = _px_x(o.x)
                    w = o.width * PX_TO_M
                    h = max(0.05, o.height * V_SCALE)
                    if o.object_type == "crate":
                        hp = max(0.2, o.hp / max(1.0, o.max_hp))
                        boxes.append(((x, h / 2, -0.15), (w, h, 0.5), (0.45 * hp + 0.15, 0.28 * hp + 0.1, 0.12),
                                      (0.8, 0.0, 0.0, 0.0), 8.0))
                    elif o.object_type == "jump_pad":
                        ready = o.cooldown <= 0
                        boxes.append(((x, 0.04, -0.15), (w, 0.08, 0.6), (0.2, 0.9, 1.0) if ready else (0.2, 0.3, 0.4),
                                      (0.4, 0.0, 1.5 if ready else 0.2, 0.0), 0.0))
                    elif o.object_type == "trap":
                        armed = o.trigger_timer > 0 or o.is_triggered
                        boxes.append(((x, 0.03, -0.15), (w, 0.06, 0.55),
                                      (1.0, 0.15, 0.1) if armed else (0.35, 0.3, 0.3),
                                      (0.4, 0.6, 2.0 if armed else 0.0, 0.0), 0.0))
                        if o.is_triggered:
                            for k in range(4):
                                boxes.append(((x - w * 0.35 + k * w * 0.23, 0.18, -0.15), (0.05, 0.3, 0.05),
                                              (0.8, 0.8, 0.85), (0.3, 0.9, 0.0, 0.0), 0.0))
            if getattr(rules, "enable_building", False):
                for wl in getattr(state, "walls", []):
                    x = _px_x(wl.x)
                    w = wl.width * PX_TO_M
                    h = wl.height * V_SCALE
                    hp = max(0.0, wl.hp / max(1.0, wl.max_hp))
                    base = (0.25, 0.45, 1.0) if wl.owner == 1 else (1.0, 0.3, 0.25)
                    boxes.append(((x, h / 2, 0.0), (w, h, 0.7), tuple(c * (0.35 + 0.4 * hp) for c in base),
                                  (0.35, 0.3, 0.25 + 0.6 * hp, 0.0), 0.0))
            if getattr(rules, "enable_loot", False):
                for it in getattr(state, "items", []):
                    x = _px_x(it.x)
                    c = ITEM_COLOURS.get(it.item_type, (1.0, 1.0, 1.0))
                    bob = 0.25 + 0.06 * math.sin(t * 3.0 + it.id)
                    boxes.append(((x, bob, 0.0), (0.16, 0.16, 0.16), c, (0.3, 0.2, 2.5, 0.0), (t * 120.0) % 360))
                    if self.particles.rng.random() < 0.2:
                        self.particles.aura((x, bob, 0.0), c, 1)
                sd = getattr(state, "supply_drop", None)
                if sd is not None:
                    x = _px_x(sd.x)
                    y = max(0.0, sd.y * V_SCALE)
                    boxes.append(((x, y + 0.25, 0.0), (0.5, 0.5, 0.5), (0.6, 0.45, 0.2), (0.6, 0.3, 0.3, 0.0), 0.0))
                    c = ITEM_COLOURS.get(sd.item_type, (1.0, 0.8, 0.2))
                    glow.append(self._beam(x, 0.0, 0.08, 6.0, c, 0.5))
            if getattr(rules, "enable_zone", False) and getattr(state, "zone", None) is not None:
                z = state.zone
                pulse = 0.7 + 0.3 * math.sin(t * 6.0)
                for edge in (z.left, z.right):
                    glow.append(self._wall_plane(_px_x(edge), 4.0, (1.0, 0.15, 0.35), 0.5 * pulse))
                if getattr(z, "is_warning", False):
                    for edge in (z.target_left, z.target_right):
                        glow.append(self._wall_plane(_px_x(edge), 3.0, (1.0, 0.85, 0.1), 0.18 * pulse))
        if getattr(rules, "enable_shield_wall", False):
            for f in (state.fighter1, state.fighter2):
                sw = getattr(f, "shield_wall", None)
                if sw is None:
                    continue
                c = SHIELD_COLOURS.get(f.character_name, (0.4, 0.9, 1.0))
                hp = max(0.0, sw.hp / max(1.0, sw.max_hp))
                x = _px_x(sw.x)
                h = sw.height * V_SCALE
                w = sw.width * PX_TO_M
                flick = 1.0 if hp > 0.33 else (0.6 + 0.4 * math.sin(t * 40.0))
                glow.append(self._panel(x, w, h, c, (0.35 + 0.25 * math.sin(t * 5.0)) * flick))
                boxes.append(((x, 0.04, 0.0), (w + 0.1, 0.08, 0.5), tuple(v * 0.6 for v in c), (0.3, 0.6, 1.5, 0.0), 0))
        return boxes, glow

    @staticmethod
    def _wall_plane(x, h, c, a):
        z0, z1 = -2.5, 2.0
        col_b = (c[0] * 2, c[1] * 2, c[2] * 2, a)
        col_t = (c[0] * 2, c[1] * 2, c[2] * 2, 0.0)
        return np.array(((x, 0, z0, *col_b), (x, 0, z1, *col_b), (x, h, z1, *col_t),
                         (x, 0, z0, *col_b), (x, h, z1, *col_t), (x, h, z0, *col_t)), dtype="f4")

    @staticmethod
    def _panel(x, w, h, c, a):
        out = []
        cb = (c[0] * 2.5, c[1] * 2.5, c[2] * 2.5, a)
        ct = (c[0] * 2.5, c[1] * 2.5, c[2] * 2.5, a * 0.4)
        for z in (-0.3, 0.3):
            out += [(x - w / 2, 0, z, *cb), (x + w / 2, 0, z, *cb), (x + w / 2, h, z, *ct),
                    (x - w / 2, 0, z, *cb), (x + w / 2, h, z, *ct), (x - w / 2, h, z, *ct)]
        for sx in (-w / 2, w / 2):
            out += [(x + sx, 0, -0.3, *cb), (x + sx, 0, 0.3, *cb), (x + sx, h, 0.3, *ct),
                    (x + sx, 0, -0.3, *cb), (x + sx, h, 0.3, *ct), (x + sx, h, -0.3, *ct)]
        return np.asarray(out, dtype="f4")

    @staticmethod
    def _beam(x, z, w, h, c, a):
        cb = (c[0] * 2, c[1] * 2, c[2] * 2, a)
        ct = (c[0] * 2, c[1] * 2, c[2] * 2, 0.0)
        return np.array(((x - w, 0, z, *cb), (x + w, 0, z, *cb), (x + w, h, z, *ct),
                         (x - w, 0, z, *cb), (x + w, h, z, *ct), (x - w, h, z, *ct)), dtype="f4")

    # ------------------------------------------------------------------
    def render(self, state, frac: float = 0.0, dt: float = 1.0 / 60.0, intro: float = 0.0,
               ko_focus: bool = False, training_boxes: bool = False):
        """Render the 3D scene for ``state`` and return a pygame Surface (width x height)."""
        t0 = time.perf_counter()
        ctx = self.ctx
        mgl = self.mgl
        self.time += dt
        if not self.fighters:
            self.setup(state.fighter1.character_name, state.fighter2.character_name, self.arena_key or "")
        if self.fighters[1].f is None:
            self.push_step(None, state)
        a1, a2 = self.fighters[1], self.fighters[2]
        # interpolated x for smooth motion
        prev = self.prev_state
        x1, x2 = state.fighter1.x, state.fighter2.x
        a1.compute(frac, x1, dt, z=0.0)
        a2.compute(frac, x2, dt, z=0.0)

        # camera
        super_focus = None
        if getattr(state, "super_freeze_frames", 0) > 0:
            att = self.fighters.get(getattr(state, "super_attacker", 0))
            if att is not None:
                super_focus = att.chest_pos
                self.streak = 1.0
                if self.particles.rng.random() < 0.8:
                    self.particles.aura(att.root_pos + np.array((0, 0.9, 0)), att.model.accent, 5)
        else:
            self.streak = max(0.0, self.streak - dt * 4.0)
        kof = None
        if ko_focus:
            loser = a1 if state.fighter1.health <= state.fighter2.health else a2
            kof = loser.root_pos
        self.camera.update(a1.root_pos[0], a2.root_pos[0], a1.root_pos[1], a2.root_pos[1], dt,
                           super_focus=super_focus, ko_focus=kof, intro=intro)
        vp = self.camera.viewproj
        vp_bytes = gl_bytes(vp)
        dim = 0.75 if super_focus is not None else 0.0

        # particles / trails update
        self._ambient(dt)
        for a in (a1, a2):
            if a.glow > 1.2 and self.particles.rng.random() < 0.5:
                self.particles.aura(a.root_pos + np.array((0, 0.9, 0)), a.model.accent, 2)
            if a.f is not None and a.f.is_fury if hasattr(a.f, "is_fury") else False:
                if self.particles.rng.random() < 0.15:
                    self.particles.aura(a.root_pos + np.array((0, 0.9, 0)), (1.0, 0.25, 0.1), 1)
        for p in getattr(state, "projectiles", []):
            owner = self.fighters.get(p.owner, a1)
            pos = (_px_x(p.x), getattr(p, "height", 50.0) * V_SCALE + 0.15, 0.0)
            c = owner.model.accent
            self.particles.emit([pos], (-np.sign(p.vx) * 0.5, 0.0, 0.0), (c[0] * 4, c[1] * 4, c[2] * 4, 0.9),
                                0.16, 0.18, kind=0, grow=-0.5)
        self.particles.update(dt)
        for idx, a in ((1, a1), (2, a2)):
            tr = self.trails[idx]
            f = a.f
            active = False
            limb = a.limb
            if f is not None and f.attack_phase in ("startup", "active", "recovery") and limb in a.tips:
                from frontend.render3d.animation import move_time
                mt = move_time(f)
                if mt is not None:
                    tt, s, aa, r = mt
                    active = (tt >= s - 2.5) and (tt <= s + aa + r * 0.3)
            tr.age(dt)
            if active:
                tr.push(a.tips[limb], a.joints[limb], True)
        self._impact_light = (0.0, 0.0, 0.0, 0.0)
        if self.particles.n:
            k = self.particles.kind[:self.particles.n]
            idx = np.nonzero(k == 4)[0]
            if len(idx):
                i = idx[-1]
                life = self.particles.life[i] / max(1e-4, self.particles.max_life[i])
                p = self.particles.pos[i]
                self._impact_light = (float(p[0]), float(p[1]), float(p[2] + 0.3), float(life))
                c = self.particles.col[i]
                m = max(c[0], c[1], c[2], 1e-3)
                self._impact_col = (c[0] / m, c[1] / m, c[2] / m)
        self._update_lights()
        self._shadow_matrices()
        boxes, glow = self._mode_objects(state)
        nbox = self._box_batch(boxes)

        # ghosts (afterimages) for dashes / flagged clips
        for idx, a in ((1, a1), (2, a2)):
            f = a.f
            want = False
            if f is not None:
                if f.attack_phase != "none":
                    clip = get_clip(a.character, f.current_action)
                    want = clip is not None and clip.ghost
                want = want or a.dash_w > 0.5
            g = self.ghosts[idx]
            if want and int(self.time * 60) % 3 == 0:
                g.append([self._bones_bytes(a), 1.0])
            for item in g:
                item[1] -= dt * 4.0
            self.ghosts[idx] = [item for item in g if item[1] > 0][-5:]

        # ---------------- shadow pass ----------------
        self.fbo_shadow.use()
        ctx.viewport = (0, 0, self.shadow_size, self.shadow_size)
        self.fbo_shadow.clear(depth=1.0)
        ctx.enable(mgl.DEPTH_TEST)
        ctx.disable(mgl.BLEND | mgl.CULL_FACE)
        self._write(self.p_depth, "u_viewproj", gl_bytes(self._shadow_vp))
        for a in (a1, a2):
            self._write(self.p_depth, "u_bones", self._bones_bytes(a))
            self.char_vaos[a.model.name][2].render()
        self._write(self.p_depth, "u_bones", self._identity_bones)
        if self.vbo_props is not None:
            self.vao_props_d.render()
        if nbox:
            self.vao_boxes_depth.render(vertices=nbox)

        # ---------------- main pass ----------------
        self.fbo_msaa.use()
        ctx.viewport = (0, 0, self.width, self.height)
        sp = self.spec
        self.fbo_msaa.clear(*sp.fog, 1.0, depth=1.0)
        self.shadow_tex.use(location=0)
        # backdrop
        ctx.disable(mgl.DEPTH_TEST)
        self.backdrop_tex.use(location=1)
        self._write(self.p_back, "u_viewproj", vp_bytes)
        self._set(self.p_back, "u_tex", 1)
        self._set(self.p_back, "u_exposure", sp.backdrop_exposure)
        self._set(self.p_back, "u_fog_col", sp.fog)
        self._set(self.p_back, "u_haze", sp.haze)
        self._set(self.p_back, "u_dim", dim)
        self.vao_back.render()
        ctx.enable(mgl.DEPTH_TEST)
        self.shadow_tex.use(location=0)
        # floor reflection of the fighters
        self._lighting(self.p_char, dim)
        refl = vp @ np.diag((1.0, -1.0, 1.0, 1.0))
        self._write(self.p_char, "u_viewproj", gl_bytes(refl))
        self._set(self.p_char, "u_reflect", 1.0)
        self._set(self.p_char, "u_rim_boost", 0.0)
        self._set(self.p_char, "u_flash", 0.0)
        self._set(self.p_char, "u_glow", 0.0)
        self._set(self.p_char, "u_glow_col", (0.0, 0.0, 0.0))
        self._set(self.p_char, "u_flash_col", (1.0, 1.0, 1.0))
        for a in (a1, a2):
            self._write(self.p_char, "u_bones", self._bones_bytes(a))
            self.char_vaos[a.model.name][0].render()
        if self.vbo_props is not None:
            self._write(self.p_char, "u_bones", self._identity_bones)
            self.vao_props.render()
        # floor
        ctx.enable(mgl.BLEND)
        ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
        self._lighting(self.p_floor, dim)
        self._write(self.p_floor, "u_viewproj", vp_bytes)
        self._set(self.p_floor, "u_floor_type", sp.floor_type)
        self._set(self.p_floor, "u_floor_a", sp.floor_a)
        self._set(self.p_floor, "u_floor_b", sp.floor_b)
        self._set(self.p_floor, "u_floor_line", sp.floor_line)
        self._set(self.p_floor, "u_floor_emit", sp.floor_emit)
        self._set(self.p_floor, "u_gloss", sp.gloss)
        self._set(self.p_floor, "u_time", self.time)
        self._set(self.p_floor, "u_wall", WALL_X)
        blobs = np.array((a1.root_pos[0], 0.0, a2.root_pos[0], 0.0), dtype="f4")
        self._write(self.p_floor, "u_blob", blobs.tobytes())
        self._set(self.p_floor, "u_blob_r", (0.45 / (1.0 + a1.root_pos[1] * 1.2), 0.45 / (1.0 + a2.root_pos[1] * 1.2)))
        self.vao_floor.render()
        ctx.disable(mgl.BLEND)
        # props + mode boxes + fighters
        self._write(self.p_char, "u_viewproj", vp_bytes)
        self._set(self.p_char, "u_reflect", 0.0)
        self._write(self.p_char, "u_bones", self._identity_bones)
        if self.vbo_props is not None:
            self.vao_props.render()
        if nbox:
            self.vao_boxes.render(vertices=nbox)
        sup_att = getattr(state, "super_attacker", 0) if dim > 0 else 0
        for idx, a in ((1, a1), (2, a2)):
            self._set(self.p_char, "u_dim", dim if idx != sup_att else 0.0)
            self._set(self.p_char, "u_glow", float(a.glow) * 0.6 + (1.5 if idx == sup_att else 0.0))
            self._set(self.p_char, "u_glow_col", tuple(a.model.accent))
            self._set(self.p_char, "u_flash", float(min(1.0, a.flash)) * 0.12)
            self._set(self.p_char, "u_flash_col", (1.0, 0.92, 0.8))
            self._set(self.p_char, "u_rim_boost", 1.5 if idx == sup_att else 0.0)
            self._write(self.p_char, "u_bones", self._bones_bytes(a))
            self.char_vaos[a.model.name][0].render()
        self._set(self.p_char, "u_flash", 0.0)
        self._set(self.p_char, "u_glow", 0.0)
        # projectiles as glowing meshes
        projs = getattr(state, "projectiles", [])
        if projs:
            bx = []
            for p in projs:
                owner = self.fighters.get(p.owner, a1)
                c = owner.model.accent
                pos = (_px_x(p.x), getattr(p, "height", 50.0) * V_SCALE + 0.15, 0.0)
                bx.append((pos, (0.22, 0.12, 0.12), c, (0.2, 0.0, 4.0, 0.0), (self.time * 900) % 360))
            n = self._box_batch(bx)
            self._write(self.p_char, "u_bones", self._identity_bones)
            self.vao_boxes.render(vertices=n)
        # additive layer: ghosts, trails, glow panels, particles
        ctx.enable(mgl.BLEND)
        ctx.blend_func = mgl.ONE, mgl.ONE
        ctx.depth_mask = False
        any_ghost = any(self.ghosts[i] for i in (1, 2))
        if any_ghost:
            self._write(self.p_ghost, "u_viewproj", vp_bytes)
            self._set(self.p_ghost, "u_cam_pos", tuple(float(c) for c in self.camera.eye))
            for idx, a in ((1, a1), (2, a2)):
                for bones, life in self.ghosts[idx]:
                    self._set(self.p_ghost, "u_ghost_col", tuple(a.model.trail))
                    self._set(self.p_ghost, "u_ghost_alpha", float(life) * 0.5)
                    self._write(self.p_ghost, "u_bones", bones)
                    self.char_vaos[a.model.name][1].render()
        ribbons = []
        for idx, a in ((1, a1), (2, a2)):
            r = self.trails[idx].build(a.model.trail)
            if r is not None:
                ribbons.append(r)
        ribbons.extend(glow)
        if ribbons:
            data = np.concatenate(ribbons).astype("f4")
            if data.nbytes > self.vbo_ribbon.size:
                self.vbo_ribbon.orphan(data.nbytes * 2)
            self.vbo_ribbon.write(data.tobytes())
            self._write(self.p_ribbon, "u_viewproj", vp_bytes)
            self.vao_ribbon.render(vertices=len(data))
        add, alpha = self.particles.build()
        self._write(self.p_part, "u_view", gl_bytes(self.camera.view))
        self._write(self.p_part, "u_proj", gl_bytes(self.camera.proj))
        if len(add):
            self.vbo_inst.write(np.ascontiguousarray(add).tobytes())
            self.vao_part.render(vertices=6, instances=len(add))
        if len(alpha):
            ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
            self.vbo_inst.write(np.ascontiguousarray(alpha).tobytes())
            self.vao_part.render(vertices=6, instances=len(alpha))
        ctx.depth_mask = True
        ctx.disable(mgl.BLEND | mgl.DEPTH_TEST)

        # ---------------- post ----------------
        ctx.copy_framebuffer(self.fbo_scene, self.fbo_msaa)
        bw, bh = self.bloom_size
        ctx.viewport = (0, 0, bw, bh)
        self.fbo_bloom_a.use()
        self.scene_tex.use(location=2)
        self._set(self.p_bright, "u_tex", 2)
        self._set(self.p_bright, "u_texel", (1.0 / self.width, 1.0 / self.height))
        self.vao_bright.render(mgl.TRIANGLE_STRIP)
        for _ in range(2):
            self.fbo_bloom_b.use()
            self.bloom_a.use(location=3)
            self._set(self.p_blur, "u_tex", 3)
            self._set(self.p_blur, "u_dir", (1.5 / bw, 0.0))
            self.vao_blur.render(mgl.TRIANGLE_STRIP)
            self.fbo_bloom_a.use()
            self.bloom_b.use(location=3)
            self._set(self.p_blur, "u_dir", (0.0, 1.5 / bh))
            self.vao_blur.render(mgl.TRIANGLE_STRIP)
        self.fbo_out.use()
        ctx.viewport = (0, 0, self.width, self.height)
        self.scene_tex.use(location=2)
        self.bloom_a.use(location=3)
        self._set(self.p_comp, "u_scene", 2)
        self._set(self.p_comp, "u_bloom", 3)
        self._set(self.p_comp, "u_bloom_amt", 0.9)
        self._set(self.p_comp, "u_grade", sp.grade)
        self._set(self.p_comp, "u_grade_amt", 1.0)
        self._set(self.p_comp, "u_exposure", sp.exposure * 0.9)
        self._set(self.p_comp, "u_vignette", 0.9)
        self._set(self.p_comp, "u_time", self.time)
        self._set(self.p_comp, "u_flash", float(min(0.6, self.screen_flash)))
        self.screen_flash = max(0.0, self.screen_flash - dt * 3.0)
        sc = (0.5, 0.5)
        if super_focus is not None:
            s = self.camera.project(super_focus, self.width, self.height)
            if s is not None:
                sc = (s[0] / self.width, s[1] / self.height)
        self._set(self.p_comp, "u_streak_center", sc)
        self._set(self.p_comp, "u_streak", float(self.streak))
        self.vao_comp.render(mgl.TRIANGLE_STRIP)
        self.fbo_out.read_into(self._readbuf, components=3, alignment=1)
        surf = pygame.image.frombuffer(self._readbuf, (self.width, self.height), "RGB")
        self.surface = surf
        self.stats_ms.append((time.perf_counter() - t0) * 1000.0)
        if len(self.stats_ms) > 240:
            self.stats_ms = self.stats_ms[-120:]
        return surf

    def _bones_bytes(self, a) -> bytes:
        n = a.gpu.shape[0]
        sc = self._bone_scratch
        sc[:n] = a.gpu
        sc[n:] = np.identity(4, dtype="f4")
        return sc.tobytes()

    def _ambient(self, dt):
        spec = AMBIENT.get(self.spec.ambient)
        if spec is None:
            return
        rng = self.particles.rng
        expected = spec["rate"] * dt * 10.0
        k = int(expected) + (1 if rng.random() < expected - int(expected) else 0)
        if k <= 0:
            return
        cx = self.camera.cx
        p = np.zeros((k, 3), dtype="f4")
        p[:, 0] = cx + rng.uniform(-7.0, 7.0, k)
        top = spec["vel"][1] < 0
        p[:, 1] = rng.uniform(3.0, 4.5, k) if top else rng.uniform(0.0, 2.5, k)
        p[:, 2] = rng.uniform(-4.0, 2.0, k)
        v = np.tile(np.asarray(spec["vel"], dtype="f4"), (k, 1))
        v += rng.normal(0, 0.15, (k, 3)).astype("f4")
        c = spec["col"]
        g = spec["glow"]
        life = 4.0 if top else 3.0
        if spec["kind"] == 1:
            life = 0.6
        self.particles.emit(p, v, (c[0] * g, c[1] * g, c[2] * g, 0.8), rng.uniform(*spec["size"], k), life,
                            kind=spec["kind"], fade_in=0.5 if spec["kind"] == 0 else 0.0)

    def mean_ms(self) -> float:
        if not self.stats_ms:
            return 0.0
        return float(sum(self.stats_ms[-60:]) / len(self.stats_ms[-60:]))

    def release(self):
        try:
            self.ctx.release()
        except Exception:
            pass
