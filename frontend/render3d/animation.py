"""Animation system: eased keyframe clips driven by engine frame data, crossfades,
and procedural layers (breathing, walk cycle with foot planting, landing squash,
hit recoil springs, knockdown/get-up, cloth chains).

The engine is the source of truth: attack clips are sampled at a time computed
from ``attack_phase`` / ``attack_frames_left`` and the move's real startup /
active / recovery numbers, so the strike pose is reached exactly on the first
active frame.
"""

import math
import random

import numpy as np

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.moves import get_move
from frontend.render3d import clips as C
from frontend.render3d.characters import get_model
from frontend.render3d.mathutil import PX_TO_M, rot_x, rot_y, rot_z, translate
from frontend.render3d.skeleton import (
    BONE_INDEX,
    FOOT_L,
    FOOT_R,
    GLOW,
    IKW_L,
    IKW_R,
    NUM_BONES,
    PELVIS_POS,
    POSE_SIZE,
    ROOT_POS,
    SMEAR,
    SMEAR_LIMB,
    Skeleton,
)

V_SCALE = 0.016          # engine vertical pixels -> metres (jump apex ~1.8 m)
JUMP_DURATION_FALLBACK = 40
JUMP_HEIGHT_FALLBACK = 110.0

# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------


def _ease(name: str, u: float) -> float:
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    if name == "lin":
        return u
    if name == "in":
        return u * u
    if name == "in3":
        return u * u * u
    if name == "out":
        return 1.0 - (1.0 - u) * (1.0 - u)
    if name == "io":
        return u * u * (3.0 - 2.0 * u)
    if name == "snap":       # fast whip into a hard stop on contact
        return 1.0 - (1.0 - u) ** 2.2
    if name == "back":       # overshoot then settle
        c1 = 1.70158 * 0.8
        c3 = c1 + 1.0
        return 1.0 + c3 * (u - 1.0) ** 3 + c1 * (u - 1.0) ** 2
    return u


EASINGS = ("lin", "in", "in3", "out", "io", "snap", "back")

# ---------------------------------------------------------------------------
# Pose dict -> vector
# ---------------------------------------------------------------------------
_KEY_BONE = {
    "root": "root", "pelvis": "pelvis", "spine": "spine", "chest": "chest", "neck": "neck", "head": "head",
    "sh_l": "shoulder_l", "ua_l": "upperarm_l", "fa_l": "forearm_l", "hd_l": "hand_l",
    "sh_r": "shoulder_r", "ua_r": "upperarm_r", "fa_r": "forearm_r", "hd_r": "hand_r",
    "th_l": "thigh_l", "sn_l": "shin_l", "ft_l": "foot_l",
    "th_r": "thigh_r", "sn_r": "shin_r", "ft_r": "foot_r",
}


def apply_overrides(base: np.ndarray, d: dict) -> np.ndarray:
    v = base.copy()
    for k, val in d.items():
        if k in _KEY_BONE:
            i = BONE_INDEX[_KEY_BONE[k]] * 3
            v[i:i + 3] = val
        elif k == "pp":
            v[PELVIS_POS:PELVIS_POS + 3] = val
        elif k == "rp":
            v[ROOT_POS:ROOT_POS + 3] = val
        elif k == "fl":
            v[FOOT_L:FOOT_L + 4] = val
        elif k == "fr":
            v[FOOT_R:FOOT_R + 4] = val
        elif k == "ikl":
            v[IKW_L] = val
        elif k == "ikr":
            v[IKW_R] = val
        elif k == "smear":
            v[SMEAR] = val
        elif k == "limb":
            v[SMEAR_LIMB] = val
        elif k == "glow":
            v[GLOW] = val
        else:
            raise KeyError(f"unknown pose channel {k!r}")
    return v


_STANCE_CACHE: dict = {}


