"""Arena Rumble Engine Mechanics.

Implements all 4 core rumble sub-systems:
- Phase 1: The Squeeze (shrinking zone barrier, inward push, scaling DPS)
- Phase 2: Building (cover walls, placement rules, HP, crack states, destruction)
- Phase 3: Loot & Supply Drops (spawns, pickups, temporary & instant buffs, falling supply crate)
- Phase 4: Arena Objects (destructible crates, jump pads, spike traps)
"""

import math
import random
from typing import Optional, Tuple

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.moves import MoveData
from backend.engine.rules import ModeRules
from backend.engine.rumble_config import (
    ARENA_LAYOUTS,
    BIG_MEDKIT_HP,
    BUILD_KIT_CHARGES,
    BUILD_KIT_MAX_EXTRA,
    BUILD_MAX_CHARGES,
    BUILD_RECHARGE_FRAMES,
    BUILD_START_CHARGES,
    CRATE_DROP_CHANCE,
    CRATE_HEIGHT,
    CRATE_MAX_HP,
    CRATE_WIDTH,
    JUMP_PAD_COOLDOWN_FRAMES,
    JUMP_PAD_HEIGHT,
    JUMP_PAD_LAUNCH_VY,
    JUMP_PAD_WIDTH,
    LOOT_MAX_GROUND_ITEMS,
    LOOT_PICKUP_RADIUS,
    LOOT_SPAWN_MAX_FRAMES,
    LOOT_SPAWN_MIN_FRAMES,
    MEDKIT_HP,
    METER_ORB_AMOUNT,
    OVERCHARGE_CHARGES,
    OVERCHARGE_METER,
    POWER_FIST_DURATION_FRAMES,
    POWER_FIST_MULTIPLIER,
    SHIELD_CELL_HP,
    SHIELD_DECAY_FRAMES,
    SHIELD_MAX_HP,
    SPEED_BOOTS_DURATION_FRAMES,
    SPEED_BOOTS_MULTIPLIER,
    SUPPLY_DROP_FALL_SPEED,
    SUPPLY_DROP_HEIGHT,
    SUPPLY_DROP_TRIGGER_FRAME,
    SUPPLY_DROP_WIDTH,
    TRAP_COOLDOWN_FRAMES,
    TRAP_DAMAGE,
    TRAP_HEIGHT,
    TRAP_KNOCKUP_VY,
    TRAP_TRIGGER_DELAY_FRAMES,
    TRAP_WIDTH,
    WALL_BUILD_TIME_FRAMES,
    WALL_CRACK_1_RATIO,
    WALL_CRACK_2_RATIO,
    WALL_CRUMBLE_DPS,
    WALL_HEAVY_ATTACK_DAMAGE,
    WALL_HEIGHT,
    WALL_LIGHT_ATTACK_DAMAGE,
    WALL_MAX_HP,
    WALL_MAX_PER_FIGHTER,
    WALL_OFFSET_X,
    WALL_WIDTH,
    ZONE_BASE_DPS,
    ZONE_CLOSE_FRAMES,
    ZONE_FINAL_WIDTH_RATIO,
    ZONE_PAUSE_FRAMES,
    ZONE_PUSH_FORCE,
    ZONE_STAGE_CYCLE_FRAMES,
    ZONE_STAGE_DPS,
    ZONE_STAGES,
    ZONE_WARNING_FRAMES,
)
from backend.engine.rumble_state import (
    ArenaObjectState,
    ItemState,
    KillFeedMessage,
    SupplyDropState,
    WallState,
    ZoneState,
)
from backend.engine.state import FighterState, FightState, ProjectileState


# ---------------------------------------------------------------------------
# Setup & Initialization
# ---------------------------------------------------------------------------

def init_rumble_zone() -> ZoneState:
    """Create the starting Zone state: full arena width, stage 1."""
    # 4 stages total to reduce from 800 to 280 (520px total, 130px per stage = 65px per side)
    return ZoneState(
        left=0.0,
        right=float(ARENA_WIDTH),
        stage=1,
        is_closing=False,
        is_warning=False,
        phase_frame=0,
        target_left=65.0,
        target_right=float(ARENA_WIDTH) - 65.0,
        closed_stages=0,
    )


