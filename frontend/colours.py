"""Legacy colour constants (kept for older modules such as the replay viewer).

Screen size lives in frontend.theme (single source of truth) and is
re-exported here so `from frontend.colours import SCREEN_WIDTH` keeps working.
New code should import from frontend.theme / frontend.fantasy_ui instead.
"""

from frontend.theme import SCREEN_HEIGHT, SCREEN_WIDTH  # noqa: F401  (re-export)

# ---------------------------------------------------------------
# Colours (R, G, B)
# ---------------------------------------------------------------
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (100, 100, 100)
DARK_GREY = (40, 40, 40)
LIGHT_GREY = (180, 180, 180)

# UI colours
MENU_BG = (15, 15, 30)
MENU_HIGHLIGHT = (50, 50, 120)
HEALTH_GREEN = (30, 200, 60)
HEALTH_RED = (200, 30, 30)
HEALTH_BG = (60, 60, 60)
TIMER_COLOUR = (240, 240, 100)

# Fighter costume colours (body, trim)
FIGHTER_COLOURS = {
    "Crimson": ((180, 30, 30), (255, 80, 80)),      # red body, light red trim
    "Steel":   ((100, 110, 130), (180, 190, 210)),   # blue-grey body, light trim
    "Shadow":  ((40, 20, 60), (130, 80, 180)),       # dark purple body, violet trim
    "Golden":  ((200, 170, 50), (255, 220, 100)),    # gold body, bright gold trim
}

# ---------------------------------------------------------------
# Fighter drawing sizes (in pixels)
# ---------------------------------------------------------------
BODY_WIDTH = 40
BODY_HEIGHT = 80
HEAD_RADIUS = 16
ARM_LENGTH = 30
LEG_LENGTH = 30

# ---------------------------------------------------------------
# UI sizes
# ---------------------------------------------------------------
HEALTH_BAR_WIDTH = 300
HEALTH_BAR_HEIGHT = 24
FONT_SIZE_LARGE = 48
FONT_SIZE_MEDIUM = 32
FONT_SIZE_SMALL = 22
