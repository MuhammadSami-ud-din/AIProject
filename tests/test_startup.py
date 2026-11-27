"""Startup / smoke tests: run the real game logic headless and make sure nothing crashes.

Everything runs with SDL_VIDEODRIVER=dummy (no window). The real menus, real
fight screen, real tutorial and real engine are used. Only these things are
replaced by scripted stand-ins:
  * the menu *answers* (match type, fighter, difficulty, results buttons),
  * the keyboard (a scripted list of actions is "pressed"),
  * the clock (so frames run as fast as possible),
  * the results database (a temporary file, so the real one is never touched).
"""

import ast
import itertools
import os
import pathlib
import random
import sys
import types

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

import frontend.fight_screen as fight_screen
import frontend.main as game_main
import frontend.screens as screens
import frontend.tutorial as tutorial
from backend.ai.actions import Action
from backend.data.results_db import ResultsDB, results_db as _REAL_DB
from backend.engine.rules import ModeRules
from frontend.colours import SCREEN_HEIGHT, SCREEN_WIDTH

FRAMES = 300
HARD_LIMIT = 30000  # safety net so a bug can never hang the test run

BASE_SCRIPT = [
    Action.FORWARD, Action.FORWARD, Action.LIGHT, Action.IDLE, Action.HEAVY,
    Action.BLOCK, Action.CROUCH, Action.LIGHT_KICK, Action.JUMP, Action.DASH,
    Action.BACKDASH, Action.SPECIAL_NEUTRAL, Action.HEAVY_KICK, Action.THROW,
    Action.BLOCK_LOW, Action.SUPER, Action.BACK, Action.IDLE,
]
SHIELD_SCRIPT = BASE_SCRIPT + [Action.SHIELD_FRONT, Action.IDLE, Action.SHIELD_BACK, Action.IDLE]


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------

class FastClock:
    """A clock that never sleeps, so 300 frames take milliseconds."""

    def tick(self, *_args, **_kwargs):
        return 0

    def tick_busy_loop(self, *_args, **_kwargs):
        return 0

    def get_fps(self):
        return 60.0

    def get_time(self):
        return 16

    def get_rawtime(self):
        return 16


def key_event(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0)


@pytest.fixture(autouse=True)
def headless_game(monkeypatch, tmp_path):
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.event.clear()
    random.seed(1234)  # deterministic AI seeds -> deterministic tests

    # Use a throw-away database everywhere the game imported `results_db`.
    db = ResultsDB(db_path=str(tmp_path / "startup_test.db"))
    for name, mod in list(sys.modules.items()):
        if name.startswith(("frontend", "backend")):
            try:
                if getattr(mod, "results_db", None) is _REAL_DB:
                    monkeypatch.setattr(mod, "results_db", db)
            except Exception:
                pass
    yield db
    pygame.event.clear()


@pytest.fixture
def screen():
    return pygame.display.get_surface()


@pytest.fixture
def clock():
    return FastClock()


@pytest.fixture
def player_id(headless_game):
    return headless_game.get_or_create_player("StartupTester")


def make_settings(shield=False):
    return {
        "log_fights": False,
        "speed": 1.0,
        "show_ai": True,
        "master_volume": 1.0,
        "sfx_volume": 0.8,
        "music_volume": 0.6,
        "is_muted": False,
        "shield_enabled": shield,
        "shield_preset": "Normal",
        "shield_same_both": True,
    }


def install_flip_hook(monkeypatch, schedule, limit=800):
    """Post scripted events on given display frames; fail instead of hanging."""
    counter = {"frames": 0}

    def fake_flip(*_a, **_k):
        counter["frames"] += 1
        if counter["frames"] > limit:
            raise AssertionError("screen never closed")
        for ev in schedule.get(counter["frames"], []):
            pygame.event.post(ev)

    monkeypatch.setattr(pygame.display, "flip", fake_flip)
    return counter


class Probe:
    """Counts engine frames of a screen and scripts the human player."""

    def __init__(self):
        self.steps = 0
        self.rules_seen = set()


