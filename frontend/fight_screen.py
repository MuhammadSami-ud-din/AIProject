"""The fight screen: runs a full match with live rendering, arenas, and audio-visual punch.

Features:
  - Arena background rendering with 25% fight dimming overlay.
  - Frozen round intro: 1.0s "ROUND X" + 0.5s "FIGHT!" before movement begins.
  - Round end: 1.5s freeze banner ("K.O.", "TIME UP", "DRAW") and reset.
  - Hit-stop: 3 frames on light hits, 6 frames on heavy hits.
  - Screen shake on heavy hits and code-drawn hit sparks (white on hit, blue on block).
  - Sliding damage trail and floating combo counter.
  - Deciding round: slow-motion KO (half speed for 1.0s).
  - In-fight pause: Resume, Restart match, Quit.
  - Detailed match combat stats tracking.
"""

import random
import time
import pygame

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.engine.constants import ARENA_WIDTH, FPS
from backend.engine.step import make_initial_state, new_round, step
from frontend.assets import assets
from frontend.draw_fighter import draw_fighter
from frontend.hud import draw_hud
from frontend.input_handler import get_human_action
from frontend.screens import pause_screen
from frontend.theme import (
    FLOOR_HEIGHT,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SPARK_BLOCK,
    SPARK_HIT,
    WHITE,
    BLACK,
    TIMER_COLOUR,
)

ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2


