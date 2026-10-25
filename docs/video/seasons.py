"""Makes Hanami's "seasons" video: the panel is open with sakura falling,
then someone asks their AI in a terminal for autumn, snow, and sakura again,
and the panel follows. The desktop is a real KDE Plasma session drawn off
screen, the terminal runs Claude Code for real against a stand-in server
(docs/seasons_ai.py), and the panel is drawn by the panel_frames example.
The music is an original koto piece (docs/seasons_music.py) or a song.

    python3 docs/seasons.py seasons.mp4
    python3 docs/seasons.py --tall seasons-tall.mp4
    python3 docs/seasons.py --music song.mp3 --bpm 107.5 --hit 31.2 seasons.mp4
    python3 docs/seasons.py --no-grain seasons.mp4

Writes the video (60 fps, about 24 seconds) and a thumbnail next to it:
1920 x 1080, or 1080 x 1920 with --tall. --music plays a song instead:
--bpm is its tempo and --hit the second in it the panel should turn to autumn
on, a downbeat where the song kicks in; the whole edit follows that beat.
--no-grain leaves out the faint film grain, for places like Discord that
re-encode uploads so roughly that grain turns into blotches.
Needs Rust, ffmpeg, Pillow, NumPy and SciPy; KDE Plasma with Konsole and
Spectacle; Claude Code (`claude` on PATH, or CLAUDE=/path/to/claude; no
account needed); and a few minutes. Frames are kept in ~/.cache/hanami-seasons
while it runs.
"""

import functools
import http.server
import json
import math
import multiprocessing
import os
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import screenshot  # noqa: E402
import seasons_ai  # noqa: E402
import seasons_music  # noqa: E402


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
GRAIN = 0.0 if "--no-grain" in sys.argv and not sys.argv.remove("--no-grain") else 1.2
if MUSIC and not (BPM and HIT):
    sys.exit("--music needs --bpm and --hit too")
FPS = 60
BEAT = 60 / float(BPM or 90)
PANEL_SCALE = 2.0
PW, PH = int(340 * PANEL_SCALE), int(440 * PANEL_SCALE)
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hanami-seasons"

TEXT = (236, 230, 238)
DIM = (155, 147, 163)
SUB = (226, 220, 232)
ACCENT = (244, 182, 200)
INK = (23, 20, 29)


def b(beats):
    return beats * BEAT


# The story, on the beat. The panel is open from the first frame; a click on
# the terminal hides it, a sentence is typed to the AI, the AI writes the
# files, and Ctrl+Alt+H opens the panel in its new look. Three times, each
# quicker than the last.
AWAY = [b(3.5), b(16.5), b(23.5)]
TYPE = [(b(4.5), b(7.5)), (b(17.0), b(18.5)), (b(24.0), b(25.25))]
HOTKEY = [[b(11.5), b(11.75), b(12.0)], [b(20.75), b(21.0), b(21.25)], [b(27.25), b(27.5), b(27.75)]]
REVEAL = [keys[-1] for keys in HOTKEY]
KEYCAST = [([("Ctrl", a), ("Alt", c), ("H", h)], h + 0.5) for a, c, h in HOTKEY]
CAPTIONS = [
    (b(0.5), b(3.25), "Sakura is\nthe default.", "Petals fall behind your games."),
    (b(12.5), b(16.0), "Your look,\nfrom one sentence.", "Your AI writes two small files."),
    (b(21.5), b(23.25), "Or snow.", "Ask again."),
    (b(28.0), b(31.25), "Or back.", "Delete the files."),
]
END = b(32.0)
LENGTH = END + 2.65
FRAMES = round(LENGTH * FPS)