def install_probe(monkeypatch, module, *, stop_after=None, stop_event=None,
                  force_ko=False, shield=False):
    """Wrap `module.step` (engine frames) and `module.get_human_action` (keyboard).

    stop_after: after this many engine frames post `stop_event` (ends the screen).
    force_ko:   make P2 lose now and then so real matches finish quickly.
    """
    probe = Probe()
    real_step = module.step
    script = itertools.cycle(SHIELD_SCRIPT if shield else BASE_SCRIPT)

    def step_wrapper(state, a1, a2, *args, **kwargs):
        probe.steps += 1
        if probe.steps > HARD_LIMIT:
            raise AssertionError("match never finished")
        probe.rules_seen.add(state.rules.enable_shield_wall)
        new_state = real_step(state, a1, a2, *args, **kwargs)
        if force_ko and probe.steps % 5 == 0:
            new_state.fighter2.health = 0.0
        if stop_after is not None and probe.steps == stop_after:
            pygame.event.post(stop_event)
        return new_state

    monkeypatch.setattr(module, "step", step_wrapper)
    monkeypatch.setattr(module, "get_human_action", lambda *a, **k: next(script))
    return probe


def stub_menus(monkeypatch, *, match_type="me_vs_ai", p1="Crimson", p2="Steel",
               difficulty="LOW", results=("menu",)):
    """Script the answers of the menu screens used by the match flow."""
    calls = types.SimpleNamespace(match_type=0, characters=[], difficulty=0, results=[])
    results_iter = iter(results)

    def match_type_select(_s, _c):
        calls.match_type += 1
        return match_type

    def character_select(_s, _c, is_p2=False, **_kwargs):
        calls.characters.append(is_p2)
        return p2 if is_p2 else p1

    def difficulty_select(_s, _c):
        calls.difficulty += 1
        return difficulty

    def results_screen(_s, _c, stats):
        calls.results.append(dict(stats))
        return next(results_iter, "menu")

    monkeypatch.setattr(game_main, "match_type_select", match_type_select)
    monkeypatch.setattr(game_main, "character_select", character_select)
    monkeypatch.setattr(game_main, "difficulty_select", difficulty_select)
    monkeypatch.setattr(game_main, "results_screen", results_screen)
    return calls


def make_setup(match_type, rules=None):
    return {
        "match_type": match_type,
        "p1_char": "Crimson",
        "p2_char": "Steel",
        "difficulty": "LOW",
        "rules": rules,
    }


def call_depth():
    frame, depth = sys._getframe(), 0
    while frame is not None:
        depth += 1
        frame = frame.f_back
    return depth


def track_run_fight_depths(monkeypatch):
    """Record how deep the Python call stack is every time a match starts."""
    real = fight_screen.run_fight
    depths = []

    def wrapper(*args, **kwargs):
        depths.append(call_depth())
        return real(*args, **kwargs)

    monkeypatch.setattr(game_main, "run_fight", wrapper)
    return depths


MATCH_TYPES = ["me_vs_ai", "random_ai", "ai_vs_ai"]
MATCH_LABELS = {
    "me_vs_ai": "Human vs AI",
    "random_ai": "Human vs Random AI",
    "ai_vs_ai": "AI vs AI",
}


# ----------------------------------------------------------------------
# 1. Menus open
# ----------------------------------------------------------------------

def test_main_menu_esc_asks_before_quitting(monkeypatch, screen, clock):
    """Esc opens a quit confirmation; cancelling keeps the menu, confirming quits."""
    frames = install_flip_hook(monkeypatch, {
        20: [key_event(pygame.K_ESCAPE)],      # open the dialog
        25: [key_event(pygame.K_ESCAPE)],      # cancel -> back to the menu
        30: [key_event(pygame.K_ESCAPE)],      # open again
        35: [key_event(pygame.K_y)],           # confirm
    })
    result = screens.main_menu(screen, clock)
    assert result == "quit"
    assert frames["frames"] >= 35  # it really drew frames (menu kept running after cancel)


def test_quick_fight_screen_returns_a_full_setup(monkeypatch, screen, clock):
    install_flip_hook(monkeypatch, {
        5: [key_event(pygame.K_RIGHT)],        # focus starts on FIGHT; right does nothing harmful
        8: [key_event(pygame.K_RETURN)],
    })
    choice = screens.quick_fight_screen(screen, clock)
    assert choice is not None
    assert choice.mode in ("me_vs_ai", "local_versus", "ai_vs_ai")
    assert choice.p1_char and choice.p2_char and choice.difficulty in ("LOW", "MEDIUM", "HIGH", "HELL")


