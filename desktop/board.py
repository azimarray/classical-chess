"""
board.py — 8x8 board state, move execution, cloning and FEN I/O.

The Board holds *position* state only (pieces, side to move, castling rights,
en-passant square, move clocks). Game-level concerns such as legality
filtering, notation, repetition and results live in game.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Set, Tuple

from constants import BLACK, START_FEN, WHITE
from pieces import (
    King, Pawn, Piece, Square, create_piece, in_bounds, opposite,
    parse_square, piece_from_symbol, square_name,
)

# Corner square -> castling right lost when a piece moves from / to it
_ROOK_CORNERS = {(7, 7): "K", (7, 0): "Q", (0, 7): "k", (0, 0): "q"}
_CASTLING_ORDER = "KQkq"


@dataclass
class AppliedMove:
    """Everything the UI and the rules controller need to know about a move
    that has just been executed on the board."""

    move: object                    # pieces.Move
    piece: Piece                    # piece that moved (pre-promotion)
    placed: Piece                   # piece now standing on move.end
    captured: Optional[Piece]
    captured_square: Optional[Square]
    rook_move: Optional[Tuple[Square, Square]]   # castling rook path
    is_castle: bool
    is_en_passant: bool
    is_promotion: bool


class Board:
    def __init__(self, fen: Optional[str] = START_FEN) -> None:
        self.grid: List[List[Optional[Piece]]] = [[None] * 8 for _ in range(8)]
        self.turn: str = WHITE
        self.castling_rights: Set[str] = set()
        self.en_passant_square: Optional[Square] = None
        self.halfmove_clock: int = 0
        self.fullmove_number: int = 1
        if fen:
            self.load_fen(fen)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def empty(cls) -> "Board":
        return cls(fen=None)

    @classmethod
    def from_fen(cls, fen: str) -> "Board":
        return cls(fen=fen)

    def copy(self) -> "Board":
        """Deep clone used to simulate moves when testing for self-check."""
        clone = Board.empty()
        clone.grid = [[p.clone() if p else None for p in row] for row in self.grid]
        clone.turn = self.turn
        clone.castling_rights = set(self.castling_rights)
        clone.en_passant_square = self.en_passant_square
        clone.halfmove_clock = self.halfmove_clock
        clone.fullmove_number = self.fullmove_number
        return clone

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    def piece_at(self, square: Square) -> Optional[Piece]:
        row, col = square
        return self.grid[row][col]

    def set_piece(self, square: Square, piece: Optional[Piece]) -> None:
        row, col = square
        self.grid[row][col] = piece

    def pieces(self, color: Optional[str] = None) -> Iterator[Tuple[Square, Piece]]:
        for row in range(8):
            for col in range(8):
                piece = self.grid[row][col]
                if piece is not None and (color is None or piece.color == color):
                    yield (row, col), piece

    def find_king(self, color: str) -> Optional[Square]:
        for square, piece in self.pieces(color):
            if isinstance(piece, King):
                return square
        return None

    # ------------------------------------------------------------------
    # Attack detection
    # ------------------------------------------------------------------
    def is_square_attacked(self, square: Square, by_color: str) -> bool:
        for origin, piece in self.pieces(by_color):
            for target in piece.attacks(self, origin):
                if target == square:
                    return True
        return False

    def in_check(self, color: str) -> bool:
        king_square = self.find_king(color)
        if king_square is None:
            return False
        return self.is_square_attacked(king_square, opposite(color))

    # ------------------------------------------------------------------
    # Move execution
    # ------------------------------------------------------------------
    def make_move(self, move) -> AppliedMove:
        """Execute a move (assumed legal). Special moves are recognised from
        geometry, so the flags on Move are not required to be set."""
        start, end = move.start, move.end
        piece = self.piece_at(start)
        if piece is None:
            raise ValueError(f"No piece on {square_name(start)}")

        is_pawn = isinstance(piece, Pawn)
        is_castle = isinstance(piece, King) and abs(end[1] - start[1]) == 2
        is_en_passant = (is_pawn and start[1] != end[1]
                         and self.piece_at(end) is None
                         and end == self.en_passant_square)
        is_double_push = is_pawn and abs(end[0] - start[0]) == 2

        captured_square: Optional[Square] = (start[0], end[1]) if is_en_passant else end
        captured = self.piece_at(captured_square)
        if captured is None:
            captured_square = None
        elif captured_square != end:
            self.set_piece(captured_square, None)

        # Move / promote
        self.set_piece(start, None)
        placed = piece
        is_promotion = is_pawn and end[0] in (0, 7)
        if is_promotion:
            placed = create_piece(move.promotion or "Q", piece.color, has_moved=True)
        else:
            piece.has_moved = True
        self.set_piece(end, placed)

        # Castling rook
        rook_move = None
        if is_castle:
            row = start[0]
            rook_from, rook_to = ((row, 7), (row, 5)) if end[1] == 6 else ((row, 0), (row, 3))
            rook = self.piece_at(rook_from)
            self.set_piece(rook_from, None)
            self.set_piece(rook_to, rook)
            if rook is not None:
                rook.has_moved = True
            rook_move = (rook_from, rook_to)

        # Castling rights
        if isinstance(piece, King):
            self.castling_rights -= {"K", "Q"} if piece.color == WHITE else {"k", "q"}
        for corner in (start, end):
            right = _ROOK_CORNERS.get(corner)
            if right:
                self.castling_rights.discard(right)

        # En-passant target
        self.en_passant_square = ((start[0] + end[0]) // 2, start[1]) if is_double_push else None

        # Clocks & turn
        if is_pawn or captured is not None:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1
        if self.turn == BLACK:
            self.fullmove_number += 1
        self.turn = opposite(self.turn)

        return AppliedMove(move=move, piece=piece, placed=placed, captured=captured,
                           captured_square=captured_square, rook_move=rook_move,
                           is_castle=is_castle, is_en_passant=is_en_passant,
                           is_promotion=is_promotion)

    # ------------------------------------------------------------------
    # FEN
    # ------------------------------------------------------------------
    def load_fen(self, fen: str) -> None:
        fields = fen.split()
        if len(fields) < 4:
            raise ValueError(f"Invalid FEN: {fen!r}")
        placement, turn, castling, ep = fields[:4]
        halfmove = fields[4] if len(fields) > 4 else "0"
        fullmove = fields[5] if len(fields) > 5 else "1"

        ranks = placement.split("/")
        if len(ranks) != 8:
            raise ValueError("FEN placement must have 8 ranks")
        self.grid = [[None] * 8 for _ in range(8)]
        for row, rank in enumerate(ranks):
            col = 0
            for char in rank:
                if char.isdigit():
                    col += int(char)
                else:
                    if col > 7:
                        raise ValueError("Too many squares in FEN rank")
                    self.grid[row][col] = piece_from_symbol(char)
                    col += 1
            if col != 8:
                raise ValueError(f"FEN rank {8 - row} does not have 8 squares")

        if turn not in (WHITE, BLACK):
            raise ValueError("FEN side to move must be 'w' or 'b'")
        self.turn = turn
        self.castling_rights = set() if castling == "-" else set(castling) & set(_CASTLING_ORDER)
        self.en_passant_square = None if ep == "-" else parse_square(ep)
        self.halfmove_clock = int(halfmove)
        self.fullmove_number = int(fullmove)

        # Derive has_moved flags (cosmetic; legality uses castling_rights)
        for square, piece in self.pieces():
            if isinstance(piece, Pawn):
                piece.has_moved = square[0] != piece.start_row
            elif isinstance(piece, King):
                home = (7, 4) if piece.color == WHITE else (0, 4)
                rights = {"K", "Q"} if piece.color == WHITE else {"k", "q"}
                piece.has_moved = square != home or not (rights & self.castling_rights)
            else:
                right = _ROOK_CORNERS.get(square)
                piece.has_moved = not (right and right in self.castling_rights
                                       and piece.kind == "R")

    def placement_fen(self) -> str:
        rows = []
        for row in self.grid:
            empty = 0
            out = ""
            for piece in row:
                if piece is None:
                    empty += 1
                else:
                    if empty:
                        out += str(empty)
                        empty = 0
                    out += piece.symbol
            if empty:
                out += str(empty)
            rows.append(out)
        return "/".join(rows)

    def castling_fen(self) -> str:
        rights = "".join(c for c in _CASTLING_ORDER if c in self.castling_rights)
        return rights or "-"

    def to_fen(self) -> str:
        ep = square_name(self.en_passant_square) if self.en_passant_square else "-"
        return (f"{self.placement_fen()} {self.turn} {self.castling_fen()} {ep} "
                f"{self.halfmove_clock} {self.fullmove_number}")

    def position_key(self) -> str:
        """Identity of a position for repetition detection (FIDE 9.2):
        same placement, side to move, castling rights and *available*
        en-passant capture."""
        ep = "-"
        if self.en_passant_square is not None:
            ep_row, ep_col = self.en_passant_square
            pawn_row = ep_row + (1 if self.turn == WHITE else -1)
            for d_col in (-1, 1):
                col = ep_col + d_col
                if in_bounds(pawn_row, col):
                    piece = self.piece_at((pawn_row, col))
                    if isinstance(piece, Pawn) and piece.color == self.turn:
                        ep = square_name(self.en_passant_square)
                        break
        return f"{self.placement_fen()} {self.turn} {self.castling_fen()} {ep}"

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        lines = []
        for row in range(8):
            cells = [(p.symbol if p else ".") for p in self.grid[row]]
            lines.append(f"{8 - row} " + " ".join(cells))
        lines.append("  a b c d e f g h")
        return "\n".join(lines)
