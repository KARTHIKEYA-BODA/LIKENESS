"""Draws fake garment photos (colour + pattern + silhouette) so the demo works with zero downloads.
Real product photos uploaded through the admin panel work exactly the same way."""
import colorsys
import random

from PIL import Image, ImageDraw, ImageFilter

S = 1024  # work at 2x then downsample for smooth edges

SILHOUETTES = {
    "dress": [(400, 130), (430, 130), (470, 300), (554, 300), (594, 130), (624, 130), (660, 380),
              (840, 900), (184, 900), (364, 380)],
    "top": [(300, 220), (420, 180), (480, 240), (544, 240), (604, 180), (724, 220), (860, 380),
            (760, 450), (704, 390), (700, 860), (324, 860), (320, 390), (264, 450), (164, 380)],
    "skirt": [(350, 290), (674, 290), (860, 860), (164, 860)],
    "sweater": [(300, 200), (420, 170), (480, 230), (544, 230), (604, 170), (724, 200), (900, 660),
                (810, 690), (704, 430), (700, 860), (324, 860), (320, 430), (214, 690), (124, 660)],
}

PALETTE = {
    "Red": (200, 40, 50), "Navy": (30, 45, 100), "Forest": (35, 100, 60), "Mustard": (222, 168, 40),
    "Black": (28, 28, 32), "Ivory": (238, 230, 214), "Pink": (238, 140, 170), "Sky": (110, 170, 225),
    "Lavender": (170, 150, 220), "Olive": (110, 118, 55), "Teal": (30, 140, 140), "Orange": (232, 110, 40),
}

PATTERNS = ["Solid", "Striped", "Polka Dot", "Checked", "Floral"]
NOUNS = {
    "dress": ["Summer Dress", "Midi Dress", "Slip Dress", "Sundress"],
    "top": ["Tee", "Boxy Top", "Cotton Top", "Relaxed Tee"],
    "skirt": ["Pleated Skirt", "A-line Skirt", "Midi Skirt", "Flare Skirt"],
    "sweater": ["Knit Sweater", "Pullover", "Crew Sweater", "Cosy Jumper"],
}
CATEGORY = {"dress": "Dresses", "top": "Tops", "skirt": "Skirts", "sweater": "Sweaters"}


def _luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _contrast(base):
    return (250, 247, 240) if _luma(base) < 140 else tuple(int(v * 0.35) for v in base)


def _pattern_layer(pattern, base, rng):
    img = Image.new("RGB", (S, S), base)
    d = ImageDraw.Draw(img, "RGBA")
    alt = _contrast(base)
    if pattern == "Striped":
        w = rng.choice([40, 56, 72])
        if rng.random() < 0.5:
            for x in range(0, S, w * 2):
                d.rectangle([x, 0, x + w, S], fill=alt + (255,))
        else:
            for y in range(0, S, w * 2):
                d.rectangle([0, y, S, y + w], fill=alt + (255,))
    elif pattern == "Polka Dot":
        step, r = rng.choice([(70, 16), (90, 22), (56, 12)])
        for row, y in enumerate(range(0, S + step, step)):
            for x in range(-step, S + step, step):
                ox = step // 2 if row % 2 else 0
                d.ellipse([x + ox - r, y - r, x + ox + r, y + r], fill=alt + (255,))
    elif pattern == "Checked":
        w = rng.choice([48, 64, 80])
        for x in range(0, S, w * 2):
            d.rectangle([x, 0, x + w, S], fill=alt + (90,))
        for y in range(0, S, w * 2):
            d.rectangle([0, y, S, y + w], fill=alt + (90,))
    elif pattern == "Floral":
        petal = rng.choice([(250, 240, 235), (255, 214, 224), (255, 226, 160)])
        for _ in range(46):
            cx, cy, r = rng.randint(0, S), rng.randint(0, S), rng.randint(16, 30)
            d.ellipse([cx - r * 2.2, cy - r * 0.9, cx - r * 0.6, cy + r * 0.9], fill=(60, 120, 70, 255)) if rng.random() < .6 else None
            for k in range(5):
                a = k * 72 + rng.randint(0, 20)
                px = cx + r * 1.1 * _cos(a)
                py = cy + r * 1.1 * _sin(a)
                d.ellipse([px - r * .8, py - r * .8, px + r * .8, py + r * .8], fill=petal + (255,))
            d.ellipse([cx - r * .5, cy - r * .5, cx + r * .5, cy + r * .5], fill=(235, 170, 40, 255))
    return img


def _cos(deg):
    import math
    return math.cos(math.radians(deg))


def _sin(deg):
    import math
    return math.sin(math.radians(deg))


def make_garment(kind: str, color_name: str, pattern: str, seed: int = 0) -> Image.Image:
    rng = random.Random(seed)
    base = PALETTE[color_name]
    bg = Image.new("RGB", (S, S), (243, 243, 245))
    cloth = _pattern_layer(pattern, base, rng)

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(SILHOUETTES[kind], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.5))

    # soft drop shadow
    shadow = Image.new("L", (S, S), 0)
    shadow.paste(mask, (10, 22))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.28))
    bg.paste((30, 30, 40), mask=shadow)

    # gentle fabric shading (darker toward the edges)
    shade = mask.filter(ImageFilter.GaussianBlur(38))
    shaded = Image.composite(cloth, Image.new("RGB", (S, S), tuple(int(c * .72) for c in base)), shade)
    bg.paste(shaded, mask=mask)

    ImageDraw.Draw(bg).polygon(SILHOUETTES[kind], outline=tuple(int(c * .6) for c in base), width=4)
    return bg.resize((512, 512), Image.LANCZOS)

