"""Regression tests for the engine review fixes (one block per review item)."""

import dataclasses

import pytest

from backend.ai.actions import Action
from backend.engine.combat import start_attack
from backend.engine.constants import (
    ARENA_WIDTH,
    DASH_FRAMES,
    GOLDEN_READ_DAMAGE_MULT,
    GOLDEN_RUSH_DAMAGE_MULT,
    PARRY_LOCKOUT_FRAMES,
    POST_STUN_THROW_INVULN_FRAMES,
    SUPER_FREEZE_FRAMES,
    WALK_SPEED,
)
from backend.engine.moves import HitLevel, get_move
from backend.engine.state import FighterState, FightState, ProjectileState
from backend.engine.step import make_initial_state, new_round, step

CHARACTERS = ("Golden", "Crimson", "Steel", "Shadow")
GROUND_NORMALS = (
    Action.LIGHT, Action.HEAVY, Action.LIGHT_KICK, Action.HEAVY_KICK, Action.LOW_SWEEP,
    Action.OVERHEAD, Action.CROUCH_JAB, Action.CROUCH_KICK, Action.ANTI_AIR,
)


def _close(c1="Golden", c2="Golden", x1=300.0, x2=340.0):
    s = make_initial_state(c1, c2)
    s.fighter1.x, s.fighter2.x = x1, x2
    return s


def _run(s, a1, a2, frames):
    """Step `frames` times, returning the final state and every frame's events."""
    events = []
    for _ in range(frames):
        s = step(s, a1, a2)
        events.append((s.fighter1.last_hit_effect, s.fighter2.last_hit_effect))
    return s, events


# ---------------------------------------------------------------------------
# 1. No blocking / parrying during your own startup, active or recovery
# ---------------------------------------------------------------------------

def test_cannot_block_or_parry_during_own_recovery():
    s = _close()
    f2 = s.fighter2
    f2.current_action = Action.HEAVY
    f2.attack_phase = "recovery"
    f2.attack_frames_left = 30
    f2.recovery = 30
    s = step(s, Action.LIGHT, Action.BLOCK)
    s, events = _run(s, Action.IDLE, Action.BLOCK, 4)
    p2_events = [e[1] for e in events]
    assert "hit" in p2_events
    assert "block" not in p2_events and "parry" not in p2_events
    assert s.fighter2.hitstun > 0 and s.fighter2.blockstun == 0


def test_cannot_block_during_own_startup():
    s = _close()
    start_attack(s.fighter2, get_move("Golden", Action.HEAVY))  # 10f startup
    s, events = _run(s, Action.LIGHT, Action.BLOCK, 4)
    assert s.fighter2.blockstun == 0
    assert s.fighter2.hitstun > 0
    assert "counter" in [e[0] for e in events]


# ---------------------------------------------------------------------------
# 2. Parry lockout: tapping block cannot parry everything
# ---------------------------------------------------------------------------

def test_failed_parry_starts_lockout_and_next_tap_only_blocks():
    s = _close()
    # A tap that parries nothing: lockout begins
    s = step(s, Action.IDLE, Action.BLOCK)
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.fighter2.parry_lockout > 0

    # Heavy (10f startup): fresh tap right before the hit only BLOCKS
    s = step(s, Action.HEAVY, Action.IDLE)
    s, _ = _run(s, Action.IDLE, Action.IDLE, 7)
    s, events = _run(s, Action.IDLE, Action.BLOCK, 3)
    p2 = [e[1] for e in events]
    assert "block" in p2 and "parry" not in p2


def test_parry_works_again_after_lockout_expires():
    s = _close()
    s = step(s, Action.IDLE, Action.BLOCK)
    s, _ = _run(s, Action.IDLE, Action.IDLE, PARRY_LOCKOUT_FRAMES + 2)
    assert s.fighter2.parry_lockout == 0
    s = step(s, Action.HEAVY, Action.IDLE)
    s, _ = _run(s, Action.IDLE, Action.IDLE, 7)
    s, events = _run(s, Action.IDLE, Action.BLOCK, 3)
    assert "parry" in [e[1] for e in events]
    assert s.fighter2.health == 1.0


