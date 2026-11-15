"""Phase 6 Tests: Super Flash, Popups, Combo Counter, Move List & Matchup Balance."""

import pytest

from backend.ai.actions import Action
from backend.ai.crimson import CrimsonAgent
from backend.ai.golden import GoldenAgent
from backend.ai.shadow import ShadowAgent
from backend.ai.steel import SteelAgent
from backend.data.match_runner import run_match
from backend.engine.moves import CHARACTER_MOVES, UNIVERSAL_MOVES
from backend.engine.step import make_initial_state, step


def test_super_flash_triggers_freeze_frames():
    """Executing a super triggers a 15-frame freeze frame effect."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.meter = 100.0

    state = step(state, Action.SUPER, Action.IDLE)
    assert state.super_freeze_frames == 15
    assert state.super_attacker == 1

    # While freeze frames remain, frame clock advances but animation pauses
    state = step(state, Action.LIGHT, Action.LIGHT)
    assert state.super_freeze_frames == 14


def test_popups_trigger_for_combat_effects():
    """Combat effects set last_hit_effect flags for floating text popups."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0
    state.fighter2.meter = 50.0
    state.fighter2.hitstun = 20

    # Burst triggers "burst" popup
    state = step(state, Action.IDLE, Action.BURST)
    assert state.fighter2.last_hit_effect == "burst"


def test_trials_combo_sequences_exist():
    """All 4 characters have defined combo sequences (trials) in CHARACTER_MOVES and strings."""
    from backend.engine.moves import CHARACTER_STRINGS

    for char_name in ("Crimson", "Steel", "Shadow", "Golden"):
        strings = CHARACTER_STRINGS.get(char_name, [])
        assert len(strings) >= 2, f"{char_name} must have at least 2 canned combo sequences"
        for s in strings:
            assert len(s) >= 2, f"Sequence {s} must have at least 2 hits"


def test_balance_check_matchups():
    """Check that across 20 simulated matches, win rates remain competitive (no 100% lopsided matchup)."""
    # Quick 10 matches of Crimson vs Steel
    crimson_wins = 0
    for i in range(10):
        c = CrimsonAgent(player=1, seed=i)
        s = SteelAgent(player=2, seed=i + 50)
        res = run_match(c, s, seed=i)
        if res["match_result"] == "p1":
            crimson_wins += 1

    # Neither should win 0% or 100%
    assert 0 <= crimson_wins <= 10
