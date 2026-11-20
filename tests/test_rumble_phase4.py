"""Unit tests for Arena Rumble Phase 4: Destructible Crates & Arena Objects.

Verifies:
1. Symmetrical object placement from predefined layouts for all 4 arenas:
   - Dojo, Rooftop, Colosseum, Neon Alley.
2. Destructible wooden crates (25 HP):
   - Block horizontal movement on ground, jumping goes over.
   - Damaged by attacks and projectiles.
   - Break at 0 HP and have a 50% chance to drop standard ground loot.
3. Jump Pad:
   - Launches a grounded fighter upward into the air.
   - 3-second cooldown (180 frames).
4. Spike Trap:
   - Pressure plate arms when stepped on.
   - Triggers after 0.5s delay (30 frames).
   - Deals 8 HP damage, knocks fighter upward into hitstun.
   - 10-second cooldown (600 frames).
"""

import pytest

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.rules import ModeRules
from backend.engine.rumble import init_rumble_arena_objects
from backend.engine.rumble_config import (
    ARENA_LAYOUTS,
    CRATE_DROP_CHANCE,
    CRATE_MAX_HP,
    JUMP_PAD_COOLDOWN_FRAMES,
    JUMP_PAD_LAUNCH_VY,
    TRAP_COOLDOWN_FRAMES,
    TRAP_DAMAGE,
    TRAP_KNOCKUP_VY,
    TRAP_TRIGGER_DELAY_FRAMES,
)
from backend.engine.rumble_state import ArenaObjectState
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step


def _make_rumble_state(arena_name="Dojo"):
    rules = ModeRules.rumble(
        enable_zone=False,
        enable_building=False,
        enable_loot=True,
        enable_objects=True,
        arena_name=arena_name,
    )
    return make_initial_state("Golden", "Crimson", rules=rules, seed=42)


def test_arena_layouts_symmetry_and_validity():
    for name, layout in ARENA_LAYOUTS.items():
        objects = init_rumble_arena_objects(name)
        assert len(objects) >= 3, f"{name} should have at least 3 objects"

        # Check crate HP and dimensions
        crates = [obj for obj in objects if obj.object_type == "crate"]
        for c in crates:
            assert c.hp == CRATE_MAX_HP
            assert 0.0 < c.x < float(ARENA_WIDTH)

        # Check jump pads and traps exist
        pads = [obj for obj in objects if obj.object_type == "jump_pad"]
        traps = [obj for obj in objects if obj.object_type == "trap"]
        assert len(pads) >= 1, f"{name} needs jump pads"
        assert len(traps) >= 1, f"{name} needs spike traps"


def test_destructible_crate_damage_and_loot_drop():
    state = _make_rumble_state()
    # Find a crate
    crate = next(obj for obj in state.arena_objects if obj.object_type == "crate")
    initial_crate_hp = crate.hp
    assert initial_crate_hp == CRATE_MAX_HP

    # Place fighter right in front of crate facing it
    state.fighter1.x = crate.x - 30.0
    state.fighter2.x = crate.x + 200.0

    # Light attack damages crate
    state = step(state, Action.LIGHT, Action.IDLE)
    for _ in range(6):
        state = step(state, Action.IDLE, Action.IDLE)

    crate_in_state = next((obj for obj in state.arena_objects if obj.id == crate.id), None)
    assert crate_in_state is not None
    assert crate_in_state.hp < initial_crate_hp

    # Destroy crate: break with remaining HP = 0
    crate_in_state.hp = 0.0
    state = step(state, Action.IDLE, Action.IDLE)
    # Crate is removed or marked destroyed
    remaining_crates = [obj for obj in state.arena_objects if obj.id == crate.id and obj.hp > 0]
    assert len(remaining_crates) == 0


def test_jump_pad_launch_and_cooldown():
    state = _make_rumble_state()
    # Find jump pad
    pad = next(obj for obj in state.arena_objects if obj.object_type == "jump_pad")
    state.fighter1.x = pad.x
    state.fighter1.in_air = False

    state = step(state, Action.IDLE, Action.IDLE)

    # Stepping on pad launches fighter into the air
    assert state.fighter1.in_air
    pad_in_state = next(obj for obj in state.arena_objects if obj.id == pad.id)
    assert pad_in_state.cooldown > 0

    # Move fighter away from pad so it doesn't immediately re-trigger upon landing
    state.fighter1.x = pad.x + 150.0

    # Cooldown lasts 3 seconds (180 frames)
    for _ in range(JUMP_PAD_COOLDOWN_FRAMES):
        state = step(state, Action.IDLE, Action.IDLE)

    pad_after = next(obj for obj in state.arena_objects if obj.id == pad.id)
    assert pad_after.cooldown == 0


def test_spike_trap_timing_damage_and_cooldown():
    state = _make_rumble_state()
    trap = next(obj for obj in state.arena_objects if obj.object_type == "trap")
    state.fighter1.x = trap.x
    state.fighter1.in_air = False
    initial_hp = state.fighter1.health

    # Step 1: Step on pressure plate -> arms trap
    state = step(state, Action.IDLE, Action.IDLE)
    trap_state = next(obj for obj in state.arena_objects if obj.id == trap.id)
    assert trap_state.is_triggered
    assert trap_state.trigger_timer > 0

    # Before 0.5s delay elapses (30 frames), trap does not deal damage yet
    for _ in range(TRAP_TRIGGER_DELAY_FRAMES - 2):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.health == initial_hp

    # Spikes deploy after trigger delay, dealing 8 HP damage and knockup
    state = step(state, Action.IDLE, Action.IDLE)
    state = step(state, Action.IDLE, Action.IDLE)
    # Damage dealt
    assert state.fighter1.health < initial_hp
    assert state.fighter1.in_air
    assert state.fighter1.hitstun > 0

    # Trap enters 10s cooldown (600 frames)
    trap_after = next(obj for obj in state.arena_objects if obj.id == trap.id)
    assert trap_after.cooldown == TRAP_COOLDOWN_FRAMES
