"""A fighter that picks random moves. Used for testing and as the weakest opponent."""

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent


class RandomAgent(Agent):
    def __init__(self, player=1, seed=None, weights=None, min_hold=4, max_hold=12):
        super().__init__(name="Random", player=player, difficulty="LOW", seed=seed)

        # How likely each move is. Default: all moves equally likely.
        if weights is None:
            weights = {a: 1 for a in ALL_ACTIONS}

        # Safety checks: stop bad settings early with a clear message.
        for move, w in weights.items():
            if not isinstance(move, Action):
                raise TypeError(f"{move!r} is not a move. Use Action.LIGHT, not 'LIGHT'")
            if w < 0:
                raise ValueError(f"Weight for {move.name} cannot be negative")
        total = sum(weights.get(a, 0) for a in ALL_ACTIONS)
        if total <= 0:
            raise ValueError("At least one move needs a weight above 0")
        if min_hold < 1 or min_hold > max_hold:
            raise ValueError("Need 1 <= min_hold <= max_hold")

        self.probs = {a: weights.get(a, 0) / total for a in ALL_ACTIONS}

        # How many frames to keep doing the same move.
        self.min_hold = min_hold
        self.max_hold = max_hold
        self.current_action = None
        self.frames_left = 0

    def reset(self):
        super().reset()
        self.current_action = None
        self.frames_left = 0

    def choose_action(self, state):
        if self.frames_left <= 0:
            self.current_action = self.rng.choices(
                ALL_ACTIONS, weights=[self.probs[a] for a in ALL_ACTIONS]
            )[0]
            self.frames_left = self.rng.randint(self.min_hold, self.max_hold)
        self.frames_left -= 1
        self.last_scores = dict(self.probs)
        return self.current_action, dict(self.probs)
