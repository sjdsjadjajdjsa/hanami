"""Makes Hanami's short video: someone on a real KDE Plasma desktop presses
the hotkey and uses the real panel (drawn off screen by the panel_frames
example), with titles and an original koto piece written here (no samples,
nothing borrowed).

    python3 docs/video.py hanami.mp4
    python3 docs/video.py --tall hanami-tall.mp4

Writes the video (60 fps, 11 seconds) and a thumbnail next to it: 1920 x 1080
for YouTube, or 1080 x 1920 with --tall for Shorts, TikTok and Reels. Needs
Rust, ffmpeg, Pillow, NumPy and SciPy, KDE Plasma with Spectacle and Dolphin
for the desktop, and a minute or two. Frames are kept
in ~/.cache/hanami-video while it runs.
"""

import functools
import json
import textwrap
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.io import wavfile
from fontTools.ttLib import TTFont
from scipy.signal import butter, fftconvolve, istft, sosfilt, stft

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import screenshot  # noqa: E402

FPS = 60
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


# The story, on the beat of the music. Keys pressed show up on screen, a
# group at a time, until the time after each group.
KEYCAST = [
    ([("Ctrl", b(0.5)), ("Alt", b(1.0)), ("H", b(1.5))], b(1.5)),
    ([("Ctrl", b(15.5)), ("Shift", b(15.75)), ("V", b(16.0))], b(16.5)),
    ([("Enter", b(16.75))], b(17.25)),
]
REVEAL = b(1.5)
CAPTIONS = [
    (b(2.0), b(5.25), "Every game,\none key away.", "Steam, Epic, GOG, Heroic and more."),
    (b(5.5), b(8.5), "Find any game\nin a keystroke.", "First letters and small typos work too."),
    (b(8.75), b(12.0), "Your list,\nyour way.", "Pin, rename or hide any game."),
    (b(12.5), b(20.75), "Questions?\nAsk your AI.", "The ? button copies a guide it can read."),
]
TYPED = [(b(5.5), "h"), (b(6.0), "hk"), (b(8.0), "h"), (b(8.25), "")]
DOWNS = [b(8.75), b(9.0), b(9.25)]
TAB, ENTER = b(9.75), b(10.75)
CLICKS = [at for at, _ in TYPED] + DOWNS + [TAB, ENTER]
# The mouse clicks ?, which copies the prompt, then the terminal, which hides
# the panel; the prompt is pasted into Claude Code there and sent.
ASK, AWAY = b(13.5), b(15.0)
PASTE, SEND = b(16.0), b(16.75)
TOOL, ANSWER, DONE = b(17.5), b(18.25), b(20.5)
END = b(21.5)
LENGTH = END + 2.65
FRAMES = round(LENGTH * FPS)


