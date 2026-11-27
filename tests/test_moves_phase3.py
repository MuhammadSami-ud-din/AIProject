"""Phase 3 Tests: Super Meter, Guard Meter & Guard Break, Fury, Perfect Parry, Burst."""

import pytest

from backend.ai.actions import Action
from backend.engine.combat import start_attack
from backend.engine.moves import get_move
from backend.engine.state import FighterState
from backend.engine.step import make_initial_state, step


def test_super_meter_gain_and_spend():
    """Dealing damage, taking damage, and whiff punishes build meter; supers spend meter."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0
    state.fighter1.meter = 0.0
    state.fighter2.meter = 0.0

    # Land a clean jab
    jab = get_move("Crimson", Action.LIGHT)
    start_attack(state.fighter1, jab)
    for _ in range(jab.startup + 1):
        state = step(state, Action.LIGHT, Action.IDLE)

    # Attacker and defender both gain meter
    assert state.fighter1.meter > 0.0
    assert state.fighter2.meter > 0.0

    # Spends 100 meter on super
    state.fighter1.recovery = 0
    state.fighter1.attack_phase = "none"
    state.fighter1.meter = 100.0
    blood_fury = get_move("Crimson", Action.SUPER)
    assert blood_fury.meter_cost == 100.0

    started = start_attack(state.fighter1, blood_fury)
    assert started is True
    assert state.fighter1.meter == 0.0


def test_guard_meter_and_guard_break():
    """Blocking repeatedly drains guard meter; at 0, guard breaks and victim is stunned for 40 frames."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0
    state.fighter2.guard_meter = 100.0

    # Heavy punch blocked
    heavy = get_move("Crimson", Action.HEAVY)
    start_attack(state.fighter1, heavy)
    for _ in range(heavy.startup + 1):
        state = step(state, Action.HEAVY, Action.BLOCK)

    # Guard meter drained
    assert state.fighter2.guard_meter < 100.0

    # Set guard meter dangerously low, reset positions & recoveries, block another hit
    state.fighter1.recovery = 0
    state.fighter1.attack_phase = "none"
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0
    state.fighter2.blockstun = 0
    state.fighter2.guard_meter = 5.0
    start_attack(state.fighter1, heavy)
    events = []
    for _ in range(heavy.startup + 1):
        state = step(state, Action.HEAVY, Action.BLOCK)
        events.append(state.fighter2.last_hit_effect)

    # GUARD BREAK! (last_hit_effect is a one-frame event)
    assert state.fighter2.guard_break_stun > 0
    assert state.fighter2.hitstun >= 38
    assert "guard_break" in events


def test_fury_mode_bonus_and_super_discount():
    """Below 25% health, fighter gains +10% damage and super unlocks for 60 meter."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.health = 0.20  # Under 25%
    assert state.fighter1.is_fury is True

    # Super costs 60 in Fury instead of 100
    state.fighter1.meter = 60.0
    blood_fury = get_move("Crimson", Action.SUPER)
    started = start_attack(state.fighter1, blood_fury)
    assert started is True
    assert state.fighter1.meter == 0.0


def test_perfect_parry():
    """Block pressed within 4 frames before incoming hit negates damage, staggers attacker, +12 meter."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0
    state.fighter2.meter = 0.0

    # Attacker starts heavy punch (startup 10f)
    heavy = get_move("Crimson", Action.HEAVY)
    start_attack(state.fighter1, heavy)

    # Defender waits until 2 frames before hit to press block
    for _ in range(heavy.startup - 1):
        state = step(state, Action.HEAVY, Action.IDLE)

    # Press block (block_held_frames <= 4)
    state = step(state, Action.HEAVY, Action.BLOCK)

    # PARRY!
    assert state.fighter2.last_hit_effect == "parry"
    assert state.fighter2.health == 1.0  # zero damage taken!
    assert state.fighter1.recovery > 0   # attacker staggered!
    assert state.fighter2.meter >= 10.0  # parry meter bonus


def test_burst_defense():
    """Burst spends 50 meter while in hitstun to end combo, blow opponent away; once per round."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0
    state.fighter2.meter = 50.0
    state.fighter2.hitstun = 20
    assert state.fighter2.burst_used_this_round is False

    # Defender triggers BURST
    state = step(state, Action.IDLE, Action.BURST)

    assert state.fighter2.burst_used_this_round is True
    assert state.fighter2.meter == 0.0
    assert state.fighter2.hitstun == 0   # hitstun broken!
    assert state.fighter2.last_hit_effect == "burst"
    assert state.fighter1.recovery > 0   # attacker staggered
    assert state.fighter1.x < 150.0      # pushed far back!

    # Cannot burst again in the same round
    state.fighter2.meter = 50.0
    state.fighter2.hitstun = 20
    state = step(state, Action.IDLE, Action.BURST)
    assert state.fighter2.meter == 50.0  # burst was not used again
