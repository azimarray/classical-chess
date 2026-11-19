"""
sounds.py — Procedurally synthesised chess audio.

Every cue is generated in memory from sine partials and filtered noise using
only the standard library, then handed to pygame.mixer as a raw PCM buffer.
No audio files are shipped or loaded.

The synthesis functions are pure Python (lists of floats in [-1, 1]) and do
not need pygame; only SoundManager touches the mixer, and it degrades to a
silent no-op if no audio device is available.
"""

from __future__ import annotations

import math
import random
from array import array
from typing import Dict, List

SAMPLE_RATE = 44100
SOUND_NAMES = ("move", "capture", "castle", "check", "promote", "game_start", "game_end")
TAU = 2.0 * math.pi


# --------------------------------------------------------------------------
# Synthesis primitives
# --------------------------------------------------------------------------
def _silence(seconds: float, rate: int = SAMPLE_RATE) -> List[float]:
    return [0.0] * int(seconds * rate)


def _mix(dst: List[float], src: List[float], offset_s: float = 0.0,
         gain: float = 1.0, rate: int = SAMPLE_RATE) -> List[float]:
    start = int(offset_s * rate)
    needed = start + len(src)
    if needed > len(dst):
        dst.extend([0.0] * (needed - len(dst)))
    for i, value in enumerate(src):
        dst[start + i] += value * gain
    return dst


def _normalize(samples: List[float], peak: float = 0.85) -> List[float]:
    top = max((abs(s) for s in samples), default=0.0)
    if top <= 1e-9:
        return samples
    k = peak / top
    return [s * k for s in samples]


def _fade_tail(samples: List[float], seconds: float = 0.01,
               rate: int = SAMPLE_RATE) -> List[float]:
    n = min(len(samples), int(seconds * rate))
    for i in range(n):
        samples[-1 - i] *= i / n
    return samples


def wood_knock(body_hz: float, decay: float = 0.035, click: float = 0.9,
               duration: float = 0.16, seed: int = 1,
               rate: int = SAMPLE_RATE) -> List[float]:
    """A piece being set down on a wooden board: a short low-passed noise
    transient ('click') over a fast-decaying inharmonic wooden body."""
    rng = random.Random(seed)
    out: List[float] = []
    lowpass = 0.0
    alpha = 0.35
    n = int(duration * rate)
    for i in range(n):
        t = i / rate
        attack = min(1.0, t / 0.0012)
        body = (math.sin(TAU * body_hz * t) * 0.65
                + math.sin(TAU * body_hz * 2.31 * t) * 0.28 * math.exp(-t / (decay * 0.55))
                + math.sin(TAU * body_hz * 4.07 * t) * 0.12 * math.exp(-t / (decay * 0.3)))
        lowpass += alpha * (rng.uniform(-1.0, 1.0) - lowpass)
        transient = click * lowpass * math.exp(-t / 0.006)
        out.append(attack * (body * math.exp(-t / decay) + transient))
    return _fade_tail(out, rate=rate)


def bell(freq: float, duration: float = 0.3, decay: float = 0.12,
         attack: float = 0.004, rate: int = SAMPLE_RATE) -> List[float]:
    """Soft mallet tone (fundamental + gentle partials)."""
    out: List[float] = []
    n = int(duration * rate)
    for i in range(n):
        t = i / rate
        env = min(1.0, t / attack) * math.exp(-t / decay)
        value = (math.sin(TAU * freq * t)
                 + 0.35 * math.sin(TAU * freq * 2.0 * t) * math.exp(-t / (decay * 0.5))
                 + 0.12 * math.sin(TAU * freq * 3.01 * t) * math.exp(-t / (decay * 0.3)))
        out.append(env * value)
    return _fade_tail(out, rate=rate)


# --------------------------------------------------------------------------
# Cue recipes
# --------------------------------------------------------------------------
def synth_move() -> List[float]:
    return _normalize(_mix(wood_knock(185, 0.032, 0.8, seed=3),
                           wood_knock(92, 0.05, 0.0, seed=4), gain=0.35), 0.7)


def synth_capture() -> List[float]:
    out = wood_knock(240, 0.026, 1.25, 0.12, seed=7)
    _mix(out, wood_knock(330, 0.03, 1.0, 0.16, seed=8), 0.038, 0.9)
    return _normalize(out, 0.85)


