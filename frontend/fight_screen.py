"""The fight screen: runs a full match with live rendering, dynamic camera,
2-layer arena ambience, jointed fighters, and modern HUD.
"""

import random
import time
from typing import Optional
import pygame

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.engine.constants import ARENA_WIDTH, FPS
from backend.engine.step import make_initial_state, new_round, step
from backend.data.progression import (
    check_match_missions,
    check_match_trophies,
    get_level_multipliers,
)
from frontend.assets import assets
from frontend.audio import audio
from frontend.camera_effects import (
    CameraState,
    draw_alignment_lines,
    draw_arena_ambience,
    draw_color_grade_and_vignette,
    draw_combat_popups,
)
from frontend.draw_fighter import draw_fighter
from frontend.draw_rumble import (
    draw_rumble_hud_extras,
    draw_rumble_items,
    draw_rumble_objects,
    draw_rumble_walls,
    draw_rumble_zone,
)
from frontend.draw_shield_wall import (
    draw_shield_wall_hud,
    draw_shield_wall_panels,
)
from frontend.hud import draw_hud
from frontend.input_handler import get_human_action
from frontend.screens import pause_screen
from frontend.theme import (
    BLACK,
    FLOOR_HEIGHT,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SPARK_BLOCK,
    SPARK_COUNTER,
    SPARK_HIT,
    TIMER_COLOUR,
    WHITE,
    get_arena_floor_y,
)

ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2
_FIGHT_VIEWPORT: Optional[pygame.Surface] = None


def _get_fight_viewport() -> pygame.Surface:
    global _FIGHT_VIEWPORT
    if _FIGHT_VIEWPORT is None or _FIGHT_VIEWPORT.get_size() != (SCREEN_WIDTH, SCREEN_HEIGHT):
        _FIGHT_VIEWPORT = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    return _FIGHT_VIEWPORT


# ---------------------------------------------------------------------------
# Renderer selection (real-3D moderngl view with automatic 2D sprite fallback)
# ---------------------------------------------------------------------------
SUPPORTS_LOCAL_VERSUS = True     # run_fight accepts human_player="both"
RENDERER_MODE = "3d"             # default; settings["renderer"] / renderer= kwarg override
DISPLAY_FPS = 60
MAX_STEPS_PER_FRAME = 4

_R3D = None                      # cached Renderer3D (GL context is expensive to create)
_R3D_FAILED = False
_ACTIVE_R3D = None               # renderer used by _draw_fight_scene for the current match


def _get_renderer3d():
    """Create (once) and return the 3D renderer, or None if OpenGL is unavailable."""
    global _R3D, _R3D_FAILED
    if _R3D is not None:
        return _R3D
    if _R3D_FAILED:
        return None
    try:
        from frontend.render3d import create_renderer
        _R3D = create_renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
    except Exception:
        _R3D = None
    if _R3D is None:
        _R3D_FAILED = True
    return _R3D


def _resolve_renderer_mode(renderer=None, settings=None) -> str:
    mode = renderer
    if mode is None and isinstance(settings, dict):
        mode = settings.get("renderer")
    if mode is None:
        mode = RENDERER_MODE
    mode = str(mode).lower()
    return "2d" if mode == "2d" else "3d"


def _pan(x: float) -> float:
    return max(-1.0, min(1.0, (x - ARENA_WIDTH / 2.0) / (ARENA_WIDTH / 2.0)))


def _audio(name, *args, fallback=None, **kwargs):
    """Call a new-style audio hook if present, else the legacy play_sfx name."""
    fn = getattr(audio, name, None)
    if callable(fn):
        try:
            fn(*args, **kwargs)
            return
        except TypeError:
            pass
        except Exception:
            return
    if fallback:
        try:
            audio.play_sfx(fallback)
        except Exception:
            pass


def _make_input_handlers():
    """Two independent input handlers for local versus (P1 WASD/pad0, P2 arrows/pad1)."""
    try:
        from frontend.input_handler import InputHandler
    except Exception:
        return None, None
    handlers = []
    for player in (1, 2):
        try:
            handlers.append(InputHandler(key_bindings=None, player=player, controller_index=None))
        except TypeError:
            try:
                handlers.append(InputHandler())
            except Exception:
                handlers.append(None)
        except Exception:
            handlers.append(None)
    return handlers[0], handlers[1]


def _handler_action(handler, enemy_x, my_x, in_air, can_act, enable_shield_wall):
    if handler is None:
        return Action.IDLE
    try:
        return handler.get_action(enemy_x, my_x, in_air=in_air, can_act=can_act,
                                  enable_shield_wall=enable_shield_wall)
    except TypeError:
        return handler.get_action(enemy_x, my_x, in_air=in_air, can_act=can_act)


_SWING_LIGHT = (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB, Action.CROUCH_KICK, Action.JUMP_PUNCH)
_SWING_HEAVY = (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD, Action.JUMP_KICK,
                Action.ANTI_AIR)
_SPECIALS = (Action.SPECIAL_NEUTRAL, Action.SPECIAL_FORWARD, Action.SPECIAL_BACK, Action.SPECIAL_DOWN)


def run_fight(surface, clock, agent1, agent2, human_player=None,
              speed_mult=1.0, arena_name=None, rules=None,
              p1_level: int = 1, p2_level: int = 1, p1_regen: Optional[bool] = None,
              player_id: Optional[int] = None, renderer: Optional[str] = None,
              settings: Optional[dict] = None):
    """Run a full match on screen.

    human_player: None (AI vs AI), 1, 2, or "both" (local versus, two InputHandlers).
    renderer: "3d" (default, moderngl) or "2d" (sprite renderer); also read from
    settings["renderer"].  Falls back to 2D automatically if OpenGL is unavailable.
    Returns "quit" or the match stats dict (unchanged contract).
    """
    global _ACTIVE_R3D
    r3d = _get_renderer3d() if _resolve_renderer_mode(renderer, settings) == "3d" else None
    _ACTIVE_R3D = r3d
    try:
        return _run_fight(surface, clock, agent1, agent2, human_player, speed_mult, arena_name, rules,
                          p1_level, p2_level, p1_regen, player_id, r3d)
    finally:
        _ACTIVE_R3D = None


