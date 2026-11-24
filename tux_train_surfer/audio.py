"""Procedurally synthesised sound effects and music (no audio files needed)."""

from __future__ import annotations

import math
import random
import threading
from array import array

import pygame

SR_DEFAULT = 22050


class Synth:
    def __init__(self, rate: int) -> None:
        self.rate = rate

    def buf(self, seconds: float) -> list[float]:
        return [0.0] * int(self.rate * seconds)

    def tone(self, out, start, dur, f0, f1=None, wave="square", vol=0.3, attack=0.005, release=0.05, duty=0.5):
        r = self.rate
        f1 = f0 if f1 is None else f1
        n = int(dur * r)
        s0 = int(start * r)
        phase = 0.0
        a_n = max(1, int(attack * r))
        r_n = max(1, int(release * r))
        for i in range(n):
            idx = s0 + i
            if idx >= len(out):
                break
            f = f0 + (f1 - f0) * (i / n)
            phase += f / r
            ph = phase % 1.0
            if wave == "square":
                v = 1.0 if ph < duty else -1.0
            elif wave == "tri":
                v = 4 * abs(ph - 0.5) - 1
            elif wave == "saw":
                v = 2 * ph - 1
            else:
                v = math.sin(ph * math.tau)
            env = min(1.0, i / a_n, (n - i) / r_n)
            out[idx] += v * vol * env

    def noise(self, out, start, dur, vol=0.3, decay=8.0, rng=None):
        rng = rng or random.Random(1)
        r = self.rate
        s0 = int(start * r)
        n = int(dur * r)
        last = 0.0
        for i in range(n):
            idx = s0 + i
            if idx >= len(out):
                break
            last = last * 0.6 + rng.uniform(-1, 1) * 0.4
            out[idx] += last * vol * math.exp(-decay * i / r)

    def to_sound(self, samples, channels: int, volume: float = 1.0):
        return pygame.mixer.Sound(buffer=self.to_bytes(samples, channels, volume))

    def to_bytes(self, samples, channels: int, volume: float = 1.0) -> bytes:
        data = array("h")
        for v in samples:
            v = max(-1.0, min(1.0, v * volume))
            iv = int(v * 32000)
            data.append(iv)
            if channels == 2:
                data.append(iv)
        return data.tobytes()


NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def freq(name: str, octave: int) -> float:
    return 440.0 * 2 ** ((NOTE[name] + (octave - 4) * 12 - 9) / 12)


def make_music(syn: Synth, seed: int, tempo: float = 140.0, minor: bool = True) -> list[float]:
    rng = random.Random(seed)
    beat = 60.0 / tempo
    bars = 8
    out = syn.buf(bars * 4 * beat + 0.05)
    roots = [("A", "F", "C", "G"), ("D", "A#", "F", "C"), ("E", "C", "G", "D")][seed % 3]
    scale = [0, 3, 5, 7, 10] if minor else [0, 2, 4, 7, 9]
    for bar in range(bars):
        root = roots[bar % 4]
        rf = freq(root, 2)
        t0 = bar * 4 * beat
        # bass: root on 8ths with octave jumps
        for k in range(8):
            f = rf * (2 if k % 4 == 3 else 1)
            syn.tone(out, t0 + k * beat / 2, beat / 2 * 0.9, f, wave="tri", vol=0.32, release=0.03)
        # drums
        for k in range(4):
            syn.tone(out, t0 + k * beat, 0.12, 140, 45, wave="sine", vol=0.5, release=0.08)
            syn.noise(out, t0 + k * beat + beat / 2, 0.05, vol=0.12, decay=60, rng=rng)
        if bar % 2 == 1:
            syn.noise(out, t0 + 3.5 * beat, 0.15, vol=0.18, decay=20, rng=rng)
    # melody: random walk on the scale, repeated A A' structure
    motif = []
    deg = 2
    for _ in range(16):
        if rng.random() < 0.2:
            motif.append(None)
            continue
        deg = max(0, min(9, deg + rng.choice((-2, -1, -1, 1, 1, 2, 0))))
        motif.append(deg)
    base = freq(roots[0], 4)
    for half in range(4):
        for k, d in enumerate(motif):
            if d is None:
                continue
            if half % 2 == 1 and k >= 12:
                d = max(0, d - 2)
            octave, idx = divmod(d, len(scale))
            f = base * 2 ** ((scale[idx] + 12 * octave) / 12)
            start = half * 8 * beat + k * beat / 2
            syn.tone(out, start, beat / 2 * 0.85, f, wave="square", vol=0.11, duty=0.25, release=0.06)
            syn.tone(out, start, beat / 2 * 0.85, f * 1.005, wave="sine", vol=0.06)
    return out


