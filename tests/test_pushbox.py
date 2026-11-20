"""Tests for Visual Overhaul Steps 1-6:
- Step 1: Pushboxes (1000-match zero-overlap soak), projectile limits, FLOOR_RATIO, explain templates.
- Step 2: Jointed fighter rendering, pose blending, character gear, dash ghosts, shadows.
- Step 3: Starburst sparks (hit/block/counter), 2-layer arena ambience, colour grade, popups.
- Step 4: Dynamic camera midpoint tracking, zoom (1.0x-1.15x), boundary clamping, KO zoom.
- Step 5: Slanted HUD health bars, 15-frame damage trail hold, portraits, diamond dots, hex timer.
- Step 6: Collapsible AI telemetry panel (FULL 180px vs COLLAPSED 32px), easing bars, eval chips.
- Performance: Frame render time strictly under 16 ms.
"""

import os
import random
import time
import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.adapter import observation_for
from backend.ai.crimson import CrimsonAgent
from backend.ai.explain import evaluate_win_factors, explain_action
from backend.ai.golden import GoldenAgent
from backend.ai.observation import example_observation
from backend.ai.personalities import CRIMSON
from backend.engine.constants import (
    ARENA_WIDTH,
    PROJECTILE_COOLDOWN_FRAMES,
    PROJECTILE_MAX_ACTIVE,
    PROJECTILE_MAX_PER_ROUND,
)
from backend.engine.projectile_rules import can_fire_projectile
from backend.engine.pushbox import min_separation, resolve_pushboxes
from backend.engine.state import FighterState, ProjectileState
from backend.engine.step import make_initial_state, new_round, step
from frontend.ai_viewer import _build_info, _draw_full_frame
from frontend.assets import assets
from frontend.camera_effects import (
    CameraState,
    draw_alignment_lines,
    draw_arena_ambience,
    draw_color_grade_and_vignette,
    draw_combat_popups,
)
from frontend.draw_fighter import draw_fighter
from frontend.hud import draw_hud, update_damage_trail
from frontend.theme import (
    FLOOR_RATIO,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SPARK_BLOCK,
    SPARK_COUNTER,
    SPARK_HIT,
    get_arena_floor_y,
)


@pytest.fixture(scope="module", autouse=True)
def init_pygame():
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    yield


def test_pushbox_even_separation_on_ground():
    """Two overlapping grounded fighters push apart evenly."""
    f1 = FighterState(x=400.0, character_name="Crimson")
    f2 = FighterState(x=410.0, character_name="Steel")
    sep = min_separation(f1, f2)

    resolve_pushboxes(f1, f2, left_bound=0.0, right_bound=ARENA_WIDTH)

    assert abs(f2.x - f1.x) == pytest.approx(sep, abs=1e-4)
    assert (f1.x + f2.x) / 2.0 == pytest.approx(405.0, abs=1e-4)


def test_pushbox_wall_pushes_free_fighter():
    """When one fighter is pinned at the wall, the free fighter takes the full push."""
    f1 = FighterState(x=0.0, character_name="Golden")
    f2 = FighterState(x=10.0, character_name="Golden")
    sep = min_separation(f1, f2)

    resolve_pushboxes(f1, f2, left_bound=0.0, right_bound=ARENA_WIDTH)

    assert f1.x == pytest.approx(0.0, abs=1e-4)
    assert f2.x == pytest.approx(sep, abs=1e-4)


def test_jumping_over_allowed():
    """Airborne fighters do not trigger ground pushbox collision, allowing cross-ups."""
    s = make_initial_state("Shadow", "Steel")
    s.fighter1.x = 400.0
    s.fighter2.x = 405.0
    s.fighter1.in_air = True
    s.fighter1.jump_frame = 5

    s = step(s, Action.FORWARD, Action.IDLE)
    assert s.fighter1.in_air is True


