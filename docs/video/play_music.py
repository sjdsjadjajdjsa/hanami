"""The music for the play video: a lo-fi koto tune in D miyako-bushi at 84 BPM.

A night desktop, someone types a sentence to an AI, the AI writes files, the
launcher panel opens in autumn colours (beat 15.5), a game is chosen and Enter
pressed, the game window opens on beat 23 (the climax), and the end card
lands on beat 32. Under the koto: soft hand-made lo-fi drums (kick, dusty
snare, closed hats, a little swing, a tape-ish drum bus) and a round bass.
`python3 docs/play_music.py` writes /tmp/play.wav and /tmp/play-wave.png to
check the hits by eye.
"""

import json
import math
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, istft, sosfilt, stft

SR = 48000
BPM = 84
BEAT = 60 / BPM
SWING = 0.56  # where the off 16th sits inside its pair of 16ths (0.5 = straight)
RNG = np.random.default_rng(11)


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


def taiko(big=False):
    t = seconds(1.8 if big else 1.4)
    low = 46 if big else 52
    phase = 2 * np.pi * np.cumsum(low + 70 * np.exp(-t / 0.05)) / SR
    skin = sosfilt(butter(2, [150, 900], "bandpass", fs=SR, output="sos"), RNG.standard_normal(len(t)))
    return np.sin(phase) * np.exp(-t / (0.42 if big else 0.32)) + 0.35 * skin * np.exp(-t / 0.02)


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


def kick():
    """A soft kick: a sine dropping from ~130 Hz to 50 Hz, about 70 ms long."""
    t = seconds(0.3)
    phase = 2 * np.pi * np.cumsum(50 + 80 * np.exp(-t / 0.022)) / SR
    body = np.sin(phase) * np.exp(-t / 0.07) * np.clip((0.3 - t) / 0.05, 0, 1)
    tap = sosfilt(butter(2, 3000, "lowpass", fs=SR, output="sos"), RNG.standard_normal(len(t))) * np.exp(-t / 0.002)
    return (body + 0.12 * tap) * np.clip(t / 0.001, 0, 1)


def snare():
    """A dusty snare/rim: band-passed noise, a short body tone and a rim tick."""
    t = seconds(0.3)
    noise = sosfilt(butter(2, [900, 5000], "bandpass", fs=SR, output="sos"), RNG.standard_normal(len(t)))
    body = np.sin(2 * np.pi * 190 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)
    rim = np.sin(2 * np.pi * 1700 * t) * np.exp(-t / 0.005)
    out = 0.55 * noise * np.exp(-t / 0.065) + 0.35 * body * np.exp(-t / 0.035) + 0.25 * rim
    return sosfilt(butter(2, 5500, "lowpass", fs=SR, output="sos"), out) * np.clip(t / 0.001, 0, 1)


def hat():
    """A closed hat: short high-passed noise."""
    t = seconds(0.09)
    noise = sosfilt(butter(4, 7000, "highpass", fs=SR, output="sos"), RNG.standard_normal(len(t)))
    return noise * np.exp(-t / 0.016) * np.clip(t / 0.0005, 0, 1)


DRUM_SOUNDS = {"kick": (kick, 0.75, 0.0), "snare": (snare, 0.5, -0.08), "hat": (hat, 0.2, 0.3)}  # sound, gain, pan


def bass(midi, length):
    """A round bass note: sine with a little 2nd and 3rd, softly saturated."""
    t = seconds(length + 0.2)
    f0 = hz(midi)
    tone = np.sin(2 * np.pi * f0 * t) + 0.3 * np.sin(4 * np.pi * f0 * t + 0.5) + 0.1 * np.sin(6 * np.pi * f0 * t)
    tone = np.tanh(1.4 * tone) / np.tanh(1.4)
    env = np.clip(t / 0.008, 0, 1) * np.exp(-t / 1.8) * np.clip(1 - (t - length) / 0.15, 0, 1)
    return sosfilt(butter(2, 700, "lowpass", fs=SR, output="sos"), tone * env)


