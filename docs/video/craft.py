"""Makes Hanami's "craft" video: any harness, any model. Six AI coding
agents, each on a different model, each change one thing about the same
Hanami, one bar of music each: Crush, OpenCode, Antigravity CLI, jcode,
Codex and Claude Code. Then Ctrl+Space (the hotkey one of them set) opens the panel
with everything they did, two letters find Minecraft, and Enter starts it
through Prism Launcher: the title screen, then a walk through a cherry grove.

The desktop is a real KDE Plasma session drawn off screen; the agents and the
models run for real in its terminal (docs/craft_ai.py), the panel is drawn by
the panel_frames example with what they wrote, and Minecraft's window is the
real one: its frame is captured in the session, its picture comes from
recordings of the game in the same setup (docs/craft_footage.py). The music
is an original piece (docs/craft_music.py), or a song.

    python3 docs/craft.py craft.mp4
    python3 docs/craft.py --music song.mp3 --bpm 96 --hit 19.92 craft.mp4

Writes the video (1920 x 1080, 60 fps, about 33 seconds) and a thumbnail
next to it. --music plays a song instead: --bpm is its tempo and --hit the
second in it the game should open on; --no-grain leaves out the film grain.
Needs Rust, ffmpeg, Pillow, NumPy and SciPy; KDE Plasma with Konsole and
Spectacle; the agents signed in and the footage recorded (see
docs/craft_ai.py and docs/craft_footage.py); and a few minutes.
"""

import functools
import json
import math
import multiprocessing
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import craft_ai  # noqa: E402
import craft_footage  # noqa: E402
import craft_music  # noqa: E402
import screenshot  # noqa: E402


def option(name):
    """Takes `name value` out of the command line; None when it isn't there."""
    if name not in sys.argv[1:]:
        return None
    at = sys.argv.index(name)
    if at + 1 >= len(sys.argv):
        sys.exit(f"{name} needs a value")
    value = sys.argv[at + 1]
    del sys.argv[at : at + 2]
    return value


MUSIC, BPM, HIT = option("--music"), option("--bpm"), option("--hit")
if MUSIC and not (BPM and HIT):
    sys.exit("--music needs --bpm and --hit too")
GRAIN = 0.0 if "--no-grain" in sys.argv and not sys.argv.remove("--no-grain") else 1.2
FPS = 60
BEAT = 60 / float(BPM or craft_music.BPM)
PANEL_SCALE = 2.0
PW, PH = int(340 * PANEL_SCALE), int(440 * PANEL_SCALE)
CACHE = craft_footage.CACHE / "video"
FOOTAGE = craft_footage.FOOTAGE

TEXT = (236, 230, 238)
DIM = (155, 147, 163)
SUB = (226, 220, 232)
ACCENT = (244, 182, 200)
INK = (23, 20, 29)


def b(beats):
    return beats * BEAT


# The story, on the beat. Each agent gets one bar: the sentence is typed in
# its first beat, the agent works (sped up to fit) until half a beat before
# the next cut. Then all six at once, Ctrl+Space, the panel, "mi", Enter,
# Minecraft.
CUTS = [b(beat) for beat in craft_music.CUTS]
TYPE_BEATS, WORK_BEATS = 0.75, 3.5
GRID = (b(craft_music.GRID), b(craft_music.REVEAL - 0.9))
HOTKEY = [b(30.25), b(30.75)]
REVEAL = b(craft_music.REVEAL)
TYPED = [(b(32.5), "m"), (b(33), "mi")]
ENTER = b(35)
GAME = b(craft_music.GAME)
# The game window: Minecraft's loading screen, sped up, until the title
# screen; the title screen; then, from beat 40, the walk.
TITLE = GAME + b(1.5)
WALK = b(40)
KEYCAST = [
    ([("Ctrl", HOTKEY[0]), ("Space", HOTKEY[1])], REVEAL + 0.5),
    ([("Enter", ENTER)], ENTER + 0.6),
]
CAPTIONS = [
    (b(0.4), b(3.6), "Any harness.\nAny model.", "Six AI agents set up one game launcher."),
    (b(31.5), b(34.7), "All of it,\nin one panel.", "Hidden, renamed, pinned, autumn, Ctrl+Space, Minecraft."),
    (b(37), b(47.2), "Then play.", "Minecraft, started through Prism Launcher."),
]
END = b(craft_music.END)
LENGTH = END + 2.65
FRAMES = round(LENGTH * FPS)

# The desktop: KDE Plasma as it comes out of the box (Breeze Dark, the
# "Darkest Hour" wallpaper from KDE's wallpaper collection, CC BY-SA 4.0), in
# a throwaway session with its own empty home folder. Hanami sits in the tray
# and each agent opens in a terminal on the right. Sizes are in logical
# pixels; the desktop is captured at twice that so the camera can move in.
SCREEN_W, SCREEN_H = 1920, 1080
DESK = 2
PANEL_BOX = ((SCREEN_W - 340) / 2, (SCREEN_H - 440) / 2, 340, 440)
LAUNCHERS = ",".join(
    ["preferred://filemanager"]
    + [f"applications:{app}.desktop" for app in ("firefox", "steam", "discord", "org.kde.konsole")]
)
WALLPAPER = "https://raw.githubusercontent.com/KDE/plasma-workspace-wallpapers/master/DarkestHour/contents/images/2560x1600.jpg"
TERMINAL = (1050, 120, 800, 660)
REST = (1700, 990)
TASKS = (
    'panels().forEach(p => p.widgets("org.kde.plasma.icontasks").forEach(w => {'
    ' w.currentConfigGroup = ["General"]; w.writeConfig("launchers", "%s"); }))' % LAUNCHERS
)
# Each agent in a terminal of its own, one after the other, shot a few
# times a second; the sentence is typed into it and the session waits until
# the settings are what was asked (craft_ai.py --done), and a little longer
# for the agent's last words. Then the desktop alone, the list Hanami would
# show, and Minecraft, started the way Hanami starts it, so its window can be
# captured where KWin puts it.
SESSION = """#!/bin/sh
plasmashell --no-respawn &
sleep 10
plasma-apply-lookandfeel --apply org.kde.breezedark.desktop --resetLayout
sleep 4
plasma-apply-wallpaperimage '{wallpaper}'
qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '{tasks}'
sleep 2
kquitapp6 plasmashell
plasmashell --no-respawn &
env -u WAYLAND_DISPLAY '{hanami}' --hidden &
sleep 8
mark() {{
    echo "$1 $(date +%s.%N)" >> '{shots}/times'
}}
echo 1 > '{shots}/step'
( n=100; while [ ! -f '{shots}/stop' ]; do
    s=$(cat '{shots}/step')
    spectacle --background --nonotify --activewindow --output '{shots}'/$s-$n.png
    echo "$s-$n $(date +%s.%N)" >> '{shots}/times'
    n=$((n + 1))
done ) &
shooter=$!
{agents}
touch '{shots}/stop'
wait $shooter
sleep 2
spectacle --background --nonotify --fullscreen --output '{out}'
XDG_CONFIG_HOME='{agent_home}/.config' '{hanami}' --list --verbose > '{shots}/list.txt' 2>&1
flatpak run {prism} --launch '{instance}' > '{shots}/prism.log' 2>&1 &
n=0; until grep -q 'atlas' '{game_log}' 2>/dev/null || [ $n -gt 120 ]; do sleep 1; n=$((n+1)); done
sleep 12
spectacle --background --nonotify --fullscreen --output '{shots}/game-full.png'
spectacle --background --nonotify --activewindow --output '{shots}/game-window.png'
"""
AGENT = """
echo {n} > '{shots}/step'
konsole --separate --hide-menubar --hide-toolbars --hide-tabbar --profile Video -qwindowgeometry {size} -e '{start}' {args} &
terminal=org.kde.konsole-$!
sleep {boot}
{keys}
mark {n}-type
printf '%s\\n' '{prompt}' | fold -w1 | while IFS= read -r c; do
    qdbus6 $terminal /Sessions/1 org.kde.konsole.Session.sendText "$c"
    sleep 0.06
done
mark {n}-enter
qdbus6 $terminal /Sessions/1 org.kde.konsole.Session.sendText "$(printf '\\r')"
n=0
until python3 '{check}' --done {n}; do
    sleep 1; n=$((n + 1))
    [ $n -gt 240 ] && {{ echo {n} > '{shots}/failed'; touch '{shots}/stop'; exit 1; }}
done
mark {n}-edited
sleep 10
mark {n}-end
qdbus6 $terminal /konsole/MainWindow_1 org.qtproject.Qt.QWidget.close 2>/dev/null || kill %%
sleep 3
"""
# Keys an agent needs before the sentence: jcode greets a folder it hasn't
# worked in with a choice, and "New session in ~" is the second one.
KEYS = {"jcode": ["\\033[B", "\\r"]}
# How long each agent takes to be ready for typing, in seconds.
BOOT = {"crush": 8, "opencode": 10, "agy": 14, "jcode": 25, "codex": 10, "claude": 10}