# The desktop the video plays on: KDE Plasma as it comes out of the box
# (Breeze Dark, the "Mountain" wallpaper that Plasma 6.2 shipped with, by
# Marc Diemert, CC BY-SA 4.0, fetched from KDE's wallpaper collection),
# started in a throwaway session with its own empty home folder, so nothing
# personal shows. Hanami sits in the tray and a terminal is open on the
# right. Sizes are in logical pixels; the desktop is captured at twice that
# so the camera can move in close.
SCREEN_W, SCREEN_H = 1920, 1080
DESK = 2
PANEL_BOX = ((SCREEN_W - 340) / 2, (SCREEN_H - 440) / 2, 340, 440)
LAUNCHERS = ",".join(
    ["preferred://filemanager"]
    + [f"applications:{app}.desktop" for app in ("firefox", "steam", "discord", "org.kde.konsole")]
)
WALLPAPER = "https://raw.githubusercontent.com/KDE/plasma-workspace-wallpapers/master/Mountain/contents/images/5120x2880.png"
TERMINAL = (1170, 170, 620, 560)
REST = (1250, 905)
TERM_CLICK = (TERMINAL[0] + 330, TERMINAL[1] + 430)
MOUSE = [(0, REST), (AWAY[0] - 0.9, REST), (AWAY[0] - 0.05, TERM_CLICK)]
MINIMISE = """for (const w of workspace.windowList()) {
    if (w.resourceClass.indexOf("konsole") >= 0) {
        w.minimized = true;
    }
}
"""
# Claude Code is captured on its own as the scene plays: a shot a few times
# a second from before the first sentence is typed until the last answer has
# settled, with the moment each sentence starts and is sent noted. Then the
# terminal is minimised, so the taskbar shows it running, and the desktop is
# captured.
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
konsole --hide-menubar --profile Video -qwindowgeometry {size} -e '{claude}' &
sleep 12
shot() {{
    spectacle --background --nonotify --activewindow --output '{shots}'/$1.png
    echo "$1 $(date +%s.%N)" >> '{shots}/times'
}}
mark() {{
    echo "$1 $(date +%s.%N)" >> '{shots}/times'
}}
shot idle
terminal=$(qdbus6 | grep -m1 org.kde.konsole)
send() {{
    printf '%s\\n' "$1" | fold -w1 | while IFS= read -r c; do
        qdbus6 $terminal /Sessions/1 org.kde.konsole.Session.sendText "$c"
        sleep 0.07
    done
}}
( n=100; while [ ! -f '{shots}/stop' ]; do shot $n; n=$((n + 1)); done ) &
shooter=$!
sleep 1
{typing}
sleep {settle}
touch '{shots}/stop'
wait $shooter
dbus-send --session --print-reply --dest=org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript \\
    string:'{minimise}' string:minimise > /dev/null
