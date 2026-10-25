"""The music for the craft video: koto over a driving beat in D miyako-bushi
at 96 BPM, with the instruments of docs/play_music.py.

Four bars for the title ("Any harness. Any model."), then six one-bar cuts,
one per AI agent, each landing on a soft hit with its own koto figure over a
full groove; two beats for all six at once, a lift into the panel opening on
beat 31, a drop-out as Minecraft is chosen, the game window on beat 36 (the
climax) and the end card on beat 48. `python3 docs/craft_music.py` writes
/tmp/craft.wav and /tmp/craft-wave.png to check the hits by eye.
"""

import math
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

import play_music
from play_music import SR, bass, chime, click, hz, koto, loudness, seconds, smooth_array, taiko, track, vinyl, whoosh

BPM = 96
BEAT = 60 / BPM
SWING = 0.54
CUTS = [4 + 4 * n for n in range(6)]
GRID = 28
REVEAL = 31
GAME = 36
END = 48


def b(beats):
    return beats * BEAT


def clamp(x, low=0.0, high=1.0):
    return max(low, min(high, x))


def pad(length):
    """The low D drone of the play video, slower to swell, with more body
    from the game window on."""
    t = seconds(length)
    out = sum(
        amp * np.sin(2 * np.pi * hz(midi) * t + 0.3 * np.sin(2 * np.pi * 0.07 * t + midi))
        for midi, amp in ((38, 0.55), (45, 0.35), (50, 0.22), (53, 0.08), (57, 0.1))
    )
    swell = smooth_array(np.clip(t / 2.5, 0, 1))
    lift = 1 + 0.4 * smooth_array(np.clip((t - b(GAME - 1)) / b(1), 0, 1))
    return sosfilt(butter(2, 650, "lowpass", fs=SR, output="sos"), out * swell * lift)


# Each agent's bar gets one of these figures (beats from the cut, MIDI
# notes in D miyako-bushi: D Eb G A Bb), climbing a little cut by cut.
FIGURES = [
    [(0, (62, 69)), (1, (70,)), (1.5, (69,)), (2.5, (67,)), (3, (69,))],
    [(0, (62, 67)), (0.75, (69,)), (1.5, (70,)), (2.5, (74,)), (3.25, (70,))],
    [(0, (63, 70)), (1, (69,)), (1.75, (67,)), (2.5, (62,)), (3, (63,))],
    [(0, (62, 69)), (0.5, (70,)), (1, (74,)), (2, (75,)), (2.75, (74,)), (3.25, (70,))],
    [(0, (67, 74)), (1, (75,)), (1.5, (74,)), (2.5, (70,)), (3, (74,))],
    [(0, (69, 74)), (0.75, (75,)), (1.5, (79,)), (2.25, (81,)), (3, (79,)), (3.5, (75,))],
]

MELODY = [
    # beat, notes, loudness, bend
    # the title: a wide open chord, a few notes and space
    (0, (50, 57), 0.5, 0), (1, (62,), 0.32, 0), (1.75, (63,), 0.28, 0), (2.5, (58,), 0.32, 1), (3.5, (69,), 0.25, 0),
]
for cut, figure in zip(CUTS, FIGURES):
    MELODY += [(cut + at, notes, 0.42 if at == 0 else 0.34, 0) for at, notes in figure]
MELODY += [
    # all six at once: a rising run
    (28, (62,), 0.35, 0), (28.5, (67,), 0.36, 0), (29, (69,), 0.38, 0), (29.5, (70,), 0.4, 0),
    (30, (74,), 0.42, 0), (30.5, (75,), 0.42, 0),
    # the panel opens: a full chord, a short line while Minecraft is found
    (31, (50, 57, 62, 67, 69, 74), 0.72, 0),
    (32, (69,), 0.4, 0), (32.5, (70,), 0.4, 0), (33, (74,), 0.45, 0), (33.75, (75,), 0.38, 0), (34, (74,), 0.42, 1),
    # Enter: a koto pickup over the drop-out
    (35, (62,), 0.32, 0), (35.25, (67,), 0.34, 0), (35.5, (69,), 0.38, 0), (35.75, (70,), 0.4, 0),
    # the game: the fullest chord, then the high line of the play video
    (36, (38, 50, 57, 62, 67, 69, 74, 81), 0.95, 0),
    (37, (81,), 0.55, 0), (37.5, (82,), 0.5, 0), (38, (86,), 0.6, 0), (38, (58,), 0.36, 0), (38.75, (82,), 0.45, 0),
    (39, (81,), 0.5, 0), (39.5, (79,), 0.45, 0), (40, (81,), 0.6, 1), (40, (55,), 0.36, 0), (40.75, (79,), 0.42, 0),
    (41, (75,), 0.45, 0), (41.5, (74,), 0.5, 0), (42, (79,), 0.55, 0), (42, (57,), 0.36, 0), (42.5, (81,), 0.5, 0),
    (42.75, (82,), 0.45, 0), (43, (86,), 0.6, 0), (43.5, (87,), 0.5, 0), (44, (86,), 0.55, 0), (44, (50,), 0.34, 0),
    (44.5, (81,), 0.42, 0), (45, (79,), 0.45, 0), (45.5, (81,), 0.48, 0), (46, (74,), 0.5, 0), (46, (57,), 0.34, 0),
    (47, (69,), 0.4, 0),
    # the end card: a final strum
    (48, (50, 57, 62, 69, 74), 0.72, 0),
]

