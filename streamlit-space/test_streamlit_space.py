"""
Tests for the Streamlit version. They run without Streamlit installed:

  * match.py and view.py are plain Python and are tested directly.
  * app.py (the exact website, embedded) is checked to load index.html full-screen.
  * app_python.py is run against a small stand-in for the `streamlit` module, which
    walks through every screen and checks the page code does not crash and
    does the right thing (start, move, finish, history, delete, clear).
  * the engine files are checked to be identical to the desktop copies.

    python -m unittest test_streamlit_space.py -v
"""

import os
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from constants import BLACK, WHITE                      # noqa: E402
from game import (CHECKMATE, TIMEOUT, GameOverError,    # noqa: E402
                  IllegalMoveError)
from match import Match                                 # noqa: E402
from pieces import parse_square as sq                   # noqa: E402
import view                                             # noqa: E402

SVG = "{http://www.w3.org/2000/svg}"


def play(m, *moves):
    for a, b in moves:
        assert m.select(sq(a)), f"cannot select {a}"
        m.play(sq(b))


def fools_mate():
    m = Match("Ann", "Ben")
    play(m, ("f2", "f3"), ("e7", "e5"), ("g2", "g4"), ("d8", "h4"))
    return m


# --------------------------------------------------------------------------
class MatchTests(unittest.TestCase):
    def test_select_only_movable_pieces_of_side_to_move(self):
        m = Match("A", "B")
        self.assertTrue(m.select(sq("e2")))
        self.assertEqual(m.targets(), {sq("e3"), sq("e4")})
        self.assertFalse(m.select(sq("e7")))            # black piece, white to move
        self.assertIsNone(m.selected)
        self.assertFalse(m.select(sq("a1")))            # rook is blocked in
        self.assertFalse(m.select(sq("e4")))            # empty square

    def test_play_switches_turn_and_clock(self):
        m = Match("A", "B")
        m.select(sq("e2"))
        rec = m.play(sq("e4"))
        self.assertEqual(rec.san, "e4")
        self.assertEqual(m.game.turn, BLACK)
        self.assertEqual(m.clock.active, BLACK)
        self.assertIsNone(m.selected)

    def test_illegal_target_is_rejected(self):
        m = Match("A", "B")
        m.select(sq("e2"))
        with self.assertRaises(IllegalMoveError):
            m.play(sq("e5"))
        with self.assertRaises(IllegalMoveError):
            Match("A", "B").play(sq("e4"))              # nothing selected

    def test_fools_mate(self):
        m = fools_mate()
        self.assertTrue(m.game.is_over)
        self.assertEqual(m.game.status, CHECKMATE)
        self.assertEqual(m.game.outcome.winner, BLACK)
        self.assertFalse(m.clock.running)
        rec = m.record()
        self.assertEqual(rec["result"], "0-1")
        self.assertEqual(rec["winner"], "black")
        self.assertEqual(rec["moves"], ["f3", "e5", "g4", "Qh4#"])

    def test_promotion_needs_a_piece(self):
        m = Match("A", "B", fen="8/P6k/8/8/8/8/8/K7 w - - 0 1")
        m.select(sq("a7"))
        self.assertTrue(m.needs_promotion(sq("a8")))
        with self.assertRaises(IllegalMoveError):
            m.play(sq("a8"))
        m.select(sq("a7"))
        self.assertEqual(m.play(sq("a8"), "N").san[:3], "a8=")

    def test_timeout_gives_the_win_to_the_opponent(self):
        t = [0.0]
        m = Match("A", "B", time_source=lambda: t[0])
        self.assertFalse(m.poll())
        t[0] = 601.0
        self.assertTrue(m.poll())
        self.assertEqual(m.game.status, TIMEOUT)
        self.assertEqual(m.game.outcome.winner, BLACK)
        self.assertFalse(m.poll())                      # only reports once

    def test_move_after_flag_fall_is_refused(self):
        t = [0.0]
        m = Match("A", "B", time_source=lambda: t[0])
        m.select(sq("e2"))
        t[0] = 700.0
        with self.assertRaises(GameOverError):
            m.play(sq("e4"))

    def test_resign_and_draw(self):
        m = Match("A", "B")
        m.resign()
        self.assertEqual(m.game.outcome.winner, BLACK)  # White was to move
        m = Match("A", "B")
        m.agree_draw()
        self.assertIsNone(m.game.outcome.winner)
        self.assertEqual(m.game.outcome.result, "1/2-1/2")
        with self.assertRaises(GameOverError):
            m.resign()