def vinyl(length, seed):
    """Vinyl-ish air: faint band-passed hiss and sparse soft crackle."""
    rng = np.random.default_rng(seed)
    n = int(length * SR)
    hiss = sosfilt(butter(2, [400, 6000], "bandpass", fs=SR, output="sos"), rng.standard_normal(n))
    pops = np.zeros(n)
    count = rng.poisson(6 * length)
    pops[rng.integers(0, n, count)] = rng.exponential(1, count) * rng.choice([-1, 1], count)
    crackle = sosfilt(butter(2, [1500, 7000], "bandpass", fs=SR, output="sos"), pops)
    return 0.05 * hiss / np.std(hiss) + crackle / np.max(np.abs(crackle))


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
    # night: a wide quiet desktop, the koto alone, a few notes and space
    (0, (50, 57), 0.45, 0), (1.5, (62,), 0.3, 0), (2.5, (63,), 0.26, 0), (3, (58,), 0.3, 1),
    # someone types a sentence: soft notes between the first hats
    (4.5, (62,), 0.32, 0), (5.5, (69,), 0.22, 0), (6.5, (67,), 0.3, 0), (7.25, (70,), 0.2, 0),
    # the AI writes files: a light ticking figure over the half-time beat
    (8, (50,), 0.3, 0), (8, (74,), 0.18, 0), (9.5, (70,), 0.15, 0), (10, (69,), 0.16, 0), (11, (67,), 0.15, 0),
    (12, (58,), 0.26, 0), (12, (74,), 0.17, 0), (13, (75,), 0.15, 0), (13.5, (74,), 0.14, 0), (14, (70,), 0.15, 0),
    (14.75, (69,), 0.15, 0),
    # the launcher opens in autumn colours: a full chord, then a melody over the full-time groove
    (15.5, (50, 57, 62, 67, 69, 74), 0.72, 0),
    (16.5, (69,), 0.4, 0), (17, (70,), 0.4, 0), (17.5, (74,), 0.45, 0), (18.25, (75,), 0.38, 0), (18.5, (74,), 0.42, 0),
    (19, (70,), 0.4, 0), (19.5, (67,), 0.42, 0), (19.5, (55,), 0.3, 0), (20, (69,), 0.45, 0), (20.75, (70,), 0.38, 0),
    (21, (69,), 0.42, 1),
    # a game is chosen: the drums drop out, a short koto pickup (Enter on 22)
    (22, (62,), 0.32, 0), (22.25, (67,), 0.34, 0), (22.5, (69,), 0.38, 0), (22.75, (70,), 0.4, 0),
    # the game opens: the fullest chord, then the most melodic line, high
    (23, (38, 50, 57, 62, 67, 69, 74, 81), 0.95, 0),
    (24, (81,), 0.55, 0), (24.5, (82,), 0.5, 0), (25, (86,), 0.6, 0), (25, (58,), 0.36, 0), (25.75, (82,), 0.45, 0),
    (26, (81,), 0.5, 0), (26.5, (79,), 0.45, 0), (27, (81,), 0.55, 1), (27, (55,), 0.36, 0), (27.75, (79,), 0.42, 0),
    (28, (75,), 0.45, 0), (28.5, (74,), 0.5, 0), (29, (79,), 0.55, 0), (29, (57,), 0.36, 0), (29.5, (81,), 0.5, 0),
    (29.75, (82,), 0.45, 0), (30, (86,), 0.6, 0), (30.5, (87,), 0.5, 0), (31, (86,), 0.55, 0), (31, (50,), 0.34, 0),
    (31.5, (81,), 0.42, 0),
    # the end card: a final strum, quieter than the climax
    (32, (50, 57, 62, 69, 74), 0.72, 0),
]

BASS = [
    # beat, MIDI root, length in beats, loudness
    (8, 38, 3.0, 0.6), (11.5, 38, 0.4, 0.4), (12, 34, 2.4, 0.6), (14.5, 33, 0.9, 0.5),
    (15.5, 38, 1.4, 0.9), (17.25, 38, 0.2, 0.5), (17.5, 34, 1.8, 0.8), (19.5, 43, 0.9, 0.8), (20.5, 33, 0.9, 0.8),
    (23, 38, 1.7, 1.0), (24.75, 38, 0.2, 0.6), (25, 34, 1.8, 0.9), (27, 43, 1.7, 0.9), (28.75, 43, 0.2, 0.6),
    (29, 33, 1.8, 0.9), (31, 38, 0.9, 0.85),
    (32, 38, 3.0, 0.6),
]

