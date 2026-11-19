"""
test_chess.py — Rules-engine test suite (no GUI / pygame required).

Run:  python -m unittest test_chess.py -v
"""

import json
import os
import shutil
import tempfile
import unittest

from board import Board
from constants import BLACK, START_FEN, WHITE
from game import (
    CHECKMATE, DRAW_AGREEMENT, FIFTY_MOVE_RULE, INSUFFICIENT_MATERIAL,
    RESIGNATION, STALEMATE, THREEFOLD_REPETITION, TIMEOUT,
    TIMEOUT_VS_INSUFFICIENT, Game, GameOverError, IllegalMoveError,
    generate_legal_moves, is_insufficient_material,
)
from history_manager import HistoryManager, build_match_record, relative_time
from pieces import Bishop, King, Knight, Pawn, Queen, Rook, parse_square as sq
from timer import ChessClock


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def play(game, *moves):
    """Play UCI-style moves such as 'e2e4' or 'a7a8q'."""
    record = None
    for text in moves:
        promo = text[4].upper() if len(text) == 5 else None
        record = game.make_move(sq(text[:2]), sq(text[2:4]), promo)
    return record


def targets(game, square):
    return {f"{'abcdefgh'[c]}{8 - r}" for r, c in game.legal_targets(sq(square))}


def perft(board, depth):
    moves = generate_legal_moves(board)
    if depth == 1:
        return len(moves)
    total = 0
    for move in moves:
        child = board.copy()
        child.make_move(move)
        total += perft(child, depth - 1)
    return total


class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# --------------------------------------------------------------------------
# Move generation correctness (perft against published reference counts)
# --------------------------------------------------------------------------
class TestPerft(unittest.TestCase):
    def test_start_position(self):
        board = Board()
        self.assertEqual(perft(board, 1), 20)
        self.assertEqual(perft(board, 2), 400)
        self.assertEqual(perft(board, 3), 8902)

    def test_kiwipete(self):
        # Castling, en passant, promotions and pins all exercised.
        board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        self.assertEqual(perft(board, 1), 48)
        self.assertEqual(perft(board, 2), 2039)

    def test_position_3_endgame(self):
        board = Board("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1")
        self.assertEqual(perft(board, 3), 2812)

    def test_position_4_promotions(self):
        board = Board("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1")
        self.assertEqual(perft(board, 2), 264)

    def test_position_5(self):
        board = Board("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8")
        self.assertEqual(perft(board, 2), 1486)


# --------------------------------------------------------------------------
# Legal move filtering
# --------------------------------------------------------------------------
class TestLegalMoveFiltering(unittest.TestCase):
    def test_initial_position_has_twenty_moves(self):
        self.assertEqual(len(Game().legal_moves()), 20)

    def test_pinned_piece_cannot_move(self):
        game = Game(fen="4k3/8/8/8/4r3/8/4N3/4K3 w - - 0 1")
        self.assertEqual(game.legal_moves_from(sq("e2")), [])

    def test_pinned_slider_may_move_along_pin(self):
        game = Game(fen="4k3/8/8/8/4r3/8/4R3/4K3 w - - 0 1")
        self.assertEqual(targets(game, "e2"), {"e3", "e4"})

    def test_king_cannot_walk_into_check(self):
        game = Game(fen="4k3/8/8/8/8/8/3r4/4K3 w - - 0 1")
        self.assertEqual(targets(game, "e1"), {"d2", "f1"})

    def test_kings_cannot_touch(self):
        game = Game(fen="8/8/8/3k4/8/3K4/P7/8 w - - 0 1")
        self.assertFalse(game.is_over)
        self.assertTrue(targets(game, "d3").isdisjoint({"c4", "d4", "e4"}))

    def test_must_resolve_check(self):
        game = Game(fen="4k3/8/8/8/8/8/P7/4K2r w - - 0 1")
        self.assertTrue(game.in_check())
        self.assertEqual(game.legal_moves_from(sq("a2")), [])
        with self.assertRaises(IllegalMoveError):
            play(game, "a2a3")
        for move in game.legal_moves():
            sim = game.board.copy()
            sim.make_move(move)
            self.assertFalse(sim.in_check(WHITE))

    def test_cannot_move_opponents_piece(self):
        with self.assertRaises(IllegalMoveError):
            play(Game(), "e7e5")

    def test_cannot_capture_own_piece(self):
        self.assertNotIn("b1", targets(Game(), "a1"))
        self.assertEqual(targets(Game(), "a1"), set())

    def test_turn_switches(self):
        game = Game()
        self.assertEqual(game.turn, WHITE)
        play(game, "e2e4")
        self.assertEqual(game.turn, BLACK)


