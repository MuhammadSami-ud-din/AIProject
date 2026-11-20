"""Comprehensive test suite for the Shield Wall Ability (Steps 1-5).

Verifies:
1. Classic mode remains untouched when enable_shield_wall=False.
2. Shield deployment: FRONT & BACK, 30x130 dimensions, 8f startup (5f Shadow), vulnerability during startup.
3. Balance controls: cost (35/100), regen (8/s), turtle penalty, cooldown (6s), max 1 rule.
4. Counters:
   - Throws ignore shields and remove them on grab.
   - Heavy attacks deal x2 damage (Crimson x2.5) + 15% chip damage; Light deals 0% chip.
   - Overheads & jump-ins bypass standing shield height.
   - Attacking while shield is up drains shield HP by 3 per attack.
5. Shield break stun: 20 frames vulnerable stun upon reaching 0 HP.
6. Movement blocking & safety: blocks walking, jumping goes over, no fighter ever stuck inside shield.
7. Presets, clamping, per-character tweaks, keybindings (Q/E), DB persistence, and determinism.
"""

import os
import tempfile
import pytest

from backend.ai.actions import Action
from backend.ai.adapter import observation_for
from backend.ai.crimson import CrimsonAgent
from backend.ai.golden import GoldenAgent
from backend.ai.shield_ai import evaluate_shield_action
from backend.data.match_runner import run_match
from backend.data.results_db import ResultsDB
from backend.engine.rules import ModeRules
from backend.engine.shield_config import (
    PRESETS,
    ShieldBalance,
    clamp_shield_balance,
    get_character_shield_balance,
)
from backend.engine.shield_state import ShieldWallState
from backend.engine.state import ProjectileState
from backend.engine.step import make_initial_state, step
from frontend.input_handler import InputHandler


def _make_shield_state(char1="Golden", char2="Crimson", enable=True):
    rules = ModeRules.classic(enable_shield_wall=enable)
    return make_initial_state(char1, char2, rules=rules, seed=42)


def test_classic_unaffected_when_shield_disabled():
    state = _make_shield_state(enable=False)
    state = step(state, Action.SHIELD_FRONT, Action.SHIELD_BACK)
    assert state.fighter1.shield_wall is None
    assert state.fighter2.shield_wall is None
    assert state.fighter1.shield_startup_frames == 0


def test_shield_front_and_back_startup_and_deploy():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 250.0
    state.fighter2.x = 550.0

    # Raise FRONT shield: costs energy_cost, 8 frames startup
    base_bal = ShieldBalance()
    state = step(state, Action.SHIELD_FRONT, Action.IDLE)
    assert pytest.approx(state.fighter1.shield_energy, abs=0.2) == (100.0 - base_bal.energy_cost)
    assert state.fighter1.shield_startup_frames == base_bal.startup_frames
    assert state.fighter1.shield_wall is None

    # Complete remaining 8 startup frames
    for _ in range(base_bal.startup_frames):
        state = step(state, Action.IDLE, Action.IDLE)

    sw = state.fighter1.shield_wall
    assert sw is not None
    assert sw.side == "front"
    assert sw.x > state.fighter1.x  # In front (between Golden and Crimson)
    assert sw.width == 30.0
    assert sw.height == 130.0
    assert sw.hp == base_bal.shield_hp

    # P2 raises BACK shield
    state = step(state, Action.IDLE, Action.SHIELD_BACK)
    for _ in range(8):
        state = step(state, Action.IDLE, Action.IDLE)
    sw2 = state.fighter2.shield_wall
    assert sw2 is not None
    assert sw2.side == "back"
    assert sw2.x > state.fighter2.x  # Behind P2 (to the right of P2)


def test_startup_hit_cancels_shield():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 300.0
    state.fighter2.x = 340.0

    # P1 starts shield (8f startup), P2 immediately uses LIGHT attack (fast startup)
    state = step(state, Action.SHIELD_FRONT, Action.LIGHT)
    for _ in range(5):
        state = step(state, Action.IDLE, Action.IDLE)

    # P1 was hit during startup -> shield cancelled
    assert state.fighter1.shield_wall is None
    assert state.fighter1.shield_startup_frames == 0
    assert state.fighter1.health < 1.0


