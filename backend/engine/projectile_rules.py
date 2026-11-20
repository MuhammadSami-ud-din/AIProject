"""Limits on shooting so fighters also have to fight by hitting.

A fighter may shoot only when:
  - the shot cooldown is over,
  - none of their earlier shots is still flying,
  - they have not used up the shots allowed in this round.
"""

from backend.engine.constants import (
    PROJECTILE_COOLDOWN_FRAMES,
    PROJECTILE_MAX_ACTIVE,
    PROJECTILE_MAX_PER_ROUND,
)


def can_fire_projectile(fighter, projectiles, owner_id: int) -> bool:
    """True when this fighter is allowed to start a projectile move now."""
    if fighter.projectile_cooldown > 0:
        return False
    if fighter.shots_fired >= PROJECTILE_MAX_PER_ROUND:
        return False
    active = sum(1 for p in projectiles if p.owner == owner_id and not p.reflected)
    return active < PROJECTILE_MAX_ACTIVE


def register_shot(fighter) -> None:
    """Count a shot that has just been started."""
    fighter.projectile_cooldown = PROJECTILE_COOLDOWN_FRAMES
    fighter.shots_fired += 1