def _run_fight(surface, clock, agent1, agent2, human_player, speed_mult, arena_name, rules,
               p1_level, p2_level, p1_regen, player_id, r3d):
    char1 = agent1.personality.name if getattr(agent1, "personality", None) else getattr(agent1, "character_name", "Golden")
    char2 = agent2.personality.name if getattr(agent2, "personality", None) else getattr(agent2, "character_name", "Golden")
    is_mirror = (char1 == char2)
    local_versus = (human_player == "both")
    human1 = human_player in (1, "both")
    human2 = human_player in (2, "both")
    hud_human = 1 if human_player == 1 else (2 if human_player == 2 else (0 if local_versus else None))

    if p1_regen is None:
        p1_regen = (human_player == 1)

    p1_stats = get_level_multipliers(p1_level)
    p2_stats = get_level_multipliers(p2_level)

    audio.play_music("music_fight")

    if arena_name is None:
        p2_diff = getattr(agent2, "difficulty", "LOW")
        arena_name = assets.pick_arena(difficulty=p2_diff)

    arena_bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))
    floor_y = get_arena_floor_y(arena_name, SCREEN_HEIGHT)

    font_banner = pygame.font.Font(None, 84)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)

    ih1, ih2 = _make_input_handlers() if local_versus else (None, None)
    speed = max(0.1, float(speed_mult or 1.0))

    if r3d is not None:
        r3d.setup(char1, char2, arena_name)

    while True:
        state = make_initial_state(
            char1, char2, rules=rules,
            p1_level=p1_level, p2_level=p2_level,
            p1_stats=p1_stats, p2_stats=p2_stats,
            p1_regen=p1_regen, p2_regen=False,
        )
        agent1.reset()
        agent2.reset()
        camera = CameraState(SCREEN_WIDTH, SCREEN_HEIGHT)
        if r3d is not None:
            r3d.reset_round()

        stats = {
            "mode": "Arena Rumble" if (rules and rules.is_rumble) else "Classic",
            "p1_name": "Player" if human1 else char1,
            "p2_name": ("Player 2" if local_versus else char2),
            "p1_character": char1,
            "p2_character": char2,
            "p1_kind": "human" if human1 else "ai",
            "p2_kind": "human" if human2 else "ai",
            "p1_difficulty": getattr(agent1, "difficulty", "LOW"),
            "p2_difficulty": getattr(agent2, "difficulty", "LOW"),
            "p1_level": p1_level,
            "p2_level": p2_level,
            "arena": arena_name,
            "damage_dealt_p1": 0.0,
            "damage_dealt_p2": 0.0,
            "hits_landed_p1": 0,
            "hits_landed_p2": 0,
            "blocks_p1": 0,
            "blocks_p2": 0,
            "longest_combo_p1": 0,
            "longest_combo_p2": 0,
            "flawless_rounds_p1": 0,
            "specials_p1": 0,
            "throws_p1": 0,
            "comeback_p1": False,
            "super_ko_p1": False,
            "rounds_history": [],
            "start_time": time.time(),
        }

        fx = {
            "prev_health1": 1.0, "prev_health2": 1.0, "trail1": 1.0, "trail2": 1.0,
            "combo1": 0, "combo2": 0, "combo1_timer": 0, "combo2_timer": 0,
            "hit_flash": 0, "screen_shake": 0, "shake_dir": 0, "hit_stop": 0,
            "f1_prev_in_air": False, "f2_prev_in_air": False, "f1_prev_kd": False, "f2_prev_kd": False,
        }
        sparks = []
        shockwaves = []
        dust_particles = []
        popups = []
        training_mode = False
        dummy_mode = 0
        show_debug = False
        show_alignment = False
        pause_result = None
        round_start_time = time.time()
        accumulator = 0.0

        _show_round_intro(
            surface, clock, state, arena_bg, 1,
            font_banner, font_medium, font_small,
            char1, char2, is_mirror, hud_human, speed_mult,
            arena_name=arena_name, floor_y=floor_y, camera=camera
        )

        while not state.match_over:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pause_result = pause_screen(surface, clock)
                        if pause_result == "quit":
                            return "quit"
                        elif pause_result == "restart":
                            state.match_over = True
                            break
                        accumulator = 0.0
                    elif event.key == pygame.K_F1:
                        training_mode = not training_mode
                    elif event.key == pygame.K_F2:
                        training_mode = True
                        dummy_mode = (dummy_mode + 1) % 4
                    elif event.key == pygame.K_F3:
                        show_debug = not show_debug
                    elif event.key == pygame.K_F4:
                        show_alignment = not show_alignment

            if state.match_over and pause_result == "restart":
                break

            # --- Fixed-timestep accumulator: 60 sim steps/s x game speed, render at display rate ---
            dt_ms = clock.tick(DISPLAY_FPS)
            if not dt_ms or dt_ms <= 0:
                dt_ms = 1000.0 / DISPLAY_FPS        # fake / non-sleeping clocks: one step per frame
            dt_ms = min(float(dt_ms), 100.0)
            accumulator += dt_ms / 1000.0 * FPS * speed
            n_steps = min(int(accumulator), MAX_STEPS_PER_FRAME)
            accumulator -= int(accumulator) if n_steps < MAX_STEPS_PER_FRAME else accumulator
            accumulator = min(accumulator, 1.0)

            for _ in range(n_steps):
                # --- Hit-Stop Freeze (3f light, 6f heavy, 10f super): sim holds, render keeps going ---
                if fx["hit_stop"] > 0:
                    fx["hit_stop"] -= 1
                    continue
                state = _sim_step(
                    state, agent1, agent2, human1, human2, local_versus, ih1, ih2,
                    training_mode, dummy_mode, stats, fx, sparks, shockwaves, dust_particles, popups,
                    floor_y, camera, r3d,
                )
                sparks[:] = [s for s in sparks if s["frame"] < 8]
                dust_particles[:] = [dp for dp in dust_particles if dp["lifetime"] > 0]
                shockwaves[:] = [sw for sw in shockwaves if sw["lifetime"] > 0]
                popups[:] = [p for p in popups if p["lifetime"] > 0]
                if state.round_over:
                    break

            frac = 0.0 if fx["hit_stop"] > 0 else min(0.999, accumulator)
            _draw_fight_scene(
                surface, state, arena_bg, font_medium, font_small,
                char1, char2, is_mirror, hud_human,
                fx["hit_flash"], fx["screen_shake"], fx["trail1"], fx["trail2"],
                fx["combo1"], fx["combo2"], getattr(agent1, "difficulty", None),
                getattr(agent2, "difficulty", None), sparks,
                popups, training_mode, dummy_mode,
                shockwaves=shockwaves, dust_particles=dust_particles,
                shake_dir=fx["shake_dir"], show_debug=show_debug,
                agent1=agent1, agent2=agent2,
                arena_name=arena_name, floor_y=floor_y,
                camera=camera, show_alignment=show_alignment,
                r3d_frac=frac, r3d_dt=dt_ms / 1000.0 * min(1.0, speed) if fx["hit_stop"] <= 0 else dt_ms / 4000.0,
            )
            pygame.display.flip()

            if state.round_over:
                # Adaptive difficulty / learned-model refresh hooks (no-ops for agents without them).
                for ag in (agent1, agent2):
                    hook = getattr(ag, "on_round_end", None)
                    if callable(hook):
                        hook(state.round_result)
                    if state.match_over:
                        hook = getattr(ag, "on_match_end", None)
                        if callable(hook):
                            hook(state.match_result)
                round_dur = time.time() - round_start_time
                ended_by = "KO" if (state.fighter1.health <= 0 or state.fighter2.health <= 0) else "TIME"
                if state.round_result == "draw":
                    ended_by = "DRAW"

                if state.round_result == "p1":
                    audio.play_sfx("round_win")
                    if state.fighter1.health >= 0.999:
                        stats["flawless_rounds_p1"] += 1

                stats["rounds_history"].append({
                    "round_number": state.round_number,
                    "winner_side": 1 if state.round_result == "p1" else (2 if state.round_result == "p2" else 0),
                    "ended_by": ended_by,
                    "p1_health_left": max(0.0, state.fighter1.health),
                    "p2_health_left": max(0.0, state.fighter2.health),
                    "duration_s": round(round_dur, 1),
                })

                if ended_by == "KO":
                    loser_x = state.fighter1.x if state.fighter1.health <= state.fighter2.health else state.fighter2.x
                    _audio("play_ko", _pan(loser_x))
                    _slow_motion_ko(
                        surface, clock, state, arena_bg, font_medium, font_small,
                        char1, char2, is_mirror, hud_human, fx["trail1"], fx["trail2"], speed_mult,
                        arena_name=arena_name, floor_y=floor_y, camera=camera
                    )

                if state.match_over:
                    if state.match_result == "p1":
                        audio.play_sfx("match_win")
                    elif state.match_result == "p2":
                        audio.play_sfx("match_lose")

                    _show_round_banner(
                        surface, clock, state, arena_bg, ended_by,
                        font_banner, font_medium, font_small,
                        char1, char2, is_mirror, hud_human, fx["trail1"], fx["trail2"],
                        arena_name=arena_name, floor_y=floor_y, camera=camera
                    )
                    break
                else:
                    _show_round_banner(
                        surface, clock, state, arena_bg, ended_by,
                        font_banner, font_medium, font_small,
                        char1, char2, is_mirror, hud_human, fx["trail1"], fx["trail2"],
                        arena_name=arena_name, floor_y=floor_y, camera=camera
                    )

                    state = new_round(state)
                    agent1.reset()
                    agent2.reset()
                    camera = CameraState(SCREEN_WIDTH, SCREEN_HEIGHT)
                    if r3d is not None:
                        r3d.reset_round()
                    fx.update({"prev_health1": 1.0, "prev_health2": 1.0, "trail1": 1.0, "trail2": 1.0,
                               "combo1": 0, "combo2": 0, "hit_stop": 0})
                    sparks.clear()
                    accumulator = 0.0
                    round_start_time = time.time()

                    _show_round_intro(
                        surface, clock, state, arena_bg, state.round_number,
                        font_banner, font_medium, font_small,
                        char1, char2, is_mirror, hud_human, speed_mult,
                        arena_name=arena_name, floor_y=floor_y, camera=camera
                    )

        if pause_result == "restart":
            continue

        stats["winner_side"] = 1 if state.match_result == "p1" else (2 if state.match_result == "p2" else 0)
        stats["rounds_p1"] = state.p1_rounds_won
        stats["rounds_p2"] = state.p2_rounds_won
        stats["duration_s"] = round(time.time() - stats["start_time"], 1)
        stats["status"] = "finished"
        stats["match_result"] = state.match_result
        stats["walls_built_p1"] = state.fighter1.walls_built
        stats["walls_built_p2"] = state.fighter2.walls_built
        stats["walls_broken_p1"] = state.fighter1.walls_broken
        stats["walls_broken_p2"] = state.fighter2.walls_broken
        stats["items_collected_p1"] = state.fighter1.items_collected
        stats["items_collected_p2"] = state.fighter2.items_collected
        stats["zone_damage_p1"] = round(state.fighter1.zone_damage_taken, 1)
        stats["zone_damage_p2"] = round(state.fighter2.zone_damage_taken, 1)
        if r3d is not None:
            stats["render_ms"] = round(r3d.mean_ms(), 2)

        if player_id is not None and human_player == 1:
            new_trophies = check_match_trophies(stats, player_id)
            if new_trophies:
                stats["unlocked_trophies"] = new_trophies
            new_missions = check_match_missions(stats, player_id)
            if new_missions:
                stats["completed_missions"] = new_missions

        return stats


