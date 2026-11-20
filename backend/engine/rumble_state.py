"""Rumble-specific state structures for Arena Rumble mode.

Contains state dataclasses for:
- ZoneState: The Squeeze (shrinking energy barrier)
- WallState: Placed cover wall blocks
- ItemState: Ground loot items
- SupplyDropState: Falling supply drop crates
- ArenaObjectState: Crates, jump pads, and spike traps
- KillFeedMessage: Event log messages
"""

from dataclasses import dataclass, field
from typing import Optional

from backend.engine.rumble_config import (
    ARENA_LAYOUTS,
    BUILD_START_CHARGES,
    CRATE_MAX_HP,
    CRATE_WIDTH,
    CRATE_HEIGHT,
    JUMP_PAD_WIDTH,
    JUMP_PAD_HEIGHT,
    LOOT_PICKUP_RADIUS,
    SHIELD_MAX_HP,
    TRAP_WIDTH,
    TRAP_HEIGHT,
    WALL_HEIGHT,
    WALL_MAX_HP,
    WALL_WIDTH,
    ZONE_STAGE_CYCLE_FRAMES,
    ZONE_STAGE_DPS,
    ZONE_STAGES,
    ZONE_WARNING_FRAMES,
)


@dataclass
class ZoneState:
    """The shrinking barrier state."""

    left: float = 0.0
    right: float = 800.0
    stage: int = 1                     # 1 to 4
    is_closing: bool = False           # False = pause phase, True = closing phase
    is_warning: bool = False           # True 5s before closing
    phase_frame: int = 0               # Frame counter within current pause/close
    target_left: float = 65.0          # Target left edge for this stage
    target_right: float = 735.0        # Target right edge for this stage
    closed_stages: int = 0             # Number of completed close stages

    def copy(self) -> "ZoneState":
        return ZoneState(
            left=self.left,
            right=self.right,
            stage=self.stage,
            is_closing=self.is_closing,
            is_warning=self.is_warning,
            phase_frame=self.phase_frame,
            target_left=self.target_left,
            target_right=self.target_right,
            closed_stages=self.closed_stages,
        )


@dataclass
class WallState:
    """A player-built vertical cover wall."""

    id: int
    owner: int                         # 1 for P1, 2 for P2
    x: float                           # Center x position
    y: float = 0.0                     # Ground y position
    hp: float = WALL_MAX_HP
    max_hp: float = WALL_MAX_HP
    width: float = WALL_WIDTH
    height: float = WALL_HEIGHT
    created_frame: int = 0

    @property
    def left(self) -> float:
        return self.x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width / 2.0

    @property
    def crack_stage(self) -> int:
        """0 = pristine, 1 = cracked (<= 66%), 2 = heavy cracked (<= 33%)."""
        ratio = self.hp / self.max_hp
        if ratio <= 0.33:
            return 2
        if ratio <= 0.66:
            return 1
        return 0

    def copy(self) -> "WallState":
        return WallState(
            id=self.id,
            owner=self.owner,
            x=self.x,
            y=self.y,
            hp=self.hp,
            max_hp=self.max_hp,
            width=self.width,
            height=self.height,
            created_frame=self.created_frame,
        )


@dataclass
class ItemState:
    """A ground loot item that can be picked up."""

    id: int
    item_type: str                     # "medkit", "shield_cell", "meter_orb", "build_kit", "speed_boots", "power_fist", "big_medkit", "overcharge"
    x: float
    y: float = 0.0
    radius: float = LOOT_PICKUP_RADIUS
    spawn_frame: int = 0

    def copy(self) -> "ItemState":
        return ItemState(
            id=self.id,
            item_type=self.item_type,
            x=self.x,
            y=self.y,
            radius=self.radius,
            spawn_frame=self.spawn_frame,
        )


@dataclass
class SupplyDropState:
    """A falling crate supply drop."""

    id: int
    item_type: str                     # "big_medkit" or "overcharge"
    x: float
    y: float                           # Starts above screen (e.g. -100), drops to floor
    target_y: float = 0.0              # Floor level
    is_landed: bool = False
    shadow_alpha: float = 1.0

    def copy(self) -> "SupplyDropState":
        return SupplyDropState(
            id=self.id,
            item_type=self.item_type,
            x=self.x,
            y=self.y,
            target_y=self.target_y,
            is_landed=self.is_landed,
            shadow_alpha=self.shadow_alpha,
        )


@dataclass
class ArenaObjectState:
    """Static or interactive arena object (Crate, Jump Pad, Trap)."""

    id: int
    object_type: str                   # "crate", "jump_pad", "trap"
    x: float
    y: float = 0.0
    width: float = 40.0
    height: float = 40.0
    hp: float = CRATE_MAX_HP
    max_hp: float = CRATE_MAX_HP
    cooldown: int = 0
    trigger_timer: int = 0             # Countdown for trap trigger (warning glow)
    is_triggered: bool = False

    @property
    def left(self) -> float:
        return self.x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width / 2.0

    def copy(self) -> "ArenaObjectState":
        return ArenaObjectState(
            id=self.id,
            object_type=self.object_type,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            hp=self.hp,
            max_hp=self.max_hp,
            cooldown=self.cooldown,
            trigger_timer=self.trigger_timer,
            is_triggered=self.is_triggered,
        )


@dataclass
class KillFeedMessage:
    """Event message shown in the corner feed."""

    text: str
    color: tuple[int, int, int] = (255, 255, 255)
    lifetime: int = 180  # 3 seconds @ 60 FPS

    def copy(self) -> "KillFeedMessage":
        return KillFeedMessage(
            text=self.text,
            color=self.color,
            lifetime=self.lifetime,
        )
