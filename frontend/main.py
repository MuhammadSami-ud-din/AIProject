"""Arena-AI: main entry point and menu flow.

Run with:  uv run python -m frontend.main

Flow overview
-------------
main()             main-menu loop (Quick Fight, Campaign, Versus & Modes, ...)
_match_session()   plays matches back to back (rematch loop, never recursive)
_start_match()     plays exactly ONE match and returns a MatchOutcome
MatchSetup         everything needed to (re)start a match
"""

from __future__ import annotations

import inspect
import json
import os
import random
import sys
from dataclasses import dataclass, replace
from typing import Any, NamedTuple, Optional

import pygame

from backend.ai.base_agent import Agent
from backend.ai.config_check import check_settings
from backend.ai.personalities import ALL_PERSONALITIES
from backend.ai.random_agent import RandomAgent
from backend.data.campaign import get_battle
from backend.data.results_db import results_db
from frontend.audio import audio
from frontend.campaign_screens import (
    campaign_map_screen,
    missions_screen,
    story_screen,
    trophy_room_screen,
    upgrade_screen,
)
from frontend.fight_screen import run_fight
from frontend.screens import (
    character_select,
    controls_screen,
    difficulty_select,
    fighter_hq_menu,
    intro_screen,
    main_menu,
    manual_screen,
    match_type_select,
    model_insights_screen,
    options_info_menu,
    player_name_prompt,
    quick_fight_screen,
    results_screen,
    rumble_menu,
    settings_screen,
    statistics_screen,
)
from frontend.theme import SCREEN_HEIGHT, SCREEN_WIDTH
from frontend.tutorial import run_tutorial

ALL_FIGHTERS = ["Crimson", "Steel", "Shadow", "Golden"]

# What _start_match can report back to its caller after ONE match.
MATCH_RESULTS = ("rematch", "new_random", "character_select", "menu")

_HUMAN_VS_PICKED = ("me_vs_ai", "human_vs_selected", "human_vs_ai")
_HUMAN_VS_RANDOM = ("random_ai", "human_vs_random")
LOCAL_VERSUS = "local_versus"
AI_VS_AI = "ai_vs_ai"

SETTINGS_PATH = os.path.join("data", "settings.json")
DEFAULT_SETTINGS = {
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

# Remembered between screens during one run (e.g. the fighter the upgrade
# screen should open on).
_SESSION = {"last_fighter": None, "quick_fight": None}


# ----------------------------------------------------------------------
# Data types
# ----------------------------------------------------------------------
@dataclass
class MatchSetup:
    """Everything needed to start (or restart) a match.

    match_type: 'me_vs_ai', 'random_ai', 'local_versus' or 'ai_vs_ai'.
    Fighter / difficulty fields may be None while the setup is still being
    chosen (e.g. after "character select" only match_type and rules are kept).
    """

    match_type: Optional[str] = None
    p1_char: Optional[str] = None
    p2_char: Optional[str] = None
    difficulty: Optional[str] = None
    rules: Any = None
    arena: Optional[str] = None
    viewer: bool = False  # AI vs AI: use the telemetry viewer instead of the plain fight screen

    @classmethod
    def coerce(cls, value) -> Optional["MatchSetup"]:
        """Accept a MatchSetup, a dict with the same keys, or None."""
        if value is None or isinstance(value, MatchSetup):
            return value
        if isinstance(value, dict):
            known = {k: value.get(k) for k in cls.__dataclass_fields__ if k in value}
            return cls(**known)
        raise TypeError(f"cannot build MatchSetup from {type(value).__name__}")

    @property
    def is_complete(self) -> bool:
        if not (self.match_type and self.p1_char and self.p2_char):
            return False
        return bool(self.difficulty) or self.match_type == LOCAL_VERSUS

    @property
    def is_ai_vs_ai(self) -> bool:
        return self.match_type == AI_VS_AI

    @property
    def is_local_versus(self) -> bool:
        return self.match_type == LOCAL_VERSUS

    def keep_mode_only(self) -> "MatchSetup":
        """Used for "character select": keep match type + rules, re-pick the rest."""
        return MatchSetup(match_type=self.match_type, rules=self.rules, arena=self.arena,
                          viewer=self.viewer)


class MatchOutcome(NamedTuple):
    """Return value of _start_match: `action, setup = _start_match(...)`.

    action is one of MATCH_RESULTS; setup is the MatchSetup that was played
    (None if the player backed out of the setup menus).
    """

    action: str
    setup: Optional[MatchSetup]


class _HumanAgent(Agent):
    """Placeholder agent for a human player (real input is read in run_fight)."""

    def __init__(self, name="Player", player=1, character="Golden"):
        super().__init__(
            name=name,
            player=player,
            difficulty="LOW",
            personality=ALL_PERSONALITIES.get(character),
        )
        self.character_name = character

    def choose_action(self, state):
        return None, {}


# ----------------------------------------------------------------------
# Settings persistence
# ----------------------------------------------------------------------
def _persistence_enabled() -> bool:
    return "PYTEST_CURRENT_TEST" not in os.environ


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    if _persistence_enabled():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            if isinstance(saved, dict):
                settings.update(saved)
        except (OSError, ValueError):
            pass
    return settings


def save_settings(settings: dict) -> None:
    if not _persistence_enabled():
        return
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in settings.items() if isinstance(v, (int, float, str, bool, dict, list))},
                      fh, indent=2)
    except OSError:
        pass


