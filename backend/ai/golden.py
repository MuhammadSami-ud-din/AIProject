"""Golden Tactician AI: adapts to the opponent's habits.

Golden starts balanced and then shifts its likes based on what the
opponent does. It counts the enemy's actions and adjusts strategy.
"""

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import GOLDEN
from backend.ai.zones import ZoneTracker, Zone, spacing_for, Spacing


class GoldenAgent(Agent):
    """Balanced adaptive fighter."""

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__(
            name="Golden",
            player=player,
            difficulty=difficulty,
            personality=GOLDEN,
            seed=seed,
        )
        self.zone_tracker = ZoneTracker()

        # Track enemy habits for adaptation
        self.enemy_action_counts = {a: 0 for a in ALL_ACTIONS}
        self.total_observations = 0

        # Current adapted likes (start same as personality, shift over time)
        self.current_likes = dict(self.personality.likes())

    def reset(self):
        super().reset()
        self.zone_tracker.reset()
        self.enemy_action_counts = {a: 0 for a in ALL_ACTIONS}
        self.total_observations = 0
        self.current_likes = dict(self.personality.likes())

    def observe(self, state, my_action, enemy_action):
        """Learn from the enemy's behaviour and adapt."""
        super().observe(state, my_action, enemy_action)
        self.enemy_action_counts[enemy_action] += 1
        self.total_observations += 1
        self._adapt()

    def _adapt(self):
        """Shift likes based on what the enemy does a lot."""
        if self.total_observations < 10:
            return  # not enough data yet

        p = self.personality
        speed = p.adapt_speed  # 0.1 for Golden

        total = self.total_observations
        attack_rate = (self.enemy_action_counts[Action.LIGHT] +
                       self.enemy_action_counts[Action.HEAVY]) / total
        block_rate = self.enemy_action_counts[Action.BLOCK] / total

        base = p.likes()

        # If the enemy attacks a lot, increase our block_punish preference
        if attack_rate > 0.3:
            self.current_likes["block_punish"] = min(10, base["block_punish"] +
                                                      speed * 30 * (attack_rate - 0.3))
        else:
            self.current_likes["block_punish"] = base["block_punish"]

        # If the enemy blocks a lot, increase closeness (get in and grab)
        if block_rate > 0.3:
            self.current_likes["closeness"] = min(10, base["closeness"] +
                                                   speed * 20 * (block_rate - 0.3))
        else:
            self.current_likes["closeness"] = base["closeness"]

        # If the enemy rarely attacks, push forward more aggressively
        if attack_rate < 0.1:
            self.current_likes["closeness"] = min(10, base["closeness"] +
                                                   speed * 20)

    def choose_action(self, obs: Observation):
        """Score every allowed action using adapted likes, then pick one."""
        scores = {}
        zone = self.zone_tracker.update(obs.distance)
        p = self.personality
        panicking = obs.is_panicking(p)
        likes = self.current_likes
        spacing = spacing_for(obs.distance, p)

        for action in ALL_ACTIONS:
            score = 0.0

            if action == Action.FORWARD:
                # Weight by closeness preference
                closeness_w = likes["closeness"] / 10  # 0 to 1
                if zone == Zone.FAR:
                    score = 3.0 + closeness_w * 5.0
                elif zone == Zone.MID:
                    score = 2.0 + closeness_w * 3.0
                else:
                    score = 1.0

            elif action == Action.BACK:
                safe_w = likes["safe_distance"] / 10
                if spacing == Spacing.TOO_CLOSE:
                    score = 2.0 + safe_w * 4.0
                elif obs.i_am_cornered:
                    score = 0.3
                else:
                    score = 1.0 + safe_w * 1.0

            elif action == Action.JUMP:
                corner_w = likes["corner_avoid"] / 10
                if obs.i_am_cornered:
                    score = 3.0 + corner_w * 4.0
                elif obs.enemy_is_attacking:
                    score = 2.0
                else:
                    score = 0.5

            elif action == Action.LIGHT:
                if not obs.can_attack:
                    continue
                if obs.enemy_is_stuck and obs.i_can_hit:
                    # Block-punish weighted by preference
                    punish_w = likes["block_punish"] / 10
                    score = 5.0 + punish_w * 5.0
                elif obs.i_can_hit:
                    score = 6.0
                else:
                    score = 0.5

            elif action == Action.HEAVY:
                if not obs.can_attack:
                    continue
                if obs.enemy_is_stuck and obs.i_can_hit:
                    punish_w = likes["block_punish"] / 10
                    score = 4.0 + punish_w * 5.0
                elif obs.i_can_hit:
                    score = 3.0
                else:
                    score = 0.3

            elif action == Action.BLOCK:
                if obs.my_in_air:
                    score = 0.0
                    continue
                punish_w = likes["block_punish"] / 10
                if obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 4.0 + punish_w * 4.0
                elif zone == Zone.CLOSE:
                    score = 2.0 + punish_w * 2.0
                else:
                    score = 1.0

            elif action == Action.IDLE:
                score = 0.3

            # --- Time pressure ---
            if obs.time_running_out:
                time_w = likes["time_pressure"] / 10
                if obs.health_lead > 0:
                    # We're ahead — play safe
                    if action in (Action.BLOCK, Action.BACK):
                        score *= 1.0 + time_w
                    elif action in (Action.LIGHT, Action.HEAVY):
                        score *= 1.0 - time_w * 0.5
                else:
                    # We're behind — attack more
                    if action in (Action.LIGHT, Action.HEAVY, Action.FORWARD):
                        score *= 1.0 + time_w * 0.5

            # --- Panic mode ---
            if panicking:
                aggression = p.panic_aggression  # 1.0 for Golden
                if action in (Action.LIGHT, Action.HEAVY, Action.FORWARD):
                    score *= aggression
                elif action == Action.BLOCK:
                    score *= 1.2

            scores[action] = score

        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