def init_rumble_arena_objects(arena_name: str = "Dojo") -> list[ArenaObjectState]:
    """Populate arena objects for the chosen arena layout."""
    layout = ARENA_LAYOUTS.get(arena_name, ARENA_LAYOUTS["Dojo"])
    objects: list[ArenaObjectState] = []
    obj_id = 1

    # Destructible crates
    for x in layout.get("crates", []):
        objects.append(
            ArenaObjectState(
                id=obj_id,
                object_type="crate",
                x=float(x),
                y=0.0,
                width=CRATE_WIDTH,
                height=CRATE_HEIGHT,
                hp=CRATE_MAX_HP,
                max_hp=CRATE_MAX_HP,
            )
        )
        obj_id += 1

    # Jump pads
    for x in layout.get("jump_pads", []):
        objects.append(
            ArenaObjectState(
                id=obj_id,
                object_type="jump_pad",
                x=float(x),
                y=0.0,
                width=JUMP_PAD_WIDTH,
                height=JUMP_PAD_HEIGHT,
                hp=999.0,
                max_hp=999.0,
            )
        )
        obj_id += 1

    # Spike traps
    for x in layout.get("traps", []):
        objects.append(
            ArenaObjectState(
                id=obj_id,
                object_type="trap",
                x=float(x),
                y=0.0,
                width=TRAP_WIDTH,
                height=TRAP_HEIGHT,
                hp=999.0,
                max_hp=999.0,
            )
        )
        obj_id += 1

    return objects


# ---------------------------------------------------------------------------
# Phase 1: Shrinking Zone ("The Squeeze")
# ---------------------------------------------------------------------------

def update_rumble_zone(state: FightState) -> None:
    """Advance the shrinking energy barrier and apply inward push and damage."""
    if not state.rules.enable_zone:
        return

    zone = state.zone
    total_reduction = ARENA_WIDTH * (1.0 - ZONE_FINAL_WIDTH_RATIO)  # 520 px
    shrink_per_stage_side = (total_reduction / float(ZONE_STAGES)) / 2.0  # 65.0 px per side

    if zone.closed_stages < ZONE_STAGES:
        # Check current stage phase
        current_stage = zone.closed_stages + 1
        zone.stage = current_stage
        zone.phase_frame += 1

        stage_target_left = (zone.closed_stages + 1) * shrink_per_stage_side
        stage_target_right = float(ARENA_WIDTH) - stage_target_left
        zone.target_left = stage_target_left
        zone.target_right = stage_target_right

        if zone.phase_frame <= ZONE_PAUSE_FRAMES:
            # Pause phase
            zone.is_closing = False
            # 5s warning before closing begins
            if zone.phase_frame >= (ZONE_PAUSE_FRAMES - ZONE_WARNING_FRAMES):
                zone.is_warning = True
            else:
                zone.is_warning = False
        else:
            # Closing phase
            zone.is_warning = False
            zone.is_closing = True
            closing_frame = zone.phase_frame - ZONE_PAUSE_FRAMES
            progress = min(1.0, closing_frame / float(ZONE_CLOSE_FRAMES))

            start_left = zone.closed_stages * shrink_per_stage_side
            start_right = float(ARENA_WIDTH) - start_left

            zone.left = start_left + (stage_target_left - start_left) * progress
            zone.right = start_right - (start_right - stage_target_right) * progress

            if closing_frame >= ZONE_CLOSE_FRAMES:
                # Stage closing complete
                zone.closed_stages += 1
                zone.phase_frame = 0
                zone.is_closing = False
                zone.left = stage_target_left
                zone.right = stage_target_right
                add_kill_feed(state, f"ZONE STAGE {zone.closed_stages} COMPLETE", (255, 180, 50))
    else:
        # Final stage reached: stay locked at minimum width
        zone.is_closing = False
        zone.is_warning = False
        final_left = ZONE_STAGES * shrink_per_stage_side
        zone.left = final_left
        zone.right = float(ARENA_WIDTH) - final_left

    # Apply outside-zone push and damage to fighters
    stage_idx = min(zone.stage - 1, len(ZONE_STAGE_DPS) - 1)
    dps = ZONE_STAGE_DPS[stage_idx]
    damage_per_frame_hp = dps / 60.0

    for f, f_name in ((state.fighter1, state.fighter1.character_name),
                      (state.fighter2, state.fighter2.character_name)):
        is_outside = False
        # Left barrier check
        if f.x < zone.left:
            is_outside = True
            f.x = min(zone.left + 2.0, f.x + ZONE_PUSH_FORCE)
        # Right barrier check
        elif f.x > zone.right:
            is_outside = True
            f.x = max(zone.right - 2.0, f.x - ZONE_PUSH_FORCE)

        if is_outside:
            apply_rumble_direct_damage(f, damage_per_frame_hp)
            f.zone_damage_taken += damage_per_frame_hp

    # Crumble cover walls that end up outside the barrier (3 HP/s)
    crumbling = []
    crumble_per_frame = WALL_CRUMBLE_DPS / 60.0
    for w in state.walls:
        if w.right < zone.left or w.left > zone.right:
            w.hp -= crumble_per_frame
            if w.hp <= 0.0:
                crumbling.append(w)
    for w in crumbling:
        state.walls.remove(w)
        owner_name = state.fighter1.character_name if w.owner == 1 else state.fighter2.character_name
        add_kill_feed(state, f"{owner_name}'s wall crumbled in the zone", (180, 180, 180))