def _apply_audio(settings: dict) -> None:
    audio.update_volume(
        master=settings["master_volume"],
        sfx=settings["sfx_volume"],
        music=settings["music_volume"],
        muted=settings["is_muted"],
    )


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
def main():
    """Start the game."""
    check_settings()

    pygame.init()
    surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Arena-AI")
    clock = pygame.time.Clock()

    settings = load_settings()
    _apply_audio(settings)

    intro_screen(surface, clock)

    default_player = results_db.get_default_player()
    if default_player is None:
        player_id = results_db.get_or_create_player(player_name_prompt(surface, clock))
    else:
        player_id = int(default_player["player_id"])

    while True:
        choice = main_menu(surface, clock)
        if choice == "quit":
            break
        elif choice == "quick":
            _quick_fight_flow(surface, clock, settings, player_id)
        elif choice == "campaign":
            _campaign_flow(surface, clock, settings, player_id=player_id)
        elif choice == "start":
            _match_session(surface, clock, settings, player_id=player_id)
        elif choice == "tutorial":
            _tutorial_flow(surface, clock)
        elif choice == "hq":
            _fighter_hq_flow(surface, clock, player_id)
        elif choice == "options":
            settings = _options_flow(surface, clock, settings)

    pygame.quit()
    sys.exit()


def _fighter_hq_flow(surface, clock, player_id):
    while True:
        hq_choice = fighter_hq_menu(surface, clock, player_id=player_id)
        if hq_choice in ("back", None):
            return
        if hq_choice == "upgrades":
            _upgrades_flow(surface, clock, player_id=player_id)
        elif hq_choice == "missions":
            missions_screen(surface, clock, player_id)
        elif hq_choice == "trophies":
            trophy_room_screen(surface, clock, player_id)
        elif hq_choice == "statistics":
            statistics_screen(surface, clock, player_id=player_id)


def _options_flow(surface, clock, settings):
    while True:
        opt_choice = options_info_menu(surface, clock)
        if opt_choice in ("back", None):
            return settings
        if opt_choice == "settings":
            settings = settings_screen(surface, clock, settings)
            save_settings(settings)
        elif opt_choice == "controls":
            controls_screen(surface, clock)
        elif opt_choice == "manual":
            manual_screen(surface, clock)
        elif opt_choice == "insights":
            model_insights_screen(surface, clock)


# ----------------------------------------------------------------------
# Match setup
# ----------------------------------------------------------------------
def _resolve_random(name: Optional[str]) -> Optional[str]:
    return random.choice(ALL_FIGHTERS) if name == "Random" else name


def _pick_fighter(surface, clock, is_p2, title=None):
    """Run character select once. Returns a fighter name, or None if cancelled."""
    choice = character_select(surface, clock, is_p2=is_p2, **({"title": title} if title else {}))
    return None if choice is None else _resolve_random(choice)