def test_mashing_block_cannot_parry_a_string():
    """Alternating BLOCK/IDLE every frame against repeated jabs: at most one parry."""
    s = _close()
    parries = 0
    for i in range(120):
        a1 = Action.LIGHT
        a2 = Action.BLOCK if i % 2 == 0 else Action.IDLE
        s = step(s, a1, a2)
        if s.fighter2.last_hit_effect == "parry":
            parries += 1
    assert parries <= 1


# ---------------------------------------------------------------------------
# 3. Measured on-block frame advantage == MoveData.on_block
# ---------------------------------------------------------------------------

def _first_free_frame(s, who, block):
    """Frames until `who` can start a Jab (probing a forked state each frame)."""
    for k in range(120):
        a1 = Action.LIGHT if who == 1 else Action.IDLE
        a2 = Action.LIGHT if who == 2 else block
        probe = step(s, a1, a2)
        f = probe.fighter1 if who == 1 else probe.fighter2
        if f.attack_phase == "startup" and f.current_action == Action.LIGHT:
            return k
        s = step(s, Action.IDLE, block)
    raise AssertionError("fighter never became free")


def _measure_on_block(char, action):
    move = get_move(char, action)
    block = Action.BLOCK_LOW if move.hit_level == HitLevel.LOW else Action.BLOCK
    s = _close(char, "Golden")
    s.fighter1.meter = 100.0  # for metered specials / supers
    s, _ = _run(s, Action.IDLE, block, 8)   # holding block well past the parry window
    s = step(s, action, block)
    for _ in range(60):
        if s.fighter2.last_hit_effect == "block":
            break
        s = step(s, Action.IDLE, block)
    assert s.fighter2.last_hit_effect == "block", f"{char} {action.name} was not blocked"
    return _first_free_frame(s, 2, block) - _first_free_frame(s, 1, block)


@pytest.mark.parametrize("char", CHARACTERS)
@pytest.mark.parametrize("action", GROUND_NORMALS, ids=lambda a: a.name)
def test_measured_on_block_advantage_matches_move_data(char, action):
    assert _measure_on_block(char, action) == get_move(char, action).on_block


def _strike_specials():
    from backend.engine.moves import CHARACTER_MOVES
    out = []
    for char, moves in CHARACTER_MOVES.items():
        for action, m in moves.items():
            if action in GROUND_NORMALS or m.damage <= 0 or m.is_air or m.is_projectile:
                continue
            if m.hit_level == HitLevel.THROW:
                continue
            out.append((char, action))
    return out


@pytest.mark.parametrize("char,action", _strike_specials(),
                         ids=lambda v: v if isinstance(v, str) else v.name)
def test_measured_on_block_advantage_matches_move_data_for_specials(char, action):
    assert _measure_on_block(char, action) == get_move(char, action).on_block


# ---------------------------------------------------------------------------
# 4. Shadow Step cannot be used in the air (no infinite air teleport)
# ---------------------------------------------------------------------------

def test_shadow_step_does_nothing_in_the_air():
    s = make_initial_state("Shadow", "Steel")
    s.fighter1.x, s.fighter2.x = 200.0, 600.0
    s = step(s, Action.JUMP, Action.IDLE)
    x0 = s.fighter1.x
    s, _ = _run(s, Action.SPECIAL_FORWARD, Action.IDLE, 10)
    assert s.fighter1.in_air
    assert s.fighter1.x == pytest.approx(x0)


def test_shadow_step_still_works_on_the_ground():
    s = make_initial_state("Shadow", "Steel")
    s.fighter1.x, s.fighter2.x = 200.0, 250.0
    s = step(s, Action.SPECIAL_FORWARD, Action.IDLE)
    assert s.fighter1.x > s.fighter2.x


# ---------------------------------------------------------------------------
# 5. Vertical axis: lows vs jumpers, high attacks vs crouchers, anti-air, projectiles
# ---------------------------------------------------------------------------