# --------------------------------------------------------------------------
class ViewTests(unittest.TestCase):
    def test_start_position_svg(self):
        root = ET.fromstring(view.board_svg(Match("A", "B").game))
        rects = list(root.iter(SVG + "rect"))
        texts = [t.text for t in root.iter(SVG + "text")]
        self.assertEqual(len(rects), 65)                # background + 64 squares
        self.assertEqual(len(texts), 32 + 16)           # 32 pieces + 16 coordinate labels
        self.assertEqual(sum(1 for t in texts if t and t.startswith("♟")), 16)
        self.assertIn("a", texts)
        self.assertIn("8", texts)

    def test_targets_and_captures_are_marked(self):
        m = Match("A", "B")
        play(m, ("e2", "e4"), ("d7", "d5"))
        m.select(sq("e4"))
        svg = view.board_svg(m.game, m.selected, m.targets())
        root = ET.fromstring(svg)
        circles = list(root.iter(SVG + "circle"))
        rings = [c for c in circles if c.get("stroke-width") == "6"]
        dots = [c for c in circles if c.get("stroke-width") is None and c.get("fill") == "#262421"]
        self.assertEqual(len(rings), 1)                 # exd5
        self.assertEqual(len(dots), 1)                  # e5

    def test_checked_king_is_highlighted(self):
        self.assertIn("url(#chk)", view.board_svg(fools_mate().game))
        self.assertNotIn('<circle cx', view.board_svg(Match("A", "B").game))

    def test_pickers(self):
        g = Match("A", "B").game
        frm = view.from_options(g)
        self.assertEqual(len(frm), 10)                  # 8 pawns + 2 knights
        self.assertIn("e2 · Pawn", [lab for lab, _ in frm])
        self.assertEqual([lab for lab, _ in view.to_options(g, sq("e2"))], ["e3", "e4"])

    def test_capture_labels_and_en_passant(self):
        m = Match("A", "B")
        play(m, ("e2", "e4"), ("a7", "a6"), ("e4", "e5"), ("d7", "d5"))
        labels = [lab for lab, _ in view.to_options(m.game, sq("e5"))]
        self.assertIn("d6 · takes Pawn (en passant)", labels)
        m2 = Match("A", "B")
        play(m2, ("e2", "e4"), ("d7", "d5"))
        self.assertIn("d5 · takes Pawn", [lab for lab, _ in view.to_options(m2.game, sq("e4"))])

    def test_text_helpers(self):
        m = Match("A", "B")
        play(m, ("e2", "e4"), ("d7", "d5"), ("e4", "d5"))
        self.assertEqual(view.moves_text(m.game), "1. e4  d5\n2. exd5")
        self.assertEqual(view.captured_text(m.game, WHITE), view.glyph("P") + " +1")
        self.assertEqual(view.captured_text(m.game, BLACK), "")
        self.assertEqual(view.clock_text(Match("A", "B", time_source=lambda: 0.0).clock, WHITE), "10:00")
        self.assertEqual(view.status_line(m.game), "B to move")
        self.assertIn("Checkmate", view.status_line(fools_mate().game))

    def test_player_card_escapes_names(self):
        m = Match("<b>x</b>", "B")
        self.assertNotIn("<b>x</b>", view.player_card(m.game, m.clock, WHITE))
        self.assertIn("&lt;b&gt;", view.player_card(m.game, m.clock, WHITE))


# --------------------------------------------------------------------------
# app.py against a stand-in for streamlit
# --------------------------------------------------------------------------
class _Rerun(Exception):
    pass


class _State(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class _Col:
    """Stands in for a column / container / placeholder: it forwards to the module."""
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)