# ---------------------------------------------------------------------------
# Phase 2: Building (Cover Walls)
# ---------------------------------------------------------------------------

def update_rumble_building(state: FightState, action1: Action, action2: Action) -> None:
    """Handle build recharge timers, building placement execution, and limits."""
    if not state.rules.enable_building:
        return

    # 1. Recharge build energy (+1 every 8 seconds, up to max)
    for f in (state.fighter1, state.fighter2):
        if f.build_charges < BUILD_MAX_CHARGES:
            f.build_recharge_timer += 1
            if f.build_recharge_timer >= BUILD_RECHARGE_FRAMES:
                f.build_charges += 1
                f.build_recharge_timer = 0
        else:
            f.build_recharge_timer = 0

    # 2. Check build action triggers
    _try_trigger_build(state, state.fighter1, state.fighter2, action1, p_id=1)
    _try_trigger_build(state, state.fighter2, state.fighter1, action2, p_id=2)

    # 3. Advance placement freeze
    _advance_building_frames(state, state.fighter1, state.fighter2, p_id=1)
    _advance_building_frames(state, state.fighter2, state.fighter1, p_id=2)

    # 4. Clean up broken walls (0 HP)
    dead_walls = [w for w in state.walls if w.hp <= 0.0]
    for w in dead_walls:
        state.walls.remove(w)


def _try_trigger_build(state: FightState, f: FighterState, enemy: FighterState,
                       action: Action, p_id: int) -> None:
    """Start the 12-frame placement lock if fighter has charges and is actionable."""
    if action != Action.BUILD:
        return

    # Check actionable conditions
    if f.hitstun > 0 or f.blockstun > 0 or f.in_air or f.is_knocked_down or f.is_thrown:
        return
    if f.building_frames > 0:
        return
    if f.build_charges < 1:
        return

    # Wall placed in front of fighter
    facing_right = enemy.x >= f.x
    wall_x = f.x + (WALL_OFFSET_X if facing_right else -WALL_OFFSET_X)

    # Placement validations upfront
    # 1. Inside safe zone
    zone_left = state.zone.left if (state.rules.enable_zone and state.zone is not None) else 0.0
    zone_right = state.zone.right if (state.rules.enable_zone and state.zone is not None) else float(ARENA_WIDTH)
    if (wall_x - WALL_WIDTH / 2.0 < zone_left) or (wall_x + WALL_WIDTH / 2.0 > zone_right):
        return

    # 2. Not inside the enemy fighter (min separation)
    if abs(wall_x - enemy.x) < (WALL_WIDTH / 2.0 + 16.0):
        return

    # 3. Not overlapping an existing wall
    for w in state.walls:
        if abs(wall_x - w.x) < WALL_WIDTH:
            return

    # Valid: deduct 1 charge and start building
    f.build_charges -= 1
    f.building_frames = WALL_BUILD_TIME_FRAMES


