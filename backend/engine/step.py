"""The single-frame update: step(state, action1, action2) -> new state.

Advances physics, timers, throws, attacks, projectiles, cancels, hit/block resolution,
meters, combos, and win conditions.
Pure function: never changes the input state.

Frame order (see docs/engine.md, "Step order"):
  1. clear one-frame events; super freeze (inputs are buffered)
  2. tick strike invulnerability; mode systems (rumble / shield wall)
  3. advance attacks that were already in progress
  4. read inputs: bursts, throw techs, jumps, movement/dashes, new attacks
  5. projectiles, then melee hits (simultaneous), pushboxes, walls
  6. Golden Read check
  7. tick timers (a stun set this frame is NOT ticked this frame)
  8. record actions, advance the clock, check round end
This ordering makes measured frame advantage on block equal MoveData.on_block.
"""

from backend.ai.actions import ATTACKS, Action
from backend.engine.characters import CHARACTER_STATS, walk_speed
from backend.engine.combat import (
    advance_attack,
    apply_damage,
    check_hit,
    hurtbox_range,
    is_busy_with_own_move,
    is_guarding,
    ranges_overlap,
    start_attack,
)
from backend.engine.constants import (
    ARENA_EDGE_MARGIN,
    ARENA_WIDTH,
    BURST_METER_COST,
    BURST_PUSHBACK,
    BURST_STAGGER_FRAMES,
    COMBO_SCALING_MIN,
    COMBO_SCALING_STEP,
    COUNTER_HIT_BONUS_METER,
    COUNTER_HITSTUN_MULT,
    COUNTER_STANCE_DAMAGE,
    COUNTER_STANCE_HITSTUN,
    COUNTER_STANCE_PUSHBACK,
    COUNTER_STANCE_SUPER_DAMAGE,
    FURY_DAMAGE_MULT,
    GOLDEN_EVADE_SPEED_MULT,
    GOLDEN_GUARD_CHIP_MULT,
    GOLDEN_GUARD_DRAIN_MULT,
    GOLDEN_READ_BONUS_FRAMES,
    GOLDEN_READ_DAMAGE_MULT,
    GOLDEN_READ_WINDOW,
    GOLDEN_RUSH_DAMAGE_MULT,
    GROUND_BOUNCE_HITSTUN,
    GUARD_AFTER_BREAK,
    GUARD_BREAK_STUN_FRAMES,
    GUARD_DRAIN_PER_BLOCK,
    GUARD_METER_MAX,
    GUARD_REGEN_PER_FRAME,
    HITSTUN_DECAY_PER_HIT,
    JUGGLE_CAP,
    KNOCKDOWN_FRAMES,
    METER_GAIN_WHEN_BLOCKING,
    METER_GAIN_WHEN_HIT,
    METER_MAX,
    MIN_HITSTUN,
    PARRY_LOCKOUT_FRAMES,
    PARRY_METER_GAIN,
    PARRY_STAGGER_FRAMES,
    PARRY_WINDOW_FRAMES,
    POST_STUN_THROW_INVULN_FRAMES,
    PROJECTILE_BLOCKSTUN,
    PROJECTILE_GUARD_DRAIN,
    PROJECTILE_HALF_HEIGHT,
    PROJECTILE_HITSTUN,
    PROJECTILE_METER_GAIN_HIT,
    PROJECTILE_REACH,
    PROJECTILE_SPAWN_OFFSET,
    REFLECTED_LIFETIME,
    REFLECTOR_RADIUS,
    REGEN_DELAY_FRAMES,
    REGEN_RATE_PER_FRAME,
    ROUND_FRAMES,
    RUMBLE_AIR_SPEED_MULT,
    AIR_CONTROL_SPEED_MULT,
    SHADOW_STEP_BEHIND_OFFSET,
    SHADOW_STEP_FAR_DISTANCE,
    SHADOW_STEP_INVULN,
    SHADOW_STEP_SLIP_RANGE,
    SHIELD_THROW_EXTRA_REACH,
    SUPER_FREEZE_FRAMES,
    THROW_GROUND_BOUNCE_HITSTUN,
    THROW_LAND_PUSHBACK,
    THROW_METER_GAIN,
    THROW_TECH_PUSHBACK,
    THROW_TECH_RECOVERY,
    THROW_TECH_WINDOW,
    WAKEUP_INVULN_FRAMES,
    WAKEUP_THROW_INVULN_FRAMES,
    WALL_BOUNCE_DISTANCE,
    WALL_BOUNCE_HITSTUN,
    WALL_BOUNCE_MIN_DAMAGE,
)
from backend.engine.moves import HitLevel, MoveData, get_move
from backend.engine.physics import (
    apply_air_control,
    apply_dash_motion,
    apply_jump,
    apply_movement,
    apply_pushback,
    start_backdash,
    stop_dash,
)
from backend.engine.projectile_rules import can_fire_projectile, register_shot
from backend.engine.pushbox import resolve_pushboxes
from backend.engine.rules import ModeRules
from backend.engine.rumble import (
    apply_rumble_attack_vs_objects,
    apply_rumble_projectile_collisions,
    apply_rumble_wall_collisions,
    init_rumble_arena_objects,
    init_rumble_zone,
    update_kill_feed,
    update_rumble_arena_objects,
    update_rumble_building,
    update_rumble_loot,
    update_rumble_zone,
)
from backend.engine.rumble_config import (
    BUILD_START_CHARGES,
    RUMBLE_ROUND_FRAMES,
    SPEED_BOOTS_MULTIPLIER,
)
from backend.engine.shield_wall import (
    apply_shield_attack_drain,
    apply_shield_wall_collisions,
    check_shield_wall_intercept,
    check_shield_wall_projectiles,
    update_shield_walls,
)
from backend.engine.state import FighterState, FightState, ProjectileState

BLOCK_ACTIONS = (Action.BLOCK, Action.BLOCK_LOW)

