"""Explain the AI's decisions in plain English.

Generates one-sentence reasons and short commentary for the
AI Model Fight Viewer and the explanation panel.
"""

from backend.ai.actions import Action
from backend.ai.observation import Observation
from backend.ai.zones import zone_of, Zone


def explain_action(action, obs, scores=None, personality=None):
    """Return a one-sentence reason for the chosen action.

    Examples:
      "Crimson rushed forward because the enemy is far away."
      "Steel blocked because the enemy just attacked."
    """
    name = personality.name if personality else "Fighter"

    if action == Action.LIGHT:
        if obs.enemy_is_stuck:
            return f"{name} attacked because the enemy is stuck after their attack."
        elif obs.is_safe_poke:
            return f"{name} poked from safe range where the enemy can't reach."
        elif obs.i_can_hit:
            return f"{name} attacked because the enemy is in range."
        else:
            return f"{name} threw a quick attack."

    elif action == Action.HEAVY:
        if obs.enemy_is_stuck:
            return f"{name} used a heavy attack to punish the enemy's recovery."
        elif obs.i_can_hit:
            return f"{name} threw a heavy attack for big damage."
        else:
            return f"{name} used a risky heavy attack."

    elif action == Action.BLOCK:
        if obs.enemy_is_attacking:
            return f"{name} blocked to defend against the incoming attack."
        elif obs.enemy_can_hit:
            return f"{name} is guarding because the enemy is in range."
        else:
            return f"{name} raised their guard cautiously."

    elif action == Action.FORWARD:
        zone = zone_of(obs.distance)
        if zone == Zone.FAR:
            return f"{name} rushed forward because the enemy is far away."
        elif obs.enemy_is_stuck:
            return f"{name} moved in to punish the enemy's recovery."
        else:
            return f"{name} advanced toward the enemy."

    elif action == Action.BACK:
        if obs.i_am_cornered:
            return f"{name} tried to back away but is near the wall."
        else:
            return f"{name} backed away to create distance."

    elif action == Action.JUMP:
        if obs.i_am_cornered:
            return f"{name} jumped to escape the corner."
        elif obs.enemy_is_attacking:
            return f"{name} jumped to dodge an attack."
        else:
            return f"{name} jumped."

    return f"{name} is waiting."


def commentary(obs, personality=None):
    """Return a short commentary line about the fight situation.

    Examples:
      "Crimson is cornered and low on health!"
      "Shadow has a big health lead."
    """
    name = personality.name if personality else "Fighter"
    lines = []

    # Health
    if obs.my_health < 0.2:
        lines.append(f"{name} is in critical condition!")
    elif obs.my_health < 0.4:
        lines.append(f"{name} is low on health.")

    if obs.enemy_health < 0.2:
        lines.append(f"The opponent is nearly knocked out!")
    elif obs.enemy_health < 0.4:
        lines.append(f"The opponent is weakening.")

    # Health lead
    if obs.health_lead > 0.3:
        lines.append(f"{name} has a big health lead.")
    elif obs.health_lead < -0.3:
        lines.append(f"{name} is losing badly.")

    # Position
    if obs.i_am_cornered:
        lines.append(f"{name} is cornered!")
    if obs.enemy_is_cornered:
        lines.append(f"The opponent is cornered!")

    # Time
    if obs.time_running_out:
        if obs.health_lead > 0:
            lines.append(f"Time is running out — {name} is ahead!")
        elif obs.health_lead < 0:
            lines.append(f"Time is running out — {name} needs to attack!")
        else:
            lines.append(f"Time is running out with equal health!")

    if not lines:
        zone = zone_of(obs.distance)
        if zone == Zone.CLOSE:
            lines.append(f"Close-range fighting!")
        elif zone == Zone.FAR:
            lines.append(f"Both fighters are far apart.")
        else:
            lines.append(f"Mid-range standoff.")

    return " ".join(lines)
