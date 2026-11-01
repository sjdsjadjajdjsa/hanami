"""Draws docs/images/looks-*.webp and site/assets/social.png: the real panel in three looks an AI can
write (sakura, autumn, snow), one above the other. Needs Rust, Pillow and fonttools.

    python3 docs/looks.py [sakura autumn snow preview]

The times (seconds into the petals; the last is the link preview's panel)
are picked so no shape covers text.
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


TIMES = [float(t) for t in sys.argv[1:5]] or [15.8, 16.26, 2.23, 22.14]
SCALE = 1.6
SHOWN = 206


def guide_shapes():
    """The maple leaf and the snowflake, as GUIDE.md gives them."""
    blocks = re.findall(r"```svg\n(.*?)```", (ROOT / "GUIDE.md").read_text(), re.S)
    return blocks[0], blocks[1]


def panels(work):
    """The panel in each look, drawn by the panel_frames example."""
    maple, snow = guide_shapes()
    looks = [({"petals": 12}, None), (dict(AUTUMN, petals=6, dots=0), maple), (dict(SNOW, petals=10, dots=0), snow), ({"petals": 12}, None)]
    rows = [{"name": n, "label": l, "icon": f"site/assets/games/{i}.png", "pinned": p} for n, l, i, p in GAMES]
    size = (round(340 * SCALE), round(440 * SCALE))
    out = []
    for k, (theme, shape) in enumerate(looks):
        state = {"time": TIMES[k], "games": rows, "selected": 1, "theme": theme}
        if shape:
            folder = work / f"look-{k}"
            folder.mkdir()
            (folder / "petal.svg").write_text(shape)
            state["look"] = str(folder)
        frames = work / f"frames-{k}"
        subprocess.run(["cargo", "run", "-q", "--release", "--example", "panel_frames", "--", str(frames), str(SCALE)],
                       input=json.dumps(state).encode(), cwd=ROOT, check=True)
        raw = (frames / "00000.rgba").read_bytes()
        out.append(Image.frombytes("RGBa", size, raw).convert("RGBA"))
    return out


AUTUMN_SCENE = dict(screenshot.SCENES["dark"], top=(44, 26, 18), bottom=(14, 10, 9),
                    glows=[((0.8, 0.16), (232, 112, 42), 0.32, 560), ((0.14, 0.88), (150, 60, 30), 0.26, 520)],
                    bokeh=[(240, 160, 64), (224, 96, 42), (154, 52, 16)])
SNOW_SCENE = dict(screenshot.SCENES["dark"], top=(18, 30, 52), bottom=(8, 12, 22),
                  glows=[((0.8, 0.16), (154, 216, 255), 0.26, 560), ((0.14, 0.88), (80, 110, 200), 0.24, 520)],
                  bokeh=[(220, 238, 255), (154, 216, 255), (120, 150, 230)])


TILE = (928, 420)


def tile(panel, scene, size=TILE, crop=True, right=40):
    small = panel.crop((0, 0, panel.width, round(SHOWN * SCALE))) if crop else panel
    radius = round(16 * small.width / 340)
    small.putalpha(screenshot.ImageChops.multiply(small.getchannel("A"), screenshot.rounded(small.size, radius)))
    at = (size[0] - small.width - right, (size[1] - small.height) // 2)
    saved = screenshot.backdrop
    screenshot.backdrop = lambda s, r, box, sz: screenshot.base(s, r, sz)
    try:
        return screenshot.scene_with_panel(small, scene, size, at, radius, seed=5)
    finally:
        screenshot.backdrop = saved


LABELS = [("Sakura", ["the default"]), ("Autumn", ["\u201cmake it autumn,", "with maple leaves\u201d"]), ("Snow", ["\u201cnow snow\u201d"])]
MODES = {"dark": ((23, 20, 29),), "light": ((253, 244, 247),)}


def caption(picture, title, lines):
    font = lambda weight, size: screenshot.ImageFont.truetype(str(ROOT / "assets" / f"Inter-{weight}.ttf"), size)
    draw = screenshot.ImageDraw.Draw(picture)
    y = TILE[1] // 2 - 10 - 18 * (len(lines) - 1)
    draw.text((52, y), title, font=font("SemiBold", 48), fill=(250, 246, 250), anchor="ls")
    for j, line in enumerate(lines):
        draw.text((54, y + 48 + j * 36), line, font=font("Regular", 27), fill=(236, 228, 238), anchor="ls")
    return picture


def card(tiles, mode):
    bg = MODES[mode][0]
    w, h = 48 * 2 + TILE[0], 48 * 2 + 3 * TILE[1] + 2 * 24
    image = Image.new("RGBA", (w, h), bg + (0,))
    image.paste(Image.new("RGBA", (w, h), bg + (255,)), (0, 0), screenshot.rounded((w, h), 36))
    for k, picture in enumerate(tiles):
        image.paste(picture.convert("RGBA"), (48, 48 + k * (TILE[1] + 24)), screenshot.rounded(TILE, 24))
    return image


def logo(image):
    font = lambda weight, size: screenshot.ImageFont.truetype(str(ROOT / "assets" / f"Inter-{weight}.ttf"), size)
    draw = screenshot.ImageDraw.Draw(image)
    draw.rounded_rectangle((88, 176, 196, 284), 28, fill=(33, 28, 41), outline=(70, 64, 78), width=2)
    icon = Image.open(ROOT / "assets" / "hanami-icon.png").convert("RGBA").resize((84, 84), Image.LANCZOS)
    image.alpha_composite(icon, (100, 188))
    draw.text((222, 262), "hanami", font=font("SemiBold", 92), fill=(236, 230, 238), anchor="ls")
    return draw, font


def social(panel):
    """site/assets/social.png: the link preview, in the banner's style."""
    size = (1200, 630)
    small = panel.resize((round(panel.width * 540 / panel.height), 540), Image.LANCZOS)
    image = tile(small, screenshot.SCENES["dark"], size, crop=False, right=90).convert("RGBA")
    for x, y, s, a in [(60, 70, 26, 20), (590, 80, 18, 140), (70, 560, 22, 300), (610, 540, 28, 60), (520, 300, 16, 210)]:
        image.alpha_composite(screenshot.petal(s, (255, 214, 226), (232, 128, 159), 0.75, a, 0), (x, y))
    draw, font = logo(image)
    draw.text((92, 350), "A small game launcher", font=font("Regular", 32), fill=(155, 147, 163), anchor="ls")
    draw.text((92, 394), "for Linux and Windows", font=font("Regular", 32), fill=(155, 147, 163), anchor="ls")
    draw.text((92, 470), "hanami.lilygrove.dev", font=font("Medium", 26), fill=(244, 182, 200), anchor="ls")
    return screenshot.dither(image)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as work:
        sakura, autumn, snow, preview = panels(Path(work))
    scenes = [(sakura, screenshot.SCENES["dark"]), (autumn, AUTUMN_SCENE), (snow, SNOW_SCENE)]
    tiles = [caption(screenshot.dither(tile(*s)).convert("RGBA"), *label) for s, label in zip(scenes, LABELS)]
    for mode in MODES:
        card(tiles, mode).save(HERE / "images" / f"looks-{mode}.webp", quality=90, method=6)
    social(preview).save(ROOT / "site" / "assets" / "social.png", optimize=True)
