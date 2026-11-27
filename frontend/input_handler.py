"""Reads keyboard / gamepad input and converts it to an Action for a human player.

Player 1 keyboard (default):
  A / D  = Walk left / right (mapped to FORWARD / BACK based on facing)
  Double-tap A / D = Dash / Backdash
  W      = Jump (Jump Punch / Jump Kick in air)
  S      = Crouch (S + L = Low Block, S + J = Crouch Jab, S + U = Crouch Kick, S + I = Low Sweep)
  J      = Light Punch (Jab)
  K      = Heavy Punch (Forward + K = Overhead Strike, Down + K = Anti-Air)
  U      = Light Kick
  I      = Heavy Kick
  L      = High Block (Stand), Low Block (Crouch)
  O      = Special move (neutral, forward, back, down)
  P      = Super
  J + U  = Throw
  L + O  = Burst
  B      = Build cover (Arena Rumble)
  F      = Pick up item (Arena Rumble). E also picks up while Shield Wall is off.
  Q / E  = Shield Wall front / back

Player 2 keyboard (default, for local versus):
  Arrow keys = move / jump / crouch
  Numpad 4 5 1 2 = light punch, heavy punch, light kick, heavy kick
  Numpad 6 = block, 8 = special, 9 = super, 7 = build, 3 = pickup,
  Numpad 0 / . = shield front / back
  Laptop alternates (no numpad): , . / ; ' [ ] keys (see P2_KEY_BINDINGS).

Gamepad (SDL game-controller layout, Xbox names; hot-plug supported):
  D-pad / left stick = move, up = jump, down = crouch
  X = light punch, Y = heavy punch, A = light kick, B = heavy kick
  RB = block, LB = special, RT = super, LT = throw, R3 = build, L3 = pickup
  Back/View = burst, Start/Menu = pause (posts an Esc key event)

A 10-frame input buffer (BUFFER_WINDOW) remembers presses made slightly
early so they execute on the first actionable frame. Keys are rebindable from
Settings -> Controls; bindings are saved to data/controls.json.

API (stable contract used by the fight screen):
  InputHandler(key_bindings=None, player=1, controller_index=None)
  handler.get_action(enemy_x, my_x, in_air=False, can_act=True, keys=None,
                     enable_shield_wall=False) -> Action
"""

from __future__ import annotations

import json
import os
from collections import deque
from typing import Dict, Iterable, List, Optional, Union

import pygame

from backend.ai.actions import Action

BUFFER_WINDOW = 10       # Frames an input press is remembered (~0.17 s at 60 FPS)
DOUBLE_TAP_WINDOW = 16   # Frames between taps to register a dash
PAD_SCAN_INTERVAL = 45   # Frames between gamepad hot-plug scans
STICK_DEADZONE = 0.45

CONTROLS_PATH = os.path.join("data", "controls.json")

# Order + labels used by the rebinding UI.
ACTION_LABELS = {
    "left": "Move Left",
    "right": "Move Right",
    "jump": "Jump",
    "crouch": "Crouch",
    "light_punch": "Light Punch",
    "heavy_punch": "Heavy Punch",
    "light_kick": "Light Kick",
    "heavy_kick": "Heavy Kick",
    "block": "Block",
    "special": "Special",
    "super": "Super",
    "build": "Build Cover",
    "pickup": "Pick Up Item",
    "shield_front": "Shield Front",
    "shield_back": "Shield Back",
}
BINDABLE_ACTIONS = list(ACTION_LABELS)

# Player 1 default key map (action name -> pygame key constant).
DEFAULT_KEY_BINDINGS: Dict[str, int] = {
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
    "build": pygame.K_b,
    "pickup": pygame.K_f,
    "shield_front": pygame.K_q,
    "shield_back": pygame.K_e,
}