# The desktop the video plays on: KDE Plasma as it comes out of the box
# (Breeze Dark, the "Waterfall" wallpaper by Krystian Zajdel, CC BY-SA 4.0),
# started in a throwaway session with its own empty home folder, so nothing
# personal shows. Hanami sits in the tray and a terminal is open on the right. Sizes are in
# logical pixels; the desktop is captured at twice that so the camera can
# move in close. Hanami opens in the middle of the screen under the mouse
# (desktop::centre_on_pointer).
SCREEN_W, SCREEN_H = 1920, 1080
DESK = 2
PANEL_BOX = ((SCREEN_W - 340) / 2, (SCREEN_H - 440) / 2, 340, 440)
LAUNCHERS = ",".join(
    ["preferred://filemanager"]
    + [f"applications:{app}.desktop" for app in ("firefox", "steam", "discord", "org.kde.konsole")]
)
TERMINAL = (1170, 170, 620, 560)
HELP = (296, 21)
REST = (1250, 905)
MOUSE = [
    (0, REST),
    (b(12.0), REST),
    (b(12.9), (PANEL_BOX[0] + HELP[0], PANEL_BOX[1] + HELP[1])),
    (b(14.25), (PANEL_BOX[0] + HELP[0], PANEL_BOX[1] + HELP[1])),
    (b(14.9), (TERMINAL[0] + 330, TERMINAL[1] + 430)),
]
MINIMISE = """for (const w of workspace.windowList()) {
    if (w.resourceClass.indexOf("konsole") >= 0) {
        w.minimized = true;
    }
}
"""
# The terminal is captured on its own, then minimised, so the taskbar shows
# it running; the video puts it back on the right of the screen.
SESSION = """#!/bin/sh
plasmashell --no-respawn &
sleep 10
plasma-apply-lookandfeel --apply org.kde.breezedark.desktop --resetLayout
sleep 4
plasma-apply-wallpaperimage /usr/share/wallpapers/Next
qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '{tasks}'
sleep 2
kquitapp6 plasmashell
plasmashell --no-respawn &
env -u WAYLAND_DISPLAY '{hanami}' --hidden &
konsole --hide-menubar -qwindowgeometry {size} -e '{claude}' &
sleep 10
spectacle --background --nonotify --activewindow --output '{window}'
dbus-send --session --print-reply --dest=org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript \\
    string:'{minimise}' string:minimise > /dev/null
dbus-send --session --print-reply --dest=org.kde.KWin /Scripting org.kde.kwin.Scripting.start > /dev/null
sleep 3
spectacle --background --nonotify --fullscreen --output '{out}'
"""
TASKS = (
    'panels().forEach(p => p.widgets("org.kde.plasma.icontasks").forEach(w => {'
    ' w.currentConfigGroup = ["General"]; w.writeConfig("launchers", "%s"); }))' % LAUNCHERS
)

