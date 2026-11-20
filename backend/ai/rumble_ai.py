"""Rumble AI decision logic and macro-actions.

Provides macro-action selection and evaluation for Arena Rumble:
- BUILD: Places cover wall when tactically advantageous
- GO_TO_ITEM: Navigates toward nearest high-value ground item or supply drop
- BREAK_WALL: Smashes wall blocking path to enemy
- MOVE_INTO_ZONE: Retreats inside safe energy barrier
"""

from enum import Enum
import random
from typing import Optional

from backend.ai.actions import Action
from backend.ai.observation import Observation


class RumbleMacro(Enum):
    FIGHT = 0
    MOVE_INTO_ZONE = 1
    GO_TO_ITEM = 2
    BREAK_WALL = 3
    BUILD = 4


def evaluate_rumble_macro(
    obs: Observation,
    personality_name: str = "Golden",
    difficulty: str = "MEDIUM",
    rng: Optional[random.Random] = None,
) -> Optional[Action]:
    """Evaluate rumble-specific tactical priorities and return an action if applicable."""
    if rng is None:
        rng = random.Random()

    # If not in rumble mode, return None immediately (zero overhead/interference in Classic)
    if not obs.is_rumble:
        return None

    # Difficulty-based attentiveness
    # LOW often ignores zone and items; HELL is hyper-aware
    diff_upper = difficulty.upper()
    if diff_upper == "LOW":
        attentive_chance = 0.35
    elif diff_upper == "MEDIUM":
        attentive_chance = 0.65
    elif diff_upper == "HIGH":
        attentive_chance = 0.90
    else:  # HELL
        attentive_chance = 0.99

    # 1. ZONE SAFETY (HIGHEST PRIORITY)
    # Outside zone or within 45px of closing barrier
    has_zone = (obs.zone_left > 0.0 or obs.zone_right < obs.arena_right)
    is_outside = has_zone and ((obs.my_x < obs.zone_left + 15.0) or (obs.my_x > obs.zone_right - 15.0))
    is_endangered = has_zone and ((obs.my_x < obs.zone_left + 45.0) or (obs.my_x > obs.zone_right - 45.0))

    if is_outside or (is_endangered and obs.zone_is_closing):
        # On HIGH and HELL, always escape outside zone immediately
        if diff_upper in ("HIGH", "HELL") or rng.random() < attentive_chance:
            # Move toward center of safe zone
            zone_center = (obs.zone_left + obs.zone_right) / 2.0
            if obs.my_x < zone_center:
                # Must move right
                return _move_right(obs)
            else:
                # Must move left
                return _move_left(obs)

    # If fighter ignores tactical environment on this decision tick, fall back to combat
    if rng.random() > attentive_chance:
        return None

    # 2. BREAK WALL (Crimson personality specialty, or when wall separates fighters)
    if obs.wall_between:
        crimson_bias = 0.95 if personality_name.capitalize() == "Crimson" or diff_upper == "HELL" else 0.60
        if rng.random() < crimson_bias:
            # If close to the wall/enemy, smash it; otherwise advance toward it
            if obs.distance <= (obs.my_reach + 60.0):
                return Action.HEAVY if rng.random() < 0.75 else Action.LIGHT
            else:
                return _move_right(obs) if obs.enemy_direction > 0 else _move_left(obs)

    # 3. BUILD COVER (Steel personality specialty, or defensive positioning)
    can_build = (
        obs.my_build_charges >= 1
        and not obs.my_in_air
        and not obs.wall_between
        and (obs.zone_left + 50.0 <= obs.my_x <= obs.zone_right - 50.0)
    )
    if can_build:
        steel_bias = 0.90 if personality_name.capitalize() == "Steel" or diff_upper == "HELL" else 0.45
        # Build when enemy is attacking, far away, or health is lower
        should_build = (obs.distance >= 150.0 or obs.enemy_health > obs.my_health or obs.my_health <= 0.35)
        if should_build and rng.random() < steel_bias:
            return Action.BUILD

    # 4. GO TO ITEM (Shadow personality specialty, or high-value items nearby)
    if obs.nearest_item_type != "none" and obs.nearest_item_dist < 450.0:
        item_bias = 0.95 if personality_name.capitalize() == "Shadow" or diff_upper == "HELL" else 0.75
        # Check if item is inside safe zone
        item_x = obs.my_x + (obs.nearest_item_dist * obs.nearest_item_dir)
        if obs.zone_left <= item_x <= obs.zone_right:
            if rng.random() < item_bias:
                if obs.nearest_item_dir > 0:
                    return _move_right(obs)
                elif obs.nearest_item_dir < 0:
                    return _move_left(obs)

    # 5. JUMP PAD USAGE (Shadow uses jump pads to reposition)
    if personality_name.capitalize() == "Shadow" and obs.nearest_pad_dist <= 30.0:
        if not obs.my_in_air and rng.random() < 0.70:
            return Action.FORWARD if obs.enemy_direction > 0 else Action.BACK

    return None


def _move_right(obs: Observation) -> Action:
    """Choose action to move right based on fighter facing direction."""
    # If enemy is to the right (enemy_direction == 1), moving right is FORWARD / DASH
    if obs.enemy_direction > 0:
        return Action.DASH if obs.distance > 180.0 else Action.FORWARD
    else:
        # Enemy is to the left, moving right is BACK / BACKDASH
        return Action.BACKDASH if obs.distance < 120.0 else Action.BACK


def _move_left(obs: Observation) -> Action:
    """Choose action to move left based on fighter facing direction."""
    # If enemy is to the right (enemy_direction == 1), moving left is BACK / BACKDASH
    if obs.enemy_direction > 0:
        return Action.BACKDASH if obs.distance < 120.0 else Action.BACK
    else:
        # Enemy is to the left, moving left is FORWARD / DASH
        return Action.DASH if obs.distance > 180.0 else Action.FORWARD
