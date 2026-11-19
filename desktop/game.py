"""
game.py — Rules controller.

Responsibilities
  * Legal move generation (pseudo-legal moves filtered by simulating each one
    on a cloned board and rejecting those that leave the mover in check).
  * Turn switching and move execution.
  * Standard Algebraic Notation (SAN) with disambiguation, '+', '#', '=Q'.
  * Captured-piece tracking and live material balance.
  * Game termination: checkmate, stalemate, insufficient material,
    threefold repetition, 50-move rule, resignation, draw agreement, timeout.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from board import AppliedMove, Board
from constants import BLACK, COLOR_NAMES, PIECE_VALUES, START_FEN, WHITE
from pieces import (
    Bishop, King, Knight, Move, Pawn, Square, is_light_square, opposite,
    square_name,
)

# --------------------------------------------------------------------------
# Status / reason constants
# --------------------------------------------------------------------------
ONGOING = "ongoing"
CHECKMATE = "checkmate"
STALEMATE = "stalemate"
INSUFFICIENT_MATERIAL = "insufficient_material"
THREEFOLD_REPETITION = "threefold_repetition"
FIFTY_MOVE_RULE = "fifty_move_rule"
RESIGNATION = "resignation"
DRAW_AGREEMENT = "draw_agreement"
TIMEOUT = "timeout"
TIMEOUT_VS_INSUFFICIENT = "timeout_vs_insufficient_material"

REASON_TEXT = {
    CHECKMATE: "by checkmate",
    STALEMATE: "by stalemate",
    INSUFFICIENT_MATERIAL: "by insufficient material",
    THREEFOLD_REPETITION: "by threefold repetition",
    FIFTY_MOVE_RULE: "by the 50-move rule",
    RESIGNATION: "by resignation",
    DRAW_AGREEMENT: "by agreement",
    TIMEOUT: "on time",
    TIMEOUT_VS_INSUFFICIENT: "timeout vs insufficient material",
}
REASON_TITLE = {
    CHECKMATE: "Checkmate",
    STALEMATE: "Stalemate",
    INSUFFICIENT_MATERIAL: "Insufficient Material",
    THREEFOLD_REPETITION: "Threefold Repetition",
    FIFTY_MOVE_RULE: "50-Move Rule",
    RESIGNATION: "Resignation",
    DRAW_AGREEMENT: "Draw Agreed",
    TIMEOUT: "Time Out",
    TIMEOUT_VS_INSUFFICIENT: "Time Out",
}


class IllegalMoveError(ValueError):
    """Raised when a move is not legal in the current position."""


class GameOverError(RuntimeError):
    """Raised when trying to move after the game has ended."""


@dataclass
class MoveRecord:
    move: Move
    san: str
    color: str
    piece_kind: str
    captured_kind: Optional[str]
    applied: AppliedMove
    fen_after: str
    is_check: bool = False
    is_checkmate: bool = False


# --------------------------------------------------------------------------
# Pure rule functions (operate on a Board; reused by tests / perft)
# --------------------------------------------------------------------------
def is_move_safe(board: Board, move: Move, color: str) -> bool:
    """True if `move` does not leave `color`'s king in check."""
    simulation = board.copy()
    simulation.make_move(move)
    return not simulation.in_check(color)


def generate_legal_moves(board: Board, color: Optional[str] = None) -> List[Move]:
    color = color or board.turn
    legal: List[Move] = []
    for square, piece in list(board.pieces(color)):
        for move in piece.pseudo_legal_moves(board, square):
            if is_move_safe(board, move, color):
                legal.append(move)
    return legal


def is_insufficient_material(board: Board) -> bool:
    """Dead positions where neither side can ever checkmate:
    K v K, K+minor v K, and any number of bishops all on one square colour."""
    minors = []
    for square, piece in board.pieces():
        if isinstance(piece, King):
            continue
        if isinstance(piece, (Knight, Bishop)):
            minors.append((square, piece))
        else:
            return False                     # pawn, rook or queen present
    if len(minors) <= 1:
        return True
    if all(isinstance(p, Bishop) for _, p in minors):
        colours = {is_light_square(sq) for sq, _ in minors}
        return len(colours) == 1
    return False


