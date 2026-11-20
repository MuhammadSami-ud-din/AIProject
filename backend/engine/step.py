"""The single-frame update: step(state, action1, action2) -> new state.

Advances physics, timers, throws, attacks, projectiles, cancels, hit/block resolution,
meters, combos, and win conditions.
Pure function: never changes the input state.
"""

from backend.ai.actions import ATTACKS, Action
from backend.engine.characters import CHARACTER_STATS, walk_speed
from backend.engine.combat import (
    advance_attack,
    apply_damage,
    can_act,
    check_hit,
    is_guarding,
    start_attack,
)
from backend.engine.constants import (
    ARENA_WIDTH,
    REGEN_DELAY_FRAMES,
    REGEN_RATE_PER_FRAME,
    ROUND_FRAMES,
)
from backend.engine.moves import HitLevel, get_move
from backend.engine.physics import apply_jump, apply_movement, apply_pushback
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
from backend.engine.projectile_rules import can_fire_projectile, register_shot
from backend.engine.pushbox import resolve_pushboxes
from backend.engine.shield_wall import (
    apply_shield_attack_drain,
    apply_shield_wall_collisions,
    check_shield_wall_intercept,
    check_shield_wall_projectiles,
    update_shield_walls,
)
from backend.engine.state import FighterState, FightState, ProjectileState


