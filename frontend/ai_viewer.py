"""AI Model Fight Viewer: high-end fighting game telemetry dashboard and live match viewer.

Features:
  - Collapsible bottom telemetry panel (Tab toggles FULL 180px vs COLLAPSED 32px bar).
  - Dark glass background (80% opacity, rounded top corners, 1px cyan top border).
  - Two fighter telemetry columns:
    * Framed portrait + name + archetype + difficulty badge.
    * Active move pill badge (green=movement, red=attack, blue=defense, purple=special/super).
    * Latency & frame rate indicator with green status dot.
    * Top 4 actions with smooth 0.15s animated easing bars, gold border & arrow on chosen move.
    * White explanation sentence + italic yellow tactical commentary line.
    * Win-probability evaluation bar (-1.0 to +1.0) with center tick + top 3 factor chips.
  - Dynamic camera (midpoint lerp + zoom + KO slow-mo), 2-layer arena ambience,
    colour grading, vignette, starburst hit sparks, F2 debug box, and F4 alignment lines.
"""

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import pygame

from backend.ai.actions import ATTACKS, DEFENCE, MOVEMENT, Action
from backend.ai.adapter import observation_for
from backend.ai.choice import top_choices
from backend.ai.evaluation import evaluate
from backend.ai.explain import commentary, evaluate_win_factors, explain_action
from backend.engine.constants import ARENA_WIDTH, FPS
from backend.engine.step import make_initial_state, new_round, step
from frontend.assets import assets
from frontend.camera_effects import (
    CameraState,
    draw_alignment_lines,
    draw_arena_ambience,
    draw_color_grade_and_vignette,
    draw_combat_popups,
)
from frontend.colours import (
    BLACK,
    DARK_GREY,
    HEALTH_GREEN,
    LIGHT_GREY,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TIMER_COLOUR,
    WHITE,
)
from frontend.draw_fighter import draw_fighter
from frontend.hud import draw_hud
from frontend.screens import pause_screen
from frontend.theme import (
    P1_COLOUR,
    P2_COLOUR,
    PRIMARY_PALETTES,
    SPARK_BLOCK,
    SPARK_COUNTER,
    SPARK_HIT,
    get_arena_floor_y,
)

# Layout constants (exported for tests)
ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2
FULL_PANEL_HEIGHT = 180
COLLAPSED_PANEL_HEIGHT = 32
PANEL_HEIGHT = FULL_PANEL_HEIGHT
PANEL_Y = SCREEN_HEIGHT - FULL_PANEL_HEIGHT  # 420
GROUND_Y = get_arena_floor_y("arena_neon_rooftop", PANEL_Y)
PANEL_WIDTH = (SCREEN_WIDTH - 30) // 2
PANEL1_X = 10
PANEL2_X = SCREEN_WIDTH // 2 + 5

SPEED_OPTIONS = [
    ("0.25x", 0.25),
    ("0.5x", 0.5),
    ("1x", 1.0),
    ("2x", 2.0),
    ("4x", 4.0),
]
DEFAULT_SPEED_INDEX = 2

# Smooth 0.15s easing state for top-4 confidence bars: maps (player_num, Action) -> eased_prob
_EASED_PROBS: Dict[Tuple[int, Action], float] = {}
_VIEWPORT_CACHE: Dict[Tuple[int, int], pygame.Surface] = {}
_PANEL_SURF_CACHE: Dict[Tuple[str, int, int], pygame.Surface] = {}
_ITALIC_FONT: Optional[pygame.font.Font] = None


def _get_italic_font() -> pygame.font.Font:
    global _ITALIC_FONT
    if _ITALIC_FONT is not None:
        try:
            _ITALIC_FONT.get_height()
            return _ITALIC_FONT
        except pygame.error:
            pass
    _ITALIC_FONT = pygame.font.Font(None, 16)
    _ITALIC_FONT.set_italic(True)
    return _ITALIC_FONT


def _get_cached_panel_surf(kind: str, w: int, h: int, rgba: Tuple[int, int, int, int], radius: int) -> pygame.Surface:
    key = (kind, w, h)
    surf = _PANEL_SURF_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if kind == "top_glass":
            pygame.draw.rect(surf, rgba, (0, 0, w, h), border_top_left_radius=radius, border_top_right_radius=radius)
        else:
            pygame.draw.rect(surf, rgba, (0, 0, w, h), border_radius=radius)
        _PANEL_SURF_CACHE[key] = surf
    return surf


def _get_viewport_surface(w: int, h: int) -> pygame.Surface:
    key = (w, h)
    surf = _VIEWPORT_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface((w, h))
        _VIEWPORT_CACHE[key] = surf
    return surf


def _flip_display() -> None:
    if pygame.display.get_surface() is not None:
        try:
            pygame.display.flip()
        except pygame.error:
            pass


def _action_category_color(action: Action) -> Tuple[int, int, int]:
    """Return pill colour: green=movement, red=attack, blue=defense, purple=special/super."""
    if action in (
        Action.SPECIAL_NEUTRAL,
        Action.SPECIAL_FORWARD,
        Action.SPECIAL_BACK,
        Action.SPECIAL_DOWN,
        Action.SUPER,
    ):
        return (155, 75, 235)  # purple for special/super
    if action in DEFENCE or action in (Action.SHIELD_FRONT, Action.SHIELD_BACK):
        return (45, 135, 235)  # blue for defense
    if action in MOVEMENT:
        return (40, 185, 95)   # green for movement
    if action in ATTACKS:
        return (225, 60, 60)   # red for attack
    return (95, 105, 130)      # neutral grey-blue for IDLE/other


