"""Shared drawing for the README cards; docs/cards.py writes them (needs fonttools)."""

import math
from pathlib import Path

from banner import BLOSSOM_D, PETAL_D, text_path

ROOT = Path(__file__).resolve().parent.parent
W, PAD = 1280, 56

LOOKS = {
    "dark": dict(
        bg="#17141d", text="#ece6ee", muted="#9b93a3", track="#241e2e",
        accent="#f4b6c8", accent2="#e98fab", tile="#1f1a27", line="#ffffff", line_op="0.09",
        glow="0.16", chip="0.14", petal="#f7c4d3",
    ),
    "light": dict(
        bg="#fdf4f7", text="#261e2b", muted="#74667b", track="#f5e6ed",
        accent="#d85a88", accent2="#b83b6a", tile="#ffffff", line="#2b1d28", line_op="0.10",
        glow="0.12", chip="0.12", petal="#e47a9e",
    ),
}


def text(font, words, size, x, y, fill, anchor="start", opacity=1.0, tracking=0.0):
    d, width = text_path(font, words, size, 0, 0, tracking)
    if anchor == "end":
        x -= width
    elif anchor == "middle":
        x -= width / 2
    alpha = f' fill-opacity="{opacity}"' if opacity < 1 else ""
    return f'<path transform="translate({x:.1f} {y:.1f})" d="{d}" fill="{fill}"{alpha}/>', width


def width_of(font, words, size):
    return text_path(font, words, size, 0, 0)[1]


def wrap(font, words, size, width):
    lines, line = [], ""
    for word in words.split():
        trial = f"{line} {word}".strip()
        if line and width_of(font, trial, size) > width:
            lines.append(line)
            trial = word
        line = trial
    return lines + [line]


ICONS = {
    "search": "M18 11a7 7 0 1 1-14 0a7 7 0 1 1 14 0z M21 21l-4.35-4.35",
    "grid": "M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z",
    "star": "M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14 2 9.27l6.91-1.01z",
    "compass": "M12 22a10 10 0 1 0 0-20a10 10 0 1 0 0 20z M16.24 7.76l-2.12 6.36-6.36 2.12 2.12-6.36z",
    "box": "M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z M3.3 7L12 12l8.7-5 M12 22V12",
    "gamepad": "M6 12h4 M8 10v4 M15 13h.01 M18 11h.01 M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z",
    "feather": "M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z M16 8L2 22 M17.5 15H9",
    "help": "M12 22a10 10 0 1 0 0-20a10 10 0 1 0 0 20z M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3 M12 17h.01",
    "download": "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M7 10l5 5 5-5 M12 15V3",
    "terminal": "M4 17l6-6-6-6 M12 19h8",
    "play": "M6 4l14 8-14 8V4z",
    "image": "M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z M8.5 10a1.5 1.5 0 1 0 0-3a1.5 1.5 0 1 0 0 3z M21 15l-5-5L5 21",
    "sliders": "M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M2 14h4 M10 8h4 M18 16h4",
}


