"""Mode rules and toggleable mechanics flags.

Classic mode has ALL flags turned OFF.
Arena Rumble mode sets is_rumble=True and can toggle individual mechanics:
- enable_zone: Shrinking zone ('The Squeeze')
- enable_building: Cover wall placement and build charges
- enable_loot: Ground item pickups and supply drops
- enable_objects: Destructible crates, jump pads, and spike traps
"""

from dataclasses import dataclass, field
from typing import Optional
from backend.engine.shield_config import ShieldBalance


@dataclass
class ModeRules:
    """Mode configuration and toggles for fight mechanics."""

    is_rumble: bool = False
    enable_zone: bool = False
    enable_building: bool = False
    enable_loot: bool = False
    enable_objects: bool = False
    arena_name: str = "Dojo"
    auto_pickup: bool = True  # Automatic pickup on walkover vs manual E key

    # Shield Wall Ability Settings (Steps 1-3)
    enable_shield_wall: bool = False
    shield_preset: str = "Normal"
    same_shield_for_both: bool = True
    shield_balance_p1: ShieldBalance = field(default_factory=ShieldBalance)
    shield_balance_p2: ShieldBalance = field(default_factory=ShieldBalance)

    @classmethod
    def classic(cls, enable_shield_wall: bool = False,
                shield_balance_p1: Optional[ShieldBalance] = None,
                shield_balance_p2: Optional[ShieldBalance] = None) -> "ModeRules":
        """Classic standard 1v1 fighting rules: all rumble mechanics disabled."""
        return cls(
            is_rumble=False,
            enable_zone=False,
            enable_building=False,
            enable_loot=False,
            enable_objects=False,
            enable_shield_wall=enable_shield_wall,
            shield_balance_p1=shield_balance_p1 or ShieldBalance(),
            shield_balance_p2=shield_balance_p2 or ShieldBalance(),
        )

    @classmethod
    def rumble(
        cls,
        enable_zone: bool = True,
        enable_building: bool = True,
        enable_loot: bool = True,
        enable_objects: bool = True,
        arena_name: str = "Dojo",
        auto_pickup: bool = True,
        enable_shield_wall: bool = False,
    ) -> "ModeRules":
        """Arena Rumble mode with optional toggleable mechanics."""
        return cls(
            is_rumble=True,
            enable_zone=enable_zone,
            enable_building=enable_building,
            enable_loot=enable_loot,
            enable_objects=enable_objects,
            arena_name=arena_name,
            auto_pickup=auto_pickup,
            enable_shield_wall=enable_shield_wall,
        )

    def copy(self) -> "ModeRules":
        return ModeRules(
            is_rumble=self.is_rumble,
            enable_zone=self.enable_zone,
            enable_building=self.enable_building,
            enable_loot=self.enable_loot,
            enable_objects=self.enable_objects,
            arena_name=self.arena_name,
            auto_pickup=self.auto_pickup,
            enable_shield_wall=self.enable_shield_wall,
            shield_preset=self.shield_preset,
            same_shield_for_both=self.same_shield_for_both,
            shield_balance_p1=self.shield_balance_p1,
            shield_balance_p2=self.shield_balance_p2,
        )
