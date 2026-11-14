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
from frontend.fight_screen import run_fight
from frontend.screens import (
    character_select,
    intro_screen,
    main_menu,
    mode_select,
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

    # Game settings (saved across menus)
    settings = {"log_fights": False}

    # Show the intro screen once
    intro_screen(surface, clock)

    # Main game loop: keep going back to the menu until the player quits
    while True:
        choice = main_menu(surface, clock)

        if choice == "quit":
            break

        elif choice == "settings":
            settings = settings_screen(surface, clock, settings)

        elif choice == "statistics":
            statistics_screen(surface, clock)

        elif choice == "start":
            _start_match(surface, clock, settings)

        elif choice == "ai_fight":
            _ai_fight(surface, clock)

    pygame.quit()
    sys.exit()


def _start_match(surface, clock, settings):
    """Human vs AI match flow."""
    # Pick an opponent
    fighter_name = character_select(surface, clock)
    if fighter_name is None:
        return

    # Pick match type and difficulty
    match_type, difficulty = mode_select(surface, clock)
    if match_type is None:
        return

    # Create the AI agent
    agent2 = _make_agent(fighter_name, player=2, difficulty=difficulty)

    # Human is always player 1, using Golden as default
    # (In a full version, the human would pick their character too)
    from backend.ai.base_agent import Agent

    # Create a dummy agent for player 1 (human-controlled, won't be used for decisions)
    class HumanAgent(Agent):
        def choose_action(self, state):
            return None, {}  # never called — input_handler is used instead

    human = HumanAgent(name="Player", player=1, difficulty="LOW")

    # Run the fight
    result = run_fight(surface, clock, human, agent2, human_player=1)

    if result != "quit":
        p1_name = "Player"
        p2_name = agent2.name
        results_screen(surface, clock, result, p1_name, p2_name)

        # Save fight log if enabled
        if settings["log_fights"]:
            _log_fight_stub()


def _ai_fight(surface, clock):
    """AI vs AI match flow with full AI thinking display."""
    from frontend.ai_viewer import run_ai_viewer

    # Pick two fighters
    name1 = character_select(surface, clock)
    if name1 is None:
        return
    name2 = character_select(surface, clock)
    if name2 is None:
        return

    _, difficulty = mode_select(surface, clock)
    if difficulty is None:
        return

    agent1 = _make_agent(name1, player=1, difficulty=difficulty)
    agent2 = _make_agent(name2, player=2, difficulty=difficulty)

    # Use the AI viewer instead of the normal fight screen
    result = run_ai_viewer(surface, clock, agent1, agent2)

    if result != "quit":
        results_screen(surface, clock, result, agent1.name, agent2.name)


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
