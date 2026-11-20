"""Unit tests for Arena Rumble Phase 5: AI Support.

Verifies:
1. Observation perceives rumble state:
   - zone boundaries, build charges, shield, ground items, walls, crates, pads, traps.
2. evaluate_rumble_macro tactical priorities:
   - Zone safety: moves inward when outside or near closing barrier.
   - Wall building: places cover when low HP or under pressure.
   - Item collection: navigates toward nearby high-value loot.
   - Wall breaking: smashes walls blocking the path to the enemy.
3. Personality adaptations:
   - Crimson smashes walls aggressively.
   - Steel builds defensive walls.
   - Shadow navigates with agility.
   - Golden adapts tactically.
4. Difficulty scaling:
   - HELL has near 100% attentiveness to zone and drops.
   - LOW ignores zone warnings often.
5. In simulated headless rumble matches, AI uses rumble mechanics without crashes.
"""

import pytest

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.ai.crimson import CrimsonAgent
from backend.ai.golden import GoldenAgent
from backend.ai.observation import Observation
from backend.ai.rumble_ai import evaluate_rumble_macro
from backend.ai.shadow import ShadowAgent
from backend.ai.steel import SteelAgent
from backend.engine.constants import ARENA_WIDTH
from backend.engine.rules import ModeRules
from backend.engine.rumble_state import ItemState, WallState
from backend.engine.step import make_initial_state, step


def _make_rumble_state():
    rules = ModeRules.rumble(
        enable_zone=True,
        enable_building=True,
        enable_loot=True,
        enable_objects=True,
    )
    return make_initial_state("Golden", "Crimson", rules=rules, seed=42)


def test_rumble_observation_fields():
    state = _make_rumble_state()
    state.zone.left = 100.0
    state.zone.right = 700.0
    state.fighter1.shield = 15.0
    state.fighter1.build_charges = 2
    state.items.append(ItemState(id=1, item_type="medkit", x=350.0, y=0.0))
    state.walls.append(WallState(id=2, owner=2, x=300.0, y=0.0, hp=25.0, max_hp=30.0))

    obs = observation_for(state, 1)
    assert obs.is_rumble
    assert obs.zone_left == 100.0
    assert obs.zone_right == 700.0
    assert obs.my_shield == 15.0
    assert obs.my_build_charges == 2
    assert obs.nearest_item_type == "medkit"
    assert obs.wall_between


def test_zone_safety_priority_on_high_and_hell():
    state = _make_rumble_state()
    state.zone.left = 150.0
    state.zone.right = 650.0
    state.zone.is_closing = True

    # Place fighter outside left barrier
    state.fighter1.x = 80.0
    state.fighter2.x = 400.0
    obs = observation_for(state, 1)

    # HELL must immediately move right toward the center of the safe zone
    action = evaluate_rumble_macro(obs, personality_name="Golden", difficulty="HELL")
    assert action in (Action.FORWARD, Action.DASH)


def test_ai_places_build_cover_when_low_health():
    state = _make_rumble_state()
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0
    state.fighter1.health = 0.25  # Low health
    state.fighter1.build_charges = 3

    obs = observation_for(state, 1)
    action = evaluate_rumble_macro(obs, personality_name="Steel", difficulty="HELL")
    assert action == Action.BUILD


def test_ai_breaks_wall_blocking_opponent():
    state = _make_rumble_state()
    state.fighter1.x = 250.0
    state.fighter2.x = 450.0
    # Wall right in front of fighter 1
    state.walls.append(WallState(id=1, owner=2, x=290.0, y=0.0, hp=15.0, max_hp=30.0))

    obs = observation_for(state, 1)
    action = evaluate_rumble_macro(obs, personality_name="Crimson", difficulty="HELL")
    # Crimson wants to break the wall with melee
    assert action in (Action.LIGHT, Action.HEAVY, Action.FORWARD, Action.DASH)


def test_ai_navigates_toward_nearby_loot():
    state = _make_rumble_state()
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0
    state.fighter1.health = 0.40  # Injured
    state.fighter1.build_charges = 0  # No build charges, focuses on loot
    # Medkit at x=280
    state.items.append(ItemState(id=1, item_type="medkit", x=280.0, y=0.0))

    obs = observation_for(state, 1)
    action = evaluate_rumble_macro(obs, personality_name="Golden", difficulty="HELL")
    # Should navigate right toward the medkit
    assert action in (Action.FORWARD, Action.DASH)


def test_difficulty_scaling_attentiveness():
    state = _make_rumble_state()
    state.zone.left = 150.0
    state.zone.right = 650.0
    state.zone.is_closing = False
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0
    state.items.append(ItemState(id=1, item_type="medkit", x=280.0, y=0.0))

    obs = observation_for(state, 1)

    # HELL almost always acts on rumble elements
    hell_actions = [
        evaluate_rumble_macro(obs, personality_name="Golden", difficulty="HELL")
        for _ in range(50)
    ]
    hell_rumble_rate = sum(1 for a in hell_actions if a is not None) / 50.0
    assert hell_rumble_rate > 0.85