def test_quick_fight_flow_plays_a_match(monkeypatch, screen, clock, player_id):
    calls = stub_menus(monkeypatch)
    install_probe(monkeypatch, fight_screen, force_ko=True)
    choice = screens.QuickFightChoice("me_vs_ai", "Crimson", "Steel", "LOW", "arena_iron_foundry")
    answers = iter([choice, None])
    monkeypatch.setattr(game_main, "quick_fight_screen", lambda s, c, initial=None: next(answers))
    game_main._quick_fight_flow(screen, clock, make_settings(), player_id)
    assert len(calls.results) == 1
    assert calls.results[0]["arena"] == "arena_iron_foundry"
    assert calls.match_type == 0 and calls.characters == []   # no extra menus


def test_local_versus_passes_both_and_falls_back(monkeypatch, screen, clock, player_id):
    """Local versus asks run_fight for two humans; a rejection falls back to P1 vs AI."""
    stub_menus(monkeypatch, match_type="local_versus")
    seen = []

    def fake_run_fight(surface, clock_, a1, a2, human_player=None, **kwargs):
        seen.append(human_player)
        if human_player == "both":
            raise ValueError("human_player='both' not supported")
        return "quit"

    monkeypatch.setattr(game_main, "run_fight", fake_run_fight)
    monkeypatch.setattr(game_main, "_local_versus_supported", lambda: True)
    result, setup = game_main._start_match(screen, clock, make_settings(), player_id=player_id)
    assert seen == ["both", 1]
    assert result == "menu" and setup.match_type == "local_versus"


def test_main_menu_enter_picks_an_entry(monkeypatch, screen, clock):
    install_flip_hook(monkeypatch, {
        5: [key_event(pygame.K_DOWN)],
        10: [key_event(pygame.K_RETURN)],
    })
    result = screens.main_menu(screen, clock)
    assert isinstance(result, str) and result


@pytest.mark.parametrize("name", ["match_type_select", "character_select", "difficulty_select"])
def test_match_setup_menus_open_and_close(monkeypatch, screen, clock, name):
    frames = install_flip_hook(monkeypatch, {15: [key_event(pygame.K_ESCAPE)]})
    getattr(screens, name)(screen, clock)  # must not crash; ESC closes it
    assert frames["frames"] >= 15


# ----------------------------------------------------------------------
# 2. One match of each type, 300 frames, scripted inputs
# ----------------------------------------------------------------------

@pytest.mark.parametrize("match_type", MATCH_TYPES, ids=[MATCH_LABELS[m] for m in MATCH_TYPES])
def test_each_match_type_plays_300_frames(monkeypatch, screen, clock, player_id, match_type):
    stub_menus(monkeypatch, match_type=match_type)
    probe = install_probe(
        monkeypatch, fight_screen, stop_after=FRAMES, stop_event=pygame.event.Event(pygame.QUIT)
    )
    result, setup = game_main._start_match(
        screen, clock, make_settings(), player_id=player_id, rules=None
    )
    assert probe.steps >= FRAMES
    assert result == "menu"          # we "quit" the match after 300 frames
    assert setup.match_type == match_type


def test_tutorial_plays_300_frames(monkeypatch, screen, clock):
    probe = install_probe(
        monkeypatch, tutorial, stop_after=FRAMES, stop_event=key_event(pygame.K_ESCAPE)
    )
    tutorial.run_tutorial(screen, clock, "Crimson")
    assert probe.steps >= FRAMES


def test_arena_rumble_exists():
    assert callable(getattr(screens, "rumble_menu", None))
    assert ModeRules.rumble().is_rumble is True


def test_arena_rumble_human_match_plays_300_frames(monkeypatch, screen, clock, player_id):
    probe = install_probe(
        monkeypatch, fight_screen, stop_after=FRAMES, stop_event=pygame.event.Event(pygame.QUIT)
    )
    result, _ = game_main._start_match(
        screen, clock, make_settings(), player_id=player_id,
        setup=make_setup("me_vs_ai", rules=ModeRules.rumble()),
    )
    assert probe.steps >= FRAMES
    assert result == "menu"