# Timers that count down once per frame at the END of the frame. A timer that
# was changed during this frame (e.g. blockstun set by a hit) is not ticked
# until the next frame, so "blockstun = N" means N full frames after the hit.
_FRAME_TIMERS = (
    "cooldown",
    "recovery",
    "hitstun",
    "blockstun",
    "guard_break_stun",
    "read_frames_left",
    "read_bonus_frames",
    "projectile_cooldown",
    "parry_lockout",
    "throw_invuln_frames",
    "knockdown_frames",
)


def step(state: FightState, action1: Action, action2: Action) -> FightState:
    """Advance the fight by one frame.

    Takes the current state and both players' chosen actions.
    Returns a completely new FightState (the old one is not touched).
    """
    if state.round_over or state.match_over:
        return state

    new = state.copy()
    f1 = new.fighter1
    f2 = new.fighter2

    _clear_frame_events(f1)
    _clear_frame_events(f2)

    # Super freeze: the world pauses, but inputs are buffered (not dropped)
    if new.super_freeze_frames > 0:
        _buffer_freeze_inputs(new, action1, action2)
        new.super_freeze_frames -= 1
        new.frame += 1
        return new
    action1, action2 = _consume_freeze_buffer(new, action1, action2)

    stats1 = CHARACTER_STATS.get(f1.character_name, CHARACTER_STATS["Golden"])
    stats2 = CHARACTER_STATS.get(f2.character_name, CHARACTER_STATS["Golden"])
    snap1 = _snapshot_timers(f1)
    snap2 = _snapshot_timers(f2)

    # --- Start of frame ---
    _start_of_frame_status(f1)
    _start_of_frame_status(f2)
    _update_mode_systems(new, action1, action2)
    _reset_combo_if_neutral(f1, f2)
    _reset_combo_if_neutral(f2, f1)

    # Attacks already in progress advance BEFORE inputs are read, so a move
    # whose recovery ends this frame lets the fighter act on this same frame.
    _advance_current_attack(f1)
    _advance_current_attack(f2)

    # --- Inputs ---
    _resolve_bursts(f1, f2, action1, action2)
    _resolve_throw_state(f1, f2, action1)
    _resolve_throw_state(f2, f1, action2)
    _movement_phase(new, action1, action2, stats1, stats2)
    _start_action_and_first_frame(f1, action1, new, 1, f2, stats1)
    _start_action_and_first_frame(f2, action2, new, 2, f1, stats2)
    _track_block_input(f1, action1)
    _track_block_input(f2, action2)

    # --- Hits ---
    move1 = get_move(f1.character_name, f1.current_action)
    move2 = get_move(f2.character_name, f2.current_action)
    _spawn_projectile(f1, move1, new, 1, f2.x)
    _spawn_projectile(f2, move2, new, 2, f1.x)
    _projectile_phase(new, action1, action2, stats1, stats2)
    _melee_phase(new, move1, move2, action1, action2, stats1, stats2)
    _post_hit_collisions(new, move1, move2, action1, action2)

    _check_golden_read(f1, action2)
    _check_golden_read(f2, action1)

    # --- End of frame ---
    _tick_timers(f1, action1, snap1)
    _tick_timers(f2, action2, snap2)
    f1.last_action = action1
    f2.last_action = action2
    new.frame += 1
    new.round_frames_left -= 1
    _check_round_end(new)
    return new


# ---------------------------------------------------------------
# Frame bookkeeping
# ---------------------------------------------------------------

def _clear_frame_events(fighter: FighterState) -> None:
    """last_hit_effect and read_success are one-frame events."""
    fighter.last_hit_effect = "none"
    fighter.read_success = False


def _buffer_freeze_inputs(state: FightState, action1: Action, action2: Action) -> None:
    if action1 != Action.IDLE:
        state.buffered_action1 = action1
    if action2 != Action.IDLE:
        state.buffered_action2 = action2


def _consume_freeze_buffer(state: FightState, action1: Action,
                           action2: Action) -> tuple[Action, Action]:
    """On the first frame after a freeze, a buffered input replaces an idle one."""
    if action1 == Action.IDLE:
        action1 = state.buffered_action1
    if action2 == Action.IDLE:
        action2 = state.buffered_action2
    state.buffered_action1 = Action.IDLE
    state.buffered_action2 = Action.IDLE
    return action1, action2


def _snapshot_timers(fighter: FighterState) -> tuple:
    return tuple(getattr(fighter, name) for name in _FRAME_TIMERS)


def _start_of_frame_status(fighter: FighterState) -> None:
    """Strike invulnerability counts the frame it was granted (ticked at frame start).

    Wakeup also happens here, so wakeup invulnerability covers the first
    WAKEUP_INVULN_FRAMES frames the fighter is standing.
    """
    if fighter.invulnerable_frames > 0:
        fighter.invulnerable_frames -= 1
    if fighter.is_knocked_down and fighter.knockdown_frames <= 0:
        fighter.is_knocked_down = False
        fighter.invulnerable_frames = WAKEUP_INVULN_FRAMES
        fighter.throw_invuln_frames = WAKEUP_THROW_INVULN_FRAMES


def _tick_timers(fighter: FighterState, action: Action, snapshot: tuple) -> None:
    """Count down frame timers that were not changed during this frame."""
    was_stunned = fighter.hitstun > 0 or fighter.blockstun > 0
    for name, before in zip(_FRAME_TIMERS, snapshot):
        value = getattr(fighter, name)
        if value > 0 and value == before:
            setattr(fighter, name, value - 1)

    # Leaving hitstun / blockstun grants a few frames of throw invulnerability
    if was_stunned and fighter.hitstun <= 0 and fighter.blockstun <= 0:
        fighter.throw_invuln_frames = max(fighter.throw_invuln_frames,
                                          POST_STUN_THROW_INVULN_FRAMES)

    # Refill guard meter when not blocking
    if action not in BLOCK_ACTIONS and fighter.guard_break_stun <= 0:
        fighter.guard_meter = min(GUARD_METER_MAX, fighter.guard_meter + GUARD_REGEN_PER_FRAME)

    _regenerate_health(fighter, action)