def _sim_step(state, agent1, agent2, human1, human2, local_versus, ih1, ih2,
              training_mode, dummy_mode, stats, fx, sparks, shockwaves, dust_particles, popups,
              floor_y, camera, r3d):
    """One fixed 1/60 s simulation step: decisions, engine step, feedback events."""
    f1_was_stuck = (state.fighter1.recovery > 0)
    f2_was_stuck = (state.fighter2.recovery > 0)
    shield = state.rules.enable_shield_wall

    def can_act(f):
        return (not f.busy and f.cooldown <= 0) or f.cancel_available

    if local_versus:
        action1 = _handler_action(ih1, state.fighter2.x, state.fighter1.x, state.fighter1.in_air,
                                  can_act(state.fighter1), shield)
        action2 = _handler_action(ih2, state.fighter1.x, state.fighter2.x, state.fighter2.in_air,
                                  can_act(state.fighter2), shield)
    elif human1:
        action1 = get_human_action(
            state.fighter2.x,
            state.fighter1.x,
            in_air=state.fighter1.in_air,
            can_act=can_act(state.fighter1),
            enable_shield_wall=shield,
        )
        obs2 = observation_for(state, 2)
        if training_mode:
            if dummy_mode == 0:
                action2 = Action.IDLE
            elif dummy_mode == 1:
                action2 = Action.CROUCH
            elif dummy_mode == 2:
                action2 = Action.BLOCK_LOW if state.fighter1.is_crouching else Action.BLOCK
            else:
                action2, _ = agent2.decide(obs2)
        else:
            action2, _ = agent2.decide(obs2)
    elif human2:
        obs1 = observation_for(state, 1)
        action1, _ = agent1.decide(obs1)
        action2 = get_human_action(
            state.fighter1.x,
            state.fighter2.x,
            in_air=state.fighter2.in_air,
            can_act=can_act(state.fighter2),
            enable_shield_wall=shield,
        )
    else:
        obs1 = observation_for(state, 1)
        obs2 = observation_for(state, 2)
        action1, _ = agent1.decide(obs1)
        action2, _ = agent2.decide(obs2)

    if action1 in (Action.BLOCK, Action.BLOCK_LOW):
        stats["blocks_p1"] += 1
    if action2 in (Action.BLOCK, Action.BLOCK_LOW):
        stats["blocks_p2"] += 1

    # Attack / special / movement SFX (only when the move really starts)
    prev_state = state
    state = step(state, action1, action2)

    for f_prev, f, act, is_p1 in ((prev_state.fighter1, state.fighter1, action1, True),
                                  (prev_state.fighter2, state.fighter2, action2, False)):
        started = (f.attack_phase != "none" and f.current_action == act and
                   (f_prev.attack_phase == "none" or f_prev.current_action != act))
        pan = _pan(f.x)
        if started:
            if act in _SWING_LIGHT:
                _audio("play_swing", 0.3, pan, fallback="whoosh_light")
            elif act in _SWING_HEAVY:
                _audio("play_swing", 0.8, pan, fallback="whoosh_heavy")
            elif act in _SPECIALS:
                _audio("play_special", pan, fallback="special")
                if is_p1:
                    stats["specials_p1"] += 1
            elif act == Action.SUPER:
                _audio("play_super", pan, fallback="super")
            elif act == Action.THROW:
                _audio("play_throw", pan, fallback="throw")
                if is_p1:
                    stats["throws_p1"] += 1
            elif act == Action.BACKDASH:
                _audio("play_dash", pan, fallback="dash")
        elif act == Action.DASH and f_prev.last_action != Action.DASH and not f.in_air:
            _audio("play_dash", pan, fallback="dash")
        if not f_prev.in_air and f.in_air and not f.hitstun:
            _audio("play_jump", pan, fallback="jump")
        elif f_prev.in_air and not f.in_air:
            _audio("play_land", pan, fallback="land")

    # Feed the 3D renderer BEFORE one-frame effects are cleared below
    if r3d is not None:
        r3d.push_step(prev_state, state)

    if state.fighter1.health < 0.15:
        stats["comeback_p1"] = True

    camera.update(ARENA_OFFSET_X + state.fighter1.x, ARENA_OFFSET_X + state.fighter2.x, floor_y)

    # --- Hits, Sparks, Screen Shake, and Floating Text ---
    for victim_idx in (1, 2):
        victim = state.fighter1 if victim_idx == 1 else state.fighter2
        attacker = state.fighter2 if victim_idx == 1 else state.fighter1
        victim_prev = prev_state.fighter1 if victim_idx == 1 else prev_state.fighter2
        victim_action = action1 if victim_idx == 1 else action2
        attacker_action = action2 if victim_idx == 1 else action1
        h_key = "prev_health%d" % victim_idx
        h_diff = fx[h_key] - victim.health
        effect = getattr(victim, "last_hit_effect", "none")
        if effect == "parry":
            _audio("play_parry", _pan(victim.x), fallback="block")
        if h_diff <= 0.001:
            continue
        a_idx = 3 - victim_idx
        stats["damage_dealt_p%d" % a_idx] += h_diff
        stats["hits_landed_p%d" % a_idx] += 1
        is_blocked = (effect == "block" or victim_action in (Action.BLOCK, Action.BLOCK_LOW)
                      or victim.blockstun > victim_prev.blockstun)
        is_counter = (effect == "counter" or getattr(attacker, "last_hit_effect", "") == "counter"
                      or victim.is_counter_hit)
        is_super = (attacker_action == Action.SUPER or attacker.current_action == Action.SUPER or h_diff >= 0.18)
        is_heavy = (h_diff > 0.07)
        pan = _pan(victim.x)
        if is_blocked:
            _audio("play_block", pan, fallback="block")
        else:
            strength = 1.0 if is_super else (0.75 if is_heavy else 0.35)
            _audio("play_hit", strength, pan, counter=is_counter,
                   fallback="hit_heavy" if (is_super or is_heavy) else "hit_light")
        if a_idx == 1 and attacker.current_action == Action.SUPER and victim.health <= 0.0:
            stats["super_ko_p1"] = True

        spark_kind = "block" if is_blocked else ("counter" if is_counter else "hit")
        spark_col = SPARK_BLOCK if is_blocked else (SPARK_COUNTER if is_counter else SPARK_HIT)
        if r3d is not None:
            hit_x, hit_y = r3d.world_to_screen(victim.x, 1.25)
            pop_x, pop_y = r3d.world_to_screen(victim.x, 2.05)
        else:
            hit_x, hit_y = ARENA_OFFSET_X + int(victim.x), floor_y - 62
            pop_x, pop_y = hit_x, floor_y - 110
        if r3d is None:
            sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0, "kind": spark_kind})

        fx["hit_flash"] = 4 if is_counter else 2
        fx["hit_stop"] = 10 if is_super else (6 if is_heavy else 3)
        fx["screen_shake"] = 12 if is_super else (5 if is_heavy else 2)
        fx["shake_dir"] = 1 if attacker.x < victim.x else -1

        was_stuck = f1_was_stuck if victim_idx == 1 else f2_was_stuck
        if is_blocked:
            popups.append({"text": "BLOCKED", "x": pop_x, "y": pop_y, "color": (120, 210, 255), "lifetime": 20, "max_lifetime": 20})
        elif was_stuck and not is_counter:
            popups.append({"text": "PUNISH!", "x": pop_x, "y": pop_y - 5, "color": (255, 215, 50), "lifetime": 20, "max_lifetime": 20})

        c_key, t_key = "combo%d" % a_idx, "combo%d_timer" % a_idx
        fx[c_key] = fx[c_key] + 1 if fx[t_key] > 0 else 1
        fx[t_key] = 30
        stats["longest_combo_p%d" % a_idx] = max(stats["longest_combo_p%d" % a_idx], fx[c_key])

    # --- 2D dust puffs (fallback renderer only; the 3D view spawns its own) ---
    f1 = state.fighter1
    f2 = state.fighter2
    if r3d is None:
        for f, prev_air, prev_kd in ((f1, fx["f1_prev_in_air"], fx["f1_prev_kd"]),
                                     (f2, fx["f2_prev_in_air"], fx["f2_prev_kd"])):
            fxx = ARENA_OFFSET_X + int(f.x)
            if (prev_air and not f.in_air) or (not prev_kd and f.is_knocked_down):
                puff_count = 6 if f.is_knocked_down else 4
                for _ in range(puff_count):
                    dust_particles.append({
                        "x": fxx + random.uniform(-14, 14),
                        "y": floor_y - random.uniform(1, 4),
                        "vx": random.uniform(-2.0, 2.0),
                        "vy": random.uniform(-1.4, -0.3),
                        "radius": random.uniform(3.5, 6.5),
                        "lifetime": 15,
                        "max_lifetime": 15,
                        "colour": (200, 195, 185),
                    })
            if f.last_action in (Action.DASH, Action.BACKDASH) and random.random() < 0.45:
                dust_particles.append({
                    "x": fxx + random.uniform(-6, 6),
                    "y": floor_y - random.uniform(1, 3),
                    "vx": random.uniform(-1.8, 1.8),
                    "vy": random.uniform(-0.9, -0.2),
                    "radius": random.uniform(2.8, 5.0),
                    "lifetime": 12,
                    "max_lifetime": 12,
                    "colour": (185, 180, 170),
                })
    fx["f1_prev_in_air"] = f1.in_air
    fx["f2_prev_in_air"] = f2.in_air
    fx["f1_prev_kd"] = f1.is_knocked_down
    fx["f2_prev_kd"] = f2.is_knocked_down

    # --- Engine Hit Effects (Counter, Parry, Guard Break, Burst) as popups ---
    colors = {
        "counter": (255, 68, 68),
        "parry": (0, 229, 255),
        "guard_break": (224, 64, 251),
        "burst": (255, 215, 0),
        "tech": (0, 230, 118),
        "wall_bounce": (255, 171, 0),
        "ground_bounce": (255, 145, 0),
        "read": (255, 225, 120),
    }
    for f in (state.fighter1, state.fighter2):
        effect = getattr(f, "last_hit_effect", "none")
        if effect not in ("none", "hit", "block", None):
            if r3d is not None:
                px, py = r3d.world_to_screen(f.x, 2.25)
            else:
                px, py = ARENA_OFFSET_X + int(f.x), floor_y - 115
            popups.append({
                "text": f"{effect.replace('_', ' ').upper()}!",
                "x": px,
                "y": py,
                "color": colors.get(effect, (255, 255, 255)),
                "lifetime": 20,
                "max_lifetime": 20,
            })
        f.last_hit_effect = "none"

    for p in popups:
        p["y"] -= 1.2
        p["lifetime"] -= 1

    fx["prev_health1"] = state.fighter1.health
    fx["prev_health2"] = state.fighter2.health
    fx["trail1"] = max(state.fighter1.health, fx["trail1"] - 0.006)
    fx["trail2"] = max(state.fighter2.health, fx["trail2"] - 0.006)

    for k in (1, 2):
        t_key, c_key = "combo%d_timer" % k, "combo%d" % k
        if fx[t_key] > 0:
            fx[t_key] -= 1
            if fx[t_key] == 0:
                fx[c_key] = 0

    for s in sparks:
        s["frame"] += 1
    for dp in dust_particles:
        dp["x"] += dp["vx"]
        dp["y"] += dp["vy"]
        dp["radius"] += 0.15
        dp["lifetime"] -= 1
    for sw in shockwaves:
        sw["lifetime"] -= 1

    fx["hit_flash"] = max(0, fx["hit_flash"] - 1)
    fx["screen_shake"] = max(0, fx["screen_shake"] - 1)

    if not human1:
        agent1.observe(observation_for(state, 1), action1, action2)
    if not human2:
        agent2.observe(observation_for(state, 2), action2, action1)
    return state


