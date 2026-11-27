"""Policy observation vector shared by the env, BC, PPO and PolicyAgent.

``Observation.features()`` (FEATURE_NAMES) stays the logging/sklearn format.
The neural policy uses a richer vector built here:

  * the 28 numeric base features (everything except the two action ids),
  * one-hot of my last action and of the enemy's last action (ids 0..26 plus
    one "other" bucket for Rumble/Shield actions) -- raw ids are categorical,
    feeding 0..26 as a magnitude made no sense,
  * one-hot attack phase (none/startup/active/recovery) for both fighters,
  * the exact action-mask inputs (thrown, guard-break stun, burst used,
    jump frame) so the policy sees what the mask sees.

Every component imports POLICY_OBS_DIM from here, so env, network, policy
agent and checkpoints always agree. Checkpoints store ``obs_dim`` and the
loader skips any checkpoint whose input size differs.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from backend.ai.actions import ATTACKS, Action
from backend.ai.observation import ATTACK_PHASES, FEATURE_NAMES, FRAMES_PER_SECOND, enrich_from_state

N_ACTION_BUCKETS = 28          # Action ids 0..26 + "other"
_NUMERIC_BASE = tuple(n for n in FEATURE_NAMES if n not in ("my_last_action", "enemy_last_action"))
_EXTRA = ("my_is_thrown", "my_guard_break_stun", "my_burst_used", "my_jump_frame")

POLICY_FEATURE_NAMES = (
    _NUMERIC_BASE
    + tuple(f"my_last_action=={i}" for i in range(N_ACTION_BUCKETS))
    + tuple(f"enemy_last_action=={i}" for i in range(N_ACTION_BUCKETS))
    + tuple(f"my_attack_phase=={p}" for p in ATTACK_PHASES)
    + tuple(f"enemy_attack_phase=={p}" for p in ATTACK_PHASES)
    + _EXTRA
)
POLICY_OBS_DIM = len(POLICY_FEATURE_NAMES)   # 96


def _action_bucket(action_id: int) -> int:
    action_id = int(action_id)
    return action_id if 0 <= action_id < N_ACTION_BUCKETS - 1 else N_ACTION_BUCKETS - 1


def _approx_phase(last_action_id: int, recovery: float) -> str:
    """Best guess at an attack phase when the observation has no engine detail."""
    if recovery > 0:
        return "recovery"
    try:
        if Action(int(last_action_id)) in ATTACKS:
            return "active"
    except ValueError:
        pass
    return "none"


def vector_from_parts(base: dict, my_phase: str, enemy_phase: str, extra: dict) -> np.ndarray:
    """Assemble the policy vector from a FEATURE_NAMES dict plus engine detail."""
    vec = np.zeros(POLICY_OBS_DIM, dtype=np.float32)
    i = 0
    for name in _NUMERIC_BASE:
        vec[i] = float(base.get(name, 0.0) or 0.0)
        i += 1
    vec[i + _action_bucket(base.get("my_last_action", 0) or 0)] = 1.0
    i += N_ACTION_BUCKETS
    vec[i + _action_bucket(base.get("enemy_last_action", 0) or 0)] = 1.0
    i += N_ACTION_BUCKETS
    vec[i + ATTACK_PHASES.index(my_phase if my_phase in ATTACK_PHASES else "none")] = 1.0
    i += len(ATTACK_PHASES)
    vec[i + ATTACK_PHASES.index(enemy_phase if enemy_phase in ATTACK_PHASES else "none")] = 1.0
    i += len(ATTACK_PHASES)
    vec[i] = float(extra.get("my_is_thrown", 0.0))
    vec[i + 1] = min(float(extra.get("my_guard_break_stun", 0)) / FRAMES_PER_SECOND, 1.0)
    vec[i + 2] = float(extra.get("my_burst_used", 0.0))
    vec[i + 3] = min(float(extra.get("my_jump_frame", 0)) / FRAMES_PER_SECOND, 1.0)
    return vec


def policy_vector(obs) -> np.ndarray:
    """Observation -> float32 vector of length POLICY_OBS_DIM."""
    base = obs.features()
    if getattr(obs, "has_engine_detail", False):
        my_phase, enemy_phase = obs.my_attack_phase, obs.enemy_attack_phase
    else:
        my_phase = _approx_phase(base["my_last_action"], obs.my_recovery)
        enemy_phase = _approx_phase(base["enemy_last_action"], obs.enemy_recovery)
    extra = {
        "my_is_thrown": float(getattr(obs, "my_is_thrown", False)),
        "my_guard_break_stun": getattr(obs, "my_guard_break_stun", 0),
        "my_burst_used": float(getattr(obs, "my_burst_used", False)),
        "my_jump_frame": getattr(obs, "my_jump_frame", 0),
    }
    return vector_from_parts(base, my_phase, enemy_phase, extra)


def vector_from_log_row(row: dict, my_side: int) -> Optional[np.ndarray]:
    """Fight-log row (FEATURE_NAMES columns, logged from player 1's view) -> vector.

    Logged rows have no attack phase, so it is approximated from recovery and
    the last action. Rows logged from the other side cannot be re-oriented
    exactly, so only ``my_side == 1`` rows are converted.
    """
    if my_side != 1:
        return None
    base = {name: row.get(name, 0.0) for name in FEATURE_NAMES}
    my_phase = _approx_phase(base["my_last_action"] or 0, float(base["my_recovery"] or 0.0))
    enemy_phase = _approx_phase(base["enemy_last_action"] or 0, float(base["enemy_recovery"] or 0.0))
    return vector_from_parts(base, my_phase, enemy_phase, {})


def full_observation_for(state, player: int):
    """observation_for() plus the engine detail the policy needs."""
    from backend.ai.adapter import observation_for

    obs = observation_for(state, player)
    if getattr(obs, "has_engine_detail", False):
        return obs
    return enrich_from_state(obs, state, player)
