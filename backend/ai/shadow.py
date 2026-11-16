"""Shadow Striker AI: fast movement, long reach, poke and retreat.

Shadow is a hit-and-run fighter.
Shadow uses superior speed and reach to stay at the edge of attack range,
poking with safe attacks and escaping before the enemy can hit back.
In panic mode, Shadow runs away and looks for long-range pokes.
"""

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import SHADOW
from backend.ai.zones import Zone, ZoneTracker


class ShadowAgent(Agent):
    """Fast hit-and-run fighter."""

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

        # --- Score each action ---
        for action in ALL_ACTIONS:
            score = 0.0

            if action in (Action.FORWARD, Action.DASH):
                # Shadow needs to close distance to attack
                mult = 1.2 if action == Action.DASH else 1.0
                if zone == Zone.FAR:
                    score = 9.0 * mult
                elif zone == Zone.MID:
                    score = 7.0 * mult
                elif not obs.i_can_hit:
                    score = 5.0 * mult
                else:
                    score = 1.0

                if obs.enemy_is_stuck and not obs.i_can_hit:
                    score = 8.0 * mult

            elif action in (Action.BACK, Action.BACKDASH):
                mult = 1.3 if action == Action.BACKDASH else 1.0
                if obs.my_recovery > 0:
                    score = 0.3
                elif obs.i_am_cornered:
                    score = 0.2
                elif zone == Zone.CLOSE and obs.my_cooldown > 0:
                    score = 4.0 * mult
                else:
                    score = 0.8 * mult

            elif action == Action.JUMP:
                if obs.i_am_cornered:
                    score = 7.0
                elif obs.enemy_is_attacking and zone == Zone.CLOSE:
                    score = 3.0
                else:
                    score = 0.5

            elif action in (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB):
                if not obs.can_attack or obs.my_in_air:
                    continue
                if obs.is_safe_poke:
                    base = 10.0
                elif obs.i_can_hit and obs.enemy_is_stuck:
                    base = 10.0
                elif obs.i_can_hit:
                    base = 9.0
                elif obs.enemy_is_open and zone == Zone.MID:
                    base = 4.0
                else:
                    base = 0.5
                if action == Action.LIGHT:
                    score = base
                elif action == Action.LIGHT_KICK:
                    score = base * 0.90
                else:
                    score = base * 0.84

            elif action in (Action.HEAVY, Action.HEAVY_KICK, Action.OVERHEAD, Action.LOW_SWEEP):
                if not obs.can_attack or obs.my_in_air:
                    continue
                can_hit_heavy = (obs.distance <= 115)
                if obs.enemy_is_stuck and can_hit_heavy:
                    base = 9.5
                elif can_hit_heavy and obs.enemy_is_open:
                    base = 8.5
                elif can_hit_heavy:
                    base = 7.0
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
                score = 8.5 if obs.enemy_in_air and obs.i_can_hit else 0.2

            elif action == Action.THROW:
                if not obs.can_attack or obs.my_in_air:
                    continue
                score = 6.0 if obs.distance <= 40 and obs.enemy_is_blocking else 0.2

            elif action in (Action.BLOCK, Action.BLOCK_LOW):
                if obs.my_in_air:
                    score = 0.0
                elif obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 7.0 if action == Action.BLOCK else 6.2
                else:
                    score = 0.5 if action == Action.BLOCK else 0.3

            elif action in (Action.JUMP_PUNCH, Action.JUMP_KICK):
                if not obs.my_in_air or not obs.can_attack:
                    continue
                score = 8.5 if obs.distance <= 95 else 1.0

            elif action in (Action.CROUCH, Action.CROUCH_KICK):
                if obs.my_in_air or (action == Action.CROUCH_KICK and not obs.can_attack):
                    continue
                score = 1.0 if obs.i_can_hit else 0.3

            # --- Shadow Signature Moves (Phase 4 & 5) ---
            elif action == Action.BURST:
                if obs.my_hitstun > 10 and obs.my_meter >= 50.0 and obs.my_health < 0.40:
                    score = 10.0
                else:
                    score = 0.0

            elif action == Action.SPECIAL_NEUTRAL:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Energy Dart: projectile zoner
                score = 9.5 if zone in (Zone.FAR, Zone.MID) else 2.0

            elif action == Action.SPECIAL_FORWARD:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Shadow Step: close-range cross-up / corner escape
                if obs.i_am_cornered and obs.distance <= 130:
                    score = 9.5
                elif zone == Zone.CLOSE and obs.enemy_is_attacking:
                    score = 8.5
                else:
                    score = 0.8

            elif action == Action.SPECIAL_DOWN:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Phantom Kick: low string mixup
                score = 8.5 if obs.distance <= 85 else 0.5

            elif action == Action.SPECIAL_BACK:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Feint Strike: bait and reposition
                score = 7.0 if zone == Zone.CLOSE else 0.5

            elif action == Action.SUPER:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Vanishing Arts: teleport combo super
                super_cost = 60.0 if obs.my_health < 0.25 else 100.0
                if obs.my_meter >= super_cost and obs.distance <= 180:
                    score = 10.5 if obs.enemy_is_stuck or obs.enemy_hitstun > 0 else 7.0
                else:
                    score = 0.0

            elif action == Action.IDLE:
                score = 0.1

            else:
                score = 0.0

            # --- Panic mode: run away! ---
            if panicking:
                if action in (Action.BACK, Action.BACKDASH):
                    score *= 2.0
                elif action in (Action.FORWARD, Action.DASH):
                    score *= 0.3

            scores[action] = score

        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