def _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                      char1, char2, is_mirror, human_player,
                      hit_flash, screen_shake, trail1, trail2,
                      combo1, combo2, diff1, diff2, sparks,
                      popups=None, training_mode=False, dummy_mode=0,
                      shockwaves=None, dust_particles=None, shake_dir=0,
                      show_debug=False, agent1=None, agent2=None,
                      arena_name="arena_neon_rooftop", floor_y=FLOOR_HEIGHT,
                      camera=None, show_alignment=False, r3d_frac=0.0, r3d_dt=1.0 / 60.0,
                      r3d_intro=0.0, r3d_ko=False):
    """Draw the fight viewport (3D renderer or 2D sprites) and the static HUD on top."""
    viewport = _get_fight_viewport()
    r3d = _ACTIVE_R3D
    if r3d is not None:
        try:
            _draw_scene_3d(surface, viewport, r3d, state, popups, font_medium, r3d_frac, r3d_dt,
                           r3d_intro, r3d_ko)
        except Exception as exc:  # GL failure mid-match: fall back to the 2D renderer for good
            _disable_3d(exc)
            r3d = None
    if r3d is None:
        _draw_scene_2d(surface, viewport, state, arena_bg, font_medium, font_small, is_mirror, human_player,
                       screen_shake, sparks, popups, training_mode, shockwaves, dust_particles, shake_dir,
                       arena_name, floor_y, camera, show_alignment)
    _draw_overlays_and_hud(surface, state, font_medium, font_small, human_player, hit_flash, trail1, trail2,
                           combo1, combo2, diff1, diff2, sparks if r3d is None else None, training_mode,
                           dummy_mode, show_debug, agent1, agent2, floor_y, screen_shake, shake_dir, r3d)


