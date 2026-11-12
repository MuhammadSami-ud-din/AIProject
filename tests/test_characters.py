"""Tests for character body stats and the helper functions that apply them."""

import pytest

from backend.engine.constants import (
    BLOCK_DAMAGE_RATIO,
    HEAVY_ATTACK,
    LIGHT_ATTACK,
    WALK_SPEED,
)
from backend.engine.characters import (
    CHARACTER_STATS,
    CRIMSON_STATS,
    GOLDEN_STATS,
    SHADOW_STATS,
    STEEL_STATS,
    adjusted_attack,
    heavy_attack_for,
    light_attack_for,
    walk_speed,
)


# --- All four fighters exist ----------------------------------------

def test_four_fighters_exist():
    assert set(CHARACTER_STATS) == {"Crimson", "Steel", "Shadow", "Golden"}


def test_lookup_by_name():
    assert CHARACTER_STATS["Crimson"] is CRIMSON_STATS
    assert CHARACTER_STATS["Steel"] is STEEL_STATS
    assert CHARACTER_STATS["Shadow"] is SHADOW_STATS
    assert CHARACTER_STATS["Golden"] is GOLDEN_STATS


# --- Crimson: high damage, short reach ------------------------------

def test_crimson_damage_multiplier():
    assert CRIMSON_STATS.damage_mult == 1.2


def test_crimson_reach_multiplier():
    assert CRIMSON_STATS.reach_mult == 0.9


def test_crimson_light_damage():
    """Crimson's light does 0.05 * 1.2 = 0.06."""
    attack = light_attack_for(CRIMSON_STATS)
    assert attack.damage == pytest.approx(0.06)


def test_crimson_light_reach():
    """Crimson's light reaches 70 * 0.9 = 63 px."""
    attack = light_attack_for(CRIMSON_STATS)
    assert attack.reach == pytest.approx(63)


def test_crimson_heavy_damage():
    """Crimson's heavy does 0.12 * 1.2 = 0.144."""
    attack = heavy_attack_for(CRIMSON_STATS)
    assert attack.damage == pytest.approx(0.144)


# --- Steel: halved block damage -------------------------------------

def test_steel_blocked_damage_ratio():
    """Steel takes half of the normal block chip damage (5% instead of 10%)."""
    assert STEEL_STATS.blocked_damage_ratio == pytest.approx(0.05)


def test_steel_normal_stats():
    """Steel has no damage, reach, or speed changes."""
    assert STEEL_STATS.damage_mult == 1.0
    assert STEEL_STATS.reach_mult == 1.0
    assert STEEL_STATS.speed_mult == 1.0


# --- Shadow: fast, long arms, soft hits -----------------------------

def test_shadow_speed():
    assert SHADOW_STATS.speed_mult == 1.3


def test_shadow_walk_speed():
    """Shadow walks at 4 * 1.3 = 5.2 px per frame."""
    assert walk_speed(SHADOW_STATS) == pytest.approx(5.2)


def test_shadow_reach():
    """Shadow's light reaches 70 * 1.15 = 80.5 px."""
    attack = light_attack_for(SHADOW_STATS)
    assert attack.reach == pytest.approx(80.5)


def test_shadow_damage():
    """Shadow's light does 0.05 * 0.85 = 0.0425."""
    attack = light_attack_for(SHADOW_STATS)
    assert attack.damage == pytest.approx(0.0425)


# --- Golden: perfectly average ---------------------------------------

def test_golden_is_default():
    """Golden has 1.0 for every multiplier."""
    assert GOLDEN_STATS.damage_mult == 1.0
    assert GOLDEN_STATS.reach_mult == 1.0
    assert GOLDEN_STATS.speed_mult == 1.0
    assert GOLDEN_STATS.blocked_damage_ratio == BLOCK_DAMAGE_RATIO


def test_golden_light_unchanged():
    attack = light_attack_for(GOLDEN_STATS)
    assert attack.damage == LIGHT_ATTACK.damage
    assert attack.reach == LIGHT_ATTACK.reach


# --- adjusted_attack keeps timing the same ---------------------------

def test_adjusted_attack_keeps_startup():
    """Multipliers change damage and reach, never the frame timing."""
    original = LIGHT_ATTACK
    changed = adjusted_attack(original, CRIMSON_STATS)
    assert changed.startup == original.startup
    assert changed.active == original.active
    assert changed.recovery == original.recovery
    assert changed.cooldown == original.cooldown


# --- walk_speed helper -----------------------------------------------

def test_walk_speed_default():
    assert walk_speed(GOLDEN_STATS) == WALK_SPEED


def test_walk_speed_crimson():
    """Crimson has no speed change, so walks at the base speed."""
    assert walk_speed(CRIMSON_STATS) == WALK_SPEED


# --- Stats are frozen ------------------------------------------------

def test_stats_cannot_be_changed():
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        CRIMSON_STATS.damage_mult = 999
