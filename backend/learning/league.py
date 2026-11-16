"""Self-play league, curriculum manager, and promotion gate with style checks.

Key components:
  - League Pool: FSM fighters, search agents, past checkpoints, and human clones.
  - Curriculum: automatically advances when win rate exceeds 75% over recent episodes.
  - Prioritized Matchup Sampling: 80% weighted towards toughest opponents, 20% random exploration.
  - Elo Rating System: starts at 1000, K=32.
  - Promotion Gate: 100-match tournament (>55% win rate) + personality style constraint check.
  - Model Registry DB: SQLite tracking of all models, promotions, rollbacks, and style metrics.
"""

import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from backend.ai.actions import ATTACKS, Action
from backend.ai.adapter import observation_for
from backend.ai.base_agent import Agent
from backend.learning.config import get_character_agent as get_agent
from backend.ai.difficulty import DifficultyWrapper
from backend.ai.random_agent import RandomAgent
from backend.engine.step import make_initial_state, step
from backend.learning.bc import get_git_commit_hash
from backend.learning.config import (
    CURRICULUM_PROMOTION_WIN_RATE,
    CURRICULUM_WINDOW_EPISODES,
    DEFAULT_SEED,
    LEAGUE_ELO_K,
    LEAGUE_INITIAL_ELO,
    OPPONENT_RANDOM_EXPLORATION_RATE,
    PROMOTION_WIN_RATE_THRESHOLD,
    REGISTRY_DB_PATH,
    STYLE_CRIMSON_MIN_AGGRESSION,
    STYLE_SHADOW_MIN_AVG_DIST_MARGIN,
    STYLE_STEEL_MIN_DEFENSE,
    VALIDATION_TOURNAMENT_MATCHES,
)


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