# --------------------------------------------------------------------------
# Checkmate & stalemate
# --------------------------------------------------------------------------
class TestCheckmate(unittest.TestCase):
    def test_fools_mate(self):
        game = Game()
        record = play(game, "f2f3", "e7e5", "g2g4", "d8h4")
        self.assertTrue(game.is_over)
        self.assertEqual(game.status, CHECKMATE)
        self.assertEqual(game.outcome.winner, BLACK)
        self.assertEqual(game.outcome.result, "0-1")
        self.assertEqual(record.san, "Qh4#")
        self.assertTrue(record.is_checkmate)
        self.assertEqual(game.legal_moves(), [])

    def test_scholars_mate(self):
        game = Game()
        play(game, "e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7")
        self.assertEqual(game.status, CHECKMATE)
        self.assertEqual(game.outcome.result, "1-0")
        self.assertEqual(game.san_list()[-1], "Qxf7#")

    def test_back_rank_mate(self):
        game = Game(fen="6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        record = play(game, "a1a8")
        self.assertEqual(record.san, "Ra8#")
        self.assertEqual(game.status, CHECKMATE)

    def test_check_is_not_mate(self):
        game = Game(fen="4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
        record = play(game, "a1a8")
        self.assertEqual(record.san, "Ra8+")
        self.assertFalse(game.is_over)
        self.assertEqual(game.checked_king_square(), sq("e8"))

    def test_moving_after_game_over_raises(self):
        game = Game()
        play(game, "f2f3", "e7e5", "g2g4", "d8h4")
        with self.assertRaises(GameOverError):
            play(game, "a2a3")


class TestStalemate(unittest.TestCase):
    def test_stalemate_by_move(self):
        game = Game(fen="7k/8/5QK1/8/8/8/8/8 w - - 0 1")
        play(game, "f6f7")
        self.assertEqual(game.status, STALEMATE)
        self.assertIsNone(game.outcome.winner)
        self.assertEqual(game.outcome.result, "1/2-1/2")

    def test_stalemate_position_detected_on_load(self):
        game = Game(fen="7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertEqual(game.status, STALEMATE)

    def test_no_moves_but_in_check_is_mate_not_stalemate(self):
        game = Game(fen="7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
        self.assertEqual(game.status, CHECKMATE)


# --------------------------------------------------------------------------
# En passant
# --------------------------------------------------------------------------
class TestEnPassant(unittest.TestCase):
    def test_en_passant_capture(self):
        game = Game()
        play(game, "e2e4", "a7a6", "e4e5", "d7d5")
        self.assertEqual(game.board.en_passant_square, sq("d6"))
        self.assertIn("d6", targets(game, "e5"))
        record = play(game, "e5d6")
        self.assertEqual(record.san, "exd6")
        self.assertTrue(record.applied.is_en_passant)
        self.assertIsNone(game.board.piece_at(sq("d5")))
        self.assertIsInstance(game.board.piece_at(sq("d6")), Pawn)
        self.assertEqual(game.captured_by(WHITE), ["P"])

    def test_en_passant_only_immediately(self):
        game = Game()
        play(game, "e2e4", "a7a6", "e4e5", "d7d5", "g1f3", "a6a5")
        self.assertNotIn("d6", targets(game, "e5"))
        with self.assertRaises(IllegalMoveError):
            play(game, "e5d6")

    def test_en_passant_cannot_expose_king(self):
        game = Game(fen="8/8/8/K2pP2r/8/8/8/7k w - d6 0 1")
        self.assertNotIn("d6", targets(game, "e5"))

    def test_black_en_passant(self):
        game = Game()
        play(game, "a2a3", "d7d5", "a3a4", "d5d4", "e2e4")
        record = play(game, "d4e3")
        self.assertEqual(record.san, "dxe3")
        self.assertIsNone(game.board.piece_at(sq("e4")))


# --------------------------------------------------------------------------
# Castling
# --------------------------------------------------------------------------
CASTLE_FEN = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"


class TestCastling(unittest.TestCase):
    def test_kingside_castle(self):
        game = Game(fen=CASTLE_FEN)
        record = play(game, "e1g1")
        self.assertEqual(record.san, "O-O")
        self.assertIsInstance(game.board.piece_at(sq("g1")), King)
        self.assertIsInstance(game.board.piece_at(sq("f1")), Rook)
        self.assertIsNone(game.board.piece_at(sq("h1")))
        self.assertNotIn("K", game.board.castling_rights)
        self.assertNotIn("Q", game.board.castling_rights)

    def test_queenside_castle(self):
        game = Game(fen=CASTLE_FEN)
        record = play(game, "e1c1")
        self.assertEqual(record.san, "O-O-O")
        self.assertIsInstance(game.board.piece_at(sq("c1")), King)
        self.assertIsInstance(game.board.piece_at(sq("d1")), Rook)
        self.assertIsNone(game.board.piece_at(sq("a1")))

    def test_black_castles(self):
        game = Game(fen=CASTLE_FEN)
        play(game, "a1a2")
        record = play(game, "e8c8")
        self.assertEqual(record.san, "O-O-O")
        self.assertIsInstance(game.board.piece_at(sq("d8")), Rook)

    def test_no_castling_through_attacked_square(self):
        game = Game(fen="r3kr2/8/8/8/8/8/8/R3K2R w KQq - 0 1")
        self.assertNotIn("g1", targets(game, "e1"))
        self.assertIn("c1", targets(game, "e1"))

    def test_no_castling_into_check(self):
        game = Game(fen="r3k1r1/8/8/8/8/8/8/R3K2R w KQq - 0 1")
        self.assertNotIn("g1", targets(game, "e1"))

    def test_no_castling_out_of_check(self):
        game = Game(fen="4k3/8/8/8/4r3/8/8/R3K2R w KQ - 0 1")
        self.assertTrue(targets(game, "e1").isdisjoint({"g1", "c1"}))

    def test_b_file_attack_does_not_prevent_queenside(self):
        game = Game(fen="1r2k3/8/8/8/8/8/8/R3K3 w Q - 0 1")
        self.assertIn("c1", targets(game, "e1"))

    def test_blocked_path(self):
        game = Game()
        self.assertTrue(targets(game, "e1").isdisjoint({"g1", "c1"}))
        game = Game(fen="r3k2r/8/8/8/8/8/8/RN2K1NR w KQkq - 0 1")
        self.assertTrue(targets(game, "e1").isdisjoint({"g1", "c1"}))

    def test_rights_lost_after_king_moves(self):
        game = Game(fen=CASTLE_FEN)
        play(game, "e1f1", "a8b8", "f1e1", "b8a8")
        self.assertTrue(targets(game, "e1").isdisjoint({"g1", "c1"}))

    def test_rights_lost_after_rook_moves(self):
        game = Game(fen=CASTLE_FEN)
        play(game, "h1h2", "a8b8", "h2h1", "b8a8")
        self.assertNotIn("g1", targets(game, "e1"))
        self.assertIn("c1", targets(game, "e1"))

    def test_rights_lost_when_rook_captured(self):
        game = Game(fen="r3k2r/8/8/8/8/8/6b1/R3K2R b KQkq - 0 1")
        play(game, "g2h1")
        self.assertNotIn("K", game.board.castling_rights)
        self.assertIn("Q", game.board.castling_rights)


# --------------------------------------------------------------------------
# Promotion
# --------------------------------------------------------------------------
class TestPromotion(unittest.TestCase):
    def test_promotion_requires_choice(self):
        game = Game(fen="8/P7/8/8/8/8/8/k6K w - - 0 1")
        self.assertTrue(game.is_promotion_move(sq("a7"), sq("a8")))
        with self.assertRaises(IllegalMoveError):
            game.make_move(sq("a7"), sq("a8"))

    def test_four_promotion_options_generated(self):
        game = Game(fen="8/P7/8/8/8/8/8/k6K w - - 0 1")
        promos = sorted(m.promotion for m in game.legal_moves_from(sq("a7")))
        self.assertEqual(promos, ["B", "N", "Q", "R"])

    def test_promote_to_queen_gives_check(self):
        game = Game(fen="8/P7/8/8/8/8/8/k6K w - - 0 1")
        record = play(game, "a7a8q")
        self.assertIsInstance(game.board.piece_at(sq("a8")), Queen)
        self.assertEqual(record.san, "a8=Q+")
        self.assertTrue(record.applied.is_promotion)

    def test_underpromotion_to_knight(self):
        game = Game(fen="8/P7/8/8/8/8/8/k6K w - - 0 1")
        record = play(game, "a7a8n")
        self.assertIsInstance(game.board.piece_at(sq("a8")), Knight)
        self.assertEqual(record.san, "a8=N")

    def test_promotion_with_capture(self):
        game = Game(fen="1r5k/P7/8/8/8/8/8/K7 w - - 0 1")
        record = play(game, "a7b8q")
        self.assertEqual(record.san, "axb8=Q+")
        self.assertEqual(game.captured_by(WHITE), ["R"])

    def test_black_promotion(self):
        game = Game(fen="k7/8/8/8/8/8/p7/7K b - - 0 1")
        record = play(game, "a2a1r")
        self.assertIsInstance(game.board.piece_at(sq("a1")), Rook)
        self.assertEqual(record.san, "a1=R+")

    def test_promotion_updates_material(self):
        game = Game(fen="k7/7P/8/8/8/8/8/K7 w - - 0 1")
        self.assertEqual(game.material_advantage(WHITE), 1)
        play(game, "h7h8q")
        self.assertEqual(game.material_advantage(WHITE), 9)

    def test_bishop_promotion(self):
        game = Game(fen="8/P6k/8/8/8/8/8/K7 w - - 0 1")
        play(game, "a7a8b")
        self.assertIsInstance(game.board.piece_at(sq("a8")), Bishop)


# --------------------------------------------------------------------------
# Draw rules, resignation, timeout
# --------------------------------------------------------------------------
class TestDrawsAndResults(unittest.TestCase):
    def test_threefold_repetition(self):
        game = Game()
        shuffle = ("g1f3", "g8f6", "f3g1", "f6g8")
        play(game, *shuffle)
        play(game, "g1f3", "g8f6", "f3g1")
        self.assertFalse(game.is_over)
        play(game, "f6g8")
        self.assertEqual(game.status, THREEFOLD_REPETITION)
        self.assertEqual(game.outcome.result, "1/2-1/2")

    def test_fifty_move_rule(self):
        game = Game(fen="4k3/8/8/8/8/8/8/R3K3 w - - 99 80")
        self.assertFalse(game.is_over)
        play(game, "a1a2")
        self.assertEqual(game.status, FIFTY_MOVE_RULE)

    def test_pawn_move_resets_fifty_move_clock(self):
        game = Game(fen="4k3/8/8/8/8/8/P7/R3K3 w - - 98 80")
        play(game, "a2a3")
        self.assertEqual(game.board.halfmove_clock, 0)
        self.assertFalse(game.is_over)

    def test_checkmate_beats_fifty_move_rule(self):
        game = Game(fen="6k1/5ppp/8/8/8/8/8/R5K1 w - - 99 80")
        play(game, "a1a8")
        self.assertEqual(game.status, CHECKMATE)

    def test_insufficient_material_after_capture(self):
        game = Game(fen="4k3/8/8/8/8/8/3q4/4K3 w - - 0 1")
        play(game, "e1d2")
        self.assertEqual(game.status, INSUFFICIENT_MATERIAL)

    def test_insufficient_material_cases(self):
        cases = {
            "4k3/8/8/8/8/8/8/4K3 w - - 0 1": True,          # K v K
            "4k3/8/8/8/8/8/8/2B1K3 w - - 0 1": True,        # K+B v K
            "4k3/8/8/8/8/8/8/1N2K3 w - - 0 1": True,        # K+N v K
            "2b1k3/8/8/8/8/8/8/2B1K3 w - - 0 1": False,     # opposite-colour bishops
            "3bk3/8/8/8/8/8/8/2B1K3 w - - 0 1": True,       # same-colour bishops
            "4k3/8/8/8/8/8/8/1NN1K3 w - - 0 1": False,      # K+NN v K is not dead
            "4k3/8/8/8/8/8/P7/4K3 w - - 0 1": False,        # pawn
        }
        for fen, expected in cases.items():
            with self.subTest(fen=fen):
                self.assertEqual(is_insufficient_material(Board(fen)), expected)

    def test_resignation(self):
        game = Game("Alice", "Bob")
        game.resign(WHITE)
        self.assertEqual(game.status, RESIGNATION)
        self.assertEqual(game.outcome.result, "0-1")
        self.assertEqual(game.result_headline(), "Bob Wins")

    def test_draw_agreement(self):
        game = Game()
        game.agree_draw()
        self.assertEqual(game.status, DRAW_AGREEMENT)
        self.assertIsNone(game.outcome.winner)

    def test_timeout_win(self):
        game = Game()
        game.timeout(WHITE)
        self.assertEqual(game.status, TIMEOUT)
        self.assertEqual(game.outcome.winner, BLACK)

    def test_timeout_vs_insufficient_material_is_draw(self):
        game = Game(fen="4k3/8/8/8/8/8/P7/4K3 b - - 0 1")
        game.timeout(WHITE)          # Black has a lone king: cannot win
        self.assertEqual(game.status, TIMEOUT_VS_INSUFFICIENT)
        self.assertEqual(game.outcome.result, "1/2-1/2")


# --------------------------------------------------------------------------
# Notation, FEN, captures & material
# --------------------------------------------------------------------------
class TestNotationAndState(unittest.TestCase):
    def test_start_fen_export(self):
        self.assertEqual(Board().to_fen(), START_FEN)

    def test_fen_after_e4(self):
        game = Game()
        play(game, "e2e4")
        self.assertEqual(game.fen(),
                         "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")

    def test_fen_round_trip(self):
        fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
        self.assertEqual(Board(fen).to_fen(), fen)

    def test_clone_is_independent(self):
        board = Board()
        clone = board.copy()
        clone.set_piece(sq("e2"), None)
        self.assertIsNotNone(board.piece_at(sq("e2")))

    def test_file_disambiguation(self):
        game = Game(fen="4k3/8/8/8/8/8/8/1N3N1K w - - 0 1")
        self.assertEqual(play(game, "b1d2").san, "Nbd2")

    def test_rank_disambiguation(self):
        game = Game(fen="4k3/8/8/R7/8/8/8/R3K3 w - - 0 1")
        self.assertEqual(play(game, "a1a3").san, "R1a3")

    def test_full_square_disambiguation(self):
        game = Game(fen="8/7k/8/8/8/2Q1Q3/8/K3Q3 w - - 0 1")
        self.assertEqual(play(game, "e3d2").san, "Qe3d2")

    def test_pawn_capture_san(self):
        game = Game()
        play(game, "e2e4", "d7d5")
        self.assertEqual(play(game, "e4d5").san, "exd5")

    def test_captures_and_material_lead(self):
        game = Game()
        play(game, "e2e4", "d7d5", "e4d5", "d8d5", "b1c3")
        self.assertEqual(game.captured_by(WHITE), ["P"])
        self.assertEqual(game.captured_by(BLACK), ["P"])
        self.assertEqual(game.material_advantage(WHITE), 0)
        play(game, "d5a2", "a1a2")
        self.assertEqual(game.captured_by(WHITE), ["P", "Q"])
        self.assertEqual(game.material_advantage(WHITE), 8)
        self.assertEqual(game.material_advantage(BLACK), 0)

    def test_fullmove_count(self):
        game = Game()
        play(game, "e2e4")
        self.assertEqual(game.fullmove_count(), 1)
        play(game, "e7e5", "g1f3")
        self.assertEqual(game.fullmove_count(), 2)


# --------------------------------------------------------------------------
# Clock
# --------------------------------------------------------------------------
class TestChessClock(unittest.TestCase):
    def test_format(self):
        self.assertEqual(ChessClock.format_time(600), "10:00")
        self.assertEqual(ChessClock.format_time(599.4), "9:59")
        self.assertEqual(ChessClock.format_time(20.0), "0:20")
        self.assertEqual(ChessClock.format_time(19.84), "0:19.8")
        self.assertEqual(ChessClock.format_time(0.05), "0:00.0")
        self.assertEqual(ChessClock.format_time(-3), "0:00.0")

    def test_running_switching_pausing(self):
        fake = FakeTime()
        clock = ChessClock(600, time_source=fake)
        clock.start(WHITE)
        fake.advance(5)
        self.assertAlmostEqual(clock.time_left(WHITE), 595)
        clock.switch()
        fake.advance(3)
        self.assertAlmostEqual(clock.time_left(BLACK), 597)
        self.assertAlmostEqual(clock.time_left(WHITE), 595)
        clock.pause()
        fake.advance(100)
        self.assertAlmostEqual(clock.time_left(BLACK), 597)
        clock.resume()
        fake.advance(1)
        self.assertAlmostEqual(clock.time_left(BLACK), 596)

    def test_flag(self):
        fake = FakeTime()
        clock = ChessClock(10, time_source=fake)
        clock.start(WHITE)
        self.assertIsNone(clock.flagged())
        fake.advance(10.5)
        self.assertEqual(clock.flagged(), WHITE)
        self.assertEqual(clock.time_left(WHITE), 0)


# --------------------------------------------------------------------------
# Match history persistence
# --------------------------------------------------------------------------
class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "match_history.json")
        self.fake = FakeTime()
        self.fake.now = 1_700_000_000.0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relative_time_in_hours(self):
        now = 10_000_000.0
        self.assertEqual(relative_time(now - 30, now), "Just now")
        self.assertEqual(relative_time(now - 3599, now), "Just now")
        self.assertEqual(relative_time(now - 3600, now), "1 hour ago")
        self.assertEqual(relative_time(now - 2 * 3600 - 5, now), "2 hours ago")
        self.assertEqual(relative_time(now - 4 * 3600, now), "4 hours ago")

    def test_save_and_load_newest_first(self):
        manager = HistoryManager(self.path, clock=self.fake)
        game = Game("Alice", "Bob")
        play(game, "f2f3", "e7e5", "g2g4", "d8h4")
        manager.save_game(game)
        self.fake.advance(60)
        game2 = Game("Carol", "Dan")
        game2.agree_draw()
        manager.save_game(game2)

        matches = manager.load_matches()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["white"], "Carol")
        self.assertEqual(matches[1]["result"], "0-1")
        self.assertEqual(matches[1]["winner"], "black")
        self.assertEqual(matches[1]["reason"], CHECKMATE)
        self.assertEqual(matches[1]["move_count"], 2)
        self.assertEqual(matches[1]["moves"], ["f3", "e5", "g4", "Qh4#"])
        self.assertTrue(matches[1]["final_fen"].startswith("rnb1kbnr/pppp1ppp"))

    def test_corrupt_file_is_quarantined(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        manager = HistoryManager(self.path, clock=self.fake)
        self.assertEqual(manager.load_matches(), [])
        self.assertFalse(os.path.exists(self.path))
        manager.save_game(Game())
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)["matches"]), 1)

    def test_delete_single_match(self):
        manager = HistoryManager(self.path, clock=self.fake)
        first = manager.save_game(Game("Alice", "Bob"))
        self.fake.advance(60)
        manager.save_game(Game("Carol", "Dan"))
        self.assertTrue(manager.delete_match(first["id"]))
        remaining = manager.load_matches()
        self.assertEqual([m["white"] for m in remaining], ["Carol"])
        self.assertFalse(manager.delete_match(first["id"]))     # already gone
        self.assertFalse(manager.delete_match(None))

    def test_clear_all(self):
        manager = HistoryManager(self.path, clock=self.fake)
        manager.save_game(Game())
        manager.save_game(Game())
        manager.clear()
        self.assertEqual(manager.load_matches(), [])

    def test_record_shape(self):
        game = Game("A", "B")
        game.resign(BLACK)
        record = build_match_record(game, timestamp=123.0)
        for key in ("white", "black", "result", "winner", "reason",
                    "move_count", "final_fen", "timestamp"):
            self.assertIn(key, record)
        self.assertEqual(record["winner"], "white")


if __name__ == "__main__":
    unittest.main(verbosity=2)
