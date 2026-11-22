---
title: Classical Chess
emoji: ♟️
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 8501
pinned: false
---

# Classical Chess (Streamlit)

Two-player, pass-and-play chess in the browser with every FIDE rule enforced: legal moves only, castling, en passant, promotion, checkmate, stalemate, insufficient material, threefold repetition, the 50-move rule, resignation, draw offers and 10-minute clocks.

The rules engine (`board.py`, `game.py`, `pieces.py`, `timer.py`) is the same Python code as the desktop Pygame version. Only the screens are different: this version is built with [Streamlit](https://streamlit.io), so it can run on a server.

## How to play

1. Pick a piece from **Piece to move**. The board highlights where it can go.
2. Pick the square under **Move to** (and a piece if you are promoting a pawn), then press **Play move**.
3. The clocks tick for the side to move. Use **Resign** or **Offer draw** at any time.

Match history is kept for the current visit only.

## Run it on your computer

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run the tests

```bash
python -m unittest test_streamlit_space.py -v
```

## Put it on Hugging Face

1. On huggingface.co choose **New → Space**, give it a name, pick **Docker** as the SDK (blank template) and create it.
2. Upload every file in this folder (including the `.streamlit` folder, `Dockerfile` and this `README.md`) to the Space, either through **Files → Add file → Upload files** or with `git push`.
3. The Space builds by itself and then shows the game.

## Files

| File | What it is |
|---|---|
| `app.py` | The Streamlit screens: home, setup, game, history |
| `match.py` | One game in progress: engine + clock + selection (no Streamlit) |
| `view.py` | Draws the board as SVG and formats text (no Streamlit) |
| `board.py`, `game.py`, `pieces.py`, `timer.py`, `constants.py`, `history_manager.py` | Rules engine, copied from `../desktop` |
| `test_streamlit_space.py` | Tests, including a check that the engine copies match the desktop ones |
