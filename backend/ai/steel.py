"""Steel Guardian AI: blocks and punishes.

Steel waits for the enemy to attack, blocks it, then hits back
during the enemy's recovery. Very patient and defensive.
"""

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import STEEL
from backend.ai.zones import ZoneTracker, Zone


class SteelAgent(Agent):
    """Defensive counter-fighter."""

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__(
            name="Steel",
            player=player,
            difficulty=difficulty,
            personality=STEEL,
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

        for action in ALL_ACTIONS:
            score = 0.0

            if action == Action.FORWARD:
                # Steel moves in slowly, prefers mid range
                if zone == Zone.FAR:
                    score = 4.0
                elif zone == Zone.MID:
                    score = 2.0
                else:
                    score = 0.5

            elif action == Action.BACK:
                # Back up if too close and enemy is dangerous
                if zone == Zone.CLOSE and not obs.enemy_is_stuck:
                    score = 4.0
                elif obs.i_am_cornered:
                    score = 0.3  # can't go further
                else:
                    score = 1.5

            elif action == Action.JUMP:
                # Steel rarely jumps, but uses it to escape corners
                if obs.i_am_cornered and obs.enemy_can_hit:
                    score = 4.0
                else:
                    score = 0.5

            elif action == Action.LIGHT:
                if not obs.can_attack:
                    continue
                # Steel's bread and butter: punish enemy recovery
                if obs.enemy_is_stuck and obs.i_can_hit:
                    score = 10.0  # the block-punish!
                elif obs.enemy_is_open and obs.i_can_hit:
                    score = 7.0
                elif obs.i_can_hit:
                    score = 3.0
                else:
                    score = 0.3

            elif action == Action.HEAVY:
                if not obs.can_attack:
                    continue
                # Heavy punish when enemy is stuck (more damage, worth the risk)
                if obs.enemy_is_stuck and obs.i_can_hit:
                    score = 9.0  # big punish!
                elif obs.i_can_hit:
                    score = 2.0
                else:
                    score = 0.2

            elif action == Action.BLOCK:
                if obs.my_in_air:
                    score = 0.0
                    continue
                # Steel LOVES blocking
                if obs.enemy_can_hit:
                    score = 9.0  # block when enemy can hit
                elif zone == Zone.CLOSE:
                    score = 6.0  # stay guarded up close
                elif zone == Zone.MID:
                    score = 3.0
                else:
                    score = 1.5

            elif action == Action.IDLE:
                score = 0.3

            # --- Panic mode: Steel plays even safer ---
            if panicking:
                aggression = p.panic_aggression  # 0.7 for Steel
                if action in (Action.LIGHT, Action.HEAVY):
                    score *= aggression  # less attacking
                elif action == Action.BLOCK:
                    score *= 1.5  # more blocking
                elif action == Action.BACK:
                    score *= 1.3  # more retreating

            # --- Time pressure: if ahead and time is running out, play safe ---
            if obs.time_running_out and obs.health_lead > 0:
                if action in (Action.BLOCK, Action.BACK):
                    score *= 1.5  # run out the clock
                elif action in (Action.LIGHT, Action.HEAVY):
                    score *= 0.5  # less risk

            scores[action] = score

        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