def run_fight(surface, clock, agent1, agent2, human_player=None,
              speed_mult=1.0, arena_name=None):
    """Run a full match on screen.

    agent1, agent2: the two fighter brains.
    human_player: 1 or 2 if a human is playing, None for AI vs AI.
    speed_mult: gameplay speed multiplier (0.5x, 1x, 2x, 3x).
    arena_name: optional pre-selected arena name.

    Returns a match summary dict or "quit".
    """
    char1 = agent1.personality.name if agent1.personality else "Golden"
    char2 = agent2.personality.name if agent2.personality else "Golden"
    is_mirror = (char1 == char2)

    # Pick an arena if not specified
    if arena_name is None:
        p2_diff = getattr(agent2, "difficulty", "LOW")
        arena_name = assets.pick_arena(difficulty=p2_diff)

    arena_bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))

    # Fonts
    font_large = pygame.font.Font(None, 64)
    font_banner = pygame.font.Font(None, 84)
    font_medium = pygame.font.Font(None, 30)
    font_small = pygame.font.Font(None, 20)

    # Initialize match state
    while True:  # Outer loop allows "Restart Match" from pause
        state = make_initial_state(char1, char2)
        agent1.reset()
        agent2.reset()

        # Match Combat Statistics (for results screen & DB)
        stats = {
            "p1_name": "Player" if human_player == 1 else char1,
            "p2_name": char2,
            "p1_character": char1,
            "p2_character": char2,
            "p1_kind": "human" if human_player == 1 else "ai",
            "p2_kind": "human" if human_player == 2 else "ai",
            "p1_difficulty": getattr(agent1, "difficulty", "LOW"),
            "p2_difficulty": getattr(agent2, "difficulty", "LOW"),
            "arena": arena_name,
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

        # Frame feedback state
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
        hit_stop = 0
        sparks = []
        popups = []
        training_mode = False
        dummy_mode = 0  # 0: Stand, 1: Crouch, 2: Block All, 3: Random
        round_start_time = time.time()

        # Show round 1 intro
        _show_round_intro(surface, clock, state, arena_bg, 1,
                          font_banner, font_medium, font_small,
                          char1, char2, is_mirror, human_player, speed_mult)

        while not state.match_over:
            # --- 1. Handle events ---
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
                        dummy_mode = (dummy_mode + 1) % 4

            if state.match_over and pause_result == "restart":
                break  # Restart outer while loop

            # --- 2. Hit-Stop Freeze ---
            if hit_stop > 0:
                hit_stop -= 1
                # Still draw and tick during hit-stop
                _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                                  char1, char2, is_mirror, human_player,
                                  hit_flash, screen_shake, trail1, trail2,
                                  combo1, combo2, getattr(agent1, "difficulty", None),
                                  getattr(agent2, "difficulty", None), sparks,
                                  popups, training_mode, dummy_mode)
                pygame.display.flip()
                clock.tick(int(FPS * speed_mult))
                continue
                pygame.display.flip()
                clock.tick(int(FPS * speed_mult))
                continue

            # --- 3. Get Fighter Actions ---
            if human_player == 1:
                can_act1 = (
                    state.fighter1.recovery == 0
                    and state.fighter1.hitstun == 0
                    and state.fighter1.blockstun == 0
                    and not state.fighter1.is_knocked_down
                )
                action1 = get_human_action(state.fighter2.x, state.fighter1.x, in_air=state.fighter1.in_air, can_act=can_act1)
                obs2 = observation_for(state, 2)
                action2, _ = agent2.decide(obs2)
            elif human_player == 2:
                obs1 = observation_for(state, 1)
                action1, _ = agent1.decide(obs1)
                can_act2 = (
                    state.fighter2.recovery == 0
                    and state.fighter2.hitstun == 0
                    and state.fighter2.blockstun == 0
                    and not state.fighter2.is_knocked_down
                )
                action2 = get_human_action(state.fighter1.x, state.fighter2.x, in_air=state.fighter2.in_air, can_act=can_act2)
            else:
                obs1 = observation_for(state, 1)
                obs2 = observation_for(state, 2)
                action1, _ = agent1.decide(obs1)
                action2, _ = agent2.decide(obs2)

            # Record block actions for stats
            if action1 in (Action.BLOCK, Action.BLOCK_LOW):
                stats["blocks_p1"] += 1
            if action2 in (Action.BLOCK, Action.BLOCK_LOW):
                stats["blocks_p2"] += 1

            # --- 4. Engine Step ---
            state = step(state, action1, action2)

            # --- 5. Detect Hits, Sparks, Screen Shake, and Damage ---
            h1_diff = prev_health1 - state.fighter1.health
            h2_diff = prev_health2 - state.fighter2.health

            # Damage to Fighter 1 (hit by P2)
            if h1_diff > 0.001:
                stats["damage_dealt_p2"] += h1_diff
                stats["hits_landed_p2"] += 1
                hit_flash = 3
                is_blocked = (action1 in (Action.BLOCK, Action.BLOCK_LOW))
                spark_col = SPARK_BLOCK if is_blocked else SPARK_HIT
                hit_x = ARENA_OFFSET_X + int(state.fighter1.x)
                hit_y = FLOOR_HEIGHT - 60
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0})

                is_heavy = (h1_diff > 0.08)
                hit_stop = 6 if is_heavy else 3
                if is_heavy:
                    screen_shake = 6

                # Combo tracking for P2
                if combo2_timer > 0:
                    combo2 += 1
                else:
                    combo2 = 1
                combo2_timer = 30
                stats["longest_combo_p2"] = max(stats["longest_combo_p2"], combo2)

            # Damage to Fighter 2 (hit by P1)
            if h2_diff > 0.001:
                stats["damage_dealt_p1"] += h2_diff
                stats["hits_landed_p1"] += 1
                hit_flash = 3
                is_blocked = (action2 in (Action.BLOCK, Action.BLOCK_LOW))
                spark_col = SPARK_BLOCK if is_blocked else SPARK_HIT
                hit_x = ARENA_OFFSET_X + int(state.fighter2.x)
                hit_y = FLOOR_HEIGHT - 60
                sparks.append({"x": hit_x, "y": hit_y, "colour": spark_col, "frame": 0})

                is_heavy = (h2_diff > 0.08)
                hit_stop = 6 if is_heavy else 3
                if is_heavy:
                    screen_shake = 6

                # Combo tracking for P1
                if combo1_timer > 0:
                    combo1 += 1
                else:
                    combo1 = 1
                combo1_timer = 30
                stats["longest_combo_p1"] = max(stats["longest_combo_p1"], combo1)

            # --- Popup Combat Text (Phase 6) ---
            for f in (state.fighter1, state.fighter2):
                if f.last_hit_effect != "none":
                    effect = f.last_hit_effect
                    fx = ARENA_OFFSET_X + int(f.x)
                    fy = FLOOR_HEIGHT - 110
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

            # Advance popups
            for p in popups:
                p["y"] -= 1.0
                p["lifetime"] -= 1
            popups = [p for p in popups if p["lifetime"] > 0]

            prev_health1 = state.fighter1.health
            prev_health2 = state.fighter2.health

            # Update sliding damage trails
            trail1 = max(state.fighter1.health, trail1 - 0.006)
            trail2 = max(state.fighter2.health, trail2 - 0.006)

            # Combo timer decay
            if combo1_timer > 0:
                combo1_timer -= 1
                if combo1_timer == 0:
                    combo1 = 0
            if combo2_timer > 0:
                combo2_timer -= 1
                if combo2_timer == 0:
                    combo2 = 0

            # Advance sparks
            for s in sparks:
                s["frame"] += 1
            sparks = [s for s in sparks if s["frame"] < 8]

            # Decay flash and shake
            hit_flash = max(0, hit_flash - 1)
            screen_shake = max(0, screen_shake - 1)

            # --- 6. Let Agents Observe ---
            if human_player != 1:
                obs1 = observation_for(state, 1)
                agent1.observe(obs1, action1, action2)
            if human_player != 2:
                obs2 = observation_for(state, 2)
                agent2.observe(obs2, action2, action1)

            # --- 7. Draw Frame ---
            _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                              char1, char2, is_mirror, human_player,
                              hit_flash, screen_shake, trail1, trail2,
                              combo1, combo2, getattr(agent1, "difficulty", None),
                              getattr(agent2, "difficulty", None), sparks,
                              popups, training_mode, dummy_mode)
            pygame.display.flip()
            clock.tick(int(FPS * speed_mult))

            # --- 8. Round Over Transition ---
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

                # Check if match is deciding round
                if state.match_over:
                    # Slow-motion KO (half speed for 1 second)
                    _slow_motion_ko(surface, clock, state, arena_bg, font_medium, font_small,
                                    char1, char2, is_mirror, human_player, trail1, trail2, speed_mult)
                    # 1.5s freeze banner
                    _show_round_banner(surface, clock, state, arena_bg, ended_by,
                                       font_banner, font_medium, font_small,
                                       char1, char2, is_mirror, human_player, trail1, trail2)
                    break
                else:
                    # Normal round end: 1.5s freeze banner
                    _show_round_banner(surface, clock, state, arena_bg, ended_by,
                                       font_banner, font_medium, font_small,
                                       char1, char2, is_mirror, human_player, trail1, trail2)

                    # Reset fighters via engine
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
                    round_start_time = time.time()

                    # Show next round intro
                    _show_round_intro(surface, clock, state, arena_bg, state.round_number,
                                      font_banner, font_medium, font_small,
                                      char1, char2, is_mirror, human_player, speed_mult)

        # Match finished normally
        stats["winner_side"] = 1 if state.match_result == "p1" else (2 if state.match_result == "p2" else 0)
        stats["rounds_p1"] = state.p1_rounds_won
        stats["rounds_p2"] = state.p2_rounds_won
        stats["duration_s"] = round(time.time() - stats["start_time"], 1)
        stats["status"] = "finished"
        stats["match_result"] = state.match_result

        return stats


