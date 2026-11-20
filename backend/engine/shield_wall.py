"""Engine mechanics for the Shield Wall ability.

Handles:
- Energy regeneration (with turtle penalty)
- Cooldowns, startup frames, and break stun
- Deploying FRONT or BACK energy shield panels
- Blocking horizontal movement for both fighters (like a wall)
- Intercepting melee attacks and projectiles with counterplay:
  - Throws & command grabs ignore shields and remove them on grab
  - Heavy attacks deal bonus damage (x2, Crimson x2.5) and 15% chip damage
  - Overheads and jump-ins bypass standing shield height
  - Attacking while shield is up drains shield HP by 3 per attack
- Shield break punishment (20 frames stun)
"""

from typing import List, Optional

from backend.ai.actions import ATTACKS, Action
from backend.engine.constants import ARENA_WIDTH
from backend.engine.moves import MoveData
from backend.engine.rumble_state import KillFeedMessage
from backend.engine.shield_config import (
    ShieldBalance,
    get_character_shield_balance,
)
from backend.engine.shield_state import ShieldWallState
from backend.engine.state import FighterState, FightState


def _add_shield_feed(state: FightState, text: str, color: tuple[int, int, int]) -> None:
    """Append a feedback message to the fight feed."""
    state.kill_feed.append(KillFeedMessage(text=text, color=color, lifetime=150))
    if len(state.kill_feed) > 5:
        state.kill_feed.pop(0)


def get_player_shield_balance(state: FightState, p_id: int) -> ShieldBalance:
    """Get the effective ShieldBalance for player 1 or player 2, with character tweaks."""
    f = state.fighter1 if p_id == 1 else state.fighter2
    base = state.rules.shield_balance_p1 if p_id == 1 else state.rules.shield_balance_p2
    if state.rules.same_shield_for_both:
        base = state.rules.shield_balance_p1
    return get_character_shield_balance(base, f.character_name)


def update_shield_walls(state: FightState, action1: Action, action2: Action) -> None:
    """Advance shield energy regen, cooldowns, startup, durations, and activations."""
    if not state.rules.enable_shield_wall:
        return

    for p_id, f, enemy, action in (
        (1, state.fighter1, state.fighter2, action1),
        (2, state.fighter2, state.fighter1, action2),
    ):
        bal = get_player_shield_balance(state, p_id)

        # 1. Tick down break stun
        if f.shield_break_stun > 0:
            f.shield_break_stun -= 1

        # 2. Tick down cooldown
        if f.shield_cooldown_frames > 0:
            f.shield_cooldown_frames -= 1

        # 3. Energy Regeneration (with Turtle Penalty)
        is_blocking = action in (Action.BLOCK, Action.BLOCK_LOW)
        turtle_halted = bal.turtle_penalty and is_blocking and (f.shield_wall is not None)
        if not turtle_halted and f.shield_energy < 100.0:
            f.shield_energy = min(100.0, f.shield_energy + bal.energy_regen_per_s / 60.0)

        # 4. Update active shield duration
        if f.shield_wall is not None:
            f.shield_wall.duration_frames -= 1
            f.shield_time_behind_frames += 1

            # Check natural duration expiry or 0 HP
            if f.shield_wall.duration_frames <= 0 or f.shield_wall.hp <= 0.0:
                if f.shield_wall.hp <= 0.0:
                    _trigger_shield_break(state, f, bal)
                else:
                    # Natural expiry: enters cooldown without break stun
                    f.shield_wall = None
                    f.shield_cooldown_frames = int(bal.cooldown_s * 60)

        # 5. Advance startup frames if currently raising
        if f.shield_startup_frames > 0:
            # Interrupted if hit or knocked down during startup
            if f.hitstun > 0 or f.is_knocked_down or f.is_thrown:
                f.shield_startup_frames = 0
                f.shield_startup_side = "none"
            else:
                f.shield_startup_frames -= 1
                if f.shield_startup_frames == 0:
                    _deploy_shield_wall(state, f, enemy, p_id, bal)

        # 6. Check new activation trigger
        if action in (Action.SHIELD_FRONT, Action.SHIELD_BACK):
            _try_start_shield_wall(state, f, action, bal)


