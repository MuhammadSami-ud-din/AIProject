"""AI Decision Logic for the Shield Wall Ability (Step 4).

Integrates personality-specific shield usage and difficulty-scaled counterplay:
- Steel: uses front shields to set up punishes.
- Shadow: uses back shields when near corner or zone.
- Crimson: rarely shields, favors heavy attacks and throws to break enemy shields.
- Golden: shields when opponent model predicts an attack.

Difficulty scaling:
- LOW: shields at random times and wastes energy.
- MEDIUM: shields when it sees an attack coming.
- HIGH: shields only for real threats and throws enemies who shield.
- HELL: rarely wastes a shield and punishes every shield break.
"""

import random
from typing import Optional

from backend.ai.actions import Action
from backend.ai.observation import Observation


def evaluate_shield_action(
    obs: Observation,
    personality_name: str = "Golden",
    difficulty: str = "MEDIUM",
    rng: Optional[random.Random] = None,
    predicted_enemy_attack: bool = False,
) -> Optional[Action]:
    """Evaluate whether the AI should raise a shield wall or counter an enemy's shield."""
    if not obs.enable_shield_wall:
        return None

    if rng is None:
        rng = random.Random()

    diff = difficulty.upper()
    char = personality_name.capitalize()

    # 1. OFFENSIVE COUNTERPLAY vs ENEMY SHIELD WALL
    if obs.enemy_shield_wall_up != "none":
        # Enemy has a shield up: counter with Throw, Overhead, or Heavy Attack occasionally
        if diff in ("HIGH", "HELL") or char == "Crimson":
            counter_prob = 0.25 if char == "Crimson" else 0.03
            if obs.distance <= obs.my_reach + 15.0 and rng.random() < counter_prob:
                roll = rng.random()
                if roll < 0.35:
                    return Action.THROW  # Throws ignore shields and remove them!
                elif roll < 0.70:
                    return Action.HEAVY  # Heavy deals x2 / x2.5 damage to shield
                else:
                    return Action.OVERHEAD  # Overhead goes over standing shield

    # 2. DEFENSIVE SHIELD DEPLOYMENT (Only if masked-valid)
    if not obs.can_use_shield():
        return None

    # LOW difficulty: shields at random times, often wasting energy
    if diff == "LOW":
        if rng.random() < 0.03:
            return Action.SHIELD_FRONT if rng.random() < 0.75 else Action.SHIELD_BACK
        return None

    # MEDIUM difficulty: shields when it sees an attack coming
    if diff == "MEDIUM":
        if obs.enemy_is_attacking and obs.distance <= obs.enemy_reach + 60.0:
            if rng.random() < 0.20:
                return Action.SHIELD_FRONT
        return None

    # HIGH & HELL difficulties: smart personality-driven shielding
    # Crimson rarely shields (prefers aggression)
    if char == "Crimson":
        if obs.my_health < 0.25 and obs.enemy_is_attacking and obs.distance < 130.0:
            if rng.random() < 0.06:
                return Action.SHIELD_FRONT
        return None

    # Shadow: uses BACK shield when near corner or closing zone
    if char == "Shadow":
        near_corner = obs.i_am_cornered or obs.room_behind_me < 75.0
        if near_corner and obs.distance < 180.0 and obs.distance > 70.0:
            if rng.random() < (0.12 if diff == "HELL" else 0.08):
                return Action.SHIELD_BACK
        elif obs.enemy_is_attacking and 75.0 < obs.distance <= obs.enemy_reach + 50.0:
            if rng.random() < 0.08:
                return Action.SHIELD_FRONT
        return None

    # Steel: uses FRONT shield at mid-range to absorb pressure and set up punishes
    if char == "Steel":
        real_threat = (
            (obs.enemy_is_attacking and 75.0 < obs.distance <= obs.enemy_reach + 60.0)
            or (obs.enemy_meter >= 100.0 and 80.0 < obs.distance < 160.0)
        )
        if real_threat:
            chance = 0.06 if diff == "HELL" else 0.04
            if rng.random() < chance:
                return Action.SHIELD_FRONT
        return None

    # Golden: shields when opponent model predicts an attack at safe spacing
    if char == "Golden":
        threat = (predicted_enemy_attack or obs.enemy_is_attacking) and (75.0 < obs.distance <= obs.enemy_reach + 60.0)
        if threat:
            chance = 0.01 if diff == "HELL" else 0.005
            if rng.random() < chance:
                return Action.SHIELD_FRONT

    return None