def _disable_3d(exc=None):
    global _ACTIVE_R3D, _R3D, _R3D_FAILED
    _ACTIVE_R3D = None
    _R3D = None
    _R3D_FAILED = True


def _draw_scene_3d(surface, viewport, r3d, state, popups, font_medium, frac, dt, intro, ko):
    if r3d.fighters and r3d.fighters[1].f is None:
        r3d.push_step(None, state)
    img = r3d.render(state, frac, dt, intro=intro, ko_focus=ko)
    viewport.blit(img, (0, 0))
    if popups:
        draw_combat_popups(viewport, popups, font_medium)
    surface.blit(viewport, (0, 0))


def _draw_scene_2d(surface, viewport, state, arena_bg, font_medium, font_small, is_mirror, human_player,
                   screen_shake, sparks, popups, training_mode, shockwaves, dust_particles, shake_dir,
                   arena_name, floor_y, camera, show_alignment):
    """Legacy sprite renderer (fallback when OpenGL is unavailable or renderer='2d')."""

    shake_x = 0
    shake_y = 0
    if screen_shake > 0:
        shake_x = int(shake_dir * screen_shake * 1.2 + random.randint(-2, 2))
        shake_y = random.randint(-max(1, screen_shake // 2), max(1, screen_shake // 2))

    # 1. Arena background onto viewport
    viewport.blit(arena_bg, (shake_x, shake_y))

    # 2. Back-layer atmospheric particles (behind fighters)
    draw_arena_ambience(viewport, arena_name, state.frame, SCREEN_HEIGHT, layer="back")

    # 3. Arena Rumble Environment: Objects, Walls, Items, Zone Barrier
    if state.rules.is_rumble:
        if state.rules.enable_zone:
            draw_rumble_zone(viewport, state.zone, ARENA_OFFSET_X + shake_x, floor_y + shake_y, state.frame)
        if state.rules.enable_objects:
            draw_rumble_objects(viewport, state.arena_objects, ARENA_OFFSET_X + shake_x, floor_y + shake_y, state.frame)
        if state.rules.enable_building:
            draw_rumble_walls(viewport, state.walls, ARENA_OFFSET_X + shake_x, floor_y + shake_y)
        if state.rules.enable_loot:
            draw_rumble_items(viewport, state.items, state.supply_drop, ARENA_OFFSET_X + shake_x, floor_y + shake_y, state.frame)

    if state.rules.enable_shield_wall:
        draw_shield_wall_panels(viewport, state, ARENA_OFFSET_X + shake_x, floor_y + shake_y)

    # 4. Ground Dust Puffs (Behind Fighters)
    if dust_particles:
        for dp in dust_particles:
            ratio = max(0.0, min(1.0, dp["lifetime"] / max(1, dp["max_lifetime"])))
            alpha = int(150 * ratio)
            r = max(1, int(dp["radius"]))
            if alpha > 0:
                dp_surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(dp_surf, (*dp["colour"], alpha), (r + 2, r + 2), r)
                viewport.blit(dp_surf, (int(dp["x"]) + shake_x - r - 2, int(dp["y"]) + shake_y - r - 2))

    # 5. Jointed Fighters
    f1 = state.fighter1
    f2 = state.fighter2
    facing1 = (f1.x < f2.x)
    facing2 = (f2.x < f1.x)

    draw_fighter(
        viewport, f1, facing1,
        arena_offset_x=ARENA_OFFSET_X + shake_x,
        ground_y=floor_y + shake_y,
        player_num=1,
        is_mirror=False,
        is_human=(human_player == 1)
    )
    draw_fighter(
        viewport, f2, facing2,
        arena_offset_x=ARENA_OFFSET_X + shake_x,
        ground_y=floor_y + shake_y,
        player_num=2,
        is_mirror=is_mirror,
        is_human=(human_player == 2)
    )

    # 6. Projectiles
    for p in state.projectiles:
        px = ARENA_OFFSET_X + int(p.x) + shake_x
        py = floor_y - 48 + shake_y
        p_col = (0, 220, 255) if p.owner == 1 else (255, 120, 40)
        pygame.draw.circle(viewport, p_col, (px, py), 9)
        pygame.draw.circle(viewport, WHITE, (px, py), 4)
        trail_dir = -1 if p.vx > 0 else 1
        pygame.draw.line(viewport, p_col, (px, py), (px + trail_dir * 20, py), 3)

    # 7. Front-layer atmospheric particles (in front of fighters for depth)
    draw_arena_ambience(viewport, arena_name, state.frame, SCREEN_HEIGHT, layer="front")

    # 8. Colour grade tint + gentle edge vignette
    draw_color_grade_and_vignette(viewport, arena_name)

    # 9. Floating Combat Text Popups ("COUNTER!", "PUNISH!", "BLOCKED")
    if popups:
        draw_combat_popups(viewport, popups, font_medium, shake_x=shake_x, shake_y=shake_y)

    # 10. Blue Arena Box ONLY in Debug View (F2 / training_mode)
    if training_mode:
        pygame.draw.rect(
            viewport, (40, 150, 255),
            pygame.Rect(ARENA_OFFSET_X + shake_x, floor_y - 220 + shake_y, ARENA_WIDTH, 220),
            2
        )

    # 11. F4 Red Alignment Lines
    if show_alignment:
        draw_alignment_lines(viewport, floor_y, ARENA_OFFSET_X, ARENA_WIDTH, arena_name, font_small)

    # 12. Present Camera-Transformed Viewport to Screen (HUD stays unaffected!)
    if camera is not None:
        camera.present(viewport, surface, (0, 0))
    else:
        surface.blit(viewport, (0, 0))



def _draw_overlays_and_hud(surface, state, font_medium, font_small, human_player, hit_flash, trail1, trail2,
                           combo1, combo2, diff1, diff2, sparks, training_mode, dummy_mode, show_debug,
                           agent1, agent2, floor_y, screen_shake, shake_dir, r3d):
    f1 = state.fighter1
    f2 = state.fighter2
    shake_x = 0
    # 13. Super Flash Freeze Overlay (the 3D view darkens / pushes in on its own)
    if state.super_freeze_frames > 0:
        if r3d is None:
            dark = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            dark.fill((0, 0, 0, 150))
            surface.blit(dark, (0, 0))
        super_font = pygame.font.Font(None, 72)
        s_text = super_font.render("SUPER!", True, (255, 215, 0))
        surface.blit(s_text, s_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 40)))

    # 14. Training Mode Hitbox / Hurtbox Overlay (F1/F2)
    if training_mode:
        dummy_names = ["STAND", "CROUCH", "BLOCK ALL", "RANDOM"]
        d_text = f"TRAINING / DEBUG (F2): {dummy_names[dummy_mode]}"
        d_surf = font_small.render(d_text, True, (0, 255, 255))
        surface.blit(d_surf, (SCREEN_WIDTH // 2 - d_surf.get_width() // 2, 78))

        for f, num in ((f1, 1), (f2, 2)):
            if r3d is not None:
                bx, by = r3d.world_to_screen(f.x, 0.0)
                tx, ty = r3d.world_to_screen(f.x, 1.8)
                fx, fy = int(bx), int(ty)
            else:
                fx = ARENA_OFFSET_X + int(f.x)
                fy = floor_y - 90 if not f.in_air else floor_y - 160
            h_rect = pygame.Rect(fx - 22, fy, 44, 90)
            pygame.draw.rect(surface, (0, 255, 0), h_rect, 2)
            if f.attack_phase == "active":
                reach = 60
                atk_dir = 1 if (f.x < (f2.x if num == 1 else f1.x)) else -1
                atk_rect = pygame.Rect(fx, fy + 20, atk_dir * reach, 30)
                pygame.draw.rect(surface, (255, 0, 0), atk_rect, 2)
            tag = f"ADV: {'+' if f.blockstun <= 0 else '-'}{f.hitstun or f.blockstun or 0}f"
            tag_surf = font_small.render(tag, True, (255, 255, 0))
            surface.blit(tag_surf, (fx - 30, fy - 20))

    # 15. Static HUD (unaffected by camera zoom/pan)
    draw_hud(
        surface, state, font_medium, font_small, hit_flash=hit_flash,
        trail1=trail1, trail2=trail2, combo1=combo1, combo2=combo2,
        diff1=diff1 if human_player not in (1, 0, "both") else None,
        diff2=diff2 if human_player not in (2, 0, "both") else None,
        sparks=sparks
    )

    if state.rules.is_rumble:
        draw_rumble_hud_extras(surface, state, font_medium, font_small)

    if state.rules.enable_shield_wall:
        draw_shield_wall_hud(surface, state, font_small)

    if show_debug:
        from frontend.ai_viewer import _draw_profiling
        font_tiny = pygame.font.Font(None, 16)
        _draw_profiling(surface, agent1, agent2, font_tiny, state=state)


def _show_round_intro(surface, clock, state, arena_bg, round_num,
                      font_banner, font_medium, font_small,
                      char1, char2, is_mirror, human_player, speed_mult,
                      arena_name="arena_neon_rooftop", floor_y=FLOOR_HEIGHT, camera=None):
    """Round intro: 'ROUND X' for 1.0s, then 'FIGHT!' for 0.5s."""
    audio.play_sfx("round_start")
    intro_frames = int(30 * (1.0 / max(0.25, speed_mult)))
    if _ACTIVE_R3D is not None:
        intro_frames = int(60 * (1.0 / max(0.25, speed_mult)))   # longer: camera sweep
    for i in range(intro_frames):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _idle_step(state)
        sweep = (1.0 - i / max(1, intro_frames - 1)) ** 2
        _draw_fight_scene(
            surface, state, arena_bg, font_medium, font_small,
            char1, char2, is_mirror, human_player,
            0, 0, 1.0, 1.0, 0, 0, None, None, [],
            arena_name=arena_name, floor_y=floor_y, camera=camera, r3d_intro=sweep
        )
        _draw_center_banner(surface, f"ROUND {round_num}", font_banner, (255, 220, 80))
        pygame.display.flip()
        clock.tick(int(FPS * speed_mult))

    audio.play_sfx("fight")
    fight_frames = int(15 * (1.0 / max(0.25, speed_mult)))
    for _ in range(fight_frames):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _idle_step(state)
        _draw_fight_scene(
            surface, state, arena_bg, font_medium, font_small,
            char1, char2, is_mirror, human_player,
            0, 0, 1.0, 1.0, 0, 0, None, None, [],
            arena_name=arena_name, floor_y=floor_y, camera=camera
        )
        _draw_center_banner(surface, "FIGHT!", font_banner, (255, 60, 60))
        pygame.display.flip()
        clock.tick(int(FPS * speed_mult))


def _show_round_banner(surface, clock, state, arena_bg, banner_type,
                       font_banner, font_medium, font_small,
                       char1, char2, is_mirror, human_player, trail1, trail2,
                       arena_name="arena_neon_rooftop", floor_y=FLOOR_HEIGHT, camera=None):
    """Freeze for 1.5 seconds displaying K.O., TIME UP, or DRAW banner; camera pulls back to 1.0x."""
    if banner_type == "KO":
        audio.play_sfx("ko")
    banner_text = "K.O."
    banner_col = (255, 50, 50)
    if banner_type == "TIME":
        banner_text = "TIME UP"
        banner_col = (240, 240, 90)
    elif banner_type == "DRAW":
        banner_text = "DRAW"
        banner_col = (200, 210, 230)

    for _ in range(45):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        if camera is not None:
            camera.focus_x += (SCREEN_WIDTH / 2.0 - camera.focus_x) * 0.14
            camera.focus_y += (SCREEN_HEIGHT / 2.0 - camera.focus_y) * 0.14
            camera.zoom += (1.0 - camera.zoom) * 0.14
        _idle_step(state)
        _draw_fight_scene(
            surface, state, arena_bg, font_medium, font_small,
            char1, char2, is_mirror, human_player,
            0, 0, trail1, trail2, 0, 0, None, None, [],
            arena_name=arena_name, floor_y=floor_y, camera=camera
        )
        _draw_center_banner(surface, banner_text, font_banner, banner_col)
        pygame.display.flip()
        clock.tick(30)


def _slow_motion_ko(surface, clock, state, arena_bg, font_medium, font_small,
                    char1, char2, is_mirror, human_player, trail1, trail2, speed_mult,
                    arena_name="arena_neon_rooftop", floor_y=FLOOR_HEIGHT, camera=None):
    """KO camera: 0.3x slow motion for 30 frames, zooming in on the defeated fighter."""
    slow_fps = max(12, int(FPS * speed_mult * 0.3))
    loser = state.fighter1 if state.fighter1.health <= state.fighter2.health else state.fighter2
    ko_x = ARENA_OFFSET_X + loser.x

    for frame_i in range(30 if _ACTIVE_R3D is None else 54):
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
        if _ACTIVE_R3D is not None and frame_i % 3 == 0:
            _idle_step(state)    # 0.3x slow motion: the fall advances every third frame
        _draw_fight_scene(
            surface, state, arena_bg, font_medium, font_small,
            char1, char2, is_mirror, human_player,
            flash, 0, trail1, trail2, 0, 0, None, None, [],
            arena_name=arena_name, floor_y=floor_y, camera=camera,
            r3d_frac=(frame_i % 3) / 3.0, r3d_dt=1.0 / 180.0, r3d_ko=True
        )
        pygame.display.flip()
        clock.tick(slow_fps)


def _idle_step(state):
    """Advance the 3D animators without stepping the engine (intros, banners, KO)."""
    if _ACTIVE_R3D is not None:
        try:
            _ACTIVE_R3D.push_step(state, state)
        except Exception as exc:
            _disable_3d(exc)


def _draw_center_banner(surface, text, font, colour):
    """Draw huge high-contrast banner in screen center with dark backing."""
    banner_surf = font.render(text, True, colour)
    rect = banner_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20))

    strip = pygame.Rect(0, rect.top - 14, SCREEN_WIDTH, rect.height + 28)
    strip_surf = pygame.Surface((SCREEN_WIDTH, strip.height), pygame.SRCALPHA)
    strip_surf.fill((0, 0, 0, 160))
    surface.blit(strip_surf, (0, strip.top))

    shadow = font.render(text, True, BLACK)
    surface.blit(shadow, rect.move(3, 3))
    surface.blit(banner_surf, rect)
