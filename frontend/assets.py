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
FIGHTERS_DIR = os.path.join(ASSET_DIR, "fighters")

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
                    if file_path.lower().endswith(".png"):
                        raw_image = raw_image.convert_alpha()
                    else:
                        raw_image = raw_image.convert()
                if target_size is not None and (raw_image.get_width(), raw_image.get_height()) != target_size:
                    scaled = pygame.transform.smoothscale(raw_image, target_size)
                else:
                    scaled = raw_image
                self._cache[cache_key] = scaled
                return scaled
            except Exception as e:
                print(f"[Assets] Warning: Failed to load {file_path}: {e}")

        # Fallback placeholder if missing or failed to decode
        placeholder = self._create_placeholder(target_size[0], target_size[1], stem)
        self._cache[cache_key] = placeholder
        return placeholder

    # ------------------------------------------------------------------
    # Fighter Full-Body Sprites & Action Poses
    # ------------------------------------------------------------------
    FIGHTER_POSES = ("idle", "kick", "punch", "run", "jump", "crouch")
    POSE_ALIASES = {
        "idle": "idle",
        "stand": "idle",
        "default": "idle",
        "ready": "idle",
        "kick": "kick",
        "light_kick": "kick",
        "heavy_kick": "kick",
        "low_sweep": "kick",
        "crouch_kick": "kick",
        "jump_kick": "kick",
        "sweep": "kick",
        "punch": "punch",
        "jab": "punch",
        "light": "punch",
        "heavy": "punch",
        "heavy_punch": "punch",
        "overhead": "punch",
        "crouch_jab": "punch",
        "jump_punch": "punch",
        "anti_air": "punch",
        "special": "punch",
        "super": "punch",
        "attack": "punch",
        "run": "run",
        "walk": "run",
        "dash": "run",
        "backdash": "run",
        "sprint": "run",
        "forward": "run",
        "back": "run",
        "jump": "jump",
        "air": "jump",
        "in_air": "jump",
        "crouch": "crouch",
        "duck": "crouch",
        "block_low": "crouch",
    }

    def normalize_pose(self, pose: Optional[str]) -> str:
        """Map any pose/action name to a canonical fighter pose key."""
        if not pose:
            return "idle"
        clean = str(pose).lower().strip()
        return self.POSE_ALIASES.get(clean, clean)

    def has_fighter_pose(self, character_name: str, pose: str = "idle") -> bool:
        """Return True if a dedicated sprite asset exists for (character_name, pose)."""
        stem = character_name.lower().strip()
        canon_pose = self.normalize_pose(pose)
        cache_key = f"has_pose:{stem}:{canon_pose}"
        if cache_key in self._cache:
            return bool(self._cache[cache_key])

        if canon_pose == "idle":
            found = self._find_file(FIGHTERS_DIR, stem) is not None
        else:
            found = self._find_file(FIGHTERS_DIR, f"{stem}_{canon_pose}") is not None
        self._cache[cache_key] = found  # type: ignore[assignment]
        return found

    def get_fighter_sprite(self, character_name: str, size: Optional[Tuple[int, int]] = None,
                           flip_h: bool = False, pose: str = "idle") -> pygame.Surface:
        """Return full-body fighter sprite for the requested pose, optionally scaled and flipped."""
        stem = character_name.lower().strip()
        canon_pose = self.normalize_pose(pose)
        cache_key = (
            f"fighter:{stem}:{canon_pose}:"
            f"{size[0] if size else 'orig'}x{size[1] if size else 'orig'}:{flip_h}"
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = None
        if canon_pose != "idle":
            file_path = self._find_file(FIGHTERS_DIR, f"{stem}_{canon_pose}")
        if file_path is None:
            file_path = self._find_file(FIGHTERS_DIR, stem)

        if file_path:
            try:
                raw = pygame.image.load(file_path)
                if pygame.display.get_surface() is not None:
                    raw = raw.convert_alpha()
                if size is not None and (raw.get_width(), raw.get_height()) != size:
                    scaled = pygame.transform.smoothscale(raw, size)
                else:
                    scaled = raw
                if flip_h:
                    scaled = pygame.transform.flip(scaled, True, False)
                self._cache[cache_key] = scaled
                return scaled
            except Exception as e:
                print(f"[Assets] Warning: Failed to load fighter sprite {file_path}: {e}")

        return self.get_portrait(character_name, size or (130, 170), flip_h=flip_h)

    def get_fighter_poses(self, character_name: str,
                          size: Optional[Tuple[int, int]] = None,
                          flip_h: bool = False) -> Dict[str, pygame.Surface]:
        """Return dictionary of all canonical pose surfaces for a character."""
        return {
            pose: self.get_fighter_sprite(character_name, size=size, flip_h=flip_h, pose=pose)
            for pose in self.FIGHTER_POSES
        }

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
        # Normalize arena name to snake_case and match existing assets
        clean = (
            str(arena_name)
            .lower()
            .strip()
            .replace(".jpeg", "")
            .replace(".jpg", "")
            .replace(".png", "")
            .replace(" ", "_")
        )
        # Map common narrative aliases to available backgrounds
        ARENA_ALIASES = {
            "underground_vault": "arena_iron_foundry",
            "temple_ruins": "arena_golden_temple",
            "dojo": "arena_moonlit_bamboo",
            "volcanic_depths": "arena_volcanic_forge",
            "sky_colosseum": "arena_sky_colosseum",
            "frozen_peak": "arena_frozen_peak",
            "neon_rooftop": "arena_neon_rooftop",
            "golden_temple": "arena_golden_temple",
            "iron_foundry": "arena_iron_foundry",
            "moonlit_bamboo": "arena_moonlit_bamboo",
            "volcanic_forge": "arena_volcanic_forge",
        }
        mapped = ARENA_ALIASES.get(clean, clean)
        if not mapped.startswith("arena_"):
            mapped = f"arena_{mapped}"

        # If normalized name has a file, use it; otherwise fallback to original clean
        file_path = self._find_file(BACKGROUNDS_DIR, mapped)
        target_stem = mapped if file_path else clean

        cache_key = f"arena:{target_stem}:{size[0]}x{size[1]}:{brightness:.2f}:{dark_overlay}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        base = self.load_surface(BACKGROUNDS_DIR, target_stem, size).copy()

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


def __getattr__(name: str):
    """Delegate module-level attribute lookups to the singleton `assets` instance.

    Prevents AttributeError if a caller does:
        from frontend import assets
        assets.get_arena(...)
    instead of:
        from frontend.assets import assets
    """
    if hasattr(assets, name):
        return getattr(assets, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

