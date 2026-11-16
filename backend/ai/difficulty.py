"""Difficulty profiles, Adrenaline low-health boost, and DifficultyWrapper.

All difficulty settings live in ONE place: DIFFICULTY_PROFILES below,
using a frozen dataclass per mode (LOW, MEDIUM, HIGH, HELL).
No extra health or damage is given to any mode — only decision quality changes.
"""

from collections import deque
from dataclasses import dataclass
import os
from typing import Dict, Optional

from backend.ai.actions import ALL_ACTIONS, ATTACKS, DEFENCE, MOVEMENT, Action
from backend.ai.base_agent import Agent, DIFFICULTIES
from backend.ai.choice import pick
from backend.ai.opponent_model import OpponentModel


@dataclass(frozen=True)
class DifficultyProfile:
    """Complete decision-quality profile for one difficulty mode."""

    name: str
    reaction_delay: int             # frames of observation delay
    mistake_chance: float           # probability of picking 2nd/3rd best move
    decides_every_n_frames: int     # frame cadence between decisions
    block_chance: float             # chance to block an attack it has seen
    punish_chance: float            # chance to punish when enemy is stuck
    combo_completion: float         # chance to continue a hit-confirmed combo
    anti_air_chance: float          # chance to anti-air a jumping enemy
    hesitation: float               # chance to stay idle for a beat
    whiff_rate: float               # chance to throw an attack out of range
    search_depth: int               # minimax lookahead plies
    opponent_model: str             # "off", "counts", "bayes", "live"


# ======================================================================
# THE SINGLE DIFFICULTY PROFILE TABLE (Step 2)
# ======================================================================
DIFFICULTY_PROFILES: Dict[str, DifficultyProfile] = {
    "LOW": DifficultyProfile(
        name="LOW",
        reaction_delay=24,
        mistake_chance=0.35,
        decides_every_n_frames=12,
        block_chance=0.15,
        punish_chance=0.05,
        combo_completion=0.30,
        anti_air_chance=0.10,
        hesitation=0.25,
        whiff_rate=0.30,
        search_depth=1,
        opponent_model="off",
    ),
    "MEDIUM": DifficultyProfile(
        name="MEDIUM",
        reaction_delay=15,
        mistake_chance=0.18,
        decides_every_n_frames=8,
        block_chance=0.40,
        punish_chance=0.30,
        combo_completion=0.60,
        anti_air_chance=0.40,
        hesitation=0.12,
        whiff_rate=0.15,
        search_depth=2,
        opponent_model="counts",
    ),
    "HIGH": DifficultyProfile(
        name="HIGH",
        reaction_delay=8,
        mistake_chance=0.07,
        decides_every_n_frames=4,
        block_chance=0.70,
        punish_chance=0.70,
        combo_completion=0.85,
        anti_air_chance=0.75,
        hesitation=0.04,
        whiff_rate=0.05,
        search_depth=3,
        opponent_model="bayes",
    ),
    "HELL": DifficultyProfile(
        name="HELL",
        reaction_delay=2,
        mistake_chance=0.01,
        decides_every_n_frames=2,
        block_chance=0.90,
        punish_chance=0.95,
        combo_completion=0.98,
        anti_air_chance=0.95,
        hesitation=0.00,
        whiff_rate=0.01,
        search_depth=4,
        opponent_model="live",
    ),
}

# Derived lookup tables for backwards compatibility (never hard-coded separately)
REACTION_DELAY = {k: p.reaction_delay for k, p in DIFFICULTY_PROFILES.items()}
MISTAKE_CHANCE = {k: p.mistake_chance for k, p in DIFFICULTY_PROFILES.items()}
SEARCH_DEPTH = {k: p.search_depth for k, p in DIFFICULTY_PROFILES.items()}
COMBO_RELIABILITY = {k: p.combo_completion for k, p in DIFFICULTY_PROFILES.items()}

_NEXT_MODE = {
    "LOW": "MEDIUM",
    "MEDIUM": "HIGH",
    "HIGH": "HELL",
    "HELL": None,
}


# ======================================================================
# STEP 3: ADRENALINE (sharper as health drops, with smooth 5% transition)
# ======================================================================
def adrenaline_level(health: float) -> str:
    """Return the fighter's current adrenaline health zone: GREEN, YELLOW, or RED."""
    if health > 0.60:
        return "GREEN"
    if health >= 0.25:
        return "YELLOW"
    return "RED"


