"""Code-built 3D fighter models.

Each fighter is a list of rigid *parts*: a procedural mesh placed in a bone's
local frame with a colour and material.  All parts of a fighter are baked into
one vertex buffer (position, normal, colour, material, bone index) so a whole
fighter draws in a single call with the bone matrices as a uniform array.

Bone-local frames (rest pose): limbs hang along -Y, the spine/neck/head point
along +Y, +X is the fighter's forward and +Z is the fighter's right side
(towards the camera).
"""

from dataclasses import dataclass, field
from functools import lru_cache
import math

import numpy as np

from frontend.render3d import meshes
from frontend.render3d.mathutil import compose
from frontend.render3d.skeleton import BONE_INDEX, NUM_BONES, Proportions

# material presets: (roughness, metalness, emissive, accent)
CLOTH = (0.85, 0.0, 0.0, 0.0)
SILK = (0.55, 0.0, 0.0, 0.0)
SKIN = (0.6, 0.0, 0.0, 0.0)
LEATHER = (0.6, 0.0, 0.0, 0.0)
HAIR = (0.5, 0.0, 0.0, 0.0)
GOLD = (0.32, 0.9, 0.0, 0.6)
STEEL = (0.32, 0.92, 0.0, 0.0)
DARK_METAL = (0.45, 0.8, 0.0, 0.0)
GLOW = (0.5, 0.0, 2.6, 1.5)
EYE = (0.3, 0.0, 0.0, 0.0)


def srgb(c):
    return tuple((v / 255.0) ** 2.2 for v in c)


@dataclass
class Part:
    bone: str
    mesh: tuple          # (positions, normals)
    matrix: np.ndarray   # local placement inside the bone frame
    colour: tuple        # linear RGB
    material: tuple      # (rough, metal, emissive, accent)
    chain: int = -1      # >=0: part belongs to cloth chain bone (chain id, segment)
    seg: int = 0


@dataclass
class ChainSpec:
    """A verlet cloth/hair chain hanging from a bone (scarf, sash, headband tails)."""

    anchor_bone: str
    anchor: tuple            # offset in the anchor bone's frame
    segments: int
    seg_len: float
    width: float
    thickness: float
    colour: tuple            # sRGB
    tip_colour: tuple        # sRGB
    material: tuple = CLOTH
    gravity: float = 9.8
    drag: float = 0.10
    stiffness: float = 0.35  # pull back towards the rest direction
    rest_dir: tuple = (-0.6, -1.0, 0.0)  # model space (fighter faces +X)


@dataclass
class FighterModel:
    name: str
    props: Proportions
    parts: list = field(default_factory=list)
    chains: list = field(default_factory=list)
    accent: tuple = (1.0, 0.8, 0.3)    # linear rgb used for VFX / glow
    trail: tuple = (1.0, 0.8, 0.4)
    spark: tuple = (1.0, 0.7, 0.3)

    # ------------------------------------------------------------------
    def add(self, bone, mesh, t=(0, 0, 0), r=(0, 0, 0), s=(1, 1, 1), col=(200, 200, 200), mat=CLOTH):
        self.parts.append(Part(bone, mesh, compose(t, r, s), srgb(col), mat))

    def bake(self) -> np.ndarray:
        """Interleaved float32 vertex data: pos3 nrm3 col3 mat4 bone1 (14 floats)."""
        chunks = []
        for p in self.parts:
            pos, nrm = meshes.transform(p.mesh, p.matrix)
            n = len(pos)
            if p.chain >= 0:
                bone_id = NUM_BONES + self._chain_offset(p.chain) + p.seg
            else:
                bone_id = BONE_INDEX[p.bone]
            data = np.empty((n, 14), dtype="f4")
            data[:, 0:3] = pos
            data[:, 3:6] = nrm
            data[:, 6:9] = p.colour
            data[:, 9:13] = p.material
            data[:, 13] = bone_id
            chunks.append(data)
        return np.concatenate(chunks, axis=0)

    def _chain_offset(self, chain_id: int) -> int:
        return sum(c.segments for c in self.chains[:chain_id])

    @property
    def num_gpu_bones(self) -> int:
        return NUM_BONES + sum(c.segments for c in self.chains)

    def add_chain(self, spec: ChainSpec):
        cid = len(self.chains)
        self.chains.append(spec)
        for i in range(spec.segments):
            t = i / max(1, spec.segments - 1)
            col = tuple(a + (b - a) * t for a, b in zip(spec.colour, spec.tip_colour))
            w = spec.width * (1.0 - 0.35 * t)
            mesh = meshes.rounded_box(spec.thickness, spec.seg_len * 1.15, w, min(spec.thickness, w) * 0.45, 2)
            self.parts.append(Part("root", mesh, compose((0, -spec.seg_len * 0.5, 0)), srgb(col), spec.material,
                                   chain=cid, seg=i))


