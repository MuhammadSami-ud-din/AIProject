"""Generate headless screenshots for Arena Rumble phases 1 through 6.

Uses pygame headlessly (dummy video driver) to render the exact in-game
surfaces and HUD overlays to PNG files in the artifact directory.
"""

import os
import pygame

# Set dummy video driver for headless rendering
os.environ["SDL_VIDEODRIVER"] = "dummy"

pygame.init()
pygame.font.init()

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.rules import ModeRules
from backend.engine.rumble_config import (
    CRATE_MAX_HP,
    CRATE_WIDTH,
    JUMP_PAD_HEIGHT,
    JUMP_PAD_WIDTH,
    TRAP_HEIGHT,
    TRAP_WIDTH,
    WALL_HEIGHT,
    WALL_MAX_HP,
    WALL_WIDTH,
)
from backend.engine.rumble_state import (
    ArenaObjectState,
    ItemState,
    KillFeedMessage,
    SupplyDropState,
    WallState,
    ZoneState,
)
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state
from frontend.draw_rumble import (
    draw_rumble_hud_extras,
    draw_rumble_items,
    draw_rumble_objects,
    draw_rumble_walls,
    draw_rumble_zone,
)

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 450
FLOOR_HEIGHT = 80
GROUND_Y = SCREEN_HEIGHT - FLOOR_HEIGHT

ARTIFACT_DIR = r"C:\Users\Muhammad Abdul Wahid\.gemini\antigravity\brain\6a188633-c12f-4cf7-b251-2e77ead26f1b"


def create_base_surface():
    """Create a dark stylized fighting arena background."""
    surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    for y in range(SCREEN_HEIGHT):
        ratio = y / SCREEN_HEIGHT
        r = int(18 + ratio * 15)
        g = int(20 + ratio * 20)
        b = int(32 + ratio * 30)
        pygame.draw.line(surf, (r, g, b), (0, y), (SCREEN_WIDTH, y))

    floor_rect = pygame.Rect(0, GROUND_Y, SCREEN_WIDTH, SCREEN_HEIGHT - GROUND_Y)
    pygame.draw.rect(surf, (40, 44, 58), floor_rect)
    pygame.draw.line(surf, (80, 110, 160), (0, GROUND_Y), (SCREEN_WIDTH, GROUND_Y), 2)
    return surf


def draw_sample_fighters(surf, state):
    """Draw simple placeholder fighter silhouettes on the floor."""
    f1 = state.fighter1
    f2 = state.fighter2

    # Fighter 1 (Golden)
    f1_rect = pygame.Rect(int(f1.x - 20), GROUND_Y - 90, 40, 90)
    pygame.draw.rect(surf, (220, 180, 50), f1_rect, border_radius=4)
    pygame.draw.rect(surf, (255, 220, 100), f1_rect, 2, border_radius=4)

    # Fighter 2 (Crimson)
    f2_rect = pygame.Rect(int(f2.x - 20), GROUND_Y - 90, 40, 90)
    pygame.draw.rect(surf, (200, 50, 60), f2_rect, border_radius=4)
    pygame.draw.rect(surf, (255, 100, 110), f2_rect, 2, border_radius=4)


