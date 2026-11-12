"""Opponent model: predicts what the enemy will do next.

Counts the opponent's actions given (distance zone, their last 2 actions).
Uses Laplace smoothing so no action has zero probability.
Old counts fade over time (multiply by 0.98 per second).
Reports prediction accuracy and time-to-model.
"""

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.observation import FRAMES_PER_SECOND
from backend.ai.zones import zone_of


# How fast old counts decay: multiply all counts by this every second
DECAY_RATE = 0.98

# Laplace smoothing: add this to every count so nothing is ever zero
LAPLACE = 1.0

# How many frames between decay applications
DECAY_INTERVAL = FRAMES_PER_SECOND  # once per second


class OpponentModel:
    """Predicts the opponent's next action based on past observations.

    The model uses a simple table:
      key = (distance zone, enemy's last action, enemy's 2nd-last action)
      value = {action: count} for each possible next action

    Laplace smoothing ensures every action has some probability.
    Old counts fade so the model adapts to changing behaviour.
    """

    def __init__(self):
        # counts[key][action] = how many times the enemy did 'action' in this situation
        self.counts = {}

        # Tracking
        self.total_predictions = 0
        self.correct_predictions = 0
        self.frames_seen = 0
        self.last_key = None
        self.last_prediction = None

        # For the 2nd-last action
        self.prev_enemy_action = Action.IDLE
        self.prev_prev_enemy_action = Action.IDLE

    def reset(self):
        """Reset for a new round (keep learned counts across rounds)."""
        self.last_key = None
        self.last_prediction = None
        self.prev_enemy_action = Action.IDLE
        self.prev_prev_enemy_action = Action.IDLE

    def full_reset(self):
        """Reset everything including learned counts (new match)."""
        self.counts = {}
        self.total_predictions = 0
        self.correct_predictions = 0
        self.frames_seen = 0
        self.reset()

    def update(self, obs, enemy_action):
        """Called after every frame with the enemy's actual action.

        Updates the count table and checks if our prediction was right.
        """
        self.frames_seen += 1

        # Build the key for this situation
        zone = zone_of(obs.distance)
        key = (zone, self.prev_enemy_action, self.prev_prev_enemy_action)

        # Check if our last prediction was correct
        if self.last_prediction is not None:
            self.total_predictions += 1
            if self.last_prediction == enemy_action:
                self.correct_predictions += 1

        # Update the count for this situation
        if key not in self.counts:
            self.counts[key] = {a: 0.0 for a in ALL_ACTIONS}
        self.counts[key][enemy_action] += 1.0

        # Decay old counts periodically
        if self.frames_seen % DECAY_INTERVAL == 0:
            self._decay_counts()

        # Shift action history
        self.prev_prev_enemy_action = self.prev_enemy_action
        self.prev_enemy_action = enemy_action

        # Store the key for the next prediction
        new_zone = zone_of(obs.distance)
        self.last_key = (new_zone, enemy_action, self.prev_prev_enemy_action)

    def predict(self, obs):
        """Predict the enemy's next action.

        Returns a dict {action: probability} that sums to 1.
        Uses Laplace smoothing so no action is ever 0.
        """
        zone = zone_of(obs.distance)
        key = (zone, self.prev_enemy_action, self.prev_prev_enemy_action)

        counts = self.counts.get(key, {})

        # Add Laplace smoothing
        smoothed = {}
        total = 0.0
        for action in ALL_ACTIONS:
            count = counts.get(action, 0.0) + LAPLACE
            smoothed[action] = count
            total += count

        # Normalize to probabilities
        probs = {a: c / total for a, c in smoothed.items()}

        # Store the most likely action as our prediction
        self.last_prediction = max(probs, key=probs.get)

        return probs

    @property
    def accuracy(self):
        """What fraction of predictions were correct (0 to 1)."""
        if self.total_predictions == 0:
            return 0.0
        return self.correct_predictions / self.total_predictions

    @property
    def time_to_model(self):
        """Frames until accuracy first passed 50%. -1 if not yet."""
        # This is a rough estimate based on current accuracy
        if self.accuracy >= 0.5:
            return self.frames_seen
        return -1

    @property
    def is_confident(self):
        """True when the model's accuracy is above 70%."""
        return self.accuracy >= 0.70

    def _decay_counts(self):
        """Multiply all counts by DECAY_RATE so old data fades."""
        for key in self.counts:
            for action in self.counts[key]:
                self.counts[key][action] *= DECAY_RATE
