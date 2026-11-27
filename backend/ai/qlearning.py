"""Tabular Q-learning with self-play.

Learns a value for each (state_bucket, action) pair by playing
against itself. Uses a simple discretisation of the observation
into buckets.

This is a teaching example of reinforcement learning: the student
should be able to explain every line in a viva.
"""

import random

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.observation import Observation
from backend.ai.personalities import GOLDEN
from backend.ai.zones import zone_of, Zone


# Q-learning parameters
LEARNING_RATE = 0.1      # how fast we update Q-values (alpha)
DISCOUNT = 0.95          # how much we value future rewards (gamma)
EPSILON_START = 0.3      # starting exploration rate
EPSILON_MIN = 0.05       # minimum exploration rate
EPSILON_DECAY = 0.999    # multiply epsilon by this each episode

# How many buckets for discretising continuous values
HEALTH_BUCKETS = 5       # 0.0-0.2, 0.2-0.4, ..., 0.8-1.0


def _bucket(value, n_buckets):
    """Turn a 0-1 value into a bucket index."""
    idx = int(value * n_buckets)
    return min(idx, n_buckets - 1)


def state_key(obs):
    """Turn an observation into a hashable state key.

    We discretise the state into a tuple of bucket indices.
    This makes the Q-table small enough to learn quickly.
    """
    zone = zone_of(obs.distance)

    my_health_bucket = _bucket(obs.my_health, HEALTH_BUCKETS)
    enemy_health_bucket = _bucket(obs.enemy_health, HEALTH_BUCKETS)

    # Am I cornered? Is the enemy cornered?
    cornered = 1 if obs.i_am_cornered else 0
    enemy_cornered = 1 if obs.enemy_is_cornered else 0

    # Can I attack?
    can_attack = 1 if obs.can_attack else 0

    # Is the enemy stuck in recovery?
    enemy_stuck = 1 if obs.enemy_is_stuck else 0

    return (
        zone,
        my_health_bucket,
        enemy_health_bucket,
        cornered,
        enemy_cornered,
        can_attack,
        enemy_stuck,
    )


class QTable:
    """A simple Q-value table mapping (state, action) -> value.

    Uses a dict so it grows only as states are visited.
    Missing entries default to 0.0.
    """

    def __init__(self):
        self.table = {}      # {state_key: {Action: float}}
        self.visits = {}     # {state_key: int} — how often each state was seen

    def get(self, key, action):
        """Get the Q-value for a state-action pair."""
        if key not in self.table:
            return 0.0
        return self.table[key].get(action, 0.0)

    def set(self, key, action, value):
        """Set the Q-value for a state-action pair."""
        if key not in self.table:
            self.table[key] = {a: 0.0 for a in ALL_ACTIONS}
        self.table[key][action] = value

    def best_action(self, key):
        """Return the action with the highest Q-value for this state."""
        if key not in self.table:
            return Action.IDLE
        actions = self.table[key]
        return max(actions, key=actions.get)

    def update(self, key, action, reward, next_key):
        """Do one Q-learning update step.

        Q(s, a) = Q(s, a) + alpha * (reward + gamma * max_Q(s') - Q(s, a))
        """
        old_q = self.get(key, action)
        # Find the best future value
        if next_key in self.table:
            max_next = max(self.table[next_key].values())
        else:
            max_next = 0.0

        new_q = old_q + LEARNING_RATE * (reward + DISCOUNT * max_next - old_q)
        self.set(key, action, new_q)

        # Track visits
        self.visits[key] = self.visits.get(key, 0) + 1

    @property
    def size(self):
        """Number of states in the table."""
        return len(self.table)


