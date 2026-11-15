"""Phase 4 Tests: Character Signature Moves, Projectiles, Armor, Command Grabs & Reflection."""

import pytest

from backend.ai.actions import Action
from backend.engine.combat import start_attack
from backend.engine.moves import get_move
from backend.engine.step import make_initial_state, step


def test_crimson_berserker_charge_armor():
    """Berserker Charge has 1 point of armor: absorbs 1 hit, takes 50% damage without flinching."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0

    charge = get_move("Crimson", Action.SPECIAL_BACK)
    assert charge.armor == 1

    start_attack(state.fighter1, charge)
    assert state.fighter1.armor_hits == 1

    # Enemy hits with a light attack during charge startup
    jab = get_move("Steel", Action.LIGHT)
    start_attack(state.fighter2, jab)

    # Step until jab connects
    for _ in range(jab.startup + 1):
        state = step(state, Action.SPECIAL_BACK, Action.LIGHT)

    # Crimson absorbed the hit: takes half damage and does NOT enter hitstun!
    assert state.fighter1.health < 1.0
    assert state.fighter1.hitstun == 0
    assert state.fighter1.attack_phase in ("startup", "active")


def test_steel_reflector_reflects_projectiles():
    """Steel's Reflector (SPECIAL_BACK) turns incoming projectiles around and changes owner."""
    state = make_initial_state("Shadow", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 400.0

    # Shadow fires Energy Dart (SPECIAL_NEUTRAL)
    dart = get_move("Shadow", Action.SPECIAL_NEUTRAL)
    assert dart.is_projectile is True

    start_attack(state.fighter1, dart)
    for _ in range(dart.startup + 1):
        state = step(state, Action.SPECIAL_NEUTRAL, Action.IDLE)

    assert len(state.projectiles) == 1
    proj = state.projectiles[0]
    assert proj.owner == 1
    assert proj.vx > 0  # flying right toward Steel

    # Advance projectile toward Steel while Steel activates Reflector
    reflector = get_move("Steel", Action.SPECIAL_BACK)
    start_attack(state.fighter2, reflector)

    for _ in range(15):
        state = step(state, Action.IDLE, Action.SPECIAL_BACK)

    # Projectile was reflected!
    assert len(state.projectiles) >= 1
    reflected_proj = state.projectiles[0]
    assert reflected_proj.reflected is True
    assert reflected_proj.owner == 2  # now owned by Steel!
    assert reflected_proj.vx < 0      # flying back left toward Shadow!


def test_shadow_step_teleports_behind_enemy():
    """Shadow Step (SPECIAL_FORWARD) teleports Shadow through the opponent to the other side."""
    state = make_initial_state("Shadow", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 250.0

    # Execute Shadow Step
    state = step(state, Action.SPECIAL_FORWARD, Action.IDLE)

    # Shadow should now be to the right of Steel (> 250.0)
    assert state.fighter1.x > state.fighter2.x
    assert state.fighter1.invulnerable_frames > 0


def test_command_grabs_beat_blocking():
    """Crimson Clinch Slam and Steel Punisher Grip beat a blocking opponent."""
    state = make_initial_state("Steel", "Crimson")
    state.fighter1.x = 200.0
    state.fighter2.x = 230.0

    grip = get_move("Steel", Action.SPECIAL_NEUTRAL)
    start_attack(state.fighter1, grip)

    # Defender holds block
    for _ in range(grip.startup + 1):
        state = step(state, Action.SPECIAL_NEUTRAL, Action.BLOCK)

    # Grab successfully connected even though defender was blocking!
    assert state.fighter2.is_thrown is True or state.fighter2.is_knocked_down is True


def test_golden_read_mechanic():
    """Golden Read predicts enemy's action; if enemy does it within 30 frames, counter is scored."""
    state = make_initial_state("Golden", "Crimson")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0

    # Golden uses Golden Read (predicts Crimson will use LIGHT)
    state.fighter2.last_action = Action.LIGHT
    read_move = get_move("Golden", Action.SPECIAL_NEUTRAL)
    start_attack(state.fighter1, read_move)
    state.fighter1.read_action = Action.LIGHT
    state.fighter1.read_frames_left = 30

    # Enemy does LIGHT
    state = step(state, Action.SPECIAL_NEUTRAL, Action.LIGHT)

    assert state.fighter1.read_success is True
    assert state.fighter1.last_hit_effect == "read"
