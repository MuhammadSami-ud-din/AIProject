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
                if not obs.can_attack or obs.my_in_air:
                    continue
                can_hit_heavy = (obs.distance <= 85)
                if can_hit_heavy and obs.enemy_is_stuck:
                    base = 10.0  # huge punish!
                elif can_hit_heavy:
                    base = 9.5  # brawler wants high damage!
                else:
                    base = 0.5
                if action == Action.HEAVY:
                    score = base
                elif action == Action.HEAVY_KICK:
                    score = base * 0.97
                elif action == Action.LOW_SWEEP:
                    score = base * (1.03 if obs.enemy_is_blocking and not obs.enemy_is_crouching else 0.94)
                else:  # OVERHEAD
                    score = base * (1.03 if obs.enemy_is_crouching else 0.93)

            elif action in (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB, Action.CROUCH_KICK):
                if not obs.can_attack or obs.my_in_air:
                    continue
                if obs.i_can_hit:
                    base = 9.5 if obs.enemy_is_stuck else 8.8
                elif zone == Zone.CLOSE:
                    base = 4.0
                else:
                    base = 0.5
                if action == Action.LIGHT:
                    score = base
                elif action == Action.LIGHT_KICK:
                    score = base * 0.97
                elif action == Action.CROUCH_KICK:
                    score = base * (1.02 if obs.enemy_is_blocking and not obs.enemy_is_crouching else 0.94)
                else:  # CROUCH_JAB
                    score = base * 0.93

            elif action == Action.ANTI_AIR:
                if not obs.can_attack or obs.my_in_air:
                    continue
                score = 9.5 if obs.enemy_in_air and obs.i_can_hit else (7.0 if obs.distance <= 65 else 0.2)

            elif action == Action.THROW:
                if not obs.can_attack or obs.my_in_air:
                    continue
                score = (9.6 if obs.enemy_is_blocking else 8.6) if obs.distance <= 48 else 0.2

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
                score = (8.8 if action == Action.JUMP_KICK else 8.5) if obs.distance <= 95 else 1.5

            elif action == Action.CROUCH:
                if obs.my_in_air:
                    continue
                score = 1.0 if obs.i_can_hit else 0.2

            # --- Signature Moves (Phase 4 & 5) ---
            elif action == Action.BURST:
                # Defensive burst when caught in combo at low health
                if obs.my_hitstun > 10 and obs.my_meter >= 50.0 and obs.my_health < 0.40:
                    score = 10.0
                else:
                    score = 0.0

            elif action == Action.SUPER:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Blood Fury 8-hit finisher
                super_cost = 60.0 if obs.my_health < 0.25 else 100.0
                if obs.my_meter >= super_cost and obs.distance <= 110:
                    score = 10.5 if obs.enemy_hitstun > 0 else 9.2
                else:
                    score = 0.0

            elif action == Action.SPECIAL_FORWARD:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Crimson Rush (dash punch / combo confirm)
                if obs.distance <= 98:
                    score = 9.8 if obs.enemy_hitstun > 0 else 8.9
                else:
                    score = 1.2

            elif action == Action.SPECIAL_NEUTRAL:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Rising Uppercut (anti-air launcher & close punish)
                if obs.enemy_in_air and obs.distance <= 75:
                    score = 10.0
                elif obs.distance <= 68:
                    score = 8.7
                else:
                    score = 0.5

            elif action == Action.SPECIAL_BACK:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Berserker Charge (armored rushdown)
                score = 9.2 if obs.enemy_is_attacking and obs.distance <= 90 else (8.4 if obs.distance <= 85 else 3.5)

            elif action == Action.SPECIAL_DOWN:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Clinch Slam (command grab, beats block)
                if obs.distance <= 52:
                    score = 9.8 if obs.enemy_is_blocking else 8.5
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

        return self._select_action_with_rl_and_diversity(scores, obs, variety=p.variety)