def can_checkmate(board: Board, color: str) -> bool:
    """Whether `color` has enough material to possibly deliver mate. Used for
    'timeout vs insufficient material' (FIDE 6.9). A lone king, or a king with
    a single minor piece and nothing else, cannot force a mate."""
    material = [p for _, p in board.pieces(color) if not isinstance(p, King)]
    if not material:
        return False
    if len(material) == 1 and isinstance(material[0], (Knight, Bishop)):
        return False
    return True


def move_to_san(board: Board, move: Move, legal_moves: List[Move]) -> str:
    """SAN for `move` in `board` (before it is played), without +/# suffix."""
    piece = board.piece_at(move.start)
    if piece is None:
        raise IllegalMoveError("No piece on start square")

    if isinstance(piece, King) and abs(move.end[1] - move.start[1]) == 2:
        return "O-O" if move.end[1] == 6 else "O-O-O"

    target = square_name(move.end)
    if isinstance(piece, Pawn):
        is_capture = move.start[1] != move.end[1]
        san = f"{square_name(move.start)[0]}x{target}" if is_capture else target
        if move.promotion:
            san += f"={move.promotion}"
        return san

    is_capture = board.piece_at(move.end) is not None
    rivals = [m.start for m in legal_moves
              if m.end == move.end and m.start != move.start
              and (other := board.piece_at(m.start)) is not None
              and other.kind == piece.kind]
    disambiguation = ""
    if rivals:
        start_name = square_name(move.start)
        if all(r[1] != move.start[1] for r in rivals):
            disambiguation = start_name[0]
        elif all(r[0] != move.start[0] for r in rivals):
            disambiguation = start_name[1]
        else:
            disambiguation = start_name
    return f"{piece.kind}{disambiguation}{'x' if is_capture else ''}{target}"


# --------------------------------------------------------------------------
# Game controller
# --------------------------------------------------------------------------
@dataclass
class GameResult:
    status: str
    result: str                     # '1-0', '0-1', '1/2-1/2'
    winner: Optional[str]           # WHITE / BLACK / None


