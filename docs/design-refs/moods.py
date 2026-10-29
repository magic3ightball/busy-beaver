"""Render our own space-time diagrams in each mood palette for the reference board.

Run from busy-beaver/: python3 docs/design-refs/moods.py
Writes docs/design-refs/img/mood-<key>-<a|b>.png
"""
import os
import sys

from PIL import Image, ImageChops, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import render  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
# Two BB(2,5) holdouts from the page: the self-similar one and the lattice fan.
MACHINES = [("a", "1RB0RB---1RB2LA_2LA4RA3LB0RB---", 300_000, 400),
            ("b", "1RB---------2LB_2LB3LA0RB4RB1LB", 2_000_000, 400)]

MOODS = {
    "mono":     dict(bg="#f3efe6", sym=["#1b1b1b", "#5a5a5a", "#9a9a9a", "#c9c5bb"], head="#c8102e", fx=["grain"]),
    "night":    dict(bg="#070b1e", sym=["#7fd4ff", "#b48cff", "#ff7ac6", "#ffe08a"], head="#ffffff", fx=["glow"]),
    "editorial": dict(bg="#fbf7ef", sym=["#2b4c7e", "#d1495b", "#edae49", "#66a182"], head="#111111", fx=[]),
    "vintage":  dict(bg="#e9dcc3", sym=["#d72638", "#1b3a6b", "#f2b705", "#e8a0a8"], head="#111111", fx=["grain", "vignette"]),
    "pastel":   dict(bg="#fff9f2", sym=["#f4a3bd", "#9fd3e6", "#ffd29d", "#bfe6b8"], head="#ff5d73", fx=["riso", "grain"]),
    "neon":     dict(bg="#0d0221", sym=["#08f7fe", "#fe53bb", "#f5d300", "#00ff9f"], head="#ffffff", fx=["glow"]),
}


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def grain(img, amount=14):
    n = Image.effect_noise(img.size, 40).convert("L")
    n = n.point(lambda v: 128 + (v - 128) * amount // 40)
    return ImageChops.overlay(img, Image.merge("RGB", (n, n, n)))


def glow(img, bg):
    base = Image.new("RGB", img.size, bg)
    light = ImageChops.subtract(img, base)
    near = light.filter(ImageFilter.GaussianBlur(3)).point(lambda v: v * 5 // 10)
    far = light.filter(ImageFilter.GaussianBlur(12)).point(lambda v: v * 3 // 10)
    return ImageChops.screen(ImageChops.screen(img, near), far)


def vignette(img):
    w, h = img.size
    m = Image.radial_gradient("L").resize((w, h)).point(lambda v: 255 - v * 70 // 255)
    dark = Image.new("RGB", img.size, (60, 40, 20))
    return Image.composite(img, dark, m)


def riso(img, bg):
    # Misregister the red channel a couple of pixels, like a two-drum print.
    r, g, b = img.split()
    r = ImageChops.offset(r, 2, 1)
    out = Image.merge("RGB", (r, g, b))
    return Image.blend(out, Image.new("RGB", img.size, bg), 0.08)


def main():
    os.makedirs(OUT, exist_ok=True)
    for key, m in MOODS.items():
        bg = rgb(m["bg"])
        render.PALETTE[:] = [bg] + [rgb(c) for c in m["sym"]] * 3
        render.HEAD = rgb(m["head"])
        for tag, tm, steps, rows in MACHINES:
            img, _ = render.render(tm, steps, rows=rows, max_w=520)
            k = min(520 / img.width, 520 / img.height)
            img = img.resize((round(img.width * k), round(img.height * k)), Image.NEAREST)
            box = Image.new("RGB", (520, max(img.height, 300) if tag == "b" else 520), bg)
            box.paste(img, ((box.width - img.width) // 2, (box.height - img.height) // 2))
            img = box
            for fx in m["fx"]:
                img = {"grain": lambda i: grain(i), "glow": lambda i: glow(i, bg),
                       "vignette": vignette, "riso": lambda i: riso(i, bg)}[fx](img)
            img.save(os.path.join(OUT, f"mood-{key}-{tag}.png"))
            print(key, tag, img.size)


if __name__ == "__main__":
    main()