def step(state: FightState, action1: Action, action2: Action) -> FightState:
    """Advance the fight by one frame.

    Takes the current state and both players' chosen actions.
    Returns a completely new FightState (the old one is not touched).
    """
    # If the round or match is already over, do nothing
    if state.round_over or state.match_over:
        return state

    # Work on a fresh copy so we never change the original
    new = state.copy()
    f1 = new.fighter1
    f2 = new.fighter2

    # Super freeze frames: freeze screen briefly for dramatic super flash
    if new.super_freeze_frames > 0:
        new.super_freeze_frames -= 1
        new.frame += 1
        return new

    # Look up each fighter's body stats
    stats1 = CHARACTER_STATS.get(f1.character_name, CHARACTER_STATS["Golden"])
    stats2 = CHARACTER_STATS.get(f2.character_name, CHARACTER_STATS["Golden"])

    # --- 0. Rumble System Updates (Shrinking Zone, Building, Loot, Arena Objects) ---
    if new.rules.is_rumble:
        update_rumble_zone(new)
        update_rumble_building(new, action1, action2)
        update_rumble_loot(new, action1, action2)
        update_rumble_arena_objects(new)
        update_kill_feed(new)

    # --- 0.5 Shield Wall Updates ---
    if new.rules.enable_shield_wall:
        update_shield_walls(new, action1, action2)
        if not new.rules.is_rumble:
            update_kill_feed(new)

    # --- 1. Tick down timers & update statuses ---
    _tick_timers(f1, action1)
    _tick_timers(f2, action2)
    _reset_combos_if_neutral(f1, f2)

    # --- 2. Handle Defensive Bursts (Phase 3) ---
    _handle_burst(f1, f2, action1)
    _handle_burst(f2, f1, action2)

    # --- 3. Handle throw tech and throw execution ---
    _resolve_throw_state(f1, f2, action1)
    _resolve_throw_state(f2, f1, action2)

    # --- 4. Handle jumps (must come before movement) ---
    apply_jump(f1, action1)
    apply_jump(f2, action2)

    # --- 5. Handle movement and crouching ---
    spd1 = walk_speed(stats1) * getattr(f1, "speed_mult", 1.0)
    if f1.speed_boost_timer > 0:
        spd1 *= SPEED_BOOTS_MULTIPLIER
    if f1.building_frames > 0 or f1.shield_break_stun > 0 or f1.shield_startup_frames > 0:
        spd1 = 0.0

    spd2 = walk_speed(stats2) * getattr(f2, "speed_mult", 1.0)
    if f2.speed_boost_timer > 0:
        spd2 *= SPEED_BOOTS_MULTIPLIER
    if f2.building_frames > 0 or f2.shield_break_stun > 0 or f2.shield_startup_frames > 0:
        spd2 = 0.0

    apply_movement(f1, action1, spd1, ARENA_WIDTH, enemy_x=f2.x)
    apply_movement(f2, action2, spd2, ARENA_WIDTH, enemy_x=f1.x)

    # Airborne horizontal movement in Rumble or Shield Wall mode (allows jumping over walls/shields)
    if new.rules.is_rumble or new.rules.enable_shield_wall:
        if f1.in_air and action1 in (Action.FORWARD, Action.DASH):
            facing_right = f2.x >= f1.x
            dir1 = 1 if facing_right else -1
            f1.x = max(0.0, min(float(ARENA_WIDTH), f1.x + dir1 * spd1))
        elif f1.in_air and action1 in (Action.BACK, Action.BACKDASH):
            facing_right = f2.x >= f1.x
            dir1 = -1 if facing_right else 1
            f1.x = max(0.0, min(float(ARENA_WIDTH), f1.x + dir1 * spd1))

        if f2.in_air and action2 in (Action.FORWARD, Action.DASH):
            facing_right = f1.x >= f2.x
            dir2 = 1 if facing_right else -1
            f2.x = max(0.0, min(float(ARENA_WIDTH), f2.x + dir2 * spd2))
        elif f2.in_air and action2 in (Action.BACK, Action.BACKDASH):
            facing_right = f1.x >= f2.x
            dir2 = -1 if facing_right else 1
            f2.x = max(0.0, min(float(ARENA_WIDTH), f2.x + dir2 * spd2))

    # Wall and Crate collisions for grounded fighters
    if new.rules.is_rumble:
        apply_rumble_wall_collisions(f1, f2, new.walls, new.arena_objects)
        apply_rumble_wall_collisions(f2, f1, new.walls, new.arena_objects)
    if new.rules.enable_shield_wall:
        apply_shield_wall_collisions(new)

    # --- 6. Special Movement / Repositioning (Shadow Step) ---
    _handle_special_movement(f1, f2, action1)
    _handle_special_movement(f2, f1, action2)

    # --- 7. Start attacks & cancels ---
    _handle_action_start(f1, action1, new, p_id=1, enemy=f2)
    _handle_action_start(f2, action2, new, p_id=2, enemy=f1)

    # --- 8. Advance attack phases ---
    move1 = get_move(f1.character_name, f1.current_action)
    move2 = get_move(f2.character_name, f2.current_action)
    advance_attack(f1, move1)
    advance_attack(f2, move2)

    # Re-fetch moves after phase advance (in case phase reached active on this frame)
    move1 = get_move(f1.character_name, f1.current_action)
    move2 = get_move(f2.character_name, f2.current_action)

    # --- 9. Spawn projectiles on active frame (Shadow Energy Dart) ---
    _spawn_projectiles(f1, move1, new, p_id=1, enemy_x=f2.x)
    _spawn_projectiles(f2, move2, new, p_id=2, enemy_x=f1.x)

    # --- 10. Update and collide projectiles ---
    if new.rules.enable_shield_wall:
        check_shield_wall_projectiles(new)
    _update_projectiles(new, stats1, stats2)
    if new.rules.is_rumble:
        apply_rumble_projectile_collisions(new)
    if new.rules.enable_shield_wall:
        check_shield_wall_projectiles(new)

    # --- 11. Check melee hits simultaneously (handles clean trades) ---
    f1_hits = (move1 is not None and not move1.is_projectile and check_hit(f1, f2, move1))
    f2_hits = (move2 is not None and not move2.is_projectile and check_hit(f2, f1, move2))

    # Also check direct melee attacks against an enemy's shield wall even if enemy body is out of reach
    if new.rules.enable_shield_wall:
        if not f1_hits and f1.attack_phase == "active" and not f1.has_hit and move1 is not None and not move1.is_projectile:
            if f2.shield_wall is not None and abs(f1.x - f2.shield_wall.x) <= (move1.reach + f2.shield_wall.width / 2.0):
                intercepted = check_shield_wall_intercept(new, f1, f2, f1.current_action, move1, 1, 2)
                if not intercepted and f1.current_action == Action.THROW and abs(f1.x - f2.x) <= (move1.reach + 45.0):
                    f1_hits = True
        if not f2_hits and f2.attack_phase == "active" and not f2.has_hit and move2 is not None and not move2.is_projectile:
            if f1.shield_wall is not None and abs(f2.x - f1.shield_wall.x) <= (move2.reach + f1.shield_wall.width / 2.0):
                intercepted = check_shield_wall_intercept(new, f2, f1, f2.current_action, move2, 2, 1)
                if not intercepted and f2.current_action == Action.THROW and abs(f2.x - f1.x) <= (move2.reach + 45.0):
                    f2_hits = True

    if f1_hits:
        if not (new.rules.enable_shield_wall and check_shield_wall_intercept(new, f1, f2, f1.current_action, move1, 1, 2)):
            _apply_hit_effect(f1, f2, move1, action2, stats2, new, p_id=1)
    if f2_hits:
        if not (new.rules.enable_shield_wall and check_shield_wall_intercept(new, f2, f1, f2.current_action, move2, 2, 1)):
            _apply_hit_effect(f2, f1, move2, action1, stats1, new, p_id=2)

    # Pushboxes: grounded fighters can never overlap (before wall resolution)
    resolve_pushboxes(f1, f2, float(ARENA_WIDTH))

    # Rumble melee attacks vs cover walls and destructible crates
    if new.rules.is_rumble:
        if f1.attack_phase == "active":
            apply_rumble_attack_vs_objects(new, f1, f2, action1, move1)
        if f2.attack_phase == "active":
            apply_rumble_attack_vs_objects(new, f2, f1, action2, move2)

        # Enforce wall and crate collision resolution after pushbacks and specials
        apply_rumble_wall_collisions(f1, f2, new.walls, new.arena_objects)
        apply_rumble_wall_collisions(f2, f1, new.walls, new.arena_objects)

    if new.rules.enable_shield_wall:
        apply_shield_wall_collisions(new)

    # --- 12. Golden Read Mechanic Check ---
    _check_golden_read(f1, action2)
    _check_golden_read(f2, action1)

    # --- 13. Record what each fighter did ---
    f1.last_action = action1
    f2.last_action = action2

    # --- 14. Advance frame and round timer ---
    new.frame += 1
    new.round_frames_left -= 1

    # --- 15. Check if the round ended ---
    _check_round_end(new)

    return new