# Where everything sits, and the camera: (time, centre x, centre y, zoom) on
# the desktop, eased from one to the next; "game" stands for the place that
# frames the game window, found once it has been captured.
TERM_FOCUS = (TERMINAL[0] + TERMINAL[2] / 2 - 120, TERMINAL[1] + TERMINAL[3] / 2)
LAYOUT = dict(
    size=(1920, 1080),
    align="left",
    keys=[(960, 930), (430, 930)],
    keys_aside=(0, 40),
    camera=[
        (0, 960, 540, 1.0),
        (b(3.2), 960, 540, 1.04),
        # Still while the agents work: a slow zoom makes terminal text shimmer.
        (b(4), *TERM_FOCUS, 1.8),
        (GRID[0], *TERM_FOCUS, 1.8),
        (GRID[1] - 0.05, 960, 540, 1.0),
        (HOTKEY[0], 960, 540, 1.02),
        (REVEAL + 0.3, 790, 540, 1.7),
        (ENTER + 0.3, 790, 540, 1.72),
        (GAME + 0.6, "game", 1.2),
        (END - 0.2, "game", 1.27),
        (END + 0.8, 960, 540, 1.0),
    ],
    words=(148, 400),
    word_sizes=(72, 32),
    end=[(150, 270), (144, 410), (152, 590), (152, 720)],
    end_sizes=(104, 132, 36, 32),
    thumbnail=(1280, 720),
)
W, H = LAYOUT["size"]

ICONS = {
    "Hades": "site/assets/games/hades.png",
    "Celeste": "site/assets/games/celeste.png",
    "Dead Cells": "site/assets/games/dead-cells.png",
    "Hollow Knight": "site/assets/games/hollow-knight.png",
    "Stardew Valley": "site/assets/games/stardew-valley.png",
}


# --- The panel ---------------------------------------------------------------


def search(rows, query):
    """The panel's search (games.rs), for the few queries the video types."""
    ranked = []
    for index, row in enumerate(rows):
        name = row["name"].lower()
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
        ranked.append((rank, index, row))
    return [row for _, _, row in sorted(ranked)]


def drawable(icon):
    """An icon the panel_frames example can read: SVGs drawn to PNG first."""
    if not icon or not icon.endswith(".svg"):
        return icon
    out = CACHE / "icons" / (Path(icon).stem + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "-w", "256", "-h", "256", "-o", str(out), icon], check=True)
    return str(out)


def panel_rows(listing):
    """The panel's rows from `hanami --list --verbose` as run on the agents'
    settings: (whole list, every game for searching). A launcher's row comes
    with the launchers, then the pinned games, then the rest by name, like
    the panel orders them; the games under a launcher show only in a search,
    labelled with where they are."""
    settings = craft_ai.tomllib.loads(craft_ai.CONFIG.read_text())
    pinned = {name.lower() for name in settings.get("favourites", [])}
    renamed = {new: old for old, new in settings.get("rename", {}).items()}
    games = []
    for line in listing.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        name, label = parts[0], parts[1]
        # This computer also has Prism's native package, with no instances
        # in the throwaway home; the person in the video has the Flatpak only.
        if label == "no instances yet":
            continue
        # A game renamed in its own [[game]] entry (not through `rename`)
        # keeps its picture: the original name starts with the new one.
        original = renamed.get(name) or next((known for known in ICONS if known.startswith(name)), name)
        icon = parts[2] if len(parts) > 2 and parts[2].startswith("/") else ICONS.get(original)
        games.append({"name": name, "label": label, "icon": drawable(icon)})
    launchers = {game["label"].split(" · in ", 1)[1] for game in games if " · in " in game["label"]}
    top, inside = [], []
    for game in games:
        if " · in " in game["label"]:
            inside.append({**game, "label": "in " + game["label"].split(" · in ", 1)[1]})
            continue
        # Prism is shown as a launcher already kept: the panel's "Found a new
        # game" question would take the eye off the list.
        new, pin = False, game["name"].lower() in pinned
        mark = "pinned" if pin else ""
        top.append({**game, "label": f"{mark} · {game['label']}" if mark else game["label"],
                    "new": new, "pinned": pin and not new, "opens": game["name"] in launchers})
    top.sort(key=lambda row: (not row["opens"], not row["pinned"], row["name"].lower()))
    return top, top + inside


def panel_state(t, look, rows):
    """The panel in the look the agents wrote, narrowed by what's typed."""
    top, everything = rows
    query = ""
    for at, typed in TYPED:
        if t >= at:
            query = typed
    shown = search(everything, query) if query else top
    theme, folder = look
    return {"time": t, "games": shown, "total": len(shown) if query else len(top), "query": query, "selected": 0,
            "pointer": None, "theme": theme, "look": str(folder)}


def render_panel(frames, look, rows):
    shutil.rmtree(frames, ignore_errors=True)
    states = "\n".join(json.dumps(panel_state(i / FPS, look, rows)) for i in range(FRAMES))
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


