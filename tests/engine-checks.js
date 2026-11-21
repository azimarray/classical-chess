/*
 * Rules-engine checks for the website, run inside the browser page by e2e.js.
 * They use the page's own engine (Board, Game, ChessClock, ...), so they test the code that is
 * actually deployed. Perft counts are the published reference numbers for each position.
 */
(() => {
let fails = 0;
const eq = (a, b, msg) => { if (JSON.stringify(a) !== JSON.stringify(b)) { fails++; console.log("FAIL", msg, a, b); } };
const sq = parseSquare;
function play(g, ...ms) { let r; for (const t of ms) r = g.makeMove(sq(t.slice(0,2)), sq(t.slice(2,4)), t.length === 5 ? t[4].toUpperCase() : null); return r; }
function perft(b, d) { const ms = generateLegalMoves(b); if (d === 1) return ms.length; let n = 0; for (const m of ms) { const c = b.copy(); c.makeMove(m); n += perft(c, d - 1); } return n; }
const tgt = (g, s) => [...g.legalTargets(sq(s))].map(squareName).sort();
eq(perft(new Board(), 3), 8902, "perft start 3");
eq(perft(new Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"), 2), 2039, "kiwipete");
eq(perft(new Board("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"), 3), 2812, "pos3");
eq(perft(new Board("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1"), 2), 264, "pos4");
eq(perft(new Board("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8"), 2), 1486, "pos5");
let g = new Game(); let r = play(g, "f2f3","e7e5","g2g4","d8h4"); eq([g.status, r.san, g.outcome.result], ["checkmate","Qh4#","0-1"], "fools");
g = new Game(); play(g,"e2e4","e7e5","f1c4","b8c6","d1h5","g8f6","h5f7"); eq(g.sanList().at(-1), "Qxf7#", "scholar");
g = new Game("a","b","7k/8/5QK1/8/8/8/8/8 w - - 0 1"); play(g,"f6f7"); eq(g.status,"stalemate","stalemate");
g = new Game(); play(g,"e2e4","a7a6","e4e5","d7d5"); r = play(g,"e5d6"); eq([r.san, r.applied.isEnPassant, g.capturedBy("w")],["exd6",true,["P"]],"ep");
g = new Game("a","b","8/8/8/K2pP2r/8/8/8/7k w - d6 0 1"); eq(tgt(g,"e5").includes("d6"), false, "ep pin");
g = new Game("a","b","r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"); eq(play(g,"e1g1").san,"O-O","castle");
g = new Game("a","b","r3kr2/8/8/8/8/8/8/R3K2R w KQq - 0 1"); eq([tgt(g,"e1").includes("g1"), tgt(g,"e1").includes("c1")],[false,true],"castle through");
g = new Game("a","b","1r2k3/8/8/8/8/8/8/R3K3 w Q - 0 1"); eq(tgt(g,"e1").includes("c1"), true, "b-file");
g = new Game("a","b","8/P7/8/8/8/8/8/k6K w - - 0 1"); eq(play(g,"a7a8q").san,"a8=Q+","promo");
g = new Game("a","b","1r5k/P7/8/8/8/8/8/K7 w - - 0 1"); eq(play(g,"a7b8q").san,"axb8=Q+","promo cap");
g = new Game(); play(g,"g1f3","g8f6","f3g1","f6g8","g1f3","g8f6","f3g1"); eq(g.isOver,false,"3fold pre"); play(g,"f6g8"); eq(g.status,"threefold_repetition","3fold");
g = new Game("a","b","4k3/8/8/8/8/8/8/R3K3 w - - 99 80"); play(g,"a1a2"); eq(g.status,"fifty_move_rule","50");
g = new Game("a","b","4k3/8/8/8/8/8/3q4/4K3 w - - 0 1"); play(g,"e1d2"); eq(g.status,"insufficient_material","insuff");
g = new Game("a","b","4k3/8/8/8/8/8/P7/4K3 b - - 0 1"); g.timeout("w"); eq(g.status,"timeout_vs_insufficient_material","timeout insuff");
g = new Game("a","b","4k3/8/8/8/8/8/8/1N3N1K w - - 0 1"); eq(play(g,"b1d2").san,"Nbd2","disamb file");
g = new Game("a","b","4k3/8/8/R7/8/8/8/R3K3 w - - 0 1"); eq(play(g,"a1a3").san,"R1a3","disamb rank");
g = new Game("a","b","8/7k/8/8/8/2Q1Q3/8/K3Q3 w - - 0 1"); eq(play(g,"e3d2").san,"Qe3d2","disamb full");
eq(new Board().toFen(), START_FEN, "fen");
g = new Game(); play(g,"e2e4"); eq(g.fen(), "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", "fen e4");
eq([ChessClock.format(600),ChessClock.format(599.4),ChessClock.format(20),ChessClock.format(19.84),ChessClock.format(0.05)],["10:00","9:59","0:20","0:19.8","0:00.0"],"clock fmt");
let t = 1000; const ck = new ChessClock(600, 0, () => t); ck.start("w"); t += 5; eq(ck.timeLeft("w"),595,"clk"); ck.switch(); t+=3; eq(ck.timeLeft("b"),597,"clk2");
eq([relativeTime(0,30),relativeTime(0,3600),relativeTime(0,7205)],["Just now","1 hour ago","2 hours ago"],"rel");
console.log(fails ? fails + " failures" : "all engine checks passed");

})();
