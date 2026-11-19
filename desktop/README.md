# Classical Chess

A two-player, pass-and-play chess desktop app in Python + Pygame with full FIDE rule enforcement, 10-minute Rapid clocks, procedurally drawn pieces and synthesised sound. No image or audio assets are needed: everything is drawn and generated in code.

## Requirements

- Python 3.9 or newer
- Pygame 2.1 or newer

## Install & run

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install pygame          # or: pip install pygame-ce
python main.py
```

## Run the tests

The rules engine has no Pygame dependency, so the tests run anywhere:

```bash
python -m unittest test_chess.py -v
```

The 74 tests cover legal-move filtering (pins, king safety, check evasion), checkmate, stalemate, en passant (including the discovered-check edge case), castling (through or into check, lost rights, captured rook), promotion and under-promotion, threefold repetition, the 50-move rule, insufficient material, resignation, draw agreement, timeout, SAN notation, FEN, the clock, and history saving and deleting.

They also include **perft** node counts against five published reference positions (start position to depth 3 = 8,902; "Kiwipete" to depth 2 = 2,039, and others). Perft is the standard way to prove a move generator is exactly right.

## Controls

| Action | How |
|---|---|
| Move a piece | Click the piece, then a target, or drag and drop |
| Deselect | Click the piece again, right-click, or press `Esc` |
| Promote | Pick from the card over the promotion file; click outside or `×` to cancel |
| Resign / Offer draw | Flag and ½ icons in the header (they act for the side to move) |
| Mute | Speaker icon or `M` |
| Scroll move list | Mouse wheel over the move strip |
| Delete a saved match | Bin icon on its card in Match History |
| Clear all history | Bin icon in the Match History header |
| Home shortcuts | `Enter` play, `H` history, `Esc` quit |
| Setup shortcuts | `Tab` switch field, `Enter` start, `Ctrl+Backspace` clear field |

The window is resizable. The UI renders on a fixed 640×892 canvas that scales to fit.

## Architecture

| Module | Responsibility |
|---|---|
| `main.py` | `App`: window, scaling, mouse mapping, screen states (`SPLASH`, `HOME`, `SETUP`, `GAME`, `HISTORY`), cross-fades |
| `constants.py` | Palette, layout, piece values, timing (no Pygame import) |
| `pieces.py` | `Piece` ABC plus `Pawn`, `Rook`, `Knight`, `Bishop`, `Queen`, `King`; pseudo-legal moves; `Move` value object |
| `board.py` | 8×8 state, `copy()` deep clone, move execution, castling rights, en passant, FEN import/export, repetition keys |
| `game.py` | Rules controller: legality via cloned-board simulation, SAN, captures, material, all end conditions |
| `timer.py` | `ChessClock` with injectable time source; `10:00` format switching to `0:19.8` under 20 s |
| `sounds.py` | `SoundManager`; synthesises move/capture/castle/check/promote/start/end cues with `math` + `array` |
| `history_manager.py` | Atomic JSON persistence to `match_history.json`; relative times in hours |
| `ui.py` | Rendering engine, vector pieces, widgets, all five screens, animations, promotion modal |
| `test_chess.py` | `unittest` suite, GUI-independent |

The UI never decides a rule. Every legality question goes through `game.Game`.

## Rule notes

- **Threefold repetition** and the **50-move rule** end the game automatically (at 3 occurrences / 100 half-moves) rather than waiting for a claim. This is the usual choice for online play. Checkmate on the 100th half-move takes precedence.
- Repetition compares placement, side to move, castling rights and an en-passant square only when a capture is actually available (FIDE 9.2).
- **Timeout:** if the player who still has time cannot possibly checkmate (lone king, or king plus a single bishop or knight), the game is drawn rather than lost (FIDE 6.9).
- **Insufficient material** draws K v K, K+minor v K, and any position where all remaining minors are bishops on one square colour.
- Clocks pause while a confirmation dialog is open, and keep running during the promotion choice, since that is the mover's own thinking time.

## Match history

Finished games are saved to `match_history.json` beside `main.py` with players, result, reason, move list (SAN), final FEN, duration and timestamp. Times show as "Just now", "1 hour ago", "N hours ago". A corrupt file is renamed to `match_history.json.corrupt-<time>` rather than crashing the app. Abandoned games (leaving mid-match) are not saved. Single matches or the whole history can be deleted from the Match History screen; both ask for confirmation first.