# ---------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------

def _tick_timers(fighter: FighterState, action: Action) -> None:
    """Count down cooldown, recovery, stun, and invulnerability timers by one frame."""
    if fighter.cooldown > 0:
        fighter.cooldown -= 1
    if fighter.recovery > 0:
        fighter.recovery -= 1
    if fighter.hitstun > 0:
        fighter.hitstun -= 1
    if fighter.blockstun > 0:
        fighter.blockstun -= 1
    if fighter.invulnerable_frames > 0:
        fighter.invulnerable_frames -= 1
    if fighter.guard_break_stun > 0:
        fighter.guard_break_stun -= 1
    if fighter.read_frames_left > 0:
        fighter.read_frames_left -= 1
    if fighter.projectile_cooldown > 0:
        fighter.projectile_cooldown -= 1

    # Track how long block has been held (for 4-frame perfect parry)
    if action in (Action.BLOCK, Action.BLOCK_LOW):
        fighter.block_held_frames += 1
    else:
        fighter.block_held_frames = 0
        # Refill guard meter when not blocking
        if fighter.guard_meter < 100.0 and fighter.guard_break_stun <= 0:
            fighter.guard_meter = min(100.0, fighter.guard_meter + 0.25)

    if fighter.is_knocked_down:
        if fighter.knockdown_frames > 0:
            fighter.knockdown_frames -= 1
        if fighter.knockdown_frames <= 0:
            fighter.is_knocked_down = False
            fighter.invulnerable_frames = 6  # Wakeup invulnerability

    # Health regeneration (only if enabled, e.g. for human in Campaign / Human vs AI)
    fighter.no_hit_timer += 1
    if getattr(fighter, "regen_enabled", False) and fighter.health < 1.0 and not fighter.is_knocked_down and not fighter.is_thrown:
        is_blocking = action in (Action.BLOCK, Action.BLOCK_LOW) or fighter.blockstun > 0
        if fighter.no_hit_timer >= REGEN_DELAY_FRAMES or is_blocking:
            fighter.health = min(1.0, fighter.health + REGEN_RATE_PER_FRAME)


