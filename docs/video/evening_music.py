"""The music for the evening video: a night koto tune in D miyako-bushi at 76 BPM.

A desktop at night, someone types a sentence to an AI, the AI works, the
launcher panel shows a newly found game (beat 15.5), Enter is pressed and the
game window opens on beat 23 (the climax), and the end card lands on beat 32.
`python3 docs/evening_music.py` writes /tmp/evening.wav and
/tmp/evening-wave.png to check the hits by eye.
"""

import json
import math
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, istft, sosfilt, stft

SR = 48000
BPM = 76
BEAT = 60 / BPM
RNG = np.random.default_rng(7)


def b(beats):
    return beats * BEAT


def clamp(x, low=0.0, high=1.0):
    return max(low, min(high, x))


def seconds(length):
    return np.arange(int(length * SR)) / SR


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def smooth_array(x):
    return x * x * (3 - 2 * x)


def koto(midi, length=3.6, bend=0.0):
    """A plucked koto string; `bend` semitones pressed in after the pluck (oshide)."""
    t = seconds(length)
    f0 = hz(midi)
    press = smooth_array(np.clip((t - 0.16) / 0.14, 0, 1))
    phase = 2 * np.pi * np.cumsum(f0 * 2 ** (bend * press / 12)) / SR
    tone, total = np.zeros_like(t), 0.0
    for k in range(1, 16):
        if k * f0 > 14000:
            break
        amp = abs(math.sin(math.pi * k * 0.18)) / k**1.05
        rate = (0.55 + 0.35 * k) * (f0 / 300) ** 0.35
        tone += amp * np.exp(-t * rate) * np.sin(k * phase * (1 + 0.0003 * k * k))
        total += amp
    pluck = sosfilt(butter(2, [1800, 6000], "bandpass", fs=SR, output="sos"), RNG.standard_normal(len(t)))
    tone = tone / total + 0.25 * pluck * np.exp(-t / 0.006)
    return tone * np.clip(t / 0.002, 0, 1)


def taiko():
    t = seconds(1.4)
    phase = 2 * np.pi * np.cumsum(52 + 70 * np.exp(-t / 0.05)) / SR
    skin = sosfilt(butter(2, [150, 900], "bandpass", fs=SR, output="sos"), RNG.standard_normal(len(t)))
    return np.sin(phase) * np.exp(-t / 0.32) + 0.35 * skin * np.exp(-t / 0.02)


def chime(midi):
    t = seconds(4.0)
    f0 = hz(midi)
    out = np.zeros_like(t)
    for ratio, amp, decay in ((1, 1, 3.2), (2.0, 0.25, 1.8), (2.76, 0.45, 2.0), (5.40, 0.22, 0.9), (8.93, 0.1, 0.5)):
        out += amp * np.exp(-t / decay) * np.sin(2 * np.pi * f0 * ratio * t)
    return out * np.clip(t / 0.003, 0, 1) / 2


def whoosh(length=0.9, peak=0.32):
    n = int(length * SR)
    freqs, times, z = stft(RNG.standard_normal(n), SR, nperseg=1024)
    centre = 400 + 2200 * np.sin(np.pi * np.clip(times / length, 0, 1)) ** 1.5
    z *= np.exp(-(np.log2(np.maximum(freqs, 1)[:, None] / centre[None, :]) ** 2) / (2 * 0.7**2))
    sound = istft(z, SR, nperseg=1024)[1][:n]
    t = np.arange(len(sound)) / SR
    sound *= np.where(t < peak, (t / peak) ** 2, np.exp(-(t - peak) / 0.18))
    return sound / np.max(np.abs(sound))


def click(heavy):
    t = seconds(0.08)
    snap = sosfilt(butter(4, 2500, "highpass", fs=SR, output="sos"), RNG.standard_normal(len(t)))
    thock = np.sin(2 * np.pi * (170 if heavy else 260) * t) * np.exp(-t / (0.018 if heavy else 0.01))
    return 0.6 * snap * np.exp(-t / 0.0035) + (0.8 if heavy else 0.4) * thock