def test_low_sweep_misses_airborne_fighter():
    s = _close()
    s.fighter2.in_air = True
    s.fighter2.jump_frame = 12
    s, _ = _run(s, Action.LOW_SWEEP, Action.IDLE, 9)
    assert s.fighter2.health == 1.0


def test_heavy_kick_whiffs_on_crouchers_but_hits_standing():
    hk = get_move("Golden", Action.HEAVY_KICK)
    crouch = _close()
    crouch, _ = _run(crouch, Action.HEAVY_KICK, Action.CROUCH, hk.startup + 1)
    assert crouch.fighter2.health == 1.0
    stand = _close()
    stand, _ = _run(stand, Action.HEAVY_KICK, Action.IDLE, hk.startup + 1)
    assert stand.fighter2.health < 1.0


def test_anti_air_beats_jump_attack_trade():
    s = _close()
    s.fighter1.in_air = True
    s.fighter1.jump_frame = 14
    start_attack(s.fighter1, get_move("Golden", Action.JUMP_PUNCH))
    start_attack(s.fighter2, get_move("Golden", Action.ANTI_AIR))
    s, _ = _run(s, Action.IDLE, Action.IDLE, 8)
    assert s.fighter2.health == 1.0       # the jump-in never landed
    assert s.fighter1.health < 1.0        # the anti-air did


def test_projectile_can_be_jumped_over():
    s = make_initial_state("Shadow", "Golden")
    s.fighter1.x, s.fighter2.x = 200.0, 420.0
    s.projectiles.append(ProjectileState(x=330.0, y=0.0, vx=12.0, owner=1, lifetime=60,
                                         damage=0.05, reach=30.0))
    s.fighter2.in_air = True
    s.fighter2.jump_frame = 12   # well above the dart (35..65 px)
    s, _ = _run(s, Action.IDLE, Action.IDLE, 14)
    assert s.fighter2.health == 1.0


def test_fighter_height_follows_parabolic_arc():
    f = FighterState(in_air=True)
    heights = []
    for jf in range(1, 40):
        f.jump_frame = jf
        heights.append(f.y)
    apex = heights.index(max(heights))
    assert 15 <= apex <= 22
    assert heights[0] < heights[10] < heights[apex]
    assert FighterState().y == 0.0


# ---------------------------------------------------------------------------
# 6. Projectiles: current-frame guard, guard break, knocked-down targets
# ---------------------------------------------------------------------------

def _dart_state():
    s = make_initial_state("Shadow", "Golden")
    s.fighter1.x, s.fighter2.x = 200.0, 400.0
    s.projectiles.append(ProjectileState(x=385.0, y=0.0, vx=12.0, owner=1, lifetime=60,
                                         damage=0.05, reach=30.0))
    return s


def test_projectile_block_uses_current_frame_input():
    s = _dart_state()
    s.fighter2.block_held_frames = 10
    s.fighter2.last_action = Action.BLOCK   # was blocking last frame...
    s = step(s, Action.IDLE, Action.IDLE)   # ...but lets go on the impact frame
    assert s.fighter2.last_hit_effect == "hit"
    assert s.fighter2.hitstun > 0


def test_projectile_can_guard_break():
    s = _dart_state()
    s.fighter2.block_held_frames = 10
    s.fighter2.guard_meter = 5.0
    s = step(s, Action.IDLE, Action.BLOCK)
    assert s.fighter2.last_hit_effect == "guard_break"
    assert s.fighter2.guard_break_stun > 0


def test_projectile_ignores_knocked_down_fighter():
    s = _dart_state()
    s.fighter2.is_knocked_down = True
    s.fighter2.knockdown_frames = 20
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.fighter2.health == 1.0


# ---------------------------------------------------------------------------
# 7. Super freeze: reset on new round, inputs buffered
# ---------------------------------------------------------------------------