def make_streamlit():
    st = types.ModuleType("streamlit")
    st.session_state = _State()
    st.clicks, st.pick, st.typed = set(), {}, {}
    for name in ("set_page_config", "markdown", "header", "caption", "code", "success",
                 "warning", "error", "info", "image"):
        setattr(st, name, mock.MagicMock(name=name))

    def button(label, key=None, on_click=None, args=(), disabled=False, **kw):
        hit = (key in st.clicks) if key else (label in st.clicks)   # keyed buttons are told apart by key
        if hit and not disabled:
            if on_click:
                on_click(*args)
            return True
        return False

    def text_input(label, value="", key=None, **kw):
        if key in st.typed:
            st.session_state[key] = st.typed[key]
        st.session_state.setdefault(key, value)
        return st.session_state[key]

    def checkbox(label, value=False, key=None, **kw):
        st.session_state.setdefault(key, value)
        return st.session_state[key]

    def selectbox(label, options, key=None, **kw):
        want = st.pick.get(label)
        value = want if want in options else options[0]
        st.session_state[key] = value
        return value

    def columns(spec, **kw):
        return [_Col(st) for _ in range(spec if isinstance(spec, int) else len(spec))]

    def rerun():
        raise _Rerun()

    def fragment(*a, **k):
        return a[0] if a and callable(a[0]) else (lambda f: f)

    st.button, st.text_input, st.checkbox, st.selectbox = button, text_input, checkbox, selectbox
    st.columns, st.rerun, st.fragment = columns, rerun, fragment
    st.empty = lambda: _Col(st)
    return st


class AppTests(unittest.TestCase):
    def setUp(self):
        self.st = make_streamlit()
        patcher = mock.patch.dict(sys.modules, {"streamlit": self.st})
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("app_python", None)
        import app_python
        self.app = app_python
        self.addCleanup(lambda: sys.modules.pop("app_python", None))

    def run_app(self, clicks=(), pick=None, typed=None):
        st = self.st
        st.clicks, st.pick, st.typed = set(clicks), dict(pick or {}), dict(typed or {})
        for _ in range(5):
            try:
                self.app.main()
                return
            except _Rerun:
                st.clicks = set()                # a rerun does not repeat the click
        self.fail("too many reruns")

    def ss(self):
        return self.st.session_state

    def start_game(self, n1="Ann", n2="Ben"):
        self.run_app()
        self.run_app(clicks=["Play Game"])
        self.assertEqual(self.ss().page, "setup")
        self.run_app(clicks=["Start Game"], typed={"name1": n1, "name2": n2})
        self.assertEqual(self.ss().page, "game")
        self.run_app()

    def test_home_and_navigation(self):
        self.run_app()
        self.assertEqual(self.ss().page, "home")
        self.run_app(clicks=["Match History"])
        self.assertEqual(self.ss().page, "history")
        self.run_app()                                   # empty history renders
        self.st.info.assert_called()
        self.run_app(clicks=["← Back"])
        self.assertEqual(self.ss().page, "home")

    def test_setup_names_default_and_trim(self):
        self.start_game(n1="   ", n2="B" * 40)
        g = self.ss().match.game
        self.assertEqual(g.white_name, "Player 1")
        self.assertEqual(len(g.black_name), 16)

    def test_swap_sides(self):
        self.run_app(clicks=["Play Game"])
        self.ss()["p1w"] = False
        self.run_app(clicks=["Start Game"], typed={"name1": "Ann", "name2": "Ben"})
        self.assertEqual(self.ss().match.game.white_name, "Ben")

    def test_play_a_move_through_the_page(self):
        self.start_game()
        self.run_app(pick={"Piece to move": "e2 · Pawn"})
        self.assertEqual(self.ss().match.selected, sq("e2"))
        board_svg = self.st.image.call_args[0][0]
        self.assertIn("<svg", board_svg)
        self.run_app(clicks=["Play move"], pick={"Piece to move": "e2 · Pawn", "Move to": "e4"})
        self.assertEqual(self.ss().match.game.san_list(), ["e4"])
        self.assertEqual(self.ss().match.game.turn, BLACK)

    def test_play_move_button_needs_a_target(self):
        self.start_game()
        self.run_app(clicks=["Play move"], pick={"Piece to move": "e2 · Pawn"})
        self.assertEqual(self.ss().match.game.san_list(), [])

    def test_resign_needs_confirmation(self):
        self.start_game()
        self.run_app(clicks=["Resign"])
        self.assertEqual(self.ss().confirm, "resign")
        self.run_app(clicks=["No"])
        self.assertFalse(self.ss().match.game.is_over)
        self.run_app(clicks=["Resign"])
        self.run_app(clicks=["Yes"])
        self.assertTrue(self.ss().match.game.is_over)
        self.run_app()
        self.assertEqual(len(self.ss().history), 1)      # saved once, not on every redraw
        self.run_app()
        self.assertEqual(len(self.ss().history), 1)

    def test_draw_offer(self):
        self.start_game()
        self.run_app(clicks=["Offer draw"])
        self.run_app(clicks=["Yes"])
        self.assertEqual(self.ss().match.game.outcome.result, "1/2-1/2")

    def test_leave_asks_first_and_does_not_save(self):
        self.start_game()
        self.run_app(clicks=["← Leave"])
        self.assertEqual(self.ss().confirm, "leave")
        self.run_app(clicks=["Stay"])
        self.assertEqual(self.ss().page, "game")
        self.run_app(clicks=["← Leave"])
        self.run_app(clicks=["Leave"])
        self.assertEqual(self.ss().page, "home")
        self.assertEqual(self.ss().history, [])

    def test_full_game_rematch_history_delete_and_clear(self):
        self.start_game()
        m = self.ss().match
        play(m, ("f2", "f3"), ("e7", "e5"), ("g2", "g4"), ("d8", "h4"))
        self.run_app()
        self.st.success.assert_called()
        self.assertEqual(len(self.ss().history), 1)
        self.run_app(clicks=["Rematch"])
        self.assertFalse(self.ss().match.game.is_over)
        self.assertEqual(self.ss().match.game.white_name, "Ann")
        # a second finished game
        self.ss().match.resign()
        self.run_app()
        self.assertEqual(len(self.ss().history), 2)
        self.run_app(clicks=["Home"])
        self.run_app(clicks=["Match History"])
        self.run_app()
        rid = self.ss().history[0]["id"]
        self.run_app(clicks=[f"del_{rid}"])
        self.assertEqual(len(self.ss().history), 1)
        self.assertNotIn(rid, [r["id"] for r in self.ss().history])
        self.run_app(clicks=["Clear all"])
        self.assertEqual(self.ss().confirm, "clear")
        self.run_app(clicks=["Cancel"])
        self.assertEqual(len(self.ss().history), 1)
        self.run_app(clicks=["Clear all"])
        self.run_app(clicks=["Delete all"])
        self.assertEqual(self.ss().history, [])

    def test_clock_panel_ends_game_on_timeout(self):
        self.start_game()
        t = [0.0]
        self.ss().match = Match("Ann", "Ben", time_source=lambda: t[0])
        t[0] = 601
        with self.assertRaises(_Rerun):                  # the panel asks for a full redraw
            self.app.players_panel()
        self.assertEqual(self.ss().match.game.status, TIMEOUT)
        self.run_app()
        self.assertEqual(len(self.ss().history), 1)


