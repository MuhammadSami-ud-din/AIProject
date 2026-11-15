"""Arena-AI: main entry point.

Run with:  uv run python -m frontend.main
"""

import random
import sys

import pygame

from backend.ai.config_check import check_settings
from backend.ai.personalities import ALL_PERSONALITIES
from backend.ai.random_agent import RandomAgent
from frontend.colours import SCREEN_HEIGHT, SCREEN_WIDTH
from backend.data.results_db import results_db
from frontend.fight_screen import run_fight
from frontend.screens import (
    character_select,
    difficulty_select,
    intro_screen,
    main_menu,
    manual_screen,
    match_type_select,
    mode_select,
    player_name_prompt,
    results_screen,
    settings_screen,
    statistics_screen,
)


def main():
    """Start the game."""
    # Check AI settings before anything else
    check_settings()

    pygame.init()
    surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Arena-AI")
    clock = pygame.time.Clock()

    # Game settings (saved across menus, persist between matches)
    settings = {"log_fights": False, "speed": 1.0, "show_ai": True}

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

        elif choice == "settings":
            settings = settings_screen(surface, clock, settings)

        elif choice == "statistics":
            statistics_screen(surface, clock, player_id=player_id)

        elif choice == "manual":
            manual_screen(surface, clock)

        elif choice == "start":
            _start_match(surface, clock, settings, player_id=player_id)

        elif choice == "ai_fight":
            _ai_fight(surface, clock, settings)

    pygame.quit()
    sys.exit()