def test_new_round_resets_super_freeze():
    s = make_initial_state()
    s.super_freeze_frames = 9
    s.super_attacker = 1
    s.round_over = True
    s2 = new_round(s)
    assert s2.super_freeze_frames == 0
    assert s2.super_attacker == 0


def test_input_pressed_during_super_freeze_is_buffered():
    s = make_initial_state("Crimson", "Golden")
    s.fighter1.meter = 100.0
    s = step(s, Action.SUPER, Action.IDLE)
    assert s.super_freeze_frames == SUPER_FREEZE_FRAMES
    s = step(s, Action.IDLE, Action.JUMP)      # pressed during the freeze
    s, _ = _run(s, Action.IDLE, Action.IDLE, SUPER_FREEZE_FRAMES - 1)
    assert s.super_freeze_frames == 0
    assert not s.fighter2.in_air
    s = step(s, Action.IDLE, Action.IDLE)      # first frame after: buffered JUMP applies
    assert s.fighter2.in_air


# ---------------------------------------------------------------------------
# 8. Throw ground bounce is decided at grab time
# ---------------------------------------------------------------------------

def test_throw_ground_bounce_uses_throw_type_from_grab_time():
    s = _close("Crimson", "Steel", 200.0, 235.0)
    slam = get_move("Crimson", Action.SPECIAL_DOWN)
    start_attack(s.fighter1, slam)
    for _ in range(slam.startup):
        s = step(s, Action.IDLE, Action.IDLE)
    assert s.fighter2.is_thrown
    # The attacker's current action changes before the throw lands
    s.fighter1.current_action = Action.IDLE
    s.fighter1.attack_phase = "none"
    s, events = _run(s, Action.IDLE, Action.IDLE, 8)
    assert "ground_bounce" in [e[0] for e in events]


# ---------------------------------------------------------------------------
# 9. Symmetric throws and bursts
# ---------------------------------------------------------------------------

def test_simultaneous_throws_clash_as_a_tech():
    s = _close("Golden", "Golden", 300.0, 330.0)
    s, events = _run(s, Action.THROW, Action.THROW, 4)
    assert not s.fighter1.is_thrown and not s.fighter2.is_thrown
    assert ("tech", "tech") in events
    assert s.fighter1.health == s.fighter2.health == 1.0


def test_simultaneous_bursts_are_symmetric():
    s = _close("Golden", "Golden", 350.0, 450.0)
    for f in (s.fighter1, s.fighter2):
        f.meter = 50.0
        f.hitstun = 10
    s = step(s, Action.BURST, Action.BURST)
    assert s.fighter1.last_hit_effect == s.fighter2.last_hit_effect == "burst"
    assert s.fighter1.hitstun == s.fighter2.hitstun == 0
    assert (400.0 - s.fighter1.x) == pytest.approx(s.fighter2.x - 400.0)


def test_mirrored_match_gives_mirrored_result():
    """Swapping P1/P2 (and mirroring positions) gives the mirrored outcome."""
    script = [(Action.THROW, Action.THROW), (Action.LIGHT, Action.BLOCK), (Action.IDLE, Action.LIGHT),
              (Action.HEAVY, Action.HEAVY), (Action.BURST, Action.BURST)] * 6
    a = _close("Steel", "Crimson", 380.0, 420.0)
    b = _close("Crimson", "Steel", 380.0, 420.0)
    for x, y in script:
        a = step(a, x, y)
        b = step(b, y, x)
    assert a.fighter1.health == pytest.approx(b.fighter2.health)
    assert a.fighter2.health == pytest.approx(b.fighter1.health)
    assert a.fighter1.x == pytest.approx(ARENA_WIDTH - b.fighter2.x)


# ---------------------------------------------------------------------------
# 10. Golden stance & Read, Shadow air dash
# ---------------------------------------------------------------------------

def _blocked_heavy_chip(stance):
    s = _close("Crimson", "Golden")
    s.fighter2.stance = stance
    s.fighter2.block_held_frames = 10
    s, _ = _run(s, Action.HEAVY, Action.BLOCK, 11)
    return 1.0 - s.fighter2.health, s.fighter2.guard_meter