# Where everything sits, and the camera: (time, centre x, centre y, zoom) on
# the desktop, eased from one to the next. The tall layout keeps the words
# and the panel clear of the buttons and captions Shorts, TikTok and Reels
# draw on top.
LAYOUTS = {
    "wide": dict(
        size=(1920, 1080),
        align="left",
        keys=[(960, 900), (430, 880), (430, 880)],
        keys_aside=(0, 40),
        camera=[
            (0, 960, 540, 1.0),
            (REVEAL + 0.1, 960, 540, 1.0),
            (REVEAL + 0.9, 790, 540, 1.7),
            (b(14.75), 780, 540, 1.76),
            (b(15.75), 1260, 457, 1.55),
            (END - 0.2, 1262, 460, 1.57),
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
            (0, 960, 540, 0.5),
            (REVEAL + 0.1, 960, 540, 0.5),
            (REVEAL + 1.0, 960, 480, 2.0),
            (b(14.75), 960, 486, 1.98),
            (b(15.75), 1480, 540, 1.6),
            (END - 0.2, 1480, 540, 1.62),
            (END + 0.8, 960, 540, 0.5),
        ],
        # The terminal fills the tall frame, so the last words leave first.
        ask_until=b(15.25),
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
    x, y = mouse(t)
    x, y = x - PANEL_BOX[0], y - PANEL_BOX[1]
    inside = 0 <= x < PANEL_BOX[2] and 0 <= y < PANEL_BOX[3] and t < AWAY
    return {
        "time": t, "games": rows, "total": len(GAMES), "query": query, "selected": selected, "acting": acting,
        "notice": "Copied. Paste it into your AI." if t >= ASK else "", "pointer": [x, y] if inside else None,
    }


def mouse(t):
    """Where the mouse is on the desktop at t."""
    for (start, a), (stop, z) in zip(MOUSE, MOUSE[1:]):
        if t < stop:
            f = smooth(between(t, start, stop - start))
            return a[0] + (z[0] - a[0]) * f, a[1] + (z[1] - a[1]) * f
    return MOUSE[-1][1]


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


# --- The terminal ------------------------------------------------------------

TERM_BG = (35, 38, 39)
TERM_TEXT = (252, 252, 252)
TERM_DIM = (153, 153, 153)
CLAUDE = (215, 119, 87)
GREEN = (78, 186, 101)
# Konsole's default font, Hack at 10 pt, and its line height.
TERM_SIZE, TERM_LINE = 40 / 3, 16
TERM_FONTS = ("Hack", "DejaVu Sans Mono", "Noto Sans Symbols", "Noto Sans Symbols 2")
LISTED = ["Hades\tepic", "Hollow Knight\tgog", "Celeste\tsteam", "Dead Cells\tsteam", "OpenTTD\tport",
          "Stardew Valley\tsteam"]
REPLY = (
    "Hanami is a small game launcher that lives in your tray.\n\n"
    "- Open or close it with Ctrl+Alt+H or a click on the tray flower; Esc or a click anywhere else hides it.\n"
    "- It found 6 games: Celeste, Dead Cells and Stardew Valley from Steam, Hades from Epic, Hollow Knight "
    "from GOG, and OpenTTD as a port.\n"
    "- Add your own with the + button, or hide one with Tab, then Hide.\n"
    "- Pins, names, hidden games and the hotkey live in ~/.config/hanami/config.toml.\n\n"
    "What would you like to do first?"
)


@functools.lru_cache(None)
def font_file(name):
    return subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True).stdout


@functools.lru_cache(None)
def charset(path):
    return set(TTFont(path, fontNumber=0).getBestCmap())


@functools.lru_cache(None)
def glyph_font(ch, bold):
    """Hack, or the first fallback font that has the character, as Konsole does."""
    for name in TERM_FONTS:
        name = f"{name}:bold" if bold and name == "Hack" else name
        if ord(ch) in charset(font_file(name)):
            return ImageFont.truetype(font_file(name), round(TERM_SIZE * DESK))
    return glyph_font("?", bold)


def term_rows(t, cols):
    """What Claude Code shows at t: rows of (text, colour, bold) runs."""
    inner = 52

    def boxed(*runs):
        used = sum(len(words) for words, _, _ in runs)
        return (("│", CLAUDE, False), *runs, (" " * (inner - used), TERM_TEXT, False), ("│", CLAUDE, False))

    rows = [
        (("[alex@desktop ~]$ claude", TERM_TEXT, False),),
        (("╭" + "─" * inner + "╮", CLAUDE, False),),
        boxed((" ✻ ", CLAUDE, False), ("Welcome to Claude Code!", TERM_TEXT, True)),
        boxed(),
        boxed(("   /help for help, /status for your current setup", TERM_DIM, False)),
        boxed(),
        boxed(("   cwd: /home/alex", TERM_DIM, False)),
        (("╰" + "─" * inner + "╯", CLAUDE, False),),
        (),
    ]
    if t >= SEND:
        rows += [(("> " + PASTED, TERM_DIM, False),), ()]
    if t >= TOOL:
        rows.append((("● ", GREEN, False), ("Bash", TERM_TEXT, True), ("(hanami --list)", TERM_TEXT, False)))
        listed = [line.expandtabs(16) for line in LISTED[:3]] + [f"… +{len(LISTED) - 3} lines (ctrl+o to expand)"]
        rows += [(("  ⎿  " if n == 0 else "     ", TERM_DIM, False), (line, TERM_DIM, False)) for n, line in enumerate(listed)]
        rows.append(())
    if t >= ANSWER:
        shown = REPLY[: math.ceil(len(REPLY) * between(t, ANSWER, DONE - ANSWER))]
        if t < DONE and " " in shown:
            shown = shown[: shown.rindex(" ")]
        for n, part in enumerate(shown.split("\n")):
            hang = "    " if part.startswith("- ") else "  "
            lines = textwrap.wrap(("● " if n == 0 else "  ") + part, cols - 1, subsequent_indent=hang) or [""]
            rows += [((line, TERM_TEXT, False),) for line in lines]
    if SEND <= t < DONE:
        spin = "·✢✳✶✻✽"[int(t * 8) % 6]
        rows += [((f"{spin} Thinking… ", CLAUDE, False), ("(esc to interrupt)", TERM_DIM, False)), ()]
    rule = (("─" * cols, TERM_DIM, False),)
    typed = PASTED if PASTE <= t < SEND else ""
    rows += [rule, (("> " + typed, TERM_TEXT, False), ("█", (190, 190, 190), False)), rule,
             (("  ? for shortcuts", TERM_DIM, False),)]
    return rows


@functools.lru_cache(512)
def term_row(row, width, cell):
    """One row of the terminal. Lines and rounded corners are drawn, like
    Konsole does, so boxes join up."""
    height = TERM_LINE * DESK
    image = Image.new("RGBA", (width, height), TERM_BG + (255,))
    draw = ImageDraw.Draw(image)
    col, mid, line = 0, height / 2, DESK
    for words, colour, bold in row:
        fill = colour + (255,)
        for ch in words:
            x = 2 * DESK + col * cell
            cx, r = x + cell / 2, cell / 2
            if ch == "─":
                draw.line((x, mid, x + cell, mid), fill=fill, width=line)
            elif ch == "│":
                draw.line((cx, 0, cx, height), fill=fill, width=line)
            elif ch in "╭╮╰╯":
                down, right = ch in "╭╮", ch in "╭╰"
                ox, oy = cx + (r if right else -r), mid + (r if down else -r)
                start = {"╭": 180, "╮": 270, "╰": 90, "╯": 0}[ch]
                draw.arc((ox - r, oy - r, ox + r, oy + r), start, start + 90, fill=fill, width=line)
                draw.line((cx, oy, cx, height if down else 0), fill=fill, width=line)
            elif ch == "█":
                draw.rectangle((x, 0, x + cell - 1, height - 1), fill=fill)
            elif ch != " ":
                draw.text((cx, mid), ch, font=glyph_font(ch, bold), fill=fill, anchor="mm")
            col += 1
    return image


def terminal(t):
    """Claude Code in the terminal at t, at the desktop's scale."""
    width, height = round(TERM_BOX[2] * DESK), round(TERM_BOX[3] * DESK)
    cell = glyph_font("M", False).getlength("M")
    cols, count = int((width - 4 * DESK) // cell), int(height // (TERM_LINE * DESK))
    image = Image.new("RGBA", (width, height), TERM_BG + (255,))
    for n, row in enumerate(term_rows(t, cols)[-count:]):
        image.paste(term_row(row, width, cell), (0, n * TERM_LINE * DESK))
    return image


def draw_terminal(image, cam, t):
    x, y, width, height = TERM_BOX
    zoom = cam[2]
    left, top = on_screen(cam, x, y)
    put(image, terminal(t).resize((round(width * zoom), round(height * zoom)), Image.LANCZOS), (left, top))


def draw_pointer(image, cam, t):
    """The mouse pointer, pressed in a little on each click."""
    sprite, (hx, hy) = POINTER
    press = max(0.0, *(1 - abs(t - at) / 0.12 for at in (ASK, AWAY)))
    scale = cam[2] / DESK * (1 - 0.12 * press)
    small = sprite.resize((max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))), Image.LANCZOS)
    x, y = on_screen(cam, *mouse(t))
    put(image, small, (x - hx * scale, y - hy * scale))


