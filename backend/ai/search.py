"""Minimax search with alpha-beta pruning for fighting games.

Fighting games are not turn-based, so we:
  1. Decide only every 6 frames (not every frame).
  2. Simulate 6 frames per ply with both actions applied together.
  3. Use iterative deepening with a 5 ms time budget.
  4. Use a COPY of the engine to look ahead, never the live game.
"""

import time

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.adapter import observation_for
from backend.ai.evaluation import evaluate
from backend.engine.step import step


# How many frames to simulate per ply (one "turn" = 6 frames)
FRAMES_PER_PLY = 6

# Time budget for search in seconds
SEARCH_BUDGET_MS = 5
SEARCH_BUDGET_S = SEARCH_BUDGET_MS / 1000


def search_best_action(state, player, personality, max_depth=3):
    """Find the best action using iterative deepening minimax.

    state: the current FightState (engine state).
    player: 1 or 2 (which fighter we are).
    personality: the personality card for evaluation.
    max_depth: maximum search depth (plies).

    Returns (best_action, best_score, depth_reached).
    """
    start = time.perf_counter()
    best_action = Action.IDLE
    best_score = float("-inf")
    depth_reached = 0

    # Get the actions we can actually do right now
    obs = observation_for(state, player)
    available = _available_actions(obs)

    if len(available) == 1:
        return available[0], 0.0, 0

    # Iterative deepening: search depth 1, then 2, then 3...
    for depth in range(1, max_depth + 1):
        elapsed = time.perf_counter() - start
        if elapsed >= SEARCH_BUDGET_S:
            break

        action, score = _minimax_root(
            state, player, personality, depth, start
        )

        if action is not None:
            best_action = action
            best_score = score
            depth_reached = depth

    return best_action, best_score, depth_reached


def _minimax_root(state, player, personality, depth, start_time):
    """Run minimax from the root: try each action, return the best."""
    obs = observation_for(state, player)
    available = _available_actions(obs)

    best_action = available[0]
    best_score = float("-inf")
    alpha = float("-inf")
    beta = float("inf")

    for action in available:
        # Check time budget
        if time.perf_counter() - start_time >= SEARCH_BUDGET_S:
            break

        # Simulate this action for FRAMES_PER_PLY frames
        new_state = _simulate_ply(state, player, action, Action.IDLE)

        # Evaluate with minimax (enemy's turn next)
        score = _minimax(
            new_state, player, personality,
            depth - 1, alpha, beta, False, start_time
        )

        if score > best_score:
            best_score = score
            best_action = action

        alpha = max(alpha, score)

    return best_action, best_score


def _minimax(state, player, personality, depth, alpha, beta,
             maximizing, start_time):
    """Minimax with alpha-beta pruning.

    maximizing=True means it's our turn (we want the highest score).
    maximizing=False means it's the enemy's turn (they want the lowest).
    """
    # Check terminal conditions
    if depth <= 0 or state.round_over or state.match_over:
        return _evaluate_state(state, player, personality)

    # Time budget check
    if time.perf_counter() - start_time >= SEARCH_BUDGET_S:
        return _evaluate_state(state, player, personality)

    obs = observation_for(state, player if maximizing else _other(player))
    available = _available_actions(obs)

    # Limit branching: consider top actions to stay fast
    available = available[:4]

    if maximizing:
        value = float("-inf")
        for action in available:
            new_state = _simulate_ply(state, player, action, Action.IDLE)
            score = _minimax(new_state, player, personality,
                             depth - 1, alpha, beta, False, start_time)
            value = max(value, score)
            alpha = max(alpha, value)
            if alpha >= beta:
                break  # beta cutoff
        return value
    else:
        value = float("inf")
        for action in available:
            new_state = _simulate_ply(state, _other(player),
                                       action, Action.IDLE)
            score = _minimax(new_state, player, personality,
                             depth - 1, alpha, beta, True, start_time)
            value = min(value, score)
            beta = min(beta, value)
            if alpha >= beta:
                break  # alpha cutoff
        return value


def _simulate_ply(state, acting_player, action, other_action):
    """Simulate FRAMES_PER_PLY frames with one player's action fixed."""
    current = state.copy()
    for _ in range(FRAMES_PER_PLY):
        if current.round_over or current.match_over:
            break
        if acting_player == 1:
            current = step(current, action, other_action)
        else:
            current = step(current, other_action, action)
    return current


def _evaluate_state(state, player, personality):
    """Use the evaluation function to score the state."""
    if state.round_over or state.match_over:
        # Big bonus/penalty for winning/losing
        if state.round_result == ("p1" if player == 1 else "p2"):
            return 100.0
        elif state.round_result == ("p2" if player == 1 else "p1"):
            return -100.0
        else:
            return 0.0

    obs = observation_for(state, player)
    score, _ = evaluate(obs, personality)
    return score


def _available_actions(obs):
    """Return a list of actions the fighter can do right now, ordered by tactical relevance."""
    from backend.ai.actions import ATTACKS, DEFENCE

    preferred_order = [
        Action.LIGHT,
        Action.HEAVY,
        Action.FORWARD,
        Action.BLOCK,
        Action.DASH,
        Action.SPECIAL_NEUTRAL,
        Action.SUPER,
        Action.BACK,
        Action.IDLE,
        Action.JUMP,
        Action.CROUCH,
    ]
    ordered = [a for a in preferred_order if a in ALL_ACTIONS]
    for a in ALL_ACTIONS:
        if a not in ordered:
            ordered.append(a)

    available = []
    for action in ordered:
        # Skip attacks if on cooldown or in recovery
        if action in ATTACKS:
            if not obs.can_attack:
                continue
            if action in (Action.JUMP_PUNCH, Action.JUMP_KICK) and not obs.my_in_air:
                continue
            if action not in (Action.JUMP_PUNCH, Action.JUMP_KICK) and obs.my_in_air:
                continue
        # Skip block if in the air
        if action in DEFENCE and obs.my_in_air:
            continue
        available.append(action)

    if not available:
        available = [Action.IDLE]
    return available


def _other(player):
    """Return the other player number."""
    return 2 if player == 1 else 1
