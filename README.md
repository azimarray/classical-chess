# Classical Chess

Two-player, pass-and-play chess with full FIDE rule enforcement, 10-minute Rapid clocks, hand-drawn vector pieces and synthesised sound effects. Two players share one screen and take turns.

This repository holds two versions of the same game:

| | Website (this folder) | Desktop (`desktop/`) |
|---|---|---|
| Language | HTML + JavaScript | Python + Pygame |
| How to play | Open the site in any browser, on any device | `python main.py` |
| Needs installing | Nothing | Python 3.9+ and Pygame |
| Match history | Saved in the player's browser | Saved to `match_history.json` |

## Features

- **Every rule enforced:** legal moves only (no moving into check), castling, en passant, promotion with a picker, checkmate, stalemate, insufficient material, threefold repetition, the 50-move rule, resignation, draw offers and timeouts.
- **Clocks:** 10:00 per side. Under 20 seconds the clock shows tenths and turns red.
- **Move list:** algebraic notation in a scrolling strip, with the latest move highlighted.
- **Material:** captured pieces and the current material lead (+1, +3, ...) beside each player.
- **Match history:** results, move counts and how long ago each game was played. Delete single matches or clear everything.
- **Intro:** the AZIM ARCHIVE logo animation plays when the site opens.

## Host the website

The website is three files at the top of this repository: `index.html`, `splash.mp4` and `splash.webm`. They have to stay in the same folder. There is no build step.

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
| Skip the intro | Tap, or press `Esc`, `Enter` or `Space` |

The intro starts by itself. Browsers only allow sound after the visitor has interacted with a site, so on a first visit most browsers play it muted; game sounds turn on with the first click or tap.

## Desktop version

See [`desktop/README.md`](desktop/README.md). In short:

```bash
cd desktop
pip install pygame
python main.py
python -m unittest test_chess.py -v   # 74 rule tests, no window needed
```

## Rule notes

- Threefold repetition and the 50-move rule end the game automatically, as in most online play.
- If a player runs out of time but the opponent has no way to checkmate (lone king, or king and one bishop or knight), the game is a draw.
- The website's rules engine is a JavaScript port of the Python engine. It matches the published perft move counts for the standard test positions, which shows the move generator is exact.