def _try_start_shield_wall(state: FightState, f: FighterState, action: Action, bal: ShieldBalance) -> None:
    """Start the 8-frame (or 5-frame for Shadow) startup if all rules allow."""
    if f.shield_wall is not None:
        return  # Max 1 shield rule (front OR back, not both)
    if f.shield_startup_frames > 0:
        return
    if f.shield_cooldown_frames > 0:
        return
    if f.shield_energy < bal.energy_cost:
        return
    if f.shield_break_stun > 0:
        return
    if (
        f.hitstun > 0
        or f.blockstun > 0
        or f.recovery > 0
        or f.in_air
        or f.is_knocked_down
        or f.is_thrown
        or f.attack_phase != "none"
    ):
        return

    # Valid activation: spend energy and enter startup
    f.shield_energy -= bal.energy_cost
    f.shield_startup_frames = bal.startup_frames
    f.shield_startup_side = "front" if action == Action.SHIELD_FRONT else "back"


def _deploy_shield_wall(state: FightState, f: FighterState, enemy: FighterState,
                        p_id: int, bal: ShieldBalance) -> None:
    """Place the solid energy shield panel next to the fighter."""
    facing_right = enemy.x >= f.x
    if f.shield_startup_side == "front":
        offset = bal.offset_x if facing_right else -bal.offset_x
    else:
        # BACK shield
        offset = -bal.offset_x if facing_right else bal.offset_x

    shield_x = f.x + offset
    min_sep = bal.width / 2.0 + 16.0
    shield_x = max(min_sep + 2.0, min(float(ARENA_WIDTH) - (min_sep + 2.0), shield_x))

    # Avoid deploying directly on top of the opponent
    if abs(shield_x - enemy.x) < min_sep:
        push_dir = 1.0 if shield_x >= enemy.x else -1.0
        shield_x = max(min_sep + 2.0, min(float(ARENA_WIDTH) - (min_sep + 2.0), enemy.x + push_dir * (min_sep + 2.0)))

    f.shield_wall = ShieldWallState(
        owner=p_id,
        side=f.shield_startup_side,
        x=shield_x,
        y=0.0,
        width=bal.width,
        height=bal.height,
        hp=bal.shield_hp,
        max_hp=bal.shield_hp,
        duration_frames=int(bal.duration_s * 60),
        created_frame=state.frame,
    )
    f.shield_startup_side = "none"
    f.shield_walls_raised += 1
    _add_shield_feed(state, f"{f.character_name}: SHIELD UP!", (80, 220, 255))


def _trigger_shield_break(state: FightState, owner_fighter: FighterState, bal: ShieldBalance) -> None:
    """Break the shield, apply 20-frame stun punishment, and trigger cooldown."""
    owner_fighter.shield_wall = None
    owner_fighter.shield_walls_broken += 1
    owner_fighter.shield_break_stun = bal.break_stun_frames
    owner_fighter.shield_cooldown_frames = int(bal.cooldown_s * 60)
    owner_fighter.last_hit_effect = "guard_break"
    _add_shield_feed(state, f"{owner_fighter.character_name} SHIELD BREAK!", (255, 60, 60))


def apply_shield_attack_drain(state: FightState, attacker: FighterState, p_id: int) -> None:
    """Can attack while shield up, but each attack drains shield HP by 3."""
    if not state.rules.enable_shield_wall:
        return
    if attacker.shield_wall is not None:
        bal = get_player_shield_balance(state, p_id)
        attacker.shield_wall.hp -= bal.attack_hp_drain
        if attacker.shield_wall.hp <= 0.0:
            _trigger_shield_break(state, attacker, bal)


