"""Small linear-algebra helpers for the 3D renderer.

Convention: matrices are numpy float32/float64 4x4, row-major, used as v' = M @ v.
Upload to GL with ``gl_bytes(M)`` (transposes to column-major).
World: +X = right along the fighting plane, +Y = up, +Z = towards the camera.
Units: metres (1 m = 100 engine pixels).
"""

import math

import numpy as np

PX_TO_M = 0.01  # engine pixels -> metres


def gl_bytes(m: np.ndarray) -> bytes:
    return np.ascontiguousarray(m.T, dtype="f4").tobytes()


def identity() -> np.ndarray:
    return np.identity(4, dtype="f8")


def translate(x: float, y: float, z: float) -> np.ndarray:
    m = np.identity(4, dtype="f8")
    m[0, 3] = x
    m[1, 3] = y
    m[2, 3] = z
    return m


def scale(x: float, y: float, z: float) -> np.ndarray:
    m = np.identity(4, dtype="f8")
    m[0, 0] = x
    m[1, 1] = y
    m[2, 2] = z
    return m


def rot_x(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4, dtype="f8")
    m[1, 1] = c
    m[1, 2] = -s
    m[2, 1] = s
    m[2, 2] = c
    return m


def rot_y(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4, dtype="f8")
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m


def rot_z(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    m = np.identity(4, dtype="f8")
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    return m


def euler_mat3(x: float, y: float, z: float) -> np.ndarray:
    """Rotation R = Ry(y) @ Rz(z) @ Rx(x), angles in degrees (3x3)."""
    ax, ay, az = math.radians(x), math.radians(y), math.radians(z)
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    # Rz @ Rx
    # Rx = [[1,0,0],[0,cx,-sx],[0,sx,cx]]
    # Rz = [[cz,-sz,0],[sz,cz,0],[0,0,1]]
    zx = (
        (cz, -sz * cx, sz * sx),
        (sz, cz * cx, -cz * sx),
        (0.0, sx, cx),
    )
    # Ry = [[cy,0,sy],[0,1,0],[-sy,0,cy]]
    r = np.empty((3, 3), dtype="f8")
    for j in range(3):
        a0, a1, a2 = zx[0][j], zx[1][j], zx[2][j]
        r[0, j] = cy * a0 + sy * a2
        r[1, j] = a1
        r[2, j] = -sy * a0 + cy * a2
    return r


def euler(x: float, y: float, z: float) -> np.ndarray:
    m = np.identity(4, dtype="f8")
    m[:3, :3] = euler_mat3(x, y, z)
    return m


def compose(t=(0.0, 0.0, 0.0), r=(0.0, 0.0, 0.0), s=(1.0, 1.0, 1.0)) -> np.ndarray:
    """T @ R(euler deg) @ S."""
    m = np.identity(4, dtype="f8")
    m[:3, :3] = euler_mat3(*r) * np.asarray(s, dtype="f8")[None, :]
    m[0, 3], m[1, 3], m[2, 3] = t
    return m


def perspective(fovy_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4), dtype="f8")
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def ortho(l, r, b, t, n, f) -> np.ndarray:
    m = np.identity(4, dtype="f8")
    m[0, 0] = 2.0 / (r - l)
    m[1, 1] = 2.0 / (t - b)
    m[2, 2] = -2.0 / (f - n)
    m[0, 3] = -(r + l) / (r - l)
    m[1, 3] = -(t + b) / (t - b)
    m[2, 3] = -(f + n) / (f - n)
    return m


def normalize(v) -> np.ndarray:
    v = np.asarray(v, dtype="f8")
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def look_at(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    eye = np.asarray(eye, dtype="f8")
    f = normalize(np.asarray(target, dtype="f8") - eye)
    s = normalize(np.cross(f, up))
    u = np.cross(s, f)
    m = np.identity(4, dtype="f8")
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -float(np.dot(s, eye))
    m[1, 3] = -float(np.dot(u, eye))
    m[2, 3] = float(np.dot(f, eye))
    return m


# ---------------------------------------------------------------------------
# Quaternions (w, x, y, z)
# ---------------------------------------------------------------------------

def quat_from_mat3(m: np.ndarray):
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        return (0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s)
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        return ((m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s)
    if m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        return ((m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s)
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    return ((m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s)


def mat3_from_quat(q) -> np.ndarray:
    w, x, y, z = q
    return np.array((
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    ), dtype="f8")


def quat_nlerp(a, b, t: float):
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    sgn = -1.0 if dot < 0 else 1.0
    q = [a[i] + (b[i] * sgn - a[i]) * t for i in range(4)]
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def mat3_blend(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    if t <= 0.0:
        return a
    if t >= 1.0:
        return b
    return mat3_from_quat(quat_nlerp(quat_from_mat3(a), quat_from_mat3(b), t))


def rotation_between(a, b) -> np.ndarray:
    """3x3 rotation taking unit vector a onto unit vector b."""
    a = normalize(a)
    b = normalize(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -0.99999:
        # 180 degrees: pick any orthogonal axis
        axis = normalize(np.cross(a, (1.0, 0.0, 0.0)) if abs(a[0]) < 0.9 else np.cross(a, (0.0, 1.0, 0.0)))
        x, y, z = axis
        return np.array(((2 * x * x - 1, 2 * x * y, 2 * x * z),
                         (2 * x * y, 2 * y * y - 1, 2 * y * z),
                         (2 * x * z, 2 * y * z, 2 * z * z - 1)), dtype="f8")
    vx = np.array(((0, -v[2], v[1]), (v[2], 0, -v[0]), (-v[1], v[0], 0)), dtype="f8")
    return np.identity(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def smoothstep(e0: float, e1: float, x: float) -> float:
    t = clamp((x - e0) / (e1 - e0), 0.0, 1.0) if e1 != e0 else (1.0 if x >= e1 else 0.0)
    return t * t * (3 - 2 * t)