PATTERNS = {
    # one bar per pattern, a character per 16th: '.' rest, '1'-'9' velocity; odd 16ths are swung
    "hats": {"hat": "5.3.4.3.5.3.4.3."},
    "half": {"kick": "9.........6.....", "snare": "........7.......", "hat": "6.3.5.3.6.3.5.33"},
    "lift": {"kick": "7...", "snare": "..46", "hat": "4.3."},
    "full": {"kick": "9......6..7.....", "snare": "....8.......8..2", "hat": "6.3.5.326.3.5.32"},
    "pickup": {"snare": "47"},
    "big": {"kick": "9.....6...8....4", "snare": "....9.....2.9..3", "hat": "7.426.4.7.426.43"},
}

DRUMS = [
    # from beat, to beat, pattern, level
    (4.5, 8, "hats", 0.45),  # typing: very soft hats only
    (8, 14.5, "half", 0.6),  # the AI writes files: half-time, light
    (14.5, 15.5, "lift", 0.6),
    (15.5, 21.5, "full", 0.85),  # the autumn launcher: full time
    # 21.5-22.5: drop-out as a game is chosen
    (22.5, 23, "pickup", 0.7),
    (23, 32, "big", 1.0),  # the game window: the full groove; stops on the end card
]

HITS = [(15.5, 0.65), (23, 1.0)]

WHOOSHES = [
    # seconds, length, peak, gain, pan
    (b(15.5) - 0.3, 0.8, 0.3, 0.1, 0.25),
    (b(23) - 0.35, 1.0, 0.35, 0.2, -0.2),
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
                strum = 0.045 * k if len(notes) > 2 else 0
                place(koto(midi, 4.5 if b(beat) >= end else 3.6, bend), b(beat) + strum, 0.32 * loud,
                      pan=clamp((midi - 62) / 30, -0.4, 0.4), wet=0.35)
        for beat, midi, beats, loud in BASS:
            place(bass(midi, b(beats)), b(beat), 0.2 * loud, wet=0.05)
        feel = np.random.default_rng(5)
        for beat, name, velocity in drum_hits():
            sound, gain, pan = DRUM_SOUNDS[name]
            place(sound(), b(beat) + feel.normal(0, 0.003), gain * velocity * feel.uniform(0.88, 1.08),
                  pan=pan, wet=0.08, bus=drums)
        # the drum bus: a gentle low-pass and a little tape saturation
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
    ends = np.clip(t / 0.02, 0, 1) * np.clip((length - t) / max(0.6, length - end - 0.6), 0, 1)
    mix *= ends[:, None]

    raw, gain = mix, 1.0
    for _ in range(3):  # the limiter takes a little loudness off the peaks, so measure again after it
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


SECTIONS = [(0, 4, "night"), (4.5, 8, "typing"), (8, 14.5, "AI writes"), (15.5, 21.5, "launcher"),
            (21.5, 22.5, "drop-out"), (23, 31.5, "game"), (32, 34, "end card")]


def levels(mix):
    """RMS level in dBFS of each story section."""
    out = []
    for start, stop, name in SECTIONS:
        part = mix[int(b(start) * SR) : int(b(stop) * SR)]
        out.append((name, 20 * math.log10(np.sqrt(np.mean(part**2)) + 1e-9)))
    return out


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
    for start, stop, name, _ in DRUMS:
        ax.axvspan(b(start), b(stop), color="#f0c890", alpha=0.25, lw=0, zorder=0)
    ax.fill_between(x, -peaks, peaks, color="#2a7f62", lw=0)
    for at, label, colour in marks:
        ax.axvline(at, color=colour, lw=1.5)
        ax.text(at + 0.05, 0.95, label, color=colour, va="top")
    ax.set_xlim(0, length)
    ax.set_ylim(-1, 1)
    ax.set_xticks([b(beat) for beat in beats[::4]], [f"{beat:g}" for beat in beats[::4]])
    ax.set_xlabel("beat (drum sections shaded)")
    fig.tight_layout()
    fig.savefig(path)


if __name__ == "__main__":
    length, end = b(32) + 2.65, b(32)
    mix = write_music("/tmp/play.wav", length, end, [], [])
    draw_wave(mix, "/tmp/play-wave.png", length, end)
    print(f"peak {np.max(np.abs(mix)):.3f}, loudness {loudness('/tmp/play.wav'):.2f} LUFS")
    print("hits at", ", ".join(f"beat {beat:g} = {b(beat):.3f} s" for beat, _ in HITS))
    print("levels", ", ".join(f"{name} {db:.1f} dB" for name, db in levels(mix)))
    sys.exit(0)
