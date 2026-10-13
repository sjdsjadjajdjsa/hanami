"""Draws the README pictures and the site's link preview: the panel from
`hanami --snapshot` over a blurred background, the way it looks with the
desktop's blur turned on.

    hanami --snapshot panel.png
    python3 docs/screenshot.py panel.png

Needs Pillow. Writes docs/screenshot-dark.webp and docs/screenshot-light.webp,
for GitHub's dark and light themes, and site/assets/social.png.
"""

import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1600, 1040
SCALE = 2
RADIUS = 16 * SCALE
HERE = Path(__file__).parent

SCENES = {
    "dark": dict(
        top=(30, 23, 40),
        bottom=(12, 10, 17),
        glows=[((0.80, 0.16), (244, 182, 200), 0.30, 640), ((0.14, 0.88), (126, 96, 196), 0.24, 580)],
        bokeh=[(244, 182, 200), (214, 150, 190), (160, 130, 220)],
        bokeh_alpha=(0.05, 0.24),
        petal=(247, 196, 211),
        vein=(233, 163, 184),
        petal_alpha=(0.45, 0.85),
        shadow=(0, 0, 0),
        shadow_alpha=0.6,
    ),
    "light": dict(
        top=(253, 240, 244),
        bottom=(236, 227, 242),
        glows=[((0.80, 0.14), (247, 186, 206), 0.60, 640), ((0.14, 0.88), (190, 210, 248), 0.55, 580)],
        bokeh=[(255, 255, 255), (247, 196, 211), (220, 204, 246)],
        bokeh_alpha=(0.20, 0.55),
        petal=(240, 158, 184),
        vein=(220, 124, 156),
        petal_alpha=(0.55, 0.95),
        shadow=(70, 30, 55),
        shadow_alpha=0.32,
    ),
}


def cubic(p0, p1, p2, p3, steps=24):
    for i in range(steps):
        t = i / steps
        u = 1 - t
        yield tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3))


def petal(size, colour, vein, alpha, angle, blur):
    """assets/petal.svg, drawn `size` pixels wide."""
    zoom = 8
    k = size * zoom / 20
    outline = [((0, 11), (-7, 5), (-9, -3), (-5, -9)), ((-5, -9), (-3, -11.5), (-1, -10.5), (0, -7.5)),
               ((0, -7.5), (1, -10.5), (3, -11.5), (5, -9)), ((5, -9), (9, -3), (7, 5), (0, 11))]
    side = int(size * 1.6 * zoom)
    to_px = lambda p: (side / 2 + p[0] * k, side / 2 + p[1] * k)
    big = Image.new("RGBA", (side, side), colour + (0,))
    draw = ImageDraw.Draw(big)
    draw.polygon([to_px(p) for seg in outline for p in cubic(*seg)], fill=colour + (255,))
    draw.line([to_px(p) for p in cubic((0, 9), (-0.8, 4), (-0.8, -1.5), (0, -5.5))] + [to_px((0, -5.5))],
              fill=vein + (180,), width=max(1, int(0.9 * k)))
    small = big.rotate(angle, resample=Image.BICUBIC).resize((side // zoom, side // zoom), Image.LANCZOS)
    small.putalpha(small.getchannel("A").point(lambda a: int(a * alpha)))
    return small.filter(ImageFilter.GaussianBlur(blur)) if blur else small


def rounded(size, radius, fill=255):
    zoom = 4
    mask = Image.new("L", (size[0] * zoom, size[1] * zoom), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius * zoom, fill=fill)
    return mask.resize(size, Image.LANCZOS)


def fade(distance):
    """Radial gradient value (181 at the edge's middle) to a smooth 255..0 falloff."""
    t = max(0.0, 1 - distance / 181)
    return int(255 * t * t * (3 - 2 * t))


def backdrop(scene, rand, panel_box, size=(W, H)):
    W, H = size
    top, bottom = (Image.new("RGBA", (W, H), c + (255,)) for c in (scene["top"], scene["bottom"]))
    image = Image.composite(bottom, top, Image.linear_gradient("L").resize((W, H)))
    for (x, y), colour, strength, radius in scene["glows"]:
        falloff = Image.radial_gradient("L").point(fade).resize((radius * 2, radius * 2), Image.BICUBIC)
        glow = Image.new("RGBA", falloff.size, colour + (0,))
        glow.putalpha(falloff.point(lambda a: int(a * strength)))
        image.alpha_composite(glow, (int(x * W) - radius, int(y * H) - radius))

    # One layer per colour, coloured everywhere, so blurring never pulls
    # black into the edges.
    for count, sizes, blur in ((14, (90, 220), 34), (26, (18, 70), 6)):
        masks = {colour: Image.new("L", (W, H), 0) for colour in scene["bokeh"]}
        for _ in range(count):
            r = rand.uniform(*sizes)
            x, y = rand.uniform(-60, W + 60), rand.uniform(-60, H + 60)
            alpha = int(255 * rand.uniform(*scene["bokeh_alpha"]))
            ImageDraw.Draw(masks[rand.choice(scene["bokeh"])]).ellipse((x - r, y - r, x + r, y + r), fill=alpha)
        for colour, mask in masks.items():
            layer = Image.new("RGBA", (W, H), colour + (0,))
            layer.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)))
            image.alpha_composite(layer)

    left, top_edge, right, bottom_edge = panel_box
    for i in range(30):
        size = rand.uniform(14, 34)
        x, y = rand.uniform(0, W), rand.uniform(0, H)
        inside = left - 20 < x < right + 20 and top_edge - 20 < y < bottom_edge + 20
        if inside and i % 3:
            continue
        near = size > 30
        p = petal(size, scene["petal"], scene["vein"], rand.uniform(*scene["petal_alpha"]), rand.uniform(0, 360),
                  2.5 if near else (0.8 if size < 18 else 0))
        image.alpha_composite(p, (int(x - p.width / 2), int(y - p.height / 2)))
    return image