def _choose_match_setup(surface, clock, settings, rules=None, match_type=None) -> Optional[MatchSetup]:
    """Ask the player what to play. Returns a MatchSetup, or None to go back.

    If match_type is given (after "character select"), the match-type screen is
    skipped the first time and the player only re-picks fighters/difficulty.
    Arena Rumble asks for its rules and then continues straight into fighter
    selection (no nested menus).
    """
    preset_type = match_type
    while True:
        match_type = preset_type or match_type_select(surface, clock)
        preset_type = None
        if match_type is None:
            return None

        if match_type == "rumble":
            r_rules, r_type = rumble_menu(surface, clock)
            if r_rules is None or r_type is None:
                continue
            rules = r_rules
            match_type = {"human_vs_ai": "me_vs_ai", "me_vs_ai": "me_vs_ai"}.get(r_type, r_type)

        if match_type in _HUMAN_VS_PICKED or match_type in (AI_VS_AI, LOCAL_VERSUS):
            p1_char = _pick_fighter(surface, clock, is_p2=False)
            if p1_char is None:
                continue
            p2_title = "PLAYER 2: CHOOSE FIGHTER" if match_type == LOCAL_VERSUS else None
            p2_char = _pick_fighter(surface, clock, is_p2=True, title=p2_title)
            if p2_char is None:
                continue
        elif match_type in _HUMAN_VS_RANDOM:
            p1_char = _pick_fighter(surface, clock, is_p2=False)
            if p1_char is None:
                continue
            p2_char = random.choice(ALL_FIGHTERS)
        else:
            continue  # unknown match type: ask again

        if match_type == LOCAL_VERSUS:
            difficulty = "LOW"  # unused: both sides are human
        else:
            difficulty = difficulty_select(surface, clock)
            if difficulty is None:
                continue

        return MatchSetup(match_type=match_type, p1_char=p1_char, p2_char=p2_char,
                          difficulty=difficulty, rules=rules)


# ----------------------------------------------------------------------
# Playing matches
# ----------------------------------------------------------------------
def _local_versus_supported() -> bool:
    """True if run_fight understands human_player='both' (two keyboard/gamepad players)."""
    try:
        import frontend.fight_screen as fs
        if getattr(fs, "SUPPORTS_LOCAL_VERSUS", False):
            return True
        return "\"both\"" in inspect.getsource(fs.run_fight) or "'both'" in inspect.getsource(fs.run_fight)
    except (OSError, TypeError):
        return False


def _run_fight_safe(surface, clock, agent1, agent2, human_player, **kwargs):
    """Call run_fight; if it rejects human_player='both', fall back to P1 human vs AI."""
    if human_player == "both" and not _local_versus_supported():
        print("[Arena-AI] Local versus is not supported by this fight screen; P2 will be AI.")
        return run_fight(surface, clock, agent1, kwargs.pop("fallback_p2"), human_player=1, **kwargs), False
    kwargs.pop("fallback_p2", None)
    try:
        return run_fight(surface, clock, agent1, agent2, human_player=human_player, **kwargs), human_player == "both"
    except (TypeError, ValueError, NotImplementedError) as exc:
        if human_player != "both":
            raise
        print(f"[Arena-AI] run_fight(human_player='both') failed ({exc}); P2 will be AI.")
        return None, False


def _shield_summary(rules) -> dict:
    return {
        "shield_enabled": rules.enable_shield_wall,
        "shield_preset": rules.shield_preset,
        "shield_balance": {
            "p1_hp": rules.shield_balance_p1.shield_hp,
            "p2_hp": rules.shield_balance_p2.shield_hp,
        },
    }


def _mode_name(setup: MatchSetup, rules) -> str:
    if setup.is_local_versus:
        return "Local Versus"
    base = "AI vs AI" if setup.is_ai_vs_ai else "Human vs AI"
    return base


def _save_abandoned(setup: MatchSetup, rules, player_id, mode_name: str, arena=None) -> None:
    """Record a match the player quit before it finished (no invented stats)."""
    record = {
        "mode": mode_name,
        "p1_kind": "ai" if setup.is_ai_vs_ai else "human",
        "p1_character": setup.p1_char,
        "p1_difficulty": setup.difficulty if setup.is_ai_vs_ai else "LOW",
        "p2_kind": "human" if setup.is_local_versus else "ai",
        "p2_character": setup.p2_char,
        "p2_difficulty": setup.difficulty,
        "winner_side": 0,
        "rounds_p1": 0,
        "rounds_p2": 0,
        "duration_s": 0.0,
        "arena": arena or setup.arena or "unknown",
        "player_id": player_id,
        "status": "abandoned",
        "rounds_history": [],
    }
    if rules is not None:
        record.update(_shield_summary(rules))
    results_db.save_match(record)


