"""Menu screens: intro, main menu, quick fight, match setup, results, settings.

Each screen is a function that takes the pygame display surface and a clock
and returns the player's choice (or None to go back). All screens share the
"obsidian & molten gold" look from frontend.fantasy_ui and cached fonts from
frontend.fonts.
"""

import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from backend.ai.personalities import ALL_PERSONALITIES
from backend.ai.random_agent import RandomAgent  # noqa: F401  (re-exported for old imports)
from backend.engine.characters import CHARACTER_STATS
from frontend import fonts
from frontend.assets import NORMAL_ARENAS, SPECIAL_ARENA, assets
from frontend.colours import (
    BLACK,  # noqa: F401
    DARK_GREY,
    FIGHTER_COLOURS,  # noqa: F401
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_SMALL,
    LIGHT_GREY,
    MENU_BG,  # noqa: F401
    MENU_HIGHLIGHT,
    WHITE,
)
from frontend.theme import (
    ALTERNATE_PALETTES,
    P1_COLOUR,
    P2_COLOUR,
    PRIMARY_PALETTES,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    get_fighter_palette,  # noqa: F401
)
from backend.data.results_db import results_db
from frontend.audio import audio
from frontend import input_handler as controls
from frontend.fantasy_ui import (
    BG_DARK,  # noqa: F401
    BRONZE_TAG,  # noqa: F401
    CENTER_X,
    CRIMSON_TAG,  # noqa: F401
    DESC_Y,
    EMBER_ORANGE,  # noqa: F401
    FOOTER_Y,
    GOLD_BRIGHT,
    GOLD_TEXT,
    HEADER_H,
    MENU_HINTS,
    P1_ACCENT,
    P2_ACCENT,
    PANEL_BORDER,
    PANEL_BORDER_GLOW,
    PANEL_BORDER_LIGHT,  # noqa: F401
    PANEL_DARK,
    PANEL_DARK_ALT,  # noqa: F401
    SILVER_TAG,  # noqa: F401
    SUCCESS_GREEN,
    TEXT_GOLD_MUTED,
    TEXT_MUTED,
    TEXT_WHITE,
    MenuItem,
    OptionRow,
    confirm_dialog,
    draw_backdrop,
    draw_button,
    draw_dark_fantasy_backdrop,  # noqa: F401
    draw_dark_fantasy_menu_buttons,  # noqa: F401
    draw_description_pill,
    draw_emblem_icon,
    draw_header,
    draw_hint_bar,
    draw_menu_cards,
    draw_obsidian_card,
    draw_option_rows,
    draw_segmented_bar,  # noqa: F401
    draw_text,
    draw_tier_badge,  # noqa: F401
    draw_wax_seal_stamp,  # noqa: F401
    get_font,
    invalidate_economy_cache,
    render_title,
    run_menu,
    safe_set_cursor,
)

FIGHTERS = list(ALL_PERSONALITIES.keys())
DIFFICULTIES = ["LOW", "MEDIUM", "HIGH", "HELL"]
ARENA_CHOICES = ["random"] + list(NORMAL_ARENAS) + [SPECIAL_ARENA]

_safe_set_cursor = safe_set_cursor


def _flip() -> None:
    if pygame.display.get_surface() is not None:
        pygame.display.flip()


def _arena_label(name: str) -> str:
    if not name or name == "random":
        return "Random Arena"
    return (str(name).replace("arena_", "").replace(".jpeg", "").replace(".jpg", "")
            .replace(".png", "").replace("_", " ").title())


def _wait_for_key_or_click():
    """Block until the user presses a key or clicks the mouse."""
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return


