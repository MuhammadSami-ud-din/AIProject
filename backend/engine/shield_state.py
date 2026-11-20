"""Data structures for the Shield Wall ability."""

from dataclasses import dataclass


@dataclass
class ShieldWallState:
    """Represents an active energy shield panel deployed by a fighter."""

    owner: int                  # 1 for P1, 2 for P2
    side: str                   # "front" or "back"
    x: float                    # Horizontal center position in arena
    y: float = 0.0              # Ground elevation (0.0 = floor)
    width: float = 30.0         # 30 px wide
    height: float = 130.0       # 130 px tall
    hp: float = 25.0
    max_hp: float = 25.0
    duration_frames: int = 180  # Frames remaining before natural expiry
    created_frame: int = 0

    @property
    def left(self) -> float:
        return self.x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width / 2.0

    def copy(self) -> "ShieldWallState":
        return ShieldWallState(
            owner=self.owner,
            side=self.side,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            hp=self.hp,
            max_hp=self.max_hp,
            duration_frames=self.duration_frames,
            created_frame=self.created_frame,
        )
