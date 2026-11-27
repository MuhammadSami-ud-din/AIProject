"""3D arena stages: lighting rig, floor material, backdrop painting, props and
ambient particles for each arena in frontend/assets/backgrounds."""

from dataclasses import dataclass, field
from functools import lru_cache
import math

import numpy as np

from frontend.render3d import meshes
from frontend.render3d.characters import CLOTH, DARK_METAL, GLOW, GOLD, STEEL, srgb
from frontend.render3d.mathutil import compose

STONE = (0.8, 0.0, 0.0, 0.0)
WOOD = (0.7, 0.0, 0.0, 0.0)
ICE = (0.15, 0.1, 0.25, 0.0)
NEON = (0.4, 0.0, 3.0, 0.0)
LAVA = (0.6, 0.0, 3.5, 0.0)

WALL_X = 4.0  # ARENA_WIDTH / 2 in metres


@dataclass
class ArenaSpec:
    key: str
    floor_type: int
    floor_a: tuple
    floor_b: tuple
    floor_line: tuple
    gloss: float
    key_col: tuple
    fill_col: tuple
    rim_col: tuple
    sky: tuple
    ground: tuple
    fog: tuple
    fog_range: tuple = (13.0, 26.0)
    key_dir: tuple = (-0.45, 0.85, 0.55)
    floor_emit: tuple = (0.0, 0.0, 0.0)
    backdrop_exposure: float = 1.0
    haze: float = 0.55
    grade: tuple = (1.0, 1.0, 1.0)
    lights: list = field(default_factory=list)     # (x, y, z, radius, r, g, b, intensity, flicker)
    ambient: str = "motes"
    exposure: float = 1.0


def _c(rgb, k=1.0):
    return tuple(v * k for v in srgb(rgb))