def stance_vector(character: str) -> np.ndarray:
    v = _STANCE_CACHE.get(character)
    if v is None:
        v = apply_overrides(np.zeros(POSE_SIZE), C.BASE_GUARD)
        v = apply_overrides(v, C.STANCES.get(character, {}))
        _STANCE_CACHE[character] = v
    return v


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------
class Clip:
    """A resolved clip: keys with full pose vectors, sampled against frame data."""

    def __init__(self, raw: dict, base: np.ndarray):
        self.limb = int(raw.get("limb", 0))
        self.ghost = bool(raw.get("ghost", False))
        self.keys = []
        for phase, frac, pose, ease in raw["keys"]:
            self.keys.append((phase, float(frac), apply_overrides(base, pose), ease))

    @staticmethod
    def key_time(phase: str, frac: float, s: int, a: int, r: int) -> float:
        if phase == "s":
            return frac * s
        if phase == "a":
            return s + frac * a
        if phase == "r":
            return s + a + frac * r
        return frac

    def times(self, s: int, a: int, r: int):
        return [self.key_time(k[0], k[1], s, a, r) for k in self.keys]

    def sample(self, t: float, s: int = 0, a: int = 0, r: int = 0) -> np.ndarray:
        keys = self.keys
        times = self.times(s, a, r)
        if t <= times[0]:
            return keys[0][2]
        for i in range(1, len(keys)):
            t1 = times[i]
            if t <= t1:
                t0 = times[i - 1]
                if t1 - t0 < 1e-6:
                    return keys[i][2]
                u = _ease(keys[i][3], (t - t0) / (t1 - t0))
                p0, p1 = keys[i - 1][2], keys[i][2]
                out = p0 + (p1 - p0) * u
                out[SMEAR_LIMB] = p1[SMEAR_LIMB] if u > 0.5 else p0[SMEAR_LIMB]
                return out
        return keys[-1][2]

    def full_extension_time(self, s: int, a: int, r: int) -> float:
        """Time of the first key reached with a 'snap' (the strike)."""
        times = self.times(s, a, r)
        for k, t in zip(self.keys, times):
            if k[3] == "snap":
                return t
        return float(s)


_CLIP_CACHE: dict = {}


def get_clip(character: str, action: Action):
    key = (character, action)
    if key in _CLIP_CACHE:
        return _CLIP_CACHE[key]
    raw = C.clip_def(character, action)
    clip = Clip(raw, stance_vector(character)) if raw is not None else None
    _CLIP_CACHE[key] = clip
    return clip


def move_time(fighter) -> tuple:
    """(t, s, a, r) clip time in frames for the fighter's current attack, or None."""
    phase = getattr(fighter, "attack_phase", "none")
    action = getattr(fighter, "current_action", Action.IDLE)
    if phase not in ("startup", "active", "recovery"):
        return None
    move = get_move(getattr(fighter, "character_name", "Golden"), action)
    if move is None:
        return None
    s, a, r = int(move.startup), int(move.active), int(move.recovery)
    left = int(getattr(fighter, "attack_frames_left", 0))
    if phase == "startup":
        t = s - left
    elif phase == "active":
        t = s + (a - left)
    else:
        rl = max(r, left)  # parry stagger etc. can lengthen recovery
        t = s + a + (rl - left) * (r / max(1, rl))
    return float(max(0.0, t)), s, a, r


def fighter_height_px(f) -> float:
    y = getattr(type(f), "y", None)
    if isinstance(y, property):
        try:
            return float(f.y)
        except Exception:
            pass
    if not getattr(f, "in_air", False):
        return 0.0
    try:
        from backend.engine import constants as K
        dur = getattr(K, "JUMP_DURATION", JUMP_DURATION_FALLBACK)
        h = getattr(K, "JUMP_HEIGHT", JUMP_HEIGHT_FALLBACK)
    except Exception:
        dur, h = JUMP_DURATION_FALLBACK, JUMP_HEIGHT_FALLBACK
    p = min(max(getattr(f, "jump_frame", 0) / float(dur), 0.0), 1.0)
    return h * 4.0 * p * (1.0 - p)


def jump_progress(f) -> float:
    try:
        from backend.engine import constants as K
        dur = getattr(K, "JUMP_DURATION", JUMP_DURATION_FALLBACK)
    except Exception:
        dur = JUMP_DURATION_FALLBACK
    return min(max(getattr(f, "jump_frame", 0) / float(dur), 0.0), 1.0)