class QLearningAgent(Agent):
    """A fighter that learns using tabular Q-learning.

    In training mode, it explores randomly (epsilon-greedy).
    In play mode, it uses the learned Q-values.
    """

    def __init__(self, player=1, difficulty="LOW", seed=None,
                 q_table=None, training=False):
        super().__init__(
            name="Q-Learner",
            player=player,
            difficulty=difficulty,
            personality=GOLDEN,
            seed=seed,
        )
        self.q_table = q_table if q_table is not None else QTable()
        self.training = training
        self.epsilon = EPSILON_START

        # For tracking the last state-action pair (for updates)
        self.last_key = None
        self.last_action = None

    def choose_action(self, obs):
        """Pick an action using epsilon-greedy policy."""
        key = state_key(obs)
        scores = {}

        if self.training and self.rng.random() < self.epsilon:
            # Explore: pick a random action
            action = self.rng.choice(list(ALL_ACTIONS))
        else:
            # Exploit: pick the best learned action
            action = self.q_table.best_action(key)

        # Build scores dict for display
        for a in ALL_ACTIONS:
            scores[a] = self.q_table.get(key, a)

        self.last_key = key
        self.last_action = action
        return action, scores

    def observe(self, obs, my_action, enemy_action):
        """After each frame, update Q-values if training."""
        if not self.training:
            return
        if self.last_key is None:
            return

        # Compute reward from the current observation
        reward = _compute_reward(obs)

        # Get the new state key
        new_key = state_key(obs)

        # Update Q-value for the last state-action pair
        self.q_table.update(self.last_key, self.last_action, reward, new_key)

    def end_episode(self):
        """Called at the end of a match. Decay epsilon."""
        self.epsilon = max(EPSILON_MIN, self.epsilon * EPSILON_DECAY)
        self.last_key = None
        self.last_action = None


def _compute_reward(obs):
    """Compute a simple reward signal from the observation.

    + health lead is good
    + enemy being stuck is good (we can punish)
    - being cornered is bad
    """
    reward = 0.0

    # Health lead: positive is good, negative is bad
    reward += obs.health_lead * 0.5

    # Punish opportunity
    if obs.enemy_is_stuck:
        reward += 0.1

    # Being cornered is bad
    if obs.i_am_cornered:
        reward -= 0.1

    return reward


def train_q_agent(episodes=100, seed=42):
    """Train a Q-learning agent through self-play.

    Two Q-learning agents play against each other.
    Returns the trained Q-table and training history.
    """
    from backend.data.match_runner import run_match

    q_table = QTable()
    history = []

    for ep in range(episodes):
        # Both agents share the same Q-table (self-play)
        agent1 = QLearningAgent(
            player=1, seed=seed + ep, q_table=q_table, training=True
        )
        agent2 = QLearningAgent(
            player=2, seed=seed + ep + 10000, q_table=q_table, training=True
        )

        result = run_match(agent1, agent2, seed=seed + ep)

        agent1.end_episode()
        agent2.end_episode()

        history.append({
            "episode": ep,
            "result": result["match_result"],
            "q_table_size": q_table.size,
            "epsilon": agent1.epsilon,
        })

    return q_table, history


# ======================================================================
# Online Combat Reinforcement Learner (Anti-Exploit & Move Diversity)
# ======================================================================

from collections import deque
from typing import Dict, Optional, Tuple
from backend.ai.actions import ATTACKS, DEFENCE

HIGH_MID_ATTACKS = (
    Action.LIGHT,
    Action.HEAVY,
    Action.LIGHT_KICK,
    Action.HEAVY_KICK,
    Action.SPECIAL_FORWARD,
    Action.SPECIAL_NEUTRAL,
    Action.SPECIAL_BACK,
    Action.SUPER,
)
LOW_ATTACKS = (
    Action.LOW_SWEEP,
    Action.CROUCH_KICK,
    Action.CROUCH_JAB,
    Action.CROUCH,
)
AIR_MOVES = (
    Action.JUMP,
    Action.JUMP_KICK,
    Action.JUMP_PUNCH,
)
OVERHEAD_MOVES = (
    Action.OVERHEAD,
)


def combat_rl_key(obs: Observation, last_enemy_move: Action) -> Tuple:
    """Compact tactical state key for live in-match Q-learning."""
    zone = zone_of(obs.distance)
    if obs.enemy_in_air:
        enemy_posture = "air"
    elif obs.enemy_is_crouching:
        enemy_posture = "crouch"
    elif obs.enemy_is_blocking:
        enemy_posture = "block"
    elif obs.enemy_is_attacking:
        enemy_posture = "attack"
    elif obs.enemy_is_stuck:
        enemy_posture = "stuck"
    else:
        enemy_posture = "stand"
    return (zone, enemy_posture, last_enemy_move)


