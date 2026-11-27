"""CPU-simulated billboard particles + ribbon trails (vectorised with numpy).

Particle kinds (see PARTICLE_FS): 0 glow dot, 1 velocity streak spark, 2 shock ring,
3 smoke/dust (alpha blended), 4 star flash, 5 ground ring, 6 speed line.
"""

import math

import numpy as np

CAP = 4096


class Particles:
    def __init__(self, seed: int = 7):
        self.rng = np.random.default_rng(seed)
        self.pos = np.zeros((CAP, 3), dtype="f4")
        self.vel = np.zeros((CAP, 3), dtype="f4")
        self.col = np.zeros((CAP, 4), dtype="f4")
        self.size = np.zeros(CAP, dtype="f4")
        self.grow = np.zeros(CAP, dtype="f4")
        self.life = np.zeros(CAP, dtype="f4")
        self.max_life = np.ones(CAP, dtype="f4")
        self.kind = np.zeros(CAP, dtype="f4")
        self.grav = np.zeros(CAP, dtype="f4")
        self.drag = np.zeros(CAP, dtype="f4")
        self.fade_in = np.zeros(CAP, dtype="f4")
        self.n = 0
        # instance buffer layout: pos3 vel3 col4 size kind (12 floats)
        self.inst = np.zeros((CAP, 12), dtype="f4")

    def clear(self):
        self.n = 0

    def emit(self, pos, vel, col, size, life, kind, grav=0.0, drag=0.0, grow=0.0, fade_in=0.0):
        """Emit k particles; arguments may be scalars or arrays of length k."""
        pos = np.atleast_2d(np.asarray(pos, dtype="f4"))
        k = len(pos)
        if k == 0:
            return
        if self.n + k > CAP:
            k = CAP - self.n
            if k <= 0:
                return
            pos = pos[:k]
        s = slice(self.n, self.n + k)

        def arr(v, shape):
            a = np.asarray(v, dtype="f4")
            if a.ndim == 0 or a.shape == (shape,) and shape != k:
                return np.broadcast_to(a, (k, shape) if shape > 1 else (k,))
            return a[:k]

        self.pos[s] = pos
        self.vel[s] = np.broadcast_to(np.asarray(vel, dtype="f4"), (k, 3)) if np.ndim(vel) == 1 else np.asarray(vel, "f4")[:k]
        self.col[s] = np.broadcast_to(np.asarray(col, dtype="f4"), (k, 4)) if np.ndim(col) == 1 else np.asarray(col, "f4")[:k]
        self.size[s] = arr(size, 1)
        self.life[s] = arr(life, 1)
        self.max_life[s] = arr(life, 1)
        self.kind[s] = kind
        self.grav[s] = grav
        self.drag[s] = drag
        self.grow[s] = grow
        self.fade_in[s] = fade_in
        self.n += k

    def update(self, dt: float):
        n = self.n
        if n == 0:
            return
        sl = slice(0, n)
        self.vel[sl, 1] -= self.grav[sl] * dt
        self.vel[sl] *= (1.0 - np.minimum(self.drag[sl] * dt, 0.95))[:, None]
        self.pos[sl] += self.vel[sl] * dt
        self.size[sl] += self.grow[sl] * dt
        self.life[sl] -= dt
        # bounce sparks on the floor
        below = self.pos[sl, 1] < 0.01
        if below.any():
            idx = np.nonzero(below)[0]
            self.pos[idx, 1] = 0.01
            self.vel[idx, 1] *= -0.35
            self.vel[idx, 0] *= 0.6
            self.vel[idx, 2] *= 0.6
        alive = self.life[sl] > 0
        if not alive.all():
            idx = np.nonzero(alive)[0]
            m = len(idx)
            for a in (self.pos, self.vel, self.col, self.size, self.grow, self.life, self.max_life, self.kind,
                      self.grav, self.drag, self.fade_in):
                a[:m] = a[idx]
            self.n = m

    def build(self):
        """Return (additive_instances, alpha_instances) float32 arrays."""
        n = self.n
        if n == 0:
            return self.inst[:0], self.inst[:0]
        sl = slice(0, n)
        t = np.clip(self.life[sl] / np.maximum(self.max_life[sl], 1e-4), 0.0, 1.0)
        fade = t.copy()
        fi = self.fade_in[sl]
        if fi.any():
            age = 1.0 - t
            fade = np.where(fi > 0, np.minimum(1.0, age / np.maximum(fi, 1e-4)) * t, t)
        inst = self.inst
        inst[sl, 0:3] = self.pos[sl]
        inst[sl, 3:6] = self.vel[sl]
        inst[sl, 6:9] = self.col[sl, :3]
        inst[sl, 9] = self.col[sl, 3] * fade
        inst[sl, 10] = np.maximum(self.size[sl], 0.0)
        inst[sl, 11] = self.kind[sl]
        smoke = self.kind[sl] == 3
        if smoke.any():
            return inst[sl][~smoke], inst[sl][smoke]
        return inst[sl], inst[:0]

    # ------------------------------------------------------------------
    # Effect recipes
    # ------------------------------------------------------------------
    def _dirs(self, k, main=None, spread=1.0):
        d = self.rng.normal(size=(k, 3)).astype("f4")
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
        if main is not None:
            m = np.asarray(main, dtype="f4")
            m = m / (np.linalg.norm(m) + 1e-6)
            d = d * spread + m
            d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
        return d

    def hit_sparks(self, pos, direction, colour, strength=0.5, kind="hit"):
        """Impact burst: streak sparks, star flash, shock ring, embers."""
        rng = self.rng
        s = float(strength)
        count = int(14 + 40 * s)
        d = self._dirs(count, main=direction, spread=1.1)
        speed = rng.uniform(2.5, 7.0 + 8.0 * s, size=(count, 1)).astype("f4")
        hot = np.array((1.0, 0.95, 0.85, 1.0), dtype="f4")
        c = np.array((*colour, 1.0), dtype="f4")
        mix = rng.uniform(0, 1, size=(count, 1)).astype("f4")
        cols = hot * (1 - mix) + c * mix
        cols[:, :3] *= 3.0 + 3.0 * s
        self.emit(np.repeat(np.asarray(pos, "f4")[None], count, 0), d * speed, cols,
                  rng.uniform(0.025, 0.05 + 0.03 * s, count), rng.uniform(0.18, 0.38 + 0.2 * s, count),
                  kind=1, grav=9.0, drag=2.0)
        # bright star flash
        self.emit([pos], (0, 0, 0), (c[0] * 2 + 1.5, c[1] * 2 + 1.5, c[2] * 2 + 1.5, 1.0), 0.25 + 0.35 * s,
                  0.10 + 0.05 * s, kind=4, grow=1.0)
        self.emit([pos], (0, 0, 0), (c[0] * 3, c[1] * 3, c[2] * 3, 0.8), 0.35 + 0.35 * s, 0.12, kind=0, grow=1.5)
        # shock ring
        self.emit([pos], (0, 0, 0), (c[0] * 2.5, c[1] * 2.5, c[2] * 2.5, 0.9), 0.12, 0.2 + 0.06 * s, kind=2,
                  grow=2.5 + 3.0 * s)
        if s > 0.6:
            self.emit([pos], (0, 0, 0), (2.4, 2.2, 2.0, 0.6), 0.1, 0.26, kind=2, grow=4.0 + 2.0 * s)
            # lingering embers
            k = 16
            d2 = self._dirs(k)
            self.emit(np.repeat(np.asarray(pos, "f4")[None], k, 0), d2 * rng.uniform(0.5, 2.5, (k, 1)),
                      (c[0] * 3, c[1] * 3, c[2] * 3, 1.0), rng.uniform(0.02, 0.04, k),
                      rng.uniform(0.5, 1.0, k), kind=0, grav=-0.6, drag=1.5)

    def block_sparks(self, pos, direction, strength=0.4):
        rng = self.rng
        count = int(10 + 20 * strength)
        d = self._dirs(count, main=direction, spread=1.4)
        cols = np.tile(np.array((1.2, 2.6, 4.0, 1.0), "f4"), (count, 1))
        self.emit(np.repeat(np.asarray(pos, "f4")[None], count, 0), d * rng.uniform(2.0, 6.0, (count, 1)), cols,
                  rng.uniform(0.02, 0.04, count), rng.uniform(0.15, 0.3, count), kind=1, grav=6.0, drag=3.0)
        self.emit([pos], (0, 0, 0), (1.0, 2.2, 3.6, 0.9), 0.12, 0.2, kind=2, grow=4.0)
        self.emit([pos], (0, 0, 0), (1.5, 2.5, 3.5, 0.8), 0.35, 0.09, kind=0, grow=1.0)

    def parry_flash(self, pos):
        self.emit([pos], (0, 0, 0), (5.0, 4.2, 2.0, 1.0), 0.8, 0.18, kind=4, grow=3.0)
        self.emit([pos], (0, 0, 0), (4.0, 3.4, 1.5, 0.9), 0.2, 0.3, kind=2, grow=5.0)
        k = 24
        d = self._dirs(k)
        self.emit(np.repeat(np.asarray(pos, "f4")[None], k, 0), d * 6.0, (4.0, 3.5, 1.8, 1.0), 0.035, 0.25,
                  kind=1, drag=4.0)

    def burst(self, pos, colour):
        c = colour
        self.emit([pos], (0, 0, 0), (c[0] * 4, c[1] * 4, c[2] * 4, 1.0), 0.3, 0.45, kind=2, grow=7.0)
        self.emit([pos], (0, 0, 0), (3.0, 3.0, 3.0, 0.7), 0.2, 0.3, kind=2, grow=5.0)
        k = 60
        d = self._dirs(k)
        self.emit(np.repeat(np.asarray(pos, "f4")[None], k, 0), d * self.rng.uniform(4, 10, (k, 1)),
                  (c[0] * 4, c[1] * 4, c[2] * 4, 1.0), 0.05, self.rng.uniform(0.3, 0.6, k), kind=1, drag=2.5)

    def dust(self, pos, count=8, spread=0.35, colour=(0.75, 0.70, 0.62), strength=1.0):
        rng = self.rng
        p = np.repeat(np.asarray(pos, "f4")[None], count, 0)
        p[:, 0] += rng.uniform(-spread, spread, count)
        p[:, 2] += rng.uniform(-0.15, 0.15, count)
        p[:, 1] = 0.05
        v = np.zeros((count, 3), "f4")
        v[:, 0] = rng.uniform(-1.5, 1.5, count) * strength
        v[:, 1] = rng.uniform(0.2, 0.9, count)
        v[:, 2] = rng.uniform(-0.4, 0.4, count)
        self.emit(p, v, (*colour, 0.55), rng.uniform(0.12, 0.25, count) * (0.7 + 0.5 * strength),
                  rng.uniform(0.35, 0.7, count), kind=3, drag=3.0, grow=0.6)

    def ground_ring(self, pos, colour=(1.0, 0.9, 0.7), size=0.4, grow=5.0, life=0.3):
        p = (pos[0], 0.02, pos[2])
        self.emit([p], (0, 0, 0), (colour[0] * 2, colour[1] * 2, colour[2] * 2, 0.8), size, life, kind=5, grow=grow)

    def aura(self, pos, colour, rate=4):
        rng = self.rng
        p = np.repeat(np.asarray(pos, "f4")[None], rate, 0)
        p += rng.normal(0, 0.18, (rate, 3)).astype("f4") * np.array((1.0, 2.2, 0.6), "f4")
        v = np.zeros((rate, 3), "f4")
        v[:, 1] = rng.uniform(0.8, 2.2, rate)
        self.emit(p, v, (colour[0] * 3, colour[1] * 3, colour[2] * 3, 0.9), rng.uniform(0.03, 0.07, rate),
                  rng.uniform(0.3, 0.6, rate), kind=0, drag=1.0, fade_in=0.3)

    def speed_lines(self, center, colour=(1.0, 0.9, 0.6), count=10):
        rng = self.rng
        ang = rng.uniform(0, 2 * math.pi, count)
        r = rng.uniform(1.2, 2.5, count)
        p = np.zeros((count, 3), "f4")
        p[:, 0] = center[0] + np.cos(ang) * r
        p[:, 1] = center[1] + np.sin(ang) * r * 0.6
        p[:, 2] = center[2] + 0.5
        v = np.zeros((count, 3), "f4")
        v[:, 0] = -np.cos(ang) * 12
        v[:, 1] = -np.sin(ang) * 7
        self.emit(p, v, (colour[0] * 2, colour[1] * 2, colour[2] * 2, 0.8), 0.06, 0.12, kind=1)


