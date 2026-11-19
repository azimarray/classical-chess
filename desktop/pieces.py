"""
pieces.py — Piece model and pseudo-legal move generation.

Coordinates are (row, col) tuples. Row 0 is rank 8 (Black's back rank),
row 7 is rank 1 (White's back rank); col 0 is the a-file.

Pieces only know how they *move*. Whether a move leaves the mover's king in
check is decided by the rules controller in game.py, which simulates each
candidate on a cloned board.

Pieces interact with the board exclusively through a small duck-typed API:
    board.piece_at(square)            -> Piece | None
    board.en_passant_square           -> square | None
    board.castling_rights             -> set of 'K', 'Q', 'k', 'q'
    board.is_square_attacked(sq, by)  -> bool
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple, Type

from constants import BLACK, PIECE_VALUES, WHITE

Square = Tuple[int, int]
FILES = "abcdefgh"


# --------------------------------------------------------------------------
# Square helpers
# --------------------------------------------------------------------------
def opposite(color: str) -> str:
    return BLACK if color == WHITE else WHITE


def in_bounds(row: int, col: int) -> bool:
    return 0 <= row < 8 and 0 <= col < 8


def square_name(square: Square) -> str:
    row, col = square
    return f"{FILES[col]}{8 - row}"


def parse_square(name: str) -> Square:
    name = name.strip().lower()
    if len(name) != 2 or name[0] not in FILES or name[1] not in "12345678":
        raise ValueError(f"Invalid square name: {name!r}")
    return 8 - int(name[1]), FILES.index(name[0])


def is_light_square(square: Square) -> bool:
    row, col = square
    return (row + col) % 2 == 0


# --------------------------------------------------------------------------
# Move value object
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Move:
    """An immutable move. Flags are informational; Board.make_move derives
    special-move handling from geometry so hand-built moves still work."""

    start: Square
    end: Square
    promotion: Optional[str] = None     # 'Q', 'R', 'B', 'N'
    is_en_passant: bool = False
    is_castle: bool = False
    is_double_push: bool = False

    def uci(self) -> str:
        promo = self.promotion.lower() if self.promotion else ""
        return f"{square_name(self.start)}{square_name(self.end)}{promo}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Move({self.uci()})"


# --------------------------------------------------------------------------
# Abstract base piece
# --------------------------------------------------------------------------
class Piece(ABC):
    """Abstract chess piece."""

    kind: str = "?"         # 'P', 'N', 'B', 'R', 'Q', 'K'
    name: str = "piece"

    def __init__(self, color: str, has_moved: bool = False) -> None:
        if color not in (WHITE, BLACK):
            raise ValueError(f"Invalid colour: {color!r}")
        self.color = color
        self.has_moved = has_moved

    # -- identity --------------------------------------------------------
    @property
    def value(self) -> int:
        return PIECE_VALUES[self.kind]

    @property
    def symbol(self) -> str:
        """FEN letter: uppercase for White, lowercase for Black."""
        return self.kind if self.color == WHITE else self.kind.lower()

    def clone(self) -> "Piece":
        return type(self)(self.color, self.has_moved)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.color})"

    # -- movement --------------------------------------------------------
    @abstractmethod
    def attacks(self, board, square: Square) -> Iterator[Square]:
        """Squares this piece attacks (used for check detection)."""

    @abstractmethod
    def pseudo_legal_moves(self, board, square: Square) -> List[Move]:
        """Moves obeying piece movement rules, ignoring self-check."""

    def _is_enemy_or_empty(self, board, target: Square) -> bool:
        occupant = board.piece_at(target)
        return occupant is None or occupant.color != self.color


# --------------------------------------------------------------------------
# Movement families
# --------------------------------------------------------------------------
class _SlidingPiece(Piece):
    directions: Tuple[Tuple[int, int], ...] = ()

    def attacks(self, board, square: Square) -> Iterator[Square]:
        row0, col0 = square
        for d_row, d_col in self.directions:
            row, col = row0 + d_row, col0 + d_col
            while in_bounds(row, col):
                yield (row, col)
                if board.piece_at((row, col)) is not None:
                    break
                row += d_row
                col += d_col

    def pseudo_legal_moves(self, board, square: Square) -> List[Move]:
        return [Move(square, t) for t in self.attacks(board, square)
                if self._is_enemy_or_empty(board, t)]


class _LeapingPiece(Piece):
    offsets: Tuple[Tuple[int, int], ...] = ()

    def attacks(self, board, square: Square) -> Iterator[Square]:
        row0, col0 = square
        for d_row, d_col in self.offsets:
            row, col = row0 + d_row, col0 + d_col
            if in_bounds(row, col):
                yield (row, col)

    def pseudo_legal_moves(self, board, square: Square) -> List[Move]:
        return [Move(square, t) for t in self.attacks(board, square)
                if self._is_enemy_or_empty(board, t)]


_ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
_DIAGONAL = ((-1, -1), (-1, 1), (1, -1), (1, 1))


# --------------------------------------------------------------------------
# Concrete pieces
# --------------------------------------------------------------------------
class Rook(_SlidingPiece):
    kind = "R"
    name = "rook"
    directions = _ORTHOGONAL


class Bishop(_SlidingPiece):
    kind = "B"
    name = "bishop"
    directions = _DIAGONAL


class Queen(_SlidingPiece):
    kind = "Q"
    name = "queen"
    directions = _ORTHOGONAL + _DIAGONAL


class Knight(_LeapingPiece):
    kind = "N"
    name = "knight"
    offsets = ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
               (1, -2), (1, 2), (2, -1), (2, 1))


class King(_LeapingPiece):
    kind = "K"
    name = "king"
    offsets = _ORTHOGONAL + _DIAGONAL

    def pseudo_legal_moves(self, board, square: Square) -> List[Move]:
        moves = super().pseudo_legal_moves(board, square)
        moves.extend(self._castling_moves(board, square))
        return moves

    def _castling_moves(self, board, square: Square) -> List[Move]:
        """Castling requires: rights intact, rook present, empty path,
        king not in check and not passing through / landing on an attacked
        square. The landing square is re-verified by the legality filter."""
        home = 7 if self.color == WHITE else 0
        if square != (home, 4):
            return []
        rights = board.castling_rights
        king_side, queen_side = ("K", "Q") if self.color == WHITE else ("k", "q")
        if king_side not in rights and queen_side not in rights:
            return []
        enemy = opposite(self.color)
        if board.is_square_attacked(square, enemy):
            return []

        moves: List[Move] = []

        def rook_ready(col: int) -> bool:
            rook = board.piece_at((home, col))
            return isinstance(rook, Rook) and rook.color == self.color

        if (king_side in rights and rook_ready(7)
                and all(board.piece_at((home, c)) is None for c in (5, 6))
                and not any(board.is_square_attacked((home, c), enemy) for c in (5, 6))):
            moves.append(Move(square, (home, 6), is_castle=True))

        if (queen_side in rights and rook_ready(0)
                and all(board.piece_at((home, c)) is None for c in (1, 2, 3))
                and not any(board.is_square_attacked((home, c), enemy) for c in (2, 3))):
            moves.append(Move(square, (home, 2), is_castle=True))
        return moves


class Pawn(Piece):
    kind = "P"
    name = "pawn"

    @property
    def direction(self) -> int:
        return -1 if self.color == WHITE else 1

    @property
    def start_row(self) -> int:
        return 6 if self.color == WHITE else 1

    @property
    def promotion_row(self) -> int:
        return 0 if self.color == WHITE else 7

    def attacks(self, board, square: Square) -> Iterator[Square]:
        row, col = square
        target_row = row + self.direction
        for d_col in (-1, 1):
            if in_bounds(target_row, col + d_col):
                yield (target_row, col + d_col)

    def _with_promotions(self, start: Square, end: Square, **flags) -> List[Move]:
        if end[0] == self.promotion_row:
            return [Move(start, end, promotion=p, **flags) for p in ("Q", "R", "B", "N")]
        return [Move(start, end, **flags)]

    def pseudo_legal_moves(self, board, square: Square) -> List[Move]:
        moves: List[Move] = []
        row, col = square
        one_step = (row + self.direction, col)

        if in_bounds(*one_step) and board.piece_at(one_step) is None:
            moves.extend(self._with_promotions(square, one_step))
            two_step = (row + 2 * self.direction, col)
            if row == self.start_row and board.piece_at(two_step) is None:
                moves.append(Move(square, two_step, is_double_push=True))

        for target in self.attacks(board, square):
            occupant = board.piece_at(target)
            if occupant is not None and occupant.color != self.color:
                moves.extend(self._with_promotions(square, target))
            elif occupant is None and target == board.en_passant_square:
                victim = board.piece_at((row, target[1]))
                if isinstance(victim, Pawn) and victim.color != self.color:
                    moves.append(Move(square, target, is_en_passant=True))
        return moves


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------
PIECE_CLASSES: Dict[str, Type[Piece]] = {
    "P": Pawn, "N": Knight, "B": Bishop, "R": Rook, "Q": Queen, "K": King,
}


def create_piece(kind: str, color: str, has_moved: bool = False) -> Piece:
    try:
        return PIECE_CLASSES[kind.upper()](color, has_moved)
    except KeyError as exc:
        raise ValueError(f"Unknown piece kind: {kind!r}") from exc


def piece_from_symbol(symbol: str) -> Piece:
    """Create a piece from a FEN letter ('P' white pawn, 'n' black knight)."""
    color = WHITE if symbol.isupper() else BLACK
    return create_piece(symbol.upper(), color)
