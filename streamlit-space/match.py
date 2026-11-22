"""
match.py — One game in progress: the rules engine, the clock and the current selection.

No Streamlit in here, so it can be tested without a browser. The page (app.py)
only calls these methods and draws the result.
"""

from __future__ import annotations

import itertools
import time
from typing import Callable, Dict, Optional, Set

from constants import START_FEN, WHITE
from game import Game, GameOverError, IllegalMoveError
from history_manager import build_match_record
from pieces import Square
from timer import ChessClock

_ids = itertools.count(1)


class Match:
    def __init__(self, white: str, black: str, fen: str = START_FEN,
                 time_source: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time) -> None:
        self.uid = next(_ids)
        self.game = Game(white, black, fen)
        self.clock = ChessClock(time_source=time_source)
        self._wall = wall_clock
        self.started_at = wall_clock()
        self.selected: Optional[Square] = None
        self.saved = False
        if not self.game.is_over:
            self.clock.start(self.game.turn)

    # -- selection -------------------------------------------------------
    def select(self, square: Optional[Square]) -> bool:
        """Select a piece of the side to move that has at least one legal move."""
        if square is not None and not self.game.is_over and self.game.legal_targets(square):
            self.selected = square
            return True
        self.selected = None
        return False

    def targets(self) -> Set[Square]:
        if self.selected is None:
            return set()
        return self.game.legal_targets(self.selected)

    def needs_promotion(self, to: Square) -> bool:
        return self.selected is not None and self.game.is_promotion_move(self.selected, to)

    # -- moves -----------------------------------------------------------
    def play(self, to: Square, promotion: Optional[str] = None):
        if self.selected is None:
            raise IllegalMoveError("Choose a piece first")
        if self.poll():
            raise GameOverError("The game is over")
        record = self.game.make_move(self.selected, to, promotion)
        self.selected = None
        if self.game.is_over:
            self.clock.stop()
        else:
            self.clock.switch()
        return record

    def resign(self) -> None:
        """The side to move resigns."""
        self.game.resign(self.game.turn)
        self._end()

    def agree_draw(self) -> None:
        self.game.agree_draw()
        self._end()

    def poll(self) -> bool:
        """End the game if the side to move ran out of time. True if it just ended."""
        if self.game.is_over:
            return False
        flagged = self.clock.flagged()
        if flagged is None:
            return False
        self.game.timeout(flagged)
        self._end()
        return True

    def _end(self) -> None:
        self.selected = None
        self.clock.stop()

    # -- saving ----------------------------------------------------------
    def record(self) -> Dict:
        return build_match_record(self.game, self._wall(), self._wall() - self.started_at)
