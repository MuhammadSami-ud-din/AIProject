"""Explain the AI's decisions in plain English.

Generates one-sentence reasons and short commentary for the
AI Model Fight Viewer and the explanation panel.
"""

from backend.ai.actions import Action
from backend.ai.observation import Observation
from backend.ai.zones import Zone, zone_of


# One template per action so only Action.IDLE says "waiting".
ACTION_TEMPLATES = {
    Action.IDLE: "{name} is waiting for an opening.",
    Action.FORWARD: "{name} steps forward to close distance.",
    Action.BACK: "{name} steps back to maintain spacing.",
    Action.JUMP: "{name} jumps into the air.",
    Action.CROUCH: "{name} crouches low to duck high attacks.",
    Action.DASH: "{name} dashes in to close the gap quickly.",
    Action.BACKDASH: "{name} backs off to make space.",
    Action.LIGHT: "{name} throws a fast jab to check the opponent.",
    Action.HEAVY: "{name} swings a heavy punch for big damage.",
    Action.LIGHT_KICK: "{name} pokes with a quick light kick.",
    Action.HEAVY_KICK: "{name} extends a long-reach roundhouse kick.",
    Action.LOW_SWEEP: "{name} sweeps low to knock the opponent down.",
    Action.OVERHEAD: "{name} strikes overhead to crack a low guard.",
    Action.CROUCH_JAB: "{name} fires a fast crouching jab.",
    Action.CROUCH_KICK: "{name} pokes low with a crouching kick.",
    Action.JUMP_PUNCH: "{name} attacks from the air with a jumping punch.",
    Action.JUMP_KICK: "{name} dives in with a jumping kick.",
    Action.ANTI_AIR: "{name} launches an anti-air uppercut against the jump.",
    Action.BLOCK: "{name} holds standing guard against incoming strikes.",
    Action.BLOCK_LOW: "{name} blocks low to stop sweeps and pokes.",
    Action.THROW: "{name} reaches in for a close-range throw.",
    Action.SPECIAL_NEUTRAL: "{name} unleashes a signature special technique.",
    Action.SPECIAL_FORWARD: "{name} lunges in with an advancing special attack.",
    Action.SPECIAL_BACK: "{name} uses a defensive special technique.",
    Action.SPECIAL_DOWN: "{name} executes a low special technique.",
    Action.SUPER: "{name} unleashes a full-meter Super Move!",
    Action.BURST: "{name} triggers an emergency Burst to break free!",
    Action.BUILD: "{name} constructs a cover barrier in the arena.",
    Action.PICKUP: "{name} grabs a nearby arena item.",
    Action.SHIELD_FRONT: "{name} deploys a front energy shield wall.",
    Action.SHIELD_BACK: "{name} deploys a rear shield wall to stop corner push.",
}


def explain_action(action, obs, scores=None, personality=None):
    """Return a one-sentence reason for the chosen action.

    Every Action has a matching template; 'waiting' is only returned for IDLE.
    """
    name = personality.name if personality else "Fighter"

    if action == Action.IDLE:
        return f"{name} is waiting."

    if action == Action.LIGHT:
        if obs.enemy_is_stuck:
            return f"{name} attacked because the enemy is stuck after their attack."
        if obs.is_safe_poke:
            return f"{name} poked from safe range where the enemy can't reach."
        if obs.i_can_hit:
            return f"{name} attacked because the enemy is in range."
        return f"{name} threw a quick attack."

    if action == Action.HEAVY:
        if obs.enemy_is_stuck:
            return f"{name} used a heavy attack to punish the enemy's recovery."
        if obs.i_can_hit:
            return f"{name} threw a heavy attack for big damage."
        return f"{name} used a risky heavy attack."

    if action == Action.BLOCK:
        if obs.enemy_is_attacking:
            return f"{name} blocked to defend against the incoming attack."
        if obs.enemy_can_hit:
            return f"{name} is guarding because the enemy is in range."
        return f"{name} raised their guard cautiously."

    if action == Action.BLOCK_LOW:
        if obs.enemy_is_attacking:
            return f"{name} blocks low to defend against a low strike."
        return f"{name} holds a low guard to check sweeps."

    if action == Action.FORWARD:
        zone = zone_of(obs.distance)
        if zone == Zone.FAR:
            return f"{name} rushed forward because the enemy is far away."
        if obs.enemy_is_stuck:
            return f"{name} moved in to punish the enemy's recovery."
        return f"{name} advanced toward the enemy."

    if action == Action.BACK:
        if obs.i_am_cornered:
            return f"{name} tried to back away but is near the wall."
        return f"{name} backed away to create distance."

    if action == Action.DASH:
        if obs.enemy_is_stuck:
            return f"{name} dashes in to punish the opponent's recovery."
        return f"{name} dashes in to close the gap."

    if action == Action.BACKDASH:
        if obs.enemy_is_attacking:
            return f"{name} backs off to make space and evade the attack."
        return f"{name} backs off to make space."

    if action == Action.JUMP:
        if obs.i_am_cornered:
            return f"{name} jumped to escape the corner."
        if obs.enemy_is_attacking:
            return f"{name} jumped to dodge an attack."
        return f"{name} jumped."

    if action == Action.ANTI_AIR:
        if getattr(obs, "enemy_in_air", False):
            return f"{name} fires an anti-air to intercept the jump."
        return f"{name} throws a rising anti-air strike."

    if action == Action.THROW:
        if getattr(obs, "enemy_is_blocking", False):
            return f"{name} goes for a throw to break the opponent's guard."
        return f"{name} reaches in for a close-range throw."

    template = ACTION_TEMPLATES.get(action)
    if template is not None:
        return template.format(name=name)

    return f"{name} performs {action.name.lower().replace('_', ' ')}."


