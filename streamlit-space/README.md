---
title: Classical Chess
emoji: ♟️
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 8501
pinned: false
---

# Classical Chess

Two-player, pass-and-play chess with every FIDE rule enforced and 10-minute clocks, served by a Python (Streamlit) server.

## Two apps in this folder

| File | What you see | Rules run in |
|---|---|---|
| `app.py` (the one the Space runs) | **Exactly the same game as the Netlify website**: opening animation, drawn pieces, click or drag moves, clocks, sounds, match history | The website's JavaScript, inside the page |
| `app_python.py` | A simpler Streamlit screen: pick the piece and square from dropdowns | **Python**: the same rules engine as the desktop version |

`app.py` shows `index.html`, an exact copy of the website, full-screen. Python serves the page, and the game itself runs in the visitor's browser. That is the only way to look and behave exactly like the website. `app_python.py` is the version where the Python code plays the game, which is why it looks different.

## Run it on your computer

```bash
pip install -r requirements.txt
streamlit run app.py          # the exact website
streamlit run app_python.py   # the Python-engine version
```

## Put it on Hugging Face

1. On huggingface.co choose **New → Space**, give it a name, pick **Docker** as the SDK (blank template) and create it.
2. Upload every file in this folder (including the `.streamlit` folder, `Dockerfile`, `index.html` and this `README.md`) to the Space, either through **Files → Add file → Upload files** or with `git push`.
3. The Space builds by itself and then shows the game.

To make the Space run the Python-engine version instead, change `app.py` to `app_python.py` on the last line of the `Dockerfile`.

## Keeping it in step with the website

`index.html` here must be the same as the website's `index.html` at the top of the repository, and the engine files must be the same as the ones in `../desktop`. The tests check both, so a change made in one place and not copied here fails CI.

## Run the tests

```bash
python -m unittest test_streamlit_space.py -v
```

## Files

| File | What it is |
|---|---|
| `app.py` | Shows the website full-screen (the Space runs this) |
| `index.html` | Copy of the website |
| `app_python.py` | Python-engine version: home, setup, game, history screens |
| `match.py` | One game in progress: engine + clock + selection (no Streamlit) |
| `view.py` | Draws the board as SVG and formats text (no Streamlit) |
| `board.py`, `game.py`, `pieces.py`, `timer.py`, `constants.py`, `history_manager.py` | Rules engine, copied from `../desktop` |
| `test_streamlit_space.py` | Tests (28), runnable without Streamlit installed |
