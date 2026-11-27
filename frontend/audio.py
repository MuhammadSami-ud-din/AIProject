"""Procedural audio engine for Arena-AI.

Every sound effect and music loop is synthesised at start-up with numpy
(no audio files). Combat sounds are layered the way modern fighting games do:

  impact = noise transient (crack) + pitched body (punch) + low thump (weight)
  swing  = band-passed noise sweep (whoosh) + faint pitched air tone
  block  = muted thud + short metallic ring
  parry  = bright two-partial "ting" with a shimmering tail
  KO     = deep boom + filtered crash + falling tone + echo taps

Public API (all optional `pan` is -1.0 left .. +1.0 right):
  audio.play_sfx(name)                  any named sound (legacy names kept)
  audio.play_music(name) / stop_music() 'music_menu', 'music_fight'
  audio.play_swing(strength=0.5, pan=0) strength 0..1 picks light/medium/heavy
  audio.play_hit(strength=0.5, pan=0, counter=False)
  audio.play_block(pan=0)    audio.play_parry(pan=0)    audio.play_ko(pan=0)
  audio.play_special(pan=0)  audio.play_super(pan=0)    audio.play_throw(pan=0)
  audio.play_jump(pan=0)     audio.play_land(pan=0)     audio.play_dash(pan=0)
  audio.update_volume(master=, sfx=, music=, muted=)
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Sequence

import numpy as np
import pygame



class AudioManager:
    """Singleton managing synthesized sound effects and looping music."""

    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate
        self.enabled = False
        self.channels = 2
        self.master_volume = 1.0
        self.sfx_volume = 0.8
        self.music_volume = 0.6
        self.is_muted = False

        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        self._variants: Dict[str, List[str]] = {}
        self._music_channel: Optional[pygame.mixer.Channel] = None
        self._current_music_name: Optional[str] = None
        self._rng = random.Random(1234)

        self._init_mixer()
        if self.enabled:
            self._synthesize_all()

    def _init_mixer(self) -> None:
        """Safely initialize the mixer without crashing if hardware is absent."""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=2, buffer=512)
            init_res = pygame.mixer.get_init()
            if init_res:
                self.sample_rate = init_res[0]
                self.channels = init_res[2]
                self.enabled = True
                pygame.mixer.set_num_channels(24)
                self._music_channel = pygame.mixer.Channel(0)
                pygame.mixer.set_reserved(1)
        except Exception:
            self.enabled = False

    # ------------------------------------------------------------------
    # DSP helpers (numpy float32 arrays in -1..1)
    # ------------------------------------------------------------------
    def _n(self, dur: float) -> int:
        return max(1, int(self.sample_rate * dur))

    def _t(self, dur: float) -> np.ndarray:
        return np.arange(self._n(dur), dtype=np.float64) / self.sample_rate

    def _noise(self, dur: float, seed: int = 0) -> np.ndarray:
        return np.random.default_rng(seed).uniform(-1.0, 1.0, self._n(dur))

    def _lowpass(self, x: np.ndarray, cutoff: float) -> np.ndarray:
        a = float(np.clip(1.0 - np.exp(-2.0 * np.pi * cutoff / self.sample_rate), 0.0, 1.0))
        out = [0.0] * len(x)
        acc = 0.0
        for i, v in enumerate(x.tolist()):
            acc += a * (v - acc)
            out[i] = acc
        return np.asarray(out)

    def _highpass(self, x: np.ndarray, cutoff: float) -> np.ndarray:
        return x - self._lowpass(x, cutoff)

    def _bandpass(self, x: np.ndarray, lo: float, hi: float) -> np.ndarray:
        return self._lowpass(self._highpass(x, lo), hi)

    def _sweep_bandpass(self, x: np.ndarray, f_start: float, f_end: float, q: float = 1.6) -> np.ndarray:
        """State-variable band-pass whose centre frequency glides f_start -> f_end."""
        n = len(x)
        freqs = np.geomspace(max(20.0, f_start), max(20.0, f_end), n)
        f = 2.0 * np.sin(np.pi * np.minimum(freqs, self.sample_rate / 6.0) / self.sample_rate)
        damp = 1.0 / q
        low = band = 0.0
        out = np.empty(n)
        xs = x.tolist()
        fs = f.tolist()
        for i in range(n):
            low += fs[i] * band
            high = xs[i] - low - damp * band
            band += fs[i] * high
            out[i] = band
        return out

    def _env(self, dur: float, attack: float = 0.002, decay: float = 12.0) -> np.ndarray:
        t = self._t(dur)
        env = np.exp(-decay * t)
        if attack > 0:
            env *= np.minimum(1.0, t / attack)
        return env

    def _osc(self, dur: float, f0: float, f1: Optional[float] = None, wave: str = "sine",
             curve: float = 1.0) -> np.ndarray:
        """Oscillator with an exponential-ish pitch glide f0 -> f1."""
        n = self._n(dur)
        f1 = f0 if f1 is None else f1
        p = np.linspace(0.0, 1.0, n) ** curve
        freq = f0 * (f1 / f0) ** p if f0 > 0 and f1 > 0 else np.linspace(f0, f1, n)
        phase = 2.0 * np.pi * np.cumsum(freq) / self.sample_rate
        if wave == "square":
            return np.sign(np.sin(phase))
        if wave == "triangle":
            return 2.0 / np.pi * np.arcsin(np.sin(phase))
        if wave == "saw":
            return 2.0 * ((phase / (2.0 * np.pi)) % 1.0) - 1.0
        return np.sin(phase)

    @staticmethod
    def _pad(x: np.ndarray, n: int) -> np.ndarray:
        return x if len(x) >= n else np.concatenate([x, np.zeros(n - len(x))])

    def _mix(self, *layers: np.ndarray, offsets: Optional[Sequence[float]] = None) -> np.ndarray:
        offs = [int(o * self.sample_rate) for o in (offsets or [0.0] * len(layers))]
        n = max(len(l) + o for l, o in zip(layers, offs))
        out = np.zeros(n)
        for l, o in zip(layers, offs):
            out[o:o + len(l)] += l
        return out

    def _echo(self, x: np.ndarray, taps: Sequence[tuple]) -> np.ndarray:
        """Cheap room: (delay_s, gain) taps."""
        n = len(x) + int(max(d for d, _ in taps) * self.sample_rate)
        out = self._pad(x.copy(), n)
        for d, g in taps:
            k = int(d * self.sample_rate)
            out[k:k + len(x)] += self._lowpass(x, 3000) * g
        return out

    def _finish(self, x: np.ndarray, gain: float = 1.0, fade: float = 0.004) -> np.ndarray:
        x = np.tanh(x * gain)
        peak = float(np.max(np.abs(x))) or 1.0
        x = x / peak * 0.92
        k = min(len(x), self._n(fade))
        if k > 1:
            x[-k:] *= np.linspace(1.0, 0.0, k)
        return x

    def _create_sound(self, samples) -> Optional[pygame.mixer.Sound]:
        """Convert normalized [-1, 1] samples (list or ndarray) into a pygame Sound."""
        if not self.enabled:
            return None
        arr = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
        pcm = (arr * 32760).astype(np.int16)
        if self.channels == 2:
            pcm = np.repeat(pcm, 2)
        try:
            return pygame.mixer.Sound(buffer=pcm.tobytes())
        except Exception:
            return None

    # Legacy helpers kept for compatibility (return python lists) -------
    def _generate_tone(self, duration: float, freq_start: float, freq_end: Optional[float] = None,
                       wave: str = "sine", attack: float = 0.01, decay: float = 0.05,
                       sustain: float = 0.7, release: float = 0.05, volume: float = 0.8) -> list:
        n = self._n(duration)
        att, dec, rel = (max(1, self._n(v)) for v in (attack, decay, release))
        env = np.full(n, sustain)
        env[:min(att, n)] = np.linspace(0, 1, min(att, n))
        d_end = min(n, att + dec)
        if d_end > att:
            env[att:d_end] = np.linspace(1, sustain, d_end - att)
        r0 = max(0, n - rel)
        env[r0:] *= np.linspace(1, 0, n - r0)
        f_end = freq_start if freq_end is None else freq_end
        osc = self._osc(duration, freq_start, f_end, wave=wave, curve=1.0) if freq_start > 0 else np.zeros(n)
        return (osc[:n] * env * volume).tolist()

    def _generate_noise(self, duration: float, decay_rate: float = 10.0, volume: float = 0.8,
                        filter_freq: float = 1000.0) -> list:
        x = self._lowpass(self._noise(duration, 42), filter_freq) * self._env(duration, 0.0, decay_rate)
        return (x * volume * 2.0).tolist()

    def _mix_tracks(self, *tracks) -> list:
        return np.tanh(self._mix(*[np.asarray(t, dtype=np.float64) for t in tracks])).tolist()

    # ------------------------------------------------------------------
    # Sound design
    # ------------------------------------------------------------------
    def _impact(self, strength: float, seed: int = 0, pitch: float = 1.0) -> np.ndarray:
        """Layered punch: crack transient + pitched body + sub thump (+ crunch when heavy)."""
        s = float(np.clip(strength, 0.0, 1.0))
        dur = 0.16 + 0.22 * s
        crack = self._highpass(self._noise(0.03, seed), 2500) * self._env(0.03, 0.0005, 140 - 60 * s)
        body = self._osc(dur, (520 - 220 * s) * pitch, (170 - 70 * s) * pitch, curve=0.5) \
            * self._env(dur, 0.001, 30 - 14 * s)
        thump = self._osc(dur, 120 - 40 * s, 42, curve=0.4) * self._env(dur, 0.002, 22 - 10 * s)
        crunch = self._bandpass(self._noise(dur, seed + 7), 300, 1800 + 1200 * s) \
            * self._env(dur, 0.001, 26 - 12 * s)
        x = self._mix(crack * (0.9 + 0.4 * s), body * 0.75, thump * (0.6 + 0.7 * s), crunch * (0.25 + 0.6 * s))
        if s > 0.6:
            x = self._echo(x, [(0.045, 0.22), (0.09, 0.1)])
        return self._finish(x, gain=1.6 + s)

    def _swing(self, strength: float, seed: int = 0) -> np.ndarray:
        s = float(np.clip(strength, 0.0, 1.0))
        dur = 0.11 + 0.14 * s
        t = self._t(dur)
        shape = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** (1.6 - 0.6 * s)
        air = self._sweep_bandpass(self._noise(dur, seed), 700 - 300 * s, 3200 - 1400 * s, q=2.2) * shape
        tone = self._osc(dur, 340 - 120 * s, 150 - 60 * s) * shape * 0.12
        return self._finish(self._mix(air * 2.4, tone), gain=1.4)

    def _block(self, seed: int = 3) -> np.ndarray:
        dur = 0.22
        thud = self._osc(dur, 180, 90, curve=0.5) * self._env(dur, 0.001, 38)
        ring = sum(self._osc(dur, f) * self._env(dur, 0.0005, d) * g
                   for f, d, g in ((1310, 26, 0.35), (1960, 32, 0.25), (2870, 40, 0.18), (3720, 55, 0.1)))
        tick = self._highpass(self._noise(0.02, seed), 3500) * self._env(0.02, 0.0003, 220)
        return self._finish(self._mix(thud * 0.9, ring, tick * 0.8), gain=1.5)

    def _parry(self) -> np.ndarray:
        dur = 0.55
        ting = (self._osc(dur, 1760) * 0.5 + self._osc(dur, 2640) * 0.32 + self._osc(dur, 3520) * 0.15) \
            * self._env(dur, 0.001, 7)
        shimmer = self._sweep_bandpass(self._noise(dur, 11), 6000, 2500, q=4.0) * self._env(dur, 0.002, 9) * 0.6
        snap = self._highpass(self._noise(0.03, 12), 2500) * self._env(0.03, 0.0005, 150)
        return self._finish(self._echo(self._mix(ting, shimmer, snap), [(0.07, 0.25), (0.14, 0.12)]), gain=1.3)

    def _ko(self) -> np.ndarray:
        dur = 1.4
        boom = self._osc(dur, 85, 28, curve=0.35) * self._env(dur, 0.003, 3.2)
        crash = self._lowpass(self._noise(dur, 21), 2200) * self._env(dur, 0.001, 4.0)
        fall = self._osc(dur, 420, 70, wave="saw", curve=0.6) * self._env(dur, 0.01, 3.5) * 0.25
        hit = self._impact(1.0, seed=5) * 0.9
        x = self._mix(hit, boom * 1.1, crash * 0.55, self._lowpass(fall, 1500))
        return self._finish(self._echo(x, [(0.11, 0.35), (0.23, 0.2), (0.37, 0.1)]), gain=1.4)

    def _special(self, rise: float = 1.0) -> np.ndarray:
        dur = 0.34
        sweep = self._osc(dur, 220, 880 * rise, wave="saw", curve=0.7)
        sweep = self._lowpass(sweep, 2600) * self._env(dur, 0.01, 6)
        air = self._sweep_bandpass(self._noise(dur, 31), 500, 4000, q=2.0) * self._env(dur, 0.02, 7) * 1.6
        sub = self._osc(dur, 70, 50) * self._env(dur, 0.005, 8) * 0.7
        return self._finish(self._mix(sweep * 0.5, air, sub), gain=1.4)

    def _super(self) -> np.ndarray:
        dur = 0.9
        rise = self._lowpass(self._osc(dur, 110, 1320, wave="saw", curve=1.4), 3000) * self._env(dur, 0.03, 2.5)
        chord = sum(self._osc(dur, f) * self._env(dur, 0.25, 3.0) for f in (220, 277, 330, 440)) * 0.2
        whoosh = self._sweep_bandpass(self._noise(dur, 41), 300, 5000, q=1.5) * self._env(dur, 0.1, 3.0) * 1.4
        boom = self._osc(dur, 60, 35) * self._env(dur, 0.004, 4) * 0.9
        return self._finish(self._echo(self._mix(rise * 0.45, chord, whoosh, boom), [(0.12, 0.25)]), gain=1.3)

    def _ui_tick(self, f: float, dur: float = 0.045, vol: float = 0.5) -> np.ndarray:
        return (self._osc(dur, f) * 0.7 + self._osc(dur, f * 2.01) * 0.2) * self._env(dur, 0.001, 70) * vol

    def _chime(self, notes: Sequence[float], step: float, dur: float, vol: float = 0.5,
               wave: str = "sine", decay: float = 9.0) -> np.ndarray:
        layers = []
        for f in notes:
            tone = self._osc(dur, f, wave=wave) * 0.7 + self._osc(dur, f * 2.0) * 0.18
            layers.append(tone * self._env(dur, 0.003, decay) * vol)
        return self._mix(*layers, offsets=[i * step for i in range(len(notes))])

    def _synthesize_all(self) -> None:
        """Synthesize all game sound effects and music loops at initialization."""
        S = self._create_sound
        # --- UI ---
        self._sounds["menu_hover"] = S(self._finish(self._ui_tick(1450, vol=0.4), gain=1.0) * 0.35)
        self._sounds["menu_select"] = S(self._finish(self._chime([660, 990], 0.05, 0.16, decay=22), gain=1.2) * 0.6)
        self._sounds["menu_back"] = S(self._finish(self._chime([740, 494], 0.045, 0.14, decay=24), gain=1.2) * 0.5)
        err = self._lowpass(self._osc(0.16, 180, 140, wave="square"), 1200) * self._env(0.16, 0.002, 16)
        self._sounds["menu_error"] = S(self._finish(err, gain=1.2) * 0.55)

        # --- Combat: swings / impacts with variants for variety ---
        for name, strength in (("whoosh_light", 0.15), ("whoosh_medium", 0.5), ("whoosh_heavy", 0.95)):
            self._register_variants(name, [self._swing(strength, seed) for seed in (1, 2)])
        for name, strength in (("hit_light", 0.2), ("hit_medium", 0.55), ("hit_heavy", 1.0)):
            self._register_variants(name, [self._impact(strength, seed, pitch)
                                           for seed, pitch in ((1, 1.0), (2, 0.92), (3, 1.07))])
        counter = self._mix(self._impact(0.9, 9), self._chime([1320], 0, 0.25, vol=0.35, decay=12))
        self._sounds["hit_counter"] = S(self._finish(counter, gain=1.2))
        self._sounds["block"] = S(self._block())
        self._sounds["parry"] = S(self._parry())
        self._sounds["special"] = S(self._special())
        self._sounds["super"] = S(self._super())
        self._sounds["ko"] = S(self._ko())
        jump = self._osc(0.12, 240, 520, curve=0.6) * self._env(0.12, 0.004, 22) * 0.4
        jump_air = self._sweep_bandpass(self._noise(0.12, 51), 800, 2400) * self._env(0.12, 0.01, 20)
        self._sounds["jump"] = S(self._finish(self._mix(jump, jump_air), gain=1.2) * 0.6)
        land = self._mix(self._osc(0.12, 110, 45, curve=0.4) * self._env(0.12, 0.001, 30),
                         self._lowpass(self._noise(0.1, 52), 900) * self._env(0.1, 0.001, 40) * 0.8)
        self._sounds["land"] = S(self._finish(land, gain=1.4) * 0.7)
        dash = self._sweep_bandpass(self._noise(0.16, 53), 2400, 600, q=1.8) * self._env(0.16, 0.005, 14)
        self._sounds["dash"] = S(self._finish(dash, gain=2.0) * 0.6)
        grab = self._mix(self._impact(0.45, 61) * 0.6,
                         self._lowpass(self._noise(0.3, 62), 700) * self._env(0.3, 0.01, 9),
                         self._impact(0.9, 63), offsets=[0.0, 0.0, 0.16])
        self._sounds["throw"] = S(self._finish(grab, gain=1.3))

        # --- Round flow & jingles ---
        self._sounds["round_start"] = S(self._finish(self._mix(
            self._chime([587.3], 0, 0.5, vol=0.6, wave="triangle", decay=5),
            self._osc(0.5, 60, 45) * self._env(0.5, 0.002, 7) * 0.5), gain=1.2))
        fight = self._mix(self._chime([440, 554.4, 659.3, 880], 0.09, 0.45, vol=0.4, wave="saw", decay=6),
                          self._impact(0.8, 71) * 0.7, offsets=[0.0, 0.27])
        self._sounds["fight"] = S(self._finish(self._lowpass(fight, 3500), gain=1.3))
        self._sounds["round_win"] = S(self._finish(self._chime([523.3, 659.3, 784.0], 0.1, 0.35, vol=0.5,
                                                               wave="triangle", decay=6), gain=1.2))
        self._sounds["match_win"] = S(self._finish(self._echo(self._chime(
            [523.3, 659.3, 784.0, 1046.5], 0.12, 0.6, vol=0.5, wave="triangle", decay=4),
            [(0.15, 0.25)]), gain=1.2))
        self._sounds["match_lose"] = S(self._finish(self._lowpass(self._chime(
            [440.0, 415.3, 392.0, 329.6], 0.18, 0.55, vol=0.5, wave="saw", decay=4), 1800), gain=1.2))
        self._sounds["coin"] = S(self._finish(self._chime([987.8, 1318.5], 0.05, 0.22, vol=0.5, decay=14), gain=1.1) * 0.7)
        self._sounds["level_up"] = S(self._finish(self._chime([440, 554.4, 659.3, 880], 0.08, 0.4,
                                                              wave="triangle", decay=6), gain=1.2))
        self._sounds["trophy"] = S(self._finish(self._echo(self._chime([523.3, 659.3, 784.0, 1046.5, 1318.5], 0.1, 0.5,
                                                                       wave="triangle", decay=5), [(0.12, 0.3)]), gain=1.2))
        self._sounds["mission_complete"] = S(self._finish(self._chime([659.3, 784.0, 1046.5], 0.08, 0.35,
                                                                      decay=8), gain=1.2))
        self._synthesize_music()

    def _register_variants(self, name: str, sample_sets: Sequence[np.ndarray]) -> None:
        names = []
        for i, samples in enumerate(sample_sets):
            key = name if i == 0 else f"{name}_{i}"
            self._sounds[key] = self._create_sound(samples)
            names.append(key)
        self._variants[name] = names

    def _synthesize_music(self) -> None:
        """Seamless loops: a mellow menu arpeggio over a pad, and a driving fight groove."""
        bpm_step = 0.25
        chords = [(261.6, 329.6, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
        arp, pad = [], []
        for chord in chords:
            pattern = [chord[0], chord[1], chord[2], chord[1] * 2]
            for f in pattern:
                note = self._osc(bpm_step, f, wave="triangle") * self._env(bpm_step, 0.004, 9) * 0.28
                arp.append(note)
            bar = 4 * bpm_step
            pad_tone = sum(self._osc(bar, f * 0.5) for f in chord) / 3.0
            pad.append(self._lowpass(pad_tone, 600) * 0.16)
        menu = np.concatenate(arp)
        menu = menu + self._pad(np.concatenate(pad), len(menu))[:len(menu)]
        self._sounds["music_menu"] = self._create_sound(self._finish(menu, gain=1.0) * 0.6)

        step = 0.1875
        bass_notes = [110.0, 110.0, 130.8, 146.8, 164.8, 146.8, 130.8, 123.5,
                      110.0, 110.0, 164.8, 196.0, 220.0, 196.0, 164.8, 146.8]
        bass, drums = [], []
        for i, f in enumerate(bass_notes):
            b = self._lowpass(self._osc(step, f, wave="saw"), 900) * self._env(step, 0.004, 7) * 0.35
            bass.append(b)
            if i % 4 == 0:
                d = self._osc(step, 110, 40, curve=0.3) * self._env(step, 0.001, 22) * 0.8
            elif i % 4 == 2:
                d = self._bandpass(self._noise(step, 80 + i), 900, 5000) * self._env(step, 0.001, 30) * 0.6
            else:
                d = self._highpass(self._noise(step, 90 + i), 6000) * self._env(step, 0.001, 60) * 0.25
            drums.append(d)
        fight = np.concatenate(bass) + np.concatenate(drums)
        self._sounds["music_fight"] = self._create_sound(self._finish(fight, gain=1.1) * 0.6)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def _sfx_volume(self) -> float:
        return max(0.0, min(1.0, self.master_volume * self.sfx_volume))

    def play_sfx(self, name: str, pan: float = 0.0, volume: float = 1.0) -> None:
        """Play a sound effect scaled by Master and SFX volume (pan -1..1)."""
        if not self.enabled or self.is_muted:
            return
        if name in self._variants:
            name = self._rng.choice(self._variants[name])
        snd = self._sounds.get(name)
        if not snd:
            return
        vol = self._sfx_volume() * max(0.0, min(1.0, volume))
        try:
            channel = snd.play()
            if channel is not None:
                p = max(-1.0, min(1.0, pan))
                channel.set_volume(vol * min(1.0, 1.0 - p), vol * min(1.0, 1.0 + p))
        except Exception:
            pass

    # Convenience API for the fight renderer -----------------------------
    def play_swing(self, strength: float = 0.5, pan: float = 0.0) -> None:
        name = "whoosh_light" if strength < 0.34 else ("whoosh_medium" if strength < 0.7 else "whoosh_heavy")
        self.play_sfx(name, pan)

    def play_hit(self, strength: float = 0.5, pan: float = 0.0, counter: bool = False) -> None:
        if counter:
            self.play_sfx("hit_counter", pan)
            return
        name = "hit_light" if strength < 0.34 else ("hit_medium" if strength < 0.7 else "hit_heavy")
        self.play_sfx(name, pan)

    def play_block(self, pan: float = 0.0) -> None:
        self.play_sfx("block", pan)

    def play_parry(self, pan: float = 0.0) -> None:
        self.play_sfx("parry", pan)

    def play_ko(self, pan: float = 0.0) -> None:
        self.play_sfx("ko", pan)

    def play_special(self, pan: float = 0.0) -> None:
        self.play_sfx("special", pan)

    def play_super(self, pan: float = 0.0) -> None:
        self.play_sfx("super", pan)

    def play_throw(self, pan: float = 0.0) -> None:
        self.play_sfx("throw", pan)

    def play_jump(self, pan: float = 0.0) -> None:
        self.play_sfx("jump", pan)

    def play_land(self, pan: float = 0.0) -> None:
        self.play_sfx("land", pan)

    def play_dash(self, pan: float = 0.0) -> None:
        self.play_sfx("dash", pan)

    def play_music(self, name: str) -> None:
        """Loop a procedural music track on the dedicated music channel."""
        if not self.enabled:
            return
        if self._current_music_name == name and self._music_channel and self._music_channel.get_busy():
            return
        self._current_music_name = name
        snd = self._sounds.get(name)
        if snd and self._music_channel:
            vol = 0.0 if self.is_muted else max(0.0, min(1.0, self.master_volume * self.music_volume))
            self._music_channel.set_volume(vol)
            self._music_channel.play(snd, loops=-1, fade_ms=250)

    def stop_music(self) -> None:
        """Stop background music."""
        if self._music_channel:
            self._music_channel.stop()
        self._current_music_name = None

    def update_volume(
        self,
        master: Optional[float] = None,
        sfx: Optional[float] = None,
        music: Optional[float] = None,
        muted: Optional[bool] = None,
    ) -> None:
        """Update volume levels and refresh active music channel volume."""
        if master is not None:
            self.master_volume = max(0.0, min(1.0, master))
        if sfx is not None:
            self.sfx_volume = max(0.0, min(1.0, sfx))
        if music is not None:
            self.music_volume = max(0.0, min(1.0, music))
        if muted is not None:
            self.is_muted = muted
        if self._music_channel:
            vol = 0.0 if self.is_muted else max(0.0, min(1.0, self.master_volume * self.music_volume))
            self._music_channel.set_volume(vol)

    def export_wavs(self, directory: str) -> List[str]:
        """Write every synthesized sound to <directory>/<name>.wav (for auditioning)."""
        import os
        import wave
        os.makedirs(directory, exist_ok=True)
        paths = []
        for name, snd in self._sounds.items():
            if snd is None:
                continue
            path = os.path.join(directory, f"{name}.wav")
            with wave.open(path, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(snd.get_raw())
            paths.append(path)
        return paths


# Global singleton instance
audio = AudioManager()


def __getattr__(name: str):
    """Delegate module-level attribute lookups to the singleton `audio` instance.

    Lets `from frontend import audio; audio.play_sfx(...)` work as well as
    `from frontend.audio import audio`.
    """
    if hasattr(audio, name):
        return getattr(audio, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