def _regenerate_health(fighter: FighterState, action: Action) -> None:
    """Health regeneration (only if enabled, e.g. for a human in Campaign / Human vs AI)."""
    fighter.no_hit_timer += 1
    if (fighter.regen_enabled and fighter.health < 1.0
            and not fighter.is_knocked_down and not fighter.is_thrown):
        is_blocking = action in BLOCK_ACTIONS or fighter.blockstun > 0
        if fighter.no_hit_timer >= REGEN_DELAY_FRAMES or is_blocking:
            fighter.health = min(1.0, fighter.health + REGEN_RATE_PER_FRAME)


def _update_mode_systems(state: FightState, action1: Action, action2: Action) -> None:
    """Rumble (zone, building, loot, arena objects) and Shield Wall upkeep."""
    if state.rules.is_rumble:
        update_rumble_zone(state)
        update_rumble_building(state, action1, action2)
        update_rumble_loot(state, action1, action2)
        update_rumble_arena_objects(state)
        update_kill_feed(state)
    if state.rules.enable_shield_wall:
        update_shield_walls(state, action1, action2)
        if not state.rules.is_rumble:
            update_kill_feed(state)


def _reset_combo_if_neutral(attacker: FighterState, defender: FighterState) -> None:
    """Reset the attacker's combo counters once the defender is back to neutral."""
    if defender.hitstun <= 0 and not defender.in_air and not defender.is_knocked_down and not defender.is_thrown:
        attacker.combo_hits = 0
        attacker.combo_damage = 0.0
        attacker.juggle_count = 0
        attacker.wall_bounced = False
        attacker.ground_bounced = False
        attacker.is_counter_hit = False


def _advance_current_attack(fighter: FighterState) -> None:
    advance_attack(fighter, get_move(fighter.character_name, fighter.current_action))


def _gain_meter(fighter: FighterState, amount: float) -> None:
    fighter.meter = min(METER_MAX, fighter.meter + amount)


def _interrupt_attack(fighter: FighterState) -> None:
    """Cancel whatever move the fighter was doing."""
    fighter.attack_phase = "none"
    fighter.attack_frames_left = 0
    fighter.current_action = Action.IDLE
    fighter.cancel_available = False


# ---------------------------------------------------------------
# Bursts and throws (resolved symmetrically)
# ---------------------------------------------------------------

def _can_burst(fighter: FighterState, action: Action) -> bool:
    return (action == Action.BURST and fighter.hitstun > 0
            and fighter.meter >= BURST_METER_COST and not fighter.burst_used_this_round)


def _resolve_bursts(f1: FighterState, f2: FighterState,
                    action1: Action, action2: Action) -> None:
    """Spend meter to burst out of a combo once per round.

    Both conditions are read before either burst applies, so P1 and P2 are
    treated the same. If both burst on the same frame they cancel out: both
    escape and are pushed apart evenly, nobody is staggered.
    """
    b1 = _can_burst(f1, action1)
    b2 = _can_burst(f2, action2)
    if b1 and b2:
        for f in (f1, f2):
            _spend_burst(f)
        left, right = (f1, f2) if f1.x <= f2.x else (f2, f1)
        left.x = max(0.0, left.x - BURST_PUSHBACK / 2.0)
        right.x = min(float(ARENA_WIDTH), right.x + BURST_PUSHBACK / 2.0)
        return
    if b1:
        _apply_burst(f1, f2)
    elif b2:
        _apply_burst(f2, f1)


def _spend_burst(victim: FighterState) -> None:
    victim.meter -= BURST_METER_COST
    victim.burst_used_this_round = True
    victim.hitstun = 0
    victim.last_hit_effect = "burst"


def _apply_burst(victim: FighterState, attacker: FighterState) -> None:
    _spend_burst(victim)
    apply_pushback(victim, attacker, BURST_PUSHBACK, ARENA_WIDTH)
    attacker.recovery = BURST_STAGGER_FRAMES
    _interrupt_attack(attacker)
    attacker.combo_hits = 0
    attacker.combo_damage = 0.0


def _resolve_throw_state(victim: FighterState, attacker: FighterState,
                         victim_action: Action) -> None:
    """Handle throw escape / execution during the tech window."""
    if not victim.is_thrown:
        return

    if victim.throw_tech_frames > 0 and victim_action == Action.THROW:
        _break_throw(victim, attacker)
        return

    victim.throw_tech_frames -= 1
    if victim.throw_tech_frames <= 0:
        _land_throw(victim, attacker)


def _break_throw(a: FighterState, b: FighterState) -> None:
    """Throw tech / throw clash: nobody is thrown, both recover, pushed apart."""
    for f in (a, b):
        f.is_thrown = False
        f.throw_tech_frames = 0
        f.throw_damage_pending = 0.0
        f.pending_throw_bounce = False
        f.recovery = THROW_TECH_RECOVERY
        f.attack_phase = "none"
        f.attack_frames_left = 0
        f.current_action = Action.IDLE
        f.cancel_available = False
        f.last_hit_effect = "tech"
    left, right = (a, b) if a.x <= b.x else (b, a)
    apply_pushback(left, right, THROW_TECH_PUSHBACK / 2.0, ARENA_WIDTH)
    apply_pushback(right, left, THROW_TECH_PUSHBACK / 2.0, ARENA_WIDTH)


def _land_throw(victim: FighterState, attacker: FighterState) -> None:
    apply_damage(victim, victim.throw_damage_pending, is_blocking=False,
                 blocked_damage_ratio=1.0, attacker=attacker)
    victim.is_thrown = False
    victim.throw_tech_frames = 0
    victim.throw_damage_pending = 0.0
    # The bounce was decided when the grab connected (not by what the
    # attacker happens to be doing now).
    if victim.pending_throw_bounce and not attacker.ground_bounced:
        attacker.ground_bounced = True
        victim.in_air = True
        victim.jump_frame = 1
        victim.hitstun = THROW_GROUND_BOUNCE_HITSTUN
        attacker.last_hit_effect = "ground_bounce"
    else:
        victim.is_knocked_down = True
        victim.knockdown_frames = KNOCKDOWN_FRAMES
    victim.pending_throw_bounce = False
    _gain_meter(attacker, THROW_METER_GAIN)
    apply_pushback(attacker, victim, THROW_LAND_PUSHBACK, ARENA_WIDTH)


