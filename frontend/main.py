"""Arena-AI: main entry point.

Run with:  uv run python -m frontend.main
"""

import random
import sys

import pygame

from backend.ai.base_agent import Agent
from backend.ai.config_check import check_settings
from backend.ai.personalities import ALL_PERSONALITIES
from backend.ai.random_agent import RandomAgent
from frontend.colours import SCREEN_HEIGHT, SCREEN_WIDTH
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
    difficulty_select,
    fighter_hq_menu,
    intro_screen,
    main_menu,
    manual_screen,
    match_type_select,
    model_insights_screen,
    mode_select,
    options_info_menu,
    player_name_prompt,
    results_screen,
    rumble_menu,
    settings_screen,
    statistics_screen,
)
from frontend.tutorial import run_tutorial


def main():
    """Start the game."""
    # Check AI settings before anything else
    check_settings()

    pygame.init()
    surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Arena-AI")
    clock = pygame.time.Clock()

    # Game settings (saved across menus, persist between matches)
    settings = {
        "log_fights": False,
        "speed": 1.0,
        "show_ai": True,
        "master_volume": 1.0,
        "sfx_volume": 0.8,
        "music_volume": 0.6,
        "is_muted": False,
    }
    audio.update_volume(
        master=settings["master_volume"],
        sfx=settings["sfx_volume"],
        music=settings["music_volume"],
        muted=settings["is_muted"],
    )

    # Show the intro screen once
    intro_screen(surface, clock)

    # Player profile (prompt on first launch)
    default_player = results_db.get_default_player()
    if default_player is None:
        p_name = player_name_prompt(surface, clock)
        player_id = results_db.get_or_create_player(p_name)
    else:
        player_id = int(default_player["player_id"])

    # Main game loop: keep going back to the menu until the player quits
    while True:
        choice = main_menu(surface, clock)

        if choice == "quit":
            break

        elif choice == "intro":
            intro_screen(surface, clock)

        elif choice == "campaign":
            _campaign_flow(surface, clock, settings, player_id=player_id)

        elif choice == "start":
            setup = None
            while True:
                result = _start_match(
                    surface, clock, settings, player_id=player_id, rules=None, setup=setup
                )
                setup = result.setup
                if setup is None:
                    break
                if result == "rematch":
                    continue
                elif result == "new_random":
                    setup = dict(setup, p2_char=random.choice(ALL_FIGHTERS))
                elif result == "character_select":
                    setup = {"match_type": setup["match_type"], "rules": setup.get("rules")}
                else:
                    break

        elif choice == "tutorial":
            _tutorial_flow(surface, clock)

        elif choice == "upgrades":
            _upgrades_flow(surface, clock, player_id=player_id)

        elif choice == "missions":
            missions_screen(surface, clock, player_id)

        elif choice == "trophies":
            trophy_room_screen(surface, clock, player_id)

        elif choice == "ai_fight":
            _ai_fight(surface, clock, settings, rules=None)

        elif choice == "insights":
            model_insights_screen(surface, clock)

        elif choice == "settings":
            settings = settings_screen(surface, clock, settings)

        elif choice == "statistics":
            statistics_screen(surface, clock, player_id=player_id)

        elif choice == "manual":
            manual_screen(surface, clock)

        elif choice == "rumble":
            rules, match_type = rumble_menu(surface, clock)
            if rules is not None and match_type is not None:
                if match_type in ("me_vs_ai", "human_vs_ai"):
                    _match_session(surface, clock, settings, player_id=player_id, rules=rules)
                else:
                    _ai_fight(surface, clock, settings, rules=rules)

        # Backward compatibility if sub-menus are invoked
        elif choice == "hq":
            while True:
                hq_choice = fighter_hq_menu(surface, clock)
                if hq_choice == "back" or hq_choice is None:
                    break
                elif hq_choice == "upgrades":
                    _upgrades_flow(surface, clock, player_id=player_id)
                elif hq_choice == "missions":
                    missions_screen(surface, clock, player_id)
                elif hq_choice == "trophies":
                    trophy_room_screen(surface, clock, player_id)
                elif hq_choice == "statistics":
                    statistics_screen(surface, clock, player_id=player_id)

        elif choice == "options":
            while True:
                opt_choice = options_info_menu(surface, clock)
                if opt_choice == "back" or opt_choice is None:
                    break
                elif opt_choice == "settings":
                    settings = settings_screen(surface, clock, settings)
                elif opt_choice == "manual":
                    manual_screen(surface, clock)
                elif opt_choice == "insights":
                    model_insights_screen(surface, clock)

        elif choice == "rumble":
            rules, match_type = rumble_menu(surface, clock)
            if rules is not None and match_type is not None:
                if match_type in ("me_vs_ai", "human_vs_ai"):
                    _match_session(surface, clock, settings, player_id=player_id, rules=rules)
                else:
                    _ai_fight(surface, clock, settings, rules=rules)

        elif choice == "ai_fight":
            _ai_fight(surface, clock, settings, rules=None)

    pygame.quit()
    sys.exit()


