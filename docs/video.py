"""Makes Hanami's short video: a desktop where someone presses the hotkey and
uses the real panel (drawn off screen by the panel_frames example), with
titles and an original koto piece written here (no samples, nothing
borrowed).

    python3 docs/video.py hanami.mp4
    python3 docs/video.py --tall hanami-tall.mp4

Writes the video (60 fps, 11 seconds) and a thumbnail next to it: 1920 x 1080
for YouTube, or 1080 x 1920 with --tall for Shorts, TikTok and Reels. Needs
Rust, ffmpeg, rsvg-convert, Pillow, NumPy and SciPy, and a minute or two. Frames are kept
in ~/.cache/hanami-video while it runs.
"""

import functools
import io
import json
import math
import multiprocessing
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, istft, sosfilt, stft

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import screenshot  # noqa: E402

FPS = 60
LENGTH = 11.0
FRAMES = round(LENGTH * FPS)
SR = 48000
BEAT = 60 / 90
PANEL_SCALE = 2.0
PW, PH = int(340 * PANEL_SCALE), int(440 * PANEL_SCALE)
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hanami-video"

TEXT = (236, 230, 238)
DIM = (155, 147, 163)
ACCENT = (244, 182, 200)
INK = (23, 20, 29)


def b(beats):
    return beats * BEAT


# The story, on the beat of the music.
KEYS = [("Ctrl", b(0.5)), ("Alt", b(1.0)), ("H", b(1.5))]
REVEAL = b(1.5)
CAPTIONS = [
    (b(2.0), b(5.25), "Every game,\none key away.", "Steam, Epic, GOG, Heroic and more."),
    (b(5.5), b(8.5), "Find any game\nin a keystroke.", "First letters and small typos work too."),
    (b(8.75), b(12.0), "Your list,\nyour way.", "Pin, rename or hide any game."),
]
END = b(12.5)
TYPED = [(b(5.5), "h"), (b(6.0), "hk"), (b(8.0), "h"), (b(8.25), "")]
DOWNS = [b(8.75), b(9.0), b(9.25)]
TAB, ENTER = b(9.75), b(10.75)
CLICKS = [at for at, _ in TYPED] + DOWNS + [TAB, ENTER]


# The desktop the video plays on, in logical pixels, drawn at twice that so
# the camera can move in close. Hanami opens in the middle of the screen
# under the mouse (desktop::centre_on_pointer).
SCREEN_W, SCREEN_H = 1920, 1080
DESK = 2
BAR = 44
PANEL_BOX = ((SCREEN_W - 340) / 2, (SCREEN_H - 440) / 2, 340, 440)
POINTER = (1540, 820)

# Where everything sits, and the camera: (time, centre x, centre y, zoom) on
# the desktop, eased from one to the next. The tall layout keeps the words
# and the panel clear of the buttons and captions Shorts, TikTok and Reels
# draw on top.
LAYOUTS = {
    "wide": dict(
        size=(1920, 1080),
        align="left",
        keys=(960, 900),
        keys_aside=(0, 40),
        camera=[
            (0, 960, 540, 1.0),
            (REVEAL + 0.1, 960, 540, 1.0),
            (REVEAL + 0.9, 790, 540, 1.7),
            (END - 0.2, 780, 540, 1.76),
            (END + 0.8, 960, 540, 1.0),
        ],
        words=(148, 400),
        word_sizes=(72, 32),
        end=[(150, 270), (144, 410), (152, 590), (152, 720)],
        end_sizes=(104, 132, 36, 32),
        thumbnail=(1280, 720),
    ),
    "tall": dict(
        size=(1080, 1920),
        align="center",
        keys=(540, 1390),
        keys_aside=(0, 60),
        camera=[
            (0, 960, 540, 0.5),
            (REVEAL + 0.1, 960, 540, 0.5),
            (REVEAL + 1.0, 960, 480, 2.0),
            (LENGTH, 960, 488, 1.97),
        ],
        words=(540, 330),
        word_sizes=(84, 38),
        end=[(540, 200), (540, 318), (540, 445), (540, 555)],
        end_sizes=(96, 120, 38, 34),
        thumbnail=(720, 1280),
    ),
}
LAYOUT = LAYOUTS["wide"]
W, H = LAYOUT["size"]

