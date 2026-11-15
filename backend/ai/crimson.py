"""Crimson Brawler AI: rushes in and chains attacks.

Crimson loves being close to the enemy and hitting hard.
In panic mode (low health), Crimson gets even MORE aggressive.
"""

from backend.ai.actions import ALL_ACTIONS, Action
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import CRIMSON
from backend.ai.zones import Zone, ZoneTracker


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

            if action in (Action.FORWARD, Action.DASH):
                # Crimson loves moving in close
                mult = 1.3 if action == Action.DASH else 1.0
                if zone == Zone.FAR:
                    score = 9.0 * mult
                elif zone == Zone.MID:
                    score = 7.0 * mult
                elif not obs.i_can_hit:
                    score = 4.0 * mult
                else:
                    score = 1.0

            elif action in (Action.BACK, Action.BACKDASH):
                score = 0.3

            elif action == Action.JUMP:
                if zone == Zone.FAR:
                    score = 3.0
                elif obs.enemy_is_attacking and obs.distance <= 60:
                    score = 2.0
                else:
                    score = 0.3

            elif action in (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD):
                if not obs.can_attack:
                    continue
                can_hit_heavy = (obs.distance <= 85)
                if can_hit_heavy and obs.enemy_is_stuck:
                    score = 10.0  # huge punish!
                elif can_hit_heavy:
                    score = 9.5  # brawler wants high damage!
                else:
                    score = 0.5

            elif action in (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB):
                if not obs.can_attack:
                    continue
                if obs.i_can_hit:
                    score = 8.5
                    if obs.enemy_is_stuck:
                        score = 9.5
                elif zone == Zone.CLOSE:
                    score = 4.0
                else:
                    score = 0.5

            elif action == Action.ANTI_AIR:
                if not obs.can_attack:
                    continue
                score = 9.0 if obs.enemy_in_air and obs.i_can_hit else 0.2

            elif action == Action.THROW:
                if not obs.can_attack:
                    continue
                score = 9.0 if obs.distance <= 40 else 0.2

            elif action in (Action.BLOCK, Action.BLOCK_LOW):
                if obs.my_in_air:
                    score = 0.0
                elif obs.enemy_can_hit and obs.enemy_is_attacking:
                    score = 7.0
                else:
                    score = 0.5

            elif action in (Action.CROUCH, Action.CROUCH_KICK, Action.JUMP_PUNCH, Action.JUMP_KICK):
                score = 1.0 if obs.i_can_hit else 0.2

            # --- Signature Moves (Phase 4 & 5) ---
            elif action == Action.BURST:
                # Defensive burst when caught in combo at low health
                if obs.my_hitstun > 10 and obs.my_meter >= 50.0 and obs.my_health < 0.40:
                    score = 10.0
                else:
                    score = 0.0

            elif action == Action.SUPER:
                # Blood Fury 8-hit finisher
                super_cost = 60.0 if obs.my_health < 0.25 else 100.0
                if obs.my_meter >= super_cost and obs.distance <= 110:
                    score = 10.5 if obs.enemy_hitstun > 0 else 8.5
                else:
                    score = 0.0

            elif action == Action.SPECIAL_FORWARD:
                # Crimson Rush (dash punch / combo confirm)
                if obs.distance <= 95:
                    score = 9.8 if obs.enemy_hitstun > 0 else 7.5
                else:
                    score = 1.0

            elif action == Action.SPECIAL_NEUTRAL:
                # Rising Uppercut (anti-air launcher)
                score = 10.0 if obs.enemy_in_air and obs.distance <= 70 else 0.5

            elif action == Action.SPECIAL_BACK:
                # Berserker Charge (armored rushdown)
                score = 9.0 if obs.enemy_is_attacking and obs.distance <= 85 else 4.0

            elif action == Action.SPECIAL_DOWN:
                # Clinch Slam (command grab, beats block)
                if obs.distance <= 48:
                    score = 9.5 if obs.enemy_is_blocking else 6.0
                else:
                    score = 0.2

            elif action == Action.IDLE:
                score = 0.1

            else:
                score = 0.0

            # --- Panic mode: even MORE aggressive ---
            if panicking:
                if action in (Action.HEAVY, Action.HEAVY_KICK, Action.LIGHT, Action.FORWARD, Action.DASH):
                    score *= p.panic_aggression
                elif action in (Action.BLOCK, Action.BLOCK_LOW):
                    score *= 0.5

            scores[action] = score

        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