ARENAS = {
    "arena_golden_temple": ArenaSpec(
        "arena_golden_temple", 0, _c((150, 128, 104)), _c((118, 98, 80)), _c((70, 58, 46)), 0.45,
        key_col=_c((255, 214, 160), 2.4), fill_col=_c((120, 140, 200), 0.45), rim_col=_c((255, 190, 110), 1.6),
        sky=_c((150, 140, 140), 0.55), ground=_c((120, 90, 60), 0.35), fog=_c((235, 180, 120), 0.9),
        key_dir=(-0.35, 0.75, 0.5), grade=(1.04, 1.0, 0.92),
        lights=[(-4.9, 1.25, -1.2, 3.0, 1.0, 0.7, 0.35, 2.5, 1), (4.9, 1.25, -1.2, 3.0, 1.0, 0.7, 0.35, 2.5, 1)],
        ambient="leaves"),
    "arena_neon_rooftop": ArenaSpec(
        "arena_neon_rooftop", 1, _c((52, 50, 62)), _c((34, 32, 42)), _c((24, 22, 30)), 0.85,
        key_col=_c((170, 150, 255), 1.4), fill_col=_c((80, 230, 255), 0.6), rim_col=_c((255, 70, 200), 2.4),
        sky=_c((70, 50, 120), 0.45), ground=_c((40, 30, 60), 0.3), fog=_c((70, 45, 110), 0.9),
        key_dir=(0.3, 0.8, 0.5), grade=(0.98, 0.95, 1.06), backdrop_exposure=1.1,
        lights=[(-5.2, 2.0, -1.4, 4.5, 1.0, 0.2, 0.75, 3.0, 0), (5.2, 2.0, -1.4, 4.5, 0.2, 0.9, 1.0, 3.0, 0)],
        ambient="rain"),
    "arena_volcanic_forge": ArenaSpec(
        "arena_volcanic_forge", 3, _c((40, 30, 30)), _c((22, 16, 18)), _c((15, 10, 10)), 0.35,
        key_col=_c((255, 150, 90), 1.6), fill_col=_c((255, 80, 20), 0.5), rim_col=_c((255, 120, 40), 2.6),
        sky=_c((120, 50, 30), 0.4), ground=_c((255, 90, 30), 0.35), fog=_c((120, 40, 20), 0.9),
        floor_emit=_c((255, 110, 30), 3.0), key_dir=(0.2, 0.8, 0.6), grade=(1.06, 0.96, 0.9),
        lights=[(-5.0, 1.4, -1.0, 4.0, 1.0, 0.45, 0.1, 3.5, 1), (5.0, 1.4, -1.0, 4.0, 1.0, 0.45, 0.1, 3.5, 1)],
        ambient="embers"),
    "arena_iron_foundry": ArenaSpec(
        "arena_iron_foundry", 2, _c((92, 88, 84)), _c((62, 58, 56)), _c((34, 32, 30)), 0.5,
        key_col=_c((255, 200, 150), 1.8), fill_col=_c((120, 150, 200), 0.4), rim_col=_c((255, 150, 70), 2.0),
        sky=_c((110, 100, 90), 0.45), ground=_c((90, 60, 40), 0.3), fog=_c((110, 80, 60), 0.9),
        key_dir=(-0.3, 0.85, 0.45), grade=(1.04, 0.99, 0.93),
        lights=[(-4.8, 2.2, -1.2, 4.0, 1.0, 0.6, 0.3, 2.8, 1), (4.8, 2.2, -1.2, 4.0, 1.0, 0.6, 0.3, 2.8, 1)],
        ambient="embers"),
    "arena_moonlit_bamboo": ArenaSpec(
        "arena_moonlit_bamboo", 4, _c((120, 100, 72)), _c((86, 70, 50)), _c((50, 40, 30)), 0.35,
        key_col=_c((170, 200, 255), 1.5), fill_col=_c((90, 220, 190), 0.4), rim_col=_c((150, 220, 255), 2.2),
        sky=_c((60, 90, 110), 0.5), ground=_c((40, 60, 40), 0.3), fog=_c((50, 80, 90), 0.9),
        key_dir=(0.4, 0.8, 0.45), grade=(0.95, 1.02, 1.04),
        lights=[(-4.8, 1.0, -1.2, 3.0, 1.0, 0.75, 0.4, 2.2, 1), (4.8, 1.0, -1.2, 3.0, 1.0, 0.75, 0.4, 2.2, 1)],
        ambient="fireflies"),
    "arena_frozen_peak": ArenaSpec(
        "arena_frozen_peak", 5, _c((215, 225, 240)), _c((150, 190, 225)), _c((120, 150, 180)), 0.6,
        key_col=_c((235, 240, 255), 2.0), fill_col=_c((120, 170, 255), 0.6), rim_col=_c((180, 220, 255), 2.0),
        sky=_c((150, 180, 220), 0.55), ground=_c((160, 180, 210), 0.4), fog=_c((190, 210, 235), 0.95),
        key_dir=(-0.4, 0.8, 0.5), grade=(0.96, 1.0, 1.06), exposure=0.9,
        lights=[(-4.8, 1.3, -1.2, 3.0, 1.0, 0.6, 0.3, 2.2, 1), (4.8, 1.3, -1.2, 3.0, 1.0, 0.6, 0.3, 2.2, 1)],
        ambient="snow"),
    "arena_sky_colosseum": ArenaSpec(
        "arena_sky_colosseum", 6, _c((225, 220, 212)), _c((190, 184, 176)), _c((200, 160, 70)), 0.6,
        key_col=_c((255, 240, 220), 2.2), fill_col=_c((170, 150, 255), 0.5), rim_col=_c((255, 220, 160), 2.0),
        sky=_c((170, 170, 210), 0.55), ground=_c((150, 130, 110), 0.35), fog=_c((210, 200, 230), 0.9),
        key_dir=(-0.3, 0.8, 0.55), grade=(1.02, 1.0, 1.02), exposure=0.92,
        lights=[(-4.9, 1.6, -1.2, 3.5, 1.0, 0.8, 0.45, 2.6, 1), (4.9, 1.6, -1.2, 3.5, 1.0, 0.8, 0.45, 2.6, 1)],
        ambient="motes"),
}