GAMES = [
    ("Hades", "epic", "hades"),
    ("Celeste", "steam", "celeste"),
    ("Dead Cells", "steam", "dead-cells"),
    ("Hollow Knight", "gog", "hollow-knight"),
    ("OpenTTD", "port", "openttd"),
    ("Stardew Valley", "steam", "stardew-valley"),
]


# --- The panel ---------------------------------------------------------------


def search(games, query):
    """The panel's search (games.rs), for the few queries the video types."""
    if not query:
        return games
    ranked = []
    for index, game in enumerate(games):
        name = game[0].lower()
        words = [word for word in re.split(r"[^a-z0-9]+", name) if word]
        initials = "".join(word[0] for word in words)
        if name.startswith(query):
            rank = 0
        elif any(word.startswith(query) for word in words):
            rank = 1
        elif len(query) > 1 and initials.startswith(query):
            rank = 2
        elif query in name:
            rank = 3
        else:
            continue
        ranked.append((rank, index, game))
    return [game for _, _, game in sorted(ranked)]


def panel_state(t):
    pinned = {"Hades"} | ({"Hollow Knight"} if t >= ENTER else set())
    games = sorted(GAMES, key=lambda game: (game[0] not in pinned, game[0].lower()))
    query = ""
    for at, typed in TYPED:
        if t >= at:
            query = typed
    shown = search(games, query)
    selected = sum(t >= at for at in DOWNS)
    if t >= ENTER:
        selected = [game[0] for game in shown].index("Hollow Knight")
    rows = [
        {
            "name": name,
            "label": f"pinned · {label}" if name in pinned else label,
            "icon": f"site/assets/games/{icon}.png",
            "pinned": name in pinned,
        }
        for name, label, icon in shown
    ]
    acting = selected if TAB <= t < ENTER else -1
    return {"time": t, "games": rows, "total": len(GAMES), "query": query, "selected": selected, "acting": acting}


def render_panel(frames):
    shutil.rmtree(frames, ignore_errors=True)
    states = "\n".join(json.dumps(panel_state(i / FPS)) for i in range(FRAMES))
    subprocess.run(
        ["cargo", "run", "-q", "--release", "--example", "panel_frames", "--", str(frames), str(PANEL_SCALE)],
        input=states.encode(),
        cwd=ROOT,
        check=True,
    )


# --- Drawing helpers ---------------------------------------------------------


def clamp(x, low=0.0, high=1.0):
    return max(low, min(high, x))


def between(t, start, length):
    return clamp((t - start) / length)


def ease(x):
    return 1 - (1 - clamp(x)) ** 3


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def put(image, sprite, xy, alpha=1.0):
    """Lays `sprite` over `image` at `xy`, faded by `alpha`, clipped to the frame."""
    if alpha <= 0:
        return
    if alpha < 1:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
    x, y = round(xy[0]), round(xy[1])
    if x >= image.width or y >= image.height or x + sprite.width <= 0 or y + sprite.height <= 0:
        return
    if x < 0 or y < 0:
        sprite = sprite.crop((max(0, -x), max(0, -y), sprite.width, sprite.height))
        x, y = max(0, x), max(0, y)
    image.alpha_composite(sprite, (x, y))


@functools.lru_cache(None)
def font(weight, size):
    return ImageFont.truetype(str(ROOT / "assets" / f"Inter-{weight}.ttf"), size)


@functools.lru_cache(None)
def cjk_font(size):
    """A Japanese font from the system, for the seal; None when there is none."""
    found = subprocess.run(
        ["fc-match", "-f", "%{file}|%{index}", "Noto Sans CJK JP:weight=bold"], capture_output=True, text=True
    ).stdout
    path, _, index = found.partition("|")
    if "CJK" not in path:
        return None
    return ImageFont.truetype(path, size, index=int(index or 0))


