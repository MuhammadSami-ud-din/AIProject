"""Procedural meshes with normals (built once, cached).

Every builder returns ``(positions, normals)`` as float32 arrays of shape (N, 3)
forming a plain triangle list (no index buffer).  Meshes are small (a few
hundred triangles), so character parts are baked into one big vertex buffer per
fighter and skinned rigidly in the vertex shader.
"""

import math
from functools import lru_cache

import numpy as np


def _lathe(profile, segs: int):
    """Revolve a 2D profile around +Y.

    profile: list of (r, y, nr, ny) from top to bottom; (nr, ny) is the 2D normal.
    Consecutive identical points with different normals create hard edges.
    """
    angs = np.linspace(0.0, 2.0 * math.pi, segs + 1)
    ca, sa = np.cos(angs), np.sin(angs)
    pos, nrm = [], []
    for i in range(len(profile) - 1):
        r0, y0, nr0, ny0 = profile[i]
        r1, y1, nr1, ny1 = profile[i + 1]
        if abs(r0 - r1) < 1e-9 and abs(y0 - y1) < 1e-9:
            continue  # hard-edge duplicate
        for j in range(segs):
            c0, s0, c1, s1 = ca[j], sa[j], ca[j + 1], sa[j + 1]
            p00 = (r0 * c0, y0, r0 * s0)
            p01 = (r0 * c1, y0, r0 * s1)
            p10 = (r1 * c0, y1, r1 * s0)
            p11 = (r1 * c1, y1, r1 * s1)
            n00 = (nr0 * c0, ny0, nr0 * s0)
            n01 = (nr0 * c1, ny0, nr0 * s1)
            n10 = (nr1 * c0, ny1, nr1 * s0)
            n11 = (nr1 * c1, ny1, nr1 * s1)
            # profile goes top->bottom, angle increases around +Y; choose CCW outward winding
            if r0 > 1e-7:
                pos += [p00, p10, p01]
                nrm += [n00, n10, n01]
            if r1 > 1e-7:
                pos += [p01, p10, p11]
                nrm += [n01, n10, n11]
    p = np.asarray(pos, dtype="f4").reshape(-1, 3)
    n = np.asarray(nrm, dtype="f4").reshape(-1, 3)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln < 1e-8] = 1.0
    return p, n / ln


def _smooth_profile(points):
    """Give (r, y) points smooth 2D normals."""
    out = []
    n = len(points)
    for i, (r, y) in enumerate(points):
        if i == 0:
            dr, dy = points[1][0] - r, points[1][1] - y
        elif i == n - 1:
            dr, dy = r - points[i - 1][0], y - points[i - 1][1]
        else:
            dr = points[i + 1][0] - points[i - 1][0]
            dy = points[i + 1][1] - points[i - 1][1]
        # tangent (dr, dy) going downwards; outward normal = (-dy, dr) rotated
        nr, ny = -dy, dr
        ln = math.hypot(nr, ny) or 1.0
        nr, ny = nr / ln, ny / ln
        if r < 1e-7:  # pole
            nr, ny = 0.0, (1.0 if i == 0 else -1.0)
        out.append((r, y, nr, ny))
    return out


@lru_cache(maxsize=None)
def sphere(radius: float = 1.0, segs: int = 18, rings: int = 12):
    prof = []
    for i in range(rings + 1):
        th = math.pi * i / rings
        prof.append((radius * math.sin(th), radius * math.cos(th), math.sin(th), math.cos(th)))
    return _lathe(prof, segs)


@lru_cache(maxsize=None)
def capsule(r_top: float, r_bot: float, length: float, segs: int = 14, rings: int = 5):
    """Tapered capsule along -Y: top sphere centre at y=0, bottom centre at y=-length."""
    prof = []
    for i in range(rings + 1):
        th = (math.pi / 2) * i / rings
        prof.append((r_top * math.sin(th), r_top * math.cos(th), math.sin(th), math.cos(th)))
    for i in range(rings + 1):
        th = math.pi / 2 + (math.pi / 2) * i / rings
        prof.append((r_bot * math.sin(th), -length + r_bot * math.cos(th), math.sin(th), math.cos(th)))
    return _lathe(prof, segs)


@lru_cache(maxsize=None)
def cylinder(r_top: float, r_bot: float, height: float, segs: int = 16, caps: bool = True):
    """Frustum from y=0 (top) to y=-height with hard-edged caps."""
    side_ny = (r_bot - r_top) / max(1e-6, height)
    ln = math.hypot(1.0, side_ny)
    snr, sny = 1.0 / ln, -side_ny / ln
    snr, sny = 1.0 / ln, (r_top - r_bot) / max(1e-6, height) / ln
    prof = []
    if caps:
        prof.append((0.0, 0.0, 0.0, 1.0))
        prof.append((r_top, 0.0, 0.0, 1.0))
    prof.append((r_top, 0.0, snr, sny))
    prof.append((r_bot, -height, snr, sny))
    if caps:
        prof.append((r_bot, -height, 0.0, -1.0))
        prof.append((0.0, -height, 0.0, -1.0))
    return _lathe(prof, segs)


@lru_cache(maxsize=None)
def lathe_smooth(points: tuple, segs: int = 16):
    """Revolve a smooth (r, y) profile (top to bottom)."""
    return _lathe(_smooth_profile(list(points)), segs)


