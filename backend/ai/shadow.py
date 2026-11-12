"""Shadow Striker AI: fast hit-and-run fighter.

Shadow uses its speed advantage to close in, land quick attacks,
then retreat. It avoids staying in close range where it takes damage.
"""

from backend.ai.actions import Action, ALL_ACTIONS
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import SHADOW
from backend.ai.zones import ZoneTracker, Zone


class ShadowAgent(Agent):
    """Fast, evasive hit-and-run fighter."""

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__(
            name="Shadow",
            player=player,
            difficulty=difficulty,
            personality=SHADOW,
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
                # Shadow needs to close distance to attack
                if zone == Zone.FAR:
                    score = 9.0  # sprint toward enemy
                elif zone == Zone.MID:
                    score = 7.0  # keep closing in
                elif not obs.i_can_hit:
                    score = 5.0  # not in range yet, move closer
                else:
                    score = 1.0  # in range, focus on attacking

                # Rush in when enemy is stuck (free punish)
                if obs.enemy_is_stuck and not obs.i_can_hit:
                    score = 8.0

            elif action == Action.BACK:
                # Back off only after attacking (hit and run)
                if obs.my_recovery > 0:
                    score = 0.3  # can't move in recovery anyway
                elif obs.i_am_cornered:
                    score = 0.2  # can't retreat, must escape forward
                elif zone == Zone.CLOSE and obs.my_cooldown > 0:
                    score = 3.0  # just attacked, back off while on cooldown
                else:
                    score = 0.5

            elif action == Action.JUMP:
                # Jump to escape corners
                if obs.i_am_cornered:
                    score = 7.0
                elif obs.enemy_is_attacking and zone == Zone.CLOSE:
                    score = 3.0  # dodge
                else:
                    score = 0.5

            elif action == Action.LIGHT:
                if not obs.can_attack:
                    continue
                # Shadow pokes with fast light attacks
                if obs.is_safe_poke:
                    score = 10.0  # best possible: hit without retaliation
                elif obs.i_can_hit and obs.enemy_is_stuck:
                    score = 10.0  # punish hard
                elif obs.i_can_hit:
                    score = 9.0  # in range = always attack
                elif obs.enemy_is_open and zone == Zone.MID:
                    score = 3.0  # enemy can't fight back, close in
                else:
                    score = 0.5

            elif action == Action.HEAVY:
                if not obs.can_attack:
                    continue
                # Heavy only on confirmed punishes (high risk otherwise)
                if obs.enemy_is_stuck and obs.i_can_hit:
                    score = 8.0
                elif obs.i_can_hit and obs.enemy_is_open:
                    score = 4.0
                else:
                    score = 0.2

            elif action == Action.BLOCK:
                if obs.my_in_air:
                    score = 0.0
                    continue
                if obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 6.0  # block when threatened
                else:
                    score = 0.5

            elif action == Action.IDLE:
                score = 0.2

            # --- Corner escape: top priority for Shadow ---
            if obs.i_am_cornered:
                if action == Action.FORWARD:
                    score += 5.0
                elif action == Action.JUMP:
                    score += 4.0

            # --- Panic mode: Shadow plays more carefully ---
            if panicking:
                aggression = p.panic_aggression  # 0.8
                if action in (Action.LIGHT, Action.HEAVY):
                    score *= aggression
                elif action == Action.BLOCK:
                    score *= 1.3

            scores[action] = score

        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
