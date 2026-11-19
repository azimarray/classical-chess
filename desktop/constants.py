"""
constants.py — Global configuration for Classical Chess.

This module is intentionally free of any pygame import so that the rules
engine (pieces / board / game / timer) and the unit tests can run headless.
Colours are plain RGB / RGBA tuples that pygame accepts directly.
"""

# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------
APP_TITLE = "Classical Chess"
APP_VERSION = "1.0.0"
FPS = 60

# Screen states managed by main.App
STATE_SPLASH = "SPLASH"
STATE_HOME = "HOME"
STATE_SETUP = "SETUP"
STATE_GAME = "GAME"
STATE_HISTORY = "HISTORY"

# --------------------------------------------------------------------------
# Side identifiers
# --------------------------------------------------------------------------
WHITE = "w"
BLACK = "b"
COLOR_NAMES = {WHITE: "White", BLACK: "Black"}


def hex_to_rgb(value: str) -> tuple:
    """Convert '#RRGGBB' to an (r, g, b) tuple."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def with_alpha(rgb: tuple, alpha: float) -> tuple:
    """Return an RGBA tuple with alpha given as 0..1."""
    return (rgb[0], rgb[1], rgb[2], int(round(255 * alpha)))


# --------------------------------------------------------------------------
# Palette — board & surfaces (reference image 13520 / 13516)
# --------------------------------------------------------------------------
LIGHT_SQUARE = hex_to_rgb("#ECD3B1")
DARK_SQUARE = hex_to_rgb("#B58763")

BG_MAIN = hex_to_rgb("#262421")        # body / screen background
BG_DEEP = hex_to_rgb("#1E1D1B")        # move-history strip, insets
BG_SURFACE = hex_to_rgb("#2C2B29")     # header, cards
BG_RAISED = hex_to_rgb("#3C3B39")      # hover / active timer
BG_RAISED_2 = hex_to_rgb("#4A4947")    # pills, pressed states

LAST_MOVE_RGBA = with_alpha(hex_to_rgb("#F5F682"), 0.45)
SELECTED_RGBA = with_alpha(hex_to_rgb("#F5F682"), 0.55)
CHECK_RGB = hex_to_rgb("#E03C31")
CHECK_ALPHA = 0.65
MOVE_DOT_RGBA = (0, 0, 0, 38)
CAPTURE_RING_RGBA = (0, 0, 0, 38)
DRAG_HOVER_RGBA = (255, 255, 255, 150)

# Timers
TIMER_ACTIVE_BG = hex_to_rgb("#3C3B39")
TIMER_INACTIVE_BG = hex_to_rgb("#2B2A28")
TIMER_ACTIVE_TEXT = (255, 255, 255)
TIMER_INACTIVE_TEXT = hex_to_rgb("#8B8987")
TIMER_URGENT_BG = hex_to_rgb("#B8341F")
TIMER_URGENT_TEXT = hex_to_rgb("#FF8A4C")

# Text
TEXT_PRIMARY = (255, 255, 255)
TEXT_SECONDARY = hex_to_rgb("#C3C2C0")
TEXT_MUTED = hex_to_rgb("#8B8987")
TEXT_DARK = hex_to_rgb("#1E1D1B")

# Buttons
BTN_PRIMARY = DARK_SQUARE
BTN_PRIMARY_HOVER = hex_to_rgb("#C4966F")
BTN_PRIMARY_EDGE = hex_to_rgb("#8C6446")
BTN_SECONDARY = BG_RAISED
BTN_SECONDARY_HOVER = BG_RAISED_2
BTN_SECONDARY_EDGE = hex_to_rgb("#232220")
BTN_DANGER = hex_to_rgb("#C9412F")
BTN_DANGER_HOVER = hex_to_rgb("#D9523F")
BTN_DANGER_EDGE = hex_to_rgb("#8E2A1D")

# --------------------------------------------------------------------------
# Piece palettes (reference image 13512)
# Each palette: fill, shade, highlight, outline (outline may be None)
# --------------------------------------------------------------------------
WHITE_PIECE_PALETTE = {
    "fill": hex_to_rgb("#F4D374"),
    "shade": hex_to_rgb("#D9B04C"),
    "highlight": hex_to_rgb("#FBE6A2"),
    "outline": hex_to_rgb("#3D3222"),
}
BLACK_PIECE_PALETTE = {
    "fill": hex_to_rgb("#4A4947"),
    "shade": hex_to_rgb("#3A3937"),
    "highlight": hex_to_rgb("#666563"),
    "outline": hex_to_rgb("#1E1D1B"),
}
# Splash-screen palettes (reference image 13514 adapted to wood theme)
SPLASH_PAWN_PALETTE = {
    "fill": (hex_to_rgb("#F4D374"), hex_to_rgb("#B58763")),   # vertical gradient
    "shade": hex_to_rgb("#A57552"),
    "highlight": hex_to_rgb("#FBE6A2"),
    "outline": None,
}
SPLASH_DARK_PALETTE = {
    "fill": hex_to_rgb("#4A4947"),
    "shade": hex_to_rgb("#3E3D3B"),
    "highlight": None,
    "outline": None,
}
AVATAR_BG = hex_to_rgb("#DEDCD9")
AVATAR_PALETTE = {
    "fill": hex_to_rgb("#A3A19E"),
    "shade": hex_to_rgb("#8D8B88"),
    "highlight": None,
    "outline": None,
}
# Captured black pieces shown on charcoal player bars need extra contrast
CAPTURED_BLACK_PALETTE = {
    "fill": hex_to_rgb("#77756F"),
    "shade": hex_to_rgb("#64625D"),
    "highlight": hex_to_rgb("#8E8C86"),
    "outline": hex_to_rgb("#141312"),
}
# Move-strip glyphs: white moves hollow, black moves solid (like 13516)
STRIP_HOLLOW_PALETTE = {
    "fill": BG_DEEP,
    "shade": BG_DEEP,
    "highlight": None,
    "outline": hex_to_rgb("#D6D5D3"),
}
STRIP_SOLID_PALETTE = {
    "fill": hex_to_rgb("#D6D5D3"),
    "shade": hex_to_rgb("#BEBDBB"),
    "highlight": None,
    "outline": hex_to_rgb("#D6D5D3"),
}

# --------------------------------------------------------------------------
# Layout (logical canvas, scaled to the window)
# --------------------------------------------------------------------------
SQUARE_SIZE = 80
BOARD_SIZE = SQUARE_SIZE * 8           # 640
LOGICAL_WIDTH = BOARD_SIZE             # 640

HEADER_HEIGHT = 56
MOVE_BAR_HEIGHT = 44
PLAYER_BAR_HEIGHT = 76

HEADER_Y = 0
MOVE_BAR_Y = HEADER_Y + HEADER_HEIGHT                    # 56
TOP_BAR_Y = MOVE_BAR_Y + MOVE_BAR_HEIGHT                 # 100
BOARD_X = 0
BOARD_Y = TOP_BAR_Y + PLAYER_BAR_HEIGHT                  # 176
BOTTOM_BAR_Y = BOARD_Y + BOARD_SIZE                      # 816
LOGICAL_HEIGHT = BOTTOM_BAR_Y + PLAYER_BAR_HEIGHT        # 892

# --------------------------------------------------------------------------
# Rules & scoring
# --------------------------------------------------------------------------
PIECE_VALUES = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}
PROMOTION_CHOICES = ("Q", "N", "R", "B")   # order shown in the modal
CAPTURE_DISPLAY_ORDER = ("P", "N", "B", "R", "Q")
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------
RAPID_SECONDS = 10 * 60
INCREMENT_SECONDS = 0
LOW_TIME_THRESHOLD = 20.0          # below this, show tenths + urgency colour
SPLASH_DURATION = 2.5
MOVE_ANIM_DURATION = 0.12          # ~120 ms piece slide
SCREEN_FADE_DURATION = 0.25
GAME_OVER_MODAL_DELAY = 0.45
DRAG_THRESHOLD_PX = 5
MAX_NAME_LENGTH = 16
MAX_HISTORY_ENTRIES = 250