ALIASES = {
    "underground_vault": "arena_iron_foundry",
    "temple_ruins": "arena_golden_temple",
    "dojo": "arena_moonlit_bamboo",
    "volcanic_depths": "arena_volcanic_forge",
}


def normalize_arena(name) -> str:
    clean = (str(name or "arena_neon_rooftop").lower().strip().replace(".jpeg", "").replace(".jpg", "")
             .replace(".png", "").replace(" ", "_"))
    clean = ALIASES.get(clean, clean)
    if not clean.startswith("arena_"):
        clean = "arena_" + clean
    if clean not in ARENAS:
        clean = "arena_neon_rooftop"
    return clean


def get_spec(name) -> ArenaSpec:
    return ARENAS[normalize_arena(name)]


# ---------------------------------------------------------------------------
# Props (static, baked into one vertex buffer per arena, bone index 0)
# ---------------------------------------------------------------------------
class _PropBuilder:
    def __init__(self):
        self.chunks = []

    def add(self, mesh, t=(0, 0, 0), r=(0, 0, 0), s=(1, 1, 1), col=(200, 200, 200), mat=STONE, mirror=True):
        for sx in ((1, -1) if mirror else (1,)):
            m = compose((t[0] * sx, t[1], t[2]), (r[0], r[1] * sx, r[2] * sx), s)
            pos, nrm = meshes.transform(mesh, m)
            d = np.empty((len(pos), 14), dtype="f4")
            d[:, 0:3] = pos
            d[:, 3:6] = nrm
            d[:, 6:9] = srgb(col)
            d[:, 9:13] = mat
            d[:, 13] = 0
            self.chunks.append(d)

    def data(self):
        if not self.chunks:
            return np.zeros((0, 14), dtype="f4")
        return np.concatenate(self.chunks)


def _lantern(b, x, z, scale=1.0, col=(120, 125, 110)):
    s = scale
    b.add(meshes.cylinder(0.18 * s, 0.24 * s, 0.12 * s, 8), t=(x, 0.12 * s, z), col=col)
    b.add(meshes.cylinder(0.09 * s, 0.11 * s, 0.7 * s, 8), t=(x, 0.82 * s, z), col=col)
    b.add(meshes.rounded_box(0.36 * s, 0.07 * s, 0.36 * s, 0.02), t=(x, 0.86 * s, z), col=col)
    b.add(meshes.rounded_box(0.26 * s, 0.26 * s, 0.26 * s, 0.03), t=(x, 1.02 * s, z), col=(255, 200, 120), mat=GLOW)
    b.add(meshes.cylinder(0.02 * s, 0.32 * s, 0.22 * s, 8), t=(x, 1.38 * s, z), col=col)
    b.add(meshes.sphere(0.06 * s, 8, 6), t=(x, 1.42 * s, z), col=col)


def _column(b, x, z, h=3.2, r=0.28, col=(230, 225, 215), mat=STONE, cap_col=None):
    b.add(meshes.rounded_box(r * 2.6, 0.22, r * 2.6, 0.03), t=(x, 0.11, z), col=col, mat=mat)
    b.add(meshes.cylinder(r, r * 1.08, h, 16), t=(x, h + 0.22, z), col=col, mat=mat)
    for k in range(8):
        a = k * math.pi / 4
        b.add(meshes.cylinder(r * 0.12, r * 0.12, h, 4),
              t=(x + math.cos(a) * r * 0.98, h + 0.22, z + math.sin(a) * r * 0.98), col=col, mat=mat)
    b.add(meshes.rounded_box(r * 2.6, 0.24, r * 2.6, 0.03), t=(x, h + 0.34, z), col=cap_col or col, mat=mat)


