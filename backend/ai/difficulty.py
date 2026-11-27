"""Difficulty profiles, Adrenaline low-health boost, and DifficultyWrapper.

All difficulty settings live in ONE place: DIFFICULTY_PROFILES below,
using a frozen dataclass per mode (LOW, MEDIUM, HIGH, HELL).
No extra health or damage is given to any mode — only decision quality changes.
"""

from collections import deque
from dataclasses import dataclass
import logging
import os
import time
from typing import Dict, Optional

from backend.ai.actions import ALL_ACTIONS, ATTACKS, DEFENCE, MOVEMENT, Action
from backend.ai.base_agent import Agent, DIFFICULTIES
from backend.ai.choice import pick
from backend.ai.opponent_model import OpponentModel
from backend.ai.qlearning import OnlineCombatLearner, get_shared_combat_learner


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
    search_depth: int               # lookahead plies (HELL runs the in-game search)
    opponent_model: str             # "off", "counts", "bayes", "live"
    # Human-like execution (Step 11): reaction time is sampled per reaction,
    # not fixed, and inputs are occasionally dropped or pressed late.
    reaction_jitter: float = 0.0    # std-dev (frames) of the sampled reaction delay
    input_drop_chance: float = 0.0  # chance a chosen input is not executed
    input_late_chance: float = 0.0  # chance a chosen input comes 1-3 frames late
    policy_weight: float = 0.0      # weight of the learned policy in the final scores


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
        reaction_jitter=6.0,
        input_drop_chance=0.06,
        input_late_chance=0.1,
        policy_weight=0.0,
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
        reaction_jitter=4.0,
        input_drop_chance=0.03,
        input_late_chance=0.06,
        policy_weight=0.0,
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
        reaction_jitter=2.5,
        input_drop_chance=0.012,
        input_late_chance=0.03,
        policy_weight=0.5,
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
        reaction_jitter=1.0,
        input_drop_chance=0.003,
        input_late_chance=0.01,
        policy_weight=0.7,
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

logger = logging.getLogger(__name__)

# Cache of resolved learned-model paths: character -> (signature, path or None).
# The signature combines the registry state and the checkpoint folder's file
# names/mtimes, so a newly trained or promoted model is picked up at the next
# round instead of a stale "no model" result being cached forever.
_LEARNED_MODEL_CACHE: Dict[str, tuple] = {}

# In-game search (HELL): only when the fighters are close enough for the next
# plies to matter, with a hard per-call budget.
SEARCH_ENGAGE_DISTANCE = 220.0
SEARCH_BUDGET_S = 0.003
SEARCH_CANDIDATES = 5
EXPECTIMAX_MIN_ACCURACY = 0.35   # opponent-model accuracy needed for expectimax
EXPECTIMAX_MIN_PREDICTIONS = 30


def resolve_learned_model(character: str, models_dir: Optional[str] = None,
                          registry_path: Optional[str] = None) -> Optional[str]:
    """Path of the model HIGH/HELL should use for ``character`` (or None).

    Order: registry "live" row (if its file is compatible) -> newest compatible
    checkpoint in models/<character>/ that the gate did not roll back ->
    bc_model.pt. Cached with invalidation.
    """
    try:
        from backend.learning.checkpoints import (
            checkpoint_signature, find_latest_checkpoint, load_compatible_state_dict,
        )
        from backend.learning.league import ModelRegistry
    except Exception:
        logger.warning("learning stack unavailable; HIGH/HELL use the FSM only", exc_info=True)
        return None

    reg = None
    reg_sig: tuple = ()
    try:
        reg = ModelRegistry(registry_path)
        reg_sig = reg.signature(character)
    except Exception:
        logger.warning("model registry unavailable", exc_info=True)
    sig = (reg_sig, checkpoint_signature(character, models_dir), models_dir, registry_path)
    cache_key = f"{character}|{models_dir}|{registry_path}"
    cached = _LEARNED_MODEL_CACHE.get(cache_key)
    if cached is not None and cached[0] == sig:
        return cached[1]

    path = None
    rejected = []
    if reg is not None:
        try:
            live = reg.get_live_model(character)
            if live and os.path.exists(live["file_path"]) and load_compatible_state_dict(live["file_path"]) is not None:
                path = live["file_path"]
            rejected = [r["file_path"] for r in reg.list_models(character) if r["status"] == "rolled_back"]
        except Exception:
            logger.warning("could not read live model for %s", character, exc_info=True)
    if path is None:
        # No promoted model: newest checkpoint the promotion gate has not rejected.
        path = find_latest_checkpoint(character, models_dir, exclude=rejected)
    _LEARNED_MODEL_CACHE[cache_key] = (sig, path)
    return path


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
        reaction_jitter=base.reaction_jitter,
        input_drop_chance=base.input_drop_chance,
        input_late_chance=base.input_late_chance,
        policy_weight=base.policy_weight,
    )