def render_phase1_zone():
    surf = create_base_surface()
    rules = ModeRules.rumble(enable_zone=True)
    state = make_initial_state("Golden", "Crimson", rules=rules, seed=42)

    state.zone.left = 140.0
    state.zone.right = 660.0
    state.zone.stage = 2
    state.zone.is_closing = True
    state.zone.is_warning = True
    state.zone.target_left = 195.0
    state.zone.target_right = 605.0

    state.fighter1.x = 220.0
    state.fighter2.x = 580.0

    draw_rumble_zone(surf, state.zone, 0, FLOOR_HEIGHT, state.frame)
    draw_sample_fighters(surf, state)

    font = pygame.font.SysFont("Arial", 22, bold=True)
    lbl = font.render("PHASE 1: THE SQUEEZE (Shrinking Energy Barrier)", True, (255, 215, 0))
    surf.blit(lbl, (SCREEN_WIDTH // 2 - lbl.get_width() // 2, 20))

    out_path = os.path.join(ARTIFACT_DIR, "rumble_phase1_zone.png")
    pygame.image.save(surf, out_path)
    print(f"Saved: {out_path}")


def render_phase2_walls():
    surf = create_base_surface()
    rules = ModeRules.rumble(enable_building=True)
    state = make_initial_state("Golden", "Crimson", rules=rules, seed=42)

    state.fighter1.x = 220.0
    state.fighter1.build_charges = 2
    state.fighter2.x = 580.0
    state.fighter2.build_charges = 1

    # Place 3 walls with different damage levels to show crack stages
    state.walls = [
        WallState(id=1, owner=1, x=290.0, y=0.0, hp=30.0, max_hp=30.0),  # Full HP
        WallState(id=2, owner=1, x=370.0, y=0.0, hp=18.0, max_hp=30.0),  # Stage 1 cracks (<=66%)
        WallState(id=3, owner=2, x=510.0, y=0.0, hp=8.0, max_hp=30.0),   # Stage 2 cracks (<=33%)
    ]

    draw_rumble_walls(surf, state.walls, 0, FLOOR_HEIGHT)
    draw_sample_fighters(surf, state)

    font = pygame.font.SysFont("Arial", 22, bold=True)
    lbl = font.render("PHASE 2: BUILDING (Cover Walls & Crack States)", True, (100, 220, 255))
    surf.blit(lbl, (SCREEN_WIDTH // 2 - lbl.get_width() // 2, 20))

    out_path = os.path.join(ARTIFACT_DIR, "rumble_phase2_walls.png")
    pygame.image.save(surf, out_path)
    print(f"Saved: {out_path}")


def render_phase3_loot():
    surf = create_base_surface()
    rules = ModeRules.rumble(enable_loot=True)
    state = make_initial_state("Golden", "Crimson", rules=rules, seed=42)

    state.fighter1.x = 240.0
    state.fighter1.shield = 25.0
    state.fighter1.speed_boost_timer = 280
    state.fighter2.x = 560.0
    state.fighter2.power_boost_timer = 200

    # Ground items
    state.items = [
        ItemState(id=1, item_type="medkit", x=320.0, y=0.0),
        ItemState(id=2, item_type="shield_cell", x=480.0, y=0.0),
    ]
    # Falling golden supply crate
    state.supply_drop = SupplyDropState(
        id=3, item_type="big_medkit", x=400.0, y=-160.0, target_y=0.0, is_landed=False
    )

    draw_rumble_items(surf, state.items, state.supply_drop, 0, FLOOR_HEIGHT, state.frame)
    draw_sample_fighters(surf, state)

    font = pygame.font.SysFont("Arial", 22, bold=True)
    lbl = font.render("PHASE 3: LOOT & SUPPLY DROPS (Items & Falling Crate)", True, (255, 230, 80))
    surf.blit(lbl, (SCREEN_WIDTH // 2 - lbl.get_width() // 2, 20))

    out_path = os.path.join(ARTIFACT_DIR, "rumble_phase3_loot.png")
    pygame.image.save(surf, out_path)
    print(f"Saved: {out_path}")


def render_phase4_objects():
    surf = create_base_surface()
    rules = ModeRules.rumble(enable_objects=True)
    state = make_initial_state("Golden", "Crimson", rules=rules, seed=42)

    state.fighter1.x = 200.0
    state.fighter2.x = 600.0

    state.arena_objects = [
        ArenaObjectState(id=1, object_type="crate", x=260.0, y=0.0, width=CRATE_WIDTH, height=48.0, hp=CRATE_MAX_HP, max_hp=CRATE_MAX_HP),
        ArenaObjectState(id=2, object_type="crate", x=540.0, y=0.0, width=CRATE_WIDTH, height=48.0, hp=12.0, max_hp=CRATE_MAX_HP),
        ArenaObjectState(id=3, object_type="jump_pad", x=140.0, y=0.0, width=JUMP_PAD_WIDTH, height=JUMP_PAD_HEIGHT, hp=999.0, max_hp=999.0),
        ArenaObjectState(id=4, object_type="jump_pad", x=660.0, y=0.0, width=JUMP_PAD_WIDTH, height=JUMP_PAD_HEIGHT, hp=999.0, max_hp=999.0),
        ArenaObjectState(id=5, object_type="trap", x=400.0, y=0.0, width=TRAP_WIDTH, height=TRAP_HEIGHT, hp=999.0, max_hp=999.0, is_triggered=True, trigger_timer=12),
    ]

    draw_rumble_objects(surf, state.arena_objects, 0, FLOOR_HEIGHT, state.frame)
    draw_sample_fighters(surf, state)

    font = pygame.font.SysFont("Arial", 22, bold=True)
    lbl = font.render("PHASE 4: CRATES, JUMP PADS & SPIKE TRAPS", True, (255, 140, 60))
    surf.blit(lbl, (SCREEN_WIDTH // 2 - lbl.get_width() // 2, 20))

    out_path = os.path.join(ARTIFACT_DIR, "rumble_phase4_objects.png")
    pygame.image.save(surf, out_path)
    print(f"Saved: {out_path}")


def render_full_rumble_hud():
    surf = create_base_surface()
    rules = ModeRules.rumble(
        enable_zone=True,
        enable_building=True,
        enable_loot=True,
        enable_objects=True,
    )
    state = make_initial_state("Golden", "Crimson", rules=rules, seed=42)

    # Active Zone
    state.zone.left = 130.0
    state.zone.right = 670.0
    state.zone.stage = 2
    state.zone.is_closing = True
    state.zone.is_warning = True
    state.zone.phase_frame = 300

    # Fighters with buffs & shield
    state.fighter1.x = 240.0
    state.fighter1.health = 0.85
    state.fighter1.shield = 20.0
    state.fighter1.build_charges = 3
    state.fighter1.speed_boost_timer = 240

    state.fighter2.x = 560.0
    state.fighter2.health = 0.65
    state.fighter2.shield = 10.0
    state.fighter2.build_charges = 1
    state.fighter2.power_boost_timer = 180

    # Walls, Crates, Items, Drop
    state.walls = [
        WallState(id=1, owner=1, x=310.0, y=0.0, hp=25.0, max_hp=30.0),
        WallState(id=2, owner=2, x=490.0, y=0.0, hp=15.0, max_hp=30.0),
    ]
    state.items = [
        ItemState(id=3, item_type="medkit", x=200.0, y=0.0),
    ]
    state.arena_objects = [
        ArenaObjectState(id=4, object_type="crate", x=270.0, y=0.0, width=CRATE_WIDTH, height=48.0, hp=25.0, max_hp=25.0),
        ArenaObjectState(id=5, object_type="jump_pad", x=160.0, y=0.0, width=JUMP_PAD_WIDTH, height=JUMP_PAD_HEIGHT, hp=999.0, max_hp=999.0),
        ArenaObjectState(id=6, object_type="trap", x=400.0, y=0.0, width=TRAP_WIDTH, height=TRAP_HEIGHT, hp=999.0, max_hp=999.0),
    ]
    state.supply_drop = SupplyDropState(
        id=7, item_type="overcharge", x=400.0, y=-90.0, target_y=0.0, is_landed=False
    )
    state.kill_feed = [
        KillFeedMessage("Crimson broke a Cover Wall!", (255, 120, 50), 120),
        KillFeedMessage("Golden collected Shield Cell (+25 Shield)", (0, 200, 255), 150),
        KillFeedMessage("SUPPLY DROP INCOMING!", (255, 220, 0), 180),
    ]

    # Draw everything
    draw_rumble_zone(surf, state.zone, 0, FLOOR_HEIGHT, state.frame)
    draw_rumble_objects(surf, state.arena_objects, 0, FLOOR_HEIGHT, state.frame)
    draw_rumble_walls(surf, state.walls, 0, FLOOR_HEIGHT)
    draw_rumble_items(surf, state.items, state.supply_drop, 0, FLOOR_HEIGHT, state.frame)
    draw_sample_fighters(surf, state)

    font_med = pygame.font.SysFont("Arial", 16, bold=True)
    font_small = pygame.font.SysFont("Arial", 12)
    draw_rumble_hud_extras(surf, state, font_med, font_small)

    out_path = os.path.join(ARTIFACT_DIR, "rumble_hud_full.png")
    pygame.image.save(surf, out_path)
    print(f"Saved: {out_path}")


def generate_visual_overhaul_screenshots():
    """Render the 4 Visual Overhaul deliverable screenshots and benchmark frame times."""
    import time
    from backend.ai.adapter import observation_for
    from backend.ai.crimson import CrimsonAgent
    from backend.ai.golden import GoldenAgent
    from backend.ai.shadow import ShadowAgent
    from backend.ai.steel import SteelAgent
    from frontend.ai_viewer import _build_info, _draw_full_frame
    from frontend.assets import assets
    from frontend.camera_effects import CameraState
    from frontend.fight_screen import ARENA_OFFSET_X, _draw_center_banner, _draw_fight_scene
    from frontend.theme import SCREEN_HEIGHT as FULL_H, SCREEN_WIDTH as FULL_W, SPARK_COUNTER, get_arena_floor_y

    surf = pygame.Surface((FULL_W, FULL_H))
    font_large = pygame.font.Font(None, 52)
    font_banner = pygame.font.Font(None, 84)
    font_medium = pygame.font.Font(None, 28)
    font_small = pygame.font.Font(None, 20)
    font_tiny = pygame.font.Font(None, 16)

    # 1. Frozen Peak with fighters close (showing pushbox, jointed fighters, new HUD, snow particles)
    arena1 = "arena_frozen_peak"
    bg1 = assets.get_arena(arena1, size=(FULL_W, FULL_H))
    state1 = make_initial_state("Crimson", "Golden")
    state1.frame = 120
    state1.round_frames_left = 3120
    state1.p1_rounds_won = 1
    state1.p2_rounds_won = 1
    state1.fighter1.x = 384.0
    state1.fighter2.x = 416.0  # Close pushbox contact (32px separation)
    state1.fighter1.health = 0.78
    state1.fighter2.health = 0.52
    state1.fighter1.meter = 68.0
    state1.fighter2.meter = 100.0
    state1.fighter1.guard_meter = 85.0
    state1.fighter2.guard_meter = 42.0
    state1.fighter1.last_action = Action.DASH
    state1.fighter2.last_action = Action.BLOCK

    agent1 = CrimsonAgent(player=1, difficulty="HIGH", seed=10)
    agent2 = GoldenAgent(player=2, difficulty="HELL", seed=20)
    obs1 = observation_for(state1, 1)
    obs2 = observation_for(state1, 2)
    a1, sc1 = agent1.decide(obs1)
    a2, sc2 = agent2.decide(obs2)
    info1 = _build_info(agent1, Action.DASH, sc1, obs1, player_num=1)
    info2 = _build_info(agent2, Action.BLOCK, sc2, obs2, player_num=2)

    cam1 = CameraState(FULL_W, FULL_H - 180)
    for _ in range(12):
        cam1.update(ARENA_OFFSET_X + state1.fighter1.x, ARENA_OFFSET_X + state1.fighter2.x, get_arena_floor_y(arena1, FULL_H - 180))

    _draw_full_frame(
        surf, state1, bg1, "Frozen Peak",
        info1, info2, font_large, font_medium, font_small, font_tiny,
        "Crimson", "Golden", False, agent1, agent2,
        0, 0, 2, False, False, 0.88, 0.68, 3, 0, [], [],
        arena_name=arena1, camera=cam1, panel_collapsed=False
    )
    p1_path = os.path.join(ARTIFACT_DIR, "frozen_peak_close.png")
    pygame.image.save(surf, p1_path)
    print(f"Saved: {p1_path}")

    # 2. Heavy Hit Impact (starburst spark, white hurt flash, floating text "COUNTER!", motion arc, camera zoom)
    arena2 = "arena_neon_rooftop"
    bg2 = assets.get_arena(arena2, size=(FULL_W, FULL_H))
    floor2 = get_arena_floor_y(arena2, FULL_H)
    state2 = make_initial_state("Steel", "Shadow")
    state2.frame = 245
    state2.round_frames_left = 2850
    state2.p1_rounds_won = 1
    state2.fighter1.x = 375.0
    state2.fighter2.x = 425.0
    state2.fighter1.health = 0.64
    state2.fighter2.health = 0.38
    state2.fighter1.meter = 80.0
    state2.fighter2.meter = 55.0
    state2.fighter1.attack_phase = "active"
    state2.fighter1.attack_type = "heavy_punch"
    state2.fighter1.current_action = Action.HEAVY
    state2.fighter2.hitstun = 16

    # Trigger 2-frame white hurt flash on P2 only
    from frontend.draw_fighter import _HURT_FLASH_TIMER, _PREV_HEALTH_STATE
    _PREV_HEALTH_STATE.clear()
    _HURT_FLASH_TIMER[1] = 0
    _HURT_FLASH_TIMER[2] = 2

    cam2 = CameraState(FULL_W, FULL_H)
    for _ in range(15):
        cam2.update(ARENA_OFFSET_X + state2.fighter1.x, ARENA_OFFSET_X + state2.fighter2.x, floor2)

    sparks2 = [
        {"x": ARENA_OFFSET_X + int(state2.fighter2.x) - 8, "y": floor2 - 62, "colour": SPARK_COUNTER, "frame": 1, "kind": "counter"},
    ]
    popups2 = [
        {"text": "COUNTER!", "x": ARENA_OFFSET_X + int(state2.fighter2.x), "y": floor2 - 118, "color": (255, 68, 68), "lifetime": 19, "max_lifetime": 20},
    ]
    dust2 = [
        {"x": ARENA_OFFSET_X + state2.fighter1.x - 10, "y": floor2 - 3, "vx": -1.0, "vy": -0.5, "radius": 5.0, "lifetime": 12, "max_lifetime": 15, "colour": (200, 195, 185)},
    ]

    _draw_fight_scene(
        surf, state2, bg2, font_medium, font_small,
        "Steel", "Shadow", False, 1,
        2, 4, 0.72, 0.56, 4, 0, None, "HIGH", sparks2,
        popups=popups2, dust_particles=dust2,
        arena_name=arena2, floor_y=floor2, camera=cam2
    )
    p2_path = os.path.join(ARTIFACT_DIR, "heavy_hit_impact.png")
    pygame.image.save(surf, p2_path)
    print(f"Saved: {p2_path}")

    # 3. KO Moment (KO slow-mo zoom on defeated fighter, white flash, defeated knockdown pose, K.O. banner)
    _PREV_HEALTH_STATE.clear()
    _HURT_FLASH_TIMER.clear()
    arena3 = "arena_volcanic_forge"
    bg3 = assets.get_arena(arena3, size=(FULL_W, FULL_H))
    floor3 = get_arena_floor_y(arena3, FULL_H)
    state3 = make_initial_state("Crimson", "Shadow")
    state3.frame = 510
    state3.round_frames_left = 480  # 8 seconds left -> red pulsing timer!
    state3.p1_rounds_won = 2
    state3.p2_rounds_won = 1
    state3.fighter1.x = 420.0
    state3.fighter2.x = 490.0
    state3.fighter1.health = 0.21  # Fury active!
    state3.fighter2.health = 0.0
    state3.fighter2.is_knocked_down = True
    state3.fighter1.meter = 100.0

    cam3 = CameraState(FULL_W, FULL_H)
    for _ in range(18):
        cam3.update(
            ARENA_OFFSET_X + state3.fighter1.x,
            ARENA_OFFSET_X + state3.fighter2.x,
            floor3,
            ko_target_x=ARENA_OFFSET_X + state3.fighter2.x,
            lerp_t=0.2,
        )

    sparks3 = [
        {"x": ARENA_OFFSET_X + int(state3.fighter2.x), "y": floor3 - 35, "colour": SPARK_COUNTER, "frame": 2, "kind": "counter"},
    ]
    _draw_fight_scene(
        surf, state3, bg3, font_medium, font_small,
        "Crimson", "Shadow", False, 1,
        3, 0, 0.28, 0.22, 6, 0, None, "HELL", sparks3,
        arena_name=arena3, floor_y=floor3, camera=cam3
    )
    _draw_center_banner(surf, "K.O.", font_banner, (255, 55, 55))
    p3_path = os.path.join(ARTIFACT_DIR, "ko_moment.png")
    pygame.image.save(surf, p3_path)
    print(f"Saved: {p3_path}")

    # 4. AI Info Panel Collapsed (full arena viewport + slim 32-px telemetry bar)
    arena4 = "arena_golden_temple"
    bg4 = assets.get_arena(arena4, size=(FULL_W, FULL_H))
    state4 = make_initial_state("Golden", "Steel")
    state4.frame = 190
    state4.round_frames_left = 3000
    state4.p1_rounds_won = 1
    state4.fighter1.x = 340.0
    state4.fighter2.x = 460.0
    state4.fighter1.health = 0.84
    state4.fighter2.health = 0.71
    state4.fighter1.meter = 45.0
    state4.fighter2.meter = 62.0

    ag_g = GoldenAgent(player=1, difficulty="HIGH", seed=5)
    ag_s = SteelAgent(player=2, difficulty="HIGH", seed=6)
    ob_g = observation_for(state4, 1)
    ob_s = observation_for(state4, 2)
    _, sc_g = ag_g.decide(ob_g)
    _, sc_s = ag_s.decide(ob_s)
    inf_g = _build_info(ag_g, Action.LIGHT_KICK, sc_g, ob_g, player_num=1)
    inf_s = _build_info(ag_s, Action.SHIELD_FRONT, sc_s, ob_s, player_num=2)

    cam4 = CameraState(FULL_W, FULL_H - 32)
    for _ in range(10):
        cam4.update(ARENA_OFFSET_X + state4.fighter1.x, ARENA_OFFSET_X + state4.fighter2.x, get_arena_floor_y(arena4, FULL_H - 32))

    _draw_full_frame(
        surf, state4, bg4, "Golden Temple",
        inf_g, inf_s, font_large, font_medium, font_small, font_tiny,
        "Golden", "Steel", False, ag_g, ag_s,
        0, 0, 2, False, False, 0.88, 0.78, 0, 0, [], [],
        arena_name=arena4, camera=cam4, panel_collapsed=True
    )
    p4_path = os.path.join(ARTIFACT_DIR, "ai_panel_collapsed.png")
    pygame.image.save(surf, p4_path)
    print(f"Saved: {p4_path}")

    # Benchmark 120 frames under full load (particles, sparks, popups, camera zoom, HUD, telemetry)
    t0 = time.perf_counter()
    frames_n = 120
    for f_i in range(frames_n):
        state1.frame = f_i
        _draw_full_frame(
            surf, state1, bg1, "Frozen Peak",
            info1, info2, font_large, font_medium, font_small, font_tiny,
            "Crimson", "Golden", False, agent1, agent2,
            0, 0, 2, False, False, 0.88, 0.68, 3, 0, sparks2, popups2,
            dust_particles=dust2, arena_name=arena1, camera=cam1, panel_collapsed=False
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    avg_ms = elapsed_ms / frames_n
    print(f"Benchmark ({frames_n} full frames): avg = {avg_ms:.2f} ms/frame (budget < 16.0 ms)")
    assert avg_ms < 16.0, f"Frame time {avg_ms:.2f} ms exceeded 16 ms budget!"


def main():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    render_phase1_zone()
    render_phase2_walls()
    render_phase3_loot()
    render_phase4_objects()
    render_full_rumble_hud()
    generate_visual_overhaul_screenshots()
    print("All screenshots generated successfully.")


if __name__ == "__main__":
    main()