# ---------------------------------------------------------------------------
# Shared body-part helpers
# ---------------------------------------------------------------------------

def _limb(m: FighterModel, bone, length, r_top, r_bot, col, mat=CLOTH, sx=1.0, sz=1.0, t0=0.0):
    m.add(bone, meshes.capsule(r_top, r_bot, length - t0), t=(0, -t0, 0), s=(sx, 1, sz), col=col, mat=mat)


def _foot(m: FighterModel, side, p: Proportions, col, mat=LEATHER, length=0.25, width=0.10, height=0.085):
    m.add("foot_" + side, meshes.rounded_box(length, height, width, 0.035),
          t=(0.055, -p.ankle_h + height / 2 - 0.005, 0), col=col, mat=mat)


def _fist(m: FighterModel, side, p: Proportions, col, mat=SKIN, size=1.0, wrap_col=None):
    s = p.fist_r * size
    m.add("hand_" + side, meshes.rounded_box(s * 1.9, s * 2.0, s * 1.75, s * 0.55),
          t=(0.012, -s * 0.95, 0), col=col, mat=mat)
    # thumb
    zs = 1 if side == "r" else -1
    m.add("hand_" + side, meshes.sphere(s * 0.42, 8, 6), t=(s * 0.75, -s * 0.55, -zs * s * 0.65), col=col, mat=mat)
    if wrap_col is not None:
        m.add("hand_" + side, meshes.cylinder(s * 1.05, s * 1.05, s * 0.7, 12),
              t=(0.012, -s * 0.15, 0), s=(1.0, 1, 0.92), col=wrap_col, mat=CLOTH)


def _head_base(m: FighterModel, p: Proportions, skin, face_fwd=True, eyes=True, eye_col=(30, 22, 18)):
    r = p.head_r
    m.add("head", meshes.sphere(r, 20, 14), t=(-r * 0.05, r * 1.0, 0), s=(1.0, 1.05, 0.88), col=skin, mat=SKIN)
    # face plane / cheeks + jaw / chin
    m.add("head", meshes.sphere(r * 0.8, 16, 10), t=(r * 0.25, r * 0.78, 0), s=(0.9, 1.0, 0.95), col=skin, mat=SKIN)
    m.add("head", meshes.sphere(r * 0.5, 14, 10), t=(r * 0.45, r * 0.38, 0), s=(1.0, 0.8, 1.1), col=skin, mat=SKIN)
    # nose
    m.add("head", meshes.sphere(r * 0.17, 8, 6), t=(r * 1.0, r * 0.82, 0), s=(1.2, 1.0, 0.8), col=skin, mat=SKIN)
    # ears
    for zs in (-1, 1):
        m.add("head", meshes.sphere(r * 0.2, 8, 6), t=(-r * 0.05, r * 0.9, zs * r * 0.88), s=(1.0, 1.3, 0.5),
              col=skin, mat=SKIN)
    if eyes:
        for zs in (-1, 1):
            m.add("head", meshes.sphere(r * 0.13, 8, 6), t=(r * 0.9, r * 1.02, zs * r * 0.36), s=(0.5, 0.9, 1.1),
                  col=eye_col, mat=EYE)
        # brows
        for zs in (-1, 1):
            m.add("head", meshes.rounded_box(r * 0.18, r * 0.07, r * 0.42, r * 0.03),
                  t=(r * 0.92, r * 1.2, zs * r * 0.36), r=(zs * 10, 0, -10), col=(40, 30, 25), mat=HAIR)


