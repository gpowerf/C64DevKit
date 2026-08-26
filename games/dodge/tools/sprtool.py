#!/usr/bin/env python3
"""Sprite edit round-trip for games/dodge (LibreSprite workflow).

unpack: .spr files  -> animated GIFs in sprite_edit/ (1 GIF per sprite set)
pack:   edited GIFs -> .spr files in assets/sprites/

Each GIF is at NATIVE C64 resolution — one image pixel per sprite pixel
(24x21), one GIF frame per animation frame (frame 0 first).  Zoom in
inside the editor (LibreSprite: +/- keys or Ctrl+wheel) to draw.
White = solid pixel, black = transparent; the VIC-II colour comes from
spec/sprites.yaml, not the art.

Pack accepts any integer scale (auto-detected from the height), so an
exported zoomed sprite sheet also works, but the GIFs themselves stay
24x21.

Usage:
    python3 tools/sprtool.py unpack
    python3 tools/sprtool.py pack
    python3 tools/sprtool.py render <name>   # ASCII preview of a .spr
"""
import sys
import pathlib

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: pip install --user pillow")

ROOT = pathlib.Path(__file__).resolve().parents[1]  # games/dodge
SPR = ROOT / "assets" / "sprites"
WORK = ROOT / "sprite_edit"

SCALE = 1  # GIFs are native resolution; zoom in the editor instead

# GIF stem -> ordered .spr files (frame 0 first).
# Mirrored pairs (l1, d1) are listed so edits stay consistent, but note
# the base art is symmetric: r1/l1 and u1/d1 are exact mirrors.
SETS = {
    "ship_r": ["ship_r.spr", "ship_r1.spr"],
    "ship_l": ["ship_l.spr", "ship_l1.spr"],
    "ship_u": ["ship_u.spr", "ship_u1.spr"],
    "ship_d": ["ship_d.spr", "ship_d1.spr"],
    "skull": ["skull.spr", "skull1.spr", "skull2.spr", "skull3.spr",
              "skull4.spr", "skull5.spr", "skull6.spr", "skull7.spr"],
    "rock": ["rock.spr"],
}


def spr_to_image(path: pathlib.Path) -> Image.Image:
    """64-byte .spr -> 24x21 white-on-black image."""
    data = path.read_bytes()
    if len(data) != 64:
        sys.exit(f"{path.name}: expected 64 bytes, got {len(data)}")
    img = Image.new("L", (24, 21), 0)
    px = img.load()
    for r in range(21):
        for c in range(24):
            if data[r * 3 + c // 8] & (1 << (7 - c % 8)):
                px[c, r] = 255
    return img


def image_to_spr(img: Image.Image, path: pathlib.Path) -> None:
    """Image -> 64-byte .spr (white-ish opaque pixels = solid).

    Scale is auto-detected from the dimensions: the image must be
    24*scale x 21*scale for some integer scale >= 1.  A width wider
    than one frame (a sprite-sheet strip) is rejected — edit the GIF
    so frames stay stacked instead."""
    img = img.convert("RGBA")
    w, h = img.size
    if h % 21 or w % 24:
        sys.exit(f"{path.name}: bad size {w}x{h} — expected 24x21 "
                 f"(or an integer multiple, e.g. 8x = {24*8}x{21*8})")
    scale = h // 21
    if w // scale != 24:
        sys.exit(f"{path.name}: {w}x{h} is a multi-frame strip — "
                 f"save the animated GIF instead so frames stay stacked")
    px = img.load()
    out = bytearray(64)
    for r in range(21):
        for c in range(24):
            # sample the centre of each scaled block
            x = c * scale + scale // 2
            y = r * scale + scale // 2
            pr, pg, pb, pa = px[x, y]
            lum = (pr * 299 + pg * 587 + pb * 114) // 1000
            if pa >= 128 and lum >= 128:
                out[r * 3 + c // 8] |= 1 << (7 - c % 8)
    # preserve the original pad byte (unused by VIC-II; files differ: $00/$01)
    if path.exists():
        prev = path.read_bytes()
        out[63] = prev[63] if len(prev) == 64 else 0x01
    else:
        out[63] = 0x01
    path.write_bytes(bytes(out))
    print(f"wrote {path.name}")


def cmd_unpack() -> None:
    WORK.mkdir(exist_ok=True)
    for stem, files in SETS.items():
        frames = [spr_to_image(SPR / f) for f in files]
        if SCALE != 1:
            frames = [f.resize((24 * SCALE, 21 * SCALE), Image.NEAREST)
                      for f in frames]
        frames[0].save(
            WORK / f"{stem}.gif",
            save_all=True,
            append_images=frames[1:],
            duration=300,
            loop=0,
        )
        print(f"{WORK / (stem + '.gif')}: {len(frames)} frames, 24x21")


def _frames_from_file(path: pathlib.Path) -> list[Image.Image]:
    img = Image.open(path)
    if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1:
        frames = []
        for i in range(img.n_frames):
            img.seek(i)
            frames.append(img.convert("RGBA").copy())
        return frames
    return [img.convert("RGBA")]


def cmd_pack() -> None:
    for stem, files in SETS.items():
        src = None
        for ext in (".gif", ".png"):
            cand = WORK / f"{stem}{ext}"
            if cand.exists():
                src = cand
                break
        if src is None:
            print(f"skip {stem}: no {stem}.gif/.png in {WORK}")
            continue
        frames = _frames_from_file(src)
        if len(frames) < len(files):
            sys.exit(f"{src.name}: has {len(frames)} frames, "
                     f"expected {len(files)} ({', '.join(files)})")
        if len(frames) > len(files):
            print(f"note: {src.name}: using first {len(files)} frames, "
                  f"dropping {len(frames) - len(files)} extra")
        for frame, fname in zip(frames, files):
            image_to_spr(frame, SPR / fname)
    print("done — rebuild with: c64devk build -p games/dodge")


def cmd_render(name: str) -> None:
    path = SPR / f"{name}.spr"
    if not path.exists():
        sys.exit(f"no such sprite: {path}")
    data = path.read_bytes()
    for r in range(21):
        bits = ""
        for c in range(24):
            bits += "#" if data[r * 3 + c // 8] & (1 << (7 - c % 8)) else "."
        print(bits)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("unpack", "pack", "render"):
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "unpack":
        cmd_unpack()
    elif sys.argv[1] == "pack":
        cmd_pack()
    else:
        cmd_render(sys.argv[2])


if __name__ == "__main__":
    main()
