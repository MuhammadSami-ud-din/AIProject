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


# ======================================================================
# Simultaneous-move search used in-game by DifficultyWrapper (HELL)
# ======================================================================
# Fighting-game moves are simultaneous, so instead of the sequential minimax
# above (my ply, then the enemy's ply with me idle) the in-game search
# simulates BOTH fighters' actions in the same ply:
#   * "expectimax": value(a) = sum_e P(e) * eval(sim(a, e)), with P from the
#     OpponentModel -- used once the model predicts the opponent well enough.
#   * "minimax":    value(a) = min_e eval(sim(a, e)) over a small threat set
#     -- the cautious default while the opponent model has little data.
# A hard time budget is enforced: the search stops as soon as the deadline
# passes and returns the best fully-evaluated candidate.

IN_GAME_BUDGET_S = 0.003          # 3 ms per search call
MINIMAX_THREATS = (Action.IDLE, Action.LIGHT, Action.BLOCK)
_SUSTAINED = (Action.FORWARD, Action.BACK, Action.DASH, Action.CROUCH,
              Action.BLOCK, Action.BLOCK_LOW)


def _infer_character(reach):
    """Guess a character from its light-attack reach (observations carry no name)."""
    from backend.engine.characters import CHARACTER_STATS, light_attack_for

    best, best_diff = "Golden", float("inf")
    for name, stats in CHARACTER_STATS.items():
        diff = abs(light_attack_for(stats).reach - reach)
        if diff < best_diff:
            best, best_diff = name, diff
    return best


def state_from_observation(obs, my_character, enemy_character=None):
    """Rebuild an approximate FightState (me = fighter 1) from an Observation.

    The game hands agents an Observation, not the engine state, so the in-game
    search runs on this belief state. Positions, health, stun/recovery timers,
    meters, air/crouch/knockdown and (when available) attack phases are exact;
    internal engine details that are not observed (e.g. which frame of a move
    the enemy is on) are approximated by the engine defaults.
    """
    from backend.engine.step import make_initial_state

    enemy_character = enemy_character or getattr(obs, "enemy_character", "") or _infer_character(obs.enemy_reach)
    my_character = getattr(obs, "my_character", "") or my_character
    st = make_initial_state(my_character, enemy_character)
    for f, side in ((st.fighter1, "my"), (st.fighter2, "enemy")):
        f.x = float(getattr(obs, f"{side}_x"))
        f.health = float(getattr(obs, f"{side}_health"))
        f.cooldown = int(getattr(obs, f"{side}_cooldown"))
        f.recovery = int(getattr(obs, f"{side}_recovery"))
        f.hitstun = int(getattr(obs, f"{side}_hitstun"))
        f.blockstun = int(getattr(obs, f"{side}_blockstun"))
        f.in_air = bool(getattr(obs, f"{side}_in_air"))
        f.is_crouching = bool(getattr(obs, f"{side}_is_crouching"))
        f.is_knocked_down = bool(getattr(obs, f"{side}_is_knocked_down"))
        f.meter = float(getattr(obs, f"{side}_meter"))
        f.guard_meter = float(getattr(obs, f"{side}_guard_meter"))
        f.combo_hits = int(getattr(obs, f"{side}_combo_count"))
        f.last_action = getattr(obs, f"{side}_last_action")
        if getattr(obs, "has_engine_detail", False):
            f.attack_phase = getattr(obs, f"{side}_attack_phase")
            f.jump_frame = int(getattr(obs, f"{side}_jump_frame"))
            f.is_thrown = bool(getattr(obs, f"{side}_is_thrown"))
            f.guard_break_stun = int(getattr(obs, f"{side}_guard_break_stun"))
    st.round_frames_left = max(1, int(obs.time_left * 60))
    return st


def _simulate_joint(state, player, my_action, enemy_action, frames=FRAMES_PER_PLY):
    current = state.copy()
    for i in range(frames):
        if current.round_over or current.match_over:
            break
        mine = my_action if (i == 0 or my_action in _SUSTAINED) else Action.IDLE
        theirs = enemy_action if (i == 0 or enemy_action in _SUSTAINED) else Action.IDLE
        current = step(current, mine, theirs) if player == 1 else step(current, theirs, mine)
    return current


def simultaneous_search(state, player, personality, candidates, enemy_probs=None,
                        mode="minimax", top_enemy=3, budget_s=IN_GAME_BUDGET_S):
    """Depth-1 simultaneous-move search over ``candidates`` with a hard budget.

    Returns (best_action, best_value, candidates_evaluated, elapsed_s).
    """
    start = time.perf_counter()
    deadline = start + budget_s
    if mode == "expectimax" and enemy_probs:
        ranked = sorted(enemy_probs.items(), key=lambda kv: kv[1], reverse=True)[:top_enemy]
        total = sum(p for _, p in ranked) or 1.0
        enemy_set = [(a, p / total) for a, p in ranked]
    else:
        mode = "minimax"
        enemy_set = [(a, 1.0) for a in MINIMAX_THREATS]

    best_action, best_value, evaluated = None, float("-inf"), 0
    for my_action in candidates:
        values = []
        for enemy_action, p in enemy_set:
            if time.perf_counter() >= deadline and best_action is not None:
                return best_action, best_value, evaluated, time.perf_counter() - start
            nxt = _simulate_joint(state, player, my_action, enemy_action)
            values.append((p, _evaluate_state(nxt, player, personality)))
        value = sum(p * v for p, v in values) if mode == "expectimax" else min(v for _, v in values)
        evaluated += 1
        if value > best_value:
            best_action, best_value = my_action, value
    return best_action or Action.IDLE, best_value, evaluated, time.perf_counter() - start