ALL_FIGHTERS = ["Crimson", "Steel", "Shadow", "Golden"]

# What _start_match can report back to its caller after ONE match.
MATCH_RESULTS = ("rematch", "new_random", "character_select", "menu")

_HUMAN_VS_PICKED = ("me_vs_ai", "human_vs_selected")
_HUMAN_VS_RANDOM = ("random_ai", "human_vs_random")


class MatchResult(str):
    """Return value of _start_match: compares equal to the action string
    ('rematch', 'new_random', 'character_select', 'menu'), carries `.setup`
    and `.rules`, and also supports `result, setup = _start_match(...)`.
    """

    def __new__(cls, action: str, setup=None):
        obj = super().__new__(cls, action)
        obj.action = action
        obj.setup = setup
        obj.rules = setup.get("rules") if isinstance(setup, dict) else None
        return obj

    def __iter__(self):
        yield str(self)
        yield self.setup


class _HumanAgent(Agent):
    """Placeholder agent for the human player (real input is read in run_fight)."""

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


def _pick_fighter(surface, clock, is_p2):
    """Run character select once. Returns a fighter name, or None if cancelled."""
    choice = character_select(surface, clock, is_p2=is_p2)
    if choice is None:
        return None
    if choice == "Random":
        choice = random.choice(ALL_FIGHTERS)
    return choice


def _choose_match_setup(surface, clock, settings, rules=None, match_type=None):
    """Ask the player what to play. Returns a setup dict, or None to go back.

    setup = {"match_type", "p1_char", "p2_char", "difficulty", "rules"}

    If match_type is given (after "character select"), the match-type screen is
    skipped the first time and the player only re-picks fighters/difficulty.
    """
    preset_type = match_type
    while True:
        match_type = preset_type or match_type_select(surface, clock)
        preset_type = None
        if match_type is None:
            return None

        if match_type == "rumble":
            r_rules, r_type = rumble_menu(surface, clock)
            if r_rules is not None and r_type is not None:
                if r_type in ("human_vs_ai", "me_vs_ai"):
                    # Keep the rumble rules and show the match-type screen again.
                    rules = r_rules
                    continue
                _ai_fight(surface, clock, settings, rules=r_rules)
            return None

        if match_type in _HUMAN_VS_PICKED or match_type == "ai_vs_ai":
            p1_char = _pick_fighter(surface, clock, is_p2=False)
            if p1_char is None:
                continue
            p2_char = _pick_fighter(surface, clock, is_p2=True)
            if p2_char is None:
                continue
        elif match_type in _HUMAN_VS_RANDOM:
            p1_char = _pick_fighter(surface, clock, is_p2=False)
            if p1_char is None:
                continue
            # Opponent is chosen RANDOMLY in Random AI mode
            p2_char = random.choice(ALL_FIGHTERS)
        else:
            continue  # unknown match type: ask again

        difficulty = difficulty_select(surface, clock)
        if difficulty is None:
            continue

        return {
            "match_type": match_type,
            "p1_char": p1_char,
            "p2_char": p2_char,
            "difficulty": difficulty,
            "rules": rules,
        }


