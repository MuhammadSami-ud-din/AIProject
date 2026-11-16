"""AI Model Fight Viewer: watch two AIs fight with full thinking display.

Shows each fighter's top move choices with confidence bars,
evaluation contributions, opponent model prediction indicator,
and a toggleable F3 profiling overlay. Speed is adjustable.
Features rich arena backgrounds, projectile visuals, combat popups,
hit sparks, screen shake, damage trails, and real match statistics.
"""

import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import pygame

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.ai.choice import top_choices
from backend.ai.evaluation import evaluate
from backend.ai.explain import commentary, explain_action
from backend.engine.constants import ARENA_WIDTH, FPS
from backend.engine.step import make_initial_state, new_round, step
from frontend.assets import assets
from frontend.colours import (
    BLACK,
    DARK_GREY,
    HEALTH_GREEN,
    LIGHT_GREY,
    MENU_BG,
    MENU_HIGHLIGHT,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TIMER_COLOUR,
    WHITE,
)
from frontend.draw_fighter import draw_fighter
from frontend.hud import draw_hud
from frontend.screens import pause_screen
from frontend.theme import (
    FLOOR_HEIGHT,
    P1_COLOUR,
    P2_COLOUR,
    SPARK_BLOCK,
    SPARK_HIT,
)

# Layout constants
ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2
GROUND_Y = 350          # raised to make room for info panels below
PANEL_Y = 412           # where the info panels start
PANEL_HEIGHT = 178      # height of each info panel
PANEL_WIDTH = (SCREEN_WIDTH - 36) // 2  # 494 px
PANEL1_X = 12
PANEL2_X = SCREEN_WIDTH // 2 + 6       # 518 px

# Speed settings: list of (label, fps_multiplier)
SPEED_OPTIONS = [
    ("0.25x", 0.25),
    ("0.5x", 0.5),
    ("1x", 1.0),
    ("2x", 2.0),
    ("4x", 4.0),
]
DEFAULT_SPEED_INDEX = 2  # start at 1x


def _flip_display() -> None:
    """Safely flip the display if a display mode has been set."""
    if pygame.display.get_surface() is not None:
        try:
            pygame.display.flip()
        except pygame.error:
            pass