@lru_cache(maxsize=None)
def torus(major: float, minor: float, segs: int = 20, sides: int = 8):
    prof = []
    for i in range(sides + 1):
        a = 2 * math.pi * i / sides + math.pi / 2
        prof.append((major + minor * math.cos(a), minor * math.sin(a), math.cos(a), math.sin(a)))
    # profile here goes around a circle; lathe expects top->bottom, but orientation only flips winding
    p, n = _lathe(prof, segs)
    return p, n


@lru_cache(maxsize=None)
def rounded_box(sx: float, sy: float, sz: float, radius: float, n: int = 4):
    """Box centred at origin with full extents (sx, sy, sz) and rounded edges."""
    radius = min(radius, sx / 2 - 1e-4, sy / 2 - 1e-4, sz / 2 - 1e-4)
    radius = max(radius, 1e-4)
    inner = np.array((sx / 2 - radius, sy / 2 - radius, sz / 2 - radius))
    pos, nrm = [], []
    g = np.linspace(-1.0, 1.0, 2 * n + 1)
    faces = [
        (0, 1, 2, 1.0), (0, 1, 2, -1.0),
        (1, 2, 0, 1.0), (1, 2, 0, -1.0),
        (2, 0, 1, 1.0), (2, 0, 1, -1.0),
    ]
    half = np.array((sx / 2, sy / 2, sz / 2))
    for (a, b, c, sgn) in faces:
        grid = np.zeros((len(g), len(g), 3))
        for i, u in enumerate(g):
            for j, v in enumerate(g):
                p = np.zeros(3)
                p[c] = sgn * half[c]
                p[a] = u * half[a]
                p[b] = v * half[b]
                grid[i, j] = p
        # project onto rounded surface
        q = np.clip(grid, -inner, inner)
        d = grid - q
        ln = np.linalg.norm(d, axis=2, keepdims=True)
        ln[ln < 1e-9] = 1e-9
        nn = d / ln
        pp = q + nn * radius
        for i in range(len(g) - 1):
            for j in range(len(g) - 1):
                quad = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                tri = [quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]]
                # orient outward
                p0, p1, p2 = pp[quad[0]], pp[quad[1]], pp[quad[2]]
                face_n = np.cross(p1 - p0, p2 - p0)
                if np.dot(face_n, nn[quad[0]] + nn[quad[2]]) < 0:
                    tri = [quad[0], quad[2], quad[1], quad[0], quad[3], quad[2]]
                for t in tri:
                    pos.append(pp[t])
                    nrm.append(nn[t])
    return np.asarray(pos, dtype="f4"), np.asarray(nrm, dtype="f4")


@lru_cache(maxsize=None)
def quad_xy(w: float = 1.0, h: float = 1.0):
    """Quad in the XY plane centred at origin facing +Z."""
    x, y = w / 2, h / 2
    p = np.array(((-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, -y, 0), (x, y, 0), (-x, y, 0)), dtype="f4")
    n = np.tile(np.array((0, 0, 1), dtype="f4"), (6, 1))
    return p, n


@lru_cache(maxsize=None)
def quad_xz(w: float = 1.0, d: float = 1.0):
    """Quad in the XZ plane (floor) facing +Y."""
    x, z = w / 2, d / 2
    p = np.array(((-x, 0, z), (x, 0, z), (x, 0, -z), (-x, 0, z), (x, 0, -z), (-x, 0, -z)), dtype="f4")
    n = np.tile(np.array((0, 1, 0), dtype="f4"), (6, 1))
    return p, n


@lru_cache(maxsize=None)
def wedge(sx: float, sy: float, sz: float):
    """Triangular prism (for shoulder fins / hair spikes) pointing +Y, base centred at origin."""
    x, z = sx / 2, sz / 2
    v = [(-x, 0, -z), (x, 0, -z), (0, sy, -z * 0.2), (-x, 0, z), (x, 0, z), (0, sy, z * 0.2)]
    tris = [(0, 2, 1), (3, 4, 5), (0, 3, 5), (0, 5, 2), (1, 2, 5), (1, 5, 4), (0, 1, 4), (0, 4, 3)]
    pos, nrm = [], []
    for a, b, c in tris:
        pa, pb, pc = np.array(v[a]), np.array(v[b]), np.array(v[c])
        n = np.cross(pb - pa, pc - pa)
        n = n / (np.linalg.norm(n) or 1.0)
        pos += [pa, pb, pc]
        nrm += [n, n, n]
    return np.asarray(pos, dtype="f4"), np.asarray(nrm, dtype="f4")


def transform(mesh, m: np.ndarray):
    """Apply a 4x4 transform to (positions, normals); normals use inverse-transpose."""
    p, n = mesh
    m3 = m[:3, :3]
    pp = p.astype("f8") @ m3.T + m[:3, 3]
    nm = np.linalg.inv(m3).T
    nn = n.astype("f8") @ nm.T
    ln = np.linalg.norm(nn, axis=1, keepdims=True)
    ln[ln < 1e-9] = 1.0
    nn /= ln
    if np.linalg.det(m3) < 0:
        # mirrored: flip winding
        pp = pp.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
        nn = nn.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
    return pp.astype("f4"), nn.astype("f4")
