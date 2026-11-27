"""Adapter: converts engine FightState into AI Observation.

The engine and the AI use different data structures.
This file bridges them: it reads a FightState and builds
an Observation from the point of view of player 1 or player 2.
"""

from backend.ai.actions import Action
from backend.ai.observation import FRAMES_PER_SECOND, ROUND_SECONDS, Observation, enrich_from_state
from backend.engine.constants import ARENA_WIDTH
from backend.engine.moves import get_move
from backend.engine.state import FightState


def _jab_reach(character_name: str) -> float:
    """The character's real Jab reach in pixels (from MoveData, per character)."""
    move = get_move(character_name, Action.LIGHT)
    return float(move.reach) if move is not None else 0.0


def observation_for(state: FightState, player: int) -> Observation:
    """Build an Observation from the given player's point of view.

    player=1 means "I am fighter 1, the enemy is fighter 2."
    player=2 means "I am fighter 2, the enemy is fighter 1."
    """
    if player not in (1, 2):
        raise ValueError(f"player must be 1 or 2, got {player}")

    # Pick which fighter is "me" and which is "enemy"
    if player == 1:
        me = state.fighter1
        enemy = state.fighter2
        my_wins = state.p1_rounds_won
        enemy_wins = state.p2_rounds_won
    else:
        me = state.fighter2
        enemy = state.fighter1
        my_wins = state.p2_rounds_won
        enemy_wins = state.p1_rounds_won

    # Reach = the real Jab (LIGHT) reach from the engine's move data
    my_reach = _jab_reach(me.character_name)
    enemy_reach = _jab_reach(enemy.character_name)

    # Convert round timer from frames to seconds
    time_left = state.round_frames_left / FRAMES_PER_SECOND

    # Rumble Perception
    zone_l = 0.0
    zone_r = float(ARENA_WIDTH)
    zone_time = 0.0
    zone_closing = False
    zone_warning = False
    wall_between = False
    wall_hp = 0.0
    nearest_type = "none"
    nearest_dist = 999.0
    nearest_dir = 0.0
    crate_dist = 999.0
    pad_dist = 999.0
    trap_dist = 999.0

    if state.rules.is_rumble:
        if state.rules.enable_zone:
            zone_l = state.zone.left
            zone_r = state.zone.right
            zone_closing = state.zone.is_closing
            zone_warning = state.zone.is_warning
            if not zone_closing:
                pause_frames_left = max(0, 1200 - state.zone.phase_frame)
                zone_time = pause_frames_left / float(FRAMES_PER_SECOND)

        # Nearest ground item or landed supply drop
        all_items = list(state.items)
        if state.supply_drop is not None and state.supply_drop.is_landed:
            all_items.append(state.supply_drop)

        if all_items:
            closest_it = min(all_items, key=lambda it: abs(me.x - it.x))
            nearest_dist = abs(me.x - closest_it.x)
            nearest_type = closest_it.item_type
            nearest_dir = 1.0 if closest_it.x > me.x else -1.0

        # Check for walls between me and enemy
        min_x = min(me.x, enemy.x)
        max_x = max(me.x, enemy.x)
        for w in state.walls:
            if min_x <= w.x <= max_x:
                wall_between = True
                wall_hp = max(wall_hp, w.hp)

        # Arena objects
        for obj in state.arena_objects:
            d = abs(me.x - obj.x)
            if obj.object_type == "crate" and obj.hp > 0:
                crate_dist = min(crate_dist, d)
            elif obj.object_type == "jump_pad":
                pad_dist = min(pad_dist, d)
            elif obj.object_type == "trap":
                trap_dist = min(trap_dist, d)

    obs = Observation(
        my_x=max(0.0, min(float(ARENA_WIDTH), me.x)),
        enemy_x=max(0.0, min(float(ARENA_WIDTH), enemy.x)),
        my_health=max(0.0, min(1.0, me.health)),
        enemy_health=max(0.0, min(1.0, enemy.health)),
        my_reach=my_reach,
        enemy_reach=enemy_reach,
        time_left=max(0.0, min(time_left, ROUND_SECONDS)),
        round_length=ROUND_SECONDS,
        frame=state.frame,
        my_cooldown=me.cooldown,
        enemy_cooldown=enemy.cooldown,
        my_recovery=me.recovery,
        enemy_recovery=enemy.recovery,
        my_hitstun=me.hitstun,
        enemy_hitstun=enemy.hitstun,
        my_blockstun=me.blockstun,
        enemy_blockstun=enemy.blockstun,
        my_in_air=me.in_air,
        enemy_in_air=enemy.in_air,
        my_is_crouching=me.is_crouching,
        enemy_is_crouching=enemy.is_crouching,
        my_is_knocked_down=me.is_knocked_down,
        enemy_is_knocked_down=enemy.is_knocked_down,
        my_meter=me.meter,
        enemy_meter=enemy.meter,
        my_guard_meter=me.guard_meter,
        enemy_guard_meter=enemy.guard_meter,
        my_combo_count=me.combo_hits,
        enemy_combo_count=enemy.combo_hits,
        is_rumble=state.rules.is_rumble,
        zone_left=zone_l,
        zone_right=zone_r,
        zone_time_to_close=zone_time,
        zone_is_closing=zone_closing,
        zone_is_warning=zone_warning,
        my_build_charges=me.build_charges,
        enemy_build_charges=enemy.build_charges,
        my_shield=me.shield,
        enemy_shield=enemy.shield,
        my_speed_boost=float(me.speed_boost_timer) / float(FRAMES_PER_SECOND),
        enemy_speed_boost=float(enemy.speed_boost_timer) / float(FRAMES_PER_SECOND),
        my_power_boost=float(me.power_boost_timer) / float(FRAMES_PER_SECOND),
        enemy_power_boost=float(enemy.power_boost_timer) / float(FRAMES_PER_SECOND),
        nearest_item_type=nearest_type,
        nearest_item_dist=nearest_dist,
        nearest_item_dir=nearest_dir,
        wall_between=wall_between,
        wall_between_hp=wall_hp,
        nearest_crate_dist=crate_dist,
        nearest_pad_dist=pad_dist,
        nearest_trap_dist=trap_dist,
        enable_shield_wall=state.rules.enable_shield_wall,
        my_shield_wall_up=me.shield_wall.side if me.shield_wall is not None else "none",
        enemy_shield_wall_up=enemy.shield_wall.side if enemy.shield_wall is not None else "none",
        my_shield_wall_hp=me.shield_wall.hp if me.shield_wall is not None else 0.0,
        enemy_shield_wall_hp=enemy.shield_wall.hp if enemy.shield_wall is not None else 0.0,
        my_shield_energy=me.shield_energy,
        enemy_shield_energy=enemy.shield_energy,
        my_shield_cooldown=float(me.shield_cooldown_frames) / float(FRAMES_PER_SECOND),
        enemy_shield_cooldown=float(enemy.shield_cooldown_frames) / float(FRAMES_PER_SECOND),
        my_last_action=me.last_action,
        enemy_last_action=enemy.last_action,
        arena_left=0,
        arena_right=ARENA_WIDTH,
        round_number=state.round_number,
        my_rounds_won=my_wins,
        enemy_rounds_won=enemy_wins,
    )
    # Fill attack phase and action-mask inputs so play matches training.
    return enrich_from_state(obs, state, player)
