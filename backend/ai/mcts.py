"""Monte Carlo Tree Search (open-loop UCT) with a hard time budget.

This is a real UCT tree, not flat Monte-Carlo:
  * Each node is a sequence of OUR macro-actions (one ply = FRAMES_PER_PLY
    frames, sustained moves held, attacks pressed on the first frame).
  * Selection uses UCB1 (exploration constant C), expansion adds one untried
    action per iteration, the rollout continues with random macro-actions up
    to ROLLOUT_PLIES plies, and the evaluation is back-propagated.
  * The opponent is modelled as a random macro-action per ply ("open-loop"
    MCTS for a simultaneous-move game), so the tree branches only on our moves.
  * The time budget is enforced before every iteration; the first iteration
    always runs so a move is always returned.

Honest scope: one iteration costs ~0.5-1 ms of engine simulation in Python, so
a 4 ms budget only allows a handful of iterations. MCTS is therefore NOT used
by the in-game difficulty wrapper (HELL uses the cheaper depth-1 simultaneous
search in ``backend.ai.search``). It is kept as an analysis tool and for
experiments with larger budgets.
"""

import math
import time

from backend.ai.actions import ATTACKS, Action
from backend.ai.adapter import observation_for
from backend.ai.evaluation import evaluate
from backend.engine.step import step

FRAMES_PER_PLY = 6
ROLLOUT_PLIES = 3            # total plies simulated per iteration (tree + rollout)
UCB_C = 1.4
MCTS_BUDGET_MS = 4
MCTS_BUDGET_S = MCTS_BUDGET_MS / 1000
MIN_ROLLOUTS = 1             # kept for backwards compatibility

# Tactical subset searched by MCTS (keeps the branching factor manageable).
CANDIDATES = (
    Action.IDLE, Action.FORWARD, Action.BACK, Action.DASH, Action.BACKDASH, Action.JUMP,
    Action.BLOCK, Action.BLOCK_LOW, Action.LIGHT, Action.HEAVY, Action.LOW_SWEEP,
    Action.THROW, Action.ANTI_AIR, Action.SPECIAL_NEUTRAL, Action.SPECIAL_FORWARD,
)
ENEMY_MOVES = (Action.IDLE, Action.FORWARD, Action.BACK, Action.BLOCK, Action.LIGHT,
               Action.HEAVY, Action.LOW_SWEEP, Action.JUMP)
_SUSTAINED = (Action.FORWARD, Action.BACK, Action.DASH, Action.CROUCH, Action.BLOCK, Action.BLOCK_LOW)


class _Node:
    __slots__ = ("children", "visits", "value", "untried")

    def __init__(self, actions):
        self.children = {}
        self.visits = 0
        self.value = 0.0
        self.untried = list(actions)

    def ucb_child(self):
        log_n = math.log(max(1, self.visits))
        best, best_score = None, float("-inf")
        for action, child in self.children.items():
            score = child.value / child.visits + UCB_C * math.sqrt(log_n / child.visits)
            if score > best_score:
                best, best_score = action, score
        return best


def _ply(state, player, my_action, enemy_action):
    current = state
    for i in range(FRAMES_PER_PLY):
        if current.round_over or current.match_over:
            break
        mine = my_action if (i == 0 or my_action in _SUSTAINED) else Action.IDLE
        theirs = enemy_action if (i == 0 or enemy_action in _SUSTAINED) else Action.IDLE
        current = step(current, mine, theirs) if player == 1 else step(current, theirs, mine)
    return current


def mcts_best_action(state, player, personality, rng, budget_s=MCTS_BUDGET_S):
    """Search with UCT for ``budget_s`` seconds.

    Returns (best_action, mean_value_of_best, iterations).
    """
    start = time.perf_counter()
    obs = observation_for(state, player)
    root_actions = _available_actions(obs)
    if len(root_actions) == 1:
        return root_actions[0], 0.0, 0

    # Normalise evaluations to roughly [-1, 1] for UCB.
    scale = 100.0
    root = _Node(root_actions)
    iterations = 0
    while iterations == 0 or (time.perf_counter() - start) < budget_s:
        node, path = root, [root]
        current = state.copy()
        depth = 0
        # Selection
        while not node.untried and node.children and depth < ROLLOUT_PLIES:
            action = node.ucb_child()
            current = _ply(current, player, action, rng.choice(ENEMY_MOVES))
            node = node.children[action]
            path.append(node)
            depth += 1
        # Expansion
        if node.untried and depth < ROLLOUT_PLIES and not (current.round_over or current.match_over):
            action = node.untried.pop(rng.randrange(len(node.untried)))
            current = _ply(current, player, action, rng.choice(ENEMY_MOVES))
            child = _Node(CANDIDATES)
            node.children[action] = child
            node = child
            path.append(node)
            depth += 1
        # Rollout
        while depth < ROLLOUT_PLIES and not (current.round_over or current.match_over):
            current = _ply(current, player, rng.choice(CANDIDATES), rng.choice(ENEMY_MOVES))
            depth += 1
        value = _eval_state(current, player, personality) / scale
        for n in path:
            n.visits += 1
            n.value += value
        iterations += 1

    best_action, best_visits, best_mean = root_actions[0], -1, 0.0
    for action, child in root.children.items():
        if child.visits > best_visits:
            best_action, best_visits, best_mean = action, child.visits, child.value / child.visits
    return best_action, float(best_mean * scale), iterations


def _eval_state(state, player, personality):
    """Score the state from our player's perspective."""
    if state.round_over or state.match_over:
        my_result = "p1" if player == 1 else "p2"
        enemy_result = "p2" if player == 1 else "p1"
        if state.round_result == my_result:
            return 100.0
        if state.round_result == enemy_result:
            return -100.0
        return 0.0
    obs = observation_for(state, player)
    score, _ = evaluate(obs, personality)
    return float(score)


def _available_actions(obs):
    """Legal root actions from the tactical candidate set."""
    available = []
    for action in CANDIDATES:
        if action in ATTACKS and (not obs.can_attack or obs.my_in_air):
            continue
        if action in (Action.BLOCK, Action.BLOCK_LOW, Action.DASH, Action.BACKDASH) and obs.my_in_air:
            continue
        available.append(action)
    return available or [Action.IDLE]
