"""Ablation study: measure how much each feature contributes.

Turns off one feature at a time (search, opponent model, learned policy)
and measures the win-rate drop. Also runs a binomial test to confirm
that harder difficulties win more.
"""

import math

from backend.ai.crimson import CrimsonAgent
from backend.ai.difficulty import DifficultyWrapper
from backend.ai.random_agent import RandomAgent
from backend.data.match_runner import run_match


def ablation_study(fighter_name="Crimson", difficulty="HIGH",
                   matches_per_config=20, seed=0):
    """Run matches with each feature toggled off.

    Returns a dict like:
      {
        "baseline":            0.85,  # all features on
        "no_search":           0.70,  # search off
        "no_opponent_model":   0.75,  # opponent model off
        "no_learned_policy":   0.80,  # learned policy off
      }
    Each value is the win rate against RandomAgent.
    """
    from backend.ai.crimson import CrimsonAgent
    from backend.ai.steel import SteelAgent
    from backend.ai.shadow import ShadowAgent
    from backend.ai.golden import GoldenAgent

    # Map fighter names to classes
    classes = {
        "Crimson": CrimsonAgent,
        "Steel": SteelAgent,
        "Shadow": ShadowAgent,
        "Golden": GoldenAgent,
    }
    fighter_cls = classes.get(fighter_name, CrimsonAgent)

    configs = {
        "baseline":          {"use_search": True,  "use_opponent_model": True,  "use_learned_policy": True},
        "no_search":         {"use_search": False, "use_opponent_model": True,  "use_learned_policy": True},
        "no_opponent_model": {"use_search": True,  "use_opponent_model": False, "use_learned_policy": True},
        "no_learned_policy": {"use_search": True,  "use_opponent_model": True,  "use_learned_policy": False},
    }

    results = {}

    for config_name, switches in configs.items():
        wins = 0
        for i in range(matches_per_config):
            # Create the fighter with the difficulty wrapper
            inner = fighter_cls(player=1, difficulty=difficulty, seed=seed + i)
            wrapped = DifficultyWrapper(inner, difficulty=difficulty)

            # Apply the switches
            wrapped.use_search = switches["use_search"]
            wrapped.use_opponent_model = switches["use_opponent_model"]
            wrapped.use_learned_policy = switches["use_learned_policy"]

            # Create the opponent
            opp = RandomAgent(player=2, seed=seed + i + 5000)

            result = run_match(wrapped, opp, seed=seed + i)
            if result["match_result"] == "p1":
                wins += 1

        results[config_name] = wins / matches_per_config

    return results


def binomial_test(wins, total, expected_rate=0.5):
    """One-sided binomial test: is the win rate significantly above expected?

    Uses the normal approximation to the binomial distribution.
    Returns (win_rate, z_score, p_value).
    A p_value < 0.05 means the fighter is significantly better than chance.
    """
    if total == 0:
        return 0.0, 0.0, 1.0

    rate = wins / total
    # Standard error under the null hypothesis
    se = math.sqrt(expected_rate * (1 - expected_rate) / total)
    if se == 0:
        return rate, 0.0, 1.0

    z = (rate - expected_rate) / se

    # Approximate p-value using the error function
    # P(Z > z) for one-sided test
    p_value = 0.5 * (1 - _erf(z / math.sqrt(2)))

    return rate, z, p_value


def _erf(x):
    """Approximation of the error function for p-value computation.

    Uses the Abramowitz and Stegun approximation (formula 7.1.26).
    Good enough for our purposes — exact to about 1.5e-7.
    """
    # Constants for the approximation
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911

    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return sign * y


def difficulty_ordering_test(fighter_name="Crimson", matches_per_level=20, seed=0):
    """Verify that LOW < MEDIUM < HIGH < HELL win rates.

    Runs the fighter at each difficulty against RandomAgent,
    then checks each consecutive pair with a binomial test.

    Returns a dict like:
      {
        "rates": {"LOW": 0.6, "MEDIUM": 0.75, "HIGH": 0.90, "HELL": 0.95},
        "ordering_correct": True,
        "tests": [
            {"pair": "LOW<MEDIUM", "p_value": 0.03, "significant": True},
            ...
        ]
      }
    """
    from backend.data.statistics import difficulty_ranking

    rates = difficulty_ranking(fighter_name, matches_per_difficulty=matches_per_level)

    # Check ordering
    levels = ["LOW", "MEDIUM", "HIGH", "HELL"]
    ordering_correct = all(
        rates[levels[i]] <= rates[levels[i + 1]]
        for i in range(len(levels) - 1)
    )

    # Pairwise binomial tests
    tests = []
    for i in range(len(levels) - 1):
        lower = levels[i]
        higher = levels[i + 1]
        wins_higher = int(rates[higher] * matches_per_level)
        wins_lower = int(rates[lower] * matches_per_level)

        # Is the higher difficulty significantly better?
        _, z, p = binomial_test(wins_higher, matches_per_level,
                                expected_rate=rates[lower])
        tests.append({
            "pair": f"{lower}<{higher}",
            "rate_lower": rates[lower],
            "rate_higher": rates[higher],
            "z_score": z,
            "p_value": p,
            "significant": p < 0.05,
        })

    return {
        "rates": rates,
        "ordering_correct": ordering_correct,
        "tests": tests,
    }