# Player 2 default key map: arrows + numpad, with laptop-friendly alternates.
P2_KEY_BINDINGS: Dict[str, List[int]] = {
    "left": [pygame.K_LEFT],
    "right": [pygame.K_RIGHT],
    "jump": [pygame.K_UP],
    "crouch": [pygame.K_DOWN],
    "light_punch": [pygame.K_KP4, pygame.K_COMMA],
    "heavy_punch": [pygame.K_KP5, pygame.K_PERIOD],
    "light_kick": [pygame.K_KP1, pygame.K_SEMICOLON],
    "heavy_kick": [pygame.K_KP2, pygame.K_QUOTE],
    "block": [pygame.K_KP6, pygame.K_SLASH],
    "special": [pygame.K_KP8, pygame.K_LEFTBRACKET],
    "super": [pygame.K_KP9, pygame.K_RIGHTBRACKET],
    "build": [pygame.K_KP7],
    "pickup": [pygame.K_KP3],
    "shield_front": [pygame.K_KP0],
    "shield_back": [pygame.K_KP_PERIOD],
}

Binding = Union[int, Iterable[int]]


def default_bindings(player: int = 1) -> Dict[str, Binding]:
    """Return a fresh copy of the default key map for player 1 or 2."""
    if player == 2:
        return {k: list(v) for k, v in P2_KEY_BINDINGS.items()}
    return dict(DEFAULT_KEY_BINDINGS)


def _as_key_list(value: Binding) -> List[int]:
    if isinstance(value, int):
        return [value]
    return [int(v) for v in value]


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------
def load_bindings(player: int = 1, path: Optional[str] = None) -> Dict[str, Binding]:
    """Saved bindings for `player` merged over the defaults (defaults if no file)."""
    merged = default_bindings(player)
    path = path or CONTROLS_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        saved = data.get(f"p{player}", {})
        for name, value in saved.items():
            if name in merged:
                keys = _as_key_list(value)
                if keys:
                    merged[name] = keys[0] if (player == 1 and len(keys) == 1) else keys
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return merged


