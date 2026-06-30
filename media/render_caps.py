#!/usr/bin/env python3
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BU = "/Users/dhruvjain/gaffer/media/build"
AU = "/Users/dhruvjain/gaffer/media/audio"
OUT = os.path.join(BU, "caps"); os.makedirs(OUT, exist_ok=True)
W, H = 1920, 1080
FONT = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
WHITE = (242, 246, 242, 255)
GREEN = (116, 209, 149, 255)   # brand --green-soft
PAD = 0.45

# each caption = list of lines; each line = list of (text, color)
W_, G_ = "w", "g"
CAPS = [
    [[("An AI catching ", W_), ("its own lie", G_)]],
    [[("It ", W_), ("referees every answer", G_)]],
    [[("It rewrites ", W_), ("its own playbook", G_)]],
    [[("We tried to fool the referee.", W_)], [("It caught all ", W_), ("22", G_), (".", W_)]],
    [[("Every decision, traced in ", W_), ("Arize Phoenix", G_)]],
    [[("The use case: the ", W_), ("World Cup", G_)]],
    [[("Grounds ", G_), ("every fact", G_), (", or says it can't", W_)]],
    [[("GAFFER", G_), ("    catches and fixes its own lies", W_)]],
]

def col(c): return GREEN if c == G_ else WHITE

ARROW_W = 78  # advance width for the drawn arrow glyph

def run_width(text, font):
    return ARROW_W if text == "__ARROW__" else font.getlength(text)

def line_width(runs, font):
    return sum(run_width(t, font) for t, _ in runs)

def draw_arrow(d, x, ycenter, color, fs):
    # vector arrow: shaft + triangular head, sized to font
    sh = max(3, fs // 16)
    x0 = x + 12; x1 = x + ARROW_W - 24; y = ycenter
    d.line([(x0, y), (x1, y)], fill=color, width=sh)
    hl = fs * 0.34
    d.polygon([(x1 - 2, y - hl / 2), (x + ARROW_W - 6, y), (x1 - 2, y + hl / 2)], fill=color)

def fit_font(cap, base=62, maxw=1660, minf=30):
    fs = base
    while fs > minf:
        f = ImageFont.truetype(FONT, fs)
        if all(line_width(line, f) <= maxw for line in cap):
            return f, fs
        fs -= 2
    return ImageFont.truetype(FONT, minf), minf

def render(cap, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # bottom scrim gradient for legibility (baked, continuous across scenes)
    scrim = Image.new("L", (1, H), 0)
    for y in range(H):
        if y < 560:
            a = 0
        else:
            a = int(165 * (y - 560) / (H - 560))
        scrim.putpixel((0, y), a)
    scrim = scrim.resize((W, H))
    dark = Image.new("RGBA", (W, H), (4, 8, 6, 255))
    img = Image.composite(dark, img, scrim)
    d = ImageDraw.Draw(img)

    font, fs = fit_font(cap)
    nlines = len(cap)
    lh = int(fs * 1.22)
    block_h = lh * nlines
    y0 = 956 - block_h + lh  # baseline-ish anchor near lower third
    asc, desc = font.getmetrics()
    for li, line in enumerate(cap):
        lw = line_width(line, font)
        x = (W - lw) / 2
        y = 880 - (nlines - 1) * lh // 2 + li * lh
        for text, c in line:
            if text == "__ARROW__":
                draw_arrow(d, x, y + asc * 0.55, col(c), fs)
                x += ARROW_W
                continue
            # shadow
            d.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0, 150))
            # main with stroke
            d.text((x, y), text, font=font, fill=col(c),
                   stroke_width=2, stroke_fill=(6, 14, 10, 235))
            x += font.getlength(text)
    img.save(path)
    return fs

# read durations, compute scene windows on the video_raw timeline
dur = {}
with open(os.path.join(AU, "durations.txt")) as fh:
    for ln in fh:
        i, v = ln.split(); dur[int(i)] = float(v)

t = 0.0; wins = []
for i in range(1, len(CAPS) + 1):
    seg = dur[i] + PAD
    wins.append((i, t, t + seg)); t += seg

with open(os.path.join(OUT, "windows.txt"), "w") as fh:
    for i, s, e in wins:
        fs = render(CAPS[i - 1], os.path.join(OUT, f"cap_{i}.png"))
        fh.write(f"{i} {s:.3f} {e:.3f}\n")
        print(f"cap_{i}: fs={fs}  window {s:.2f}-{e:.2f}")
print("TOTAL", round(t, 2))