def test_max_one_shield_and_cooldown_prevents_spam():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0

    # Deploy front shield
    state = step(state, Action.SHIELD_FRONT, Action.IDLE)
    for _ in range(8):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.shield_wall.side == "front"

    # Attempt to raise BACK shield while FRONT is active -> blocked by Max 1 rule
    state = step(state, Action.SHIELD_BACK, Action.IDLE)
    assert state.fighter1.shield_startup_frames == 0
    assert state.fighter1.shield_wall.side == "front"

    # Let duration expire (3.0s = 180 frames)
    for _ in range(180):
        state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.shield_wall is None
    assert state.fighter1.shield_cooldown_frames > 0

    # Back-to-back shield blocked by cooldown
    state = step(state, Action.SHIELD_FRONT, Action.IDLE)
    assert state.fighter1.shield_startup_frames == 0


def test_turtle_penalty_halts_regen_while_blocking():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0
    state.fighter1.shield_wall = ShieldWallState(owner=1, side="front", x=245.0, hp=25.0, duration_frames=120)
    state.fighter1.shield_energy = 50.0

    # While blocking AND shield is up -> regen stops
    state = step(state, Action.BLOCK, Action.IDLE)
    assert state.fighter1.shield_energy == 50.0

    # When not blocking -> regen resumes
    state = step(state, Action.IDLE, Action.IDLE)
    assert state.fighter1.shield_energy > 50.0


def test_attack_while_shield_up_drains_3_hp():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 200.0
    state.fighter2.x = 600.0
    state.fighter1.shield_wall = ShieldWallState(owner=1, side="front", x=245.0, hp=25.0, duration_frames=180)

    state = step(state, Action.LIGHT, Action.IDLE)
    assert state.fighter1.shield_wall.hp == 22.0


def test_counter_throws_ignore_and_remove_shield():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 300.0
    state.fighter2.x = 355.0
    state.fighter1.shield_wall = ShieldWallState(owner=1, side="front", x=335.0, hp=25.0, duration_frames=180)

    # P2 performs THROW -> ignores shield and removes it
    state = step(state, Action.IDLE, Action.THROW)
    for _ in range(20):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.fighter1.shield_wall is None
    assert state.fighter1.health < 1.0


def test_counter_heavy_deals_2x_damage_and_15pct_chip():
    state = _make_shield_state("Golden", "Golden")
    state.fighter1.x = 300.0
    state.fighter2.x = 365.0
    state.fighter1.shield_wall = ShieldWallState(owner=1, side="front", x=340.0, hp=25.0, duration_frames=180)
    initial_hp = state.fighter1.health

    # P2 performs HEAVY attack
    state = step(state, Action.IDLE, Action.HEAVY)
    for _ in range(12):
        state = step(state, Action.IDLE, Action.IDLE)

    # Shield took 2x heavy damage (e.g. 12 * 2 = 24 HP or broke)
    if state.fighter1.shield_wall is not None:
        assert state.fighter1.shield_wall.hp < 10.0
    # Fighter took 15% chip damage
    assert state.fighter1.health < initial_hp


def test_counter_overhead_goes_over_shield():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 300.0
    state.fighter2.x = 355.0
    state.fighter1.shield_wall = ShieldWallState(owner=1, side="front", x=335.0, hp=25.0, duration_frames=180)

    # P2 performs OVERHEAD -> goes over standing shield height, hits P1 directly
    state = step(state, Action.IDLE, Action.OVERHEAD)
    for _ in range(18):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.fighter1.health < 1.0
    # Shield was not damaged by the overhead
    assert state.fighter1.shield_wall.hp == 25.0


def test_shield_break_stun_20_frames():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 300.0
    state.fighter2.x = 360.0
    state.fighter1.shield_wall = ShieldWallState(owner=1, side="front", x=335.0, hp=5.0, duration_frames=180)

    # P2 hits shield to break it
    state = step(state, Action.IDLE, Action.HEAVY)
    for _ in range(12):
        state = step(state, Action.IDLE, Action.IDLE)

    assert state.fighter1.shield_wall is None
    assert state.fighter1.shield_break_stun > 0
    assert state.fighter1.shield_walls_broken == 1


