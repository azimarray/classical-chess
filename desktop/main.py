"""
main.py — Classical Chess entry point and screen-state manager.

States: SPLASH -> HOME -> SETUP -> GAME, and HOME -> HISTORY.

All screens render to a fixed logical canvas (640 x 892). The canvas is
scaled to fit the (resizable) window, and mouse coordinates are mapped back
into logical space, so layout code never deals with window size.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

import constants as C  # noqa: E402
import ui  # noqa: E402
from history_manager import HistoryManager  # noqa: E402
from sounds import SoundManager  # noqa: E402


def _enable_windows_dpi_awareness() -> None:
    """Prevent Windows from bitmap-stretching the window on high-DPI screens."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


class App:
    SCREENS = {
        C.STATE_SPLASH: ui.SplashScreen,
        C.STATE_HOME: ui.HomeScreen,
        C.STATE_SETUP: ui.SetupScreen,
        C.STATE_GAME: ui.GameScreen,
        C.STATE_HISTORY: ui.HistoryScreen,
    }

    def __init__(self) -> None:
        _enable_windows_dpi_awareness()
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption(C.APP_TITLE)

        self.window = pygame.display.set_mode(self._initial_window_size(), pygame.RESIZABLE)
        self.canvas = pygame.Surface((C.LOGICAL_WIDTH, C.LOGICAL_HEIGHT)).convert()
        self.frame_clock = pygame.time.Clock()
        self._view = (0, 0, 1.0)            # x offset, y offset, scale
        self._hand_cursor = False
        self._cursor_is_hand = False
        pygame.key.set_repeat(400, 35)

        self.assets = ui.Assets()
        self.sound = SoundManager()
        self.history = HistoryManager()
        self._set_window_icon()

        # Remembered between screens (setup form)
        self.player_names = ["", ""]
        self.p1_white = True

        self.state = None
        self.screen = None
        self._pending = None
        self._fade_snapshot = None
        self._fade_t = 0.0
        self.running = True
        self.go(C.STATE_SPLASH)
        self._apply_pending(fade=False)

    # ------------------------------------------------------------------
    # Window helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _initial_window_size():
        width, height = C.LOGICAL_WIDTH, C.LOGICAL_HEIGHT
        try:
            desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        except Exception:
            info = pygame.display.Info()
            desktop_w, desktop_h = info.current_w, info.current_h
        if desktop_w > 0 and desktop_h > 0:
            scale = min(1.0, desktop_h * 0.88 / height, desktop_w * 0.95 / width)
            width, height = int(width * scale), int(height * scale)
        return width, height

    def _set_window_icon(self) -> None:
        icon = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.rect(icon, C.DARK_SQUARE, icon.get_rect(), border_radius=12)
        pawn = self.assets.piece("P", "white", 56)
        icon.blit(pawn, pawn.get_rect(center=(32, 33)))
        pygame.display.set_icon(icon)

    def to_logical(self, pos):
        ox, oy, scale = self._view
        return (int((pos[0] - ox) / scale), int((pos[1] - oy) / scale))

    def mouse_pos(self):
        return self.to_logical(pygame.mouse.get_pos())

    def request_hand_cursor(self) -> None:
        self._hand_cursor = True

    def _apply_cursor(self) -> None:
        if self._hand_cursor != self._cursor_is_hand:
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if self._hand_cursor
                                        else pygame.SYSTEM_CURSOR_ARROW)
            except (pygame.error, AttributeError):
                pass
            self._cursor_is_hand = self._hand_cursor

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def go(self, state: str, **kwargs) -> None:
        """Request a screen change; applied at the end of the current frame."""
        self._pending = (state, kwargs)

    def _apply_pending(self, fade: bool = True) -> None:
        if self._pending is None:
            return
        state, kwargs = self._pending
        self._pending = None
        if self.screen is not None:
            self.screen.on_exit()
            if fade:
                self._fade_snapshot = self.canvas.copy()
                self._fade_t = 0.0
        self.screen = self.SCREENS[state](self, **kwargs)
        self.state = state
        self.screen.on_enter()

    def quit(self) -> None:
        self.running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _translate(self, event):
        if hasattr(event, "pos") and event.type in (pygame.MOUSEBUTTONDOWN,
                                                    pygame.MOUSEBUTTONUP,
                                                    pygame.MOUSEMOTION):
            data = dict(event.dict)
            data["pos"] = self.to_logical(event.pos)
            return pygame.event.Event(event.type, data)
        return event

    def _present(self) -> None:
        window = pygame.display.get_surface()
        ww, wh = window.get_size()
        lw, lh = C.LOGICAL_WIDTH, C.LOGICAL_HEIGHT
        scale = min(ww / lw, wh / lh)
        sw, sh = max(1, int(lw * scale)), max(1, int(lh * scale))
        ox, oy = (ww - sw) // 2, (wh - sh) // 2
        self._view = (ox, oy, scale)
        if (sw, sh) == (lw, lh):
            if (ox, oy) != (0, 0):
                window.fill(C.BG_DEEP)
            window.blit(self.canvas, (ox, oy))
        else:
            window.fill(C.BG_DEEP)
            window.blit(pygame.transform.smoothscale(self.canvas, (sw, sh)), (ox, oy))
        pygame.display.flip()

    def step(self) -> None:
        """Run one frame: events, update, draw, present, screen transition."""
        dt = min(self.frame_clock.tick(C.FPS) / 1000.0, 0.1)
        for raw in pygame.event.get():
            if raw.type == pygame.QUIT:
                self.running = False
                return
            if self._fade_snapshot is not None and raw.type in (
                    pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                continue                # ignore clicks during the cross-fade
            self.screen.handle_event(self._translate(raw))
            if self._pending is not None:
                break                   # stop routing events to a screen that is leaving

        self.screen.update(dt)
        self._hand_cursor = False
        self.screen.draw(self.canvas)

        if self._fade_snapshot is not None:
            self._fade_t += dt
            progress = self._fade_t / C.SCREEN_FADE_DURATION
            if progress >= 1.0:
                self._fade_snapshot = None
            else:
                self._fade_snapshot.set_alpha(int(255 * (1 - ui.ease_in_out(progress))))
                self.canvas.blit(self._fade_snapshot, (0, 0))

        self._apply_cursor()
        self._present()
        self._apply_pending()

    def run(self) -> None:
        try:
            while self.running:
                self.step()
        finally:
            if self.screen is not None:
                self.screen.on_exit()
            pygame.quit()


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