@functools.lru_cache(None)
def pill(words, size=26):
    """Small words on a dark rounded pill: a terminal's speed, a grid label."""
    sprite = text(words, "Medium", size, TEXT)
    image = Image.new("RGBA", (sprite.width + 2 * size, sprite.height + size), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=image.height // 2,
                                            fill=(12, 10, 16, 190))
    image.alpha_composite(sprite, (size, size // 2))
    return image


# --- The agents in the terminal ----------------------------------------------


@functools.lru_cache(16)
def term_shot(path):
    return Image.open(path).convert("RGBA").crop(TERM_FRAMES[int(Path(path).name.split("-")[0])])


def same(a, b):
    """Two terminal shots that look alike."""
    look = lambda path: np.asarray(Image.open(path).convert("L").reduce(4), np.int16)
    return np.abs(look(a) - look(b)).mean() < 0.5


def settled_at(shots, since):
    """When the terminal stopped changing after `since`: the time of the
    first shot that looks like the last one."""
    last = shots[-1][1]
    return next((at for at, path in shots if at >= since and same(path, last)), shots[-1][0])


def step_at(t):
    """Which agent the terminal shows at t (counted from 1)."""
    return max(1, min(len(CUTS), 1 + sum(1 for cut in CUTS[1:] if t >= cut)))


RATE = 5


def term_wall(t):
    """(agent, wall-clock time in its session) the terminal shows at t: the
    sentence typed in the first part of its bar, its work in the rest, at
    whatever speed fits; still before and after."""
    step = step_at(t)
    cut, marks = CUTS[step - 1], MARKS[step]
    typing, working = cut + b(TYPE_BEATS), cut + b(WORK_BEATS)
    if t < cut:
        return step, marks["type"] - 0.5
    if t < typing:
        return step, marks["type"] + (t - cut) / (typing - cut) * (marks["enter"] - marks["type"])
    if t < working:
        # Sped up, an agent's screen would redraw a dozen times a second and
        # jitter; it changes at most RATE times a second of video instead.
        t = typing + math.floor((t - typing) * RATE) / RATE
        return step, marks["enter"] + (t - typing) / (working - typing) * (SETTLED[step] - marks["enter"])
    return step, SETTLED[step]


def term_image(t):
    step, wall = term_wall(t)
    shown = SHOTS[step][0][1]
    for at, path in SHOTS[step]:
        if at <= wall:
            shown = path
    return term_shot(shown)


def speed(step):
    """How many times faster than real time the agent's work plays."""
    return (SETTLED[step] - MARKS[step]["enter"]) / b(WORK_BEATS - TYPE_BEATS)


def terminal_on(screen, t):
    """The agent's terminal; after all six, it's minimised, like the session
    leaves the desktop for the panel and the game."""
    if t < GRID[1]:
        put(screen, term_image(t), (TERMINAL[0] * DESK, TERMINAL[1] * DESK))


def pointer_on(screen, t):
    sprite, (hx, hy) = POINTER
    put(screen, sprite, (REST[0] * DESK - hx, REST[1] * DESK - hy))


def panel_on(screen, t, index):
    """The real panel where Hanami opens it, over frosted wallpaper. Like the
    app, it fades in and out over 140 ms; Enter starts the game and hides it."""
    opacity = between(t, REVEAL, 0.14) * (1 - between(t, ENTER + 0.08, 0.14))
    if opacity <= 0:
        return
    left, top = round(PANEL_BOX[0] * DESK), round(PANEL_BOX[1] * DESK)
    put(screen, PANEL_SHADOW, (left - PANEL_PAD, top - PANEL_PAD + 16 * DESK), opacity)
    frosted = WALL_BLUR.crop((left, top, left + PW, top + PH))
    screen.paste(frosted, (left, top), MASK.point(lambda v: int(v * opacity)))
    raw = (CACHE / "panel" / f"{index:05}.rgba").read_bytes()
    put(screen, Image.frombytes("RGBa", (PW, PH), raw).convert("RGBA"), (left, top), opacity)


@functools.lru_cache(4)
def footage(name, index):
    return Image.open(CACHE / "frames" / name / f"{index + 1:04}.png").convert("RGBA")


def game_picture(t):
    """What's in Minecraft's window at t: the loading screen sped up, the
    title screen, then the walk."""
    if t < TITLE:
        return footage("load", min(COUNTS["load"] - 1, int((t - GAME) * FPS)))
    title = footage("title", min(COUNTS["title"] - 1, int((t - TITLE) * FPS)))
    if t < WALK:
        return title
    walk = footage("walk", min(COUNTS["walk"] - 1, int((t - WALK) * FPS)))
    fade = smooth(between(t, WALK, 0.3))
    return Image.blend(title, walk, fade) if fade < 1 else walk


def game_on(screen, t):
    """Minecraft's window as KWin opens it (growing from 90 % and fading in
    over 200 ms): its frame as captured in the session, its picture from the
    recordings."""
    if t < GAME:
        return
    window = GAME_WINDOW.copy()
    window.paste(game_picture(t), GAME_INSET)
    grow = ease(between(t, GAME, 0.2))
    if grow < 1:
        scale = 0.9 + 0.1 * grow
        window = window.resize((round(window.width * scale), round(window.height * scale)), Image.LANCZOS)
    x = GAME_AT[0] + (GAME_WINDOW.width - window.width) / 2
    y = GAME_AT[1] + (GAME_WINDOW.height - window.height) / 2
    put(screen, window, (x, y), grow)


def project(source, size, left, top, scale):
    """`source` drawn `scale` times its size with its corner at a fractional
    (left, top), cut to a frame of `size`. Resampling from a fractional box
    keeps slow camera moves smooth, where rounding to whole pixels shakes."""
    x0, y0 = max(0, math.floor(left)), max(0, math.floor(top))
    x1, y1 = min(size[0], math.ceil(left + source.width * scale)), min(size[1], math.ceil(top + source.height * scale))
    if x1 <= x0 or y1 <= y0:
        return None, (0, 0)
    pad = math.ceil(1 / scale) + 1
    padded = ImageOps.expand(source, pad, (0, 0, 0, 0))
    box = (pad + (x0 - left) / scale, pad + (y0 - top) / scale, pad + (x1 - left) / scale, pad + (y1 - top) / scale)
    return padded.resize((x1 - x0, y1 - y0), Image.LANCZOS, box=box), (x0, y0)


# --- Capturing ---------------------------------------------------------------


def capture_desktop(out, shots):
    """Starts the throwaway Plasma session off screen and saves a screenshot
    of the desktop, of each agent in its terminal as it works, the list
    Hanami makes of what they set, and Minecraft's window where KWin opens
    it."""
    if not (FOOTAGE / "walk.mp4").exists():
        sys.exit("needs the Minecraft footage: python3 docs/craft_footage.py")
    subprocess.run(["cargo", "build", "-q", "--release", "-p", "hanami"], cwd=ROOT, check=True)
    place = CACHE / "desktop"
    # A session cut short can leave the document portal's mount behind.
    subprocess.run(["fusermount3", "-u", "-q", str(place / "run" / "doc")], stderr=subprocess.DEVNULL, check=False)
    shutil.rmtree(place, ignore_errors=True)
    shutil.rmtree(shots, ignore_errors=True)
    shutil.rmtree(shots.with_name(shots.name + "-raw"), ignore_errors=True)
    shots.mkdir(parents=True)
    home, run = place / "home", place / "run"
    for folder in ("Desktop", "Documents", "Downloads", "Games", "Music", "Pictures", "Videos", ".config"):
        (home / folder).mkdir(parents=True)
    run.mkdir(mode=0o700)
    # Konsole as it comes, with a bigger font so the words read in the video.
    (home / ".config" / "konsolerc").write_text(
        "[Desktop Entry]\nDefaultProfile=Video.profile\n\n[KonsoleWindow]\nEnableSecuritySensitiveDBusAPI=true\n"
    )
    (home / ".local" / "share" / "konsole").mkdir(parents=True)
    (home / ".local" / "share" / "konsole" / "Video.profile").write_text(
        "[Appearance]\nColorScheme=Breeze\nFont=Hack,18\n\n[General]\nName=Video\nParent=FALLBACK/\nShowTerminalSizeHint=false\n"
    )
    name, _ = craft_footage.instance()
    game = craft_footage.prism_home(home, name, fullscreen=False)
    (game / "logs" / "latest.log").unlink(missing_ok=True)
    wallpaper = craft_footage.CACHE / "darkest-hour.jpg"
    if not wallpaper.exists():
        subprocess.run(["curl", "-sfL", "-o", str(wallpaper), WALLPAPER], check=True)
    starts = craft_ai.prepare_home([step["agent"] for step in craft_ai.STEPS])
    size = f"{TERMINAL[2] * DESK}x{TERMINAL[3] * DESK}"
    agents = "".join(
        AGENT.format(n=n, shots=shots, size=size, start=starts[step["agent"]][0],
                     args=" ".join(starts[step["agent"]][1]), boot=BOOT[step["agent"]], prompt=step["prompt"],
                     keys="".join(f"qdbus6 $terminal /Sessions/1 org.kde.konsole.Session.sendText \"$(printf '{key}')\"\n"
                                  "sleep 0.5\n" for key in KEYS.get(step["agent"], [])) + ("sleep 2" if step["agent"] in KEYS else ""),
                     check=HERE / "craft_ai.py")
        for n, step in enumerate(craft_ai.STEPS, 1)
    )
    session = place / "session.sh"
    session.write_text(SESSION.format(
        wallpaper=wallpaper, tasks=TASKS, hanami=ROOT / "target" / "release" / "hanami", shots=shots, agents=agents,
        out=out, agent_home=craft_ai.HOME, prism=craft_footage.PRISM_ID, instance=name,
        game_log=game / "logs" / "latest.log",
    ))
    session.chmod(0o755)
    env = {
        "HOME": str(home),
        "XDG_RUNTIME_DIR": str(run),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_DIRS": "/var/lib/flatpak/exports/share:/usr/local/share:/usr/share",
        "XDG_SESSION_TYPE": "wayland",
        "XDG_CURRENT_DESKTOP": "KDE",
        "KDE_FULL_SESSION": "true",
        "KDE_SESSION_VERSION": "6",
        "PATH": "/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
    }
    # The session goes when this script does, however it ends: two at once
    # would share the agents' home folder.
    import signal

    desk = subprocess.Popen(
        ["dbus-run-session", "--", "kwin_wayland", "--virtual", "--width", str(SCREEN_W), "--height",
         str(SCREEN_H), "--scale", str(DESK), "--xwayland", "--no-lockscreen", "--exit-with-session", str(session)],
        env=env, cwd=home, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    signal.signal(signal.SIGTERM, lambda *_: sys.exit("stopped"))
    try:
        desk.wait(timeout=3600)
    finally:
        if desk.poll() is None:
            os.killpg(desk.pid, signal.SIGTERM)
            desk.wait(30)
        subprocess.run(["fusermount3", "-u", "-q", str(place / "run" / "doc")], stderr=subprocess.DEVNULL, check=False)
    shutil.rmtree(place, ignore_errors=True)
    if (shots / "failed").exists():
        step = craft_ai.STEPS[int((shots / "failed").read_text()) - 1]
        sys.exit(f"{step['name']} didn't do {step['prompt']!r} in time; run again")
    ok, report = craft_ai.check(len(craft_ai.STEPS))
    if not (out.exists() and (shots / "game-full.png").exists()):
        sys.exit("could not capture the desktop")
    if not ok:
        sys.exit("the agents didn't change Hanami as asked:\n" + report)


# --- Keeping the person private ----------------------------------------------


def private_words():
    """What must never show: the email addresses and names of the accounts
    the agents and the game run on, read from their sign-ins, plus anything
    in CRAFT_HIDE (comma-separated). Kept lower-case, never printed."""
    found = {word.strip().lower() for word in os.environ.get("CRAFT_HIDE", "").split(",") if word.strip()}
    claude = craft_ai.LOGINS / "claude" / ".claude.json"
    if claude.exists():
        account = json.loads(claude.read_text()).get("oauthAccount") or {}
        found |= {str(account.get(key, "")).lower() for key in ("emailAddress", "displayName")}
    codex = craft_ai.LOGINS / "codex" / ".codex" / "auth.json"
    if codex.exists():
        import base64

        token = (json.loads(codex.read_text()).get("tokens") or {}).get("id_token", "")
        if token.count(".") == 2:
            body = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            found |= {str(claims.get(key, "")).lower() for key in ("email", "name")}
    google = subprocess.run(["gcloud", "config", "get-value", "account"], capture_output=True, text=True, check=False)
    found.add(google.stdout.strip().lower())
    accounts = craft_footage.PRISM_DATA / "accounts.json"
    if accounts.exists():
        for account in json.loads(accounts.read_text()).get("accounts", []):
            found.add(str((account.get("profile") or {}).get("name", "")).lower())
    parts = set()
    for word in found:
        if len(word) < 3:
            continue
        parts.add(word)
        if "@" in word:
            parts.add(word.split("@")[0])
        parts |= {piece for piece in word.split() if len(piece) >= 4}
    return sorted(parts)


def tessdata():
    """Tesseract's English model, fetched once (the system may have none)."""
    folder = craft_footage.CACHE / "tessdata"
    if not (folder / "eng.traineddata").exists():
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sfL", "-o", str(folder / "eng.traineddata"),
                        "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata"], check=True)
    return folder


def private_boxes(path, words):
    """Boxes (x0, y0, x1, y1) of the words in a screenshot that give the
    person away, found by reading it with Tesseract. An address read with a
    letter or two wrong still counts."""
    import difflib

    small = Path(f"/tmp/craft-ocr-{os.getpid()}.png")
    Image.open(path).convert("RGB").save(small)
    read = subprocess.run(["tesseract", "--tessdata-dir", str(tessdata()), str(small), "-", "--psm", "11", "-c", "tessedit_create_tsv=1"],
                          capture_output=True, text=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                          check=False).stdout
    small.unlink(missing_ok=True)
    boxes = []
    for line in read.splitlines()[1:]:
        cells = line.split("\t")
        if len(cells) < 12 or not cells[11].strip():
            continue
        seen = re.sub(r"[^a-z0-9@._-]", "", cells[11].lower())
        # Long words and addresses count when they're part of what was read
        # (or it's part of them); a short piece of a name only on its own.
        close = "@" in seen and any("@" in word and difflib.SequenceMatcher(None, seen, word).ratio() >= 0.7
                                    for word in words)
        if close or len(seen) >= 3 and any((word in seen or (len(seen) >= 5 and seen in word))
                                           if len(word) >= 6 or "@" in word else seen.strip("._-") == word
                                           for word in words):
            x, y, w, h = map(int, cells[6:10])
            boxes.append((x - 3, y - 2, x + w + 3, y + h + 2))
    return boxes


FAKE = "sam@example.com"
HACK = "/usr/share/fonts/TTF/Hack-Regular.ttf"
# The terminal's character grid, (font size, cell width in pixels): every
# terminal in the session uses the same Konsole profile, so it's measured once.
TERM_GRID = {}


@functools.lru_cache(64)
def text_mask(word, size, cell):
    """`word` as the terminal draws it, one character per cell: (mask 0..1,
    the origin's place in it as (x, baseline))."""
    font = ImageFont.truetype(HACK, size)
    ascent, descent = font.getmetrics()
    mask = Image.new("L", (cell * len(word) + 4, ascent + descent + 4), 0)
    draw = ImageDraw.Draw(mask)
    for n, letter in enumerate(word):
        draw.text((2 + n * cell, 2 + ascent), letter, font=font, fill=255, anchor="ls")
    return np.asarray(mask, np.float32) / 255, (2, 2 + ascent)


def place(gray, box, word, size, cell):
    """Where `word` sits in a screenshot near `box`, found by matching its
    shape: (how well it matches, x, baseline)."""
    mask, (mx, my) = text_mask(word, size, cell)
    x0, y0, _, _ = box
    left, top = max(0, x0 - 14), max(0, y0 - 14)
    region = gray[top : top + mask.shape[0] + 28, left : left + mask.shape[1] + 28]
    ink = np.abs(region - np.median(region))
    norm = np.sqrt((mask**2).sum())
    best = (0.0, x0, y0)
    for dy in range(0, region.shape[0] - mask.shape[0] + 1):
        for dx in range(0, region.shape[1] - mask.shape[1] + 1):
            window = ink[dy : dy + mask.shape[0], dx : dx + mask.shape[1]]
            score = float((window * mask).sum() / (np.sqrt((window**2).sum()) * norm + 1e-6))
            if score > best[0]:
                best = (score, left + dx + mx, top + dy + my)
    return best


def grid(gray, box, word):
    """The terminal's font size and cell width, from one word it drew."""
    if not TERM_GRID:
        guess = (box[2] - box[0] - 6) / len(word)
        tries = [(place(gray, box, word, size, cell)[0], size, cell)
                 for cell in range(math.floor(guess) - 1, math.ceil(guess) + 2)
                 for size in range(round(cell / 0.602) - 2, round(cell / 0.602) + 3)]
        _, size, cell = max(tries)
        TERM_GRID["size"], TERM_GRID["cell"] = size, cell
    return TERM_GRID["size"], TERM_GRID["cell"]


def scrub(path, words, boxes=None):
    """Puts sam@example.com (or "sam" for a name) where the person's address
    or name is in one screenshot, in the terminal's own character grid: the
    word is found by its shape, the line is cleared, the fake drawn cell by
    cell in the same colour, and the rest of the line (like "(Google AI
    Pro)") moved left to follow it, as the terminal would print it. The
    same pixels always give the same result, so nothing shakes from frame to
    frame. Returns the places it covered."""
    boxes = private_boxes(path, words) if boxes is None else boxes
    if not boxes:
        return boxes
    # Kept with its see-through margin (the window's shadow), which the
    # video crops away by it.
    image = Image.open(path).convert("RGBA")
    gray = np.asarray(image.convert("L"), np.float32)
    pixels = np.asarray(image.convert("RGB"), np.int16)
    fixes = []
    for box in boxes:
        widest = max(words, key=len)
        size, cell = grid(gray, box, widest if "@" in widest else words[0])
        width = box[2] - box[0] - 6
        choices = [word for word in words if abs(len(word) * cell - width) <= 3 * cell] or list(words)
        score, x, base, word = max(place(gray, box, word, size, cell) + (word,) for word in choices)
        if score < 0.5:
            continue
        top, bottom = base - round(0.86 * size), base + round(0.26 * size)
        end = x + len(word) * cell
        band = pixels[top:bottom]
        background = np.median(band[:, max(0, x - 3 * cell) : x].reshape(-1, 3), axis=0)
        lit = np.nonzero((np.abs(band - background).sum(axis=2) > 90).any(axis=0))[0]
        last = end
        for column in lit[lit >= end]:
            if column - last > 3 * cell:
                break
            last = column + 1
        letters = pixels[top:bottom, x:end].reshape(-1, 3)
        far = np.abs(letters - background).sum(axis=1)
        ink = np.median(letters[far >= np.percentile(far, 97)], axis=0)
        fixes.append((x, base, top, bottom, end, last, word, tuple(int(v) for v in background),
                      tuple(int(v) for v in ink), image.crop((end, top, last, bottom)) if last > end else None))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(HACK, TERM_GRID.get("size", 20))
    cell = TERM_GRID.get("cell", 12)
    for x, base, top, bottom, end, last, word, background, ink, rest in fixes:
        fake = FAKE if "@" in word else "sam"
        draw.rectangle((x - 2, top, max(end, last) + 2, bottom - 1), fill=background + (255,))
        for n, letter in enumerate(fake):
            draw.text((x + n * cell, base), letter, font=font, fill=ink + (255,), anchor="ls")
        if rest:
            image.paste(rest, (x + len(fake) * cell, top))
    image.save(path)
    return boxes


def look_of(path):
    """A small picture of a shot: shots taken while nothing moved match."""
    return Image.open(path).convert("L").reduce(8).tobytes()


def read_one(args):
    path, words = args
    return private_boxes(path, words)


def scrub_all(shots):
    """Scrubs every screenshot of the session; says how many it changed.
    Each different picture is read once; a shot that looks like the one
    before it gets that one's boxes."""
    raw = shots.with_name(shots.name + "-raw")
    if raw.exists():
        for path in raw.glob("*.png"):
            shutil.copy(path, shots / path.name)
    else:
        shutil.copytree(shots, raw)
    words = private_words()
    paths = sorted(shots.glob("*.png"))
    looks = [look_of(path) for path in paths]
    first = {}
    for path, look in zip(paths, looks):
        first.setdefault(look, path)
    with multiprocessing.get_context("fork").Pool(os.cpu_count()) as pool:
        found = dict(zip(first, pool.map(read_one, [(path, words) for path in first.values()])))
    # Where reading missed the words in one shot, the same pixels in the
    # same place as a shot where it found them give them away too.
    # In the same terminal, nearly the same pixels in the same place: a
    # blinking cursor or a redraw changes a few.
    def terminal(path):
        return path.name.split("-")[0]

    known = {}
    for look, boxes in found.items():
        picture = Image.open(first[look]).convert("L")
        known.setdefault(terminal(first[look]), []).extend(
            (box, np.asarray(picture.crop(box), np.int16)) for box in boxes)
    plans = []
    for path, look in zip(paths, looks):
        boxes = list(found[look])
        if known.get(terminal(path)):
            picture = Image.open(path).convert("L")
            boxes += [box for box, pixels in known[terminal(path)] if box not in boxes
                      and np.abs(np.asarray(picture.crop(box), np.int16) - pixels).mean() < 6]
        plans.append(boxes)
    counts = [scrub(path, words, boxes) for path, boxes in zip(paths, plans)]
    changed = [path.name for path, count in zip(paths, counts) if count]
    print(f"covered personal details in {len(changed)} of {len(paths)} screenshots")
    return changed


def locate(window, full):
    """Where the opaque part of `window` sits in `full`, both screenshots:
    found coarsely on small copies, then to the pixel."""
    alpha = np.asarray(window)[..., 3]
    ys, xs = np.nonzero(alpha == 255)
    inner = np.asarray(window.convert("L"), np.float32)[ys.min() + 40 : ys.min() + 240, xs.min() + 40 : xs.min() + 440]
    big = np.asarray(full.convert("L"), np.float32)
    small, step = big[::4, ::4], 4
    patch = inner[::4, ::4]
    best = None
    for y in range(0, small.shape[0] - patch.shape[0]):
        rows = small[y : y + patch.shape[0]]
        for x in range(0, small.shape[1] - patch.shape[1], 2):
            score = np.abs(rows[:, x : x + patch.shape[1]] - patch).mean()
            if best is None or score < best[0]:
                best = (score, y, x)
    _, y0, x0 = best
    best = None
    for y in range(max(0, y0 * step - 8), y0 * step + 8):
        for x in range(max(0, x0 * step - 12), x0 * step + 12):
            score = np.abs(big[y : y + inner.shape[0], x : x + inner.shape[1]] - inner).mean()
            if best is None or score < best[0]:
                best = (score, y, x)
    _, y, x = best
    return x - xs.min() - 40, y - ys.min() - 40


def pointer(size):
    """Breeze's arrow pointer at about `size` pixels, read from the cursor
    theme (Xcursor), and its hot spot."""
    data = Path("/usr/share/icons/breeze_cursors/cursors/left_ptr").read_bytes()
    header, count = struct.unpack_from("<4xI4xI", data)
    entries = [struct.unpack_from("<III", data, header + 12 * n) for n in range(count)]
    _, _, at = min((e for e in entries if e[0] == 0xFFFD0002), key=lambda e: abs(e[1] - size))
    width, height, x, y = struct.unpack_from("<16xIIII", data, at)
    argb = np.frombuffer(data, np.uint8, width * height * 4, at + 36).reshape(height, width, 4).astype(np.float32)
    alpha = argb[..., 3:4]
    rgb = np.where(alpha > 0, argb[..., 2::-1] * 255 / np.maximum(alpha, 1), 0)
    image = np.concatenate([np.clip(rgb, 0, 255), alpha], axis=2).astype(np.uint8)
    return Image.fromarray(image, "RGBA"), (x, y)


def scrim():
    """A soft shade behind the words, so they read over any wallpaper."""
    ramp = np.clip(np.linspace(0, 1, W)[None, :] / 0.62, 0, 1)
    alpha = np.broadcast_to(0.7 * (1 - ramp * ramp * (3 - 2 * ramp)), (H, W))
    layer = Image.new("RGBA", (W, H), (8, 6, 12, 0))
    layer.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))
    return layer


