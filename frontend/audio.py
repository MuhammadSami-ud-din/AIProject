"""Procedural audio engine for Arena-AI.

Generates 100% of sound effects and music via mathematical waveforms
(sine, square, triangle, saw, noise) using Python's standard array module
and pygame.mixer. Zero external audio files required.
"""

import array
import math
import random
from typing import Dict, Optional
import pygame


class AudioManager:
    """Singleton managing synthesized sound effects and looping chiptune music."""

    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate
        self.enabled = False
        self.channels = 2  # default stereo
        self.master_volume = 1.0
        self.sfx_volume = 0.8
        self.music_volume = 0.6
        self.is_muted = False

        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        self._music_channel: Optional[pygame.mixer.Channel] = None
        self._current_music_name: Optional[str] = None

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
                # Reserve channel 0 for music
                pygame.mixer.set_num_channels(16)
                self._music_channel = pygame.mixer.Channel(0)
        except Exception:
            self.enabled = False

    def _create_sound(self, samples: list[float]) -> Optional[pygame.mixer.Sound]:
        """Convert a list of normalized [-1.0, 1.0] samples into a pygame Sound."""
        if not self.enabled:
            return None
        buf = array.array("h")
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            val = int(clamped * 32760)
            buf.append(val)
            if self.channels == 2:
                buf.append(val)
        try:
            return pygame.mixer.Sound(buffer=buf)
        except Exception:
            return None

    # --- Waveform Helpers ---

    def _generate_tone(
        self,
        duration: float,
        freq_start: float,
        freq_end: Optional[float] = None,
        wave: str = "sine",
        attack: float = 0.01,
        decay: float = 0.05,
        sustain: float = 0.7,
        release: float = 0.05,
        volume: float = 0.8,
    ) -> list[float]:
        """Generate an envelope-shaped tone with optional frequency sweep."""
        if freq_end is None:
            freq_end = freq_start
        total_samples = max(1, int(self.sample_rate * duration))
        samples: list[float] = []

        phase = 0.0
        att_samples = int(self.sample_rate * attack)
        dec_samples = int(self.sample_rate * decay)
        rel_samples = int(self.sample_rate * release)
        sus_samples = max(0, total_samples - (att_samples + dec_samples + rel_samples))

        for i in range(total_samples):
            # ADSR envelope
            if i < att_samples:
                env = (i / att_samples) if att_samples > 0 else 1.0
            elif i < att_samples + dec_samples:
                progress = (i - att_samples) / dec_samples
                env = 1.0 - progress * (1.0 - sustain)
            elif i < att_samples + dec_samples + sus_samples:
                env = sustain
            else:
                progress = (i - (att_samples + dec_samples + sus_samples)) / max(1, rel_samples)
                env = max(0.0, sustain * (1.0 - progress))

            # Frequency interpolation
            t = i / total_samples
            current_freq = freq_start + t * (freq_end - freq_start)
            phase += 2.0 * math.pi * current_freq / self.sample_rate

            # Waveform
            if wave == "square":
                val = 1.0 if (phase % (2.0 * math.pi)) < math.pi else -1.0
            elif wave == "triangle":
                p = (phase / (2.0 * math.pi)) % 1.0
                val = 4.0 * abs(p - 0.5) - 1.0
            elif wave == "saw":
                p = (phase / (2.0 * math.pi)) % 1.0
                val = 2.0 * p - 1.0
            else:  # sine
                val = math.sin(phase)

            samples.append(val * env * volume)
        return samples

    def _generate_noise(
        self,
        duration: float,
        decay_rate: float = 10.0,
        volume: float = 0.8,
        filter_freq: float = 1000.0,
    ) -> list[float]:
        """Generate filtered white noise burst with exponential decay."""
        total_samples = max(1, int(self.sample_rate * duration))
        samples: list[float] = []
        rng = random.Random(42)  # Deterministic seed for crisp consistency
        last_val = 0.0
        alpha = min(1.0, 2.0 * math.pi * filter_freq / self.sample_rate)

        for i in range(total_samples):
            t = i / self.sample_rate
            env = math.exp(-decay_rate * t)
            raw = rng.uniform(-1.0, 1.0)
            # Low-pass filter
            last_val = last_val + alpha * (raw - last_val)
            samples.append(last_val * env * volume)
        return samples

    def _mix_tracks(self, *tracks: list[float]) -> list[float]:
        """Mix multiple sample tracks together and normalize to avoid clipping."""
        max_len = max(len(t) for t in tracks)
        out = [0.0] * max_len
        for t in tracks:
            for i, s in enumerate(t):
                out[i] += s
        # Soft limiter
        return [math.tanh(s) for s in out]

    # --- Sound Synthesis ---

    def _synthesize_all(self) -> None:
        """Synthesize all game sound effects and music loops at initialization."""
        # Menu sounds
        self._sounds["menu_hover"] = self._create_sound(
            self._generate_tone(0.04, 750, 950, wave="square", attack=0.005, decay=0.03, sustain=0.0, release=0.005, volume=0.3)
        )
        self._sounds["menu_select"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.08, 523.25, 523.25, wave="sine", attack=0.005, decay=0.07, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.05) + self._generate_tone(0.10, 783.99, 783.99, wave="sine", attack=0.005, decay=0.09, sustain=0.0, release=0.01, volume=0.5),
            )
        )
        self._sounds["menu_back"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.06, 659.25, 659.25, wave="sine", attack=0.005, decay=0.05, sustain=0.0, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.04) + self._generate_tone(0.08, 440.00, 440.00, wave="sine", attack=0.005, decay=0.07, sustain=0.0, release=0.01, volume=0.4),
            )
        )
        self._sounds["menu_error"] = self._create_sound(
            self._generate_tone(0.12, 160, 130, wave="saw", attack=0.01, decay=0.10, sustain=0.1, release=0.01, volume=0.5)
        )

        # Combat Whooshes & Impacts
        self._sounds["whoosh_light"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.08, 400, 180, wave="sine", attack=0.01, decay=0.06, sustain=0.1, release=0.01, volume=0.3),
                self._generate_noise(0.07, decay_rate=25.0, volume=0.25, filter_freq=1200),
            )
        )
        self._sounds["whoosh_heavy"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.14, 260, 90, wave="saw", attack=0.02, decay=0.10, sustain=0.1, release=0.02, volume=0.4),
                self._generate_noise(0.12, decay_rate=18.0, volume=0.4, filter_freq=900),
            )
        )
        self._sounds["hit_light"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.10, 320, 80, wave="triangle", attack=0.005, decay=0.08, sustain=0.0, release=0.015, volume=0.6),
                self._generate_noise(0.08, decay_rate=30.0, volume=0.5, filter_freq=1800),
            )
        )
        self._sounds["hit_heavy"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.20, 220, 45, wave="square", attack=0.005, decay=0.18, sustain=0.0, release=0.015, volume=0.7),
                self._generate_noise(0.16, decay_rate=16.0, volume=0.7, filter_freq=1100),
            )
        )
        self._sounds["block"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.10, 880, 700, wave="triangle", attack=0.002, decay=0.09, sustain=0.0, release=0.01, volume=0.5),
                self._generate_noise(0.06, decay_rate=35.0, volume=0.4, filter_freq=3000),
            )
        )
        self._sounds["special"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.22, 280, 880, wave="saw", attack=0.02, decay=0.18, sustain=0.2, release=0.02, volume=0.5),
                self._generate_noise(0.18, decay_rate=15.0, volume=0.35, filter_freq=2200),
            )
        )
        self._sounds["super"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.38, 180, 1100, wave="saw", attack=0.04, decay=0.30, sustain=0.3, release=0.04, volume=0.6),
                self._generate_tone(0.38, 90, 45, wave="sine", attack=0.02, decay=0.32, sustain=0.4, release=0.04, volume=0.6),
                self._generate_noise(0.35, decay_rate=8.0, volume=0.5, filter_freq=1600),
            )
        )
        self._sounds["jump"] = self._create_sound(
            self._generate_tone(0.09, 220, 480, wave="sine", attack=0.01, decay=0.07, sustain=0.0, release=0.01, volume=0.4)
        )
        self._sounds["land"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.08, 140, 50, wave="sine", attack=0.005, decay=0.07, sustain=0.0, release=0.01, volume=0.4),
                self._generate_noise(0.06, decay_rate=40.0, volume=0.3, filter_freq=600),
            )
        )
        self._sounds["dash"] = self._create_sound(
            self._mix_tracks(
                self._generate_noise(0.11, decay_rate=20.0, volume=0.4, filter_freq=1500),
                self._generate_tone(0.10, 350, 150, wave="sine", attack=0.01, decay=0.08, sustain=0.0, release=0.01, volume=0.3),
            )
        )
        self._sounds["throw"] = self._create_sound(
            self._mix_tracks(
                self._generate_noise(0.20, decay_rate=12.0, volume=0.6, filter_freq=1000),
                self._generate_tone(0.20, 240, 60, wave="triangle", attack=0.01, decay=0.18, sustain=0.0, release=0.01, volume=0.6),
            )
        )
        self._sounds["round_start"] = self._create_sound(
            self._generate_tone(0.40, 587.33, 587.33, wave="triangle", attack=0.005, decay=0.38, sustain=0.0, release=0.015, volume=0.5)
        )
        self._sounds["fight"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.12, 440, 440, wave="square", attack=0.01, decay=0.10, sustain=0.1, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.10) + self._generate_tone(0.12, 554.37, 554.37, wave="square", attack=0.01, decay=0.10, sustain=0.1, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.20) + self._generate_tone(0.30, 659.25, 880.00, wave="square", attack=0.01, decay=0.28, sustain=0.2, release=0.01, volume=0.5),
            )
        )
        self._sounds["ko"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.70, 150, 30, wave="saw", attack=0.01, decay=0.65, sustain=0.1, release=0.04, volume=0.7),
                self._generate_noise(0.60, decay_rate=6.0, volume=0.6, filter_freq=800),
            )
        )
        self._sounds["round_win"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.12, 523.25, 523.25, wave="square", attack=0.01, decay=0.10, sustain=0.0, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.11) + self._generate_tone(0.12, 659.25, 659.25, wave="square", attack=0.01, decay=0.10, sustain=0.0, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.22) + self._generate_tone(0.25, 783.99, 783.99, wave="square", attack=0.01, decay=0.23, sustain=0.0, release=0.01, volume=0.45),
            )
        )
        self._sounds["match_win"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.14, 523.25, 523.25, wave="triangle", attack=0.01, decay=0.12, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.12) + self._generate_tone(0.14, 659.25, 659.25, wave="triangle", attack=0.01, decay=0.12, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.24) + self._generate_tone(0.14, 783.99, 783.99, wave="triangle", attack=0.01, decay=0.12, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.36) + self._generate_tone(0.35, 1046.50, 1046.50, wave="triangle", attack=0.01, decay=0.33, sustain=0.1, release=0.01, volume=0.6),
            )
        )
        self._sounds["match_lose"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.18, 440.00, 440.00, wave="saw", attack=0.02, decay=0.15, sustain=0.0, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.16) + self._generate_tone(0.18, 415.30, 415.30, wave="saw", attack=0.02, decay=0.15, sustain=0.0, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.32) + self._generate_tone(0.35, 392.00, 329.63, wave="saw", attack=0.02, decay=0.32, sustain=0.1, release=0.01, volume=0.45),
            )
        )

        # Economy & UI
        self._sounds["coin"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.08, 987.77, 987.77, wave="sine", attack=0.005, decay=0.07, sustain=0.0, release=0.005, volume=0.5),
                [0.0] * int(self.sample_rate * 0.05) + self._generate_tone(0.14, 1318.51, 1318.51, wave="sine", attack=0.005, decay=0.13, sustain=0.0, release=0.005, volume=0.6),
            )
        )
        self._sounds["level_up"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.10, 440.00, 440.00, wave="triangle", attack=0.01, decay=0.08, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.09) + self._generate_tone(0.10, 554.37, 554.37, wave="triangle", attack=0.01, decay=0.08, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.18) + self._generate_tone(0.10, 659.25, 659.25, wave="triangle", attack=0.01, decay=0.08, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.27) + self._generate_tone(0.25, 880.00, 880.00, wave="triangle", attack=0.01, decay=0.23, sustain=0.1, release=0.01, volume=0.6),
            )
        )
        self._sounds["trophy"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.15, 523.25, 523.25, wave="square", attack=0.01, decay=0.13, sustain=0.0, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.12) + self._generate_tone(0.15, 659.25, 659.25, wave="square", attack=0.01, decay=0.13, sustain=0.0, release=0.01, volume=0.4),
                [0.0] * int(self.sample_rate * 0.24) + self._generate_tone(0.35, 783.99, 1046.50, wave="square", attack=0.01, decay=0.33, sustain=0.1, release=0.01, volume=0.5),
            )
        )
        self._sounds["mission_complete"] = self._create_sound(
            self._mix_tracks(
                self._generate_tone(0.10, 659.25, 659.25, wave="sine", attack=0.01, decay=0.08, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.08) + self._generate_tone(0.10, 783.99, 783.99, wave="sine", attack=0.01, decay=0.08, sustain=0.0, release=0.01, volume=0.5),
                [0.0] * int(self.sample_rate * 0.16) + self._generate_tone(0.20, 1046.50, 1046.50, wave="sine", attack=0.01, decay=0.18, sustain=0.0, release=0.01, volume=0.5),
            )
        )

        # Synthesize procedural looping music
        self._synthesize_music()

    def _synthesize_music(self) -> None:
        """Synthesize seamless looping chiptune patterns for menu and combat."""
        # Menu Theme: Chill 8-beat arpeggiated groove (~4.0 seconds loop)
        menu_notes = [
            (261.63, 0.25), (329.63, 0.25), (392.00, 0.25), (523.25, 0.25),
            (220.00, 0.25), (261.63, 0.25), (329.63, 0.25), (440.00, 0.25),
            (174.61, 0.25), (220.00, 0.25), (261.63, 0.25), (349.23, 0.25),
            (196.00, 0.25), (246.94, 0.25), (293.66, 0.25), (392.00, 0.25),
        ]
        menu_samples: list[float] = []
        for freq, dur in menu_notes:
            tone = self._generate_tone(dur, freq, freq, wave="triangle", attack=0.01, decay=dur * 0.85, sustain=0.1, release=0.02, volume=0.25)
            menu_samples.extend(tone)
        self._sounds["music_menu"] = self._create_sound(menu_samples)

        # Fight Theme: Driving 160 BPM combat groove with pulse bass and noise beat (~3.0 seconds loop)
        fight_seq = [
            (110.0, 0.1875, True), (110.0, 0.1875, False), (130.81, 0.1875, True), (146.83, 0.1875, False),
            (164.81, 0.1875, True), (146.83, 0.1875, False), (130.81, 0.1875, True), (123.47, 0.1875, False),
            (110.0, 0.1875, True), (110.0, 0.1875, False), (164.81, 0.1875, True), (196.00, 0.1875, False),
            (220.0, 0.1875, True), (196.00, 0.1875, False), (164.81, 0.1875, True), (146.83, 0.1875, False),
        ]
        bass_track: list[float] = []
        perc_track: list[float] = []
        for freq, dur, has_beat in fight_seq:
            bass_tone = self._generate_tone(dur, freq, freq, wave="saw", attack=0.01, decay=dur * 0.7, sustain=0.15, release=0.02, volume=0.30)
            bass_track.extend(bass_tone)
            if has_beat:
                beat = self._generate_noise(dur, decay_rate=25.0, volume=0.22, filter_freq=1800)
            else:
                beat = [0.0] * int(self.sample_rate * dur)
            perc_track.extend(beat)

        fight_samples = self._mix_tracks(bass_track, perc_track)
        self._sounds["music_fight"] = self._create_sound(fight_samples)

    # --- Playback Controls ---

    def play_sfx(self, name: str) -> None:
        """Play a synthesized sound effect scaled by Master and SFX volume."""
        if not self.enabled or self.is_muted:
            return
        snd = self._sounds.get(name)
        if snd:
            vol = max(0.0, min(1.0, self.master_volume * self.sfx_volume))
            snd.set_volume(vol)
            snd.play()

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
            self._music_channel.play(snd, loops=-1)

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


# Global singleton instance
audio = AudioManager()


def __getattr__(name: str):
    """Delegate module-level attribute lookups to the singleton `audio` instance.

    Prevents AttributeError if a caller does:
        from frontend import audio
        audio.play_sfx(...)
    instead of:
        from frontend.audio import audio
    """
    if hasattr(audio, name):
        return getattr(audio, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