def run_ai_viewer(surface: pygame.Surface, clock: pygame.time.Clock,
                  agent1: Any, agent2: Any, speed_mult: float = 1.0,
                  arena_name: Optional[str] = None) -> Dict[str, Any]:
    """Run an AI-vs-AI match with full thinking display and applied arena background.

    agent1, agent2: the two AI agents.
    speed_mult: initial speed from Settings (0.5, 1.0, 2.0, 3.0).
                Can still be changed with Left/Right arrows during the fight.
    arena_name: optional arena name; if None, picked dynamically based on difficulty.
    Returns: full match statistics dict, or 'quit'.
    """
    char1 = agent1.personality.name if getattr(agent1, "personality", None) else getattr(agent1, "character_name", "Golden")
    char2 = agent2.personality.name if getattr(agent2, "personality", None) else getattr(agent2, "character_name", "Golden")
    is_mirror = (char1 == char2)

    diff1 = getattr(agent1, "difficulty", "LOW")
    diff2 = getattr(agent2, "difficulty", "LOW")
    match_diff = "HELL" if (diff1 == "HELL" or diff2 == "HELL") else diff2

    # Pick and load arena background
    if arena_name is None:
        arena_name = assets.pick_arena(difficulty=match_diff)

    arena_display_name = arena_name.replace("arena_", "").replace("_", " ").title()
    arena_bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))

    # Fonts
    font_large = pygame.font.Font(None, 52)
    font_banner = pygame.font.Font(None, 72)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)
    font_tiny = pygame.font.Font(None, 16)

    # State for the viewer
    speed_index = DEFAULT_SPEED_INDEX
    for i, (_, mult) in enumerate(SPEED_OPTIONS):
        if abs(mult - speed_mult) < 0.01:
            speed_index = i
            break
    show_profiling = False
    paused = False

    while True:
        state = make_initial_state(char1, char2)
        agent1.reset()
        agent2.reset()

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
        result = None
        round_start_time = time.time()

        # Round 1 Intro Banner
        _show_round_intro_viewer(
            surface, clock, state, arena_bg, 1,
            font_banner, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, info1, info2, agent1, agent2,
            arena_display_name, speed_index
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
                    elif event.key == pygame.K_F3:
                        show_profiling = not show_profiling
                    elif event.key == pygame.K_SPACE:
                        paused = not paused

            if state.match_over and result == "restart":
                break

            if paused:
                _draw_full_frame(
                    surface, state, arena_bg, arena_display_name,
                    info1, info2, font_large, font_medium, font_small, font_tiny,
                    char1, char2, is_mirror, agent1, agent2,
                    hit_flash, screen_shake, speed_index, show_profiling, paused,
                    trail1, trail2, combo1, combo2, sparks, popups,
                    shockwaves, dust_particles, shake_dir
                )
                _flip_display()
                clock.tick(30)
                continue

            if hit_stop > 0:
                hit_stop -= 1
                _draw_full_frame(
                    surface, state, arena_bg, arena_display_name,
                    info1, info2, font_large, font_medium, font_small, font_tiny,
                    char1, char2, is_mirror, agent1, agent2,
                    hit_flash, screen_shake, speed_index, show_profiling, paused,
                    trail1, trail2, combo1, combo2, sparks, popups,
                    shockwaves, dust_particles, shake_dir
                )
                _flip_display()
                _, speed_mult = SPEED_OPTIONS[speed_index]
                clock.tick(int(FPS * speed_mult))
                continue

            obs1 = observation_for(state, 1)
            obs2 = observation_for(state, 2)
            action1, scores1 = agent1.decide(obs1)
            action2, scores2 = agent2.decide(obs2)

            info1 = _build_info(agent1, action1, scores1, obs1)
            info2 = _build_info(agent2, action2, scores2, obs2)

            if action1 in (Action.BLOCK, Action.BLOCK_LOW):
                stats["blocks_p1"] += 1
            if action2 in (Action.BLOCK, Action.BLOCK_LOW):
                stats["blocks_p2"] += 1

            state = step(state, action1, action2)

            h1_diff = prev_health1 - state.fighter1.health
            h2_diff = prev_health2 - state.fighter2.health

            if h1_diff > 0.001:
                stats["damage_dealt_p2"] += h1_diff
                stats["hits_landed_p2"] += 1
                hit_flash = 3
                is_blocked = (action1 in (Action.BLOCK, Action.BLOCK_LOW))
                spark_col = SPARK_BLOCK if is_blocked else SPARK_HIT
                hit_x = ARENA_OFFSET_X + int(state.fighter1.x)
                hit_y = GROUND_Y - 50
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0})
                is_heavy = (h1_diff > 0.08)
                hit_stop = 4 if is_heavy else 2
                screen_shake = 6 if is_heavy else 3
                shake_dir = 1 if state.fighter2.x < state.fighter1.x else -1
                shockwaves.append({
                    "x": hit_x,
                    "y": hit_y,
                    "radius": 6.0,
                    "max_radius": 40.0 if is_heavy else 25.0,
                    "colour": (80, 220, 255) if is_blocked else (255, 255, 255),
                    "lifetime": 9 if is_heavy else 6,
                    "max_lifetime": 9 if is_heavy else 6,
                    "width": 3 if is_heavy else 2,
                })

                if combo2_timer > 0:
                    combo2 += 1
                else:
                    combo2 = 1
                combo2_timer = 30
                stats["longest_combo_p2"] = max(stats["longest_combo_p2"], combo2)

            if h2_diff > 0.001:
                stats["damage_dealt_p1"] += h2_diff
                stats["hits_landed_p1"] += 1
                hit_flash = 3
                is_blocked = (action2 in (Action.BLOCK, Action.BLOCK_LOW))
                spark_col = SPARK_BLOCK if is_blocked else SPARK_HIT
                hit_x = ARENA_OFFSET_X + int(state.fighter2.x)
                hit_y = GROUND_Y - 50
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0})
                is_heavy = (h2_diff > 0.08)
                hit_stop = 4 if is_heavy else 2
                screen_shake = 6 if is_heavy else 3
                shake_dir = 1 if state.fighter1.x < state.fighter2.x else -1
                shockwaves.append({
                    "x": hit_x,
                    "y": hit_y,
                    "radius": 6.0,
                    "max_radius": 40.0 if is_heavy else 25.0,
                    "colour": (80, 220, 255) if is_blocked else (255, 255, 255),
                    "lifetime": 9 if is_heavy else 6,
                    "max_lifetime": 9 if is_heavy else 6,
                    "width": 3 if is_heavy else 2,
                })

                if combo1_timer > 0:
                    combo1 += 1
                else:
                    combo1 = 1
                combo1_timer = 30
                stats["longest_combo_p1"] = max(stats["longest_combo_p1"], combo1)

            # Ground dust particles on landing or dashing
            f1 = state.fighter1
            f2 = state.fighter2
            if f1_prev_in_air and not f1.in_air:
                fx = ARENA_OFFSET_X + int(f1.x)
                for _ in range(4):
                    dust_particles.append({
                        "x": fx + random.uniform(-10, 10),
                        "y": GROUND_Y - random.uniform(1, 4),
                        "vx": random.uniform(-1.5, 1.5),
                        "vy": random.uniform(-1.2, -0.3),
                        "radius": random.uniform(3.0, 5.5),
                        "lifetime": 14,
                        "max_lifetime": 14,
                        "colour": (190, 185, 175),
                    })
            if f2_prev_in_air and not f2.in_air:
                fx = ARENA_OFFSET_X + int(f2.x)
                for _ in range(4):
                    dust_particles.append({
                        "x": fx + random.uniform(-10, 10),
                        "y": GROUND_Y - random.uniform(1, 4),
                        "vx": random.uniform(-1.5, 1.5),
                        "vy": random.uniform(-1.2, -0.3),
                        "radius": random.uniform(3.0, 5.5),
                        "lifetime": 14,
                        "max_lifetime": 14,
                        "colour": (190, 185, 175),
                    })
            if getattr(f1, "is_dashing", False) and random.random() < 0.35:
                fx = ARENA_OFFSET_X + int(f1.x)
                d_dir = -1.5 if (f1.x < f2.x) else 1.5
                dust_particles.append({
                    "x": fx + random.uniform(-4, 4),
                    "y": GROUND_Y - random.uniform(1, 3),
                    "vx": d_dir * random.uniform(0.8, 1.8),
                    "vy": random.uniform(-0.8, -0.2),
                    "radius": random.uniform(2.5, 4.5),
                    "lifetime": 12,
                    "max_lifetime": 12,
                    "colour": (180, 175, 165),
                })
            if getattr(f2, "is_dashing", False) and random.random() < 0.35:
                fx = ARENA_OFFSET_X + int(f2.x)
                d_dir = -1.5 if (f2.x < f1.x) else 1.5
                dust_particles.append({
                    "x": fx + random.uniform(-4, 4),
                    "y": GROUND_Y - random.uniform(1, 3),
                    "vx": d_dir * random.uniform(0.8, 1.8),
                    "vy": random.uniform(-0.8, -0.2),
                    "radius": random.uniform(2.5, 4.5),
                    "lifetime": 12,
                    "max_lifetime": 12,
                    "colour": (180, 175, 165),
                })
            f1_prev_in_air = f1.in_air
            f2_prev_in_air = f2.in_air

            for f in (state.fighter1, state.fighter2):
                effect = getattr(f, "last_hit_effect", "none")
                if effect != "none":
                    fx = ARENA_OFFSET_X + int(f.x)
                    fy = GROUND_Y - 95
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
                        "lifetime": 35,
                    })
                    f.last_hit_effect = "none"

            for p in popups:
                p["y"] -= 1.0
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
                surface, state, arena_bg, arena_display_name,
                info1, info2, font_large, font_medium, font_small, font_tiny,
                char1, char2, is_mirror, agent1, agent2,
                hit_flash, screen_shake, speed_index, show_profiling, paused,
                trail1, trail2, combo1, combo2, sparks, popups,
                shockwaves, dust_particles, shake_dir
            )
            _flip_display()

            _, speed_mult = SPEED_OPTIONS[speed_index]
            clock.tick(int(FPS * speed_mult))

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

                if state.match_over:
                    _slow_motion_ko_viewer(
                        surface, clock, state, arena_bg, arena_display_name,
                        info1, info2, font_large, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, agent1, agent2,
                        trail1, trail2, speed_mult
                    )
                    _show_round_banner_viewer(
                        surface, clock, state, arena_bg, arena_display_name,
                        ended_by, font_banner, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, info1, info2, agent1, agent2,
                        trail1, trail2, speed_index
                    )
                    break
                else:
                    _show_round_banner_viewer(
                        surface, clock, state, arena_bg, arena_display_name,
                        ended_by, font_banner, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, info1, info2, agent1, agent2,
                        trail1, trail2, speed_index
                    )

                    state = new_round(state)
                    agent1.reset()
                    agent2.reset()
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
                        surface, clock, state, arena_bg, state.round_number,
                        font_banner, font_medium, font_small, font_tiny,
                        char1, char2, is_mirror, info1, info2, agent1, agent2,
                        arena_display_name, speed_index
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
    """Default empty info dict before the first frame."""
    return {
        "action": Action.IDLE,
        "top_choices": [],
        "explanation": "",
        "commentary": "",
        "eval_score": 0.0,
        "contributions": {},
        "decision_ms": 0.0,
        "opp_model_accurate": False,
        "opp_model_prediction": None,
    }