# ---------------------------------------------------------------
# Movement
# ---------------------------------------------------------------

def _movement_speed(fighter: FighterState, stats) -> float:
    speed = walk_speed(stats) * fighter.speed_mult
    if fighter.speed_boost_timer > 0:
        speed *= SPEED_BOOTS_MULTIPLIER
    if fighter.character_name == "Golden" and fighter.stance == "evade":
        speed *= GOLDEN_EVADE_SPEED_MULT
    if fighter.building_frames > 0 or fighter.shield_break_stun > 0 or fighter.shield_startup_frames > 0:
        speed = 0.0
    return speed


def _move_fighter(state: FightState, fighter: FighterState, enemy_x: float,
                  action: Action, speed: float) -> None:
    """Jump, walk / dash, air control and dash travel for one fighter."""
    apply_jump(fighter, action, enemy_x=enemy_x)
    if action in BLOCK_ACTIONS and not fighter.in_air:
        stop_dash(fighter)
    apply_movement(fighter, action, speed, ARENA_WIDTH, enemy_x=enemy_x)
    air_mult = (RUMBLE_AIR_SPEED_MULT if (state.rules.is_rumble or state.rules.enable_shield_wall)
                else AIR_CONTROL_SPEED_MULT)
    apply_air_control(fighter, action, speed, air_mult, ARENA_WIDTH, enemy_x=enemy_x)
    apply_dash_motion(fighter, ARENA_WIDTH)


def _movement_phase(state: FightState, action1: Action, action2: Action, stats1, stats2) -> None:
    f1, f2 = state.fighter1, state.fighter2
    spd1 = _movement_speed(f1, stats1)
    spd2 = _movement_speed(f2, stats2)
    # Both fighters read the enemy position from the start of this phase.
    x1, x2 = f1.x, f2.x
    _move_fighter(state, f1, x2, action1, spd1)
    _move_fighter(state, f2, x1, action2, spd2)

    if state.rules.is_rumble:
        apply_rumble_wall_collisions(f1, f2, state.walls, state.arena_objects)
        apply_rumble_wall_collisions(f2, f1, state.walls, state.arena_objects)
    if state.rules.enable_shield_wall:
        apply_shield_wall_collisions(state)


# ---------------------------------------------------------------
# Starting actions
# ---------------------------------------------------------------

def _start_action_and_first_frame(fighter: FighterState, action: Action, state: FightState,
                                  p_id: int, enemy: FighterState, stats) -> None:
    """Start a new move from this frame's input; a new move plays its first frame now."""
    if _handle_action_start(fighter, action, state, p_id, enemy, stats):
        _advance_current_attack(fighter)


def _handle_action_start(fighter: FighterState, action: Action, state: FightState,
                         p_id: int, enemy: FighterState, stats) -> bool:
    """Try to begin a normal attack, throw, special, super or backdash. True if started."""
    if fighter.shield_break_stun > 0 or fighter.shield_startup_frames > 0:
        return False
    if action not in ATTACKS and action != Action.BACKDASH:
        return False

    move = get_move(fighter.character_name, action)
    if move is None:
        return False
    # Shooting is limited: cooldown, one shot in flight, shots per round.
    if move.is_projectile and not can_fire_projectile(fighter, state.projectiles, p_id):
        return False
    if not start_attack(fighter, move):
        return False

    if action == Action.BACKDASH:
        start_backdash(fighter, _movement_speed(fighter, stats), enemy.x)
    elif not fighter.in_air:
        stop_dash(fighter)

    if move.is_projectile:
        register_shot(fighter)
    if action in ATTACKS:
        apply_shield_attack_drain(state, fighter, p_id)
    if action == Action.SUPER:
        state.super_freeze_frames = SUPER_FREEZE_FRAMES
        state.super_attacker = p_id
    if fighter.character_name == "Shadow" and action == Action.SPECIAL_FORWARD:
        _shadow_step(fighter, enemy)
    if fighter.character_name == "Golden" and action == Action.SPECIAL_NEUTRAL:
        # Golden Read: predict the enemy's next action
        fighter.read_action = enemy.last_action if enemy.last_action != Action.IDLE else Action.LIGHT
        fighter.read_frames_left = GOLDEN_READ_WINDOW
    return True


def _shadow_step(fighter: FighterState, enemy: FighterState) -> None:
    """Shadow Step reposition (only when the ground move actually starts)."""
    direction = 1 if enemy.x >= fighter.x else -1
    if abs(enemy.x - fighter.x) <= SHADOW_STEP_SLIP_RANGE:
        target = enemy.x + direction * SHADOW_STEP_BEHIND_OFFSET   # slip behind
    else:
        target = fighter.x + direction * SHADOW_STEP_FAR_DISTANCE  # bounded step
    fighter.x = max(ARENA_EDGE_MARGIN, min(ARENA_WIDTH - ARENA_EDGE_MARGIN, target))
    fighter.invulnerable_frames = max(fighter.invulnerable_frames, SHADOW_STEP_INVULN)


def _track_block_input(fighter: FighterState, action: Action) -> None:
    """Track block presses for the parry window and the failed-parry lockout.

    A FRESH block press arms a parry for PARRY_WINDOW_FRAMES, unless the
    fighter is in parry lockout. If the window passes (or block is released)
    without a parry, the lockout starts: for PARRY_LOCKOUT_FRAMES a fresh
    press can still block, but not parry. Mashing block cannot parry everything.
    """
    pressing = action in BLOCK_ACTIONS and not is_busy_with_own_move(fighter)
    if pressing:
        fighter.block_held_frames += 1
        if fighter.block_held_frames == 1:
            fighter.parry_armed = fighter.parry_lockout <= 0
        elif fighter.parry_armed and fighter.block_held_frames > PARRY_WINDOW_FRAMES:
            _fail_parry(fighter)
    else:
        if fighter.parry_armed:
            _fail_parry(fighter)
        fighter.block_held_frames = 0


