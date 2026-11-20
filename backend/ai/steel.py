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
        from backend.ai.rumble_ai import evaluate_rumble_macro
        rumble_act = evaluate_rumble_macro(obs, self.name, self.difficulty, self.rng)
        if rumble_act is not None:
            return rumble_act, {rumble_act: 10.0}

        if obs.enable_shield_wall:
            from backend.ai.shield_ai import evaluate_shield_action
            shield_act = evaluate_shield_action(obs, self.name, self.difficulty, self.rng)
            if shield_act is not None:
                return shield_act, {shield_act: 10.0}

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
                if not obs.can_attack or obs.my_in_air:
                    continue
                if obs.enemy_is_stuck and obs.i_can_hit:
                    base = 10.0  # the block-punish!
                elif obs.enemy_is_open and obs.i_can_hit:
                    base = 8.5
                elif obs.i_can_hit:
                    base = 7.5
                else:
                    base = 0.3
                if action == Action.LIGHT:
                    score = base
                elif action == Action.LIGHT_KICK:
                    score = base * 0.90
                else:
                    score = base * 0.84

            elif action in (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD):
                if not obs.can_attack or obs.my_in_air:
                    continue
                if obs.enemy_is_stuck and obs.i_can_hit:
                    base = 9.5  # big punish!
                elif obs.i_can_hit:
                    base = 6.5
                else:
                    base = 0.2
                if action == Action.HEAVY:
                    score = base
                elif action == Action.HEAVY_KICK:
                    score = base * 0.88
                elif action == Action.LOW_SWEEP:
                    score = base * 0.82
                else:
                    score = base * 0.78

            elif action == Action.ANTI_AIR:
                if not obs.can_attack or obs.my_in_air:
                    continue
                score = 8.0 if obs.enemy_in_air and obs.i_can_hit else 0.2

            elif action == Action.THROW:
                if not obs.can_attack or obs.my_in_air:
                    continue
                score = 7.0 if obs.distance <= 40 and obs.enemy_is_blocking else 0.2

            elif action in (Action.BLOCK, Action.BLOCK_LOW):
                if obs.my_in_air:
                    score = 0.0
                elif obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 8.0 if action == Action.BLOCK else 7.2
                elif obs.enemy_can_hit:
                    score = 5.0 if action == Action.BLOCK else 4.2
                else:
                    score = 1.0 if action == Action.BLOCK else 0.7

            elif action in (Action.JUMP_PUNCH, Action.JUMP_KICK):
                if not obs.my_in_air or not obs.can_attack:
                    continue
                score = 7.5 if obs.distance <= 90 else 1.0

            elif action in (Action.CROUCH, Action.CROUCH_KICK):
                if obs.my_in_air or (action == Action.CROUCH_KICK and not obs.can_attack):
                    continue
                score = 1.0 if obs.i_can_hit else 0.2

            # --- Steel Signature Moves (Phase 4 & 5) ---
            elif action == Action.BURST:
                if obs.my_hitstun > 10 and obs.my_meter >= 50.0 and obs.my_health < 0.45:
                    score = 10.0
                else:
                    score = 0.0

            elif action == Action.SPECIAL_DOWN:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Iron Wall counter stance: triggers against incoming attacks
                score = 8.5 if (obs.enemy_can_hit and obs.enemy_is_attacking and obs.enemy_recovery == 0) else 0.2

            elif action == Action.SPECIAL_FORWARD:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Shield Bash: escape the corner or heavy pushback (costs 25 meter)
                if obs.my_meter >= 25.0 and obs.distance <= 80:
                    score = 9.8 if obs.i_am_cornered else 6.0
                else:
                    score = 0.2

            elif action == Action.SPECIAL_NEUTRAL:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Punisher Grip: slow command grab that beats blocking
                if obs.distance <= 52:
                    score = 9.5 if obs.enemy_is_blocking else 3.0
                else:
                    score = 0.2

            elif action == Action.SPECIAL_BACK:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Reflector: reflects projectiles
                score = 9.5 if obs.enemy_last_action == Action.SPECIAL_NEUTRAL else 0.1

            elif action == Action.SUPER:
                if not obs.can_attack or obs.my_in_air:
                    continue
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
