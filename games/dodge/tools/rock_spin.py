#!/usr/bin/env python3
"""Rock rotation frames for the asteroid spin (rock1.spr, rock2.spr).

Generates two 24x21 drafts from rock.spr by rotating the bitmap +20 and
-20 degrees at high resolution, then downsampling back onto the sprite
grid.  Drafts are editable: use tools/sprtool.py unpack/pack to hand-tune
them (the rotation cadence lives in game_logic.acme, not the art).

Frame layout (see routines/game_logic.acme):
    $3800 rock.spr   pointer $E0   frame 0 (original)
    $3880 rock1.spr  pointer $E2   frame 1 (+20 deg)
    $38C0 rock2.spr  pointer $E3   frame 2 (-20 deg)

Usage:
    python3 tools/rock_spin.py
"""
import pathlib

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "sprites" / "rock.spr"
OUT1 = ROOT / "assets" / "sprites" / "rock1.spr"
OUT2 = ROOT / "assets" / "sprites" / "rock2.spr"

SCALE = 8
W, H = 24, 21
ANGLES = (20, -20)
THRESHOLD = 110
PAD = 0x00          # match rock.spr's pad byte


def load_spr(path):
    data = path.read_bytes()
    if len(data) != 64:
        raise SystemExit(f"{path.name}: expected 64 bytes, got {len(data)}")
    img = Image.new("L", (W, H), 0)
    px = img.load()
    for r in range(H):
        for c in range(W):
            if data[r * 3 + c // 8] & (1 << (7 - c % 8)):
                px[c, r] = 255
    return img


def rotate_frame(rock, angle):
    big = rock.resize((W * SCALE, H * SCALE), Image.NEAREST).convert("L")
    rot = big.rotate(angle, resample=Image.BICUBIC, expand=False,
                     center=(big.width / 2, big.height / 2))
    out = rot.resize((W, H), Image.LANCZOS)
    px = out.load()
    for y in range(H):
        for x in range(W):
            px[x, y] = 255 if px[x, y] >= THRESHOLD else 0
    return out


def save_spr(img, path):
    out = bytearray(64)
    px = img.load()
    for r in range(H):
        for c in range(W):
            if px[c, r] > 127:
                out[r * 3 + c // 8] |= 1 << (7 - c % 8)
    out[63] = PAD
    path.write_bytes(bytes(out))
    print(f"wrote {path.name}")


def main():
    rock = load_spr(SRC)
    for path, angle in ((OUT1, ANGLES[0]), (OUT2, ANGLES[1])):
        save_spr(rotate_frame(rock, angle), path)


if __name__ == "__main__":
    main()
