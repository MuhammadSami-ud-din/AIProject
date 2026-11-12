"""Turns move scores into one chosen move, with variety, mistakes and confidence."""

import math

from backend.ai.actions import Action

MISTAKE_POOL = 3   # a mistake picks one of the next best moves, up to the 3rd best


def ranked(scores):
    """Moves sorted from best score to worst."""
    _check_scores(scores)
    return sorted(scores, key=lambda action: scores[action], reverse=True)


def probabilities(scores, variety=0.0):
    """Turn scores into chances that add up to 1.

    variety 0   = the best move gets all the chance (ties share it)
    variety 1   = chances spread out a lot
    Used for picking AND for the "confidence" shown on screen."""
    _check_scores(scores)
    _check_between_0_and_1("variety", variety)

    best = max(scores.values())
    worst = min(scores.values())

    if variety == 0 or best == worst:
        winners = [a for a, s in scores.items() if s == best]
        return {a: (1 / len(winners) if a in winners else 0.0) for a in scores}

    # Squeeze scores into 0..1 so the same variety works for any score size.
    spread = best - worst
    weights = {a: math.exp((s - best) / spread / variety) for a, s in scores.items()}
    total = sum(weights.values())
    return {a: w / total for a, w in weights.items()}


def top_choices(scores, variety=0.0, n=3):
    """The n most likely moves with their chances, best first.
    For the explanation panel: [(Action.LIGHT, 0.7), (Action.HEAVY, 0.2), ...]"""
    if n < 1:
        raise ValueError("n must be at least 1")
    chances = probabilities(scores, variety)
    best_first = sorted(chances, key=lambda action: chances[action], reverse=True)
    return [(action, chances[action]) for action in best_first[:n]]


def pick(scores, rng, variety=0.0, mistake_chance=0.0):
    """Choose one move from the scores.

    variety         comes from the fighter's card (personality)
    mistake_chance  comes from the difficulty level (Low = often, Hell = almost never)
    rng             the fighter's own random generator, so fights can be repeated"""
    _check_between_0_and_1("mistake_chance", mistake_chance)
    order = ranked(scores)

    # Human-like mistake: not a random move, but a slightly worse one.
    if len(order) > 1 and rng.random() < mistake_chance:
        return rng.choice(order[1:MISTAKE_POOL])

    chances = probabilities(scores, variety)
    moves = list(chances)
    return rng.choices(moves, weights=[chances[m] for m in moves])[0]


# ---------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------
def _check_scores(scores):
    if not scores:
        raise ValueError("scores is empty: there must be at least one move to pick")
    for action, score in scores.items():
        if not isinstance(action, Action):
            raise TypeError(f"{action!r} is not a move. Use Action.LIGHT, not 'LIGHT'")
        if not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError(f"score for {action.name} must be a normal number, got {score!r}")


def _check_between_0_and_1(name, value):
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")
