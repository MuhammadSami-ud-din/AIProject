"""Central, cached font loading for every menu screen.

Three roles:
  display - condensed heavy face for titles and big numbers
  ui      - bold sans for buttons, labels and headers
  body    - regular sans for descriptions and table text

Each role tries a chain of system fonts (macOS / Windows / Linux names) and
falls back to the bundled DejaVu Sans files in frontend/assets/fonts/
(free license, see LICENSE_DEJAVU.txt) and finally to pygame's built-in
freesansbold. Fonts are created once per (role, size) and cached, so screens
can call `font("ui", 22)` every frame for free.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import pygame

_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")

_CHAINS = {
    "display": ("avenirnextcondensed", "dincondensed", "bahnschrift", "ubuntucondensed",
                "robotocondensed", "impact", "arialnarrow"),
    "ui": ("avenirnext", "segoeuisemibold", "segoeui", "ubuntu", "roboto", "arial"),
    "body": ("helveticaneue", "segoeui", "ubuntu", "roboto", "liberationsans", "arial"),
}
_BOLD_ROLES = {"display", "ui"}
_BUNDLED = {
    "display": "DejaVuSans-Bold.ttf",
    "ui": "DejaVuSans-Bold.ttf",
    "body": "DejaVuSans.ttf",
}

# Font(None, n) renders freesansbold at ~0.69 n; real TTFs at n px are larger.
# legacy_font() keeps old layouts (written for Font(None, n)) the same size.
LEGACY_SCALE = 0.70


def _ensure_init() -> None:
    if not pygame.font.get_init():
        pygame.font.init()


@lru_cache(maxsize=None)
def _resolve_path(role: str) -> Optional[str]:
    """Pick the first available font file for a role (cached for the process)."""
    _ensure_init()
    bold = role in _BOLD_ROLES
    for name in _CHAINS.get(role, ()):
        try:
            path = pygame.font.match_font(name, bold=bold)
        except Exception:
            path = None
        # match_font silently substitutes unrelated fonts on some platforms;
        # only accept files whose name resembles the request.
        if path and os.path.exists(path):
            stem = os.path.basename(path).lower().replace(" ", "").replace("-", "")
            if name[:6] in stem:
                return path
    bundled = os.path.join(_FONT_DIR, _BUNDLED.get(role, "DejaVuSans.ttf"))
    if os.path.exists(bundled):
        return bundled
    return None


_CACHE: dict = {}
_SENTINEL: list = []


def _cache_valid() -> bool:
    """False if pygame.font was quit/re-initialised since fonts were cached."""
    if not pygame.font.get_init():
        return False
    try:
        if not _SENTINEL:
            _SENTINEL.append(pygame.font.Font(None, 8))
        _SENTINEL[0].get_height()
        return True
    except Exception:
        return False


def font(role: str = "body", size: int = 20) -> pygame.font.Font:
    """Return a cached Font for a role at a real pixel size."""
    if not _cache_valid():
        _CACHE.clear()
        _SENTINEL.clear()
        _ensure_init()
    size = max(6, int(size))
    key = (role, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    path = _resolve_path(role)
    try:
        f = pygame.font.Font(path, size)
    except Exception:
        f = pygame.font.Font(None, int(size / LEGACY_SCALE))
    _CACHE[key] = f
    return f


def legacy_font(size: int, bold: bool = True) -> pygame.font.Font:
    """Drop-in replacement for pygame.font.Font(None, size): same visual size, nicer face."""
    return font("ui" if bold else "body", max(6, int(round(size * LEGACY_SCALE))))


def display(size: int) -> pygame.font.Font:
    return font("display", size)


def ui(size: int) -> pygame.font.Font:
    return font("ui", size)


def body(size: int) -> pygame.font.Font:
    return font("body", size)


def clear_cache() -> None:
    """Forget cached fonts (e.g. after pygame.quit/init in tests)."""
    _CACHE.clear()
    _SENTINEL.clear()
    _resolve_path.cache_clear()