def _start_match(surface, clock, settings, player_id=None, rules=None, setup=None) -> MatchOutcome:
    """Play exactly ONE match (it never calls itself).

    Returns MatchOutcome(action, setup): action is one of MATCH_RESULTS and
    setup holds everything needed to start the same match again. The caller
    (_match_session) runs the rematch loop.
    """
    setup = MatchSetup.coerce(setup)
    active_rules = rules if rules is not None else _rules_from_settings(settings, None)
    if setup is not None and setup.rules is not None:
        active_rules = setup.rules

    # Step 1: find out what to play (menus) unless the caller already knows.
    if setup is None or not setup.is_complete:
        preset_type = setup.match_type if setup else None
        chosen = _choose_match_setup(surface, clock, settings, rules=active_rules, match_type=preset_type)
        if chosen is None:
            return MatchOutcome("menu", None)
        if setup is not None:
            chosen = replace(chosen, arena=setup.arena, viewer=setup.viewer)
        setup = chosen
        if setup.rules is not None:
            active_rules = setup.rules

    setup = replace(setup, rules=active_rules,
                    p1_char=_resolve_random(setup.p1_char), p2_char=_resolve_random(setup.p2_char))
    speed = settings.get("speed", 1.0)
    mode_name = _mode_name(setup, active_rules)

    # Step 2: build the two sides.
    if setup.is_ai_vs_ai:
        agent1 = _make_agent(setup.p1_char, player=1, difficulty=setup.difficulty)
        human_player = None
        p1_lvl = 1
    else:
        agent1 = _HumanAgent(name="Player", player=1, character=setup.p1_char)
        _SESSION["last_fighter"] = setup.p1_char
        human_player = "both" if setup.is_local_versus else 1
        p1_lvl = results_db.get_character_level(player_id, setup.p1_char) if player_id else 1
    # Adaptive difficulty only makes sense against a human.
    ai_p2 = _make_agent(setup.p2_char, player=2, difficulty=setup.difficulty,
                        adaptive=bool(settings.get("adaptive_difficulty")) and not setup.is_ai_vs_ai)
    agent2 = _HumanAgent(name="Player 2", player=2, character=setup.p2_char) if setup.is_local_versus else ai_p2

    # Step 3: play.
    fight_kwargs = dict(speed_mult=speed, rules=active_rules, p1_level=p1_lvl, p2_level=p1_lvl,
                        p1_regen=not setup.is_ai_vs_ai, player_id=player_id, settings=settings)
    if setup.arena:
        fight_kwargs["arena_name"] = setup.arena
    if setup.is_ai_vs_ai and setup.viewer and not active_rules.is_rumble:
        from frontend.ai_viewer import run_ai_viewer
        stats = run_ai_viewer(surface, clock, agent1, agent2, speed_mult=speed, arena_name=setup.arena)
        local_ok = False
    elif setup.is_local_versus:
        stats, local_ok = _run_fight_safe(surface, clock, agent1, agent2, "both",
                                          fallback_p2=ai_p2, **fight_kwargs)
        if stats is None:  # 'both' rejected at call time: play P1 vs AI instead
            stats = run_fight(surface, clock, agent1, ai_p2, human_player=1, **fight_kwargs)
    else:
        stats = run_fight(surface, clock, agent1, agent2, human_player=human_player, **fight_kwargs)
        local_ok = False

    # Step 4: the player quit in the middle of the match.
    if not isinstance(stats, dict):
        _save_abandoned(setup, active_rules, player_id, mode_name)
        return MatchOutcome("menu", setup)

    # Step 5: match finished: save real stats and show the results screen.
    if setup.is_local_versus and local_ok:
        stats["p1_kind"] = stats["p2_kind"] = "human"
        stats["p1_name"], stats["p2_name"] = "Player 1", "Player 2"
    stats["mode"] = mode_name if (local_ok or not setup.is_local_versus) else "Human vs AI"
    stats["player_id"] = player_id
    stats["status"] = "finished"
    stats.setdefault("p1_difficulty", setup.difficulty)
    stats.setdefault("p2_difficulty", setup.difficulty)
    stats.update(_shield_summary(active_rules))
    results_db.save_match(stats)

    action = results_screen(surface, clock, stats)
    if action not in MATCH_RESULTS:
        action = "menu"
    return MatchOutcome(action, setup)