def icon(name, x, y, size, colour):
    if name == "sakura":
        cx, cy = x + size / 2, y + size / 2
        s = size / 60
        arms = "".join(f'<path d="{BLOSSOM_D}" transform="rotate({r})"/>' for r in (0, 72, 144, 216, 288))
        return f'<g transform="translate({cx:.1f} {cy:.1f}) scale({s:.3f})" fill="{colour}">{arms}<circle r="4.5"/></g>'
    return (
        f'<path transform="translate({x:.1f} {y:.1f}) scale({size / 24:.3f})" d="{ICONS[name]}" fill="none" '
        f'stroke="{colour}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def petals_bg(c, height):
    spots = [
        (0.03, 0.14, 0.78, -28, 0.24), (0.97, 0.18, 0.88, 36, 0.26),
        (0.02, 0.56, 0.72, 22, 0.20), (0.98, 0.62, 0.82, -34, 0.24),
        (0.18, 0.96, 0.74, 44, 0.20), (0.84, 0.95, 0.80, -24, 0.22),
    ]
    return "".join(
        f'<path transform="translate({fx * W:.1f} {fy * height:.1f}) rotate({rot}) scale({sc})" '
        f'd="{PETAL_D}" fill="{c["petal"]}" fill-opacity="{op}"/>'
        for fx, fy, sc, rot, op in spots
    )


def frame(c, height, body, label, glow=(0.92, 0.0)):
    p = petals_bg(c, height)
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" role="img" aria-label="{label}">',
        f'<defs><clipPath id="card"><rect width="{W}" height="{height}" rx="28"/></clipPath>',
        f'<radialGradient id="glow" cx="{glow[0]}" cy="{glow[1]}" r="0.65"><stop offset="0" stop-color="{c["accent"]}" stop-opacity="{c["glow"]}"/><stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/></radialGradient></defs>',
        f'<g clip-path="url(#card)"><rect width="{W}" height="{height}" fill="{c["bg"]}"/><rect width="{W}" height="{height}" fill="url(#glow)"/>{p}</g>',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="27.5" fill="none" stroke="{c["line"]}" stroke-opacity="{c["line_op"]}"/>',
        *body,
        "</svg>\n",
    ])


def tile(c, x, y, w, h, radius=20):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{radius}" fill="{c["tile"]}" stroke="{c["line"]}" stroke-opacity="{c["line_op"]}"/>'


def chip(c, name, x, y, size=46):
    return [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" rx="14" fill="{c["accent"]}" fill-opacity="{c["chip"]}"/>',
        icon(name, x + (size - 24) / 2, y + (size - 24) / 2, 24, c["accent"]),
    ]


FEATURES = [
    ("grid", "Every launcher, one list", "Steam, Heroic, Epic, GOG, Lutris"),
    ("search", "Search that forgives", "Type hk to find Hollow Knight"),
    ("star", "Your list, your order", "Pin, rename, hide, recent first"),
    ("compass", "Ports and rewrites", "Ship of Harkinian, OpenMW, more"),
    ("box", "Minecraft instances", "Prism, PolyMC and MultiMC"),
    ("gamepad", "Controller ready", "Hold Start + Select to open"),
    ("sakura", "Custom colours and petals", "Two small files, or ask your AI"),
    ("feather", "Tiny footprint", "28 MB, under 3 % CPU, 6 ms"),
    ("help", "AI help and crash reports", "The ? button teaches your AI"),
]


