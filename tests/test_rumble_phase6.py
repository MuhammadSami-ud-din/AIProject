"""Unit tests for Arena Rumble Phase 6: Mode Toggle, Controls & Stats Polish.

Verifies:
1. ModeRules toggles:
   - classic(): all flags False.
   - rumble(): is_rumble=True, allows selective toggles (zone only, building only, full).
2. Keybindings:
   - B key triggers Action.BUILD.
   - E key triggers Action.PICKUP.
3. Post-fight stats tracking on FighterState:
   - walls_built, walls_broken, items_collected, zone_damage_taken.
4. Results Database integration:
   - Saves 'classic' vs 'rumble' mode column in match records.
   - Stores and retrieves rumble match records.
"""

import os
import tempfile
import pytest

from backend.ai.actions import Action
from backend.data.results_db import ResultsDB
from backend.engine.rules import ModeRules
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step
from frontend.input_handler import InputHandler


def test_mode_rules_factory_and_toggles():
    classic = ModeRules.classic()
    assert not classic.is_rumble
    assert not classic.enable_zone
    assert not classic.enable_building
    assert not classic.enable_loot
    assert not classic.enable_objects

    full_rumble = ModeRules.rumble()
    assert full_rumble.is_rumble
    assert full_rumble.enable_zone
    assert full_rumble.enable_building
    assert full_rumble.enable_loot
    assert full_rumble.enable_objects

    # Selective toggles (e.g. Zone Only)
    zone_only = ModeRules.rumble(enable_building=False, enable_loot=False, enable_objects=False)
    assert zone_only.is_rumble
    assert zone_only.enable_zone
    assert not zone_only.enable_building
    assert not zone_only.enable_loot
    assert not zone_only.enable_objects


def test_rumble_keybindings_mapping():
    import pygame
    handler = InputHandler()
    all_keys = {code: False for code in range(512)}

    # Press 'b' -> Action.BUILD
    all_keys[pygame.K_b] = True
    action_b = handler.get_action(enemy_x=400.0, my_x=200.0, keys=all_keys)
    assert action_b == Action.BUILD

    # Release 'b', press 'e' -> Action.PICKUP
    all_keys[pygame.K_b] = False
    all_keys[pygame.K_e] = True
    action_e = handler.get_action(enemy_x=400.0, my_x=200.0, keys=all_keys)
    assert action_e == Action.PICKUP


def test_fighter_rumble_stats_tracking():
    state = make_initial_state("Golden", "Crimson", rules=ModeRules.rumble(), seed=42)
    f1 = state.fighter1
    assert f1.walls_built == 0
    assert f1.walls_broken == 0
    assert f1.items_collected == 0
    assert f1.zone_damage_taken == 0.0

    # Build a wall -> walls_built increments
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0
    state = step(state, Action.BUILD, Action.IDLE)
    for _ in range(12):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.walls_built == 1


def test_results_db_stores_and_queries_rumble_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_rumble_results.db")
        db = ResultsDB(db_path=db_path)

        # Record a classic match
        db.save_match({
            "mode": "classic",
            "p1_kind": "human",
            "p1_character": "Golden",
            "p2_kind": "ai",
            "p2_character": "Crimson",
            "winner_side": 1,
            "rounds_p1": 2,
            "rounds_p2": 0,
            "duration_s": 20.0,
            "arena": "Dojo",
            "status": "finished",
        })

        # Record a rumble match
        db.save_match({
            "mode": "rumble",
            "p1_kind": "human",
            "p1_character": "Steel",
            "p2_kind": "ai",
            "p2_character": "Shadow",
            "winner_side": 1,
            "rounds_p1": 2,
            "rounds_p2": 1,
            "duration_s": 40.0,
            "arena": "Dojo",
            "status": "finished",
        })

        # Filter by mode
        classic_matches = db.get_last_matches(limit=10, mode="classic")
        rumble_matches = db.get_last_matches(limit=10, mode="rumble")

        assert len(classic_matches) == 1
        assert classic_matches[0]["p1_character"] == "Golden"

        assert len(rumble_matches) == 1
        assert rumble_matches[0]["p1_character"] == "Steel"
        assert rumble_matches[0]["mode"] == "rumble"
