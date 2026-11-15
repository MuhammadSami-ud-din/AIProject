"""Steel Guardian AI: waits, blocks, and punishes mistakes.

Steel is a defensive counter-fighter.
Steel prefers to stand at mid range, block incoming attacks,
and counter-hit during the enemy's recovery.
"""

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import STEEL
from backend.ai.zones import Zone, ZoneTracker


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

        # --- Score each action ---
        for action in ALL_ACTIONS:
            score = 0.0

            if action in (Action.FORWARD, Action.DASH):
                if zone == Zone.FAR:
                    score = 4.0
                elif zone == Zone.MID:
                    score = 2.0
                else:
                    score = 0.5

            elif action in (Action.BACK, Action.BACKDASH):
                if zone == Zone.CLOSE and not obs.enemy_is_stuck:
                    score = 4.0
                elif obs.i_am_cornered:
                    score = 0.3
                else:
                    score = 1.5

            elif action == Action.JUMP:
                if obs.i_am_cornered and obs.enemy_can_hit:
                    score = 4.0
                else:
                    score = 0.5

            elif action in (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB):
                if not obs.can_attack:
                    continue
                if obs.enemy_is_stuck and obs.i_can_hit:
                    score = 10.0  # the block-punish!
                elif obs.enemy_is_open and obs.i_can_hit:
                    score = 8.5
                elif obs.i_can_hit:
                    score = 7.5
                else:
                    score = 0.3

            elif action in (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD):
                if not obs.can_attack:
                    continue
                if obs.enemy_is_stuck and obs.i_can_hit:
                    score = 9.5  # big punish!
                elif obs.i_can_hit:
                    score = 6.5
                else:
                    score = 0.2

            elif action == Action.ANTI_AIR:
                if not obs.can_attack:
                    continue
                score = 8.0 if obs.enemy_in_air and obs.i_can_hit else 0.2

            elif action == Action.THROW:
                if not obs.can_attack:
                    continue
                score = 7.0 if obs.distance <= 40 and obs.enemy_is_blocking else 0.2

            elif action in (Action.BLOCK, Action.BLOCK_LOW):
                if obs.my_in_air:
                    score = 0.0
                elif obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 8.0  # block incoming hit!
                elif obs.enemy_can_hit:
                    score = 5.0  # be ready to block
                else:
                    score = 1.0

            elif action in (Action.CROUCH, Action.CROUCH_KICK, Action.JUMP_PUNCH, Action.JUMP_KICK):
                score = 1.0 if obs.i_can_hit else 0.2

            # --- Steel Signature Moves (Phase 4 & 5) ---
            elif action == Action.BURST:
                if obs.my_hitstun > 10 and obs.my_meter >= 50.0 and obs.my_health < 0.45:
                    score = 10.0
                else:
                    score = 0.0

            elif action == Action.SPECIAL_DOWN:
                # Iron Wall counter stance: triggers against incoming attacks
                score = 8.5 if (obs.enemy_can_hit and obs.enemy_is_attacking and obs.enemy_recovery == 0) else 0.2

            elif action == Action.SPECIAL_FORWARD:
                # Shield Bash: escape the corner or heavy pushback (costs 25 meter)
                if obs.my_meter >= 25.0 and obs.distance <= 80:
                    score = 9.8 if obs.i_am_cornered else 6.0
                else:
                    score = 0.2

            elif action == Action.SPECIAL_NEUTRAL:
                # Punisher Grip: slow command grab that beats blocking
                if obs.distance <= 52:
                    score = 9.5 if obs.enemy_is_blocking else 3.0
                else:
                    score = 0.2

            elif action == Action.SPECIAL_BACK:
                # Reflector: reflects projectiles
                score = 9.5 if obs.enemy_last_action == Action.SPECIAL_NEUTRAL else 0.1

            elif action == Action.SUPER:
                # Fortress Crush: counter super stance
                super_cost = 60.0 if obs.my_health < 0.25 else 100.0
                if obs.my_meter >= super_cost and obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 10.5
                else:
                    score = 0.0

            elif action == Action.IDLE:
                score = 0.5

            else:
                score = 0.0

            # --- Panic mode: turtle up ---
            if panicking:
                if action in (Action.BLOCK, Action.BLOCK_LOW):
                    score *= 1.5
                elif action in (Action.FORWARD, Action.DASH):
                    score *= 0.5

            scores[action] = score

        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