def _reset_combos_if_neutral(f1: FighterState, f2: FighterState) -> None:
    """Reset attacker's combo counters when the defender returns to neutral."""
    if f2.hitstun <= 0 and not f2.in_air and not f2.is_knocked_down and not f2.is_thrown:
        f1.combo_hits = 0
        f1.combo_damage = 0.0
        f1.juggle_count = 0
        f1.wall_bounced = False
        f1.ground_bounced = False
        f1.is_counter_hit = False

    if f1.hitstun <= 0 and not f1.in_air and not f1.is_knocked_down and not f1.is_thrown:
        f2.combo_hits = 0
        f2.combo_damage = 0.0
        f2.juggle_count = 0
        f2.wall_bounced = False
        f2.ground_bounced = False
        f2.is_counter_hit = False


def _handle_burst(victim: FighterState, attacker: FighterState, action: Action) -> None:
    """Spend 50 meter to burst out of a combo once per round."""
    if action == Action.BURST and victim.hitstun > 0 and victim.meter >= 50.0 and not victim.burst_used_this_round:
        victim.meter -= 50.0
        victim.burst_used_this_round = True
        victim.hitstun = 0
        victim.last_hit_effect = "burst"

        # Push attacker far away and stagger
        apply_pushback(victim, attacker, 140.0, ARENA_WIDTH)
        attacker.recovery = 20
        attacker.attack_phase = "none"
        attacker.attack_frames_left = 0
        attacker.current_action = Action.IDLE
        attacker.cancel_available = False

        # End combo
        attacker.combo_hits = 0
        attacker.combo_damage = 0.0


def _handle_special_movement(fighter: FighterState, enemy: FighterState, action: Action) -> None:
    """Handle special repositioning moves like Shadow Step."""
    if fighter.character_name == "Shadow" and action == Action.SPECIAL_FORWARD and can_act(fighter):
        direction = 1 if enemy.x >= fighter.x else -1
        dist = abs(enemy.x - fighter.x)
        if dist <= 140.0:
            # Close-range slip behind opponent
            fighter.x = max(20.0, min(ARENA_WIDTH - 20.0, enemy.x + direction * 55.0))
        else:
            # Bounded forward step when far (no full-screen teleporting)
            fighter.x = max(20.0, min(ARENA_WIDTH - 20.0, fighter.x + direction * 75.0))
        fighter.invulnerable_frames = 6


