/*
 * End-to-end tests for the Classical Chess website.
 *
 * Serves the repository root (index.html + intro videos) on a local port, then drives the real
 * page in headless Chromium: intro, menus, moves, special rules, game endings, match history,
 * keyboard, sound and layout at five screen sizes.
 *
 *   cd tests && npm install && npx playwright install chromium && node e2e.js
 *
 * Exits with code 1 if any test fails.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const http = require('http');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mp4': 'video/mp4', '.webm': 'video/webm', '.json': 'application/json' };

function serve() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html';
    const file = path.resolve(ROOT, rel);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
    const size = fs.statSync(file).size, type = TYPES[path.extname(file)] || 'application/octet-stream';
    const range = /bytes=(\d*)-(\d*)/.exec(req.headers.range || '');
    if (range) {   // byte ranges, as browsers request them for video
      const start = range[1] ? Number(range[1]) : 0, end = range[2] ? Number(range[2]) : size - 1;
      res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1 });
      return fs.createReadStream(file, { start, end }).pipe(res);
    }
    res.writeHead(200, { 'Content-Type': type, 'Content-Length': size, 'Accept-Ranges': 'bytes' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

let URL = '';
const results = [];
let current = '';
const ok = (cond, msg) => { if (!cond) throw new Error(msg); };
async function test(name, fn) {
  current = name;
  try { await fn(); results.push([name, 'PASS', '']); }
  catch (e) { results.push([name, 'FAIL', String(e.message || e).split('\n')[0]]); }
}

(async () => {
  const server = await serve();
  URL = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  const blockedBrowser = await chromium.launch({ args: ['--autoplay-policy=user-gesture-required'] });
  const pageErrors = [];

  async function open(b = browser, viewport = { width: 1000, height: 1000 }, opts = {}) {
    const ctx = await b.newContext({ viewport, ...opts });
    const p = await ctx.newPage();
    p.on('pageerror', (e) => pageErrors.push(`${current}: ${e.message}`));
    p.on('console', (m) => { if (m.type() === 'error' && !/fonts\.g|ERR_|net::/.test(m.text())) pageErrors.push(`${current}: console ${m.text()}`); });
    await p.goto(URL);
    await p.waitForFunction(() => typeof APP !== 'undefined' && APP);
    return p;
  }
  const skipIntro = async (p) => { await p.keyboard.press('Escape'); await p.waitForFunction(() => !document.getElementById('intro')); await p.waitForTimeout(150); };
  const state = (p) => p.evaluate(() => APP.state);
  const toPage = async (p, x, y) => p.evaluate(([x, y]) => { const r = document.getElementById('board').getBoundingClientRect(); return [r.left + x * r.width / 640, r.top + y * r.height / 892]; }, [x, y]);
  const clickAt = async (p, x, y) => { const [a, b] = await toPage(p, x, y); await p.mouse.click(a, b); await p.waitForTimeout(60); };
  const clickRect = async (p, expr) => { const r = await p.evaluate(expr); ok(r, 'button not found: ' + expr); await clickAt(p, r.x + r.w / 2, r.y + r.h / 2); };
  const sqXY = (n) => ['abcdefgh'.indexOf(n[0]) * 80 + 40, 176 + (8 - Number(n[1])) * 80 + 40];
  const move = async (p, a, b) => { await clickAt(p, ...sqXY(a)); await clickAt(p, ...sqXY(b)); await p.waitForTimeout(60); };
  const go = async (p, s) => { await p.evaluate((s) => APP.go(s), s); await p.waitForTimeout(400); };
  const startGame = async (p, fen) => {
    await go(p, 'SETUP'); await clickRect(p, () => APP.screen.startBtn.rect); await p.waitForTimeout(400);
    ok(await state(p) === 'GAME', 'did not reach the game');
    if (fen) await p.evaluate((f) => { const s = APP.screen; s.game = new Game(s.game.whiteName, s.game.blackName, f); s.clock.start(s.game.turn); s.tokensDirty = true; }, fen);
  };
  const pieceAt = (p, n) => p.evaluate((n) => { const x = APP.screen.game.board.pieceAt(parseSquare(n)); return x ? x.color + x.kind : null; }, n);
  const storedHistory = (p) => p.evaluate(() => JSON.parse(localStorage.getItem('classical-chess.history') || '[]'));

  // ---------------------------------------------------------------- 1. engine
  await test('Rules engine in the browser: perft + 25 rule checks', async () => {
    const p = await open(); await skipIntro(p);
    const logs = []; p.on('console', (m) => logs.push(m.text()));
    await p.addScriptTag({ content: fs.readFileSync(path.join(__dirname, 'engine-checks.js'), 'utf8') });
    await p.waitForTimeout(300);
    ok(logs.some((l) => l.includes('all engine checks passed')), logs.filter((l) => l.startsWith('FAIL')).join('; ') || 'engine tests did not finish');
    await p.context().close();
  });

  // ---------------------------------------------------------------- 2. intro
  await test('Intro plays with sound when the browser allows it, then opens Home', async () => {
    const p = await open(); await p.waitForTimeout(900);
    const v = await p.evaluate(() => { const v = document.querySelector('#intro video'); return v && { playing: !v.paused, muted: v.muted, src: v.currentSrc.split('/').pop() }; });
    ok(v && v.playing && !v.muted, 'expected unmuted playback, got ' + JSON.stringify(v));
    await p.waitForFunction(() => !document.getElementById('intro'), null, { timeout: 7000 });
    ok(await state(p) === 'HOME', 'not on Home after intro');
    await p.context().close();
  });
  await test('Intro falls back to muted when sound is blocked (no buttons shown)', async () => {
    const p = await open(blockedBrowser); await p.waitForTimeout(900);
    const v = await p.evaluate(() => { const v = document.querySelector('#intro video'); return v && { playing: !v.paused, muted: v.muted, buttons: document.querySelectorAll('#intro button').length }; });
    ok(v && v.playing && v.muted && v.buttons === 0, JSON.stringify(v));
    await p.waitForFunction(() => !document.getElementById('intro'), null, { timeout: 7000 });
    await p.context().close();
  });
  await test('Esc, Enter and Space each skip the intro', async () => {
    for (const key of ['Escape', 'Enter', 'Space']) {
      const p = await open(); await p.waitForTimeout(500); await p.keyboard.press(key);
      await p.waitForFunction(() => !document.getElementById('intro'), null, { timeout: 2000 });
      ok(await state(p) === 'HOME', key + ' left Home');   // the key must not also trigger "Play"
      await p.context().close();
    }
  });
  await test('Game is locked while the intro is showing', async () => {
    const p = await open(); await p.waitForTimeout(400);
    ok(await p.evaluate(() => APP.blocked) === true, 'app not blocked during intro');
    await p.context().close();
  });

  // ---------------------------------------------------------------- 3. home & setup
  await test('Home: Play Game, Match History and Sound toggle work', async () => {
    const p = await open(); await skipIntro(p);
    await clickRect(p, () => APP.screen.historyBtn.rect); await p.waitForTimeout(400);
    ok(await state(p) === 'HISTORY', 'Match History did not open');
    await go(p, 'HOME');
    const before = await p.evaluate(() => APP.sound.muted);
    await clickRect(p, () => APP.screen.soundBtn.rect);
    const after = await p.evaluate(() => [APP.sound.muted, localStorage.getItem('classical-chess.muted')]);
    ok(after[0] === !before && after[1] === (after[0] ? '1' : '0'), 'sound toggle not saved: ' + after);
    await clickRect(p, () => APP.screen.soundBtn.rect);
    await clickRect(p, () => APP.screen.playBtn.rect); await p.waitForTimeout(400);
    ok(await state(p) === 'SETUP', 'Play Game did not open setup');
    await p.context().close();
  });
  await test('Setup: names, empty-name defaults, Swap Sides, 16-char limit', async () => {
    const p = await open(); await skipIntro(p); await go(p, 'SETUP');
    await p.fill('#p1-name', 'Azim'); await p.fill('#p2-name', '');
    ok(await p.getAttribute('#p1-name', 'maxlength') === '16', 'no 16-char limit');
    await clickRect(p, () => APP.screen.swapBtn.rect); await p.waitForTimeout(300);
    await clickRect(p, () => APP.screen.startBtn.rect); await p.waitForTimeout(400);
    const names = await p.evaluate(() => [APP.screen.game.whiteName, APP.screen.game.blackName]);
    ok(names[0] === 'Player 2' && names[1] === 'Azim', 'expected Player 2 (White) vs Azim (Black), got ' + names);
    await p.context().close();
  });

  // ---------------------------------------------------------------- 4. gameplay
  await test('Click-to-move, legal-move dots, illegal moves rejected', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    await clickAt(p, ...sqXY('e2'));
    const t = await p.evaluate(() => [...APP.screen.targets].map(squareName).sort().join(','));
    ok(t === 'e3,e4', 'e2 targets were ' + t);
    await clickAt(p, ...sqXY('e5'));             // illegal
    ok(await pieceAt(p, 'e2') === 'wP', 'illegal move was played');
    await move(p, 'e2', 'e4');
    ok(await pieceAt(p, 'e4') === 'wP' && await p.evaluate(() => APP.screen.game.turn) === 'b', 'e4 not played');
    await clickAt(p, ...sqXY('d2'));             // White piece on Black's turn
    ok(await p.evaluate(() => APP.screen.selected) === null, 'could select a piece out of turn');
    await p.context().close();
  });
  await test('Drag-and-drop moves a piece', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    const [a1, a2] = await toPage(p, ...sqXY('g1')), [b1, b2] = await toPage(p, ...sqXY('f3'));
    await p.mouse.move(a1, a2); await p.mouse.down(); await p.mouse.move(a1 + 20, a2 - 20, { steps: 4 }); await p.mouse.move(b1, b2, { steps: 8 }); await p.mouse.up();
    await p.waitForTimeout(150);
    ok(await pieceAt(p, 'f3') === 'wN', 'knight not on f3');
    await p.context().close();
  });
  await test('Castling both sides through the board', async () => {
    const p = await open(); await skipIntro(p); await startGame(p, 'r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1');
    await move(p, 'e1', 'g1');
    ok(await pieceAt(p, 'g1') === 'wK' && await pieceAt(p, 'f1') === 'wR', 'White O-O failed');
    await move(p, 'e8', 'c8');
    ok(await pieceAt(p, 'c8') === 'bK' && await pieceAt(p, 'd8') === 'bR', 'Black O-O-O failed');
    const san = await p.evaluate(() => APP.screen.game.sanList().join(' '));
    ok(san === 'O-O O-O-O', 'notation was ' + san);
    await p.context().close();
  });
  await test('En passant through the board', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    for (const [a, b] of [['e2', 'e4'], ['a7', 'a6'], ['e4', 'e5'], ['d7', 'd5'], ['e5', 'd6']]) await move(p, a, b);
    ok(await pieceAt(p, 'd5') === null && await pieceAt(p, 'd6') === 'wP', 'en passant failed');
    ok(await p.evaluate(() => APP.screen.game.sanList().pop()) === 'exd6', 'notation wrong');
    await p.context().close();
  });
  await test('Promotion card: choose a Knight, then cancel works', async () => {
    const p = await open(); await skipIntro(p); await startGame(p, '7k/P7/8/8/8/8/8/K7 w - - 0 1');
    await move(p, 'a7', 'a8');
    ok(await p.evaluate(() => !!APP.screen.promotion), 'promotion card did not open');
    await clickRect(p, () => APP.screen.promotion.cancel);
    ok(await p.evaluate(() => !APP.screen.promotion) && await pieceAt(p, 'a7') === 'wP', 'cancel failed');
    await move(p, 'a7', 'a8');
    await clickRect(p, () => APP.screen.promotion.options.find(([k]) => k === 'N')[1]);
    ok(await pieceAt(p, 'a8') === 'wN', 'did not promote to a knight');
    ok(await p.evaluate(() => APP.screen.game.sanList().pop()) === 'a8=N', 'notation wrong');
    await p.context().close();
  });
  await test("Fool's Mate ends the game in checkmate and shows the result card", async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    for (const [a, b] of [['f2', 'f3'], ['e7', 'e5'], ['g2', 'g4'], ['d8', 'h4']]) await move(p, a, b);
    const g = await p.evaluate(() => ({ s: APP.screen.game.status, r: APP.screen.game.outcome.result, h: APP.screen.game.resultHeadline() }));
    ok(g.s === 'checkmate' && g.r === '0-1' && g.h === 'Player 2 Wins', JSON.stringify(g));
    await p.waitForTimeout(700);
    ok(await p.evaluate(() => !!APP.screen.resultModal), 'result card did not appear');
    await p.context().close();
  });
  await test('Move list and captured-material display', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    for (const [a, b] of [['e2', 'e4'], ['d7', 'd5'], ['e4', 'd5'], ['d8', 'd5'], ['b1', 'c3']]) await move(p, a, b);
    await p.waitForTimeout(100);
    const s = await p.evaluate(() => ({ san: APP.screen.game.sanList().join(' '), toks: APP.screen.tokens.filter(t => t.kind === 'move').length,
      latest: APP.screen.tokens.filter(t => t.latest).length, capW: APP.screen.game.capturedBy('w').join(''), capB: APP.screen.game.capturedBy('b').join('') }));
    ok(s.san === 'e4 d5 exd5 Qxd5 Nc3' && s.toks === 5 && s.latest === 1 && s.capW === 'P' && s.capB === 'P', JSON.stringify(s));
    await p.context().close();
  });
  await test('Threefold repetition is detected through the board', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    const shuffle = [['g1', 'f3'], ['g8', 'f6'], ['f3', 'g1'], ['f6', 'g8']];
    for (const m of shuffle.concat(shuffle)) await move(p, ...m);
    ok(await p.evaluate(() => APP.screen.game.status) === 'threefold_repetition', 'not drawn by repetition');
    await p.context().close();
  });
  await test('Resign button asks first, then ends the game for the side to move', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    await clickRect(p, () => APP.screen.resignBtn.rect);
    ok(await p.evaluate(() => !!APP.screen.dialog && !APP.screen.clock.running), 'no confirm dialog / clock not paused');
    await clickRect(p, () => APP.screen.dialog.cancelBtn.rect);
    ok(await p.evaluate(() => !APP.screen.game.isOver && APP.screen.clock.running), 'cancel did not resume');
    await clickRect(p, () => APP.screen.resignBtn.rect);
    await clickRect(p, () => APP.screen.dialog.confirmBtn.rect);
    const g = await p.evaluate(() => [APP.screen.game.status, APP.screen.game.outcome.winner]);
    ok(g[0] === 'resignation' && g[1] === 'b', 'got ' + g);
    await p.context().close();
  });
  await test('Draw offer: accepted ends the game as a draw', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    await clickRect(p, () => APP.screen.drawBtn.rect);
    await clickRect(p, () => APP.screen.dialog.confirmBtn.rect);
    ok(await p.evaluate(() => APP.screen.game.outcome.result) === '1/2-1/2', 'not a draw');
    await p.context().close();
  });
  await test('Clock runs for the side to move and flags on timeout', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    await p.waitForTimeout(1100);
    const t = await p.evaluate(() => [APP.screen.clock.timeLeft('w'), APP.screen.clock.timeLeft('b')]);
    ok(t[0] < 599.2 && t[1] === 600, 'clock times ' + t);
    ok(await p.evaluate(() => ChessClock.format(19.84)) === '0:19.8', 'low-time format wrong');
    await p.evaluate(() => { APP.screen.clock.remaining.w = 0.3; });
    await p.waitForTimeout(700);
    const g = await p.evaluate(() => [APP.screen.game.status, APP.screen.game.outcome && APP.screen.game.outcome.winner]);
    ok(g[0] === 'timeout' && g[1] === 'b', 'got ' + g);
    await p.context().close();
  });
  await test('Leaving mid-game asks first and does not save the game', async () => {
    const p = await open(); await skipIntro(p); await p.evaluate(() => localStorage.clear()); await startGame(p);
    await move(p, 'e2', 'e4');
    await clickRect(p, () => APP.screen.backBtn.rect);
    ok(await p.evaluate(() => !!APP.screen.dialog), 'no confirmation');
    await clickRect(p, () => APP.screen.dialog.confirmBtn.rect); await p.waitForTimeout(400);
    ok(await state(p) === 'HOME' && (await storedHistory(p)).length === 0, 'abandoned game was saved or did not leave');
    await p.context().close();
  });
  await test('Rematch from the result card starts a fresh game with the same players', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    await p.evaluate(() => { APP.screen.game.whiteName = 'Ann'; });
    for (const [a, b] of [['f2', 'f3'], ['e7', 'e5'], ['g2', 'g4'], ['d8', 'h4']]) await move(p, a, b);
    await p.waitForTimeout(700);
    await clickRect(p, () => APP.screen.resultModal.rematch.rect); await p.waitForTimeout(400);
    const s = await p.evaluate(() => [APP.state, APP.screen.game.history.length, APP.screen.game.whiteName]);
    ok(s[0] === 'GAME' && s[1] === 0 && s[2] === 'Ann', 'got ' + s);
    await p.context().close();
  });

  // ---------------------------------------------------------------- 5. history
  await test('Finished games are saved with the right details', async () => {
    const p = await open(); await skipIntro(p); await p.evaluate(() => localStorage.clear()); await startGame(p);
    for (const [a, b] of [['f2', 'f3'], ['e7', 'e5'], ['g2', 'g4'], ['d8', 'h4']]) await move(p, a, b);
    await p.waitForTimeout(300);
    const h = await storedHistory(p);
    ok(h.length === 1, 'saved ' + h.length + ' games');
    const m = h[0];
    ok(m.result === '0-1' && m.winner === 'black' && m.reason === 'checkmate' && m.move_count === 2 &&
       m.moves.join(' ') === 'f3 e5 g4 Qh4#' && m.final_fen.startsWith('rnb1kbnr/pppp1ppp') && m.id, JSON.stringify(m).slice(0, 200));
    await p.context().close();
  });
  await test('History screen lists games; delete one and clear all both confirm first', async () => {
    const p = await open(); await skipIntro(p);
    await p.evaluate(() => {
      const mk = (i, w) => ({ id: 'id' + i, timestamp: Date.now() / 1000 - i * 3600, white: 'W' + i, black: 'B' + i, result: w ? '1-0' : '1/2-1/2',
        winner: w ? 'white' : null, reason: w ? 'checkmate' : 'stalemate', reason_text: w ? 'by checkmate' : 'by stalemate', move_count: 10 + i, moves: [], final_fen: '' });
      localStorage.setItem('classical-chess.history', JSON.stringify([mk(0, true), mk(1, false), mk(2, true)]));
    });
    await go(p, 'HISTORY'); await p.waitForTimeout(300);
    ok(await p.evaluate(() => APP.screen.matches.length) === 3, 'did not list 3 games');
    ok(await p.evaluate(() => relativeTime(APP.screen.matches[1].timestamp)) === '1 hour ago', 'relative time wrong');
    await clickRect(p, () => { const s = APP.screen; return s.deleteRect(s.cardRect(0)); });
    ok(await p.evaluate(() => !!APP.screen.dialog), 'delete did not ask');
    await clickRect(p, () => APP.screen.dialog.confirmBtn.rect); await p.waitForTimeout(300);
    const left = await storedHistory(p);
    ok(left.length === 2 && !left.some((m) => m.id === 'id0'), 'delete one failed');
    await clickRect(p, () => APP.screen.clearBtn.rect);
    await clickRect(p, () => APP.screen.dialog.confirmBtn.rect); await p.waitForTimeout(300);
    ok((await storedHistory(p)).length === 0 && await p.evaluate(() => APP.screen.matches.length) === 0, 'clear all failed');
    await p.context().close();
  });

  // ---------------------------------------------------------------- 6. keyboard & sound
  await test('Keyboard: M mutes, Esc deselects then asks to leave', async () => {
    const p = await open(); await skipIntro(p); await startGame(p);
    const m0 = await p.evaluate(() => APP.sound.muted);
    await p.keyboard.press('m');
    ok(await p.evaluate(() => APP.sound.muted) === !m0, 'M did not toggle mute');
    await p.keyboard.press('m');
    await clickAt(p, ...sqXY('e2')); await p.keyboard.press('Escape');
    ok(await p.evaluate(() => APP.screen.selected) === null, 'Esc did not deselect');
    await p.keyboard.press('Escape');
    ok(await p.evaluate(() => !!APP.screen.dialog), 'Esc did not ask to leave');
    await p.context().close();
  });
  await test('All 7 sound effects are generated after the first interaction', async () => {
    const p = await open(); await skipIntro(p); await clickAt(p, 320, 300);
    const names = await p.evaluate(() => Object.keys(APP.sound.buffers).sort().join(','));
    ok(names === 'capture,castle,check,game_end,game_start,move,promote', 'sounds: ' + names);
    await p.context().close();
  });

  // ---------------------------------------------------------------- 7. layout
  for (const [w, h, label, mobile] of [[1440, 900, 'laptop', false], [1024, 768, 'tablet landscape', false], [768, 1024, 'tablet portrait', true], [390, 844, 'iPhone', true], [360, 640, 'small Android', true]]) {
    await test(`Layout fits with no sideways scroll: ${label} ${w}x${h}`, async () => {
      const p = await open(browser, { width: w, height: h }, mobile ? { isMobile: true, hasTouch: true, deviceScaleFactor: 2 } : {});
      await skipIntro(p);
      const r = await p.evaluate(() => { const b = document.getElementById('board').getBoundingClientRect();
        return { l: b.left, t: b.top, r: b.right, b: b.bottom, sw: document.documentElement.scrollWidth, iw: innerWidth, ih: innerHeight }; });
      ok(r.l >= 15 && r.r <= r.iw - 15 && r.t >= 0 && r.b <= r.ih + 0.5 && r.sw <= r.iw, JSON.stringify(r));
      if (mobile) {   // a tap moves a piece on a touch screen
        await startGame(p);
        for (const s of ['e2', 'e4']) { const [x, y] = await toPage(p, ...sqXY(s)); await p.touchscreen.tap(x, y); await p.waitForTimeout(80); }
        ok(await pieceAt(p, 'e4') === 'wP', 'tap-to-move failed');
      }
      await p.context().close();
    });
  }

  await test('No JavaScript errors during the whole run', async () => { ok(pageErrors.length === 0, pageErrors.slice(0, 3).join(' | ')); });

  await browser.close(); await blockedBrowser.close(); server.close();
  for (const [n, s, why] of results) console.log(`${s}  ${n}${why ? '  -> ' + why : ''}`);
  const passed = results.filter((r) => r[1] === 'PASS').length;
  console.log(`\n${passed}/${results.length} passed`);
  if (passed !== results.length) process.exitCode = 1;
})().catch((e) => { console.error(e); process.exit(1); });