class Game:
    def __init__(self, white_name: str = "White", black_name: str = "Black",
                 fen: str = START_FEN) -> None:
        self.white_name = white_name
        self.black_name = black_name
        self.start_fen = fen
        self.board = Board.from_fen(fen)
        self.history: List[MoveRecord] = []
        # pieces captured BY each colour (kinds of enemy pieces taken)
        self.captured: Dict[str, List[str]] = {WHITE: [], BLACK: []}
        self.position_counts: Counter = Counter({self.board.position_key(): 1})
        self.outcome: Optional[GameResult] = None
        self._legal_cache: Optional[List[Move]] = None
        # A game can begin in an already-finished position (tests / FEN)
        self._evaluate_position()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @property
    def turn(self) -> str:
        return self.board.turn

    @property
    def is_over(self) -> bool:
        return self.outcome is not None

    @property
    def status(self) -> str:
        return self.outcome.status if self.outcome else ONGOING

    def player_name(self, color: str) -> str:
        return self.white_name if color == WHITE else self.black_name

    def legal_moves(self) -> List[Move]:
        if self.is_over:
            return []
        if self._legal_cache is None:
            self._legal_cache = generate_legal_moves(self.board)
        return self._legal_cache

    def legal_moves_from(self, square: Square) -> List[Move]:
        return [m for m in self.legal_moves() if m.start == square]

    def legal_targets(self, square: Square) -> set:
        return {m.end for m in self.legal_moves_from(square)}

    def find_move(self, start: Square, end: Square,
                  promotion: Optional[str] = None) -> Optional[Move]:
        for move in self.legal_moves():
            if move.start == start and move.end == end:
                if move.promotion is None or move.promotion == (promotion or "").upper():
                    return move
        return None

    def is_promotion_move(self, start: Square, end: Square) -> bool:
        return any(m.start == start and m.end == end and m.promotion
                   for m in self.legal_moves())

    def in_check(self) -> bool:
        return self.board.in_check(self.turn)

    def checked_king_square(self) -> Optional[Square]:
        """Square of the side-to-move's king if it is in check."""
        if self.board.in_check(self.turn):
            return self.board.find_king(self.turn)
        return None

    def material(self, color: str) -> int:
        return sum(PIECE_VALUES[p.kind] for _, p in self.board.pieces(color))

    def material_advantage(self, color: str) -> int:
        """Positive lead in material for `color` (0 if level or behind)."""
        return max(0, self.material(color) - self.material(opposite(color)))

    def captured_by(self, color: str) -> List[str]:
        return list(self.captured[color])

    def fullmove_count(self) -> int:
        return (len(self.history) + 1) // 2

    def san_list(self) -> List[str]:
        return [r.san for r in self.history]

    def last_move(self) -> Optional[MoveRecord]:
        return self.history[-1] if self.history else None

    def fen(self) -> str:
        return self.board.to_fen()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def make_move(self, start: Square, end: Square,
                  promotion: Optional[str] = None) -> MoveRecord:
        if self.is_over:
            raise GameOverError("The game is over")
        if self.is_promotion_move(start, end) and not promotion:
            raise IllegalMoveError("A promotion piece (Q, R, B, N) is required")
        move = self.find_move(start, end, promotion)
        if move is None:
            raise IllegalMoveError(f"Illegal move {square_name(start)}{square_name(end)}")

        mover = self.turn
        san = move_to_san(self.board, move, self.legal_moves())
        applied = self.board.make_move(move)
        self._legal_cache = None

        if applied.captured is not None:
            self.captured[mover].append(applied.captured.kind)

        key = self.board.position_key()
        self.position_counts[key] += 1

        in_check = self.board.in_check(self.turn)
        has_reply = bool(generate_legal_moves(self.board))
        is_mate = in_check and not has_reply
        san += "#" if is_mate else ("+" if in_check else "")

        record = MoveRecord(move=move, san=san, color=mover,
                            piece_kind=applied.piece.kind,
                            captured_kind=applied.captured.kind if applied.captured else None,
                            applied=applied, fen_after=self.board.to_fen(),
                            is_check=in_check, is_checkmate=is_mate)
        self.history.append(record)
        self._evaluate_position(in_check=in_check, has_reply=has_reply)
        return record

    def resign(self, color: str) -> GameResult:
        self._require_ongoing()
        return self._finish(RESIGNATION, winner=opposite(color))

    def agree_draw(self) -> GameResult:
        self._require_ongoing()
        return self._finish(DRAW_AGREEMENT, winner=None)

    def timeout(self, color: str) -> GameResult:
        """`color` ran out of time. The opponent wins unless they could never
        checkmate, in which case the game is drawn (FIDE 6.9)."""
        self._require_ongoing()
        opponent = opposite(color)
        if not can_checkmate(self.board, opponent):
            return self._finish(TIMEOUT_VS_INSUFFICIENT, winner=None)
        return self._finish(TIMEOUT, winner=opponent)

    # ------------------------------------------------------------------
    # Result description
    # ------------------------------------------------------------------
    def result_headline(self) -> str:
        if not self.outcome:
            return ""
        if self.outcome.winner is None:
            return "Draw"
        return f"{self.player_name(self.outcome.winner)} Wins"

    def result_reason(self) -> str:
        if not self.outcome:
            return ""
        return REASON_TEXT.get(self.outcome.status, "")

    def result_title(self) -> str:
        if not self.outcome:
            return ""
        return REASON_TITLE.get(self.outcome.status, "Game Over")

    def winner_color_name(self) -> Optional[str]:
        if self.outcome and self.outcome.winner:
            return COLOR_NAMES[self.outcome.winner]
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _require_ongoing(self) -> None:
        if self.is_over:
            raise GameOverError("The game is over")

    def _finish(self, status: str, winner: Optional[str]) -> GameResult:
        if winner == WHITE:
            result = "1-0"
        elif winner == BLACK:
            result = "0-1"
        else:
            result = "1/2-1/2"
        self.outcome = GameResult(status=status, result=result, winner=winner)
        self._legal_cache = []
        return self.outcome

    def _evaluate_position(self, in_check: Optional[bool] = None,
                           has_reply: Optional[bool] = None) -> None:
        """Check automatic game-ending conditions, mate taking precedence."""
        if in_check is None:
            in_check = self.board.in_check(self.turn)
        if has_reply is None:
            has_reply = bool(generate_legal_moves(self.board))

        if not has_reply:
            if in_check:
                self._finish(CHECKMATE, winner=opposite(self.turn))
            else:
                self._finish(STALEMATE, winner=None)
        elif is_insufficient_material(self.board):
            self._finish(INSUFFICIENT_MATERIAL, winner=None)
        elif self.position_counts[self.board.position_key()] >= 3:
            self._finish(THREEFOLD_REPETITION, winner=None)
        elif self.board.halfmove_clock >= 100:
            self._finish(FIFTY_MOVE_RULE, winner=None)
