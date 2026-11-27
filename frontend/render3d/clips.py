"""Animation data: stances and keyframed clips for every move.

Poses are dicts of *absolute* overrides on top of a character's guard stance:

  bone keys   pelvis spine chest neck head sh_l ua_l fa_l hd_l sh_r ua_r fa_r hd_r
              th_l sn_l ft_l th_r sn_r ft_r root   -> (x, y, z) euler degrees
              (R = Ry @ Rz @ Rx; facing +X: z>0 swings a limb forwards/up,
               y<0 turns the body towards the camera, z<0 leans the spine forwards)
  pp          pelvis offset (x, y, z) metres
  rp          root offset (x, y, z) metres (whole body, used for hops / falls)
  fl, fr      foot IK targets (x, y, z, yaw)   ikl, ikr  IK weight
  smear       striking-limb stretch            limb      1 lead hand, 2 rear hand,
                                                         3 lead foot, 4 rear foot
  glow        accent emissive boost

Move clips are keyed by *phase*: ("s", f) startup fraction, ("a", f) active,
("r", f) recovery, ("t", n) absolute frame.  The sampler maps those onto the
move's real frame data so the strike pose lands exactly on the first active
frame and the limb returns during recovery.
"""

from backend.ai.actions import Action

S, A, R, T = "s", "a", "r", "t"

# ---------------------------------------------------------------------------
# Stances
# ---------------------------------------------------------------------------
BASE_GUARD = dict(
    pelvis=(0, -30, 0), spine=(0, -8, -4), chest=(0, -8, -6), neck=(0, 18, 2), head=(0, 18, 4),
    sh_l=(0, 0, 0), sh_r=(0, 0, 0),
    ua_l=(8, 42, 55), fa_l=(0, 0, 100), hd_l=(0, 0, -10),
    ua_r=(-12, 30, 28), fa_r=(0, 0, 135), hd_r=(0, 0, -10),
    th_l=(0, 25, 10), sn_l=(0, 0, -20), ft_l=(0, 0, 0),
    th_r=(0, 25, -5), sn_r=(0, 0, -20), ft_r=(0, 0, 0),
    root=(0, 0, 0),
    pp=(0.0, -0.09, 0.0), rp=(0.0, 0.0, 0.0),
    fl=(0.27, 0.0, -0.09, -8), fr=(-0.25, 0.0, 0.13, -55), ikl=1.0, ikr=1.0,
    smear=0.0, limb=0, glow=0.0,
)

STANCES = {
    "Golden": dict(
        pelvis=(0, -28, 0), spine=(0, -6, -2), chest=(0, -8, -3), pp=(0.0, -0.065, 0.0),
        ua_l=(6, 40, 72), fa_l=(0, 0, 58), hd_l=(0, 0, 40),
        ua_r=(-28, 10, -12), fa_r=(0, 0, 100), hd_r=(0, 0, 10),
        fl=(0.25, 0.0, -0.09, -10), fr=(-0.24, 0.0, 0.12, -55),
    ),
    "Crimson": dict(
        chest=(0, -8, -11), spine=(0, -8, -6), pp=(0.0, -0.11, 0.0),
        ua_l=(8, 44, 62), fa_l=(0, 0, 112), ua_r=(-16, 32, 38), fa_r=(0, 0, 140),
        head=(0, 18, -2),
    ),
    "Shadow": dict(
        pelvis=(0, -34, 0), chest=(0, -8, -12), spine=(0, -8, -8), pp=(0.0, -0.19, 0.0),
        ua_l=(10, 46, 62), fa_l=(0, 0, 38), hd_l=(0, 0, 25),
        ua_r=(-22, 30, 62), fa_r=(0, 0, 122),
        fl=(0.37, 0.0, -0.10, -5), fr=(-0.33, 0.0, 0.15, -62), head=(0, 18, 8),
    ),
    "Steel": dict(
        pelvis=(0, -26, 0), chest=(0, -6, -3), spine=(0, -6, -2), pp=(0.0, -0.10, 0.0),
        ua_l=(16, 44, 42), fa_l=(0, 0, 96), ua_r=(-16, 36, 32), fa_r=(0, 0, 104),
        fl=(0.30, 0.0, -0.15, -10), fr=(-0.28, 0.0, 0.19, -50),
    ),
}

CROUCH = dict(
    pp=(-0.02, -0.40, 0.0), chest=(0, -8, -16), spine=(0, -6, -10), head=(0, 16, 14),
    fl=(0.30, 0.0, -0.13, -12), fr=(-0.27, 0.0, 0.17, -62),
    ua_l=(8, 42, 45), fa_l=(0, 0, 105), ua_r=(-14, 30, 25), fa_r=(0, 0, 130),
)

BLOCK_HIGH = dict(
    chest=(0, -16, -12), spine=(0, -10, -6), neck=(0, 18, -8), head=(0, 18, -6), pp=(-0.03, -0.13, 0.0),
    ua_l=(4, 42, 82), fa_l=(0, 0, 124), hd_l=(0, 0, 0), ua_r=(-8, 40, 66), fa_r=(0, 0, 128), hd_r=(0, 0, 0),
)
BLOCK_LOW = dict(
    CROUCH, chest=(0, -16, -20),
    ua_l=(10, 42, 32), fa_l=(0, 0, 72), ua_r=(-10, 36, 28), fa_r=(0, 0, 84), head=(0, 18, 6),
)

WALK_STRIDE = 0.80   # metres travelled per full walk cycle

