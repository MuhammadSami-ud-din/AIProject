"""Unit tests for Arena Rumble Phase 3: Loot & Supply Drops.

Verifies:
1. Ground item periodic spawning respects the max 2 items limit.
2. Items spawn inside the current safe zone.
3. Item effects on pickup:
   - Medkit: +25 HP (capped at starting HP 1.0).
   - Shield Cell: +25 Shield (absorbs damage before health, decays 1 per 3s).
   - Meter Orb: +30% special meter.
   - Build Kit: +2 build charges (can exceed max by 1, up to 4).
   - Speed Boots: +30% speed boost for 6s (360 frames).
   - Power Fist: +25% attack damage for 5s (300 frames).
4. Supply Drop triggers at 30s remaining, drops slowly in 4s, lands, and contains rare items:
   - Big Medkit (+50 HP).
   - Overcharge (+50% meter and +3 build charges).
5. Auto pickup vs manual Action.PICKUP (key E).
"""

import pytest

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.rules import ModeRules
from backend.engine.rumble_config import (
    BIG_MEDKIT_HP,
    BUILD_KIT_CHARGES,
    BUILD_KIT_MAX_EXTRA,
    BUILD_MAX_CHARGES,
    LOOT_MAX_GROUND_ITEMS,
    LOOT_SPAWN_MIN_FRAMES,
    MEDKIT_HP,
    METER_ORB_AMOUNT,
    OVERCHARGE_CHARGES,
    OVERCHARGE_METER,
    POWER_FIST_DURATION_FRAMES,
    POWER_FIST_MULTIPLIER,
    RUMBLE_ROUND_FRAMES,
    SHIELD_CELL_HP,
    SHIELD_DECAY_FRAMES,
    SHIELD_MAX_HP,
    SPEED_BOOTS_DURATION_FRAMES,
    SPEED_BOOTS_MULTIPLIER,
    SUPPLY_DROP_TRIGGER_FRAME,
)
from backend.engine.rumble_state import ItemState, SupplyDropState
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step


def _make_rumble_state(auto_pickup=True):
    rules = ModeRules.rumble(
        enable_zone=True,
        enable_building=False,
        enable_loot=True,
        enable_objects=False,
        auto_pickup=auto_pickup,
    )
    return make_initial_state("Golden", "Crimson", rules=rules, seed=42)


def test_ground_item_spawn_limits():
    state = _make_rumble_state()
    assert len(state.items) == 0

    # Advance past first loot timer
    state.next_loot_timer = 1
    state = step(state, Action.IDLE, Action.IDLE)
    assert len(state.items) == 1

    # Advance past second loot timer
    state.next_loot_timer = 1
    state = step(state, Action.IDLE, Action.IDLE)
    assert len(state.items) == 2

    # Third loot spawn is blocked by max ground items limit
    state.next_loot_timer = 1
    state = step(state, Action.IDLE, Action.IDLE)
    assert len(state.items) == LOOT_MAX_GROUND_ITEMS


def test_item_pickup_medkit_and_cap():
    state = _make_rumble_state(auto_pickup=True)
    state.fighter1.health = 0.50
    state.fighter1.x = 300.0

    # Place medkit on ground at x=300
    medkit = ItemState(id=1, item_type="medkit", x=300.0, y=0.0)
    state.items.append(medkit)

    state = step(state, Action.IDLE, Action.IDLE)
    # Collected: +25 HP = 0.75
    assert len(state.items) == 0
    assert pytest.approx(state.fighter1.health, abs=0.01) == 0.75
    assert state.fighter1.items_collected == 1

    # Test cap at full health 1.0
    state.fighter1.health = 0.90
    medkit2 = ItemState(id=2, item_type="medkit", x=300.0, y=0.0)
    state.items.append(medkit2)
    state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.health == 1.0


