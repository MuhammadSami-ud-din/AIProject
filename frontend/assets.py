"""Asset management: safe loading, caching, scaling, and fallbacks.

Ensures:
  1. Every image is loaded and scaled ONCE at startup, never per-frame.
  2. Accepts .png, .jpg, and .jpeg extensions.
  3. If an image is missing or corrupted, renders an attractive gradient
     placeholder with the asset name and keeps running (never crashes).
  4. Automatically generates a blurred menu background if intro_blur is absent.
  5. Manages arena rotation (seed-based, non-repeating, Sky Colosseum for HELL).
"""

import os
import random
from typing import Dict, List, Optional, Tuple
import pygame

from frontend.theme import FLOOR_HEIGHT, SCREEN_HEIGHT, SCREEN_WIDTH


# Base asset directory
ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
SCREENS_DIR = os.path.join(ASSET_DIR, "screens")
PORTRAITS_DIR = os.path.join(ASSET_DIR, "portraits")
BACKGROUNDS_DIR = os.path.join(ASSET_DIR, "backgrounds")

# Supported file extensions in order of preference
EXTENSIONS = (".jpeg", ".jpg", ".png")

# Arenas definition
NORMAL_ARENAS: List[str] = [
    "arena_neon_rooftop",
    "arena_volcanic_forge",
    "arena_iron_foundry",
    "arena_moonlit_bamboo",
    "arena_golden_temple",
    "arena_frozen_peak",
]

SPECIAL_ARENA = "arena_sky_colosseum"