# ---------------------------------------------------------------------------
# Reaction / state poses
# ---------------------------------------------------------------------------
HIT_HIGH = dict(
    neck=(0, 18, 26), head=(0, 18, 28), chest=(0, -22, 20), spine=(0, -10, 10),
    ua_l=(35, 30, 35), fa_l=(0, 0, 55), ua_r=(-40, 15, 10), fa_r=(0, 0, 45), pp=(-0.07, -0.10, 0.0),
)
HIT_MID = dict(
    chest=(0, -14, -30), spine=(0, -10, -20), neck=(0, 12, -12), head=(0, 12, -8), pelvis=(0, -30, 12),
    ua_l=(0, 40, 25), fa_l=(0, 0, 115), ua_r=(-4, 30, 22), fa_r=(0, 0, 118), pp=(-0.12, -0.17, 0.0),
)
HIT_LOW = dict(
    chest=(0, -14, -14), spine=(0, -8, -8), pp=(-0.05, -0.24, 0.0), head=(0, 18, -6),
    fl=(0.20, 0.07, -0.09, -8), ua_l=(30, 40, 40), fa_l=(0, 0, 70), ua_r=(-30, 30, 20), fa_r=(0, 0, 80),
)
HIT_AIR = dict(
    chest=(0, -12, 26), spine=(0, -8, 12), head=(0, 10, 22), ikl=0.0, ikr=0.0,
    th_l=(0, 20, 35), sn_l=(0, 0, -70), th_r=(0, 20, -5), sn_r=(0, 0, -45),
    ua_l=(60, 30, 130), fa_l=(0, 0, 30), ua_r=(-60, 30, 110), fa_r=(0, 0, 30),
)
GUARD_BREAK = dict(
    ua_l=(45, 20, 135), fa_l=(0, 0, 30), ua_r=(-45, 20, 125), fa_r=(0, 0, 35),
    chest=(0, -20, 18), spine=(0, -10, 8), head=(0, 12, 22), pp=(-0.06, -0.10, 0.0),
)
PARRY = dict(
    ua_l=(30, 62, 125), fa_l=(0, 0, 55), hd_l=(0, 0, 30), chest=(0, -36, 6), spine=(0, -12, 2),
    ua_r=(-14, 30, 40), fa_r=(0, 0, 135), pp=(-0.05, -0.12, 0.0), glow=1.2,
)
BURST = dict(
    ua_l=(75, 0, 45), fa_l=(0, 0, 10), ua_r=(-75, 0, 45), fa_r=(0, 0, 10), chest=(0, -32, 16),
    spine=(0, -10, 6), head=(0, 18, 16), pp=(0.0, -0.05, 0.0), glow=2.5,
)
THROWN = dict(
    HIT_HIGH, rp=(0.0, 0.10, 0.0), ikl=0.4, ikr=0.4, th_l=(0, 20, 25), sn_l=(0, 0, -40), th_r=(0, 20, 0),
    sn_r=(0, 0, -50),
)
LYING = dict(
    root=(0, 0, 90), rp=(-0.30, -0.76, 0.0), ikl=0.0, ikr=0.0,
    pelvis=(0, -10, 0), spine=(0, -4, 4), chest=(0, -4, 4), neck=(0, 0, 4), head=(0, 10, 12),
    th_l=(0, 10, 22), sn_l=(0, 0, -35), th_r=(0, 10, 6), sn_r=(0, 0, -12), ft_l=(0, 0, 20), ft_r=(0, 0, 25),
    ua_l=(70, 10, 150), fa_l=(0, 0, 25), ua_r=(-70, 10, 130), fa_r=(0, 0, 30), pp=(0.0, 0.0, 0.0),
)
FALLING = dict(
    LYING, root=(0, 0, 55), rp=(-0.18, -0.36, 0.0), chest=(0, -10, 20), head=(0, 10, 25),
    th_l=(0, 20, 45), sn_l=(0, 0, -70), th_r=(0, 20, 25), sn_r=(0, 0, -50),
    ua_l=(60, 30, 120), ua_r=(-60, 30, 105),
)
GETUP = dict(
    root=(0, 0, 28), rp=(-0.12, -0.25, 0.0), pp=(-0.05, -0.40, 0.0), chest=(0, -8, -25), spine=(0, -6, -15),
    ikl=1.0, ikr=1.0, fl=(0.25, 0.0, -0.12, -10), fr=(-0.20, 0.0, 0.18, -60),
    ua_r=(-30, 20, -20), fa_r=(0, 0, 10), ua_l=(10, 40, 45), fa_l=(0, 0, 100),
)
LAND = dict(pp=(-0.02, -0.26, 0.0), chest=(0, -8, -18), ua_l=(14, 42, 40), ua_r=(-20, 30, 15))
KNEEL = dict(
    pp=(0.0, -0.47, 0.0), fl=(0.28, 0.0, -0.10, -10), fr=(-0.38, 0.0, 0.13, -70), chest=(0, -16, -26),
    spine=(0, -8, -14), neck=(0, 10, -18), head=(0, 10, -22),
    ua_l=(10, 30, 20), fa_l=(0, 0, 35), ua_r=(-15, 20, 5), fa_r=(0, 0, 30),
)

# jump body: tucked legs, guard arms
JUMP_UP = dict(
    ikl=0.0, ikr=0.0, th_l=(0, 25, 18), sn_l=(0, 0, -25), ft_l=(0, 0, -35), th_r=(0, 25, -12),
    sn_r=(0, 0, -30), ft_r=(0, 0, -40), chest=(0, -8, 4), ua_l=(14, 40, 80), ua_r=(-20, 30, 60),
)
JUMP_TUCK = dict(
    ikl=0.0, ikr=0.0, th_l=(0, 25, 78), sn_l=(0, 0, -112), ft_l=(0, 0, -20), th_r=(0, 25, 52),
    sn_r=(0, 0, -125), ft_r=(0, 0, -25), chest=(0, -8, -12), pp=(0.0, -0.05, 0.0),
)
JUMP_FALL = dict(
    ikl=0.0, ikr=0.0, th_l=(0, 25, 30), sn_l=(0, 0, -40), ft_l=(0, 0, -15), th_r=(0, 25, 5),
    sn_r=(0, 0, -45), ft_r=(0, 0, -20), chest=(0, -8, -6),
)

DASH_RUN = dict(
    chest=(0, -6, -26), spine=(0, -6, -12), pp=(0.04, -0.16, 0.0), head=(0, 14, 20),
    ua_l=(10, 30, -35), fa_l=(0, 0, 60), ua_r=(-10, 30, -45), fa_r=(0, 0, 55),
)

VICTORY = {
    "Golden": dict(
        pelvis=(0, -30, 0), chest=(0, -14, -14), spine=(0, -8, -6), head=(0, 18, -14), pp=(0.0, -0.03, 0.0),
        ua_l=(0, 46, 58), fa_l=(0, 0, 92), ua_r=(0, 46, 54), fa_r=(0, 0, 96), hd_l=(0, 0, 50),
        fl=(0.10, 0.0, -0.10, -20), fr=(-0.08, 0.0, 0.10, -45), glow=0.8,
    ),
    "Crimson": dict(
        chest=(0, -30, 12), spine=(0, -10, 6), head=(0, 20, 22), pp=(0.0, -0.06, 0.0),
        ua_r=(-22, 0, 168), fa_r=(0, 0, 28), ua_l=(10, 30, 15), fa_l=(0, 0, 120), glow=1.0,
    ),
    "Shadow": dict(
        pp=(0.0, -0.36, 0.0), chest=(0, -20, -10), head=(0, 22, 4),
        ua_r=(-6, 46, 72), fa_r=(0, 0, 132), ua_l=(30, 20, -40), fa_l=(0, 0, 20), glow=0.8,
        fl=(0.32, 0.0, -0.12, -8), fr=(-0.30, 0.0, 0.18, -60),
    ),
    "Steel": dict(
        chest=(0, -28, 4), spine=(0, -8, 2), pp=(0.0, -0.05, 0.0), head=(0, 22, 8),
        ua_l=(6, 46, 82), fa_l=(0, 0, 104), ua_r=(-6, 46, 82), fa_r=(0, 0, 108), glow=0.8,
    ),
}

SUPER_POSE = {
    "Golden": dict(ua_l=(0, 48, 80), fa_l=(0, 0, 70), ua_r=(0, 46, 76), fa_r=(0, 0, 76), hd_l=(0, 0, 55),
                   hd_r=(0, 0, 55), chest=(0, -30, 6), head=(0, 22, 6), pp=(0.0, -0.14, 0.0), glow=3.0),
    "Crimson": dict(ua_l=(40, 30, 20), fa_l=(0, 0, 110), ua_r=(-40, 30, 20), fa_r=(0, 0, 112),
                    chest=(0, -26, 16), head=(0, 18, 24), pp=(0.0, -0.20, 0.0), glow=3.0),
    "Shadow": dict(ua_r=(-6, 50, 80), fa_r=(0, 0, 140), ua_l=(6, 50, 78), fa_l=(0, 0, 138), chest=(0, -24, -8),
                   pp=(0.0, -0.30, 0.0), head=(0, 18, -4), glow=3.0),
    "Steel": dict(ua_l=(6, 48, 88), fa_l=(0, 0, 92), ua_r=(-6, 48, 86), fa_r=(0, 0, 94), chest=(0, -18, -8),
                  pp=(0.0, -0.18, 0.0), fl=(0.36, 0.0, -0.16, -10), fr=(-0.34, 0.0, 0.2, -50), glow=3.0),
}


