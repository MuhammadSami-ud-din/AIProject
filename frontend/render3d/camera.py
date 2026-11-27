"""2.5D fight camera: side-on, slightly elevated, tracks the fighters' midpoint,
zooms with their distance, adds directional 3D shake, dutch tilt / push-in on
heavy hits, super-freeze push-in, KO orbit and a round-intro sweep."""

import math

import numpy as np

from frontend.render3d.mathutil import clamp, look_at, perspective, rot_z


class FightCamera:
    FOVY = 30.0

    def __init__(self, width: int, height: int):
        self.aspect = width / float(height)
        self.reset()

    def reset(self):
        self.cx = 0.0
        self.cy = 1.05
        self.dist = 7.6
        self.shake = 0.0
        self.shake_dir = np.zeros(3)
        self.shake_t = 0.0
        self.tilt = 0.0
        self.push = 0.0
        self.orbit = 0.0
        self.intro = 0.0
        self.focus_override = None
        self.override = None  # (eye, target) for screenshots / debugging
        self.eye = np.array((0.0, 2.0, 8.0))
        self.target = np.array((0.0, 1.0, 0.0))
        self.view = np.identity(4)
        self.proj = perspective(self.FOVY, self.aspect, 0.1, 80.0)
        self.viewproj = self.proj.copy()

    def kick(self, amount: float, direction=(1.0, 0.0, 0.0), tilt: float = 0.0, push: float = 0.0):
        self.shake = max(self.shake, amount)
        d = np.asarray(direction, dtype="f8")
        self.shake_dir = d / (np.linalg.norm(d) or 1.0)
        self.tilt += tilt
        self.push = max(self.push, push)

    def update(self, x1: float, x2: float, y1: float, y2: float, dt: float, super_focus=None,
               ko_focus=None, intro: float = 0.0):
        """x/y in world metres. intro: 1 -> 0 over the round intro sweep."""
        mid = (x1 + x2) * 0.5
        span = abs(x1 - x2)
        # distance needed to keep both fighters (plus margin) in the horizontal FOV
        half_w_needed = span * 0.5 + 1.7
        tan_h = math.tan(math.radians(self.FOVY) * 0.5) * self.aspect
        want_dist = clamp(half_w_needed / tan_h, 7.2, 12.5)
        want_y = 1.0 + max(y1, y2) * 0.45
        want_x = clamp(mid, -2.3, 2.3)
        k = 1.0 - math.exp(-dt * 6.0)
        if super_focus is not None:
            want_x = super_focus[0]
            want_y = super_focus[1] * 0.9 + 0.35
            want_dist = 4.4
            k = 1.0 - math.exp(-dt * 10.0)
        if ko_focus is not None:
            want_x = ko_focus[0]
            want_y = 0.7
            want_dist = 4.8
            k = 1.0 - math.exp(-dt * 4.0)
        self.cx += (want_x - self.cx) * k
        self.cy += (want_y - self.cy) * k
        self.dist += (want_dist - self.dist) * k
        self.push *= math.exp(-dt * 7.0)
        self.tilt *= math.exp(-dt * 6.0)
        self.shake *= math.exp(-dt * 9.0)
        self.shake_t += dt
        self.orbit = self.orbit + dt * 0.35 if ko_focus is not None else self.orbit * math.exp(-dt * 3.0)
        self.intro = intro

        d = self.dist * (1.0 - self.push * 0.18)
        yaw = math.sin(self.orbit) * 0.55 + intro * 0.9
        height = 1.05 + 0.5 * (d / 8.0) + intro * 1.4
        ex = self.cx + math.sin(yaw) * d
        ez = math.cos(yaw) * d
        eye = np.array((ex, self.cy + height * 0.62, ez))
        target = np.array((self.cx, self.cy, 0.0))
        if self.shake > 1e-3:
            s = self.shake
            w = self.shake_t * 55.0
            jitter = np.array((math.sin(w * 1.3), math.sin(w * 1.7 + 1.0), 0.0)) * 0.5
            off = (self.shake_dir * math.sin(w) + jitter) * s * 0.06
            eye = eye + off
            target = target + off * 0.6
        if self.override is not None:
            eye = np.asarray(self.override[0], dtype="f8")
            target = np.asarray(self.override[1], dtype="f8")
        self.eye, self.target = eye, target
        view = look_at(eye, target)
        if abs(self.tilt) > 1e-3:
            view = rot_z(self.tilt) @ view
        self.view = view
        self.viewproj = self.proj @ view
        return self.viewproj

    def project(self, p, width: int, height: int):
        v = self.viewproj @ np.array((p[0], p[1], p[2], 1.0))
        if v[3] <= 1e-5:
            return None
        x = (v[0] / v[3] * 0.5 + 0.5) * width
        y = (1.0 - (v[1] / v[3] * 0.5 + 0.5)) * height
        return x, y