def _torso(m: FighterModel, p: Proportions, col_chest, col_belly, col_hips, chest_scale=(1, 1, 1), mat=CLOTH):
    w, d = p.torso_w, p.torso_d
    # hips (wedge-ish block, narrower than the shoulders)
    m.add("pelvis", meshes.lathe_smooth(((0.0, 0.07), (0.15, 0.065), (0.19, 0.0), (0.18, -0.07), (0.12, -0.12),
                                         (0.0, -0.13)), 16),
          t=(0, 0.0, 0), s=(d / 0.40, 1.0, w * 0.9 / 0.38), col=col_hips, mat=mat)
    # abdomen: tapered waist joining hips to chest
    m.add("spine", meshes.lathe_smooth(((0.0, 0.0), (0.15, -0.005), (0.165, -0.06), (0.16, -0.14), (0.15, -0.20),
                                        (0.0, -0.21)), 16),
          t=(0.0, p.spine_len + 0.02, 0), s=(d * 0.95 / 0.33, p.spine_len / 0.2, w * 0.85 / 0.33), col=col_belly,
          mat=mat)
    # chest: V-taper (broad shoulders, narrow waist)
    cs = chest_scale
    m.add("chest", meshes.lathe_smooth(((0.0, 0.165), (0.10, 0.16), (0.175, 0.135), (0.205, 0.08), (0.2, 0.0),
                                        (0.17, -0.08), (0.145, -0.14), (0.0, -0.15)), 20),
          t=(0.0, p.chest_len * 0.48, 0), s=(d / 0.40 * cs[0], p.chest_len / 0.31 * cs[1], w / 0.40 * cs[2]),
          col=col_chest, mat=mat)
    # trapezius slope up to the neck
    m.add("chest", meshes.sphere(1.0, 14, 8), t=(-0.01, p.chest_len * 0.86, 0),
          s=(d * 0.36, 0.07, w * 0.36), col=col_chest, mat=mat)


def _neck(m: FighterModel, p: Proportions, col, r=0.055):
    m.add("neck", meshes.capsule(r, r * 1.05, p.neck_len + 0.02), t=(0.0, p.neck_len + 0.02, 0), col=col, mat=SKIN)


# ---------------------------------------------------------------------------
# GOLDEN — regal tactician master: white robe, gold trim, grey topknot, beard
# ---------------------------------------------------------------------------

