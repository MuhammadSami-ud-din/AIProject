"""Reads keyboard input and converts it to an Action for the human player.

Controls:
  A / D  = Walk left / right (mapped to FORWARD / BACK based on facing)
  Double-tap A / D = Dash / Backdash
  W      = Jump (Jump Punch / Jump Kick in air)
  S      = Crouch (Hold S + L = Low Block, S + J = Crouch Jab, S + U = Crouch Kick, S + I = Low Sweep)
  J      = Light Punch (Jab)
  K      = Heavy Punch (Forward + K = Overhead Strike, Down-Forward + K = Anti-Air)
  U      = Light Kick
  I      = Heavy Kick
  L      = High Block (Stand), Low Block (Crouch)
  O      = Special move (neutral, forward, back, down)
  P      = Super
  J + U  = Throw
  L + O  = Burst

Features a 6-frame input buffer so inputs pressed early execute cleanly on the
first actionable frame. Keys are rebindable.
"""

from collections import deque
import pygame

from backend.ai.actions import Action

BUFFER_WINDOW = 6        # Frames an input press is remembered
DOUBLE_TAP_WINDOW = 16   # Frames between taps to register a dash


# Rebindable key map (action name -> pygame key constant)
DEFAULT_KEY_BINDINGS = {
    "left": pygame.K_a,
    "right": pygame.K_d,
    "jump": pygame.K_w,
    "crouch": pygame.K_s,
    "light_punch": pygame.K_j,
    "heavy_punch": pygame.K_k,
    "light_kick": pygame.K_u,
    "heavy_kick": pygame.K_i,
    "block": pygame.K_l,
    "special": pygame.K_o,
    "super": pygame.K_p,
}


class InputHandler:
    """Processes raw keyboard inputs into fight Actions with buffering and double-tap."""

    def __init__(self, key_bindings=None):
        self.bindings = dict(key_bindings or DEFAULT_KEY_BINDINGS)
        self.last_keys = set()
        self.last_tap_frame = {"left": -100, "right": -100}
        self.current_frame = 0
        self.buffer = deque()  # list of (Action, frame_recorded)

    def reset(self):
        """Reset buffers and timestamps."""
        self.last_keys.clear()
        self.last_tap_frame = {"left": -100, "right": -100}
        self.current_frame = 0
        self.buffer.clear()

    def update_frame(self):
        """Advance frame count and clear expired buffered inputs."""
        self.current_frame += 1
        while self.buffer and (self.current_frame - self.buffer[0][1] > BUFFER_WINDOW):
            self.buffer.popleft()

    def get_action(self, enemy_x: float, my_x: float, in_air: bool = False,
                   can_act: bool = True) -> Action:
        """Evaluate key states, buffer new presses, and return the chosen Action."""
        self.update_frame()
        keys = pygame.key.get_pressed()

        b = self.bindings
        facing_right = enemy_x >= my_x

        # Detect newly pressed keys this frame
        just_pressed = {
            name for name, key_code in b.items()
            if keys[key_code] and key_code not in self.last_keys
        }
        self.last_keys = {key_code for key_code in b.values() if keys[key_code]}

        # Check double-taps for Dash / Backdash
        is_dash = False
        is_backdash = False

        if "right" in just_pressed:
            if self.current_frame - self.last_tap_frame["right"] <= DOUBLE_TAP_WINDOW:
                if facing_right:
                    is_dash = True
                else:
                    is_backdash = True
            self.last_tap_frame["right"] = self.current_frame

        if "left" in just_pressed:
            if self.current_frame - self.last_tap_frame["left"] <= DOUBLE_TAP_WINDOW:
                if facing_right:
                    is_backdash = True
                else:
                    is_dash = True
            self.last_tap_frame["left"] = self.current_frame

        # Resolve newly pressed action
        new_action = None

        # 1. Simultaneous Combos (Throw = J+U, Burst = L+O)
        if (keys[b["light_punch"]] and keys[b["light_kick"]]) and (
                "light_punch" in just_pressed or "light_kick" in just_pressed):
            new_action = Action.THROW

        elif (keys[b["block"]] and keys[b["special"]]) and (
                "block" in just_pressed or "special" in just_pressed):
            new_action = Action.BURST

        # 2. Super (P)
        elif "super" in just_pressed:
            new_action = Action.SUPER

        # 3. Specials (O + Direction)
        elif "special" in just_pressed:
            if keys[b["crouch"]]:
                new_action = Action.SPECIAL_DOWN
            elif (keys[b["right"]] and facing_right) or (keys[b["left"]] and not facing_right):
                new_action = Action.SPECIAL_FORWARD
            elif (keys[b["left"]] and facing_right) or (keys[b["right"]] and not facing_right):
                new_action = Action.SPECIAL_BACK
            else:
                new_action = Action.SPECIAL_NEUTRAL

        # 4. Air Attacks
        elif in_air:
            if "light_punch" in just_pressed:
                new_action = Action.JUMP_PUNCH
            elif "light_kick" in just_pressed or "heavy_kick" in just_pressed:
                new_action = Action.JUMP_KICK
            elif "heavy_punch" in just_pressed:
                new_action = Action.JUMP_PUNCH

        # 5. Ground Attacks & Normals
        elif keys[b["crouch"]]:
            # Crouching attacks
            if "light_punch" in just_pressed:
                new_action = Action.CROUCH_JAB
            elif "light_kick" in just_pressed:
                new_action = Action.CROUCH_KICK
            elif "heavy_kick" in just_pressed:
                new_action = Action.LOW_SWEEP
            elif "heavy_punch" in just_pressed:
                new_action = Action.ANTI_AIR

        else:
            # Standing directional attacks
            forward_held = (keys[b["right"]] and facing_right) or (keys[b["left"]] and not facing_right)
            if "heavy_punch" in just_pressed:
                if forward_held:
                    new_action = Action.OVERHEAD
                else:
                    new_action = Action.HEAVY
            elif "heavy_kick" in just_pressed:
                new_action = Action.HEAVY_KICK
            elif "light_punch" in just_pressed:
                new_action = Action.LIGHT
            elif "light_kick" in just_pressed:
                new_action = Action.LIGHT_KICK

        # If an attack/tech action was pressed, push into buffer
        if new_action is not None:
            self.buffer.append((new_action, self.current_frame))

        # Check double-tap dashes
        if is_dash:
            self.buffer.append((Action.DASH, self.current_frame))
        elif is_backdash:
            self.buffer.append((Action.BACKDASH, self.current_frame))

        # Check jump press
        if "jump" in just_pressed and not in_air:
            self.buffer.append((Action.JUMP, self.current_frame))

        # If we can act, consume the freshest valid buffered action
        if can_act and self.buffer:
            action, _ = self.buffer.pop()
            return action

        # Continuous / Held inputs (Defense & Walking & Crouching)
        if keys[b["block"]]:
            if keys[b["crouch"]]:
                return Action.BLOCK_LOW
            return Action.BLOCK

        if keys[b["crouch"]]:
            return Action.CROUCH

        if keys[b["right"]]:
            return Action.FORWARD if facing_right else Action.BACK
        if keys[b["left"]]:
            return Action.BACK if facing_right else Action.FORWARD

        return Action.IDLE


# Global handler for convenient backward-compatible calls
_global_handler = InputHandler()


def get_human_action(enemy_x: float, my_x: float, in_air: bool = False,
                     can_act: bool = True) -> Action:
    """Backward-compatible functional interface for human action lookup."""
    return _global_handler.get_action(enemy_x, my_x, in_air=in_air, can_act=can_act)