class Trail:
    """Ribbon following a striking fist/foot (tip + a point up the limb)."""

    N = 12

    def __init__(self):
        self.tips = []
        self.bases = []
        self.ages = []

    def push(self, tip, base, active: bool):
        if active:
            self.tips.append(np.asarray(tip, "f4").copy())
            self.bases.append(np.asarray(base, "f4").copy())
            self.ages.append(0.0)
        if len(self.tips) > self.N:
            self.tips.pop(0)
            self.bases.pop(0)
            self.ages.pop(0)

    def age(self, dt):
        for i in range(len(self.ages)):
            self.ages[i] += dt
        while self.ages and self.ages[0] > 0.16:
            self.tips.pop(0)
            self.bases.pop(0)
            self.ages.pop(0)

    def build(self, colour, intensity=1.0):
        """Triangle list (pos3 col4) for the ribbon."""
        n = len(self.tips)
        if n < 2:
            return None
        verts = []
        for i in range(n - 1):
            a0 = 1.0 - self.ages[i] / 0.16
            a1 = 1.0 - self.ages[i + 1] / 0.16
            f0 = (i / (n - 1)) * a0
            f1 = ((i + 1) / (n - 1)) * a1
            t0, t1 = self.tips[i], self.tips[i + 1]
            b0 = t0 + (self.bases[i] - t0) * 0.55
            b1 = t1 + (self.bases[i + 1] - t1) * 0.55
            c0 = (colour[0] * 2.5 * intensity, colour[1] * 2.5 * intensity, colour[2] * 2.5 * intensity)
            ct0 = (*c0, max(0.0, f0))
            ct1 = (*c0, max(0.0, f1))
            cb0 = (*c0, 0.0)
            cb1 = (*c0, 0.0)
            verts += [(*t0, *ct0), (*b0, *cb0), (*t1, *ct1), (*t1, *ct1), (*b0, *cb0), (*b1, *cb1)]
        return np.asarray(verts, dtype="f4")
