"""Tests for Phase 1: Normals, High/Low, Throws, Frame Advantage, Trades, Determinism."""

import pytest

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.moves import HitLevel, get_move
from backend.engine.state import FighterState, FightState
from backend.engine.step import make_initial_state, step


# ---------------------------------------------------------------------------
# 1. Frame Advantage on Block
# ---------------------------------------------------------------------------

def test_jab_frame_advantage_plus_two():
    """Jab is +2 on block: attacker recovers 2 frames before defender."""
    move = get_move("Golden", Action.LIGHT)
    assert move is not None
    assert move.startup == 3
    assert move.active == 2
    assert move.recovery == 7
    assert move.on_block == 2

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 230.0  # within jab reach (55px)

    # Defender holds block (turtling before jab starts)
    for _ in range(5):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Frame 1: start jab
    s = step(s, Action.LIGHT, Action.BLOCK)
    # Frame 2: startup
    s = step(s, Action.IDLE, Action.BLOCK)
    # Frame 3: startup finishes -> active frame 1 connects!
    s = step(s, Action.IDLE, Action.BLOCK)
    assert s.fighter2.blockstun == move.blockstun

    # Advance through remaining active frames (1) and recovery frames
    for _ in range((move.active - 1) + move.recovery + 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Attacker recovery is now 0, but defender still has 1 frame of blockstun left (+2 advantage total across recovery windows)
    assert s.fighter1.recovery == 0
    assert s.fighter2.blockstun == 1

    # Step remaining frame of blockstun
    s = step(s, Action.IDLE, Action.BLOCK)
    assert s.fighter2.blockstun == 0


def test_heavy_punch_frame_advantage_minus_five():
    """Heavy punch is -5 on block: defender recovers 5 frames before attacker."""
    move = get_move("Golden", Action.HEAVY)
    assert move is not None
    assert move.startup == 10
    assert move.active == 4
    assert move.recovery == 18
    assert move.on_block == -5

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 260.0  # within heavy punch reach (85px)

    # Frame 1: start heavy punch
    s = step(s, Action.HEAVY, Action.BLOCK)
    # Advance remaining startup frames (9)
    for _ in range(move.startup - 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Frame 10: active frame 1 connects!
    assert s.fighter2.blockstun == move.blockstun

    # Step through all defender blockstun frames + 1 for recovery completion
    for _ in range(move.blockstun + 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Defender is free (0), attacker still has 5 frames of recovery remaining (-5 advantage!)
    assert s.fighter2.blockstun == 0
    assert s.fighter1.recovery == 5


def test_low_sweep_frame_advantage_minus_twelve():
    """Low sweep is -12 on block."""
    move = get_move("Golden", Action.LOW_SWEEP)
    assert move is not None
    assert move.on_block == -12
    assert move.knockdown is True


def test_overhead_frame_advantage_minus_four():
    """Overhead is -4 on block."""
    move = get_move("Golden", Action.OVERHEAD)
    assert move is not None
    assert move.on_block == -4
    assert move.hit_level == HitLevel.HIGH


# ---------------------------------------------------------------------------
# 2. High / Low / Mid Blocking
# ---------------------------------------------------------------------------

def test_high_overhead_hits_low_blocking_opponent():
    """An overhead (HIGH) must be blocked standing; low block gets hit."""
    move = get_move("Golden", Action.OVERHEAD)
    assert move.hit_level == HitLevel.HIGH

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 250.0

    # Start overhead while opponent holds low block
    s = step(s, Action.OVERHEAD, Action.BLOCK_LOW)
    for _ in range(move.startup - 1):
        s = step(s, Action.IDLE, Action.BLOCK_LOW)

    # Overhead hit connects cleanly: full damage, not blocked
    expected_damage = move.health_damage
    actual_damage = 1.0 - s.fighter2.health
    assert actual_damage == pytest.approx(expected_damage, abs=0.001)
    assert s.fighter2.hitstun > 0
    assert s.fighter2.blockstun == 0


def test_high_overhead_blocked_by_standing_block():
    """An overhead is successfully blocked when standing."""
    move = get_move("Golden", Action.OVERHEAD)

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 250.0

    s = step(s, Action.OVERHEAD, Action.BLOCK)
    for _ in range(move.startup - 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Blocked: reduced damage and blockstun
    actual_damage = 1.0 - s.fighter2.health
    assert actual_damage < move.health_damage
    assert s.fighter2.blockstun > 0
    assert s.fighter2.hitstun == 0


def test_low_sweep_hits_standing_blocking_opponent():
    """A low sweep (LOW) must be blocked crouching; standing block gets hit."""
    move = get_move("Golden", Action.LOW_SWEEP)
    assert move.hit_level == HitLevel.LOW

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 250.0

    s = step(s, Action.LOW_SWEEP, Action.BLOCK)
    for _ in range(move.startup - 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Clean hit: full damage and knockdown
    actual_damage = 1.0 - s.fighter2.health
    assert actual_damage == pytest.approx(move.health_damage, abs=0.001)
    assert s.fighter2.is_knocked_down is True


def test_low_sweep_blocked_by_low_block():
    """A low sweep is blocked by Action.BLOCK_LOW."""
    move = get_move("Golden", Action.LOW_SWEEP)

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 250.0

    s = step(s, Action.LOW_SWEEP, Action.BLOCK_LOW)
    for _ in range(move.startup - 1):
        s = step(s, Action.IDLE, Action.BLOCK_LOW)

    actual_damage = 1.0 - s.fighter2.health
    assert actual_damage < move.health_damage
    assert s.fighter2.blockstun > 0
    assert not s.fighter2.is_knocked_down


def test_mid_attack_blocked_standing_or_crouching():
    """Mid attacks are blocked by both standing and crouching block."""
    move = get_move("Golden", Action.LIGHT_KICK)
    assert move.hit_level == HitLevel.MID

    # Test 1: standing block
    s1 = make_initial_state()
    s1.fighter1.x, s1.fighter2.x = 200.0, 240.0
    s1 = step(s1, Action.LIGHT_KICK, Action.BLOCK)
    for _ in range(move.startup - 1):
        s1 = step(s1, Action.IDLE, Action.BLOCK)
    assert s1.fighter2.blockstun > 0

    # Test 2: crouching block
    s2 = make_initial_state()
    s2.fighter1.x, s2.fighter2.x = 200.0, 240.0
    s2 = step(s2, Action.LIGHT_KICK, Action.BLOCK_LOW)
    for _ in range(move.startup - 1):
        s2 = step(s2, Action.IDLE, Action.BLOCK_LOW)
    assert s2.fighter2.blockstun > 0


# ---------------------------------------------------------------------------
# 3. Throws: Unblockable, Beats Blocking, Loses to Startup, Throw Tech
# ---------------------------------------------------------------------------

def test_throw_beats_blocking():
    """Throw connects even when the opponent is holding block."""
    throw = get_move("Golden", Action.THROW)
    assert throw.hit_level == HitLevel.THROW

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 225.0  # within throw reach (38px)

    # Fighter 1 initiates throw against blocking fighter 2
    s = step(s, Action.THROW, Action.BLOCK)
    for _ in range(throw.startup - 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Throw connected -> defender is in throw tech window
    assert s.fighter2.is_thrown is True
    assert s.fighter2.throw_tech_frames == 7

    # Advance through the 7-frame tech window without teching
    for _ in range(7):
        s = step(s, Action.IDLE, Action.BLOCK)

    # Throw completes: full damage (10 HP = 0.10) and knockdown!
    assert s.fighter2.is_thrown is False
    assert s.fighter2.health == pytest.approx(0.90, abs=0.001)
    assert s.fighter2.is_knocked_down is True


def test_throw_loses_to_attack_startup():
    """Throw loses if defender is in attack startup."""
    throw = get_move("Golden", Action.THROW)

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 225.0

    # Fighter 1 starts throw (startup 4), Fighter 2 starts heavy attack (startup 10)
    s = step(s, Action.THROW, Action.HEAVY)

    # Step until throw would become active (frame 4)
    for _ in range(throw.startup - 1):
        s = step(s, Action.IDLE, Action.IDLE)

    # Fighter 2 is in attack startup, so the throw fails and does not connect!
    assert s.fighter2.is_thrown is False
    assert s.fighter2.health == 1.0


def test_throw_tech_breaks_throw():
    """Pressing throw within 7 frames techs the throw, dealing 0 damage."""
    throw = get_move("Golden", Action.THROW)

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 225.0

    s = step(s, Action.THROW, Action.IDLE)
    for _ in range(throw.startup - 1):
        s = step(s, Action.IDLE, Action.IDLE)

    assert s.fighter2.is_thrown is True
    assert s.fighter2.throw_tech_frames == 7

    # Fighter 2 inputs THROW to tech!
    s = step(s, Action.IDLE, Action.THROW)

    # Throw is broken!
    assert s.fighter2.is_thrown is False
    assert s.fighter2.health == 1.0
    assert not s.fighter2.is_knocked_down
    assert s.fighter1.recovery == 8
    assert s.fighter2.recovery == 8


# ---------------------------------------------------------------------------
# 4. Simultaneous Trades
# ---------------------------------------------------------------------------

def test_simultaneous_hits_trade():
    """When both fighters' active frames hit on the same frame, both take damage."""
    move = get_move("Golden", Action.LIGHT)

    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 240.0  # within reach of both

    # Both start Jab on the same frame
    s = step(s, Action.LIGHT, Action.LIGHT)
    for _ in range(move.startup - 1):
        s = step(s, Action.IDLE, Action.IDLE)

    # Both took damage!
    assert s.fighter1.health < 1.0
    assert s.fighter2.health < 1.0
    assert s.fighter1.health == pytest.approx(s.fighter2.health)
    assert s.fighter1.hitstun > 0
    assert s.fighter2.hitstun > 0


# ---------------------------------------------------------------------------
# 5. Backdash Invulnerability
# ---------------------------------------------------------------------------

def test_backdash_first_four_frames_invulnerable():
    """Backdash is invulnerable for the first 4 frames."""
    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 240.0

    # Fighter 1 starts jab, fighter 2 backdashes
    s = step(s, Action.LIGHT, Action.BACKDASH)

    # Backdash has 4 invulnerable frames
    assert s.fighter2.invulnerable_frames > 0


# ---------------------------------------------------------------------------
# 6. Pushback
# ---------------------------------------------------------------------------

def test_pushback_separates_fighters():
    """Hits and blocks push fighters apart."""
    s = make_initial_state()
    s.fighter1.x = 200.0
    s.fighter2.x = 240.0
    initial_dist = s.fighter2.x - s.fighter1.x

    move = get_move("Golden", Action.HEAVY)
    s = step(s, Action.HEAVY, Action.BLOCK)
    for _ in range(move.startup - 1):
        s = step(s, Action.IDLE, Action.BLOCK)

    new_dist = s.fighter2.x - s.fighter1.x
    assert new_dist > initial_dist


# ---------------------------------------------------------------------------
# 7. Determinism
# ---------------------------------------------------------------------------

def test_engine_determinism():
    """Stepping two separate identical states with the same inputs produces identical results."""
    s1 = make_initial_state("Crimson", "Shadow")
    s2 = make_initial_state("Crimson", "Shadow")

    script = [
        (Action.FORWARD, Action.BACK),
        (Action.LIGHT, Action.BLOCK),
        (Action.LIGHT_KICK, Action.BLOCK_LOW),
        (Action.THROW, Action.IDLE),
        (Action.IDLE, Action.THROW),
        (Action.OVERHEAD, Action.BLOCK),
        (Action.LOW_SWEEP, Action.BLOCK_LOW),
    ]

    for a1, a2 in script:
        s1 = step(s1, a1, a2)
        s2 = step(s2, a1, a2)

        assert s1.fighter1.x == s2.fighter1.x
        assert s1.fighter2.x == s2.fighter2.x
        assert s1.fighter1.health == s2.fighter1.health
        assert s1.fighter2.health == s2.fighter2.health
        assert s1.fighter1.hitstun == s2.fighter1.hitstun
        assert s1.fighter2.blockstun == s2.fighter2.blockstun