# ---------------------------------------------------------------------------
# Cloth chains (verlet)
# ---------------------------------------------------------------------------
class ChainSim:
    def __init__(self, spec):
        self.spec = spec
        self.n = spec.segments + 1
        self.p = None
        self.prev = None

    def reset(self, anchor, rest_dir):
        d = rest_dir / (np.linalg.norm(rest_dir) or 1.0)
        self.p = np.array([anchor + d * self.spec.seg_len * i for i in range(self.n)], dtype="f8")
        self.prev = self.p.copy()

    def step(self, anchor, rest_dir, dt):
        spec = self.spec
        if self.p is None:
            self.reset(anchor, rest_dir)
        dt = min(max(dt, 1e-3), 1 / 30)
        p, prev = self.p, self.prev
        d = rest_dir / (np.linalg.norm(rest_dir) or 1.0)
        vel = (p - prev) * (1.0 - spec.drag)
        prev[:] = p
        acc = np.array((0.0, -spec.gravity, 0.0))
        p[1:] += vel[1:] + acc * dt * dt
        # pull towards rest shape (keeps scarves flowing behind)
        for i in range(1, self.n):
            target = anchor + d * spec.seg_len * i
            p[i] += (target - p[i]) * spec.stiffness * 0.25
        p[0] = anchor
        L = spec.seg_len
        for _ in range(3):
            for i in range(self.n - 1):
                a, b = p[i], p[i + 1]
                delta = b - a
                dist = math.sqrt(delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2) or 1e-6
                diff = (dist - L) / dist
                if i == 0:
                    p[i + 1] = b - delta * diff
                else:
                    p[i] = a + delta * diff * 0.5
                    p[i + 1] = b - delta * diff * 0.5
            np.maximum(p[:, 1], 0.015, out=p[:, 1])

    def matrices(self):
        out = []
        p = self.p
        zref = np.array((0.0, 0.0, 1.0))
        for i in range(self.n - 1):
            seg = p[i + 1] - p[i]
            ln = np.linalg.norm(seg) or 1e-6
            y = -seg / ln
            z = zref - y * float(np.dot(zref, y))
            nz = np.linalg.norm(z)
            z = z / nz if nz > 1e-5 else np.array((1.0, 0.0, 0.0))
            x = np.cross(y, z)
            m = np.identity(4)
            m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, z, p[i]
            out.append(m)
        return out


