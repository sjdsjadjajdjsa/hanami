"""Draws the README cards into docs/images, dark and light: python3 docs/cards.py (needs fonttools)."""

import math
from pathlib import Path

from art import LOOKS, PAD, ROOT, W, chip, frame, text, tile, width_of

PLATFORMS = [
    ("Linux", "hanami-x86_64.AppImage", "download", ["Make it executable and run it.", "Ubuntu 22.04, Fedora 36, Debian 12 or newer."]),
    ("Windows", "hanami-setup-x86_64.exe", "download", ["Installs for your user, no admin rights.", "Start menu entry, optional start with Windows."]),
    ("Portable", "hanami-linux-x86_64.tar.gz", "box", ["Or hanami-windows-x86_64.zip: just the program.", "Every release has SHA256SUMS and a build record."]),
    ("From source", "cargo build --release", "terminal", ["Rust and a few dev packages, see below.", "Then run ./target/release/hanami."]),
]


def install(c):
    cols, gap, h = 2, 16, 232
    w = (W - 2 * PAD - gap) / cols
    body = []
    for i, (name, file, ic, lines) in enumerate(PLATFORMS):
        x, y = PAD + (i % cols) * (w + gap), PAD + (i // cols) * (h + gap)
        body.append(tile(c, x, y, w, h))
        body += chip(c, ic, x + 26, y + 26, 52)
        body.append(text("Inter-SemiBold.ttf", name, 26, x + 96, y + 62, c["text"], tracking=-0.02)[0])
        fw = width_of("Inter-Medium.ttf", file, 17) + 26
        body.append(f'<rect x="{x + 24:.1f}" y="{y + 100}" width="{fw:.1f}" height="38" rx="8" fill="{c["track"]}"/>')
        body.append(text("Inter-Medium.ttf", file, 17, x + 39, y + 125, c["accent2"])[0])
        for j, line in enumerate(lines):
            body.append(text("Inter-Regular.ttf", line, 18, x + 26, y + 176 + j * 28, c["muted"])[0])
    height = PAD * 2 + 2 * h + gap
    return frame(c, height, body, "Install Hanami", glow=(0.1, 0.0))


STATS = [("28 MB", "memory with 200 games"), ("2.8 %", "of one core, panel open"), ("6 ms", "from hotkey to panel")]


def stats(c):
    gap, h = 16, 172
    w = (W - 2 * PAD - gap * 2) / 3
    body = []
    for i, (big, small) in enumerate(STATS):
        x = PAD + i * (w + gap)
        body.append(tile(c, x, PAD, w, h))
        body.append(text("Inter-SemiBold.ttf", big, 64, x + w / 2, PAD + 96, c["accent2"], "middle", tracking=-0.03)[0])
        body.append(text("Inter-Regular.ttf", small, 20, x + w / 2, PAD + 136, c["muted"], "middle")[0])
    return frame(c, PAD * 2 + h, body, "28 MB, 2.8 % CPU, 6 ms to open", glow=(0.5, 0.0))


if __name__ == "__main__":
    import art

    cards = {"features": art.features, "sources": art.sources_card, "agents": art.agents_card, "install": install, "stats": stats}
    out = ROOT / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in cards.items():
        for look, c in LOOKS.items():
            (out / f"{name}-{look}.svg").write_text(draw(c))

