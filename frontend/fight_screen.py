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


def run_fight(surface, clock, agent1, agent2, human_player=None,
              speed_mult=1.0, arena_name=None, rules=None,
              p1_level: int = 1, p2_level: int = 1, p1_regen: Optional[bool] = None,
              player_id: Optional[int] = None):
    """Run a full match on screen with dynamic camera, ambience, and modern HUD."""
    char1 = agent1.personality.name if getattr(agent1, "personality", None) else getattr(agent1, "character_name", "Golden")
    char2 = agent2.personality.name if getattr(agent2, "personality", None) else getattr(agent2, "character_name", "Golden")
    is_mirror = (char1 == char2)

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

        stats = {
            "mode": "Arena Rumble" if (rules and rules.is_rumble) else "Classic",
            "p1_name": "Player" if human_player == 1 else char1,
            "p2_name": char2,
            "p1_character": char1,
            "p2_character": char2,
            "p1_kind": "human" if human_player == 1 else "ai",
            "p2_kind": "human" if human_player == 2 else "ai",
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
        sparks = []
        shockwaves = []
        dust_particles = []
        popups = []
        f1_prev_in_air = False
        f2_prev_in_air = False
        f1_prev_kd = False
        f2_prev_kd = False
        training_mode = False
        dummy_mode = 0
        show_debug = False
        show_alignment = False
        pause_result = None
        round_start_time = time.time()

        _show_round_intro(
            surface, clock, state, arena_bg, 1,
            font_banner, font_medium, font_small,
            char1, char2, is_mirror, human_player, speed_mult,
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

            # --- Hit-Stop Freeze (3f light, 6f heavy, 10f super) ---
            if hit_stop > 0:
                hit_stop -= 1
                _draw_fight_scene(
                    surface, state, arena_bg, font_medium, font_small,
                    char1, char2, is_mirror, human_player,
                    hit_flash, screen_shake, trail1, trail2,
                    combo1, combo2, getattr(agent1, "difficulty", None),
                    getattr(agent2, "difficulty", None), sparks,
                    popups, training_mode, dummy_mode,
                    shockwaves=shockwaves, dust_particles=dust_particles,
                    shake_dir=shake_dir, show_debug=show_debug,
                    agent1=agent1, agent2=agent2,
                    arena_name=arena_name, floor_y=floor_y,
                    camera=camera, show_alignment=show_alignment
                )
                pygame.display.flip()
                clock.tick(int(FPS * speed_mult))
                continue

            # --- Fighter Decisions ---
            f1_was_stuck = (state.fighter1.recovery > 0)
            f2_was_stuck = (state.fighter2.recovery > 0)

            if human_player == 1:
                can_act1 = (not state.fighter1.busy and state.fighter1.cooldown <= 0) or state.fighter1.cancel_available
                action1 = get_human_action(
                    state.fighter2.x,
                    state.fighter1.x,
                    in_air=state.fighter1.in_air,
                    can_act=can_act1,
                    enable_shield_wall=state.rules.enable_shield_wall,
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
            elif human_player == 2:
                obs1 = observation_for(state, 1)
                action1, _ = agent1.decide(obs1)
                can_act2 = (not state.fighter2.busy and state.fighter2.cooldown <= 0) or state.fighter2.cancel_available
                action2 = get_human_action(
                    state.fighter1.x,
                    state.fighter2.x,
                    in_air=state.fighter2.in_air,
                    can_act=can_act2,
                    enable_shield_wall=state.rules.enable_shield_wall,
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

            # Play attack / special / movement SFX
            if action1 in (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB, Action.CROUCH_KICK):
                audio.play_sfx("whoosh_light")
            elif action1 in (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD):
                audio.play_sfx("whoosh_heavy")
            elif action1 in (Action.SPECIAL_NEUTRAL, Action.SPECIAL_FORWARD, Action.SPECIAL_BACK, Action.SPECIAL_DOWN):
                audio.play_sfx("special")
                stats["specials_p1"] += 1
            elif action1 == Action.SUPER:
                audio.play_sfx("super")
            elif action1 == Action.THROW:
                audio.play_sfx("throw")
                stats["throws_p1"] += 1
            elif action1 in (Action.DASH, Action.BACKDASH):
                audio.play_sfx("dash")

            state = step(state, action1, action2)

            # Check comeback condition
            if state.fighter1.health < 0.15:
                stats["comeback_p1"] = True

            # Update dynamic camera toward midpoint
            camera.update(
                ARENA_OFFSET_X + state.fighter1.x,
                ARENA_OFFSET_X + state.fighter2.x,
                floor_y,
            )

            # --- Hits, Sparks, Screen Shake, and Floating Text ---
            h1_diff = prev_health1 - state.fighter1.health
            h2_diff = prev_health2 - state.fighter2.health

            if h1_diff > 0.001:
                stats["damage_dealt_p2"] += h1_diff
                stats["hits_landed_p2"] += 1
                is_blocked = (action1 in (Action.BLOCK, Action.BLOCK_LOW) or state.fighter1.blockstun > 0)
                is_counter = (state.fighter1.last_hit_effect == "counter" or state.fighter1.is_counter_hit)
                is_super = (action2 == Action.SUPER or h1_diff >= 0.18)
                is_heavy = (h1_diff > 0.07)

                if is_blocked:
                    audio.play_sfx("block")
                elif is_super or is_heavy:
                    audio.play_sfx("hit_heavy")
                else:
                    audio.play_sfx("hit_light")

                spark_kind = "block" if is_blocked else ("counter" if is_counter else "hit")
                spark_col = SPARK_BLOCK if is_blocked else (SPARK_COUNTER if is_counter else SPARK_HIT)
                hit_x = ARENA_OFFSET_X + int(state.fighter1.x)
                hit_y = floor_y - 62
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0, "kind": spark_kind})

                hit_flash = 4 if is_counter else 2
                hit_stop = 10 if is_super else (6 if is_heavy else 3)
                screen_shake = 12 if is_super else (5 if is_heavy else 2)
                shake_dir = 1 if state.fighter2.x < state.fighter1.x else -1

                if is_blocked:
                    popups.append({"text": "BLOCKED", "x": hit_x, "y": floor_y - 110, "color": (120, 210, 255), "lifetime": 20, "max_lifetime": 20})
                elif f1_was_stuck and not is_counter:
                    popups.append({"text": "PUNISH!", "x": hit_x, "y": floor_y - 115, "color": (255, 215, 50), "lifetime": 20, "max_lifetime": 20})

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

                if is_blocked:
                    audio.play_sfx("block")
                elif is_super or is_heavy:
                    audio.play_sfx("hit_heavy")
                else:
                    audio.play_sfx("hit_light")

                if action1 == Action.SUPER and state.fighter2.health <= 0.0:
                    stats["super_ko_p1"] = True

                spark_kind = "block" if is_blocked else ("counter" if is_counter else "hit")
                spark_col = SPARK_BLOCK if is_blocked else (SPARK_COUNTER if is_counter else SPARK_HIT)
                hit_x = ARENA_OFFSET_X + int(state.fighter2.x)
                hit_y = floor_y - 62
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0, "kind": spark_kind})

                hit_flash = 4 if is_counter else 2
                hit_stop = 10 if is_super else (6 if is_heavy else 3)
                screen_shake = 12 if is_super else (5 if is_heavy else 2)
                shake_dir = 1 if state.fighter1.x < state.fighter2.x else -1

                if is_blocked:
                    popups.append({"text": "BLOCKED", "x": hit_x, "y": floor_y - 110, "color": (120, 210, 255), "lifetime": 20, "max_lifetime": 20})
                elif f2_was_stuck and not is_counter:
                    popups.append({"text": "PUNISH!", "x": hit_x, "y": floor_y - 115, "color": (255, 215, 50), "lifetime": 20, "max_lifetime": 20})

                if combo1_timer > 0:
                    combo1 += 1
                else:
                    combo1 = 1
                combo1_timer = 30
                stats["longest_combo_p1"] = max(stats["longest_combo_p1"], combo1)

            # --- Dust Puffs on Landing, Dashing, and Knockdown ---
            f1 = state.fighter1
            f2 = state.fighter2
            for f, prev_air, prev_kd in ((f1, f1_prev_in_air, f1_prev_kd), (f2, f2_prev_in_air, f2_prev_kd)):
                fx = ARENA_OFFSET_X + int(f.x)
                if (prev_air and not f.in_air) or (not prev_kd and f.is_knocked_down):
                    puff_count = 6 if f.is_knocked_down else 4
                    for _ in range(puff_count):
                        dust_particles.append({
                            "x": fx + random.uniform(-14, 14),
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
                        "x": fx + random.uniform(-6, 6),
                        "y": floor_y - random.uniform(1, 3),
                        "vx": random.uniform(-1.8, 1.8),
                        "vy": random.uniform(-0.9, -0.2),
                        "radius": random.uniform(2.8, 5.0),
                        "lifetime": 12,
                        "max_lifetime": 12,
                        "colour": (185, 180, 170),
                    })

            if not f1_prev_in_air and f1.in_air:
                audio.play_sfx("jump")
            elif f1_prev_in_air and not f1.in_air:
                audio.play_sfx("land")

            f1_prev_in_air = f1.in_air
            f2_prev_in_air = f2.in_air
            f1_prev_kd = f1.is_knocked_down
            f2_prev_kd = f2.is_knocked_down

            # --- Engine Hit Effects (Counter, Parry, Guard Break, Burst) ---
            for f in (state.fighter1, state.fighter2):
                if f.last_hit_effect != "none":
                    effect = f.last_hit_effect
                    fx = ARENA_OFFSET_X + int(f.x)
                    fy = floor_y - 115
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

            if human_player != 1:
                obs1 = observation_for(state, 1)
                agent1.observe(obs1, action1, action2)
            if human_player != 2:
                obs2 = observation_for(state, 2)
                agent2.observe(obs2, action2, action1)

            _draw_fight_scene(
                surface, state, arena_bg, font_medium, font_small,
                char1, char2, is_mirror, human_player,
                hit_flash, screen_shake, trail1, trail2,
                combo1, combo2, getattr(agent1, "difficulty", None),
                getattr(agent2, "difficulty", None), sparks,
                popups, training_mode, dummy_mode,
                shockwaves=shockwaves, dust_particles=dust_particles,
                shake_dir=shake_dir, show_debug=show_debug,
                agent1=agent1, agent2=agent2,
                arena_name=arena_name, floor_y=floor_y,
                camera=camera, show_alignment=show_alignment
            )
            pygame.display.flip()
            clock.tick(int(FPS * speed_mult))

            if state.round_over:
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
                    _slow_motion_ko(
                        surface, clock, state, arena_bg, font_medium, font_small,
                        char1, char2, is_mirror, human_player, trail1, trail2, speed_mult,
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
                        char1, char2, is_mirror, human_player, trail1, trail2,
                        arena_name=arena_name, floor_y=floor_y, camera=camera
                    )
                    break
                else:
                    _show_round_banner(
                        surface, clock, state, arena_bg, ended_by,
                        font_banner, font_medium, font_small,
                        char1, char2, is_mirror, human_player, trail1, trail2,
                        arena_name=arena_name, floor_y=floor_y, camera=camera
                    )

                    state = new_round(state)
                    agent1.reset()
                    agent2.reset()
                    camera = CameraState(SCREEN_WIDTH, SCREEN_HEIGHT)
                    prev_health1 = 1.0
                    prev_health2 = 1.0
                    trail1 = 1.0
                    trail2 = 1.0
                    combo1 = 0
                    combo2 = 0
                    sparks.clear()
                    round_start_time = time.time()

                    _show_round_intro(
                        surface, clock, state, arena_bg, state.round_number,
                        font_banner, font_medium, font_small,
                        char1, char2, is_mirror, human_player, speed_mult,
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

        if player_id is not None and human_player == 1:
            new_trophies = check_match_trophies(stats, player_id)
            if new_trophies:
                stats["unlocked_trophies"] = new_trophies
            new_missions = check_match_missions(stats, player_id)
            if new_missions:
                stats["completed_missions"] = new_missions

        return stats


def _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                      char1, char2, is_mirror, human_player,
                      hit_flash, screen_shake, trail1, trail2,
                      combo1, combo2, diff1, diff2, sparks,
                      popups=None, training_mode=False, dummy_mode=0,
                      shockwaves=None, dust_particles=None, shake_dir=0,
                      show_debug=False, agent1=None, agent2=None,
                      arena_name="arena_neon_rooftop", floor_y=FLOOR_HEIGHT,
                      camera=None, show_alignment=False):
    """Draw the fight viewport (with camera zoom/pan, ambience, vignette) and static HUD on top."""
    viewport = _get_fight_viewport()

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

    # 13. Super Flash Freeze Overlay
    if state.super_freeze_frames > 0:
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
            fx = ARENA_OFFSET_X + int(f.x) + shake_x
            fy = floor_y - 90 + shake_y if not f.in_air else floor_y - 160 + shake_y
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
        diff1=diff1 if human_player != 1 else None,
        diff2=diff2 if human_player != 2 else None,
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
    for _ in range(intro_frames):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_fight_scene(
            surface, state, arena_bg, font_medium, font_small,
            char1, char2, is_mirror, human_player,
            0, 0, 1.0, 1.0, 0, 0, None, None, [],
            arena_name=arena_name, floor_y=floor_y, camera=camera
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
        _draw_fight_scene(
            surface, state, arena_bg, font_medium, font_small,
            char1, char2, is_mirror, human_player,
            flash, 0, trail1, trail2, 0, 0, None, None, [],
            arena_name=arena_name, floor_y=floor_y, camera=camera
        )
        pygame.display.flip()
        clock.tick(slow_fps)


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