def setup():
    """Things every frame shares; made once, before the workers start."""
    global WALL, WALL_BLUR, SCREEN_MASK, BACKDROP, MASK, PANEL_PAD, PANEL_SHADOW, SCRIM, NOISE, POINTER
    global TERM_FRAMES, SHOTS, MARKS, SETTLED, GAME_WINDOW, GAME_INSET, GAME_AT, GAME_SIZE, COUNTS, GRID_CELLS
    WALL = Image.open(CACHE / "desktop.png").convert("RGBA").resize((SCREEN_W * DESK, SCREEN_H * DESK), Image.LANCZOS)
    shots = CACHE / "shots"
    times = [line.split() for line in (shots / "times").read_text().splitlines()]
    MARKS, SHOTS, TERM_FRAMES, SETTLED = {}, {}, {}, {}
    for name, at in times:
        step, kind = name.split("-", 1)
        if kind.isdigit():
            if (shots / f"{name}.png").exists() and Image.open(shots / f"{name}.png").size != (SCREEN_W * DESK, SCREEN_H * DESK):
                SHOTS.setdefault(int(step), []).append((float(at), shots / f"{name}.png"))
        else:
            MARKS.setdefault(int(step), {})[kind] = float(at)
    for step, found in SHOTS.items():
        found.sort()
        window = Image.open(found[0][1]).convert("RGBA")
        ys, xs = np.nonzero(np.asarray(window)[..., 3] == 255)
        TERM_FRAMES[step] = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        inside = [(at, path) for at, path in found if at <= MARKS[step]["end"]]
        SETTLED[step] = settled_at(inside, MARKS[step]["edited"])
    # Minecraft's window: the opaque part of the shot, with the recordings'
    # picture where the game draws (below the title bar).
    window = Image.open(shots / "game-window.png").convert("RGBA")
    ys, xs = np.nonzero(np.asarray(window)[..., 3] == 255)
    GAME_WINDOW = window.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    GAME_INSET = (GAME_WINDOW.width - 1920) // 2, GAME_WINDOW.height - 1080
    GAME_AT = locate(GAME_WINDOW, Image.open(shots / "game-full.png").convert("RGBA"))
    GAME_SIZE = GAME_WINDOW.size
    COUNTS = {name: len(list((CACHE / "frames" / name).glob("*.png"))) for name in ("load", "title", "walk")}
    POINTER = pointer(24 * DESK)
    WALL_BLUR = WALL.filter(ImageFilter.GaussianBlur(30 * DESK))
    SCREEN_MASK = screenshot.rounded((SCREEN_W, SCREEN_H), 28).resize(WALL.size, Image.BICUBIC)
    cover = min(WALL.width / W, WALL.height / H)
    crop = ((WALL.width - W * cover) / 2, (WALL.height - H * cover) / 2,
            (WALL.width + W * cover) / 2, (WALL.height + H * cover) / 2)
    BACKDROP = WALL_BLUR.resize((W, H), Image.BILINEAR, box=crop).point(lambda v: int(v * 0.5))
    MASK = screenshot.rounded((PW, PH), int(16 * PANEL_SCALE))
    PANEL_PAD = 46 * DESK
    shade = Image.new("L", (PW + 2 * PANEL_PAD, PH + 2 * PANEL_PAD), 0)
    shade.paste(MASK, (PANEL_PAD, PANEL_PAD))
    small = shade.resize((shade.width // 4, shade.height // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5 * DESK))
    PANEL_SHADOW = Image.new("RGBA", shade.size, (0, 0, 0, 0))
    PANEL_SHADOW.putalpha(small.resize(shade.size, Image.BILINEAR).point(lambda v: int(v * 0.55)))
    SCRIM = scrim()
    noise = np.random.default_rng(3)
    NOISE = [noise.normal(0, GRAIN, (H, W, 1)).astype(np.float32) for _ in range(6)]
    GRID_CELLS = grid_cells()


def game_focus(zoom):
    """The camera's centre that puts the game window right of the words, its
    left edge at x 700 of the frame and its middle at the frame's middle."""
    left, top = GAME_AT[0] / DESK, GAME_AT[1] / DESK
    height = GAME_SIZE[1] / DESK
    return left + (W / 2 - 700) / zoom, top + height / 2


def camera(t):
    """Where the camera is at t: (centre x, centre y, zoom), kept on the desktop."""
    keys = [(at, *game_focus(rest[-1]), rest[-1]) if rest[0] == "game" else (at, *rest) for at, *rest in LAYOUT["camera"]]
    x, y, zoom = keys[-1][1:]
    for (start, *a), (stop, *b_) in zip(keys, keys[1:]):
        if t < stop:
            f = smooth(between(t, start, stop - start))
            x, y, zoom = a[0] + (b_[0] - a[0]) * f, a[1] + (b_[1] - a[1]) * f, a[2] * (b_[2] / a[2]) ** f
            break
    half_w, half_h = W / zoom / 2, H / zoom / 2
    x = clamp(x, half_w, SCREEN_W - half_w) if half_w < SCREEN_W / 2 else SCREEN_W / 2
    y = clamp(y, half_h, SCREEN_H - half_h) if half_h < SCREEN_H / 2 else SCREEN_H / 2
    return x, y, zoom


def on_screen(cam, x, y, size=None):
    """A point on the desktop to a point in the frame (or an image of `size`)."""
    width, height = size or (W, H)
    return (x - cam[0]) * cam[2] + width / 2, (y - cam[1]) * cam[2] + height / 2


def desktop(cam, t, index):
    """The desktop with the terminal, the panel, the game and the mouse, drawn
    as one picture and then seen through the camera. Zoomed out past the
    screen's edges, the whole screen floats over a dim copy of itself."""
    screen = WALL.copy()
    terminal_on(screen, t)
    panel_on(screen, t, index)
    game_on(screen, t)
    pointer_on(screen, t)
    zoom = cam[2]
    left, top = on_screen(cam, 0, 0)
    if W / zoom <= SCREEN_W + 0.5 and H / zoom <= SCREEN_H + 0.5:
        patch, _ = project(screen, (W, H), left, top, zoom / DESK)
        return patch
    screen.putalpha(SCREEN_MASK)
    frame = BACKDROP.copy()
    shade = Image.new("L", (W // 8, H // 8), 0)
    small = SCREEN_MASK.resize((max(1, round(SCREEN_W * zoom / 8)), max(1, round(SCREEN_H * zoom / 8))), Image.BILINEAR)
    shade.paste(small, (round(left / 8), round((top + 24 * zoom) / 8)))
    shade = shade.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR).point(lambda v: int(v * 0.6))
    frame.paste((0, 0, 0, 255), (0, 0, W, H), shade)
    patch, at = project(screen, (W, H), left, top, zoom / DESK)
    if patch:
        frame.alpha_composite(patch, at)
    return frame


# --- On top of the picture ------------------------------------------------------


def draw_keycaps(image, t):
    plus = text("+", "Regular", 36, DIM)
    for n, (keys, gone_at) in enumerate(KEYCAST):
        gone = ease(between(t, gone_at, 0.3))
        if gone >= 1 or t < keys[0][1] - 0.15:
            continue
        items = []
        for k, (label, at) in enumerate(keys):
            if k:
                items.append((plus, at, None))
            items.append((keycap(label, False), at, label))
        gap = 26
        total = sum(item[0].width for item in items) + gap * (len(items) - 1)
        (cx, cy), (dx, dy) = LAYOUT["keys"][n], LAYOUT["keys_aside"] if n == 0 else (0, 0)
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


def draw_caption(image, t, start, end, title, sub, place=None):
    leave = smooth(between(t, end - 0.25, 0.25))
    first, second = ease(between(t, start, 0.35)), ease(between(t, start + 0.07, 0.35))
    if first <= 0 or leave >= 1:
        return
    (x, y), (title_size, sub_size), align = place or LAYOUT["words"], LAYOUT["word_sizes"], LAYOUT["align"]
    heading = text(title, "SemiBold", title_size, TEXT, align=align)
    under = text(sub, "Regular", sub_size, SUB, align=align)
    put(image, bar(), (anchor(bar(), x, 4), y - 28 + 30 * (1 - first) - 16 * leave), first * (1 - leave))
    words(image, heading, (anchor(heading, x), y + 30 * (1 - first) - 16 * leave), first * (1 - leave))
    words(image, under, (anchor(under, x, 4), y + 30 + heading.height + 30 * (1 - second) - 16 * leave),
          second * (1 - leave))


def draw_agent(image, t):
    """The agent of the bar, left of the terminal: its name, its model and
    what it was asked; and under them, how much faster than real time its
    work plays (on the terminal, it would sit on some agents' own boxes)."""
    if not CUTS[0] <= t < GRID[0]:
        return
    step = step_at(t)
    agent = craft_ai.STEPS[step - 1]
    start = CUTS[step - 1]
    end = CUTS[step] if step < len(CUTS) else GRID[0]
    draw_caption(image, t, start, end + 0.05, agent["name"], f"{agent['model']}\n“{agent['prompt']}”", (148, 380))
    count = text(f"{step} / {len(CUTS)}", "Medium", 28, DIM)
    words(image, count, (152, 300), ease(between(t, start, 0.3)) * (1 - smooth(between(t, end - 0.2, 0.2))))
    working = start + b(TYPE_BEATS) <= t < start + b(WORK_BEATS)
    if working:
        badge = pill(f"▶▶ {round(speed(step))}× speed")
        put(image, badge, (148, 600),
            smooth(between(t, start + b(TYPE_BEATS), 0.15)) * (1 - smooth(between(t, start + b(WORK_BEATS) - 0.15, 0.15))))


def flash(image, t):
    """A short white flash on each cut from one agent to the next."""
    for cut in CUTS[1:]:
        if cut <= t < cut + 0.16:
            strength = 0.22 * (1 - (t - cut) / 0.16)
            image.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, round(255 * strength))))


