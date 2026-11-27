"""Hierarchical fighter skeleton: bone layout, proportions, FK and two-bone leg IK.

Model space: the fighter faces +X, +Y is up, +Z points towards the camera.
"L" bones are the fighter's LEFT side = the LEAD side in an orthodox stance,
which sits on the far side (-Z) of the body.  "R" bones are the REAR side,
closest to the camera (+Z).  Facing left is a mirror (scale X by -1) of the
whole model, so the lead hand is always the far hand, like 2.5D fighters.
"""

from dataclasses import dataclass, field
import math

import numpy as np

from frontend.render3d.mathutil import euler_mat3

BONES = [
    # name,          parent
    ("root", -1),
    ("pelvis", 0),
    ("spine", 1),
    ("chest", 2),
    ("neck", 3),
    ("head", 4),
    ("shoulder_l", 3),
    ("upperarm_l", 6),
    ("forearm_l", 7),
    ("hand_l", 8),
    ("shoulder_r", 3),
    ("upperarm_r", 10),
    ("forearm_r", 11),
    ("hand_r", 12),
    ("thigh_l", 1),
    ("shin_l", 14),
    ("foot_l", 15),
    ("thigh_r", 1),
    ("shin_r", 17),
    ("foot_r", 18),
]
BONE_NAMES = [b[0] for b in BONES]
BONE_INDEX = {name: i for i, name in enumerate(BONE_NAMES)}
PARENTS = [b[1] for b in BONES]
NUM_BONES = len(BONES)
MAX_GPU_BONES = 48  # skeleton + cloth chain bones


@dataclass(frozen=True)
class Proportions:
    """Body measurements in metres."""

    pelvis_h: float = 0.98       # hip joint height when standing straight
    spine_len: float = 0.20
    chest_len: float = 0.26
    neck_len: float = 0.09
    head_r: float = 0.115
    shoulder_half: float = 0.20  # chest centre -> shoulder joint (Z)
    clav_up: float = 0.0
    upper_arm: float = 0.29
    forearm: float = 0.27
    hip_half: float = 0.10
    thigh: float = 0.45
    shin: float = 0.44
    ankle_h: float = 0.08
    # girths (used by model builders)
    arm_r: float = 0.050
    leg_r: float = 0.070
    torso_w: float = 0.34
    torso_d: float = 0.22
    fist_r: float = 0.055


def rest_offsets(p: Proportions) -> np.ndarray:
    """Per-bone translation from the parent joint, in the parent's frame."""
    off = np.zeros((NUM_BONES, 3), dtype="f8")
    hip = p.thigh + p.shin + p.ankle_h + 0.0
    off[BONE_INDEX["pelvis"]] = (0.0, hip, 0.0)
    off[BONE_INDEX["spine"]] = (0.0, 0.06, 0.0)
    off[BONE_INDEX["chest"]] = (0.0, p.spine_len, 0.0)
    off[BONE_INDEX["neck"]] = (0.0, p.chest_len, 0.0)
    off[BONE_INDEX["head"]] = (0.0, p.neck_len, 0.0)
    off[BONE_INDEX["shoulder_l"]] = (0.0, p.chest_len - 0.05, -0.05)
    off[BONE_INDEX["upperarm_l"]] = (0.0, p.clav_up, -(p.shoulder_half - 0.05))
    off[BONE_INDEX["forearm_l"]] = (0.0, -p.upper_arm, 0.0)
    off[BONE_INDEX["hand_l"]] = (0.0, -p.forearm, 0.0)
    off[BONE_INDEX["shoulder_r"]] = (0.0, p.chest_len - 0.05, 0.05)
    off[BONE_INDEX["upperarm_r"]] = (0.0, p.clav_up, (p.shoulder_half - 0.05))
    off[BONE_INDEX["forearm_r"]] = (0.0, -p.upper_arm, 0.0)
    off[BONE_INDEX["hand_r"]] = (0.0, -p.forearm, 0.0)
    off[BONE_INDEX["thigh_l"]] = (0.0, 0.0, -p.hip_half)
    off[BONE_INDEX["shin_l"]] = (0.0, -p.thigh, 0.0)
    off[BONE_INDEX["foot_l"]] = (0.0, -p.shin, 0.0)
    off[BONE_INDEX["thigh_r"]] = (0.0, 0.0, p.hip_half)
    off[BONE_INDEX["shin_r"]] = (0.0, -p.thigh, 0.0)
    off[BONE_INDEX["foot_r"]] = (0.0, -p.shin, 0.0)
    return off