def pad(length):
    """A dark, low D drone under the whole piece: slow swell in, a slow
    breathing, and a little more body from the climax (beat 23) on."""
    t = seconds(length)
    out = sum(
        amp * np.sin(2 * np.pi * hz(midi) * t + 0.3 * np.sin(2 * np.pi * 0.07 * t + midi))
        for midi, amp in ((38, 0.55), (45, 0.35), (50, 0.22), (53, 0.08), (57, 0.1))
    )
    swell = smooth_array(np.clip(t / 3.5, 0, 1))
    breath = 1 + 0.12 * np.sin(2 * np.pi * t / (8 * BEAT))
    lift = 1 + 0.35 * smooth_array(np.clip((t - b(22.5)) / b(1.5), 0, 1))
    return sosfilt(butter(2, 650, "lowpass", fs=SR, output="sos"), out * swell * breath * lift)


MELODY = [
    # beat, notes (MIDI, D miyako-bushi: D Eb G A Bb), loudness, bend
    # night: a wide quiet desktop, a few low notes and space
    (0, (38, 50), 0.5, 0), (2, (57,), 0.32, 0), (3, (51,), 0.3, 1),
    # someone types a sentence: a low string, a soft tick between
    (4.5, (50,), 0.36, 0), (5.5, (69,), 0.2, 0), (6.5, (55,), 0.32, 0), (7.5, (70,), 0.2, 0),
    # the AI works: a slow, very light ticking figure over a low string
    (8, (50,), 0.3, 0), (8, (74,), 0.16, 0), (9, (75,), 0.14, 0), (10, (74,), 0.16, 0), (11, (70,), 0.14, 0),
    (12, (45,), 0.28, 0), (12, (74,), 0.16, 0), (13, (75,), 0.14, 0), (14, (74,), 0.15, 0), (14.75, (69,), 0.13, 0),
    # the launcher shows a new game: a warm chord, then a short rise to 20
    (15.5, (50, 55, 62, 67, 70), 0.7, 0),
    (16.5, (62,), 0.38, 0), (17, (63,), 0.38, 0), (17.5, (67,), 0.4, 0), (18, (69,), 0.42, 0),
    (18.5, (70,), 0.42, 0), (19, (74,), 0.48, 0), (19.5, (75,), 0.45, 0), (20, (74,), 0.5, 1),
    # held breath before Enter
    (21, (50,), 0.32, 0), (22, (57,), 0.3, 0),
    # the game opens: the fullest chord, then the melody opens up, high
    (23, (38, 50, 57, 62, 67, 69, 74), 0.95, 0),
    (24, (79,), 0.55, 0), (24.5, (81,), 0.5, 0), (25, (82,), 0.6, 0), (25, (50,), 0.38, 0), (25.5, (81,), 0.5, 0),
    (26, (79,), 0.52, 0), (26.5, (75,), 0.45, 0), (27, (74,), 0.55, 1), (27, (55,), 0.38, 0), (27.5, (74,), 0.45, 0),
    (28, (79,), 0.52, 0), (28.5, (81,), 0.52, 0), (29, (86,), 0.6, 0), (29, (57,), 0.38, 0), (29.5, (87,), 0.5, 0),
    (30, (86,), 0.52, 0), (30.5, (82,), 0.48, 0), (31, (81,), 0.55, 1), (31, (50,), 0.36, 0), (31.5, (79,), 0.42, 0),
    # the end card: a final strum, quieter than the climax
    (32, (50, 57, 62, 69, 74), 0.75, 0),
]

HITS = [(15.5, 0.6), (23, 1.0)]

WHOOSHES = [
    # seconds, length, peak, gain, pan
    (b(15.5) - 0.3, 0.8, 0.3, 0.1, 0.25),
    (b(23) - 0.35, 1.0, 0.35, 0.2, -0.2),
]


def loudness(path):
    report = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "loudnorm=I=-16:TP=-1.5:print_format=json", "-f", "null", "-"],
        capture_output=True,
        text=True,
    ).stderr
    start = report.rindex("{")
    data = json.loads(report[start : report.index("}", start) + 1])
    return float(data["input_i"])


def track(music, hit, reveal, length, end):
    """`length` seconds of `music`, starting so its `hit` lands at `reveal`;
    a quick fade in, and out after the end card."""
    n = int(length * SR)
    start = hit - reveal
    trim = f"atrim=start={max(0.0, start):.5f}:duration={length:.5f},asetpts=PTS-STARTPTS"
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(music), "-af", trim, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
        capture_output=True, check=True,
    ).stdout
    audio = np.concatenate([np.zeros((round(max(0.0, -start) * SR), 2)), np.frombuffer(raw, np.float32).reshape(-1, 2)])
    audio = np.pad(audio, ((0, max(0, n - len(audio))), (0, 0)))[:n]
    t = np.arange(n) / SR
    return audio * (np.clip(t / 0.25, 0, 1) * np.clip((length - t) / max(0.6, length - end - 0.6), 0, 1))[:, None]