# ---------------------------------------------------------------------------
# Per-fighter animator
# ---------------------------------------------------------------------------
class FighterAnimator:
    """Turns successive engine FighterStates into a smooth 3D pose."""

    PIVOT = 0.92

    def __init__(self, character: str, player: int):
        self.character = character if character in C.STANCES else "Golden"
        self.player = player
        self.model = get_model(self.character)
        self.skel = Skeleton(self.model.props)
        self.stance = stance_vector(self.character)
        self.crouch = apply_overrides(self.stance, C.CROUCH)
        self.block_high = apply_overrides(self.stance, C.BLOCK_HIGH)
        self.block_low = apply_overrides(self.stance, C.BLOCK_LOW)
        self.poses = {name: apply_overrides(self.stance, getattr(C, name)) for name in (
            "HIT_HIGH", "HIT_MID", "HIT_LOW", "HIT_AIR", "GUARD_BREAK", "PARRY", "BURST", "THROWN", "LYING",
            "FALLING", "GETUP", "LAND", "KNEEL", "JUMP_UP", "JUMP_TUCK", "JUMP_FALL", "DASH_RUN")}
        self.victory = apply_overrides(self.stance, C.VICTORY.get(self.character, {}))
        self.super_pose = apply_overrides(self.stance, C.SUPER_POSE.get(self.character, {}))
        self.chains = [ChainSim(spec) for spec in self.model.chains]
        self.reset()

    # ------------------------------------------------------------------
    def reset(self):
        self.clock = 0
        self.f = None
        self.opp = None
        self.prev_x = None
        self.x_render = 0.0
        self.facing = 1.0
        self.face_vis = 1.0
        self.layer = None
        self.fade_from = None
        self.fade_start = 0.0
        self.fade_len = 1.0
        self.last_pose = self.stance.copy()
        self.walk_phase = 0.0
        self.walk_w = 0.0
        self.crouch_w = 0.0
        self.block_w = 0.0
        self.block_low_w = 0.0
        self.dash_w = 0.0
        self.land_timer = 0
        self.prev_in_air = False
        self.reaction = None       # (start_clock, duration, pose_key, strength)
        self.kd_start = None
        self.kd_total = 30
        self.ko_start = None
        self.parry_start = None
        self.burst_start = None
        self.flip_start = None
        self.prev_jump_frame = 0
        self.spring = 0.0
        self.spring_v = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.round_over_clock = None
        self.round_result = "none"
        self.super_freeze = False
        self.glow_extra = 0.0
        self.tips = {1: np.zeros(3), 2: np.zeros(3), 3: np.zeros(3), 4: np.zeros(3)}
        self.joints = {1: np.zeros(3), 2: np.zeros(3), 3: np.zeros(3), 4: np.zeros(3)}
        self.chest_pos = np.zeros(3)
        self.head_pos = np.zeros(3)
        self.world = np.tile(np.identity(4), (self.model.num_gpu_bones, 1, 1))
        self.gpu = np.zeros((self.model.num_gpu_bones, 4, 4), dtype="f4")
        for ch in self.chains:
            ch.p = None

    # ------------------------------------------------------------------
    def on_hit(self, strength: float, level: str = "mid", blocked: bool = False, launch: bool = False):
        """Called by the renderer when this fighter is struck (or blocks)."""
        if blocked:
            self.spring_v += 0.12 + 0.20 * strength
            self.shake = 0.6
            return
        self.spring_v += 0.25 + 0.55 * strength
        key = {"high": "HIT_HIGH", "low": "HIT_LOW"}.get(level, "HIT_MID")
        stun = int(getattr(self.f, "hitstun", 12) or 12) if self.f is not None else 12
        self.reaction = (self.clock, max(8, stun), key, strength)
        self.flash = 1.0
        self.shake = 1.0

    def on_parry(self):
        self.parry_start = self.clock

    def on_burst(self):
        self.burst_start = self.clock

    # ------------------------------------------------------------------
    def update(self, f, opp, state):
        """Advance one simulation step with the new engine state."""
        self.clock += 1
        prev = self.f
        self.f = f
        self.opp = opp
        x = f.x
        if self.prev_x is None:
            self.prev_x = x
        dx = x - self.prev_x
        self.prev_x = x

        # facing (with hysteresis while overlapping)
        if opp is not None and abs(opp.x - x) > 1.0:
            self.facing = 1.0 if opp.x > x else -1.0

        # smoothed locomotion weights
        busy_attack = getattr(f, "attack_phase", "none") != "none"
        la = getattr(f, "last_action", Action.IDLE)
        stunned = (f.hitstun > 0 or f.blockstun > 0 or f.is_knocked_down or f.is_thrown)
        want_crouch = 1.0 if (getattr(f, "is_crouching", False) and not f.in_air) else 0.0
        want_block = 1.0 if (la == Action.BLOCK or (f.blockstun > 0 and not want_crouch)) else 0.0
        want_block_low = 1.0 if (la == Action.BLOCK_LOW or (f.blockstun > 0 and want_crouch)) else 0.0
        self.crouch_w += (want_crouch - self.crouch_w) * 0.35
        self.block_w += (want_block - self.block_w) * 0.45
        self.block_low_w += (want_block_low - self.block_low_w) * 0.45
        dash_frames = getattr(f, "dash_frames_left", 0)
        dashing = (dash_frames > 0 and not busy_attack) or (la == Action.DASH and abs(dx) > 4.5)
        self.dash_w += ((1.0 if dashing else 0.0) - self.dash_w) * 0.4
        fwd = dx * self.facing
        walking = (not f.in_air and not busy_attack and not stunned and abs(dx) > 0.3 and not dashing)
        self.walk_w += ((1.0 if walking else 0.0) - self.walk_w) * 0.3
        if not f.in_air:
            stride = C.WALK_STRIDE * (1.25 if self.character == "Shadow" else 1.0)
            if dashing:
                stride *= 1.6
            self.walk_phase += (fwd * PX_TO_M) / stride

        # landing squash
        if self.prev_in_air and not f.in_air and not f.is_knocked_down:
            self.land_timer = 8
        elif self.land_timer > 0:
            self.land_timer -= 1
        # Shadow double-jump flip
        jf = getattr(f, "jump_frame", 0)
        if f.in_air and self.prev_in_air and jf < self.prev_jump_frame - 3:
            self.flip_start = self.clock
        self.prev_jump_frame = jf
        self.prev_in_air = f.in_air

        # knockdown bookkeeping
        if f.is_knocked_down and not f.in_air:
            if self.kd_start is None:
                self.kd_start = self.clock
                self.kd_total = max(12, int(getattr(f, "knockdown_frames", 30)) + 1)
        elif not f.is_knocked_down:
            self.kd_start = None
        if f.health <= 0.0 and not f.in_air:
            if self.ko_start is None:
                self.ko_start = self.clock
        elif f.health > 0.0:
            self.ko_start = None

        if f.hitstun <= 0 and self.reaction is not None and self.clock - self.reaction[0] > self.reaction[1]:
            self.reaction = None

        # recoil spring (critically-ish damped)
        self.spring_v += -0.10 * self.spring - 0.30 * self.spring_v
        self.spring += self.spring_v
        self.flash = max(0.0, self.flash - 0.34)
        self.shake = max(0.0, self.shake - 0.12)

        self.super_freeze = state is not None and getattr(state, "super_freeze_frames", 0) > 0 and \
            getattr(state, "super_attacker", 0) == self.player
        if state is not None and getattr(state, "round_over", False):
            if self.round_over_clock is None:
                self.round_over_clock = self.clock
            self.round_result = getattr(state, "round_result", "none")
        else:
            self.round_over_clock = None
            self.round_result = "none"

    # ------------------------------------------------------------------
    def _fade_to(self, key, length, t):
        if key != self.layer:
            self.fade_from = self.last_pose.copy()
            self.fade_start = t
            self.fade_len = max(0.5, float(length))
            self.layer = key

    def _loco(self, t: float) -> np.ndarray:
        f = self.f
        v = self.stance.copy()
        if self.crouch_w > 0.01:
            v += (self.crouch - v) * self.crouch_w
        if self.block_w > 0.01:
            v += (self.block_high - v) * self.block_w
        if self.block_low_w > 0.01:
            v += (self.block_low - v) * self.block_low_w
        if self.dash_w > 0.01:
            v += (self.poses["DASH_RUN"] - v) * self.dash_w
        # walk / run cycle with planted feet
        w = max(self.walk_w, self.dash_w)
        if w > 0.01:
            ph = self.walk_phase
            s = 0.20 * (1.3 if self.dash_w > 0.5 else 1.0)
            lift = 0.09
            for slot, off in ((FOOT_L, 0.0), (FOOT_R, 0.5)):
                p = (ph + off) % 1.0
                if p < 0.5:
                    u = p / 0.5
                    fx, fy = s * (1.0 - 2.0 * u), 0.0
                else:
                    u = (p - 0.5) / 0.5
                    fx = -s + 2.0 * s * (u * u * (3 - 2 * u))
                    fy = math.sin(math.pi * u) * lift
                v[slot] += fx * w
                v[slot + 1] += fy * w
            v[PELVIS_POS + 1] += (math.cos(ph * 4.0 * math.pi) * 0.5 - 0.5) * 0.025 * w
            ci = BONE_INDEX["chest"] * 3
            v[ci + 2] -= 4.0 * w
            v[ci + 1] += math.sin(ph * 2.0 * math.pi) * 4.0 * w
            for side, sgn in (("l", 1.0), ("r", -1.0)):
                ui = BONE_INDEX["upperarm_" + side] * 3
                v[ui + 2] += math.sin(ph * 2.0 * math.pi) * 6.0 * sgn * w
        # idle breathing / bounce
        idle = max(0.0, 1.0 - w - self.block_w - self.block_low_w)
        if idle > 0.01:
            if self.character == "Crimson":
                b = abs(math.sin(t * 0.17)) * 0.035 - 0.02
                v[PELVIS_POS + 1] += b * idle
                v[FOOT_R + 1] += max(0.0, b) * 0.4 * idle
            elif self.character == "Steel":
                v[PELVIS_POS + 1] += math.sin(t * 0.05) * 0.012 * idle
            else:
                v[PELVIS_POS + 1] += math.sin(t * 0.08) * 0.012 * idle
            ci = BONE_INDEX["chest"] * 3
            v[ci + 2] += math.sin(t * 0.08 + 1.0) * 1.6 * idle
            for side in ("l", "r"):
                fi = BONE_INDEX["forearm_" + side] * 3
                v[fi + 2] += math.sin(t * 0.08 + (0.5 if side == "l" else 1.7)) * 3.0 * idle
        if self.land_timer > 0:
            k = (self.land_timer / 8.0) ** 1.5
            v += (self.poses["LAND"] - v) * k * 0.9
        return v

    def _jump(self, t: float) -> np.ndarray:
        f = self.f
        p = jump_progress(f)
        P = self.poses
        if p < 0.12:
            v = P["JUMP_UP"].copy()
        elif p < 0.30:
            u = _ease("io", (p - 0.12) / 0.18)
            v = P["JUMP_UP"] + (P["JUMP_TUCK"] - P["JUMP_UP"]) * u
        elif p < 0.70:
            v = P["JUMP_TUCK"].copy()
        else:
            u = _ease("io", (p - 0.70) / 0.25)
            v = P["JUMP_TUCK"] + (P["JUMP_FALL"] - P["JUMP_TUCK"]) * u
        if self.flip_start is not None:
            ft = (t - self.flip_start) / 18.0
            if 0.0 <= ft <= 1.0:
                v = v.copy()
                v[2] = -360.0 * _ease("io", ft)   # root z rotation: front flip
                v += (P["JUMP_TUCK"] - v) * 0.0
        return v

    def target_pose(self, t: float) -> tuple:
        """Return (layer_key, pose_vector, fade_frames) for the current state."""
        f = self.f
        P = self.poses
        # round end: victory / defeat
        if self.round_over_clock is not None and self.f.health > 0.0:
            won = (self.round_result == "p1" and self.player == 1) or (self.round_result == "p2" and self.player == 2)
            if t - self.round_over_clock > 25:
                if won:
                    v = self.victory.copy()
                    v[PELVIS_POS + 1] += math.sin(t * 0.07) * 0.01
                    return ("victory",), v, 14
                if self.round_result in ("p1", "p2"):
                    return ("defeat",), P["KNEEL"], 16
        # KO: fall and stay down
        if self.ko_start is not None:
            e = t - self.ko_start
            return ("ko",), self._fall_sequence(e, stay=True), 3
        if f.is_thrown:
            v = P["THROWN"].copy()
            v[2] += math.sin(t * 0.9) * 4.0
            return ("thrown",), v, 3
        if f.in_air and (f.hitstun > 0 or f.is_knocked_down):
            v = P["HIT_AIR"].copy()
            p = jump_progress(f)
            v[2] = 15.0 + 45.0 * p      # tumble backwards
            return ("juggle",), v, 3
        if f.is_knocked_down:
            e = t - (self.kd_start if self.kd_start is not None else t)
            remaining = float(getattr(f, "knockdown_frames", 0))
            return ("kd",), self._fall_sequence(e, stay=False, remaining=remaining), 3
        if getattr(f, "guard_break_stun", 0) > 0:
            v = P["GUARD_BREAK"].copy()
            ci = BONE_INDEX["chest"] * 3
            v[ci] += math.sin(t * 0.25) * 8.0
            v[PELVIS_POS] += math.sin(t * 0.25) * 0.03
            return ("guard_break",), v, 3
        if f.hitstun > 0 and self.reaction is not None:
            start, dur, key, strength = self.reaction
            e = t - start
            peak = P[key]
            amt = min(1.0, 0.65 + strength * 0.6)
            if e < 2.0:
                u = _ease("snap", e / 2.0)
            elif e < dur * 0.45:
                u = 1.0
            else:
                u = 1.0 - _ease("io", (e - dur * 0.45) / max(1.0, dur * 0.55))
            base = self.crouch if self.crouch_w > 0.5 and key != "HIT_HIGH" else self.stance
            v = base + (peak - base) * (u * amt)
            v[PELVIS_POS] -= 0.12 * strength * u
            return ("hit", start), v, 2
        if f.blockstun > 0:
            v = self._loco(t)
            return ("loco",), v, 4
        mt = move_time(f)
        if mt is not None:
            clip = get_clip(self.character, f.current_action)
            if clip is not None:
                tt, s, a, r = mt
                v = clip.sample(tt + self._frac, s, a, r)
                if self.super_freeze:
                    v = self.super_pose
                fade = min(3.0, max(1.0, s * 0.6))
                return ("move", f.current_action, self._move_serial(f)), v, fade
        if self.super_freeze:
            return ("super",), self.super_pose, 3
        if self.parry_start is not None and t - self.parry_start < 16:
            e = t - self.parry_start
            u = _ease("snap", e / 2.5) if e < 2.5 else 1.0 - _ease("io", (e - 8) / 8.0) if e > 8 else 1.0
            v = self.stance + (P["PARRY"] - self.stance) * u
            return ("parry", self.parry_start), v, 1
        if self.burst_start is not None and t - self.burst_start < 24:
            clip = get_clip(self.character, Action.BURST)
            return ("burst", self.burst_start), clip.sample(t - self.burst_start), 1
        la = getattr(f, "last_action", Action.IDLE)
        if la in (Action.BUILD, Action.PICKUP, Action.SHIELD_FRONT, Action.SHIELD_BACK):
            if getattr(f, "building_frames", 0) > 0 or getattr(f, "shield_startup_frames", 0) > 0:
                clip = get_clip(self.character, la)
                return ("act", la), clip.sample(6.0), 4
        if f.in_air:
            return ("jump",), self._jump(t), 3
        return ("loco",), self._loco(t), 6

    def _move_serial(self, f):
        # a new move instance starts whenever the phase restarts from startup
        return id(f.current_action), getattr(self, "_serial", 0)

    def _fall_sequence(self, e: float, stay: bool, remaining: float = 99.0) -> np.ndarray:
        P = self.poses
        if e < 7.0:
            u = _ease("in", e / 7.0)
            v = P["FALLING"] + (P["LYING"] - P["FALLING"]) * u
        else:
            v = P["LYING"].copy()
            b = e - 7.0
            if b < 6.0:
                v[ROOT_POS + 1] += math.sin(math.pi * b / 6.0) * 0.09
        if not stay and remaining < 13.0:
            g = 1.0 - max(0.0, remaining - 0.0) / 13.0
            if g < 0.55:
                u = _ease("io", g / 0.55)
                v = v + (P["GETUP"] - v) * u
            else:
                u = _ease("out", (g - 0.55) / 0.45)
                v = P["GETUP"] + (self.stance - P["GETUP"]) * u
        return v

    # ------------------------------------------------------------------
    def pose(self, frac: float = 0.0) -> np.ndarray:
        self._frac = frac
        t = self.clock + frac
        key, target, fade = self.target_pose(t)
        self._fade_to(key, fade, t)
        if self.fade_from is not None:
            u = (t - self.fade_start) / self.fade_len
            if u < 1.0:
                w = _ease("io", u)
                target = self.fade_from + (target - self.fade_from) * w
            else:
                self.fade_from = None
        v = target.copy()
        # additive recoil spring
        if abs(self.spring) > 1e-4:
            ci = BONE_INDEX["chest"] * 3
            hi = BONE_INDEX["head"] * 3
            v[ci + 2] += self.spring * 22.0
            v[hi + 2] += self.spring * 26.0
            v[PELVIS_POS] -= self.spring * 0.10
        # head looks at the opponent's head a little
        self.last_pose = v
        return v

    _frac = 0.0
    _serial = 0

    # ------------------------------------------------------------------
    def compute(self, frac: float, x_px: float, dt: float, z: float = 0.0):
        """Pose -> world matrices (fills self.world / self.gpu)."""
        f = self.f
        v = self.pose(frac)
        # turning around: squash through zero over a few frames
        self.face_vis += (self.facing - self.face_vis) * 0.55
        sx = self.face_vis if abs(self.face_vis) > 0.15 else math.copysign(0.15, self.face_vis or 1.0)
        y_m = fighter_height_px(f) * V_SCALE if f is not None else 0.0
        xw = (x_px - ARENA_WIDTH / 2.0) * PX_TO_M
        shake = 0.0
        if self.shake > 0:
            shake = (random.random() - 0.5) * 0.04 * self.shake
        root = translate(xw + shake, y_m, z)
        root[0, :3] *= 1.0
        root = root @ np.diag((sx, 1.0, 1.0, 1.0))
        rp = v[ROOT_POS:ROOT_POS + 3]
        root = root @ translate(rp[0], rp[1], rp[2])
        rx, ry, rz = v[0], v[1], v[2]
        if abs(rx) + abs(ry) + abs(rz) > 1e-4:
            c = self.PIVOT
            root = root @ translate(0, c, 0) @ rot_y(ry) @ rot_z(rz) @ rot_x(rx) @ translate(0, -c, 0)
        M = self.skel.solve(v, floor_clamp=y_m < 0.02, lift=0.0)
        W = self.world
        W[:NUM_BONES] = root @ M
        self.glow = float(v[GLOW])
        self.limb = int(round(v[SMEAR_LIMB]))
        # strike points
        p = self.model.props
        hand_tip = np.array((0.015, -p.fist_r * 1.0, 0.0, 1.0))
        foot_tip = np.array((0.16, -p.ankle_h + 0.03, 0.0, 1.0))
        self.tips[1] = (W[BONE_INDEX["hand_l"]] @ hand_tip)[:3]
        self.tips[2] = (W[BONE_INDEX["hand_r"]] @ hand_tip)[:3]
        self.tips[3] = (W[BONE_INDEX["foot_l"]] @ foot_tip)[:3]
        self.tips[4] = (W[BONE_INDEX["foot_r"]] @ foot_tip)[:3]
        self.joints[1] = W[BONE_INDEX["forearm_l"]][:3, 3].copy()
        self.joints[2] = W[BONE_INDEX["forearm_r"]][:3, 3].copy()
        self.joints[3] = W[BONE_INDEX["shin_l"]][:3, 3].copy()
        self.joints[4] = W[BONE_INDEX["shin_r"]][:3, 3].copy()
        self.chest_pos = W[BONE_INDEX["chest"]][:3, 3] + W[BONE_INDEX["chest"]][:3, 1] * 0.12
        self.head_pos = W[BONE_INDEX["head"]][:3, 3] + W[BONE_INDEX["head"]][:3, 1] * 0.1
        self.root_pos = np.array((xw, y_m, z))
        # cloth chains
        idx = NUM_BONES
        face = 1.0 if self.face_vis >= 0 else -1.0
        for ch in self.chains:
            spec = ch.spec
            ab = W[BONE_INDEX[spec.anchor_bone]]
            anchor = (ab @ np.array((spec.anchor[0], spec.anchor[1], spec.anchor[2], 1.0)))[:3]
            rd = np.array((spec.rest_dir[0] * face, spec.rest_dir[1], spec.rest_dir[2]))
            ch.step(anchor, rd, dt)
            for m in ch.matrices():
                W[idx] = m
                idx += 1
        np.copyto(self.gpu, np.transpose(W, (0, 2, 1)))
        return W
