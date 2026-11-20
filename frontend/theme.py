"""Theme, colours, palettes, fighter visual traits, and arena dimensions.

All UI styling, fighter palettes (primary and mirror/P2 alternate),
and screen measurements live here.
"""

# ------------------------------------------------------------------
# Screen and Arena Dimensions
# ------------------------------------------------------------------
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600

# In every background image, the default floor begins at the bottom 18%
FLOOR_FRACTION = 0.18
FLOOR_HEIGHT = int(round(SCREEN_HEIGHT * (1.0 - FLOOR_FRACTION)))  # 492 px from top

# Per-arena floor ratio (from top of viewport) so feet stand right on the floor art
FLOOR_RATIO = {
    "arena_frozen_peak": 0.85,
    "arena_neon_rooftop": 0.83,
    "arena_volcanic_forge": 0.84,
    "arena_iron_foundry": 0.83,
    "arena_moonlit_bamboo": 0.84,
    "arena_golden_temple": 0.83,
    "arena_sky_colosseum": 0.83,
}
DEFAULT_FLOOR_RATIO = 1.0 - FLOOR_FRACTION  # 0.82


def get_arena_floor_y(arena_name: str, viewport_height: int = SCREEN_HEIGHT) -> int:
    """Return the pixel Y coordinate of the floor for a given arena and viewport height."""
    if not arena_name:
        return int(round(viewport_height * DEFAULT_FLOOR_RATIO))
    clean = (
        str(arena_name)
        .lower()
        .strip()
        .replace(".jpeg", "")
        .replace(".jpg", "")
        .replace(".png", "")
        .replace(" ", "_")
    )
    if not clean.startswith("arena_"):
        clean = f"arena_{clean}"
    ratio = FLOOR_RATIO.get(clean, DEFAULT_FLOOR_RATIO)
    return int(round(viewport_height * ratio))


# Subtle arena colour grading tint (R, G, B, Alpha)
ARENA_COLOR_GRADE = {
    "arena_frozen_peak": (160, 215, 255, 22),
    "arena_neon_rooftop": (120, 60, 220, 20),
    "arena_volcanic_forge": (255, 110, 40, 22),
    "arena_iron_foundry": (255, 150, 60, 18),
    "arena_moonlit_bamboo": (80, 200, 190, 20),
    "arena_golden_temple": (255, 200, 90, 18),
    "arena_sky_colosseum": (210, 190, 255, 20),
}

# ------------------------------------------------------------------
# General Colours (R, G, B)
# ------------------------------------------------------------------
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (100, 100, 100)
DARK_GREY = (40, 40, 40)
LIGHT_GREY = (180, 180, 180)

# UI Elements
MENU_BG = (15, 15, 30)
MENU_HIGHLIGHT = (50, 50, 120)
HEALTH_GREEN = (30, 200, 60)
HEALTH_YELLOW = (245, 195, 40)
HEALTH_RED = (220, 40, 40)
HEALTH_BG = (35, 38, 52)
HEALTH_TRAIL = (245, 245, 250)  # white sliding damage trail
TIMER_COLOUR = (240, 240, 100)

# Overhead Player Tags & Shadows
P1_COLOUR = (52, 152, 219)     # Blue
P2_COLOUR = (231, 76, 60)      # Red

# Hit spark colours
SPARK_HIT = (255, 255, 255)       # White/yellow for clean hits
SPARK_BLOCK = (41, 168, 245)      # Blue for blocked attacks
SPARK_COUNTER = (255, 60, 60)     # Red for counter-hits