def test_golden_guard_stance_reduces_chip_and_guard_drain():
    chip_n, guard_n = _blocked_heavy_chip("neutral")
    chip_g, guard_g = _blocked_heavy_chip("guard")
    assert 0.0 < chip_g < chip_n
    assert guard_g > guard_n


def test_golden_rush_stance_deals_more_damage():
    def dmg(stance):
        s = _close("Golden", "Steel")
        s.fighter1.stance = stance
        s, _ = _run(s, Action.HEAVY, Action.IDLE, 11)
        return 1.0 - s.fighter2.health
    assert dmg("rush") == pytest.approx(dmg("neutral") * GOLDEN_RUSH_DAMAGE_MULT)


def test_golden_stance_cycles_on_special_down():
    s = make_initial_state("Golden", "Steel")
    s = step(s, Action.SPECIAL_DOWN, Action.IDLE)
    assert s.fighter1.stance == "rush"


def test_golden_read_success_boosts_next_hit():
    s = _close("Golden", "Steel")
    s.fighter1.read_action = Action.HEAVY
    s.fighter1.read_frames_left = 30
    s = step(s, Action.IDLE, Action.HEAVY)
    assert s.fighter1.read_success and s.fighter1.last_hit_effect == "read"
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.fighter1.read_success is False  # one-frame event
    assert s.fighter1.read_bonus_frames > 0
    # Steel is in heavy startup; strip that so the counter-hit comes from the read
    s.fighter2.attack_phase = "none"
    s.fighter2.current_action = Action.IDLE
    s, events = _run(s, Action.LIGHT, Action.IDLE, 3)
    assert "counter" in [e[0] for e in events]
    jab = get_move("Golden", Action.LIGHT)
    assert 1.0 - s.fighter2.health == pytest.approx(jab.health_damage * GOLDEN_READ_DAMAGE_MULT)


def test_shadow_air_dash_moves_horizontally():
    s = make_initial_state("Shadow", "Steel")
    s.fighter1.x, s.fighter2.x = 200.0, 600.0
    s = step(s, Action.JUMP, Action.IDLE)
    x0 = s.fighter1.x
    s = step(s, Action.DASH, Action.IDLE)
    s, _ = _run(s, Action.IDLE, Action.IDLE, 6)
    assert s.fighter1.air_dash_left == 0
    assert s.fighter1.x - x0 > 50.0


# ---------------------------------------------------------------------------
# 11. Throw invulnerability, real dashes, air control
# ---------------------------------------------------------------------------

def test_no_throw_on_wakeup():
    s = _close("Golden", "Golden", 300.0, 330.0)
    s.fighter2.is_knocked_down = True
    s.fighter2.knockdown_frames = 1
    s = step(s, Action.IDLE, Action.IDLE)
    s = step(s, Action.IDLE, Action.IDLE)
    assert not s.fighter2.is_knocked_down
    s, _ = _run(s, Action.THROW, Action.IDLE, 4)
    assert not s.fighter2.is_thrown


def test_no_throw_during_or_just_after_blockstun():
    s = _close("Golden", "Golden", 300.0, 330.0)
    s.fighter2.blockstun = 3
    s, _ = _run(s, Action.THROW, Action.BLOCK, 4)
    assert not s.fighter2.is_thrown
    assert s.fighter2.throw_invuln_frames > 0 or s.fighter2.blockstun == 0
    assert POST_STUN_THROW_INVULN_FRAMES > 0


def test_forward_dash_bursts_then_decelerates():
    s = make_initial_state()
    xs = [s.fighter1.x]
    s = step(s, Action.DASH, Action.IDLE)
    xs.append(s.fighter1.x)
    for _ in range(DASH_FRAMES):
        s = step(s, Action.IDLE, Action.IDLE)
        xs.append(s.fighter1.x)
    speeds = [b - a for a, b in zip(xs, xs[1:])]
    assert speeds[0] > 2 * WALK_SPEED                      # burst
    assert all(x >= y for x, y in zip(speeds, speeds[1:]))  # decel
    assert speeds[-1] == 0.0                              # dash finished
    assert 60.0 < xs[-1] - xs[0] < 140.0


