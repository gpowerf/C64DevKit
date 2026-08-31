#!/usr/bin/env python3
"""Composite the chrome title onto assets/marketing/cover_no_text.jpeg.

Matches the game's splash-screen treatment: Orbitron ExtraBold caps with
the white-sheen / gold / orange chrome gradient (smooth variant for the
painted cover), dark outline + soft drop shadow for legibility over art.

Layout mirrors the original cover: two centered lines — "LAST STAR" over
"SYSTEM" — in the dark console band at lower center.

Usage:
    python3 tools/cover_title.py            # write cover_titled.png
Options:
    --size N      title scale override (px font size at 2x supersample)
    --check       also write cover_title_preview.jpg (downscaled look)
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "marketing" / "cover_no_text.jpeg"
DST = ROOT / "assets" / "marketing" / "cover_titled.png"
FONT = ROOT / "tools" / "fonts" / "Orbitron.ttf"
VARIATION = "ExtraBold"

SS = 2                              # supersample factor
TRACK = 14                          # extra letter spacing, px at 2x
STROKE = 7                          # dark outline width, px at 2x
SHADOW_OFFSET = (0, 14)
SHADOW_BLUR = 16
SHADOW_ALPHA = 200

TITLE = "LAST STAR SYSTEM"          # single line, across the bottom
TITLE_SIZE = 168                    # px at 2x — same as the old LAST STAR line
TITLE_MAX_W = 0.90                  # of canvas width (safety shrink only)
TITLE_CY = 0.905                    # vertical center, fraction of height

# chrome gradient stops (pos 0..1 across the letter height) — the splash
# logo is white on top, gold body, orange base; keep the sheen bright
GRADIENT = [
    (0.00, (255, 255, 255)),
    (0.24, (255, 255, 255)),
    (0.48, (255, 221, 119)),
    (0.72, (255, 180, 60)),
    (1.00, (224, 96, 10)),
]
OUTLINE = (26, 12, 6, 255)


def gradient_strip(w, h, stops):
    """Vertical gradient image w x h through the given (pos, rgb) stops."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                f = 0 if p1 == p0 else (t - p0) / (p1 - p0)
                col = tuple(round(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))
                break
        else:
            col = stops[-1][1]
        for x in range(w):
            px[x, y] = col
    return img


def tracked_width(font, text, track):
    return sum(font.getlength(ch) for ch in text) + track * (len(text) - 1)


def draw_tracked(draw, xy, text, font, track, fill=None, mask_img=None,
                 stroke=0, stroke_fill=None):
    """Draw text letter by letter for even tracking. If mask_img is given,
    paint solid white glyphs onto it instead (for the gradient mask)."""
    x, y = xy
    for ch in text:
        if mask_img is not None:
            d = ImageDraw.Draw(mask_img)
            d.text((x, y), ch, font=font, fill=255,
                   stroke_width=stroke, stroke_fill=255)
        elif stroke:
            draw.text((x, y), ch, font=font, fill=fill,
                      stroke_width=stroke, stroke_fill=stroke_fill)
        else:
            draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + track


def line_layer(canvas_w, canvas_h, text, size, cy, font_var=VARIATION):
    """Render one title line as (RGBA layer) at supersampled scale."""
    font = ImageFont.truetype(str(FONT), size)
    try:
        font.set_variation_by_name(font_var)
    except Exception:
        pass

    w = tracked_width(font, text, TRACK)
    pad = STROKE + SHADOW_BLUR + 8
    layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    ox = (canvas_w - w) / 2
    oy = cy * canvas_h - size * 0.5

    # 1. soft drop shadow (blurred solid glyphs)
    mask = Image.new("L", (canvas_w, canvas_h), 0)
    draw_tracked(None, (ox, oy), text, font, TRACK, mask_img=mask)
    shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    black = Image.new("RGBA", mask.size, (0, 0, 0, SHADOW_ALPHA))
    shadow.paste(black, SHADOW_OFFSET, mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR / 2))
    layer = Image.alpha_composite(layer, shadow)

    # 2. dark outline (stroked glyphs)
    stroke_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw_tracked(None, (ox, oy), text, font, TRACK,
                 mask_img=stroke_layer.split()[3]) if False else None
    mask_s = Image.new("L", (canvas_w, canvas_h), 0)
    draw_tracked(None, (ox, oy), text, font, TRACK, mask_img=mask_s,
                 stroke=STROKE)
    dark = Image.new("RGBA", mask_s.size, OUTLINE)
    stroke_layer.paste(dark, (0, 0), mask_s)
    layer = Image.alpha_composite(layer, stroke_layer)

    # 3. chrome gradient through the plain glyph mask
    bbox = mask.getbbox()
    if bbox:
        grad = gradient_strip(bbox[2] - bbox[0], bbox[3] - bbox[1], GRADIENT)
        grad_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        grad_layer.paste(grad, (bbox[0], bbox[1]))
        glyph_mask = mask.crop(bbox)
        full = Image.new("L", (canvas_w, canvas_h), 0)
        full.paste(glyph_mask, (bbox[0], bbox[1]))
        layer.paste(grad_layer, (0, 0), full)
    return layer


def main():
    import sys
    size1 = TITLE_SIZE
    for i, a in enumerate(sys.argv):
        if a == "--size":
            size1 = int(sys.argv[i + 1])

    src = Image.open(SRC).convert("RGB")
    W, H = src.width * SS, src.height * SS
    canvas = src.resize((W, H), Image.LANCZOS).convert("RGBA")

    # safety: shrink only if the single line would overflow the canvas
    probe = ImageFont.truetype(str(FONT), size1)
    try:
        probe.set_variation_by_name(VARIATION)
    except Exception:
        pass
    while tracked_width(probe, TITLE, TRACK) > TITLE_MAX_W * W and size1 > 40:
        size1 -= 4
        probe = ImageFont.truetype(str(FONT), size1)
        try:
            probe.set_variation_by_name(VARIATION)
        except Exception:
            pass

    canvas = Image.alpha_composite(
        canvas, line_layer(W, H, TITLE, size1, TITLE_CY))

    out = canvas.convert("RGB").resize((src.width, src.height), Image.LANCZOS)
    out.save(DST, quality=95)
    print(f"wrote {DST}  (line1 size {size1}px @2x)")


if __name__ == "__main__":
    main()