dbus-send --session --print-reply --dest=org.kde.KWin /Scripting org.kde.kwin.Scripting.start > /dev/null
sleep 3
spectacle --background --nonotify --fullscreen --output '{out}'
"""
TYPING = """mark type{n}
send '{prompt}'
mark enter{n}
qdbus6 $terminal /Sessions/1 org.kde.konsole.Session.sendText "$(printf '\\r')"
sleep {wait}
"""
# How long the AI is given for each answer in the session, in seconds; the
# video plays each stretch at whatever speed fits its slot.
WAITS = (8, 7, 7)
TASKS = (
    'panels().forEach(p => p.widgets("org.kde.plasma.icontasks").forEach(w => {'
    ' w.currentConfigGroup = ["General"]; w.writeConfig("launchers", "%s"); }))' % LAUNCHERS
)

# Where everything sits, and the camera: (time, centre x, centre y, zoom) on
# the desktop, eased from one to the next. The first two looks get a close
# camera that moves between the panel and the terminal; the last two share
# one wide shot, so the panel pops in beside the terminal.
WIDE = (1152, 520, 1.25)
LAYOUTS = {
    "wide": dict(
        size=(1920, 1080),
        align="left",
        keys=[(960, 900), (1370, 930), (1370, 930)],
        keys_aside=(0, 40),
        camera=[
            (0, 790, 540, 1.7),
            (AWAY[0] + 0.1, 790, 540, 1.7),
            (AWAY[0] + 0.9, 1371, 457, 1.75),
            (HOTKEY[0][0] - 0.5, 1371, 457, 1.75),
            (HOTKEY[0][0] + 0.4, 790, 540, 1.7),
            (AWAY[1] - 0.3, 790, 540, 1.7),
            (AWAY[1] + 0.5, *WIDE),
            (END - 0.2, *WIDE),
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
        keys=[(540, 1390), (540, 1440), (540, 1440)],
        keys_aside=(0, 60),
        camera=[
            (0, 960, 480, 2.0),
            (AWAY[0] + 0.1, 960, 480, 2.0),
            (AWAY[0] + 0.9, 1480, 540, 1.6),
            (HOTKEY[0][0] - 0.5, 1480, 540, 1.6),
            (HOTKEY[0][0] + 0.4, 960, 480, 2.0),
            (AWAY[1] - 0.3, 960, 480, 2.0),
            (AWAY[1] + 0.5, 1180, 520, 1.3),
            (END - 0.2, 1180, 520, 1.3),
            (END + 0.8, 960, 540, 0.5),
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

# The three looks, as the AI writes them (the rows of the table in GUIDE.md,
# "Changing the look"), and the petal picture that goes with each.
LOOKS = [
    (None, None),
    (seasons_ai.AUTUMN, ROOT / "notes" / "maple.svg"),
    (seasons_ai.SNOW, ROOT / "notes" / "snow.svg"),
    (None, None),
]


# --- The panel ---------------------------------------------------------------


def shown_look(t):
    """Which look the panel has at t: 0 sakura, then autumn, snow, sakura."""
    return sum(t >= at - 0.2 for at in REVEAL)


def look_folder(index):
    return CACHE / f"look-{index}"


def panel_state(t):
    pinned = {"Hades"}
    games = sorted(GAMES, key=lambda game: (game[0] not in pinned, game[0].lower()))
    rows = [
        {
            "name": name,
            "label": f"pinned · {label}" if name in pinned else label,
            "icon": f"site/assets/games/{icon}.png",
            "pinned": name in pinned,
        }
        for name, label, icon in games
    ]
    theme, petal = LOOKS[shown_look(t)]
    state = {"time": t, "games": rows, "total": len(GAMES), "selected": 0, "pointer": None}
    if theme:
        state["theme"] = theme
        state["look"] = str(look_folder(shown_look(t)))
    return state


def mouse(t):
    """Where the mouse is on the desktop at t."""
    for (start, a), (stop, z) in zip(MOUSE, MOUSE[1:]):
        if t < stop:
            f = smooth(between(t, start, stop - start))
            return a[0] + (z[0] - a[0]) * f, a[1] + (z[1] - a[1]) * f
    return MOUSE[-1][1]


def render_panel(frames):
    shutil.rmtree(frames, ignore_errors=True)
    for index, (_, petal) in enumerate(LOOKS):
        if petal:
            look_folder(index).mkdir(parents=True, exist_ok=True)
            shutil.copy(petal, look_folder(index) / "petal.svg")
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


# --- The terminal ------------------------------------------------------------


@functools.lru_cache(4)
def term_shot(path):
    return Image.open(path).convert("RGBA").crop(TERM_FRAME)


def same(a, b):
    """Two terminal shots that look alike."""
    look = lambda path: np.asarray(Image.open(path).convert("L").reduce(4), np.int16)
    return np.abs(look(a) - look(b)).mean() < 0.5


def settled_at(shots, since, before):
    """When the terminal stopped changing between two moments: the time of
    the first shot after `since` that looks like the last one before `before`."""
    last = [path for at, path in shots if at < before][-1]
    return next((at for at, path in shots if since <= at < before and same(path, last)), before)


def term_at(t):
    """The terminal screenshot to show at t. Each stretch of the session (a
    sentence being typed; the AI answering) plays in its own slot of the
    video, at whatever speed fits, and holds still in between."""
    wall = None
    for (start, end), (since, until) in zip(TERM_SLOTS, TERM_STRETCHES):
        if t < start:
            break
        wall = until if t >= end else since + (t - start) / (end - start) * (until - since)
    if wall is None:
        return TERM_IDLE
    shown = TERM_IDLE
    for at, path in TERM_SHOTS:
        if at <= wall:
            shown = path
    return shown


def terminal_on(screen, t):
    put(screen, term_shot(term_at(t)), (TERMINAL[0] * DESK, TERMINAL[1] * DESK))


def pointer_on(screen, t):
    """The mouse pointer, pressed in a little on each click."""
    sprite, (hx, hy) = POINTER
    press = max(0.0, *(1 - abs(t - at) / 0.12 for at in AWAY))
    scale = 1 - 0.12 * press
    if scale < 1:
        sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.LANCZOS)
    x, y = mouse(t)
    put(screen, sprite, (x * DESK - hx * scale, y * DESK - hy * scale))


def panel_on(screen, t, index):
    """The real panel where Hanami opens it, over frosted wallpaper. Like the
    app, it fades in and out over 140 ms; a click on the terminal hides it,
    the hotkey brings it back in its new look, and the end card takes its place."""
    opacity = 1 - between(t, AWAY[0], 0.14)
    for reveal, away in zip(REVEAL, AWAY[1:] + [END - 0.2]):
        opacity += between(t, reveal, 0.14) * (1 - between(t, away, 0.14))
    opacity = clamp(opacity)
    if opacity <= 0:
        return
    left, top = round(PANEL_BOX[0] * DESK), round(PANEL_BOX[1] * DESK)
    put(screen, PANEL_SHADOW, (left - PANEL_PAD, top - PANEL_PAD + 16 * DESK), opacity)
    # Frosted glass: the blurred desktop, seen through the panel.
    frosted = WALL_BLUR.crop((left, top, left + PW, top + PH))
    screen.paste(frosted, (left, top), MASK.point(lambda v: int(v * opacity)))
    raw = (CACHE / "panel" / f"{index:05}.rgba").read_bytes()
    put(screen, Image.frombytes("RGBa", (PW, PH), raw).convert("RGBA"), (left, top), opacity)


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




# --- The picture -------------------------------------------------------------


def capture_desktop(out, shots):
    """Starts the throwaway Plasma session off screen and saves a screenshot of
    the desktop, and of Claude Code in the terminal as the scene plays."""
    claude = os.environ.get("CLAUDE") or shutil.which("claude")
    if not claude:
        sys.exit("needs Claude Code: install it, or set CLAUDE=/path/to/claude")
    subprocess.run(["cargo", "build", "-q", "--release", "-p", "hanami"], cwd=ROOT, check=True)
    place = CACHE / "desktop"
    shutil.rmtree(place, ignore_errors=True)
    shutil.rmtree(shots, ignore_errors=True)
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
        "[Appearance]\nColorScheme=Breeze\nFont=Hack,24\n\n"
        "[General]\nName=Video\nParent=FALLBACK/\n"
    )
    (place / "minimise.js").write_text(MINIMISE)
    wallpaper = CACHE / "Mountain.png"
    if not wallpaper.exists():
        subprocess.run(["curl", "-sfL", "-o", str(wallpaper), WALLPAPER], check=True)
    start = seasons_ai.prepare_claude(Path(claude).resolve())
    typing = "".join(
        TYPING.format(n=n, prompt=prompt, wait=wait) for n, (prompt, wait) in enumerate(zip(seasons_ai.PROMPTS, WAITS))
    )
    session = place / "session.sh"
    session.write_text(SESSION.format(
        tasks=TASKS, hanami=ROOT / "target" / "release" / "hanami", size=f"{TERMINAL[2] * DESK}x{TERMINAL[3] * DESK}",
        claude=start, shots=shots, typing=typing, settle=2, minimise=place / "minimise.js", out=out,
        wallpaper=wallpaper,
    ))
    session.chmod(0o755)
    env = {
        "HOME": str(home),
        "XDG_RUNTIME_DIR": str(run),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_SESSION_TYPE": "wayland",
        "XDG_CURRENT_DESKTOP": "KDE",
        "KDE_FULL_SESSION": "true",
        "KDE_SESSION_VERSION": "6",
        "PATH": "/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
    }
    server = http.server.ThreadingHTTPServer(("127.0.0.1", seasons_ai.STAND_IN_PORT), seasons_ai.StandIn)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        subprocess.run(
            ["dbus-run-session", "--", "kwin_wayland", "--virtual", "--width", str(SCREEN_W), "--height",
             str(SCREEN_H), "--scale", str(DESK), "--xwayland", "--exit-with-session", str(session)],
            env=env, cwd=home, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    finally:
        server.shutdown()
        shutil.rmtree(seasons_ai.CLAUDE_HOME, ignore_errors=True)
    if not (out.exists() and (shots / "idle.png").exists()):
        sys.exit("could not capture the desktop")


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
    if LAYOUT["align"] == "center":
        ramp = np.clip(np.linspace(0, 1, H)[:, None] / 0.52, 0, 1)
    else:
        ramp = np.clip(np.linspace(0, 1, W)[None, :] / 0.62, 0, 1)
    alpha = np.broadcast_to(0.7 * (1 - ramp * ramp * (3 - 2 * ramp)), (H, W))
    layer = Image.new("RGBA", (W, H), (8, 6, 12, 0))
    layer.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))
    return layer


def setup():
    """Things every frame shares; made once, before the workers start."""
    global WALL, WALL_BLUR, SCREEN_MASK, BACKDROP, MASK, PANEL_PAD, PANEL_SHADOW, SCRIM, NOISE, POINTER
    global TERM_FRAME, TERM_IDLE, TERM_SHOTS, TERM_SLOTS, TERM_STRETCHES
    WALL = Image.open(CACHE / "desktop.png").convert("RGBA").resize((SCREEN_W * DESK, SCREEN_H * DESK), Image.LANCZOS)
    shots = CACHE / "claude"
    window = Image.open(shots / "idle.png").convert("RGBA")
    ys, xs = np.nonzero(np.asarray(window)[..., 3] == 255)
    TERM_FRAME = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    WALL.alpha_composite(window, (TERMINAL[0] * DESK - TERM_FRAME[0], TERMINAL[1] * DESK - TERM_FRAME[1]))
    TERM_IDLE = shots / "idle.png"
    times = dict(line.split() for line in (shots / "times").read_text().splitlines())
    marks = {name: float(at) for name, at in times.items() if not name.isdigit()}
    TERM_SHOTS = sorted((float(at), shots / f"{name}.png") for name, at in times.items() if name.isdigit())
    # Each sentence plays in its typing slot; each answer in the slot before
    # the hotkey, up to the moment the terminal settled.
    TERM_SLOTS, TERM_STRETCHES = [], []
    for n, ((typed, sent), keys) in enumerate(zip(TYPE, HOTKEY)):
        next_typed = marks.get(f"type{n + 1}", TERM_SHOTS[-1][0] + 1)
        TERM_SLOTS += [(typed, sent), (sent, keys[0] - 0.3)]
        TERM_STRETCHES += [(marks[f"type{n}"], marks[f"enter{n}"]),
                           (marks[f"enter{n}"], settled_at(TERM_SHOTS, marks[f"enter{n}"] + 1.5, next_typed))]
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


def desktop(cam, t, index):
    """The desktop with the terminal, the panel and the mouse, drawn as one
    picture and then seen through the camera. Zoomed out past the screen's
    edges, the whole screen floats over a dim copy of itself."""
    screen = WALL.copy()
    terminal_on(screen, t)
    panel_on(screen, t, index)
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
        # The first keys step aside when the panel opens, to make room for it.
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


def draw_caption(image, t, start, end, title, sub):
    leave = smooth(between(t, end - 0.3, 0.3))
    first, second = ease(between(t, start, 0.5)), ease(between(t, start + 0.1, 0.5))
    if first <= 0 or leave >= 1:
        return
    (x, y), (title_size, sub_size), align = LAYOUT["words"], LAYOUT["word_sizes"], LAYOUT["align"]
    heading = text(title, "SemiBold", title_size, TEXT, align=align)
    under = text(sub, "Regular", sub_size, SUB, align=align)
    put(image, bar(), (anchor(bar(), x, 4), y - 28 + 30 * (1 - first) - 16 * leave), first * (1 - leave))
    words(image, heading, (anchor(heading, x), y + 30 * (1 - first) - 16 * leave), first * (1 - leave))
    words(image, under, (anchor(under, x, 4), y + 30 + heading.height + 30 * (1 - second) - 16 * leave),
          second * (1 - leave))


HALOS = {}


def halo(sprite):
    """A soft dark shadow under words (kept per sprite; the words come from
    text(), which keeps its sprites), and how far it reaches past them."""
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
    put(image, SCRIM, (0, 0), smooth(between(t, CAPTIONS[0][0] - 0.4, 0.5)))
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
    keys = [at for keys, _ in KEYCAST for _, at in keys]
    song = (MUSIC, float(HIT), REVEAL[0]) if MUSIC else None
    seasons_music.write_music(CACHE / "music.wav", LENGTH, END, keys, AWAY, song=song)
    print("setting up the desktop")
    capture_desktop(CACHE / "desktop.png", CACHE / "claude")
    print("putting it together")
    setup()
    encode(out, CACHE / "music.wav")
    thumbnail = compose(round((END + 1.6) * FPS)).convert("RGB").resize(LAYOUT["thumbnail"], Image.LANCZOS)
    thumbnail.save(out.with_name(out.stem + "-thumbnail.jpg"), quality=92)
    shutil.rmtree(CACHE)
    print(out)


if __name__ == "__main__":
    main()
