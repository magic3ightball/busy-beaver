"""Images for the light-minimal mock (docs/design-refs/mock/index.html).

Run from busy-beaver/: python3 docs/design-refs/mock/mock.py
Diagrams are rendered large, cropped to their ink, then downscaled smoothly so they
read as shapes rather than noisy pixel strips.
"""
import os
import sys

from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
import render  # noqa: E402

OUT = os.path.join(HERE, "img")
INK = [(255, 255, 255), (17, 17, 17)] + [(17, 17, 17)] * 8          # everything non-zero = black
COLOR = [(255, 255, 255), (23, 23, 23), (99, 91, 255), (0, 190, 230), (255, 89, 150),
         (130, 200, 40), (148, 163, 184), (180, 120, 255), (120, 120, 120), (200, 150, 90)]


def shot(name, tm, steps, palette, head, rows, max_w, out_w, aspect=None):
    render.PALETTE[:] = palette
    render.HEAD = head
    img, _ = render.render(tm, steps, rows=rows, max_w=max_w)
    bg = Image.new("RGB", img.size, palette[0])
    box = ImageChops.difference(img, bg).getbbox() or (0, 0, *img.size)
    img = img.crop(box)
    if aspect:  # pad to a fixed aspect so cards line up, keeping the shape centred at the bottom
        w, h = img.size
        W, H = (w, round(w / aspect)) if w / h > aspect else (round(h * aspect), h)
        pad = Image.new("RGB", (W, H), palette[0])
        pad.paste(img, ((W - w) // 2, H - h))
        img = pad
    img = img.resize((out_w, round(img.height * out_w / img.width)), Image.LANCZOS)
    img.save(os.path.join(OUT, name))
    print(name, img.size)


os.makedirs(OUT, exist_ok=True)
BB5 = "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA"
FAN = "1RB---------2LB_2LB3LA0RB4RB1LB"
# Hero A: BB(5) champion's whole run as one black silhouette (Vercel / Rauno: one strong shape).
shot("hero-a.png", BB5, 47176870, INK, (17, 17, 17), 700, 1400, 1400)
# Hero B: colourful fan machine, large and smooth (Stripe: one vivid image bleeding off the edge).
shot("hero-b.png", FAN, 100000000, COLOR, (255, 90, 31), 900, 900, 1400)
# Section cards: the three famous cryptids, same aspect, no empty margins.
for key, tm in (("antihydra", "1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA"),
                ("hydra", "1RB3RB---3LA1RA_2LA3RA4LB0LB0LA"),
                ("bigfoot", "1RB2RA1LC_2LC1RB2RB_---2LA1LA")):
    shot(f"{key}.png", tm, 30000000, COLOR, (255, 90, 31), 500, 900, 900, aspect=4 / 3)