def run_ai_viewer(surface: pygame.Surface, clock: pygame.time.Clock,
                  agent1: Any, agent2: Any, speed_mult: float = 1.0,
                  arena_name: Optional[str] = None) -> Dict[str, Any]:
    """Run an AI-vs-AI match with collapsible telemetry dashboard and dynamic camera."""
    char1 = agent1.personality.name if getattr(agent1, "personality", None) else getattr(agent1, "character_name", "Golden")
    char2 = agent2.personality.name if getattr(agent2, "personality", None) else getattr(agent2, "character_name", "Golden")
    is_mirror = (char1 == char2)

    diff1 = getattr(agent1, "difficulty", "LOW")
    diff2 = getattr(agent2, "difficulty", "LOW")
    match_diff = "HELL" if (diff1 == "HELL" or diff2 == "HELL") else diff2

    if arena_name is None:
        arena_name = assets.pick_arena(difficulty=match_diff)

    arena_display_name = arena_name.replace("arena_", "").replace("_", " ").title()
    arena_bg_full = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))

    font_large = pygame.font.Font(None, 52)
    font_banner = pygame.font.Font(None, 72)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)
    font_tiny = pygame.font.Font(None, 16)

    speed_index = DEFAULT_SPEED_INDEX
    for i, (_, mult) in enumerate(SPEED_OPTIONS):
        if abs(mult - speed_mult) < 0.01:
            speed_index = i
            break

    show_profiling = False
    show_debug_box = False
    show_alignment = False
    panel_collapsed = False
    paused = False

    while True:
        state = make_initial_state(char1, char2)
        agent1.reset()
        agent2.reset()
        camera = CameraState(SCREEN_WIDTH, SCREEN_HEIGHT - FULL_PANEL_HEIGHT)

        stats = {
            "p1_name": agent1.name,
            "p2_name": agent2.name,
            "p1_character": char1,
            "p2_character": char2,
            "p1_kind": "ai",
            "p2_kind": "ai",
            "p1_difficulty": diff1,
            "p2_difficulty": diff2,
            "arena": arena_display_name,
            "damage_dealt_p1": 0.0,
            "damage_dealt_p2": 0.0,
            "hits_landed_p1": 0,
            "hits_landed_p2": 0,
            "blocks_p1": 0,
            "blocks_p2": 0,
            "longest_combo_p1": 0,
            "longest_combo_p2": 0,
            "rounds_history": [],
            "start_time": time.time(),
        }

        info1 = _empty_info()
        info2 = _empty_info()
        prev_health1 = 1.0
        prev_health2 = 1.0
        trail1 = 1.0
        trail2 = 1.0
        combo1 = 0
        combo2 = 0
        combo1_timer = 0
        combo2_timer = 0
        hit_flash = 0
        screen_shake = 0
        shake_dir = 0
        hit_stop = 0
        sparks: List[Dict[str, Any]] = []
        shockwaves: List[Dict[str, Any]] = []
        dust_particles: List[Dict[str, Any]] = []
        popups: List[Dict[str, Any]] = []
        f1_prev_in_air = False
        f2_prev_in_air = False
        f1_prev_kd = False
        f2_prev_kd = False
        result = None
        round_start_time = time.time()

        _show_round_intro_viewer(
            surface, clock, state, arena_bg_full, 1,
            font_banner, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, info1, info2, agent1, agent2,
            arena_display_name, speed_index, arena_name=arena_name,
            camera=camera, panel_collapsed=panel_collapsed
        )

        while not state.match_over:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        result = pause_screen(surface, clock)
                        if result == "quit":
                            return "quit"
                        elif result == "restart":
                            state.match_over = True
                            break
                    elif event.key == pygame.K_LEFT:
                        speed_index = max(0, speed_index - 1)
                    elif event.key == pygame.K_RIGHT:
                        speed_index = min(len(SPEED_OPTIONS) - 1, speed_index + 1)
                    elif event.key == pygame.K_TAB:
                        panel_collapsed = not panel_collapsed
                    elif event.key == pygame.K_F2:
                        show_debug_box = not show_debug_box
                    elif event.key == pygame.K_F3:
                        show_profiling = not show_profiling
                    elif event.key == pygame.K_F4:
                        show_alignment = not show_alignment
                    elif event.key == pygame.K_SPACE:
                        paused = not paused

            if state.match_over and result == "restart":
                break

            viewport_h = SCREEN_HEIGHT - (COLLAPSED_PANEL_HEIGHT if panel_collapsed else FULL_PANEL_HEIGHT)
            floor_y = get_arena_floor_y(arena_name, viewport_h)

            if paused:
                _draw_full_frame(
                    surface, state, arena_bg_full, arena_display_name,
                    info1, info2, font_large, font_medium, font_small, font_tiny,
                    char1, char2, is_mirror, agent1, agent2,
                    hit_flash, screen_shake, speed_index, show_profiling, paused,
                    trail1, trail2, combo1, combo2, sparks, popups,
                    shockwaves, dust_particles, shake_dir,
                    arena_name=arena_name, camera=camera,
                    panel_collapsed=panel_collapsed,
                    show_debug_box=show_debug_box,
                    show_alignment=show_alignment,
                )
                _flip_display()
                clock.tick(30)
                continue

            if hit_stop > 0:
                hit_stop -= 1
                _draw_full_frame(
                    surface, state, arena_bg_full, arena_display_name,
                    info1, info2, font_large, font_medium, font_small, font_tiny,
                    char1, char2, is_mirror, agent1, agent2,
                    hit_flash, screen_shake, speed_index, show_profiling, paused,
                    trail1, trail2, combo1, combo2, sparks, popups,
                    shockwaves, dust_particles, shake_dir,
                    arena_name=arena_name, camera=camera,
                    panel_collapsed=panel_collapsed,
                    show_debug_box=show_debug_box,
                    show_alignment=show_alignment,
                )
                _flip_display()
                _, speed_mult_cur = SPEED_OPTIONS[speed_index]
                clock.tick(int(FPS * speed_mult_cur))
                continue

            f1_was_stuck = (state.fighter1.recovery > 0)
            f2_was_stuck = (state.fighter2.recovery > 0)

            obs1 = observation_for(state, 1)
            obs2 = observation_for(state, 2)
            action1, scores1 = agent1.decide(obs1)
            action2, scores2 = agent2.decide(obs2)

            info1 = _build_info(agent1, action1, scores1, obs1, player_num=1)
            info2 = _build_info(agent2, action2, scores2, obs2, player_num=2)

            if action1 in (Action.BLOCK, Action.BLOCK_LOW):
                stats["blocks_p1"] += 1
            if action2 in (Action.BLOCK, Action.BLOCK_LOW):
                stats["blocks_p2"] += 1

            state = step(state, action1, action2)

            camera.update(
                ARENA_OFFSET_X + state.fighter1.x,
                ARENA_OFFSET_X + state.fighter2.x,
                floor_y,
            )

            h1_diff = prev_health1 - state.fighter1.health
            h2_diff = prev_health2 - state.fighter2.health

            if h1_diff > 0.001:
                stats["damage_dealt_p2"] += h1_diff
                stats["hits_landed_p2"] += 1
                is_blocked = (action1 in (Action.BLOCK, Action.BLOCK_LOW) or state.fighter1.blockstun > 0)
                is_counter = (state.fighter1.last_hit_effect == "counter" or state.fighter1.is_counter_hit)
                is_super = (action2 == Action.SUPER or h1_diff >= 0.18)
                is_heavy = (h1_diff > 0.07)

                spark_kind = "block" if is_blocked else ("counter" if is_counter else "hit")
                spark_col = SPARK_BLOCK if is_blocked else (SPARK_COUNTER if is_counter else SPARK_HIT)
                hit_x = ARENA_OFFSET_X + int(state.fighter1.x)
                hit_y = floor_y - 54
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0, "kind": spark_kind})

                hit_flash = 4 if is_counter else 2
                hit_stop = 10 if is_super else (6 if is_heavy else 3)
                screen_shake = 12 if is_super else (5 if is_heavy else 2)
                shake_dir = 1 if state.fighter2.x < state.fighter1.x else -1

                if is_blocked:
                    popups.append({"text": "BLOCKED", "x": hit_x, "y": floor_y - 95, "color": (120, 210, 255), "lifetime": 20, "max_lifetime": 20})
                elif f1_was_stuck and not is_counter:
                    popups.append({"text": "PUNISH!", "x": hit_x, "y": floor_y - 100, "color": (255, 215, 50), "lifetime": 20, "max_lifetime": 20})

                if combo2_timer > 0:
                    combo2 += 1
                else:
                    combo2 = 1
                combo2_timer = 30
                stats["longest_combo_p2"] = max(stats["longest_combo_p2"], combo2)

            if h2_diff > 0.001:
                stats["damage_dealt_p1"] += h2_diff
                stats["hits_landed_p1"] += 1
                is_blocked = (action2 in (Action.BLOCK, Action.BLOCK_LOW) or state.fighter2.blockstun > 0)
                is_counter = (state.fighter2.last_hit_effect == "counter" or state.fighter2.is_counter_hit)
                is_super = (action1 == Action.SUPER or h2_diff >= 0.18)
                is_heavy = (h2_diff > 0.07)

                spark_kind = "block" if is_blocked else ("counter" if is_counter else "hit")
                spark_col = SPARK_BLOCK if is_blocked else (SPARK_COUNTER if is_counter else SPARK_HIT)
                hit_x = ARENA_OFFSET_X + int(state.fighter2.x)
                hit_y = floor_y - 54
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0, "kind": spark_kind})

                hit_flash = 4 if is_counter else 2
                hit_stop = 10 if is_super else (6 if is_heavy else 3)
                screen_shake = 12 if is_super else (5 if is_heavy else 2)
                shake_dir = 1 if state.fighter1.x < state.fighter2.x else -1

                if is_blocked:
                    popups.append({"text": "BLOCKED", "x": hit_x, "y": floor_y - 95, "color": (120, 210, 255), "lifetime": 20, "max_lifetime": 20})
                elif f2_was_stuck and not is_counter:
                    popups.append({"text": "PUNISH!", "x": hit_x, "y": floor_y - 100, "color": (255, 215, 50), "lifetime": 20, "max_lifetime": 20})

                if combo1_timer > 0:
                    combo1 += 1
                else:
                    combo1 = 1
                combo1_timer = 30
                stats["longest_combo_p1"] = max(stats["longest_combo_p1"], combo1)

            # Dust puffs on landing, dashing, and knockdown
            f1 = state.fighter1
            f2 = state.fighter2
            for f, prev_air, prev_kd in ((f1, f1_prev_in_air, f1_prev_kd), (f2, f2_prev_in_air, f2_prev_kd)):
                fx = ARENA_OFFSET_X + int(f.x)
                if (prev_air and not f.in_air) or (not prev_kd and f.is_knocked_down):
                    for _ in range(5 if f.is_knocked_down else 4):
                        dust_particles.append({
                            "x": fx + random.uniform(-12, 12),
                            "y": floor_y - random.uniform(1, 4),
                            "vx": random.uniform(-1.8, 1.8),
                            "vy": random.uniform(-1.2, -0.3),
                            "radius": random.uniform(3.0, 5.5),
                            "lifetime": 14,
                            "max_lifetime": 14,
                            "colour": (195, 190, 180),
                        })
                if f.last_action in (Action.DASH, Action.BACKDASH) and random.random() < 0.4:
                    dust_particles.append({
                        "x": fx + random.uniform(-5, 5),
                        "y": floor_y - random.uniform(1, 3),
                        "vx": random.uniform(-1.5, 1.5),
                        "vy": random.uniform(-0.8, -0.2),
                        "radius": random.uniform(2.5, 4.5),
                        "lifetime": 12,
                        "max_lifetime": 12,
                        "colour": (185, 180, 170),
                    })
            f1_prev_in_air = f1.in_air
            f2_prev_in_air = f2.in_air
            f1_prev_kd = f1.is_knocked_down
            f2_prev_kd = f2.is_knocked_down

            for f in (state.fighter1, state.fighter2):
                effect = getattr(f, "last_hit_effect", "none")
                # "hit"/"block" fire on every plain hit; only label special events.
                if effect not in ("none", "hit", "block"):
                    fx = ARENA_OFFSET_X + int(f.x)
                    fy = floor_y - 98
                    colors = {
                        "counter": (255, 68, 68),
                        "parry": (0, 229, 255),
                        "guard_break": (224, 64, 251),
                        "burst": (255, 215, 0),
                        "tech": (0, 230, 118),
                        "wall_bounce": (255, 171, 0),
                        "ground_bounce": (255, 145, 0),
                    }
                    col = colors.get(effect, (255, 255, 255))
                    popups.append({
                        "text": f"{effect.replace('_', ' ').upper()}!",
                        "x": fx,
                        "y": fy,
                        "color": col,
                        "lifetime": 20,
                        "max_lifetime": 20,
                    })
                    f.last_hit_effect = "none"

            for p in popups:
                p["y"] -= 1.2
                p["lifetime"] -= 1
            popups = [p for p in popups if p["lifetime"] > 0]

            prev_health1 = state.fighter1.health
            prev_health2 = state.fighter2.health

            trail1 = max(state.fighter1.health, trail1 - 0.006)
            trail2 = max(state.fighter2.health, trail2 - 0.006)

            if combo1_timer > 0:
                combo1_timer -= 1
                if combo1_timer == 0:
                    combo1 = 0
            if combo2_timer > 0:
                combo2_timer -= 1
                if combo2_timer == 0:
                    combo2 = 0

            for s in sparks:
                s["frame"] += 1
            sparks = [s for s in sparks if s["frame"] < 8]

            for dp in dust_particles:
                dp["x"] += dp["vx"]
                dp["y"] += dp["vy"]
                dp["radius"] += 0.15
                dp["lifetime"] -= 1
            dust_particles = [dp for dp in dust_particles if dp["lifetime"] > 0]

            for sw in shockwaves:
                sw["lifetime"] -= 1
            shockwaves = [sw for sw in shockwaves if sw["lifetime"] > 0]

            hit_flash = max(0, hit_flash - 1)
            screen_shake = max(0, screen_shake - 1)

            obs1 = observation_for(state, 1)
            obs2 = observation_for(state, 2)
            agent1.observe(obs1, action1, action2)
            agent2.observe(obs2, action2, action1)

            _draw_full_frame(
                surface, state, arena_bg_full, arena_display_name,
                info1, info2, font_large, font_medium, font_small, font_tiny,
                char1, char2, is_mirror, agent1, agent2,
                hit_flash, screen_shake, speed_index, show_profiling, paused,
                trail1, trail2, combo1, combo2, sparks, popups,
                shockwaves, dust_particles, shake_dir,
                arena_name=arena_name, camera=camera,
                panel_collapsed=panel_collapsed,
                show_debug_box=show_debug_box,
                show_alignment=show_alignment,
            )
            _flip_display()

            _, speed_mult_cur = SPEED_OPTIONS[speed_index]
            clock.tick(int(FPS * speed_mult_cur))

            if state.round_over:
                round_dur = time.time() - round_start_time
                ended_by = "KO" if (state.fighter1.health <= 0 or state.fighter2.health <= 0) else "TIME"
                if state.round_result == "draw":
                    ended_by = "DRAW"

                stats["rounds_history"].append({
                    "round_number": state.round_number,
                    "winner_side": 1 if state.round_result == "p1" else (2 if state.round_result == "p2" else 0),
                    "ended_by": ended_by,
                    "p1_health_left": max(0.0, state.fighter1.health),
                    "p2_health_left": max(0.0, state.fighter2.health),
                    "duration_s": round(round_dur, 1),
                })

                if ended_by == "KO":
                    _slow_motion_ko_viewer(
                        surface, clock, state, arena_bg_full, arena_display_name,
                        info1, info2, font_large, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, agent1, agent2,
                        trail1, trail2, speed_mult_cur,
                        arena_name=arena_name, camera=camera,
                        panel_collapsed=panel_collapsed
                    )

                if state.match_over:
                    _show_round_banner_viewer(
                        surface, clock, state, arena_bg_full, arena_display_name,
                        ended_by, font_banner, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, info1, info2, agent1, agent2,
                        trail1, trail2, speed_index,
                        arena_name=arena_name, camera=camera,
                        panel_collapsed=panel_collapsed
                    )
                    break
                else:
                    _show_round_banner_viewer(
                        surface, clock, state, arena_bg_full, arena_display_name,
                        ended_by, font_banner, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, info1, info2, agent1, agent2,
                        trail1, trail2, speed_index,
                        arena_name=arena_name, camera=camera,
                        panel_collapsed=panel_collapsed
                    )

                    state = new_round(state)
                    agent1.reset()
                    agent2.reset()
                    camera = CameraState(SCREEN_WIDTH, viewport_h)
                    prev_health1 = 1.0
                    prev_health2 = 1.0
                    trail1 = 1.0
                    trail2 = 1.0
                    combo1 = 0
                    combo2 = 0
                    sparks.clear()
                    popups.clear()
                    round_start_time = time.time()

                    _show_round_intro_viewer(
                        surface, clock, state, arena_bg_full, state.round_number,
                        font_banner, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, info1, info2, agent1, agent2,
                        arena_display_name, speed_index, arena_name=arena_name,
                        camera=camera, panel_collapsed=panel_collapsed
                    )

        if result == "restart":
            continue

        stats["winner_side"] = 1 if state.match_result == "p1" else (2 if state.match_result == "p2" else 0)
        stats["rounds_p1"] = state.p1_rounds_won
        stats["rounds_p2"] = state.p2_rounds_won
        stats["duration_s"] = round(time.time() - stats["start_time"], 1)
        stats["status"] = "finished"
        stats["match_result"] = state.match_result
        stats["mode"] = "AI vs AI"
        return stats


