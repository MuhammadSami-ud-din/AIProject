"""Self-play league, curriculum manager, and promotion gate with style checks.

Key components:
  - League Pool: random, FSM fighters at several difficulties, and past
    checkpoints of the learner (self-play), grouped into curriculum tiers.
  - Curriculum: advances one tier when the learner wins >= 75% of its recent
    league matches; only opponents of tier <= current tier are sampled.
  - Prioritized Matchup Sampling: weighted towards the opponents the learner
    loses to most, plus 20% uniform exploration.
  - Elo Rating System: starts at 1000, K=32, updated after every training match.
  - Promotion Gate: validation tournament (win rate >= 55%) AND a personality
    style check. Quick mode only plays fewer matches -- the gate is identical
    and the reported numbers are the measured ones.
  - Model Registry DB: SQLite (WAL) tracking of models, promotions, rollbacks.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from backend.ai.base_agent import Agent
from backend.ai.difficulty import DifficultyWrapper
from backend.ai.random_agent import RandomAgent
from backend.engine.step import make_initial_state, step
from backend.learning.bc import get_git_commit_hash
from backend.learning.config import (
    CRIMSON_PRESSURE_RANGE,
    CURRICULUM_PROMOTION_WIN_RATE,
    CURRICULUM_WINDOW_EPISODES,
    DEFAULT_SEED,
    LEAGUE_ELO_K,
    LEAGUE_INITIAL_ELO,
    OPPONENT_RANDOM_EXPLORATION_RATE,
    PROMOTION_WIN_RATE_THRESHOLD,
    QUICK_MODE_VALIDATION_MATCHES,
    REGISTRY_DB_PATH,
    STYLE_CRIMSON_MIN_AGGRESSION,
    STYLE_GOLDEN_ENTROPY_MIN,
    STYLE_MIN_DAMAGE_PER_MINUTE,
    STYLE_SHADOW_MIN_AVG_DISTANCE,
    STYLE_STEEL_MIN_DEFENSE,
    VALIDATION_TOURNAMENT_MATCHES,
    get_character_agent as get_agent,
)
from backend.learning.features import full_observation_for
from backend.learning.rewards import extract_frame_events

logger = logging.getLogger(__name__)



def compute_elo_update(
    rating_a: float, rating_b: float, score_a: float, k: float = LEAGUE_ELO_K
) -> Tuple[float, float]:
    """Calculate new Elo ratings following a match (score_a: 1.0 win, 0.5 draw, 0.0 loss)."""
    expected_a = 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a

    new_rating_a = rating_a + k * (score_a - expected_a)
    new_rating_b = rating_b + k * (score_b - expected_b)
    return float(new_rating_a), float(new_rating_b)


# ======================================================================
# Model registry
# ======================================================================
class ModelRegistry:
    """SQLite-backed registry for tracking model versions, promotions, and rollbacks."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = os.path.abspath(db_path or REGISTRY_DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    personality TEXT,
                    version_tag TEXT,
                    file_path TEXT,
                    elo REAL,
                    status TEXT, -- 'live', 'archived', 'rolled_back', 'candidate'
                    win_rate REAL,
                    aggression REAL,
                    defense REAL,
                    avg_distance REAL,
                    commit_hash TEXT,
                    timestamp REAL,
                    metadata_json TEXT
                )
                """
            )
        conn.close()

    def register_model(
        self,
        personality: str,
        version_tag: str,
        file_path: str,
        elo: float,
        status: str,
        win_rate: float,
        style_metrics: Dict[str, float],
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        conn = self._connect()
        with conn:
            cur = conn.execute(
                """
                INSERT INTO models (
                    personality, version_tag, file_path, elo, status, win_rate,
                    aggression, defense, avg_distance, commit_hash, timestamp, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    personality,
                    version_tag,
                    file_path,
                    elo,
                    status,
                    win_rate,
                    style_metrics.get("aggression", 0.0),
                    style_metrics.get("defense", 0.0),
                    style_metrics.get("avg_distance", 0.0),
                    get_git_commit_hash(),
                    time.time(),
                    json.dumps({**(meta or {}), "style_metrics": style_metrics}),
                ),
            )
            row_id = cur.lastrowid
        conn.close()
        return int(row_id)

    def get_live_model(self, personality: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM models WHERE personality = ? AND status = 'live' ORDER BY id DESC LIMIT 1",
            (personality,),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def set_live_status(self, personality: str, model_id: int) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE models SET status = 'archived' WHERE personality = ? AND status = 'live'",
                (personality,),
            )
            conn.execute("UPDATE models SET status = 'live' WHERE id = ?", (model_id,))
        conn.close()

    def list_models(self, personality: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        if personality:
            cur = conn.execute(
                "SELECT * FROM models WHERE personality = ? ORDER BY id DESC", (personality,)
            )
        else:
            cur = conn.execute("SELECT * FROM models ORDER BY id DESC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def signature(self, personality: str) -> Tuple[int, int]:
        """(newest row id, live row id) -- changes whenever a model is registered/promoted."""
        conn = self._connect()
        try:
            max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM models").fetchone()[0]
            live = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM models WHERE personality = ? AND status = 'live'",
                (personality,),
            ).fetchone()[0]
        finally:
            conn.close()
        return int(max_id), int(live)


# ======================================================================
# Match playing + style metrics (shared by validation and evaluation)
# ======================================================================
def play_round(
    agent1: Agent,
    agent2: Agent,
    char1: str,
    char2: str,
    max_frames: int = 3600 * 2,
) -> Tuple[str, Dict[str, float]]:
    """Play one round frame-by-frame; return (round_result, raw style counters).

    Both agents are called every frame (as in the game). A PolicyAgent applies
    its own macro-step execution internally, so its decision granularity is
    the same here as in training.
    """
    for a in (agent1, agent2):
        if hasattr(a, "reset"):
            a.reset()
    state = make_initial_state(char1, char2)
    counters = _empty_counters()
    while not (state.round_over or state.match_over or state.round_frames_left <= 0):
        if counters["frames"] >= max_frames:
            break
        obs1 = full_observation_for(state, 1)
        obs2 = full_observation_for(state, 2)
        a1 = agent1.choose_action(obs1)
        a1 = a1[0] if isinstance(a1, tuple) else a1
        a2 = agent2.choose_action(obs2)
        a2 = a2[0] if isinstance(a2, tuple) else a2
        before = state
        state = step(state, a1, a2)
        for a, me, mine, theirs in ((agent1, 1, a1, a2), (agent2, 2, a2, a1)):
            if hasattr(a, "observe"):
                a.observe(full_observation_for(state, me), mine, theirs)

        ev = extract_frame_events(before, state, 1)
        f1, f2 = state.fighter1, state.fighter2
        dist = abs(f1.x - f2.x)
        enemy_pressured = f2.hitstun > 0 or f2.blockstun > 0 or f2.is_knocked_down
        counters["frames"] += 1
        counters["pressure_frames"] += float(enemy_pressured and dist <= CRIMSON_PRESSURE_RANGE)
        counters["defense_events"] += ev["block"] + ev["parry"]
        counters["distance_sum"] += dist
        counters["damage_dealt"] += ev["dmg_dealt"]
        counters["damage_taken"] += max(0.0, before.fighter1.health - f1.health)
        if a1 != before.fighter1.last_action and a1.value < 27 and a1.name != "IDLE":
            counters[f"act_{a1.value}"] = counters.get(f"act_{a1.value}", 0.0) + 1.0
    return state.round_result, counters


def _empty_counters() -> Dict[str, float]:
    return {"frames": 0.0, "pressure_frames": 0.0, "defense_events": 0.0,
            "distance_sum": 0.0, "damage_dealt": 0.0, "damage_taken": 0.0}


def style_from_counters(c: Dict[str, float]) -> Dict[str, float]:
    frames = max(1.0, c["frames"])
    minutes = max(1.0 / 60.0, frames / 3600.0)
    acts = np.array([v for k, v in c.items() if k.startswith("act_")], dtype=np.float64)
    entropy = 0.0
    if acts.sum() > 0:
        p = acts / acts.sum()
        entropy = float(-(p * np.log2(p)).sum())
    return {
        "action_entropy": entropy,
        "aggression": c["pressure_frames"] / frames,
        "defense": c["defense_events"] / minutes,
        "avg_distance": c["distance_sum"] / frames,
        "damage_per_minute": 100.0 * c["damage_dealt"] / minutes,
    }


# ======================================================================
# League
# ======================================================================
@dataclass
class LeagueOpponent:
    """An opponent entry in the self-play league pool.

    ``wins`` counts the LEARNER's wins against this opponent.
    """
    name: str
    agent: Agent
    elo: float = LEAGUE_INITIAL_ELO
    matches_played: int = 0
    wins: int = 0
    character: str = "Steel"
    tier: int = 1
    factory: Optional[Callable[[], Agent]] = field(default=None, repr=False)

    def make_agent(self) -> Agent:
        """A fresh agent instance (so parallel envs never share mutable state)."""
        return self.factory() if self.factory is not None else self.agent


def _wrapped(char: str, difficulty: str, seed: int) -> Callable[[], Agent]:
    def make() -> Agent:
        # Learned-policy blending and search are disabled inside the training
        # league to keep rollouts fast and to avoid training against itself
        # implicitly; past checkpoints are added explicitly instead.
        return DifficultyWrapper(get_agent(char, player=2, seed=seed), difficulty=difficulty,
                                 use_learned_policy=False, use_search=False)
    return make


class LeagueManager:
    """Manages opponent matchmaking, curriculum tiers, and style validation."""

    def __init__(
        self,
        learner_personality: str = "Crimson",
        registry_path: Optional[str] = None,
        seed: int = DEFAULT_SEED,
        registry: Optional[ModelRegistry] = None,
    ):
        self.learner_personality = learner_personality.capitalize()
        self._registry = registry
        self._registry_path = registry_path
        self.seed = seed
        self.learner_elo = LEAGUE_INITIAL_ELO
        self.recent_results: List[float] = []
        self.curriculum_tier = 1  # 1: random/LOW, 2: MEDIUM/FSMs, 3: HIGH/HELL/checkpoints
        self.opponents: Dict[str, LeagueOpponent] = {}
        self._init_pool()

    @property
    def registry(self) -> ModelRegistry:
        """Opened lazily so pure training runs never touch the registry DB."""
        if self._registry is None:
            self._registry = ModelRegistry(self._registry_path)
        return self._registry

    @registry.setter
    def registry(self, value: ModelRegistry) -> None:
        self._registry = value

    def _init_pool(self) -> None:
        s = self.seed
        self.add_opponent("random", RandomAgent(player=2, seed=s + 1), character="Steel", tier=1,
                          factory=lambda: RandomAgent(player=2, seed=s + 1))
        self.add_opponent("fsm_low", None, character="Steel", tier=1, factory=_wrapped("Steel", "LOW", s + 2))
        self.add_opponent("fsm_medium", None, character="Steel", tier=2, factory=_wrapped("Steel", "MEDIUM", s + 3))
        for i, char in enumerate(("Crimson", "Shadow", "Golden")):
            self.add_opponent(f"{char.lower()}_fsm", None, character=char, tier=2,
                              factory=(lambda c=char, k=i: get_agent(c, player=2, seed=s + 10 + k)))
        self.add_opponent("fsm_high", None, character="Steel", tier=3, factory=_wrapped("Steel", "HIGH", s + 4))
        self.add_opponent("fsm_hell", None, character="Steel", tier=3, factory=_wrapped("Steel", "HELL", s + 5))

    def add_opponent(self, name: str, agent: Optional[Agent], elo: float = LEAGUE_INITIAL_ELO,
                     character: str = "Steel", tier: int = 1,
                     factory: Optional[Callable[[], Agent]] = None) -> None:
        if agent is None and factory is not None:
            agent = factory()
        self.opponents[name] = LeagueOpponent(name=name, agent=agent, elo=elo, character=character,
                                              tier=tier, factory=factory)

    def add_checkpoint_opponent(self, checkpoint_path: str, name: Optional[str] = None) -> None:
        """Add a past learner checkpoint as a tier-3 self-play opponent."""
        from backend.learning.policy_agent import PolicyAgent

        char = self.learner_personality
        label = name or f"self_{os.path.splitext(os.path.basename(checkpoint_path))[0]}"

        def make() -> Agent:
            return PolicyAgent(char, player=2, model_path=checkpoint_path, use_registry=False)

        probe = make()
        if probe.model is None:
            logger.info("not adding %s to league: incompatible or unreadable", checkpoint_path)
            return
        self.add_opponent(label, probe, character=char, tier=3, factory=make)

    def available_opponents(self) -> List[LeagueOpponent]:
        opps = [o for o in self.opponents.values() if o.tier <= self.curriculum_tier]
        return opps or list(self.opponents.values())

    def sample_opponent(self, rng=None) -> LeagueOpponent:
        """Prioritized sampling over the current curriculum tier + 20% exploration."""
        rng = rng if rng is not None else np.random.default_rng()
        opp_list = self.available_opponents()

        def uniform() -> float:
            return float(rng.random())

        if len(opp_list) == 1 or uniform() < OPPONENT_RANDOM_EXPLORATION_RATE:
            idx = int(uniform() * len(opp_list)) % len(opp_list)
            return opp_list[idx]

        weights = []
        for opp in opp_list:
            loss_rate = 0.5 if opp.matches_played == 0 else 1.0 - (opp.wins / opp.matches_played)
            weights.append(max(0.05, loss_rate + 0.1))
        probs = np.array(weights, dtype=np.float64)
        probs /= probs.sum()
        r = uniform()
        idx = int(np.searchsorted(np.cumsum(probs), r, side="right"))
        return opp_list[min(idx, len(opp_list) - 1)]

    def record_match_result(self, opponent_name: str, learner_won: bool) -> None:
        """Update Elo and track curriculum progression."""
        opp = self.opponents.get(opponent_name)
        if not opp:
            return

        score_learner = 1.0 if learner_won else 0.0
        self.learner_elo, opp.elo = compute_elo_update(self.learner_elo, opp.elo, score_learner)
        opp.matches_played += 1
        if learner_won:
            opp.wins += 1

        self.recent_results.append(score_learner)
        if len(self.recent_results) > CURRICULUM_WINDOW_EPISODES:
            self.recent_results.pop(0)

        if len(self.recent_results) >= 20:
            win_rate = sum(self.recent_results) / len(self.recent_results)
            if win_rate >= CURRICULUM_PROMOTION_WIN_RATE and self.curriculum_tier < 3:
                self.curriculum_tier += 1
                self.recent_results.clear()

    # ------------------------------------------------------------------
    def run_validation_tournament(
        self, candidate_agent: Agent, num_matches: int = VALIDATION_TOURNAMENT_MATCHES
    ) -> Tuple[float, Dict[str, float]]:
        """Round-robin over the WHOLE pool (all tiers); returns (win_rate, style metrics)."""
        totals = _empty_counters()
        wins = 0
        elo = LEAGUE_INITIAL_ELO
        opp_list = list(self.opponents.values())
        for match_idx in range(num_matches):
            opp = opp_list[match_idx % len(opp_list)]
            result, counters = play_round(candidate_agent, opp.make_agent(),
                                          self.learner_personality, opp.character)
            won = result == "p1"
            wins += int(won)
            score = 1.0 if won else (0.5 if result == "draw" else 0.0)
            elo, _ = compute_elo_update(elo, opp.elo, score)
            for k, v in counters.items():
                totals[k] = totals.get(k, 0.0) + v

        win_rate = wins / max(1, num_matches)
        style = style_from_counters(totals)
        style["tournament_elo"] = float(elo)
        style["matches"] = float(num_matches)
        style["wins"] = float(wins)
        return float(win_rate), style

    def evaluate_style(self, style_metrics: Dict[str, float]) -> bool:
        """Verify that the model satisfies personality-specific stylistic constraints."""
        p = self.learner_personality
        if p == "Crimson":
            return style_metrics["aggression"] >= STYLE_CRIMSON_MIN_AGGRESSION
        if p == "Steel":
            return style_metrics["defense"] >= STYLE_STEEL_MIN_DEFENSE
        if p == "Shadow":
            # Fights at range AND actually lands hits (a flailing random agent
            # keeps a large distance too, so distance alone is not a style).
            return (style_metrics["avg_distance"] >= STYLE_SHADOW_MIN_AVG_DISTANCE
                    and style_metrics.get("damage_per_minute", 0.0) >= STYLE_MIN_DAMAGE_PER_MINUTE)
        if p == "Golden":
            return (style_metrics.get("action_entropy", 0.0) >= STYLE_GOLDEN_ENTROPY_MIN
                    and style_metrics.get("damage_per_minute", 0.0) >= STYLE_MIN_DAMAGE_PER_MINUTE)
        return True

    def attempt_promotion(
        self,
        candidate_agent: Agent,
        model_path: str,
        version_tag: str,
        num_matches: int = 25,
        quick_mode: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Promotion gate: tournament + style check. Rolls back on failure.

        Quick mode plays QUICK_MODE_VALIDATION_MATCHES matches instead of
        ``num_matches``; the thresholds and the reported numbers are unchanged.
        Returns (promoted, status message, metrics incl. the true win_rate).
        """
        matches = min(num_matches, QUICK_MODE_VALIDATION_MATCHES) if quick_mode else num_matches
        win_rate, style_metrics = self.run_validation_tournament(candidate_agent, num_matches=matches)
        passed_style = self.evaluate_style(style_metrics)
        passed_win_rate = win_rate >= PROMOTION_WIN_RATE_THRESHOLD
        elo = style_metrics.get("tournament_elo", self.learner_elo)
        metrics = {"win_rate": win_rate, "passed_win_rate": passed_win_rate,
                   "passed_style": passed_style, "quick_mode": quick_mode, **style_metrics}

        if passed_win_rate and passed_style:
            model_id = self.registry.register_model(
                personality=self.learner_personality,
                version_tag=version_tag,
                file_path=os.path.abspath(model_path),
                elo=elo,
                status="live",
                win_rate=win_rate,
                style_metrics=style_metrics,
                meta={"quick_mode": quick_mode, "matches": matches},
            )
            self.registry.set_live_status(self.learner_personality, model_id)
            return True, "PROMOTED to Live Roster!", metrics

        reasons = []
        if not passed_win_rate:
            reasons.append(f"Failed win rate threshold ({win_rate:.0%} < {PROMOTION_WIN_RATE_THRESHOLD:.0%})")
        if not passed_style:
            reasons.append("Failed style constraint check")
        reason = "; ".join(reasons)
        self.registry.register_model(
            personality=self.learner_personality,
            version_tag=version_tag,
            file_path=os.path.abspath(model_path),
            elo=elo,
            status="rolled_back",
            win_rate=win_rate,
            style_metrics=style_metrics,
            meta={"rollback_reason": reason, "quick_mode": quick_mode, "matches": matches},
        )
        return False, f"ROLLED_BACK: {reason}", metrics


# ======================================================================
# CLI
# ======================================================================
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the promotion gate for a checkpoint.")
    parser.add_argument("--character", default="Crimson")
    parser.add_argument("--checkpoint", default=None,
                        help="checkpoint to validate (default: newest compatible in models/<character>)")
    parser.add_argument("--models-dir", default=None)
    parser.add_argument("--matches", type=int, default=25)
    parser.add_argument("--quick", action="store_true", help="fewer matches, same gate")
    parser.add_argument("--registry", default=None, help="registry DB path (default data/model_registry.db)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    import torch
    torch.set_num_threads(1)   # tiny networks: threads only add contention

    from backend.learning.checkpoints import find_latest_checkpoint
    from backend.learning.policy_agent import PolicyAgent

    ckpt = args.checkpoint or find_latest_checkpoint(args.character, args.models_dir, include_bc=False)
    if not ckpt:
        print(f"No compatible checkpoint for {args.character}")
        return 1
    random.seed(args.seed)
    league = LeagueManager(args.character, registry_path=args.registry, seed=args.seed)
    agent = PolicyAgent(args.character, player=1, model_path=ckpt, seed=args.seed, use_registry=False)
    if agent.model is None:
        print(f"Checkpoint {ckpt} is incompatible")
        return 1
    tag = os.path.splitext(os.path.basename(ckpt))[0]
    promoted, msg, metrics = league.attempt_promotion(agent, ckpt, tag, num_matches=args.matches,
                                                      quick_mode=args.quick)
    print(msg)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