def dither(image):
    noise = Image.effect_noise(image.size, 3)
    channels = [ImageChops.add(c, noise, 1.0, -128) for c in image.convert("RGB").split()]
    return Image.merge("RGB", channels)


def scene_with_panel(panel, scene, size, at, radius, seed=7):
    """The backdrop, then the panel's shadow, frosted glass and the panel."""
    x, y = at
    box = (x, y, x + panel.width, y + panel.height)
    image = backdrop(scene, random.Random(seed), box, size)
    blur = panel.width * 36 // 680

    pad = 120
    shadow = Image.new("RGBA", (panel.width + pad * 2, panel.height + pad * 2), scene["shadow"] + (0,))
    mask = Image.new("L", shadow.size, 0)
    mask.paste(rounded(panel.size, radius, int(255 * scene["shadow_alpha"])), (pad, pad))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)))
    image.alpha_composite(shadow, (x - pad, y - pad + blur * 3 // 4))

    frosted = image.crop(box).filter(ImageFilter.GaussianBlur(blur))
    image.paste(frosted, (x, y), rounded(panel.size, radius))
    image.alpha_composite(panel, (x, y))
    return image


def draw(panel, name, scene):
    image = scene_with_panel(panel, scene, (W, H), ((W - panel.width) // 2, (H - panel.height) // 2), RADIUS)
    out = HERE / f"screenshot-{name}.webp"
    dither(image).save(out, quality=92, method=6)
    print(out)


def social(panel):
    """The 1200 x 630 card chat apps show for a link to the site."""
    size = (1200, 630)
    scale = 540 / panel.height
    small = panel.resize((round(panel.width * scale), 540), Image.LANCZOS)
    image = scene_with_panel(small, SCENES["dark"], size, (size[0] - small.width - 110, 45), round(RADIUS * scale), seed=3)
    fonts = HERE.parent / "assets"
    draw = ImageDraw.Draw(image)
    draw.text((96, 215), "hanami", font=ImageFont.truetype(str(fonts / "Inter-SemiBold.ttf"), 92), fill=(236, 230, 238))
    regular = ImageFont.truetype(str(fonts / "Inter-Regular.ttf"), 30)
    draw.text((100, 335), "A small game launcher", font=regular, fill=(155, 147, 163))
    draw.text((100, 375), "for Linux and Windows", font=regular, fill=(155, 147, 163))
    draw.text((100, 455), "hanami.lilygrove.dev", font=ImageFont.truetype(str(fonts / "Inter-Medium.ttf"), 26), fill=(244, 182, 200))
    out = HERE.parent / "site" / "assets" / "social.png"
    dither(image).save(out, optimize=True)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    panel = Image.open(sys.argv[1]).convert("RGBA")
    for name, scene in SCENES.items():
        draw(panel, name, scene)
    social(panel)
