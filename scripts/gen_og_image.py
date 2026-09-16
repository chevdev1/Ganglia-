"""Generate assets/og-image.png (1200x630) for link previews.

Pixel-brand OG card: dark ground, dotted grid (matches .ground in
css/styles.css), GANGLIA wordmark, tagline, and a 16x8 node grid with
a handful of nodes lit in the accent blue to suggest "claimed".
Deterministic (seeded), no external assets, run with:
    python scripts/gen_og_image.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og-image.png"

W, H = 1200, 630
BG = (0, 0, 0)
FG = (242, 242, 242)
DIM = (122, 122, 122)
ACC = (77, 124, 255)
LINE = (31, 31, 31)
CELL = (22, 22, 22)

FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"
FONT_REG = "C:/Windows/Fonts/consola.ttf"


def draw_ground(draw: ImageDraw.ImageDraw) -> None:
    step = 16
    for y in range(0, H, step):
        for x in range(0, W, step):
            draw.point((x, y), fill=LINE)


def draw_node_grid(draw: ImageDraw.ImageDraw, ox: int, oy: int) -> None:
    rnd = random.Random(128)
    cols, rows, size, gap = 16, 8, 22, 5
    for r in range(rows):
        for c in range(cols):
            x = ox + c * (size + gap)
            y = oy + r * (size + gap)
            lit = rnd.random() < 0.32
            color = ACC if lit else CELL
            draw.rectangle([x, y, x + size, y + size], fill=color)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_ground(draw)
    draw.rectangle([18, 18, W - 19, H - 19], outline=DIM, width=2)

    wordmark = ImageFont.truetype(FONT_BOLD, 64)
    tagline = ImageFont.truetype(FONT_REG, 26)
    sub = ImageFont.truetype(FONT_REG, 20)

    draw.text((56, 64), "GANGLIA", font=wordmark, fill=FG)
    draw.text((60, 150), "One mind. 128 nodes.", font=tagline, fill=ACC)
    draw.text(
        (60, 470),
        "A shared digital character. 128 people hold its nodes.",
        font=sub,
        fill=DIM,
    )
    draw.text((60, 500), "ganglia-navy.vercel.app", font=sub, fill=DIM)

    draw_node_grid(draw, W - 56 - (16 * 27 - 5), 180)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