# ------------------------------------------------------------------
# Info helpers
# ------------------------------------------------------------------
def _empty_info() -> Dict[str, Any]:
    return {
        "action": Action.IDLE,
        "top_choices": [(Action.IDLE, 1.0)],
        "explanation": "Fighter is waiting.",
        "commentary": "Mid-range standoff.",
        "eval_score": 0.0,
        "contributions": {},
        "eval_chips": ["+0% neutral", "+4% frame even", "+6% spacing"],
        "decision_ms": 0.4,
        "opp_model_accurate": False,
        "opp_model_prediction": None,
    }


def _build_info(
    agent: Any,
    action: Action,
    scores: Dict[Action, float],
    obs: Any,
    player_num: int = 1,
) -> Dict[str, Any]:
    """Build telemetry info dict ensuring move badge, explanation, and bars match the same decision."""
    personality = getattr(agent, "personality", None)
    variety = personality.variety if personality else 0.0

    choices: List[Tuple[Action, float]] = []
    if scores:
        raw_choices = top_choices(scores, variety, n=4)
        # Ensure the actually executed action is present in top 4 so the bars match the move!
        present_acts = [a for a, _ in raw_choices]
        if action not in present_acts and raw_choices:
            top_p = raw_choices[0][1]
            raw_choices = [(action, top_p)] + raw_choices[:3]
        # Apply 0.15s smooth easing (lerp alpha = 0.28 per frame at 60fps)
        for act_item, target_p in raw_choices:
            key = (player_num, act_item)
            prev_p = _EASED_PROBS.get(key, target_p)
            eased_p = prev_p + (target_p - prev_p) * 0.28
            _EASED_PROBS[key] = eased_p
            choices.append((act_item, eased_p))
    else:
        choices = [(action, 1.0)]

    explanation = explain_action(action, obs, scores, personality)
    comment = commentary(obs, personality)

    eval_score, eval_chips = evaluate_win_factors(obs)
    contributions = {}
    if personality:
        _, contributions = evaluate(obs, personality)

    opp_accurate = False
    opp_prediction = None
    inner = getattr(agent, "inner", agent)
    model = getattr(inner, "opp_model", None)
    if model is not None:
        opp_accurate = getattr(model, "is_confident", False)
        if getattr(model, "last_prediction", None) is not None:
            opp_prediction = model.last_prediction.name

    return {
        "action": action,
        "top_choices": choices,
        "explanation": explanation,
        "commentary": comment,
        "eval_score": eval_score,
        "contributions": contributions,
        "eval_chips": eval_chips,
        "decision_ms": getattr(agent, "last_decision_ms", 0.4),
        "opp_model_accurate": opp_accurate,
        "opp_model_prediction": opp_prediction,
    }