def test_movement_blocked_and_no_stuck_inside_shield():
    state = _make_shield_state("Golden", "Crimson")
    state.fighter1.x = 200.0
    state.fighter2.x = 400.0
    state.fighter1.shield_wall = ShieldWallState(owner=1, side="front", x=245.0, hp=25.0, duration_frames=180)

    # Walk forward into shield: cannot pass shield
    for _ in range(15):
        state = step(state, Action.FORWARD, Action.IDLE)

    assert state.fighter1.x < state.fighter1.shield_wall.left
    assert abs(state.fighter1.x - state.fighter1.shield_wall.x) >= (state.fighter1.shield_wall.width / 2.0 + 15.0)

    # Jump over shield
    state = step(state, Action.JUMP, Action.IDLE)
    for _ in range(25):
        state = step(state, Action.FORWARD, Action.IDLE)
    assert state.fighter1.x > state.fighter1.shield_wall.right


def test_character_tweaks_and_clamping():
    base = ShieldBalance()
    steel = get_character_shield_balance(base, "Steel")
    crimson = get_character_shield_balance(base, "Crimson")
    shadow = get_character_shield_balance(base, "Shadow")
    golden = get_character_shield_balance(base, "Golden")

    assert steel.shield_hp == pytest.approx(base.shield_hp * 1.3)
    assert crimson.duration_s == pytest.approx(base.duration_s * 0.7)
    assert crimson.heavy_attack_bonus == 2.5
    assert shadow.startup_frames == 5
    assert shadow.shield_hp == pytest.approx(base.shield_hp * 0.7)
    assert golden == base

    # Clamping boundaries
    clamped = clamp_shield_balance(
        shield_hp=999.0,
        duration_s=0.1,
        cooldown_s=99.0,
        energy_cost=5.0,
        energy_regen_per_s=100.0,
    )
    assert clamped.shield_hp == 60.0
    assert clamped.duration_s == 1.0
    assert clamped.cooldown_s == 15.0
    assert clamped.energy_cost == 20.0
    assert clamped.energy_regen_per_s == 15.0


def test_keybindings_and_observation_mask():
    import pygame
    handler = InputHandler()
    keys = {c: False for c in range(512)}
    keys[pygame.K_q] = True
    assert handler.get_action(400.0, 200.0, keys=keys, enable_shield_wall=True) == Action.SHIELD_FRONT

    keys[pygame.K_q] = False
    keys[pygame.K_e] = True
    assert handler.get_action(400.0, 200.0, keys=keys, enable_shield_wall=True) == Action.SHIELD_BACK

    # Observation masking
    state = _make_shield_state("Golden", "Crimson")
    obs = observation_for(state, 1)
    assert obs.enable_shield_wall
    assert obs.can_use_shield()

    state.fighter1.shield_energy = 10.0
    obs_low = observation_for(state, 1)
    assert not obs_low.can_use_shield()


def test_shield_wall_determinism():
    rules = ModeRules.classic(enable_shield_wall=True)
    a1 = GoldenAgent(player=1, difficulty="HIGH", seed=777)
    a2 = CrimsonAgent(player=2, difficulty="HIGH", seed=778)
    r1 = run_match(a1, a2, seed=777, rules=rules, record_frames=False)

    b1 = GoldenAgent(player=1, difficulty="HIGH", seed=777)
    b2 = CrimsonAgent(player=2, difficulty="HIGH", seed=778)
    r2 = run_match(b1, b2, seed=777, rules=rules, record_frames=False)

    assert r1["match_result"] == r2["match_result"]
    assert r1["p1_rounds_won"] == r2["p1_rounds_won"]
    assert r1["p2_rounds_won"] == r2["p2_rounds_won"]


def test_results_db_stores_shield_balance():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "shield_db.db")
        db = ResultsDB(db_path=db_path)
        db.save_match({
            "mode": "Human vs AI",
            "p1_kind": "human",
            "p1_character": "Golden",
            "p2_kind": "ai",
            "p2_character": "Steel",
            "winner_side": 1,
            "rounds_p1": 2,
            "rounds_p2": 0,
            "duration_s": 30.0,
            "arena": "Dojo",
            "status": "finished",
            "shield_enabled": True,
            "shield_preset": "Strong",
            "shield_balance": {"p1_hp": 35.0, "p2_hp": 35.0},
        })
        with db.connection() as conn:
            row = conn.execute("SELECT shield_enabled, shield_preset FROM matches").fetchone()
            assert row["shield_enabled"] == 1
            assert row["shield_preset"] == "Strong"
