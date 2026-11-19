"""
history_manager.py — Persistent match history (match_history.json).

Writes are atomic (temp file + os.replace) and a corrupt file is moved aside
instead of crashing the application.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from typing import Callable, Dict, List, Optional

from constants import MAX_HISTORY_ENTRIES

DEFAULT_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "match_history.json")


def relative_time(timestamp: float, now: Optional[float] = None) -> str:
    """Elapsed time expressed in hours: 'Just now', '1 hour ago', 'N hours ago'."""
    now = time.time() if now is None else now
    hours = int(max(0.0, now - timestamp) // 3600)
    if hours == 0:
        return "Just now"
    if hours == 1:
        return "1 hour ago"
    return f"{hours} hours ago"


def build_match_record(game, timestamp: Optional[float] = None,
                       duration_seconds: Optional[float] = None) -> Dict:
    """Serialise a finished game.Game into a JSON-friendly dict."""
    outcome = game.outcome
    winner = None
    if outcome and outcome.winner:
        winner = "white" if outcome.winner == "w" else "black"
    return {
        "id": uuid.uuid4().hex,
        "timestamp": time.time() if timestamp is None else timestamp,
        "white": game.white_name,
        "black": game.black_name,
        "result": outcome.result if outcome else "*",
        "winner": winner,
        "reason": outcome.status if outcome else "ongoing",
        "reason_text": game.result_reason(),
        "headline": game.result_headline(),
        "move_count": game.fullmove_count(),
        "ply_count": len(game.history),
        "moves": game.san_list(),
        "final_fen": game.fen(),
        "duration_seconds": round(duration_seconds, 1) if duration_seconds else None,
    }


class HistoryManager:
    def __init__(self, path: str = DEFAULT_HISTORY_PATH,
                 clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self._clock = clock

    # ------------------------------------------------------------------
    def load_matches(self) -> List[Dict]:
        """All saved matches, newest first."""
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            self._quarantine_corrupt_file()
            return []
        matches = data.get("matches", []) if isinstance(data, dict) else data
        if not isinstance(matches, list):
            return []
        valid = [m for m in matches if isinstance(m, dict) and "timestamp" in m]
        return sorted(valid, key=lambda m: m.get("timestamp", 0), reverse=True)

    def save_match(self, record: Dict) -> Dict:
        matches = self.load_matches()
        matches.insert(0, record)
        self._write(matches[:MAX_HISTORY_ENTRIES])
        return record

    def save_game(self, game, duration_seconds: Optional[float] = None) -> Dict:
        return self.save_match(build_match_record(game, self._clock(), duration_seconds))

    def delete_match(self, match_id: str) -> bool:
        """Remove one match by id. Returns True if something was deleted."""
        if not match_id:
            return False
        matches = self.load_matches()
        remaining = [m for m in matches if m.get("id") != match_id]
        if len(remaining) == len(matches):
            return False
        self._write(remaining)
        return True

    def clear(self) -> None:
        """Delete every saved match."""
        self._write([])

    def relative_time(self, timestamp: float) -> str:
        return relative_time(timestamp, self._clock())

    # ------------------------------------------------------------------
    def _write(self, matches: List[Dict]) -> None:
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {"version": 1, "matches": matches}
        fd, tmp_path = tempfile.mkstemp(prefix=".history_", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except OSError:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def _quarantine_corrupt_file(self) -> None:
        try:
            os.replace(self.path, f"{self.path}.corrupt-{int(self._clock())}")
        except OSError:
            pass
