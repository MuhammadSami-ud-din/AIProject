"""Personality tuning: hill climbing to find the best personality weights.

Runs headless matches to test different personality settings.
Uses hill climbing: try a small change, keep it if it wins more.

Also includes co-evolution: two fighters evolve against each other,
so neither one stays in a fixed strategy.
"""

import random

from backend.ai.personalities import Personality, mix, mutate, ALL_PERSONALITIES
from backend.data.match_runner import run_match


# Default settings
DEFAULT_TRIALS = 20        # matches per evaluation
DEFAULT_STEPS = 10         # how many hill-climbing steps


def evaluate_personality(personality, fighter_class, opponent_class,
                         trials=DEFAULT_TRIALS, seed=0):
    """Run several matches and return the win rate.

    fighter_class: the AI class to test (e.g. CrimsonAgent).
    opponent_class: who to fight against.
    trials: how many matches to run.
    seed: starting seed for reproducibility.

    Returns the fraction of matches won (0.0 to 1.0).
    """
    wins = 0
    for i in range(trials):
        # Create the fighter with the test personality
        agent1 = fighter_class(player=1, difficulty="LOW", seed=seed + i)
        # Override the personality for testing
        agent1.personality = personality

        agent2 = opponent_class(player=2, seed=seed + i + 1000)
        result = run_match(agent1, agent2, seed=seed + i)
        if result["match_result"] == "p1":
            wins += 1

    return wins / trials


def hill_climb(base_personality, fighter_class, opponent_class,
               steps=DEFAULT_STEPS, trials=DEFAULT_TRIALS, seed=42):
    """Improve a personality using hill climbing.

    Starts from base_personality. Each step:
      1. Mutate the personality slightly.
      2. Test both the old and new personality.
      3. Keep whichever wins more.

    Returns (best_personality, best_win_rate, history).
    history is a list of (step, win_rate) tuples for plotting.
    """
    rng = random.Random(seed)
    current = base_personality
    current_rate = evaluate_personality(current, fighter_class, opponent_class,
                                        trials, seed)
    history = [(0, current_rate)]

    for step_num in range(1, steps + 1):
        # Mutate: make a small random change
        candidate = mutate(current, rng, amount=0.5)

        # Evaluate the candidate
        candidate_rate = evaluate_personality(candidate, fighter_class,
                                              opponent_class, trials,
                                              seed + step_num * 1000)

        # Keep the better one
        if candidate_rate >= current_rate:
            current = candidate
            current_rate = candidate_rate

        history.append((step_num, current_rate))

    return current, current_rate, history


def co_evolve(personality1, fighter_class1, personality2, fighter_class2,
              generations=5, trials=DEFAULT_TRIALS, seed=42):
    """Two fighters evolve against each other.

    Each generation:
      1. Fighter 1 hill-climbs against the current fighter 2.
      2. Fighter 2 hill-climbs against the updated fighter 1.
    Neither stays in a fixed strategy.

    Returns (best_p1, best_p2, history).
    """
    rng = random.Random(seed)
    p1 = personality1
    p2 = personality2
    history = []

    for gen in range(generations):
        # Fighter 1 evolves against fighter 2
        # We need a wrapper that uses p2 as the opponent
        class Opp2:
            """Temporary opponent class with the current p2 personality."""
            def __init__(self, **kwargs):
                self._inner = fighter_class2(**kwargs)
                self._inner.personality = p2
            def __getattr__(self, name):
                return getattr(self._inner, name)

        p1, rate1, _ = hill_climb(p1, fighter_class1, fighter_class2,
                                   steps=3, trials=trials,
                                   seed=seed + gen * 10000)

        # Fighter 2 evolves against fighter 1
        p2, rate2, _ = hill_climb(p2, fighter_class2, fighter_class1,
                                   steps=3, trials=trials,
                                   seed=seed + gen * 10000 + 5000)

        history.append({
            "generation": gen,
            "p1_rate": rate1,
            "p2_rate": rate2,
        })

    return p1, p2, history
