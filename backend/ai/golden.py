"""Golden Tactician AI: reads the enemy and adapts during the fight.

Golden is an adaptive strategist.
Golden starts with balanced preferences, but adapts them as it observes
the enemy's patterns (tracks how often they attack, block, jump, etc.).
"""

from backend.ai.actions import ALL_ACTIONS, ATTACKS, DEFENCE, Action
from backend.ai.base_agent import Agent
from backend.ai.choice import pick
from backend.ai.observation import Observation
from backend.ai.personalities import GOLDEN
from backend.ai.zones import Spacing, Zone, ZoneTracker, spacing_for


class GoldenAgent(Agent):
    """Adaptive strategist who learns during the fight."""

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__(
            name="Golden",
            player=player,
            difficulty=difficulty,
            personality=GOLDEN,
            seed=seed,
        )
        self.zone_tracker = ZoneTracker()
        self.enemy_action_counts = {a: 0 for a in ALL_ACTIONS}
        self.total_observations = 0
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
            return

        p = self.personality
        speed = p.adapt_speed

        total = self.total_observations
        attack_rate = sum(self.enemy_action_counts.get(a, 0) for a in ATTACKS) / total
        block_rate = sum(self.enemy_action_counts.get(d, 0) for d in DEFENCE) / total

        base = p.likes()

        # If enemy attacks a lot, increase block_punish
        if attack_rate > 0.3:
            self.current_likes["block_punish"] = min(10, base["block_punish"] +
                                                      speed * 30 * (attack_rate - 0.3))
        else:
            self.current_likes["block_punish"] = base["block_punish"]

        # If enemy blocks a lot, increase closeness (to throw)
        if block_rate > 0.3:
            self.current_likes["closeness"] = min(10, base["closeness"] +
                                                   speed * 20 * (block_rate - 0.3))
        else:
            self.current_likes["closeness"] = base["closeness"]

        # If enemy rarely attacks, push forward
        if attack_rate < 0.1:
            self.current_likes["closeness"] = min(10, base["closeness"] +
                                                   speed * 20)

    def choose_action(self, obs: Observation):
        """Score every allowed action using adapted likes, then pick one."""
        from backend.ai.rumble_ai import evaluate_rumble_macro
        rumble_act = evaluate_rumble_macro(obs, self.name, self.difficulty, self.rng)
        if rumble_act is not None:
            return rumble_act, {rumble_act: 10.0}

        if obs.enable_shield_wall:
            from backend.ai.shield_ai import evaluate_shield_action
            attack_rate = sum(self.enemy_action_counts.get(a, 0) for a in ATTACKS) / max(1, self.total_observations)
            pred_attack = (attack_rate > 0.35 and obs.distance <= obs.enemy_reach + 60.0) or obs.enemy_is_attacking
            shield_act = evaluate_shield_action(
                obs, self.name, self.difficulty, self.rng, predicted_enemy_attack=pred_attack
            )
            if shield_act is not None:
                return shield_act, {shield_act: 10.0}

        scores = {}
        zone = self.zone_tracker.update(obs.distance)
        p = self.personality
        panicking = obs.is_panicking(p)
        likes = self.current_likes
        spacing = spacing_for(obs.distance, p)
        total = max(1, self.total_observations)
        attack_rate = sum(self.enemy_action_counts.get(a, 0) for a in ATTACKS) / total

        # --- Score each action ---
        for action in ALL_ACTIONS:
            score = 0.0

            if action in (Action.FORWARD, Action.DASH):
                closeness_w = likes["closeness"] / 10
                mult = 1.2 if action == Action.DASH else 1.0
                if zone == Zone.FAR:
                    score = (6.0 + closeness_w * 3.5) * mult
                elif zone == Zone.MID:
                    score = (5.5 + closeness_w * 3.5) * mult
                else:
                    score = (3.0 + closeness_w * 2.0 if not obs.i_can_hit else 1.0)

            elif action in (Action.BACK, Action.BACKDASH):
                safe_w = likes["safe_distance"] / 10
                if spacing == Spacing.TOO_CLOSE and not obs.i_can_hit:
                    score = 1.5 + safe_w * 2.0
                elif obs.i_am_cornered:
                    score = 0.3
                else:
                    score = 0.8 + safe_w * 0.8

            elif action == Action.JUMP:
                corner_w = likes["corner_avoid"] / 10
                if obs.i_am_cornered:
                    score = 3.0 + corner_w * 4.0
                elif obs.enemy_is_attacking:
                    score = 2.0
                else:
                    score = 0.5

            elif action in (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB):
                if not obs.can_attack or obs.my_in_air:
                    continue
                if obs.enemy_is_stuck and obs.i_can_hit:
                    punish_w = likes["block_punish"] / 10
                    base = 8.0 + punish_w * 2.0
                elif obs.i_can_hit:
                    base = 9.5
                else:
                    base = 0.5
                if action == Action.LIGHT:
                    score = base
                elif action == Action.LIGHT_KICK:
                    score = base * 0.90
                else:
                    score = base * 0.84

            elif action in (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD):
                if not obs.can_attack or obs.my_in_air:
                    continue
                can_hit_heavy = (obs.distance <= 100)
                if obs.enemy_is_stuck and can_hit_heavy:
                    punish_w = likes["block_punish"] / 10
                    base = 8.0 + punish_w * 2.0
                elif can_hit_heavy:
                    base = 9.0
                else:
                    base = 0.3
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
                score = 9.0 if obs.enemy_in_air and obs.i_can_hit else 0.2

            elif action == Action.THROW:
                if not obs.can_attack or obs.my_in_air:
                    continue
                closeness_w = likes["closeness"] / 10
                score = (6.0 + closeness_w * 3.0) if obs.distance <= 40 and obs.enemy_is_blocking else 0.2

            elif action in (Action.BLOCK, Action.BLOCK_LOW):
                if obs.my_in_air:
                    score = 0.0
                    continue
                punish_w = likes["block_punish"] / 10
                if obs.enemy_can_hit and obs.enemy_is_attacking:
                    base_blk = 4.0 + punish_w * 4.0
                elif zone == Zone.CLOSE:
                    base_blk = 2.0 + punish_w * 2.0
                else:
                    base_blk = 0.5
                score = base_blk if action == Action.BLOCK else base_blk * 0.85

            elif action in (Action.JUMP_PUNCH, Action.JUMP_KICK):
                if not obs.my_in_air or not obs.can_attack:
                    continue
                score = 8.0 if obs.distance <= 90 else 1.0

            elif action in (Action.CROUCH, Action.CROUCH_KICK):
                if obs.my_in_air or (action == Action.CROUCH_KICK and not obs.can_attack):
                    continue
                score = 1.0 if obs.i_can_hit else 0.3

            # --- Golden Signature Moves (Phase 4 & 5) ---
            elif action == Action.BURST:
                if obs.my_hitstun > 10 and obs.my_meter >= 50.0 and obs.my_health < 0.40:
                    score = 10.0
                else:
                    score = 0.0

            elif action == Action.SPECIAL_NEUTRAL:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Golden Read: predictive counter (uses when enemy has a distinct predictable habit)
                top_action_count = max(self.enemy_action_counts.values()) if self.enemy_action_counts else 0
                has_habit = self.total_observations > 40 and (top_action_count / total > 0.45)
                score = 8.5 if (has_habit and zone == Zone.MID) else 0.2

            elif action == Action.SPECIAL_DOWN:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Tactician Stance: stance transition
                score = 1.0 if zone == Zone.FAR else 0.2

            elif action == Action.SPECIAL_FORWARD:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Gambit Strike: high-risk high-reward poke
                if obs.enemy_is_stuck and obs.distance <= 90:
                    score = 9.5
                elif obs.distance <= 90 and obs.enemy_is_open:
                    score = 7.5
                else:
                    score = 0.5

            elif action == Action.SPECIAL_BACK:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Tactical Step: reposition
                score = 3.0 if obs.enemy_is_attacking and zone == Zone.CLOSE else 0.2

            elif action == Action.SUPER:
                if not obs.can_attack or obs.my_in_air:
                    continue
                # Checkmate super finisher
                super_cost = 60.0 if obs.my_health < 0.25 else 100.0
                if obs.my_meter >= super_cost and obs.distance <= 100:
                    score = 10.5 if obs.enemy_is_stuck or obs.enemy_hitstun > 0 else 7.5
                else:
                    score = 0.0

            elif action == Action.IDLE:
                score = 0.2

            else:
                score = 0.0

            # --- Panic mode ---
            if panicking:
                if action in (Action.LIGHT, Action.HEAVY, Action.LIGHT_KICK, Action.HEAVY_KICK, Action.FORWARD):
                    score *= 1.3
                elif action in (Action.BLOCK, Action.BLOCK_LOW):
                    score *= 1.2

            scores[action] = score

        chosen = pick(scores, self.rng, variety=p.variety)
        return chosen, scores