# ------------------------------------------------------------------
# Fighter Palettes
# ------------------------------------------------------------------
# Primary Palettes (P1 or non-mirror)
PRIMARY_PALETTES = {
    # Crimson Brawler: red #C0392B + black, flame accent
    "Crimson": {
        "body": (192, 57, 43),
        "secondary": (24, 24, 28),
        "accent": (243, 156, 18),
        "skin": (232, 190, 160),
        "name": "Crimson",
        "title": "Crimson Brawler",
        "subtitle": "The Blazing Striker",
        "emblem": "flame",
    },
    # Steel Guardian: steel grey #7F8C8D + navy #1F3A5F, shield crest
    "Steel": {
        "body": (127, 140, 148),
        "secondary": (31, 58, 95),
        "accent": (80, 210, 255),
        "skin": (160, 175, 185),
        "name": "Steel",
        "title": "Steel Guardian",
        "subtitle": "The Iron Bulwark",
        "emblem": "shield",
    },
    # Shadow Striker: purple #4A235A + black, teal #17A2B8 eyes, crescent moon
    "Shadow": {
        "body": (74, 35, 90),
        "secondary": (20, 20, 26),
        "accent": (23, 210, 225),
        "skin": (195, 180, 205),
        "name": "Shadow",
        "title": "Shadow Striker",
        "subtitle": "The Silent Phantom",
        "emblem": "crescent",
    },
    # Golden Tactician: gold #D4AC0D + white, compass emblem
    "Golden": {
        "body": (212, 172, 13),
        "secondary": (242, 242, 246),
        "accent": (245, 205, 35),
        "skin": (235, 198, 165),
        "name": "Golden",
        "title": "Golden Tactician",
        "subtitle": "The Grandmaster",
        "emblem": "compass",
    },
}

# Alternate Palettes (used by P2 in mirror matches)
ALTERNATE_PALETTES = {
    # Crimson mirror: orange + charcoal
    "Crimson": {
        "body": (230, 126, 34),
        "secondary": (44, 62, 80),
        "accent": (241, 196, 15),
    },
    # Steel mirror: bronze + dark green
    "Steel": {
        "body": (205, 127, 50),
        "secondary": (20, 90, 50),
        "accent": (245, 230, 180),
    },
    # Shadow mirror: dark blue + white
    "Shadow": {
        "body": (26, 82, 118),
        "secondary": (240, 240, 240),
        "accent": (133, 193, 233),
    },
    # Golden mirror: silver + black
    "Golden": {
        "body": (189, 195, 199),
        "secondary": (30, 30, 30),
        "accent": (255, 255, 255),
    },
}

# Backwards-compatible tuple format (body, trim)
FIGHTER_COLOURS = {
    name: (p["body"], p["secondary"]) for name, p in PRIMARY_PALETTES.items()
}

# ------------------------------------------------------------------
# Fighter Body Dimensions (distinct silhouettes)
# ------------------------------------------------------------------
FIGHTER_PROPORTIONS = {
    "Crimson": {
        "body_width": 46,      # wide stocky body
        "body_height": 78,
        "head_radius": 16,
        "arm_length": 32,
        "leg_length": 30,
        "special_accent": "taped_fists",
    },
    "Steel": {
        "body_width": 52,      # tallest and widest
        "body_height": 92,
        "head_radius": 18,
        "arm_length": 36,
        "leg_length": 34,
        "special_accent": "shoulder_shields",
    },
    "Shadow": {
        "body_width": 34,      # thinnest body
        "body_height": 76,
        "head_radius": 14,
        "arm_length": 30,
        "leg_length": 32,
        "special_accent": "trailing_scarf",
    },
    "Golden": {
        "body_width": 40,      # balanced medium build
        "body_height": 82,
        "head_radius": 15,
        "arm_length": 32,
        "leg_length": 32,
        "special_accent": "robe_sash",
    },
}

# Defaults for stubs/custom characters
DEFAULT_PROPORTIONS = FIGHTER_PROPORTIONS["Golden"]

# ------------------------------------------------------------------
# UI Sizes & Typography
# ------------------------------------------------------------------
HEALTH_BAR_WIDTH = 320
HEALTH_BAR_HEIGHT = 26
FONT_SIZE_LARGE = 48
FONT_SIZE_MEDIUM = 30
FONT_SIZE_SMALL = 20
FONT_SIZE_TINY = 16


def get_fighter_palette(character_name: str, is_p2_mirror: bool = False):
    """Return the palette dict for a character, accounting for P2 mirror matches."""
    if is_p2_mirror and character_name in ALTERNATE_PALETTES:
        alt = ALTERNATE_PALETTES[character_name]
        primary = PRIMARY_PALETTES.get(character_name, PRIMARY_PALETTES["Golden"])
        return {**primary, **alt}
    return PRIMARY_PALETTES.get(character_name, PRIMARY_PALETTES["Golden"])