# ---------------------------------------------------------------------------
# Pose channel layout (a pose is a flat float vector -> cheap blending)
# ---------------------------------------------------------------------------
# [0 : 3*NUM_BONES)          euler XYZ degrees per bone (R = Ry Rz Rx)
# PELVIS_POS (3)             pelvis offset (m) in root space
# FOOT_L (4), FOOT_R (4)     foot IK target (x, y, z) + foot yaw (deg), root space
# IKW_L, IKW_R               IK weights (0 = pure FK leg, 1 = foot planted at target)
# SMEAR                      stretch of the striking limb
# SMEAR_LIMB                 which limb (encoded, nearest-int: 0 none,1 arm L,2 arm R,3 leg L,4 leg R)
# GLOW                       extra emissive accent strength (specials / supers)
ROT_END = 3 * NUM_BONES
PELVIS_POS = ROT_END
FOOT_L = PELVIS_POS + 3
FOOT_R = FOOT_L + 4
IKW_L = FOOT_R + 4
IKW_R = IKW_L + 1
SMEAR = IKW_R + 1
SMEAR_LIMB = SMEAR + 1
GLOW = SMEAR_LIMB + 1
ROOT_POS = GLOW + 1          # root offset (m) applied around the body pivot (falls, lunges)
POSE_SIZE = ROOT_POS + 3

SMEAR_LIMBS = {
    1: ("forearm_l", "hand_l"),
    2: ("forearm_r", "hand_r"),
    3: ("shin_l", "foot_l"),
    4: ("shin_r", "foot_r"),
}


def rot_slice(bone: str) -> slice:
    i = BONE_INDEX[bone] * 3
    return slice(i, i + 3)


