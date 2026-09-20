"""Share cards: 1200x630 PNGs drawn server-side with Pillow, brand-matched to the site."""

from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG, FG, DIM, ACC, LINE, CELL = (0, 0, 0), (242, 242, 242), (122, 122, 122), (77, 124, 255), (31, 31, 31), (22, 22, 22)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow: fixed-size bitmap font
        return ImageFont.load_default()


def _base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(0, H, 16):
        for x in range(0, W, 16):
            d.point((x, y), fill=LINE)
    d.rectangle([18, 18, W - 19, H - 19], outline=DIM, width=2)
    d.text((56, 52), "GANGLIA", font=_font(46), fill=FG)
    return img, d


def _wrap(d: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=font) <= width:
            line = trial
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) == max_lines and " ".join(lines) != text.strip():
        lines[-1] = lines[-1].rstrip(".,;: ")[: max(0, len(lines[-1]) - 1)] + "…"
    return lines


def _meter(d: ImageDraw.ImageDraw, x: int, y: int, label: str, value: int) -> None:
    d.text((x, y), label, font=_font(18), fill=DIM)
    for i in range(10):
        d.rectangle([x + 120 + i * 16, y + 4, x + 120 + i * 16 + 12, y + 18], fill=FG if i < value else CELL)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def thought_card(*, thought_id: int, text: str, node_id: int | None, writer: str, trigger: str,
                 curiosity: int, intensity: int, warmth: int, digest: str | None) -> bytes:
    img, d = _base()
    who = f"node {node_id:03d}" if node_id is not None else "the room alone"
    d.text((56, 112), f"thought {thought_id}  ·  {trigger}  ·  {who}", font=_font(22), fill=ACC)
    body = _font(38)
    for i, line in enumerate(_wrap(d, text, body, W - 112, 7)):
        d.text((56, 170 + i * 52), line, font=body, fill=FG)
    _meter(d, 56, 548, "curiosity", curiosity)
    _meter(d, 380, 548, "intensity", intensity)
    _meter(d, 704, 548, "warmth", warmth)
    d.text((56, 584), f"writer: {writer}" + (f"   hash {digest}" if digest else ""), font=_font(18), fill=DIM)
    return _png(img)


def node_card(*, node_id: int, region: str, myth: str, blurb: str, status: str, relics: list[str], scenarios: int) -> bytes:
    img, d = _base()
    d.text((56, 130), f"{node_id:03d}", font=_font(190), fill=ACC)
    d.text((56, 350), f"{region} · {myth}", font=_font(34), fill=FG)
    for i, line in enumerate(_wrap(d, blurb, _font(26), 640, 3)):
        d.text((56, 404 + i * 36), line, font=_font(26), fill=DIM)
    facts = [status, f"{scenarios} scenarios"] + [r.replace("-", " ") for r in relics]
    d.text((56, 560), "   ·   ".join(facts), font=_font(22), fill=FG)
    rnd = random.Random(node_id + 1)
    size = 34
    for y in range(5):
        for x in range(3):
            on = rnd.random() > 0.5
            for cx in (x, 4 - x):
                d.rectangle([840 + cx * size, 150 + y * size, 840 + cx * size + size - 4, 150 + y * size + size - 4], fill=ACC if on else CELL)
    return _png(img)