def _advance_building_frames(state: FightState, f: FighterState, enemy: FighterState, p_id: int) -> None:
    """Advance building countdown and place wall block when completed."""
    if f.building_frames <= 0:
        return

    # Interrupted if fighter takes a hit
    if f.hitstun > 0 or f.is_knocked_down or f.is_thrown:
        f.building_frames = 0
        return

    f.building_frames -= 1
    if f.building_frames == 0:
        # Placement frame!
        facing_right = enemy.x >= f.x
        wall_x = f.x + (WALL_OFFSET_X if facing_right else -WALL_OFFSET_X)

        # Max 2 walls per fighter: remove oldest if at capacity
        my_walls = [w for w in state.walls if w.owner == p_id]
        if len(my_walls) >= WALL_MAX_PER_FIGHTER:
            oldest = min(my_walls, key=lambda w: (w.created_frame, w.id))
            state.walls.remove(oldest)

        new_wall = WallState(
            id=state.next_object_id,
            owner=p_id,
            x=wall_x,
            y=0.0,
            hp=WALL_MAX_HP,
            max_hp=WALL_MAX_HP,
            width=WALL_WIDTH,
            height=WALL_HEIGHT,
            created_frame=state.frame,
        )
        state.next_object_id += 1
        state.walls.append(new_wall)
        f.walls_built += 1
        add_kill_feed(state, f"{f.character_name} built a Cover Wall", (100, 200, 255))


# ---------------------------------------------------------------------------
# Phase 3: Loot and Supply Drops
# ---------------------------------------------------------------------------

def update_rumble_loot(state: FightState, action1: Action, action2: Action) -> None:
    """Manage ground item spawns, pickup detection, and falling supply drops."""
    if not state.rules.enable_loot:
        return

    # Update active buff countdowns and shield decay on fighters
    for f in (state.fighter1, state.fighter2):
        if f.speed_boost_timer > 0:
            f.speed_boost_timer -= 1
        if f.power_boost_timer > 0:
            f.power_boost_timer -= 1
        if f.shield > 0.0 and state.frame > 0 and (state.frame % SHIELD_DECAY_FRAMES == 0):
            f.shield = max(0.0, f.shield - 1.0)

    rng = random.Random(state.match_seed + state.frame * 7)

    # 1. Ground item periodic spawning (every 12-18 seconds, max 2 on ground)
    if len(state.items) < LOOT_MAX_GROUND_ITEMS:
        state.next_loot_timer -= 1
        if state.next_loot_timer <= 0:
            _spawn_ground_item(state, rng)
            # Reset timer to next 12-18s window
            state.next_loot_timer = rng.randint(LOOT_SPAWN_MIN_FRAMES, LOOT_SPAWN_MAX_FRAMES)

    # 2. Supply Drop crate at 30s mark (frame 1800)
    if state.frame == SUPPLY_DROP_TRIGGER_FRAME and state.supply_drop is None:
        _spawn_supply_drop(state, rng)

    # Update falling supply drop
    if state.supply_drop is not None:
        sd = state.supply_drop
        if not sd.is_landed:
            sd.y += SUPPLY_DROP_FALL_SPEED
            if sd.y >= sd.target_y:
                sd.y = sd.target_y
                sd.is_landed = True
                add_kill_feed(state, "SUPPLY DROP LANDED!", (255, 215, 0))

    # 3. Item Pickup Checks
    _check_item_pickups(state, state.fighter1, action1, p_id=1)
    _check_item_pickups(state, state.fighter2, action2, p_id=2)


def _spawn_ground_item(state: FightState, rng: random.Random) -> None:
    """Spawn a random ground item inside current safe zone boundaries."""
    zone_left = state.zone.left if state.rules.enable_zone else 0.0
    zone_right = state.zone.right if state.rules.enable_zone else float(ARENA_WIDTH)

    min_x = zone_left + 40.0
    max_x = zone_right - 40.0
    if min_x >= max_x:
        min_x = zone_left + 10.0
        max_x = zone_right - 10.0

    spawn_x = rng.uniform(min_x, max_x)
    # Ensure not directly inside an existing wall
    for w in state.walls:
        if abs(spawn_x - w.x) < 25.0:
            spawn_x = (w.left - 30.0) if spawn_x < w.x else (w.right + 30.0)

    spawn_x = max(zone_left + 20.0, min(zone_right - 20.0, spawn_x))

    loot_types = ["medkit", "shield_cell", "meter_orb", "build_kit", "speed_boots", "power_fist"]
    chosen_type = rng.choice(loot_types)

    item = ItemState(
        id=state.next_object_id,
        item_type=chosen_type,
        x=spawn_x,
        y=0.0,
        radius=LOOT_PICKUP_RADIUS,
        spawn_frame=state.frame,
    )
    state.next_object_id += 1
    state.items.append(item)