CELL = (880, 318)


def answer_box(path, step):
    """The part of an agent's finished terminal with its answer: the lowest
    lines that talk about what it was asked (the game, the key, the look),
    read with Tesseract, the terminal's full width (its lines wrap there),
    in a window of CELL's shape. Lines in the input box at the bottom (a
    suggestion like "Bind Ctrl+Space") don't count."""
    agent = craft_ai.STEPS[step - 1]
    keys = {word.lower() for word in re.findall(r"[A-Za-z+]{4,}", agent["prompt"])} - {"make", "just", "with", "find", "open"}
    for value in agent["set"].values():
        keys |= {str(part).lower() for part in (value if isinstance(value, (set, dict)) else [value])}
    read = subprocess.run(["tesseract", "--tessdata-dir", str(tessdata()), str(path), "-", "--psm", "11", "-c",
                           "tessedit_create_tsv=1"], capture_output=True, text=True, check=False).stdout
    frame = TERM_FRAMES[step]
    hits = []
    for line in read.splitlines()[1:]:
        cells = line.split("\t")
        if len(cells) >= 12 and any(key in cells[11].lower() for key in keys if len(key) >= 4):
            hit = tuple(map(int, cells[6:10]))
            if hit[1] < frame[3] - 0.14 * (frame[3] - frame[1]):
                hits.append(hit)
    image = Image.open(path)
    left, width = frame[0], frame[2] - frame[0]
    height = round(width * CELL[1] / CELL[0])
    if not hits:
        return left, frame[3] - height, frame[2], frame[3]
    _, y, _, h = max(hits, key=lambda hit: hit[1])
    bottom = min(frame[3], y + h + round(height * 0.25))
    top = max(frame[1], bottom - height)
    return left, top, left + width, min(image.height, top + height)