def test_arena_rumble_ai_match_plays_300_frames(monkeypatch, screen, clock):
    stub_menus(monkeypatch)
    probe = install_probe(
        monkeypatch, fight_screen, stop_after=FRAMES, stop_event=pygame.event.Event(pygame.QUIT)
    )
    game_main._ai_fight(screen, clock, make_settings(), rules=ModeRules.rumble())
    assert probe.steps >= FRAMES


def test_arena_rumble_from_menu_choice(monkeypatch, screen, clock, player_id):
    """Match-type menu -> 'rumble' -> rumble menu -> human match."""
    calls = stub_menus(monkeypatch, match_type="rumble")
    answers = iter(["rumble", "me_vs_ai"])  # first rumble, then pick a normal match type
    monkeypatch.setattr(game_main, "match_type_select", lambda s, c: next(answers))
    monkeypatch.setattr(game_main, "rumble_menu", lambda s, c: (ModeRules.rumble(), "me_vs_ai"))
    probe = install_probe(
        monkeypatch, fight_screen, stop_after=FRAMES, stop_event=pygame.event.Event(pygame.QUIT)
    )
    result = game_main._match_session(screen, clock, make_settings(), player_id=player_id)
    assert probe.steps >= FRAMES
    assert result == "menu"
    assert calls.difficulty == 1


# ----------------------------------------------------------------------
# 3. Rematches: no recursion, same match again
# ----------------------------------------------------------------------

@pytest.mark.parametrize("match_type", MATCH_TYPES, ids=[MATCH_LABELS[m] for m in MATCH_TYPES])
def test_five_rematches_in_a_row(monkeypatch, screen, clock, player_id, match_type):
    calls = stub_menus(monkeypatch, match_type=match_type, results=["rematch"] * 5 + ["menu"])
    install_probe(monkeypatch, fight_screen, force_ko=True)
    depths = track_run_fight_depths(monkeypatch)

    result = game_main._match_session(screen, clock, make_settings(), player_id=player_id)

    assert result == "menu"
    assert len(calls.results) == 6               # 1 match + 5 rematches, all finished
    assert len(depths) == 6
    assert len(set(depths)) == 1                 # stack never got deeper -> no recursion
    assert calls.match_type == 1                 # menus were asked only once
    assert len(calls.characters) == (1 if match_type == "random_ai" else 2)
    assert calls.difficulty == 1
    # Same fighters every time
    assert len({(s["p1_character"], s["p2_character"]) for s in calls.results}) == 1


def test_new_random_opponent_and_character_select_results(monkeypatch, screen, clock, player_id):
    calls = stub_menus(
        monkeypatch, match_type="random_ai",
        results=["new_random", "character_select", "rematch", "menu"],
    )
    install_probe(monkeypatch, fight_screen, force_ko=True)
    depths = track_run_fight_depths(monkeypatch)

    result = game_main._match_session(screen, clock, make_settings(), player_id=player_id)

    assert result == "menu"
    assert len(calls.results) == 4
    assert len(set(depths)) == 1
    # "character_select" sends the player back to pick a fighter again (not match type)
    assert calls.characters == [False, False]
    assert calls.match_type == 1
    assert calls.difficulty == 2


def test_quitting_a_match_returns_to_menu(monkeypatch, screen, clock, player_id):
    stub_menus(monkeypatch, match_type="me_vs_ai", results=["rematch"])
    install_probe(
        monkeypatch, fight_screen, stop_after=50, stop_event=pygame.event.Event(pygame.QUIT)
    )
    result = game_main._match_session(screen, clock, make_settings(), player_id=player_id)
    assert result == "menu"


# ----------------------------------------------------------------------
# 4. Shield wall ON and OFF
# ----------------------------------------------------------------------

@pytest.mark.parametrize("shield", [True, False], ids=["shield_on", "shield_off"])
@pytest.mark.parametrize("match_type", MATCH_TYPES, ids=[MATCH_LABELS[m] for m in MATCH_TYPES])
def test_shield_wall_on_and_off_plays_300_frames(monkeypatch, screen, clock, player_id,
                                                 match_type, shield):
    stub_menus(monkeypatch, match_type=match_type)
    probe = install_probe(
        monkeypatch, fight_screen, shield=shield,
        stop_after=FRAMES, stop_event=pygame.event.Event(pygame.QUIT),
    )
    result, _ = game_main._start_match(
        screen, clock, make_settings(shield=shield), player_id=player_id
    )
    assert probe.steps >= FRAMES
    assert result == "menu"
    assert probe.rules_seen == {shield}  # the engine really ran with that setting