def _handle_action_start(fighter: FighterState, action: Action,
                         state: FightState, p_id: int, enemy: FighterState) -> None:
    """Try to begin a normal attack, throw, special, or super."""
    if fighter.shield_break_stun > 0 or fighter.shield_startup_frames > 0:
        return

    if action in ATTACKS or action == Action.BACKDASH:
        move = get_move(fighter.character_name, action)
        if move is not None:
            # Shooting is limited: cooldown, one shot in flight, shots per round.
            if move.is_projectile and not can_fire_projectile(fighter, state.projectiles, p_id):
                return
            started = start_attack(fighter, move)
            if started and move.is_projectile:
                register_shot(fighter)
            if started and action in ATTACKS:
                apply_shield_attack_drain(state, fighter, p_id)
            if started and action == Action.SUPER:
                # Trigger super cinematic flash
                state.super_freeze_frames = 15
                state.super_attacker = p_id

            if started and fighter.character_name == "Golden" and action == Action.SPECIAL_NEUTRAL:
                # Golden Read: predict enemy's next action
                fighter.read_action = enemy.last_action if enemy.last_action != Action.IDLE else Action.LIGHT
                fighter.read_frames_left = 30
                fighter.read_success = False


def _spawn_projectiles(fighter: FighterState, move, state: FightState,
                       p_id: int, enemy_x: float) -> None:
    """Spawn deterministic projectiles (e.g. Shadow Energy Dart)."""
    if move is not None and move.is_projectile and fighter.attack_phase == "active" and not fighter.has_hit:
        fighter.has_hit = True
        direction = 1.0 if enemy_x >= fighter.x else -1.0
        proj = ProjectileState(
            x=fighter.x + direction * 30.0,
            y=0.0,
            vx=direction * move.projectile_speed,
            owner=p_id,
            lifetime=move.projectile_lifetime,
            damage=move.health_damage,
            hit_level=move.hit_level.value,
            reach=30.0,
        )
        state.projectiles.append(proj)


def _update_projectiles(state: FightState, stats1, stats2) -> None:
    """Update positions and collisions for all active projectiles."""
    f1 = state.fighter1
    f2 = state.fighter2
    alive_projectiles: list[ProjectileState] = []

    for p in state.projectiles:
        p.x += p.vx
        p.lifetime -= 1

        if p.lifetime <= 0 or p.x < 0 or p.x > ARENA_WIDTH:
            continue

        target = f2 if p.owner == 1 else f1
        target_action = target.last_action
        target_stats = stats2 if p.owner == 1 else stats1
        attacker = f1 if p.owner == 1 else f2

        # Check Steel Reflector: reflect projectile
        if (target.character_name == "Steel" and
                target.current_action == Action.SPECIAL_BACK and
                target.attack_phase in ("startup", "active") and
                abs(p.x - target.x) <= 65.0):
            p.vx = -p.vx
            p.owner = 3 - p.owner
            p.reflected = True
            p.lifetime = 60
            alive_projectiles.append(p)
            continue

        # Check collision with target
        if abs(p.x - target.x) <= p.reach and target.invulnerable_frames <= 0:
            level = HitLevel.MID if p.hit_level == "mid" else (
                HitLevel.HIGH if p.hit_level == "high" else HitLevel.LOW
            )
            blocked = is_guarding(target, target_action, level)
            if blocked:
                apply_damage(target, p.damage, is_blocking=True,
                             blocked_damage_ratio=target_stats.blocked_damage_ratio,
                             attacker=attacker)
                target.blockstun = max(target.blockstun, 12)
                target.guard_meter = max(0.0, target.guard_meter - 10.0)
            else:
                apply_damage(target, p.damage, is_blocking=False, blocked_damage_ratio=1.0,
                             attacker=attacker)
                target.hitstun = max(target.hitstun, 16)
                target.attack_phase = "none"
                target.attack_frames_left = 0
                target.recovery = 0
                target.current_action = Action.IDLE
                target.cancel_available = False
                attacker.meter = min(100.0, attacker.meter + 8.0)
                target.meter = min(100.0, target.meter + 3.0)
            continue  # Consumed

        alive_projectiles.append(p)

    state.projectiles = alive_projectiles


