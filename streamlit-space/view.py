"""
view.py — Turns a Game into pictures and text for the page.

Everything here is plain Python (no Streamlit): the board is an SVG string,
the rest is text. That keeps it testable.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, List, Optional, Tuple

from constants import BLACK, WHITE
from game import Game
from pieces import Square, is_light_square, square_name
from timer import ChessClock

LIGHT = "#ECD3B1"
DARK = "#B58763"
GOLD = "#F4D374"

# The filled chess glyphs are used for both colours; the colours come from fill/stroke.
# U+FE0E asks for the plain text look instead of an emoji.
_GLYPH = {"K": "♚", "Q": "♛", "R": "♜", "B": "♝", "N": "♞", "P": "♟"}
PIECE_NAMES = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight", "P": "Pawn"}
_FONTS = "'DejaVu Sans','Segoe UI Symbol','Noto Sans Symbols 2','Apple Symbols','Arial Unicode MS',serif"


def glyph(kind: str) -> str:
    return _GLYPH[kind] + "︎"


# --------------------------------------------------------------------------
# Board
# --------------------------------------------------------------------------
def board_svg(game: Game, selected: Optional[Square] = None,
              targets: Iterable[Square] = (), square: int = 70) -> str:
    s = square
    left, top = 26, 8
    width, height = left + 8 * s + 8, top + 8 * s + 26
    targets = set(targets)
    last = game.last_move()
    last_squares = {last.move.start, last.move.end} if last else set()
    check_sq = game.checked_king_square()
    capture_targets = set()
    if selected is not None:
        for m in game.legal_moves_from(selected):
            if game.board.piece_at(m.end) is not None or m.is_en_passant:
                capture_targets.add(m.end)

    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '<defs><radialGradient id="chk"><stop offset="0" stop-color="#ff3b30" stop-opacity="0.95"/>'
        '<stop offset="0.65" stop-color="#e0352b" stop-opacity="0.55"/>'
        '<stop offset="1" stop-color="#e0352b" stop-opacity="0"/></radialGradient></defs>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#262421"/>',
    ]
    for row in range(8):
        for col in range(8):
            sq = (row, col)
            x, y = left + col * s, top + row * s
            out.append(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{LIGHT if is_light_square(sq) else DARK}"/>')
            if sq in last_squares:
                out.append(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{GOLD}" fill-opacity="0.5"/>')
            if sq == selected:
                out.append(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{GOLD}" fill-opacity="0.85"/>')
            if sq == check_sq:
                out.append(f'<circle cx="{x + s / 2}" cy="{y + s / 2}" r="{s * 0.5}" fill="url(#chk)"/>')
            piece = game.board.piece_at(sq)
            if piece is not None:
                white = piece.color == WHITE
                out.append(
                    f'<text x="{x + s / 2}" y="{y + s * 0.74}" text-anchor="middle" font-size="{s * 0.82:.1f}" '
                    f'font-family="{_FONTS}" fill="{"#FBF6EC" if white else "#26221F"}" '
                    f'stroke="{"#2B2622" if white else "#F2E6CF"}" stroke-width="{1.6 if white else 1.0}" '
                    f'paint-order="stroke">{glyph(piece.kind)}</text>')
            if sq in targets:
                if sq in capture_targets:
                    out.append(f'<circle cx="{x + s / 2}" cy="{y + s / 2}" r="{s * 0.43}" fill="none" '
                               f'stroke="#262421" stroke-opacity="0.45" stroke-width="6"/>')
                else:
                    out.append(f'<circle cx="{x + s / 2}" cy="{y + s / 2}" r="{s * 0.16}" fill="#262421" fill-opacity="0.38"/>')
    for i in range(8):
        out.append(f'<text x="{left + i * s + s / 2}" y="{top + 8 * s + 18}" text-anchor="middle" font-size="14" '
                   f'font-family="sans-serif" fill="#A8A29A">{"abcdefgh"[i]}</text>')
        out.append(f'<text x="{left - 9}" y="{top + i * s + s / 2 + 5}" text-anchor="middle" font-size="14" '
                   f'font-family="sans-serif" fill="#A8A29A">{8 - i}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Move pickers
# --------------------------------------------------------------------------
def from_options(game: Game) -> List[Tuple[str, Square]]:
    """Pieces the side to move can move, as ('e2 · Pawn', square)."""
    squares = sorted({m.start for m in game.legal_moves()}, key=lambda sq: (sq[1], -sq[0]))
    return [(f"{square_name(sq)} · {PIECE_NAMES[game.board.piece_at(sq).kind]}", sq) for sq in squares]


def to_options(game: Game, start: Square) -> List[Tuple[str, Square]]:
    """Where the chosen piece can go, as ('e4', square) or ('d5 · takes Pawn', square)."""
    out = []
    for sq in sorted(game.legal_targets(start), key=lambda sq: (sq[1], -sq[0])):
        victim = game.board.piece_at(sq)
        if victim is not None:
            out.append((f"{square_name(sq)} · takes {PIECE_NAMES[victim.kind]}", sq))
        elif game.board.piece_at(start).kind == "P" and sq[1] != start[1]:
            out.append((f"{square_name(sq)} · takes Pawn (en passant)", sq))
        else:
            out.append((square_name(sq), sq))
    return out


# --------------------------------------------------------------------------
# Text pieces
# --------------------------------------------------------------------------
def moves_text(game: Game) -> str:
    sans = game.san_list()
    lines = []
    for i in range(0, len(sans), 2):
        pair = "  ".join(sans[i:i + 2])
        lines.append(f"{i // 2 + 1}. {pair}")
    return "\n".join(lines)


def captured_text(game: Game, color: str) -> str:
    """Pieces `color` has taken, in order of value, plus the material lead (+3)."""
    order = "PNBRQ"
    kinds = sorted(game.captured_by(color), key=lambda k: order.index(k) if k in order else 9)
    text = "".join(glyph(k) for k in kinds)
    lead = game.material_advantage(color)
    return f"{text} +{lead}".strip() if lead else text


def clock_text(clock: ChessClock, color: str) -> str:
    return ChessClock.format_time(clock.time_left(color))


def player_card(game: Game, clock: ChessClock, color: str) -> str:
    """HTML for one player bar: name, captured pieces and the clock."""
    active = (game.turn == color) and not game.is_over
    low = clock.is_low(color)
    name = escape(game.player_name(color))
    dot = "#FBF6EC" if color == WHITE else "#26221F"
    border = GOLD if active else "#3a3835"
    clock_color = "#ff6b5e" if low else "#ECD3B1"
    return (
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;'
        f'padding:10px 14px;margin-bottom:8px;border-radius:10px;background:#2C2B29;border:2px solid {border}">'
        f'<div><div style="font-weight:700;font-size:18px"><span style="display:inline-block;width:12px;height:12px;'
        f'border-radius:50%;background:{dot};border:1px solid #6b665e;margin-right:8px"></span>{name}</div>'
        f'<div style="min-height:22px;color:#A8A29A;font-size:16px;font-family:{_FONTS}">{captured_text(game, color)}</div></div>'
        f'<div style="font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;color:{clock_color}">'
        f'{clock_text(clock, color)}</div></div>')


def status_line(game: Game) -> str:
    if game.is_over:
        return f"{game.result_title()} · {game.result_headline()}"
    who = game.player_name(game.turn)
    return f"{who} to move" + (" · CHECK" if game.in_check() else "")
