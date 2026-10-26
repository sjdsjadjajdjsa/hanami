"""Makes the README animation: the real panel (drawn off screen by the
panel_frames example) opens over the same backdrop as the screenshots, two
letters find a game, and Tab pins it to the top.

    python3 docs/video/demo.py

Writes docs/demo-dark.webp and docs/demo-light.webp, for GitHub's dark and
light themes. Needs Rust and Pillow and NumPy; it builds the example itself.
"""

import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import screenshot  # noqa: E402

FPS = 24
LENGTH = 7.6
FRAMES = round(FPS * LENGTH)
SCALE = 2.0
PW, PH = int(340 * SCALE), int(440 * SCALE)
OUT_SIZE = (1200, 780)

GAMES = [
    ("Hades", "epic", "hades"),
    ("Celeste", "steam", "celeste"),
    ("Dead Cells", "steam", "dead-cells"),
    ("Hollow Knight", "gog", "hollow-knight"),
    ("OpenTTD", "port", "openttd"),
    ("Stardew Valley", "steam", "stardew-valley"),
]

# When things happen, in seconds.
FADE_IN, FADE_OUT = (0.0, 0.4), (6.9, 7.3)
TYPED = [(1.2, "h"), (1.6, "hk"), (3.5, "")]
DOWNS = [3.9, 4.2, 4.5]
TAB, PIN = 5.0, 6.0


def search(games, query):
    """What the panel's search (games.rs) lists: names that start with the
    query, or whose words' first letters do ("hk" is Hollow Knight)."""
    def initials(name):
        return "".join(word[0] for word in name.lower().split())

    return [
        game for game in games
        if not query or game[0].lower().startswith(query) or (len(query) > 1 and initials(game[0]).startswith(query))
    ]


def state(t):
    pinned = {"Hades"} | ({"Hollow Knight"} if t >= PIN else set())
    games = sorted(GAMES, key=lambda game: (game[0] not in pinned, game[0].lower()))
    query = ""
    for at, typed in TYPED:
        if t >= at:
            query = typed
    shown = search(games, query)
    names = [game[0] for game in shown]
    selected = sum(t >= at for at in DOWNS)
    if t >= PIN:
        selected = names.index("Hollow Knight")
    rows = [
        {
            "name": name,
            "label": f"pinned · {label}" if name in pinned else label,
            "icon": f"site/assets/games/{icon}.png",
            "pinned": name in pinned,
        }
        for name, label, icon in shown
    ]
    return {
        "time": t,
        "games": rows,
        "total": len(GAMES),
        "query": query,
        "selected": selected,
        "acting": selected if TAB <= t < PIN else -1,
        "notice": "",
        "pointer": None,
    }


def render(frames):
    states = "\n".join(json.dumps(state(i / FPS)) for i in range(FRAMES))
    subprocess.run(
        ["cargo", "run", "-q", "--release", "--example", "panel_frames", "--", str(frames), str(SCALE)],
        input=states.encode(),
        cwd=ROOT,
        check=True,
    )


def panel_at(frames, index):
    """One drawn frame as straight (not premultiplied) RGBA."""
    raw = np.frombuffer((frames / f"{index:05d}.rgba").read_bytes(), dtype=np.uint8).reshape(PH, PW, 4).astype(np.float32)
    alpha = raw[..., 3:4]
    colour = np.where(alpha > 0, raw[..., :3] * 255 / np.maximum(alpha, 1), 0)
    return np.concatenate([np.clip(colour, 0, 255), alpha], axis=2)


def fade(t):
    if t < FADE_IN[1]:
        return max(0.0, (t - FADE_IN[0]) / (FADE_IN[1] - FADE_IN[0]))
    if t > FADE_OUT[0]:
        return max(0.0, 1 - (t - FADE_OUT[0]) / (FADE_OUT[1] - FADE_OUT[0]))
    return 1.0


def backgrounds(scene):
    """The backdrop without and with the panel's shadow and frosted glass."""
    size = (screenshot.W, screenshot.H)
    at = ((size[0] - PW) // 2, (size[1] - PH) // 2)
    empty = Image.new("RGBA", (PW, PH))
    plain = screenshot.backdrop(scene, random.Random(7), (at[0], at[1], at[0] + PW, at[1] + PH), size)
    glass = screenshot.scene_with_panel(empty, scene, size, at, screenshot.RADIUS)
    return plain, glass, at


def make(name, scene, frames):
    plain, glass, at = backgrounds(scene)
    sequence = []
    for index in range(FRAMES):
        t = index / FPS
        a = fade(t)
        panel = panel_at(frames, index)
        panel[..., 3] *= a
        picture = Image.blend(plain, glass, a) if a < 1 else glass.copy()
        picture.alpha_composite(Image.fromarray(panel.astype(np.uint8), "RGBA"), at)
        sequence.append(screenshot.dither(picture).resize(OUT_SIZE, Image.LANCZOS))
    out = HERE.parent / f"demo-{name}.webp"
    sequence[0].save(
        out, save_all=True, append_images=sequence[1:], duration=round(1000 / FPS), loop=0, quality=80, method=6
    )
    print(out, f"{out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    frames = Path(tempfile.mkdtemp(prefix="hanami-demo-"))
    try:
        render(frames)
        for name, scene in screenshot.SCENES.items():
            make(name, scene, frames)
    finally:
        shutil.rmtree(frames, ignore_errors=True)