def build_golden() -> FighterModel:
    p = Proportions(pelvis_h=0.98, spine_len=0.21, chest_len=0.27, head_r=0.112, shoulder_half=0.205,
                    upper_arm=0.29, forearm=0.27, thigh=0.45, shin=0.44, arm_r=0.05, leg_r=0.07,
                    torso_w=0.35, torso_d=0.22, fist_r=0.052)
    m = FighterModel("Golden", p, accent=srgb((255, 205, 90)), trail=srgb((255, 215, 120)),
                     spark=srgb((255, 220, 140)))
    skin = (214, 166, 124)
    robe = (238, 234, 224)
    robe_shade = (215, 210, 198)
    gold = (232, 178, 64)
    hair = (196, 196, 202)
    _torso(m, p, robe, robe, robe_shade, chest_scale=(1.05, 1.0, 1.0))
    # crossed gold lapel (diagonal band across chest)
    m.add("chest", meshes.rounded_box(0.035, 0.40, 0.06, 0.015), t=(p.torso_d * 0.46, p.chest_len * 0.52, 0.0),
          r=(32, 0, 0), col=gold, mat=GOLD)
    m.add("chest", meshes.rounded_box(0.03, 0.30, 0.05, 0.012), t=(p.torso_d * 0.44, p.chest_len * 0.62, -0.04),
          r=(-30, 0, 0), col=gold, mat=GOLD)
    # compass emblem
    m.add("chest", meshes.torus(0.045, 0.011, 16, 6), t=(p.torso_d * 0.47, p.chest_len * 0.58, 0.09),
          r=(0, 0, 90), col=gold, mat=GOLD)
    m.add("chest", meshes.wedge(0.02, 0.06, 0.02), t=(p.torso_d * 0.5, p.chest_len * 0.58, 0.09), col=gold, mat=GOLD)
    # gold sash
    m.add("spine", meshes.cylinder(0.205, 0.21, 0.10, 20), t=(0.0, 0.07, 0), s=(p.torso_d / 0.36, 1, 1.0),
          col=gold, mat=GOLD)
    # robe skirt panels on the thighs + short apron on pelvis
    m.add("pelvis", meshes.cylinder(0.20, 0.235, 0.18, 20), t=(0.0, 0.0, 0), s=(0.75, 1, 1.0), col=robe, mat=CLOTH)
    for side in ("l", "r"):
        zs = -1 if side == "l" else 1
        m.add("thigh_" + side, meshes.cylinder(0.11, 0.15, 0.62, 16), t=(0.0, 0.02, zs * 0.01), s=(1.1, 1, 0.9),
              col=robe, mat=CLOTH)
        m.add("thigh_" + side, meshes.torus(0.148, 0.014, 18, 6), t=(0.0, -0.585, zs * 0.01), s=(1.1, 1, 0.9),
              col=gold, mat=GOLD)
        _limb(m, "shin_" + side, p.shin, 0.075, 0.06, robe_shade)
        m.add("shin_" + side, meshes.cylinder(0.062, 0.058, 0.07, 14), t=(0, -p.shin + 0.08, 0), col=gold, mat=GOLD)
        _foot(m, side, p, (70, 56, 46))
        # shoulders: robe pad + gold rim
        m.add("upperarm_" + side, meshes.sphere(0.085, 14, 10), t=(0, -0.02, 0), s=(1.0, 0.9, 1.0), col=robe)
        m.add("upperarm_" + side, meshes.torus(0.075, 0.014, 16, 6), t=(0, -0.06, 0), col=gold, mat=GOLD)
        # wide sleeves
        _limb(m, "upperarm_" + side, p.upper_arm, 0.07, 0.072, robe)
        _limb(m, "forearm_" + side, p.forearm, 0.05, 0.042, skin, SKIN)
        # ornate gold bracer
        m.add("forearm_" + side, meshes.cylinder(0.062, 0.056, 0.16, 16), t=(0, -0.08, 0), col=gold, mat=GOLD)
        m.add("forearm_" + side, meshes.torus(0.062, 0.010, 16, 6), t=(0, -0.09, 0), col=(255, 214, 110), mat=GOLD)
        m.add("forearm_" + side, meshes.torus(0.058, 0.010, 16, 6), t=(0, -0.23, 0), col=(255, 214, 110), mat=GOLD)
        _fist(m, side, p, skin)
    _neck(m, p, skin, 0.05)
    _head_base(m, p, skin)
    r = p.head_r
    # grey hair cap, swept back
    m.add("head", meshes.sphere(r * 1.04, 18, 12), t=(-r * 0.14, r * 1.12, 0), s=(1.0, 0.92, 0.96), col=hair, mat=HAIR)
    # topknot
    m.add("head", meshes.sphere(r * 0.38, 12, 8), t=(-r * 0.15, r * 2.05, 0), col=hair, mat=HAIR)
    m.add("head", meshes.torus(r * 0.26, r * 0.07, 12, 6), t=(-r * 0.15, r * 1.82, 0), col=gold, mat=GOLD)
    # long hair at the back
    m.add("head", meshes.rounded_box(r * 0.6, r * 1.6, r * 1.4, r * 0.25), t=(-r * 0.75, r * 0.45, 0), r=(0, 0, -8),
          col=hair, mat=HAIR)
    # beard + moustache
    m.add("head", meshes.lathe_smooth(((0.0, 0.0), (0.05, -0.01), (0.055, -0.05), (0.03, -0.10), (0.0, -0.13)), 12),
          t=(r * 0.62, r * 0.42, 0), s=(0.9, 1.0, 1.25), r=(0, 0, 12), col=hair, mat=HAIR)
    m.add("head", meshes.rounded_box(r * 0.18, r * 0.12, r * 0.8, r * 0.05), t=(r * 0.9, r * 0.66, 0),
          col=hair, mat=HAIR)
    # trailing gold sash ends
    m.add_chain(ChainSpec("pelvis", (0.02, 0.06, -0.20), 6, 0.075, 0.09, 0.018, gold, (250, 205, 100), GOLD,
                          rest_dir=(-0.5, -1.0, -0.2), stiffness=0.25))
    m.add_chain(ChainSpec("pelvis", (-0.04, 0.06, -0.17), 5, 0.075, 0.08, 0.018, gold, (250, 205, 100), GOLD,
                          rest_dir=(-0.9, -1.0, -0.1), stiffness=0.25))
    return m


# ---------------------------------------------------------------------------
# CRIMSON — aggressive red brawler: sleeveless gi, bare arms, hand wraps
# ---------------------------------------------------------------------------

