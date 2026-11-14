"""Ghost fighter: an AI that copies the human player's style.

Looks at logged human fight data and uses the learned model
to make decisions the same way the human would.
If no learned model is available, falls back to a simple
frequency-based approach: count which actions the human used
in each situation and pick the most common one.
"""

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.observation import FEATURE_NAMES
from backend.ai.personalities import GOLDEN
from backend.ai.zones import zone_of


class GhostAgent(Agent):
    """A fighter that mimics a human player's logged behaviour.

    If a trained model exists, uses it for decisions.
    Otherwise, uses a frequency table of (zone, enemy_stuck) -> action counts.
    """

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__(
            name="Ghost",
            player=player,
            difficulty=difficulty,
            personality=GOLDEN,  # neutral base personality
            seed=seed,
        )
        # Try to load the learned model
        self.model = None
        self._try_load_model()

        # Fallback: frequency table from logged data
        self.action_counts = {}
        self.total_decisions = 0

    def _try_load_model(self):
        """Try to load the latest trained model."""
        try:
            from backend.data.learning import load_model
            self.model = load_model()
        except Exception:
            self.model = None

    def learn_from_logs(self, action_log):
        """Load a list of (observation_features_dict, action_name) pairs.

        This builds the frequency table for the fallback mode.
        action_log: list of tuples (features_dict, action_str).
        """
        for features, action_name in action_log:
            # Build a simple key from the situation
            dist_ratio = features.get("distance", 0.5)
            enemy_stuck = features.get("enemy_recovery", 0) > 0
            key = (round(dist_ratio, 1), enemy_stuck)

            if key not in self.action_counts:
                self.action_counts[key] = {a: 0 for a in ALL_ACTIONS}

            try:
                action = Action[action_name]
                self.action_counts[key][action] += 1
                self.total_decisions += 1
            except KeyError:
                pass  # skip unknown actions

    def choose_action(self, obs):
        """Pick the action the human would most likely choose.

        Uses the trained model if available, otherwise the frequency table.
        """
        scores = {}

        if self.model is not None:
            # Use the trained model
            scores = self._model_scores(obs)
        elif self.action_counts:
            # Use the frequency table
            scores = self._frequency_scores(obs)
        else:
            # No data at all: act like a random fighter
            for action in ALL_ACTIONS:
                scores[action] = 1.0

        # Pick the best action
        best = max(scores, key=scores.get)
        return best, scores

    def _model_scores(self, obs):
        """Use the trained model to score each action."""
        from backend.data.learning import predict_action
        features = obs.features()

        # Get the model's prediction
        predicted = predict_action(self.model, features)

        # Turn it into scores: predicted action gets 10, others get 1
        scores = {}
        for action in ALL_ACTIONS:
            if action == predicted:
                scores[action] = 10.0
            else:
                scores[action] = 1.0

        return scores

    def _frequency_scores(self, obs):
        """Use the frequency table to score each action."""
        dist_ratio = obs.distance_ratio
        enemy_stuck = obs.enemy_is_stuck
        key = (round(dist_ratio, 1), enemy_stuck)

        counts = self.action_counts.get(key, None)
        if counts is None:
            # No data for this situation: uniform scores
            return {a: 1.0 for a in ALL_ACTIONS}

        # Turn counts into scores (add 1 for smoothing)
        scores = {}
        for action in ALL_ACTIONS:
            scores[action] = counts.get(action, 0) + 1.0

        return scores