class DifficultyWrapper(Agent):
    """Wraps a fighter agent to apply the DifficultyProfile and Adrenaline boost.

    Decision pipeline per frame: sampled (jittered) reaction delay -> reactive
    gates (block / anti-air / punish / combo / whiff) -> opponent model ->
    learned policy blend (HIGH/HELL) -> in-game search (HELL) -> online
    Q-learning -> one probabilistic pick with ONE mistake roll -> human-like
    input execution (occasional dropped / late inputs).

    Match-flow hooks for the game: ``on_round_end(result)`` and
    ``on_match_end(result)`` (result = "p1"/"p2"/"draw" or "win"/"loss"/"draw"
    from this AI's point of view) feed Dynamic Difficulty Adjustment when
    ``adaptive_difficulty`` is enabled.
    """

    def __init__(self, inner_agent: Agent, difficulty: str = "LOW",
                 use_learned_policy: bool = True, use_search: bool = True,
                 use_opponent_model: bool = True, models_dir: Optional[str] = None,
                 registry_path: Optional[str] = None, adaptive_difficulty: bool = False):
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

        # Reaction delay: ``delay`` is the profile's mean; the delay actually
        # used is re-sampled with jitter at every decision / newly seen attack.
        self.delay: int = self.base_profile.reaction_delay
        self.current_reaction_delay: int = self.base_profile.reaction_delay
        self.obs_buffer = deque(maxlen=max(self.base_profile.reaction_delay * 2 + 10, 40))

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
        self._prev_can_attack: bool = True
        self.last_reaction_frames: Optional[int] = None

        # Human-like input execution
        self._late_action: Optional[Action] = None
        self._late_frames: int = 0
        self.dropped_inputs: int = 0
        self.late_inputs: int = 0
        self.mistakes_made: int = 0

        # Opponent model & live online reinforcement learner (per character AND side)
        self.use_search: bool = use_search
        self.use_opponent_model: bool = use_opponent_model
        self.use_learned_policy: bool = use_learned_policy
        self.opp_model: Optional[OpponentModel] = OpponentModel()
        self.enemy_counts: Dict[Action, int] = {a: 0 for a in ALL_ACTIONS}
        self.rl_learner: OnlineCombatLearner = get_shared_combat_learner(self.inner.name, self.player)

        # In-game search diagnostics
        self.last_search: Optional[dict] = None
        self.search_calls: int = 0
        self.search_over_budget: int = 0

        # Dynamic Difficulty Adjustment (settings option for HIGH and HELL)
        self.adaptive_difficulty: bool = adaptive_difficulty
        self.recent_human_wins: list[float] = []
        self._dda_mistake_offset: float = 0.0

        # Learned policy (HIGH and HELL)
        self.models_dir = models_dir
        self.registry_path = registry_path
        self._learned_model = None      # path of the loaded model (or None)
        self._policy_agent = None
        if self.use_learned_policy and self.difficulty in ("HIGH", "HELL"):
            self._try_load_learned_model()

    # ------------------------------------------------------------------
    # Dynamic Difficulty Adjustment + match-flow hooks
    # ------------------------------------------------------------------
    def update_dda(self, human_won: bool) -> None:
        """Update mistake chance dynamically to keep the player's win rate near 45-55%."""
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

    def _human_won(self, result: str) -> Optional[bool]:
        r = (result or "").strip().lower()
        mine = "p1" if self.player == 1 else "p2"
        theirs = "p2" if self.player == 1 else "p1"
        if r in ("win", mine):
            return False
        if r in ("loss", "lose", theirs):
            return True
        return None   # draw / unknown: no DDA signal

    def on_round_end(self, result: str) -> None:
        """Call after every round. ``result``: "p1"/"p2"/"draw" or "win"/"loss" (AI's view)."""
        human_won = self._human_won(result)
        if human_won is not None:
            self.update_dda(human_won)

    def on_match_end(self, result: str) -> None:
        """Call after a match; refreshes the learned model if a new one was promoted."""
        if self.use_learned_policy and self.difficulty in ("HIGH", "HELL"):
            self._try_load_learned_model()

    # ------------------------------------------------------------------
    def _try_load_learned_model(self) -> None:
        """Load the newest usable policy for this character (cached, invalidated on change)."""
        char_name = self.inner.personality.name if self.inner.personality else self.inner.name
        path = resolve_learned_model(char_name, self.models_dir, self.registry_path)
        if path == self._learned_model and (path is None or self._policy_agent is not None):
            return
        self._learned_model, self._policy_agent = None, None
        if path is None:
            return
        try:
            from backend.learning.policy_agent import PolicyAgent

            agent = PolicyAgent(char_name, model_path=path, player=self.player, use_registry=False)
            if agent.model is not None:
                self._learned_model, self._policy_agent = path, agent
        except Exception:
            logger.warning("failed to load learned policy %s; using FSM only", path, exc_info=True)

    def reset(self) -> None:
        """Reset for a new round (preserves learned Q-table and opponent habit counts)."""
        super().reset()
        self.inner.reset()
        self.obs_buffer.clear()
        self.current_profile = self.base_profile
        self.health_zone = "GREEN"
        self.delay = self.base_profile.reaction_delay
        self.current_reaction_delay = self.delay
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
        self._prev_can_attack = True
        self._late_action, self._late_frames = None, 0
        if self.opp_model is not None:
            self.opp_model.reset()
        self.rl_learner.reset_round()
        if self.use_learned_policy and self.difficulty in ("HIGH", "HELL"):
            self._try_load_learned_model()

    def observe(self, state, my_action: Action, enemy_action: Action) -> None:
        """Called after every frame: updates inner agent, opponent model, and live Q-learner."""
        self.inner.observe(state, my_action, enemy_action)
        self.rl_learner.observe(state, my_action, enemy_action)
        if self.use_opponent_model:
            eff_enemy = enemy_action if enemy_action != Action.IDLE else state.enemy_last_action
            if eff_enemy != Action.IDLE:
                self.enemy_counts[eff_enemy] = self.enemy_counts.get(eff_enemy, 0) + 1
            if self.opp_model is not None:
                self.opp_model.observe(state, eff_enemy, my_action)

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

    def _sample_delay(self, mean_delay: int, jitter: float) -> int:
        """Human reaction time: a fresh sample around the mean (never below 1 frame)."""
        if jitter <= 0:
            return max(1, int(mean_delay))
        return max(1, int(round(self.rng.gauss(mean_delay, jitter))))

    def _execute(self, action: Action, prof: DifficultyProfile) -> Action:
        """Human-like execution: occasionally drop an input or press it late."""
        r = self.rng.random()
        if r < prof.input_drop_chance:
            self.dropped_inputs += 1
            return Action.IDLE
        if r < prof.input_drop_chance + prof.input_late_chance:
            self.late_inputs += 1
            self._late_action = action
            self._late_frames = 1 + int(self.rng.random() * 3)
            return Action.IDLE
        return action

    def choose_action(self, obs):
        """Choose an action applying reaction delay, cadence, RL adaptation, and move diversity."""
        with self.stage("difficulty"):
            prof = self._apply_adrenaline(obs.my_health)

            # A late input from a previous decision fires once its delay has passed.
            if self._late_action is not None:
                self._late_frames -= 1
                if self._late_frames <= 0:
                    late, self._late_action = self._late_action, None
                    return late, self._last_scores
                return Action.IDLE, self._last_scores

            # Check if the opponent is repeating a move/pattern so the AI adapts its focus
            spam_move, spam_intensity = self.rl_learner.detect_spam(obs)
            eff_block_chance = min(0.95, prof.block_chance + 0.50 * spam_intensity)
            eff_punish_chance = min(0.96, prof.punish_chance + 0.55 * spam_intensity)
            eff_anti_air_chance = min(0.96, prof.anti_air_chance + 0.55 * spam_intensity)
            eff_hesitation = max(0.0, prof.hesitation * (1.0 - 0.75 * spam_intensity))
            mean_delay = max(1, int(prof.reaction_delay * (1.0 - 0.45 * spam_intensity)))

            # 1. Reaction buffer: the AI acts on what it saw current_reaction_delay frames ago
            if len(self.obs_buffer) == 0:
                for _ in range(mean_delay):
                    self.obs_buffer.append(obs)
            self.obs_buffer.append(obs)
            d = min(self.current_reaction_delay, len(self.obs_buffer) - 1)
            delayed_obs = self.obs_buffer[-d - 1]

            self._frame_counter += 1
            self.last_reaction_frames = None

            # 2. A newly SEEN enemy attack (seen through the reaction delay)
            enemy_attack_seen_now = delayed_obs.enemy_is_attacking and delayed_obs.distance <= 165
            just_saw_attack = enemy_attack_seen_now and not self._seen_enemy_attacking
            self._seen_enemy_attacking = enemy_attack_seen_now

            is_low_threat = (
                delayed_obs.enemy_is_crouching
                or delayed_obs.enemy_last_action in (Action.LOW_SWEEP, Action.CROUCH_JAB, Action.CROUCH_KICK)
                or spam_move in (Action.LOW_SWEEP, Action.CROUCH_JAB, Action.CROUCH_KICK)
            )

            if just_saw_attack:
                self.last_reaction_frames = self.current_reaction_delay
                self._block_decision_for_attack = (self.rng.random() < eff_block_chance)
                if self._block_decision_for_attack:
                    self._block_hold_frames = 12
                # next reaction gets a fresh human reaction time
                self.current_reaction_delay = self._sample_delay(mean_delay, prof.reaction_jitter)

            if self._block_hold_frames > 0:
                self._block_hold_frames -= 1
                if not obs.my_in_air:
                    blk = Action.BLOCK_LOW if is_low_threat else Action.BLOCK
                    self._held_action = blk
                    self._last_scores = {blk: 10.0, Action.IDLE: 1.0}
                    self.rl_learner.record_decision(obs, blk)
                    return blk, self._last_scores

            # 3. Newly seen enemy recovery (punish opportunity)
            enemy_stuck_now = delayed_obs.enemy_is_stuck and delayed_obs.distance <= 125
            if enemy_stuck_now and not self._seen_enemy_stuck:
                self._punish_decision_for_window = (self.rng.random() < eff_punish_chance)
            self._seen_enemy_stuck = enemy_stuck_now

            just_recovered = obs.can_attack and not self._prev_can_attack
            self._prev_can_attack = obs.can_attack

            # 4. Decision cadence
            eff_cadence = max(2, int(prof.decides_every_n_frames * (1.0 - 0.35 * spam_intensity)))
            is_decision_tick = (
                self._frame_counter == 1
                or (self._frame_counter % eff_cadence == 0)
                or just_saw_attack
                or enemy_stuck_now
                or just_recovered
            )
            if not is_decision_tick:
                if self._held_action in (Action.FORWARD, Action.BACK, Action.DASH, Action.BACKDASH, Action.CROUCH):
                    return self._held_action, self._last_scores
                return Action.IDLE, self._last_scores
            self.current_reaction_delay = self._sample_delay(mean_delay, prof.reaction_jitter)

            # 4.5 Rumble macro-action check (Zone retreat, Build cover, Smash walls, Loot)
            from backend.ai.rumble_ai import evaluate_rumble_macro
            rumble_act = evaluate_rumble_macro(obs, self.inner.name, self.difficulty, self.rng)
            if rumble_act is not None:
                self._held_action = rumble_act
                self._last_scores = {rumble_act: 10.0}
                return rumble_act, self._last_scores

            # 4.6 Shield Wall decision check
            if obs.enable_shield_wall:
                from backend.ai.shield_ai import evaluate_shield_action
                shield_act = evaluate_shield_action(obs, self.inner.name, self.difficulty, self.rng)
                if shield_act is not None:
                    self._held_action = shield_act
                    self._last_scores = {shield_act: 10.0}
                    return shield_act, self._last_scores

            # 5. Hesitation check
            if not just_saw_attack and not enemy_stuck_now and obs.distance <= 140 and self.rng.random() < eff_hesitation:
                self._held_action = Action.IDLE
                self._last_scores = {Action.IDLE: 5.0}
                return Action.IDLE, self._last_scores

            # 6. Ask inner personality agent for base move scores
            _, raw_scores = self.inner.choose_action(delayed_obs)
            if not raw_scores:
                return Action.IDLE, {Action.IDLE: 1.0}
            scores = dict(raw_scores)

            # 7. Block gate
            if enemy_attack_seen_now and self._block_decision_for_attack and not obs.my_in_air:
                blk = Action.BLOCK_LOW if is_low_threat else Action.BLOCK
                scores[blk] = max(scores.values()) + 5.0
            else:
                scores[Action.BLOCK] = 0.05
                scores[Action.BLOCK_LOW] = 0.05

            # 8. Anti-air gate against jumping opponents
            if delayed_obs.enemy_in_air and obs.distance <= 110 and obs.can_attack and not obs.my_in_air:
                if self.rng.random() < eff_anti_air_chance:
                    top_s = max(scores.values())
                    scores[Action.ANTI_AIR] = top_s + 3.5
                    if Action.SPECIAL_NEUTRAL in scores and self.inner.name == "Crimson":
                        scores[Action.SPECIAL_NEUTRAL] = top_s + 3.4
                else:
                    scores[Action.ANTI_AIR] = 0.05

            # 9. Punish gate when enemy is stuck
            if enemy_stuck_now and obs.can_attack and not obs.my_in_air:
                if self._punish_decision_for_window:
                    for atk in (
                        Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.OVERHEAD,
                        Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB, Action.CROUCH_KICK,
                        Action.SPECIAL_FORWARD, Action.SPECIAL_DOWN, Action.SPECIAL_NEUTRAL,
                        Action.SUPER,
                    ):
                        if atk in scores and scores[atk] >= 5.0:
                            scores[atk] = scores[atk] * 1.28 + 1.8
                else:
                    for atk in ATTACKS:
                        if atk in scores:
                            scores[atk] *= 0.08

            # 10. Combo completion gate
            if obs.my_combo_count >= 1:
                if self.rng.random() > prof.combo_completion:
                    for atk in ATTACKS:
                        if atk in scores:
                            scores[atk] = 0.05
                    scores[Action.IDLE] = 5.0

            # 11. Whiff gate when out of range
            out_of_melee_range = (not obs.i_can_hit) and (obs.distance > 125)
            if out_of_melee_range and obs.can_attack and not obs.my_in_air:
                if self.rng.random() < prof.whiff_rate:
                    whiff_pool = [a for a in (Action.LIGHT, Action.LIGHT_KICK, Action.HEAVY_KICK, Action.CROUCH_KICK) if a in scores]
                    if whiff_pool:
                        scores[self.rng.choice(whiff_pool)] = max(scores.values()) + 3.0
                else:
                    for melee_act in (
                        Action.LIGHT, Action.HEAVY, Action.LIGHT_KICK, Action.HEAVY_KICK,
                        Action.CROUCH_JAB, Action.CROUCH_KICK, Action.LOW_SWEEP,
                        Action.OVERHEAD, Action.THROW, Action.ANTI_AIR,
                    ):
                        if melee_act in scores:
                            scores[melee_act] = 0.05

            # 12. Opponent model adjustments
            if self.use_opponent_model:
                scores = self._apply_opponent_model(scores, delayed_obs, prof)

            must_consider = []
            # 13. Learned policy (HIGH / HELL)
            if self.use_learned_policy and self._policy_agent is not None and prof.policy_weight > 0:
                scores, policy_top = self._blend_learned_scores(scores, delayed_obs, prof.policy_weight)
                if policy_top is not None:
                    must_consider.append(policy_top)

            # 14. In-game search (HELL), hard time budget
            if self.use_search and prof.search_depth >= 4 and delayed_obs.distance <= SEARCH_ENGAGE_DISTANCE:
                best = self._run_search(scores, delayed_obs)
                if best is not None and best in scores:
                    scores[best] = max(scores.values()) * 1.15 + 0.5
                    must_consider.append(best)

            # 15. Online reinforcement learning (Q-values, anti-spam, diversity decay)
            scores, _ = self.rl_learner.adjust_scores(scores, delayed_obs, self.difficulty)

            # 16. One pick with ONE mistake roll
            base_variety = self.inner.personality.variety if self.inner.personality else 0.25
            variety_scale = {"LOW": 1.15, "MEDIUM": 1.00, "HIGH": 0.85, "HELL": 0.75}[self.difficulty]
            effective_variety = min(0.65, max(0.24, base_variety * variety_scale))

            max_s = max(scores.values()) if scores else 1.0
            viable_scores = {a: s for a, s in scores.items() if s >= max_s * 0.58 and s > 0.1}
            for a in must_consider:
                if a in scores:
                    viable_scores[a] = scores[a]
            if len(viable_scores) < 2:
                viable_scores = scores

            eff_mistake = max(0.0, self.mistake_chance * (1.0 - 0.65 * spam_intensity))
            if self.rng.random() < eff_mistake:
                # Human-like mistake: a clearly worse but still sensible move
                ordered = [a for a in sorted(scores, key=lambda a: scores[a], reverse=True) if scores[a] > 0.1]
                pool = ordered[1:5] if len(ordered) >= 3 else ordered[1:]
                chosen = self.rng.choice(pool) if pool else pick(viable_scores, self.rng, variety=effective_variety)
                self.mistakes_made += 1
            else:
                chosen = pick(viable_scores, self.rng, variety=effective_variety)

            self.rl_learner.record_decision(obs, chosen)
            self._held_action = chosen
            self._last_scores = scores
            return self._execute(chosen, prof), scores

    def _run_search(self, scores: Dict[Action, float], obs) -> Optional[Action]:
        """Depth-1 simultaneous search over the top candidates (expectimax or minimax)."""
        from backend.ai.search import simultaneous_search, state_from_observation

        try:
            candidates = [a for a in sorted(scores, key=lambda a: scores[a], reverse=True)
                          if scores[a] > 0.1 and a.value < 27][:SEARCH_CANDIDATES]
            if len(candidates) < 2:
                return None
            mode, probs = "minimax", None
            om = self.opp_model
            if (self.use_opponent_model and om is not None
                    and om.total_predictions >= EXPECTIMAX_MIN_PREDICTIONS
                    and om.accuracy >= EXPECTIMAX_MIN_ACCURACY):
                mode, probs = "expectimax", om.predict_distribution(obs)
            state = state_from_observation(obs, self.inner.name)
            with self.stage("search"):
                best, value, n, elapsed = simultaneous_search(
                    state, 1, self.personality, candidates, enemy_probs=probs, mode=mode,
                    budget_s=SEARCH_BUDGET_S,
                )
            self.search_calls += 1
            if elapsed > SEARCH_BUDGET_S * 1.5:
                self.search_over_budget += 1
            self.last_search = {"mode": mode, "best": best, "value": value,
                                "evaluated": n, "ms": elapsed * 1000.0}
            return best
        except Exception:
            if self.strict:
                raise
            logger.warning("in-game search failed; continuing without it", exc_info=True)
            return None

    def _apply_opponent_model(
        self, scores: Dict[Action, float], obs, prof: DifficultyProfile
    ) -> Dict[Action, float]:
        """Adjust move scores based on the opponent model predictions."""
        adjusted = dict(scores)
        predicted_action: Optional[Action] = None

        non_idle_counts = {a: c for a, c in self.enemy_counts.items() if a != Action.IDLE and c > 0}
        if prof.opponent_model in ("off", "counts") or self.opp_model is None:
            total = sum(non_idle_counts.values())
            if total >= 4:
                predicted_action = max(non_idle_counts, key=lambda a: non_idle_counts[a])
        else:
            probs = self.opp_model.predict(obs)
            if isinstance(probs, dict) and probs:
                non_idle_probs = {a: p for a, p in probs.items() if a != Action.IDLE}
                predicted_action = max(non_idle_probs, key=lambda a: non_idle_probs[a]) if non_idle_probs else max(probs, key=lambda a: probs[a])
            elif isinstance(probs, Action):
                predicted_action = probs

        if predicted_action is None:
            return adjusted

        mult = 2.6 if prof.opponent_model == "live" else 1.8
        if predicted_action in DEFENCE:
            if obs.distance <= 50 and Action.THROW in adjusted:
                adjusted[Action.THROW] += mult * 1.2
            if Action.LOW_SWEEP in adjusted and obs.distance <= 88:
                adjusted[Action.LOW_SWEEP] += mult * 0.95
            if Action.CROUCH_KICK in adjusted and obs.distance <= 85:
                adjusted[Action.CROUCH_KICK] += mult * 0.90
            if Action.OVERHEAD in adjusted and obs.distance <= 88:
                adjusted[Action.OVERHEAD] += mult * 0.95
        elif predicted_action in (Action.LOW_SWEEP, Action.CROUCH_KICK, Action.CROUCH_JAB, Action.CROUCH):
            if Action.OVERHEAD in adjusted and obs.distance <= 88:
                adjusted[Action.OVERHEAD] += mult * 1.15
            if Action.JUMP_KICK in adjusted:
                adjusted[Action.JUMP_KICK] += mult
            if Action.BLOCK_LOW in adjusted and obs.distance <= 115:
                adjusted[Action.BLOCK_LOW] += mult * 0.9
        elif predicted_action in (Action.JUMP, Action.JUMP_KICK, Action.JUMP_PUNCH):
            if Action.ANTI_AIR in adjusted and obs.distance <= 110:
                adjusted[Action.ANTI_AIR] += mult * 1.3
        elif predicted_action in ATTACKS and obs.distance <= 110:
            for fast_counter in (Action.LIGHT, Action.LIGHT_KICK, Action.CROUCH_JAB, Action.LOW_SWEEP, Action.SPECIAL_DOWN, Action.SPECIAL_BACK):
                if fast_counter in adjusted and obs.i_can_hit:
                    adjusted[fast_counter] += mult * 0.85
        elif predicted_action in (Action.BACK, Action.BACKDASH):
            if Action.DASH in adjusted:
                adjusted[Action.DASH] += mult
            if Action.FORWARD in adjusted:
                adjusted[Action.FORWARD] += mult * 0.8

        return adjusted

    def _blend_learned_scores(self, scores: Dict[Action, float], obs, weight: float):
        """Blend FSM scores with the policy's action distribution.

        final[a] = max_s * ((1 - w) * fsm[a] / max_s + w * p[a] / max_p)
        so at HELL (w=0.7) the policy dominates the ranking, while the FSM's
        reactive gates (block/punish/anti-air boosts above) still shape it.
        Returns (blended_scores, policy_argmax) -- the argmax is always kept
        in the candidate pool so the viability filter cannot drop it.
        """
        try:
            probs = self._policy_agent.suggest(obs)
        except Exception:
            if self.strict:
                raise
            logger.warning("policy inference failed; using FSM scores", exc_info=True)
            return scores, None
        if probs is None or probs.max() <= 0:
            return scores, None
        max_s = max(scores.values()) or 1.0
        max_p = float(probs.max())
        blended = {}
        for a, s in scores.items():
            p = float(probs[a.value]) if a.value < len(probs) else 0.0
            blended[a] = max_s * ((1.0 - weight) * (s / max_s) + weight * (p / max_p))
        top = ALL_ACTIONS[int(probs.argmax())]
        if top not in blended:
            blended[top] = max_s * weight
        return blended, top
