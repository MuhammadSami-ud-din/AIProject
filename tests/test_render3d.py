"""Tests for the real-3D fight renderer (frontend/render3d).

Pure-Python parts (skeleton, clips, timing) always run.  GL parts are skipped
when no OpenGL 3.3 context can be created (e.g. headless CI).
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from backend.ai.actions import Action
from backend.engine.moves import CHARACTER_MOVES, get_move
from backend.engine.step import make_initial_state, step
from frontend.render3d import animation as anim
from frontend.render3d import clips as C
from frontend.render3d.characters import BUILDERS, get_model
from frontend.render3d.skeleton import NUM_BONES, POSE_SIZE, SMEAR, Skeleton

CHARACTERS = list(CHARACTER_MOVES)


def _gl_ok():
    from frontend.render3d import gl_available
    return gl_available()


# ---------------------------------------------------------------------------
# Skeleton / pose sampling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", CHARACTERS)
def test_every_character_has_a_distinct_model(name):
    assert name in BUILDERS
    model = get_model(name)
    data = model.bake()
    assert data.shape[1] == 14 and len(data) > 1000
    assert np.isfinite(data).all()
    assert model.num_gpu_bones <= 48
    # bone ids must address existing bones
    assert data[:, 13].max() < model.num_gpu_bones


def test_models_differ_in_palette_and_proportions():
    sigs = set()
    for name in CHARACTERS:
        m = get_model(name)
        cols = tuple(np.round(m.bake()[:, 6:9].mean(axis=0), 3))
        sigs.add((cols, m.props.pelvis_h, m.props.torso_w))
    assert len(sigs) == len(CHARACTERS)


def test_pose_sampling_is_deterministic():
    for name in CHARACTERS:
        clip = anim.get_clip(name, Action.HEAVY_KICK)
        m = get_move(name, Action.HEAVY_KICK)
        a = [clip.sample(t * 0.5, m.startup, m.active, m.recovery) for t in range(80)]
        b = [clip.sample(t * 0.5, m.startup, m.active, m.recovery) for t in range(80)]
        for x, y in zip(a, b):
            assert x.shape == (POSE_SIZE,)
            np.testing.assert_array_equal(x, y)
        sk1, sk2 = Skeleton(get_model(name).props), Skeleton(get_model(name).props)
        np.testing.assert_allclose(sk1.solve(a[20]).copy(), sk2.solve(a[20]).copy())


def test_stance_feet_are_planted_on_the_floor():
    for name in CHARACTERS:
        sk = Skeleton(get_model(name).props)
        M = sk.solve(anim.stance_vector(name))
        for foot in ("foot_l", "foot_r"):
            from frontend.render3d.skeleton import BONE_INDEX
            ankle_y = M[BONE_INDEX[foot]][1, 3]
            assert abs(ankle_y - sk.props.ankle_h) < 0.03, (name, foot, ankle_y)


# ---------------------------------------------------------------------------
# Clip coverage and timing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", CHARACTERS)
def test_every_move_has_an_animation_clip(name):
    missing = [a.name for a in CHARACTER_MOVES[name] if anim.get_clip(name, a) is None]
    assert not missing, f"{name} moves without a clip: {missing}"


def test_specials_and_supers_are_character_specific():
    for action in (Action.SPECIAL_NEUTRAL, Action.SPECIAL_FORWARD, Action.SPECIAL_BACK, Action.SPECIAL_DOWN,
                   Action.SUPER):
        defs = {id(C.clip_def(n, action)) for n in CHARACTERS}
        assert len(defs) == len(CHARACTERS), action


def test_clip_keys_use_known_easings_and_channels():
    for name in CHARACTERS:
        for action in CHARACTER_MOVES[name]:
            clip = anim.get_clip(name, action)
            for phase, frac, pose, ease in clip.keys:
                assert phase in ("s", "a", "r", "t")
                assert ease in anim.EASINGS
                assert np.isfinite(pose).all()


@pytest.mark.parametrize("name", CHARACTERS)
def test_full_extension_lands_on_first_active_frame(name):
    """The strike pose (first 'snap' key) is reached exactly when the hitbox goes live."""
    for action, move in CHARACTER_MOVES[name].items():
        clip = anim.get_clip(name, action)
        if not any(k[3] == "snap" for k in clip.keys):
            continue
        s, a, r = move.startup, move.active, move.recovery
        t_ext = clip.full_extension_time(s, a, r)
        limit = s + a + (r * 0.3 if move.is_counter_stance else 0.0)  # counters strike back late
        assert s - 1e-6 <= t_ext <= limit, (action, t_ext, s, a)
        if clip.limb and t_ext == s:
            pose = clip.sample(float(s), s, a, r)
            if action in C.UNIVERSAL_CLIPS:
                assert pose[SMEAR] > 0.0, (name, action)  # striking limb is stretched on contact
            before = clip.sample(max(0.0, s - 1.0), s, a, r)
            after_recovery = clip.sample(float(s + a + r), s, a, r)
            # the limb moves away from the strike pose before and after the hit
            assert np.abs(pose - before).sum() > 1.0 or s <= 1
            assert np.abs(pose - after_recovery).sum() > 1.0


def test_engine_phase_maps_to_clip_time():
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x, state.fighter2.x = 300.0, 500.0
    move = get_move("Crimson", Action.HEAVY_KICK)
    s = step(state, Action.HEAVY_KICK, Action.IDLE)
    times = []
    for _ in range(move.startup + move.active + move.recovery + 2):
        mt = anim.move_time(s.fighter1)
        if mt is not None:
            times.append((s.fighter1.attack_phase, mt[0]))
        s = step(s, Action.IDLE, Action.IDLE)
    first_active = next(t for ph, t in times if ph == "active")
    assert first_active == move.startup
    ts = [t for _, t in times]
    assert ts == sorted(ts)


def test_animator_drives_full_match_without_gl():
    """Animators + skeleton run on real engine states (no GL needed)."""
    state = make_initial_state("Shadow", "Golden")
    a1, a2 = anim.FighterAnimator("Shadow", 1), anim.FighterAnimator("Golden", 2)
    script = [Action.FORWARD] * 10 + [Action.LIGHT, Action.IDLE, Action.HEAVY_KICK] + [Action.IDLE] * 20 + \
        [Action.JUMP] + [Action.IDLE] * 10 + [Action.JUMP_KICK] + [Action.IDLE] * 30 + [Action.LOW_SWEEP]
    for act in script * 2:
        state = step(state, act, Action.BLOCK)
        a1.update(state.fighter1, state.fighter2, state)
        a2.update(state.fighter2, state.fighter1, state)
        for a, f in ((a1, state.fighter1), (a2, state.fighter2)):
            W = a.compute(0.5, f.x, 1 / 60)
            assert np.isfinite(W).all()
            # feet never sink far below the floor
            assert min(a.tips[3][1], a.tips[4][1]) > -0.15


# ---------------------------------------------------------------------------
# Fallback + GL smoke render
# ---------------------------------------------------------------------------

def test_renderer_falls_back_cleanly_without_gl(monkeypatch):
    import frontend.render3d as r3d_pkg
    import moderngl

    def boom(*a, **k):
        raise RuntimeError("no GL here")

    r3d_pkg.reset_failure()
    monkeypatch.setattr(moderngl, "create_standalone_context", boom)
    assert r3d_pkg.create_renderer(320, 200) is None
    assert "no GL" in r3d_pkg.last_error()
    assert r3d_pkg.gl_available() is False
    r3d_pkg.reset_failure()


def test_fight_screen_uses_2d_when_3d_unavailable(monkeypatch):
    import frontend.fight_screen as fs
    monkeypatch.setattr(fs, "_R3D", None)
    monkeypatch.setattr(fs, "_R3D_FAILED", True)
    assert fs._get_renderer3d() is None
    assert fs._resolve_renderer_mode(None, {"renderer": "2d"}) == "2d"
    assert fs._resolve_renderer_mode(None, {}) == "3d"
    assert fs.SUPPORTS_LOCAL_VERSUS is True
    # the 2D scene still draws
    pygame.init()
    surf = pygame.display.set_mode((1024, 600))
    st = make_initial_state("Golden", "Steel")
    fs._draw_fight_scene(surf, st, pygame.Surface((1024, 600)), pygame.font.Font(None, 28),
                         pygame.font.Font(None, 20), "Golden", "Steel", False, 1,
                         0, 0, 1.0, 1.0, 0, 0, None, None, [])


@pytest.mark.skipif(not _gl_ok(), reason="OpenGL 3.3 context unavailable")
def test_headless_smoke_render():
    from frontend.render3d import create_renderer
    pygame.init()
    r = create_renderer(320, 200, samples=2)
    assert r is not None
    r.setup("Crimson", "Steel", "arena_volcanic_forge")
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x, state.fighter2.x = 340.0, 420.0
    prev = None
    surf = None
    for act in [Action.IDLE] * 3 + [Action.HEAVY] + [Action.IDLE] * 14:
        nxt = step(state, act, Action.IDLE)
        r.push_step(state if prev else None, nxt)
        prev, state = state, nxt
        surf = r.render(state, 0.0, 1 / 60)
    assert surf.get_size() == (320, 200)
    arr = pygame.surfarray.array3d(surf)
    assert arr.std() > 5.0          # not a blank frame
    assert r.mean_ms() > 0.0


def test_local_versus_and_fixed_timestep(monkeypatch):
    """run_fight(human_player="both") plays with two input handlers and returns the usual contract."""
    import frontend.fight_screen as fs
    import frontend.main as game_main

    pygame.init()
    screen = pygame.display.set_mode((1024, 600))

    class FastClock:
        def tick(self, *a, **k):
            return 0

    flips = {"n": 0}

    def fake_flip(*a, **k):
        flips["n"] += 1
        if flips["n"] == 150:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    steps = {"n": 0}
    real_step = fs.step

    def counting_step(*a, **k):
        steps["n"] += 1
        return real_step(*a, **k)

    monkeypatch.setattr(pygame.display, "flip", fake_flip)
    monkeypatch.setattr(fs, "step", counting_step)
    a1 = game_main._HumanAgent(name="P1", player=1, character="Crimson")
    a2 = game_main._HumanAgent(name="P2", player=2, character="Shadow")
    result = fs.run_fight(screen, FastClock(), a1, a2, human_player="both", arena_name="arena_frozen_peak")
    assert result == "quit"
    assert steps["n"] > 50      # one fixed step per frame with a non-sleeping clock
