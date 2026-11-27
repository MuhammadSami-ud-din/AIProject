"""Tutorial Room for Arena-AI.

Provides:
- Non-aggressive practice dummy with cyclable modes (Stand, Crouch, Block, Jump-Dash).
- Infinite timer and automatic health refill.
- Dynamic on-screen controls panel bound to active key bindings.
- Guided step-by-step interactive lesson mode with action verification.
- Free Practice mode toggle and live combat telemetry (hit count, combo, damage).
"""

from typing import Optional, Tuple
import pygame

from backend.ai.actions import Action
from backend.ai.base_agent import Agent
from backend.engine.constants import ARENA_WIDTH, ROUND_FRAMES
from backend.engine.moves import get_move
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step
from frontend.assets import assets
from frontend.audio import audio
from frontend.camera_effects import CameraState
from frontend.draw_fighter import draw_fighter
from frontend.hud import draw_hud
from frontend.input_handler import DEFAULT_KEY_BINDINGS, InputHandler, current_bindings, get_human_action  # noqa: F401
from frontend.fantasy_ui import draw_obsidian_card, GOLD_TEXT, GOLD_BRIGHT, PANEL_BORDER_GLOW, TEXT_WHITE, TEXT_MUTED
from frontend.theme import (
    BLACK,
    DARK_GREY,
    FLOOR_HEIGHT,
    GREY,
    HEALTH_GREEN,
    HEALTH_YELLOW,
    LIGHT_GREY,
    MENU_BG,
    MENU_HIGHLIGHT,
    P1_COLOUR,
    P2_COLOUR,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TIMER_COLOUR,
    WHITE,
    get_arena_floor_y,
)


class DummyAgent(Agent):
    """Immortal dummy opponent that cycles between practice stances."""

    MODES = ["STAND", "CROUCH", "BLOCK ALL", "JUMP & DASH"]

    def __init__(self, character_name: str = "Steel"):
        super().__init__(name="Dummy", player=2, difficulty="LOW")
        self.character_name = character_name
        self.mode_index = 0
        self.frame_counter = 0

    def cycle_mode(self) -> str:
        self.mode_index = (self.mode_index + 1) % len(self.MODES)
        return self.current_mode

    @property
    def current_mode(self) -> str:
        return self.MODES[self.mode_index]

    def choose_action(self, state) -> Tuple[Action, dict]:
        self.frame_counter += 1
        mode = self.current_mode
        if mode == "STAND":
            return Action.IDLE, {}
        elif mode == "CROUCH":
            return Action.CROUCH, {}
        elif mode == "BLOCK ALL":
            return Action.BLOCK, {}
        elif mode == "JUMP & DASH":
            cycle = self.frame_counter % 120
            if cycle == 0:
                return Action.JUMP, {}
            elif cycle == 50:
                return Action.DASH, {}
            elif cycle == 80:
                return Action.BACKDASH, {}
            return Action.IDLE, {}
        return Action.IDLE, {}


