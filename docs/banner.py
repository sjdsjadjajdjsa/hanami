"""Draws the README banner: python3 docs/banner.py (needs fonttools)."""

from functools import cache
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets"
W, H = 1280, 360

LOOKS = {
    "dark": dict(
        bg="#17141d", border="#ffffff", border_op="0.09", glow="#f4b6c8", glow_op="0.22",
        glow2="#8a68c8", glow2_op="0.16", text="#ece6ee", muted="#9b93a3",
        blossom="#f4b6c8", center="#e98fab", petal="#f7c4d3", tile="#211c29",
    ),
    "light": dict(
        bg="#fdf4f7", border="#2b1d28", border_op="0.10", glow="#d85a88", glow_op="0.16",
        glow2="#b898e8", glow2_op="0.14", text="#261e2b", muted="#74667b",
        blossom="#d85a88", center="#b83b6a", petal="#e47a9e", tile="#ffffff",
    ),
}


@cache
def load_font(font_file):
    return TTFont(FONTS / font_file)


def text_path(font_file, text, size, x, baseline, tracking=0.0):
    font = load_font(font_file)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    cursor = 0.0
    for ch in text:
        name = cmap[ord(ch)]
        glyph = glyphs[name]
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x + cursor, baseline)))
        cursor += glyph.width * scale + tracking * size
    return pen.getCommands(), cursor - tracking * size


PETAL_D = (
    "M0 11 C -5.2 8 -7.2 2.5 -6.2 -3.4 C -5.5 -7.6 -4 -10.4 -2.1 -10.5 "
    "C -1.1 -10.5 -0.3 -10 0.2 -9.4 C 0.7 -10.1 1.6 -10.5 2.5 -10.4 "
    "C 4.5 -10.2 6 -7.8 6 -3.6 C 6 1.2 3.8 6.4 0 11 Z"
)
BLOSSOM_D = "M0 -2 C -9 -10 -10 -22 -4 -28 C -2 -30 0 -28 0 -25 C 0 -28 2 -30 4 -28 C 10 -22 9 -10 0 -2 Z"


def petals(c):
    spec = [
        (88, 62, 1.05, -24, 0.38, 16, 0, -18),
        (178, 286, 0.78, 38, 0.24, 21, 5, 22),
        (315, 44, 0.90, -42, 0.30, 19, 11, -14),
        (490, 312, 0.74, 28, 0.22, 23, 3, 18),
        (685, 48, 0.86, 52, 0.28, 20, 14, -20),
        (865, 304, 0.96, -34, 0.32, 18, 7, 20),
        (1010, 68, 1.12, 26, 0.42, 17, 2, -16),
        (1118, 188, 0.84, -48, 0.30, 22, 9, 24),
        (1182, 94, 1.02, 34, 0.38, 18, 13, -18),
        (1224, 278, 0.88, -28, 0.32, 20, 4, 16),
    ]
    out = []
    for x, y, sc, rot, op, dur, begin, sway in spec:
        out.append(
            f'<g transform="translate({x} {y})"><g>'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="0 0; {sway} 14; 0 0" dur="{dur}s" begin="-{begin}s" repeatCount="indefinite"/>'
            f'<g transform="rotate({rot}) scale({sc})">'
            f'<path d="{PETAL_D}" fill="{c["petal"]}" fill-opacity="{op}"/>'
            f'</g></g></g>'
        )
    return "".join(out)


def banner(look):
    c = LOOKS[look]
    word, word_w = text_path("Inter-SemiBold.ttf", "hanami", 112, 0, 0, -0.035)
    line_one, line_w = text_path(
        "Inter-Medium.ttf",
        "A small game launcher for Linux and Windows, with falling sakura petals.",
        23, 0, 0, -0.005,
    )
    line_two, _ = text_path(
        "Inter-Regular.ttf",
        "Steam  ·  Heroic  ·  Epic  ·  GOG  ·  Lutris  ·  ports & rewrites  ·  Minecraft",
        17, 0, 0, 0.005,
    )
    icon_size, gap = 128, 40
    left = (W - (icon_size + gap + max(word_w, line_w + 6))) / 2
    text_x = left + icon_size + gap
    cx, cy = left + icon_size / 2, 180
    blossom = "".join(f'<path d="{BLOSSOM_D}" transform="rotate({r})"/>' for r in (0, 72, 144, 216, 288))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="hanami, a small game launcher for Linux and Windows">
<defs>
<clipPath id="card"><rect width="{W}" height="{H}" rx="28"/></clipPath>
<radialGradient id="g1" cx="0.82" cy="0.14" r="0.65"><stop offset="0" stop-color="{c["glow"]}" stop-opacity="{c["glow_op"]}"/><stop offset="1" stop-color="{c["glow"]}" stop-opacity="0"/></radialGradient>
<radialGradient id="g2" cx="0.14" cy="0.90" r="0.60"><stop offset="0" stop-color="{c["glow2"]}" stop-opacity="{c["glow2_op"]}"/><stop offset="1" stop-color="{c["glow2"]}" stop-opacity="0"/></radialGradient>
</defs>
<g clip-path="url(#card)">
<rect width="{W}" height="{H}" fill="{c["bg"]}"/>
<rect width="{W}" height="{H}" fill="url(#g1)"/>
<rect width="{W}" height="{H}" fill="url(#g2)"/>
{petals(c)}
</g>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="27.5" fill="none" stroke="{c["border"]}" stroke-opacity="{c["border_op"]}"/>
<rect x="{left:.1f}" y="{cy - icon_size / 2:.1f}" width="{icon_size}" height="{icon_size}" rx="32" fill="{c["tile"]}" stroke="{c["border"]}" stroke-opacity="{c["border_op"]}"/>
<g transform="translate({cx:.1f} {cy:.1f}) scale(1.42)">
<g fill="{c["blossom"]}">{blossom}</g>
<circle r="4" fill="{c["center"]}"/>
</g>
<path transform="translate({text_x:.1f} 166)" d="{word}" fill="{c["text"]}"/>
<path transform="translate({text_x + 4:.1f} 216)" d="{line_one}" fill="{c["text"]}" fill-opacity="0.92"/>
<path transform="translate({text_x + 4:.1f} 252)" d="{line_two}" fill="{c["muted"]}"/>
</svg>
"""


if __name__ == "__main__":
    out_dir = ROOT / "docs" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    for look in LOOKS:
        (out_dir / f"banner-{look}.svg").write_text(banner(look))



