"""Golden Tactician AI: reads the enemy and adapts during the fight.

Golden is an adaptive strategist.
Golden starts with balanced preferences, but adapts them as it observes
the enemy's patterns (tracks how often they attack, block, jump, etc.).
"""

from backend.ai.actions import ALL_ACTIONS, ATTACKS, DEFENCE, Action
from backend.ai.fsm_base import (
    DISABLED, HEAVY_FAMILY, LIGHT_FAMILY, OUT_OF_RANGE, SKIP, THROW_RANGE,
    FighterTuning, FSMFighter, heavy_variant, light_variant, super_cost,
)
from backend.ai.observation import Observation
from backend.ai.personalities import GOLDEN
from backend.ai.zones import Spacing, Zone, spacing_for

HEAVY_REACH = 100.0


class GoldenAgent(FSMFighter):
    """Adaptive strategist who learns during the fight."""

    TUNING = FighterTuning(
        anti_air_hit=9.4, anti_air_close=6.8, anti_air_range=68.0,
        throw_vs_block=0.0, throw_normal=0.0,   # Golden's throw is scored in score_special
        jump_kick=8.5, jump_punch=8.2, jump_far=1.0,
        crouch_far=0.3, burst_health=0.40, idle=0.2,
    )

    def __init__(self, player=1, difficulty="LOW", seed=None):
        super().__init__("Golden", GOLDEN, player=player, difficulty=difficulty, seed=seed)
        self.enemy_action_counts = {a: 0 for a in ALL_ACTIONS}
        self.total_observations = 0
        self.current_likes = dict(self.personality.likes())

    def reset(self):
        super().reset()
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

    def shield_prediction(self, obs: Observation):
        attack_rate = self._attack_rate()
        return (attack_rate > 0.35 and obs.distance <= obs.enemy_reach + 60.0) or obs.enemy_is_attacking

    def _attack_rate(self) -> float:
        total = max(1, self.total_observations)
        return sum(self.enemy_action_counts.get(a, 0) for a in ATTACKS) / total

    def score_special(self, action: Action, obs: Observation, zone):
        likes = self.current_likes
        if action in (Action.FORWARD, Action.DASH):
            closeness_w = likes["closeness"] / 10
            mult = 1.2 if action == Action.DASH else 1.0
            if zone == Zone.FAR:
                return (6.0 + closeness_w * 3.5) * mult
            if zone == Zone.MID:
                return (5.5 + closeness_w * 3.5) * mult
            return 3.0 + closeness_w * 2.0 if not obs.i_can_hit else 1.0
        if action in (Action.BACK, Action.BACKDASH):
            safe_w = likes["safe_distance"] / 10
            if spacing_for(obs.distance, self.personality) == Spacing.TOO_CLOSE and not obs.i_can_hit:
                return 1.5 + safe_w * 2.0
            if obs.i_am_cornered:
                return 0.3
            return 0.8 + safe_w * 0.8
        if action == Action.JUMP:
            if obs.i_am_cornered:
                return 3.0 + likes["corner_avoid"] / 10 * 4.0
            return 2.0 if obs.enemy_is_attacking else 0.5
        if action in LIGHT_FAMILY:
            if obs.enemy_is_stuck and obs.i_can_hit:
                base = 8.2 + likes["block_punish"] / 10 * 2.0
            else:
                base = 9.4 if obs.i_can_hit else 0.5
            return light_variant(base, action, obs)
        if action in HEAVY_FAMILY:
            in_reach = obs.distance <= HEAVY_REACH
            if obs.enemy_is_stuck and in_reach:
                base = 8.2 + likes["block_punish"] / 10 * 2.0
            else:
                base = 9.1 if in_reach else 0.3
            return heavy_variant(base, action, obs)
        if action == Action.THROW:
            if obs.distance > THROW_RANGE:
                return OUT_OF_RANGE
            closeness_w = likes["closeness"] / 10
            return (6.8 + closeness_w * 3.0) if obs.enemy_is_blocking else (6.2 + closeness_w * 2.2)
        if action in (Action.BLOCK, Action.BLOCK_LOW):
            if obs.my_in_air:
                return SKIP
            punish_w = likes["block_punish"] / 10
            if obs.enemy_can_hit and obs.enemy_is_attacking:
                base_blk = 4.0 + punish_w * 4.0
            elif zone == Zone.CLOSE:
                base_blk = 2.0 + punish_w * 2.0
            else:
                base_blk = 0.5
            return base_blk if action == Action.BLOCK else base_blk * 0.85
        if action == Action.SPECIAL_NEUTRAL:   # Golden Read: predictive counter
            total = max(1, self.total_observations)
            top_count = max(self.enemy_action_counts.values()) if self.enemy_action_counts else 0
            has_habit = self.total_observations > 25 and (top_count / total > 0.35)
            if has_habit and zone in (Zone.MID, Zone.CLOSE):
                return 9.0
            return 7.2 if zone == Zone.MID else 0.2
        if action == Action.SPECIAL_DOWN:      # Tactician Stance
            return 2.5 if zone == Zone.FAR else 0.4
        if action == Action.SPECIAL_FORWARD:   # Gambit Strike
            if obs.distance > 95:
                return 0.5
            if obs.enemy_is_stuck:
                return 9.6
            return 8.4 if obs.enemy_is_open else 7.8
        if action == Action.SPECIAL_BACK:      # Tactical Step
            return 7.6 if obs.enemy_is_attacking and zone == Zone.CLOSE else 0.4
        if action == Action.SUPER:             # Checkmate
            if obs.my_meter >= super_cost(obs) and obs.distance <= 100:
                return 10.5 if obs.enemy_is_stuck or obs.enemy_hitstun > 0 else 7.5
            return DISABLED
        return None

    def panic_multiplier(self, action: Action) -> float:
        if action in (Action.LIGHT, Action.HEAVY, Action.LIGHT_KICK, Action.HEAVY_KICK, Action.FORWARD):
            return 1.3
        if action in (Action.BLOCK, Action.BLOCK_LOW):
            return 1.2
        return 1.0