@dataclass
class Skeleton:
    """Per-fighter skeleton instance (offsets cached from proportions)."""

    props: Proportions
    offsets: np.ndarray = field(init=False)
    model: np.ndarray = field(init=False)  # (NUM_BONES, 4, 4) model-space matrices

    def __post_init__(self):
        self.offsets = rest_offsets(self.props)
        self.model = np.tile(np.identity(4), (NUM_BONES, 1, 1))

    # -------------------------------------------------------------------
    def solve(self, pose: np.ndarray, floor_clamp: bool = True, lift: float = 0.0) -> np.ndarray:
        """Forward kinematics + leg IK.  Returns model-space bone matrices."""
        M = self.model
        off = self.offsets
        rots = [None] * NUM_BONES
        rots[0] = np.identity(3)  # root rotation is applied by the caller around the body pivot
        for b in range(1, NUM_BONES):
            i = 3 * b
            rots[b] = euler_mat3(pose[i], pose[i + 1], pose[i + 2])
        for b in range(NUM_BONES):
            par = PARENTS[b]
            local = np.identity(4)
            local[:3, :3] = rots[b]
            t = off[b]
            if b == 1:
                t = t + pose[PELVIS_POS:PELVIS_POS + 3]
            local[:3, 3] = t
            if par < 0:
                M[b] = local
            else:
                M[b] = M[par] @ local
        # Legs: blend FK result with an IK solve towards the foot targets
        for side, fslot, wslot in (("l", FOOT_L, IKW_L), ("r", FOOT_R, IKW_R)):
            w = float(pose[wslot])
            if w > 1e-3:
                self._leg_ik(side, pose[fslot:fslot + 3], float(pose[fslot + 3]), w)
        # Floor clamp: a foot never sinks below the floor (blends / crouches / lunges)
        if floor_clamp and abs(pose[0]) + abs(pose[1]) + abs(pose[2]) < 1.0:
            floor = -float(pose[ROOT_POS + 1]) - lift
            for side, fslot in (("l", FOOT_L), ("r", FOOT_R)):
                ia = BONE_INDEX["foot_" + side]
                ankle = M[ia][:3, 3]
                need = floor + self.props.ankle_h - 0.005
                if ankle[1] < need:
                    tgt = (float(ankle[0]), need - self.props.ankle_h + 0.005, float(ankle[2]))
                    self._leg_ik(side, tgt, float(pose[fslot + 3]), 1.0)
        # Smear: stretch the striking limb along its axis
        sm = float(pose[SMEAR])
        limb = int(round(float(pose[SMEAR_LIMB])))
        if sm > 1e-3 and limb in SMEAR_LIMBS:
            a, b2 = SMEAR_LIMBS[limb]
            ia, ib = BONE_INDEX[a], BONE_INDEX[b2]
            s = 1.0 + sm
            # scale bone a along its -Y axis and push the child outwards
            seg = M[ia][:3, 1].copy()
            length = self.offsets[ib][1]  # negative (child is along -Y)
            M[ia] = M[ia].copy()
            M[ia][:3, 1] *= s
            M[ia][:3, 0] *= 1.0 - sm * 0.25
            M[ia][:3, 2] *= 1.0 - sm * 0.25
            M[ib] = M[ib].copy()
            M[ib][:3, 3] += seg * length * (s - 1.0)
        return M

    # -------------------------------------------------------------------
    def _leg_ik(self, side: str, target, foot_yaw: float, weight: float) -> None:
        M = self.model
        p = self.props
        it, ish, ift = BONE_INDEX["thigh_" + side], BONE_INDEX["shin_" + side], BONE_INDEX["foot_" + side]
        hip = M[it][:3, 3].copy()
        ankle = np.array((target[0], target[1] + p.ankle_h, target[2]), dtype="f8")
        l1, l2 = p.thigh, p.shin
        d_vec = ankle - hip
        d = float(np.linalg.norm(d_vec))
        if d < 1e-6:
            return
        u = d_vec / d
        d = min(max(d, abs(l1 - l2) + 1e-3), l1 + l2 - 1e-4)
        cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
        cos_a = max(-1.0, min(1.0, cos_a))
        sin_a = math.sqrt(1.0 - cos_a * cos_a)
        yaw = math.radians(foot_yaw)
        pole = np.array((math.cos(yaw), 0.0, -math.sin(yaw)))
        # knees point roughly where the foot points, a bit outward
        pole = pole + np.array((0.0, 0.0, -0.25 if side == "l" else 0.25))
        v = pole - u * float(np.dot(pole, u))
        nv = float(np.linalg.norm(v))
        if nv < 1e-6:
            v = np.array((1.0, 0.0, 0.0))
        else:
            v /= nv
        knee = hip + l1 * (cos_a * u + sin_a * v)
        ankle_pos = hip + u * d

        def frame(direction, fwd):
            y = -direction / (np.linalg.norm(direction) or 1.0)
            x = fwd - y * float(np.dot(fwd, y))
            nx = float(np.linalg.norm(x))
            x = x / nx if nx > 1e-6 else np.array((1.0, 0.0, 0.0))
            z = np.cross(x, y)
            r = np.empty((3, 3))
            r[:, 0], r[:, 1], r[:, 2] = x, y, z
            return r

        thigh_w = frame(knee - hip, v)
        shin_w = frame(ankle_pos - knee, v)
        cy, sy = math.cos(yaw), math.sin(yaw)
        foot_w = np.array(((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)))

        if weight < 0.999:
            from frontend.render3d.mathutil import mat3_blend
            thigh_w = mat3_blend(M[it][:3, :3], thigh_w, weight)
            shin_w = mat3_blend(M[ish][:3, :3], shin_w, weight)
            foot_w = mat3_blend(M[ift][:3, :3], foot_w, weight)
        M[it] = M[it].copy()
        M[it][:3, :3] = thigh_w
        M[ish] = np.identity(4)
        M[ish][:3, :3] = shin_w
        M[ish][:3, 3] = M[it][:3, 3] + thigh_w @ self.offsets[ish]
        M[ift] = np.identity(4)
        M[ift][:3, :3] = foot_w
        M[ift][:3, 3] = M[ish][:3, 3] + shin_w @ self.offsets[ift]