def commentary(obs, personality=None):
    """Return a short tactical commentary line about the fight situation."""
    name = personality.name if personality else "Fighter"
    lines = []

    if getattr(obs, "enemy_is_stuck", False):
        lines.append("Capitalizing on enemy recovery frames.")

    # Health
    if obs.my_health < 0.2:
        lines.append(f"{name} is in critical condition!")
    elif obs.my_health < 0.4:
        lines.append(f"{name} is low on health.")

    if obs.enemy_health < 0.2:
        lines.append("The opponent is nearly knocked out!")
    elif obs.enemy_health < 0.4:
        lines.append("The opponent is weakening.")

    # Health lead
    if obs.health_lead > 0.3:
        lines.append(f"{name} has a big health lead.")
    elif obs.health_lead < -0.3:
        lines.append(f"{name} is losing badly.")

    # Position
    if obs.i_am_cornered:
        lines.append(f"{name} is cornered!")
    if obs.enemy_is_cornered:
        lines.append("The opponent is cornered!")

    # Time
    if obs.time_running_out:
        if obs.health_lead > 0:
            lines.append(f"Time is running out — {name} is ahead!")
        elif obs.health_lead < 0:
            lines.append(f"Time is running out — {name} needs to attack!")
        else:
            lines.append("Time is running out with equal health!")

    if not lines:
        zone = zone_of(obs.distance)
        if zone == Zone.CLOSE:
            lines.append("Close-range fighting!")
        elif zone == Zone.FAR:
            lines.append("Both fighters are far apart.")
        else:
            lines.append("Mid-range standoff.")

    return " ".join(lines)


def evaluate_win_factors(obs):
    """Return (eval_score, top_chips) for the AI telemetry dashboard.

    eval_score is in [-1.0, +1.0].
    top_chips is a list of 3 short strings like '+12% spacing', '+8% frame adv'.
    """
    if obs is None:
        return 0.0, ["+0% neutral", "+0% spacing", "+0% meter"]

    factors = []

    # 1. Health advantage
    hp_diff = float(getattr(obs, "my_health", 1.0) - getattr(obs, "enemy_health", 1.0))
    hp_pct = int(round(hp_diff * 45))
    if hp_pct != 0:
        lbl = "HP lead" if hp_pct > 0 else "low HP"
        factors.append((abs(hp_pct), f"{hp_pct:+d}% {lbl}"))

    # 2. Frame advantage / punish window
    my_Wait = int(getattr(obs, "my_recovery", 0) + getattr(obs, "my_hitstun", 0) + getattr(obs, "my_blockstun", 0))
    en_Wait = int(getattr(obs, "enemy_recovery", 0) + getattr(obs, "enemy_hitstun", 0) + getattr(obs, "enemy_blockstun", 0))
    f_adv = en_Wait - my_Wait
    f_pct = max(-25, min(25, f_adv * 2))
    if f_pct != 0:
        factors.append((abs(f_pct), f"{f_pct:+d}% frame adv"))
    else:
        factors.append((4, "+4% frame even"))

    # 3. Spacing / corner positioning
    if getattr(obs, "enemy_is_cornered", False):
        factors.append((14, "+14% corner press"))
        pos_score = 0.14
    elif getattr(obs, "i_am_cornered", False):
        factors.append((14, "-14% cornered"))
        pos_score = -0.14
    else:
        dist = float(getattr(obs, "distance", 200.0))
        sp_pct = 10 if 90.0 <= dist <= 220.0 else (-6 if dist > 380.0 else 6)
        factors.append((abs(sp_pct), f"{sp_pct:+d}% spacing"))
        pos_score = sp_pct / 100.0

    # 4. Meter advantage
    m_diff = float(getattr(obs, "my_meter", 0.0) - getattr(obs, "enemy_meter", 0.0))
    m_pct = int(round(m_diff * 0.2))
    if abs(m_pct) >= 3:
        factors.append((abs(m_pct), f"{m_pct:+d}% meter"))

    factors.sort(key=lambda item: item[0], reverse=True)
    while len(factors) < 3:
        factors.append((2, "+2% tempo"))

    raw_eval = hp_diff * 0.65 + (f_pct / 100.0) * 0.8 + pos_score + (m_diff / 100.0) * 0.15
    eval_score = max(-1.0, min(1.0, raw_eval))
    chips = [c for _, c in factors[:3]]
    return eval_score, chips