def _setup_is_complete(setup):
    return bool(setup) and all(
        setup.get(k) for k in ("match_type", "p1_char", "p2_char", "difficulty")
    )


def _start_match(surface, clock, settings, player_id=None, rules=None, setup=None):
    """Play exactly ONE match (it never calls itself).

    Returns MatchResult(result, setup):
      result is one of MATCH_RESULTS: "rematch", "new_random",
              "character_select" or "menu".
      setup  holds everything needed to start the same match again
              (match type, fighters, difficulty and the rules).

    The caller (main / _match_session) runs the rematch loop.
    """
    # Set active_rules once at the very top of _start_match for every branch.
    active_rules = rules if rules is not None else _rules_from_settings(settings, None)
    if setup and setup.get("rules") is not None:
        active_rules = setup["rules"]

    # Step 1: find out what to play (menus) unless the caller already knows.
    if not _setup_is_complete(setup):
        preset_type = setup.get("match_type") if setup else None
        setup = _choose_match_setup(
            surface, clock, settings, rules=active_rules, match_type=preset_type
        )
        if setup is None:
            return MatchResult("menu", None)
        if setup.get("rules") is not None:
            active_rules = setup["rules"]

    setup = dict(setup, rules=active_rules)
    match_type = setup["match_type"]
    p1_char = setup["p1_char"]
    p2_char = setup["p2_char"]
    difficulty = setup["difficulty"]
    speed = settings.get("speed", 1.0)
    is_ai_vs_ai = (match_type == "ai_vs_ai")
    mode_name = "AI vs AI" if is_ai_vs_ai else "Human vs AI"
    p1_kind = "ai" if is_ai_vs_ai else "human"
    p1_difficulty = difficulty if is_ai_vs_ai else "LOW"
    human_player = None if is_ai_vs_ai else 1
    p1_regen = not is_ai_vs_ai
    p1_lvl = (
        1
        if (is_ai_vs_ai or not player_id)
        else results_db.get_character_level(player_id, p1_char)
    )

    # Step 2: build the two sides and play the match.
    agent1 = (
        _make_agent(p1_char, player=1, difficulty=difficulty)
        if is_ai_vs_ai
        else _HumanAgent(name="Player", player=1, character=p1_char)
    )
    agent2 = _make_agent(p2_char, player=2, difficulty=difficulty)
    stats = run_fight(
        surface, clock, agent1, agent2, human_player=human_player,
        speed_mult=speed, rules=active_rules,
        p1_level=p1_lvl, p2_level=p1_lvl,
        p1_regen=p1_regen, player_id=player_id,
    )

    # Step 3: the player quit in the middle of the match.
    if stats == "quit":
        abandoned = {
            "mode": mode_name,
            "p1_kind": p1_kind,
            "p1_character": p1_char,
            "p1_difficulty": p1_difficulty,
            "p2_kind": "ai",
            "p2_character": p2_char,
            "p2_difficulty": difficulty,
            "winner_side": 0,
            "rounds_p1": 0,
            "rounds_p2": 0,
            "duration_s": 0.0,
            "arena": "arena_neon_rooftop.jpeg",
            "player_id": player_id,
            "status": "abandoned",
            "shield_enabled": active_rules.enable_shield_wall,
            "shield_preset": active_rules.shield_preset,
            "shield_balance": {
                "p1_hp": active_rules.shield_balance_p1.shield_hp,
                "p2_hp": active_rules.shield_balance_p2.shield_hp,
            },
            "rounds_history": [],
        }
        results_db.save_match(abandoned)
        return MatchResult("menu", setup)

    # Step 4: match finished: save it and show the results screen.
    stats["mode"] = mode_name
    stats["player_id"] = player_id
    stats["status"] = "finished"
    stats["shield_enabled"] = active_rules.enable_shield_wall
    stats["shield_preset"] = active_rules.shield_preset
    stats["shield_balance"] = {
        "p1_hp": active_rules.shield_balance_p1.shield_hp,
        "p2_hp": active_rules.shield_balance_p2.shield_hp,
    }
    results_db.save_match(stats)

    action = results_screen(surface, clock, stats)

    if settings.get("log_fights", False):
        _log_fight_stub()

    if action not in MATCH_RESULTS:
        action = "menu"
    return MatchResult(action, setup)