def _spawn_supply_drop(state: FightState, rng: random.Random) -> None:
    """Trigger the falling supply crate at a random safe coordinate."""
    zone_left = state.zone.left if state.rules.enable_zone else 0.0
    zone_right = state.zone.right if state.rules.enable_zone else float(ARENA_WIDTH)

    min_x = zone_left + 60.0
    max_x = zone_right - 60.0
    if min_x >= max_x:
        min_x = zone_left + 20.0
        max_x = zone_right - 20.0

    drop_x = rng.uniform(min_x, max_x)
    rare_item = rng.choice(["big_medkit", "overcharge"])

    state.supply_drop = SupplyDropState(
        id=state.next_object_id,
        item_type=rare_item,
        x=drop_x,
        y=-120.0,  # Starts above top of screen
        target_y=0.0,
        is_landed=False,
    )
    state.next_object_id += 1
    add_kill_feed(state, "SUPPLY DROP INCOMING!", (255, 220, 0))


def _check_item_pickups(state: FightState, f: FighterState, action: Action, p_id: int) -> None:
    """Check for item walkover or explicit Action.PICKUP."""
    can_pick = state.rules.auto_pickup or (action == Action.PICKUP)

    # 1. Ground items
    picked_items = []
    for item in state.items:
        if abs(f.x - item.x) <= item.radius and can_pick:
            _apply_item_effect(state, f, item.item_type)
            picked_items.append(item)
            f.items_collected += 1
            break  # Pick one item per frame max

    for it in picked_items:
        state.items.remove(it)

    # 2. Supply Drop crate
    if state.supply_drop is not None and state.supply_drop.is_landed and can_pick:
        sd = state.supply_drop
        if abs(f.x - sd.x) <= (SUPPLY_DROP_WIDTH / 2.0 + 20.0):
            _apply_item_effect(state, f, sd.item_type)
            f.items_collected += 1
            add_kill_feed(state, f"{f.character_name} captured the Supply Drop!", (255, 230, 80))
            state.supply_drop = None


def _apply_item_effect(state: FightState, f: FighterState, item_type: str) -> None:
    """Apply the stat boost or resource from picking up an item."""
    if item_type == "medkit":
        f.health = min(1.0, f.health + MEDKIT_HP / 100.0)
        add_kill_feed(state, f"{f.character_name} picked up Medkit (+15 HP)", (50, 255, 50))
    elif item_type == "shield_cell":
        f.shield = min(SHIELD_MAX_HP, f.shield + SHIELD_CELL_HP)
        add_kill_feed(state, f"{f.character_name} picked up Shield Cell (+20 Shield)", (0, 200, 255))
    elif item_type == "meter_orb":
        f.meter = min(100.0, f.meter + METER_ORB_AMOUNT)
        add_kill_feed(state, f"{f.character_name} picked up Meter Orb (+25 Meter)", (200, 50, 255))
    elif item_type == "build_kit":
        f.build_charges = min(BUILD_MAX_CHARGES + BUILD_KIT_MAX_EXTRA, f.build_charges + BUILD_KIT_CHARGES)
        add_kill_feed(state, f"{f.character_name} picked up Build Kit (+2 Charges)", (255, 180, 0))
    elif item_type == "speed_boots":
        f.speed_boost_timer = SPEED_BOOTS_DURATION_FRAMES
        add_kill_feed(state, f"{f.character_name} activated Speed Boots (+25% Speed)", (100, 255, 200))
    elif item_type == "power_fist":
        f.power_boost_timer = POWER_FIST_DURATION_FRAMES
        add_kill_feed(state, f"{f.character_name} activated Power Fist (+20% Damage)", (255, 80, 80))
    elif item_type == "big_medkit":
        f.health = min(1.0, f.health + BIG_MEDKIT_HP / 100.0)
        add_kill_feed(state, f"{f.character_name} used Big Medkit (+35 HP)", (0, 255, 100))
    elif item_type == "overcharge":
        f.meter = OVERCHARGE_METER
        f.build_charges = min(BUILD_MAX_CHARGES + BUILD_KIT_MAX_EXTRA, f.build_charges + OVERCHARGE_CHARGES)
        add_kill_feed(state, f"{f.character_name} triggered OVERCHARGE (Full Meter + 3 Charges)", (255, 215, 0))


# ---------------------------------------------------------------------------
# Phase 4: Arena Objects (Crates, Jump Pads, Traps)
# ---------------------------------------------------------------------------