def M(*dicts, **kw):
    out = {}
    for d in dicts:
        out.update(d)
    out.update(kw)
    return out


# ---------------------------------------------------------------------------
# Clip helpers
# ---------------------------------------------------------------------------

def strike(ant, ext, limb, follow=None, hold=None, ant_at=0.6, pre=None, smear=0.2, settle="back",
           follow_at=0.3, extra=None):
    """Standard strike: guard -> anticipation (ease-in) -> SNAP to full extension on the
    first active frame -> hold through active -> follow-through -> overshoot-settle to guard."""
    ext = M(ext, smear=smear, limb=limb)
    hold = M(ext, hold or {}, smear=smear * 0.35, limb=limb)
    keys = [(S, 0.0, {}, "lin")]
    if pre is not None:
        keys.append((S, ant_at * 0.5, pre, "io"))
    keys.append((S, ant_at, M(ant, limb=limb), "io"))
    keys.append((A, 0.0, ext, "snap"))
    keys.append((A, 1.0, hold, "lin"))
    if extra:
        keys.extend(extra)
    keys.append((R, follow_at, M(follow if follow is not None else ext, smear=0.0, limb=limb), "out"))
    keys.append((R, 1.0, {}, settle))
    return dict(keys=keys, limb=limb)


def crouched(d):
    return M(CROUCH, d)


# ---------------------------------------------------------------------------
# Universal normals
# ---------------------------------------------------------------------------
JAB = strike(
    ant=dict(chest=(0, -14, -4), ua_l=(8, 40, 46), fa_l=(0, 0, 122), pp=(-0.03, -0.11, 0.0)),
    ext=dict(pelvis=(0, -22, 0), spine=(0, -6, -6), chest=(0, -10, -9), neck=(0, 14, -2), head=(0, 16, 0),
             ua_l=(0, 37, 91), fa_l=(0, 0, 3), hd_l=(0, 0, 0), pp=(0.06, -0.11, 0.0),
             fl=(0.31, 0.0, -0.09, -8)),
    follow=dict(ua_l=(4, 38, 80), fa_l=(0, 0, 40), chest=(0, -12, -8)),
    limb=1, smear=0.18,
)

HEAVY_PUNCH = strike(
    ant=dict(pelvis=(0, -52, 0), spine=(0, -10, 0), chest=(0, -12, 3), ua_r=(-16, 10, 24), fa_r=(0, 0, 146),
             ua_l=(8, 50, 72), fa_l=(0, 0, 70), pp=(-0.06, -0.14, 0.0), fr=(-0.25, 0.0, 0.13, -62)),
    ext=dict(pelvis=(0, 6, 0), spine=(0, 6, -9), chest=(0, 8, -12), neck=(0, -4, 0), head=(0, -6, -2),
             ua_r=(0, -18, 89), fa_r=(0, 0, 2), hd_r=(0, 0, 0), ua_l=(16, 30, 30), fa_l=(0, 0, 138),
             pp=(0.12, -0.13, 0.0), fr=(-0.21, 0.0, 0.10, -12), fl=(0.34, 0.0, -0.09, -8)),
    follow=dict(pelvis=(0, 12, 0), chest=(0, 14, -14), ua_r=(0, -22, 80), fa_r=(0, 0, 18),
                pp=(0.12, -0.15, 0.0), fr=(-0.21, 0.0, 0.10, -12), fl=(0.34, 0.0, -0.09, -8)),
    limb=2, smear=0.24, settle="io",
)

LIGHT_KICK = strike(
    ant=dict(ikl=0.0, th_l=(0, 30, 86), sn_l=(0, 0, -118), ft_l=(0, 0, -10), pp=(-0.08, -0.06, 0.0),
             chest=(0, -8, 5), ua_l=(10, 40, 40), fa_l=(0, 0, 110)),
    ext=dict(ikl=0.0, th_l=(0, 30, 82), sn_l=(0, 0, -5), ft_l=(0, 0, -28), pp=(-0.05, -0.04, 0.0),
             chest=(0, -12, 12), spine=(0, -8, 6), ua_l=(14, 30, 10), fa_l=(0, 0, 70)),
    follow=dict(ikl=0.0, th_l=(0, 30, 70), sn_l=(0, 0, -60), ft_l=(0, 0, -10), pp=(-0.06, -0.06, 0.0)),
    limb=3, smear=0.15,
)

HEAVY_KICK = strike(
    pre=dict(pelvis=(0, -38, 0), chest=(0, -10, 2), pp=(-0.02, -0.14, 0.0)),
    ant=dict(ikr=0.0, th_r=(-10, 15, 84), sn_r=(0, 0, -128), ft_r=(0, 0, -20), pelvis=(0, 12, 0),
             chest=(0, -10, 9), pp=(-0.03, -0.05, 0.0), ua_r=(-25, 10, -10), fa_r=(0, 0, 70),
             fl=(0.27, 0.0, -0.09, 30)),
    ext=dict(ikr=0.0, th_r=(-4, -50, 104), sn_r=(0, 0, -6), ft_r=(0, 0, -35), pelvis=(-8, 50, 0),
             spine=(0, -6, 14), chest=(0, -14, 20), neck=(0, -10, -6), head=(0, -12, -10),
             pp=(0.0, 0.02, 0.0), ua_r=(-28, 0, -32), fa_r=(0, 0, 45), ua_l=(15, 40, 62), fa_l=(0, 0, 110),
             fl=(0.27, 0.0, -0.09, 48)),
    follow=dict(ikr=0.0, th_r=(0, -78, 86), sn_r=(0, 0, -45), ft_r=(0, 0, -20), pelvis=(-6, 76, 0),
                chest=(0, -6, 16), pp=(0.0, -0.02, 0.0), fl=(0.27, 0.0, -0.09, 55)),
    limb=4, smear=0.22, settle="io",
)

LOW_SWEEP_CLIP = strike(
    ant=dict(pp=(-0.06, -0.55, 0.0), pelvis=(0, -62, 0), chest=(0, -20, -34), spine=(0, -10, -16),
             ua_l=(20, 40, 38), fa_l=(0, 0, 20), ua_r=(-25, 30, 22), fa_r=(0, 0, 20),
             fr=(-0.40, 0.0, 0.16, -70), fl=(0.16, 0.0, -0.15, -20)),
    ext=dict(pp=(0.0, -0.62, 0.0), pelvis=(0, 42, 0), chest=(0, -12, -36), spine=(0, -8, -16),
             ikr=0.0, th_r=(0, -42, 79), sn_r=(0, 0, -4), ft_r=(0, 0, -30), fl=(0.08, 0.0, -0.13, 30),
             ua_l=(25, 40, 40), fa_l=(0, 0, 15), ua_r=(-30, 20, 30), fa_r=(0, 0, 20), head=(0, 10, 18)),
    follow=dict(pp=(0.0, -0.60, 0.0), pelvis=(0, 72, 0), ikr=0.0, th_r=(0, -72, 76), sn_r=(0, 0, -20),
                chest=(0, -10, -34), fl=(0.08, 0.0, -0.13, 40)),
    limb=4, smear=0.18, settle="io",
)
LOW_SWEEP_CLIP["keys"][-1] = (R, 1.0, CROUCH, "io")