def build_crimson() -> FighterModel:
    p = Proportions(pelvis_h=0.98, spine_len=0.20, chest_len=0.28, head_r=0.112, shoulder_half=0.23,
                    upper_arm=0.29, forearm=0.27, thigh=0.45, shin=0.44, arm_r=0.06, leg_r=0.075,
                    torso_w=0.40, torso_d=0.25, fist_r=0.06)
    m = FighterModel("Crimson", p, accent=srgb((255, 70, 40)), trail=srgb((255, 90, 40)),
                     spark=srgb((255, 120, 50)))
    skin = (205, 150, 108)
    red = (200, 30, 34)
    red_dark = (140, 18, 24)
    black = (26, 22, 24)
    _torso(m, p, red, red, black, chest_scale=(1.0, 1.0, 1.08))
    # open gi: skin V on the chest + black lapels
    m.add("chest", meshes.sphere(1.0, 14, 10), t=(p.torso_d * 0.36, p.chest_len * 0.62, 0),
          s=(0.06, 0.12, 0.085), col=skin, mat=SKIN)
    for zs in (-1, 1):
        m.add("chest", meshes.rounded_box(0.035, 0.36, 0.05, 0.015),
              t=(p.torso_d * 0.43, p.chest_len * 0.5, zs * 0.075), r=(zs * -14, 0, 0), col=black, mat=CLOTH)
    # flame emblem
    m.add("chest", meshes.wedge(0.05, 0.09, 0.02), t=(p.torso_d * 0.46, p.chest_len * 0.36, 0.12), r=(0, 0, -6),
          col=(255, 150, 30), mat=GLOW)
    # belt with knot
    m.add("spine", meshes.cylinder(0.215, 0.22, 0.07, 20), t=(0, 0.05, 0), s=(p.torso_d / 0.40, 1, 1.0),
          col=black, mat=CLOTH)
    m.add("spine", meshes.sphere(0.035, 8, 6), t=(p.torso_d * 0.5, 0.02, 0.04), col=black)
    for side in ("l", "r"):
        zs = -1 if side == "l" else 1
        # gi armholes (red trim on shoulders)
        m.add("chest", meshes.sphere(0.09, 12, 8), t=(0.0, p.chest_len - 0.04, zs * (p.shoulder_half - 0.06)),
              s=(1.1, 0.7, 1.0), col=red_dark)
        # muscular arms
        m.add("upperarm_" + side, meshes.sphere(0.088, 14, 10), t=(0, -0.025, 0), s=(1.05, 1.0, 1.0), col=skin, mat=SKIN)
        _limb(m, "upperarm_" + side, p.upper_arm, 0.07, 0.056, skin, SKIN)
        m.add("upperarm_" + side, meshes.sphere(0.06, 12, 8), t=(0.025, -0.14, 0), s=(1.1, 1.5, 1.0), col=skin, mat=SKIN)
        _limb(m, "forearm_" + side, p.forearm, 0.058, 0.045, skin, SKIN)
        # hand wraps
        for k in range(4):
            m.add("forearm_" + side, meshes.torus(0.05 - k * 0.002, 0.012, 14, 6), t=(0, -0.15 - k * 0.032, 0),
                  r=(0, 0, 6 * (1 if k % 2 else -1)), col=red if k % 2 else red_dark, mat=CLOTH)
        _fist(m, side, p, (190, 36, 36), CLOTH, size=1.08)
        # gi pants
        _limb(m, "thigh_" + side, p.thigh, 0.092, 0.075, black)
        _limb(m, "shin_" + side, p.shin, 0.075, 0.06, black)
        m.add("shin_" + side, meshes.cylinder(0.062, 0.058, 0.07, 14), t=(0, -p.shin + 0.07, 0), col=red, mat=CLOTH)
        _foot(m, side, p, skin, SKIN, length=0.24)
    _neck(m, p, skin, 0.062)
    _head_base(m, p, skin)
    r = p.head_r
    # spiky black hair
    m.add("head", meshes.sphere(r * 1.03, 18, 12), t=(-r * 0.12, r * 1.12, 0), s=(1.0, 0.9, 0.97), col=black, mat=HAIR)
    spikes = [(-55, 0, 0.0), (-85, 0, 0.0), (-115, 0, 0.0), (-35, 22, 0.55), (-70, 26, 0.6), (-105, 22, 0.55),
              (-35, -22, -0.55), (-70, -26, -0.6), (-105, -22, -0.55), (-10, 0, 0.0), (-15, 28, 0.5),
              (-15, -28, -0.5), (-140, 0, 0.0)]
    for (zr, xr, zoff) in spikes:
        m.add("head", meshes.wedge(r * 0.7, r * 1.15, r * 0.45),
              t=(-r * 0.2, r * 1.45, zoff * r), r=(xr, 0, zr), col=black, mat=HAIR)
    # fringe over the brow
    m.add("head", meshes.rounded_box(r * 0.4, r * 0.35, r * 1.5, r * 0.15), t=(r * 0.7, r * 1.48, 0), r=(0, 0, -25),
          col=black, mat=HAIR)
    # red headband + tails
    m.add("head", meshes.torus(r * 0.97, r * 0.12, 20, 6), t=(-r * 0.02, r * 1.42, 0), r=(0, 0, -14), s=(1.02, 1, 0.92),
          col=red, mat=CLOTH)
    m.add_chain(ChainSpec("head", (-r * 0.98, r * 1.3, -0.03), 5, 0.07, 0.045, 0.012, red, red_dark,
                          rest_dir=(-1.0, -0.4, -0.15), stiffness=0.3))
    m.add_chain(ChainSpec("head", (-r * 0.98, r * 1.27, 0.03), 4, 0.07, 0.04, 0.012, red, red_dark,
                          rest_dir=(-1.0, -0.6, 0.15), stiffness=0.3))
    return m