# --------------------------------------------------------------------------
class EmbeddedSiteTests(unittest.TestCase):
    """app.py: the Netlify website shown full-screen on the Streamlit server."""

    def test_app_embeds_the_website_full_screen(self):
        st = make_streamlit()
        components_v1 = types.ModuleType("streamlit.components.v1")
        components_v1.html = mock.MagicMock(name="html")
        components = types.ModuleType("streamlit.components")
        components.v1 = components_v1
        st.components = components
        mods = {"streamlit": st, "streamlit.components": components, "streamlit.components.v1": components_v1}
        with mock.patch.dict(sys.modules, mods):
            sys.modules.pop("app", None)
            import app
            try:
                app.main()
            finally:
                sys.modules.pop("app", None)
        html = components_v1.html.call_args[0][0]
        self.assertIn('<canvas id="board"', html)
        self.assertIn("class SplashScreen", html)
        self.assertEqual(components_v1.html.call_args[1].get("scrolling"), False)
        css = st.markdown.call_args_list[0][0][0]
        self.assertIn('header[data-testid="stHeader"]', css)
        self.assertIn("100vh", css)


# --------------------------------------------------------------------------
@unittest.skipUnless(os.path.isdir(os.path.join(HERE, "..", "desktop")), "desktop folder not present")
class EngineCopyTests(unittest.TestCase):
    def test_index_html_matches_the_website(self):
        with open(os.path.join(HERE, "index.html"), "rb") as a, open(os.path.join(HERE, "..", "index.html"), "rb") as b:
            self.assertEqual(a.read(), b.read(), "index.html differs from the website; copy ../index.html over")

    def test_engine_files_match_the_desktop_version(self):
        for name in ("constants.py", "pieces.py", "board.py", "game.py", "timer.py", "history_manager.py"):
            with open(os.path.join(HERE, name), "rb") as a, open(os.path.join(HERE, "..", "desktop", name), "rb") as b:
                self.assertEqual(a.read(), b.read(), f"{name} differs from desktop/{name}; copy it over")


if __name__ == "__main__":
    unittest.main()