ROOTS = [38, 34, 43, 33, 38, 36]
BASS = [(cut, root, 1.6, 0.85) for cut, root in zip(CUTS, ROOTS)]
BASS += [(cut + 2, root, 1.4, 0.7) for cut, root in zip(CUTS, ROOTS)]
BASS += [
    (28, 38, 1.8, 0.8), (30, 33, 0.9, 0.7),
    (31, 38, 1.4, 0.9), (32.75, 38, 0.2, 0.5), (33, 34, 1.8, 0.8),
    (36, 38, 1.7, 1.0), (37.75, 38, 0.2, 0.6), (38, 34, 1.8, 0.9), (40, 43, 1.7, 0.9), (41.75, 43, 0.2, 0.6),
    (42, 33, 1.8, 0.9), (44, 38, 1.7, 0.85), (46, 34, 1.8, 0.8),
    (48, 38, 3.0, 0.6),
]

PATTERNS = {
    "hats": {"hat": "5.3.4.3.5.3.4.3."},
    "drive": {"kick": "9.....6.9.......", "snare": "....8.......8..3", "hat": "6.4.6.4.6.4.6.44"},
    "lift": {"kick": "7.7.", "snare": "..46"},
    "full": {"kick": "9......6..7.....", "snare": "....8.......8..2", "hat": "6.3.5.326.3.5.32"},
    "pickup": {"snare": "4567"},
    "big": {"kick": "9.....6...8....4", "snare": "....9.....2.9..3", "hat": "7.426.4.7.426.43"},
}

DRUMS = [
    # from beat, to beat, pattern, level
    (2, 4, "hats", 0.45),
    (4, 28, "drive", 0.8),  # the agents, one bar each
    (28, 31, "lift", 0.6),  # all six at once, then Ctrl+Space
    (31, 34.5, "full", 0.85),  # the panel
    # 34.5-35: drop-out as Minecraft is chosen
    (35, 36, "pickup", 0.7),
    (36, 48, "big", 1.0),  # the game; stops on the end card
]

HITS = [(cut, 0.4) for cut in CUTS[1:]] + [(REVEAL, 0.65), (GAME, 1.0)]

WHOOSHES = [
    # seconds, length, peak, gain, pan
    *[(b(cut) - 0.22, 0.5, 0.2, 0.06, (-0.3, 0.3)[n % 2]) for n, cut in enumerate(CUTS[1:])],
    (b(GRID) - 0.3, 0.8, 0.3, 0.1, 0.0),
    (b(REVEAL) - 0.3, 0.8, 0.3, 0.1, 0.25),
    (b(GAME) - 0.35, 1.0, 0.35, 0.2, -0.2),
]


def drum_hits():
    """DRUMS expanded to (beat, sound, velocity), with the swing applied."""
    hits = []
    for start, stop, name, level in DRUMS:
        pattern = PATTERNS[name]
        steps = max(len(row) for row in pattern.values())
        bar = 0
        while start + bar * steps / 4 < stop - 1e-9:
            for sound, row in pattern.items():
                for step, mark in enumerate(row):
                    beat = start + (bar * steps + step) / 4
                    if mark == "." or beat >= stop - 1e-9:
                        continue
                    hits.append((beat + (step % 2) * (SWING - 0.5) * 0.5, sound, level * int(mark) / 9))
            bar += 1
    return sorted(hits)