@functools.lru_cache(None)
def text(words, weight, size, colour, spacing=10, align="left"):
    f = font(weight, size)
    left, top, right, bottom = ImageDraw.Draw(Image.new("L", (1, 1))).multiline_textbbox(
        (0, 0), words, font=f, spacing=spacing, align=align
    )
    image = Image.new("RGBA", (math.ceil(right - left) + 4, math.ceil(bottom - top) + 4), colour + (0,))
    ImageDraw.Draw(image).multiline_text(
        (2 - left, 2 - top), words, font=f, fill=colour + (255,), spacing=spacing, align=align
    )
    return image


def anchor(sprite, x, nudge=0):
    """Where a sprite starts so it sits at x: from x, or centred on it."""
    return x - sprite.width / 2 if LAYOUT["align"] == "center" else x + nudge


@functools.lru_cache(None)
def bar():
    image = Image.new("RGBA", (56, 5), ACCENT + (0,))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, 55, 4), radius=2, fill=ACCENT + (255,))
    return image


@functools.lru_cache(None)
def seal(size=104):
    """A small hanko-style seal reading 花見, hanami."""
    big = size * 4
    image = Image.new("RGBA", (big, big), ACCENT + (0,))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=56, fill=ACCENT + (255,))
    face = cjk_font(int(big * 0.36))
    if face:
        draw.text((big / 2, big * 0.29), "花", font=face, fill=INK + (255,), anchor="mm")
        draw.text((big / 2, big * 0.71), "見", font=face, fill=INK + (255,), anchor="mm")
    return image.resize((size, size), Image.LANCZOS)