# --- The picture -------------------------------------------------------------


def capture_desktop(out, window):
    """Starts the throwaway Plasma session off screen and saves a screenshot
    of the desktop and one of the terminal window."""
    subprocess.run(["cargo", "build", "-q", "--release", "-p", "hanami"], cwd=ROOT, check=True)
    place = CACHE / "desktop"
    shutil.rmtree(place, ignore_errors=True)
    home, run = place / "home", place / "run"
    for folder in ("Desktop", "Documents", "Downloads", "Games", "Music", "Pictures", "Videos", ".config"):
        (home / folder).mkdir(parents=True)
    run.mkdir(mode=0o700)
    (place / "minimise.js").write_text(MINIMISE)
    # Stands in for Claude Code, so the terminal's title reads "claude".
    (place / "claude").write_text("#!/bin/sh\nexec sleep 600\n")
    (place / "claude").chmod(0o755)
    session = place / "session.sh"
    session.write_text(SESSION.format(
        tasks=TASKS, hanami=ROOT / "target" / "release" / "hanami", claude=place / "claude",
        size=f"{TERMINAL[2] * DESK}x{TERMINAL[3] * DESK}", window=window, minimise=place / "minimise.js", out=out,
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
    subprocess.run(
        ["dbus-run-session", "--", "kwin_wayland", "--virtual", "--width", str(SCREEN_W), "--height", str(SCREEN_H),
         "--scale", str(DESK), "--xwayland", "--exit-with-session", str(session)],
        env=env, cwd=home, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if not (out.exists() and window.exists()):
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
        ramp = np.clip(np.linspace(0, 1, H)[:, None] / 0.45, 0, 1)
    else:
        ramp = np.clip(np.linspace(0, 1, W)[None, :] / 0.6, 0, 1)
    alpha = np.broadcast_to(0.6 * (1 - ramp * ramp * (3 - 2 * ramp)), (H, W))
    layer = Image.new("RGBA", (W, H), (8, 6, 12, 0))
    layer.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))
    return layer


def setup():
    """Things every frame shares; made once, before the workers start."""
    global WALL, WALL_BLUR, SCREEN_MASK, BACKDROP, MASK, SCRIM, NOISE, TERM_BOX, POINTER, PASTED
    WALL = Image.open(CACHE / "desktop.png").convert("RGBA").resize((SCREEN_W * DESK, SCREEN_H * DESK), Image.LANCZOS)
    window = Image.open(CACHE / "terminal.png").convert("RGBA")
    pixels = np.asarray(window)
    ys, xs = np.nonzero(pixels[..., 3] == 255)
    left, top, right, bottom = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    WALL.alpha_composite(window, (TERMINAL[0] * DESK - left, TERMINAL[1] * DESK - top))
    # The terminal's text area: the rows below the title bar that are all
    # background colour.
    plain = np.all(np.abs(pixels[top:bottom, left:right, :3].astype(int) - TERM_BG) < 4, axis=2).mean(axis=1) > 0.95
    rows = np.nonzero(plain)[0]
    TERM_BOX = (TERMINAL[0] + 1, TERMINAL[1] + rows.min() / DESK, (right - left) / DESK - 2, (rows.max() - rows.min()) / DESK)
    POINTER = pointer(24 * DESK)
    WALL_BLUR = WALL.filter(ImageFilter.GaussianBlur(30 * DESK))
    SCREEN_MASK = screenshot.rounded((SCREEN_W, SCREEN_H), 28)
    cover = min(WALL.width / W, WALL.height / H)
    crop = ((WALL.width - W * cover) / 2, (WALL.height - H * cover) / 2,
            (WALL.width + W * cover) / 2, (WALL.height + H * cover) / 2)
    BACKDROP = WALL_BLUR.resize((W, H), Image.BILINEAR, box=crop).point(lambda v: int(v * 0.5))
    MASK = screenshot.rounded((PW, PH), int(16 * PANEL_SCALE))
    SCRIM = scrim()
    guide = subprocess.run([ROOT / "target" / "release" / "hanami", "--guide"], capture_output=True, text=True, check=True)
    PASTED = f"[Pasted text #1 +{guide.stdout.count(chr(10))} lines]"
    noise = np.random.default_rng(3)
    NOISE = [noise.normal(0, 1.2, (H, W, 1)).astype(np.float32) for _ in range(6)]


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


def desktop(cam):
    """The desktop as the camera sees it. Zoomed out past the screen's edges,
    the whole screen floats over a dim copy of itself."""
    zoom = cam[2]
    fills = W / zoom <= SCREEN_W + 0.5 and H / zoom <= SCREEN_H + 0.5
    size = (W, H) if fills else (round(SCREEN_W * zoom), round(SCREEN_H * zoom))
    view = cam if fills else (SCREEN_W / 2, SCREEN_H / 2, zoom)
    half_w, half_h = min(size[0] / zoom, SCREEN_W) / 2, min(size[1] / zoom, SCREEN_H) / 2
    box = tuple(v * DESK for v in (view[0] - half_w, view[1] - half_h, view[0] + half_w, view[1] + half_h))
    image = WALL.resize(size, Image.BILINEAR, box=box)
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


def draw_panel(image, cam, t, index):
    """The real panel where Hanami opens it, over frosted wallpaper. Like the
    app, it fades in and out over 140 ms; the click on the terminal hides it."""
    opacity = between(t, REVEAL, 0.14) * (1 - between(t, AWAY, 0.14))
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


def captions():
    """The captions; the tall layout ends the last one early."""
    *first, (start, end, title, sub) = CAPTIONS
    return [*first, (start, LAYOUT.get("ask_until", end), title, sub)]


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
    image = desktop(cam)
    draw_terminal(image, cam, t)
    put(image, SCRIM, (0, 0), smooth(between(t, CAPTIONS[0][0] - 0.4, 0.5)))
    draw_keycaps(image, t)
    draw_panel(image, cam, t, index)
    draw_pointer(image, cam, t)
    for caption in captions():
        draw_caption(image, t, *caption)
    draw_end_card(image, t)
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
    (12, (46, 62), 0.6, 0), (12.5, (67,), 0.45, 0), (13, (69,), 0.5, 0), (13.5, (74,), 0.6, 0),
    (14, (70,), 0.45, 0), (14.5, (69,), 0.45, 0), (15, (67,), 0.6, 2),
    (16, (55, 62), 0.65, 0), (16.5, (70,), 0.45, 0), (17, (69,), 0.5, 0), (17.5, (67,), 0.45, 0),
    (18, (63,), 0.45, 0), (18.5, (67,), 0.5, 0), (19, (69,), 0.55, 0), (19.5, (70,), 0.5, 0),
    (20, (51, 63), 0.6, 0), (20.5, (74,), 0.5, 0), (21, (57, 69), 0.6, 0),
    (21.5, (50, 57, 62, 69, 74), 0.85, 0), (22.5, (74,), 0.5, 0), (23.5, (81,), 0.4, 0),
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
            place(koto(midi, 4.0 if b(beat) >= END else 3.2, bend), b(beat) + strum, 0.32 * loud,
                  pan=clamp((midi - 62) / 30, -0.4, 0.4), wet=0.3)
    for beat, loud in ((0, 0.55), (1.5, 0.8), (8, 0.45), (15, 0.5), (21.5, 1.0)):
        place(taiko(), b(beat), 0.5 * loud, wet=0.12)
    place(pad(), 0, 0.06, wet=0.3)
    place(chime(86), END + 0.05, 0.2, pan=0.2, wet=0.4)
    place(chime(93), END + 0.4, 0.12, pan=-0.2, wet=0.4)
    place(whoosh(), REVEAL - 0.3, 0.2, pan=0.25, wet=0.15)
    place(whoosh(0.8, 0.3), b(14.75) - 0.2, 0.1, pan=0.3, wet=0.15)
    place(whoosh(0.8, 0.3), END - 0.3, 0.12, pan=-0.1, wet=0.15)
    for keys, _ in KEYCAST:
        for label, at in keys:
            place(click(True), at, 0.2, wet=0.06)
    for at in CLICKS:
        place(click(False), at, 0.14, pan=0.2, wet=0.06)
    for at in (ASK, AWAY):
        place(click(False), at, 0.12, pan=0.35, wet=0.06)

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
    write_music(CACHE / "music.wav")
    print("setting up the desktop")
    capture_desktop(CACHE / "desktop.png", CACHE / "terminal.png")
    print("putting it together")
    setup()
    encode(out, CACHE / "music.wav")
    thumbnail = compose(round((END + 1.6) * FPS)).convert("RGB").resize(LAYOUT["thumbnail"], Image.LANCZOS)
    thumbnail.save(out.with_name(out.stem + "-thumbnail.jpg"), quality=92)
    shutil.rmtree(CACHE)
    print(out)


if __name__ == "__main__":
    main()
