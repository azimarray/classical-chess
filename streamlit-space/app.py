"""
app.py — Classical Chess on a Python (Streamlit) server.

This shows exactly the same game as the Netlify website: the page below loads
index.html (a copy of the website) full-screen, so the opening animation, board,
pieces, clocks, sounds and match history are identical.

The Python-only version, which uses the Python rules engine with Streamlit
widgets, is app_python.py:  streamlit run app_python.py

Run this one:  streamlit run app.py
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent

# Hide Streamlit's own header, menu, footer and padding, and let the game fill the window.
FULL_SCREEN_CSS = """
<style>
  header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"], footer, #MainMenu { display: none !important; }
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: #262421 !important; overflow: hidden !important;
  }
  .block-container, [data-testid="stMainBlockContainer"], [data-testid="stAppViewBlockContainer"] {
    padding: 0 !important; margin: 0 !important; max-width: 100% !important;
  }
  [data-testid="stVerticalBlock"] { gap: 0 !important; }
  [data-testid="stElementContainer"]:has(> style), .element-container:has(> div > style) { display: none !important; }
  iframe { display: block; width: 100vw !important; height: 100vh !important; height: 100dvh !important; border: 0; }
</style>
"""


def load_site() -> str:
    return (HERE / "index.html").read_text(encoding="utf-8")


def main() -> None:
    st.set_page_config(page_title="Classical Chess", page_icon="♟️", layout="wide",
                       initial_sidebar_state="collapsed")
    st.markdown(FULL_SCREEN_CSS, unsafe_allow_html=True)
    components.html(load_site(), height=900, scrolling=False)


if __name__ == "__main__":
    main()