def _start_match(surface, clock, settings, player_id=None):
    """Start match flow: pick mode first, then choose fighters/difficulty with respect to that."""
    from backend.ai.base_agent import Agent

    while True:
        # Step 1: First choose match type ("Me vs AI", "Random AI", or "AI vs AI")
        match_type = match_type_select(surface, clock)
        if match_type is None:
            return

        if match_type in ("me_vs_ai", "human_vs_selected"):
            # Step 2: Choose player character (P1)
            p1_char = character_select(surface, clock, is_p2=False)
            if p1_char is None:
                continue

            # Step 3: Choose AI opponent character (P2)
            p2_char = character_select(surface, clock, is_p2=True)
            if p2_char is None:
                continue

            # Step 4: Choose difficulty
            difficulty = difficulty_select(surface, clock)
            if difficulty is None:
                continue

            # Rematch loop for Me vs AI
            while True:
                agent2 = _make_agent(p2_char, player=2, difficulty=difficulty)

                class HumanAgent(Agent):
                    def __init__(self, name="Player", player=1, character="Golden"):
                        super().__init__(name=name, player=player, difficulty="LOW")
                        self.character_name = character

                    def choose_action(self, state):
                        return None, {}

                human = HumanAgent(name="Player", player=1, character=p1_char)

                speed = settings.get("speed", 1.0)
                stats = run_fight(surface, clock, human, agent2, human_player=1, speed_mult=speed)

                if stats == "quit":
                    abandoned_data = {
                        "mode": "Human vs AI",
                        "p1_kind": "human",
                        "p1_character": p1_char,
                        "p1_difficulty": "LOW",
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
                        "rounds_history": [],
                    }
                    results_db.save_match(abandoned_data)
                    return

                stats["mode"] = "Human vs AI"
                stats["player_id"] = player_id
                stats["status"] = "finished"
                results_db.save_match(stats)

                action = results_screen(surface, clock, stats)

                if settings.get("log_fights", False):
                    _log_fight_stub()

                if action == "rematch":
                    continue
                elif action == "character_select":
                    break
                else:
                    return

        elif match_type in ("random_ai", "human_vs_random"):
            # Step 2: Choose player character (P1)
            p1_char = character_select(surface, clock, is_p2=False)
            if p1_char is None:
                continue

            # Opponent is chosen RANDOMLY with respect to Random AI mode
            all_chars = ["Crimson", "Steel", "Shadow", "Golden"]
            p2_char = random.choice(all_chars)

            # Step 3: Choose difficulty
            difficulty = difficulty_select(surface, clock)
            if difficulty is None:
                continue

            # Rematch loop for Random AI
            while True:
                agent2 = _make_agent(p2_char, player=2, difficulty=difficulty)

                class HumanAgent(Agent):
                    def __init__(self, name="Player", player=1, character="Golden"):
                        super().__init__(name=name, player=player, difficulty="LOW")
                        self.character_name = character

                    def choose_action(self, state):
                        return None, {}

                human = HumanAgent(name="Player", player=1, character=p1_char)

                speed = settings.get("speed", 1.0)
                stats = run_fight(surface, clock, human, agent2, human_player=1, speed_mult=speed)

                if stats == "quit":
                    abandoned_data = {
                        "mode": "Human vs AI",
                        "p1_kind": "human",
                        "p1_character": p1_char,
                        "p1_difficulty": "LOW",
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
                        "rounds_history": [],
                    }
                    results_db.save_match(abandoned_data)
                    return

                stats["mode"] = "Human vs AI"
                stats["player_id"] = player_id
                stats["status"] = "finished"
                results_db.save_match(stats)

                action = results_screen(surface, clock, stats)

                if settings.get("log_fights", False):
                    _log_fight_stub()

                if action == "rematch":
                    continue
                elif action == "character_select":
                    break
                else:
                    return

        elif match_type == "ai_vs_ai":
            # AI vs AI battle: Two autonomous AIs playing, NOT the user!
            p1_char = character_select(surface, clock, is_p2=False)
            if p1_char is None:
                continue

            p2_char = character_select(surface, clock, is_p2=True)
            if p2_char is None:
                continue

            difficulty = difficulty_select(surface, clock)
            if difficulty is None:
                continue

            while True:
                agent1 = _make_agent(p1_char, player=1, difficulty=difficulty)
                agent2 = _make_agent(p2_char, player=2, difficulty=difficulty)

                speed = settings.get("speed", 1.0)
                # human_player=None means TWO AIs playing, user does NOT play!
                stats = run_fight(surface, clock, agent1, agent2, human_player=None, speed_mult=speed)

                if stats == "quit":
                    abandoned_ai = {
                        "mode": "AI vs AI",
                        "p1_kind": "ai",
                        "p1_character": p1_char,
                        "p1_difficulty": difficulty,
                        "p2_kind": "ai",
                        "p2_character": p2_char,
                        "p2_difficulty": difficulty,
                        "winner_side": 0,
                        "rounds_p1": 0,
                        "rounds_p2": 0,
                        "duration_s": 0.0,
                        "arena": "arena_neon_rooftop.jpeg",
                        "status": "abandoned",
                        "rounds_history": [],
                    }
                    results_db.save_match(abandoned_ai)
                    return

                stats["mode"] = "AI vs AI"
                stats["status"] = "finished"
                results_db.save_match(stats)

                action = results_screen(surface, clock, stats)

                if action == "rematch":
                    continue
                elif action == "character_select":
                    break
                else:
                    return


def _ai_fight(surface, clock, settings):
    """AI Model Fight flow: directly pick fighters & difficulty with NO 'vs ai' mode prompt."""
    from frontend.ai_viewer import run_ai_viewer

    while True:
        # Pick two AI fighters
        name1 = character_select(surface, clock, is_p2=False)
        if name1 is None:
            return
        name2 = character_select(surface, clock, is_p2=True)
        if name2 is None:
            return

        # Directly pick difficulty (NO match type / vs ai prompt!)
        difficulty = difficulty_select(surface, clock)
        if difficulty is None:
            return

        while True:
            agent1 = _make_agent(name1, player=1, difficulty=difficulty)
            agent2 = _make_agent(name2, player=2, difficulty=difficulty)

            # Use the AI viewer with the speed from settings
            speed = settings.get("speed", 1.0)
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
        return cls(player=player, difficulty=difficulty, seed=seed)

    # Fallback to random
    return RandomAgent(player=player, seed=seed)


def _log_fight_stub():
    """Placeholder for fight logging — will be connected in M2 integration."""
    pass


if __name__ == "__main__":
    main()
