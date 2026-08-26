#!/usr/bin/env python3
"""Chrome block-logo title font for the dodge splash screen.

Renders "LAST STAR SYSTEM" as 16x24 pixel letterforms (2 cols x 3 rows
of 8x8 charset glyphs per letter), styled after the marketing cover's
chrome title: bold letterforms with a white sheen on top, yellow body,
orange base — the gradient is applied via colour RAM per 8x8 cell.

Outputs:
  assets/title_font.bin   48 glyphs x 8 bytes (charset slots $B0-$DF)
  sprite_edit/title_preview.png   full-splash mockup for review

The 8 unique letters (L A S T R Y E M) get glyph slots $B0 + n*6 ..
$B0 + n*6 + 5; screen codes $B0-$DF are unused by the game (the solid
block $A0 and all text glyphs stay intact).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]      # games/dodge
ASSETS = ROOT / "assets"
PREVIEW = ROOT / "sprite_edit" / "title_preview.png"

W, H = 24, 21                 # C64 screen (cols, rows) for the mockup
CELL_W, CELL_H = 8, 8         # charset glyph size
LETTER_W, LETTER_H = 2, 3     # letter = 2x3 glyph cells (16x24 px)
N_FRAMES = 1

TITLE = "LAST STAR SYSTEM"
LETTERS = "LASTRYEM"          # unique letters, index 1..8 (0 = space)
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

# chrome gradient per glyph row: white sheen / yellow body / orange base
ROW_COLOURS = [1, 7, 8]       # white, yellow, orange


def render_letter(ch, font_path, size):
    """Render one character bold: draw large, crop, downscale to fill
    the 16x24 cell (downscaling thick strokes keeps them bold), centred."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(font_path, size)
    big = size * 2
    img = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(img)
    d.text((big // 3, big // 4), ch, fill=255, font=font)
    bbox = img.getbbox()
    if not bbox:
        return [[0] * 16 for _ in range(24)]
    cropped = img.crop(bbox)
    w, h = cropped.size
    scale = min(16 / w, 24 / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    cropped = cropped.resize((nw, nh), Image.LANCZOS)
    out = Image.new("L", (16, 24), 0)
    out.paste(cropped, ((16 - nw) // 2, (24 - nh) // 2))
    px = out.load()
    return [[1 if px[c, r] >= 100 else 0 for c in range(16)] for r in range(24)]


def build_letters():
    letters = {}
    font_path = FONT_CANDIDATES[0]   # DejaVu Serif Bold — closest to the cover
    for ch in LETTERS:
        letters[ch] = render_letter(ch, font_path, 64)
    print(f"font: {font_path.split('/')[-1]} @ 64, downscaled to 16x24")
    return letters


def split_glyphs(letters):
    """Letter grid -> 6 glyphs (8x8) per letter, in LETTERS order."""
    glyphs = []
    for ch in LETTERS:
        g = letters[ch]
        for gr in range(LETTER_H):
            for gc in range(LETTER_W):
                glyph = []
                for r in range(8):
                    row = []
                    for c in range(8):
                        row.append(g[gr * 8 + r][gc * 8 + c])
                    glyph.append(row)
                glyphs.append(glyph)
    return glyphs


def write_bin(glyphs):
    out = bytearray()
    for glyph in glyphs:
        for row in glyph:
            b = 0
            for i, v in enumerate(row):
                if v:
                    b |= 1 << (7 - i)
            out.append(b)
    (ASSETS / "title_font.bin").write_bytes(bytes(out))
    print(f"wrote assets/title_font.bin ({len(out)} bytes, {len(glyphs)} glyphs)")


def preview(letters, out_path):
    """Mock the full splash at native C64 resolution (320x200), upscaled."""
    from PIL import Image, ImageDraw, ImageFont
    scale = 3
    img = Image.new("RGB", (320, 200), (0, 0, 0))
    px = img.load()

    # side shimmer bars (static hint of the animated ones)
    bar_cols = [(180, 120, 255), (120, 255, 180), (255, 200, 120),
                (120, 180, 255), (255, 120, 120), (200, 200, 90)]
    for r in range(200):
        for c in list(range(0, 6)) + list(range(34, 40)):
            if (r + c) % 4 != 0:
                px[c, r] = bar_cols[(r * 3 + c) % 6]

    # title: 16 positions x 2 cols x 3 rows of glyphs, chrome gradient
    colour_rgb = {1: (255, 255, 255), 7: (255, 255, 0), 8: (255, 128, 0)}
    for pos, ch in enumerate(TITLE):
        li = LETTERS.find(ch) + 1 if ch in LETTERS else 0
        if li == 0:
            continue
        base_col = 4 + pos * LETTER_W
        for gr in range(LETTER_H):
            for gc in range(LETTER_W):
                for r in range(8):
                    for c in range(8):
                        if letters[ch][gr * 8 + r][gc * 8 + c]:
                            px[(base_col + gc) * 8 + c,
                               (8 + gr) * 8 + r] = colour_rgb[ROW_COLOURS[gr]]

    # subtitle + credit in grey at their game positions
    font = ImageFont.truetype(FONT_CANDIDATES[1], 8)
    d = ImageDraw.Draw(img)
    d.text((11 * 8, 14 * 8 + 1), "press fire to play",
           fill=(170, 170, 170), font=font)
    d.text((14 * 8, 22 * 8 + 1), "gpowerf 2026",
           fill=(170, 170, 170), font=font)

    img = img.resize((320 * scale, 200 * scale), Image.NEAREST)
    img.save(out_path)
    print(f"preview: {out_path}")


def main():
    letters = build_letters()
    glyphs = split_glyphs(letters)
    write_bin(glyphs)
    preview(letters, str(PREVIEW))
    if "--write-only" not in sys.argv:
        print("review the preview before wiring the splash")


if __name__ == "__main__":
    main()