# ------------------------------------------------------------------
# Drawing
# ------------------------------------------------------------------
def _draw_full_frame(surface: pygame.Surface, state: Any, arena_bg: pygame.Surface,
                     arena_display_name: str, info1: Dict[str, Any], info2: Dict[str, Any],
                     font_large: pygame.font.Font, font_medium: pygame.font.Font,
                     font_small: pygame.font.Font, font_tiny: pygame.font.Font,
                     char1: str, char2: str, is_mirror: bool, agent1: Any, agent2: Any,
                     hit_flash: int, screen_shake: int, speed_index: int,
                     show_profiling: bool, paused: bool, trail1: float, trail2: float,
                     combo1: int, combo2: int, sparks: List[Dict[str, Any]],
                     popups: List[Dict[str, Any]],
                     shockwaves: Optional[List[Dict[str, Any]]] = None,
                     dust_particles: Optional[List[Dict[str, Any]]] = None,
                     shake_dir: int = 0,
                     arena_name: str = "arena_neon_rooftop",
                     camera: Optional[CameraState] = None,
                     panel_collapsed: bool = False,
                     show_debug_box: bool = False,
                     show_alignment: bool = False):
    """Draw one complete frame: camera-transformed fight viewport + HUD + telemetry dashboard."""
    panel_h = COLLAPSED_PANEL_HEIGHT if panel_collapsed else FULL_PANEL_HEIGHT
    viewport_h = SCREEN_HEIGHT - panel_h
    floor_y = get_arena_floor_y(arena_name, viewport_h)
    viewport = _get_viewport_surface(SCREEN_WIDTH, viewport_h)

    if screen_shake > 0:
        shake_x = int(shake_dir * screen_shake * 1.2 + random.randint(-2, 2))
        shake_y = random.randint(-max(1, screen_shake // 2), max(1, screen_shake // 2))
    else:
        shake_x = 0
        shake_y = 0

    # 1. Scale/blit arena background to fit fight viewport cleanly
    scaled_bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, viewport_h))
    viewport.blit(scaled_bg, (shake_x, shake_y))

    # 2. Back-layer atmospheric particles (behind fighters)
    draw_arena_ambience(viewport, arena_name, state.frame, viewport_h, layer="back")

    # 3. Ground Dust Particles (behind fighters)
    if dust_particles:
        for dp in dust_particles:
            ratio = max(0.0, min(1.0, dp["lifetime"] / max(1, dp["max_lifetime"])))
            alpha = int(145 * ratio)
            r = max(1, int(dp["radius"]))
            if alpha > 0:
                dp_surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(dp_surf, (*dp["colour"], alpha), (r + 2, r + 2), r)
                viewport.blit(dp_surf, (int(dp["x"]) + shake_x - r - 2, int(dp["y"]) + shake_y - r - 2))

    # 4. Jointed Fighters
    stage_x = ARENA_OFFSET_X + shake_x
    stage_y = floor_y + shake_y
    f1 = state.fighter1
    f2 = state.fighter2
    facing1 = (f1.x < f2.x)
    facing2 = (f2.x < f1.x)
    draw_fighter(viewport, f1, facing1, arena_offset_x=stage_x,
                 ground_y=stage_y, player_num=1, is_mirror=False, is_human=False)
    draw_fighter(viewport, f2, facing2, arena_offset_x=stage_x,
                 ground_y=stage_y, player_num=2, is_mirror=is_mirror, is_human=False)

    # 5. Projectiles
    for p in getattr(state, "projectiles", []):
        px = stage_x + int(p.x)
        py = stage_y - 45
        p_col = (0, 220, 255) if p.owner == 1 else (255, 120, 40)
        pygame.draw.circle(viewport, p_col, (px, py), 8)
        pygame.draw.circle(viewport, WHITE, (px, py), 4)
        trail_dir = -1 if p.vx > 0 else 1
        pygame.draw.line(viewport, p_col, (px, py), (px + trail_dir * 18, py), 3)

    # 6. Front-layer atmospheric particles (in front of fighters)
    draw_arena_ambience(viewport, arena_name, state.frame, viewport_h, layer="front")

    # 7. Colour grade + gentle edge vignette
    draw_color_grade_and_vignette(viewport, arena_name)

    # 8. Floating Combat Text Popups ("COUNTER!", "PUNISH!", "BLOCKED")
    if popups:
        draw_combat_popups(viewport, popups, font_medium, shake_x=shake_x, shake_y=shake_y)

    # 9. Blue Arena Box ONLY in Debug View (F2)
    if show_debug_box:
        pygame.draw.rect(
            viewport, (40, 150, 255),
            pygame.Rect(stage_x, stage_y - 200, ARENA_WIDTH, 200),
            2
        )

    # 10. F4 Red Alignment Lines
    if show_alignment:
        draw_alignment_lines(viewport, floor_y, ARENA_OFFSET_X, ARENA_WIDTH, arena_name, font_small)

    # 11. Present Camera-Transformed Fight Viewport onto Screen
    if camera is not None:
        camera.present(viewport, surface, (0, 0))
    else:
        surface.blit(viewport, (0, 0))

    # 12. Super Move Cinematic Darken
    if getattr(state, "super_freeze_frames", 0) > 0:
        dark = pygame.Surface((SCREEN_WIDTH, viewport_h), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 150))
        surface.blit(dark, (0, 0))
        super_text = font_large.render("SUPER MOVE!", True, (255, 230, 80))
        s_rect = super_text.get_rect(center=(SCREEN_WIDTH // 2, viewport_h // 2))
        shadow = font_large.render("SUPER MOVE!", True, BLACK)
        surface.blit(shadow, (s_rect.x + 3, s_rect.y + 3))
        surface.blit(super_text, s_rect)

    # 13. HUD (Slanted health bars, damage trails, portraits, diamond dots, hex timer, sparks)
    draw_hud(
        surface, state, font_medium, font_small, hit_flash=hit_flash,
        trail1=trail1, trail2=trail2, combo1=combo1, combo2=combo2,
        diff1=getattr(agent1, "difficulty", None),
        diff2=getattr(agent2, "difficulty", None),
        sparks=sparks
    )

    # 14. Pause Banner
    if paused:
        pause_text = font_medium.render("PAUSED (Press Space to Resume)", True, WHITE)
        p_rect = pause_text.get_rect(center=(SCREEN_WIDTH // 2, viewport_h // 2))
        badge_bg = pygame.Surface((p_rect.width + 30, p_rect.height + 14), pygame.SRCALPHA)
        badge_bg.fill((0, 0, 0, 200))
        surface.blit(badge_bg, (p_rect.x - 15, p_rect.y - 7))
        pygame.draw.rect(surface, (240, 200, 60), (p_rect.x - 15, p_rect.y - 7, p_rect.width + 30, p_rect.height + 14), 2, border_radius=6)
        surface.blit(pause_text, p_rect)

    # 15. Bottom AI Telemetry Dashboard (FULL 180px or COLLAPSED 32px)
    if panel_collapsed:
        _draw_collapsed_bar(
            surface, viewport_h, COLLAPSED_PANEL_HEIGHT,
            info1, info2, char1, char2, speed_index, font_small, font_tiny
        )
    else:
        _draw_full_telemetry_dashboard(
            surface, viewport_h, FULL_PANEL_HEIGHT,
            info1, info2, agent1, agent2, char1, char2,
            arena_display_name, speed_index, font_small, font_tiny
        )

    # 16. Profiling overlay (F3)
    if show_profiling:
        _draw_profiling(surface, agent1, agent2, font_tiny, state=state)


def _draw_collapsed_bar(
    surface: pygame.Surface,
    y: int,
    h: int,
    info1: Dict[str, Any],
    info2: Dict[str, Any],
    char1: str,
    char2: str,
    speed_index: int,
    font_small: pygame.font.Font,
    font_tiny: pygame.font.Font,
) -> None:
    """Draw slim 32-px status bar showing current move + confidence + latency for both AIs."""
    bar_surf = _get_cached_panel_surf("top_glass", SCREEN_WIDTH, h, (14, 18, 30, 204), 8)
    surface.blit(bar_surf, (0, y))
    pygame.draw.line(surface, (0, 215, 255), (6, y), (SCREEN_WIDTH - 6, y), 1)

    for p_num, info, cname, base_x in ((1, info1, char1, 14), (2, info2, char2, SCREEN_WIDTH // 2 + 92)):
        act = info.get("action", Action.IDLE)
        choices = info.get("top_choices", [])
        conf = choices[0][1] if choices else 1.0
        ms = max(0.2, float(info.get("decision_ms", 0.4)))

        p_col = P1_COLOUR if p_num == 1 else P2_COLOUR
        name_s = font_small.render(f"P{p_num} {cname.upper()}", True, p_col)
        surface.blit(name_s, (base_x, y + 7))

        # Active move pill
        pill_col = _action_category_color(act)
        pill_rect = pygame.Rect(base_x + name_s.get_width() + 10, y + 5, 96, 22)
        pygame.draw.rect(surface, pill_col, pill_rect, border_radius=5)
        pygame.draw.rect(surface, WHITE, pill_rect, 1, border_radius=5)
        act_lbl = font_tiny.render(act.name[:11], True, WHITE)
        surface.blit(act_lbl, act_lbl.get_rect(center=pill_rect.center))

        # Confidence + Latency with green dot
        cx_stat = pill_rect.right + 10
        conf_lbl = font_tiny.render(f"Conf: {conf:.0%}", True, TIMER_COLOUR)
        surface.blit(conf_lbl, (cx_stat, y + 9))

        dot_x = cx_stat + conf_lbl.get_width() + 12
        pygame.draw.circle(surface, (46, 215, 115), (dot_x, y + 15), 4)
        lat_lbl = font_tiny.render(f"{ms:.1f}ms / 60 FPS", True, (190, 205, 225))
        surface.blit(lat_lbl, (dot_x + 7, y + 9))

    hint = font_tiny.render("[Tab] Expand Panel", True, (130, 195, 235))
    surface.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, y + 16)))


def _draw_full_telemetry_dashboard(
    surface: pygame.Surface,
    y: int,
    h: int,
    info1: Dict[str, Any],
    info2: Dict[str, Any],
    agent1: Any,
    agent2: Any,
    char1: str,
    char2: str,
    arena_display_name: str,
    speed_index: int,
    font_small: pygame.font.Font,
    font_tiny: pygame.font.Font,
) -> None:
    """Draw the 180px dark-glass telemetry dashboard with two fighter columns."""
    # Dark glass backdrop (80% opacity = alpha 204, rounded top corners, 1px cyan top border)
    glass = _get_cached_panel_surf("top_glass", SCREEN_WIDTH, h, (14, 19, 32, 204), 12)
    surface.blit(glass, (0, y))
    pygame.draw.line(surface, (0, 215, 255), (10, y), (SCREEN_WIDTH - 10, y), 1)

    # Slim top telemetry header bar (20px) inside the 180px panel
    speed_label, _ = SPEED_OPTIONS[speed_index]
    hdr_left = font_tiny.render(f"ARENA: {arena_display_name.upper()}", True, (150, 205, 255))
    hdr_mid = font_tiny.render("[Tab] Collapse Panel  ·  [Space] Pause  ·  [F2] Debug  ·  [F3] Prof  ·  [F4] Align", True, LIGHT_GREY)
    hdr_right = font_tiny.render(f"SPEED: {speed_label} (< / >)", True, TIMER_COLOUR)
    surface.blit(hdr_left, (16, y + 4))
    surface.blit(hdr_mid, hdr_mid.get_rect(center=(SCREEN_WIDTH // 2, y + 10)))
    surface.blit(hdr_right, (SCREEN_WIDTH - hdr_right.get_width() - 16, y + 4))

    col_y = y + 22
    col_h = h - 26
    _draw_ai_panel(
        surface, PANEL1_X, col_y, PANEL_WIDTH, col_h,
        info1, getattr(agent1, "name", char1), char1,
        getattr(agent1, "difficulty", "LOW"),
        font_small, font_tiny, player_num=1
    )
    _draw_ai_panel(
        surface, PANEL2_X, col_y, PANEL_WIDTH, col_h,
        info2, getattr(agent2, "name", char2), char2,
        getattr(agent2, "difficulty", "LOW"),
        font_small, font_tiny, player_num=2
    )


def _draw_ai_panel(
    surface: pygame.Surface,
    x: int,
    y: int,
    width: int,
    height: int,
    info: Dict[str, Any],
    name: str,
    char_name: str,
    difficulty: str,
    font_small: pygame.font.Font,
    font_tiny: pygame.font.Font,
    player_num: int = 1,
):
    """Draw one fighter telemetry column inside the bottom dashboard."""
    accent_col = P1_COLOUR if player_num == 1 else P2_COLOUR
    palette = PRIMARY_PALETTES.get(char_name, {})
    archetype = palette.get("subtitle", palette.get("title", char_name))

    # Card container
    card = _get_cached_panel_surf("card", width, height, (20, 26, 44, 210), 8)
    surface.blit(card, (x, y))
    pygame.draw.rect(surface, accent_col, (x, y, width, height), 1, border_radius=8)

    # 1. Portrait (36x36) + Name + Archetype + Difficulty Badge
    port_sz = 36
    port_rect = pygame.Rect(x + 8, y + 6, port_sz, port_sz)
    port_img = assets.get_portrait(char_name, size=(port_sz, port_sz), flip_h=(player_num == 2))
    surface.blit(port_img, port_rect.topleft)
    pygame.draw.rect(surface, accent_col, port_rect, 1, border_radius=4)

    title_lbl = font_small.render(f"P{player_num} {char_name.upper()}", True, WHITE)
    surface.blit(title_lbl, (port_rect.right + 8, y + 5))

    arch_lbl = font_tiny.render(f"{archetype} · [{difficulty}]", True, (165, 180, 205))
    surface.blit(arch_lbl, (port_rect.right + 8, y + 23))

    # 2. Active Move Badge (Colored Pill)
    cur_action = info.get("action", Action.IDLE)
    pill_col = _action_category_color(cur_action)
    pill_w = 104
    pill_rect = pygame.Rect(x + 215, y + 7, pill_w, 20)
    pygame.draw.rect(surface, pill_col, pill_rect, border_radius=5)
    pygame.draw.rect(surface, (235, 240, 255), pill_rect, 1, border_radius=5)
    move_txt = font_tiny.render(cur_action.name[:12], True, WHITE)
    surface.blit(move_txt, move_txt.get_rect(center=pill_rect.center))

    # 3. Latency Indicator ("0.4ms / 60 FPS") with green status dot
    ms = max(0.2, float(info.get("decision_ms", 0.4)))
    lat_str = f"{ms:.1f}ms / 60 FPS"
    lat_surf = font_tiny.render(lat_str, True, (200, 215, 235))
    lx = x + width - lat_surf.get_width() - 10
    pygame.draw.circle(surface, (46, 215, 115), (lx - 8, y + 16), 4)
    surface.blit(lat_surf, (lx, y + 10))

    # Divider under header
    pygame.draw.line(surface, (45, 58, 88), (x + 8, y + 45), (x + width - 8, y + 45), 1)

    # 4. Left Sub-Column: Top 4 Actions with Animated Easing Bars + Gold Border & Arrow on Chosen
    short_action_names = {
        "LIGHT_KICK": "L.KICK",
        "HEAVY_KICK": "H.KICK",
        "CROUCH_JAB": "C.JAB",
        "CROUCH_KICK": "C.KICK",
        "LOW_SWEEP": "SWEEP",
        "OVERHEAD": "OVERHD",
        "ANTI_AIR": "UPPER",
        "JUMP_PUNCH": "J.PUNCH",
        "JUMP_KICK": "J.KICK",
        "BLOCK_LOW": "BLK.LO",
        "BACKDASH": "B.DASH",
        "SPECIAL_NEUTRAL": "SP.NEU",
        "SPECIAL_FORWARD": "SP.FWD",
        "SPECIAL_BACK": "SP.BCK",
        "SPECIAL_DOWN": "SP.DWN",
        "SHIELD_FRONT": "SH.FRT",
        "SHIELD_BACK": "SH.BCK",
    }

    col1_x = x + 18
    bar_y0 = y + 51
    bar_w = 80
    bar_h = 13

    choices = info.get("top_choices", [])[:4]
    for i, (act_item, prob) in enumerate(choices):
        by = bar_y0 + i * 24
        if by + bar_h > y + height - 4:
            break
        is_chosen = (act_item == cur_action)

        # Small gold selection arrow for the chosen action
        if is_chosen:
            arrow_pts = [(x + 7, by + 3), (x + 14, by + 6), (x + 7, by + 10)]
            pygame.draw.polygon(surface, (255, 215, 40), arrow_pts)

        short_name = short_action_names.get(act_item.name, act_item.name[:7])
        lbl_col = (255, 225, 80) if is_chosen else LIGHT_GREY
        act_lbl = font_tiny.render(short_name, True, lbl_col)
        surface.blit(act_lbl, (col1_x, by + 1))

        bx = col1_x + 56
        bar_rect = pygame.Rect(bx, by, bar_w, bar_h)
        pygame.draw.rect(surface, (30, 36, 54), bar_rect, border_radius=3)

        fill_w = int(bar_w * max(0.0, min(1.0, prob)))
        if fill_w > 0:
            fill_col = _action_category_color(act_item) if is_chosen else (65, 155, 215)
            pygame.draw.rect(surface, fill_col, (bx, by, fill_w, bar_h), border_radius=3)

        if is_chosen:
            pygame.draw.rect(surface, (255, 215, 40), bar_rect, 2, border_radius=3)
        else:
            pygame.draw.rect(surface, (60, 70, 95), bar_rect, 1, border_radius=3)

        pct_lbl = font_tiny.render(f"{prob:.0%}", True, WHITE if is_chosen else LIGHT_GREY)
        surface.blit(pct_lbl, (bx + bar_w + 5, by + 1))

    # 5. Right Sub-Column: White Explanation + Italic Yellow Commentary + Eval Bar & Chips
    col2_x = x + 194
    col2_w = width - 202
    col2_y = y + 50

    # Clean white explanation sentence
    explanation = info.get("explanation", "")
    _draw_wrapped_text(surface, explanation, font_tiny, WHITE, col2_x, col2_y, col2_w, 2)

    # Tactical comment in italic yellow
    comment = info.get("commentary", "")
    if comment:
        font_italic = _get_italic_font()
        c_surf = font_italic.render(f'"{comment[:44]}"', True, (255, 225, 75))
        surface.blit(c_surf, (col2_x, col2_y + 32))

    # Evaluation Score Bar (-1.0 to +1.0) with center mark
    eval_y = col2_y + 52
    eval_score = max(-1.0, min(1.0, float(info.get("eval_score", 0.0))))
    ev_lbl = font_tiny.render(f"WIN PROB {eval_score:+.2f}", True, (185, 200, 225))
    surface.blit(ev_lbl, (col2_x, eval_y))

    ev_bar_x = col2_x + 96
    ev_bar_w = max(80, col2_w - 100)
    ev_bar_h = 10
    ev_rect = pygame.Rect(ev_bar_x, eval_y + 1, ev_bar_w, ev_bar_h)
    pygame.draw.rect(surface, (26, 32, 48), ev_rect, border_radius=3)

    mid_x = ev_bar_x + ev_bar_w // 2
    half_w = ev_bar_w // 2
    span = int(abs(eval_score) * half_w)
    if span > 0:
        if eval_score >= 0:
            pygame.draw.rect(surface, (46, 210, 110), (mid_x, eval_y + 2, span, ev_bar_h - 2), border_radius=2)
        else:
            pygame.draw.rect(surface, (235, 70, 70), (mid_x - span, eval_y + 2, span, ev_bar_h - 2), border_radius=2)

    pygame.draw.rect(surface, (85, 100, 130), ev_rect, 1, border_radius=3)
    # Center mark line
    pygame.draw.line(surface, WHITE, (mid_x, eval_y - 1), (mid_x, eval_y + ev_bar_h + 2), 2)

    # Top 3 Contributing Factor Chips (+12% spacing, +8% frame adv, -5% low HP)
    chips = info.get("eval_chips", ["+10% spacing", "+4% frame adv", "+2% tempo"])[:3]
    chip_x = col2_x
    chip_y = eval_y + 18
    for chip_str in chips:
        is_pos = not chip_str.strip().startswith("-")
        c_border = (55, 195, 115) if is_pos else (225, 80, 80)
        c_bg = (22, 48, 38) if is_pos else (54, 24, 30)
        c_txt = font_tiny.render(chip_str, True, (220, 245, 230) if is_pos else (255, 210, 210))
        cw = c_txt.get_width() + 10
        ch = 16
        if chip_x + cw > x + width - 6:
            break
        c_rect = pygame.Rect(chip_x, chip_y, cw, ch)
        pygame.draw.rect(surface, c_bg, c_rect, border_radius=4)
        pygame.draw.rect(surface, c_border, c_rect, 1, border_radius=4)
        surface.blit(c_txt, c_txt.get_rect(center=c_rect.center))
        chip_x += cw + 5


def _draw_wrapped_text(surface: pygame.Surface, text: str, font: pygame.font.Font,
                       colour: Tuple[int, int, int], x: int, y: int,
                       max_width: int, max_lines: int):
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = current_line + " " + word if current_line else word
        if font.size(test)[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
        if len(lines) >= max_lines:
            break
    if current_line and len(lines) < max_lines:
        lines.append(current_line)

    for i, line in enumerate(lines):
        rendered = font.render(line, True, colour)
        surface.blit(rendered, (x, y + i * 14))


def _draw_profiling(
    surface: pygame.Surface,
    agent1: Any,
    agent2: Any,
    font_tiny: pygame.font.Font,
    state: Optional[Any] = None,
):
    """Draw the F3 debug & profiling overlay."""
    from backend.ai.difficulty import adrenaline_level, effective_profile

    overlay = pygame.Surface((350, 145), pygame.SRCALPHA)
    overlay.fill((8, 12, 22, 215))
    surface.blit(overlay, (12, 85))
    pygame.draw.rect(surface, (80, 120, 190), (12, 85, 350, 145), 1, border_radius=5)

    y = 91
    x = 18
    header = font_tiny.render("F3 AI Difficulty & Adrenaline Debug", True, TIMER_COLOUR)
    surface.blit(header, (x, y))
    y += 16

    fighters = [
        (agent1, getattr(state, "fighter1", None), 1),
        (agent2, getattr(state, "fighter2", None), 2),
    ]
    for agent, f_state, p_num in fighters:
        name = getattr(agent, "name", f"P{p_num}")
        mode = getattr(agent, "difficulty", "LOW")
        hp = getattr(f_state, "health", 1.0) if f_state is not None else 1.0
        zone = getattr(agent, "health_zone", adrenaline_level(hp))
        prof = getattr(agent, "current_profile", None) or effective_profile(mode, hp)
        react_f = getattr(agent, "delay", prof.reaction_delay)
        mistake_pct = getattr(agent, "mistake_chance", prof.mistake_chance) * 100.0
        block_pct = getattr(agent, "block_chance", prof.block_chance) * 100.0
        ms = getattr(agent, "last_decision_ms", 0.0)
        slowest = getattr(agent, "slowest_decision_ms", 0.0)

        zone_col = (100, 255, 120) if zone == "GREEN" else ((255, 220, 80) if zone == "YELLOW" else (255, 80, 80))
        line1 = f"P{p_num} {name} [{mode}] | Zone: {zone} | {ms:.2f}ms (max {slowest:.1f}ms)"
        line2 = f"  React: {react_f}f | Mistake: {mistake_pct:.1f}% | Block: {block_pct:.1f}%"
        surface.blit(font_tiny.render(line1, True, zone_col), (x, y))
        y += 14
        surface.blit(font_tiny.render(line2, True, WHITE), (x, y))
        y += 16


# ------------------------------------------------------------------
# Cinematic Banners & Transitions
# ------------------------------------------------------------------
def _show_round_intro_viewer(surface: pygame.Surface, clock: pygame.time.Clock,
                             state: Any, arena_bg: pygame.Surface, round_num: int,
                             font_banner: pygame.font.Font, font_medium: pygame.font.Font,
                             font_small: pygame.font.Font, font_tiny: pygame.font.Font,
                             char1: str, char2: str, is_mirror: bool,
                             info1: Dict[str, Any], info2: Dict[str, Any],
                             agent1: Any, agent2: Any, arena_display_name: str,
                             speed_index: int, arena_name: str = "arena_neon_rooftop",
                             camera: Optional[CameraState] = None,
                             panel_collapsed: bool = False):
    _, speed_mult = SPEED_OPTIONS[speed_index]
    frames1 = int(24 * (1.0 / max(0.5, speed_mult)))
    for _ in range(frames1):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_full_frame(
            surface, state, arena_bg, arena_display_name,
            info1, info2, font_banner, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, agent1, agent2,
            0, 0, speed_index, False, False, 1.0, 1.0, 0, 0, [], [],
            arena_name=arena_name, camera=camera, panel_collapsed=panel_collapsed
        )
        _draw_center_banner_viewer(surface, f"ROUND {round_num}", font_banner, (255, 220, 80))
        _flip_display()
        clock.tick(int(FPS * speed_mult))

    frames2 = int(14 * (1.0 / max(0.5, speed_mult)))
    for _ in range(frames2):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_full_frame(
            surface, state, arena_bg, arena_display_name,
            info1, info2, font_banner, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, agent1, agent2,
            0, 0, speed_index, False, False, 1.0, 1.0, 0, 0, [], [],
            arena_name=arena_name, camera=camera, panel_collapsed=panel_collapsed
        )
        _draw_center_banner_viewer(surface, "FIGHT!", font_banner, (255, 60, 60))
        _flip_display()
        clock.tick(int(FPS * speed_mult))


def _show_round_banner_viewer(surface: pygame.Surface, clock: pygame.time.Clock,
                              state: Any, arena_bg: pygame.Surface, arena_display_name: str,
                              banner_type: str, font_banner: pygame.font.Font,
                              font_medium: pygame.font.Font, font_small: pygame.font.Font,
                              font_tiny: pygame.font.Font, char1: str, char2: str,
                              is_mirror: bool, info1: Dict[str, Any], info2: Dict[str, Any],
                              agent1: Any, agent2: Any, trail1: float, trail2: float,
                              speed_index: int, arena_name: str = "arena_neon_rooftop",
                              camera: Optional[CameraState] = None,
                              panel_collapsed: bool = False):
    banner_text = "K.O."
    banner_col = (255, 50, 50)
    if banner_type == "TIME":
        banner_text = "TIME UP"
        banner_col = (240, 240, 90)
    elif banner_type == "DRAW":
        banner_text = "DRAW"
        banner_col = (200, 210, 230)

    for _ in range(35):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        if camera is not None:
            camera.zoom += (1.0 - camera.zoom) * 0.15
        _draw_full_frame(
            surface, state, arena_bg, arena_display_name,
            info1, info2, font_banner, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, agent1, agent2,
            0, 0, speed_index, False, False, trail1, trail2, 0, 0, [], [],
            arena_name=arena_name, camera=camera, panel_collapsed=panel_collapsed
        )
        _draw_center_banner_viewer(surface, banner_text, font_banner, banner_col)
        _flip_display()
        clock.tick(30)


def _slow_motion_ko_viewer(surface: pygame.Surface, clock: pygame.time.Clock,
                           state: Any, arena_bg: pygame.Surface, arena_display_name: str,
                           info1: Dict[str, Any], info2: Dict[str, Any],
                           font_large: pygame.font.Font, font_medium: pygame.font.Font,
                           font_small: pygame.font.Font, font_tiny: pygame.font.Font,
                           char1: str, char2: str, is_mirror: bool,
                           agent1: Any, agent2: Any, trail1: float, trail2: float,
                           speed_mult: float, arena_name: str = "arena_neon_rooftop",
                           camera: Optional[CameraState] = None,
                           panel_collapsed: bool = False):
    """KO slow-motion (0.3x speed for 30 frames) zooming in on the defeated fighter."""
    slow_fps = max(12, int(FPS * speed_mult * 0.3))
    loser = state.fighter1 if state.fighter1.health <= state.fighter2.health else state.fighter2
    ko_x = ARENA_OFFSET_X + loser.x
    viewport_h = SCREEN_HEIGHT - (COLLAPSED_PANEL_HEIGHT if panel_collapsed else FULL_PANEL_HEIGHT)
    floor_y = get_arena_floor_y(arena_name, viewport_h)

    for frame_i in range(30):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        if camera is not None:
            camera.update(
                ARENA_OFFSET_X + state.fighter1.x,
                ARENA_OFFSET_X + state.fighter2.x,
                floor_y,
                ko_target_x=ko_x,
                lerp_t=0.16,
            )
        flash = 3 if frame_i < 3 else 0
        _draw_full_frame(
            surface, state, arena_bg, arena_display_name,
            info1, info2, font_large, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, agent1, agent2,
            flash, 0, 2, False, False, trail1, trail2, 0, 0, [], [],
            arena_name=arena_name, camera=camera, panel_collapsed=panel_collapsed
        )
        _flip_display()
        clock.tick(slow_fps)


def _draw_center_banner_viewer(surface: pygame.Surface, text: str,
                               font: pygame.font.Font, colour: Tuple[int, int, int]):
    center_y = 200
    banner_surf = font.render(text, True, colour)
    rect = banner_surf.get_rect(center=(SCREEN_WIDTH // 2, center_y))

    strip_h = rect.height + 20
    strip_surf = pygame.Surface((SCREEN_WIDTH, strip_h), pygame.SRCALPHA)
    strip_surf.fill((0, 0, 0, 175))
    surface.blit(strip_surf, (0, rect.top - 10))

    shadow = font.render(text, True, BLACK)
    surface.blit(shadow, rect.move(3, 3))
    surface.blit(banner_surf, rect)
