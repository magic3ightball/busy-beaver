"""Render space-time diagrams with ../bb diagram.

Each image: time runs top to bottom, tape cells left to right.
Two themes (light minimal page, picked from docs/design-refs/modern.html): background =
symbol 0, ink/purple/cyan/pink/... = symbols 1..9, orange = head. Pass `paths` to write
both themes from a single simulation.
"""
import os
import struct
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BB = os.path.join(ROOT, "bb")
THEMES = {
    "light": dict(palette=[(255, 255, 255), (23, 23, 23), (99, 91, 255), (0, 190, 230),
                           (255, 89, 150), (130, 200, 40), (148, 163, 184), (180, 120, 255),
                           (120, 120, 120), (200, 150, 90)], head=(255, 90, 31)),
    "dark": dict(palette=[(13, 13, 13), (237, 237, 237), (140, 133, 255), (40, 210, 245),
                          (255, 110, 165), (160, 225, 70), (148, 163, 184), (195, 150, 255),
                          (150, 150, 150), (215, 170, 110)], head=(255, 110, 50)),
}
PALETTE = THEMES["light"]["palette"]
HEAD = THEMES["light"]["head"]


def diagram(tm, steps, rows, tmp):
    subprocess.run([BB, "diagram", tm, str(steps), str(rows), tmp],
                   check=True, capture_output=True)
    with open(tmp, "rb") as f:
        w, h, every = struct.unpack("<iiq", f.read(16))
        cells = f.read(w * h)
        heads = struct.unpack(f"<{h}i", f.read(4 * h))
    return w, h, every, cells, heads


def colorize(idx, palette, head):
    """idx: 'P' image, index = symbol*9 + density step (0..8), 255 = head."""
    bg, pal = palette[0], []
    for i in range(256):
        if i == 255:
            c = head
        elif i // 9 < 1 or i // 9 >= 10:
            c = bg
        else:
            sym, q = divmod(i, 9)
            col = palette[sym % len(palette)]
            f = 1.0 if q == 8 else 0.35 + 0.65 * q / 8
            c = tuple(round(b + (a - b) * f) for a, b in zip(col, bg))
        pal.extend(c)
    out = idx.copy()
    out.putpalette(pal)
    return out.convert("RGB")


def render(tm, steps, rows=400, max_w=800, path=None, tmp=None, min_scale=1, paths=None):
    """Write `path` with the current PALETTE/HEAD, or `paths` = {theme: file} for THEMES."""
    tmp = tmp or os.path.join(os.environ.get("TMPDIR", "/tmp"), f"bbdiag{os.getpid()}.bin")
    w, h, every, cells, heads = diagram(tm, steps, rows, tmp)
    # Downsample columns if the tape is wider than max_w. A merged pixel takes the
    # largest symbol's colour, faded toward the background by how many cells are 0,
    # so long runs show their texture instead of a solid block.
    k = max(1, -(-w // max_w))
    W = -(-w // k)
    idx = Image.new("P", (W, h), 0)
    px = idx.load()
    extents = []  # occupied tape width per row (first..last non-zero cell)
    for y in range(h):
        row = cells[y * w:(y + 1) * w]
        right = len(row.rstrip(b"\0"))
        extents.append(right - (len(row) - len(row.lstrip(b"\0"))) if right else 0)
        for X in range(W):
            seg = row[X * k:(X + 1) * k]
            s = max(seg) if seg else 0
            if s:
                q = 8 if k == 1 else 8 * (len(seg) - seg.count(0)) // len(seg)
                px[X, y] = (s % 10) * 9 + q
        if heads[y] >= 0:
            px[min(W - 1, heads[y] // k), y] = 255
    # Scale up small diagrams so they are readable.
    scale = max(min_scale, min(4, 600 // max(W, 1), 800 // max(h, 1)))
    if scale > 1:
        idx = idx.resize((W * scale, h * scale), Image.NEAREST)
    img = colorize(idx, PALETTE, HEAD)
    if path:
        img.save(path)
    for theme, p in (paths or {}).items():
        colorize(idx, THEMES[theme]["palette"], THEMES[theme]["head"]).save(p)
    return img, dict(width=w, rows=h, every=every, colscale=k, extents=extents)


def sheet(entries, path, steps, cols=6, cell=(260, 260)):
    """Contact sheet: entries = list of (tm, caption)."""
    rows = -(-len(entries) // cols)
    cw, ch = cell
    out = Image.new("RGB", (cols * cw, rows * (ch + 30)), (255, 255, 255))
    d = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    for i, (tm, cap) in enumerate(entries):
        img, _ = render(tm, steps, rows=ch, max_w=cw)
        img = img.resize(cell, Image.NEAREST)
        x, y = (i % cols) * cw, (i // cols) * (ch + 30)
        out.paste(img, (x, y))
        d.text((x + 3, y + ch + 2), tm[:44], fill=(0, 0, 0), font=font)
        d.text((x + 3, y + ch + 15), cap[:44], fill=(80, 80, 80), font=font)
    out.save(path)


if __name__ == "__main__":
    tm, steps, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    print(render(tm, steps, path=out)[1])