def grid_cells():
    """Each agent's answer, close up, with its name and model under it:
    (sprite, label sprite) per agent, for the grid."""
    cells = []
    for step, agent in enumerate(craft_ai.STEPS, 1):
        last = [path for at, path in SHOTS[step] if at <= SETTLED[step]]
        path = last[-1] if last else SHOTS[step][-1][1]
        box = answer_box(path, step)
        cell = Image.open(path).convert("RGBA").crop(box).resize(CELL, Image.LANCZOS)
        mask = screenshot.rounded(CELL, 14)
        cell.putalpha(Image.fromarray(np.minimum(np.asarray(cell.getchannel("A")), np.asarray(mask))))
        cells.append((cell, pill(f"{agent['name']} · {agent['model']}", 28)))
    return cells


def draw_grid(image, t):
    """All six at once: the agents' terminals as they finished, popping in
    one after the other over the dimmed desktop."""
    shown = smooth(between(t, GRID[0], 0.2)) * (1 - smooth(between(t, GRID[1] - 0.25, 0.25)))
    if shown <= 0:
        return
    dim = Image.new("RGBA", (W, H), (8, 6, 12, round(200 * shown)))
    image.alpha_composite(dim)
    width, height = GRID_CELLS[0][0].size
    gap_x, gap_y, label = 40, 18, 0
    left = (W - 2 * width - gap_x) / 2
    top = (H - 3 * (height + label) - 2 * gap_y) / 2
    for n, (cell, name) in enumerate(GRID_CELLS):
        pop = ease(between(t, GRID[0] + 0.07 * n, 0.3))
        if pop <= 0:
            continue
        x = left + (n % 2) * (width + gap_x)
        y = top + (n // 2) * (height + label + gap_y)
        scale = 0.85 + 0.15 * pop
        sprite = cell.resize((round(width * scale), round(height * scale)), Image.LANCZOS) if scale < 1 else cell
        put(image, sprite, (x + (width - sprite.width) / 2, y + 20 * (1 - pop) + (height - sprite.height) / 2), pop * shown)
        # The agent's name sits on its cell's top right, where terminals are empty.
        put(image, name, (x + width - name.width - 14, y + 14 + 20 * (1 - pop)), pop * shown)


HALOS = {}


def halo(sprite):
    """A soft dark shadow under words (kept per sprite), and how far it reaches past them."""
    if id(sprite) not in HALOS:
        pad = 24
        alpha = ImageOps.expand(sprite.getchannel("A"), pad, 0).filter(ImageFilter.GaussianBlur(9))
        shadow = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
        shadow.putalpha(alpha.point(lambda v: int(v * 0.6)))
        HALOS[id(sprite)] = shadow, pad
    return HALOS[id(sprite)]


def words(image, sprite, xy, alpha):
    """Words with a soft shadow, so they read over any wallpaper."""
    shadow, pad = halo(sprite)
    put(image, shadow, (xy[0] - pad, xy[1] - pad + 3), alpha)
    put(image, sprite, xy, alpha)


def draw_end_card(image, t):
    mark, name, tagline, link = LAYOUT["end_sizes"]
    parts = [
        seal(mark),
        text("hanami", "SemiBold", name, TEXT),
        text("A small game launcher\nfor Linux and Windows.", "Regular", tagline, SUB, align=LAYOUT["align"]),
        text("hanami.lilygrove.dev", "Medium", link, ACCENT),
    ]
    for n, (sprite, (x, y)) in enumerate(zip(parts, LAYOUT["end"])):
        shown = ease(between(t, END + 0.08 * n, 0.6))
        (put if n == 0 else words)(image, sprite, (anchor(sprite, x), y + 30 * (1 - shown)), shown)


def compose(index):
    t = index / FPS
    image = desktop(camera(t), t, index)
    flash(image, t)
    put(image, SCRIM, (0, 0), smooth(between(t, CAPTIONS[0][0] - 0.4, 0.5)))
    draw_agent(image, t)
    draw_grid(image, t)
    draw_keycaps(image, t)
    for caption in CAPTIONS:
        draw_caption(image, t, *caption)
    draw_end_card(image, t)
    return image


def frame(index):
    t = index / FPS
    light = smooth(between(t, 0, 0.45)) * (1 - smooth(between(t, LENGTH - 0.5, 0.5)))
    rgb = np.asarray(compose(index).convert("RGB"), dtype=np.float32) * light + NOISE[index % len(NOISE)]
    return np.clip(rgb, 0, 255).astype(np.uint8).tobytes()


# --- Putting it together -----------------------------------------------------


def encode(out, music):
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", str(music),
         "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
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


def look():
    """The look jcode wrote: its [theme] and the folder with its petal.svg,
    copied so the panel is drawn with exactly that."""
    folder = CACHE / "look"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    shutil.copy(craft_ai.PETAL, folder / "petal.svg")
    return craft_ai.tomllib.loads(craft_ai.CONFIG.read_text())["theme"], folder


def red_share(path):
    """How much of a frame is Mojang's loading-screen red."""
    pixels = np.asarray(Image.open(path).convert("RGB").reduce(8), np.int16)
    red = (pixels[..., 0] > 180) & (pixels[..., 1] < 90) & (pixels[..., 2] < 100)
    return red.mean()


def footage_frames():
    """Frames for the game window: the loading screen, from the first red
    frame to the title screen, squeezed into its slot; the title screen; and
    the walk once the turn is under way."""
    frames = CACHE / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    probe = frames / "probe"
    probe.mkdir(parents=True)
    title = FOOTAGE / "title.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(title), "-vf", "fps=10", str(probe / "%04d.png")], check=True)
    reds = [red_share(path) for path in sorted(probe.glob("*.png"))]
    loading = next(n for n, share in enumerate(reds) if share > 0.5) / 10
    shown = next(n for n, share in enumerate(reds) if n / 10 > loading and share < 0.05) / 10 + 0.3
    shutil.rmtree(probe)

    def cut(name, source, start, length, rate=FPS):
        folder = frames / name
        folder.mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(source),
                        "-vf", f"fps={rate}", str(folder / "%04d.png")], check=True)

    needed = (TITLE - GAME) * FPS
    cut("load", title, loading, shown - loading, rate=needed / (shown - loading))
    cut("title", title, shown, WALK - TITLE + 0.5)
    cut("walk", FOOTAGE / "walk.mp4", 5.0, LENGTH - WALK + 0.5)