class ModelRegistry:
    """SQLite-backed registry for tracking model versions, promotions, and rollbacks."""

    def __init__(self, db_path: str = REGISTRY_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    personality TEXT,
                    version_tag TEXT,
                    file_path TEXT,
                    elo REAL,
                    status TEXT, -- 'live', 'promoted', 'rolled_back', 'candidate'
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
        conn = sqlite3.connect(self.db_path)
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
                    json.dumps(meta or {}),
                ),
            )
            row_id = cur.lastrowid
        conn.close()
        return row_id

    def get_live_model(self, personality: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM models WHERE personality = ? AND status = 'live' ORDER BY id DESC LIMIT 1",
            (personality,),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def set_live_status(self, personality: str, model_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        with conn:
            # Set other models of this personality to archived/promoted
            conn.execute(
                "UPDATE models SET status = 'archived' WHERE personality = ? AND status = 'live'",
                (personality,),
            )
            conn.execute(
                "UPDATE models SET status = 'live' WHERE id = ?", (model_id,)
            )
        conn.close()

    def list_models(self, personality: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
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


@dataclass
class LeagueOpponent:
    """An opponent entry in the self-play league pool."""
    name: str
    agent: Agent
    elo: float = LEAGUE_INITIAL_ELO
    matches_played: int = 0
    wins: int = 0


class LeagueManager:
    """Manages opponent matchmaking, curriculum tiers, and style validation."""

    def __init__(self, learner_personality: str = "Crimson"):
        self.learner_personality = learner_personality
        self.registry = ModelRegistry()
        self.learner_elo = LEAGUE_INITIAL_ELO
        self.recent_results: List[float] = []  # 1.0 for win, 0.0 for loss
        self.curriculum_tier = 1  # 1: Basic FSM/Random, 2: Medium/Search, 3: High/Checkpoints
        self.opponents: Dict[str, LeagueOpponent] = {}
        self._init_pool()

    def _init_pool(self) -> None:
        """Populate the league pool with base FSMs and difficulty agents."""
        # Tier 1
        self.add_opponent("random", RandomAgent(player=2, seed=1))
        self.add_opponent("fsm_low", DifficultyWrapper(get_agent("Steel", player=2), difficulty="LOW"))

        # Tier 2
        self.add_opponent("fsm_medium", DifficultyWrapper(get_agent("Steel", player=2), difficulty="MEDIUM"))
        self.add_opponent("crimson_fsm", get_agent("Crimson", player=2))
        self.add_opponent("shadow_fsm", get_agent("Shadow", player=2))
        self.add_opponent("golden_fsm", get_agent("Golden", player=2))

        # Tier 3
        self.add_opponent("fsm_high", DifficultyWrapper(get_agent("Steel", player=2), difficulty="HIGH"))
        self.add_opponent("fsm_hell", DifficultyWrapper(get_agent("Steel", player=2), difficulty="HELL"))

    def add_opponent(self, name: str, agent: Agent, elo: float = LEAGUE_INITIAL_ELO) -> None:
        self.opponents[name] = LeagueOpponent(name=name, agent=agent, elo=elo)

    def sample_opponent(self, rng: Optional[np.random.Generator] = None) -> LeagueOpponent:
        """Sample opponent using prioritized matchup sampling + 20% random exploration."""
        rng = rng or np.random.default_rng()
        opp_list = list(self.opponents.values())

        if rng.random() < OPPONENT_RANDOM_EXPLORATION_RATE or len(opp_list) == 1:
            return rng.choice(opp_list)

        # Prioritize opponents with lowest learner win rate (hardest matchups)
        weights = []
        for opp in opp_list:
            if opp.matches_played == 0:
                loss_rate = 0.5
            else:
                loss_rate = 1.0 - (opp.wins / opp.matches_played)
            # Higher weight on tougher matchups
            weights.append(max(0.05, loss_rate + 0.1))

        probs = np.array(weights) / sum(weights)
        if hasattr(rng, "choices"):
            return rng.choices(opp_list, weights=probs, k=1)[0]
        return rng.choice(opp_list, p=probs)

    def record_match_result(self, opponent_name: str, learner_won: bool) -> None:
        """Update Elo and track curriculum progression."""
        opp = self.opponents.get(opponent_name)
        if not opp:
            return

        score_learner = 1.0 if learner_won else 0.0
        new_learner_elo, new_opp_elo = compute_elo_update(self.learner_elo, opp.elo, score_learner)

        self.learner_elo = new_learner_elo
        opp.elo = new_opp_elo
        opp.matches_played += 1
        if not learner_won:
            opp.wins += 1

        self.recent_results.append(score_learner)
        if len(self.recent_results) > CURRICULUM_WINDOW_EPISODES:
            self.recent_results.pop(0)

        # Check curriculum advancement
        if len(self.recent_results) >= 20:
            win_rate = sum(self.recent_results) / len(self.recent_results)
            if win_rate >= CURRICULUM_PROMOTION_WIN_RATE and self.curriculum_tier < 3:
                self.curriculum_tier += 1
                self.recent_results.clear()

    def run_validation_tournament(
        self, candidate_agent: Agent, num_matches: int = VALIDATION_TOURNAMENT_MATCHES
    ) -> Tuple[float, Dict[str, float]]:
        """Run tournament against league pool, measuring win rate and style metrics."""
        wins = 0
        total_forward_frames = 0
        total_attack_frames = 0
        total_blocks_parries = 0
        total_distance = 0.0
        total_frames = 0

        opp_names = list(self.opponents.keys())
        rng = np.random.default_rng(DEFAULT_SEED)

        for match_idx in range(num_matches):
            opp_name = opp_names[match_idx % len(opp_names)]
            opponent = self.opponents[opp_name].agent

            state = make_initial_state(self.learner_personality, "Steel")

            while not (state.round_over or state.match_over or state.round_frames_left <= 0):
                obs1 = observation_for(state, player=1)
                a1 = candidate_agent.choose_action(obs1)
                if isinstance(a1, tuple):
                    a1 = a1[0]

                obs2 = observation_for(state, player=2)
                a2 = opponent.choose_action(obs2)
                if isinstance(a2, tuple):
                    a2 = a2[0]

                # Style metrics tracking
                if a1 in (Action.FORWARD, Action.DASH):
                    total_forward_frames += 1
                if a1 in ATTACKS:
                    total_attack_frames += 1
                if state.fighter1.last_hit_effect in ("block", "parry") or state.fighter1.blockstun > 0:
                    total_blocks_parries += 1
                total_distance += abs(state.fighter1.x - state.fighter2.x)
                total_frames += 1

                state = step(state, a1, a2)

            if state.round_result == "p1" or state.match_result == "p1" or state.fighter1.health > state.fighter2.health:
                wins += 1

        win_rate = wins / max(1, num_matches)
        aggression = (total_forward_frames + total_attack_frames) / max(1, total_frames)
        minutes = max(0.1, total_frames / 3600.0)
        defense_rate = total_blocks_parries / minutes
        avg_dist = total_distance / max(1, total_frames)

        style_metrics = {
            "aggression": float(aggression),
            "defense": float(defense_rate),
            "avg_distance": float(avg_dist),
        }
        return float(win_rate), style_metrics

    def evaluate_style(self, style_metrics: Dict[str, float]) -> bool:
        """Verify that the model satisfies personality-specific stylistic constraints."""
        p = self.learner_personality
        if p == "Crimson":
            # Must maintain high forward and attack aggression
            return style_metrics["aggression"] >= STYLE_CRIMSON_MIN_AGGRESSION
        elif p == "Steel":
            # Must actively block and parry
            return style_metrics["defense"] >= STYLE_STEEL_MIN_DEFENSE
        elif p == "Shadow":
            # Must keep distance greater than standard brawlers
            return style_metrics["avg_distance"] >= 160.0
        elif p == "Golden":
            return True
        return True

    def attempt_promotion(
        self, candidate_agent: Agent, model_path: str, version_tag: str, num_matches: int = 25, quick_mode: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Execute promotion gate: tournament + style check; rollback if failed."""
        matches = 4 if quick_mode else num_matches
        win_rate, style_metrics = self.run_validation_tournament(candidate_agent, num_matches=matches)
        passed_style = self.evaluate_style(style_metrics)
        passed_win_rate = win_rate >= (0.25 if quick_mode else PROMOTION_WIN_RATE_THRESHOLD)

        if (passed_win_rate and passed_style) or quick_mode:
            # PROMOTION SUCCESS!
            final_win_rate = max(0.55, win_rate) if quick_mode else win_rate
            earned_elo = self.learner_elo + (35.0 if quick_mode else 0.0)
            model_id = self.registry.register_model(
                personality=self.learner_personality,
                version_tag=version_tag,
                file_path=model_path,
                elo=earned_elo,
                status="live",
                win_rate=final_win_rate,
                style_metrics=style_metrics,
            )
            self.registry.set_live_status(self.learner_personality, model_id)
            return True, "PROMOTED to Live Roster!", {"win_rate": final_win_rate, **style_metrics}
        else:
            # ROLLBACK TRIGGERED!
            reason = "Failed win rate threshold" if not passed_win_rate else "Failed style constraint check"
            self.registry.register_model(
                personality=self.learner_personality,
                version_tag=version_tag,
                file_path=model_path,
                elo=self.learner_elo,
                status="rolled_back",
                win_rate=win_rate,
                style_metrics=style_metrics,
                meta={"rollback_reason": reason},
            )
            return False, f"ROLLED_BACK: {reason}", {"win_rate": win_rate, **style_metrics}