def _lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolate between a and b for t in [0, 1]."""
    t_clamped = max(0.0, min(1.0, t))
    return a + (b - a) * t_clamped


def effective_profile(difficulty: str, health: float) -> DifficultyProfile:
    """Compute the effective DifficultyProfile at the given health (0..1).

    - GREEN (health > 60%): normal values from DIFFICULTY_PROFILES.
    - YELLOW (25-60%): reaction_delay x0.8, mistake_chance x0.8,
                       block_chance & punish_chance x1.1.
    - RED (< 25%): reaction_delay x0.5, mistake_chance x0.5,
                   block/punish/anti_air x1.25, decides_every_n_frames - 1 (min 1),
                   hesitation = 0.
    - Smoothly interpolates over a 5% (0.05) health range around 0.60 (0.55..0.60)
      and around 0.25 (0.20..0.25) so there are no sudden jumps.
    - LIMIT: a mode in RED never becomes better than the NEXT mode's GREEN values
      (LOW red <= MEDIUM green, etc.). HELL in red can go down to 1-frame reaction.
    """
    if difficulty not in DIFFICULTY_PROFILES:
        raise ValueError(f"difficulty must be one of {DIFFICULTIES}")

    base = DIFFICULTY_PROFILES[difficulty]
    h = max(0.0, min(1.0, float(health)))

    # Pure Anchor Values for GREEN, YELLOW, RED (before next-mode cap)
    g_delay = float(base.reaction_delay)
    g_mistake = base.mistake_chance
    g_cadence = float(base.decides_every_n_frames)
    g_block = base.block_chance
    g_punish = base.punish_chance
    g_anti_air = base.anti_air_chance
    g_hesitation = base.hesitation

    y_delay = g_delay * 0.8
    y_mistake = g_mistake * 0.8
    y_cadence = g_cadence
    y_block = min(1.0, g_block * 1.1)
    y_punish = min(1.0, g_punish * 1.1)
    y_anti_air = g_anti_air
    y_hesitation = g_hesitation

    r_delay = g_delay * 0.5
    r_mistake = g_mistake * 0.5
    r_cadence = max(1.0, g_cadence - 1.0)
    r_block = min(1.0, g_block * 1.25)
    r_punish = min(1.0, g_punish * 1.25)
    r_anti_air = min(1.0, g_anti_air * 1.25)
    r_hesitation = 0.0

    # Smooth interpolation over 5% health bands:
    # Band 1: 0.60 down to 0.55 transitions GREEN -> YELLOW
    # Band 2: 0.25 down to 0.20 transitions YELLOW -> RED
    if h >= 0.60:
        cur_delay = g_delay
        cur_mistake = g_mistake
        cur_cadence = g_cadence
        cur_block = g_block
        cur_punish = g_punish
        cur_anti_air = g_anti_air
        cur_hesitation = g_hesitation
    elif h > 0.55:
        t = (0.60 - h) / 0.05
        cur_delay = _lerp(g_delay, y_delay, t)
        cur_mistake = _lerp(g_mistake, y_mistake, t)
        cur_cadence = _lerp(g_cadence, y_cadence, t)
        cur_block = _lerp(g_block, y_block, t)
        cur_punish = _lerp(g_punish, y_punish, t)
        cur_anti_air = _lerp(g_anti_air, y_anti_air, t)
        cur_hesitation = _lerp(g_hesitation, y_hesitation, t)
    elif h >= 0.25:
        cur_delay = y_delay
        cur_mistake = y_mistake
        cur_cadence = y_cadence
        cur_block = y_block
        cur_punish = y_punish
        cur_anti_air = y_anti_air
        cur_hesitation = y_hesitation
    elif h > 0.20:
        t = (0.25 - h) / 0.05
        cur_delay = _lerp(y_delay, r_delay, t)
        cur_mistake = _lerp(y_mistake, r_mistake, t)
        cur_cadence = _lerp(y_cadence, r_cadence, t)
        cur_block = _lerp(y_block, r_block, t)
        cur_punish = _lerp(y_punish, r_punish, t)
        cur_anti_air = _lerp(y_anti_air, r_anti_air, t)
        cur_hesitation = _lerp(y_hesitation, r_hesitation, t)
    else:
        cur_delay = r_delay
        cur_mistake = r_mistake
        cur_cadence = r_cadence
        cur_block = r_block
        cur_punish = r_punish
        cur_anti_air = r_anti_air
        cur_hesitation = r_hesitation

    # Enforce strict ceiling: never exceed the NEXT mode's GREEN values
    next_mode_name = _NEXT_MODE[difficulty]
    if next_mode_name is not None:
        bound = DIFFICULTY_PROFILES[next_mode_name]
        final_delay = max(bound.reaction_delay, int(round(cur_delay)))
        final_mistake = max(bound.mistake_chance, cur_mistake)
        final_cadence = max(bound.decides_every_n_frames, int(round(cur_cadence)))
        final_block = min(bound.block_chance, cur_block)
        final_punish = min(bound.punish_chance, cur_punish)
        final_anti_air = min(bound.anti_air_chance, cur_anti_air)
        final_hesitation = max(bound.hesitation, cur_hesitation)
    else:
        # HELL in red can go down to a 1-frame reaction
        final_delay = max(1, int(round(cur_delay)))
        final_mistake = max(0.0, cur_mistake)
        final_cadence = max(1, int(round(cur_cadence)))
        final_block = min(0.99, cur_block)
        final_punish = min(0.99, cur_punish)
        final_anti_air = min(0.99, cur_anti_air)
        final_hesitation = max(0.0, cur_hesitation)

    return DifficultyProfile(
        name=base.name,
        reaction_delay=final_delay,
        mistake_chance=final_mistake,
        decides_every_n_frames=final_cadence,
        block_chance=final_block,
        punish_chance=final_punish,
        combo_completion=base.combo_completion,
        anti_air_chance=final_anti_air,
        hesitation=final_hesitation,
        whiff_rate=base.whiff_rate,
        search_depth=base.search_depth,
        opponent_model=base.opponent_model,
    )


class DifficultyWrapper(Agent):
    """Wraps a fighter agent to apply the DifficultyProfile and Adrenaline boost."""

    def __init__(self, inner_agent: Agent, difficulty: str = "LOW"):
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")

        super().__init__(
            name=inner_agent.name,
            player=inner_agent.player,
            difficulty=difficulty,
            personality=inner_agent.personality,
            seed=None,
        )

        self.inner = inner_agent
        self.inner.difficulty = difficulty
        self.rng = inner_agent.rng

        self.base_profile: DifficultyProfile = DIFFICULTY_PROFILES[difficulty]
        self.current_profile: DifficultyProfile = self.base_profile
        self.health_zone: str = "GREEN"

        # Reaction delay buffer: stores recent observations
        self.delay: int = self.base_profile.reaction_delay
        self.obs_buffer = deque(maxlen=max(self.base_profile.reaction_delay + 5, 30))

        # Exposed difficulty settings (updated dynamically by Adrenaline & DDA)
        self.mistake_chance: float = self.base_profile.mistake_chance
        self.search_depth: int = self.base_profile.search_depth
        self.block_chance: float = self.base_profile.block_chance
        self.punish_chance: float = self.base_profile.punish_chance
        self.decides_every_n_frames: int = self.base_profile.decides_every_n_frames

        # Cadence & reactive state tracking
        self._frame_counter: int = 0
        self._held_action: Action = Action.IDLE
        self._last_scores: Dict[Action, float] = {Action.IDLE: 1.0}
        self._seen_enemy_attacking: bool = False
        self._block_decision_for_attack: bool = False
        self._block_hold_frames: int = 0
        self._seen_enemy_stuck: bool = False
        self._punish_decision_for_window: bool = False
        self.last_reaction_frames: Optional[int] = None

        # Opponent model setup per table ("off", "counts", "bayes", "live")
        self.use_search: bool = True
        self.use_opponent_model: bool = (self.base_profile.opponent_model != "off")
        self.use_learned_policy: bool = True
        self.opp_model: Optional[OpponentModel] = (
            OpponentModel() if self.base_profile.opponent_model in ("bayes", "live") else None
        )
        self.enemy_counts: Dict[Action, int] = {a: 0 for a in ALL_ACTIONS}

        # Dynamic Difficulty Adjustment (DDA, settings option for HIGH and HELL)
        self.adaptive_difficulty: bool = False
        self.recent_human_wins: list[float] = []
        self._dda_mistake_offset: float = 0.0

        # Learned policy blending (HIGH and HELL)
        self._learned_model = None
        self._policy_agent = None
        if self.use_learned_policy and self.difficulty in ("HIGH", "HELL"):
            self._try_load_learned_model()

    def update_dda(self, human_won: bool) -> None:
        """Update mistake chance dynamically to maintain 45-55% player win rate."""
        if not self.adaptive_difficulty or self.difficulty not in ("HIGH", "HELL"):
            return

        self.recent_human_wins.append(1.0 if human_won else 0.0)
        if len(self.recent_human_wins) > 5:
            self.recent_human_wins.pop(0)

        if len(self.recent_human_wins) >= 3:
            rate = sum(self.recent_human_wins) / len(self.recent_human_wins)
            if rate < 0.45:
                self._dda_mistake_offset = min(0.35, self._dda_mistake_offset + 0.05)
                self.mistake_chance = min(0.40, self.mistake_chance + 0.05)
            elif rate > 0.55:
                self._dda_mistake_offset = max(-0.05, self._dda_mistake_offset - 0.05)
                self.mistake_chance = max(0.01, self.mistake_chance - 0.05)

    def _try_load_learned_model(self) -> None:
        """Try to load the latest trained model for blending."""
        try:
            from backend.learning.league import ModelRegistry
            from backend.learning.policy_agent import PolicyAgent
            reg = ModelRegistry()
            char_name = self.inner.personality.name if self.inner.personality else "Crimson"
            live = reg.get_live_model(char_name)
            if live and os.path.exists(live["file_path"]):
                self._learned_model = live
                self._policy_agent = PolicyAgent(
                    char_name, model_path=live["file_path"], player=self.player
                )
                return
        except Exception:
            pass

        try:
            from backend.data.learning import load_model
            self._learned_model = load_model()
        except Exception:
            self._learned_model = None

    def reset(self) -> None:
        """Reset for a new round."""
        super().reset()
        self.inner.reset()
        self.obs_buffer.clear()
        self.current_profile = self.base_profile
        self.health_zone = "GREEN"
        self.delay = self.base_profile.reaction_delay
        self.mistake_chance = max(0.01, min(0.45, self.base_profile.mistake_chance + self._dda_mistake_offset))
        self.block_chance = self.base_profile.block_chance
        self.punish_chance = self.base_profile.punish_chance
        self.decides_every_n_frames = self.base_profile.decides_every_n_frames
        self._frame_counter = 0
        self._held_action = Action.IDLE
        self._last_scores = {Action.IDLE: 1.0}
        self._seen_enemy_attacking = False
        self._block_decision_for_attack = False
        self._block_hold_frames = 0
        self._seen_enemy_stuck = False
        self._punish_decision_for_window = False
        self.enemy_counts = {a: 0 for a in ALL_ACTIONS}
        if self.opp_model is not None:
            self.opp_model.reset()

    def observe(self, state, my_action: Action, enemy_action: Action) -> None:
        """Called after every frame."""
        self.inner.observe(state, my_action, enemy_action)
        if self.use_opponent_model:
            self.enemy_counts[enemy_action] = self.enemy_counts.get(enemy_action, 0) + 1
            if self.opp_model is not None:
                self.opp_model.observe(state, my_action, enemy_action)

    def _apply_adrenaline(self, my_health: float) -> DifficultyProfile:
        """Update current profile and live attributes based on current health."""
        prof = effective_profile(self.difficulty, my_health)
        self.current_profile = prof
        self.health_zone = adrenaline_level(my_health)
        self.delay = prof.reaction_delay
        self.mistake_chance = max(0.0, min(0.45, prof.mistake_chance + self._dda_mistake_offset))
        self.block_chance = prof.block_chance
        self.punish_chance = prof.punish_chance
        self.decides_every_n_frames = prof.decides_every_n_frames
        self.search_depth = prof.search_depth
        return prof

    def choose_action(self, obs):
        """Choose an action applying reaction delay, cadence, block/punish/combo/whiff gates, and Adrenaline."""
        with self.stage("difficulty"):
            prof = self._apply_adrenaline(obs.my_health)

            # 1. Push current observation into reaction buffer and fetch delayed observation
            if len(self.obs_buffer) == 0:
                for _ in range(prof.reaction_delay):
                    self.obs_buffer.append(obs)
            self.obs_buffer.append(obs)
            if len(self.obs_buffer) > prof.reaction_delay:
                delayed_obs = self.obs_buffer[-prof.reaction_delay - 1]
            else:
                delayed_obs = self.obs_buffer[0]

            self._frame_counter += 1
            self.last_reaction_frames = None

            # 2. Detect newly seen enemy attack in the delayed observation
            enemy_attack_seen_now = (
                delayed_obs.enemy_is_attacking and delayed_obs.distance <= 165
            )
            just_saw_attack = enemy_attack_seen_now and not self._seen_enemy_attacking
            self._seen_enemy_attacking = enemy_attack_seen_now

            is_low_threat = (
                delayed_obs.enemy_is_crouching
                or delayed_obs.enemy_last_action in (
                    Action.LOW_SWEEP, Action.CROUCH_JAB, Action.CROUCH_KICK
                )
            )

            if just_saw_attack:
                self.last_reaction_frames = max(1, prof.reaction_delay)
                # Roll block_chance at the exact moment the delayed observation sees the attack!
                self._block_decision_for_attack = (self.rng.random() < prof.block_chance)
                if self._block_decision_for_attack:
                    self._block_hold_frames = 14

            if self._block_hold_frames > 0:
                self._block_hold_frames -= 1
                if not obs.my_in_air:
                    blk = Action.BLOCK_LOW if is_low_threat else Action.BLOCK
                    self._held_action = blk
                    self._last_scores = {blk: 10.0, Action.IDLE: 1.0}
                    return blk, self._last_scores

            # 3. Detect newly seen enemy recovery (punish opportunity)
            enemy_stuck_now = (delayed_obs.enemy_is_stuck or obs.enemy_is_stuck) and obs.distance <= 115
            if enemy_stuck_now and not self._seen_enemy_stuck:
                self._punish_decision_for_window = (self.rng.random() < prof.punish_chance)
            self._seen_enemy_stuck = enemy_stuck_now

            # 4. Decision Cadence: only re-decide every N frames (unless reacting to a newly seen attack)
            is_decision_tick = (
                self._frame_counter == 1
                or (self._frame_counter % prof.decides_every_n_frames == 0)
                or just_saw_attack
            )
            if not is_decision_tick:
                # Between decision ticks: hold movement/crouch, or IDLE if an attack was already triggered
                if self._held_action in (Action.FORWARD, Action.BACK, Action.CROUCH):
                    return self._held_action, self._last_scores
                return Action.IDLE, self._last_scores

            # 5. Hesitation check: stays idle for a beat with probability `prof.hesitation`
            if not just_saw_attack and self.rng.random() < prof.hesitation:
                self._held_action = Action.IDLE
                self._last_scores = {Action.IDLE: 5.0}
                return Action.IDLE, self._last_scores

            # 6. Ask inner personality agent for base move scores on delayed observation
            _, raw_scores = self.inner.choose_action(delayed_obs)
            if not raw_scores:
                return Action.IDLE, {Action.IDLE: 1.0}
            scores = dict(raw_scores)

            # 7. Apply Block Gate: only block when an attack was seen AND block roll succeeded
            if enemy_attack_seen_now and self._block_decision_for_attack and not obs.my_in_air:
                blk = Action.BLOCK_LOW if delayed_obs.enemy_is_crouching else Action.BLOCK
                scores[blk] = max(scores.values()) + 5.0
            else:
                # Do not pre-emptively hold block when no attack has been seen or block roll failed
                scores[Action.BLOCK] = 0.05
                scores[Action.BLOCK_LOW] = 0.05

            # 8. Apply Anti-Air Gate against jumping opponents
            if delayed_obs.enemy_in_air and delayed_obs.distance <= 110 and obs.can_attack and not obs.my_in_air:
                if self.rng.random() < prof.anti_air_chance:
                    scores[Action.ANTI_AIR] = max(scores.values()) + 4.0
                else:
                    scores[Action.ANTI_AIR] = 0.05

            # 9. Apply Punish Gate when enemy is stuck
            if enemy_stuck_now and obs.can_attack and not obs.my_in_air:
                if self._punish_decision_for_window:
                    if obs.distance <= 85 and Action.HEAVY in scores:
                        scores[Action.HEAVY] = max(scores.values()) + 4.5
                    elif Action.LIGHT in scores:
                        scores[Action.LIGHT] = max(scores.values()) + 4.0
                else:
                    # Missed punish opportunity: suppress attacks this tick
                    for atk in ATTACKS:
                        if atk in scores:
                            scores[atk] *= 0.08

            # 10. Apply Combo Completion Gate when continuing a combo
            if obs.my_combo_count >= 1:
                if self.rng.random() > prof.combo_completion:
                    # Drop the combo
                    for atk in ATTACKS:
                        if atk in scores:
                            scores[atk] = 0.05
                    scores[Action.IDLE] = 5.0

            # 11. Apply Whiff Gate when out of range
            out_of_melee_range = (not obs.i_can_hit) and (obs.distance > 95)
            if out_of_melee_range and obs.can_attack and not obs.my_in_air:
                if self.rng.random() < prof.whiff_rate:
                    # Deliberate out-of-range whiff (common on LOW, rare on HELL)
                    scores[Action.LIGHT] = max(scores.values()) + 3.0
                else:
                    # Suppress out-of-range melee normals so sharp AI closes distance instead of whiffing
                    for melee_act in (
                        Action.LIGHT, Action.HEAVY, Action.LIGHT_KICK, Action.HEAVY_KICK,
                        Action.CROUCH_JAB, Action.CROUCH_KICK, Action.LOW_SWEEP,
                        Action.OVERHEAD, Action.THROW, Action.ANTI_AIR,
                    ):
                        if melee_act in scores:
                            scores[melee_act] = 0.05

            # 12. Opponent Model adjustments ("counts", "bayes", "live")
            if self.use_opponent_model and prof.opponent_model != "off":
                scores = self._apply_opponent_model(scores, delayed_obs, prof)

            # 13. Blend in learned model suggestions (HIGH and HELL)
            if self.use_learned_policy and self.difficulty in ("HIGH", "HELL") and self._learned_model is not None:
                scores = self._blend_learned_scores(scores, delayed_obs)

            # 14. Scale softmax variety by difficulty so HIGH/HELL play sharply while preserving personality
            base_variety = self.inner.personality.variety if self.inner.personality else 0.1
            variety_scale = {"LOW": 1.0, "MEDIUM": 0.65, "HIGH": 0.25, "HELL": 0.05}[self.difficulty]
            effective_variety = base_variety * variety_scale

            chosen = pick(
                scores,
                self.rng,
                variety=effective_variety,
                mistake_chance=self.mistake_chance,
            )

            # Ensure a mistake on LOW/MEDIUM actually picks a weaker move when mistake triggers
            if self.rng.random() < self.mistake_chance:
                ordered = sorted(scores, key=lambda a: scores[a], reverse=True)
                if len(ordered) >= 6:
                    chosen = self.rng.choice(ordered[2:6])

            self._held_action = chosen
            self._last_scores = scores
            return chosen, scores

    def _apply_opponent_model(
        self, scores: Dict[Action, float], obs, prof: DifficultyProfile
    ) -> Dict[Action, float]:
        """Adjust move scores based on the difficulty's opponent model tier."""
        adjusted = dict(scores)
        predicted_action: Optional[Action] = None

        if prof.opponent_model == "counts":
            total = sum(self.enemy_counts.values())
            if total >= 10:
                predicted_action = max(self.enemy_counts, key=lambda a: self.enemy_counts[a])
        elif prof.opponent_model in ("bayes", "live") and self.opp_model is not None:
            predicted_action = self.opp_model.predict(obs)

        if predicted_action is None:
            return adjusted

        mult = 2.5 if prof.opponent_model == "live" else 1.5
        if predicted_action in DEFENCE:
            # Enemy likes to block -> counter with throw, low sweep, or overhead
            if obs.distance <= 45 and Action.THROW in adjusted:
                adjusted[Action.THROW] += mult
            if Action.LOW_SWEEP in adjusted and obs.distance <= 85:
                adjusted[Action.LOW_SWEEP] += mult * 0.8
            if Action.OVERHEAD in adjusted and obs.distance <= 85:
                adjusted[Action.OVERHEAD] += mult * 0.8
        elif predicted_action in ATTACKS and obs.distance <= 110:
            # Enemy about to attack -> boost fast counter-poke or block
            if Action.LIGHT in adjusted and obs.i_can_hit:
                adjusted[Action.LIGHT] += mult
        elif predicted_action in (Action.BACK, Action.BACKDASH):
            # Enemy retreating -> chase down with dash or forward
            if Action.DASH in adjusted:
                adjusted[Action.DASH] += mult
            if Action.FORWARD in adjusted:
                adjusted[Action.FORWARD] += mult * 0.8

        return adjusted

    def _blend_learned_scores(self, scores: Dict[Action, float], obs) -> Dict[Action, float]:
        """Blend the inner agent's scores with the learned model's prediction."""
        try:
            if self._policy_agent is not None:
                pred_action, _ = self._policy_agent.choose_action(obs)
                blended = dict(scores)
                if pred_action in blended:
                    max_score = max(blended.values())
                    blended[pred_action] += max_score * 0.3
                return blended

            from backend.data.learning import predict_action
            predicted = predict_action(self._learned_model, obs.features())

            BLEND_WEIGHT = 0.3
            blended = dict(scores)
            if predicted in blended:
                max_score = max(blended.values())
                blended[predicted] += max_score * BLEND_WEIGHT
            return blended
        except Exception:
            return scores
