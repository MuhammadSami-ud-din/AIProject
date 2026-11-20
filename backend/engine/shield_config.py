"""Configuration and Balance Controls for the Shield Wall Ability.

All balance numeric values, timings, costs, multipliers, and preset profiles
live in this single file. Nothing elsewhere hard-codes any shield balance number.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ShieldBalance:
    """Frozen dataclass holding all balance controls for a fighter's shield wall."""

    shield_hp: float = 14.0
    duration_s: float = 1.0
    cooldown_s: float = 14.0
    energy_cost: float = 55.0          # Out of 100.0 max energy
    energy_regen_per_s: float = 6.0    # Passive regen per second
    max_shields: int = 1               # Front OR back, strictly max 1
    startup_frames: int = 8            # Startup delay before shield becomes solid
    break_stun_frames: int = 20        # Vulnerable stun applied when shield is broken
    heavy_chip_rate: float = 0.15      # 0% damage through for light, 15% through for heavy
    heavy_attack_bonus: float = 2.0    # Heavy attacks deal 2x damage against shields
    throws_ignore_shields: bool = True # Throws bypass shield completely and remove it
    attack_hp_drain: float = 3.0       # Drains 3 shield HP per attack while shield is up
    turtle_penalty: bool = True        # Regen halts while blocking AND a shield is active

    # Dimensions & Spacing
    width: float = 30.0                # 30 px wide
    height: float = 130.0              # 130 px tall
    offset_x: float = 45.0             # Horizontal distance from fighter center to shield center


# Clamping boundaries for custom player sliders in settings
SLIDER_RANGES = {
    "shield_hp": (10.0, 60.0),
    "duration_s": (1.0, 6.0),
    "cooldown_s": (3.0, 15.0),
    "energy_cost": (20.0, 60.0),
    "energy_regen_per_s": (2.0, 15.0),
}


# Balance Presets for the in-game settings menu
PRESETS: Dict[str, ShieldBalance] = {
    "Weak": ShieldBalance(
        shield_hp=15.0,
        duration_s=2.0,
        cooldown_s=8.0,
        energy_cost=45.0,
        energy_regen_per_s=5.0,
    ),
    "Normal": ShieldBalance(),  # Default balanced baseline
    "Strong": ShieldBalance(
        shield_hp=35.0,
        duration_s=4.0,
        cooldown_s=4.5,
        energy_cost=25.0,
        energy_regen_per_s=12.0,
    ),
}


def clamp_shield_balance(
    shield_hp: float,
    duration_s: float,
    cooldown_s: float,
    energy_cost: float,
    energy_regen_per_s: float,
    **kwargs: Any,
) -> ShieldBalance:
    """Clamp custom balance parameters into safe, balanced ranges."""
    c_hp = max(SLIDER_RANGES["shield_hp"][0], min(SLIDER_RANGES["shield_hp"][1], float(shield_hp)))
    c_dur = max(SLIDER_RANGES["duration_s"][0], min(SLIDER_RANGES["duration_s"][1], float(duration_s)))
    c_cd = max(SLIDER_RANGES["cooldown_s"][0], min(SLIDER_RANGES["cooldown_s"][1], float(cooldown_s)))
    c_cost = max(SLIDER_RANGES["energy_cost"][0], min(SLIDER_RANGES["energy_cost"][1], float(energy_cost)))
    c_reg = max(SLIDER_RANGES["energy_regen_per_s"][0], min(SLIDER_RANGES["energy_regen_per_s"][1], float(energy_regen_per_s)))

    return ShieldBalance(
        shield_hp=c_hp,
        duration_s=c_dur,
        cooldown_s=c_cd,
        energy_cost=c_cost,
        energy_regen_per_s=c_reg,
    )


def get_character_shield_balance(base: ShieldBalance, character_name: str) -> ShieldBalance:
    """Apply personality-specific balance adjustments to the base shield profile.

    - Steel: shield HP x1.3 (defensive fortress style).
    - Crimson: shield duration x0.7, but heavy attacks break shields faster (x2.5).
    - Shadow: startup 5 frames (faster deploy), but HP x0.7.
    - Golden: default values (tactical benchmark).
    """
    char = character_name.capitalize() if character_name else "Golden"

    if char == "Steel":
        return ShieldBalance(
            shield_hp=round(base.shield_hp * 1.3, 1),
            duration_s=base.duration_s,
            cooldown_s=base.cooldown_s,
            energy_cost=base.energy_cost,
            energy_regen_per_s=base.energy_regen_per_s,
            max_shields=base.max_shields,
            startup_frames=base.startup_frames,
            break_stun_frames=base.break_stun_frames,
            heavy_chip_rate=base.heavy_chip_rate,
            heavy_attack_bonus=base.heavy_attack_bonus,
            throws_ignore_shields=base.throws_ignore_shields,
            attack_hp_drain=base.attack_hp_drain,
            turtle_penalty=base.turtle_penalty,
            width=base.width,
            height=base.height,
            offset_x=base.offset_x,
        )
    elif char == "Crimson":
        return ShieldBalance(
            shield_hp=base.shield_hp,
            duration_s=round(base.duration_s * 0.7, 2),
            cooldown_s=base.cooldown_s,
            energy_cost=base.energy_cost,
            energy_regen_per_s=base.energy_regen_per_s,
            max_shields=base.max_shields,
            startup_frames=base.startup_frames,
            break_stun_frames=base.break_stun_frames,
            heavy_chip_rate=base.heavy_chip_rate,
            heavy_attack_bonus=2.5,  # Crimson heavy attacks break shields 25% faster
            throws_ignore_shields=base.throws_ignore_shields,
            attack_hp_drain=base.attack_hp_drain,
            turtle_penalty=base.turtle_penalty,
            width=base.width,
            height=base.height,
            offset_x=base.offset_x,
        )
    elif char == "Shadow":
        return ShieldBalance(
            shield_hp=round(base.shield_hp * 0.7, 1),
            duration_s=base.duration_s,
            cooldown_s=base.cooldown_s,
            energy_cost=base.energy_cost,
            energy_regen_per_s=base.energy_regen_per_s,
            max_shields=base.max_shields,
            startup_frames=5,  # Shadow faster deploy: 5 frames instead of 8
            break_stun_frames=base.break_stun_frames,
            heavy_chip_rate=base.heavy_chip_rate,
            heavy_attack_bonus=base.heavy_attack_bonus,
            throws_ignore_shields=base.throws_ignore_shields,
            attack_hp_drain=base.attack_hp_drain,
            turtle_penalty=base.turtle_penalty,
            width=base.width,
            height=base.height,
            offset_x=base.offset_x,
        )
    else:  # Golden or default
        return base