@pytest.mark.parametrize("shield", [True, False], ids=["shield_on", "shield_off"])
@pytest.mark.parametrize("match_type", ["me_vs_ai", "random_ai"])
def test_finished_human_match_records_shield_setting(monkeypatch, screen, clock, player_id,
                                                      match_type, shield):
    """This is the code that used to crash with 'active_rules' not set."""
    calls = stub_menus(monkeypatch, match_type=match_type)
    install_probe(monkeypatch, fight_screen, force_ko=True, shield=shield)

    result, _ = game_main._start_match(
        screen, clock, make_settings(shield=shield), player_id=player_id
    )

    assert result == "menu"
    stats = calls.results[0]
    assert stats["shield_enabled"] is shield
    assert stats["shield_preset"] == "Normal"
    assert set(stats["shield_balance"]) == {"p1_hp", "p2_hp"}
    assert stats["status"] == "finished"


# ----------------------------------------------------------------------
# 5. The real main() loop wiring
# ----------------------------------------------------------------------

def test_main_loop_starts_a_match_then_quits(monkeypatch, headless_game):
    calls = stub_menus(monkeypatch, match_type="me_vs_ai", results=["rematch", "menu"])
    install_probe(monkeypatch, fight_screen, force_ko=True)
    choices = iter(["start", "quit"])
    monkeypatch.setattr(game_main, "check_settings", lambda: None)
    monkeypatch.setattr(game_main, "intro_screen", lambda s, c: None)
    monkeypatch.setattr(game_main, "player_name_prompt", lambda s, c: "StartupTester")
    monkeypatch.setattr(game_main, "main_menu", lambda s, c: next(choices))
    monkeypatch.setattr(pygame, "quit", lambda: None)  # keep pygame alive for other tests
    monkeypatch.setattr(game_main.pygame, "quit", lambda: None)
    monkeypatch.setattr(game_main.pygame.time, "Clock", FastClock)

    with pytest.raises(SystemExit):
        game_main.main()

    assert len(calls.results) == 2  # first match + one rematch


# ----------------------------------------------------------------------
# 6. Guard rails for the three bugs
# ----------------------------------------------------------------------

def _function_defs(path):
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def test_start_match_does_not_call_itself():
    fn = next(f for f in _function_defs("frontend/main.py") if f.name == "_start_match")
    called = {
        c.func.id for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "_start_match" not in called


def test_no_frontend_function_calls_itself():
    offenders = []
    for path in pathlib.Path("frontend").rglob("*.py"):
        for fn in _function_defs(path):
            for c in ast.walk(fn):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == fn.name:
                    offenders.append(f"{path}:{fn.name}")
    assert offenders == []


def test_active_rules_is_assigned_before_any_use():
    """`active_rules` must be set before the first line that reads it."""
    fn = next(f for f in _function_defs("frontend/main.py") if f.name == "_start_match")
    first_assign = first_use = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == "active_rules":
            if isinstance(node.ctx, ast.Store):
                first_assign = min(first_assign or node.lineno, node.lineno)
            else:
                first_use = min(first_use or node.lineno, node.lineno)
    assert first_assign is not None and first_use is not None
    assert first_assign < first_use


def test_frontend_only_uses_fighterstate_attributes_that_exist():
    """Every `state.fighter1.xxx` / `f1.xxx` style access must be a real field/property."""
    import dataclasses
    from backend.engine.state import FighterState

    known = {f.name for f in dataclasses.fields(FighterState)} | {
        n for n in dir(FighterState) if not n.startswith("__")
    }
    missing = []
    for path in pathlib.Path("frontend").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            base = node.value
            on_fighter = (
                isinstance(base, ast.Attribute) and base.attr in ("fighter1", "fighter2")
            ) or (isinstance(base, ast.Name) and base.id in ("f1", "f2", "fighter_state"))
            if on_fighter and node.attr not in known:
                missing.append(f"{path}:{node.lineno} {node.attr}")
    assert missing == []
