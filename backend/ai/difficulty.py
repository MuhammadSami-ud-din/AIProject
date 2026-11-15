"""Difficulty wrapper: adds reaction delay, mistakes, and search depth.

Wraps any fighter agent to make it easier or harder:
  - Reaction delay: sees an observation from N frames ago.
  - Mistake chance: sometimes picks 2nd or 3rd best move.
  - Search depth: how many plies of minimax to use.
  - Learned policy: HIGH+ can use a trained model to boost scores.
"""

from collections import deque

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.base_agent import Agent, DIFFICULTIES
from backend.ai.choice import pick

# How many frames of delay for each difficulty level
REACTION_DELAY = {"LOW": 24, "MEDIUM": 15, "HIGH": 7, "HELL": 1}

# How often the AI picks a suboptimal move
MISTAKE_CHANCE = {"LOW": 0.30, "MEDIUM": 0.15, "HIGH": 0.05, "HELL": 0.01}

# How many plies of minimax search
SEARCH_DEPTH = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "HELL": 4}


class DifficultyWrapper(Agent):
    """Wraps a fighter agent to add difficulty-based handicaps.

    The inner agent does the actual thinking (scoring moves).
    This wrapper adds:
      1. Reaction delay: the agent sees an old observation.
      2. Mistake chance: sometimes picks a worse move.
      3. Passes difficulty settings through for search/opponent model.
      4. Learned policy: can blend in a trained model's suggestions.
    """

    def __init__(self, inner_agent, difficulty="LOW"):
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")

        super().__init__(
            name=inner_agent.name,
            player=inner_agent.player,
            difficulty=difficulty,
            personality=inner_agent.personality,
            seed=None,  # use inner agent's rng
        )

        self.inner = inner_agent
        self.inner.difficulty = difficulty

        # Use the inner agent's RNG for consistency
        self.rng = inner_agent.rng

        # Reaction delay buffer: stores recent observations
        self.delay = REACTION_DELAY[difficulty]
        self.obs_buffer = deque(maxlen=max(self.delay + 1, 2))

        # Difficulty settings
        self.mistake_chance = MISTAKE_CHANCE[difficulty]
        self.search_depth = SEARCH_DEPTH[difficulty]

        # Feature switches for ablation studies
        self.use_search = True
        self.use_opponent_model = True
        self.use_learned_policy = True

        # Try to load a trained model for learned-policy blending
        self._learned_model = None
        if self.use_learned_policy:
            self._try_load_learned_model()

    def _try_load_learned_model(self):
        """Try to load the latest trained model for blending."""
        try:
            from backend.data.learning import load_model
            self._learned_model = load_model()
        except Exception:
            self._learned_model = None

    def reset(self):
        """Reset for a new round."""
        super().reset()
        self.inner.reset()
        self.obs_buffer.clear()

    def observe(self, state, my_action, enemy_action):
        """Called after every frame."""
        self.inner.observe(state, my_action, enemy_action)

    def choose_action(self, obs):
        """Get the inner agent's scores, then apply difficulty handicaps."""
        # Store this observation in the buffer
        self.obs_buffer.append(obs)

        # Use a delayed observation (simulates slow reactions)
        if len(self.obs_buffer) > self.delay:
            delayed_obs = self.obs_buffer[-self.delay - 1]
        else:
            # Not enough history yet — use the oldest available
            delayed_obs = self.obs_buffer[0]

        # Ask the inner agent to score moves based on the delayed observation
        _, scores = self.inner.choose_action(delayed_obs)

        if not scores:
            return Action.IDLE, {Action.IDLE: 1.0}

        # Blend in learned model suggestions (HIGH+ only)
        if self.use_learned_policy and self._learned_model is not None:
            scores = self._blend_learned_scores(scores, delayed_obs)

        # Apply mistake chance using pick()
        chosen = pick(
            scores,
            self.rng,
            variety=self.inner.personality.variety if self.inner.personality else 0.0,
            mistake_chance=self.mistake_chance,
        )

        return chosen, scores

    def _blend_learned_scores(self, scores, obs):
        """Blend the inner agent's scores with the learned model's prediction.

        The learned model gets a weight of 0.3 — it nudges the decision
        toward what historically winning fighters did, without overriding
        the fighter's own logic.
        """
        try:
            from backend.data.learning import predict_action
            predicted = predict_action(self._learned_model, obs.features())

            # Boost the predicted action's score by 30%
            BLEND_WEIGHT = 0.3
            blended = dict(scores)
            if predicted in blended:
                max_score = max(blended.values())
                bonus = max_score * BLEND_WEIGHT
                blended[predicted] += bonus

            return blended
        except Exception:
            # If anything goes wrong, just use original scores
            return scores