# ---------------------------------------------------------------------------
# SHADOW — hooded ninja: purple hood, mask, teal eyes, long trailing scarf
# ---------------------------------------------------------------------------

def build_shadow() -> FighterModel:
    p = Proportions(pelvis_h=0.95, spine_len=0.20, chest_len=0.25, head_r=0.105, shoulder_half=0.185,
                    upper_arm=0.29, forearm=0.27, thigh=0.45, shin=0.44, arm_r=0.045, leg_r=0.062,
                    torso_w=0.31, torso_d=0.20, fist_r=0.048)
    m = FighterModel("Shadow", p, accent=srgb((80, 255, 220)), trail=srgb((170, 90, 255)),
                     spark=srgb((150, 110, 255)))
    purple = (92, 44, 138)
    purple_dark = (52, 26, 82)
    black = (24, 22, 30)
    grey = (48, 46, 56)
    skin = (200, 160, 130)
    teal = (90, 255, 225)
    _torso(m, p, purple, purple_dark, black)
    # cross wrap straps
    m.add("chest", meshes.rounded_box(0.03, 0.40, 0.035, 0.012), t=(p.torso_d * 0.45, p.chest_len * 0.5, 0),
          r=(28, 0, 0), col=black)
    m.add("spine", meshes.cylinder(0.185, 0.19, 0.08, 18), t=(0, 0.06, 0), s=(p.torso_d / 0.34, 1, 1.0), col=black)
    # front tabard flap
    m.add("pelvis", meshes.rounded_box(0.03, 0.32, 0.13, 0.012), t=(p.torso_d * 0.5, -0.16, 0.0), col=purple)
    m.add("pelvis", meshes.rounded_box(0.03, 0.28, 0.13, 0.012), t=(-p.torso_d * 0.5, -0.14, 0.0), col=purple_dark)
    for side in ("l", "r"):
        zs = -1 if side == "l" else 1
        m.add("upperarm_" + side, meshes.sphere(0.07, 12, 8), t=(0, -0.02, 0), col=purple)
        _limb(m, "upperarm_" + side, p.upper_arm, 0.055, 0.045, purple)
        _limb(m, "forearm_" + side, p.forearm, 0.046, 0.038, black)
        for k in range(3):
            m.add("forearm_" + side, meshes.torus(0.043, 0.008, 12, 5), t=(0, -0.06 - k * 0.07, 0), r=(0, 0, 10),
                  col=grey)
        _fist(m, side, p, skin, SKIN, size=0.95, wrap_col=black)
        _limb(m, "thigh_" + side, p.thigh, 0.078, 0.06, grey)
        _limb(m, "shin_" + side, p.shin, 0.06, 0.045, black)
        # knee pads
        m.add("shin_" + side, meshes.sphere(0.06, 10, 8), t=(0.035, -0.02, 0), s=(0.9, 1.1, 1.0), col=purple_dark,
              mat=LEATHER)
        _foot(m, side, p, black, length=0.23, width=0.09)
    # crescent shoulder plate (lead shoulder)
    m.add("upperarm_l", meshes.sphere(0.08, 12, 8), t=(0, 0.0, -0.01), s=(1.0, 0.6, 1.0), col=(70, 60, 90),
          mat=DARK_METAL)
    m.add("upperarm_r", meshes.sphere(0.08, 12, 8), t=(0, 0.0, 0.01), s=(1.0, 0.6, 1.0), col=(70, 60, 90),
          mat=DARK_METAL)
    m.add("upperarm_r", meshes.torus(0.035, 0.008, 12, 5), t=(0.0, 0.0, 0.085), r=(90, 0, 0), col=(200, 200, 215),
          mat=STEEL)
    _neck(m, p, black, 0.05)
    _head_base(m, p, (190, 150, 120), eyes=False)
    r = p.head_r
    # mask over lower face
    m.add("head", meshes.sphere(r * 0.86, 16, 12), t=(r * 0.3, r * 0.62, 0), s=(0.95, 0.72, 1.0), col=black)
    # glowing teal eyes
    for zs in (-1, 1):
        m.add("head", meshes.rounded_box(r * 0.12, r * 0.09, r * 0.34, r * 0.035),
              t=(r * 0.98, r * 1.02, zs * r * 0.34), r=(zs * -12, 0, 0), col=teal, mat=GLOW)
    # hood: shell behind the face, pointed peak, drapes onto the shoulders
    m.add("head", meshes.sphere(r * 1.25, 18, 12), t=(-r * 0.38, r * 1.12, 0), s=(1.0, 1.06, 1.0), col=purple)
    m.add("head", meshes.sphere(r * 1.0, 16, 10), t=(r * 0.18, r * 1.42, 0), s=(1.0, 0.55, 1.12), col=purple)
    m.add("head", meshes.lathe_smooth(((0.0, 0.0), (0.06, -0.03), (0.09, -0.10), (0.0, -0.16)), 12),
          t=(-r * 1.3, r * 1.75, 0), r=(0, 0, 75), col=purple)
    for zs in (-1, 1):
        m.add("head", meshes.rounded_box(r * 1.2, r * 1.5, r * 0.3, r * 0.12), t=(-r * 0.2, r * 0.6, zs * r * 1.0),
              r=(zs * 8, 0, 10), col=purple_dark)
    # scarf wrap around neck + long trailing scarf
    m.add("neck", meshes.torus(0.075, 0.035, 16, 8), t=(0.0, 0.03, 0), col=purple_dark)
    m.add_chain(ChainSpec("neck", (-0.06, 0.04, -0.02), 9, 0.10, 0.11, 0.02, (60, 30, 96), (26, 18, 40),
                          rest_dir=(-1.0, -0.35, -0.1), stiffness=0.22, gravity=6.0))
    return m


