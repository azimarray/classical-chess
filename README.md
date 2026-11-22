# Classical Chess

[![Tests](https://github.com/azimarray/classical-chess/actions/workflows/tests.yml/badge.svg)](https://github.com/azimarray/classical-chess/actions/workflows/tests.yml)

Two-player, pass-and-play chess with full FIDE rule enforcement, 10-minute Rapid clocks, hand-drawn vector pieces and synthesised sound effects. Two players share one screen and take turns.

This repository holds three versions of the same game:

| | Website (this folder) | Desktop (`desktop/`) | Streamlit (`streamlit-space/`) |
|---|---|---|---|
| Language | HTML + JavaScript | Python + Pygame | Python (Streamlit) server |
| How to play | Open the site in any browser, on any device | `python main.py` | `streamlit run app.py`, or host it (for example on Hugging Face) |
| Needs installing | Nothing | Python 3.9+ and Pygame | Python and Streamlit |
| Match history | Saved in the player's browser | Saved to `match_history.json` | `app.py`: saved in the player's browser; `app_python.py`: current visit only |

## Features

- **Every rule enforced:** legal moves only (no moving into check), castling, en passant, promotion with a picker, checkmate, stalemate, insufficient material, threefold repetition, the 50-move rule, resignation, draw offers and timeouts.
- **Clocks:** 10:00 per side. Under 20 seconds the clock shows tenths and turns red.
- **Move list:** algebraic notation in a scrolling strip, with the latest move highlighted.
- **Material:** captured pieces and the current material lead (+1, +3, ...) beside each player.
- **Match history:** results, move counts and how long ago each game was played. Delete single matches or clear everything.
- **Opening animation:** a golden pawn pops up, a knight and rook slide out from behind it, and the CLASSICAL CHESS wordmark fades in (same as the desktop version).

## Host the website

The website is a single file at the top of this repository: `index.html`. There is no build step.

### GitHub Pages

1. Open the repository's **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to *Deploy from a branch*, choose the `main` branch and the `/ (root)` folder, then **Save**.
3. After a minute or two the site is live at `https://azimarray.github.io/classical-chess/`.

Every push to `main` updates the site automatically.

### Netlify

1. In Netlify choose **Add new site → Import an existing project → GitHub** and pick this repository.
2. Leave the build command empty and set the publish directory to `/`.
3. Deploy. Netlify redeploys on every push to `main`.

### Try it locally

Double-clicking `index.html` works, but serving the folder is closer to how it runs online:

```bash
python -m http.server 8000
# then open http://localhost:8000
```

## Controls

| Action | How |
|---|---|
| Move a piece | Click or tap the piece, then the target square, or drag and drop |
| Deselect | Click the piece again, right-click, or press `Esc` |
| Promote | Pick from the card that opens over the promotion square |
| Resign / offer draw | Flag and ½ buttons in the header (they act for the side to move) |
| Mute | Speaker button, `M`, or **Sound On/Off** on the home screen |
| Skip the opening animation | Press any key or click |

The opening animation runs by itself for about 2.5 seconds. Game sounds turn on with the first click or tap, because browsers only allow sound after the visitor has interacted with a site.

## Desktop version

See [`desktop/README.md`](desktop/README.md). In short:

```bash
cd desktop
pip install pygame
python main.py
python -m unittest test_chess.py -v   # 74 rule tests, no window needed
```

## Streamlit version

A Python (Streamlit) app built to be hosted, for example as a Hugging Face Space. `app.py` shows exactly the same game as the website; `app_python.py` is a simpler version where the Python rules engine plays the game. See [`streamlit-space/README.md`](streamlit-space/README.md) for how to run it and how to put it on Hugging Face.

## Tests

Every push and pull request runs three test jobs on GitHub Actions (see the **Actions** tab, or the badge at the top):

| Job | What it covers |
|---|---|
| **Desktop rules** (Python, 74 tests) | Every chess rule, notation, FEN, the clock and saving history, plus perft move counts against published reference positions |
| **Streamlit version** (Python, 28 tests) | The embedded website, the Python-engine version's move, clock and history logic, its SVG board and every screen (run against a stand-in for Streamlit), and checks that `index.html` and the engine files are identical to the website and desktop copies |
| **Website** (Chromium, 28 tests) | The rules engine running in the real page, the opening animation (drawn pieces, auto-advance, key and click skip), home and setup screens, click and drag moves, castling, en passant, promotion, checkmate, repetition, resign, draw offers, timeouts, leaving a game, rematch, saving, listing and deleting match history, keyboard shortcuts, sound effects, layout at five screen sizes from laptop to small phone, and no JavaScript errors |

Run them on your own computer:

```bash
# desktop rules
cd desktop && python -m unittest test_chess.py -v

# website (needs Node.js 18+)
cd tests
npm install
npx playwright install chromium
node e2e.js
```

The browser tests start their own small web server for the repository, so nothing else needs to be running.

## Rule notes

- Threefold repetition and the 50-move rule end the game automatically, as in most online play.
- If a player runs out of time but the opponent has no way to checkmate (lone king, or king and one bishop or knight), the game is a draw.
- The website's rules engine is a JavaScript port of the Python engine. It matches the published perft move counts for the standard test positions, which shows the move generator is exact.