OVERHEAD_CLIP = strike(
    pre=dict(pp=(-0.04, -0.24, 0.0), ua_l=(20, 30, -30), fa_l=(0, 0, 40), ua_r=(-20, 30, -30), fa_r=(0, 0, 40),
             chest=(0, -10, -16)),
    ant=dict(rp=(0.06, 0.30, 0.0), ikl=0.0, ikr=0.0, th_l=(0, 30, 70), sn_l=(0, 0, -100), th_r=(0, 30, 40),
             sn_r=(0, 0, -112), ua_l=(10, 30, 172), fa_l=(0, 0, 45), ua_r=(-10, 30, 168), fa_r=(0, 0, 45),
             chest=(0, -12, 16), head=(0, 18, 14)),
    ext=dict(rp=(0.16, 0.0, 0.0), ua_l=(6, 36, 76), fa_l=(0, 0, 6), ua_r=(-6, 30, 70), fa_r=(0, 0, 6),
             chest=(0, -4, -32), spine=(0, -4, -14), pelvis=(0, -14, 0), pp=(0.06, -0.18, 0.0),
             fl=(0.40, 0.0, -0.10, -5), head=(0, 12, 10)),
    follow=dict(rp=(0.16, 0.0, 0.0), ua_l=(6, 36, 50), ua_r=(-6, 30, 46), chest=(0, -4, -34), pp=(0.06, -0.22, 0.0),
                fl=(0.40, 0.0, -0.10, -5)),
    limb=2, smear=0.15, ant_at=0.75, settle="io",
)

CROUCH_JAB_CLIP = strike(
    ant=crouched(dict(ua_l=(8, 40, 40), fa_l=(0, 0, 118))),
    ext=crouched(dict(ua_l=(0, 38, 80), fa_l=(0, 0, 4), hd_l=(0, 0, 0), chest=(0, -12, -20),
                      pp=(0.04, -0.40, 0.0))),
    follow=crouched(dict(ua_l=(4, 38, 64), fa_l=(0, 0, 50))),
    limb=1, smear=0.15,
)
CROUCH_JAB_CLIP["keys"][0] = (S, 0.0, CROUCH, "lin")
CROUCH_JAB_CLIP["keys"][-1] = (R, 1.0, CROUCH, "back")

CROUCH_KICK_CLIP = strike(
    ant=crouched(dict(ikl=0.0, th_l=(0, 30, 52), sn_l=(0, 0, -105), pp=(-0.06, -0.40, 0.0))),
    ext=crouched(dict(ikl=0.0, th_l=(0, 32, 64), sn_l=(0, 0, -6), ft_l=(0, 0, -30), chest=(0, -10, -6),
                      pp=(-0.04, -0.40, 0.0))),
    follow=crouched(dict(ikl=0.0, th_l=(0, 30, 50), sn_l=(0, 0, -60))),
    limb=3, smear=0.15,
)
CROUCH_KICK_CLIP["keys"][0] = (S, 0.0, CROUCH, "lin")
CROUCH_KICK_CLIP["keys"][-1] = (R, 1.0, CROUCH, "back")

JUMP_PUNCH_CLIP = strike(
    ant=M(JUMP_TUCK, ua_r=(-12, 22, 50), fa_r=(0, 0, 145), chest=(0, -4, -4)),
    ext=M(JUMP_TUCK, ua_r=(0, -10, 58), fa_r=(0, 0, 2), hd_r=(0, 0, 0), chest=(0, 6, -22), spine=(0, 6, -10),
          ua_l=(15, 30, 20), fa_l=(0, 0, 130)),
    follow=M(JUMP_TUCK, ua_r=(0, -10, 50), fa_r=(0, 0, 30), chest=(0, 4, -16)),
    limb=2, smear=0.16,
)
for _i, _k in enumerate(JUMP_PUNCH_CLIP["keys"]):
    if _k[2] == {}:
        JUMP_PUNCH_CLIP["keys"][_i] = (_k[0], _k[1], JUMP_TUCK, _k[3])

JUMP_KICK_CLIP = strike(
    ant=M(JUMP_TUCK, th_l=(0, 30, 84), sn_l=(0, 0, -125)),
    ext=M(JUMP_TUCK, th_l=(0, 32, 52), sn_l=(0, 0, -2), ft_l=(0, 0, -32), th_r=(0, 30, 92), sn_r=(0, 0, -140),
          chest=(0, -18, 16), spine=(0, -10, 6), ua_l=(30, 30, -10), fa_l=(0, 0, 50), ua_r=(-20, 30, 70),
          fa_r=(0, 0, 120)),
    follow=M(JUMP_TUCK, th_l=(0, 32, 48), sn_l=(0, 0, -20), chest=(0, -16, 12)),
    limb=3, smear=0.16,
)
for _i, _k in enumerate(JUMP_KICK_CLIP["keys"]):
    if _k[2] == {}:
        JUMP_KICK_CLIP["keys"][_i] = (_k[0], _k[1], JUMP_TUCK, _k[3])

ANTI_AIR_CLIP = strike(
    ant=dict(pp=(-0.02, -0.27, 0.0), ua_r=(-22, 30, -12), fa_r=(0, 0, 105), chest=(0, -22, -16),
             spine=(0, -10, -8), pelvis=(0, -40, 0)),
    ext=dict(pp=(0.06, 0.03, 0.0), pelvis=(0, 10, 0), spine=(0, 4, 6), chest=(0, 8, 12), head=(0, -4, 16),
             neck=(0, -4, 8), ua_r=(0, -12, 166), fa_r=(0, 0, 24), hd_r=(0, 0, 0), ua_l=(15, 40, 18),
             fa_l=(0, 0, 95), fr=(-0.20, 0.06, 0.10, -20), fl=(0.30, 0.0, -0.09, -8)),
    follow=dict(pp=(0.06, 0.02, 0.0), pelvis=(0, 16, 0), chest=(0, 10, 14), ua_r=(0, -14, 160),
                fa_r=(0, 0, 40), fr=(-0.20, 0.03, 0.10, -20), fl=(0.30, 0.0, -0.09, -8)),
    limb=2, smear=0.2, settle="io",
)

THROW_CLIP = dict(limb=2, keys=[
    (S, 0.0, {}, "lin"),
    (A, 0.0, dict(ua_l=(0, 40, 82), fa_l=(0, 0, 22), ua_r=(-6, 12, 76), fa_r=(0, 0, 26), hd_l=(0, 0, 20),
                  hd_r=(0, 0, 20), chest=(0, -6, -16), pp=(0.09, -0.13, 0.0), fl=(0.34, 0.0, -0.09, -8),
                  smear=0.1, limb=2), "snap"),
    (A, 1.0, dict(ua_l=(0, 40, 78), fa_l=(0, 0, 42), ua_r=(-6, 12, 72), fa_r=(0, 0, 45), chest=(0, -6, -14),
                  pp=(0.08, -0.13, 0.0), fl=(0.34, 0.0, -0.09, -8)), "lin"),
    (R, 0.35, dict(pelvis=(0, 62, 0), chest=(0, 38, -12), ua_r=(-10, -30, 105), fa_r=(0, 0, 20), ua_l=(0, 0, 95),
                   fa_l=(0, 0, 30), pp=(0.04, -0.16, 0.0), fl=(0.30, 0.0, -0.09, 40)), "out"),
    (R, 1.0, {}, "io"),
])

