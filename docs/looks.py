"""Draws docs/images/looks.webp: the real panel in three looks an AI can
write (sakura, autumn, snow), side by side. Needs Rust, Pillow and fonttools.

    python3 docs/looks.py [time time time]

The times (seconds into the petals) are picked so no shape covers text.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "video"))
sys.path.insert(0, str(HERE))
import screenshot  # noqa: E402
from seasons_ai import AUTUMN, SNOW  # noqa: E402

GAMES = [("Hades", "pinned · epic", "hades", True), ("Celeste", "steam", "celeste", False),
         ("Dead Cells", "steam", "dead-cells", False), ("Hollow Knight", "gog", "hollow-knight", False),
         ("OpenTTD", "port", "openttd", False), ("Stardew Valley", "steam", "stardew-valley", False)]


TIMES = [float(t) for t in sys.argv[1:4]] or [3.85, 5.7, 9.03]


def guide_shapes():
    """The maple leaf and the snowflake, as GUIDE.md gives them."""
    blocks = re.findall(r"```svg\n(.*?)```", (ROOT / "GUIDE.md").read_text(), re.S)
    return blocks[0], blocks[1]


def panels(work):
    """The panel in each look, drawn by the panel_frames example."""
    maple, snow = guide_shapes()
    looks = [({"petals": 12}, None), (dict(AUTUMN, petals=8, dots=0), maple), (dict(SNOW, petals=10, dots=0), snow)]
    rows = [{"name": n, "label": l, "icon": f"site/assets/games/{i}.png", "pinned": p} for n, l, i, p in GAMES]
    lines = []
    for k, (theme, shape) in enumerate(looks):
        state = {"time": TIMES[k], "games": rows, "selected": 1, "theme": theme}
        if shape:
            folder = work / f"look-{k}"
            folder.mkdir()
            (folder / "petal.svg").write_text(shape)
            state["look"] = str(folder)
        lines.append(json.dumps(state))
    frames = work / "frames"
    subprocess.run(["cargo", "run", "-q", "--release", "--example", "panel_frames", "--", str(frames), "2.0"],
                   input="\n".join(lines).encode(), cwd=ROOT, check=True)
    size = (680, 880)
    out = []
    for k in range(len(looks)):
        raw = (frames / f"{k:05}.rgba").read_bytes()
        out.append(Image.frombytes("RGBa", size, raw).convert("RGBA"))
    return out


AUTUMN_SCENE = dict(screenshot.SCENES["dark"], top=(44, 26, 18), bottom=(14, 10, 9),
                    glows=[((0.8, 0.16), (232, 112, 42), 0.32, 560), ((0.14, 0.88), (150, 60, 30), 0.26, 520)],
                    bokeh=[(240, 160, 64), (224, 96, 42), (154, 52, 16)])
SNOW_SCENE = dict(screenshot.SCENES["dark"], top=(18, 30, 52), bottom=(8, 12, 22),
                  glows=[((0.8, 0.16), (154, 216, 255), 0.26, 560), ((0.14, 0.88), (80, 110, 200), 0.24, 520)],
                  bokeh=[(220, 238, 255), (154, 216, 255), (120, 150, 230)])


def tile(panel, scene, petals, size=(520, 660)):
    small = panel.resize((440, 569), Image.LANCZOS)
    at = ((size[0] - 440) // 2, (size[1] - 569) // 2)
    saved = screenshot.backdrop
    if not petals:
        screenshot.backdrop = lambda s, r, box, sz: screenshot.base(s, r, sz)
    try:
        return screenshot.scene_with_panel(small, scene, size, at, 14, seed=5)
    finally:
        screenshot.backdrop = saved


LABELS = ["Sakura, the default", "\u201cmake it autumn, with maple leaves\u201d", "\u201cnow snow\u201d"]
MODES = {"dark": ((23, 20, 29), (236, 230, 238), (155, 147, 163)), "light": ((253, 244, 247), (38, 30, 43), (116, 102, 123))}


def card(tiles, mode):
    bg, ink, dim = MODES[mode]
    w, h = 48 * 2 + 520 * 3 + 24 * 2, 48 + 660 + 96
    image = Image.new("RGBA", (w, h), bg + (0,))
    image.paste(Image.new("RGBA", (w, h), bg + (255,)), (0, 0), screenshot.rounded((w, h), 36))
    font = screenshot.ImageFont.truetype(str(ROOT / "assets" / "Inter-Medium.ttf"), 28)
    draw = screenshot.ImageDraw.Draw(image)
    for k, (picture, label) in enumerate(zip(tiles, LABELS)):
        x = 48 + k * (520 + 24)
        image.paste(picture.convert("RGBA"), (x, 48), screenshot.rounded(picture.size, 24))
        draw.text((x + 260, 48 + 660 + 46), label, font=font, fill=ink if k == 0 else dim, anchor="mm")
    return image


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as work:
        sakura, autumn, snow = panels(Path(work))
    scenes = [(sakura, screenshot.SCENES["dark"], True), (autumn, AUTUMN_SCENE, False), (snow, SNOW_SCENE, False)]
    tiles = [screenshot.dither(tile(*s)) for s in scenes]
    for mode in MODES:
        card(tiles, mode).save(HERE / "images" / f"looks-{mode}.webp", quality=90, method=6)