def _fail_parry(fighter: FighterState) -> None:
    fighter.parry_armed = False
    fighter.parry_lockout = PARRY_LOCKOUT_FRAMES


def _can_parry(defender: FighterState, defender_action: Action, hit_level: HitLevel) -> bool:
    return (defender_action in BLOCK_ACTIONS
            and defender.parry_armed
            and defender.block_held_frames <= PARRY_WINDOW_FRAMES
            and is_guarding(defender, defender_action, hit_level))


# ---------------------------------------------------------------
# Projectiles
# ---------------------------------------------------------------

def _spawn_projectile(fighter: FighterState, move: MoveData | None, state: FightState,
                      p_id: int, enemy_x: float) -> None:
    """Spawn a deterministic projectile (e.g. Shadow Energy Dart) on its first active frame."""
    if move is None or not move.is_projectile or fighter.attack_phase != "active" or fighter.has_hit:
        return
    fighter.has_hit = True
    direction = 1.0 if enemy_x >= fighter.x else -1.0
    state.projectiles.append(ProjectileState(
        x=fighter.x + direction * PROJECTILE_SPAWN_OFFSET,
        y=0.0,
        vx=direction * move.projectile_speed,
        owner=p_id,
        lifetime=move.projectile_lifetime,
        damage=move.health_damage,
        hit_level=move.hit_level.value,
        reach=PROJECTILE_REACH,
    ))


def _projectile_phase(state: FightState, action1: Action, action2: Action, stats1, stats2) -> None:
    if state.rules.enable_shield_wall:
        check_shield_wall_projectiles(state)
    _update_projectiles(state, action1, action2, stats1, stats2)
    if state.rules.is_rumble:
        apply_rumble_projectile_collisions(state)
    if state.rules.enable_shield_wall:
        check_shield_wall_projectiles(state)


def _projectile_reflected(p: ProjectileState, target: FighterState) -> bool:
    """Steel's Reflector turns projectiles around and takes ownership."""
    if (target.character_name == "Steel"
            and target.current_action == Action.SPECIAL_BACK
            and target.attack_phase in ("startup", "active")
            and abs(p.x - target.x) <= REFLECTOR_RADIUS):
        p.vx = -p.vx
        p.owner = 3 - p.owner
        p.reflected = True
        p.lifetime = REFLECTED_LIFETIME
        return True
    return False


def _projectile_touches(p: ProjectileState, target: FighterState) -> bool:
    if target.invulnerable_frames > 0 or target.is_knocked_down:
        return False
    if abs(p.x - target.x) > p.reach:
        return False
    vertical = (p.height - PROJECTILE_HALF_HEIGHT, p.height + PROJECTILE_HALF_HEIGHT)
    return ranges_overlap(vertical, hurtbox_range(target))


def _update_projectiles(state: FightState, action1: Action, action2: Action,
                        stats1, stats2) -> None:
    """Move projectiles and resolve their hits (same guard rules as melee)."""
    f1, f2 = state.fighter1, state.fighter2
    alive: list[ProjectileState] = []

    for p in state.projectiles:
        p.x += p.vx
        p.lifetime -= 1
        if p.lifetime <= 0 or p.x < 0 or p.x > ARENA_WIDTH:
            continue

        if p.owner == 1:
            attacker, target, target_action, target_stats = f1, f2, action2, stats2
        else:
            attacker, target, target_action, target_stats = f2, f1, action1, stats1

        if _projectile_reflected(p, target):
            alive.append(p)
            continue

        if _projectile_touches(p, target):
            _apply_projectile_hit(p, attacker, target, target_action, target_stats)
            continue  # consumed

        alive.append(p)

    state.projectiles = alive


def _apply_projectile_hit(p: ProjectileState, attacker: FighterState, target: FighterState,
                          target_action: Action, target_stats) -> None:
    level = HitLevel(p.hit_level) if p.hit_level in ("mid", "high", "low") else HitLevel.MID
    if _can_parry(target, target_action, level):
        target.last_hit_effect = "parry"
        target.parry_armed = False
        _gain_meter(target, PARRY_METER_GAIN)
        return
    if is_guarding(target, target_action, level):
        _apply_guarded_hit(attacker, target, p.damage, PROJECTILE_BLOCKSTUN,
                           PROJECTILE_GUARD_DRAIN, 0.0, 0.0, target_stats)
        return
    apply_damage(target, p.damage, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker)
    target.hitstun = max(target.hitstun, PROJECTILE_HITSTUN)
    target.recovery = 0
    _interrupt_attack(target)
    target.last_hit_effect = "hit"
    _gain_meter(attacker, PROJECTILE_METER_GAIN_HIT)
    _gain_meter(target, METER_GAIN_WHEN_HIT)


# ---------------------------------------------------------------
# Melee
# ---------------------------------------------------------------

def _melee_connects(state: FightState, attacker: FighterState, defender: FighterState,
                    move: MoveData | None, a_id: int, d_id: int) -> bool:
    """Does this fighter's melee move connect this frame (before shield interception)?"""
    if move is None or move.is_projectile:
        return False
    if check_hit(attacker, defender, move):
        return True
    # Direct melee attacks against an enemy's shield wall, even if the body is out of reach
    if not state.rules.enable_shield_wall:
        return False
    shield = defender.shield_wall
    if (attacker.attack_phase != "active" or attacker.has_hit or shield is None
            or abs(attacker.x - shield.x) > move.reach + shield.width / 2.0):
        return False
    intercepted = check_shield_wall_intercept(state, attacker, defender, attacker.current_action,
                                              move, a_id, d_id)
    return (not intercepted and attacker.current_action == Action.THROW
            and abs(attacker.x - defender.x) <= move.reach + SHIELD_THROW_EXTRA_REACH)