def _brazier(b, x, z, col=(200, 160, 70), mat=GOLD, flame=(255, 150, 50)):
    b.add(meshes.cylinder(0.05, 0.08, 1.0, 8), t=(x, 1.0, z), col=(60, 50, 45), mat=DARK_METAL)
    b.add(meshes.lathe_smooth(((0.0, 0.0), (0.28, 0.02), (0.30, -0.06), (0.2, -0.2), (0.0, -0.22)), 14),
          t=(x, 1.22, z), col=col, mat=mat)
    b.add(meshes.sphere(0.2, 10, 8), t=(x, 1.28, z), s=(1.0, 1.3, 1.0), col=flame, mat=LAVA)


def build_props(key: str) -> np.ndarray:
    b = _PropBuilder()
    W = WALL_X + 0.75
    if key == "arena_golden_temple":
        _lantern(b, W, -1.2, 1.15)
        _lantern(b, W + 1.6, -3.4, 1.4)
        b.add(meshes.rounded_box(0.25, 0.9, 6.0, 0.04), t=(W + 3.2, 0.45, -3.0), col=(140, 130, 110))
        for k in range(5):
            b.add(meshes.rounded_box(1.4, 0.18, 4.0, 0.03), t=(W + 3.8 + k * 0.25, 0.09 + k * 0.18, -2.5),
                  col=(150, 135, 112))
    elif key == "arena_neon_rooftop":
        for z, h in ((-1.6, 1.0), (-3.2, 1.4)):
            b.add(meshes.rounded_box(1.1, h, 0.8, 0.05), t=(W + 0.4, h / 2, z), col=(110, 110, 125), mat=DARK_METAL)
            b.add(meshes.cylinder(0.32, 0.32, 0.04, 16), t=(W + 0.4, h * 0.55, z + 0.42), r=(90, 0, 0),
                  col=(50, 50, 60), mat=DARK_METAL)
        b.add(meshes.cylinder(0.05, 0.05, 2.6, 8), t=(W + 0.1, 2.6, -1.0), col=(70, 70, 80), mat=DARK_METAL)
        b.add(meshes.rounded_box(0.08, 0.9, 0.08, 0.03), t=(W + 0.1, 2.0, -0.94), col=(255, 60, 200), mat=NEON,
              mirror=False)
        b.add(meshes.rounded_box(0.08, 0.9, 0.08, 0.03), t=(-W - 0.1, 2.0, -0.94), col=(60, 230, 255), mat=NEON,
              mirror=False)
        b.add(meshes.rounded_box(14.0, 0.5, 0.35, 0.05), t=(0, 0.25, -6.2), col=(60, 58, 70), mirror=False)
    elif key == "arena_volcanic_forge":
        for z, h in ((-1.4, 2.4), (-3.6, 3.4)):
            b.add(meshes.lathe_smooth(((0.0, 0.0), (0.3, -0.1), (0.45, -0.6), (0.5, -1.0)), 7),
                  t=(W + 0.5, h, z), s=(1.0, h, 1.0), col=(40, 30, 32))
            b.add(meshes.rounded_box(0.04, h * 0.7, 0.04, 0.01), t=(W + 0.25, h * 0.45, z + 0.3), col=(255, 120, 30),
                  mat=LAVA)
        _brazier(b, W - 0.2, -0.9, col=(70, 50, 45), mat=DARK_METAL)
    elif key == "arena_iron_foundry":
        for z in (-1.3, -3.6):
            b.add(meshes.rounded_box(0.36, 4.5, 0.36, 0.02), t=(W + 0.3, 2.25, z), col=(90, 70, 60), mat=DARK_METAL)
            b.add(meshes.rounded_box(0.5, 0.12, 0.5, 0.02), t=(W + 0.3, 0.06, z), col=(70, 60, 55), mat=DARK_METAL)
        b.add(meshes.rounded_box(0.9, 0.9, 0.9, 0.04), t=(W + 1.2, 0.45, -0.6), r=(0, 15, 0), col=(130, 95, 60),
              mat=CLOTH)
        b.add(meshes.rounded_box(0.6, 0.6, 0.6, 0.04), t=(W + 1.15, 1.2, -0.7), r=(0, -10, 0), col=(120, 90, 58),
              mat=CLOTH)
        b.add(meshes.rounded_box(14.0, 0.25, 0.25, 0.02), t=(0, 4.6, -1.3), col=(80, 65, 55), mat=DARK_METAL,
              mirror=False)
        b.add(meshes.cylinder(0.25, 0.4, 0.25, 12), t=(0, 4.3, -1.3), col=(60, 55, 50), mat=DARK_METAL, mirror=False)
        b.add(meshes.sphere(0.12, 10, 8), t=(0, 4.1, -1.3), col=(255, 200, 140), mat=GLOW, mirror=False)
    elif key == "arena_moonlit_bamboo":
        rng = np.random.default_rng(3)
        for k in range(9):
            x = W + 0.2 + rng.uniform(0, 2.2)
            z = -0.8 - rng.uniform(0, 3.5)
            h = rng.uniform(4.0, 6.0)
            r = rng.uniform(0.05, 0.08)
            b.add(meshes.cylinder(r, r * 1.1, h, 8), t=(x, h, z), r=(rng.uniform(-4, 4), 0, rng.uniform(-4, 4)),
                  col=(80, 140, 70), mat=WOOD)
            for j in range(int(h / 0.6)):
                b.add(meshes.torus(r * 1.05, r * 0.25, 8, 4), t=(x, 0.4 + j * 0.6, z), col=(60, 110, 55), mat=WOOD)
        _lantern(b, W - 0.1, -1.0, 0.9)
    elif key == "arena_frozen_peak":
        rng = np.random.default_rng(5)
        for k in range(6):
            x = W + 0.2 + rng.uniform(0, 2.0)
            z = -0.8 - rng.uniform(0, 3.0)
            h = rng.uniform(0.8, 2.2)
            b.add(meshes.lathe_smooth(((0.0, 0.0), (0.12, -0.2), (0.25, -1.0)), 6), t=(x, h, z),
                  s=(1.0, h, 1.0), r=(rng.uniform(-12, 12), 0, rng.uniform(-12, 12)), col=(170, 215, 255), mat=ICE)
        b.add(meshes.sphere(1.0, 14, 8), t=(W + 1.2, -0.1, -1.4), s=(1.4, 0.45, 1.0), col=(235, 242, 255), mat=STONE)
        _brazier(b, W - 0.1, -1.1, col=(80, 70, 70), mat=DARK_METAL)
    else:  # sky colosseum
        _column(b, W + 0.3, -1.3, h=3.4)
        _column(b, W + 1.6, -3.6, h=3.8)
        _brazier(b, W - 0.25, -0.75)
    return b.data()


