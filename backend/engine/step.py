"""The single-frame update: step(state, action1, action2) -> new state.

This is the heart of the engine. It takes the current fight state and
both players' actions, and returns a brand new state for the next frame.
It never changes the input state (pure function).
"""

from backend.ai.actions import Action
from backend.engine.characters import (
    CHARACTER_STATS,
    heavy_attack_for,
    light_attack_for,
    walk_speed,
)
from backend.engine.combat import (
    advance_attack,
    apply_damage,
    check_hit,
    start_attack,
)
from backend.engine.constants import HEAVY_ATTACK, LIGHT_ATTACK
from backend.engine.physics import apply_jump, apply_movement
from backend.engine.state import FightState


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

    # Look up each fighter's body stats
    stats1 = CHARACTER_STATS[f1.character_name]
    stats2 = CHARACTER_STATS[f2.character_name]

    # --- 1. Tick down timers ---
    _tick_timers(f1)
    _tick_timers(f2)

    # --- 2. Handle jumps (must come before movement) ---
    apply_jump(f1, action1)
    apply_jump(f2, action2)

    # --- 3. Handle movement ---
    apply_movement(f1, action1, walk_speed(stats1), new.fighter2.x, enemy_x=f2.x)
    apply_movement(f2, action2, walk_speed(stats2), new.fighter1.x, enemy_x=f1.x)

    # --- 4. Handle attacks ---
    _handle_attacks(f1, action1, stats1)
    _handle_attacks(f2, action2, stats2)

    # --- 5. Advance attack phases ---
    _advance_fighter_attack(f1, stats1)
    _advance_fighter_attack(f2, stats2)

    # --- 6. Check hits ---
    _check_and_apply_hit(f1, f2, stats1, stats2, action2)
    _check_and_apply_hit(f2, f1, stats2, stats1, action1)

    # --- 7. Record what each fighter did ---
    f1.last_action = action1
    f2.last_action = action2

    # --- 8. Advance frame and round timer ---
    new.frame += 1
    new.round_frames_left -= 1

    # --- 9. Check if the round ended ---
    _check_round_end(new)

    return new


# ---------------------------------------------------------------
# Helper functions (private, used only by step)
# ---------------------------------------------------------------

def _tick_timers(fighter):
    """Count down cooldown and recovery timers by one frame."""
    if fighter.cooldown > 0:
        fighter.cooldown -= 1
    if fighter.recovery > 0:
        fighter.recovery -= 1


def _handle_attacks(fighter, action, stats):
    """If the fighter is pressing an attack button, try to start an attack."""
    if action == Action.LIGHT and fighter.attack_phase == "none":
        attack_data = light_attack_for(stats)
        start_attack(fighter, attack_data, "light")

    elif action == Action.HEAVY and fighter.attack_phase == "none":
        attack_data = heavy_attack_for(stats)
        start_attack(fighter, attack_data, "heavy")


def _advance_fighter_attack(fighter, stats):
    """Move the fighter's current attack to the next phase frame."""
    if fighter.attack_phase == "none":
        return

    # Get the right attack data based on what type of attack this is
    if fighter.attack_type == "light":
        attack_data = light_attack_for(stats)
    else:
        attack_data = heavy_attack_for(stats)

    advance_attack(fighter, attack_data)


def _check_and_apply_hit(attacker, defender, attacker_stats, defender_stats,
                         defender_action):
    """If the attacker's hit connects, apply damage to the defender."""
    # Get the right attack data
    if attacker.attack_type == "light":
        attack_data = light_attack_for(attacker_stats)
    elif attacker.attack_type == "heavy":
        attack_data = heavy_attack_for(attacker_stats)
    else:
        return

    if check_hit(attacker, defender, attack_data):
        is_blocking = (defender_action == Action.BLOCK)
        blocked_ratio = defender_stats.blocked_damage_ratio
        apply_damage(defender, attack_data.damage, is_blocking, blocked_ratio)


def _check_round_end(state):
    """Check if the round is over (KO or time-out) and update the state."""
    f1 = state.fighter1
    f2 = state.fighter2

    # KO: one or both fighters are at 0 health
    p1_ko = f1.health <= 0
    p2_ko = f2.health <= 0

    # Time-out: the round timer ran out
    time_out = state.round_frames_left <= 0

    if not p1_ko and not p2_ko and not time_out:
        return  # round still going

    # Determine the round result
    if p1_ko and p2_ko:
        # Both knocked out at the same time: draw
        state.round_result = "draw"
    elif p1_ko:
        state.round_result = "p2"
        state.p2_rounds_won += 1
    elif p2_ko:
        state.round_result = "p1"
        state.p1_rounds_won += 1
    elif time_out:
        # Time ran out: higher health wins, equal = draw
        if f1.health > f2.health:
            state.round_result = "p1"
            state.p1_rounds_won += 1
        elif f2.health > f1.health:
            state.round_result = "p2"
            state.p2_rounds_won += 1
        else:
            # Equal health: draw, worth no point
            state.round_result = "draw"

    state.round_over = True

    # Check if the match is over
    _check_match_end(state)


def _check_match_end(state):
    """Check if the match is over after a round ended."""
    p1w = state.p1_rounds_won
    p2w = state.p2_rounds_won
    from backend.engine.constants import MAX_ROUNDS, WINS_NEEDED

    # Someone reached the wins needed
    if p1w >= WINS_NEEDED:
        state.match_over = True
        state.match_result = "p1"
        return
    if p2w >= WINS_NEEDED:
        state.match_over = True
        state.match_result = "p2"
        return

    # All rounds played: whoever has more round wins takes the match
    if state.round_number >= MAX_ROUNDS:
        state.match_over = True
        if p1w > p2w:
            state.match_result = "p1"
        elif p2w > p1w:
            state.match_result = "p2"
        else:
            state.match_result = "draw"


def new_round(state: FightState) -> FightState:
    """Reset fighters for the next round, keeping the match score.

    Call this after round_over is True and before stepping again.
    Returns a new state with fresh fighter positions and health.
    """
    from backend.engine.constants import ARENA_WIDTH, ROUND_FRAMES

    new = state.copy()
    new.round_number += 1
    new.round_frames_left = ROUND_FRAMES
    new.frame = 0
    new.round_over = False
    new.round_result = "none"

    # Reset fighter 1 (left side of arena)
    _reset_fighter(new.fighter1, x=ARENA_WIDTH * 0.25)

    # Reset fighter 2 (right side of arena)
    _reset_fighter(new.fighter2, x=ARENA_WIDTH * 0.75)

    return new


def _reset_fighter(fighter, x):
    """Put a fighter back to full health at a starting position."""
    fighter.x = x
    fighter.health = 1.0
    fighter.cooldown = 0
    fighter.recovery = 0
    fighter.attack_phase = "none"
    fighter.attack_frames_left = 0
    fighter.attack_type = "none"
    fighter.in_air = False
    fighter.jump_frame = 0
    fighter.last_action = Action.IDLE


def make_initial_state(character1: str = "Golden",
                       character2: str = "Golden") -> FightState:
    """Create the starting state for a new match.

    Fighters start at 25% and 75% of the arena width, facing each other.
    """
    from backend.engine.constants import ARENA_WIDTH

    f1 = FighterState(x=ARENA_WIDTH * 0.25, character_name=character1)
    f2 = FighterState(x=ARENA_WIDTH * 0.75, character_name=character2)

    # Import here to avoid circular dependency
    from backend.engine.state import FightState as FS

    return FS(fighter1=f1, fighter2=f2)


# Need to import FighterState for make_initial_state
from backend.engine.state import FighterState  # noqa: E402