def _melee_phase(state: FightState, move1: MoveData | None, move2: MoveData | None,
                 action1: Action, action2: Action, stats1, stats2) -> None:
    """Resolve melee hits simultaneously, so P1 and P2 are treated the same.

    - Both throws connect: throw clash (treated as a tech).
    - A throw and a strike connect on the same frame: the strike wins.
    - Two strikes: a clean trade, both apply.
    """
    f1, f2 = state.fighter1, state.fighter2
    hit1 = _melee_connects(state, f1, f2, move1, 1, 2)
    hit2 = _melee_connects(state, f2, f1, move2, 2, 1)

    throw1 = hit1 and move1.hit_level == HitLevel.THROW
    throw2 = hit2 and move2.hit_level == HitLevel.THROW
    if throw1 and throw2:
        f1.has_hit = f2.has_hit = True
        _break_throw(f1, f2)
        return
    if throw1 and hit2:
        hit1 = False
        f1.has_hit = True
    if throw2 and hit1:
        hit2 = False
        f2.has_hit = True

    if hit1 and not (state.rules.enable_shield_wall
                     and check_shield_wall_intercept(state, f1, f2, f1.current_action, move1, 1, 2)):
        _apply_hit_effect(f1, f2, move1, action2, stats2)
    if hit2 and not (state.rules.enable_shield_wall
                     and check_shield_wall_intercept(state, f2, f1, f2.current_action, move2, 2, 1)):
        _apply_hit_effect(f2, f1, move2, action1, stats1)


def _post_hit_collisions(state: FightState, move1, move2, action1: Action, action2: Action) -> None:
    f1, f2 = state.fighter1, state.fighter2
    # Pushboxes: grounded fighters can never overlap (before wall resolution)
    resolve_pushboxes(f1, f2, float(ARENA_WIDTH))

    if state.rules.is_rumble:
        if f1.attack_phase == "active":
            apply_rumble_attack_vs_objects(state, f1, f2, action1, move1)
        if f2.attack_phase == "active":
            apply_rumble_attack_vs_objects(state, f2, f1, action2, move2)
        apply_rumble_wall_collisions(f1, f2, state.walls, state.arena_objects)
        apply_rumble_wall_collisions(f2, f1, state.walls, state.arena_objects)

    if state.rules.enable_shield_wall:
        apply_shield_wall_collisions(state)


def _apply_hit_effect(attacker: FighterState, defender: FighterState,
                      move: MoveData, defender_action: Action, defender_stats) -> None:
    """Apply the result of an active move connecting with the defender."""
    attacker.has_hit = True

    if _can_parry(defender, defender_action, move.hit_level):
        _apply_parry(attacker, defender)
    elif defender.counter_stance:
        _apply_counter_stance(attacker, defender)
    elif move.hit_level == HitLevel.THROW:
        _grab(defender, move)
    elif is_guarding(defender, defender_action, move.hit_level):
        _apply_guarded_hit(attacker, defender, move.health_damage, move.blockstun,
                           GUARD_DRAIN_PER_BLOCK, move.pushback_block, move.pushback_hit,
                           defender_stats)
        _gain_meter(attacker, move.meter_gain_block)
    else:
        _apply_clean_hit(attacker, defender, move)


def _apply_parry(attacker: FighterState, defender: FighterState) -> None:
    """Perfect parry: no damage, defender gains meter, attacker is staggered."""
    defender.last_hit_effect = "parry"
    defender.parry_armed = False
    _gain_meter(defender, PARRY_METER_GAIN)
    attacker.recovery = PARRY_STAGGER_FRAMES
    attacker.attack_phase = "recovery"
    attacker.attack_frames_left = PARRY_STAGGER_FRAMES
    attacker.cancel_available = False


def _apply_counter_stance(attacker: FighterState, defender: FighterState) -> None:
    """Steel Iron Wall / Fortress Crush: absorb the hit and strike back."""
    defender.counter_stance = False
    defender.last_hit_effect = "counter"
    damage = COUNTER_STANCE_SUPER_DAMAGE if defender.current_action == Action.SUPER else COUNTER_STANCE_DAMAGE
    apply_damage(attacker, damage, is_blocking=False, blocked_damage_ratio=1.0, attacker=defender)
    attacker.hitstun = COUNTER_STANCE_HITSTUN
    _interrupt_attack(attacker)
    apply_pushback(defender, attacker, COUNTER_STANCE_PUSHBACK, ARENA_WIDTH)


def _grab(defender: FighterState, move: MoveData) -> None:
    """A throw connected: start the tech window. The throw type is stored now."""
    defender.is_thrown = True
    defender.throw_tech_frames = THROW_TECH_WINDOW
    defender.throw_damage_pending = move.health_damage
    defender.pending_throw_bounce = move.ground_bounce


def _apply_guarded_hit(attacker: FighterState, defender: FighterState, damage: float,
                       blockstun: int, guard_drain: float, pushback_block: float,
                       pushback_hit: float, defender_stats) -> None:
    """A blocked hit (melee or projectile): chip, guard drain, maybe Guard Break."""
    golden_guard = defender.character_name == "Golden" and defender.stance == "guard"
    if golden_guard:
        guard_drain *= GOLDEN_GUARD_DRAIN_MULT
    defender.guard_meter = max(0.0, defender.guard_meter - guard_drain)

    if defender.guard_meter <= 0.0:
        defender.guard_break_stun = GUARD_BREAK_STUN_FRAMES
        defender.hitstun = GUARD_BREAK_STUN_FRAMES
        defender.blockstun = 0
        defender.guard_meter = GUARD_AFTER_BREAK
        defender.last_hit_effect = "guard_break"
        apply_damage(defender, damage, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker)
        apply_pushback(attacker, defender, pushback_hit, ARENA_WIDTH)
        return

    ratio = defender_stats.blocked_damage_ratio
    if golden_guard:
        ratio *= GOLDEN_GUARD_CHIP_MULT
    apply_damage(defender, damage, is_blocking=True, blocked_damage_ratio=ratio, attacker=attacker)
    defender.blockstun = max(defender.blockstun, blockstun)
    defender.last_hit_effect = "block"
    apply_pushback(attacker, defender, pushback_block, ARENA_WIDTH)
    _gain_meter(defender, METER_GAIN_WHEN_BLOCKING)