class Audio:
    def __init__(self, sfx_volume: float = 0.8, music_volume: float = 0.6, enabled: bool = True) -> None:
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.music: dict[str, pygame.mixer.Sound] = {}
        self.sfx_volume = sfx_volume
        self.music_volume = music_volume
        self.music_channel = None
        self.current_music = None
        self.wanted_music = None
        if not enabled:
            return
        try:
            init = pygame.mixer.get_init()
            if not init:
                pygame.mixer.init(SR_DEFAULT, -16, 1, 512)
                init = pygame.mixer.get_init()
            if not init:
                return
            self.rate, _, self.channels = init
            pygame.mixer.set_num_channels(16)
            self.music_channel = pygame.mixer.Channel(15)
            pygame.mixer.set_reserved(1)
            self.syn = Synth(self.rate)
            self._build_sfx()
            self.enabled = True
            threading.Thread(target=self._build_music, daemon=True).start()
        except Exception:
            self.enabled = False

    # ------------------------------------------------------------------ sfx
    def _build_sfx(self) -> None:
        s = self.syn
        defs = {}
        b = s.buf(0.22); s.tone(b, 0, 0.2, 300, 750, "square", 0.25, duty=0.3); defs["jump"] = b
        b = s.buf(0.16); s.tone(b, 0, 0.06, 1320, wave="square", vol=0.18, duty=0.25)
        s.tone(b, 0.06, 0.1, 1760, wave="square", vol=0.18, duty=0.25); defs["fish"] = b
        b = s.buf(0.35); s.tone(b, 0, 0.3, 1200, 2400, "sine", 0.2); s.tone(b, 0.1, 0.25, 1500, 3000, "sine", 0.15); defs["golden"] = b
        b = s.buf(0.6); s.noise(b, 0, 0.6, 0.7, 6); s.tone(b, 0, 0.4, 120, 40, "square", 0.35); defs["crash"] = b
        b = s.buf(0.3); s.noise(b, 0, 0.25, 0.4, 12); s.tone(b, 0, 0.2, 200, 90, "tri", 0.4); defs["stumble"] = b
        b = s.buf(0.5); s.tone(b, 0, 0.45, 1800, 500, "sine", 0.25); s.noise(b, 0, 0.45, 0.1, 3); defs["slip"] = b
        b = s.buf(0.4)
        for i, f in enumerate((523, 659, 784, 1046)):
            s.tone(b, i * 0.07, 0.12, f, wave="square", vol=0.16, duty=0.25)
        defs["powerup"] = b
        b = s.buf(0.12); s.tone(b, 0, 0.1, 500, 300, "tri", 0.3); defs["land"] = b
        b = s.buf(0.12); s.noise(b, 0, 0.1, 0.25, 25); defs["swoosh"] = b
        b = s.buf(0.08); s.tone(b, 0, 0.06, 180, wave="square", vol=0.15); defs["bonk"] = b
        b = s.buf(0.15); s.tone(b, 0, 0.12, 400, 200, "square", 0.15, duty=0.2); defs["duck"] = b
        b = s.buf(0.9)
        s.tone(b, 0, 0.85, 311, wave="saw", vol=0.16, release=0.2); s.tone(b, 0, 0.85, 392, wave="saw", vol=0.14, release=0.2)
        defs["horn"] = b
        b = s.buf(0.4); s.tone(b, 0, 0.35, 900, 300, "square", 0.2, duty=0.4); s.noise(b, 0, 0.2, 0.2, 15); defs["shield_break"] = b
        b = s.buf(0.07); s.tone(b, 0, 0.05, 880, wave="square", vol=0.12, duty=0.3); defs["click"] = b
        b = s.buf(1.2)
        for i, f in enumerate((523, 659, 784, 1046, 784, 1046)):
            s.tone(b, i * 0.12, 0.25 if i < 5 else 0.5, f, wave="square", vol=0.15, duty=0.3)
        defs["complete"] = b
        b = s.buf(1.0)
        for i, f in enumerate((392, 370, 349, 330)):
            s.tone(b, i * 0.18, 0.22 if i < 3 else 0.45, f, wave="square", vol=0.16, duty=0.5)
        defs["caught"] = b
        b = s.buf(0.3)
        for i in range(3):
            s.tone(b, i * 0.09, 0.07, 700, wave="square", vol=0.12)
        defs["count"] = b
        for name, v in defs.items():
            self.sounds[name] = s.to_sound(v, self.channels)
        self._apply_sfx_volume()

    # Synthesising music in pure Python takes a few seconds, so the result is cached on disk.
    CACHE_VERSION = 1

    def _cache_path(self, key: str):
        from .storage import data_dir

        return data_dir() / "cache" / f"music-{key}-{self.rate}-{self.channels}-v{self.CACHE_VERSION}.pcm"

    def _build_music(self) -> None:
        try:
            for key, seed, tempo, minor in (("menu", 2, 112, False), ("game", 7, 142, True)):
                path = self._cache_path(key)
                data = None
                try:
                    data = path.read_bytes()
                except OSError:
                    pass
                if not data:
                    samples = make_music(self.syn, seed, tempo, minor)
                    data = self.syn.to_bytes(samples, self.channels, 0.8)
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    except OSError:
                        pass
                self.music[key] = pygame.mixer.Sound(buffer=data)
            if self.wanted_music:
                self.play_music(self.wanted_music)
        except Exception:
            pass

    def _apply_sfx_volume(self) -> None:
        for snd in self.sounds.values():
            snd.set_volume(self.sfx_volume)

    def set_volumes(self, sfx: float, music: float) -> None:
        self.sfx_volume, self.music_volume = sfx, music
        if not self.enabled:
            return
        self._apply_sfx_volume()
        if self.music_channel:
            self.music_channel.set_volume(music)

    def play(self, name: str) -> None:
        if self.enabled and name in self.sounds and self.sfx_volume > 0:
            self.sounds[name].play()

    def play_music(self, key: str) -> None:
        self.wanted_music = key
        if not self.enabled or key == self.current_music and self.music_channel.get_busy():
            return
        snd = self.music.get(key)
        if snd is None:
            return
        self.current_music = key
        self.music_channel.set_volume(self.music_volume)
        self.music_channel.play(snd, loops=-1, fade_ms=400)

    def stop_music(self) -> None:
        self.wanted_music = None
        self.current_music = None
        if self.enabled and self.music_channel:
            self.music_channel.fadeout(300)
