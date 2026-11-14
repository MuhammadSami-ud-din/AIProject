"""Monte Carlo Tree Search for Hell mode.

MCTS explores many possible futures by playing random rollouts
from each candidate move. The move with the best average outcome
wins. Faster than deep minimax, and handles simultaneous actions
better because it does not assume worst-case.

How it works:
  1. For each legal action, simulate several random rollouts.
  2. Each rollout plays N frames with random moves for both sides.
  3. Score the final state using the evaluation function.
  4. Pick the action whose rollouts scored best on average.
"""

import time

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.adapter import observation_for
from backend.ai.evaluation import evaluate
from backend.engine.step import step


# How many frames each rollout simulates
ROLLOUT_DEPTH = 18          # about 0.3 seconds of game time

# Time budget for the entire MCTS search
MCTS_BUDGET_MS = 4
MCTS_BUDGET_S = MCTS_BUDGET_MS / 1000

# Minimum rollouts per action before we stop early
MIN_ROLLOUTS = 2


def mcts_best_action(state, player, personality, rng,
                     budget_s=MCTS_BUDGET_S):
    """Find the best action using Monte Carlo rollouts.

    state: the current FightState.
    player: 1 or 2.
    personality: for evaluation.
    rng: random generator for rollouts.
    budget_s: time budget in seconds.

    Returns (best_action, best_score, rollouts_done).
    """
    start = time.perf_counter()
    obs = observation_for(state, player)
    available = _available_actions(obs)

    if len(available) == 1:
        return available[0], 0.0, 0

    # Track scores for each action
    total_score = {a: 0.0 for a in available}
    count = {a: 0 for a in available}
    total_rollouts = 0

    # Round-robin: give each action at least MIN_ROLLOUTS
    while True:
        for action in available:
            elapsed = time.perf_counter() - start
            if elapsed >= budget_s and count[action] >= MIN_ROLLOUTS:
                # Over budget and we have enough data
                break

            # Run one rollout from this action
            score = _rollout(state, player, action, personality, rng)
            total_score[action] += score
            count[action] += 1
            total_rollouts += 1
        else:
            # If we haven't gone over budget, keep going
            if time.perf_counter() - start < budget_s:
                continue
        break

    # Pick the action with the best average score
    best_action = available[0]
    best_avg = float("-inf")
    for action in available:
        if count[action] > 0:
            avg = total_score[action] / count[action]
            if avg > best_avg:
                best_avg = avg
                best_action = action

    return best_action, best_avg, total_rollouts


def _rollout(state, player, first_action, personality, rng):
    """Simulate one random rollout from a starting action.

    Plays ROLLOUT_DEPTH frames with the first action for our player,
    then random actions for both sides. Returns the evaluation score
    of the final state.
    """
    current = state.copy()
    all_acts = list(ALL_ACTIONS)

    for frame in range(ROLLOUT_DEPTH):
        if current.round_over or current.match_over:
            break

        # Our action: use the specified first_action for frame 0,
        # then pick random moves
        if frame == 0:
            my_action = first_action
        else:
            my_action = rng.choice(all_acts)

        # Enemy action: always random in rollouts
        enemy_action = rng.choice(all_acts)

        # Apply the actions to the engine
        if player == 1:
            current = step(current, my_action, enemy_action)
        else:
            current = step(current, enemy_action, my_action)

    # Evaluate the final state
    return _eval_state(current, player, personality)


def _eval_state(state, player, personality):
    """Score the state from our player's perspective."""
    if state.round_over or state.match_over:
        my_result = "p1" if player == 1 else "p2"
        enemy_result = "p2" if player == 1 else "p1"
        if state.round_result == my_result:
            return 100.0
        elif state.round_result == enemy_result:
            return -100.0
        else:
            return 0.0

    obs = observation_for(state, player)
    score, _ = evaluate(obs, personality)
    return score


def _available_actions(obs):
    """Return legal actions for this frame."""
    available = []
    for action in ALL_ACTIONS:
        if action in (Action.LIGHT, Action.HEAVY):
            if not obs.can_attack:
                continue
        if action == Action.BLOCK and obs.my_in_air:
            continue
        available.append(action)

    if not available:
        available = [Action.IDLE]
    return available