# ---------------------------------------------------------------------------
# STEEL — bulky armoured guardian: plate armour, blue visor, forearm shields
# ---------------------------------------------------------------------------

def build_steel() -> FighterModel:
    p = Proportions(pelvis_h=1.02, spine_len=0.22, chest_len=0.30, head_r=0.118, shoulder_half=0.26,
                    upper_arm=0.30, forearm=0.28, thigh=0.47, shin=0.46, arm_r=0.065, leg_r=0.085,
                    torso_w=0.46, torso_d=0.30, fist_r=0.064)
    m = FighterModel("Steel", p, accent=srgb((80, 170, 255)), trail=srgb((120, 190, 255)),
                     spark=srgb((150, 210, 255)))
    plate = (178, 184, 196)
    plate_dark = (110, 116, 130)
    navy = (34, 44, 92)
    navy_dark = (22, 28, 60)
    blue = (90, 180, 255)
    _torso(m, p, plate, plate_dark, plate_dark, chest_scale=(1.0, 1.0, 1.0), mat=STEEL)
    # breastplate ridge + shield emblem
    m.add("chest", meshes.rounded_box(p.torso_d * 0.55, p.chest_len * 0.8, p.torso_w * 0.78, 0.07),
          t=(p.torso_d * 0.22, p.chest_len * 0.52, 0), col=plate, mat=STEEL)
    m.add("chest", meshes.rounded_box(0.06, 0.24, 0.04, 0.02), t=(p.torso_d * 0.5, p.chest_len * 0.5, 0),
          col=(205, 210, 220), mat=STEEL)
    for k in range(3):
        m.add("spine", meshes.cylinder(0.2 - k * 0.006, 0.205 - k * 0.006, 0.06, 18),
              t=(0, p.spine_len - 0.02 - k * 0.055, 0), s=(p.torso_d / 0.42, 1, p.torso_w / 0.45), col=plate_dark,
              mat=STEEL)
    m.add("chest", meshes.lathe_smooth(((0.0, 0.0), (0.06, -0.005), (0.055, -0.06), (0.0, -0.11)), 4),
          t=(p.torso_d * 0.5, p.chest_len * 0.62, 0.0), r=(0, 0, 90), s=(1, 0.4, 1), col=(70, 120, 210), mat=STEEL)
    # navy sash across + tabard
    m.add("spine", meshes.cylinder(0.25, 0.25, 0.10, 20), t=(0, 0.08, 0), s=(p.torso_d / 0.48, 1, 1.0), col=navy)
    m.add("pelvis", meshes.rounded_box(0.04, 0.46, 0.20, 0.015), t=(p.torso_d * 0.48, -0.22, 0.0), col=navy)
    m.add("pelvis", meshes.rounded_box(0.04, 0.42, 0.22, 0.015), t=(-p.torso_d * 0.48, -0.2, 0.0), col=navy_dark)
    # faulds (hip plates)
    m.add("pelvis", meshes.cylinder(0.25, 0.28, 0.12, 20), t=(0, 0.0, 0), s=(0.8, 1, 1.0), col=plate_dark, mat=STEEL)
    for side in ("l", "r"):
        zs = -1 if side == "l" else 1
        # massive pauldrons (layered)
        m.add("shoulder_" + side, meshes.sphere(0.13, 16, 10), t=(0, 0.02, zs * 0.17), s=(1.15, 0.85, 1.0),
              col=plate, mat=STEEL)
        m.add("shoulder_" + side, meshes.sphere(0.12, 16, 10), t=(0, -0.05, zs * 0.20), s=(1.1, 0.6, 0.95),
              col=plate_dark, mat=STEEL)
        _limb(m, "upperarm_" + side, p.upper_arm, 0.07, 0.06, navy)
        m.add("upperarm_" + side, meshes.cylinder(0.075, 0.068, 0.12, 14), t=(0, -0.13, 0), col=plate, mat=STEEL)
        # elbow cop
        m.add("forearm_" + side, meshes.sphere(0.065, 12, 8), t=(0, 0.0, 0), col=plate_dark, mat=STEEL)
        # gauntlet
        m.add("forearm_" + side, meshes.cylinder(0.07, 0.066, p.forearm - 0.02, 14), t=(0, -0.02, 0), col=plate,
              mat=STEEL)
        _fist(m, side, p, plate_dark, STEEL, size=1.1)
        # forearm shield (kite shape) on the outer side
        m.add("forearm_" + side, meshes.rounded_box(0.30, 0.40, 0.035, 0.015),
              t=(0.0, -0.17, zs * 0.085), col=(160, 168, 182), mat=STEEL)
        m.add("forearm_" + side, meshes.rounded_box(0.25, 0.34, 0.02, 0.01),
              t=(0.0, -0.17, zs * 0.105), col=(120, 128, 146), mat=STEEL)
        m.add("forearm_" + side, meshes.rounded_box(0.02, 0.30, 0.012, 0.005),
              t=(0.0, -0.17, zs * 0.118), col=blue, mat=GLOW)
        # legs: navy cloth + plate cuisses, greaves, sabatons
        _limb(m, "thigh_" + side, p.thigh, 0.1, 0.085, navy)
        m.add("thigh_" + side, meshes.cylinder(0.105, 0.09, 0.28, 14), t=(0.01, -0.06, 0), s=(1.0, 1, 1.0), col=plate,
              mat=STEEL)
        m.add("shin_" + side, meshes.sphere(0.075, 12, 8), t=(0.03, 0.0, 0), col=plate_dark, mat=STEEL)
        _limb(m, "shin_" + side, p.shin, 0.085, 0.07, plate, STEEL)
        _foot(m, side, p, plate_dark, STEEL, length=0.28, width=0.13, height=0.10)
    _neck(m, p, navy_dark, 0.07)
    r = p.head_r
    # great helm: domed top, flat faceplate, cheek guards
    m.add("head", meshes.sphere(r * 1.12, 20, 14), t=(-r * 0.05, r * 1.15, 0), s=(1.08, 1.05, 0.95), col=plate,
          mat=STEEL)
    m.add("head", meshes.rounded_box(r * 1.0, r * 1.3, r * 1.75, r * 0.35), t=(r * 0.42, r * 0.72, 0), col=plate,
          mat=STEEL)
    m.add("head", meshes.wedge(r * 0.5, r * 0.55, r * 1.2), t=(r * 0.88, r * 0.35, 0), r=(0, 0, 180),
          col=plate_dark, mat=STEEL)
    # crest ridge
    m.add("head", meshes.rounded_box(r * 2.0, r * 0.22, r * 0.2, r * 0.08), t=(-r * 0.1, r * 2.2, 0), r=(0, 0, -6),
          col=(210, 215, 228), mat=STEEL)
    # glowing visor slit + breathing slot
    m.add("head", meshes.rounded_box(r * 0.2, r * 0.13, r * 1.4, r * 0.05), t=(r * 0.93, r * 1.08, 0),
          col=blue, mat=GLOW)
    m.add("head", meshes.rounded_box(r * 0.12, r * 0.5, r * 0.1, r * 0.04), t=(r * 0.96, r * 0.7, 0),
          col=(30, 34, 44), mat=DARK_METAL)
    # gorget
    m.add("neck", meshes.cylinder(0.11, 0.13, 0.09, 16), t=(0, 0.05, 0), col=plate_dark, mat=STEEL)
    return m


BUILDERS = {
    "Golden": build_golden,
    "Crimson": build_crimson,
    "Shadow": build_shadow,
    "Steel": build_steel,
}


@lru_cache(maxsize=None)
def get_model(name: str) -> FighterModel:
    return BUILDERS.get(name, build_golden)()


@lru_cache(maxsize=None)
def get_vertex_data(name: str) -> bytes:
    return get_model(name).bake().tobytes()