def _resolve_throw_state(victim: FighterState, attacker: FighterState,
                         victim_action: Action) -> None:
    """Handle throw escape / execution during the 7-frame tech window."""
    if not victim.is_thrown:
        return

    # Check throw tech: pressing throw during tech window breaks the throw
    if victim.throw_tech_frames > 0 and victim_action == Action.THROW:
        victim.is_thrown = False
        victim.throw_tech_frames = 0
        victim.throw_damage_pending = 0.0
        victim.recovery = 8
        attacker.recovery = 8
        attacker.attack_phase = "none"
        attacker.attack_frames_left = 0
        attacker.current_action = Action.IDLE
        victim.last_hit_effect = "tech"
        attacker.last_hit_effect = "tech"
        apply_pushback(attacker, victim, 40.0, ARENA_WIDTH)
        return

    victim.throw_tech_frames -= 1
    if victim.throw_tech_frames <= 0:
        # Throw successfully lands!
        apply_damage(victim, victim.throw_damage_pending, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker)
        victim.is_thrown = False
        victim.throw_tech_frames = 0
        victim.throw_damage_pending = 0.0
        attacker_move = get_move(attacker.character_name, attacker.current_action)
        if attacker_move is not None and attacker_move.ground_bounce and not attacker.ground_bounced:
            attacker.ground_bounced = True
            victim.in_air = True
            victim.jump_frame = 1
            victim.hitstun = 24
            attacker.last_hit_effect = "ground_bounce"
        else:
            victim.is_knocked_down = True
            victim.knockdown_frames = 30
        attacker.meter = min(100.0, attacker.meter + 12.0)
        apply_pushback(attacker, victim, 50.0, ARENA_WIDTH)