def _build_info(agent: Any, action: Action, scores: Dict[Action, float], obs: Any) -> Dict[str, Any]:
    """Build the display info dict for one agent."""
    personality = getattr(agent, "personality", None)
    variety = personality.variety if personality else 0.0

    choices = []
    if scores:
        choices = top_choices(scores, variety, n=4)

    explanation = explain_action(action, obs, scores, personality)
    comment = commentary(obs, personality)

    eval_score = 0.0
    contributions = {}
    if personality:
        eval_score, contributions = evaluate(obs, personality)

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
        "decision_ms": getattr(agent, "last_decision_ms", 0.0),
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
                     shake_dir: int = 0):
    """Draw one complete frame: arena background + floor + fighters + HUD + AI panels."""
    if screen_shake > 0:
        shake_x = int(shake_dir * screen_shake * 1.5 + random.randint(-2, 2))
        shake_y = random.randint(-screen_shake, screen_shake)
    else:
        shake_x = 0
        shake_y = 0

    # 1. Arena Background Artwork
    surface.blit(arena_bg, (shake_x, shake_y))

    # 2. Stage Floor & Boundary Laser Pillars
    stage_x = ARENA_OFFSET_X + shake_x
    stage_y = GROUND_Y + shake_y
    floor_surf = pygame.Surface((ARENA_WIDTH, 6), pygame.SRCALPHA)
    floor_surf.fill((25, 30, 52, 225))
    surface.blit(floor_surf, (stage_x, stage_y))
    pygame.draw.line(surface, (100, 160, 255), (stage_x, stage_y), (stage_x + ARENA_WIDTH, stage_y), 2)

    # Boundaries
    barrier_col = (70, 130, 240)
    pygame.draw.line(surface, barrier_col, (stage_x, stage_y - 220), (stage_x, stage_y + 6), 2)
    pygame.draw.line(surface, barrier_col, (stage_x + ARENA_WIDTH, stage_y - 220), (stage_x + ARENA_WIDTH, stage_y + 6), 2)
    pygame.draw.circle(surface, (0, 220, 255), (stage_x, stage_y - 220), 4)
    pygame.draw.circle(surface, (0, 220, 255), (stage_x + ARENA_WIDTH, stage_y - 220), 4)

    # 2b. Ground Dust Particles (Behind Fighters)
    if dust_particles:
        for dp in dust_particles:
            ratio = max(0.0, min(1.0, dp["lifetime"] / max(1, dp["max_lifetime"])))
            alpha = int(140 * ratio)
            r = max(1, int(dp["radius"]))
            if alpha > 0:
                dp_surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(dp_surf, (*dp["colour"], alpha), (r + 2, r + 2), r)
                surface.blit(dp_surf, (int(dp["x"]) + shake_x - r - 2, int(dp["y"]) + shake_y - r - 2))

    # 3. Fighters
    f1 = state.fighter1
    f2 = state.fighter2
    facing1 = (f1.x < f2.x)
    facing2 = (f2.x < f1.x)
    draw_fighter(surface, f1, facing1, arena_offset_x=stage_x,
                 ground_y=stage_y, player_num=1, is_mirror=False, is_human=False)
    draw_fighter(surface, f2, facing2, arena_offset_x=stage_x,
                 ground_y=stage_y, player_num=2, is_mirror=is_mirror, is_human=False)

    # 4. Projectiles
    for p in getattr(state, "projectiles", []):
        px = stage_x + int(p.x)
        py = stage_y - 45
        p_col = (0, 220, 255) if p.owner == 1 else (255, 120, 40)
        pygame.draw.circle(surface, p_col, (px, py), 8)
        pygame.draw.circle(surface, (255, 255, 255), (px, py), 4)
        trail_dir = -1 if p.vx > 0 else 1
        pygame.draw.line(surface, p_col, (px, py), (px + trail_dir * 18, py), 3)

    # 4b. Expanding Shockwave Rings
    if shockwaves:
        for sw in shockwaves:
            ratio = max(0.0, min(1.0, sw["lifetime"] / max(1, sw["max_lifetime"])))
            progress = 1.0 - ratio
            r = int(sw["radius"] + (sw["max_radius"] - sw["radius"]) * progress)
            alpha = int(220 * ratio)
            if r > 0 and alpha > 0:
                sw_surf = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
                pygame.draw.circle(sw_surf, (*sw["colour"][:3], alpha), (r + 3, r + 3), r, sw.get("width", 2))
                surface.blit(sw_surf, (sw["x"] + shake_x - r - 3, sw["y"] + shake_y - r - 3))

    # 5. Hit Sparks
    for s in sparks:
        sx, sy = s["x"] + shake_x, s["y"] + shake_y
        frame = s["frame"]
        col = s["colour"]
        radius = 4 + frame * 2
        pygame.draw.circle(surface, col, (sx, sy), radius, 1)
        for angle_idx in range(4):
            rad = frame * 3
            dx = int(rad * (1 if angle_idx in (0, 1) else -1))
            dy = int(rad * (1 if angle_idx in (1, 2) else -1))
            pygame.draw.circle(surface, (255, 255, 255), (sx + dx, sy + dy), 2)

    # 6. Combat Popups
    for pop in popups:
        p_surf = font_medium.render(pop["text"], True, pop["color"])
        p_rect = p_surf.get_rect(center=(pop["x"] + shake_x, int(pop["y"]) + shake_y))
        shadow_surf = font_medium.render(pop["text"], True, BLACK)
        surface.blit(shadow_surf, (p_rect.x + 2, p_rect.y + 2))
        surface.blit(p_surf, p_rect)

    # 7. Super Move Cinematic Darken
    if getattr(state, "super_freeze_frames", 0) > 0:
        dark = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 150))
        surface.blit(dark, (0, 0))
        super_text = font_large.render("SUPER MOVE!", True, (255, 230, 80))
        s_rect = super_text.get_rect(center=(SCREEN_WIDTH // 2, GROUND_Y - 120))
        shadow = font_large.render("SUPER MOVE!", True, BLACK)
        surface.blit(shadow, (s_rect.x + 3, s_rect.y + 3))
        surface.blit(super_text, s_rect)

    # 8. HUD (Health, damage trails, timer, combo counter)
    draw_hud(surface, state, font_medium, font_small, hit_flash=hit_flash,
             trail1=trail1, trail2=trail2, combo1=combo1, combo2=combo2,
             diff1=getattr(agent1, "difficulty", None),
             diff2=getattr(agent2, "difficulty", None),
             sparks=sparks)

    # 9. Controls & Telemetry Sub-Bar (Between Arena Floor and Thinking Panels at y=386)
    subbar_rect = pygame.Rect(0, 386, SCREEN_WIDTH, 24)
    subbar_surf = pygame.Surface((SCREEN_WIDTH, 24), pygame.SRCALPHA)
    subbar_surf.fill((12, 16, 28, 220))
    surface.blit(subbar_surf, (0, 386))
    pygame.draw.line(surface, (60, 75, 110), (0, 386), (SCREEN_WIDTH, 386), 1)

    # Left: Arena name
    arena_tag = font_small.render(f"Arena: {arena_display_name}", True, (200, 220, 255))
    surface.blit(arena_tag, (16, 390))

    # Center: Shortcut guide
    guide_text = font_tiny.render("[Space] Pause  ·  [Esc] Menu  ·  [F3] Profiling", True, LIGHT_GREY)
    surface.blit(guide_text, guide_text.get_rect(center=(SCREEN_WIDTH // 2, 398)))

    # Right: Speed multiplier
    speed_label, _ = SPEED_OPTIONS[speed_index]
    speed_tag = font_small.render(f"Speed: {speed_label} (< / >)", True, TIMER_COLOUR)
    surface.blit(speed_tag, (SCREEN_WIDTH - speed_tag.get_width() - 16, 390))

    # Pause Banner
    if paused:
        pause_text = font_medium.render("PAUSED (Press Space to Resume)", True, WHITE)
        p_rect = pause_text.get_rect(center=(SCREEN_WIDTH // 2, GROUND_Y - 60))
        badge_bg = pygame.Surface((p_rect.width + 30, p_rect.height + 14), pygame.SRCALPHA)
        badge_bg.fill((0, 0, 0, 200))
        surface.blit(badge_bg, (p_rect.x - 15, p_rect.y - 7))
        pygame.draw.rect(surface, (240, 200, 60), (p_rect.x - 15, p_rect.y - 7, p_rect.width + 30, p_rect.height + 14), 2, border_radius=6)
        surface.blit(pause_text, p_rect)

    # 10. AI Thinking Panels Backdrop
    backdrop = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT - 410), pygame.SRCALPHA)
    backdrop.fill((10, 14, 24, 230))
    surface.blit(backdrop, (0, 410))

    # 11. Left and Right AI Thinking Panels
    _draw_ai_panel(surface, PANEL1_X, PANEL_Y, PANEL_WIDTH, PANEL_HEIGHT,
                   info1, agent1.name, char1, font_small, font_tiny, player_num=1)
    _draw_ai_panel(surface, PANEL2_X, PANEL_Y, PANEL_WIDTH, PANEL_HEIGHT,
                   info2, agent2.name, char2, font_small, font_tiny, player_num=2)

    # 12. Profiling overlay (F3)
    if show_profiling:
        _draw_profiling(surface, agent1, agent2, font_tiny, state=state)


def _draw_ai_panel(surface: pygame.Surface, x: int, y: int, width: int, height: int,
                   info: Dict[str, Any], name: str, char_name: str,
                   font_small: pygame.font.Font, font_tiny: pygame.font.Font,
                   player_num: int = 1):
    """Draw one AI's thinking panel: choices, explanation, evaluation, prediction."""
    accent_col = P1_COLOUR if player_num == 1 else P2_COLOUR
    side_label = f"P{player_num}: {name}" if name != char_name else f"P{player_num}: {char_name}"

    # Rounded container
    panel_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    panel_surf.fill((18, 22, 38, 235))
    surface.blit(panel_surf, (x, y))
    pygame.draw.rect(surface, accent_col, (x, y, width, height), 1, border_radius=6)

    # Header: Name and Latency
    label = font_small.render(side_label, True, accent_col)
    surface.blit(label, (x + 10, y + 6))

    ms = info.get("decision_ms", 0.0)
    time_text = font_tiny.render(f"{ms:.1f}ms", True, LIGHT_GREY)
    surface.blit(time_text, (x + width - 55, y + 8))

    # Subheader: Action & Opponent Prediction
    action_name = info["action"].name
    act_text = font_tiny.render(f"Move: {action_name}", True, TIMER_COLOUR)
    surface.blit(act_text, (x + 10, y + 26))

    if info.get("opp_model_prediction"):
        pred = info.get("opp_model_prediction", "?")
        dot_col = HEALTH_GREEN if info.get("opp_model_accurate") else (240, 180, 50)
        pygame.draw.circle(surface, dot_col, (x + width - 110, y + 31), 4)
        pred_text = font_tiny.render(f"Read: {pred}", True, dot_col)
        surface.blit(pred_text, (x + width - 100, y + 26))

    # Left Column: Confidence Bars
    col1_x = x + 10
    bar_y = y + 46
    bar_width = 72
    bar_height = 11

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
    }

    choices = info.get("top_choices", [])[:4]
    for i, (action, prob) in enumerate(choices):
        by = bar_y + i * 20
        if by + bar_height > y + height - 6:
            break

        short_name = short_action_names.get(action.name, action.name[:7])
        act_lbl = font_tiny.render(short_name, True, LIGHT_GREY)
        surface.blit(act_lbl, (col1_x, by))

        bx = col1_x + 66
        pygame.draw.rect(surface, DARK_GREY, (bx, by + 1, bar_width, bar_height), border_radius=2)
        fill_w = int(bar_width * min(prob, 1.0))
        if fill_w > 0:
            fill_col = HEALTH_GREEN if prob > 0.4 else TIMER_COLOUR
            pygame.draw.rect(surface, fill_col, (bx, by + 1, fill_w, bar_height), border_radius=2)

        pct = font_tiny.render(f"{prob:.0%}", True, WHITE)
        surface.blit(pct, (bx + bar_width + 4, by - 1))

    # Right Column: Strategy, Explanation, Evaluation
    col2_x = x + 195
    col2_y = y + 46
    col2_w = width - 205

    explanation = info.get("explanation", "")
    _draw_wrapped_text(surface, explanation, font_tiny, LIGHT_GREY, col2_x, col2_y, col2_w, 2)

    comment = info.get("commentary", "")
    if comment:
        comment_text = font_tiny.render(f'"{comment[:38]}"', True, TIMER_COLOUR)
        surface.blit(comment_text, (col2_x, col2_y + 36))

    score = info.get("eval_score", 0.0)
    score_col = HEALTH_GREEN if score >= 0 else (240, 80, 80)
    score_text = font_tiny.render(f"Eval: {score:+.1f}", True, score_col)
    surface.blit(score_text, (col2_x, col2_y + 54))

    contrib_labels = {
        "closeness": "Close",
        "safe_distance": "Spacing",
        "corner_avoid": "Corner",
        "health_lead": "Health",
        "block_punish": "Punish",
        "whiff_punish": "Whiff",
    }
    contribs = info.get("contributions", {})
    if contribs:
        sorted_contribs = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        for idx, (fname, val) in enumerate(sorted_contribs):
            c_col = HEALTH_GREEN if val > 0 else (240, 80, 80)
            short_f = contrib_labels.get(fname, fname[:7])
            ct = font_tiny.render(f"{short_f}:{val:+.1f}", True, c_col)
            surface.blit(ct, (col2_x + idx * 92, col2_y + 72))


def _draw_wrapped_text(surface: pygame.Surface, text: str, font: pygame.font.Font,
                       colour: Tuple[int, int, int], x: int, y: int,
                       max_width: int, max_lines: int):
    """Draw text wrapped to fit within max_width, up to max_lines."""
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
        surface.blit(rendered, (x, y + i * 15))


def _draw_profiling(
    surface: pygame.Surface,
    agent1: Any,
    agent2: Any,
    font_tiny: pygame.font.Font,
    state: Optional[Any] = None,
):
    """Draw the F3 debug & profiling overlay showing mode, health zone, reaction, mistake %, block %, and timing."""
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
                             speed_index: int):
    """Display 'ROUND X' followed by 'FIGHT!' over the arena background."""
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
            0, 0, speed_index, False, False, 1.0, 1.0, 0, 0, [], []
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
            0, 0, speed_index, False, False, 1.0, 1.0, 0, 0, [], []
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
                              speed_index: int):
    """Display KO, TIME UP, or DRAW banner over the arena scene."""
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
        _draw_full_frame(
            surface, state, arena_bg, arena_display_name,
            info1, info2, font_banner, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, agent1, agent2,
            0, 0, speed_index, False, False, trail1, trail2, 0, 0, [], []
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
                           speed_mult: float):
    """Dramatic slow-motion freeze on deciding round KO."""
    half_fps = max(15, int(FPS * speed_mult * 0.5))
    for _ in range(25):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_full_frame(
            surface, state, arena_bg, arena_display_name,
            info1, info2, font_large, font_medium, font_small, font_tiny,
            char1, char2, is_mirror, agent1, agent2,
            0, 0, 2, False, False, trail1, trail2, 0, 0, [], []
        )
        _flip_display()
        clock.tick(half_fps)


def _draw_center_banner_viewer(surface: pygame.Surface, text: str,
                               font: pygame.font.Font, colour: Tuple[int, int, int]):
    """Draw high-contrast banner in the center of the fight viewport."""
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