class AssetManager:
    """Singleton-style cache for game graphics and arena selection."""

    def __init__(self):
        self._cache: Dict[str, pygame.Surface] = {}
        self._last_arena: Optional[str] = None

    def _find_file(self, directory: str, stem: str) -> Optional[str]:
        """Look for stem with any supported extension."""
        for ext in EXTENSIONS:
            path = os.path.join(directory, stem + ext)
            if os.path.exists(path):
                return path
        return None

    def _create_placeholder(self, width: int, height: int, label: str,
                            top_colour=(40, 50, 75), bot_colour=(15, 20, 35)) -> pygame.Surface:
        """Create a smooth vertical gradient placeholder with text label."""
        surface = pygame.Surface((width, height))
        if pygame.display.get_surface() is not None:
            surface = surface.convert()
        # Draw vertical gradient
        for y in range(height):
            t = y / max(height - 1, 1)
            r = int(top_colour[0] * (1 - t) + bot_colour[0] * t)
            g = int(top_colour[1] * (1 - t) + bot_colour[1] * t)
            b = int(top_colour[2] * (1 - t) + bot_colour[2] * t)
            pygame.draw.line(surface, (r, g, b), (0, y), (width, y))

        # Add border
        pygame.draw.rect(surface, (70, 90, 130), surface.get_rect(), 2)

        # Draw label
        if pygame.font.get_init():
            font = pygame.font.Font(None, 24)
            text_surf = font.render(f"[{label}]", True, (200, 210, 230))
            rect = text_surf.get_rect(center=(width // 2, height // 2))
            surface.blit(text_surf, rect)

        return surface

    def load_surface(self, directory: str, stem: str, target_size: Tuple[int, int]) -> pygame.Surface:
        """Load an image scaled to target_size with caching and fallback."""
        cache_key = f"{directory}:{stem}:{target_size[0]}x{target_size[1]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = self._find_file(directory, stem)
        if file_path:
            try:
                raw_image = pygame.image.load(file_path)
                if pygame.display.get_surface() is not None:
                    raw_image = raw_image.convert()
                scaled = pygame.transform.smoothscale(raw_image, target_size)
                self._cache[cache_key] = scaled
                return scaled
            except Exception as e:
                print(f"[Assets] Warning: Failed to load {file_path}: {e}")

        # Fallback placeholder if missing or failed to decode
        placeholder = self._create_placeholder(target_size[0], target_size[1], stem)
        self._cache[cache_key] = placeholder
        return placeholder

    # ------------------------------------------------------------------
    # Screen Art (Intro, Victory, Defeat)
    # ------------------------------------------------------------------
    def get_intro(self, size=(SCREEN_WIDTH, SCREEN_HEIGHT)) -> pygame.Surface:
        return self.load_surface(SCREENS_DIR, "intro", size)

    def get_intro_blur(self, size=(SCREEN_WIDTH, SCREEN_HEIGHT)) -> pygame.Surface:
        """Return the blurred intro.

        If intro_blur is absent, automatically creates one by downscaling
        the normal intro to 1/8 and upscaling.
        """
        cache_key = f"screen:intro_blur:{size[0]}x{size[1]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = self._find_file(SCREENS_DIR, "intro_blur")
        if file_path:
            return self.load_surface(SCREENS_DIR, "intro_blur", size)

        # Algorithmic blur from normal intro
        base = self.get_intro(size)
        small_size = (max(size[0] // 8, 1), max(size[1] // 8, 1))
        shrunk = pygame.transform.smoothscale(base, small_size)
        blurred = pygame.transform.smoothscale(shrunk, size)
        self._cache[cache_key] = blurred
        return blurred

    def get_victory(self, size=(SCREEN_WIDTH, SCREEN_HEIGHT)) -> pygame.Surface:
        return self.load_surface(SCREENS_DIR, "victory", size)

    def get_defeat(self, size=(SCREEN_WIDTH, SCREEN_HEIGHT)) -> pygame.Surface:
        return self.load_surface(SCREENS_DIR, "defeat", size)

    def get_draw_screen(self, size=(SCREEN_WIDTH, SCREEN_HEIGHT)) -> pygame.Surface:
        """Victory screen dimmed for a draw result."""
        cache_key = f"screen:draw:{size[0]}x{size[1]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        base = self.get_victory(size).copy()
        dim_overlay = pygame.Surface(size, pygame.SRCALPHA)
        dim_overlay.fill((0, 0, 0, 140))
        base.blit(dim_overlay, (0, 0))
        self._cache[cache_key] = base
        return base

    # ------------------------------------------------------------------
    # Fighter Portraits
    # ------------------------------------------------------------------
    def get_portrait(self, character_name: str, size=(160, 200),
                     flip_h: bool = False) -> pygame.Surface:
        """Return character portrait, optionally flipped horizontally for P2."""
        stem = character_name.lower()
        base = self.load_surface(PORTRAITS_DIR, stem, size)
        if flip_h:
            cache_key = f"portrait:{stem}:flipped:{size[0]}x{size[1]}"
            if cache_key not in self._cache:
                self._cache[cache_key] = pygame.transform.flip(base, True, False)
            return self._cache[cache_key]
        return base

    # ------------------------------------------------------------------
    # Arena Backgrounds
    # ------------------------------------------------------------------
    def get_arena(self, arena_name: str, size=(SCREEN_WIDTH, SCREEN_HEIGHT),
                  brightness: float = 1.0, dark_overlay: bool = True) -> pygame.Surface:
        """Get pre-scaled arena surface with fight dimming overlay."""
        cache_key = f"arena:{arena_name}:{size[0]}x{size[1]}:{brightness:.2f}:{dark_overlay}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        base = self.load_surface(BACKGROUNDS_DIR, arena_name, size).copy()

        # Adjust brightness if not 1.0
        if abs(brightness - 1.0) > 0.05:
            if brightness < 1.0:
                dark_val = int(255 * (1.0 - brightness))
                overlay = pygame.Surface(size, pygame.SRCALPHA)
                overlay.fill((0, 0, 0, min(dark_val, 255)))
                base.blit(overlay, (0, 0))
            else:
                bright_val = int(50 * (brightness - 1.0))
                overlay = pygame.Surface(size, pygame.SRCALPHA)
                overlay.fill((255, 255, 255, min(bright_val, 100)))
                base.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        # Standard 25% fight overlay so characters pop out
        if dark_overlay:
            fight_dim = pygame.Surface(size, pygame.SRCALPHA)
            fight_dim.fill((0, 0, 0, 64))  # ~25% alpha
            base.blit(fight_dim, (0, 0))

        self._cache[cache_key] = base
        return base

    def pick_arena(self, difficulty: str = "LOW", seed: Optional[int] = None) -> str:
        """Pick an arena for the match.

        - HELL matches always use arena_sky_colosseum.
        - Other matches pick randomly from NORMAL_ARENAS using seed.
        - Never picks the same arena twice in a row.
        """
        if difficulty == "HELL":
            return SPECIAL_ARENA

        rng = random.Random(seed) if seed is not None else random
        candidates = [a for a in NORMAL_ARENAS if a != self._last_arena]
        if not candidates:
            candidates = NORMAL_ARENAS

        chosen = rng.choice(candidates)
        self._last_arena = chosen
        return chosen


# Global singleton instance
assets = AssetManager()
