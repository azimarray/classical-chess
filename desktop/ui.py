"""
ui.py — Pygame rendering engine and interactive screens.

Contents
  * Drawing helpers (rounded rects, blurred shadows, text, easing)
  * PieceRenderer — programmatic Staunton-style vector pieces, supersampled
    and cached per (kind, palette, size)
  * Icon rendering (back, flag, speaker, swap, clock, close, ½)
  * Widgets — Button, IconButton, TextInput, ConfirmDialog
  * Screens — SplashScreen, HomeScreen, SetupScreen, GameScreen, HistoryScreen

The UI never decides chess rules: every legality question is delegated to
game.Game, and clocks to timer.ChessClock.
"""

from __future__ import annotations

import math
import time
from typing import Callable, Dict, List, Optional, Tuple

import pygame

import constants as C
from constants import BLACK, WHITE
from game import CHECKMATE, Game
from history_manager import relative_time
from pieces import Square
from timer import ChessClock

SQ = C.SQUARE_SIZE
W, H = C.LOGICAL_WIDTH, C.LOGICAL_HEIGHT


# ==========================================================================
# Math / colour helpers
# ==========================================================================
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1, c2, t: float) -> tuple:
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out_back(t: float, s: float = 1.55) -> float:
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


# ==========================================================================
# Drawing helpers
# ==========================================================================
def fill_rounded(surface, color, rect, radius: int = 0, width: int = 0) -> None:
    rect = pygame.Rect(rect)
    if len(color) == 4 and color[3] < 255:
        tmp = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(tmp, color, tmp.get_rect(), width, border_radius=radius)
        surface.blit(tmp, rect.topleft)
    else:
        pygame.draw.rect(surface, color[:3], rect, width, border_radius=radius)


_SHADOW_CACHE: Dict[tuple, pygame.Surface] = {}