@lru_cache(maxsize=None)
def get_prop_bytes(key: str) -> bytes:
    return build_props(key).tobytes()


# ---------------------------------------------------------------------------
# Ambient particles
# ---------------------------------------------------------------------------
AMBIENT = {
    "leaves": dict(rate=0.6, col=(1.0, 0.45, 0.12), size=(0.03, 0.05), vel=(0.4, -0.5, 0.0), kind=0, glow=1.0),
    "rain": dict(rate=6.0, col=(0.5, 0.7, 1.0), size=(0.012, 0.018), vel=(-1.2, -11.0, 0.0), kind=1, glow=0.6),
    "embers": dict(rate=2.5, col=(1.0, 0.45, 0.1), size=(0.015, 0.03), vel=(0.0, 0.9, 0.0), kind=0, glow=3.0),
    "fireflies": dict(rate=0.8, col=(0.4, 1.0, 0.7), size=(0.02, 0.035), vel=(0.0, 0.2, 0.0), kind=0, glow=2.5),
    "snow": dict(rate=3.0, col=(0.9, 0.95, 1.0), size=(0.015, 0.03), vel=(0.3, -0.9, 0.0), kind=0, glow=1.0),
    "motes": dict(rate=0.8, col=(1.0, 0.9, 0.6), size=(0.012, 0.025), vel=(0.1, 0.15, 0.0), kind=0, glow=1.6),
}