def update_rumble_arena_objects(state: FightState) -> None:
    """Update cooldowns, trap triggers, and jump pad interactions."""
    if not state.rules.enable_objects:
        return

    for obj in state.arena_objects:
        # Tick down general cooldown
        if obj.cooldown > 0:
            obj.cooldown -= 1

        if obj.object_type == "jump_pad":
            # Jump pad triggers on fighter contact
            if obj.cooldown == 0:
                for f in (state.fighter1, state.fighter2):
                    if abs(f.x - obj.x) <= (obj.width / 2.0 + 8.0) and not f.in_air:
                        # Launch fighter vertically high!
                        f.in_air = True
                        f.jump_frame = 1  # Air physics starts
                        obj.cooldown = JUMP_PAD_COOLDOWN_FRAMES
                        add_kill_feed(state, f"{f.character_name} used Jump Pad", (150, 255, 255))
                        break

        elif obj.object_type == "trap":
            # Trap pressure plate
            if obj.is_triggered:
                # Warning delay countdown (0.5s = 30 frames)
                obj.trigger_timer -= 1
                if obj.trigger_timer <= 0:
                    # Spikes deploy!
                    obj.is_triggered = False
                    obj.cooldown = TRAP_COOLDOWN_FRAMES
                    # Damage any fighter standing on trap
                    for f in (state.fighter1, state.fighter2):
                        if abs(f.x - obj.x) <= (obj.width / 2.0 + 10.0):
                            apply_rumble_direct_damage(f, TRAP_DAMAGE)
                            f.in_air = True
                            f.jump_frame = 10
                            f.hitstun = 15
                            add_kill_feed(state, f"{f.character_name} hit a Spike Trap! (-8 HP)", (255, 60, 60))
            elif obj.cooldown == 0:
                # Arm pressure plate if fighter steps on it
                for f in (state.fighter1, state.fighter2):
                    if abs(f.x - obj.x) <= (obj.width / 2.0 + 5.0) and not f.in_air:
                        obj.is_triggered = True
                        obj.trigger_timer = TRAP_TRIGGER_DELAY_FRAMES
                        break


# ---------------------------------------------------------------------------
# Collisions: Movement & Projectiles vs Walls & Crates
# ---------------------------------------------------------------------------

def apply_rumble_wall_collisions(f: FighterState, enemy: FighterState,
                                 walls: list[WallState], objects: list[ArenaObjectState]) -> None:
    """Block horizontal movement against walls and crates for grounded fighters."""
    # A jump goes over a wall / crate: skip collision if fighter is in the air
    if f.in_air:
        return

    # Check against cover walls
    for w in walls:
        wall_half = w.width / 2.0 + 16.0
        if abs(f.x - w.x) < wall_half:
            # Fighter is colliding horizontally with wall
            if f.x < w.x:
                f.x = w.x - wall_half
            else:
                f.x = w.x + wall_half

    # Check against destructible crates
    for obj in objects:
        if obj.object_type == "crate" and obj.hp > 0:
            crate_half = obj.width / 2.0 + 16.0
            if abs(f.x - obj.x) < crate_half:
                if f.x < obj.x:
                    f.x = obj.x - crate_half
                else:
                    f.x = obj.x + crate_half


def apply_rumble_projectile_collisions(state: FightState) -> None:
    """Walls and crates absorb and block projectiles."""
    if not (state.rules.enable_building or state.rules.enable_objects):
        return

    expired_projectiles = []
    broken_walls = []
    broken_crates = []

    for p in state.projectiles:
        # Check collision with walls
        for w in state.walls:
            if w.left <= p.x <= w.right:
                # Absorb projectile damage into wall
                wall_dmg = p.damage * 100.0
                w.hp -= wall_dmg
                expired_projectiles.append(p)
                if w.hp <= 0:
                    broken_walls.append(w)
                break

        if p in expired_projectiles:
            continue

        # Check collision with crates
        for obj in state.arena_objects:
            if obj.object_type == "crate" and obj.hp > 0:
                if obj.left <= p.x <= obj.right:
                    crate_dmg = p.damage * 100.0
                    obj.hp -= crate_dmg
                    expired_projectiles.append(p)
                    if obj.hp <= 0:
                        broken_crates.append(obj)
                    break

    # Remove collided projectiles
    for p in expired_projectiles:
        if p in state.projectiles:
            state.projectiles.remove(p)

    # Process broken walls
    for w in broken_walls:
        if w in state.walls:
            state.walls.remove(w)
            add_kill_feed(state, "Wall destroyed by projectile", (200, 200, 200))

    # Process broken crates
    for c in broken_crates:
        _destroy_crate(state, c, destroyer_name="Projectile")