def test_backdash_travels_and_keeps_four_invulnerable_frames():
    s = _close()
    s = step(s, Action.IDLE, Action.BACKDASH)
    invuln = [s.fighter2.invulnerable_frames > 0]
    for _ in range(6):
        s = step(s, Action.IDLE, Action.IDLE)
        invuln.append(s.fighter2.invulnerable_frames > 0)
    assert invuln[:4] == [True] * 4 and not any(invuln[4:])
    assert s.fighter2.x > 380.0


def test_classic_air_control_is_small():
    s = make_initial_state()
    s = step(s, Action.JUMP, Action.IDLE)
    x0 = s.fighter1.x
    s, _ = _run(s, Action.FORWARD, Action.IDLE, 10)
    drift = s.fighter1.x - x0
    assert 0.0 < drift < 10 * WALK_SPEED


# ---------------------------------------------------------------------------
# 12. One-frame events
# ---------------------------------------------------------------------------

def test_block_and_hit_are_one_frame_events():
    s = _close()
    s.fighter2.block_held_frames = 10
    s, events = _run(s, Action.LIGHT, Action.BLOCK, 6)
    p2 = [e[1] for e in events]
    assert p2.count("block") == 1
    assert p2[-1] == "none"

    s = _close()
    s = step(s, Action.LIGHT, Action.IDLE)
    s, events = _run(s, Action.IDLE, Action.IDLE, 6)
    p2 = [e[1] for e in events]
    assert p2.count("hit") == 1


def test_events_reset_at_start_of_step():
    s = make_initial_state()
    s.fighter1.last_hit_effect = "parry"
    s.fighter2.read_success = True
    s = step(s, Action.IDLE, Action.IDLE)
    assert s.fighter1.last_hit_effect == "none"
    assert s.fighter2.read_success is False


def test_utility_moves_do_not_hit():
    s = _close("Golden", "Steel", 300.0, 320.0)
    s, events = _run(s, Action.BACKDASH, Action.IDLE, 6)
    assert s.fighter2.health == 1.0
    assert all(e[1] == "none" for e in events)


# ---------------------------------------------------------------------------
# 13. copy() covers every field
# ---------------------------------------------------------------------------

def _differs(cls, field, value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 7
    if isinstance(value, str):
        return value + "_x"
    if isinstance(value, Action):
        return Action.SUPER if value != Action.SUPER else Action.BURST
    return value


def test_fighter_copy_covers_every_field():
    f = FighterState()
    for fld in dataclasses.fields(FighterState):
        setattr(f, fld.name, _differs(FighterState, fld.name, getattr(f, fld.name)))
    c = f.copy()
    for fld in dataclasses.fields(FighterState):
        assert getattr(c, fld.name) == getattr(f, fld.name), fld.name


def test_fight_state_copy_covers_every_field():
    s = make_initial_state()
    for fld in dataclasses.fields(FightState):
        v = getattr(s, fld.name)
        if isinstance(v, (bool, int, float, str, Action)):
            setattr(s, fld.name, _differs(FightState, fld.name, v))
    c = s.copy()
    for fld in dataclasses.fields(FightState):
        v = getattr(s, fld.name)
        if isinstance(v, (bool, int, float, str, Action)):
            assert getattr(c, fld.name) == v, fld.name
        elif isinstance(v, list):
            assert getattr(c, fld.name) is not v, fld.name
    assert c.fighter1 is not s.fighter1


def test_projectile_copy_covers_every_field():
    p = ProjectileState(x=1.0, y=2.0, vx=3.0, owner=2, lifetime=9, damage=0.1,
                        hit_level="low", reach=5.0, reflected=True, height=77.0)
    c = p.copy()
    for fld in dataclasses.fields(ProjectileState):
        assert getattr(c, fld.name) == getattr(p, fld.name), fld.name
    assert c is not p