LESSONS = [
    {
        "id": "move",
        "title": "Movement: Walk Forward and Back",
        "instruction": "Press A / D to advance towards or retreat from the dummy.",
        "target_actions": [Action.FORWARD, Action.BACK],
    },
    {
        "id": "dash",
        "title": "Dash & Backdash",
        "instruction": "Double-tap A or D to dash across the floor.",
        "target_actions": [Action.DASH, Action.BACKDASH],
    },
    {
        "id": "jump",
        "title": "Jump",
        "instruction": "Press W to jump into the air.",
        "target_actions": [Action.JUMP],
    },
    {
        "id": "crouch",
        "title": "Crouch",
        "instruction": "Hold S to crouch low under high attacks.",
        "target_actions": [Action.CROUCH],
    },
    {
        "id": "light_attack",
        "title": "Light Attacks",
        "instruction": "Press J (Light Punch) or U (Light Kick) for rapid strikes.",
        "target_actions": [Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB, Action.CROUCH_KICK],
    },
    {
        "id": "heavy_attack",
        "title": "Heavy Attacks",
        "instruction": "Press K (Heavy Punch) or I (Heavy Kick) for high-impact blows.",
        "target_actions": [Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD],
    },
    {
        "id": "block",
        "title": "Guard Defense",
        "instruction": "Hold L to guard. Deflects incoming attacks.",
        "target_actions": [Action.BLOCK, Action.BLOCK_LOW],
    },
    {
        "id": "special",
        "title": "Special Moves",
        "instruction": "Press O (Special) neutral or with directional inputs (Forward/Back/Down).",
        "target_actions": [Action.SPECIAL_NEUTRAL, Action.SPECIAL_FORWARD, Action.SPECIAL_BACK, Action.SPECIAL_DOWN],
    },
    {
        "id": "super",
        "title": "Super Move",
        "instruction": "Press P to unleash your warrior's Super Attack!",
        "target_actions": [Action.SUPER],
    },
    {
        "id": "throw",
        "title": "Throw Grab",
        "instruction": "Press J + U simultaneously to grab through enemy blocks.",
        "target_actions": [Action.THROW],
    },
    {
        "id": "burst",
        "title": "Defensive Burst",
        "instruction": "Press L + O simultaneously to perform a burst knockback.",
        "target_actions": [Action.BURST],
    },
    {
        "id": "combo",
        "title": "Combo Strings",
        "instruction": "Chain multiple attacks together to land a 3-Hit combo!",
        "target_actions": [],  # Verified via combo_hits >= 3
    },
]


def _format_key(k) -> str:
    if not isinstance(k, int):  # a binding may hold several keys; show the first
        k = list(k)[0] if k else 0
    name = pygame.key.name(k).upper()
    return name if name else str(k)