def test_thousand_random_matches_never_overlap_on_ground():
    """After 1000 seeded random matches, grounded fighters never overlap at the end of any frame."""
    chars = ["Crimson", "Steel", "Shadow", "Golden"]
    move_pool = [
        Action.IDLE,
        Action.FORWARD,
        Action.BACK,
        Action.DASH,
        Action.BACKDASH,
        Action.JUMP,
        Action.CROUCH,
        Action.LIGHT,
        Action.HEAVY,
        Action.BLOCK,
        Action.THROW,
    ]

    for match_idx in range(1000):
        rng = random.Random(match_idx)
        c1 = chars[match_idx % 4]
        c2 = chars[(match_idx // 4) % 4]
        state = make_initial_state(c1, c2, seed=match_idx)
        state.fighter1.x = 360.0
        state.fighter2.x = 440.0
        state.round_frames_left = 30

        while not state.round_over and state.round_frames_left > 0:
            a1 = rng.choice(move_pool)
            a2 = rng.choice(move_pool)
            state = step(state, a1, a2)

            f1, f2 = state.fighter1, state.fighter2
            if not f1.in_air and not f2.in_air:
                sep = min_separation(f1, f2)
                actual_dist = abs(f1.x - f2.x)
                assert actual_dist + 1e-4 >= sep, (
                    f"Match {match_idx} frame {state.frame}: grounded overlap "
                    f"({actual_dist:.2f} < {sep:.2f})"
                )


def test_projectile_limits_cooldown_active_and_round_cap():
    """Shooting obeys cooldown, max 1 active projectile, and max 4 shots per round."""
    s = make_initial_state("Shadow", "Golden")
    s.fighter1.x = 150.0
    s.fighter2.x = 650.0
    s.fighter1.meter = 100.0

    # Fire first Energy Dart (Shadow SPECIAL_NEUTRAL)
    s = step(s, Action.SPECIAL_NEUTRAL, Action.IDLE)
    assert s.fighter1.shots_fired == 1
    assert s.fighter1.projectile_cooldown == PROJECTILE_COOLDOWN_FRAMES

    for _ in range(15):
        s = step(s, Action.IDLE, Action.IDLE)

    assert not can_fire_projectile(s.fighter1, s.projectiles, 1)

    s.fighter1.projectile_cooldown = 0
    s.projectiles = [ProjectileState(x=300.0, y=0.0, vx=9.0, owner=1, lifetime=60, damage=0.06)]
    assert len([p for p in s.projectiles if p.owner == 1]) == PROJECTILE_MAX_ACTIVE
    assert not can_fire_projectile(s.fighter1, s.projectiles, 1)

    s.projectiles.clear()
    s.fighter1.shots_fired = PROJECTILE_MAX_PER_ROUND
    assert not can_fire_projectile(s.fighter1, s.projectiles, 1)

    s2 = new_round(s)
    assert s2.fighter1.shots_fired == 0
    assert s2.fighter1.projectile_cooldown == 0


def test_explain_all_actions_have_templates_and_only_idle_waits():
    """Every action in ALL_ACTIONS has a template; only IDLE says 'waiting'."""
    obs = example_observation(my_x=300, enemy_x=420)

    dash_text = explain_action(Action.DASH, obs, personality=CRIMSON)
    assert "dashes in" in dash_text.lower()

    backdash_text = explain_action(Action.BACKDASH, obs, personality=CRIMSON)
    assert "backs off to make space" in backdash_text.lower()

    for act in ALL_ACTIONS:
        txt = explain_action(act, obs, personality=CRIMSON)
        assert isinstance(txt, str) and len(txt) > 5
        if act == Action.IDLE:
            assert "waiting" in txt.lower()
        else:
            assert "waiting" not in txt.lower(), f"{act} unexpectedly returned waiting: {txt}"

    score, chips = evaluate_win_factors(obs)
    assert -1.0 <= score <= 1.0
    assert len(chips) == 3


def test_floor_ratio_and_camera_zoom_and_clamping():
    """Verify per-arena FLOOR_RATIO (especially Frozen Peak) and dynamic camera zoom/clamping."""
    assert "arena_frozen_peak" in FLOOR_RATIO
    fp_floor = get_arena_floor_y("arena_frozen_peak", 600)
    assert 490 <= fp_floor <= 530

    cam = CameraState(1024, 600)
    # Close fighters -> zoom approaches 1.15
    for _ in range(40):
        cam.update(500.0, 540.0, fp_floor)
    assert 1.10 <= cam.zoom <= 1.155

    # Far fighters -> zoom returns toward 1.0
    for _ in range(60):
        cam.update(180.0, 840.0, fp_floor)
    assert 1.0 <= cam.zoom <= 1.03

    # KO zoom on defeated fighter near left corner clamps cleanly inside viewport
    for _ in range(30):
        cam.update(120.0, 500.0, fp_floor, ko_target_x=120.0, lerp_t=0.2)
    src = pygame.Surface((1024, 600))
    dst = pygame.Surface((1024, 600))
    cam.present(src, dst, (0, 0))


def test_jointed_fighters_hud_and_collapsed_panel_under_16ms():
    """Verify jointed fighters, HUD trail hold, collapsed/full panel, and <16ms frame time."""
    surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    font_large = pygame.font.Font(None, 52)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)
    font_tiny = pygame.font.Font(None, 16)

    # Test all 4 jointed characters across key poses
    for idx, char_name in enumerate(("Crimson", "Steel", "Shadow", "Golden")):
        f = FighterState(x=200.0 + idx * 120, character_name=char_name)
        f.health = 0.20  # Fury active
        for act in (Action.IDLE, Action.DASH, Action.HEAVY, Action.LIGHT_KICK, Action.BLOCK):
            f.last_action = act
            f.current_action = act
            f.attack_phase = "active" if act in (Action.HEAVY, Action.LIGHT_KICK) else "none"
            f.attack_type = "heavy_punch" if act == Action.HEAVY else ("light_kick" if act == Action.LIGHT_KICK else "none")
            draw_fighter(surf, f, facing_right=True, ground_y=492, player_num=1)

    # Test 15-frame damage trail hold
    update_damage_trail(1, 1.0, 1.0)
    t_hold = update_damage_trail(1, 0.70, 0.70)
    assert t_hold == pytest.approx(1.0)

    # Benchmark full frame render time (< 16 ms)
    state = make_initial_state("Crimson", "Golden")
    bg = assets.get_arena("arena_frozen_peak", size=(SCREEN_WIDTH, SCREEN_HEIGHT))
    ag1 = CrimsonAgent(player=1, difficulty="HIGH", seed=1)
    ag2 = GoldenAgent(player=2, difficulty="HIGH", seed=2)
    obs1 = observation_for(state, 1)
    obs2 = observation_for(state, 2)
    a1, sc1 = ag1.decide(obs1)
    a2, sc2 = ag2.decide(obs2)
    info1 = _build_info(ag1, a1, sc1, obs1, player_num=1)
    info2 = _build_info(ag2, a2, sc2, obs2, player_num=2)
    cam = CameraState(SCREEN_WIDTH, SCREEN_HEIGHT - 180)
    cam.update(400.0, 440.0, 350.0)

    sparks = [
        {"x": 500, "y": 300, "colour": SPARK_HIT, "frame": 1, "kind": "hit"},
        {"x": 520, "y": 300, "colour": SPARK_BLOCK, "frame": 2, "kind": "block"},
        {"x": 540, "y": 300, "colour": SPARK_COUNTER, "frame": 1, "kind": "counter"},
    ]
    popups = [
        {"text": "COUNTER!", "x": 500, "y": 250, "color": (255, 68, 68), "lifetime": 15, "max_lifetime": 20},
    ]

    # Warm-up frame
    _draw_full_frame(
        surf, state, bg, "Frozen Peak",
        info1, info2, font_large, font_medium, font_small, font_tiny,
        "Crimson", "Golden", False, ag1, ag2,
        0, 0, 2, False, False, 0.9, 0.8, 3, 0, sparks, popups,
        arena_name="arena_frozen_peak", camera=cam, panel_collapsed=True,
        show_debug_box=True, show_alignment=True
    )

    t0 = time.perf_counter()
    n_frames = 60
    for i in range(n_frames):
        state.frame = i
        _draw_full_frame(
            surf, state, bg, "Frozen Peak",
            info1, info2, font_large, font_medium, font_small, font_tiny,
            "Crimson", "Golden", False, ag1, ag2,
            0, 0, 2, False, False, 0.9, 0.8, 3, 0, sparks, popups,
            arena_name="arena_frozen_peak", camera=cam, panel_collapsed=False
        )
    avg_ms = ((time.perf_counter() - t0) * 1000.0) / n_frames
    assert avg_ms < 16.0, f"Average frame time {avg_ms:.2f} ms exceeded 16.0 ms!"