def _hit_damage(attacker: FighterState, move: MoveData, read_boost: bool) -> float:
    """Combo scaling (100%, 90%, ... min 30%) with Fury, Rush stance and Read bonuses."""
    scaling = max(COMBO_SCALING_MIN, 1.0 - attacker.combo_hits * COMBO_SCALING_STEP)
    if attacker.is_fury:
        scaling *= FURY_DAMAGE_MULT
    if attacker.character_name == "Golden" and attacker.stance == "rush":
        scaling *= GOLDEN_RUSH_DAMAGE_MULT
    if read_boost:
        scaling *= GOLDEN_READ_DAMAGE_MULT
    return move.health_damage * scaling


def _apply_clean_hit(attacker: FighterState, defender: FighterState, move: MoveData) -> None:
    read_boost = attacker.read_bonus_frames > 0
    if read_boost:
        attacker.read_bonus_frames = 0

    # Counter-hit: hitting the opponent during their startup (or a successful Golden Read)
    is_counter = defender.attack_phase == "startup" or read_boost
    defender.last_hit_effect = "hit"
    if is_counter:
        attacker.last_hit_effect = "counter"
        attacker.is_counter_hit = True
        _interrupt_attack(defender)

    damage = _hit_damage(attacker, move, read_boost)
    had_armor = defender.armor_hits > 0
    apply_damage(defender, damage, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker)

    if not had_armor:
        base_stun = int(move.hitstun * COUNTER_HITSTUN_MULT) if is_counter else move.hitstun
        defender.hitstun = max(defender.hitstun,
                               max(MIN_HITSTUN, base_stun - attacker.combo_hits * HITSTUN_DECAY_PER_HIT))
        defender.recovery = 0
        _interrupt_attack(defender)
        stop_dash(defender)

    _gain_meter(attacker, move.meter_gain_hit + (COUNTER_HIT_BONUS_METER if is_counter else 0.0))
    _gain_meter(defender, METER_GAIN_WHEN_HIT)
    apply_pushback(attacker, defender, move.pushback_hit, ARENA_WIDTH)

    _apply_launch_and_juggle(attacker, defender, move)
    _apply_bounces(attacker, defender, move)
    if move.knockdown and not move.launch:
        _knock_down(defender)

    attacker.combo_hits += 1
    attacker.combo_damage += damage
    attacker.cancel_available = True  # hit-cancel window for combos and strings


def _knock_down(defender: FighterState) -> None:
    defender.is_knocked_down = True
    defender.knockdown_frames = KNOCKDOWN_FRAMES


def _pop_up(defender: FighterState) -> None:
    defender.in_air = True
    defender.jump_frame = 1


def _apply_launch_and_juggle(attacker: FighterState, defender: FighterState, move: MoveData) -> None:
    """Air juggles are capped: on the cap-th air hit the victim drops into knockdown."""
    if defender.in_air:
        attacker.juggle_count += 1
        if attacker.juggle_count >= JUGGLE_CAP:
            _knock_down(defender)
            defender.hitstun = 0
    elif move.launch:
        _pop_up(defender)
        attacker.juggle_count = 1


def _apply_bounces(attacker: FighterState, defender: FighterState, move: MoveData) -> None:
    """Wall bounce and ground bounce, each once per combo."""
    near_wall = defender.x <= WALL_BOUNCE_DISTANCE or defender.x >= (ARENA_WIDTH - WALL_BOUNCE_DISTANCE)
    if (move.wall_bounce or (move.damage >= WALL_BOUNCE_MIN_DAMAGE and near_wall)) and not attacker.wall_bounced:
        attacker.wall_bounced = True
        _pop_up(defender)
        defender.hitstun = max(defender.hitstun, WALL_BOUNCE_HITSTUN)
        attacker.last_hit_effect = "wall_bounce"

    if move.ground_bounce and not attacker.ground_bounced:
        attacker.ground_bounced = True
        _pop_up(defender)
        defender.hitstun = max(defender.hitstun, GROUND_BOUNCE_HITSTUN)
        attacker.last_hit_effect = "ground_bounce"


def _check_golden_read(golden: FighterState, enemy_action: Action) -> None:
    """Golden Read: if the enemy does the predicted attack inside the window,
    the read succeeds (one-frame "read" event) and Golden's next clean hit within
    GOLDEN_READ_BONUS_FRAMES is a counter-hit with bonus damage."""
    if (golden.character_name == "Golden"
            and golden.read_frames_left > 0
            and golden.read_action == enemy_action
            and enemy_action in ATTACKS):
        golden.read_success = True
        golden.last_hit_effect = "read"
        golden.read_frames_left = 0
        golden.read_bonus_frames = GOLDEN_READ_BONUS_FRAMES


# ---------------------------------------------------------------
# Rounds and match
# ---------------------------------------------------------------

def _check_round_end(state: FightState) -> None:
    """Check if the round is over (KO or time-out) and update the state."""
    f1 = state.fighter1
    f2 = state.fighter2

    p1_ko = f1.health <= 0
    p2_ko = f2.health <= 0
    time_out = state.round_frames_left <= 0

    if not p1_ko and not p2_ko and not time_out:
        return

    if p1_ko and p2_ko:
        state.round_result = "draw"
    elif p1_ko:
        state.round_result = "p2"
        state.p2_rounds_won += 1
    elif p2_ko:
        state.round_result = "p1"
        state.p1_rounds_won += 1
    else:
        if f1.health > f2.health:
            state.round_result = "p1"
            state.p1_rounds_won += 1
        elif f2.health > f1.health:
            state.round_result = "p2"
            state.p2_rounds_won += 1
        else:
            state.round_result = "draw"

    state.round_over = True
    _check_match_end(state)


