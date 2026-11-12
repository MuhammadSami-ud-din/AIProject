"""The complete snapshot of a fight at one moment in time.

FighterState holds one fighter's body (position, health, timers).
FightState holds both fighters plus the round/match bookkeeping.
Both are plain dataclasses so the step() function can copy and update them.
"""

from dataclasses import dataclass, field

from backend.ai.actions import Action
from backend.engine.constants import ARENA_WIDTH, ROUND_FRAMES


# ---------------------------------------------------------------
# One fighter's body
# ---------------------------------------------------------------

@dataclass
class FighterState:
    """Everything about one fighter's body right now."""

    x: float = 0.0                # position in pixels (0 = left wall)
    health: float = 1.0           # 0.0 = dead, 1.0 = full

    # Attack timers (in frames, 0 = free)
    cooldown: int = 0             # frames until this fighter can attack again
    recovery: int = 0             # frames this fighter is stuck after attacking

    # Attack phase tracking
    # phase: "none", "startup", "active", "recovery"
    attack_phase: str = "none"
    attack_frames_left: int = 0   # frames left in the current attack phase
    attack_type: str = "none"     # "light" or "heavy" or "none"

    # Jumping
    in_air: bool = False
    jump_frame: int = 0           # which frame of the jump we are on (0 = on ground)

    # What this fighter did last frame
    last_action: Action = Action.IDLE

    # Which character this fighter is (for looking up body stats)
    character_name: str = "Golden"

    def copy(self):
        """A fresh copy that can be changed without touching the original."""
        return FighterState(
            x=self.x,
            health=self.health,
            cooldown=self.cooldown,
            recovery=self.recovery,
            attack_phase=self.attack_phase,
            attack_frames_left=self.attack_frames_left,
            attack_type=self.attack_type,
            in_air=self.in_air,
            jump_frame=self.jump_frame,
            last_action=self.last_action,
            character_name=self.character_name,
        )


# ---------------------------------------------------------------
# The whole fight
# ---------------------------------------------------------------

@dataclass
class FightState:
    """Everything about the fight right now: both fighters plus bookkeeping."""

    fighter1: FighterState = field(default_factory=FighterState)
    fighter2: FighterState = field(default_factory=FighterState)

    frame: int = 0                         # current frame number in this round
    round_number: int = 1                  # which round we are in (starts at 1)
    round_frames_left: int = ROUND_FRAMES  # frames left in this round

    p1_rounds_won: int = 0
    p2_rounds_won: int = 0

    round_over: bool = False       # True when the current round just ended
    match_over: bool = False       # True when the whole match is done
    round_result: str = "none"     # "p1", "p2", "draw", or "none"
    match_result: str = "none"     # "p1", "p2", "draw", or "none"

    def copy(self):
        """A fresh copy of the entire fight state."""
        return FightState(
            fighter1=self.fighter1.copy(),
            fighter2=self.fighter2.copy(),
            frame=self.frame,
            round_number=self.round_number,
            round_frames_left=self.round_frames_left,
            p1_rounds_won=self.p1_rounds_won,
            p2_rounds_won=self.p2_rounds_won,
            round_over=self.round_over,
            match_over=self.match_over,
            round_result=self.round_result,
            match_result=self.match_result,
        )