def save_bindings(p1: Dict[str, Binding], p2: Optional[Dict[str, Binding]] = None,
                  path: Optional[str] = None) -> str:
    """Write bindings to data/controls.json and refresh the global handler."""
    path = path or CONTROLS_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = {"p1": {k: _as_key_list(v) for k, v in p1.items()}}
    if p2 is not None:
        data["p2"] = {k: _as_key_list(v) for k, v in p2.items()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    reload_global_bindings(path)
    return path


def _use_saved_bindings() -> bool:
    # Test runs always use the documented defaults, regardless of local files.
    return "PYTEST_CURRENT_TEST" not in os.environ


def key_name(code: int) -> str:
    """Short human-readable key label for the UI."""
    try:
        name = pygame.key.name(code)
    except Exception:
        name = str(code)
    name = name.replace("keypad ", "Num ").replace("[", "Num ").replace("]", "")
    return name.upper() if len(name) <= 2 else name.title()


# ----------------------------------------------------------------------
# Gamepad
# ----------------------------------------------------------------------
class _Gamepad:
    """Thin wrapper over SDL GameController (preferred) or a raw joystick."""

    # Game-controller button/axis ids (SDL_GameControllerButton).
    _BTN = {"a": 0, "b": 1, "x": 2, "y": 3, "back": 4, "start": 6,
            "l3": 7, "r3": 8, "lb": 9, "rb": 10,
            "up": 11, "down": 12, "left": 13, "right": 14}
    _AX_LX, _AX_LY, _AX_LT, _AX_RT = 0, 1, 4, 5

    def __init__(self, device, is_controller: bool):
        self.device = device
        self.is_controller = is_controller

    @staticmethod
    def open(index: int) -> Optional["_Gamepad"]:
        try:
            from pygame._sdl2 import controller as sdl_controller
            if not sdl_controller.get_init():
                sdl_controller.init()
            if index < sdl_controller.get_count() and sdl_controller.is_controller(index):
                return _Gamepad(sdl_controller.Controller(index), True)
        except Exception:
            pass
        try:
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            if index < pygame.joystick.get_count():
                joy = pygame.joystick.Joystick(index)
                joy.init()
                return _Gamepad(joy, False)
        except Exception:
            pass
        return None

    def attached(self) -> bool:
        try:
            if self.is_controller:
                return bool(self.device.attached())
            return bool(self.device.get_init())
        except Exception:
            return False

    def _button(self, name: str) -> bool:
        try:
            if self.is_controller:
                return bool(self.device.get_button(self._BTN[name]))
            # Generic joystick fallback: Xbox-style indices on most drivers.
            raw = {"a": 0, "b": 1, "x": 2, "y": 3, "lb": 4, "rb": 5,
                   "back": 6, "start": 7, "l3": 8, "r3": 9}
            if name in raw:
                idx = raw[name]
                return idx < self.device.get_numbuttons() and bool(self.device.get_button(idx))
            if name in ("up", "down", "left", "right") and self.device.get_numhats() > 0:
                hx, hy = self.device.get_hat(0)
                return {"up": hy > 0, "down": hy < 0, "left": hx < 0, "right": hx > 0}[name]
        except Exception:
            pass
        return False

    def _axis(self, idx: int) -> float:
        try:
            if self.is_controller:
                return self.device.get_axis(idx) / 32767.0
            if idx < self.device.get_numaxes():
                return float(self.device.get_axis(idx))
        except Exception:
            pass
        return 0.0

    def held(self) -> Dict[str, bool]:
        """Action-name -> held, using the fighting-game mapping in the module doc."""
        lx, ly = self._axis(self._AX_LX), self._axis(self._AX_LY)
        trig_scale = 1.0 if self.is_controller else 0.5
        lt = self._axis(self._AX_LT) * trig_scale if self.is_controller else 0.0
        rt = self._axis(self._AX_RT) * trig_scale if self.is_controller else 0.0
        return {
            "left": self._button("left") or lx < -STICK_DEADZONE,
            "right": self._button("right") or lx > STICK_DEADZONE,
            "jump": self._button("up") or ly < -0.6,
            "crouch": self._button("down") or ly > 0.6,
            "light_punch": self._button("x"),
            "heavy_punch": self._button("y"),
            "light_kick": self._button("a"),
            "heavy_kick": self._button("b"),
            "block": self._button("rb"),
            "special": self._button("lb"),
            "super": rt > 0.5,
            "throw": lt > 0.5,
            "build": self._button("r3"),
            "pickup": self._button("l3"),
            "burst": self._button("back"),
            "pause": self._button("start"),
            "shield_front": False,
            "shield_back": False,
        }


# ----------------------------------------------------------------------
# Input handler
# ----------------------------------------------------------------------
class InputHandler:
    """Processes keyboard + gamepad state into fight Actions with buffering and double-tap.

    key_bindings:     action -> key code (or list of key codes). None = the
                      saved bindings for `player` (data/controls.json) or the
                      defaults if nothing is saved.
    player:           1 (WASD/JKL layout) or 2 (arrows + numpad layout).
    controller_index: None = auto (player 1 uses pad 0, player 2 uses pad 1),
                      an int = that pad, -1 = keyboard only.
    """

    def __init__(self, key_bindings=None, player: int = 1, controller_index: Optional[int] = None):
        self.player = 2 if player == 2 else 1
        if key_bindings is None:
            key_bindings = load_bindings(self.player) if _use_saved_bindings() else default_bindings(self.player)
        self.bindings = dict(key_bindings)
        self.controller_index = controller_index
        self._pad: Optional[_Gamepad] = None
        self._pad_scan_frame = -PAD_SCAN_INTERVAL
        self._pad_prev: Dict[str, bool] = {}
        self.last_keys = set()
        self.last_tap_frame = {"left": -100, "right": -100}
        self.current_frame = 0
        self.buffer = deque()  # (Action, frame_recorded)

    # --- housekeeping -------------------------------------------------
    def set_bindings(self, key_bindings) -> None:
        self.bindings = dict(key_bindings)
        self.last_keys.clear()

    def reset(self):
        """Reset buffers and timestamps."""
        self.last_keys.clear()
        self._pad_prev = {}
        self.last_tap_frame = {"left": -100, "right": -100}
        self.current_frame = 0
        self.buffer.clear()

    def update_frame(self):
        """Advance frame count and clear expired buffered inputs."""
        self.current_frame += 1
        while self.buffer and (self.current_frame - self.buffer[0][1] > BUFFER_WINDOW):
            self.buffer.popleft()

    @property
    def gamepad_connected(self) -> bool:
        return self._pad is not None and self._pad.attached()

    def _poll_gamepad(self) -> Dict[str, bool]:
        if self.controller_index == -1:
            return {}
        if self._pad is not None and not self._pad.attached():
            self._pad = None  # unplugged
        if self._pad is None and self.current_frame - self._pad_scan_frame >= PAD_SCAN_INTERVAL:
            self._pad_scan_frame = self.current_frame
            idx = self.controller_index if self.controller_index is not None else self.player - 1
            self._pad = _Gamepad.open(idx)
        if self._pad is None:
            return {}
        return self._pad.held()

    # --- main entry point ---------------------------------------------
    def get_action(self, enemy_x: float, my_x: float, in_air: bool = False,
                   can_act: bool = True, keys=None, enable_shield_wall: bool = False) -> Action:
        """Evaluate key/pad states, buffer new presses, and return the chosen Action."""
        self.update_frame()
        if keys is None:
            keys = pygame.key.get_pressed()

        facing_right = enemy_x >= my_x

        def _down(code: int) -> bool:
            try:
                return bool(keys[code])
            except (IndexError, KeyError):
                return False

        # Held state per action name (keyboard OR gamepad).
        held: Dict[str, bool] = {}
        pressed_codes = set()
        for name, binding in self.bindings.items():
            codes = _as_key_list(binding)
            down_codes = [c for c in codes if _down(c)]
            held[name] = bool(down_codes)
            pressed_codes.update(down_codes)
        just_pressed = {
            name for name, binding in self.bindings.items()
            if any(_down(c) and c not in self.last_keys for c in _as_key_list(binding))
        }
        self.last_keys = pressed_codes

        # Legacy alias: the shield-back key also picks up items when Shield Wall is off.
        if not enable_shield_wall and "shield_back" in just_pressed:
            just_pressed.add("pickup")

        pad = self._poll_gamepad()
        pad_throw = pad_burst = False
        if pad:
            for name, is_down in pad.items():
                was = self._pad_prev.get(name, False)
                if name in ("throw", "burst", "pause"):
                    continue
                held[name] = held.get(name, False) or is_down
                if is_down and not was:
                    just_pressed.add(name)
            pad_throw = pad.get("throw", False) and not self._pad_prev.get("throw", False)
            pad_burst = pad.get("burst", False) and not self._pad_prev.get("burst", False)
            if pad.get("pause") and not self._pad_prev.get("pause"):
                try:
                    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE,
                                                         mod=0, unicode="", scancode=0))
                except Exception:
                    pass
            self._pad_prev = dict(pad)

        def h(name: str) -> bool:
            return held.get(name, False)

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

        new_action = None
        forward_held = (h("right") and facing_right) or (h("left") and not facing_right)
        back_held = (h("left") and facing_right) or (h("right") and not facing_right)

        # 1. Simultaneous combos (Throw = LP+LK, Burst = Block+Special) and pad shortcuts
        if pad_throw or ((h("light_punch") and h("light_kick")) and (
                "light_punch" in just_pressed or "light_kick" in just_pressed)):
            new_action = Action.THROW
        elif pad_burst or ((h("block") and h("special")) and (
                "block" in just_pressed or "special" in just_pressed)):
            new_action = Action.BURST
        # 2. Super
        elif "super" in just_pressed:
            new_action = Action.SUPER
        # 2.5 Shield Wall & Arena Rumble actions
        elif enable_shield_wall and "shield_front" in just_pressed:
            new_action = Action.SHIELD_FRONT
        elif enable_shield_wall and "shield_back" in just_pressed:
            new_action = Action.SHIELD_BACK
        elif "build" in just_pressed:
            new_action = Action.BUILD
        elif "pickup" in just_pressed:
            new_action = Action.PICKUP
        # 3. Specials (Special + direction)
        elif "special" in just_pressed:
            if h("crouch"):
                new_action = Action.SPECIAL_DOWN
            elif forward_held:
                new_action = Action.SPECIAL_FORWARD
            elif back_held:
                new_action = Action.SPECIAL_BACK
            else:
                new_action = Action.SPECIAL_NEUTRAL
        # 4. Air attacks
        elif in_air:
            if "light_punch" in just_pressed or "heavy_punch" in just_pressed:
                new_action = Action.JUMP_PUNCH
            elif "light_kick" in just_pressed or "heavy_kick" in just_pressed:
                new_action = Action.JUMP_KICK
        # 5. Crouching attacks
        elif h("crouch"):
            if "light_punch" in just_pressed:
                new_action = Action.CROUCH_JAB
            elif "light_kick" in just_pressed:
                new_action = Action.CROUCH_KICK
            elif "heavy_kick" in just_pressed:
                new_action = Action.LOW_SWEEP
            elif "heavy_punch" in just_pressed:
                new_action = Action.ANTI_AIR
        # 6. Standing attacks
        else:
            if "heavy_punch" in just_pressed:
                new_action = Action.OVERHEAD if forward_held else Action.HEAVY
            elif "heavy_kick" in just_pressed:
                new_action = Action.HEAVY_KICK
            elif "light_punch" in just_pressed:
                new_action = Action.LIGHT
            elif "light_kick" in just_pressed:
                new_action = Action.LIGHT_KICK

        if new_action is not None:
            # Burst (during hitstun) and Throw Tech (during grab) execute immediately
            if new_action in (Action.BURST, Action.THROW):
                return new_action
            self.buffer.append((new_action, self.current_frame))

        if is_dash:
            self.buffer.append((Action.DASH, self.current_frame))
        elif is_backdash:
            self.buffer.append((Action.BACKDASH, self.current_frame))

        # Jump press (ground jump + Shadow double-jump in air)
        if "jump" in just_pressed:
            self.buffer.append((Action.JUMP, self.current_frame))

        # If we can act, consume the freshest valid buffered action
        if can_act and self.buffer:
            action, _ = self.buffer.pop()
            return action

        # Held inputs (defence, walking, crouching)
        if h("block"):
            return Action.BLOCK_LOW if h("crouch") else Action.BLOCK
        if h("crouch"):
            return Action.CROUCH
        if h("right"):
            return Action.FORWARD if facing_right else Action.BACK
        if h("left"):
            return Action.BACK if facing_right else Action.FORWARD
        return Action.IDLE


# Global handler for convenient backward-compatible calls (player 1).
_global_handler = InputHandler()


def reload_global_bindings(path: Optional[str] = None) -> None:
    """Re-read saved bindings into the global player-1 handler (after rebinding)."""
    if _use_saved_bindings():
        _global_handler.set_bindings(load_bindings(1, path))


def current_bindings() -> Dict[str, Binding]:
    """Bindings currently used by the global player-1 handler (for on-screen help)."""
    return dict(_global_handler.bindings)


def get_human_action(enemy_x: float, my_x: float, in_air: bool = False,
                     can_act: bool = True, enable_shield_wall: bool = False) -> Action:
    """Backward-compatible functional interface for human action lookup (player 1)."""
    return _global_handler.get_action(
        enemy_x, my_x, in_air=in_air, can_act=can_act, enable_shield_wall=enable_shield_wall
    )