def write_music(path, length, end, keycast_times, click_times, song=None):
    """Mix the tune (or `song` = (mp3, hit second, reveal second)) into a
    48 kHz stereo wav at -16 LUFS; returns the mix."""
    n = int(length * SR)
    dry, send = np.zeros((n, 2)), np.zeros((n, 2))

    def place(sound, at, gain, pan=0.0, wet=0.2):
        start = int(round(at * SR))
        if start >= n:
            return
        sound = sound[: n - start]
        for channel, side in ((0, math.cos((pan + 1) * math.pi / 4)), (1, math.sin((pan + 1) * math.pi / 4))):
            dry[start : start + len(sound), channel] += sound * gain * side
            send[start : start + len(sound), channel] += sound * gain * side * wet

    if song:
        dry[:] += track(*song, length, end)
    else:
        for beat, notes, loud, bend in MELODY:
            for k, midi in enumerate(notes):
                strum = 0.045 * k if len(notes) > 2 else 0
                place(koto(midi, 4.5 if b(beat) >= end else 3.6, bend), b(beat) + strum, 0.32 * loud,
                      pan=clamp((midi - 62) / 30, -0.4, 0.4), wet=0.35)
        for beat, loud in HITS:
            place(taiko(), b(beat), 0.5 * loud, wet=0.15)
        place(pad(length), 0, 0.08, wet=0.35)
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
    ends = np.clip(t / 0.02, 0, 1) * np.clip((length - t) / max(0.6, length - end - 0.6), 0, 1)
    mix *= ends[:, None]

    wavfile.write(path, SR, mix.astype(np.float32))
    mix *= 10 ** ((-16 - loudness(path)) / 20)
    if np.max(np.abs(mix)) > 0.89:
        mix = 0.89 * np.tanh(mix / 0.89)
    wavfile.write(path, SR, (mix * 32767).astype(np.int16))
    return mix


def draw_wave(mix, path, length, end):
    """A png of the mix with the beat grid, the hits and the end card marked."""
    width, height = 2400, 600
    columns = len(mix) // width
    peaks = np.abs(mix[: columns * width].mean(axis=1)).reshape(width, columns).max(axis=1)
    beats = np.arange(0, length / BEAT, 1.0)
    marks = [(b(beat), f"hit {beat:g}", "#d04040") for beat, _ in HITS] + [(end, "end", "#4060d0")]
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        for beat in beats:
            x = int(b(beat) / length * width)
            draw.line([(x, 0), (x, height)], fill="#c8c8c8" if beat % 4 else "#808080")
        for x, peak in enumerate(peaks):
            draw.line([(x, height / 2 * (1 - peak)), (x, height / 2 * (1 + peak))], fill="#2a7f62")
        for at, label, colour in marks:
            x = int(at / length * width)
            draw.line([(x, 0), (x, height)], fill=colour, width=2)
            draw.text((x + 3, 4), label, fill=colour)
        image.save(path)
        return
    x = np.arange(width) * length / width
    fig, ax = plt.subplots(figsize=(24, 6), dpi=100)
    for beat in beats:
        ax.axvline(b(beat), color="#808080" if beat % 4 == 0 else "#d0d0d0", lw=1 if beat % 4 == 0 else 0.5, zorder=0)
    ax.fill_between(x, -peaks, peaks, color="#2a7f62", lw=0)
    for at, label, colour in marks:
        ax.axvline(at, color=colour, lw=1.5)
        ax.text(at + 0.05, 0.95, label, color=colour, va="top")
    ax.set_xlim(0, length)
    ax.set_ylim(-1, 1)
    ax.set_xticks([b(beat) for beat in beats[::4]], [f"{beat:g}" for beat in beats[::4]])
    ax.set_xlabel("beat")
    fig.tight_layout()
    fig.savefig(path)


if __name__ == "__main__":
    length, end = b(32) + 2.65, b(32)
    mix = write_music("/tmp/evening.wav", length, end, [], [])
    draw_wave(mix, "/tmp/evening-wave.png", length, end)
    print(f"peak {np.max(np.abs(mix)):.3f}, loudness {loudness('/tmp/evening.wav'):.2f} LUFS")
    print("hits at", ", ".join(f"beat {beat:g} = {b(beat):.3f} s" for beat, _ in HITS))
    sys.exit(0)
