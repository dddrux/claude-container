#!/usr/bin/env python3
"""Gera assets/icon.png (512) e assets/icon.ico (16-256) — mesmo desenho do ícone do app. Requer Pillow."""
import math
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
LENGTHS = [1.0, 0.74, 0.92, 0.68, 1.0, 0.78, 0.90, 0.70, 1.0, 0.72, 0.94, 0.76]


def render(size=1024, color="#D97757"):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.26, fill=color)
    r, w, c = size * 0.38, size * 0.38 * 0.20, size / 2
    for i, ln in enumerate(LENGTHS):
        a = math.radians(i * 30 + 8)
        L = r * ln - w / 2
        x, y = c + L * math.sin(a), c - L * math.cos(a)
        d.line((c, c, x, y), fill="white", width=int(w))
        for px, py in ((c, c), (x, y)):
            d.ellipse((px - w / 2, py - w / 2, px + w / 2, py + w / 2), fill="white")
    return img


if __name__ == "__main__":
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    big = render(1024)
    big.resize((512, 512), Image.LANCZOS).save(out / "icon.png")
    big.resize((256, 256), Image.LANCZOS).save(
        out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    (out / "icons").mkdir(exist_ok=True)  # tamanhos hicolor usados pelo install.sh (GNOME)
    for n in (16, 24, 32, 48, 64, 128, 256, 512):
        big.resize((n, n), Image.LANCZOS).save(out / "icons" / f"{n}.png")
    print("ok")