@functools.lru_cache(None)
def keycap(label, pressed):
    f = font("Medium", 40)
    width = max(96, int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(label, font=f)) + 64)
    image = Image.new("RGBA", (width, 112), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lift = 4 if pressed else 0
    draw.rounded_rectangle((0, 10, width - 1, 105), radius=18, fill=(8, 6, 12, 150))
    face = (74, 58, 72, 255) if pressed else (46, 40, 54, 255)
    edge = (244, 182, 200, 150) if pressed else (255, 255, 255, 46)
    draw.rounded_rectangle((0, lift, width - 1, 95 + lift), radius=18, fill=face, outline=edge, width=2)
    draw.text((width / 2, 48 + lift), label, font=f, fill=(ACCENT if pressed else TEXT) + (255,), anchor="mm")
    return image


# --- The picture -------------------------------------------------------------


def setup():
    """Things every frame shares; made once, before the workers start."""
    global WALL, WALL_BLUR, CHROME, SCREEN_MASK, BACKDROP, MASK, SPRITE, PETALS, NOISE
    scene = screenshot.SCENES["dark"]
    size = (SCREEN_W * DESK, SCREEN_H * DESK)
    WALL = screenshot.base(scene, random.Random(7), (SCREEN_W, SCREEN_H)).resize(size, Image.BICUBIC)
    WALL_BLUR = WALL.filter(ImageFilter.GaussianBlur(30 * DESK))
    CHROME = chrome(size)
    SCREEN_MASK = screenshot.rounded((SCREEN_W, SCREEN_H), 28)
    cover = min(size[0] / W, size[1] / H)
    crop = ((size[0] - W * cover) / 2, (size[1] - H * cover) / 2, (size[0] + W * cover) / 2, (size[1] + H * cover) / 2)
    BACKDROP = WALL_BLUR.resize((W, H), Image.BILINEAR, box=crop).point(lambda v: int(v * 0.5))
    MASK = screenshot.rounded((PW, PH), int(16 * PANEL_SCALE))
    SPRITE = screenshot.petal(64, scene["petal"], scene["vein"], 1.0, 0, 0)
    rand = random.Random(11)
    PETALS = []
    for k in range(36):
        depth = rand.uniform(0.35, 1.1) if k < 29 else rand.uniform(1.4, 2.0)
        PETALS.append(
            dict(
                depth=depth,
                x=rand.uniform(0, 1),
                y=rand.uniform(0, 1),
                sway=rand.uniform(10, 30) * depth,
                freq=rand.uniform(0.5, 1.1),
                phase=rand.uniform(0, math.tau),
                spin=rand.uniform(-70, 70),
                angle=rand.uniform(0, 360),
                flip=rand.uniform(0.6, 1.4),
            )
        )
    noise = np.random.default_rng(3)
    NOISE = [noise.normal(0, 1.2, (H, W, 1)).astype(np.float32) for _ in range(6)]


def chrome(size):
    """The desktop's own things over the wallpaper: a frosted taskbar with a
    start button, the tray (Hanami's flower beside sound and network) and a
    clock, and the mouse pointer. Drawn at twice the desktop's scale, then
    halved, for smooth edges."""
    u = DESK * 2
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    top = (SCREEN_H - BAR) * DESK
    layer.paste(WALL_BLUR.crop((0, top, size[0], size[1])), (0, top))
    layer.alpha_composite(Image.new("RGBA", (size[0], BAR * DESK), (14, 12, 19, 205)), (0, top))

    strip = Image.new("RGBA", (SCREEN_W * u, BAR * u), (0, 0, 0, 0))
    draw = ImageDraw.Draw(strip)
    ink, cy = TEXT + (225,), BAR * u / 2
    draw.line((0, 0, strip.width, 0), fill=(255, 255, 255, 30), width=u // 2)
    for dx in (0, 1):
        for dy in (0, 1):
            x, y = (16 + dx * 10) * u, cy + (dy * 10 - 9) * u
            draw.rounded_rectangle((x, y, x + 8 * u, y + 8 * u), radius=2 * u, fill=ink)
    clock = font("Medium", 14 * u)
    x = (SCREEN_W - 18) * u
    draw.text((x, cy), "21:30", font=clock, fill=ink, anchor="rm")
    x -= draw.textlength("21:30", font=clock) + 24 * u
    base = cy + 6 * u
    draw.ellipse((x - 2 * u, base - 2 * u, x + 2 * u, base + 2 * u), fill=ink)
    for r in (6, 10):
        draw.arc((x - r * u, base - r * u, x + r * u, base + r * u), 225, 315, fill=ink, width=2 * u)
    x -= 32 * u
    draw.polygon([(x - 8 * u, cy - 3 * u), (x - 4 * u, cy - 3 * u), (x + 1 * u, cy - 8 * u),
                  (x + 1 * u, cy + 8 * u), (x - 4 * u, cy + 3 * u), (x - 8 * u, cy + 3 * u)], fill=ink)
    for r in (5, 9):
        draw.arc((x + u - r * u, cy - r * u, x + u + r * u, cy + r * u), -45, 45, fill=ink, width=2 * u)
    x -= 32 * u
    flower = subprocess.run(["rsvg-convert", "-w", str(20 * u), "-h", str(20 * u), str(ROOT / "assets" / "hanami-icon.svg")],
                            capture_output=True, check=True).stdout
    flower = Image.open(io.BytesIO(flower)).convert("RGBA")
    strip.alpha_composite(flower, (round(x - flower.width / 2), round(cy - flower.height / 2)))
    layer.alpha_composite(strip.resize((size[0], BAR * DESK), Image.LANCZOS), (0, top))

    arrow = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]
    pointer = Image.new("RGBA", (16 * u, 24 * u), (0, 0, 0, 0))
    ImageDraw.Draw(pointer).polygon([(u + x * u, u + y * u) for x, y in arrow], fill=(255, 255, 255, 255),
                                     outline=(0, 0, 0, 255), width=u)
    pointer = pointer.resize((pointer.width * DESK // u, pointer.height * DESK // u), Image.LANCZOS)
    layer.alpha_composite(pointer, (POINTER[0] * DESK, POINTER[1] * DESK))
    return layer


def camera(t):
    """Where the camera is at t: (centre x, centre y, zoom), kept on the desktop."""
    keys = LAYOUT["camera"]
    x, y, zoom = keys[-1][1:]
    for (start, *a), (stop, *b) in zip(keys, keys[1:]):
        if t < stop:
            f = smooth(between(t, start, stop - start))
            x, y, zoom = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] * (b[2] / a[2]) ** f
            break
    half_w, half_h = W / zoom / 2, H / zoom / 2
    x = clamp(x, half_w, SCREEN_W - half_w) if half_w < SCREEN_W / 2 else SCREEN_W / 2
    y = clamp(y, half_h, SCREEN_H - half_h) if half_h < SCREEN_H / 2 else SCREEN_H / 2
    return x, y, zoom


def on_screen(cam, x, y, size=None):
    """A point on the desktop to a point in the frame (or an image of `size`)."""
    width, height = size or (W, H)
    return (x - cam[0]) * cam[2] + width / 2, (y - cam[1]) * cam[2] + height / 2


def desktop(cam, t):
    """The wallpaper, its petals and the taskbar as the camera sees them.
    Zoomed out past the screen's edges, the whole screen floats over a dim
    copy of the wallpaper."""
    zoom = cam[2]
    fills = W / zoom <= SCREEN_W + 0.5 and H / zoom <= SCREEN_H + 0.5
    size = (W, H) if fills else (round(SCREEN_W * zoom), round(SCREEN_H * zoom))
    view = cam if fills else (SCREEN_W / 2, SCREEN_H / 2, zoom)
    half_w, half_h = min(size[0] / zoom, SCREEN_W) / 2, min(size[1] / zoom, SCREEN_H) / 2
    box = tuple(v * DESK for v in (view[0] - half_w, view[1] - half_h, view[0] + half_w, view[1] + half_h))
    image = WALL.resize(size, Image.BILINEAR, box=box)
    for p in PETALS:
        if p["depth"] < 1.2:
            draw_petal(image, p, t, view)
    image.alpha_composite(CHROME.resize(size, Image.BILINEAR, box=box))
    if fills:
        return image
    frame = BACKDROP.copy()
    left, top = (round(v) for v in on_screen(cam, 0, 0))
    shade = Image.new("L", (W // 8, H // 8), 0)
    small = SCREEN_MASK.resize((max(1, size[0] // 8), max(1, size[1] // 8)), Image.BILINEAR)
    shade.paste(small, (left // 8, (top + round(24 * zoom)) // 8))
    shade = shade.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR).point(lambda v: int(v * 0.6))
    frame.paste((0, 0, 0, 255), (0, 0, W, H), shade)
    frame.paste(image, (left, top), SCREEN_MASK.resize(size, Image.BILINEAR))
    return frame


def draw_petal(image, p, t, cam=None):
    """A falling petal: on the wallpaper, moving with the camera, or with no
    camera close in front of everything."""
    depth = p["depth"]
    width, height = (SCREEN_W, SCREEN_H) if cam else (W, H)
    x = (p["x"] * (width + 400) - (25 + 35 * depth) * t + p["sway"] * math.sin(p["freq"] * t + p["phase"]))
    x = x % (width + 400) - 200
    y = (p["y"] * (height + 300) + (28 + 38 * depth) * t) % (height + 300) - 150
    zoom = 1.0
    if cam:
        (x, y), zoom = on_screen(cam, x, y, image.size), cam[2]
    size = (9 + 16 * depth) / 64 * zoom
    squash = 0.3 + 0.7 * abs(math.cos(p["flip"] * t + p["phase"]))
    sprite = SPRITE.resize(
        (max(2, round(SPRITE.width * size * squash)), max(2, round(SPRITE.height * size))), Image.LANCZOS
    )
    sprite = sprite.rotate(p["angle"] + p["spin"] * t, Image.BICUBIC, expand=True)
    blur = 1.6 + 2.5 * (depth - 1.4) if depth > 1.2 else (0.6 if depth < 0.6 else 0)
    if blur:
        pad = int(blur * 3)
        padded = Image.new("RGBA", (sprite.width + 2 * pad, sprite.height + 2 * pad), sprite.getpixel((0, 0))[:3] + (0,))
        padded.paste(sprite, (pad, pad))
        sprite = padded.filter(ImageFilter.GaussianBlur(blur))
    alpha = 0.75 if depth > 1.2 else 0.3 + 0.45 * min(depth, 1)
    put(image, sprite, (x - sprite.width / 2, y - sprite.height / 2), alpha)


def draw_panel(image, cam, t, index):
    """The real panel where Hanami opens it, over frosted wallpaper. Like the
    app, it fades in over 140 ms."""
    opacity = between(t, REVEAL, 0.14)
    if opacity <= 0:
        return
    x0, y0, pw, ph = PANEL_BOX
    zoom = cam[2]
    left, top = (round(v) for v in on_screen(cam, x0, y0))
    w, h = round(pw * zoom), round(ph * zoom)
    mask = MASK.resize((w, h), Image.LANCZOS)

    pad = round(46 * zoom)
    shade = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    shade.paste(mask, (pad, pad))
    small = shade.resize((shade.width // 4, shade.height // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5 * zoom))
    shadow = Image.new("RGBA", shade.size, (0, 0, 0, 0))
    shadow.putalpha(small.resize(shade.size, Image.BILINEAR).point(lambda v: int(v * 0.55 * opacity)))
    put(image, shadow, (left - pad, top - pad + 16 * zoom))

    # Frosted glass: the blurred wallpaper, seen through the panel.
    region = tuple(v * DESK for v in (x0, y0, x0 + pw, y0 + ph))
    image.paste(WALL_BLUR.resize((w, h), Image.BILINEAR, box=region), (left, top), mask.point(lambda v: int(v * opacity)))
    raw = (CACHE / "panel" / f"{index:05}.rgba").read_bytes()
    put(image, Image.frombytes("RGBa", (PW, PH), raw).convert("RGBA").resize((w, h), Image.LANCZOS), (left, top), opacity)


def draw_keycaps(image, t):
    gone = ease(between(t, REVEAL, 0.3))
    if gone >= 1:
        return
    plus = text("+", "Regular", 36, DIM)
    items = []
    for n, (label, at) in enumerate(KEYS):
        if n:
            items.append((plus, at, None))
        items.append((keycap(label, False), at, label))
    gap = 26
    total = sum(item[0].width for item in items) + gap * (len(items) - 1)
    # When the panel opens, the keys step aside to make room for it.
    (cx, cy), (dx, dy) = LAYOUT["keys"], LAYOUT["keys_aside"]
    x, y = cx - total / 2 + dx * gone, cy + dy * gone
    for sprite, at, label in items:
        shown = ease(between(t, at - 0.15, 0.2))
        if label:
            sprite = keycap(label, t >= at)
            pop = 0.88 + 0.12 * shown
            scaled = sprite.resize((round(sprite.width * pop), round(sprite.height * pop)), Image.LANCZOS)
            put(image, scaled, (x + (sprite.width - scaled.width) / 2, y - 52), shown * (1 - gone))
        else:
            put(image, sprite, (x, y - sprite.height / 2), shown * (1 - gone))
        x += sprite.width + gap


def draw_caption(image, t, start, end, title, sub):
    leave = smooth(between(t, end - 0.3, 0.3))
    first, second = ease(between(t, start, 0.5)), ease(between(t, start + 0.1, 0.5))
    if first <= 0 or leave >= 1:
        return
    (x, y), (title_size, sub_size), align = LAYOUT["words"], LAYOUT["word_sizes"], LAYOUT["align"]
    heading = text(title, "SemiBold", title_size, TEXT, align=align)
    under = text(sub, "Regular", sub_size, DIM, align=align)
    put(image, bar(), (anchor(bar(), x, 4), y - 28 + 30 * (1 - first) - 16 * leave), first * (1 - leave))
    put(image, heading, (anchor(heading, x), y + 30 * (1 - first) - 16 * leave), first * (1 - leave))
    put(image, under, (anchor(under, x, 4), y + 30 + heading.height + 30 * (1 - second) - 16 * leave),
        second * (1 - leave))


def draw_end_card(image, t):
    mark, name, tagline, link = LAYOUT["end_sizes"]
    parts = [
        seal(mark),
        text("hanami", "SemiBold", name, TEXT),
        text("A small game launcher\nfor Linux and Windows.", "Regular", tagline, DIM, align=LAYOUT["align"]),
        text("hanami.lilygrove.dev", "Medium", link, ACCENT),
    ]
    for n, (sprite, (x, y)) in enumerate(zip(parts, LAYOUT["end"])):
        shown = ease(between(t, END + 0.08 * n, 0.6))
        put(image, sprite, (anchor(sprite, x), y + 30 * (1 - shown)), shown)


def compose(index):
    t = index / FPS
    cam = camera(t)
    image = desktop(cam, t)
    draw_keycaps(image, t)
    draw_panel(image, cam, t, index)
    for caption in CAPTIONS:
        draw_caption(image, t, *caption)
    draw_end_card(image, t)
    for p in PETALS:
        if p["depth"] >= 1.2:
            draw_petal(image, p, t)
    return image


def frame(index):
    t = index / FPS
    light = smooth(between(t, 0, 0.45)) * (1 - smooth(between(t, LENGTH - 0.5, 0.5)))
    rgb = np.asarray(compose(index).convert("RGB"), dtype=np.float32) * light + NOISE[index % len(NOISE)]
    return np.clip(rgb, 0, 255).astype(np.uint8).tobytes()


# --- The music ---------------------------------------------------------------

RNG = np.random.default_rng(5)


def seconds(length):
    return np.arange(int(length * SR)) / SR


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def koto(midi, length=3.2, bend=0.0):
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


def smooth_array(x):
    return x * x * (3 - 2 * x)


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


def pad():
    t = seconds(LENGTH)
    out = sum(
        amp * np.sin(2 * np.pi * hz(midi) * t + 0.3 * np.sin(2 * np.pi * 0.11 * t + midi))
        for midi, amp in ((38, 0.5), (45, 0.35), (50, 0.25), (57, 0.12))
    )
    swell = smooth_array(np.clip(t / 2.0, 0, 1))
    return sosfilt(butter(2, 900, "lowpass", fs=SR, output="sos"), out * swell)


MELODY = [
    # beat, notes (MIDI, D miyako-bushi: D Eb G A Bb), loudness, bend
    (0, (50, 62), 0.9, 0), (0.5, (69,), 0.55, 0), (1, (70,), 0.6, 0), (1.5, (69,), 0.55, 0),
    (2, (67,), 0.6, 0), (2.5, (63,), 0.5, 0), (3, (67,), 0.7, 2),
    (4, (55, 62), 0.75, 0), (4.5, (70,), 0.5, 0), (5, (69,), 0.55, 0), (5.5, (74,), 0.6, 0),
    (6, (70,), 0.5, 0), (6.5, (69,), 0.5, 0), (7, (67,), 0.65, 0),
    (8, (51, 63), 0.7, 0), (8.5, (67,), 0.5, 0), (9, (69,), 0.55, 0), (9.5, (70,), 0.55, 0),
    (10, (74,), 0.65, 0), (10.5, (75,), 0.55, 0), (11, (74,), 0.6, 0), (11.5, (70,), 0.5, 0),
    (12, (57, 69), 0.6, 0), (12.5, (50, 57, 62, 69, 74), 0.85, 0), (13.5, (74,), 0.5, 0), (14.5, (81,), 0.4, 0),
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


def write_music(path):
    n = int(LENGTH * SR)
    dry, send = np.zeros((n, 2)), np.zeros((n, 2))

    def place(sound, at, gain, pan=0.0, wet=0.2):
        start = int(round(at * SR))
        if start >= n:
            return
        sound = sound[: n - start]
        for channel, side in ((0, math.cos((pan + 1) * math.pi / 4)), (1, math.sin((pan + 1) * math.pi / 4))):
            dry[start : start + len(sound), channel] += sound * gain * side
            send[start : start + len(sound), channel] += sound * gain * side * wet

    for beat, notes, loud, bend in MELODY:
        for k, midi in enumerate(notes):
            strum = 0.035 * k if len(notes) > 2 else 0
            place(koto(midi, 4.0 if beat >= 12.5 else 3.2, bend), b(beat) + strum, 0.32 * loud,
                  pan=clamp((midi - 62) / 30, -0.4, 0.4), wet=0.3)
    for beat, loud in ((0, 0.55), (1.5, 0.8), (8, 0.45), (12.5, 1.0)):
        place(taiko(), b(beat), 0.5 * loud, wet=0.12)
    place(pad(), 0, 0.06, wet=0.3)
    place(chime(86), END + 0.05, 0.2, pan=0.2, wet=0.4)
    place(chime(93), END + 0.4, 0.12, pan=-0.2, wet=0.4)
    place(whoosh(), REVEAL - 0.3, 0.2, pan=0.25, wet=0.15)
    place(whoosh(0.8, 0.3), END - 0.3, 0.12, pan=-0.1, wet=0.15)
    for label, at in KEYS:
        place(click(True), at, 0.2, wet=0.06)
    for at in CLICKS:
        place(click(False), at, 0.14, pan=0.2, wet=0.06)

    t = np.arange(int(2.4 * SR)) / SR
    rooms = []
    for seed in (1, 2):
        room = sosfilt(butter(2, 4500, "lowpass", fs=SR, output="sos"), np.random.default_rng(seed).standard_normal(len(t)))
        room *= np.exp(-t / 0.3) * np.clip(t / 0.012, 0, 1)
        rooms.append(room / np.sqrt(np.sum(room**2)))
    mix = dry + 0.9 * np.stack([fftconvolve(send[:, c], rooms[c])[:n] for c in (0, 1)], axis=1)
    mix = sosfilt(butter(2, 30, "highpass", fs=SR, output="sos"), mix, axis=0)
    ends = np.clip(np.arange(n) / (0.02 * SR), 0, 1) * np.clip((n - np.arange(n)) / (0.6 * SR), 0, 1)
    mix *= ends[:, None]

    wavfile.write(path, SR, mix.astype(np.float32))
    mix *= 10 ** ((-16 - loudness(path)) / 20)
    if np.max(np.abs(mix)) > 0.89:
        mix = 0.89 * np.tanh(mix / 0.89)
    wavfile.write(path, SR, (mix * 32767).astype(np.int16))


# --- Putting it together -----------------------------------------------------


def encode(out, music):
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", str(music),
         "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
         "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", str(out)],
        stdin=subprocess.PIPE,
    )
    with multiprocessing.get_context("fork").Pool(os.cpu_count()) as pool:
        for data in pool.imap(frame, range(FRAMES), chunksize=4):
            ffmpeg.stdin.write(data)
    ffmpeg.stdin.close()
    if ffmpeg.wait():
        sys.exit("ffmpeg failed")


def main():
    global LAYOUT, W, H
    args = sys.argv[1:]
    if "--tall" in args:
        args.remove("--tall")
        LAYOUT = LAYOUTS["tall"]
    if len(args) != 1:
        sys.exit(__doc__)
    W, H = LAYOUT["size"]
    out = Path(args[0]).resolve()
    CACHE.mkdir(parents=True, exist_ok=True)
    print("drawing the panel")
    render_panel(CACHE / "panel")
    print("writing the music")
    write_music(CACHE / "music.wav")
    print("putting it together")
    setup()
    encode(out, CACHE / "music.wav")
    thumbnail = compose(round((END + 1.6) * FPS)).convert("RGB").resize(LAYOUT["thumbnail"], Image.LANCZOS)
    thumbnail.save(out.with_name(out.stem + "-thumbnail.jpg"), quality=92)
    shutil.rmtree(CACHE)
    print(out)


if __name__ == "__main__":
    main()
