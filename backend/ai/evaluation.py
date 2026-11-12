"""Evaluation: score a situation by combining personality likes with features.

Each "like" in the personality (health_lead, closeness, etc.) is multiplied
by the matching feature value. The sum is the overall score.
Also returns each part's contribution for the explanation panel.
"""

from backend.ai.observation import Observation
from backend.ai.personalities import Personality, LIKE_FIELDS
from backend.ai.zones import distance_ratio, ARENA_WIDTH


def evaluate(obs: Observation, personality: Personality):
    """Score how good this situation is for a fighter with this personality.

    Returns (total_score, contributions) where contributions is a dict
    like {"health_lead": 2.4, "closeness": 3.6, ...} showing each part.
    """
    contributions = {}
    total = 0.0

    likes = personality.likes()

    # health_lead: positive means I'm winning
    # Value: my_health - enemy_health, range -1 to 1
    value = obs.health_lead
    part = likes["health_lead"] * value
    contributions["health_lead"] = part
    total += part

    # closeness: how close I am to the enemy (inverted distance ratio)
    # 1 = touching, 0 = far apart
    closeness_value = 1.0 - obs.distance_ratio
    part = likes["closeness"] * closeness_value
    contributions["closeness"] = part
    total += part

    # safe_distance: how close I am to my preferred distance
    # 1 = exactly at preferred distance, 0 = very far from it
    dist_diff = abs(obs.distance - personality.preferred_distance)
    max_diff = ARENA_WIDTH  # maximum possible difference
    safe_value = 1.0 - min(dist_diff / max_diff, 1.0)
    part = likes["safe_distance"] * safe_value
    contributions["safe_distance"] = part
    total += part

    # block_punish: reward for the enemy being stuck (punishable)
    # 1 if enemy is stuck, 0 otherwise
    punish_value = 1.0 if obs.enemy_is_stuck else 0.0
    part = likes["block_punish"] * punish_value
    contributions["block_punish"] = part
    total += part

    # corner_avoid: penalty for being cornered
    # 1 = not cornered at all, 0 = fully cornered
    width = obs.arena_right - obs.arena_left
    corner_value = min(obs.room_behind_me / (width * 0.15), 1.0)
    part = likes["corner_avoid"] * corner_value
    contributions["corner_avoid"] = part
    total += part

    # time_pressure: reward for being ahead when time is running out
    # Positive when ahead and time is low, negative when behind
    if obs.time_running_out:
        time_value = obs.health_lead  # positive = good if I'm ahead
    else:
        time_value = 0.0
    part = likes["time_pressure"] * time_value
    contributions["time_pressure"] = part
    total += part

    return total, contributions