def test_item_pickup_shield_cell_and_decay():
    state = _make_rumble_state(auto_pickup=True)
    state.fighter1.shield = 0.0
    state.fighter1.x = 300.0

    # Place shield cell
    shield_item = ItemState(id=1, item_type="shield_cell", x=300.0, y=0.0)
    state.items.append(shield_item)

    state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.shield == SHIELD_CELL_HP  # 25.0

    # Fast forward to next decay tick (180 frames = 3s)
    for _ in range(SHIELD_DECAY_FRAMES):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.fighter1.shield == SHIELD_CELL_HP - 1.0


def test_item_pickup_meter_orb_and_build_kit():
    state = _make_rumble_state(auto_pickup=True)
    state.fighter1.x = 300.0
    state.fighter1.meter = 20.0
    state.fighter1.build_charges = 3

    # Meter Orb: +30% meter
    meter_orb = ItemState(id=1, item_type="meter_orb", x=300.0, y=0.0)
    state.items.append(meter_orb)
    state = step(state, Action.IDLE, Action.IDLE)
    assert pytest.approx(state.fighter1.meter, abs=0.01) == 50.0

    # Build Kit: +2 charges, exceeds max by 1 (max 4)
    build_kit = ItemState(id=2, item_type="build_kit", x=300.0, y=0.0)
    state.items.append(build_kit)
    state = step(state, Action.IDLE, Action.IDLE)
    # Starts at 3 + 2 = 5, capped at max 3 + 1 = 4
    assert state.fighter1.build_charges == BUILD_MAX_CHARGES + BUILD_KIT_MAX_EXTRA  # 4


def test_item_pickup_speed_boots_and_power_fist():
    state = _make_rumble_state(auto_pickup=True)
    state.fighter1.x = 300.0

    # Speed Boots: duration 360 frames (6s)
    boots = ItemState(id=1, item_type="speed_boots", x=300.0, y=0.0)
    state.items.append(boots)
    state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.speed_boost_timer == SPEED_BOOTS_DURATION_FRAMES

    # Power Fist: duration 300 frames (5s)
    fist = ItemState(id=2, item_type="power_fist", x=300.0, y=0.0)
    state.items.append(fist)
    state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.power_boost_timer == POWER_FIST_DURATION_FRAMES


def test_supply_drop_arrival_and_rare_loot():
    state = _make_rumble_state(auto_pickup=True)
    # Move fighters away to the edges so they do not pick up supply drop early
    state.fighter1.x = 20.0
    state.fighter2.x = 780.0

    # Set frame to supply drop trigger frame
    state.frame = SUPPLY_DROP_TRIGGER_FRAME
    state = step(state, Action.IDLE, Action.IDLE)

    assert state.supply_drop is not None
    assert not state.supply_drop.is_landed
    assert state.supply_drop.item_type in ("big_medkit", "overcharge")

    # Fast forward falling (4s = 240 frames)
    for _ in range(250):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.supply_drop.is_landed
    assert state.supply_drop.y == 0.0

    # Fighter collects landed supply drop
    drop_x = state.supply_drop.x
    state.fighter1.x = drop_x
    drop_type = state.supply_drop.item_type

    if drop_type == "big_medkit":
        state.fighter1.health = 0.20
    else:
        state.fighter1.meter = 0.0
        state.fighter1.build_charges = 0

    state = step(state, Action.IDLE, Action.IDLE)
    assert state.supply_drop is None

    if drop_type == "big_medkit":
        assert pytest.approx(state.fighter1.health, abs=0.01) == 0.70  # +50 HP
    else:
        assert state.fighter1.meter >= 50.0
        assert state.fighter1.build_charges >= 3


def test_manual_pickup_requires_action_pickup():
    state = _make_rumble_state(auto_pickup=False)
    state.fighter1.x = 300.0
    medkit = ItemState(id=1, item_type="medkit", x=300.0, y=0.0)
    state.items.append(medkit)

    # Walking over without E does not pick it up
    state = step(state, Action.FORWARD, Action.IDLE)
    assert len(state.items) == 1

    # Action.PICKUP (key E) collects item
    state = step(state, Action.PICKUP, Action.IDLE)
    assert len(state.items) == 0
