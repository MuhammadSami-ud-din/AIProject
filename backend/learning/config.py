"""Centralized configuration for the Arena-AI learning pipeline.

Every setting (learning rates, reward weights, league parameters, network shapes,
thresholds) lives in this file. Balancing and tuning means editing this file only.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# General & Reproducibility Settings
# ---------------------------------------------------------------------------
DEFAULT_SEED: int = 42
DEVICE: str = "cpu"  # PyTorch on CPU for low latency (<1 ms)

# All paths are absolute, anchored at the project root, so the game, the CLIs
# and the background trainer process agree regardless of the working directory.
PROJECT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS_DIR: str = os.path.join(PROJECT_ROOT, "models")
REGISTRY_DB_PATH: str = os.path.join(PROJECT_ROOT, "data", "model_registry.db")
# Fight logs written by backend.data.simulate / match logging (backend/data/database.py)
FIGHT_LOGS_DB_PATH: str = os.path.join(PROJECT_ROOT, "backend", "data", "fights.db")
RESULTS_DIR: str = os.path.join(PROJECT_ROOT, "docs", "results")


# ---------------------------------------------------------------------------
# Network Architecture
# ---------------------------------------------------------------------------
from backend.learning.features import POLICY_OBS_DIM

OBS_DIM: int = POLICY_OBS_DIM  # Matches backend.learning.features.policy_vector (96)
ACTION_DIM: int = 27        # Matches len(ALL_ACTIONS)
HIDDEN_DIM: int = 128       # Small networks only (2 hidden layers of 128)
NUM_HIDDEN_LAYERS: int = 2


# ---------------------------------------------------------------------------
# Gymnasium Environment & Frame-Skip Settings (Phase 1)
# ---------------------------------------------------------------------------
MAX_ROUND_FRAMES: int = 3600    # 60s @ 60 FPS
FRAME_SKIP_FALLBACK: int = 6    # Maximum frames to advance if not actionable
ACTION_EXECUTION_FRAMES: int = 6  # Macro-action execution commitment


# ---------------------------------------------------------------------------
# Shared Base Rewards & Penalties (Phase 2)
# ---------------------------------------------------------------------------
DAMAGE_DEALT_WEIGHT: float = 100.0   # Scaled to HP (0.02 dmg = 2.0 reward)
DAMAGE_TAKEN_WEIGHT: float = 100.0   # Negative penalty for taking damage
ROUND_WIN_REWARD: float = 10.0
ROUND_LOSS_PENALTY: float = -10.0
TIME_PENALTY_PER_STEP: float = 0.005 # Discourage passive stalling
WHIFF_PENALTY: float = 0.3           # Penalty when attacking and missing


# ---------------------------------------------------------------------------
# Personality Reward Shaping Bonuses (Phase 2)
# ---------------------------------------------------------------------------
# Crimson (Rushdown Berserker). Aggression is rewarded only when it achieves
# something: damage dealt, or forcing the enemy to block while in range.
# (A flat bonus per FORWARD step was farmable by walking into the wall.)
CRIMSON_DAMAGE_BONUS: float = 0.50      # extra reward per 1% HP dealt
CRIMSON_PRESSURE_BONUS: float = 0.40    # enemy forced into blockstun while in range
CRIMSON_PRESSURE_RANGE: float = 140.0   # pixels: "in range" for pressure
CRIMSON_COMBO_HIT_BONUS: float = 0.50
CRIMSON_BACKING_PENALTY: float = -0.25
# Backwards-compatible name (no longer used as a per-step bonus)
CRIMSON_FORWARD_BONUS: float = 0.0

# Steel (Counter-Fighter & Tank)
STEEL_BLOCK_BONUS: float = 0.80
STEEL_PARRY_BONUS: float = 2.50
STEEL_PUNISH_BONUS: float = 1.50     # Damage dealt within 30f of blocking
STEEL_WHIFF_PENALTY: float = -0.60   # Heavy penalty on wild whiffs

# Shadow (Agile Hit-and-Run)
SHADOW_PREFERRED_DIST_MIN: float = 180.0
SHADOW_PREFERRED_DIST_MAX: float = 320.0
SHADOW_PREFERRED_DIST_BONUS: float = 0.25
SHADOW_WHIFF_PUNISH_BONUS: float = 1.60
SHADOW_EVADE_BONUS: float = 0.80     # Successful backdash / air dash
SHADOW_CORNER_PENALTY: float = -0.50 # Penalty for being cornered

# Golden (Adaptive Strategist)
GOLDEN_ROUND_WIN_BONUS: float = 3.00
GOLDEN_READ_HIT_BONUS: float = 3.00  # Golden Read counter landing
GOLDEN_BALANCED_BONUS: float = 0.20  # Small bonuses on variety/spacing


# ---------------------------------------------------------------------------
# Behaviour Cloning Settings (Phase 3)
# ---------------------------------------------------------------------------
BC_LEARNING_RATE: float = 1e-3
BC_BATCH_SIZE: int = 64
BC_EPOCHS: int = 15
BC_TEST_SPLIT: float = 0.20
BC_JITTER_STD: float = 0.02


# ---------------------------------------------------------------------------
# PPO Hyperparameters (Phase 4)
# ---------------------------------------------------------------------------
PPO_LEARNING_RATE: float = 3e-4
PPO_GAMMA: float = 0.99
PPO_GAE_LAMBDA: float = 0.95
PPO_CLIP_EPS: float = 0.20
PPO_VALUE_COEF: float = 0.50
PPO_ENTROPY_COEF: float = 0.01
PPO_MAX_GRAD_NORM: float = 0.50
PPO_EPOCHS_PER_UPDATE: float = 4
PPO_BATCH_SIZE: int = 64
PPO_STEPS_PER_ENV: int = 128
PPO_N_ENVS: int = 4
PPO_CHECKPOINT_INTERVAL: int = 10
PPO_QUICK_TRAIN_SECONDS: int = 300   # 5-minute laptop test mode


# ---------------------------------------------------------------------------
# Self-Play League & Curriculum (Phase 5)
# ---------------------------------------------------------------------------
LEAGUE_INITIAL_ELO: float = 1000.0
LEAGUE_ELO_K: float = 32.0
CURRICULUM_PROMOTION_WIN_RATE: float = 0.75
CURRICULUM_WINDOW_EPISODES: int = 50
OPPONENT_RANDOM_EXPLORATION_RATE: float = 0.20

# Promotion Validation Tournament
VALIDATION_TOURNAMENT_MATCHES: int = 100
PROMOTION_WIN_RATE_THRESHOLD: float = 0.55
QUICK_MODE_VALIDATION_MATCHES: int = 8   # quick mode plays fewer matches, same gate

# Style Check Constraints (Aggression, Defense, Distance)
# Calibrated by playing the validation tournament (8 rounds vs the league pool)
# with the FSM experts, a RandomAgent and an always-FORWARD agent:
#   aggression (share of frames the enemy is in hit/blockstun or knocked down
#   while Crimson is within CRIMSON_PRESSURE_RANGE -- same notion as the reward):
#       Crimson FSM 0.35, Random 0.09, always-FORWARD 0.00
#   Steel successful blocks+parries per minute: Random 0.3-0.9, FSM Steel 0-1.3
#   Shadow avg distance: FSM 118 px, Random 197 px (so damage is also required)
STYLE_CRIMSON_MIN_AGGRESSION: float = 0.20
STYLE_STEEL_MIN_DEFENSE: float = 1.0          # successful blocks/parries per minute
STYLE_SHADOW_MIN_AVG_DISTANCE: float = 110.0  # px
STYLE_SHADOW_MIN_AVG_DIST_MARGIN: float = 20.0  # legacy name, unused
STYLE_MIN_DAMAGE_PER_MINUTE: float = 250.0    # % HP per minute (Random ~125, FSMs 390-530)
STYLE_GOLDEN_ENTROPY_MIN: float = 1.5         # bits, entropy of chosen (non-idle) actions


# ---------------------------------------------------------------------------
# Dynamic Difficulty Adjustment (DDA) & Fallback (Phase 6)
# ---------------------------------------------------------------------------
DDA_TARGET_MIN_WIN_RATE: float = 0.45
DDA_TARGET_MAX_WIN_RATE: float = 0.55
DDA_EVAL_WINDOW_ROUNDS: int = 5
DDA_MISTAKE_ADJUSTMENT_STEP: float = 0.05
DDA_MIN_MISTAKE_CHANCE: float = 0.01
DDA_MAX_MISTAKE_CHANCE: float = 0.40


@dataclass
class LearningConfig:
    """Dataclass view of the configuration settings."""
    obs_dim: int = OBS_DIM
    action_dim: int = ACTION_DIM
    hidden_dim: int = HIDDEN_DIM
    num_hidden_layers: int = NUM_HIDDEN_LAYERS
    learning_rate: float = PPO_LEARNING_RATE
    gamma: float = PPO_GAMMA
    gae_lambda: float = PPO_GAE_LAMBDA
    clip_eps: float = PPO_CLIP_EPS
    value_coef: float = PPO_VALUE_COEF
    entropy_coef: float = PPO_ENTROPY_COEF
    max_grad_norm: float = PPO_MAX_GRAD_NORM
    n_envs: int = PPO_N_ENVS
    seed: int = DEFAULT_SEED


def get_character_agent(name: str, player: int = 1, seed: Optional[int] = None):
    """Instantiate the rule-based FSM agent for a given character name."""
    from backend.ai.crimson import CrimsonAgent
    from backend.ai.steel import SteelAgent
    from backend.ai.shadow import ShadowAgent
    from backend.ai.golden import GoldenAgent
    classes = {
        "Crimson": CrimsonAgent,
        "Steel": SteelAgent,
        "Shadow": ShadowAgent,
        "Golden": GoldenAgent,
    }
    cls = classes.get(name.capitalize(), CrimsonAgent)
    return cls(player=player, seed=seed)