def _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                      char1, char2, is_mirror, human_player,
                      hit_flash, screen_shake, trail1, trail2,
                      combo1, combo2, diff1, diff2, sparks,
                      popups=None, training_mode=False, dummy_mode=0):
    """Draw the arena, fighters, projectiles, popups, super freeze, and HUD."""
    # Apply screen shake offset
    shake_x = 0
    shake_y = 0
    if screen_shake > 0:
        shake_x = random.randint(-4, 4)
        shake_y = random.randint(-4, 4)

    # Arena background
    surface.blit(arena_bg, (shake_x, shake_y))

    # Arena boundary lines
    pygame.draw.line(surface, (80, 85, 105),
                     (ARENA_OFFSET_X + shake_x, FLOOR_HEIGHT - 220 + shake_y),
                     (ARENA_OFFSET_X + shake_x, FLOOR_HEIGHT + shake_y), 2)
    pygame.draw.line(surface, (80, 85, 105),
                     (ARENA_OFFSET_X + ARENA_WIDTH + shake_x, FLOOR_HEIGHT - 220 + shake_y),
                     (ARENA_OFFSET_X + ARENA_WIDTH + shake_x, FLOOR_HEIGHT + shake_y), 2)

    # Draw Fighters
    f1 = state.fighter1
    f2 = state.fighter2
    facing1 = (f1.x < f2.x)
    facing2 = (f2.x < f1.x)

    draw_fighter(surface, f1, facing1,
                 arena_offset_x=ARENA_OFFSET_X + shake_x,
                 ground_y=FLOOR_HEIGHT + shake_y,
                 player_num=1,
                 is_mirror=False,
                 is_human=(human_player == 1))

    draw_fighter(surface, f2, facing2,
                 arena_offset_x=ARENA_OFFSET_X + shake_x,
                 ground_y=FLOOR_HEIGHT + shake_y,
                 player_num=2,
                 is_mirror=is_mirror,
                 is_human=(human_player == 2))

    # Draw Projectiles (Phase 4)
    for p in state.projectiles:
        px = ARENA_OFFSET_X + int(p.x) + shake_x
        py = FLOOR_HEIGHT - 45 + shake_y
        p_col = (0, 220, 255) if p.owner == 1 else (255, 120, 40)
        pygame.draw.circle(surface, p_col, (px, py), 8)
        pygame.draw.circle(surface, (255, 255, 255), (px, py), 4)
        trail_dir = -1 if p.vx > 0 else 1
        pygame.draw.line(surface, p_col, (px, py), (px + trail_dir * 18, py), 3)

    # Draw Popup Combat Text (Phase 6)
    if popups:
        for pop in popups:
            p_surf = font_medium.render(pop["text"], True, pop["color"])
            p_rect = p_surf.get_rect(center=(pop["x"], pop["y"]))
            # Drop shadow
            shadow_surf = font_medium.render(pop["text"], True, (0, 0, 0))
            surface.blit(shadow_surf, (p_rect.x + 2, p_rect.y + 2))
            surface.blit(p_surf, p_rect)

    # Super Flash Freeze Screen Darken (Phase 6)
    if state.super_freeze_frames > 0:
        dark = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 150))
        surface.blit(dark, (0, 0))
        super_font = pygame.font.Font(None, 72)
        s_text = super_font.render("SUPER!", True, (255, 215, 0))
        surface.blit(s_text, s_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 40)))

    # Training Mode Hitbox / Hurtbox Overlay & Frame Data (Phase 6)
    if training_mode:
        dummy_names = ["STAND", "CROUCH", "BLOCK ALL", "RANDOM"]
        d_text = f"TRAINING MODE | DUMMY (F2): {dummy_names[dummy_mode]}"
        d_surf = font_small.render(d_text, True, (0, 255, 255))
        surface.blit(d_surf, (SCREEN_WIDTH // 2 - d_surf.get_width() // 2, 75))

        for f, num in ((f1, 1), (f2, 2)):
            fx = ARENA_OFFSET_X + int(f.x) + shake_x
            fy = FLOOR_HEIGHT - 90 + shake_y if not f.in_air else FLOOR_HEIGHT - 160 + shake_y
            h_rect = pygame.Rect(fx - 25, fy, 50, 90)
            pygame.draw.rect(surface, (0, 255, 0), h_rect, 2)
            if f.attack_phase == "active":
                reach = 60
                atk_dir = 1 if (f.x < (f2.x if num == 1 else f1.x)) else -1
                atk_rect = pygame.Rect(fx, fy + 20, atk_dir * reach, 30)
                pygame.draw.rect(surface, (255, 0, 0), atk_rect, 2)
            # Frame info tag
            tag = f"ADV: {'+' if f.blockstun <= 0 else '-'}{f.hitstun or f.blockstun or 0}f"
            tag_surf = font_small.render(tag, True, (255, 255, 0))
            surface.blit(tag_surf, (fx - 30, fy - 20))

    # HUD (Health bars, damage trails, timer, combo counter, sparks)
    draw_hud(surface, state, font_medium, font_small, hit_flash=hit_flash,
             trail1=trail1, trail2=trail2, combo1=combo1, combo2=combo2,
             diff1=diff1, diff2=diff2, sparks=sparks)


def _show_round_intro(surface, clock, state, arena_bg, round_num,
                      font_banner, font_medium, font_small,
                      char1, char2, is_mirror, human_player, speed_mult):
    """Round intro: 'ROUND X' for 1.0s, then 'FIGHT!' for 0.5s. Inputs & timer frozen."""
    # Phase 1: 'ROUND X' (1.0 second = 30 frames at 30 FPS base)
    intro_frames = int(30 * (1.0 / max(0.25, speed_mult)))
    for _ in range(intro_frames):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                          char1, char2, is_mirror, human_player,
                          0, 0, 1.0, 1.0, 0, 0, None, None, [])
        _draw_center_banner(surface, f"ROUND {round_num}", font_banner, (255, 220, 80))
        pygame.display.flip()
        clock.tick(int(FPS * speed_mult))

    # Phase 2: 'FIGHT!' (0.5 second)
    fight_frames = int(15 * (1.0 / max(0.25, speed_mult)))
    for _ in range(fight_frames):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                          char1, char2, is_mirror, human_player,
                          0, 0, 1.0, 1.0, 0, 0, None, None, [])
        _draw_center_banner(surface, "FIGHT!", font_banner, (255, 60, 60))
        pygame.display.flip()
        clock.tick(int(FPS * speed_mult))