def _match_session(surface, clock, settings, player_id=None, rules=None, setup=None,
                   stop_on_character_select=False):
    """Play matches one after another until the player goes back to the menu.

    Returns "menu", or "character_select" when stop_on_character_select is set
    (Quick Fight then reopens its own setup screen).
    """
    setup = MatchSetup.coerce(setup)
    while True:
        result, setup = _start_match(
            surface, clock, settings, player_id=player_id, rules=rules, setup=setup
        )
        if setup is None:
            return result
        if result == "rematch":
            continue  # same fighters, same rules
        elif result == "new_random":
            setup = replace(setup, p2_char=random.choice(ALL_FIGHTERS))
        elif result == "character_select":
            if stop_on_character_select:
                return "character_select"
            setup = setup.keep_mode_only()
        else:
            return result  # "menu"


def _quick_fight_flow(surface, clock, settings, player_id):
    """Quick Fight: one setup screen, then straight into the rematch loop."""
    while True:
        choice = quick_fight_screen(surface, clock, initial=_SESSION.get("quick_fight"))
        if choice is None:
            return
        _SESSION["quick_fight"] = choice.as_dict()
        setup = MatchSetup(match_type=choice.mode, p1_char=choice.p1_char, p2_char=choice.p2_char,
                           difficulty=choice.difficulty, arena=choice.arena,
                           viewer=(choice.mode == AI_VS_AI))
        if _match_session(surface, clock, settings, player_id=player_id, setup=setup,
                          stop_on_character_select=True) != "character_select":
            return


def _ai_fight(surface, clock, settings, rules=None, player_id=None):
    """AI-vs-AI flow: pick two fighters and a difficulty, then watch.

    Classic rules use the telemetry viewer; Arena Rumble uses the fight screen.
    Only real stats returned by the match are saved.
    """
    name1 = _pick_fighter(surface, clock, is_p2=False)
    if name1 is None:
        return
    name2 = _pick_fighter(surface, clock, is_p2=True)
    if name2 is None:
        return
    difficulty = difficulty_select(surface, clock)
    if difficulty is None:
        return
    setup = MatchSetup(match_type=AI_VS_AI, p1_char=name1, p2_char=name2, difficulty=difficulty,
                       rules=rules, viewer=rules is None or not rules.is_rumble)
    _match_session(surface, clock, settings, player_id=player_id, rules=rules, setup=setup)


def _make_agent(name, player, difficulty="LOW", seed=None, adaptive=False):
    """Create an AI agent for the given fighter name."""
    from backend.ai.crimson import CrimsonAgent
    from backend.ai.steel import SteelAgent
    from backend.ai.shadow import ShadowAgent
    from backend.ai.golden import GoldenAgent
    from backend.ai.ghost import GhostAgent

    if seed is None:
        seed = random.randint(0, 999999)
    if name == "Random":
        return RandomAgent(player=player, seed=seed)
    if name == "Ghost":
        return GhostAgent(player=player, difficulty=difficulty, seed=seed)

    agent_classes = {
        "Crimson": CrimsonAgent,
        "Steel": SteelAgent,
        "Shadow": ShadowAgent,
        "Golden": GoldenAgent,
    }
    cls = agent_classes.get(name)
    if cls:
        from backend.ai.difficulty import DifficultyWrapper
        inner = cls(player=player, difficulty=difficulty, seed=seed)
        return DifficultyWrapper(inner, difficulty=difficulty, adaptive_difficulty=adaptive)
    return RandomAgent(player=player, seed=seed)


