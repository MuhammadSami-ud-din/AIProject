"""Adapter: converts engine FightState into AI Observation.

The engine and the AI use different data structures.
This file bridges them: it reads a FightState and builds
an Observation from the point of view of player 1 or player 2.
"""

from backend.ai.actions import Action
from backend.ai.observation import FRAMES_PER_SECOND, ROUND_SECONDS, Observation
from backend.engine.characters import (
    CHARACTER_STATS,
    light_attack_for,
)
from backend.engine.constants import ARENA_WIDTH
from backend.engine.state import FightState


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

    # Look up each fighter's body stats for reach
    my_stats = CHARACTER_STATS[me.character_name]
    enemy_stats = CHARACTER_STATS[enemy.character_name]

    # Use light attack reach as the "reach" value the AI sees
    # (this is the most common attack, so the AI plans around it)
    my_reach = light_attack_for(my_stats).reach
    enemy_reach = light_attack_for(enemy_stats).reach

    # Convert round timer from frames to seconds
    time_left = state.round_frames_left / FRAMES_PER_SECOND

    return Observation(
        my_x=me.x,
        enemy_x=enemy.x,
        my_health=me.health,
        enemy_health=enemy.health,
        my_reach=my_reach,
        enemy_reach=enemy_reach,
        time_left=min(time_left, ROUND_SECONDS),
        round_length=ROUND_SECONDS,
        frame=state.frame,
        my_cooldown=me.cooldown,
        enemy_cooldown=enemy.cooldown,
        my_recovery=me.recovery,
        enemy_recovery=enemy.recovery,
        my_in_air=me.in_air,
        enemy_in_air=enemy.in_air,
        my_last_action=me.last_action,
        enemy_last_action=enemy.last_action,
        arena_left=0,
        arena_right=ARENA_WIDTH,
        round_number=state.round_number,
        my_rounds_won=my_wins,
        enemy_rounds_won=enemy_wins,
    )
