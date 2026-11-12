"""The template every fighter brain is built from, plus timing and safe fallback."""

import logging
import random
import time
from collections import deque
from contextlib import contextmanager

from backend.ai.actions import Action
from backend.ai.personalities import Personality

DIFFICULTIES = ("LOW", "MEDIUM", "HIGH", "HELL")
SAFE_ACTION = Action.BLOCK      # used if a fighter's brain crashes during a demo
FRAME_BUDGET_MS = 1000 / 60     # one frame at 60 FPS, about 16.7 milliseconds
HISTORY_FRAMES = 600            # remember the last 10 seconds of decision times

logger = logging.getLogger(__name__)


class Agent:
    def __init__(self, name="Agent", player=1, difficulty="LOW", personality=None, seed=None):
        # Safety checks: stop typos early with a clear message.
        if player not in (1, 2):
            raise ValueError(f"player must be 1 or 2, got {player!r}")
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}, got {difficulty!r}")
        if personality is not None and not isinstance(personality, Personality):
            raise TypeError("personality must be a Personality, like CRIMSON, not text")

        self.name = name                    # shown on screen
        self.player = player                # 1 or 2: which fighter this brain controls
        self.difficulty = difficulty        # "LOW", "MEDIUM", "HIGH" or "HELL"
        self.personality = personality      # this fighter's card (from personalities.py)
        self.rng = random.Random(seed)      # same seed = same fight every time
        self.last_scores = {}               # scores from the latest decision

        # True while building and testing: a crash stops the program so you see the bug.
        # Set to False on demo day: a crash is logged and the fighter blocks instead.
        self.strict = True

        # Speed measurements (in milliseconds)
        self.last_decision_ms = 0.0
        self.slowest_decision_ms = 0.0
        self.fallback_count = 0             # how many times the safe move was used
        self.over_budget_count = 0          # how many decisions took longer than one frame
        self.decision_times = deque(maxlen=HISTORY_FRAMES)  # recent times, for charts
        self.last_breakdown = {}            # time per part of the last decision

    def reset(self):
        """Called at the start of each round. Forget old notes."""
        self.last_scores = {}

    def observe(self, state, my_action, enemy_action):
        """Called after every frame. Learn from what just happened."""

    def choose_action(self, state):
        """Each fighter writes its own version. Return (action, scores)."""
        raise NotImplementedError

    def decide(self, state):
        """The game calls THIS every frame (not choose_action).
        It asks the brain for a move, times how long it took,
        and uses a safe move if the brain crashes (when strict is False)."""
        self.last_breakdown = {}
        start = time.perf_counter()
        try:
            action, scores = self.choose_action(state)
            if not isinstance(action, Action):
                raise TypeError(f"{self.name} returned {action!r}, which is not an Action")
        except Exception:
            if self.strict:
                raise
            logger.exception("%s crashed while deciding; using %s instead",
                             self.name, SAFE_ACTION.name)
            self.fallback_count += 1
            action, scores = SAFE_ACTION, {SAFE_ACTION: 1.0}

        took = (time.perf_counter() - start) * 1000
        self.last_decision_ms = took
        self.slowest_decision_ms = max(self.slowest_decision_ms, took)
        self.decision_times.append(took)
        if took > FRAME_BUDGET_MS:
            self.over_budget_count += 1
            logger.debug("%s took %.1f ms (budget %.1f ms)", self.name, took, FRAME_BUDGET_MS)
        self.last_scores = dict(scores)
        return action, scores

    @contextmanager
    def stage(self, name):
        """Time one part of a decision. Inside a fighter's choose_action:
            with self.stage("search"):
                ...
        The time goes into last_breakdown, e.g. {"search": 2.3}."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.last_breakdown[name] = (time.perf_counter() - start) * 1000

    @property
    def within_frame_budget(self):
        """True if even the slowest decision fit inside one frame."""
        return self.slowest_decision_ms <= FRAME_BUDGET_MS

    @property
    def budget_compliance(self):
        """Share of recent decisions that fit in one frame (1.0 = all of them)."""
        if not self.decision_times:
            return 1.0
        fits = sum(1 for t in self.decision_times if t <= FRAME_BUDGET_MS)
        return fits / len(self.decision_times)

    def __repr__(self):
        return f"{self.name} ({self.difficulty}, player {self.player})"
