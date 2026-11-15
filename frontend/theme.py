"""Theme, colours, palettes, fighter visual traits, and arena dimensions.

All UI styling, fighter palettes (primary and mirror/P2 alternate),
and screen measurements live here.
"""

# ------------------------------------------------------------------
# Screen and Arena Dimensions
# ------------------------------------------------------------------
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600

# In every background image, the floor begins at the bottom 18%
FLOOR_FRACTION = 0.18
FLOOR_HEIGHT = int(round(SCREEN_HEIGHT * (1.0 - FLOOR_FRACTION)))  # 492 px from top

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
HEALTH_RED = (200, 30, 30)
HEALTH_BG = (60, 60, 60)
HEALTH_TRAIL = (240, 240, 240)  # white sliding damage trail
TIMER_COLOUR = (240, 240, 100)

# Overhead Player Tags & Shadows
P1_COLOUR = (52, 152, 219)     # Blue
P2_COLOUR = (231, 76, 60)      # Red

# Hit spark colours
SPARK_HIT = (255, 255, 255)    # White for clean hits
SPARK_BLOCK = (41, 128, 185)   # Blue for blocked attacks

# ------------------------------------------------------------------
# Fighter Palettes
# ------------------------------------------------------------------
# Primary Palettes (P1 or non-mirror)
# (primary_body, secondary/trim, accent/emblem)
PRIMARY_PALETTES = {
    # Crimson Brawler: red #C0392B + black, flame accent
    "Crimson": {
        "body": (192, 57, 43),
        "secondary": (20, 20, 20),
        "accent": (243, 156, 18),
        "name": "Crimson",
        "title": "Crimson Brawler",
        "emblem": "flame",
    },
    # Steel Guardian: steel grey #7F8C8D + navy #1F3A5F, shield crest
    "Steel": {
        "body": (127, 140, 141),
        "secondary": (31, 58, 95),
        "accent": (200, 215, 225),
        "name": "Steel",
        "title": "Steel Guardian",
        "emblem": "shield",
    },
    # Shadow Striker: purple #4A235A + black, teal #17A2B8 eyes, crescent moon
    "Shadow": {
        "body": (74, 35, 90),
        "secondary": (20, 20, 20),
        "accent": (23, 162, 184),
        "name": "Shadow",
        "title": "Shadow Striker",
        "emblem": "crescent",
    },
    # Golden Tactician: gold #D4AC0D + white, compass emblem
    "Golden": {
        "body": (212, 172, 13),
        "secondary": (245, 245, 245),
        "accent": (241, 196, 15),
        "name": "Golden",
        "title": "Golden Tactician",
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