def write_music(path, length, end, keycast_times, click_times, song=None):
    """Mix the tune (or `song` = (mp3, hit second, game second)) into a
    48 kHz stereo wav at -16 LUFS; returns the mix."""
    n = int(length * SR)
    dry, send, drums = np.zeros((n, 2)), np.zeros((n, 2)), np.zeros((n, 2))

    def place(sound, at, gain, pan=0.0, wet=0.2, bus=None):
        start = int(round(max(0.0, at) * SR))
        if start >= n:
            return
        sound = sound[: n - start]
        for channel, side in ((0, math.cos((pan + 1) * math.pi / 4)), (1, math.sin((pan + 1) * math.pi / 4))):
            (dry if bus is None else bus)[start : start + len(sound), channel] += sound * gain * side
            send[start : start + len(sound), channel] += sound * gain * side * wet

    if song:
        dry[:] += track(*song, length, end)
    else:
        for beat, notes, loud, bend in MELODY:
            for k, midi in enumerate(notes):
                strum = 0.04 * k if len(notes) > 2 else 0
                place(koto(midi, 4.5 if b(beat) >= end else 3.2, bend), b(beat) + strum, 0.32 * loud,
                      pan=clamp((midi - 62) / 30, -0.4, 0.4), wet=0.35)
        for beat, midi, beats, loud in BASS:
            place(bass(midi, b(beats)), b(beat), 0.2 * loud, wet=0.05)
        feel = np.random.default_rng(5)
        for beat, name, velocity in drum_hits():
            sound, gain, pan = play_music.DRUM_SOUNDS[name]
            place(sound(), b(beat) + feel.normal(0, 0.003), gain * velocity * feel.uniform(0.88, 1.08),
                  pan=pan, wet=0.08, bus=drums)
        drums = sosfilt(butter(2, 6500, "lowpass", fs=SR, output="sos"), drums, axis=0)
        dry += np.tanh(1.6 * drums) / 1.6
        for beat, loud in HITS:
            place(taiko(big=loud >= 1), b(beat), 0.5 * loud, wet=0.15)
        place(pad(length), 0, 0.06, wet=0.35)
        place(vinyl(length, 1), 0, 0.012, pan=-0.5, wet=0.0)
        place(vinyl(length, 2), 0, 0.012, pan=0.5, wet=0.0)
        place(chime(86), end + 0.05, 0.2, pan=0.2, wet=0.4)
        place(chime(93), end + 0.4, 0.12, pan=-0.2, wet=0.4)
        for at, size, peak, gain, pan in WHOOSHES:
            place(whoosh(size, peak), at, gain, pan=pan, wet=0.15)
        place(whoosh(0.8, 0.3), end - 0.3, 0.1, pan=-0.1, wet=0.15)
    for at in keycast_times:
        place(click(True), at, 0.2, wet=0.06)
    for at in click_times:
        place(click(False), at, 0.14, pan=0.2, wet=0.06)

    t = np.arange(int(3.0 * SR)) / SR
    rooms = []
    for seed in (1, 2):
        room = sosfilt(butter(2, 4000, "lowpass", fs=SR, output="sos"), np.random.default_rng(seed).standard_normal(len(t)))
        room *= np.exp(-t / 0.4) * np.clip(t / 0.015, 0, 1)
        rooms.append(room / np.sqrt(np.sum(room**2)))
    mix = dry + 0.9 * np.stack([fftconvolve(send[:, c], rooms[c])[:n] for c in (0, 1)], axis=1)
    mix = sosfilt(butter(2, 30, "highpass", fs=SR, output="sos"), mix, axis=0)
    t = np.arange(n) / SR
    mix *= (np.clip(t / 0.02, 0, 1) * np.clip((length - t) / max(0.6, length - end - 0.6), 0, 1))[:, None]

    raw, gain = mix, 1.0
    for _ in range(3):
        mix = raw * gain
        if np.max(np.abs(mix)) > 0.89:
            mix = 0.89 * np.tanh(mix / 0.89)
        wavfile.write(path, SR, mix.astype(np.float32))
        gain *= 10 ** ((-16 - loudness(path)) / 20)
    mix = raw * gain
    if np.max(np.abs(mix)) > 0.89:
        mix = 0.89 * np.tanh(mix / 0.89)
    wavfile.write(path, SR, (mix * 32767).astype(np.int16))
    return mix


SECTIONS = [(0, 4, "title"), (4, 28, "agents"), (28, 31, "all six"), (31, 34.5, "panel"),
            (34.5, 35, "drop-out"), (36, 47.5, "game"), (48, 50, "end card")]


def levels(mix):
    """RMS level in dBFS of each story section."""
    out = []
    for start, stop, name in SECTIONS:
        part = mix[int(b(start) * SR) : int(b(stop) * SR)]
        out.append((name, 20 * math.log10(np.sqrt(np.mean(part**2)) + 1e-9)))
    return out


if __name__ == "__main__":
    length, end = b(END) + 2.65, b(END)
    mix = write_music("/tmp/craft.wav", length, end, [], [])
    play_music.BEAT, play_music.HITS, play_music.DRUMS = BEAT, HITS, DRUMS
    play_music.draw_wave(mix, "/tmp/craft-wave.png", length, end)
    print(f"peak {np.max(np.abs(mix)):.3f}, loudness {loudness('/tmp/craft.wav'):.2f} LUFS")
    print("levels", ", ".join(f"{name} {db:.1f} dB" for name, db in levels(mix)))
    sys.exit(0)