def features(c):
    cols, gap, h = 3, 16, 178
    w = (W - 2 * PAD - gap * (cols - 1)) / cols
    body = []
    for i, (name, title, line) in enumerate(FEATURES):
        x, y = PAD + (i % cols) * (w + gap), PAD + (i // cols) * (h + gap)
        body.append(tile(c, x, y, w, h))
        body += chip(c, name, x + 26, y + 26, 52)
        body.append(text("Inter-SemiBold.ttf", title, 23, x + 26, y + 112, c["text"], tracking=-0.015)[0])
        lines = wrap("Inter-Regular.ttf", line, 19, w - 52)
        assert len(lines) == 1, line
        body.append(text("Inter-Regular.ttf", lines[0], 19, x + 26, y + 146, c["muted"])[0])
    rows = math.ceil(len(FEATURES) / cols)
    height = PAD * 2 + rows * h + (rows - 1) * gap
    return frame(c, height, body, "Hanami's features")


SOURCES = [
    ("Steam", "Installed games, tools left out", True, True),
    ("Heroic", "Epic, GOG, Amazon and sideloaded", True, True),
    ("Epic & GOG", "Epic Games Launcher and GOG Galaxy", False, True),
    ("Lutris", "Installed games, hidden left out", True, False),
    ("App menu", "Desktop entries in the Game category", True, False),
    ("Ports & rewrites", "Ship of Harkinian, OpenMW, Rust builds", True, True),
    ("Minecraft", "Prism, PolyMC and MultiMC instances", True, True),
    ("Your own", "Any program, added with the + button", True, True),
]


def sources_card(c):
    cols, gap, h = 2, 16, 112
    w = (W - 2 * PAD - gap) / cols
    body = []
    for i, (name, sub, linux, windows) in enumerate(SOURCES):
        x, y = PAD + (i % cols) * (w + gap), PAD + (i // cols) * (h + gap)
        body.append(tile(c, x, y, w, h, 18))
        body.append(text("Inter-SemiBold.ttf", name, 23, x + 26, y + 46, c["text"], tracking=-0.015)[0])
        body.append(text("Inter-Regular.ttf", sub, 18, x + 26, y + 84, c["muted"])[0])
        bx = x + w - 22
        for label, on in (("Windows", windows), ("Linux", linux)):
            if not on:
                continue
            bw = width_of("Inter-Medium.ttf", label, 16) + 26
            bx -= bw
            body.append(f'<rect x="{bx:.1f}" y="{y + 20}" width="{bw:.1f}" height="34" rx="8" fill="{c["accent"]}" fill-opacity="{c["chip"]}"/>')
            body.append(text("Inter-Medium.ttf", label, 16, bx + bw / 2, y + 43, c["accent2"], "middle")[0])
            bx -= 8
    rows = math.ceil(len(SOURCES) / cols)
    height = PAD * 2 + rows * h + (rows - 1) * gap
    return frame(c, height, body, "Where Hanami finds games", glow=(0.08, 0.0))


AGENTS_LIST = [
    ("Crush", "Kimi K2.8", "hide Dead Cells", 'hide = ["Dead Cells"]'),
    ("OpenCode", "Devstral 24B", "rename Stardew Valley to Stardew", 'rename = { … = "Stardew" }'),
    ("Antigravity CLI", "Gemini 3.8 Flash", "pin Hades and Hollow Knight", 'favourites = ["Hades", …]'),
    ("jcode", "Kimi K3", "make it autumn, with maple leaves", "[theme] + petal.svg"),
    ("Codex", "GPT-5.5", "make Ctrl+Space open Hanami", 'hotkey = "Ctrl+Space"'),
    ("Claude Code", "Claude Opus 5.5", "find my Minecraft too", 'find = ["prism"]'),
]


def agents_card(c):
    cols, gap, h = 3, 16, 214
    w = (W - 2 * PAD - gap * (cols - 1)) / cols
    body = []
    for i, (agent, model, prompt, result) in enumerate(AGENTS_LIST):
        x, y = PAD + (i % cols) * (w + gap), PAD + (i // cols) * (h + gap)
        body.append(tile(c, x, y, w, h))
        body.append(f'<rect x="{x + 24:.1f}" y="{y + 22}" width="44" height="34" rx="8" fill="{c["accent"]}" fill-opacity="{c["chip"]}"/>')
        body.append(text("Inter-SemiBold.ttf", f"{i + 1}/6", 16, x + 46, y + 45, c["accent2"], "middle")[0])
        body.append(text("Inter-SemiBold.ttf", agent, 23, x + 82, y + 47, c["text"], tracking=-0.015)[0])
        body.append(text("Inter-Regular.ttf", f"on {model}", 18, x + 24, y + 92, c["muted"])[0])
        quoted = f"\u201c{prompt}\u201d"
        assert width_of("Inter-Medium.ttf", quoted, 18) < w - 48, prompt
        body.append(text("Inter-Medium.ttf", quoted, 18, x + 24, y + 130, c["text"])[0])
        rw = width_of("Inter-Medium.ttf", result, 16) + 24
        assert rw < w - 48, result
        body.append(f'<rect x="{x + 24:.1f}" y="{y + 152}" width="{rw:.1f}" height="36" rx="8" fill="{c["track"]}"/>')
        body.append(text("Inter-Medium.ttf", result, 16, x + 36, y + 176, c["accent2"])[0])
    rows = math.ceil(len(AGENTS_LIST) / cols)
    height = PAD * 2 + rows * h + (rows - 1) * gap
    return frame(c, height, body, "Any harness, any model: six AI agents configure Hanami", glow=(0.88, 0.0))




