def _show_round_banner(surface, clock, state, arena_bg, banner_type,
                       font_banner, font_medium, font_small,
                       char1, char2, is_mirror, human_player, trail1, trail2):
    """Freeze for 1.5 seconds displaying K.O., TIME UP, or DRAW banner."""
    banner_text = "K.O."
    banner_col = (255, 50, 50)
    if banner_type == "TIME":
        banner_text = "TIME UP"
        banner_col = (240, 240, 90)
    elif banner_type == "DRAW":
        banner_text = "DRAW"
        banner_col = (200, 210, 230)

    # 1.5 seconds = 45 frames at 30 FPS
    for _ in range(45):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                          char1, char2, is_mirror, human_player,
                          0, 0, trail1, trail2, 0, 0, None, None, [])
        _draw_center_banner(surface, banner_text, font_banner, banner_col)
        pygame.display.flip()
        clock.tick(30)


def _slow_motion_ko(surface, clock, state, arena_bg, font_medium, font_small,
                    char1, char2, is_mirror, human_player, trail1, trail2, speed_mult):
    """Slow-motion freeze on deciding round KO (half speed for 1 second)."""
    half_fps = max(15, int(FPS * speed_mult * 0.5))
    for _ in range(30):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        _draw_fight_scene(surface, state, arena_bg, font_medium, font_small,
                          char1, char2, is_mirror, human_player,
                          0, 0, trail1, trail2, 0, 0, None, None, [])
        pygame.display.flip()
        clock.tick(half_fps)


def _draw_center_banner(surface, text, font, colour):
    """Draw huge high-contrast banner in screen center with dark backing."""
    banner_surf = font.render(text, True, colour)
    rect = banner_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20))

    # Dark translucent backing strip across the arena
    strip = pygame.Rect(0, rect.top - 14, SCREEN_WIDTH, rect.height + 28)
    strip_surf = pygame.Surface((SCREEN_WIDTH, strip.height), pygame.SRCALPHA)
    strip_surf.fill((0, 0, 0, 160))
    surface.blit(strip_surf, (0, strip.top))

    # Drop shadow
    shadow = font.render(text, True, BLACK)
    surface.blit(shadow, rect.move(3, 3))
    surface.blit(banner_surf, rect)