def _match_session(surface, clock, settings, player_id=None, rules=None):
    """Play matches one after another until the player goes back to the menu.

    This is the loop that used to be hidden inside _start_match (as recursion).
    """
    setup = None
    while True:
        result, setup = _start_match(
            surface, clock, settings, player_id=player_id, rules=rules, setup=setup
        )
        if setup is None:
            return result
        if result == "rematch":
            continue  # same fighters, same rules
        elif result == "new_random":
            setup = dict(setup, p2_char=random.choice(ALL_FIGHTERS))
        elif result == "character_select":
            # keep the match type + rules, pick fighters/difficulty again
            setup = {"match_type": setup["match_type"], "rules": setup.get("rules")}
        else:
            return result  # "menu"


def _ai_fight(surface, clock, settings, rules=None):
    """AI Model Fight flow: directly pick fighters & difficulty with NO 'vs ai' mode prompt."""
    from frontend.ai_viewer import run_ai_viewer

    while True:
        # Pick two AI fighters
        name1 = character_select(surface, clock, is_p2=False)
        if name1 is None:
            return
        if name1 == "Random":
            name1 = random.choice(["Crimson", "Steel", "Shadow", "Golden"])
        name2 = character_select(surface, clock, is_p2=True)
        if name2 is None:
            return
        if name2 == "Random":
            name2 = random.choice(["Crimson", "Steel", "Shadow", "Golden"])

        # Directly pick difficulty (NO match type / vs ai prompt!)
        difficulty = difficulty_select(surface, clock)
        if difficulty is None:
            return

        while True:
            agent1 = _make_agent(name1, player=1, difficulty=difficulty)
            agent2 = _make_agent(name2, player=2, difficulty=difficulty)

            speed = settings.get("speed", 1.0)
            if rules is not None and rules.is_rumble:
                res = run_fight(surface, clock, agent1, agent2, human_player=None, speed_mult=speed, rules=rules)
            else:
                res = run_ai_viewer(surface, clock, agent1, agent2, speed_mult=speed)

            if res == "quit":
                abandoned_ai = {
                    "mode": "AI vs AI",
                    "p1_kind": "ai",
                    "p1_character": name1,
                    "p1_difficulty": difficulty,
                    "p2_kind": "ai",
                    "p2_character": name2,
                    "p2_difficulty": difficulty,
                    "winner_side": 0,
                    "rounds_p1": 0,
                    "rounds_p2": 0,
                    "duration_s": 0.0,
                    "arena": "Sky Colosseum" if difficulty == "HELL" else "Neon Rooftop",
                    "status": "abandoned",
                    "rounds_history": [],
                }
                results_db.save_match(abandoned_ai)
                return

            if isinstance(res, dict):
                stats = res
                stats["mode"] = "AI vs AI"
                stats["p1_difficulty"] = difficulty
                stats["p2_difficulty"] = difficulty
            else:
                stats = {
                    "p1_name": agent1.name,
                    "p2_name": agent2.name,
                    "p1_character": name1,
                    "p2_character": name2,
                    "p1_kind": "ai",
                    "p2_kind": "ai",
                    "p1_difficulty": difficulty,
                    "p2_difficulty": difficulty,
                    "arena": "Sky Colosseum" if difficulty == "HELL" else "Neon Rooftop",
                    "damage_dealt_p1": 1.0 if res == "p1" else 0.5,
                    "damage_dealt_p2": 1.0 if res == "p2" else 0.5,
                    "hits_landed_p1": 6 if res == "p1" else 3,
                    "hits_landed_p2": 6 if res == "p2" else 3,
                    "blocks_p1": 2,
                    "blocks_p2": 2,
                    "longest_combo_p1": 2,
                    "longest_combo_p2": 2,
                    "winner_side": 1 if res == "p1" else (2 if res == "p2" else 0),
                    "rounds_p1": 2 if res == "p1" else 0,
                    "rounds_p2": 2 if res == "p2" else 0,
                    "duration_s": 25.0,
                    "status": "finished",
                    "mode": "AI vs AI",
                    "match_result": res,
                    "rounds_history": [
                        {"round_number": 1, "winner_side": 1 if res == "p1" else 2, "ended_by": "KO", "duration_s": 12.0, "p1_health_left": 0.35 if res == "p1" else 0.0, "p2_health_left": 0.35 if res == "p2" else 0.0},
                        {"round_number": 2, "winner_side": 1 if res == "p1" else 2, "ended_by": "KO", "duration_s": 13.0, "p1_health_left": 0.50 if res == "p1" else 0.0, "p2_health_left": 0.50 if res == "p2" else 0.0},
                    ],
            }

            results_db.save_match(stats)
            action = results_screen(surface, clock, stats)

            if action == "rematch":
                continue
            elif action == "character_select":
                break
            else:
                return