def _apply_hit_effect(attacker: FighterState, defender: FighterState,
                      move, defender_action: Action, defender_stats,
                      state: FightState, p_id: int) -> None:
    """Apply the result of an active move connecting with the defender."""
    attacker.has_hit = True

    # 1. Check Perfect Parry (Phase 3): block pressed within 4 frames before incoming hit
    if (defender_action in (Action.BLOCK, Action.BLOCK_LOW) and
            defender.block_held_frames <= 4 and
            is_guarding(defender, defender_action, move.hit_level)):
        # PARRY SUCCESSFUL!
        defender.last_hit_effect = "parry"
        defender.meter = min(100.0, defender.meter + 12.0)
        # Attacker is staggered
        attacker.recovery = 22
        attacker.attack_phase = "recovery"
        attacker.attack_frames_left = 22
        attacker.cancel_available = False
        return

    # 2. Check Counter Stance (Steel Iron Wall / Fortress Crush)
    if defender.counter_stance:
        defender.counter_stance = False
        defender.last_hit_effect = "counter"
        counter_damage = 0.35 if defender.current_action == Action.SUPER else 0.16
        apply_damage(attacker, counter_damage, is_blocking=False, blocked_damage_ratio=1.0, attacker=defender)
        attacker.hitstun = 35
        attacker.attack_phase = "none"
        attacker.attack_frames_left = 0
        attacker.current_action = Action.IDLE
        attacker.cancel_available = False
        apply_pushback(defender, attacker, 60.0, ARENA_WIDTH)
        return

    # 3. Handle Throws
    if move.hit_level == HitLevel.THROW:
        defender.is_thrown = True
        defender.throw_tech_frames = 7
        defender.throw_damage_pending = move.health_damage
        return

    # 4. Normal strike: check if blocked
    blocked = is_guarding(defender, defender_action, move.hit_level)

    if blocked:
        # Blocked hit: drain guard meter
        defender.guard_meter = max(0.0, defender.guard_meter - 18.0)

        # Check Guard Break
        if defender.guard_meter <= 0.0:
            defender.guard_break_stun = 40
            defender.hitstun = 40
            defender.blockstun = 0
            defender.guard_meter = 50.0
            defender.last_hit_effect = "guard_break"
            apply_damage(defender, move.health_damage, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker)
            apply_pushback(attacker, defender, move.pushback_hit, ARENA_WIDTH)
        else:
            blocked_ratio = defender_stats.blocked_damage_ratio
            apply_damage(defender, move.health_damage, is_blocking=True, blocked_damage_ratio=blocked_ratio, attacker=attacker)
            defender.blockstun = max(defender.blockstun, move.blockstun)
            apply_pushback(attacker, defender, move.pushback_block, ARENA_WIDTH)

        attacker.meter = min(100.0, attacker.meter + move.meter_gain_block)
        defender.meter = min(100.0, defender.meter + 1.5)

    else:
        # Clean hit!
        # Check Counter-hit: hitting opponent during their startup
        is_counter = defender.attack_phase == "startup"
        if is_counter:
            attacker.last_hit_effect = "counter"
            attacker.is_counter_hit = True
            defender.attack_phase = "none"
            defender.attack_frames_left = 0
            defender.current_action = Action.IDLE

        # Combo scaling: 100%, 90%, 80%... down to min 30%
        scaling = max(0.30, 1.0 - attacker.combo_hits * 0.10)
        # Fury bonus: +10% damage when health < 25%
        if attacker.is_fury:
            scaling *= 1.10

        actual_damage = move.health_damage * scaling
        had_armor = defender.armor_hits > 0
        apply_damage(defender, actual_damage, is_blocking=False, blocked_damage_ratio=1.0, attacker=attacker)

        # Hitstun with counter bonus (+50%) and infinite combo protection decay
        if not had_armor:
            base_stun = int(move.hitstun * 1.5) if is_counter else move.hitstun
            decayed_hitstun = max(4, base_stun - attacker.combo_hits * 2)
            defender.hitstun = max(defender.hitstun, decayed_hitstun)
            defender.attack_phase = "none"
            defender.attack_frames_left = 0
            defender.recovery = 0
            defender.current_action = Action.IDLE
            defender.cancel_available = False

        # Meter gain
        bonus_meter = 5.0 if is_counter else 0.0
        attacker.meter = min(100.0, attacker.meter + move.meter_gain_hit + bonus_meter)
        defender.meter = min(100.0, defender.meter + 3.0)

        # Pushback
        apply_pushback(attacker, defender, move.pushback_hit, ARENA_WIDTH)

        # Launch and Juggle (Air juggle capped at 4 hits)
        if defender.in_air:
            attacker.juggle_count += 1
            if attacker.juggle_count >= 4:
                # Juggle cap reached: opponent falls into hard knockdown
                defender.is_knocked_down = True
                defender.knockdown_frames = 30
                defender.hitstun = 0
        elif move.launch:
            defender.in_air = True
            defender.jump_frame = 1
            attacker.juggle_count = 1

        # Wall Bounce
        is_near_wall = defender.x <= 35.0 or defender.x >= (ARENA_WIDTH - 35.0)
        if (move.wall_bounce or (move.damage >= 8.0 and is_near_wall)) and not attacker.wall_bounced:
            attacker.wall_bounced = True
            defender.in_air = True
            defender.jump_frame = 1
            defender.hitstun = max(defender.hitstun, 24)
            attacker.last_hit_effect = "wall_bounce"

        # Ground Bounce
        if move.ground_bounce and not attacker.ground_bounced:
            attacker.ground_bounced = True
            defender.in_air = True
            defender.jump_frame = 1
            defender.hitstun = max(defender.hitstun, 22)
            attacker.last_hit_effect = "ground_bounce"

        # Knockdown
        if move.knockdown and not move.launch:
            defender.is_knocked_down = True
            defender.knockdown_frames = 30

        # Update Combo tracker
        attacker.combo_hits += 1
        attacker.combo_damage += actual_damage

        # Enable Cancel window for combos and strings
        attacker.cancel_available = True