def run_tutorial(
    surface: pygame.Surface,
    clock: pygame.time.Clock,
    warrior_name: str = "Golden",
) -> None:
    """Run interactive Tutorial Room."""
    audio.play_music("music_fight")
    font_large = pygame.font.Font(None, 34)
    font_medium = pygame.font.Font(None, 28)
    font_med = pygame.font.Font(None, 24)
    font_small = pygame.font.Font(None, 18)

    arena_name = "arena_moonlit_bamboo"
    arena_bg = assets.get_arena(arena_name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))
    floor_y = get_arena_floor_y(arena_name, SCREEN_HEIGHT)
    ARENA_OFFSET_X = (SCREEN_WIDTH - ARENA_WIDTH) // 2

    dummy_char = "Steel" if warrior_name != "Steel" else "Golden"
    dummy_agent = DummyAgent(dummy_char)

    state = make_initial_state(warrior_name, dummy_char)
    state.fighter1.meter = 100.0  # Full meter for practice
    camera = CameraState(SCREEN_WIDTH, SCREEN_HEIGHT)

    current_lesson_idx = 0
    free_practice_mode = False
    lesson_success_timer = 0
    stats_damage_last_hit = 0.0
    last_p2_health = 1.0

    while True:
        clock.tick(60)

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                audio.stop_music()
                return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Exit tutorial
                    audio.play_sfx("menu_back")
                    audio.stop_music()
                    return
                elif event.key == pygame.K_TAB:
                    # Cycle dummy mode
                    new_mode = dummy_agent.cycle_mode()
                    audio.play_sfx("menu_select")
                elif event.key == pygame.K_F1:
                    # Toggle Free Practice mode
                    free_practice_mode = not free_practice_mode
                    audio.play_sfx("menu_select")

        # Human action and Dummy action
        can_act1 = (
            (
                state.fighter1.current_action == Action.IDLE
                or not state.fighter1.busy
                and not state.fighter1.is_knocked_down
            )
            or state.fighter1.cancel_available
        )
        action1 = get_human_action(
            state.fighter2.x,
            state.fighter1.x,
            in_air=state.fighter1.in_air,
            can_act=can_act1,
            enable_shield_wall=False,
        )
        action2, _ = dummy_agent.choose_action(state)

        # Step engine
        state = step(state, action1, action2)

        # Infinite Practice: Refill health automatically if low, and keep meter up
        if state.fighter1.health <= 0.20 or state.fighter2.health <= 0.20:
            state.fighter1.health = 1.0
            state.fighter2.health = 1.0
            state.fighter1.meter = 100.0
            state.fighter2.meter = 100.0
            state.fighter2.is_knocked_down = False
            state.fighter2.knockdown_frames = 0
            state.fighter1.is_knocked_down = False
            state.fighter1.knockdown_frames = 0

        # Keep round timer pegged so it never expires
        state.round_frames_left = ROUND_FRAMES
        state.round_over = False
        state.match_over = False

        # Measure damage per hit
        if state.fighter2.health < last_p2_health:
            stats_damage_last_hit = (last_p2_health - state.fighter2.health) * 100.0
        last_p2_health = state.fighter2.health

        # Lesson verification
        if not free_practice_mode and current_lesson_idx < len(LESSONS):
            lesson = LESSONS[current_lesson_idx]
            passed = False
            if lesson["id"] == "combo":
                if state.fighter1.combo_hits >= 3:
                    passed = True
            elif action1 in lesson["target_actions"] or state.fighter1.current_action in lesson["target_actions"]:
                passed = True

            if passed and lesson_success_timer == 0:
                lesson_success_timer = 45  # frames to display success before advancing
                audio.play_sfx("mission_complete")

        if lesson_success_timer > 0:
            lesson_success_timer -= 1
            if lesson_success_timer == 0:
                current_lesson_idx += 1
                if current_lesson_idx >= len(LESSONS):
                    free_practice_mode = True

        # Render Fight Scene
        viewport = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        camera.update(ARENA_OFFSET_X + state.fighter1.x, ARENA_OFFSET_X + state.fighter2.x, floor_y)

        viewport.blit(arena_bg, (0, 0))

        # Render projectiles
        for p in state.projectiles:
            px = ARENA_OFFSET_X + int(p.x)
            py = floor_y - int(p.y) - 10
            col = (255, 200, 50) if p.owner == 1 else (255, 80, 80)
            pygame.draw.circle(viewport, col, (px, py), 12)
            pygame.draw.circle(viewport, (255, 255, 255), (px, py), 7)

        # Render fighters
        facing1 = (state.fighter1.x < state.fighter2.x)
        facing2 = (state.fighter2.x < state.fighter1.x)
        draw_fighter(
            viewport, state.fighter1, facing1,
            arena_offset_x=ARENA_OFFSET_X, ground_y=floor_y,
            player_num=1, is_mirror=False, is_human=True
        )
        draw_fighter(
            viewport, state.fighter2, facing2,
            arena_offset_x=ARENA_OFFSET_X, ground_y=floor_y,
            player_num=2, is_mirror=(dummy_char == warrior_name), is_human=False
        )

        camera.present(viewport, surface, (0, 0))

        # Standard HUD
        draw_hud(
            surface, state, font_medium, font_small,
            hit_flash=0, trail1=state.fighter1.health, trail2=state.fighter2.health,
            combo1=state.fighter1.combo_hits, combo2=state.fighter2.combo_hits,
            diff1=None, diff2=None, sparks=None
        )

        # --------------------------------------------------------------
        # Overlay Panel 1: Guided Lesson / Free Practice Card
        # --------------------------------------------------------------
        card_w, card_h = 440, 110
        card_rect = pygame.Rect(20, 115, card_w, card_h)
        draw_obsidian_card(surface, card_rect, is_selected=(lesson_success_timer > 0), border_radius=8)

        if free_practice_mode:
            t_lbl = font_med.render("FREE PRACTICE MODE", True, (255, 215, 80))
            sub_lbl = font_small.render("Practice all moves and combos freely against the dummy.", True, WHITE)
            mode_lbl = font_small.render("[TAB] Cycle Dummy Stance   |   [F1] Lessons", True, (160, 200, 255))
            surface.blit(t_lbl, (card_rect.x + 15, card_rect.y + 12))
            surface.blit(sub_lbl, (card_rect.x + 15, card_rect.y + 44))
            surface.blit(mode_lbl, (card_rect.x + 15, card_rect.y + 75))
        else:
            cur_l = LESSONS[min(current_lesson_idx, len(LESSONS) - 1)]
            l_num_text = f"LESSON {current_lesson_idx + 1}/{len(LESSONS)}: {cur_l['title']}"
            t_lbl = font_med.render(l_num_text, True, (255, 215, 80) if lesson_success_timer == 0 else (100, 255, 120))
            inst_lbl = font_small.render(cur_l["instruction"], True, WHITE)
            status_text = "PASSED! NICE WORK!" if lesson_success_timer > 0 else "[TAB] Dummy Mode   |   [F1] Free Practice"
            st_lbl = font_small.render(status_text, True, (120, 255, 140) if lesson_success_timer > 0 else LIGHT_GREY)

            surface.blit(t_lbl, (card_rect.x + 15, card_rect.y + 12))
            surface.blit(inst_lbl, (card_rect.x + 15, card_rect.y + 44))
            surface.blit(st_lbl, (card_rect.x + 15, card_rect.y + 75))

        # --------------------------------------------------------------
        # Overlay Panel 2: Live Combat Telemetry Card
        # --------------------------------------------------------------
        telem_rect = pygame.Rect(20, 235, 260, 100)
        draw_obsidian_card(surface, telem_rect, is_selected=False, border_radius=8)

        act_text = f"Input: {action1.name}"
        combo_text = f"Combo: {state.fighter1.combo_hits} Hits"
        dmg_text = f"Damage (Hit): {stats_damage_last_hit:.1f} HP"
        dummy_text = f"Dummy: {dummy_agent.current_mode}"

        surface.blit(font_small.render(act_text, True, (160, 220, 255)), (telem_rect.x + 12, telem_rect.y + 10))
        surface.blit(font_small.render(combo_text, True, (255, 215, 80)), (telem_rect.x + 12, telem_rect.y + 32))
        surface.blit(font_small.render(dmg_text, True, (255, 140, 140)), (telem_rect.x + 12, telem_rect.y + 54))
        surface.blit(font_small.render(dummy_text, True, (120, 255, 140)), (telem_rect.x + 12, telem_rect.y + 76))

        # --------------------------------------------------------------
        # Overlay Panel 3: Key Controls Reference Panel (Top Right)
        # --------------------------------------------------------------
        b = current_bindings()
        ctrl_rect = pygame.Rect(SCREEN_WIDTH - 280, 115, 260, 220)
        draw_obsidian_card(surface, ctrl_rect, is_selected=False, border_radius=8)

        surface.blit(font_small.render("COMMAND CONTROLS", True, (255, 215, 80)), (ctrl_rect.x + 12, ctrl_rect.y + 8))

        controls_list = [
            f"Walk / Dash: {_format_key(b['left'])} / {_format_key(b['right'])}",
            f"Jump / Crouch: {_format_key(b['jump'])} / {_format_key(b['crouch'])}",
            f"Punches: {_format_key(b['light_punch'])} (L) / {_format_key(b['heavy_punch'])} (H)",
            f"Kicks: {_format_key(b['light_kick'])} (L) / {_format_key(b['heavy_kick'])} (H)",
            f"Guard / Block: {_format_key(b['block'])}",
            f"Special / Super: {_format_key(b['special'])} / {_format_key(b['super'])}",
            f"Throw: {_format_key(b['light_punch'])}+{_format_key(b['light_kick'])}",
            f"Burst: {_format_key(b['block'])}+{_format_key(b['special'])}",
        ]

        y_c = ctrl_rect.y + 32
        for line in controls_list:
            surface.blit(font_small.render(line, True, WHITE), (ctrl_rect.x + 12, y_c))
            y_c += 22

        # Exit instruction at bottom
        esc_lbl = font_small.render("Press ESC to exit Tutorial Room", True, (180, 180, 200))
        surface.blit(esc_lbl, (SCREEN_WIDTH // 2 - esc_lbl.get_width() // 2, SCREEN_HEIGHT - 25))

        pygame.display.flip()