def apply_shield_wall_collisions(state: FightState) -> None:
    """Prevent grounded fighters from walking through any active shield wall."""
    if not state.rules.enable_shield_wall:
        return

    shields: List[ShieldWallState] = []
    if state.fighter1.shield_wall is not None:
        shields.append(state.fighter1.shield_wall)
    if state.fighter2.shield_wall is not None:
        shields.append(state.fighter2.shield_wall)

    if not shields:
        return

    for f in (state.fighter1, state.fighter2):
        # Jumps go over the shield
        if f.in_air:
            continue
        for s in shields:
            min_sep = s.width / 2.0 + 16.0
            if abs(f.x - s.x) < min_sep:
                if f.x < s.x:
                    target_x = s.x - min_sep
                    f.x = target_x if target_x >= 0.0 else (s.x + min_sep)
                else:
                    target_x = s.x + min_sep
                    f.x = target_x if target_x <= float(ARENA_WIDTH) else (s.x - min_sep)


def check_shield_wall_intercept(
    state: FightState,
    attacker: FighterState,
    defender: FighterState,
    action: Action,
    move: MoveData,
    attacker_id: int,
    defender_id: int,
) -> bool:
    """Check if defender's active shield wall blocks an incoming melee attack.

    Returns True if the shield intercepted the strike (damage absorbed by shield,
    with possible heavy chip damage to defender). Returns False if the attack
    bypasses or ignores the shield (throws, overheads, jump-ins, or wrong side).
    """
    if not state.rules.enable_shield_wall:
        return False

    shield = defender.shield_wall
    if shield is None:
        return False

    def_bal = get_player_shield_balance(state, defender_id)
    atk_bal = get_player_shield_balance(state, attacker_id)

    # Counter 1: Throws and command grabs ignore shields completely and remove them
    if action == Action.THROW and def_bal.throws_ignore_shields:
        defender.shield_wall = None
        defender.shield_cooldown_frames = int(def_bal.cooldown_s * 60)
        _add_shield_feed(state, "THROW THROUGH!", (255, 180, 50))
        return False

    # Counter 2: Overheads and jump-ins go over the standing shield height
    if action in (Action.OVERHEAD, Action.JUMP_PUNCH, Action.JUMP_KICK) or move.is_air:
        return False

    # Side check: is the shield between the attacker and the defender?
    min_x = min(attacker.x, defender.x)
    max_x = max(attacker.x, defender.x)
    is_between = (min_x - 10.0) <= shield.x <= (max_x + 10.0)
    if not is_between:
        return False

    # Shield intercepts the strike!
    attacker.has_hit = True
    is_heavy = action in (Action.HEAVY, Action.HEAVY_KICK, Action.LOW_SWEEP, Action.SUPER) or move.damage >= 10.0

    # Heavy attack bonus vs shield (x2 default, Crimson x2.5)
    shield_dmg = move.damage * (atk_bal.heavy_attack_bonus if is_heavy else 1.0)
    shield.hp -= shield_dmg

    # Chip damage through shield: 0% light, 15% heavy
    if is_heavy and def_bal.heavy_chip_rate > 0.0:
        chip_dmg = move.health_damage * def_bal.heavy_chip_rate
        defender.health = max(0.0, defender.health - chip_dmg)

    # Check if shield shattered
    if shield.hp <= 0.0:
        _trigger_shield_break(state, defender, def_bal)

    return True


def check_shield_wall_projectiles(state: FightState) -> None:
    """Active shield walls intercept and absorb incoming enemy projectiles."""
    if not state.rules.enable_shield_wall:
        return

    expired = []
    for p in state.projectiles:
        target_f = state.fighter2 if p.owner == 1 else state.fighter1
        target_id = 2 if p.owner == 1 else 1
        shield = target_f.shield_wall
        if shield is not None:
            if shield.left <= p.x <= shield.right:
                shield.hp -= p.damage * 100.0
                expired.append(p)
                if shield.hp <= 0.0:
                    bal = get_player_shield_balance(state, target_id)
                    _trigger_shield_break(state, target_f, bal)

    for p in expired:
        if p in state.projectiles:
            state.projectiles.remove(p)