def check_private(out):
    """Reads the finished video four times a second; if anything personal
    still shows, the video is set aside as .unsafe.mp4 and the script stops."""
    frames = CACHE / "check"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-vf", "fps=4", str(frames / "%04d.png")], check=True)
    # Whole names and addresses only: short pieces of a name turn up inside
    # ordinary words, which the scrub may cover but this can't call a leak.
    words = [word for word in private_words() if len(word) >= 6 or "@" in word]
    paths = sorted(frames.glob("*.png"))
    with multiprocessing.get_context("fork").Pool(os.cpu_count()) as pool:
        found = pool.map(read_one, [(path, words) for path in paths])
    shutil.rmtree(frames)
    leaks = [round(n / 4, 2) for n, boxes in enumerate(found) if any(y1 - y0 > 24 for _, y0, _, y1 in boxes)]
    if leaks:
        out.rename(out.with_suffix(".unsafe.mp4"))
        sys.exit(f"personal details still show at {leaks} s; the video is set aside as .unsafe.mp4")
    print("checked: nothing personal shows")


def main():
    args = sys.argv[1:]
    if len(args) != 1:
        sys.exit(__doc__)
    out = Path(args[0]).resolve()
    CACHE.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CRAFT_REUSE") and (CACHE / "shots" / "game-full.png").exists():
        print("using the session already captured")
    else:
        print("setting up the desktop and running the agents")
        capture_desktop(CACHE / "desktop.png", CACHE / "shots")
    print("covering personal details")
    scrub_all(CACHE / "shots")
    scrub(CACHE / "desktop.png", private_words())
    rows = panel_rows((CACHE / "shots" / "list.txt").read_text())
    print("drawing the panel")
    render_panel(CACHE / "panel", look(), rows)
    print("writing the music")
    keys = [at for keys, _ in KEYCAST for _, at in keys]
    song = (MUSIC, float(HIT), GAME) if MUSIC else None
    craft_music.write_music(CACHE / "music.wav", LENGTH, END, keys, [at for at, _ in TYPED], song=song)
    print("putting it together")
    footage_frames()
    setup()
    encode(out, CACHE / "music.wav")
    check_private(out)
    thumbnail = compose(round((b(38.5)) * FPS)).convert("RGB").resize(LAYOUT["thumbnail"], Image.LANCZOS)
    thumbnail.save(out.with_name(out.stem + "-thumbnail.jpg"), quality=92)
    # The session's screenshots stay, so CRAFT_REUSE=1 can build again from them.
    for spent in ("panel", "desktop", "music.wav", "frames", "look", "icons"):
        path = CACHE / spent
        shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
    print(out)


if __name__ == "__main__":
    main()
