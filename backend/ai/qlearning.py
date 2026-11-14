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
