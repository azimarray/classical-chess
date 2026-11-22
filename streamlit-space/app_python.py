"""
app_python.py — Classical Chess with the Python rules engine and Streamlit widgets.

The rules engine (board.py, game.py, pieces.py, timer.py) is the same code as the
desktop version. This file only draws the screens and passes clicks to match.py.

Run it:   streamlit run app_python.py
"""

from __future__ import annotations

import streamlit as st

import view
from constants import MAX_HISTORY_ENTRIES, MAX_NAME_LENGTH
from game import GameOverError, IllegalMoveError
from history_manager import relative_time
from match import Match
from pieces import square_name

PROMOTIONS = {"Queen": "Q", "Rook": "R", "Bishop": "B", "Knight": "N"}


# --------------------------------------------------------------------------
# Small state helpers (all state lives in st.session_state, one per visitor)
# --------------------------------------------------------------------------
def init_state() -> None:
    ss = st.session_state
    ss.setdefault("page", "home")
    ss.setdefault("names", ("Player 1", "Player 2"))
    ss.setdefault("p1_white", True)
    ss.setdefault("history", [])        # finished games of this visit, newest first
    ss.setdefault("match", None)
    ss.setdefault("confirm", None)      # 'resign' | 'draw' | 'leave' | 'clear' | None


def go(page: str) -> None:
    st.session_state.page = page
    st.session_state.confirm = None


def ask(what) -> None:
    st.session_state.confirm = what


def start_match() -> None:
    ss = st.session_state
    n1 = (ss.get("name1") or "").strip()[:MAX_NAME_LENGTH] or "Player 1"
    n2 = (ss.get("name2") or "").strip()[:MAX_NAME_LENGTH] or "Player 2"
    p1_white = bool(ss.get("p1w", True))
    ss.names, ss.p1_white = (n1, n2), p1_white
    white, black = (n1, n2) if p1_white else (n2, n1)
    ss.match = Match(white, black)
    go("game")


def rematch() -> None:
    m = st.session_state.match
    st.session_state.match = Match(m.game.white_name, m.game.black_name)
    st.session_state.confirm = None


def leave_game() -> None:
    st.session_state.match = None
    go("home")


def do_resign() -> None:
    st.session_state.match.resign()
    st.session_state.confirm = None


def do_draw() -> None:
    st.session_state.match.agree_draw()
    st.session_state.confirm = None


def delete_record(match_id: str) -> None:
    st.session_state.history = [r for r in st.session_state.history if r.get("id") != match_id]


def clear_history() -> None:
    st.session_state.history = []
    st.session_state.confirm = None


