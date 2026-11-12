"""Round-robin tournament, Elo ratings, and win rate statistics.

Runs every fighter against every other fighter at every difficulty.
Computes Elo ratings, win rates with confidence intervals, and
checks that harder difficulties win more.
"""

import math
from collections import defaultdict

from backend.ai.crimson import CrimsonAgent
from backend.ai.golden import GoldenAgent
from backend.ai.random_agent import RandomAgent
from backend.ai.shadow import ShadowAgent
from backend.ai.steel import SteelAgent
from backend.data.match_runner import run_match

# Map fighter names to their agent classes
AGENT_CLASSES = {
    "Crimson": CrimsonAgent,
    "Steel": SteelAgent,
    "Shadow": ShadowAgent,
    "Golden": GoldenAgent,
    "Random": RandomAgent,
}

FIGHTER_NAMES = ["Crimson", "Steel", "Shadow", "Golden"]

# Elo settings
ELO_START = 1000
ELO_K = 32


def run_round_robin(fighters=None, difficulties=None, matches_per_pair=10):
    """Run every fighter against every other fighter.

    Returns a list of result dicts with keys:
      fighter1, fighter2, difficulty, wins1, wins2, draws
    """
    if fighters is None:
        fighters = FIGHTER_NAMES
    if difficulties is None:
        difficulties = ["LOW"]

    results = []

    for difficulty in difficulties:
        for i, name1 in enumerate(fighters):
            for name2 in fighters[i + 1:]:
                wins1 = 0
                wins2 = 0
                draws = 0

                for seed in range(matches_per_pair):
                    a1 = _make_agent(name1, 1, difficulty, seed * 1000)
                    a2 = _make_agent(name2, 2, difficulty, seed * 1000 + 500)
                    result = run_match(a1, a2, seed=seed)

                    if result["match_result"] == "p1":
                        wins1 += 1
                    elif result["match_result"] == "p2":
                        wins2 += 1
                    else:
                        draws += 1

                results.append({
                    "fighter1": name1,
                    "fighter2": name2,
                    "difficulty": difficulty,
                    "wins1": wins1,
                    "wins2": wins2,
                    "draws": draws,
                    "total": matches_per_pair,
                })

    return results


def compute_elo(results):
    """Compute Elo ratings from round-robin results.

    Returns a dict like {"Crimson": 1050, "Steel": 980, ...}
    """
    ratings = defaultdict(lambda: ELO_START)

    for r in results:
        name1 = r["fighter1"]
        name2 = r["fighter2"]

        # Process each match outcome
        for _ in range(r["wins1"]):
            _update_elo(ratings, name1, name2, 1.0)
        for _ in range(r["wins2"]):
            _update_elo(ratings, name1, name2, 0.0)
        for _ in range(r["draws"]):
            _update_elo(ratings, name1, name2, 0.5)

    return dict(ratings)


def _update_elo(ratings, name1, name2, score1):
    """Update Elo ratings for one match result.
    score1: 1.0 = name1 wins, 0.0 = name2 wins, 0.5 = draw.
    """
    r1 = ratings[name1]
    r2 = ratings[name2]

    # Expected scores
    e1 = 1.0 / (1.0 + 10 ** ((r2 - r1) / 400))
    e2 = 1.0 - e1

    ratings[name1] = r1 + ELO_K * (score1 - e1)
    ratings[name2] = r2 + ELO_K * ((1 - score1) - e2)


def win_rate_with_ci(wins, total, confidence=0.95):
    """Compute win rate and confidence interval using normal approximation.

    Returns (rate, lower, upper).
    """
    if total == 0:
        return 0.0, 0.0, 0.0

    rate = wins / total
    # 95% CI uses z = 1.96
    z = 1.96 if confidence == 0.95 else 1.645
    margin = z * math.sqrt(rate * (1 - rate) / total)

    return rate, max(0, rate - margin), min(1, rate + margin)


def difficulty_ranking(fighter_name, matches_per_difficulty=20):
    """Check that harder difficulties beat easier ones.

    Runs the same fighter at each difficulty against RandomAgent.
    Returns a dict like {"LOW": 0.6, "MEDIUM": 0.75, ...}
    """
    rates = {}

    for difficulty in ["LOW", "MEDIUM", "HIGH", "HELL"]:
        wins = 0
        for seed in range(matches_per_difficulty):
            agent = _make_agent(fighter_name, 1, difficulty, seed)
            random_opp = RandomAgent(player=2, seed=seed + 5000)
            result = run_match(agent, random_opp, seed=seed)
            if result["match_result"] == "p1":
                wins += 1
        rates[difficulty] = wins / matches_per_difficulty

    return rates


def _make_agent(name, player, difficulty="LOW", seed=None):
    """Create an agent for the given fighter name."""
    cls = AGENT_CLASSES.get(name)
    if cls is None or name == "Random":
        return RandomAgent(player=player, seed=seed)

    if name in ("Crimson", "Steel", "Shadow", "Golden"):
        return cls(player=player, difficulty=difficulty, seed=seed)

    return RandomAgent(player=player, seed=seed)