def apply_rumble_attack_vs_objects(state: FightState, attacker: FighterState,
                                   enemy: FighterState, action: Action, move: Optional[MoveData]) -> None:
    """Allow melee attacks to damage and break walls and crates in range."""
    if not (state.rules.enable_building or state.rules.enable_objects):
        return
    if move is None:
        return

    # Attacks deal damage: light = 5 HP, heavy = 12 HP, or scaled move damage
    if action == Action.LIGHT:
        damage = WALL_LIGHT_ATTACK_DAMAGE
    elif action == Action.HEAVY:
        damage = WALL_HEAVY_ATTACK_DAMAGE
    else:
        damage = max(WALL_LIGHT_ATTACK_DAMAGE, move.damage)

    # Apply power fist boost if active
    if attacker.power_boost_timer > 0:
        damage *= POWER_FIST_MULTIPLIER

    facing_right = enemy.x >= attacker.x
    reach = move.reach

    # 1. Damage walls
    broken_walls = []
    for w in state.walls:
        in_front = (w.x >= attacker.x) if facing_right else (w.x <= attacker.x)
        if in_front and abs(w.x - attacker.x) <= (reach + w.width / 2.0):
            w.hp -= damage
            if w.hp <= 0:
                broken_walls.append(w)

    for w in broken_walls:
        if w in state.walls:
            state.walls.remove(w)
            attacker.walls_broken += 1
            owner_name = state.fighter1.character_name if w.owner == 1 else state.fighter2.character_name
            add_kill_feed(state, f"{attacker.character_name} broke {owner_name}'s wall!", (255, 120, 50))

    # 2. Damage crates
    broken_crates = []
    for obj in state.arena_objects:
        if obj.object_type == "crate" and obj.hp > 0:
            in_front = (obj.x >= attacker.x) if facing_right else (obj.x <= attacker.x)
            if in_front and abs(obj.x - attacker.x) <= (reach + obj.width / 2.0):
                obj.hp -= damage
                if obj.hp <= 0:
                    broken_crates.append(obj)

    for c in broken_crates:
        _destroy_crate(state, c, destroyer_name=attacker.character_name)


def _destroy_crate(state: FightState, crate: ArenaObjectState, destroyer_name: str) -> None:
    """Remove crate and trigger 50% ground loot drop at crate position."""
    if crate in state.arena_objects:
        state.arena_objects.remove(crate)
        add_kill_feed(state, f"{destroyer_name} smashed a crate!", (220, 180, 100))

        # 50% drop chance
        rng = random.Random(state.match_seed + state.frame * 13 + crate.id)
        if rng.random() < CRATE_DROP_CHANCE and len(state.items) < LOOT_MAX_GROUND_ITEMS:
            loot_types = ["medkit", "shield_cell", "meter_orb", "build_kit", "speed_boots", "power_fist"]
            item_type = rng.choice(loot_types)
            dropped = ItemState(
                id=state.next_object_id,
                item_type=item_type,
                x=crate.x,
                y=0.0,
                radius=LOOT_PICKUP_RADIUS,
                spawn_frame=state.frame,
            )
            state.next_object_id += 1
            state.items.append(dropped)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def apply_rumble_direct_damage(fighter: FighterState, damage_hp: float) -> None:
    """Damage that respects absorbing shield bar first, then health."""
    remaining = damage_hp
    if fighter.shield > 0.0:
        absorb = min(fighter.shield, remaining)
        fighter.shield -= absorb
        remaining -= absorb

    if remaining > 0.0:
        fighter.health = max(0.0, fighter.health - remaining / 100.0)


def add_kill_feed(state: FightState, text: str, color: Tuple[int, int, int] = (255, 255, 255)) -> None:
    """Add an event notification to the corner kill feed."""
    msg = KillFeedMessage(text=text, color=color, lifetime=180)
    state.kill_feed.append(msg)
    # Keep feed limited to recent messages
    if len(state.kill_feed) > 5:
        state.kill_feed.pop(0)


def update_kill_feed(state: FightState) -> None:
    """Tick down message lifetimes and prune expired messages."""
    expired = []
    for msg in state.kill_feed:
        msg.lifetime -= 1
        if msg.lifetime <= 0:
            expired.append(msg)
    for msg in expired:
        if msg in state.kill_feed:
            state.kill_feed.remove(msg)