def save_once(m: Match) -> None:
    if m.saved or not m.game.is_over:
        return
    m.saved = True
    hist = st.session_state.history
    hist.insert(0, m.record())
    del hist[MAX_HISTORY_ENTRIES:]


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------
def render_home() -> None:
    st.markdown("<h1 style='text-align:center;letter-spacing:6px;margin-top:1.5rem'>CLASSICAL CHESS</h1>",
                unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#A8A29A'>Two players · One board · Every rule enforced</p>",
                unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.button("Play Game", type="primary", use_container_width=True, on_click=go, args=("setup",))
        st.button("Match History", use_container_width=True, on_click=go, args=("history",))
        st.caption("Pass-and-play on one screen. 10:00 Rapid clocks. Every FIDE rule enforced, "
                   "including castling, en passant, promotion, threefold repetition and the 50-move rule.")


def render_setup() -> None:
    ss = st.session_state
    st.button("← Back", on_click=go, args=("home",))
    st.header("Player Setup")
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.text_input("Player 1", value=ss.names[0], max_chars=MAX_NAME_LENGTH, key="name1")
        st.text_input("Player 2", value=ss.names[1], max_chars=MAX_NAME_LENGTH, key="name2")
        st.checkbox("Player 1 plays White", value=ss.p1_white, key="p1w")
        st.button("Start Game", type="primary", use_container_width=True, on_click=start_match)


@st.fragment(run_every=1)
def players_panel() -> None:
    """Both player bars. Re-runs every second so the clocks tick."""
    m = st.session_state.get("match")
    if m is None:
        return
    if m.poll():
        st.rerun()          # time ran out: redraw the whole page with the result
    g = m.game
    st.markdown(view.player_card(g, m.clock, "b") + view.player_card(g, m.clock, "w"), unsafe_allow_html=True)


def render_game() -> None:
    ss = st.session_state
    m: Match = ss.match
    if m is None:
        go("home")
        st.rerun()
    m.poll()
    g = m.game
    save_once(m)

    top = st.columns([1, 3])
    top[0].button("← Leave", on_click=ask, args=("leave",), disabled=ss.confirm == "leave")
    top[1].markdown(f"### {view.status_line(g)}")

    left, right = st.columns([3, 2], gap="large")
    board_slot = left.empty()

    with right:
        players_panel()

        if g.is_over:
            st.success(f"**{g.result_headline()}** {g.result_reason()}" if g.outcome.winner
                       else f"**Draw** {g.result_reason()}")
            c1, c2 = st.columns(2)
            c1.button("Rematch", type="primary", use_container_width=True, on_click=rematch)
            c2.button("New Game", use_container_width=True, on_click=go, args=("setup",))
            st.button("Home", use_container_width=True, on_click=go, args=("home",))
        elif ss.confirm == "leave":
            st.warning("Leave this game? It will not be saved.")
            c1, c2 = st.columns(2)
            c1.button("Leave", type="primary", use_container_width=True, on_click=leave_game)
            c2.button("Stay", use_container_width=True, on_click=ask, args=(None,))
        else:
            _render_move_controls(m)

        if g.history:
            st.markdown("**Moves**")
            st.code(view.moves_text(g), language=None)

    board_slot.image(view.board_svg(g, m.selected, m.targets()), use_container_width=True)


def _render_move_controls(m: Match) -> None:
    ss = st.session_state
    g = m.game
    key = f"{m.uid}_{len(g.history)}"        # new widgets after every move, so they reset

    from_opts = view.from_options(g)
    labels = ["Choose a piece…"] + [lab for lab, _ in from_opts]
    picked = st.selectbox("Piece to move", labels, key=f"from_{key}")
    start = dict(from_opts).get(picked)
    m.select(start)

    target = None
    promo = None
    if start is not None:
        to_opts = view.to_options(g, start)
        to_labels = ["Choose a square…"] + [lab for lab, _ in to_opts]
        to_picked = st.selectbox("Move to", to_labels, key=f"to_{key}_{square_name(start)}")
        target = dict(to_opts).get(to_picked)
        if target is not None and m.needs_promotion(target):
            name = st.selectbox("Promote to", list(PROMOTIONS), key=f"promo_{key}_{square_name(target)}")
            promo = PROMOTIONS[name]

    if st.button("Play move", type="primary", use_container_width=True, disabled=target is None):
        try:
            m.play(target, promo)
        except (IllegalMoveError, GameOverError) as exc:
            st.error(str(exc))
        st.rerun()

    if ss.confirm in ("resign", "draw"):
        who = g.player_name(g.turn)
        if ss.confirm == "resign":
            st.warning(f"{who} resigns?")
            do = do_resign
        else:
            st.warning("Both players agree to a draw?")
            do = do_draw
        c1, c2 = st.columns(2)
        c1.button("Yes", type="primary", use_container_width=True, on_click=do)
        c2.button("No", use_container_width=True, on_click=ask, args=(None,))
    else:
        c1, c2 = st.columns(2)
        c1.button("Resign", use_container_width=True, on_click=ask, args=("resign",))
        c2.button("Offer draw", use_container_width=True, on_click=ask, args=("draw",))


def render_history() -> None:
    ss = st.session_state
    top = st.columns([1, 3, 1])
    top[0].button("← Back", on_click=go, args=("home",))
    top[1].header("Match History")
    records = ss.history
    top[2].button("Clear all", on_click=ask, args=("clear",), disabled=not records)

    if ss.confirm == "clear" and records:
        st.warning(f"Delete all {len(records)} saved matches? This cannot be undone.")
        c1, c2, _ = st.columns([1, 1, 3])
        c1.button("Delete all", type="primary", on_click=clear_history)
        c2.button("Cancel", on_click=ask, args=(None,))

    if not records:
        st.info("No matches yet. Finished games are saved here automatically.")
        st.button("Play Game", type="primary", on_click=go, args=("setup",))
        st.caption("History is kept for this visit only. Closing the tab clears it.")
        return

    for r in records:
        c = st.columns([1, 6, 1])
        c[0].markdown(f"#### {'½-½' if r['result'] == '1/2-1/2' else r['result']}")
        if r.get("winner"):
            line = f"**{r[r['winner']]}** won {r.get('reason_text', '')}"
        else:
            line = f"**Draw** {r.get('reason_text', '')}"
        mins, secs = divmod(int(r.get("duration_seconds") or 0), 60)
        c[1].markdown(f"{r['white']} vs {r['black']} — {line}  \n"
                      f"{r.get('move_count', 0)} moves · {mins}m {secs:02d}s · {relative_time(r['timestamp'])}")
        c[2].button("Delete", key=f"del_{r['id']}", on_click=delete_record, args=(r["id"],))
    st.caption("History is kept for this visit only. Closing the tab clears it.")


# --------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Classical Chess", page_icon="♟️", layout="wide")
    init_state()
    {"home": render_home, "setup": render_setup, "game": render_game,
     "history": render_history}[st.session_state.page]()


if __name__ == "__main__":
    main()