BACKDASH_CLIP = dict(limb=0, keys=[
    (A, 0.0, dict(rp=(0.0, 0.10, 0.0), chest=(0, -10, 14), ikl=0.0, ikr=0.0, th_l=(0, 25, 40), sn_l=(0, 0, -70),
                  th_r=(0, 25, 12), sn_r=(0, 0, -80), ua_l=(20, 40, 60), ua_r=(-20, 30, 40)), "out"),
    (A, 1.0, dict(rp=(0.0, 0.16, 0.0), chest=(0, -10, 10), ikl=0.0, ikr=0.0, th_l=(0, 25, 36),
                  sn_l=(0, 0, -60), th_r=(0, 25, 16), sn_r=(0, 0, -70)), "io"),
    (R, 0.45, M(LAND, pp=(-0.02, -0.20, 0.0)), "in"),
    (R, 1.0, {}, "io"),
])

# ---------------------------------------------------------------------------
# Generic (non-move) action clips
# ---------------------------------------------------------------------------
BURST_CLIP = dict(limb=0, keys=[(T, 0, {}, "lin"), (T, 3, BURST, "snap"), (T, 14, BURST, "lin"), (T, 24, {}, "io")])
BUILD_CLIP = dict(limb=0, keys=[(T, 0, {}, "lin"),
                                (T, 4, M(CROUCH, ua_l=(10, 30, 60), fa_l=(0, 0, 10), ua_r=(-10, 30, 55),
                                         fa_r=(0, 0, 10), chest=(0, -10, -30)), "out"),
                                (T, 10, M(CROUCH, ua_l=(10, 30, 50), fa_l=(0, 0, 10), ua_r=(-10, 30, 45),
                                          fa_r=(0, 0, 10), chest=(0, -10, -32), glow=1.5), "io"),
                                (T, 14, {}, "io")])
PICKUP_CLIP = dict(limb=0, keys=[(T, 0, {}, "lin"),
                                 (T, 5, M(CROUCH, ua_r=(-10, 30, 40), fa_r=(0, 0, 10), chest=(0, -10, -30)), "out"),
                                 (T, 12, {}, "io")])
SHIELD_FRONT_CLIP = dict(limb=1, keys=[(T, 0, {}, "lin"),
                                       (T, 3, dict(ua_l=(0, 40, 90), fa_l=(0, 0, 20), hd_l=(0, 0, 70),
                                                   chest=(0, -16, -8), pp=(0.05, -0.12, 0.0), glow=1.5), "snap"),
                                       (T, 12, {}, "io")])
SHIELD_BACK_CLIP = dict(limb=2, keys=[(T, 0, {}, "lin"),
                                      (T, 3, dict(ua_r=(-20, 140, 70), fa_r=(0, 0, 20), chest=(0, 10, 2),
                                                  head=(0, 40, 0), glow=1.5), "snap"),
                                      (T, 12, {}, "io")])

UNIVERSAL_CLIPS = {
    Action.LIGHT: JAB,
    Action.HEAVY: HEAVY_PUNCH,
    Action.LIGHT_KICK: LIGHT_KICK,
    Action.HEAVY_KICK: HEAVY_KICK,
    Action.LOW_SWEEP: LOW_SWEEP_CLIP,
    Action.OVERHEAD: OVERHEAD_CLIP,
    Action.CROUCH_JAB: CROUCH_JAB_CLIP,
    Action.CROUCH_KICK: CROUCH_KICK_CLIP,
    Action.JUMP_PUNCH: JUMP_PUNCH_CLIP,
    Action.JUMP_KICK: JUMP_KICK_CLIP,
    Action.ANTI_AIR: ANTI_AIR_CLIP,
    Action.THROW: THROW_CLIP,
    Action.BACKDASH: BACKDASH_CLIP,
    Action.BURST: BURST_CLIP,
    Action.BUILD: BUILD_CLIP,
    Action.PICKUP: PICKUP_CLIP,
    Action.SHIELD_FRONT: SHIELD_FRONT_CLIP,
    Action.SHIELD_BACK: SHIELD_BACK_CLIP,
}

# ---------------------------------------------------------------------------
# Character specials and supers
# ---------------------------------------------------------------------------

def flurry(base_ext, n, limb_a=1, limb_b=2, a_pose=None, b_pose=None):
    """Alternating strikes spread over the active window."""
    keys = []
    for i in range(n):
        f = i / max(1, n)
        pose = a_pose if i % 2 == 0 else b_pose
        keys.append((A, f, M(base_ext, pose, smear=0.2, limb=limb_a if i % 2 == 0 else limb_b), "snap"))
    return keys


_PUNCH_L = dict(ua_l=(0, 37, 92), fa_l=(0, 0, 3), ua_r=(-14, 30, 35), fa_r=(0, 0, 140), chest=(0, -14, -14),
                pelvis=(0, -26, 0))
_PUNCH_R = dict(ua_r=(0, -16, 90), fa_r=(0, 0, 2), ua_l=(14, 32, 40), fa_l=(0, 0, 135), chest=(0, 8, -14),
                pelvis=(0, 4, 0))