def _rules_from_settings(settings, base_rules=None):
    """Build ModeRules incorporating the user's Shield Wall balance configuration."""
    from backend.engine.rules import ModeRules
    from backend.engine.shield_config import PRESETS, clamp_shield_balance

    r = base_rules.copy() if base_rules is not None else ModeRules.classic()
    if settings.get("shield_enabled", False):
        r.enable_shield_wall = True
    r.shield_preset = settings.get("shield_preset", "Normal")
    r.same_shield_for_both = settings.get("shield_same_both", True)

    if r.shield_preset in PRESETS:
        r.shield_balance_p1 = PRESETS[r.shield_preset]
        r.shield_balance_p2 = PRESETS[r.shield_preset]
    else:
        p1_d = settings.get("shield_p1", {})
        p2_d = settings.get("shield_p2", p1_d)
        r.shield_balance_p1 = clamp_shield_balance(**p1_d) if p1_d else PRESETS["Normal"]
        r.shield_balance_p2 = (
            r.shield_balance_p1 if r.same_shield_for_both
            else (clamp_shield_balance(**p2_d) if p2_d else PRESETS["Normal"])
        )
    return r


# ----------------------------------------------------------------------
# Campaign, tutorial, upgrades
# ----------------------------------------------------------------------
CAMPAIGN_RESULT_LABELS = ("Retry Battle", "Campaign Map", "Main Menu")


def _record_campaign_win(player_id, b_id, battle, stats) -> None:
    camp_before = results_db.get_campaign_progress(player_id)
    already_cleared = b_id in set(camp_before.get("completed_battles", []))
    p1_rounds = stats.get("rounds_p1", 2)
    p2_rounds = stats.get("rounds_p2", 0)
    stars = 3 if p2_rounds == 0 else (2 if p1_rounds > p2_rounds else 1)
    results_db.save_campaign_battle_result(player_id, b_id, stars)
    if not already_cleared:
        results_db.add_coins(player_id, battle.get("reward_coins", 60))
    if b_id == 1:
        results_db.unlock_trophy(player_id, "campaign_start")
    elif b_id == 8:
        results_db.unlock_trophy(player_id, "campaign_champ")


def _campaign_flow(surface, clock, settings, player_id):
    """8-battle campaign. Results: Retry Battle / Campaign Map / Main Menu."""
    warrior = _pick_fighter(surface, clock, is_p2=False)
    if not warrior:
        return
    _SESSION["last_fighter"] = warrior
    retry_battle = None

    while True:
        b_id = retry_battle or campaign_map_screen(surface, clock, player_id, warrior)
        is_retry = retry_battle is not None
        retry_battle = None
        if b_id is None:
            return

        battle = get_battle(b_id)
        if not is_retry and not story_screen(surface, clock, battle, warrior):
            continue

        agent2 = _make_agent(battle["opponent"], player=2, difficulty=battle["difficulty"])
        human = _HumanAgent(name="Player", player=1, character=warrior)
        p1_lvl = results_db.get_character_level(player_id, warrior)
        p2_lvl = max(1, p1_lvl + battle.get("level_offset", 0))
        stats = run_fight(
            surface, clock, human, agent2, human_player=1,
            speed_mult=settings.get("speed", 1.0), arena_name=battle["arena"],
            rules=_rules_from_settings(settings, None),
            p1_level=p1_lvl, p2_level=p2_lvl, p1_regen=True, player_id=player_id,
            settings=settings,
        )
        if not isinstance(stats, dict):
            continue  # quit mid-fight: back to the map

        if stats.get("winner_side") == 1:
            _record_campaign_win(player_id, b_id, battle, stats)
        action = results_screen(surface, clock, stats, button_labels=CAMPAIGN_RESULT_LABELS)
        if action == "rematch":
            retry_battle = b_id
        elif action == "menu":
            return
        # "character_select" (Campaign Map) -> loop back to the map


def _tutorial_flow(surface, clock):
    """Run the interactive Tutorial Room."""
    warrior = _pick_fighter(surface, clock, is_p2=False)
    if warrior:
        run_tutorial(surface, clock, warrior)


def _upgrades_flow(surface, clock, player_id, fighter=None):
    """Upgrade station; opens on the given / last played fighter (Left/Right switches)."""
    upgrade_screen(surface, clock, player_id, fighter or _SESSION.get("last_fighter") or ALL_FIGHTERS[0])


if __name__ == "__main__":
    main()