def _make_agent(name, player, difficulty="LOW", seed=None):
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

    # Map fighter names to their AI classes
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
        return DifficultyWrapper(inner, difficulty=difficulty)

    # Fallback to random
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


def _log_fight_stub():
    """Placeholder for fight logging — will be connected in M2 integration."""
    pass


def _campaign_flow(surface, clock, settings, player_id):
    """Run the 8-battle Campaign mode with dark-fantasy lore and progressive scaling."""
    warrior = character_select(surface, clock, is_p2=False)
    if not warrior:
        return
    if warrior == "Random":
        warrior = random.choice(["Crimson", "Steel", "Shadow", "Golden"])

    while True:
        b_id = campaign_map_screen(surface, clock, player_id, warrior)
        if b_id is None:
            return

        battle = get_battle(b_id)
        proceed = story_screen(surface, clock, battle, warrior)
        if not proceed:
            continue

        opp_char = battle["opponent"]
        diff = battle["difficulty"]
        agent2 = _make_agent(opp_char, player=2, difficulty=diff)

        from backend.ai.base_agent import Agent

        class HumanAgent(Agent):
            def __init__(self, name="Player", player=1, character="Golden"):
                super().__init__(name=name, player=player, difficulty="LOW", personality=ALL_PERSONALITIES.get(character))
                self.character_name = character

            def choose_action(self, state):
                return None, {}

        human = HumanAgent(name="Player", player=1, character=warrior)
        speed = settings.get("speed", 1.0)

        p1_lvl = results_db.get_character_level(player_id, warrior)
        p2_lvl = max(1, p1_lvl + battle.get("level_offset", 0))

        active_rules = _rules_from_settings(settings, None)
        stats = run_fight(
            surface, clock, human, agent2, human_player=1,
            speed_mult=speed, arena_name=battle["arena"], rules=active_rules,
            p1_level=p1_lvl, p2_level=p2_lvl, p1_regen=True, player_id=player_id,
        )

        if stats != "quit":
            if stats.get("winner_side") == 1:
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

            results_screen(surface, clock, stats)


def _tutorial_flow(surface, clock):
    """Run interactive Tutorial Room."""
    warrior = character_select(surface, clock, is_p2=False)
    if not warrior:
        return
    if warrior == "Random":
        warrior = random.choice(["Crimson", "Steel", "Shadow", "Golden"])
    run_tutorial(surface, clock, warrior)


def _upgrades_flow(surface, clock, player_id):
    """Run warrior upgrades station."""
    upgrade_screen(surface, clock, player_id, "Golden")


if __name__ == "__main__":
    main()