def _check_golden_read(attacker: FighterState, enemy_action: Action) -> None:
    """Check if Golden Tactician's read prediction matched the enemy's action."""
    if (attacker.character_name == "Golden" and
            attacker.read_frames_left > 0 and
            attacker.read_action == enemy_action and
            enemy_action in ATTACKS):
        attacker.read_success = True
        attacker.last_hit_effect = "read"


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
        # Time-out
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
    p1w = state.p1_rounds_won
    p2w = state.p2_rounds_won
    from backend.engine.constants import MAX_ROUNDS, WINS_NEEDED

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

    _reset_fighter(new.fighter1, x=ARENA_WIDTH * 0.25)
    _reset_fighter(new.fighter2, x=ARENA_WIDTH * 0.75)

    if new.rules.is_rumble:
        new.walls = []
        new.items = []
        new.supply_drop = None
        new.fighter1.build_charges = BUILD_START_CHARGES
        new.fighter2.build_charges = BUILD_START_CHARGES
        new.fighter1.shield = 0.0
        new.fighter2.shield = 0.0
        new.fighter1.speed_boost_timer = 0
        new.fighter2.speed_boost_timer = 0
        new.fighter1.power_boost_timer = 0
        new.fighter2.power_boost_timer = 0
        if new.rules.enable_zone:
            new.zone = init_rumble_zone()
        if new.rules.enable_objects:
            new.arena_objects = init_rumble_arena_objects(new.rules.arena_name)

    return new


def _reset_fighter(fighter: FighterState, x: float) -> None:
    """Put a fighter back to full health at a starting position for a new round."""
    fighter.x = x
    fighter.health = 1.0
    fighter.cooldown = 0
    fighter.recovery = 0
    fighter.hitstun = 0
    fighter.blockstun = 0
    fighter.attack_phase = "none"
    fighter.attack_frames_left = 0
    fighter.attack_type = "none"
    fighter.current_action = Action.IDLE
    fighter.is_crouching = False
    fighter.in_air = False
    fighter.jump_frame = 0
    fighter.air_jumps_left = 1
    fighter.air_dash_left = 1
    fighter.is_knocked_down = False
    fighter.knockdown_frames = 0
    fighter.invulnerable_frames = 0
    fighter.throw_tech_frames = 0
    fighter.is_thrown = False
    fighter.throw_damage_pending = 0.0
    fighter.armor_hits = 0
    fighter.combo_hits = 0
    fighter.combo_damage = 0.0
    fighter.juggle_count = 0
    fighter.wall_bounced = False
    fighter.ground_bounced = False
    fighter.cancel_available = False
    fighter.is_counter_hit = False
    fighter.guard_meter = 100.0
    fighter.guard_break_stun = 0
    fighter.block_held_frames = 0
    fighter.burst_used_this_round = False
    fighter.shield_wall = None
    fighter.shield_energy = 100.0
    fighter.shield_cooldown_frames = 0
    fighter.shield_startup_frames = 0
    fighter.shield_startup_side = "none"
    fighter.shield_break_stun = 0
    fighter.projectile_cooldown = 0
    fighter.shots_fired = 0
    fighter.counter_stance = False
    fighter.read_frames_left = 0
    fighter.read_success = False
    fighter.last_action = Action.IDLE
    fighter.no_hit_timer = 0


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

    if p1_stats:
        f1.health_mult = p1_stats.get("health_mult", 1.0)
        f1.damage_mult = p1_stats.get("damage_mult", 1.0)
        f1.speed_mult = p1_stats.get("speed_mult", 1.0)
        f1.block_mult = p1_stats.get("block_mult", 1.0)

    if p2_stats:
        f2.health_mult = p2_stats.get("health_mult", 1.0)
        f2.damage_mult = p2_stats.get("damage_mult", 1.0)
        f2.speed_mult = p2_stats.get("speed_mult", 1.0)
        f2.block_mult = p2_stats.get("block_mult", 1.0)

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
