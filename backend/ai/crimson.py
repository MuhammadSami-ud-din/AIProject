"""Crimson Brawler AI: rushes in and chains attacks.

Crimson loves being close to the enemy and hitting hard.
In panic mode (low health), Crimson gets even MORE aggressive.
"""

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import CRIMSON
from backend.ai.zones import ZoneTracker, zone_of, Zone


class CrimsonAgent(Agent):
    """Aggressive rush-down fighter."""

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__(
            name="Crimson",
            player=player,
            difficulty=difficulty,
            personality=CRIMSON,
            seed=seed,
        )
        self.zone_tracker = ZoneTracker()

    def reset(self):
        super().reset()
        self.zone_tracker.reset()

    def choose_action(self, obs: Observation):
        """Score every allowed action, then pick one."""
        scores = {}
        zone = self.zone_tracker.update(obs.distance)
        p = self.personality
        panicking = obs.is_panicking(p)

        # --- Score each action ---
        for action in ALL_ACTIONS:
            score = 0.0

            if action == Action.FORWARD:
                # Crimson loves moving in close
                if zone == Zone.FAR:
                    score = 8.0  # run at them!
                elif zone == Zone.MID:
                    score = 5.0
                else:
                    score = 1.0  # already close enough

            elif action == Action.BACK:
                # Crimson rarely retreats
                if obs.i_am_cornered:
                    score = 0.5  # can't go further anyway
                else:
                    score = 0.5

            elif action == Action.JUMP:
                # Jump to close distance fast or dodge
                if zone == Zone.FAR:
                    score = 3.0
                elif obs.enemy_is_attacking:
                    score = 2.0  # dodge an attack
                else:
                    score = 0.5

            elif action == Action.LIGHT:
                if not obs.can_attack:
                    continue  # skip — on cooldown or in recovery
                if obs.i_can_hit:
                    score = 9.0  # in range, attack!
                    if obs.enemy_is_stuck:
                        score = 10.0  # punish their recovery
                elif zone == Zone.CLOSE:
                    score = 4.0  # close but not quite in range
                else:
                    score = 0.5

            elif action == Action.HEAVY:
                if not obs.can_attack:
                    continue  # skip
                if obs.i_can_hit and obs.enemy_is_stuck:
                    score = 10.0  # big punish!
                elif obs.i_can_hit:
                    score = 6.0  # in range, heavy hits hard
                else:
                    score = 0.3

            elif action == Action.BLOCK:
                if obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 5.0  # block their attack
                elif obs.my_in_air:
                    score = 0.0  # can't block in air
                else:
                    score = 1.0

            elif action == Action.IDLE:
                score = 0.2

            # --- Panic mode: Crimson gets more aggressive ---
            if panicking:
                aggression = p.panic_aggression  # 1.5 for Crimson
                if action in (Action.LIGHT, Action.HEAVY, Action.FORWARD):
                    score *= aggression
                elif action == Action.BLOCK:
                    score *= 0.5  # less blocking when panicking

            scores[action] = score

        # Pick an action using the personality's variety
        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