def _draw_title(surface, text, font=None, y=50):
    """Centred gradient-gold title (font argument kept for old callers)."""
    t = render_title(str(text).upper(), 40)
    surface.blit(t, t.get_rect(midtop=(SCREEN_WIDTH // 2, y)))


def _screen_bg(surface, title: Optional[str] = None, frame: int = 0,
               sub_title: Optional[str] = None, dim: int = 165, compact: bool = False) -> int:
    """Standard menu background + header used by every screen in this module.

    compact=True uses a smaller title for data-heavy screens (stats, manual, insights).
    """
    return draw_backdrop(surface, frame, title=title, sub_title=sub_title, bg="menu", dim=dim,
                         title_size=32 if compact else 46, header_y=8 if compact else 18)


def _draw_menu_items(surface, items, selected, font=None, start_y=180, step_y=50):
    """Legacy helper: draw a centred list of cards."""
    return draw_menu_cards(surface, items, selected, top=start_y, height=min(44, step_y - 8),
                           gap=max(4, step_y - min(44, step_y - 8)))


def _draw_menu_items_clickable(surface, items, selected, font=None, start_y=180, step_y=50,
                               inflate_x=50, inflate_y=10, btn_w=None, btn_h=None):
    """Legacy helper kept for compatibility; returns the card hit-rects."""
    return _draw_menu_items(surface, items, selected, font, start_y, step_y)


def _cross_fade(surface, clock, from_surf, to_surf, duration_s=0.5):
    """Smooth cross-fade between two full-screen surfaces."""
    frames = max(1, int(30 * duration_s))
    blend_surf = to_surf.copy()
    for f in range(frames + 1):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
        surface.blit(from_surf, (0, 0))
        blend_surf.set_alpha(int(255 * f / frames))
        surface.blit(blend_surf, (0, 0))
        _flip()
        clock.tick(30)


# ----------------------------------------------------------------------
# Intro & main menus
# ----------------------------------------------------------------------
def intro_screen(surface, clock):
    """Intro art with a pulsing 'PRESS ANY KEY'; cross-fades into the menu backdrop."""
    intro_img = assets.get_intro((SCREEN_WIDTH, SCREEN_HEIGHT))
    blur_img = assets.get_intro_blur((SCREEN_WIDTH, SCREEN_HEIGHT))
    prompt = fonts.font("ui", 20).render("PRESS ANY KEY TO START", True, WHITE)
    prompt_alpha = pygame.Surface(prompt.get_size(), pygame.SRCALPHA)
    prompt_alpha.blit(prompt, (0, 0))
    start_time = time.time()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.JOYBUTTONDOWN):
                _cross_fade(surface, clock, intro_img, blur_img, duration_s=0.5)
                return
        surface.blit(intro_img, (0, 0))
        alpha = int(150 + 105 * math.sin((time.time() - start_time) * 3.5))
        prompt_alpha.set_alpha(max(0, min(255, alpha)))
        surface.blit(prompt_alpha, prompt_alpha.get_rect(center=(CENTER_X, int(SCREEN_HEIGHT * 0.91))))
        _flip()
        clock.tick(30)


MAIN_MENU_ITEMS = [
    MenuItem("quick", "Quick Fight", "Pick both fighters, difficulty and arena on one screen and fight", "quick"),
    MenuItem("campaign", "Campaign", "The 8-battle Sovereign Tournament with story and scaling bosses", "campaign"),
    MenuItem("start", "Versus & Modes", "Me vs AI, Random AI, Local Versus (2 players), Arena Rumble, AI vs AI", "versus"),
    MenuItem("tutorial", "Tutorial Room", "Practice movement, attacks, defence, combos and specials on a dummy", "tutorial"),
    MenuItem("hq", "Fighter HQ", "Upgrades, missions, trophies and your combat statistics", "hq"),
    MenuItem("options", "Settings & Info", "Audio, controls and key bindings, the combat manual and AI insights", "settings"),
    MenuItem("quit", "Quit", "Exit Arena-AI to the desktop", "quit"),
]


def main_menu(surface, clock, player_id: Optional[int] = None):
    """Main menu. Returns a key from MAIN_MENU_ITEMS ('quick', 'campaign', 'start',
    'tutorial', 'hq', 'options' or 'quit'). Esc asks for quit confirmation."""

    def on_escape():
        if confirm_dialog(surface, clock, "Quit Arena-AI?", "Leave the arena and return to the desktop?",
                          confirm_label="Quit", cancel_label="Stay", danger=True):
            return "quit"
        return None

    return run_menu(surface, clock, "ARENA-AI", MAIN_MENU_ITEMS, subtitle="AI FIGHTING ARENA",
                    on_escape=on_escape, quit_value="quit", player_id=player_id, show_economy=True,
                    hints=[("↑ ↓", "Select"), ("Enter", "Confirm"), ("Esc", "Quit")], width=420,
                    card_h=44, gap=9)


FIGHTER_HQ_ITEMS = [
    MenuItem("upgrades", "Warrior Upgrades", "Spend gold to boost Health, Attack, Speed and Guard of any fighter", "upgrades"),
    MenuItem("missions", "Missions & Contracts", "Claim gold rewards for battle feats and combat milestones", "chain"),
    MenuItem("trophies", "Trophy Showcase", "18 unlockable trophies, accolades and campaign badges", "trophies"),
    MenuItem("statistics", "Combat Statistics", "Match history, win/loss records and AI model results", "statistics"),
    MenuItem("back", "Back", "Return to the main menu", "back"),
]


def fighter_hq_menu(surface, clock, player_id: Optional[int] = None):
    """Fighter HQ hub. Returns 'upgrades', 'missions', 'trophies', 'statistics' or 'back'."""
    return run_menu(surface, clock, "FIGHTER HQ", FIGHTER_HQ_ITEMS, esc_value="back",
                    player_id=player_id, show_economy=True)


OPTIONS_ITEMS = [
    MenuItem("settings", "Game & Audio Settings", "Volume, game speed, Shield Wall balance and data tools", "settings"),
    MenuItem("controls", "Controls & Key Bindings", "Rebind keyboard keys for Player 1 and Player 2; gamepad layout", "controls"),
    MenuItem("manual", "Move List & Manual", "Special moves, controls, frame data and combat mechanics", "manual"),
    MenuItem("insights", "AI Model Insights", "Inspect trained AI models, decisions and training telemetry", "insights"),
    MenuItem("back", "Back", "Return to the main menu", "back"),
]


def options_info_menu(surface, clock):
    """Settings & Info hub. Returns 'settings', 'controls', 'manual', 'insights' or 'back'."""
    return run_menu(surface, clock, "SETTINGS & INFO", OPTIONS_ITEMS, esc_value="back")


MATCH_TYPE_ITEMS = [
    MenuItem("me_vs_ai", "Me vs AI", "Pick your fighter and an AI opponent for a 1v1 duel", "swords"),
    MenuItem("random_ai", "Random AI", "Pick your fighter and face a randomly chosen AI opponent", "crystal"),
    MenuItem("local_versus", "Local Versus (2 Players)", "Two humans, one keyboard (P1: WASD + JKL, P2: arrows + numpad) or gamepads", "versus"),
    MenuItem("rumble", "Arena Rumble", "Battle royale rules: shrinking zone, cover building, traps and loot", "rumble"),
    MenuItem("ai_vs_ai", "AI vs AI", "Watch two AI fighters battle it out (Quick Fight AI vs AI adds the telemetry dashboard)", "insights"),
]


def match_type_select(surface, clock):
    """Returns 'me_vs_ai', 'random_ai', 'local_versus', 'rumble', 'ai_vs_ai', or None."""
    return run_menu(surface, clock, "SELECT MATCH FORMAT", MATCH_TYPE_ITEMS, esc_value=None)


DIFFICULTY_DESCS = {
    "LOW": "Slow reactions (24f delay), 30% mistakes, basic 1-ply search",
    "MEDIUM": "Moderate reactions (15f delay), 15% mistakes, 2-ply search",
    "HIGH": "Fast reactions (7f delay), 5% mistakes, 3-ply search",
    "HELL": "Instant reactions, 1% mistakes, Expectimax + opponent model on the Sky Colosseum",
}
DIFFICULTY_ITEMS = [
    MenuItem("LOW", "Low", DIFFICULTY_DESCS["LOW"], "shield"),
    MenuItem("MEDIUM", "Medium", DIFFICULTY_DESCS["MEDIUM"], "swords"),
    MenuItem("HIGH", "High", DIFFICULTY_DESCS["HIGH"], "flame"),
    MenuItem("HELL", "Hell", DIFFICULTY_DESCS["HELL"], "skull"),
]


def difficulty_select(surface, clock):
    """Returns 'LOW', 'MEDIUM', 'HIGH', 'HELL', or None if cancelled."""
    return run_menu(surface, clock, "SELECT AI DIFFICULTY", DIFFICULTY_ITEMS, esc_value=None)


def mode_select(surface, clock):
    """Backwards-compatible helper: pick match type then difficulty."""
    m_type = match_type_select(surface, clock)
    if m_type is None:
        return None, None
    diff = difficulty_select(surface, clock)
    if diff is None:
        return None, None
    return m_type, diff


# ----------------------------------------------------------------------
# Fighter cards (character select + quick fight)
# ----------------------------------------------------------------------
def _fighter_stat_bars(name: str) -> List[Tuple[str, float]]:
    st = CHARACTER_STATS.get(name)
    if st is None:
        return []

    def norm(v):
        return max(0.05, min(1.0, (v - 0.7) / 0.6))

    return [
        ("POWER", norm(st.damage_mult)),
        ("REACH", norm(st.reach_mult)),
        ("SPEED", norm(st.speed_mult)),
        ("GUARD", max(0.05, min(1.0, 1.0 - st.blocked_damage_ratio * 4))),
    ]


def _draw_stat_bars(surface, name: str, x: int, y: int, width: int, accent) -> None:
    for i, (label, frac) in enumerate(_fighter_stat_bars(name)):
        yy = y + i * 18
        draw_text(surface, label, 11, TEXT_MUTED, role="ui", midleft=(x, yy + 4))
        bar = pygame.Rect(x + 52, yy, width - 52, 8)
        pygame.draw.rect(surface, (36, 39, 56), bar, border_radius=4)
        pygame.draw.rect(surface, accent, (bar.x, bar.y, max(4, int(bar.width * frac)), bar.height),
                         border_radius=4)


def _draw_portrait_card(surface, rect: pygame.Rect, name: str, *, selected: bool, flip: bool,
                        accent=GOLD_TEXT, tag: Optional[str] = None, portrait_frac: float = 0.70) -> None:
    """Fighter portrait card used by character select and quick fight."""
    draw_obsidian_card(surface, rect, is_selected=selected, border_radius=12)
    pad = 8
    p_rect = pygame.Rect(rect.x + pad, rect.y + pad, rect.width - 2 * pad, int(rect.height * portrait_frac))
    if name in ALL_PERSONALITIES:
        surface.blit(assets.get_portrait(name, size=p_rect.size, flip_h=flip), p_rect)
    else:
        pygame.draw.rect(surface, (26, 28, 42), p_rect, border_radius=8)
        q = render_title("?", int(p_rect.height * 0.5))
        surface.blit(q, q.get_rect(center=p_rect.center))
    # Gradient fade at the bottom of the portrait for the name plate
    fade = _portrait_fade(p_rect.width, 40)
    surface.blit(fade, (p_rect.x, p_rect.bottom - 40))
    pygame.draw.rect(surface, accent if selected else (60, 64, 84), p_rect, 1, border_radius=8)
    title = PRIMARY_PALETTES.get(name, {}).get("title", "Mystery Fighter" if name == "Random" else name)
    draw_text(surface, name.upper(), 20, GOLD_BRIGHT if selected else TEXT_WHITE, role="display",
              midtop=(rect.centerx, p_rect.bottom + 6))
    draw_text(surface, title, 12, TEXT_MUTED, role="ui", midtop=(rect.centerx, p_rect.bottom + 30),
              max_width=rect.width - 12)
    if tag:
        t = fonts.font("ui", 12).render(tag, True, WHITE)
        chip = t.get_rect(topleft=(rect.x + 14, rect.y + 14)).inflate(12, 6)
        pygame.draw.rect(surface, accent, chip, border_radius=chip.height // 2)
        surface.blit(t, t.get_rect(center=chip.center))


_FADE_CACHE: Dict[Tuple[int, int], pygame.Surface] = {}


def _portrait_fade(w: int, h: int) -> pygame.Surface:
    key = (w, h)
    if key not in _FADE_CACHE:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            pygame.draw.line(s, (12, 13, 22, int(200 * y / h)), (0, y), (w, y))
        _FADE_CACHE[key] = s
    return _FADE_CACHE[key]


def character_select(surface, clock, is_p2=False, initial: Optional[str] = None,
                     title: Optional[str] = None):
    """Pick a fighter. Returns the fighter name, 'Random', or None when cancelled."""
    fighters = FIGHTERS + ["Random"]
    selected = fighters.index(initial) if initial in fighters else 0
    n = len(fighters)
    gap = 14
    card_w = min(170, (SCREEN_WIDTH - 80 - (n - 1) * gap) // n)
    card_h = int(SCREEN_HEIGHT * 0.50)
    start_x = CENTER_X - (n * card_w + (n - 1) * gap) // 2
    top = HEADER_H + 22
    rects = [pygame.Rect(start_x + i * (card_w + gap), top, card_w, card_h) for i in range(n)]
    accent = P2_ACCENT if is_p2 else P1_ACCENT
    heading = title or ("CHOOSE PLAYER 2" if is_p2 else "CHOOSE YOUR FIGHTER")
    frame = 0
    last_mouse = pygame.mouse.get_pos()
    while True:
        frame += 1
        mouse_pos = pygame.mouse.get_pos()
        if mouse_pos != last_mouse:
            last_mouse = mouse_pos
            for i, r in enumerate(rects):
                if r.collidepoint(mouse_pos) and i != selected:
                    selected = i
                    audio.play_sfx("menu_hover")
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    audio.play_sfx("menu_hover")
                    selected = (selected - 1) % n
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    audio.play_sfx("menu_hover")
                    selected = (selected + 1) % n
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    audio.play_sfx("menu_select")
                    return fighters[selected]
                elif event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(event.pos):
                        audio.play_sfx("menu_select")
                        return fighters[i]

        _screen_bg(surface, heading, frame)
        for i, name in enumerate(fighters):
            _draw_portrait_card(surface, rects[i], name, selected=(i == selected), flip=is_p2,
                                accent=accent)
        sel = fighters[selected]
        info_y = top + card_h + 16
        if sel in ALL_PERSONALITIES:
            _draw_stat_bars(surface, sel, CENTER_X - 160, info_y, 320, accent)
            desc = f"{ALL_PERSONALITIES[sel].full_name}: {ALL_PERSONALITIES[sel].description}"
        else:
            desc = "Mystery fighter: one of the four warriors is picked at random."
        draw_description_pill(surface, desc)
        draw_hint_bar(surface, [("← →", "Choose"), ("Enter", "Confirm"), ("Esc", "Back")])
        _flip()
        clock.tick(30)


# ----------------------------------------------------------------------
# Quick Fight (one screen: P1, P2, mode, difficulty, arena)
# ----------------------------------------------------------------------
QUICK_MODES = [
    ("me_vs_ai", "You vs AI"),
    ("local_versus", "Local Versus"),
    ("ai_vs_ai", "AI vs AI"),
]


@dataclass
class QuickFightChoice:
    """Result of quick_fight_screen (also usable as a dict via as_dict())."""
    mode: str
    p1_char: str
    p2_char: str
    difficulty: str
    arena: Optional[str] = None  # None = random

    def as_dict(self) -> dict:
        return {"match_type": self.mode, "p1_char": self.p1_char, "p2_char": self.p2_char,
                "difficulty": self.difficulty, "arena": self.arena}


def quick_fight_screen(surface, clock, initial: Optional[dict] = None) -> Optional[QuickFightChoice]:
    """Single-screen match setup. Returns a QuickFightChoice, or None on Esc."""
    initial = initial or {}
    fighters = FIGHTERS + ["Random"]
    state = {
        "p1": fighters.index(initial.get("p1_char")) if initial.get("p1_char") in fighters else 0,
        "p2": fighters.index(initial.get("p2_char")) if initial.get("p2_char") in fighters else 1,
        "mode": next((i for i, (k, _) in enumerate(QUICK_MODES) if k == initial.get("match_type")), 0),
        "diff": DIFFICULTIES.index(initial.get("difficulty")) if initial.get("difficulty") in DIFFICULTIES else 1,
        "arena": ARENA_CHOICES.index(initial.get("arena")) if initial.get("arena") in ARENA_CHOICES else 0,
    }
    focus_order = ["p1", "mode", "diff", "arena", "fight", "p2"]
    focus = 4  # FIGHT button

    panel_w = int(SCREEN_WIDTH * 0.26)
    panel_h = int(SCREEN_HEIGHT * 0.66)
    top = HEADER_H + 12
    p1_rect = pygame.Rect(36, top, panel_w, panel_h)
    p2_rect = pygame.Rect(SCREEN_WIDTH - 36 - panel_w, top, panel_w, panel_h)
    mid_w = p2_rect.left - p1_rect.right - 40
    mid_x = p1_rect.right + 20
    row_h, row_gap = 50, 12
    rows_top = top + 150
    row_rects = {k: pygame.Rect(mid_x, rows_top + i * (row_h + row_gap), mid_w, row_h)
                 for i, k in enumerate(("mode", "diff", "arena"))}
    fight_rect = pygame.Rect(0, 0, 220, 52)
    fight_rect.midtop = (CENTER_X, rows_top + 3 * (row_h + row_gap) + 10)
    preview_rect = pygame.Rect(mid_x, top, mid_w, 136)
    frame = 0

    def change(key: str, delta: int) -> None:
        sizes = {"p1": len(fighters), "p2": len(fighters), "mode": len(QUICK_MODES),
                 "diff": len(DIFFICULTIES), "arena": len(ARENA_CHOICES)}
        if key in sizes:
            state[key] = (state[key] + delta) % sizes[key]
            audio.play_sfx("menu_hover")

    def result() -> QuickFightChoice:
        arena = ARENA_CHOICES[state["arena"]]
        return QuickFightChoice(QUICK_MODES[state["mode"]][0], fighters[state["p1"]],
                                fighters[state["p2"]], DIFFICULTIES[state["diff"]],
                                None if arena == "random" else arena)

    def hit_key(pos) -> Optional[str]:
        if p1_rect.collidepoint(pos):
            return "p1"
        if p2_rect.collidepoint(pos):
            return "p2"
        for k, r in row_rects.items():
            if r.collidepoint(pos):
                return k
        if fight_rect.collidepoint(pos):
            return "fight"
        return None

    while True:
        frame += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                key = focus_order[focus]
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return None
                if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER, pygame.K_f):
                    audio.play_sfx("menu_select")
                    return result()
                if event.key in (pygame.K_UP, pygame.K_w):
                    focus = (focus - 1) % len(focus_order)
                    audio.play_sfx("menu_hover")
                elif event.key in (pygame.K_DOWN, pygame.K_s, pygame.K_TAB):
                    focus = (focus + 1) % len(focus_order)
                    audio.play_sfx("menu_hover")
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    change(key, -1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    change(key, 1)
            if event.type == pygame.MOUSEMOTION:
                k = hit_key(event.pos)
                if k is not None:
                    focus = focus_order.index(k)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                k = hit_key(event.pos)
                if k == "fight":
                    audio.play_sfx("menu_select")
                    return result()
                if k is not None:
                    rect = {"p1": p1_rect, "p2": p2_rect}.get(k) or row_rects[k]
                    change(k, -1 if (event.button == 3 or event.pos[0] < rect.centerx - rect.width // 4) else 1)
            if event.type == pygame.MOUSEWHEEL:
                k = hit_key(pygame.mouse.get_pos())
                if k:
                    change(k, -1 if event.y > 0 else 1)

        _screen_bg(surface, "QUICK FIGHT", frame)
        cur = focus_order[focus]
        mode_key = QUICK_MODES[state["mode"]][0]
        p1_tag = "AI" if mode_key == "ai_vs_ai" else "P1"
        p2_tag = "P2" if mode_key == "local_versus" else "AI"
        for key, rect, flip, accent, tag in (("p1", p1_rect, False, P1_ACCENT, p1_tag),
                                             ("p2", p2_rect, True, P2_ACCENT, p2_tag)):
            name = fighters[state[key]]
            _draw_portrait_card(surface, rect, name, selected=(cur == key), flip=flip,
                                accent=accent, tag=tag, portrait_frac=0.62)
            _draw_stat_bars(surface, name, rect.x + 18, rect.bottom - 78, rect.width - 36, accent)
            ay = rect.y + int(rect.height * 0.36)
            col = GOLD_TEXT if cur == key else (150, 150, 165)
            for side in (-1, 1):
                ax = rect.x + 2 if side < 0 else rect.right - 2
                pts = [(ax + side * -12, ay - 12), (ax + side * 2, ay), (ax + side * -12, ay + 12)] if side > 0 \
                    else [(ax + 12, ay - 12), (ax - 2, ay), (ax + 12, ay + 12)]
                pygame.draw.polygon(surface, col, pts)

        # Arena preview + VS
        arena_name = ARENA_CHOICES[state["arena"]]
        preview_name = arena_name if arena_name != "random" else "arena_neon_rooftop"
        draw_obsidian_card(surface, preview_rect, is_selected=(cur == "arena"), border_radius=12)
        inner = preview_rect.inflate(-10, -10)
        thumb = _arena_thumb(preview_name, inner.size, dim=arena_name == "random")
        surface.blit(thumb, inner.topleft)
        vs = render_title("VS", 58)
        surface.blit(vs, vs.get_rect(center=inner.center))
        if arena_name == "random":
            draw_text(surface, "RANDOM ARENA", 13, TEXT_WHITE, role="ui",
                      center=(inner.centerx, inner.bottom - 14))

        rows = [
            OptionRow("mode", "Mode", "choice", QUICK_MODES[state["mode"]][1]),
            OptionRow("diff", "AI Difficulty", "choice", DIFFICULTIES[state["diff"]].title()
                      if mode_key != "local_versus" else "n/a"),
            OptionRow("arena", "Arena", "choice", _arena_label(arena_name)),
        ]
        sel_idx = {"mode": 0, "diff": 1, "arena": 2}.get(cur, -1)
        draw_option_rows(surface, rows, sel_idx, top=rows_top, width=mid_w, row_h=row_h, gap=row_gap,
                         center_x=mid_x + mid_w // 2)
        draw_button(surface, fight_rect, "FIGHT!", selected=(cur == "fight"), primary=True, size=22)

        p1_name, p2_name = fighters[state["p1"]], fighters[state["p2"]]
        draw_description_pill(surface, {
            "me_vs_ai": f"You play {p1_name} against an AI {p2_name}.",
            "local_versus": "P1: WASD move · J K U I attack · L block   |   P2: arrows · numpad 4 5 1 2 · 6 block",
            "ai_vs_ai": f"Watch {p1_name} and {p2_name} AIs fight with live decision telemetry.",
        }[mode_key])
        draw_hint_bar(surface, [("↑ ↓", "Field"), ("← →", "Change"), ("Enter", "Fight"), ("Esc", "Back")])
        _flip()
        clock.tick(30)


def _arena_thumb(name: str, size: Tuple[int, int], dim: bool = False) -> pygame.Surface:
    key = ("thumb", name, size, dim)
    cache = _FADE_CACHE
    if key not in cache:
        art = assets.get_arena(name, size=(SCREEN_WIDTH, SCREEN_HEIGHT))
        w, h = size
        src_h = int(SCREEN_WIDTH * h / w)
        src = art.subsurface(pygame.Rect(0, max(0, (SCREEN_HEIGHT - src_h) // 2), SCREEN_WIDTH,
                                         min(SCREEN_HEIGHT, src_h)))
        thumb = pygame.transform.smoothscale(src, size)
        shade = pygame.Surface(size, pygame.SRCALPHA)
        shade.fill((8, 9, 16, 150 if dim else 70))
        thumb.blit(shade, (0, 0))
        cache[key] = thumb
    return cache[key]


# ----------------------------------------------------------------------
# Pause & move list (shown over the frozen fight frame)
# ----------------------------------------------------------------------
def pause_screen(surface, clock):
    """Pause overlay. Returns 'resume', 'restart', or 'quit'."""
    items = ["Resume", "Move List", "Restart Match", "Quit to Menu"]
    keys = ["resume", "movelist", "restart", "quit"]
    selected = 0
    base_frame = surface.copy()
    shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    shade.fill((6, 7, 14, 175))
    base_frame.blit(shade, (0, 0))
    card_h, gap, width = 44, 10, 340
    top = SCREEN_HEIGHT // 2 - (len(items) * (card_h + gap)) // 2 + 20
    panel = pygame.Rect(0, 0, width + 60, len(items) * (card_h + gap) + 110)
    panel.midtop = (CENTER_X, top - 80)
    rects = [pygame.Rect(CENTER_X - width // 2, top + i * (card_h + gap), width, card_h) for i in range(len(items))]

    def activate(idx):
        res = keys[idx]
        if res == "movelist":
            move_list_screen(surface, clock)
            return None
        _safe_set_cursor(pygame.SYSTEM_CURSOR_ARROW)
        return res

    while True:
        mouse_pos = pygame.mouse.get_pos()
        for i, r in enumerate(rects):
            if r.collidepoint(mouse_pos) and selected != i:
                selected = i
                audio.play_sfx("menu_hover")
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "resume"
                if event.key in (pygame.K_UP, pygame.K_w):
                    audio.play_sfx("menu_hover")
                    selected = (selected - 1) % len(items)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    audio.play_sfx("menu_hover")
                    selected = (selected + 1) % len(items)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    res = activate(selected)
                    if res:
                        return res
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(rects):
                    if r.collidepoint(event.pos):
                        res = activate(i)
                        if res:
                            return res
        surface.blit(base_frame, (0, 0))
        draw_obsidian_card(surface, panel, border_radius=16, bg_color=(16, 17, 30))
        t = render_title("PAUSED", 44)
        surface.blit(t, t.get_rect(midtop=(CENTER_X, panel.y + 14)))
        draw_menu_cards(surface, items, selected, top=top, width=width, height=card_h, gap=gap)
        draw_hint_bar(surface, [("↑ ↓", "Select"), ("Enter", "Confirm"), ("Esc", "Resume")])
        _flip()
        clock.tick(30)


MOVE_INPUTS = {
    "Jab": "J", "Heavy Punch": "K", "Light Kick": "U", "Heavy Kick": "I",
    "Low Sweep": "S + I", "Overhead Strike": "Fwd + K", "Crouching Jab": "S + J",
    "Crouching Kick": "S + U", "Anti-Air Uppercut": "S + K", "Normal Throw": "J + U",
    "Crimson Rush": "Fwd + O", "Rising Uppercut": "O", "Berserker Charge": "Back + O",
    "Clinch Slam": "Down + O", "Blood Fury": "P",
    "Iron Wall": "Down + O", "Shield Bash": "Fwd + O", "Punisher Grip": "O",
    "Reflector": "Back + O", "Fortress Crush": "P",
    "Shadow Step": "Fwd + O", "Phantom Kick": "Down + O", "Feint Strike": "Back + O",
    "Energy Dart": "O", "Vanishing Arts": "P",
    "Tactician Stance": "Down + O", "Golden Read": "O", "Gambit Strike": "Fwd + O",
    "Tactical Step": "Back + O", "Checkmate": "P",
}


def move_list_screen(surface, clock):
    """Move list with inputs and frame data, one tab per fighter."""
    from backend.engine.moves import UNIVERSAL_MOVES, CHARACTER_MOVES

    tabs = ["Universal"] + FIGHTERS
    current_tab = 0
    tab_w, tab_gap = 132, 10
    tabs_x = CENTER_X - (len(tabs) * tab_w + (len(tabs) - 1) * tab_gap) // 2
    tab_rects = [pygame.Rect(tabs_x + i * (tab_w + tab_gap), HEADER_H - 2, tab_w, 32) for i in range(len(tabs))]
    panel = pygame.Rect(40, HEADER_H + 40, SCREEN_WIDTH - 80, SCREEN_HEIGHT - HEADER_H - 90)
    cols = [("MOVE", 0.0), ("INPUT", 0.24), ("DMG", 0.40), ("STARTUP", 0.50), ("ON BLOCK", 0.61), ("PROPERTIES", 0.73)]
    frame = 0
    while True:
        frame += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    return
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    current_tab = (current_tab - 1) % len(tabs)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    current_tab = (current_tab + 1) % len(tabs)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for idx, r in enumerate(tab_rects):
                    if r.collidepoint(event.pos):
                        current_tab = idx

        _screen_bg(surface, "MOVE LIST & FRAME DATA", frame, dim=185)
        for idx, r in enumerate(tab_rects):
            draw_button(surface, r, tabs[idx], selected=(idx == current_tab), size=14,
                        primary=(idx == current_tab))
        draw_obsidian_card(surface, panel, border_radius=12)
        x0 = panel.x + 24
        inner_w = panel.width - 48
        hy = panel.y + 18
        for label, frac in cols:
            draw_text(surface, label, 13, GOLD_TEXT, role="ui", midleft=(x0 + int(inner_w * frac), hy))
        pygame.draw.line(surface, (70, 74, 100), (x0, hy + 14), (x0 + inner_w, hy + 14), 1)

        name = tabs[current_tab]
        if name == "Universal":
            moves = list(UNIVERSAL_MOVES.values())[:10]
        else:
            char_dict = CHARACTER_MOVES.get(name, {})
            moves = [m for m in char_dict.values() if "Special" in m.name or "Super" in m.name
                     or m.action.name.startswith("SPECIAL") or m.action.name == "SUPER"]
            moves = moves or list(char_dict.values())[:10]
        y = hy + 34
        for i, m in enumerate(moves[:12]):
            if i % 2 == 0:
                pygame.draw.rect(surface, (30, 32, 50), (x0 - 8, y - 11, inner_w + 16, 24), border_radius=5)
            prop = m.hit_level.name.title()
            if m.knockdown:
                prop += ", Knockdown"
            if m.launch:
                prop += ", Launch"
            if m.meter_cost > 0:
                prop += f", Cost {int(m.meter_cost)}"
            adv = f"{'+' if m.on_block > 0 else ''}{m.on_block}"
            vals = [(m.name, TEXT_WHITE), (MOVE_INPUTS.get(m.name, m.action.name), (110, 220, 255)),
                    (f"{m.damage:.1f}", (255, 130, 120)), (f"{m.startup}f", (220, 220, 230)),
                    (adv, (120, 235, 140) if m.on_block >= 0 else (255, 130, 130)), (prop, TEXT_MUTED)]
            for (txt, col), (_, frac) in zip(vals, cols):
                draw_text(surface, txt, 14, col, role="body", midleft=(x0 + int(inner_w * frac), y),
                          max_width=int(inner_w * 0.26))
            y += 27
        draw_hint_bar(surface, [("← →", "Fighter"), ("Esc", "Back")])
        _flip()
        clock.tick(30)


# ----------------------------------------------------------------------
# Results screen
# ----------------------------------------------------------------------
def format_hp_stat(val) -> str:
    """Format damage/health (stored 0..1 per round) as HP, e.g. 2.12 -> '212 HP'.

    Values above 10 are treated as already being HP. Never returns '... dmg'.
    """
    if val is None:
        return "0 HP"
    v = float(val)
    hp = int(round(v * 100.0)) if v <= 10.0 else int(round(v))
    return f"{hp} HP"


def _hp_number(val) -> float:
    v = float(val or 0.0)
    return v * 100.0 if v <= 10.0 else v


def _stats_from_legacy_result(res: str, p1_name=None, p2_name=None) -> dict:
    """Old callers passed only 'p1'/'p2'/'draw'; build a minimal stats dict (no invented numbers)."""
    winner = 1 if res == "p1" else (2 if res == "p2" else 0)
    return {
        "p1_name": p1_name or "Player",
        "p2_name": p2_name or "AI",
        "p1_character": "Golden",
        "p2_character": "Crimson",
        "p1_kind": "human" if (p1_name == "Player" or not p1_name) else "ai",
        "p2_kind": "ai",
        "winner_side": winner,
        "rounds_p1": 2 if winner == 1 else 0,
        "rounds_p2": 2 if winner == 2 else 0,
        "status": "finished",
        "match_result": res,
        "rounds_history": [],
    }


def _award_match_coins(stats: dict) -> Optional[dict]:
    """Compute (and outside tests, grant) the coin rewards of a human-vs-AI match."""
    from backend.data.progression import calculate_match_rewards

    reward_info = calculate_match_rewards(
        stats, player_level=stats.get("p1_level", 1), opponent_level=stats.get("p2_level", 1)
    )
    if "PYTEST_CURRENT_TEST" not in os.environ and reward_info.get("total_coins", 0) > 0:
        target_pid = stats.get("player_id")
        if target_pid is None:
            def_player = results_db.get_default_player()
            target_pid = int(def_player["player_id"]) if def_player else None
        if target_pid is not None:
            results_db.add_coins(int(target_pid), reward_info["total_coins"])
            invalidate_economy_cache()
    return reward_info


@dataclass
class _ResultView:
    """Everything the results screen draws, computed once from the stats dict."""
    title: str
    result_col: Tuple[int, int, int]
    bg: str
    left_char: str
    right_char: str
    left_status: str
    right_status: str
    winner_side: int
    p1_head: Tuple[str, str]
    p2_head: Tuple[str, str]
    p2_color: Tuple[int, int, int]
    chips: List[Tuple[str, Tuple[int, int, int]]]
    stat_rows: List[Tuple[str, float, float, str, str]]
    info: str
    rounds: Tuple[int, int]
    is_ai_vs_ai: bool
    is_local_versus: bool
    trophies: List[str] = field(default_factory=list)
    missions: List[str] = field(default_factory=list)


def _build_result_view(stats: dict) -> _ResultView:
    winner_side = stats.get("winner_side", 0)
    p1_kind = stats.get("p1_kind", "human")
    p2_kind = stats.get("p2_kind", "ai")
    is_local = p1_kind == "human" and p2_kind == "human"
    is_ai_vs_ai = p1_kind == "ai" and p2_kind == "ai"
    p1_char = stats.get("p1_character", "Golden")
    p2_char = stats.get("p2_character", "Crimson")
    is_mirror = str(p1_char).strip().lower() == str(p2_char).strip().lower()
    p2_color = ALTERNATE_PALETTES.get(p2_char, {}).get("body", P2_COLOUR) if is_mirror else P2_COLOUR
    p1_full = PRIMARY_PALETTES.get(p1_char, {}).get("title", p1_char)
    p2_full = PRIMARY_PALETTES.get(p2_char, {}).get("title", p2_char) + (" (Alt)" if is_mirror else "")
    p2_diff = str(stats.get("p2_difficulty", "MEDIUM")).upper()

    if winner_side in (1, 2):
        w_char = p1_char if winner_side == 1 else p2_char
        if is_local:
            title, col, bg = f"PLAYER {winner_side} WINS", (P1_ACCENT if winner_side == 1 else P2_ACCENT), "victory"
        elif is_ai_vs_ai:
            title = f"{PRIMARY_PALETTES.get(w_char, {}).get('title', w_char).upper()} WINS"
            col, bg = PRIMARY_PALETTES.get(w_char, {}).get("accent", GOLD_TEXT), "victory"
        elif (winner_side == 1) == (p1_kind == "human"):
            title, col, bg = "YOU WIN", (241, 196, 15), "victory"
        else:
            title, col, bg = "YOU LOSE", (231, 76, 60), "defeat"
    else:
        title, col, bg = "DRAW", (189, 195, 199), "draw"

    if winner_side == 2:
        left_char, right_char, ls, rs = p2_char, p1_char, "WINNER", "DEFEATED"
    elif winner_side == 1:
        left_char, right_char, ls, rs = p1_char, p2_char, "WINNER", "DEFEATED"
    else:
        left_char, right_char, ls, rs = p1_char, p2_char, "DRAW", "DRAW"

    if is_local:
        p1_head, p2_head = ("PLAYER 1", p1_full), ("PLAYER 2", p2_full)
    elif is_ai_vs_ai:
        p1_head = (p1_full, f"(AI, {str(stats.get('p1_difficulty', 'MEDIUM')).upper()})")
        p2_head = (p2_full, f"(AI, {p2_diff})")
    else:
        p1_head = ("YOU", p1_full)
        p2_head = (p2_full, f"({str(p2_kind).upper()}, {p2_diff})")

    def side_label(side: int) -> str:
        kind = p1_kind if side == 1 else p2_kind
        char = p1_char if side == 1 else p2_char
        if is_local:
            return f"P{side}"
        return "YOU" if kind == "human" else (f"{char} (AI)" if kind == "ai" else char)

    chips = []
    history = stats.get("rounds_history", []) or []
    if history:
        for idx, r in enumerate(history):
            w = r.get("winner_side", 0)
            label = side_label(w) if w in (1, 2) else "DRAW"
            c = P1_COLOUR if w == 1 else (p2_color if w == 2 else (160, 165, 175))
            chips.append((f"R{r.get('round_number', idx + 1)}  {label}  {str(r.get('ended_by', 'KO')).upper()}", c))
    else:
        r1, r2 = stats.get("rounds_p1", 0), stats.get("rounds_p2", 0)
        for i in range(r1 + r2):
            side = 1 if i < r1 else 2
            chips.append((f"R{i + 1}  {side_label(side)}", P1_COLOUR if side == 1 else p2_color))

    if history:
        hl1 = history[-1].get("p1_health_left", stats.get("p1_health_left", 0.0))
        hl2 = history[-1].get("p2_health_left", stats.get("p2_health_left", 0.0))
    else:
        hl1 = stats.get("p1_health_left", 1.0 if winner_side == 1 else 0.0)
        hl2 = stats.get("p2_health_left", 1.0 if winner_side == 2 else 0.0)

    def count_row(label, key):
        a, b = stats.get(f"{key}_p1", 0) or 0, stats.get(f"{key}_p2", 0) or 0
        return (label, float(a), float(b), str(a), str(b))

    d1, d2 = stats.get("damage_dealt_p1", 0.0), stats.get("damage_dealt_p2", 0.0)
    stat_rows = [
        ("Damage dealt (HP)", _hp_number(d1), _hp_number(d2), format_hp_stat(d1), format_hp_stat(d2)),
        count_row("Hits landed", "hits_landed"),
        count_row("Blocks", "blocks"),
        count_row("Longest combo", "longest_combo"),
        ("Health left (last round)", _hp_number(hl1), _hp_number(hl2), format_hp_stat(hl1), format_hp_stat(hl2)),
    ]
    dur = float(stats.get("duration_s", 0.0) or 0.0)
    info = f"Time {int(dur) // 60}:{int(dur) % 60:02d}  ·  "
    info += "Local Versus" if is_local else f"Difficulty {p2_diff}"
    info += f"  ·  Arena {_arena_label(str(stats.get('arena', 'Neon Rooftop')))}"

    return _ResultView(
        title=title, result_col=tuple(col), bg=bg, left_char=left_char, right_char=right_char,
        left_status=ls, right_status=rs, winner_side=winner_side, p1_head=p1_head, p2_head=p2_head,
        p2_color=tuple(p2_color), chips=chips, stat_rows=stat_rows, info=info,
        rounds=(stats.get("rounds_p1", 0), stats.get("rounds_p2", 0)),
        is_ai_vs_ai=is_ai_vs_ai, is_local_versus=is_local,
        trophies=[t["name"] for t in stats.get("unlocked_trophies", []) or []],
        missions=[m["name"] for m in stats.get("completed_missions", []) or []],
    )


# Layout of the results panel, derived from the screen size.
_RES_PANEL = pygame.Rect(40, 14, SCREEN_WIDTH - 80, SCREEN_HEIGHT - 28)
_RES_PORTRAIT_W = 150
_RES_TABLE = pygame.Rect(_RES_PANEL.x + _RES_PORTRAIT_W + 44, 168,
                         _RES_PANEL.width - 2 * (_RES_PORTRAIT_W + 44), 200)


def _draw_result_title(surface, view: _ResultView, elapsed: float) -> None:
    anim = min(1.0, elapsed / 0.3)
    scale = 1.0 + 0.30 * (1.0 - anim)
    col = view.result_col
    top = tuple(min(255, int(c * 0.6 + 255 * 0.4)) for c in col)
    bottom = tuple(int(c * 0.75) for c in col)
    t = render_title(view.title, 50, top=top, bottom=bottom)
    if scale > 1.005:
        t = pygame.transform.smoothscale(t, (int(t.get_width() * scale), int(t.get_height() * scale)))
    surface.blit(t, t.get_rect(center=(CENTER_X, 54)))
    # Rounds score
    r1, r2 = view.rounds
    f = fonts.font("ui", 18)
    parts = [("ROUNDS   ", TEXT_MUTED), (str(r1), P1_COLOUR if view.winner_side == 1 else WHITE),
             ("   –   ", TEXT_MUTED), (str(r2), view.p2_color if view.winner_side == 2 else WHITE)]
    surfs = [f.render(txt, True, c) for txt, c in parts]
    x = CENTER_X - sum(s.get_width() for s in surfs) // 2
    for s in surfs:
        surface.blit(s, (x, 86))
        x += s.get_width()


def _draw_result_chips(surface, view: _ResultView) -> None:
    if not view.chips:
        return
    chip_w, chip_h, spacing = 178, 24, 14
    total = len(view.chips) * chip_w + (len(view.chips) - 1) * spacing
    x0 = CENTER_X - total // 2
    for i, (txt, col) in enumerate(view.chips):
        r = pygame.Rect(x0 + i * (chip_w + spacing), 114, chip_w, chip_h)
        pygame.draw.rect(surface, (18, 20, 32), r, border_radius=12)
        pygame.draw.rect(surface, col, r, width=1, border_radius=12)
        draw_text(surface, txt, 13, col, role="ui", center=r.center, max_width=chip_w - 10)


def _draw_result_portraits(surface, view: _ResultView) -> None:
    decided = view.winner_side in (1, 2)
    for side in ("left", "right"):
        is_left = side == "left"
        char = view.left_char if is_left else view.right_char
        status = view.left_status if is_left else view.right_status
        winner = is_left and decided
        loser = (not is_left) and decided
        w = _RES_PORTRAIT_W if not loser else int(_RES_PORTRAIT_W * 0.84)
        h = int(w * 1.25)
        box = pygame.Rect(0, 0, w + 16, h + 46)
        box.midtop = ((_RES_PANEL.x + 22 + _RES_PORTRAIT_W // 2 + 8) if is_left
                      else (_RES_PANEL.right - 22 - _RES_PORTRAIT_W // 2 - 8), 160 + (14 if loser else 0))
        draw_obsidian_card(surface, box, is_selected=winner, border_radius=12)
        slot = pygame.Rect(box.x + 8, box.y + 8, w, h)
        portrait = assets.get_portrait(char, size=(w, h), flip_h=not is_left)
        if loser:
            portrait = portrait.copy()
            dark = pygame.Surface((w, h), pygame.SRCALPHA)
            dark.fill((0, 0, 0, 130))
            portrait.blit(dark, (0, 0))
        surface.blit(portrait, slot)
        pygame.draw.rect(surface, GOLD_TEXT if winner else (80, 85, 100), slot, 1, border_radius=6)
        col = GOLD_BRIGHT if winner else (150, 155, 165)
        draw_text(surface, status, 18 if winner else 15, col, role="display", center=(box.centerx, box.bottom - 20))


def _draw_result_table(surface, view: _ResultView) -> None:
    t = _RES_TABLE
    c1 = t.x + int(t.width * 0.53)
    c2 = t.x + int(t.width * 0.85)
    draw_text(surface, "MATCH STATS", 15, TEXT_GOLD_MUTED, role="ui", midleft=(t.x + 8, t.y))
    draw_text(surface, view.p1_head[0], 16, P1_COLOUR, role="ui", center=(c1, t.y - 6), max_width=150)
    draw_text(surface, view.p1_head[1], 12, TEXT_MUTED, role="body", center=(c1, t.y + 12), max_width=150)
    draw_text(surface, view.p2_head[0], 16, view.p2_color, role="ui", center=(c2, t.y - 6), max_width=150)
    draw_text(surface, view.p2_head[1], 12, TEXT_MUTED, role="body", center=(c2, t.y + 12), max_width=150)
    y = t.y + 28
    for label, n1, n2, s1, s2 in view.stat_rows:
        row = pygame.Rect(t.x, y, t.width, 34)
        surface.blit(_row_fill(row.width, row.height), row.topleft)
        draw_text(surface, label, 14, (200, 204, 215), role="body", midleft=(row.x + 10, y + 13))
        better1, better2 = n1 > n2, n2 > n1
        draw_text(surface, s1, 16 if better1 else 15, P1_COLOUR if better1 else (WHITE if not better2 else (140, 140, 150)),
                  role="ui" if better1 else "body", center=(c1, y + 13))
        draw_text(surface, s2, 16 if better2 else 15, view.p2_color if better2 else (WHITE if not better1 else (140, 140, 150)),
                  role="ui" if better2 else "body", center=(c2, y + 13))
        bar_w = row.width - 20
        frac = max(0.04, min(0.96, n1 / (n1 + n2))) if (n1 + n2) > 0 else 0.5
        w1 = int(round(bar_w * frac))
        pygame.draw.rect(surface, P1_COLOUR, (row.x + 10, y + 27, w1, 3))
        pygame.draw.rect(surface, view.p2_color, (row.x + 10 + w1, y + 27, bar_w - w1, 3))
        y += 40


_ROW_CACHE: Dict[Tuple[int, int], pygame.Surface] = {}


def _row_fill(w: int, h: int) -> pygame.Surface:
    if (w, h) not in _ROW_CACHE:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s, (26, 28, 44, 200), (0, 0, w, h), border_radius=6)
        _ROW_CACHE[(w, h)] = s
    return _ROW_CACHE[(w, h)]


def _draw_result_rewards(surface, view: _ResultView, reward_info: Optional[dict], elapsed: float) -> None:
    y = 404
    draw_text(surface, view.info, 14, TEXT_MUTED, role="ui", center=(CENTER_X, y))
    if reward_info:
        tot = reward_info.get("total_coins", 0)
        anim = int(tot * min(1.0, elapsed / 1.0))
        txt = f"PRIZE  +{anim} GOLD"
        bonuses = [f"{lbl} +{val}" for lbl, val in reward_info.get("breakdown", [])[:3] if val > 0]
        if bonuses:
            txt += "   (" + ", ".join(bonuses) + ")"
        r = pygame.Rect(0, 0, 640, 26)
        r.center = (CENTER_X, y + 26)
        pygame.draw.rect(surface, (30, 26, 16), r, border_radius=13)
        pygame.draw.rect(surface, GOLD_TEXT, r, width=1, border_radius=13)
        draw_text(surface, txt, 14, GOLD_BRIGHT, role="ui", center=r.center, max_width=620)
    if view.trophies:
        draw_text(surface, "TROPHY UNLOCKED: " + ", ".join(view.trophies), 14, GOLD_TEXT, role="ui",
                  center=(CENTER_X, y + 52))
    elif view.missions:
        draw_text(surface, "MISSION COMPLETE: " + ", ".join(view.missions), 14, SUCCESS_GREEN, role="ui",
                  center=(CENTER_X, y + 52))


RESULT_ACTIONS = ("rematch", "character_select", "menu")
RESULT_LABELS = ("Rematch", "Character Select", "Main Menu")
RESULT_KEYS = ("R", "C", "Esc")


def results_screen(surface, clock, stats_or_result, p1_name=None, p2_name=None,
                   lockout_s=0.8, ai_timeout_s=10.0, button_labels: Optional[Sequence[str]] = None):
    """Result screen after the deciding round.

    Shows the result title, round chips, both portraits (winner left), a stats
    table with comparison bars, coin rewards and three buttons. Rematch is the
    default button (Enter = instant rematch); R / C / Esc are direct shortcuts.
    Input is ignored for `lockout_s` seconds so a mashed attack key cannot skip
    the screen. AI-vs-AI results auto-return after `ai_timeout_s`.

    Returns 'rematch', 'character_select' or 'menu'.
    """
    stats = (stats_or_result if isinstance(stats_or_result, dict)
             else _stats_from_legacy_result(str(stats_or_result), p1_name, p2_name))
    view = _build_result_view(stats)
    reward_info = _award_match_coins(stats) if (
        not view.is_ai_vs_ai and not view.is_local_versus
        and "human" in (stats.get("p1_kind", "human"), stats.get("p2_kind", "ai"))) else None

    labels = tuple(button_labels) if button_labels else RESULT_LABELS
    btn_w, btn_h, gap = 230, 46, 26
    total = 3 * btn_w + 2 * gap
    btn_y = _RES_PANEL.bottom - 104
    buttons = [pygame.Rect(CENTER_X - total // 2 + i * (btn_w + gap), btn_y, btn_w, btn_h) for i in range(3)]
    selected = 0
    start_time = time.time()
    last_ding = -1

    while True:
        elapsed = time.time() - start_time
        locked = elapsed < lockout_s
        if view.is_ai_vs_ai and elapsed >= ai_timeout_s:
            return "menu"
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "menu"
            if locked:
                continue
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    selected = (selected - 1) % 3
                    audio.play_sfx("menu_hover")
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    selected = (selected + 1) % 3
                    audio.play_sfx("menu_hover")
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    audio.play_sfx("menu_select")
                    return RESULT_ACTIONS[selected]
                elif event.key == pygame.K_r:
                    return "rematch"
                elif event.key == pygame.K_c:
                    return "character_select"
                elif event.key == pygame.K_ESCAPE:
                    return "menu"
            elif event.type == pygame.MOUSEMOTION:
                for i, r in enumerate(buttons):
                    if r.collidepoint(event.pos):
                        selected = i
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(buttons):
                    if r.collidepoint(event.pos):
                        return RESULT_ACTIONS[i]

        if reward_info and elapsed < 1.0 and reward_info.get("total_coins", 0) > 0:
            step = int(elapsed * 8)
            if step != last_ding:
                audio.play_sfx("coin")
                last_ding = step

        draw_backdrop(surface, int(elapsed * 30), bg=view.bg, dim=120, embers=view.bg != "defeat")
        draw_obsidian_card(surface, _RES_PANEL, border_radius=18, bg_color=(12, 13, 24))
        pygame.draw.rect(surface, view.result_col, _RES_PANEL, width=2, border_radius=18)
        _draw_result_title(surface, view, elapsed)
        _draw_result_chips(surface, view)
        pygame.draw.line(surface, (52, 56, 80), (_RES_PANEL.x + 24, 148), (_RES_PANEL.right - 24, 148), 1)
        _draw_result_portraits(surface, view)
        _draw_result_table(surface, view)
        _draw_result_rewards(surface, view, reward_info, elapsed)

        for i, r in enumerate(buttons):
            draw_button(surface, r, f"{labels[i]}", selected=(not locked and i == selected),
                        disabled=locked, primary=(i == 0), size=17)
            if not locked:
                draw_text(surface, RESULT_KEYS[i], 11, TEXT_MUTED, role="ui", midtop=(r.centerx, r.bottom + 6))
        if locked:
            bar = pygame.Rect(buttons[0].x, btn_y + btn_h + 12, total, 4)
            pygame.draw.rect(surface, (30, 33, 48), bar, border_radius=2)
            pygame.draw.rect(surface, view.result_col,
                             (bar.x, bar.y, int(bar.width * min(1.0, elapsed / max(0.01, lockout_s))), 4),
                             border_radius=2)
        elif view.is_ai_vs_ai:
            rem = max(0, int(round(ai_timeout_s - elapsed)))
            draw_text(surface, f"Returning automatically in {rem}s", 13, TEXT_MUTED, role="ui",
                      center=(CENTER_X, btn_y + btn_h + 30))
        _flip()
        clock.tick(30)


# ----------------------------------------------------------------------
# Player profile prompt
# ----------------------------------------------------------------------
def player_name_prompt(surface, clock) -> str:
    """Ask for the player's name on first launch."""
    player_name = "Player"
    frame = 0
    modal = pygame.Rect(0, 0, 520, 250)
    modal.center = (CENTER_X, SCREEN_HEIGHT // 2 + 10)
    while True:
        frame += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return player_name
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                    return player_name.strip() or "Player"
                elif event.key == pygame.K_BACKSPACE:
                    player_name = player_name[:-1]
                elif len(player_name) < 16 and (event.unicode.isalnum() or event.unicode in " _-"):
                    player_name += event.unicode

        _screen_bg(surface, "WARRIOR PROFILE", frame)
        draw_obsidian_card(surface, modal, is_selected=True, border_radius=14, bg_color=(18, 19, 32))
        t = render_title("WELCOME TO ARENA-AI", 34)
        surface.blit(t, t.get_rect(midtop=(CENTER_X, modal.y + 22)))
        draw_text(surface, "Enter your fighter name", 16, TEXT_MUTED, role="ui", center=(CENTER_X, modal.y + 86))
        box = pygame.Rect(0, 0, 340, 50)
        box.center = (CENTER_X, modal.y + 136)
        pygame.draw.rect(surface, (14, 15, 26), box, border_radius=10)
        pygame.draw.rect(surface, PANEL_BORDER_GLOW, box, width=2, border_radius=10)
        cursor = "_" if (frame // 15) % 2 == 0 else " "
        draw_text(surface, player_name + cursor, 24, GOLD_BRIGHT, role="ui", center=box.center)
        draw_hint_bar(surface, [("Enter", "Confirm"), ("Esc", "Use default")], y=modal.bottom - 26)
        _flip()
        clock.tick(30)


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
SPEED_OPTIONS = [0.5, 1.0, 2.0, 3.0]
SPEED_LABELS = ["0.5x", "1x", "2x", "3x"]
SETTINGS_DEFAULTS = {
    "log_fights": False,
    "speed": 1.0,
    "show_ai": True,
    "master_volume": 1.0,
    "sfx_volume": 0.8,
    "music_volume": 0.6,
    "is_muted": False,
    "renderer": "3d",
    "adaptive_difficulty": False,
}
# (key, label, kind) in display order; None entries are section headers.
SETTINGS_LAYOUT = [
    ("Audio", None, "header"),
    ("master_vol", "Master Volume", "slider"),
    ("sfx_vol", "Sound Effects", "slider"),
    ("music_vol", "Music", "slider"),
    ("mute", "Mute All Audio", "toggle"),
    ("Gameplay", None, "header"),
    ("speed", "Game Speed", "choice"),
    ("show_ai", "Show AI Thinking", "toggle"),
    ("log_fights", "Log Human Fights", "toggle"),
    ("adaptive_difficulty", "Adaptive Difficulty", "toggle"),
    ("renderer", "Fight Graphics", "choice"),
    ("shield_wall", "Shield Wall Balance", "action"),
    ("controls", "Controls & Key Bindings", "action"),
    ("Data", None, "header"),
    ("export_csv", "Export Results to CSV", "action"),
    ("reset_results", "Reset Match Results", "action"),
]
SETTINGS_KEYS = [k for k, _, kind in SETTINGS_LAYOUT if kind != "header"]
_VOLUME_KEYS = {"master_vol": "master_volume", "sfx_vol": "sfx_volume", "music_vol": "music_volume"}
SETTINGS_DESCS = {
    "master_vol": "Overall volume for everything", "sfx_vol": "Punches, blocks, menus",
    "music_vol": "Menu and fight music loops", "mute": "Silence all audio",
    "speed": "Simulation speed for matches (1x is normal)", "show_ai": "Show AI decision overlays during fights",
    "log_fights": "Record human fights for training data",
    "adaptive_difficulty": "AI eases off or pushes harder based on how your rounds go",
    "renderer": "3D (real-time lighting, smooth animation) or classic 2D sprites",
    "shield_wall": "Toggle and tune the Shield Wall mechanic",
    "controls": "Rebind keyboard keys for Player 1 / Player 2 and view the gamepad layout",
    "export_csv": "Write all match results to data/results_export.csv",
    "reset_results": "Delete all recorded match results (asks first)",
}


def _settings_rows(settings: dict) -> List[OptionRow]:
    rows = []
    for key, label, kind in SETTINGS_LAYOUT:
        if kind == "header":
            rows.append(OptionRow(key, key, "header"))
        elif key in _VOLUME_KEYS:
            rows.append(OptionRow(key, label, kind, settings[_VOLUME_KEYS[key]]))
        elif key == "mute":
            rows.append(OptionRow(key, label, kind, settings["is_muted"]))
        elif key == "speed":
            idx = SPEED_OPTIONS.index(settings["speed"]) if settings["speed"] in SPEED_OPTIONS else 1
            rows.append(OptionRow(key, label, kind, SPEED_LABELS[idx]))
        elif key == "renderer":
            rows.append(OptionRow(key, label, kind, "3D" if settings.get("renderer", "3d") == "3d" else "2D"))
        elif kind == "toggle":
            rows.append(OptionRow(key, label, kind, settings.get(key, False)))
        elif key == "shield_wall":
            on = "On" if settings.get("shield_enabled", False) else "Off"
            rows.append(OptionRow(key, label, kind, f"{on} · {settings.get('shield_preset', 'Normal')}"))
        else:
            rows.append(OptionRow(key, label, kind))
    return rows


def _settings_adjust(settings: dict, key: str, delta: int) -> None:
    """Left/Right change of a setting (delta = -1 or +1)."""
    if key in _VOLUME_KEYS:
        sk = _VOLUME_KEYS[key]
        settings[sk] = max(0.0, min(1.0, round(settings[sk] + 0.1 * delta, 1)))
        audio.update_volume(**{sk.split("_")[0]: settings[sk]})
        audio.play_sfx("menu_hover")
    elif key == "speed":
        idx = SPEED_OPTIONS.index(settings["speed"]) if settings["speed"] in SPEED_OPTIONS else 1
        settings["speed"] = SPEED_OPTIONS[(idx + delta) % len(SPEED_OPTIONS)]
        audio.play_sfx("menu_hover")
    elif key == "renderer":
        _settings_activate(settings, key)
        audio.play_sfx("menu_hover")
    elif key in ("mute", "show_ai", "log_fights", "adaptive_difficulty"):
        _settings_activate(settings, key)


def _settings_activate(settings: dict, key: str) -> None:
    """Enter/click on a toggle or slider row (actions are handled by the screen)."""
    if key == "mute":
        settings["is_muted"] = not settings["is_muted"]
        audio.update_volume(muted=settings["is_muted"])
    elif key in ("show_ai", "log_fights", "adaptive_difficulty"):
        settings[key] = not settings.get(key, False)
    elif key == "renderer":
        settings["renderer"] = "2d" if settings.get("renderer", "3d") == "3d" else "3d"
    elif key in _VOLUME_KEYS:
        sk = _VOLUME_KEYS[key]
        settings[sk] = 0.0 if settings[sk] >= 0.99 else min(1.0, round(settings[sk] + 0.2, 1))
        audio.update_volume(**{sk.split("_")[0]: settings[sk]})
    elif key == "speed":
        _settings_adjust(settings, key, 1)


def settings_screen(surface, clock, settings):
    """Audio / gameplay / data settings. Returns the (updated) settings dict."""
    for k, v in SETTINGS_DEFAULTS.items():
        settings.setdefault(k, v)
    if settings["speed"] not in SPEED_OPTIONS:
        settings["speed"] = 1.0
    sel_key = 0  # index into SETTINGS_KEYS
    status_msg, status_until = "", 0.0
    frame = 0
    row_rects: List[Optional[pygame.Rect]] = []

    def run_action(key: str):
        nonlocal settings, status_msg, status_until
        if key == "shield_wall":
            settings = shield_wall_settings_screen(surface, clock, settings)
        elif key == "controls":
            controls_screen(surface, clock)
        elif key == "export_csv":
            path = results_db.export_results_to_csv()
            status_msg, status_until = f"Exported to {path}", time.time() + 3.0
        elif key == "reset_results":
            if confirm_dialog(surface, clock, "Reset results?", "Delete every recorded match result?",
                              confirm_label="Reset", cancel_label="Cancel", danger=True):
                results_db.reset_results()
                status_msg, status_until = "Match results reset", time.time() + 3.0
        else:
            _settings_activate(settings, key)

    while True:
        frame += 1
        rows = _settings_rows(settings)
        row_index = [i for i, r in enumerate(rows) if r.kind != "header"]
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return settings
            if event.type == pygame.KEYDOWN:
                key = SETTINGS_KEYS[sel_key]
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return settings
                if event.key in (pygame.K_UP, pygame.K_w):
                    sel_key = (sel_key - 1) % len(SETTINGS_KEYS)
                    audio.play_sfx("menu_hover")
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel_key = (sel_key + 1) % len(SETTINGS_KEYS)
                    audio.play_sfx("menu_hover")
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    _settings_adjust(settings, key, -1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    _settings_adjust(settings, key, 1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    audio.play_sfx("menu_select")
                    run_action(key)
            if event.type == pygame.MOUSEMOTION:
                for n, ri in enumerate(row_index):
                    r = row_rects[ri] if ri < len(row_rects) else None
                    if r is not None and r.collidepoint(event.pos) and n != sel_key:
                        sel_key = n
                        audio.play_sfx("menu_hover")
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for n, ri in enumerate(row_index):
                    r = row_rects[ri] if ri < len(row_rects) else None
                    if r is not None and r.collidepoint(event.pos):
                        sel_key = n
                        audio.play_sfx("menu_select")
                        run_action(SETTINGS_KEYS[n])

        _screen_bg(surface, "SETTINGS", frame)
        rows = _settings_rows(settings)
        row_rects = draw_option_rows(surface, rows, row_index[sel_key], top=HEADER_H - 6, width=600,
                                     row_h=29, gap=3)
        if time.time() < status_until and status_msg:
            draw_description_pill(surface, status_msg, y=DESC_Y + 8)
        else:
            draw_description_pill(surface, SETTINGS_DESCS.get(SETTINGS_KEYS[sel_key], ""), y=DESC_Y + 8)
        draw_hint_bar(surface, [("↑ ↓", "Select"), ("← →", "Adjust"), ("Enter", "Toggle / Open"), ("Esc", "Back")])
        _flip()
        clock.tick(30)


# ----------------------------------------------------------------------
# Controls / key rebinding
# ----------------------------------------------------------------------
GAMEPAD_HELP = ("Gamepad:  D-pad/stick move  ·  X light punch  ·  Y heavy punch  ·  A light kick  ·  "
                "B heavy kick  ·  RB block  ·  LB special  ·  RT super  ·  LT throw  ·  Start pause")


def _binding_label(binding) -> str:
    codes = [binding] if isinstance(binding, int) else list(binding)
    return " / ".join(controls.key_name(c) for c in codes[:2]) if codes else "—"


def controls_screen(surface, clock):
    """Rebind keys for Player 1 and Player 2. Saved to data/controls.json on exit."""
    binds = {1: controls.load_bindings(1), 2: controls.load_bindings(2)}
    player = 1
    actions = controls.BINDABLE_ACTIONS
    half = (len(actions) + 1) // 2
    sel = 0
    capturing = False
    dirty = False
    frame = 0
    col_w = 400
    col_x = (CENTER_X - col_w // 2 - 214, CENTER_X + col_w // 2 - 186)
    top = HEADER_H + 44
    tab_rects = [pygame.Rect(CENTER_X - 210, HEADER_H, 200, 32), pygame.Rect(CENTER_X + 10, HEADER_H, 200, 32)]
    rects: List[pygame.Rect] = []

    def assign(code: int) -> None:
        nonlocal dirty
        name = actions[sel]
        b = binds[player]
        old = b[name]
        for other, val in b.items():  # swap if the key is already used
            codes = [val] if isinstance(val, int) else list(val)
            if other != name and code in codes:
                b[other] = old if player == 1 else ([old] if isinstance(old, int) else list(old))
        b[name] = code if player == 1 else [code]
        dirty = True

    def finish():
        if dirty:
            controls.save_bindings(binds[1], binds[2])

    while True:
        frame += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                finish()
                return
            if capturing:
                if event.type == pygame.KEYDOWN:
                    if event.key != pygame.K_ESCAPE:
                        assign(event.key)
                        audio.play_sfx("menu_select")
                    capturing = False
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    finish()
                    return
                if event.key in (pygame.K_UP,):
                    sel = (sel - 1) % len(actions)
                elif event.key in (pygame.K_DOWN,):
                    sel = (sel + 1) % len(actions)
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    sel = (sel + half) % len(actions) if sel < half else max(0, sel - half)
                elif event.key in (pygame.K_TAB, pygame.K_1, pygame.K_2):
                    player = {pygame.K_1: 1, pygame.K_2: 2}.get(event.key, 3 - player)
                    audio.play_sfx("menu_hover")
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    capturing = True
                elif event.key == pygame.K_BACKSPACE or event.key == pygame.K_DELETE:
                    binds[player] = controls.default_bindings(player)
                    dirty = True
                    audio.play_sfx("menu_back")
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(tab_rects):
                    if r.collidepoint(event.pos):
                        player = i + 1
                for i, r in enumerate(rects):
                    if r.collidepoint(event.pos):
                        sel = i
                        capturing = True

        _screen_bg(surface, "CONTROLS", frame)
        for i, r in enumerate(tab_rects):
            draw_button(surface, r, f"Player {i + 1}" + ("  (WASD)" if i == 0 else "  (Arrows)"),
                        selected=(player == i + 1), primary=(player == i + 1), size=14,
                        accent=P1_ACCENT if i == 0 else P2_ACCENT)
        rects = []
        for col in range(2):
            names = actions[col * half:(col + 1) * half]
            rows = [OptionRow(n, controls.ACTION_LABELS[n], "key",
                              "press a key…" if (capturing and actions.index(n) == sel)
                              else _binding_label(binds[player][n])) for n in names]
            local_sel = sel - col * half if col * half <= sel < (col + 1) * half else -1
            rr = draw_option_rows(surface, rows, local_sel, top=top, width=col_w, row_h=32, gap=5,
                                  center_x=col_x[col] + col_w // 2)
            rects.extend(r for r in rr if r is not None)
        note = "Press any key to bind (Esc cancels)" if capturing else GAMEPAD_HELP
        draw_description_pill(surface, note, y=DESC_Y + 8, font=fonts.font("body", 13))
        draw_hint_bar(surface, [("↑ ↓ ← →", "Select"), ("Enter", "Rebind"), ("Tab", "Player"),
                                ("Bksp", "Defaults"), ("Esc", "Save & back")])
        _flip()
        clock.tick(30)


def statistics_screen(surface, clock, player_id: Optional[int] = None):
    """Show match statistics with two tabs:

    Tab 1 - 'You': Your record per opponent character & difficulty,
                   current and best streaks, last 10 matches.
    Tab 2 - 'AI':  AI character records (W/L/D and win %), split into
                   'vs human' and 'vs AI', plus chronological AI history.
    """
    font_large = get_font(FONT_SIZE_LARGE, bold=True)
    font_medium = get_font(FONT_SIZE_MEDIUM, bold=True)
    font_small = get_font(20, bold=False)

    active_tab = 0  # 0 = You, 1 = AI

    tab_you_rect = pygame.Rect(180, 75, 300, 36)
    tab_ai_rect = pygame.Rect(544, 75, 300, 36)

    # Query the database once (not every frame).
    human_records = results_db.get_human_record(player_id)
    last_matches = results_db.get_last_matches(player_id, limit=7)
    ai_records = results_db.get_ai_record()
    ai_history = results_db.get_ai_history(limit=7)

    while True:

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                elif event.key == pygame.K_1:
                    active_tab = 0
                elif event.key == pygame.K_2:
                    active_tab = 1
                elif event.key in (pygame.K_TAB, pygame.K_LEFT, pygame.K_RIGHT):
                    active_tab = 1 - active_tab
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if tab_you_rect.collidepoint(event.pos):
                    active_tab = 0
                elif tab_ai_rect.collidepoint(event.pos):
                    active_tab = 1

        _screen_bg(surface, "COMBAT STATISTICS", pygame.time.get_ticks() // 33, compact=True, dim=185)

        # Main Obsidian Panel
        stat_box = pygame.Rect(52, 65, 920, 510)
        draw_obsidian_card(surface, stat_box, is_selected=False, border_radius=12)

        # Tab Buttons
        for idx, (rect, label) in enumerate([(tab_you_rect, "[1] YOU (Human Record)"), (tab_ai_rect, "[2] AI (Model Stats & History)")]):
            is_active = (active_tab == idx)
            draw_button(surface, rect, label, selected=is_active, primary=is_active, size=15)

        # Divider
        pygame.draw.line(surface, (50, 60, 90), (75, 122), (SCREEN_WIDTH - 75, 122), 1)

        # Tab Content
        if active_tab == 0:
            # === TAB 1: YOU ===
            sec1 = font_medium.render("Career Record vs Opponents", True, (241, 196, 15))
            surface.blit(sec1, (80, 130))

            # Headers
            headers = [
                ("Opponent", 100),
                ("Difficulty", 240),
                ("Played", 360),
                ("Record (W-L-D)", 480),
                ("Win %", 630),
                ("Cur Streak", 740),
                ("Best Streak", 850),
            ]
            for h_text, h_x in headers:
                h_surf = font_small.render(h_text, True, (160, 175, 200))
                surface.blit(h_surf, (h_x, 155))

            y_pos = 180
            if not human_records:
                empty_msg = font_small.render("No human matches recorded yet. Start a match to build your record!", True, LIGHT_GREY)
                surface.blit(empty_msg, empty_msg.get_rect(center=(SCREEN_WIDTH // 2, 215)))
            else:
                for r in human_records[:4]:
                    opp_color = PRIMARY_PALETTES.get(r["opponent"], {}).get("body", WHITE)
                    w_l_d = f"{r['wins']} - {r['losses']} - {r['draws']}"
                    pct = round((r["wins"] / r["played"]) * 100, 1) if r["played"] > 0 else 0.0

                    surface.blit(font_small.render(r["opponent"], True, opp_color), (100, y_pos))
                    surface.blit(font_small.render(r["difficulty"], True, WHITE), (240, y_pos))
                    surface.blit(font_small.render(str(r["played"]), True, WHITE), (360, y_pos))
                    surface.blit(font_small.render(w_l_d, True, WHITE), (480, y_pos))
                    pct_color = (46, 204, 113) if pct >= 50 else (231, 76, 60)
                    surface.blit(font_small.render(f"{pct:.1f}%", True, pct_color), (630, y_pos))
                    surface.blit(font_small.render(str(r["current_streak"]), True, WHITE), (740, y_pos))
                    surface.blit(font_small.render(str(r["best_streak"]), True, WHITE), (850, y_pos))
                    y_pos += 26

            # Divider
            pygame.draw.line(surface, (50, 60, 90), (75, 295), (SCREEN_WIDTH - 75, 295), 1)

            # Recent Matches
            sec2 = font_medium.render("Recent Match History (Last 7)", True, (241, 196, 15))
            surface.blit(sec2, (80, 305))

            m_headers = [
                ("Date", 90),
                ("Opponent", 220),
                ("Difficulty", 360),
                ("Score", 480),
                ("Result", 600),
                ("Arena", 720),
            ]
            for h_text, h_x in m_headers:
                h_surf = font_small.render(h_text, True, (160, 175, 200))
                surface.blit(h_surf, (h_x, 330))

            m_y = 355
            if not last_matches:
                empty_m = font_small.render("No match history available.", True, LIGHT_GREY)
                surface.blit(empty_m, empty_m.get_rect(center=(SCREEN_WIDTH // 2, 400)))
            else:
                for m in last_matches:
                    dt_short = m["played_at"][:16] if m.get("played_at") else ""
                    opp = m.get("p2_character", "Fighter")
                    diff = m.get("p2_difficulty", "MEDIUM")
                    score = f"{m.get('rounds_p1', 0)} - {m.get('rounds_p2', 0)}"
                    w_side = m.get("winner_side", 0)
                    if w_side == 1:
                        res_str = "WIN"
                        res_col = (46, 204, 113)
                    elif w_side == 2:
                        res_str = "LOSS"
                        res_col = (231, 76, 60)
                    else:
                        res_str = "DRAW"
                        res_col = LIGHT_GREY

                    arena_raw = str(m.get("arena", "Neon Rooftop")).replace("arena_", "").replace(".jpeg", "").replace(".png", "").replace("_", " ").title()

                    surface.blit(font_small.render(dt_short, True, LIGHT_GREY), (90, m_y))
                    surface.blit(font_small.render(opp, True, WHITE), (220, m_y))
                    surface.blit(font_small.render(diff, True, WHITE), (360, m_y))
                    surface.blit(font_small.render(score, True, WHITE), (480, m_y))
                    surface.blit(font_small.render(res_str, True, res_col), (600, m_y))
                    surface.blit(font_small.render(arena_raw[:18], True, LIGHT_GREY), (720, m_y))
                    m_y += 24

        else:
            # === TAB 2: AI ===
            sec1 = font_medium.render("AI Fighter Records by Difficulty", True, (241, 196, 15))
            surface.blit(sec1, (80, 130))

            ai_headers = [
                ("Fighter", 100),
                ("Difficulty", 250),
                ("Opponent Type", 410),
                ("Played", 570),
                ("Record (W-L-D)", 690),
                ("Win %", 840),
            ]
            for h_text, h_x in ai_headers:
                h_surf = font_small.render(h_text, True, (160, 175, 200))
                surface.blit(h_surf, (h_x, 155))

            y_pos = 180
            if not ai_records:
                empty_ai = font_small.render("No AI matches recorded yet.", True, LIGHT_GREY)
                surface.blit(empty_ai, empty_ai.get_rect(center=(SCREEN_WIDTH // 2, 215)))
            else:
                for r in ai_records[:4]:
                    f_col = PRIMARY_PALETTES.get(r["character"], {}).get("body", WHITE)
                    wld = f"{r['wins']} - {r['losses']} - {r['draws']}"
                    surface.blit(font_small.render(r["character"], True, f_col), (100, y_pos))
                    surface.blit(font_small.render(r["difficulty"], True, WHITE), (250, y_pos))
                    surface.blit(font_small.render(r["opponent_type"], True, LIGHT_GREY), (410, y_pos))
                    surface.blit(font_small.render(str(r["played"]), True, WHITE), (570, y_pos))
                    surface.blit(font_small.render(wld, True, WHITE), (690, y_pos))
                    pct = r.get("win_pct", 0.0)
                    pct_col = (46, 204, 113) if pct >= 50 else (231, 76, 60)
                    surface.blit(font_small.render(f"{pct:.1f}%", True, pct_col), (840, y_pos))
                    y_pos += 26

            # Divider
            pygame.draw.line(surface, (50, 60, 90), (75, 295), (SCREEN_WIDTH - 75, 295), 1)

            # Chronological AI Results
            sec2 = font_medium.render("Latest AI Match Results (Chronological)", True, (241, 196, 15))
            surface.blit(sec2, (80, 305))

            h_y = 340
            if not ai_history:
                empty_h = font_small.render("No AI match history recorded yet.", True, LIGHT_GREY)
                surface.blit(empty_h, empty_h.get_rect(center=(SCREEN_WIDTH // 2, 400)))
            else:
                for h in ai_history:
                    line_surf = font_small.render(f"•  {h['summary']}", True, WHITE)
                    surface.blit(line_surf, (95, h_y))
                    h_y += 24

        # Footer Hint
        draw_hint_bar(surface, [("1 / 2", "Tab"), ("Tab", "Switch"), ("Esc", "Back")], y=SCREEN_HEIGHT - 44)

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


# ------------------------------------------------------------------
# Manual / How to Play
# ------------------------------------------------------------------
def manual_screen(surface, clock):
    """Show the game manual: rules, controls, and special moves.

    Has three pages — use ←/→ or click tabs to switch. Press Esc or click
    'Back' to return to the main menu.
    """
    font_large = get_font(FONT_SIZE_LARGE, bold=True)
    font_medium = get_font(24, bold=True)
    font_small = get_font(18, bold=False)


    page = 0   # 0 = How to Play, 1 = Controls, 2 = Special Moves, 3 = Campaign & Progression
    pages = ["How to Play", "Controls", "Special Moves", "Campaign & Upgrades"]
    tab_rects = []

    while True:
        # Back button rect (drawn every frame, checked on click)
        back_rect = pygame.Rect(20, SCREEN_HEIGHT - 50, 100, 36)
        tab_w = 190
        tab_gap = 14
        total_tab_w = len(pages) * tab_w + (len(pages) - 1) * tab_gap
        start_tab_x = (SCREEN_WIDTH - total_tab_w) // 2

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.play_sfx("menu_back")
                    return
                elif event.key == pygame.K_LEFT:
                    audio.play_sfx("menu_hover")
                    page = max(0, page - 1)
                elif event.key == pygame.K_RIGHT:
                    audio.play_sfx("menu_hover")
                    page = min(len(pages) - 1, page + 1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    audio.play_sfx("menu_select")
                    page = (page + 1) % len(pages)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_rect.collidepoint(event.pos):
                    audio.play_sfx("menu_back")
                    return
                for i, rect in enumerate(tab_rects):
                    if rect.collidepoint(event.pos):
                        audio.play_sfx("menu_select")
                        page = i

        _screen_bg(surface, "COMBAT MANUAL", pygame.time.get_ticks() // 33, compact=True, dim=185)

        # --- Page tabs ---
        tab_rects = []
        for i, tab_name in enumerate(pages):
            tx = start_tab_x + i * (tab_w + tab_gap)
            ty = 64
            tab_rect = pygame.Rect(tx, ty, tab_w, 34)
            tab_rects.append(tab_rect)
            draw_button(surface, tab_rect, tab_name, selected=(i == page), primary=(i == page), size=14)

        # --- Page content ---
        if page == 0:
            _draw_rules_page(surface, font_medium, font_small)
        elif page == 1:
            _draw_controls_page(surface, font_medium, font_small)
        elif page == 2:
            _draw_specials_page(surface, font_medium, font_small)
        else:
            _draw_campaign_guide_page(surface, font_medium, font_small)

        # --- Back button ---
        draw_button(surface, back_rect, "Back", size=15)

        # Navigation hint
        draw_hint_bar(surface, [("← →", "Page"), ("Esc", "Back")], y=SCREEN_HEIGHT - 30)

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def _draw_manual_card(surface, rect, border_color=(70, 80, 110), bg_color=(18, 22, 34, 215)):
    """Draw a semi-transparent panel with a rounded colored border."""
    panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    panel.fill(bg_color)
    surface.blit(panel, (rect.x, rect.y))
    pygame.draw.rect(surface, border_color, rect, 1, border_radius=6)


def _draw_rules_page(surface, font_medium, font_small):
    """Draw the 'How to Play' rules page covering rules, guard levels, combos, and meters."""
    col_w = 445
    card_bg = (18, 22, 34, 215)

    # --- Left Column: Match Rules & Combat System ---
    c1_x = 50

    # 1. Match & Arena Rules
    r1 = pygame.Rect(c1_x, 110, col_w, 126)
    _draw_manual_card(surface, r1, border_color=(130, 150, 190), bg_color=card_bg)
    surface.blit(font_medium.render("Match & Arena Rules", True, (240, 215, 90)), (c1_x + 14, 118))
    rules_c1 = [
        "• 800px arena with walls (supports hard Wall Bounce juggles).",
        "• Best of 3 rounds, 60 seconds per round.",
        "• Win a round by KO (0 HP) or timeout (highest remaining health).",
        "• Equal health at time-out results in a drawn round.",
    ]
    for idx, line in enumerate(rules_c1):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c1_x + 14, 146 + idx * 21))

    # 2. High / Low Guard & Throws
    r2 = pygame.Rect(c1_x, 246, col_w, 136)
    _draw_manual_card(surface, r2, border_color=(90, 160, 230), bg_color=card_bg)
    surface.blit(font_medium.render("High / Low Guard & Throws", True, (100, 205, 255)), (c1_x + 14, 254))
    guard_lines = [
        "• Standing Block (L): Blocks High & Mid attacks. Vulnerable to Lows!",
        "• Crouching Block (S+L): Blocks Low & Mid attacks. Vulnerable to Highs!",
        "• Throw (J+U): Unblockable grip that breaks turtling defenders.",
        "• Throw Tech: Press Throw within 7 frames of being grabbed to escape.",
    ]
    for idx, line in enumerate(guard_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c1_x + 14, 282 + idx * 21))

    # 3. Combos, Juggle Cap & Cancels
    r3 = pygame.Rect(c1_x, 392, col_w, 136)
    _draw_manual_card(surface, r3, border_color=(230, 130, 90), bg_color=card_bg)
    surface.blit(font_medium.render("Combos & Cancels", True, (255, 145, 95)), (c1_x + 14, 400))
    combo_lines = [
        "• Canned Strings: Character chains (e.g. Jab->Jab->Heavy) advance on hit.",
        "• Cancels: Normal attacks cancel into Specials; Specials cancel into Super.",
        "• Counter-Hit: Striking during opponent startup grants +50% hitstun!",
        "• Juggle Cap: Air juggles max out at 4 hits before victim drops safely.",
    ]
    for idx, line in enumerate(combo_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c1_x + 14, 428 + idx * 21))

    # --- Right Column: Meters, Defense & Resources ---
    c2_x = 525

    # 4. Guard Meter & Guard Break
    r4 = pygame.Rect(c2_x, 110, col_w, 126)
    _draw_manual_card(surface, r4, border_color=(230, 90, 90), bg_color=card_bg)
    surface.blit(font_medium.render("Guard Meter & Guard Break", True, (255, 105, 105)), (c2_x + 14, 118))
    guard_meter_lines = [
        "• Blocking attacks drains Guard Meter. Regenerates when idle.",
        "• At 0 Guard: GUARD BREAK! Stunned for 40 frames and helpless to combos.",
        "• Prevents turtling and rewards continuous offensive pressure.",
        "• Every block generates pushback to naturally reset fighter spacing.",
    ]
    for idx, line in enumerate(guard_meter_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c2_x + 14, 146 + idx * 21))

    # 5. Super Meter & Burst
    r5 = pygame.Rect(c2_x, 246, col_w, 136)
    _draw_manual_card(surface, r5, border_color=(170, 110, 240), bg_color=card_bg)
    surface.blit(font_medium.render("Super Meter (0–100) & Burst", True, (190, 135, 255)), (c2_x + 14, 254))
    super_lines = [
        "• Build meter by landing attacks, absorbing damage, and parrying.",
        "• Enhanced Specials / Shield Bash: Costs 25 meter.",
        "• Burst (L+O): Costs 50 meter in hitstun. Blasts the enemy away!",
        "• Super Move (P): Costs 100 meter with a 15-frame cinematic freeze.",
    ]
    for idx, line in enumerate(super_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c2_x + 14, 282 + idx * 21))

    # 6. Fury Mode & Perfect Parry
    r6 = pygame.Rect(c2_x, 392, col_w, 136)
    _draw_manual_card(surface, r6, border_color=(90, 200, 140), bg_color=card_bg)
    surface.blit(font_medium.render("Fury Mode & Perfect Parry", True, (110, 245, 160)), (c2_x + 14, 400))
    fury_lines = [
        "• FURY (< 25% HP): +10% attack damage; Super cost drops to 60 meter!",
        "• Perfect Parry: Tap Block within 4 frames before an incoming hit.",
        "• Parry Effect: 0 damage taken, staggers attacker for 22f, grants +12m.",
        "• Turns patient defensive reads into high-damage counter opportunities.",
    ]
    for idx, line in enumerate(fury_lines):
        surface.blit(font_small.render(line, True, LIGHT_GREY), (c2_x + 14, 428 + idx * 21))


def _draw_controls_page(surface, font_medium, font_small):
    """Draw the 'Controls' page with combat, defensive, special, and shortcut keys."""
    col_w = 445
    card_bg = (18, 22, 34, 215)

    # --- Left Column: Movement & Universal Normals ---
    c1_x = 50

    # 1. Movement Card
    r1 = pygame.Rect(c1_x, 110, col_w, 136)
    _draw_manual_card(surface, r1, border_color=(130, 150, 190), bg_color=card_bg)
    surface.blit(font_medium.render("Movement & Agility", True, (240, 215, 90)), (c1_x + 14, 118))
    moves = [
        ("A / D", "Walk Backward / Forward"),
        ("Double-tap A / D", "Dash / Backdash (4f invulnerability window)"),
        ("W", "Jump (Shadow has Double Jump & Air Dash)"),
        ("S", "Crouch (reduces hurtbox, enables low attacks & low block)"),
    ]
    for idx, (k, desc) in enumerate(moves):
        surface.blit(font_small.render(k, True, WHITE), (c1_x + 14, 146 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c1_x + 140, 146 + idx * 21))

    # 2. Universal Normals Card
    r2 = pygame.Rect(c1_x, 256, col_w, 272)
    _draw_manual_card(surface, r2, border_color=(90, 160, 230), bg_color=card_bg)
    surface.blit(font_medium.render("Normals & Universal Attacks", True, (100, 205, 255)), (c1_x + 14, 264))
    attacks = [
        ("J", "Light Punch / Jab (3f startup, +2 on block, starter)"),
        ("K", "Heavy Punch (10f startup, 8 HP damage, staggers)"),
        ("U", "Light Kick (5f startup, 4 HP damage, mid-range poke)"),
        ("I", "Heavy Kick (12f startup, 10 HP damage, longest reach)"),
        ("S + U / S + I", "Low Sweep (hits LOW, knocks down opponent)"),
        ("S + K", "Anti-Air Uppercut (6f startup, launches jumpers)"),
        ("W + J / W + U", "Jump Punch / Jump Kick (airborne priority)"),
        ("J + U", "Throw (unblockable close grip; tech with J+U in 7f)"),
    ]
    for idx, (k, desc) in enumerate(attacks):
        surface.blit(font_small.render(k, True, WHITE), (c1_x + 14, 292 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c1_x + 120, 292 + idx * 21))

    # --- Right Column: Defense, Specials & Training Shortcuts ---
    c2_x = 525

    # 3. Defense & Specials Card
    r3 = pygame.Rect(c2_x, 110, col_w, 230)
    _draw_manual_card(surface, r3, border_color=(90, 200, 140), bg_color=card_bg)
    surface.blit(font_medium.render("Defense, Specials & Super", True, (110, 245, 160)), (c2_x + 14, 118))
    specials = [
        ("L (hold)", "Standing High Block (blocks High & Mid attacks)"),
        ("S + L (hold)", "Crouching Low Block (blocks Low & Mid attacks)"),
        ("L (tap)", "Perfect Parry (within 4f of hit: 0 dmg, staggers foe)"),
        ("L + O", "Burst (costs 50 meter in hitstun: ends enemy combo)"),
        ("O", "Special Neutral (character signature move 1)"),
        ("D + O / A + O", "Special Forward / Special Back"),
        ("S + O", "Special Down (command grab / ground slam)"),
        ("P", "Super Move (costs 100 meter, or 60 in Fury)"),
    ]
    for idx, (k, desc) in enumerate(specials):
        surface.blit(font_small.render(k, True, WHITE), (c2_x + 14, 146 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c2_x + 120, 146 + idx * 21))

    # 4. Training Mode & Replay Controls Card
    r4 = pygame.Rect(c2_x, 350, col_w, 178)
    _draw_manual_card(surface, r4, border_color=(170, 110, 240), bg_color=card_bg)
    surface.blit(font_medium.render("Training Mode & Replay Controls", True, (190, 135, 255)), (c2_x + 14, 358))
    shortcuts = [
        ("F1", "Toggle Training Mode (Hitboxes, Frame Data & Dummy AI)"),
        ("F2", "Cycle Dummy AI (Stand -> Crouch -> Block All -> Random)"),
        ("F3", "Toggle profiling & performance HUD overlay"),
        ("Esc", "Pause match (open options and Move List screen)"),
        ("Left / Right", "Change match replay speed (0.25x – 4x in AI Viewer)"),
        ("Space", "Pause / resume fight replay"),
    ]
    for idx, (k, desc) in enumerate(shortcuts):
        surface.blit(font_small.render(k, True, WHITE), (c2_x + 14, 386 + idx * 21))
        surface.blit(font_small.render(desc, True, LIGHT_GREY), (c2_x + 110, 386 + idx * 21))


def _draw_specials_page(surface, font_medium, font_small):
    """Draw the 'Special Moves' page detailing each character's unique toolkit without overlaps."""
    fighters_info = [
        {
            "name": "Crimson Brawler",
            "archetype": "Rushdown Berserker",
            "border": (220, 60, 60),
            "accent": (255, 100, 100),
            "moves": [
                ("O", "Crimson Rush", "3-hit advancing dash punch string"),
                ("D+O", "Rising Uppercut", "Anti-air launcher, beats jumps"),
                ("A+O", "Berserker Charge", "Armored dash (takes 50% dmg)"),
                ("S+O", "Clinch Slam", "Close-range command grab"),
                ("P", "Blood Fury (Super)", "8-hit cinematic combo super"),
            ],
            "trait_lines": ["High close-range damage output", "and aggressive cancel pressure."],
        },
        {
            "name": "Steel Guardian",
            "archetype": "Counter & Bulwark",
            "border": (110, 160, 230),
            "accent": (140, 190, 255),
            "moves": [
                ("O", "Iron Wall", "Counter stance; parries & hits"),
                ("D+O", "Shield Bash", "Pushes foe away (costs 25m)"),
                ("A+O", "Reflector", "Reflects projectiles back"),
                ("S+O", "Punisher Grip", "Armored grab; beats blocking"),
                ("P", "Fortress Crush (Super)", "Counter super upon being hit"),
            ],
            "trait_lines": ["Takes 50% less chip damage", "when holding block."],
        },
        {
            "name": "Shadow Striker",
            "archetype": "Agile Hit-and-Run",
            "border": (175, 105, 235),
            "accent": (205, 140, 255),
            "moves": [
                ("O", "Shadow Step", "Teleports behind the opponent"),
                ("D+O", "Phantom Kick", "Low-Mid-Mid deceptive kick"),
                ("A+O", "Feint Strike", "Fake attack into dash / grab"),
                ("S+O", "Energy Dart", "Fast horizontal projectile"),
                ("P", "Vanishing Arts (Super)", "Multi-angle teleport super"),
            ],
            "trait_lines": ["Double Jump (W in air) and", "Air Dash (double-tap A/D in air)."],
        },
        {
            "name": "Golden Tactician",
            "archetype": "Adaptive Stance Master",
            "border": (235, 195, 60),
            "accent": (255, 220, 100),
            "moves": [
                ("O", "Tactician Stance", "Cycles Rush / Guard / Evade"),
                ("D+O", "Gambit Strike", "Advancing tactical thrust"),
                ("A+O", "Golden Read", "Counter read if foe acts in 30f"),
                ("S+O", "Checkmate", "Tactical ground slam finisher"),
                ("P", "Grandmaster (Super)", "Calculated full-screen super"),
            ],
            "trait_lines": ["Tracks enemy attack habits and", "dynamically shifts counters."],
        },
    ]

    col_w = 224
    col_gap = 14
    start_x = 43
    card_bg = (18, 22, 34, 215)

    for i, f_info in enumerate(fighters_info):
        card_x = start_x + i * (col_w + col_gap)
        card_rect = pygame.Rect(card_x, 108, col_w, 428)
        _draw_manual_card(surface, card_rect, border_color=f_info["border"], bg_color=card_bg)

        # Header title & archetype
        title_surf = font_medium.render(f_info["name"], True, f_info["accent"])
        surface.blit(title_surf, (card_x + 10, 118))
        arch_surf = font_small.render(f_info["archetype"], True, LIGHT_GREY)
        surface.blit(arch_surf, (card_x + 10, 142))
        pygame.draw.line(surface, f_info["border"], (card_x + 8, 162), (card_x + col_w - 8, 162), 1)

        # Move list with badge inputs (no text doubling or box overlap)
        cur_y = 172
        for inp, m_name, m_desc in f_info["moves"]:
            badge_w = font_small.size(inp)[0] + 10
            badge_rect = pygame.Rect(card_x + 10, cur_y - 2, badge_w, 18)
            pygame.draw.rect(surface, (45, 55, 75), badge_rect, border_radius=3)
            pygame.draw.rect(surface, (80, 100, 130), badge_rect, 1, border_radius=3)
            inp_surf = font_small.render(inp, True, WHITE)
            surface.blit(inp_surf, inp_surf.get_rect(center=badge_rect.center))

            name_surf = font_small.render(m_name, True, f_info["accent"])
            surface.blit(name_surf, (card_x + 14 + badge_w, cur_y))

            desc_surf = font_small.render(m_desc, True, (170, 180, 200))
            surface.blit(desc_surf, (card_x + 10, cur_y + 19))
            cur_y += 41

        # Passive Trait box (separated clearly at y=380, zero overlap)
        pygame.draw.line(surface, (60, 70, 95), (card_x + 8, 380), (card_x + col_w - 8, 380), 1)
        trait_title = font_small.render("Passive Trait:", True, (240, 215, 90))
        surface.blit(trait_title, (card_x + 10, 390))
        for t_idx, t_line in enumerate(f_info["trait_lines"]):
            t_surf = font_small.render(t_line, True, (210, 220, 240))
            surface.blit(t_surf, (card_x + 10, 410 + t_idx * 18))


def _draw_campaign_guide_page(surface, font_medium, font_small):
    """Draw the 'Campaign & Upgrades' guide page detailing new tournament systems."""
    sections = [
        {
            "title": "Tournament Campaign Mode",
            "accent": (255, 215, 80),
            "lines": [
                "• Embark on an 8-battle escalating campaign against skilled champions.",
                "• Immerse yourself in typewriter story dialogues before each bout.",
                "• Face personality-aligned rivals, culminating with the Grand Sovereign.",
                "• Win battles to earn star ratings and unlock rich coin bounty chests.",
            ],
        },
        {
            "title": "Warrior Upgrades & Level Scaling",
            "accent": (100, 220, 140),
            "lines": [
                "• Earn gold from match victories, combos, parries, and flawless rounds.",
                "• Upgrade individual warriors up to Level 20 in the Upgrade station.",
                "• Enhances Effective Health (+5%), Damage (+3%), Speed, and Guard Defense.",
                "• Opponents scale dynamically to match your battle progression.",
            ],
        },
        {
            "title": "Health Regeneration & Defense",
            "accent": (120, 200, 255),
            "lines": [
                "• Human fighters recover health (1.5%/s) when resting or actively guarding.",
                "• Activates automatically after 2 seconds without taking hit damage.",
                "• A subtle soft green pulse glows along the health bar during regeneration.",
                "• Taking any strike resets the timer immediately; stays off in AI simulations.",
            ],
        },
        {
            "title": "Tutorial Room & Contracts",
            "accent": (220, 140, 255),
            "lines": [
                "• Practice indefinitely against an immortal dummy (Stand, Crouch, Guard, Jump).",
                "• Guided interactive lessons confirm actual inputs before checking off steps.",
                "• Fulfill 18 trophies and ongoing contracts for massive coin rewards.",
                "• Dynamic command bindings display adapts if keys are rebound.",
            ],
        },
    ]

    card_w = (SCREEN_WIDTH - 90) // 2
    card_h = 190
    card_bg = (18, 22, 38)

    for i, s in enumerate(sections):
        col = i % 2
        row = i // 2
        cx = 35 + col * (card_w + 20)
        cy = 118 + row * (card_h + 16)
        card_rect = pygame.Rect(cx, cy, card_w, card_h)

        _draw_manual_card(surface, card_rect, border_color=(70, 75, 110), bg_color=card_bg)
        t_surf = font_medium.render(s["title"], True, s["accent"])
        surface.blit(t_surf, (cx + 16, cy + 14))
        pygame.draw.line(surface, s["accent"], (cx + 16, cy + 40), (cx + card_w - 16, cy + 40), 1)

        y_l = cy + 50
        for line in s["lines"]:
            l_surf = font_small.render(line, True, (210, 220, 235))
            surface.blit(l_surf, (cx + 16, y_l))
            y_l += 28


# ------------------------------------------------------------------
# Model Insights & Neural League Screen (Phase 6)
# ------------------------------------------------------------------
def model_insights_screen(surface, clock):
    """Display model versions, Elo history, style checks, and live training progress."""
    font_large = get_font(FONT_SIZE_LARGE, bold=True)
    font_medium = get_font(24, bold=True)
    font_small = get_font(18, bold=False)

    from backend.learning.league import ModelRegistry
    from backend.learning.trainer_proc import training_manager

    registry = ModelRegistry()
    personalities = ["Crimson", "Steel", "Shadow", "Golden"]
    selected_p_idx = 0


    while True:
        training_manager.poll()

        back_rect = pygame.Rect(20, SCREEN_HEIGHT - 50, 100, 36)
        train_btn_rect = pygame.Rect(SCREEN_WIDTH - 220, SCREEN_HEIGHT - 50, 200, 36)
        tab_w = 140
        start_x = (SCREEN_WIDTH - (len(personalities) * tab_w + (len(personalities) - 1) * 16)) // 2

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                elif event.key == pygame.K_LEFT:
                    selected_p_idx = (selected_p_idx - 1) % len(personalities)
                elif event.key == pygame.K_RIGHT:
                    selected_p_idx = (selected_p_idx + 1) % len(personalities)
                elif event.key in (pygame.K_RETURN, pygame.K_t):
                    if not training_manager.is_alive():
                        training_manager.start_training(
                            personality=personalities[selected_p_idx], total_updates=6, quick_mode=True
                        )
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back_rect.collidepoint(event.pos):
                    return
                if train_btn_rect.collidepoint(event.pos):
                    if not training_manager.is_alive():
                        training_manager.start_training(
                            personality=personalities[selected_p_idx], total_updates=6, quick_mode=True
                        )
                for i in range(len(personalities)):
                    t_rect = pygame.Rect(start_x + i * (tab_w + 16), 62, tab_w, 32)
                    if t_rect.collidepoint(event.pos):
                        selected_p_idx = i

        _screen_bg(surface, "AI MODEL INSIGHTS", pygame.time.get_ticks() // 33, compact=True, dim=185)

        # Personality selector tabs
        for i, p_name in enumerate(personalities):
            tab_rect = pygame.Rect(start_x + i * (tab_w + 16), 62, tab_w, 32)
            is_sel = (i == selected_p_idx)
            draw_button(surface, tab_rect, p_name, selected=is_sel, primary=is_sel, size=14)

        active_char = personalities[selected_p_idx]
        models = registry.list_models(personality=active_char)

        # Left Panel: Model Registry & Versions
        left_panel = pygame.Rect(45, 108, 450, 360)
        _draw_manual_card(surface, left_panel, border_color=(90, 110, 150))
        surface.blit(font_medium.render(f"Registered Models ({active_char})", True, (240, 215, 90)), (left_panel.x + 14, 118))
        pygame.draw.line(surface, (70, 80, 105), (left_panel.x + 14, 144), (left_panel.x + left_panel.width - 14, 144), 1)

        row_y = 154
        surface.blit(font_small.render("VER", True, (160, 170, 190)), (left_panel.x + 14, row_y))
        surface.blit(font_small.render("STATUS", True, (160, 170, 190)), (left_panel.x + 80, row_y))
        surface.blit(font_small.render("ELO", True, (160, 170, 190)), (left_panel.x + 190, row_y))
        surface.blit(font_small.render("WIN %", True, (160, 170, 190)), (left_panel.x + 270, row_y))
        surface.blit(font_small.render("UPDATED", True, (160, 170, 190)), (left_panel.x + 350, row_y))
        row_y += 24

        if not models:
            surface.blit(
                font_small.render("No trained checkpoints yet. Click 'Train Now' to begin!", True, LIGHT_GREY),
                (left_panel.x + 14, row_y + 40),
            )
        else:
            for m in models[:8]:
                st = m.get("status", "candidate")
                if st == "live":
                    status_color = (100, 255, 120)
                elif st == "promoted":
                    status_color = (100, 200, 255)
                elif st == "archived":
                    status_color = (160, 180, 210)
                else:
                    status_color = (255, 100, 100)
                surface.blit(font_small.render(m.get("version_tag", "v001"), True, WHITE), (left_panel.x + 14, row_y))
                surface.blit(font_small.render(st.upper(), True, status_color), (left_panel.x + 80, row_y))
                surface.blit(font_small.render(f"{m.get('elo', 1000.0):.1f}", True, (240, 220, 100)), (left_panel.x + 190, row_y))
                surface.blit(font_small.render(f"{m.get('win_rate', 0.0)*100:.1f}%", True, WHITE), (left_panel.x + 270, row_y))
                ago_min = max(0, int((time.time() - m.get("timestamp", time.time())) / 60))
                surface.blit(font_small.render(f"{ago_min}m ago", True, LIGHT_GREY), (left_panel.x + 350, row_y))
                row_y += 22

        # Right Panel: Style Constraints & Explanation Preview
        right_panel = pygame.Rect(520, 108, 455, 360)
        _draw_manual_card(surface, right_panel, border_color=(120, 100, 170))
        surface.blit(font_medium.render("Style Check & Neural Explanation", True, (190, 140, 255)), (right_panel.x + 14, 118))
        pygame.draw.line(surface, (70, 80, 105), (right_panel.x + 14, 144), (right_panel.x + right_panel.width - 14, 144), 1)

        # Live model stats
        live_m = registry.get_live_model(active_char)
        s_y = 154
        if live_m:
            surface.blit(font_small.render(f"Live Model: {live_m['version_tag']} (Elo: {live_m['elo']:.1f})", True, (100, 255, 120)), (right_panel.x + 14, s_y))
            s_y += 22
            surface.blit(font_small.render(f"• Aggression Score: {live_m.get('aggression', 0.0):.2f}", True, WHITE), (right_panel.x + 14, s_y))
            s_y += 20
            surface.blit(font_small.render(f"• Defense Rate: {live_m.get('defense', 0.0):.1f} blocks/min", True, WHITE), (right_panel.x + 14, s_y))
            s_y += 20
            surface.blit(font_small.render(f"• Average Spacing: {live_m.get('avg_distance', 0.0):.1f} px", True, WHITE), (right_panel.x + 14, s_y))
        else:
            from backend.ai.difficulty import resolve_learned_model
            from backend.learning import config as lcfg
            resolved = resolve_learned_model(active_char)
            if resolved:
                label = f"HIGH/HELL model: {os.path.basename(resolved)} (no live promotion)"
            else:
                label = "HIGH/HELL model: none found - rule-based FSM + search"
            surface.blit(font_small.render(label, True, (240, 215, 90)), (right_panel.x + 14, s_y))
            s_y += 24
            surface.blit(font_small.render("Style Constraints:", True, LIGHT_GREY), (right_panel.x + 14, s_y))
            s_y += 20
            if active_char == "Crimson":
                rule = f"• Aggression >= {lcfg.STYLE_CRIMSON_MIN_AGGRESSION:.2f}"
            elif active_char == "Steel":
                rule = f"• Defense >= {lcfg.STYLE_STEEL_MIN_DEFENSE:.1f} blocks/parries per min"
            elif active_char == "Shadow":
                rule = (f"• Avg spacing >= {lcfg.STYLE_SHADOW_MIN_AVG_DISTANCE:.0f} px and "
                        f">= {lcfg.STYLE_MIN_DAMAGE_PER_MINUTE:.0f}% dmg/min")
            else:
                rule = (f"• Action entropy >= {lcfg.STYLE_GOLDEN_ENTROPY_MIN:.1f} bits and "
                        f">= {lcfg.STYLE_MIN_DAMAGE_PER_MINUTE:.0f}% dmg/min")
            surface.blit(font_small.render(rule, True, WHITE), (right_panel.x + 14, s_y))

        s_y += 30
        pygame.draw.line(surface, (70, 80, 105), (right_panel.x + 14, s_y), (right_panel.x + right_panel.width - 14, s_y), 1)
        s_y += 10
        surface.blit(font_medium.render("Decision Explanation Preview", True, (100, 220, 255)), (right_panel.x + 14, s_y))
        s_y += 24
        surface.blit(font_small.render("Live decision explanations (policy confidence,", True, WHITE), (right_panel.x + 14, s_y))
        s_y += 20
        surface.blit(font_small.render("opponent prediction, latency) are shown in the", True, WHITE), (right_panel.x + 14, s_y))
        s_y += 20
        surface.blit(font_small.render("AI vs AI viewer, measured from the real match.", True, WHITE), (right_panel.x + 14, s_y))

        # Bottom Bar: Live Training Progress & Actions
        bottom_box = pygame.Rect(45, 480, SCREEN_WIDTH - 90, 60)
        _draw_manual_card(surface, bottom_box, border_color=(70, 80, 110))

        # Draw progress bar
        p_bar_rect = pygame.Rect(55, 492, SCREEN_WIDTH - 390, 18)
        pygame.draw.rect(surface, (30, 35, 50), p_bar_rect, border_radius=4)
        if training_manager.progress > 0:
            fill_w = int(p_bar_rect.width * min(1.0, training_manager.progress))
            fill_rect = pygame.Rect(55, 492, fill_w, 18)
            pygame.draw.rect(surface, (50, 160, 240), fill_rect, border_radius=4)
        pygame.draw.rect(surface, (70, 90, 130), p_bar_rect, 1, border_radius=4)

        surface.blit(font_small.render(training_manager.last_status, True, WHITE), (55, 516))

        # Train button
        btn_text = "Training..." if training_manager.is_alive() else f"Train {active_char} (T)"
        draw_button(surface, train_btn_rect, btn_text, disabled=training_manager.is_alive(), primary=True, size=15)

        # Back button
        draw_button(surface, back_rect, "Back", size=15)

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def shield_wall_settings_screen(surface, clock, settings):
    """In-game Shield Wall Balance Settings submenu (Step 3).

    Provides:
    - Toggle On/Off
    - Presets: Weak / Normal / Strong / Custom
    - Same for both fighters toggle (default ON)
    - Sliders (HP, duration, cooldown, cost, regen) with clamped ranges
    """
    from backend.engine.shield_config import (
        PRESETS,
        SLIDER_RANGES,
        clamp_shield_balance,
    )

    font_large = get_font(FONT_SIZE_LARGE, bold=True)
    font_medium = get_font(FONT_SIZE_MEDIUM, bold=True)
    font_small = get_font(FONT_SIZE_SMALL, bold=False)

    settings.setdefault("shield_enabled", False)
    settings.setdefault("shield_preset", "Normal")
    settings.setdefault("shield_same_both", True)
    settings.setdefault("shield_p1", {
        "shield_hp": 25.0, "duration_s": 3.0, "cooldown_s": 6.0,
        "energy_cost": 35.0, "energy_regen_per_s": 8.0,
    })
    settings.setdefault("shield_p2", {
        "shield_hp": 25.0, "duration_s": 3.0, "cooldown_s": 6.0,
        "energy_cost": 35.0, "energy_regen_per_s": 8.0,
    })

    PRESET_LIST = ["Weak", "Normal", "Strong", "Custom"]
    SLIDER_KEYS = [
        ("shield_hp", "Shield HP", 5.0),
        ("duration_s", "Duration (s)", 0.5),
        ("cooldown_s", "Cooldown (s)", 0.5),
        ("energy_cost", "Energy Cost", 5.0),
        ("energy_regen_per_s", "Regen / sec", 1.0),
    ]

    selected = 0
    editing_p2 = False

    while True:
        target_dict = settings["shield_p2"] if (not settings["shield_same_both"] and editing_p2) else settings["shield_p1"]

        items = ["enabled", "preset", "same_both"]
        if not settings["shield_same_both"]:
            items.append("switch_player")
        if settings["shield_preset"] == "Custom":
            items.extend([k for k, _, _ in SLIDER_KEYS])

        selected = min(selected, len(items) - 1)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return settings
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return settings
                elif event.key == pygame.K_UP:
                    selected = (selected - 1) % len(items)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(items)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    cur = items[selected]
                    if cur == "enabled":
                        settings["shield_enabled"] = not settings["shield_enabled"]
                    elif cur == "same_both":
                        settings["shield_same_both"] = not settings["shield_same_both"]
                    elif cur == "switch_player":
                        editing_p2 = not editing_p2
                    elif cur == "preset":
                        idx = PRESET_LIST.index(settings["shield_preset"])
                        new_pre = PRESET_LIST[(idx + 1) % len(PRESET_LIST)]
                        settings["shield_preset"] = new_pre
                        if new_pre in PRESETS:
                            p_bal = PRESETS[new_pre]
                            for d in (settings["shield_p1"], settings["shield_p2"]):
                                d["shield_hp"] = p_bal.shield_hp
                                d["duration_s"] = p_bal.duration_s
                                d["cooldown_s"] = p_bal.cooldown_s
                                d["energy_cost"] = p_bal.energy_cost
                                d["energy_regen_per_s"] = p_bal.energy_regen_per_s
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    delta_sign = 1.0 if event.key == pygame.K_RIGHT else -1.0
                    cur = items[selected]
                    if cur == "preset":
                        idx = PRESET_LIST.index(settings["shield_preset"])
                        new_pre = PRESET_LIST[(idx + int(delta_sign)) % len(PRESET_LIST)]
                        settings["shield_preset"] = new_pre
                        if new_pre in PRESETS:
                            p_bal = PRESETS[new_pre]
                            for d in (settings["shield_p1"], settings["shield_p2"]):
                                d["shield_hp"] = p_bal.shield_hp
                                d["duration_s"] = p_bal.duration_s
                                d["cooldown_s"] = p_bal.cooldown_s
                                d["energy_cost"] = p_bal.energy_cost
                                d["energy_regen_per_s"] = p_bal.energy_regen_per_s
                    else:
                        for sk, _, step_val in SLIDER_KEYS:
                            if cur == sk:
                                lo, hi = SLIDER_RANGES[sk]
                                target_dict[sk] = round(max(lo, min(hi, target_dict[sk] + delta_sign * step_val)), 1)
                                if settings["shield_same_both"]:
                                    settings["shield_p2"][sk] = target_dict[sk]

        _screen_bg(surface, "SHIELD WALL BALANCE", pygame.time.get_ticks() // 33)

        rows = []
        for key in items:
            if key == "enabled":
                rows.append(OptionRow(key, "Shield Wall", "toggle", settings["shield_enabled"]))
            elif key == "preset":
                rows.append(OptionRow(key, "Preset", "choice", settings["shield_preset"]))
            elif key == "same_both":
                rows.append(OptionRow(key, "Same for both fighters", "toggle", settings["shield_same_both"]))
            elif key == "switch_player":
                rows.append(OptionRow(key, "Editing sliders for", "action",
                                      "Player 2 (handicap)" if editing_p2 else "Player 1"))
            else:
                label = next(lbl for k, lbl, _ in SLIDER_KEYS if k == key)
                rows.append(OptionRow(key, label, "choice", target_dict[key]))
        draw_option_rows(surface, rows, selected, top=HEADER_H + 10, width=560, row_h=36, gap=6)

        draw_hint_bar(surface, [("↑ ↓", "Select"), ("Enter", "Toggle"), ("← →", "Adjust"), ("Esc", "Back")])

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)


def rumble_menu(surface, clock):
    """Arena Rumble configuration submenu allowing selective mechanic toggles."""
    from backend.engine.rules import ModeRules

    font_large = get_font(FONT_SIZE_LARGE, bold=True)
    font_medium = get_font(FONT_SIZE_MEDIUM, bold=True)
    font_small = get_font(FONT_SIZE_SMALL, bold=False)

    rules = ModeRules.rumble()
    match_types = ["Human vs AI", "Local Versus", "AI vs AI"]
    match_keys = ["human_vs_ai", "local_versus", "ai_vs_ai"]
    match_idx = 0

    items = [
        "start",
        "match_type",
        "zone",
        "building",
        "loot",
        "objects",
        "shield_wall",
        "auto_pickup",
    ]
    selected = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None, None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None, None
                elif event.key == pygame.K_UP:
                    selected = (selected - 1) % len(items)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(items)
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT) and items[selected] == "match_type":
                    match_idx = (match_idx + 1) % len(match_types)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    cur = items[selected]
                    if cur == "start":
                        m_type = match_keys[match_idx]
                        return rules, m_type
                    elif cur == "match_type":
                        match_idx = (match_idx + 1) % len(match_types)
                    elif cur == "zone":
                        rules.enable_zone = not rules.enable_zone
                    elif cur == "building":
                        rules.enable_building = not rules.enable_building
                    elif cur == "loot":
                        rules.enable_loot = not rules.enable_loot
                    elif cur == "objects":
                        rules.enable_objects = not rules.enable_objects
                    elif cur == "shield_wall":
                        rules.enable_shield_wall = not rules.enable_shield_wall
                    elif cur == "auto_pickup":
                        rules.auto_pickup = not rules.auto_pickup

        _screen_bg(surface, "ARENA RUMBLE", pygame.time.get_ticks() // 33)

        labels = {
            "start": "[ START ARENA RUMBLE ]",
            "match_type": f"Match Type:  {match_types[match_idx]}",
            "zone": f"The Squeeze (Zone):  {'ON' if rules.enable_zone else 'OFF'}",
            "building": f"Cover Building (B):  {'ON' if rules.enable_building else 'OFF'}",
            "loot": f"Loot & Supply Drops:  {'ON' if rules.enable_loot else 'OFF'}",
            "objects": f"Crates, Pads & Traps:  {'ON' if rules.enable_objects else 'OFF'}",
            "shield_wall": f"Shield Wall (Q/E):  {'ON' if rules.enable_shield_wall else 'OFF'}",
            "auto_pickup": f"Auto-Pickup Items:  {'ON' if rules.auto_pickup else 'OFF'}",
        }

        rows = [
            OptionRow("start", "Start Arena Rumble", "action", ""),
            OptionRow("match_type", "Match Type", "choice", match_types[match_idx]),
            OptionRow("zone", "The Squeeze (shrinking zone)", "toggle", rules.enable_zone),
            OptionRow("building", "Cover Building (B)", "toggle", rules.enable_building),
            OptionRow("loot", "Loot & Supply Drops", "toggle", rules.enable_loot),
            OptionRow("objects", "Crates, Pads & Traps", "toggle", rules.enable_objects),
            OptionRow("shield_wall", "Shield Wall (Q / E)", "toggle", rules.enable_shield_wall),
            OptionRow("auto_pickup", "Auto-Pickup Items", "toggle", rules.auto_pickup),
        ]
        draw_option_rows(surface, rows, selected, top=HEADER_H + 4, width=560, row_h=38, gap=6)

        draw_hint_bar(surface, [("↑ ↓", "Select"), ("Enter", "Toggle / Start"), ("← →", "Match type"), ("Esc", "Back")])

        if pygame.display.get_surface() is not None:
            pygame.display.flip()
        clock.tick(30)
