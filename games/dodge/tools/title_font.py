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
    ("serif-ref",  "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    ("dejavu-sans","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("liberation", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ("fira-cond",  "/usr/share/fonts/opentype/fira/FiraSansCondensed-Bold.otf"),
]

# chrome gradient per glyph row: white sheen / yellow body / orange base
ROW_COLOURS = [1, 7, 8]       # white, yellow, orange


def render_letter(ch, font_path, size, dilate=0):
    """Render one character bold: draw large, crop, downscale to fill
    the 16x24 cell (downscaling thick strokes keeps them bold), centred.
    `dilate` 1 adds a pixel beyond every set pixel for a fatter stroke."""
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
    grid = [[1 if px[c, r] >= 100 else 0 for c in range(16)] for r in range(24)]
    if dilate:
        grid = _dilate(grid)
    return grid


def _dilate(grid):
    """8-neighbour dilation: every empty cell next to a set pixel becomes
    set (fatten the letterform by ~1px, then thin the holes back)."""
    ng = [row[:] for row in grid]
    for r in range(24):
        for c in range(16):
            if grid[r][c]:
                continue
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < 24 and 0 <= cc < 16 and grid[rr][cc]:
                        ng[r][c] = 1
                        break
    return ng


def build_letters(font_path, dilate=0):
    letters = {}
    for ch in LETTERS:
        letters[ch] = render_letter(ch, font_path, 64, dilate)
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
    font = ImageFont.truetype(FONT_CANDIDATES[1][1], 8)
    d = ImageDraw.Draw(img)
    d.text((11 * 8, 14 * 8 + 1), "press fire to play",
           fill=(170, 170, 170), font=font)
    d.text((14 * 8, 22 * 8 + 1), "gpowerf 2026",
           fill=(170, 170, 170), font=font)

    img = img.resize((320 * scale, 200 * scale), Image.NEAREST)
    img.save(out_path)
    print(f"preview: {out_path}")


def compare_sheet(out_path):
    """Render 'LAST STAR SYSTEM' in every candidate font (and weight),
    one row each, for style review."""
    from PIL import Image, ImageDraw, ImageFont
    scale = 5
    row_w, row_h = 320 * scale, 200 * scale
    rows = [(name, path, d) for name, path in FONT_CANDIDATES for d in (0, 1)]
    sheet = Image.new("RGB", (row_w + 260, row_h * len(rows)), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    for i, (name, path, d) in enumerate(rows):
        letters = build_letters(path, dilate=d)
        img = Image.new("RGB", (320, 200), (0, 0, 0))
        px = img.load()
        colour_rgb = {1: (255, 255, 255), 7: (255, 255, 0), 8: (255, 128, 0)}
        for pos, ch in enumerate(TITLE):
            li = LETTERS.find(ch) + 1 if ch in LETTERS else 0
            if li == 0:
                continue
            for gr in range(LETTER_H):
                for gc in range(LETTER_W):
                    for r in range(8):
                        for c in range(8):
                            if letters[ch][gr * 8 + r][gc * 8 + c]:
                                px[(4 + pos * 2 + gc) * 8 + c,
                                   (8 + gr) * 8 + r] = colour_rgb[ROW_COLOURS[gr]]
        big = img.resize((320 * scale, 200 * scale), Image.NEAREST)
        sheet.paste(big, (0, i * row_h))
        draw.text((row_w + 12, i * row_h + 10), f"{name}\n{'' if not d else '+1px dilation'}",
                  fill=(255, 255, 255))
    sheet.save(out_path)
    print(f"comparison: {out_path}")


def main():
    if "--compare" in sys.argv:
        compare_sheet(ROOT / "sprite_edit" / "title_compare.png")
        return
    choice = None
    for i, (name, path) in enumerate(FONT_CANDIDATES):
        if f"--font-{i}" in sys.argv or f"--font-{name}" in sys.argv:
            choice = (name, path)
            break
    if choice is None:
        choice = FONT_CANDIDATES[0]
    dilate = 1 if "--dilate" in sys.argv else 0
    letters = build_letters(choice[1], dilate)
    glyphs = split_glyphs(letters)
    write_bin(glyphs)
    preview(letters, str(PREVIEW))
    print(f"font: {choice[0]} (dilate={dilate})")


if __name__ == "__main__":
    main()