def _check_match_end(state: FightState) -> None:
    """Check if the match is over after a round ended."""
    from backend.engine.constants import MAX_ROUNDS, WINS_NEEDED

    p1w = state.p1_rounds_won
    p2w = state.p2_rounds_won

    if p1w >= WINS_NEEDED:
        state.match_over = True
        state.match_result = "p1"
        return
    if p2w >= WINS_NEEDED:
        state.match_over = True
        state.match_result = "p2"
        return

    if state.round_number >= MAX_ROUNDS:
        state.match_over = True
        if p1w > p2w:
            state.match_result = "p1"
        elif p2w > p1w:
            state.match_result = "p2"
        else:
            state.match_result = "draw"


def new_round(state: FightState) -> FightState:
    """Reset fighters for the next round, keeping the match score and super meter."""
    new = state.copy()
    new.round_number += 1
    new.round_frames_left = RUMBLE_ROUND_FRAMES if new.rules.is_rumble else ROUND_FRAMES
    new.frame = 0
    new.round_over = False
    new.round_result = "none"
    new.projectiles = []
    new.super_freeze_frames = 0
    new.super_attacker = 0
    new.buffered_action1 = Action.IDLE
    new.buffered_action2 = Action.IDLE

    _reset_fighter(new.fighter1, x=ARENA_WIDTH * 0.25)
    _reset_fighter(new.fighter2, x=ARENA_WIDTH * 0.75)

    if new.rules.is_rumble:
        new.walls = []
        new.items = []
        new.supply_drop = None
        for f in (new.fighter1, new.fighter2):
            f.build_charges = BUILD_START_CHARGES
            f.shield = 0.0
            f.speed_boost_timer = 0
            f.power_boost_timer = 0
        if new.rules.enable_zone:
            new.zone = init_rumble_zone()
        if new.rules.enable_objects:
            new.arena_objects = init_rumble_arena_objects(new.rules.arena_name)

    return new


# Per-round fields reset to these values by new_round (everything else —
# meter, stats, identity, per-match statistics — carries over).
_ROUND_RESET_VALUES = {
    "health": 1.0,
    "cooldown": 0,
    "recovery": 0,
    "hitstun": 0,
    "blockstun": 0,
    "attack_phase": "none",
    "attack_frames_left": 0,
    "attack_type": "none",
    "current_action": Action.IDLE,
    "has_hit": False,
    "is_crouching": False,
    "in_air": False,
    "jump_frame": 0,
    "air_jumps_left": 1,
    "air_dash_left": 1,
    "is_knocked_down": False,
    "knockdown_frames": 0,
    "invulnerable_frames": 0,
    "throw_tech_frames": 0,
    "is_thrown": False,
    "throw_damage_pending": 0.0,
    "armor_hits": 0,
    "throw_invuln_frames": 0,
    "pending_throw_bounce": False,
    "dash_frames_left": 0,
    "dash_total_frames": 0,
    "dash_dir": 0,
    "dash_speed": 0.0,
    "dash_in_air": False,
    "combo_hits": 0,
    "combo_damage": 0.0,
    "juggle_count": 0,
    "wall_bounced": False,
    "ground_bounced": False,
    "cancel_available": False,
    "is_counter_hit": False,
    "last_hit_effect": "none",
    "guard_meter": GUARD_METER_MAX,
    "guard_break_stun": 0,
    "block_held_frames": 0,
    "parry_armed": False,
    "parry_lockout": 0,
    "burst_used_this_round": False,
    "counter_stance": False,
    "read_frames_left": 0,
    "read_success": False,
    "read_bonus_frames": 0,
    "shield_wall": None,
    "shield_energy": 100.0,
    "shield_cooldown_frames": 0,
    "shield_startup_frames": 0,
    "shield_startup_side": "none",
    "shield_break_stun": 0,
    "projectile_cooldown": 0,
    "shots_fired": 0,
    "last_action": Action.IDLE,
    "no_hit_timer": 0,
}


def _reset_fighter(fighter: FighterState, x: float) -> None:
    """Put a fighter back to full health at a starting position for a new round."""
    fighter.x = x
    for name, value in _ROUND_RESET_VALUES.items():
        setattr(fighter, name, value)


def _apply_stat_overrides(fighter: FighterState, stats: dict | None) -> None:
    if not stats:
        return
    fighter.health_mult = stats.get("health_mult", 1.0)
    fighter.damage_mult = stats.get("damage_mult", 1.0)
    fighter.speed_mult = stats.get("speed_mult", 1.0)
    fighter.block_mult = stats.get("block_mult", 1.0)


def make_initial_state(character1: str = "Golden",
                       character2: str = "Golden",
                       rules: ModeRules | None = None,
                       seed: int = 42,
                       p1_level: int = 1,
                       p2_level: int = 1,
                       p1_stats: dict | None = None,
                       p2_stats: dict | None = None,
                       p1_regen: bool = False,
                       p2_regen: bool = False) -> FightState:
    """Create the starting state for a new match."""
    mode_rules = rules.copy() if rules is not None else ModeRules.classic()
    f1 = FighterState(x=ARENA_WIDTH * 0.25, character_name=character1, level=p1_level, regen_enabled=p1_regen)
    f2 = FighterState(x=ARENA_WIDTH * 0.75, character_name=character2, level=p2_level, regen_enabled=p2_regen)
    _apply_stat_overrides(f1, p1_stats)
    _apply_stat_overrides(f2, p2_stats)

    state = FightState(fighter1=f1, fighter2=f2, rules=mode_rules, match_seed=seed)

    if mode_rules.is_rumble:
        state.round_frames_left = RUMBLE_ROUND_FRAMES
        f1.build_charges = BUILD_START_CHARGES
        f2.build_charges = BUILD_START_CHARGES
        if mode_rules.enable_zone:
            state.zone = init_rumble_zone()
        if mode_rules.enable_objects:
            state.arena_objects = init_rumble_arena_objects(mode_rules.arena_name)

    return state