class OnlineCombatLearner:
    """Live Q-learning + opponent habit counter-adapter + move diversity manager.

    - Learns Q(s, a) online from real damage dealt, damage taken, blocks, and whiffs.
    - Detects when the opponent repeats the same move or tactic (spamming high attacks,
      low sweeps, jump-ins, crouch pokes, or turtle blocking) and boosts direct counters.
    - Penalizes self-repetition so the AI rotates through all of its attack moves
      according to their probabilities instead of spamming a single attack.
    """

    def __init__(self, alpha: float = 0.28, gamma: float = 0.85):
        self.alpha = alpha
        self.gamma = gamma
        self.q_table = QTable()

        # Sliding windows of meaningful (non-IDLE) actions
        self.recent_enemy_moves: deque[Action] = deque(maxlen=18)
        self.my_recent_attacks: deque[Action] = deque(maxlen=8)
        self.transition_counts: Dict[Tuple, Dict[Action, float]] = {}

        self._last_enemy_recorded: Action = Action.IDLE
        self._frames_since_enemy_record: int = 0
        self._prev_enemy_move: Action = Action.IDLE

        # Active RL transition tracking
        self._pending_key: Optional[Tuple] = None
        self._pending_action: Optional[Action] = None
        self._pending_my_hp: float = 1.0
        self._pending_enemy_hp: float = 1.0
        self._pending_frames: int = 0
        self._consecutive_blocked_attacks: int = 0

    def reset_round(self) -> None:
        """Reset transient round pointers while preserving learned Q-values and habits."""
        self._pending_key = None
        self._pending_action = None
        self._pending_my_hp = 1.0
        self._pending_enemy_hp = 1.0
        self._pending_frames = 0
        self._frames_since_enemy_record = 0
        self.my_recent_attacks.clear()

    def _update_q(self, key: Tuple, action: Action, reward: float, next_key: Tuple) -> None:
        old_q = self.q_table.get(key, action)
        if next_key in self.q_table.table:
            max_next = max(self.q_table.table[next_key].values())
        else:
            max_next = 0.0
        new_q = old_q + self.alpha * (reward + self.gamma * max_next - old_q)
        # Clamp Q-values to [-5.0, +5.0] so they blend smoothly with heuristic scores
        self.q_table.set(key, action, max(-5.0, min(5.0, new_q)))
        self.q_table.visits[key] = self.q_table.visits.get(key, 0) + 1

    def record_decision(self, obs: Observation, chosen_action: Action) -> None:
        """Record the AI's chosen decision so the outcome can be reinforced on subsequent frames."""
        if chosen_action in ATTACKS:
            self.my_recent_attacks.append(chosen_action)

        if chosen_action != Action.IDLE:
            self._pending_key = combat_rl_key(obs, self._last_enemy_recorded)
            self._pending_action = chosen_action
            self._pending_my_hp = obs.my_health
            self._pending_enemy_hp = obs.enemy_health
            self._pending_frames = 0

    def observe(self, obs: Observation, my_action: Action, enemy_action: Action) -> None:
        """Observe frame outcome, update opponent habit model, and perform TD Q-learning step."""
        self._frames_since_enemy_record += 1

        # 1. Identify enemy's active move (do not let filler IDLE frames erase active attacks/stances)
        explicit_press = (enemy_action != Action.IDLE)
        eff_enemy = enemy_action
        if not explicit_press and obs.enemy_last_action != Action.IDLE:
            if obs.enemy_is_attacking or obs.enemy_in_air or obs.enemy_is_crouching or obs.enemy_is_blocking:
                eff_enemy = obs.enemy_last_action

        should_record = (
            eff_enemy != Action.IDLE
            and (
                explicit_press
                or eff_enemy != self._last_enemy_recorded
                or self._frames_since_enemy_record >= 12
            )
        )
        if should_record:
            zone = zone_of(obs.distance)
            t_key = (zone, self._prev_enemy_move)
            if t_key not in self.transition_counts:
                self.transition_counts[t_key] = {}
            self.transition_counts[t_key][eff_enemy] = self.transition_counts[t_key].get(eff_enemy, 0.0) + 1.0

            self._prev_enemy_move = self._last_enemy_recorded
            self._last_enemy_recorded = eff_enemy
            self.recent_enemy_moves.append(eff_enemy)
            self._frames_since_enemy_record = 0

        # 2. Evaluate pending RL transition
        if self._pending_key is None or self._pending_action is None:
            return

        self._pending_frames += 1
        my_dmg_taken = max(0.0, self._pending_my_hp - obs.my_health)
        enemy_dmg_taken = max(0.0, self._pending_enemy_hp - obs.enemy_health)

        # Resolve transition when damage occurs or after a 10-frame action evaluation window
        if my_dmg_taken > 0.001 or enemy_dmg_taken > 0.001 or self._pending_frames >= 10:
            reward = 0.0
            cur_key = combat_rl_key(obs, self._last_enemy_recorded)

            if enemy_dmg_taken > 0.001:
                if obs.enemy_blockstun > 0 or obs.enemy_is_blocking:
                    self._consecutive_blocked_attacks += 1
                    # Penalize hammering into a blocking opponent repeatedly so AI switches to throws/lows/overheads
                    if self._consecutive_blocked_attacks >= 2:
                        reward -= 0.75 * min(3, self._consecutive_blocked_attacks)
                        for guard_breaker in (Action.THROW, Action.LOW_SWEEP, Action.OVERHEAD, Action.SPECIAL_DOWN, Action.SPECIAL_NEUTRAL):
                            self._update_q(self._pending_key, guard_breaker, 1.15, cur_key)
                    else:
                        reward += 2.0 * enemy_dmg_taken
                else:
                    self._consecutive_blocked_attacks = 0
                    reward += 22.0 * enemy_dmg_taken + 1.1

            if my_dmg_taken > 0.001:
                reward -= (24.0 * my_dmg_taken + 1.3)
                # Direct counter-reinforcement: teach Q-table what would have beaten eff_enemy
                for counter_act in self.counters_for(self._last_enemy_recorded, obs):
                    self._update_q(self._pending_key, counter_act, 1.45, cur_key)

            if my_dmg_taken <= 0.001 and enemy_dmg_taken <= 0.001:
                if self._pending_action in (Action.BLOCK, Action.BLOCK_LOW) and obs.enemy_is_attacking and obs.distance <= 130:
                    reward += 0.85
                elif self._pending_action in ATTACKS and obs.distance <= 115:
                    # Whiffed or stuffed attack
                    reward -= 0.40

            if abs(reward) > 1e-4:
                self._update_q(self._pending_key, self._pending_action, reward, cur_key)

            self._pending_key = None
            self._pending_action = None

    def counters_for(self, enemy_move: Action, obs: Observation) -> Tuple[Action, ...]:
        """Return the set of direct tactical counter-moves against a specific enemy move."""
        if enemy_move in AIR_MOVES or obs.enemy_in_air:
            return (Action.ANTI_AIR, Action.SPECIAL_NEUTRAL, Action.BLOCK, Action.BACKDASH)
        if enemy_move in LOW_ATTACKS:
            return (Action.BLOCK_LOW, Action.OVERHEAD, Action.JUMP_KICK, Action.JUMP_PUNCH, Action.LOW_SWEEP)
        if enemy_move in OVERHEAD_MOVES:
            return (Action.BLOCK, Action.LIGHT, Action.ANTI_AIR, Action.SPECIAL_DOWN)
        if enemy_move in DEFENCE:
            if enemy_move == Action.BLOCK_LOW or obs.enemy_is_crouching:
                return (Action.OVERHEAD, Action.THROW, Action.SPECIAL_DOWN, Action.JUMP_KICK)
            return (Action.THROW, Action.LOW_SWEEP, Action.CROUCH_KICK, Action.SPECIAL_DOWN, Action.SPECIAL_NEUTRAL)
        if enemy_move == Action.THROW:
            return (Action.THROW, Action.LIGHT, Action.CROUCH_JAB, Action.BACKDASH, Action.JUMP_KICK)
        if enemy_move in HIGH_MID_ATTACKS:
            return (
                Action.BLOCK,
                Action.LIGHT,
                Action.LIGHT_KICK,
                Action.CROUCH_JAB,
                Action.CROUCH_KICK,
                Action.LOW_SWEEP,
                Action.SPECIAL_DOWN,
                Action.SPECIAL_BACK,
            )
        return (Action.LIGHT, Action.LIGHT_KICK, Action.HEAVY_KICK)

    def detect_spam(self, obs: Observation) -> Tuple[Optional[Action], float]:
        """Detect if the opponent is repeating a specific move or category.

        Returns (dominant_action, spam_intensity in 0.0..1.0).
        """
        if len(self.recent_enemy_moves) < 3:
            return None, 0.0

        recent = list(self.recent_enemy_moves)[-10:]
        counts: Dict[Action, int] = {}
        for m in recent:
            counts[m] = counts.get(m, 0) + 1

        top_move = max(counts, key=lambda a: counts[a])
        top_ratio = counts[top_move] / float(len(recent))

        # Check immediate last-4 streak
        tail = recent[-4:]
        tail_count = sum(1 for m in tail if m == top_move)
        streak_ratio = tail_count / float(len(tail))

        # Also check Markov transition prediction
        zone = zone_of(obs.distance)
        t_counts = self.transition_counts.get((zone, self._last_enemy_recorded), {})
        if t_counts:
            t_total = sum(t_counts.values())
            t_best = max(t_counts, key=lambda a: t_counts[a])
            t_prob = t_counts[t_best] / max(1.0, t_total)
            if t_total >= 2 and t_prob >= 0.55:
                return t_best, min(1.0, max(top_ratio, t_prob))

        intensity = max(top_ratio, streak_ratio * 0.9)
        if intensity >= 0.34:
            return top_move, min(1.0, intensity)
        return None, 0.0

    def adjust_scores(
        self,
        scores: Dict[Action, float],
        obs: Observation,
        difficulty: str = "LOW",
    ) -> Tuple[Dict[Action, float], float]:
        """Apply live Q-learning values, anti-spam counter boosts, and move-diversity penalties.

        Returns (adjusted_scores, spam_intensity).
        """
        adjusted = dict(scores)
        key = combat_rl_key(obs, self._last_enemy_recorded)

        # Difficulty weight on RL adaptation (active on ALL difficulties, strongest on HIGH/HELL)
        rl_weight = {"LOW": 0.75, "MEDIUM": 1.0, "HIGH": 1.35, "HELL": 1.65}.get(difficulty, 1.0)

        # 1. Add learned Q(s, a) values for every available action
        if key in self.q_table.table:
            for act, q_val in self.q_table.table[key].items():
                if act in adjusted and adjusted[act] > 0.05:
                    adjusted[act] = max(0.05, adjusted[act] + q_val * rl_weight)

        # 2. Detect repeated player moves/habits and boost direct tactical counters
        spam_move, spam_intensity = self.detect_spam(obs)
        if spam_move is not None and spam_intensity >= 0.34:
            counter_boost = (2.8 + 3.5 * spam_intensity) * rl_weight
            counters = self.counters_for(spam_move, obs)
            for c_act in counters:
                if c_act in adjusted:
                    # Only boost attacks if in or near range, or defense/movement anytime
                    if c_act in DEFENCE or c_act in (Action.BACKDASH, Action.JUMP):
                        if obs.distance <= 150:
                            adjusted[c_act] += counter_boost * 0.95
                    elif c_act == Action.THROW:
                        if obs.distance <= 55 and obs.can_attack and not obs.my_in_air:
                            adjusted[c_act] += counter_boost * 1.15
                    elif c_act in (Action.ANTI_AIR, Action.SPECIAL_NEUTRAL) and (obs.enemy_in_air or spam_move in AIR_MOVES):
                        if obs.distance <= 115 and obs.can_attack and not obs.my_in_air:
                            adjusted[c_act] += counter_boost * 1.25
                    elif obs.can_attack and obs.distance <= 115:
                        adjusted[c_act] += counter_boost

        # 3. Self-Repetition / Staleness Penalty so AI uses ALL its attack moves according to chances
        if self.my_recent_attacks:
            recent_counts: Dict[Action, int] = {}
            # Recent moves weighted more heavily
            for idx, act in enumerate(self.my_recent_attacks):
                weight = 2 if idx >= len(self.my_recent_attacks) - 3 else 1
                recent_counts[act] = recent_counts.get(act, 0) + weight

            last_atk = self.my_recent_attacks[-1]
            for act, cnt in recent_counts.items():
                if act in adjusted and act in ATTACKS and adjusted[act] > 0.5:
                    decay = (0.76 ** cnt) * (0.78 if act == last_atk else 1.0)
                    adjusted[act] *= max(0.28, decay)

        return adjusted, spam_intensity


# Persistent live learners so the AI keeps its learned Q-table across rounds and
# rematches. Keyed by (character, side): in a mirror match (Crimson vs Crimson)
# each side learns its own table instead of both sides writing into one.
_SHARED_COMBAT_LEARNERS: Dict[tuple, OnlineCombatLearner] = {}


def get_shared_combat_learner(character_name: str, player: int = 0) -> OnlineCombatLearner:
    """Return the persistent OnlineCombatLearner for a fighter on a given side (1 or 2)."""
    key = ((character_name or "Default").strip().title(), int(player or 0))
    if key not in _SHARED_COMBAT_LEARNERS:
        _SHARED_COMBAT_LEARNERS[key] = OnlineCombatLearner()
    return _SHARED_COMBAT_LEARNERS[key]