GOLDEN_CLIPS = {
    Action.SPECIAL_DOWN: dict(limb=1, keys=[  # Tactician Stance: flowing hand circle, aura shift
        (S, 0.0, {}, "lin"),
        (S, 1.0, dict(ua_l=(30, 50, 120), fa_l=(0, 0, 50), hd_l=(0, 0, 50), ua_r=(-10, 30, 50), fa_r=(0, 0, 120),
                      chest=(0, -20, 4), glow=1.0), "io"),
        (A, 1.0, dict(ua_l=(-10, 40, 60), fa_l=(0, 0, 70), hd_l=(0, 0, 55), ua_r=(-10, 30, 50),
                      fa_r=(0, 0, 120), chest=(0, -24, -2), pp=(0.0, -0.12, 0.0), glow=2.0), "io"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_NEUTRAL: dict(limb=1, keys=[  # Golden Read: counter-ready open palm
        (S, 0.0, {}, "lin"),
        (S, 0.8, dict(ua_l=(10, 30, 40), fa_l=(0, 0, 120), hd_l=(0, 0, 50), chest=(0, -30, 2),
                      pp=(-0.04, -0.12, 0.0), glow=1.0), "io"),
        (A, 0.0, dict(ua_l=(4, 40, 84), fa_l=(0, 0, 25), hd_l=(0, 0, 70), ua_r=(-26, 10, -20), fa_r=(0, 0, 100),
                      chest=(0, -20, -2), pp=(0.0, -0.15, 0.0), glow=2.0), "snap"),
        (A, 0.5, dict(ua_l=(4, 42, 82), fa_l=(0, 0, 30), hd_l=(0, 0, 70), ua_r=(-26, 10, -20), fa_r=(0, 0, 100),
                      chest=(0, -22, 0), pp=(0.0, -0.17, 0.0), glow=2.6), "io"),
        (A, 1.0, dict(ua_l=(4, 40, 84), fa_l=(0, 0, 25), hd_l=(0, 0, 70), ua_r=(-26, 10, -20), fa_r=(0, 0, 100),
                      chest=(0, -20, -2), pp=(0.0, -0.15, 0.0), glow=2.0), "io"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_FORWARD: strike(  # Gambit Strike: stepping double palm
        ant=dict(ua_l=(10, 30, 40), fa_l=(0, 0, 120), ua_r=(-10, 30, 30), fa_r=(0, 0, 125), hd_l=(0, 0, 60),
                 hd_r=(0, 0, 60), pelvis=(0, -48, 0), chest=(0, -14, 6), pp=(-0.08, -0.16, 0.0), glow=1.0),
        ext=dict(ua_l=(0, 34, 86), fa_l=(0, 0, 4), ua_r=(0, 6, 82), fa_r=(0, 0, 4), hd_l=(0, 0, 70),
                 hd_r=(0, 0, 70), pelvis=(0, -6, 0), chest=(0, 0, -14), spine=(0, -2, -8), rp=(0.18, 0.0, 0.0),
                 pp=(0.06, -0.18, 0.0), fl=(0.42, 0.0, -0.09, -8), glow=2.2),
        follow=dict(ua_l=(0, 34, 80), fa_l=(0, 0, 18), ua_r=(0, 6, 76), fa_r=(0, 0, 18), rp=(0.18, 0.0, 0.0),
                    pp=(0.06, -0.2, 0.0), chest=(0, 0, -16), fl=(0.42, 0.0, -0.09, -8)),
        limb=1, smear=0.2, settle="io",
    ),
    Action.SPECIAL_BACK: dict(limb=0, keys=[  # Tactical Step: slip back into the depth plane
        (A, 0.0, dict(rp=(-0.10, 0.06, -0.35), chest=(0, -40, 8), pp=(0.0, -0.14, 0.0), glow=1.0,
                      ua_l=(20, 50, 70), fa_l=(0, 0, 80)), "out"),
        (A, 1.0, dict(rp=(-0.14, 0.02, -0.40), chest=(0, -40, 6), pp=(0.0, -0.16, 0.0), glow=0.8), "io"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SUPER: dict(limb=1, keys=[  # Checkmate: palm flurry -> rising double palm
        (S, 0.0, SUPER_POSE["Golden"], "lin"),
        *flurry(dict(rp=(0.12, 0.0, 0.0), pp=(0.05, -0.16, 0.0), glow=3.0, hd_l=(0, 0, 70), hd_r=(0, 0, 70)), 6,
                a_pose=_PUNCH_L, b_pose=_PUNCH_R),
        (A, 1.0, dict(rp=(0.16, 0.0, 0.0), ua_l=(0, 34, 120), fa_l=(0, 0, 4), ua_r=(0, 6, 116), fa_r=(0, 0, 4),
                      hd_l=(0, 0, 70), hd_r=(0, 0, 70), chest=(0, 0, 6), pp=(0.05, -0.08, 0.0), glow=3.5,
                      smear=0.25, limb=2), "snap"),
        (R, 0.4, dict(rp=(0.16, 0.0, 0.0), ua_l=(0, 34, 125), ua_r=(0, 6, 120), chest=(0, 0, 8), glow=2.0), "out"),
        (R, 1.0, {}, "io"),
    ]),
}

CRIMSON_CLIPS = {
    Action.SPECIAL_FORWARD: dict(limb=2, keys=[  # Crimson Rush: lunging rush punches
        (S, 0.0, {}, "lin"),
        (S, 0.7, dict(pelvis=(0, -50, 0), chest=(0, -12, -14), pp=(-0.06, -0.20, 0.0), ua_r=(-16, 10, 24),
                      fa_r=(0, 0, 146), glow=1.0), "io"),
        *flurry(dict(rp=(0.24, 0.0, 0.0), pp=(0.10, -0.18, 0.0), spine=(0, -4, -12), fl=(0.42, 0.0, -0.09, -8),
                     glow=1.5), 3, limb_a=2, limb_b=1, a_pose=_PUNCH_R, b_pose=_PUNCH_L),
        (A, 1.0, M(_PUNCH_R, rp=(0.28, 0.0, 0.0), pp=(0.12, -0.18, 0.0), smear=0.25, limb=2,
                   fl=(0.42, 0.0, -0.09, -8), glow=1.5), "snap"),
        (R, 0.35, M(_PUNCH_R, rp=(0.28, 0.0, 0.0), pp=(0.12, -0.2, 0.0), fl=(0.42, 0.0, -0.09, -8)), "out"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_NEUTRAL: dict(limb=2, keys=[  # Rising Uppercut (dragon punch)
        (S, 0.0, {}, "lin"),
        (S, 0.8, dict(pp=(-0.02, -0.32, 0.0), ua_r=(-24, 30, -16), fa_r=(0, 0, 110), chest=(0, -24, -18),
                      pelvis=(0, -44, 0), glow=1.0), "in"),
        (A, 0.0, dict(rp=(0.10, 0.45, 0.0), pp=(0.04, 0.0, 0.0), pelvis=(0, 14, 0), chest=(0, 10, 14),
                      spine=(0, 4, 8), ua_r=(0, -12, 170), fa_r=(0, 0, 14), ua_l=(30, 40, 10), fa_l=(0, 0, 100),
                      ikl=0.0, ikr=0.0, th_l=(0, 30, 80), sn_l=(0, 0, -100), th_r=(0, 25, 0), sn_r=(0, 0, -20),
                      ft_r=(0, 0, -40), smear=0.25, limb=2, glow=2.5, head=(0, -4, 18)), "snap"),
        (A, 1.0, dict(rp=(0.14, 0.75, 0.0), pp=(0.04, 0.0, 0.0), pelvis=(0, 30, 0), chest=(0, 12, 16),
                      ua_r=(0, -12, 172), fa_r=(0, 0, 10), ua_l=(30, 40, 10), fa_l=(0, 0, 100), ikl=0.0, ikr=0.0,
                      th_l=(0, 30, 85), sn_l=(0, 0, -110), th_r=(0, 25, 5), sn_r=(0, 0, -30), smear=0.1, limb=2,
                      glow=2.0), "out"),
        (R, 0.5, M(JUMP_FALL, rp=(0.14, 0.25, 0.0), ua_r=(0, -12, 120), fa_r=(0, 0, 40)), "in"),
        (R, 0.7, M(LAND, rp=(0.14, 0.0, 0.0)), "in"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_BACK: strike(  # Berserker Charge: armoured shoulder tackle
        ant=dict(pelvis=(0, -60, 0), chest=(0, -20, -8), pp=(-0.10, -0.20, 0.0), ua_l=(20, 50, 30),
                 fa_l=(0, 0, 130), ua_r=(-20, 30, 10), fa_r=(0, 0, 130), glow=2.0),
        ext=dict(pelvis=(0, -10, 0), chest=(0, 10, -38), spine=(0, 0, -16), head=(0, 0, 10), rp=(0.32, 0.0, 0.0),
                 pp=(0.06, -0.24, 0.0), ua_l=(30, 60, 50), fa_l=(0, 0, 130), ua_r=(-20, 20, 20), fa_r=(0, 0, 130),
                 fl=(0.46, 0.0, -0.09, -5), fr=(-0.34, 0.0, 0.12, -40), glow=2.5),
        hold=dict(rp=(0.40, 0.0, 0.0)),
        follow=dict(rp=(0.40, 0.0, 0.0), chest=(0, 4, -26), pp=(0.04, -0.18, 0.0), fl=(0.40, 0.0, -0.09, -5)),
        limb=1, smear=0.0, settle="io",
    ),
    Action.SPECIAL_DOWN: dict(limb=2, keys=[  # Clinch Slam: collar grab -> overhead slam
        (S, 0.0, {}, "lin"),
        (A, 0.0, dict(ua_l=(0, 40, 100), fa_l=(0, 0, 30), ua_r=(-6, 12, 96), fa_r=(0, 0, 34), chest=(0, -6, -10),
                      pp=(0.08, -0.12, 0.0), fl=(0.34, 0.0, -0.09, -8)), "snap"),
        (R, 0.25, dict(ua_l=(0, 30, 175), fa_l=(0, 0, 30), ua_r=(0, 10, 170), fa_r=(0, 0, 30), chest=(0, -10, 18),
                       pp=(0.02, -0.06, 0.0), glow=1.5), "out"),
        (R, 0.5, dict(ua_l=(0, 30, 40), fa_l=(0, 0, 10), ua_r=(0, 10, 36), fa_r=(0, 0, 10), chest=(0, 0, -40),
                      pp=(0.08, -0.38, 0.0), fl=(0.38, 0.0, -0.1, -8), glow=2.0, smear=0.2, limb=2), "snap"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SUPER: dict(limb=2, keys=[  # Blood Fury: berserk flurry -> rising finisher
        (S, 0.0, SUPER_POSE["Crimson"], "lin"),
        *flurry(dict(rp=(0.18, 0.0, 0.0), pp=(0.08, -0.16, 0.0), glow=3.0, fl=(0.40, 0.0, -0.09, -8)), 8,
                limb_a=1, limb_b=2, a_pose=_PUNCH_L, b_pose=_PUNCH_R),
        (A, 1.0, dict(rp=(0.22, 0.30, 0.0), pelvis=(0, 14, 0), chest=(0, 10, 14), ua_r=(0, -12, 170),
                      fa_r=(0, 0, 14), ua_l=(30, 40, 10), fa_l=(0, 0, 100), ikl=0.0, ikr=0.0, th_l=(0, 30, 80),
                      sn_l=(0, 0, -100), th_r=(0, 25, 0), sn_r=(0, 0, -20), smear=0.3, limb=2, glow=3.5), "snap"),
        (R, 0.4, M(JUMP_FALL, rp=(0.22, 0.15, 0.0), ua_r=(0, -12, 130), glow=2.0), "in"),
        (R, 0.6, M(LAND, rp=(0.22, 0.0, 0.0)), "in"),
        (R, 1.0, {}, "io"),
    ]),
}

STEEL_CLIPS = {
    Action.SPECIAL_DOWN: dict(limb=1, keys=[  # Iron Wall: braced counter stance behind both shields
        (S, 0.0, {}, "lin"),
        (A, 0.0, dict(ua_l=(6, 46, 84), fa_l=(0, 0, 96), ua_r=(-6, 44, 80), fa_r=(0, 0, 100), chest=(0, -14, -10),
                      pp=(-0.04, -0.22, 0.0), fl=(0.34, 0.0, -0.16, -10), fr=(-0.34, 0.0, 0.2, -50), glow=2.0),
         "snap"),
        (A, 1.0, dict(ua_l=(6, 46, 84), fa_l=(0, 0, 96), ua_r=(-6, 44, 80), fa_r=(0, 0, 100), chest=(0, -14, -12),
                      pp=(-0.04, -0.24, 0.0), fl=(0.34, 0.0, -0.16, -10), fr=(-0.34, 0.0, 0.2, -50), glow=2.6),
         "io"),
        (R, 0.3, dict(ua_l=(0, 40, 92), fa_l=(0, 0, 20), chest=(0, -20, -14), pp=(0.08, -0.2, 0.0), glow=1.0,
                      smear=0.15, limb=1), "snap"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_FORWARD: strike(  # Shield Bash: lunging shield shove
        ant=dict(ua_l=(10, 30, 50), fa_l=(0, 0, 120), pelvis=(0, -50, 0), chest=(0, -16, 4), pp=(-0.08, -0.16, 0.0),
                 glow=1.0),
        ext=dict(ua_l=(0, 40, 84), fa_l=(0, 0, 70), hd_l=(0, 0, 0), pelvis=(0, -14, 0), chest=(0, -8, -18),
                 rp=(0.22, 0.0, 0.0), pp=(0.08, -0.18, 0.0), fl=(0.44, 0.0, -0.12, -10), glow=2.0),
        follow=dict(ua_l=(0, 40, 80), fa_l=(0, 0, 80), rp=(0.22, 0.0, 0.0), chest=(0, -8, -16),
                    fl=(0.44, 0.0, -0.12, -10)),
        limb=1, smear=0.1, settle="io",
    ),
    Action.SPECIAL_NEUTRAL: dict(limb=2, keys=[  # Punisher Grip: wide reach -> lift -> slam
        (S, 0.0, {}, "lin"),
        (S, 0.7, dict(ua_l=(70, 20, 60), fa_l=(0, 0, 30), ua_r=(-70, 20, 60), fa_r=(0, 0, 30), chest=(0, -20, 6),
                      pp=(-0.06, -0.18, 0.0), glow=1.0), "io"),
        (A, 0.0, dict(ua_l=(10, 30, 88), fa_l=(0, 0, 20), ua_r=(-10, 10, 86), fa_r=(0, 0, 22), chest=(0, -6, -18),
                      rp=(0.12, 0.0, 0.0), pp=(0.08, -0.16, 0.0), fl=(0.40, 0.0, -0.12, -10)), "snap"),
        (R, 0.3, dict(ua_l=(0, 30, 172), fa_l=(0, 0, 20), ua_r=(0, 10, 168), fa_r=(0, 0, 20), chest=(0, -10, 18),
                      rp=(0.12, 0.0, 0.0), pp=(0.0, -0.06, 0.0), glow=1.5), "out"),
        (R, 0.55, dict(ua_l=(0, 30, 40), fa_l=(0, 0, 10), ua_r=(0, 10, 36), fa_r=(0, 0, 10), chest=(0, 0, -38),
                       rp=(0.12, 0.0, 0.0), pp=(0.06, -0.36, 0.0), smear=0.2, limb=2, glow=2.0), "snap"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_BACK: dict(limb=2, keys=[  # Reflector: rear shield thrust, glowing
        (S, 0.0, {}, "lin"),
        (A, 0.0, dict(ua_r=(-4, 6, 90), fa_r=(0, 0, 72), hd_r=(0, 0, 0), pelvis=(0, 4, 0), chest=(0, 6, -10),
                      ua_l=(14, 40, 40), fa_l=(0, 0, 110), pp=(0.04, -0.16, 0.0), glow=3.0), "snap"),
        (A, 1.0, dict(ua_r=(-4, 6, 90), fa_r=(0, 0, 76), pelvis=(0, 4, 0), chest=(0, 6, -10), ua_l=(14, 40, 40),
                      fa_l=(0, 0, 110), pp=(0.04, -0.17, 0.0), glow=2.4), "io"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SUPER: dict(limb=2, keys=[  # Fortress Crush: glowing fortress -> double hammer smash
        (S, 0.0, SUPER_POSE["Steel"], "lin"),
        (A, 0.0, M(SUPER_POSE["Steel"], glow=3.5), "io"),
        (A, 0.85, M(SUPER_POSE["Steel"], pp=(0.0, -0.22, 0.0), glow=3.0), "io"),
        (A, 1.0, dict(ua_l=(0, 30, 172), fa_l=(0, 0, 30), ua_r=(0, 10, 168), fa_r=(0, 0, 30), chest=(0, -10, 18),
                      pp=(0.0, -0.04, 0.0), glow=3.5), "out"),
        (R, 0.2, dict(ua_l=(0, 34, 50), fa_l=(0, 0, 6), ua_r=(0, 12, 46), fa_r=(0, 0, 6), chest=(0, 0, -40),
                      rp=(0.15, 0.0, 0.0), pp=(0.06, -0.40, 0.0), fl=(0.42, 0.0, -0.12, -10), smear=0.3, limb=2,
                      glow=3.5), "snap"),
        (R, 0.55, dict(ua_l=(0, 34, 46), ua_r=(0, 12, 42), chest=(0, 0, -38), rp=(0.15, 0.0, 0.0),
                       pp=(0.06, -0.40, 0.0), glow=1.5), "lin"),
        (R, 1.0, {}, "io"),
    ]),
}

SHADOW_CLIPS = {
    Action.SPECIAL_FORWARD: dict(limb=0, ghost=True, keys=[  # Shadow Step: vanishing dash
        (S, 0.0, {}, "lin"),
        (S, 1.0, M(DASH_RUN, pp=(0.04, -0.30, 0.0), chest=(0, -6, -40), glow=2.0), "in"),
        (A, 1.0, M(DASH_RUN, pp=(0.04, -0.32, 0.0), chest=(0, -6, -42), glow=2.0), "lin"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_DOWN: strike(  # Phantom Kick: low sliding kick
        ant=crouched(dict(pp=(-0.06, -0.48, 0.0), ikl=0.0, th_l=(0, 30, 50), sn_l=(0, 0, -120), glow=1.0)),
        ext=dict(pp=(0.0, -0.66, 0.0), rp=(0.22, 0.0, 0.0), pelvis=(0, -20, 0), chest=(0, -10, 24),
                 spine=(0, -6, 10), ikl=0.0, th_l=(0, 25, 78), sn_l=(0, 0, -2), ft_l=(0, 0, -30),
                 fr=(-0.18, 0.0, 0.18, -60), ua_r=(-30, 20, -60), fa_r=(0, 0, 20), ua_l=(20, 40, 50),
                 fa_l=(0, 0, 100), glow=1.8),
        hold=dict(rp=(0.34, 0.0, 0.0)),
        follow=dict(pp=(0.0, -0.6, 0.0), rp=(0.34, 0.0, 0.0), ikl=0.0, th_l=(0, 25, 70), sn_l=(0, 0, -40),
                    chest=(0, -10, 18)),
        limb=3, smear=0.2, settle="io",
    ),
    Action.SPECIAL_BACK: dict(limb=1, keys=[  # Feint Strike: fake jab, snap back
        (S, 0.0, {}, "lin"),
        (S, 1.0, dict(ua_l=(4, 38, 75), fa_l=(0, 0, 50), chest=(0, -12, -10), pp=(0.05, -0.2, 0.0)), "out"),
        (A, 0.5, dict(ua_l=(8, 42, 40), fa_l=(0, 0, 125), chest=(0, -20, 6), rp=(-0.12, 0.08, 0.0),
                      pp=(-0.04, -0.18, 0.0), glow=1.0), "snap"),
        (A, 1.0, dict(rp=(-0.14, 0.0, 0.0), pp=(-0.02, -0.22, 0.0)), "in"),
        (R, 1.0, {}, "io"),
    ]),
    Action.SPECIAL_NEUTRAL: strike(  # Energy Dart: overhand throw
        ant=dict(ua_r=(-30, 40, 160), fa_r=(0, 0, 100), hd_r=(0, 0, 40), chest=(0, -40, 14), pelvis=(0, -50, 0),
                 pp=(-0.06, -0.20, 0.0), ua_l=(20, 46, 80), fa_l=(0, 0, 20), glow=1.5),
        ext=dict(ua_r=(0, -10, 84), fa_r=(0, 0, 4), hd_r=(0, 0, -20), chest=(0, 10, -18), pelvis=(0, 4, 0),
                 pp=(0.08, -0.2, 0.0), ua_l=(20, 30, 10), fa_l=(0, 0, 60), fl=(0.40, 0.0, -0.10, -5), glow=2.5),
        follow=dict(ua_r=(0, -10, 50), fa_r=(0, 0, 20), chest=(0, 12, -22), pp=(0.08, -0.22, 0.0),
                    fl=(0.40, 0.0, -0.10, -5)),
        limb=2, smear=0.2, settle="io",
    ),
    Action.SUPER: dict(limb=4, ghost=True, keys=[  # Vanishing Arts: afterimage spinning kicks
        (S, 0.0, SUPER_POSE["Shadow"], "lin"),
        (A, 0.0, M(DASH_RUN, rp=(0.30, 0.0, 0.0), pp=(0.04, -0.30, 0.0), glow=3.0), "snap"),
        (A, 0.35, dict(rp=(0.40, 0.25, 0.0), ikr=0.0, ikl=0.0, th_r=(0, -50, 100), sn_r=(0, 0, -6),
                       ft_r=(0, 0, -30), th_l=(0, 25, 40), sn_l=(0, 0, -90), pelvis=(0, 60, 0), chest=(0, -14, 18),
                       smear=0.3, limb=4, glow=3.0), "snap"),
        (A, 0.7, dict(rp=(0.45, 0.35, 0.0), ikr=0.0, ikl=0.0, th_l=(0, 60, 100), sn_l=(0, 0, -5),
                      ft_l=(0, 0, -30), th_r=(0, 25, 40), sn_r=(0, 0, -90), pelvis=(0, -100, 0),
                      chest=(0, -14, 18), smear=0.3, limb=3, glow=3.0), "snap"),
        (A, 1.0, dict(rp=(0.45, 0.20, 0.0), ikr=0.0, ikl=0.0, th_r=(0, -50, 105), sn_r=(0, 0, -4),
                      ft_r=(0, 0, -30), th_l=(0, 25, 40), sn_l=(0, 0, -90), pelvis=(0, 50, 0), chest=(0, -14, 20),
                      smear=0.3, limb=4, glow=3.0), "snap"),
        (R, 0.4, M(LAND, rp=(0.45, 0.0, 0.0), glow=1.0), "in"),
        (R, 1.0, {}, "io"),
    ]),
}

CHARACTER_CLIPS = {
    "Golden": GOLDEN_CLIPS,
    "Crimson": CRIMSON_CLIPS,
    "Steel": STEEL_CLIPS,
    "Shadow": SHADOW_CLIPS,
}


def clip_def(character: str, action: Action):
    """Return the raw clip definition for a character's action (or None)."""
    c = CHARACTER_CLIPS.get(character, {})
    if action in c:
        return c[action]
    return UNIVERSAL_CLIPS.get(action)