def synth_castle() -> List[float]:
    out = wood_knock(180, 0.03, 0.8, seed=11)
    _mix(out, wood_knock(205, 0.03, 0.8, seed=12), 0.11, 0.9)
    return _normalize(out, 0.75)


def synth_check() -> List[float]:
    out = wood_knock(200, 0.03, 0.9, seed=21)
    _mix(out, bell(880, 0.32, 0.11), 0.015, 0.45)
    _mix(out, bell(1318.5, 0.28, 0.08), 0.015, 0.22)
    return _normalize(out, 0.8)


def synth_promote() -> List[float]:
    out = wood_knock(190, 0.03, 0.8, seed=31)
    for idx, freq in enumerate((523.25, 659.25, 783.99, 1046.5)):
        _mix(out, bell(freq, 0.3, 0.1), 0.03 + idx * 0.065, 0.42)
    return _normalize(out, 0.8)


def synth_game_start() -> List[float]:
    out = bell(392.0, 0.45, 0.2, attack=0.012)
    _mix(out, bell(587.33, 0.55, 0.24, attack=0.012), 0.12, 0.9)
    return _normalize(out, 0.6)


def synth_game_end() -> List[float]:
    out: List[float] = []
    for idx, freq in enumerate((659.25, 523.25, 392.0)):
        _mix(out, bell(freq, 0.6, 0.22, attack=0.01), idx * 0.15, 0.8)
    _mix(out, bell(261.63, 0.9, 0.35, attack=0.02), 0.45, 0.6)
    return _normalize(out, 0.65)


RECIPES = {
    "move": synth_move,
    "capture": synth_capture,
    "castle": synth_castle,
    "check": synth_check,
    "promote": synth_promote,
    "game_start": synth_game_start,
    "game_end": synth_game_end,
}


def resample(samples: List[float], src_rate: int, dst_rate: int) -> List[float]:
    """Linear resampling so cues keep their pitch if the device runs at a
    different rate (e.g. 48 kHz)."""
    if src_rate == dst_rate or not samples:
        return samples
    ratio = src_rate / dst_rate
    length = int(len(samples) / ratio)
    out = []
    last = len(samples) - 1
    for i in range(length):
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        nxt = samples[j + 1] if j < last else samples[last]
        out.append(samples[j] * (1 - frac) + nxt * frac)
    return out


def to_pcm(samples: List[float], size: int, channels: int) -> bytes:
    """Encode float samples for the mixer's format (size as reported by
    pygame.mixer.get_init(): -16, 16, -8, 8 or 32 for float)."""
    if size == 32:
        data = array("f", (s for s in samples for _ in range(channels)))
    elif abs(size) == 8:
        if size < 0:
            data = array("b", (int(max(-1, min(1, s)) * 127) for s in samples for _ in range(channels)))
        else:
            data = array("B", (int((max(-1, min(1, s)) + 1) * 127.5) for s in samples for _ in range(channels)))
    elif size > 0:
        data = array("H", (int((max(-1, min(1, s)) + 1) * 32767.5) for s in samples for _ in range(channels)))
    else:
        data = array("h", (int(max(-1, min(1, s)) * 32767) for s in samples for _ in range(channels)))
    return data.tobytes()


# --------------------------------------------------------------------------
# Mixer facade
# --------------------------------------------------------------------------
class SoundManager:
    def __init__(self, volume: float = 0.7) -> None:
        self.muted = False
        self.available = False
        self.volume = volume
        self._sounds: Dict[str, object] = {}
        try:
            import pygame
            self._pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
            init = pygame.mixer.get_init()
            if not init:
                return
            freq, size, channels = init
            for name, recipe in RECIPES.items():
                samples = resample(recipe(), SAMPLE_RATE, freq)
                sound = pygame.mixer.Sound(buffer=to_pcm(samples, size, channels))
                sound.set_volume(volume)
                self._sounds[name] = sound
            pygame.mixer.set_num_channels(16)
            self.available = True
        except Exception:      # no audio device / headless — stay silent
            self.available = False

    def play(self, name: str) -> None:
        if self.muted or not self.available:
            return
        sound = self._sounds.get(name)
        if sound is not None:
            sound.play()

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted and self.available:
            self._pygame.mixer.stop()
        return self.muted

    def set_muted(self, muted: bool) -> None:
        if muted != self.muted:
            self.toggle_mute()
