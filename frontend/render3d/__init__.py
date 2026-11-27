"""Real-3D "2.5D" fight renderer (moderngl, offscreen) for the pygame fight screen.

Usage::

    from frontend.render3d import create_renderer
    r3d = create_renderer(1024, 600)          # None if OpenGL is unavailable
    if r3d:
        r3d.setup("Crimson", "Steel", "arena_golden_temple")
        r3d.push_step(prev_state, state)      # after every engine step
        surf = r3d.render(state, frac, dt)    # pygame.Surface, blit then draw HUD

The gameplay stays 2D: engine x -> world X on the fighting plane, jump height ->
world Y.  If no GL context can be created the caller falls back to the 2D sprite
renderer (frontend.draw_fighter).
"""

import os

_FAILED = False
_LAST_ERROR = ""


def gl_available() -> bool:
    """True if a standalone OpenGL 3.3 context can be created on this machine."""
    global _FAILED, _LAST_ERROR
    if _FAILED:
        return False
    if os.environ.get("FIGHT_RENDERER", "").lower() == "2d":
        return False
    try:
        import moderngl
        ctx = moderngl.create_standalone_context(require=330)
        ctx.release()
        return True
    except Exception as exc:  # pragma: no cover - depends on the machine
        _FAILED = True
        _LAST_ERROR = repr(exc)
        return False


def create_renderer(width: int = 1024, height: int = 600, samples: int = 4):
    """Create the 3D renderer, or return None (with the reason in last_error())."""
    global _FAILED, _LAST_ERROR
    if _FAILED or os.environ.get("FIGHT_RENDERER", "").lower() == "2d":
        return None
    try:
        from frontend.render3d.renderer import Renderer3D
        return Renderer3D(width, height, samples=samples)
    except Exception as exc:
        _FAILED = True
        _LAST_ERROR = repr(exc)
        return None


def last_error() -> str:
    return _LAST_ERROR


def reset_failure():
    """Allow another attempt (used by tests)."""
    global _FAILED, _LAST_ERROR
    _FAILED = False
    _LAST_ERROR = ""