def draw_shadow(surface, rect, radius: int = 10, blur: int = 16,
                alpha: int = 120, offset: Tuple[int, int] = (0, 6)) -> None:
    """Soft drop shadow made by down/up-scaling a rounded rectangle."""
    rect = pygame.Rect(rect)
    key = (rect.w, rect.h, radius, blur, alpha)
    shadow = _SHADOW_CACHE.get(key)
    if shadow is None:
        w, h = rect.w + blur * 2, rect.h + blur * 2
        base = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(base, (0, 0, 0, alpha), (blur, blur, rect.w, rect.h),
                         border_radius=radius)
        factor = max(2, blur // 2)
        small = pygame.transform.smoothscale(base, (max(1, w // factor), max(1, h // factor)))
        shadow = pygame.transform.smoothscale(small, (w, h))
        _SHADOW_CACHE[key] = shadow
    surface.blit(shadow, (rect.x - blur + offset[0], rect.y - blur + offset[1]))


def blit_text(surface, font, text: str, color, **anchor) -> pygame.Rect:
    image = font.render(text, True, color)
    rect = image.get_rect(**anchor)
    surface.blit(image, rect)
    return rect


def truncate(font, text: str, max_width: int) -> str:
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "...")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def spaced_text(font, text: str, color, spacing: int) -> pygame.Surface:
    """Render text with extra letter spacing (for the title wordmark)."""
    glyphs = [font.render(ch, True, color) for ch in text]
    width = sum(g.get_width() for g in glyphs) + spacing * (len(glyphs) - 1)
    height = max(g.get_height() for g in glyphs)
    out = pygame.Surface((max(1, width), height), pygame.SRCALPHA)
    x = 0
    for g in glyphs:
        out.blit(g, (x, 0))
        x += g.get_width() + spacing
    return out


def round_corners(surface: pygame.Surface, radius: int) -> pygame.Surface:
    """Return a copy of `surface` clipped to a rounded rectangle."""
    out = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    out.blit(surface, (0, 0))
    mask = pygame.Surface(out.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def square_rect(square: Square) -> pygame.Rect:
    row, col = square
    return pygame.Rect(C.BOARD_X + col * SQ, C.BOARD_Y + row * SQ, SQ, SQ)


def square_at(pos) -> Optional[Square]:
    x, y = pos
    col = (x - C.BOARD_X) // SQ
    row = (y - C.BOARD_Y) // SQ
    if 0 <= row < 8 and 0 <= col < 8:
        return int(row), int(col)
    return None


# ==========================================================================
# Fonts
# ==========================================================================
class Fonts:
    FAMILIES = "segoeui,helveticaneue,helvetica,arial,dejavusans,liberationsans,freesans"

    def __init__(self) -> None:
        self._cache: Dict[tuple, pygame.font.Font] = {}

    def get(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        font = self._cache.get(key)
        if font is None:
            try:
                font = pygame.font.SysFont(self.FAMILIES, size, bold=bold)
            except Exception:
                font = pygame.font.Font(None, int(size * 1.35))
                font.set_bold(bold)
            self._cache[key] = font
        return font


# ==========================================================================
# Vector piece geometry (100 x 100 design space, y grows downwards)
# ==========================================================================
def _cubic(p0, p1, p2, p3, n: int = 14) -> List[Tuple[float, float]]:
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _quad(p0, p1, p2, n: int = 12) -> List[Tuple[float, float]]:
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t ** 2
        pts.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return pts


def _catmull_rom(points, samples: int = 6, closed: bool = True) -> List[Tuple[float, float]]:
    pts = list(points)
    n = len(pts)
    out = []
    segments = n if closed else n - 1
    for i in range(segments):
        p0 = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        p1 = pts[i]
        p2 = pts[(i + 1) % n] if closed else pts[min(i + 1, n - 1)]
        p3 = pts[(i + 2) % n] if closed else pts[min(i + 2, n - 1)]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t
                                    + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)
                             for k in (0, 1)))
    if not closed:
        out.append(pts[-1])
    return out


def _base(ring=(24, 74, 52, 8), foot=(18, 82, 64, 9)) -> List[dict]:
    return [{"t": "rrect", "rect": ring, "r": 3},
            {"t": "rrect", "rect": foot, "r": 3.5}]


def _build_piece_shapes() -> Dict[str, List[dict]]:
    shapes: Dict[str, List[dict]] = {}

    # Pawn ---------------------------------------------------------------
    pawn_body = ([(42.5, 40.0)] + _cubic((42.5, 40), (43, 57), (36, 66), (27, 76))
                 + _cubic((73, 76), (64, 66), (57, 57), (57.5, 40)))
    shapes["P"] = [
        {"t": "poly", "pts": pawn_body},
        {"t": "circle", "c": (50, 25), "r": 12.5},
        {"t": "rrect", "rect": (33, 36, 34, 7.5), "r": 3.5},
        *_base((25, 74, 50, 8), (20, 82, 60, 9)),
    ]

    # Rook ---------------------------------------------------------------
    shapes["R"] = [
        {"t": "poly", "pts": [(32, 38), (68, 38), (71.5, 76), (28.5, 76)]},
        {"t": "poly", "pts": [(25, 33), (25, 13), (35.5, 13), (35.5, 20.5), (44.5, 20.5),
                              (44.5, 13), (55.5, 13), (55.5, 20.5), (64.5, 20.5),
                              (64.5, 13), (75, 13), (75, 33)]},
        {"t": "rrect", "rect": (26, 31, 48, 8), "r": 2.5, "hl": False},
        *_base(),
    ]

    # Bishop -------------------------------------------------------------
    mitre = (_cubic((50, 15), (35, 25), (25.5, 45), (36.5, 62))
             + _cubic((63.5, 62), (74.5, 45), (65, 25), (50, 15)))
    shapes["B"] = [
        {"t": "circle", "c": (50, 11), "r": 5},
        {"t": "poly", "pts": mitre},
        {"t": "cut", "pts": [(57.5, 23.5), (61.5, 27.5), (51.5, 44.5), (47.5, 41.5)]},
        {"t": "poly", "pts": [(39, 66), (61, 66), (66.5, 76), (33.5, 76)]},
        {"t": "rrect", "rect": (33, 59, 34, 8), "r": 3.5, "hl": False},
        *_base(),
    ]

    # Queen --------------------------------------------------------------
    crown = [(31, 70), (18, 31), (30, 45), (34, 24), (43, 41.5), (50, 19),
             (57, 41.5), (66, 24), (70, 45), (82, 31), (69, 70)]
    shapes["Q"] = [
        {"t": "poly", "pts": crown},
        {"t": "line", "pts": [(26.5, 57), (73.5, 57)], "w": 0.7},
        {"t": "circle", "c": (18, 29.5), "r": 4.2},
        {"t": "circle", "c": (34, 22), "r": 4.2},
        {"t": "circle", "c": (50, 16.5), "r": 4.8},
        {"t": "circle", "c": (66, 22), "r": 4.2},
        {"t": "circle", "c": (82, 29.5), "r": 4.2},
        {"t": "rrect", "rect": (28, 65, 44, 8.5), "r": 3.5, "hl": False},
        *_base(),
    ]

    # King ---------------------------------------------------------------
    king_body = (_cubic((32, 68), (20, 57), (13, 37), (30, 31))
                 + _quad((30, 31), (50, 22.5), (70, 31))
                 + _cubic((70, 31), (87, 37), (80, 57), (68, 68)))
    shapes["K"] = [
        {"t": "rrect", "rect": (46, 3.5, 8, 22), "r": 2, "hl": False},
        {"t": "rrect", "rect": (39, 9, 22, 7.5), "r": 2, "hl": False, "shade": False},
        {"t": "poly", "pts": king_body},
        {"t": "line", "pts": [(50, 27), (50, 64)], "w": 0.7},
        {"t": "line", "pts": [(39.5, 30), (41.5, 64)], "w": 0.7},
        {"t": "line", "pts": [(60.5, 30), (58.5, 64)], "w": 0.7},
        {"t": "rrect", "rect": (27, 64, 46, 9), "r": 3.5, "hl": False},
        *_base(),
    ]

    # Knight (faces right, like the reference set) --------------------------
    knight_outline = _catmull_rom([
        (30, 76), (27, 62), (25.5, 48), (27.5, 36), (32, 26), (36, 17.5), (39.5, 8.5),
        (44.5, 14.5), (53, 14.5), (62.5, 18.5), (70.5, 25), (77.5, 32), (81.5, 38),
        (80, 44), (74, 46.5), (66, 44.5), (59, 44.5), (55.5, 49.5), (60.5, 58.5),
        (67, 67), (70, 76),
    ], samples=6, closed=True)
    mane = _catmull_rom([(41, 18.5), (35, 29), (32.5, 43), (33, 58)], samples=6, closed=False)
    shapes["N"] = [
        {"t": "poly", "pts": knight_outline},
        {"t": "line", "pts": mane, "w": 0.75},
        {"t": "dot", "rect": (56.5, 24.5, 6, 3.6)},
        {"t": "dot", "rect": (75, 36.2, 3, 2.4)},
        {"t": "line", "pts": [(73.5, 42.8), (78.5, 41.8)], "w": 0.6},
        *_base(),
    ]
    return shapes


PIECE_SHAPES = _build_piece_shapes()

PALETTES = {
    "white": C.WHITE_PIECE_PALETTE,
    "black": C.BLACK_PIECE_PALETTE,
    "splash_pawn": C.SPLASH_PAWN_PALETTE,
    "splash_dark": C.SPLASH_DARK_PALETTE,
    "avatar": C.AVATAR_PALETTE,
    "captured_black": C.CAPTURED_BLACK_PALETTE,
    "strip_hollow": C.STRIP_HOLLOW_PALETTE,
    "strip_solid": C.STRIP_SOLID_PALETTE,
}


def palette_for(color: str) -> str:
    return "white" if color == WHITE else "black"


class PieceRenderer:
    """Renders and caches crisp, shaded vector pieces at any pixel size."""

    def __init__(self) -> None:
        self._cache: Dict[tuple, pygame.Surface] = {}

    def get(self, kind: str, palette: str, size: int) -> pygame.Surface:
        key = (kind, palette, int(size))
        surface = self._cache.get(key)
        if surface is None:
            surface = self._render(kind, PALETTES[palette], int(size))
            self._cache[key] = surface
        return surface

    def for_piece(self, piece, size: int = SQ) -> pygame.Surface:
        return self.get(piece.kind, palette_for(piece.color), size)

    def is_cached(self, kind: str, palette: str, size: int) -> bool:
        return (kind, palette, int(size)) in self._cache

    # ------------------------------------------------------------------
    @staticmethod
    def _outline_poly(surface, color, pts, width: float) -> None:
        w = max(1, int(round(width)))
        pygame.draw.lines(surface, color, True, pts, w)
        radius = width / 2
        if radius >= 1:
            for p in pts:
                pygame.draw.circle(surface, color, p, radius)

    @classmethod
    def _draw_component(cls, surface, comp, color, k: float, width: float) -> None:
        kind = comp["t"]
        if kind in ("poly", "cut"):
            pts = [(x * k, y * k) for x, y in comp["pts"]]
            if width:
                cls._outline_poly(surface, color, pts, width)
            else:
                pygame.draw.polygon(surface, color, pts)
        elif kind == "circle":
            cx, cy = comp["c"]
            pygame.draw.circle(surface, color, (cx * k, cy * k), comp["r"] * k,
                               max(1, int(round(width * 0.85))) if width else 0)
        elif kind == "rrect":
            x, y, w, h = comp["rect"]
            rect = pygame.Rect(round(x * k), round(y * k), round(w * k), round(h * k))
            pygame.draw.rect(surface, color, rect,
                             max(1, int(round(width * 0.85))) if width else 0,
                             border_radius=int(comp.get("r", 0) * k))

    _SHADE_LINES: Dict[str, float] = {}

    @classmethod
    def _shade_line(cls, kind: str) -> float:
        """x (design units) where shading starts: 60% across the piece."""
        if kind not in cls._SHADE_LINES:
            xs = []
            for comp in PIECE_SHAPES[kind]:
                if comp["t"] == "poly":
                    xs += [p[0] for p in comp["pts"]]
                elif comp["t"] == "circle":
                    xs += [comp["c"][0] - comp["r"], comp["c"][0] + comp["r"]]
                elif comp["t"] == "rrect":
                    xs += [comp["rect"][0], comp["rect"][0] + comp["rect"][2]]
            cls._SHADE_LINES[kind] = min(xs) + (max(xs) - min(xs)) * 0.6
        return cls._SHADE_LINES[kind]

    def _render(self, kind: str, pal: dict, size: int) -> pygame.Surface:
        ss = 4 if size <= 128 else 2
        S = size * ss
        k = S / 100.0
        boost = 1.0 if size >= 48 else min(2.2, (48 / max(size, 1)) ** 0.6)
        ow = 2.5 * boost * k

        surf = pygame.Surface((S, S), pygame.SRCALPHA)
        fill = pal["fill"]
        gradient = isinstance(fill[0], (tuple, list))
        grad_surf = None
        if gradient:
            grad_surf = pygame.Surface((S, S), pygame.SRCALPHA)
            top, bottom = fill
            y0, y1 = 10 * k, 92 * k
            for y in range(S):
                col = mix(top, bottom, clamp((y - y0) / (y1 - y0)))
                pygame.draw.line(grad_surf, col + (255,), (0, y), (S, y))

        outline = pal.get("outline")
        shade = pal.get("shade")
        # One light source for the whole piece: everything right of this
        # vertical line is in shade, so the edge lines up across parts.
        shade_x = self._shade_line(kind) * k
        highlight = pal.get("highlight")
        detail_color = outline or shade or (0, 0, 0)

        for comp in PIECE_SHAPES[kind]:
            t = comp["t"]
            if t == "line":
                pts = [(x * k, y * k) for x, y in comp["pts"]]
                w = max(1.0, ow * comp.get("w", 0.8))
                pygame.draw.lines(surf, detail_color, False, pts, max(1, int(round(w))))
                for p in (pts[0], pts[-1]):
                    pygame.draw.circle(surf, detail_color, p, w / 2)
                continue
            if t == "dot":
                x, y, w, h = comp["rect"]
                pygame.draw.ellipse(surf, detail_color,
                                    pygame.Rect(int(x * k), int(y * k), int(w * k), int(h * k)))
                continue
            if t == "cut":
                pts = [(x * k, y * k) for x, y in comp["pts"]]
                pygame.draw.polygon(surf, (0, 0, 0, 0), pts)      # punch transparent slit
                if outline:
                    self._outline_poly(surf, outline, pts, ow * 0.8)
                continue

            mask = pygame.Surface((S, S), pygame.SRCALPHA)
            self._draw_component(mask, comp, (255, 255, 255, 255), k, 0)
            bbox = mask.get_bounding_rect()
            if bbox.w == 0 or bbox.h == 0:
                continue

            layer = pygame.Surface((S, S), pygame.SRCALPHA)
            if grad_surf is not None:
                layer.blit(grad_surf, (0, 0))
            else:
                layer.fill(tuple(fill) + (255,))
            if shade and comp.get("shade", True):
                x0 = max(shade_x, bbox.x + bbox.w * 0.5)
                pygame.draw.rect(layer, shade, pygame.Rect(int(x0), 0, S - int(x0), S))
            if highlight and comp.get("hl", True) and bbox.h >= 14 * k:
                hl_rect = pygame.Rect(int(bbox.x + bbox.w * 0.17), int(bbox.y + bbox.h * 0.16),
                                      max(2, int(bbox.w * 0.1)), int(bbox.h * 0.5))
                pygame.draw.ellipse(layer, highlight, hl_rect)
            layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(layer, (0, 0))
            if outline:
                self._draw_component(surf, comp, outline, k, ow)

        return pygame.transform.smoothscale(surf, (size, size))


# ==========================================================================
# Icons (drawn on a 24-unit grid at 4x, then smoothscaled)
# ==========================================================================
def _stroke(surf, color, a, b, width: float) -> None:
    pygame.draw.line(surf, color, a, b, max(1, int(round(width))))
    for p in (a, b):
        pygame.draw.circle(surf, color, p, width / 2)


def _icon_back(surf, u, color, **_):
    _stroke(surf, color, (20 * u, 12 * u), (5 * u, 12 * u), 2.4 * u)
    _stroke(surf, color, (5 * u, 12 * u), (11 * u, 6 * u), 2.4 * u)
    _stroke(surf, color, (5 * u, 12 * u), (11 * u, 18 * u), 2.4 * u)


def _icon_flag(surf, u, color, **_):
    _stroke(surf, color, (6 * u, 3.5 * u), (6 * u, 21 * u), 2.2 * u)
    pygame.draw.polygon(surf, color, [(6 * u, 4 * u), (19 * u, 4 * u), (16 * u, 8.5 * u),
                                      (19 * u, 13 * u), (6 * u, 13 * u)])


def _icon_speaker(surf, u, color, muted=False, **_):
    pygame.draw.polygon(surf, color, [(3 * u, 9 * u), (7 * u, 9 * u), (12 * u, 4.5 * u),
                                      (12 * u, 19.5 * u), (7 * u, 15 * u), (3 * u, 15 * u)])
    if muted:
        _stroke(surf, color, (15.5 * u, 9 * u), (21 * u, 14.5 * u), 2 * u)
        _stroke(surf, color, (21 * u, 9 * u), (15.5 * u, 14.5 * u), 2 * u)
    else:
        width = max(1, int(2 * u))
        pygame.draw.arc(surf, color, pygame.Rect(int(7.5 * u), int(7.5 * u), int(9 * u), int(9 * u)),
                        -0.9, 0.9, width)
        pygame.draw.arc(surf, color, pygame.Rect(int(3.5 * u), int(3.5 * u), int(17 * u), int(17 * u)),
                        -0.85, 0.85, width)


def _icon_swap(surf, u, color, **_):
    w = 2.2 * u
    _stroke(surf, color, (4 * u, 8 * u), (19 * u, 8 * u), w)
    _stroke(surf, color, (19 * u, 8 * u), (15 * u, 4.2 * u), w)
    _stroke(surf, color, (19 * u, 8 * u), (15 * u, 11.8 * u), w)
    _stroke(surf, color, (20 * u, 16 * u), (5 * u, 16 * u), w)
    _stroke(surf, color, (5 * u, 16 * u), (9 * u, 12.2 * u), w)
    _stroke(surf, color, (5 * u, 16 * u), (9 * u, 19.8 * u), w)


def _icon_close(surf, u, color, **_):
    _stroke(surf, color, (6 * u, 6 * u), (18 * u, 18 * u), 2.4 * u)
    _stroke(surf, color, (18 * u, 6 * u), (6 * u, 18 * u), 2.4 * u)


def _icon_clock(surf, u, color, angle=0, filled=False, hand=None, **_):
    center = (12 * u, 12 * u)
    if filled:
        pygame.draw.circle(surf, color, center, 10 * u)
        hand_color = hand or (0, 0, 0)
    else:
        pygame.draw.circle(surf, color, center, 10 * u, max(1, int(2 * u)))
        hand_color = color
    rad = math.radians(angle - 90)
    tip = (center[0] + math.cos(rad) * 6.5 * u, center[1] + math.sin(rad) * 6.5 * u)
    _stroke(surf, hand_color, center, tip, 2 * u)
    if not filled:
        _stroke(surf, hand_color, center, (center[0] + 4 * u, center[1]), 2 * u)


def _icon_list(surf, u, color, **_):
    for y in (6, 12, 18):
        pygame.draw.circle(surf, color, (5 * u, y * u), 1.6 * u)
        _stroke(surf, color, (9 * u, y * u), (20 * u, y * u), 2.2 * u)


def _icon_trash(surf, u, color, **_):
    w = 2.0 * u
    _stroke(surf, color, (3.5 * u, 6.5 * u), (20.5 * u, 6.5 * u), w)            # lid
    _stroke(surf, color, (9.5 * u, 6.5 * u), (9.5 * u, 3.5 * u), w)             # handle
    _stroke(surf, color, (9.5 * u, 3.5 * u), (14.5 * u, 3.5 * u), w)
    _stroke(surf, color, (14.5 * u, 3.5 * u), (14.5 * u, 6.5 * u), w)
    body = [(6 * u, 9 * u), (7.2 * u, 20.5 * u), (16.8 * u, 20.5 * u), (18 * u, 9 * u)]
    for a, b in zip(body, body[1:]):
        _stroke(surf, color, a, b, w)
    _stroke(surf, color, (10 * u, 11.5 * u), (10 * u, 17.5 * u), 1.7 * u)       # ribs
    _stroke(surf, color, (14 * u, 11.5 * u), (14 * u, 17.5 * u), 1.7 * u)


ICON_FUNCS: Dict[str, Callable] = {
    "back": _icon_back, "flag": _icon_flag, "speaker": _icon_speaker,
    "swap": _icon_swap, "close": _icon_close, "clock": _icon_clock, "list": _icon_list,
    "trash": _icon_trash,
}


# ==========================================================================
# Asset hub
# ==========================================================================
class Assets:
    def __init__(self) -> None:
        self.fonts = Fonts()
        self.pieces = PieceRenderer()
        self._icons: Dict[tuple, pygame.Surface] = {}
        self._prewarm_queue = [(k, p, s) for s in (SQ,) for p in ("white", "black")
                               for k in "PNBRQK"]
        self._prewarm_queue += [(k, p, 22) for p in ("white", "captured_black") for k in "PNBRQ"]
        self._prewarm_queue += [(k, p, 20) for p in ("strip_hollow", "strip_solid") for k in "NBRQK"]
        self._prewarm_queue += [("P", "avatar", 42)]

    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        return self.fonts.get(size, bold)

    def piece(self, kind: str, palette: str, size: int) -> pygame.Surface:
        return self.pieces.get(kind, palette, size)

    def icon(self, name: str, size: int, color, **params) -> pygame.Surface:
        key = (name, size, tuple(color), tuple(sorted(params.items())))
        surface = self._icons.get(key)
        if surface is None:
            ss = 4
            S = size * ss
            big = pygame.Surface((S, S), pygame.SRCALPHA)
            if name == "half":
                font = self.font(int(S * 0.78), bold=True)
                img = font.render("½", True, color)
                big.blit(img, img.get_rect(center=(S // 2, S // 2)))
            else:
                ICON_FUNCS[name](big, S / 24.0, tuple(color), **params)
            surface = pygame.transform.smoothscale(big, (size, size))
            self._icons[key] = surface
        return surface

    def prewarm_step(self, budget_s: float = 0.008) -> bool:
        """Render queued pieces for up to `budget_s`. Returns True when done."""
        deadline = time.perf_counter() + budget_s
        while self._prewarm_queue and time.perf_counter() < deadline:
            self.pieces.get(*self._prewarm_queue.pop())
        return not self._prewarm_queue

    def mini_board(self, size: int) -> pygame.Surface:
        """Small 4x4 board logo in the board palette (header icon)."""
        key = ("mini_board", size)
        surface = self._icons.get(key)
        if surface is None:
            ss = 4
            S = size * ss
            big = pygame.Surface((S, S), pygame.SRCALPHA)
            cell = S / 4
            for r in range(4):
                for c in range(4):
                    color = C.LIGHT_SQUARE if (r + c) % 2 == 0 else C.DARK_SQUARE
                    pygame.draw.rect(big, color, pygame.Rect(round(c * cell), round(r * cell),
                                                             math.ceil(cell), math.ceil(cell)))
            big = round_corners(big, int(S * 0.16))
            pygame.draw.rect(big, C.BG_DEEP, big.get_rect(), int(S * 0.05),
                             border_radius=int(S * 0.16))
            surface = pygame.transform.smoothscale(big, (size, size))
            self._icons[key] = surface
        return surface


# ==========================================================================
# Widgets
# ==========================================================================
BUTTON_STYLES = {
    "primary": (C.BTN_PRIMARY, C.BTN_PRIMARY_HOVER, C.BTN_PRIMARY_EDGE, C.TEXT_PRIMARY),
    "secondary": (C.BTN_SECONDARY, C.BTN_SECONDARY_HOVER, C.BTN_SECONDARY_EDGE, C.TEXT_PRIMARY),
    "danger": (C.BTN_DANGER, C.BTN_DANGER_HOVER, C.BTN_DANGER_EDGE, C.TEXT_PRIMARY),
}


class Button:
    """Chunky 3-D button with a darker bottom edge that compresses on press."""

    EDGE = 4

    def __init__(self, rect, text: str, style: str = "primary", font_size: int = 22,
                 icon: Optional[Callable] = None, enabled: bool = True, radius: int = 10) -> None:
        self.rect = pygame.Rect(rect)
        self.text = text
        self.style = style
        self.font_size = font_size
        self.icon = icon            # callable(surface, center, color)
        self.enabled = enabled
        self.radius = radius
        self._pressed = False

    def handle_event(self, event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._pressed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_pressed = self._pressed
            self._pressed = False
            return was_pressed and self.rect.collidepoint(event.pos)
        return False

    def draw(self, surface, app) -> None:
        base, hover_col, edge, text_col = BUTTON_STYLES[self.style]
        hover = self.enabled and self.rect.collidepoint(app.mouse_pos())
        pressed = hover and self._pressed
        if hover:
            app.request_hand_cursor()
        face_color = hover_col if hover else base
        if not self.enabled:
            face_color = mix(base, C.BG_MAIN, 0.5)
            text_col = C.TEXT_MUTED
        edge_rect = pygame.Rect(self.rect.x, self.rect.y + self.EDGE, self.rect.w, self.rect.h - self.EDGE)
        face = pygame.Rect(self.rect.x, self.rect.y + (3 if pressed else 0),
                           self.rect.w, self.rect.h - self.EDGE)
        fill_rounded(surface, edge, edge_rect, self.radius)
        fill_rounded(surface, face_color, face, self.radius)

        font = app.assets.font(self.font_size, bold=True)
        text_img = font.render(self.text, True, text_col)
        icon_w = 30 if self.icon else 0
        total = icon_w + text_img.get_width()
        x = face.centerx - total // 2
        if self.icon:
            self.icon(surface, (x + 12, face.centery), text_col)
        surface.blit(text_img, text_img.get_rect(midleft=(x + icon_w, face.centery)))


class IconButton:
    def __init__(self, rect, icon: str, tooltip: str = "", **params) -> None:
        self.rect = pygame.Rect(rect)
        self.icon = icon
        self.tooltip = tooltip
        self.params = params
        self.enabled = True
        self.visible = True
        self._pressed = False

    def handle_event(self, event) -> bool:
        if not (self.enabled and self.visible):
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._pressed = True
                return False
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_pressed = self._pressed
            self._pressed = False
            return was_pressed and self.rect.collidepoint(event.pos)
        return False

    def is_hovered(self, app) -> bool:
        return self.visible and self.enabled and self.rect.collidepoint(app.mouse_pos())

    def draw(self, surface, app, color=C.TEXT_SECONDARY, size: int = 24) -> None:
        if not self.visible:
            return
        hover = self.is_hovered(app)
        if hover:
            app.request_hand_cursor()
            fill_rounded(surface, C.BG_RAISED, self.rect, 8)
            color = C.TEXT_PRIMARY
        if not self.enabled:
            color = mix(color, C.BG_SURFACE, 0.6)
        img = app.assets.icon(self.icon, size, color, **self.params)
        surface.blit(img, img.get_rect(center=self.rect.center))

    def draw_tooltip(self, surface, app) -> None:
        if not (self.tooltip and self.is_hovered(app)):
            return
        font = app.assets.font(14, bold=True)
        img = font.render(self.tooltip, True, C.TEXT_PRIMARY)
        box = img.get_rect().inflate(16, 10)
        box.midtop = (self.rect.centerx, self.rect.bottom + 6)
        box.right = min(box.right, W - 6)
        draw_shadow(surface, box, 6, 8, 120, (0, 3))
        fill_rounded(surface, C.BG_DEEP, box, 6)
        surface.blit(img, img.get_rect(center=box.center))


class TextInput:
    def __init__(self, rect, placeholder: str = "", text: str = "",
                 max_length: int = C.MAX_NAME_LENGTH) -> None:
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.text = text
        self.max_length = max_length
        self.focused = False
        self._blink_origin = time.perf_counter()

    def focus(self, value: bool = True) -> None:
        self.focused = value
        self._blink_origin = time.perf_counter()

    def value(self) -> str:
        return " ".join(self.text.split()) or self.placeholder

    def handle_event(self, event, font) -> Optional[str]:
        """Returns 'submit' on Enter, 'tab' on Tab, else None."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focus(self.rect.collidepoint(event.pos))
            return None
        if not self.focused:
            return None
        if event.type == pygame.TEXTINPUT:
            for ch in event.text:
                if ch.isprintable() and len(self.text) < self.max_length:
                    candidate = self.text + ch
                    if font.size(candidate)[0] <= self.rect.w - 80:
                        self.text = candidate
            self._blink_origin = time.perf_counter()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                if event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
                    self.text = ""
                else:
                    self.text = self.text[:-1]
                self._blink_origin = time.perf_counter()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return "submit"
            elif event.key == pygame.K_TAB:
                return "tab"
        return None

    def draw(self, surface, app, tag: str = "") -> None:
        hover = self.rect.collidepoint(app.mouse_pos())
        bg = C.BG_DEEP
        fill_rounded(surface, bg, self.rect, 8)
        border = C.DARK_SQUARE if self.focused else (C.BG_RAISED_2 if hover else C.BG_RAISED)
        fill_rounded(surface, border, self.rect, 8, 2)
        font = app.assets.font(20, bold=True)
        x = self.rect.x + 16
        if self.text:
            img = font.render(self.text, True, C.TEXT_PRIMARY)
        else:
            img = font.render(self.placeholder, True, C.TEXT_MUTED)
        text_rect = surface.blit(img, img.get_rect(midleft=(x, self.rect.centery)))
        if self.focused and ((time.perf_counter() - self._blink_origin) % 1.0) < 0.55:
            caret_x = text_rect.right + 2 if self.text else x
            pygame.draw.line(surface, C.LIGHT_SQUARE, (caret_x, self.rect.centery - 12),
                             (caret_x, self.rect.centery + 12), 2)
        if tag:
            tag_font = app.assets.font(13, bold=True)
            tag_img = tag_font.render(tag, True, C.TEXT_SECONDARY)
            pill = tag_img.get_rect().inflate(14, 8)
            pill.midright = (self.rect.right - 12, self.rect.centery)
            fill_rounded(surface, C.BG_RAISED, pill, pill.h // 2)
            surface.blit(tag_img, tag_img.get_rect(center=pill.center))


class ConfirmDialog:
    """Modal card with a title, a message and two buttons."""

    def __init__(self, title: str, lines: List[str], confirm_text: str,
                 on_confirm: Callable[[], None], cancel_text: str = "Cancel",
                 on_cancel: Optional[Callable[[], None]] = None,
                 confirm_style: str = "primary") -> None:
        self.title = title
        self.lines = lines
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        width = 456
        height = 150 + 26 * len(lines)
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (W // 2, C.BOARD_Y + C.BOARD_SIZE // 2)
        bw = (width - 24 * 2 - 12) // 2
        by = self.rect.bottom - 24 - 52
        self.cancel_btn = Button((self.rect.x + 24, by, bw, 52), cancel_text, "secondary", 19)
        self.confirm_btn = Button((self.rect.x + 24 + bw + 12, by, bw, 52), confirm_text,
                                  confirm_style, 19)

    def handle_event(self, event) -> bool:
        """Returns True once the dialog should close."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._cancel()
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.on_confirm()
                return True
        if self.confirm_btn.handle_event(event):
            self.on_confirm()
            return True
        if self.cancel_btn.handle_event(event):
            self._cancel()
            return True
        return False

    def _cancel(self) -> None:
        if self.on_cancel:
            self.on_cancel()

    def draw(self, surface, app) -> None:
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 140))
        surface.blit(veil, (0, 0))
        draw_shadow(surface, self.rect, 14, 22, 170, (0, 10))
        fill_rounded(surface, C.BG_SURFACE, self.rect, 14)
        blit_text(surface, app.assets.font(25, bold=True), self.title, C.TEXT_PRIMARY,
                  midtop=(self.rect.centerx, self.rect.y + 26))
        body = app.assets.font(17)
        for i, line in enumerate(self.lines):
            blit_text(surface, body, line, C.TEXT_SECONDARY,
                      midtop=(self.rect.centerx, self.rect.y + 70 + i * 26))
        self.cancel_btn.draw(surface, app)
        self.confirm_btn.draw(surface, app)


# ==========================================================================
# Screen base & shared chrome
# ==========================================================================
class Screen:
    def __init__(self, app) -> None:
        self.app = app

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def handle_event(self, event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface) -> None:
        pass


def draw_header(surface, app, title: str, back_btn: Optional[IconButton]) -> None:
    pygame.draw.rect(surface, C.BG_SURFACE, (0, C.HEADER_Y, W, C.HEADER_HEIGHT))
    pygame.draw.line(surface, C.BG_DEEP, (0, C.HEADER_HEIGHT - 1), (W, C.HEADER_HEIGHT - 1))
    x = 16
    if back_btn is not None:
        back_btn.draw(surface, app, C.TEXT_SECONDARY, 26)
        x = back_btn.rect.right + 8
    logo = app.assets.mini_board(28)
    surface.blit(logo, logo.get_rect(midleft=(x, C.HEADER_HEIGHT // 2)))
    blit_text(surface, app.assets.font(24, bold=True), title, C.TEXT_PRIMARY,
              midleft=(x + 40, C.HEADER_HEIGHT // 2))


# ==========================================================================
# Splash screen (reference 13514)
# ==========================================================================
class SplashScreen(Screen):
    def __init__(self, app) -> None:
        super().__init__(app)
        pieces = app.assets.pieces
        self.pawn = pieces.get("P", "splash_pawn", 260)
        self.knight = pygame.transform.flip(pieces.get("N", "splash_dark", 210), True, False)
        self.rook = pieces.get("R", "splash_dark", 200)
        self.t = 0.0
        self._done_prewarm = False

    def handle_event(self, event) -> None:
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN) and self.t > 0.3:
            self.t = max(self.t, C.SPLASH_DURATION)

    def update(self, dt: float) -> None:
        self.t += dt
        if not self._done_prewarm:
            self._done_prewarm = self.app.assets.prewarm_step()
        if self.t >= C.SPLASH_DURATION:
            while not self.app.assets.prewarm_step(0.05):
                pass
            self.app.go(C.STATE_HOME)

    @staticmethod
    def _blit_scaled(surface, image, scale: float, midbottom, alpha: int) -> None:
        if scale <= 0.01 or alpha <= 0:
            return
        w, h = image.get_size()
        scaled = pygame.transform.smoothscale(image, (max(1, int(w * scale)), max(1, int(h * scale))))
        scaled.set_alpha(alpha)
        surface.blit(scaled, scaled.get_rect(midbottom=midbottom))

    def draw(self, surface) -> None:
        surface.fill(C.BG_MAIN)
        t = self.t
        cx, base_y = W // 2, H // 2 + 96

        # Soft floor shadow grows with the composition
        grow = ease_out_cubic(t / 1.2)
        if grow > 0:
            shadow = pygame.Rect(0, 0, int(300 * grow) + 1, int(30 * grow) + 1)
            shadow.center = (cx, base_y - 6)
            draw_shadow(surface, shadow, shadow.h // 2, 18, int(110 * grow), (0, 0))

        # Knight & rook slide out from behind the pawn
        side = ease_out_cubic((t - 0.45) / 0.8)
        side_alpha = int(255 * clamp((t - 0.4) / 0.35))
        offset = 92 * side
        self._blit_scaled(surface, self.knight, lerp(0.8, 1.0, side),
                          (cx - offset - 8, base_y - 26), side_alpha)
        self._blit_scaled(surface, self.rook, lerp(0.8, 1.0, side),
                          (cx + offset + 10, base_y - 24), side_alpha)

        # Pawn scales up and settles in front
        pawn_scale = lerp(0.35, 1.0, ease_out_back(t / 0.75))
        self._blit_scaled(surface, self.pawn, pawn_scale, (cx, base_y + 6),
                          int(255 * clamp(t / 0.3)))

        # Wordmark fades in
        word_alpha = int(255 * ease_in_out((t - 1.0) / 0.6))
        if word_alpha > 0:
            word = spaced_text(self.app.assets.font(22, bold=True), "CLASSICAL CHESS",
                               C.LIGHT_SQUARE, 6)
            word.set_alpha(word_alpha)
            surface.blit(word, word.get_rect(midtop=(cx, base_y + 40)))


# ==========================================================================
# Home menu
# ==========================================================================
class HomeScreen(Screen):
    HERO_SQ = 64

    def __init__(self, app) -> None:
        super().__init__(app)
        bw, bh = 380, 66
        x = (W - bw) // 2
        self.play_btn = Button((x, 520, bw, bh), "Play Game", "primary", 24,
                               icon=self._pawn_icon)
        self.history_btn = Button((x, 604, bw, bh), "Match History", "secondary", 22,
                                  icon=self._history_icon)
        self.quit_btn = Button((x, 688, bw, bh), "Quit", "secondary", 22)
        self.hero = self._build_hero()
        self.title = spaced_text(app.assets.font(40, bold=True), "CLASSICAL CHESS",
                                 C.LIGHT_SQUARE, 5)
        self.t = 0.0

    def _pawn_icon(self, surface, center, color) -> None:
        img = self.app.assets.piece("P", "white", 30)
        surface.blit(img, img.get_rect(center=center))

    def _history_icon(self, surface, center, color) -> None:
        img = self.app.assets.icon("list", 22, color)
        surface.blit(img, img.get_rect(center=center))

    def _build_hero(self) -> pygame.Surface:
        n, s = 4, self.HERO_SQ
        board = pygame.Surface((n * s, n * s))
        for r in range(n):
            for c in range(n):
                color = C.LIGHT_SQUARE if (r + c) % 2 == 0 else C.DARK_SQUARE
                pygame.draw.rect(board, color, (c * s, r * s, s, s))
        board = round_corners(board, 14)
        layout = {(0, 0): ("R", BLACK), (0, 3): ("K", BLACK), (1, 1): ("N", BLACK),
                  (2, 2): ("N", WHITE), (3, 0): ("P", WHITE), (3, 3): ("K", WHITE)}
        pieces = self.app.assets.pieces
        for (r, c), (kind, side) in layout.items():
            img = pieces.get(kind, palette_for(side), s)
            board.blit(img, (c * s, r * s))
        return board

    def handle_event(self, event) -> None:
        if self.play_btn.handle_event(event):
            self.app.go(C.STATE_SETUP)
        elif self.history_btn.handle_event(event):
            self.app.go(C.STATE_HISTORY)
        elif self.quit_btn.handle_event(event):
            self.app.quit()
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.app.go(C.STATE_SETUP)
            elif event.key == pygame.K_h:
                self.app.go(C.STATE_HISTORY)
            elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                self.app.quit()

    def update(self, dt: float) -> None:
        self.t += dt

    def draw(self, surface) -> None:
        surface.fill(C.BG_MAIN)
        hero_rect = self.hero.get_rect(center=(W // 2, 206))     # fixed, centred
        draw_shadow(surface, hero_rect, 14, 26, 170, (0, 14))
        surface.blit(self.hero, hero_rect)

        surface.blit(self.title, self.title.get_rect(midtop=(W // 2, 386)))
        blit_text(surface, self.app.assets.font(17), "Two players · One board · Every rule enforced",
                  C.TEXT_MUTED, midtop=(W // 2, 450))

        self.play_btn.draw(surface, self.app)
        self.history_btn.draw(surface, self.app)
        self.quit_btn.draw(surface, self.app)

        blit_text(surface, self.app.assets.font(14), f"v{C.APP_VERSION}  ·  10:00 Rapid",
                  C.TEXT_MUTED, midbottom=(W // 2, H - 22))


# ==========================================================================
# Player setup
# ==========================================================================
class SetupScreen(Screen):
    ROW_WHITE_Y = 168
    ROW_BLACK_Y = 300
    INPUT_X = 124

    def __init__(self, app) -> None:
        super().__init__(app)
        names = app.player_names
        self.back_btn = IconButton((8, 8, 40, 40), "back", "Back")
        width = W - self.INPUT_X - 52
        self.inputs = [TextInput((self.INPUT_X, 0, width, 56), "Player 1", names[0]),
                       TextInput((self.INPUT_X, 0, width, 56), "Player 2", names[1])]
        self.p1_white = app.p1_white
        self._y = [float(self._target_y(0)), float(self._target_y(1))]
        self._sync_rects()
        self.inputs[0].focus(True)
        self.swap_btn = Button((W // 2 - 90, 246, 180, 44), "Swap Sides", "secondary", 17,
                               icon=self._swap_icon, radius=22)
        self.start_btn = Button((32, 552, W - 64, 68), "Start Match", "primary", 25)

    def _swap_icon(self, surface, center, color) -> None:
        img = self.app.assets.icon("swap", 22, color)
        surface.blit(img, img.get_rect(center=center))

    def _target_y(self, index: int) -> int:
        is_white = self.p1_white if index == 0 else not self.p1_white
        return self.ROW_WHITE_Y + 8 if is_white else self.ROW_BLACK_Y + 8

    def _sync_rects(self) -> None:
        for i, field_input in enumerate(self.inputs):
            field_input.rect.y = int(round(self._y[i]))

    def on_enter(self) -> None:
        pygame.key.start_text_input()

    def on_exit(self) -> None:
        self._remember()

    def _remember(self) -> None:
        self.app.player_names = [self.inputs[0].text.strip(), self.inputs[1].text.strip()]
        self.app.p1_white = self.p1_white

    def _start(self) -> None:
        self._remember()
        p1, p2 = self.inputs[0].value(), self.inputs[1].value()
        white, black = (p1, p2) if self.p1_white else (p2, p1)
        self.app.go(C.STATE_GAME, white_name=white, black_name=black)

    def handle_event(self, event) -> None:
        if self.back_btn.handle_event(event):
            self.app.go(C.STATE_HOME)
            return
        if self.swap_btn.handle_event(event):
            self.p1_white = not self.p1_white
            self.app.sound.play("move")
            return
        if self.start_btn.handle_event(event):
            self._start()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go(C.STATE_HOME)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = [i for i, f in enumerate(self.inputs) if f.rect.collidepoint(event.pos)]
            if hit:
                for i, field_input in enumerate(self.inputs):
                    field_input.focus(i == hit[0])
            return
        font = self.app.assets.font(20, bold=True)
        for i, field_input in enumerate(self.inputs):
            action = field_input.handle_event(event, font)
            if action == "submit":
                self._start()
                return
            if action == "tab":
                field_input.focus(False)
                self.inputs[1 - i].focus(True)
                return

    def update(self, dt: float) -> None:
        for i in range(2):
            target = self._target_y(i)
            self._y[i] = lerp(self._y[i], target, clamp(dt * 14))
            if abs(self._y[i] - target) < 0.5:
                self._y[i] = target
        self._sync_rects()

    def _draw_row(self, surface, y: int, color: str) -> None:
        tile = pygame.Rect(52, y + 4, 60, 60)
        square_color = C.LIGHT_SQUARE if color == WHITE else C.DARK_SQUARE
        fill_rounded(surface, square_color, tile, 8)
        img = self.app.assets.piece("K", palette_for(color), 54)
        surface.blit(img, img.get_rect(center=tile.center))
        blit_text(surface, self.app.assets.font(13, bold=True), C.COLOR_NAMES[color].upper(),
                  C.TEXT_MUTED, bottomleft=(self.INPUT_X + 2, y + 2))

    def draw(self, surface) -> None:
        app = self.app
        surface.fill(C.BG_MAIN)
        draw_header(surface, app, "New Match", self.back_btn)

        card = pygame.Rect(32, 88, W - 64, 304)
        fill_rounded(surface, C.BG_SURFACE, card, 14)
        surface.blit(spaced_text(app.assets.font(14, bold=True), "PLAYERS", C.TEXT_MUTED, 3),
                     (52, 108))

        self._draw_row(surface, self.ROW_WHITE_Y, WHITE)
        self._draw_row(surface, self.ROW_BLACK_Y, BLACK)
        for i, field_input in enumerate(self.inputs):
            field_input.draw(surface, app, tag=f"P{i + 1}")
        self.swap_btn.draw(surface, app)

        # Match format indicator: 10:00 Rapid | Rule-Enforced
        pill = pygame.Rect(0, 0, 380, 44)
        pill.center = (W // 2, 440)
        fill_rounded(surface, C.BG_DEEP, pill, 22)
        fill_rounded(surface, C.BG_RAISED, pill, 22, 1)
        clock_img = app.assets.icon("clock", 20, C.LIGHT_SQUARE, angle=60)
        bold, regular = app.assets.font(17, bold=True), app.assets.font(17)
        parts = [(bold, "10:00 Rapid", C.TEXT_PRIMARY), (regular, "   |   ", C.TEXT_MUTED),
                 (bold, "Rule-Enforced", C.LIGHT_SQUARE)]
        total = 28 + sum(f.size(s)[0] for f, s, _ in parts)
        x = pill.centerx - total // 2
        surface.blit(clock_img, clock_img.get_rect(midleft=(x, pill.centery)))
        x += 28
        for font, text, color in parts:
            rect = blit_text(surface, font, text, color, midleft=(x, pill.centery))
            x = rect.right
        rules = ["Castling · En passant · Promotion · Checkmate · Stalemate",
                 "Threefold repetition · 50-move rule · Insufficient material"]
        for i, line in enumerate(rules):
            blit_text(surface, app.assets.font(14), line, C.TEXT_MUTED,
                      midtop=(W // 2, 478 + i * 22))

        self.start_btn.draw(surface, app)
        blit_text(surface, app.assets.font(14), "Tab switches field  ·  Enter starts the match",
                  C.TEXT_MUTED, midtop=(W // 2, 640))


# ==========================================================================
# Game screen (references 13516, 13517, 13520)
# ==========================================================================
class SlideAnimation:
    def __init__(self, items, hidden, ghosts, duration: float = C.MOVE_ANIM_DURATION) -> None:
        self.items = items          # [(surface, (x0, y0), (x1, y1))]
        self.hidden = hidden        # squares whose occupants are drawn by the animation
        self.ghosts = ghosts        # [(surface, (x, y))] captured pieces until arrival
        self.duration = duration
        self.t = 0.0

    @property
    def done(self) -> bool:
        return self.t >= self.duration

    def progress(self) -> float:
        return ease_out_cubic(self.t / self.duration)


class GameScreen(Screen):
    def __init__(self, app, white_name: str = "White", black_name: str = "Black") -> None:
        super().__init__(app)
        self.game = Game(white_name, black_name)
        self.clock = ChessClock(C.RAPID_SECONDS, C.INCREMENT_SECONDS)
        self.selected: Optional[Square] = None
        self.targets: set = set()
        self.drag: Optional[dict] = None
        self.anim: Optional[SlideAnimation] = None
        self.promotion: Optional[dict] = None
        self.dialog: Optional[ConfirmDialog] = None
        self.result_modal: Optional[dict] = None
        self.modal_timer: Optional[float] = None
        self.saved = False
        self.started_at = time.time()

        self.tokens: List[dict] = []
        self.tokens_width = 0
        self.tokens_dirty = True
        self.scroll = 0.0
        self.scroll_target = 0.0
        self.manual_scroll = False

        self.back_btn = IconButton((8, 8, 40, 40), "back", "Leave match")
        self.mute_btn = IconButton((W - 52, 8, 40, 40), "speaker", "Mute", muted=False)
        self.draw_btn = IconButton((W - 98, 8, 40, 40), "half", "Offer draw")
        self.resign_btn = IconButton((W - 144, 8, 40, 40), "flag", "Resign")
        self.result_btn = Button((W - 168, 10, 108, 36), "Result", "secondary", 16, radius=8)

        self._build_static_layers()

    # ------------------------------------------------------------------
    # Pre-rendered layers
    # ------------------------------------------------------------------
    def _build_static_layers(self) -> None:
        fonts = self.app.assets
        board = pygame.Surface((C.BOARD_SIZE, C.BOARD_SIZE))
        coord_font = fonts.font(15, bold=True)
        for row in range(8):
            for col in range(8):
                light = (row + col) % 2 == 0
                color = C.LIGHT_SQUARE if light else C.DARK_SQUARE
                pygame.draw.rect(board, color, (col * SQ, row * SQ, SQ, SQ))
                text_color = C.DARK_SQUARE if light else C.LIGHT_SQUARE
                if col == 0:
                    blit_text(board, coord_font, str(8 - row), text_color,
                              topleft=(col * SQ + 5, row * SQ + 3))
                if row == 7:
                    blit_text(board, coord_font, "abcdefgh"[col], text_color,
                              bottomright=(col * SQ + SQ - 5, row * SQ + SQ - 2))
        self.board_surface = board

        self.hl_last = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        self.hl_last.fill(C.LAST_MOVE_RGBA)
        self.hl_selected = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        self.hl_selected.fill(C.SELECTED_RGBA)

        self.check_glow = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        peak = int(255 * C.CHECK_ALPHA)
        max_r = SQ * 0.72
        steps = 40
        for i in range(steps, 0, -1):
            r = max_r * i / steps
            a = int(peak * (1 - (i / steps) ** 2.2))
            pygame.draw.circle(self.check_glow, C.CHECK_RGB + (a,), (SQ / 2, SQ / 2), r)

        ss = 4
        big = pygame.Surface((SQ * ss, SQ * ss), pygame.SRCALPHA)
        pygame.draw.circle(big, C.MOVE_DOT_RGBA, (SQ * ss / 2, SQ * ss / 2), SQ * ss * 0.16)
        self.dot = pygame.transform.smoothscale(big, (SQ, SQ))
        big = pygame.Surface((SQ * ss, SQ * ss), pygame.SRCALPHA)
        pygame.draw.circle(big, C.CAPTURE_RING_RGBA, (SQ * ss / 2, SQ * ss / 2),
                           SQ * ss * 0.48, int(SQ * ss * 0.085))
        self.ring = pygame.transform.smoothscale(big, (SQ, SQ))

        self.drag_hover = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        pygame.draw.rect(self.drag_hover, C.DRAG_HOVER_RGBA, (0, 0, SQ, SQ), 4)

        self.fade_left = pygame.Surface((28, C.MOVE_BAR_HEIGHT), pygame.SRCALPHA)
        for x in range(28):
            pygame.draw.line(self.fade_left, C.BG_DEEP + (int(255 * (1 - x / 28)),),
                             (x, 0), (x, C.MOVE_BAR_HEIGHT))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_enter(self) -> None:
        self.clock.start(WHITE)
        self.app.sound.play("game_start")

    def on_exit(self) -> None:
        self.clock.stop()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        if self.dialog is not None:
            if self.dialog.handle_event(event):
                self.dialog = None
                if not self.game.is_over:
                    self.clock.resume()
            return

        if self.result_modal is not None:
            self._handle_result_modal(event)
            return

        if event.type == pygame.KEYDOWN:
            self._handle_key(event)
            return

        if self.mute_btn.handle_event(event):
            muted = self.app.sound.toggle_mute()
            self.mute_btn.params = {"muted": muted}
            self.mute_btn.tooltip = "Unmute" if muted else "Mute"
            return
        if self.back_btn.handle_event(event):
            self._request_leave()
            return
        if not self.game.is_over:
            if self.resign_btn.handle_event(event):
                self._request_resign()
                return
            if self.draw_btn.handle_event(event):
                self._request_draw()
                return
        elif self.result_btn.handle_event(event):
            self._open_result_modal()
            return

        if self.promotion is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._click_promotion(event.pos)
            return

        if event.type == pygame.MOUSEWHEEL:
            mouse = self.app.mouse_pos()
            if C.MOVE_BAR_Y <= mouse[1] < C.MOVE_BAR_Y + C.MOVE_BAR_HEIGHT:
                self.manual_scroll = True
                max_scroll = max(0, self.tokens_width - (W - 14))
                delta = (event.x - event.y) * 40
                self.scroll_target = clamp(self.scroll_target + delta, 0, max_scroll)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._board_mouse_down(event.pos)
        elif event.type == pygame.MOUSEMOTION and self.drag is not None:
            self._board_mouse_move(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._board_mouse_up(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._deselect()
            self.drag = None

    def _handle_key(self, event) -> None:
        if event.key == pygame.K_ESCAPE:
            if self.promotion is not None:
                self.promotion = None
            elif self.selected is not None:
                self._deselect()
            else:
                self._request_leave()
        elif event.key == pygame.K_m:
            muted = self.app.sound.toggle_mute()
            self.mute_btn.params = {"muted": muted}
            self.mute_btn.tooltip = "Unmute" if muted else "Mute"

    # -- board interaction ---------------------------------------------
    def _board_mouse_down(self, pos) -> None:
        if self.anim is not None:
            self.anim = None
        square = square_at(pos)
        if square is None or self.game.is_over:
            self._deselect()
            return
        if self.selected is not None and square in self.targets:
            self._attempt_move(self.selected, square, animate=True)
            return
        piece = self.game.board.piece_at(square)
        if piece is not None and piece.color == self.game.turn:
            was_selected = square == self.selected
            self._select(square)
            self.drag = {"origin": square, "start": pos, "pos": pos,
                         "active": False, "toggle": was_selected}
            return
        self._deselect()

    def _board_mouse_move(self, pos) -> None:
        drag = self.drag
        drag["pos"] = pos
        if not drag["active"]:
            dx, dy = pos[0] - drag["start"][0], pos[1] - drag["start"][1]
            if dx * dx + dy * dy >= C.DRAG_THRESHOLD_PX ** 2:
                drag["active"] = True

    def _board_mouse_up(self, pos) -> None:
        drag, self.drag = self.drag, None
        if drag is None:
            return
        if drag["active"]:
            target = square_at(pos)
            if target is not None and target != drag["origin"] and target in self.targets:
                self._attempt_move(drag["origin"], target, animate=False)
        elif drag["toggle"]:
            self._deselect()

    def _select(self, square: Square) -> None:
        self.selected = square
        self.targets = self.game.legal_targets(square)

    def _deselect(self) -> None:
        self.selected = None
        self.targets = set()

    # -- moves ---------------------------------------------------------
    def _attempt_move(self, start: Square, end: Square, animate: bool) -> None:
        if self.game.is_promotion_move(start, end):
            self._open_promotion(start, end, animate)
            return
        self._execute(start, end, None, animate)

    def _execute(self, start: Square, end: Square, promotion: Optional[str], animate: bool) -> None:
        record = self.game.make_move(start, end, promotion)
        self._deselect()
        self.promotion = None
        if self.game.is_over:
            self.clock.pause()
        else:
            self.clock.switch()
        self._start_animation(record, animate)
        self._play_move_sound(record)
        self.tokens_dirty = True
        self.manual_scroll = False
        if self.game.is_over:
            self._on_game_over()

    def _start_animation(self, record, animate: bool) -> None:
        applied = record.applied
        pieces = self.app.assets.pieces
        items, hidden, ghosts = [], set(), []
        if animate:
            items.append((pieces.for_piece(applied.placed), square_rect(record.move.start).topleft,
                          square_rect(record.move.end).topleft))
            hidden.add(record.move.end)
            if applied.captured is not None and applied.captured_square is not None:
                ghosts.append((pieces.for_piece(applied.captured),
                               square_rect(applied.captured_square).topleft))
        if applied.rook_move is not None:
            rook_from, rook_to = applied.rook_move
            rook = self.game.board.piece_at(rook_to)
            if rook is not None:
                items.append((pieces.for_piece(rook), square_rect(rook_from).topleft,
                              square_rect(rook_to).topleft))
                hidden.add(rook_to)
        self.anim = SlideAnimation(items, hidden, ghosts) if items else None

    def _play_move_sound(self, record) -> None:
        sound = self.app.sound
        applied = record.applied
        if self.game.is_over:
            sound.play("capture" if applied.captured else "move")
            sound.play("game_end")
        elif record.is_check:
            sound.play("check")
        elif applied.is_promotion:
            sound.play("promote")
        elif applied.is_castle:
            sound.play("castle")
        elif applied.captured is not None:
            sound.play("capture")
        else:
            sound.play("move")

    # -- promotion -----------------------------------------------------
    def _open_promotion(self, start: Square, end: Square, animate: bool) -> None:
        color = self.game.turn
        col = end[1]
        x = C.BOARD_X + col * SQ
        if color == WHITE:
            order = list(C.PROMOTION_CHOICES)
            top = C.BOARD_Y
            cancel = pygame.Rect(x, top + 4 * SQ, SQ, 34)
        else:
            order = list(reversed(C.PROMOTION_CHOICES))
            top = C.BOARD_Y + 4 * SQ
            cancel = pygame.Rect(x, top - 34, SQ, 34)
        options = [(kind, pygame.Rect(x, top + i * SQ, SQ, SQ)) for i, kind in enumerate(order)]
        self.promotion = {"start": start, "end": end, "color": color, "animate": animate,
                          "options": options, "cancel": cancel,
                          "card": pygame.Rect(x, top, SQ, 4 * SQ).union(cancel)}
        self.drag = None
        self.targets = set()

    def _click_promotion(self, pos) -> None:
        promo = self.promotion
        for kind, rect in promo["options"]:
            if rect.collidepoint(pos):
                self._execute(promo["start"], promo["end"], kind, promo["animate"])
                return
        self.promotion = None
        self._deselect()

    # -- dialogs -------------------------------------------------------
    def _open_dialog(self, dialog: ConfirmDialog) -> None:
        self.dialog = dialog
        self.clock.pause()
        self.drag = None

    def _request_leave(self) -> None:
        if self.game.is_over:
            self.app.go(C.STATE_HOME)
            return
        self._open_dialog(ConfirmDialog(
            "Leave match?", ["This game is still in progress.",
                             "It will be abandoned and not saved."],
            "Leave", lambda: self.app.go(C.STATE_HOME), "Stay", confirm_style="danger"))

    def _request_resign(self) -> None:
        color = self.game.turn
        name = self.game.player_name(color)
        self._open_dialog(ConfirmDialog(
            "Resign?", [f"{name} ({C.COLOR_NAMES[color]}), are you sure",
                        "you want to resign this game?"],
            "Resign", lambda: self._finish_by(lambda: self.game.resign(color)),
            confirm_style="danger"))

    def _request_draw(self) -> None:
        offerer = self.game.turn
        receiver = BLACK if offerer == WHITE else WHITE
        self._open_dialog(ConfirmDialog(
            "Draw offered", [f"{self.game.player_name(offerer)} offers a draw.",
                             f"{self.game.player_name(receiver)}, do you accept?"],
            "Accept", lambda: self._finish_by(self.game.agree_draw), "Decline"))

    def _finish_by(self, action: Callable[[], object]) -> None:
        if self.game.is_over:
            return
        action()
        self.clock.pause()
        self._deselect()
        self.promotion = None
        self.tokens_dirty = True
        self.app.sound.play("game_end")
        self._on_game_over()

    # -- game over -----------------------------------------------------
    def _on_game_over(self) -> None:
        self.modal_timer = C.GAME_OVER_MODAL_DELAY
        if not self.saved:
            self.saved = True
            try:
                self.app.history.save_game(self.game, time.time() - self.started_at)
            except OSError as exc:      # disk full / read-only folder
                print(f"[Classical Chess] Could not save match history: {exc}")

    def _open_result_modal(self) -> None:
        card = pygame.Rect(0, 0, 420, 372)
        card.center = (W // 2, C.BOARD_Y + C.BOARD_SIZE // 2)
        bw = (card.w - 48 - 12) // 2
        self.result_modal = {
            "card": card,
            "rematch": Button((card.x + 24, card.bottom - 140, card.w - 48, 58), "Rematch", "primary", 21),
            "new": Button((card.x + 24, card.bottom - 72, bw, 50), "New Game", "secondary", 18),
            "home": Button((card.x + 36 + bw, card.bottom - 72, bw, 50), "Home", "secondary", 18),
            "close": IconButton((card.right - 46, card.y + 8, 38, 38), "close", "View board"),
        }

    def _handle_result_modal(self, event) -> None:
        modal = self.result_modal
        if modal["rematch"].handle_event(event):
            self.app.go(C.STATE_GAME, white_name=self.game.white_name,
                        black_name=self.game.black_name)
        elif modal["new"].handle_event(event):
            self.app.go(C.STATE_SETUP)
        elif modal["home"].handle_event(event):
            self.app.go(C.STATE_HOME)
        elif modal["close"].handle_event(event):
            self.result_modal = None
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.result_modal = None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.anim is not None:
            self.anim.t += dt
            if self.anim.done:
                self.anim = None

        if not self.game.is_over and self.dialog is None:
            flagged = self.clock.flagged()
            if flagged is not None:
                self._finish_by(lambda: self.game.timeout(flagged))

        if self.modal_timer is not None:
            self.modal_timer -= dt
            if self.modal_timer <= 0:
                self.modal_timer = None
                self._open_result_modal()

        if self.tokens_dirty:
            self._rebuild_tokens()
        if not self.manual_scroll:
            self.scroll_target = max(0, self.tokens_width - (W - 14))
        self.scroll = lerp(self.scroll, self.scroll_target, clamp(dt * 12))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface) -> None:
        surface.fill(C.BG_MAIN)
        self._draw_header(surface)
        self._draw_move_bar(surface)
        self._draw_player_bar(surface, C.TOP_BAR_Y, BLACK)
        self._draw_board(surface)
        self._draw_player_bar(surface, C.BOTTOM_BAR_Y, WHITE)
        if self.promotion is not None:
            self._draw_promotion(surface)
        if self.result_modal is not None:
            self._draw_result_modal(surface)
        if self.dialog is not None:
            self.dialog.draw(surface, self.app)
        elif self.result_modal is None:
            for btn in (self.back_btn, self.resign_btn, self.draw_btn, self.mute_btn):
                btn.draw_tooltip(surface, self.app)

    def _draw_header(self, surface) -> None:
        draw_header(surface, self.app, C.APP_TITLE, self.back_btn)
        over = self.game.is_over
        self.resign_btn.visible = not over
        self.draw_btn.visible = not over
        self.resign_btn.draw(surface, self.app, size=22)
        self.draw_btn.draw(surface, self.app, size=26)
        self.mute_btn.draw(surface, self.app, size=24)
        if over and self.result_modal is None:
            self.result_btn.draw(surface, self.app)

    # -- move history strip -------------------------------------------
    def _rebuild_tokens(self) -> None:
        self.tokens_dirty = False
        move_font = self.app.assets.font(17, bold=True)
        num_font = self.app.assets.font(16)
        pieces = self.app.assets.pieces
        tokens: List[dict] = []
        x = 14
        last_index = len(self.game.history) - 1
        for i, record in enumerate(self.game.history):
            if i % 2 == 0:
                img = num_font.render(f"{i // 2 + 1}.", True, C.TEXT_MUTED)
                tokens.append({"kind": "num", "img": img, "x": x, "w": img.get_width()})
                x += img.get_width() + 6
            text, icon = record.san, None
            if record.piece_kind != "P" and not text.startswith("O-"):
                palette = "strip_hollow" if record.color == WHITE else "strip_solid"
                icon = pieces.get(text[0], palette, 20)
                text = text[1:]
            latest = i == last_index
            img = move_font.render(text, True, C.TEXT_PRIMARY if latest else C.TEXT_SECONDARY)
            width = img.get_width() + 16 + (19 if icon else 0)
            tokens.append({"kind": "move", "img": img, "icon": icon, "x": x, "w": width,
                           "latest": latest})
            x += width + 4
            if i % 2 == 1:
                x += 10
        if self.game.is_over:
            result = self.game.outcome.result.replace("1/2", "½")
            img = self.app.assets.font(17, bold=True).render(result, True, C.LIGHT_SQUARE)
            x += 6
            tokens.append({"kind": "result", "img": img, "x": x, "w": img.get_width()})
            x += img.get_width() + 8
        self.tokens = tokens
        self.tokens_width = x

    def _draw_move_bar(self, surface) -> None:
        bar = pygame.Rect(0, C.MOVE_BAR_Y, W, C.MOVE_BAR_HEIGHT)
        pygame.draw.rect(surface, C.BG_DEEP, bar)
        if not self.tokens:
            blit_text(surface, self.app.assets.font(16), "Moves will appear here",
                      C.TEXT_MUTED, midleft=(16, bar.centery))
            return
        previous_clip = surface.get_clip()
        surface.set_clip(bar)
        offset = -int(round(self.scroll))
        for token in self.tokens:
            x = token["x"] + offset
            if x > W or x + token["w"] < 0:
                continue
            if token["kind"] == "move":
                pill = pygame.Rect(x, bar.y + 7, token["w"], bar.h - 14)
                if token["latest"]:
                    fill_rounded(surface, C.BG_RAISED_2, pill, 6)
                tx = x + 8
                if token["icon"] is not None:
                    surface.blit(token["icon"], token["icon"].get_rect(midleft=(tx - 2, bar.centery)))
                    tx += 19
                surface.blit(token["img"], token["img"].get_rect(midleft=(tx, bar.centery)))
            else:
                surface.blit(token["img"], token["img"].get_rect(midleft=(x, bar.centery)))
        if self.scroll > 2:
            surface.blit(self.fade_left, (0, bar.y))
        surface.set_clip(previous_clip)

    # -- player bars ---------------------------------------------------
    def _draw_player_bar(self, surface, y: int, color: str) -> None:
        app = self.app
        game = self.game
        active = not game.is_over and game.turn == color and self.dialog is None

        avatar = pygame.Rect(16, y + 14, 48, 48)
        fill_rounded(surface, C.AVATAR_BG, avatar, 4)
        pawn = app.assets.piece("P", "avatar", 42)
        surface.blit(pawn, pawn.get_rect(center=(avatar.centerx, avatar.centery + 1)))
        chip_color = C.WHITE_PIECE_PALETTE["fill"] if color == WHITE else C.BLACK_PIECE_PALETTE["fill"]
        pygame.draw.circle(surface, C.BG_MAIN, (avatar.right - 2, avatar.bottom - 2), 8)
        pygame.draw.circle(surface, chip_color, (avatar.right - 2, avatar.bottom - 2), 6)

        name_font = app.assets.font(19, bold=True)
        name = truncate(name_font, game.player_name(color), 300)
        blit_text(surface, name_font, name, C.TEXT_PRIMARY, topleft=(76, y + 12))

        # captured enemy pieces + material lead
        enemy_palette = "captured_black" if color == WHITE else "white"
        captured = game.captured_by(color)
        x = 76
        cy = y + 52
        for kind in C.CAPTURE_DISPLAY_ORDER:
            count = captured.count(kind)
            if not count:
                continue
            icon = app.assets.piece(kind, enemy_palette, 22)
            for _ in range(count):
                surface.blit(icon, icon.get_rect(midleft=(x, cy)))
                x += 9
            x += 15
        lead = game.material_advantage(color)
        if lead > 0:
            blit_text(surface, app.assets.font(15, bold=True), f"+{lead}", C.TEXT_MUTED,
                      midleft=(x + (4 if captured else 0), cy))

        # clock
        remaining = self.clock.time_left(color)
        low = remaining < C.LOW_TIME_THRESHOLD
        box = pygame.Rect(W - 16 - 150, y + 14, 150, 48)
        if active:
            bg = C.TIMER_URGENT_BG if low else C.TIMER_ACTIVE_BG
            fg = C.TIMER_ACTIVE_TEXT
        else:
            bg = C.TIMER_INACTIVE_BG
            fg = C.TIMER_URGENT_TEXT if low else C.TIMER_INACTIVE_TEXT
        fill_rounded(surface, bg, box, 6)
        if active:
            angle = (int(remaining) % 4) * 90
            icon = app.assets.icon("clock", 20, fg, angle=angle, filled=True, hand=bg)
            surface.blit(icon, icon.get_rect(midleft=(box.x + 12, box.centery)))
        blit_text(surface, app.assets.font(30, bold=True), ChessClock.format_time(remaining), fg,
                  midright=(box.right - 14, box.centery + 1))

    # -- board ---------------------------------------------------------
    def _draw_board(self, surface) -> None:
        game = self.game
        board = game.board
        pieces = self.app.assets.pieces
        surface.blit(self.board_surface, (C.BOARD_X, C.BOARD_Y))

        last = game.last_move()
        if last is not None:
            for square in (last.move.start, last.move.end):
                surface.blit(self.hl_last, square_rect(square))
        if self.selected is not None:
            surface.blit(self.hl_selected, square_rect(self.selected))

        check_square = None
        if game.is_over and game.status == CHECKMATE:
            check_square = board.find_king(game.turn)
        elif not game.is_over:
            check_square = game.checked_king_square()
        if check_square is not None:
            surface.blit(self.check_glow, square_rect(check_square))

        hidden = set()
        if self.anim is not None:
            hidden |= self.anim.hidden
        if self.drag is not None and self.drag["active"]:
            hidden.add(self.drag["origin"])
        if self.promotion is not None:
            hidden.add(self.promotion["start"])

        if self.anim is not None:
            for image, pos in self.anim.ghosts:
                surface.blit(image, pos)

        hovering_piece = False
        mouse_square = square_at(self.app.mouse_pos())
        for square, piece in board.pieces():
            if square in hidden:
                continue
            surface.blit(pieces.for_piece(piece), square_rect(square))
            if square == mouse_square and piece.color == game.turn and not game.is_over:
                hovering_piece = True

        # legal-move hints
        if self.selected is not None and not game.is_over:
            for target in self.targets:
                image = self.ring if board.piece_at(target) is not None else self.dot
                surface.blit(image, square_rect(target))
            if mouse_square in self.targets:
                hovering_piece = True

        if self.drag is not None and self.drag["active"]:
            hover_square = square_at(self.drag["pos"])
            if hover_square is not None:
                surface.blit(self.drag_hover, square_rect(hover_square))

        if self.anim is not None:
            p = self.anim.progress()
            for image, (x0, y0), (x1, y1) in self.anim.items:
                surface.blit(image, (lerp(x0, x1, p), lerp(y0, y1, p)))

        if self.drag is not None and self.drag["active"]:
            piece = board.piece_at(self.drag["origin"])
            if piece is not None:
                image = pieces.for_piece(piece)
                surface.blit(image, image.get_rect(center=self.drag["pos"]))
                hovering_piece = True

        if hovering_piece and self.promotion is None and self.dialog is None:
            self.app.request_hand_cursor()

    def _draw_promotion(self, surface) -> None:
        promo = self.promotion
        card = promo["card"]
        draw_shadow(surface, card, 4, 18, 150, (0, 6))
        fill_rounded(surface, (255, 255, 255), card, 4)
        mouse = self.app.mouse_pos()
        palette = palette_for(promo["color"])
        for kind, rect in promo["options"]:
            if rect.collidepoint(mouse):
                fill_rounded(surface, (236, 234, 230), rect, 4)
                self.app.request_hand_cursor()
            img = self.app.assets.piece(kind, palette, SQ)
            surface.blit(img, rect)
        cancel = promo["cancel"]
        cancel_bg = (232, 230, 227) if cancel.collidepoint(mouse) else (244, 243, 241)
        fill_rounded(surface, cancel_bg, cancel, 4)
        icon = self.app.assets.icon("close", 16, (120, 118, 115))
        surface.blit(icon, icon.get_rect(center=cancel.center))

    def _draw_result_modal(self, surface) -> None:
        app = self.app
        game = self.game
        modal = self.result_modal
        card = modal["card"]
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 110))
        surface.blit(veil, (0, 0))
        draw_shadow(surface, card, 16, 24, 180, (0, 12))
        fill_rounded(surface, C.BG_SURFACE, card, 16)

        band = pygame.Rect(card.x, card.y, card.w, 104)
        band_color = C.DARK_SQUARE if game.outcome.winner else C.BG_RAISED_2
        fill_rounded(surface, band_color, band, 16)
        pygame.draw.rect(surface, band_color, (band.x, band.bottom - 16, band.w, 16))
        headline_font = app.assets.font(30, bold=True)
        headline = truncate(headline_font, game.result_headline(), card.w - 80)
        blit_text(surface, headline_font, headline, C.TEXT_PRIMARY,
                  midtop=(card.centerx, card.y + 22))
        blit_text(surface, app.assets.font(17), game.result_reason(), (245, 236, 224),
                  midtop=(card.centerx, card.y + 64))

        # avatars & score
        result = game.outcome.result
        scores = ("½", "½") if result == "1/2-1/2" else tuple(result.split("-"))
        for i, color in enumerate((WHITE, BLACK)):
            cx = card.centerx + (-110 if i == 0 else 110)
            tile = pygame.Rect(0, 0, 64, 64)
            tile.center = (cx, card.y + 156)
            winner = game.outcome.winner == color
            fill_rounded(surface, C.LIGHT_SQUARE if color == WHITE else C.DARK_SQUARE, tile, 10)
            if winner:
                fill_rounded(surface, (245, 246, 130), tile.inflate(6, 6), 12, 3)
            img = app.assets.piece("K", palette_for(color), 58)
            surface.blit(img, img.get_rect(center=tile.center))
            name_font = app.assets.font(15, bold=True)
            blit_text(surface, name_font, truncate(name_font, game.player_name(color), 150),
                      C.TEXT_SECONDARY, midtop=(cx, tile.bottom + 8))
        blit_text(surface, app.assets.font(34, bold=True), f"{scores[0]}  –  {scores[1]}",
                  C.TEXT_PRIMARY, center=(card.centerx, card.y + 156))
        blit_text(surface, app.assets.font(14), f"{game.fullmove_count()} moves",
                  C.TEXT_MUTED, center=(card.centerx, card.y + 186))

        for key in ("rematch", "new", "home"):
            modal[key].draw(surface, app)
        modal["close"].draw(surface, app, (245, 236, 224), 20)


# ==========================================================================
# Match history
# ==========================================================================
class HistoryScreen(Screen):
    CARD_H = 108
    GAP = 12
    MARGIN = 16
    LIST_TOP = C.HEADER_HEIGHT + 52

    def __init__(self, app) -> None:
        super().__init__(app)
        self.back_btn = IconButton((8, 8, 40, 40), "back", "Back")
        self.clear_btn = IconButton((W - 48, 8, 40, 40), "trash", "Clear all history")
        self.matches = app.history.load_matches()
        self.scroll = 0.0
        self.target = 0.0
        self.drag_from: Optional[Tuple[int, float]] = None
        self.play_btn = Button((W // 2 - 140, 520, 280, 60), "Play a Game", "primary", 21)
        self.view = pygame.Rect(0, self.LIST_TOP, W, H - self.LIST_TOP)
        self.dialog: Optional[ConfirmDialog] = None
        self._pressed_delete: Optional[int] = None      # index of card whose bin was pressed

    @property
    def content_height(self) -> int:
        n = len(self.matches)
        return self.MARGIN + n * (self.CARD_H + self.GAP)

    def _max_scroll(self) -> float:
        return max(0.0, self.content_height - self.view.h + self.MARGIN)

    # -- card geometry ----------------------------------------------------
    def _card_rect(self, index: int) -> pygame.Rect:
        y = (self.view.y + self.MARGIN - int(round(self.scroll))
             + index * (self.CARD_H + self.GAP))
        return pygame.Rect(self.MARGIN, y, W - 2 * self.MARGIN, self.CARD_H)

    @staticmethod
    def _delete_rect(card: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(card.right - 46, card.y + 10, 34, 34)

    def _delete_hit(self, pos) -> Optional[int]:
        if not self.view.collidepoint(pos):
            return None
        for index in range(len(self.matches)):
            if self._delete_rect(self._card_rect(index)).collidepoint(pos):
                return index
        return None

    # -- deleting ---------------------------------------------------------
    def _close_dialog(self) -> None:
        self.dialog = None

    def _reload(self) -> None:
        self.matches = self.app.history.load_matches()
        self.target = clamp(self.target, 0, self._max_scroll())
        self.scroll = clamp(self.scroll, 0, self._max_scroll())

    def _ask_delete(self, index: int) -> None:
        match = self.matches[index]
        match_id = match.get("id")

        def confirm() -> None:
            self.app.history.delete_match(match_id)
            self._reload()
            self._close_dialog()

        names = f"{match.get('white', '?')} vs {match.get('black', '?')}"
        when = relative_time(match.get("timestamp", 0))
        self.dialog = ConfirmDialog("Delete Match?", [names, f"Played {when.lower()}"],
                                    "Delete", confirm, on_cancel=self._close_dialog,
                                    confirm_style="danger")

    def _ask_clear(self) -> None:
        def confirm() -> None:
            self.app.history.clear()
            self._reload()
            self._close_dialog()

        count = len(self.matches)
        self.dialog = ConfirmDialog(
            "Clear All History?",
            [f"All {count} saved match{'es' if count != 1 else ''} will be deleted.",
             "This cannot be undone."],
            "Delete All", confirm, on_cancel=self._close_dialog, confirm_style="danger")

    def handle_event(self, event) -> None:
        if self.dialog is not None:
            if self.dialog.handle_event(event):
                self.dialog = None
            return
        if self.back_btn.handle_event(event):
            self.app.go(C.STATE_HOME)
            return
        if not self.matches and self.play_btn.handle_event(event):
            self.app.go(C.STATE_SETUP)
            return
        self.clear_btn.visible = bool(self.matches)
        if self.clear_btn.handle_event(event):
            self._ask_clear()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self._delete_hit(event.pos)
            if hit is not None:
                self._pressed_delete = hit
                return
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 \
                and self._pressed_delete is not None:
            pressed, self._pressed_delete = self._pressed_delete, None
            if self._delete_hit(event.pos) == pressed:
                self._ask_delete(pressed)
            return
        if event.type == pygame.KEYDOWN:
            step = {pygame.K_UP: -60, pygame.K_DOWN: 60, pygame.K_PAGEUP: -self.view.h + 60,
                    pygame.K_PAGEDOWN: self.view.h - 60}.get(event.key)
            if event.key == pygame.K_ESCAPE:
                self.app.go(C.STATE_HOME)
            elif event.key == pygame.K_HOME:
                self.target = 0
            elif event.key == pygame.K_END:
                self.target = self._max_scroll()
            elif step is not None:
                self.target = clamp(self.target + step, 0, self._max_scroll())
        elif event.type == pygame.MOUSEWHEEL:
            self.target = clamp(self.target - event.y * 64, 0, self._max_scroll())
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.view.collidepoint(event.pos):
                self.drag_from = (event.pos[1], self.target)
        elif event.type == pygame.MOUSEMOTION and self.drag_from is not None:
            start_y, start_scroll = self.drag_from
            self.target = clamp(start_scroll - (event.pos[1] - start_y), 0, self._max_scroll())
            self.scroll = self.target
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.drag_from = None

    def update(self, dt: float) -> None:
        self.scroll = lerp(self.scroll, self.target, clamp(dt * 14))

    def draw(self, surface) -> None:
        app = self.app
        surface.fill(C.BG_MAIN)
        draw_header(surface, app, "Match History", self.back_btn)
        self.clear_btn.visible = bool(self.matches)
        self.clear_btn.draw(surface, app, C.TEXT_SECONDARY, 24)

        total = len(self.matches)
        decisive = sum(1 for m in self.matches if m.get("winner"))
        summary = f"{total} match{'es' if total != 1 else ''}"
        if total:
            summary += f"  ·  {decisive} decisive  ·  {total - decisive} drawn"
        blit_text(surface, app.assets.font(15, bold=True), summary, C.TEXT_MUTED,
                  midleft=(self.MARGIN + 4, C.HEADER_HEIGHT + 26))

        if not self.matches:
            self._draw_empty(surface)
            self._draw_overlays(surface)
            return

        previous_clip = surface.get_clip()
        surface.set_clip(self.view)
        mouse = app.mouse_pos()
        interactive = self.dialog is None
        for index, match in enumerate(self.matches):
            rect = self._card_rect(index)
            if rect.bottom >= self.view.y and rect.top <= self.view.bottom:
                in_view = interactive and self.view.collidepoint(mouse)
                hover = in_view and rect.collidepoint(mouse)
                self._draw_card(surface, rect, match, hover)
                bin_rect = self._delete_rect(rect)
                bin_hover = in_view and bin_rect.collidepoint(mouse)
                self._draw_delete_button(surface, bin_rect, bin_hover)
        surface.set_clip(previous_clip)

        # fade under the summary line and scrollbar
        max_scroll = self._max_scroll()
        if max_scroll > 0:
            track_h = self.view.h - 16
            thumb_h = max(40, int(track_h * self.view.h / (self.content_height + self.MARGIN)))
            thumb_y = self.view.y + 8 + int((track_h - thumb_h) * clamp(self.scroll / max_scroll))
            fill_rounded(surface, C.BG_RAISED_2, (W - 7, thumb_y, 4, thumb_h), 2)

        self._draw_overlays(surface)

    def _draw_overlays(self, surface) -> None:
        if self.dialog is not None:
            self.dialog.draw(surface, self.app)
        else:
            self.clear_btn.draw_tooltip(surface, self.app)

    def _draw_delete_button(self, surface, rect: pygame.Rect, hover: bool) -> None:
        if hover:
            self.app.request_hand_cursor()
            fill_rounded(surface, C.BTN_DANGER, rect, 8)
            color = C.TEXT_PRIMARY
        else:
            color = C.TEXT_MUTED
        img = self.app.assets.icon("trash", 20, color)
        surface.blit(img, img.get_rect(center=rect.center))

    def _draw_card(self, surface, rect, match: dict, hover: bool) -> None:
        app = self.app
        fill_rounded(surface, C.BG_RAISED if hover else C.BG_SURFACE, rect, 10)
        winner = match.get("winner")
        result = match.get("result", "*")

        badge = pygame.Rect(rect.x + 16, rect.y + 22, 64, 64)
        if winner == "white":
            badge_bg, badge_fg = C.LIGHT_SQUARE, C.TEXT_DARK
        elif winner == "black":
            badge_bg, badge_fg = C.BG_DEEP, C.TEXT_PRIMARY
        else:
            badge_bg, badge_fg = C.BG_RAISED_2, C.TEXT_PRIMARY
        fill_rounded(surface, badge_bg, badge, 10)
        if winner == "black":
            fill_rounded(surface, C.BG_RAISED_2, badge, 10, 2)
        label = "½-½" if result == "1/2-1/2" else result
        blit_text(surface, app.assets.font(19, bold=True), label, badge_fg, center=badge.center)

        name_font = app.assets.font(18, bold=True)
        x = badge.right + 18
        top = rect.y + 18
        for i, (key, fill) in enumerate((("white", C.WHITE_PIECE_PALETTE["fill"]),
                                         ("black", C.BLACK_PIECE_PALETTE["fill"]))):
            if i == 1:
                vs = blit_text(surface, app.assets.font(15), "vs", C.TEXT_MUTED, midleft=(x, top + 11))
                x = vs.right + 10
            pygame.draw.circle(surface, C.BG_DEEP, (x + 7, top + 11), 8)
            pygame.draw.circle(surface, fill, (x + 7, top + 11), 6)
            name = truncate(name_font, str(match.get(key, "?")), 150)
            name_rect = blit_text(surface, name_font, name,
                                  C.TEXT_PRIMARY if winner in (key, None) else C.TEXT_SECONDARY,
                                  midleft=(x + 20, top + 11))
            x = name_rect.right + 10

        reason = match.get("reason_text", "")
        if winner:
            winner_name = match.get(winner, winner.title())
            line = f"{winner_name} won {reason}".strip()
        elif reason.startswith(("by ", "on ")):
            line = f"Draw {reason}"
        else:
            line = f"Draw · {reason}" if reason else "Draw"
        line_font = app.assets.font(16)
        blit_text(surface, line_font, truncate(line_font, line, rect.right - badge.right - 40),
                  C.TEXT_SECONDARY, topleft=(badge.right + 18, rect.y + 46))

        moves = match.get("move_count", 0)
        details = f"{moves} move{'s' if moves != 1 else ''}"
        duration = match.get("duration_seconds")
        if duration:
            minutes, seconds = divmod(int(duration), 60)
            details += f"  ·  {minutes}m {seconds:02d}s"
        blit_text(surface, app.assets.font(14), details, C.TEXT_MUTED,
                  topleft=(badge.right + 18, rect.y + 74))

        when = relative_time(match.get("timestamp", 0))
        blit_text(surface, app.assets.font(14, bold=True), when, C.TEXT_MUTED,
                  topright=(rect.right - 16, rect.y + 76))

    def _draw_empty(self, surface) -> None:
        app = self.app
        img = app.assets.piece("R", "splash_dark", 140)
        surface.blit(img, img.get_rect(center=(W // 2, 300)))
        blit_text(surface, app.assets.font(24, bold=True), "No matches yet", C.TEXT_PRIMARY,
                  midtop=(W // 2, 390))
        blit_text(surface, app.assets.font(16), "Finished games are saved here automatically.",
                  C.TEXT_MUTED, midtop=(W // 2, 428))
        self.play_btn.draw(surface, app)
