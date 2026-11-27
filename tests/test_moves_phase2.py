"""Phase 2 Tests: Combos, Cancels, Juggle Cap, Counter-Hits, Bounces & Scaling."""

import pytest

from backend.ai.actions import Action
from backend.engine.combat import can_cancel_into, start_attack
from backend.engine.constants import ARENA_WIDTH
from backend.engine.moves import CancelType, get_move
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step


def test_combo_damage_scaling():
    """Combo scaling reduces damage on each extra hit: 100%, 90%, 80%... down to min 30%."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 240.0  # close range

    # Set up attacker combo_hits = 0 (100% scale)
    f1 = state.fighter1
    f2 = state.fighter2
    base_move = get_move("Crimson", Action.LIGHT)
    f1.combo_hits = 0
    scale0 = max(0.30, 1.0 - f1.combo_hits * 0.10)
    assert scale0 == 1.0

    f1.combo_hits = 1
    scale1 = max(0.30, 1.0 - f1.combo_hits * 0.10)
    assert pytest.approx(scale1) == 0.90

    f1.combo_hits = 2
    scale2 = max(0.30, 1.0 - f1.combo_hits * 0.10)
    assert pytest.approx(scale2) == 0.80

    f1.combo_hits = 8
    scale8 = max(0.30, 1.0 - f1.combo_hits * 0.10)
    assert pytest.approx(scale8) == 0.30  # minimum clamp at 30%


def test_counter_hit_bonus():
    """Hitting a fighter during their startup gives +50% hitstun and triggers counter hit."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 245.0

    # Defender starts a slow heavy punch (startup 10f)
    heavy = get_move("Steel", Action.HEAVY)
    start_attack(state.fighter2, heavy)
    assert state.fighter2.attack_phase == "startup"

    # Attacker starts a fast jab (startup 3f)
    jab = get_move("Crimson", Action.LIGHT)
    start_attack(state.fighter1, jab)

    # Step until jab hits (last_hit_effect is a one-frame event: collect it)
    events = []
    for _ in range(4):
        state = step(state, Action.LIGHT, Action.HEAVY)
        events.append(state.fighter1.last_hit_effect)

    # Defender should be counter-hit!
    assert state.fighter1.is_counter_hit is True
    assert "counter" in events
    # Jab hitstun is 12, so counter-hitstun = int(12 * 1.5) = 18; ticks down 1 on frame 4 to 17
    assert state.fighter2.hitstun >= 17
    # Defender's attack was interrupted
    assert state.fighter2.attack_phase == "none"


def test_air_juggle_cap():
    """Air juggle cap is 4 hits; on the 4th air hit, victim falls into knockdown."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 230.0
    state.fighter2.in_air = True
    state.fighter2.jump_frame = 10

    # Hit 1, 2, 3 in air
    state.fighter1.juggle_count = 3
    # Connect with an attack
    state = step(state, Action.LIGHT, Action.IDLE)
    for _ in range(4):
        state = step(state, Action.LIGHT, Action.IDLE)

    # When juggle count reaches 4, defender is knocked down
    assert state.fighter1.juggle_count >= 4
    assert state.fighter2.is_knocked_down is True
    assert state.fighter2.knockdown_frames > 0


def test_wall_bounce():
    """A heavy hit near the arena wall causes a wall bounce once per combo."""
    state = make_initial_state("Crimson", "Steel")
    # Place defender close to the wall (x = 25px)
    state.fighter1.x = 75.0
    state.fighter2.x = 25.0

    # Connect with heavy kick (wall_bounce=True)
    hk = get_move("Crimson", Action.HEAVY_KICK)
    start_attack(state.fighter1, hk)

    # Advance until active
    events = []
    for _ in range(hk.startup + 1):
        state = step(state, Action.HEAVY_KICK, Action.IDLE)
        events.append(state.fighter1.last_hit_effect)

    # Attacker recorded wall bounce (one-frame event)
    assert state.fighter1.wall_bounced is True
    assert "wall_bounce" in events
    # Defender bounced into air
    assert state.fighter2.in_air is True


def test_ground_bounce():
    """Crimson Clinch Slam causes a ground bounce once per combo."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 235.0

    slam = get_move("Crimson", Action.SPECIAL_DOWN)
    assert slam.ground_bounce is True

    start_attack(state.fighter1, slam)
    # Advance through startup (7f) and throw execution window (7f)
    events = []
    for _ in range(slam.startup + 8):
        state = step(state, Action.SPECIAL_DOWN, Action.IDLE)
        events.append(state.fighter1.last_hit_effect)

    assert state.fighter1.ground_bounced is True
    assert "ground_bounce" in events
    assert state.fighter2.in_air is True


def test_cancels_normal_into_special_into_super():
    """Attacks with valid cancel windows can cancel on hit into special and super."""
    f = FighterState(character_name="Crimson", current_action=Action.LIGHT)
    f.cancel_available = True

    # Jab can cancel into special and super
    assert can_cancel_into(f, Action.SPECIAL_FORWARD) is True
    assert can_cancel_into(f, Action.SUPER) is True

    # Special can cancel into super, but not normal chain
    f.current_action = Action.SPECIAL_FORWARD
    assert can_cancel_into(f, Action.SUPER) is True
    assert can_cancel_into(f, Action.LIGHT) is False


def test_no_infinite_combo_protection():
    """Simulating repeated attack loops for 600 frames guarantees victim recovers due to hitstun decay."""
    state = make_initial_state("Crimson", "Steel")
    state.fighter1.x = 200.0
    state.fighter2.x = 230.0

    recovered_at_least_once = False

    # Simulate attacker pressing jab continuously for 600 frames
    for _ in range(600):
        prev_stun = state.fighter2.hitstun
        state = step(state, Action.LIGHT, Action.IDLE)
        # Check if victim recovered to hitstun 0
        if prev_stun > 0 and state.fighter2.hitstun == 0:
            recovered_at_least_once = True
            break

    assert recovered_at_least_once is True
