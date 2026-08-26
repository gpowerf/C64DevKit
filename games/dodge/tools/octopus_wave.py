#!/usr/bin/env python3
"""Fluid octopus tentacle animation for games/dodge.

Each hanging tentacle is extracted as per-row pixel runs from the
hand-drawn base art.  Per frame, every run is displaced horizontally
by a traveling sine wave whose amplitude ramps from the web anchor
(zero) to the tip and whose phase advances down the arm — the wave
visibly travels down each tentacle.  Runs are redrawn whole (preserving
width), and any diagonal gap between consecutive rows is bridged with
an 8-connected connector so tentacles never tear.

Side sweeps paddle horizontally in anti-phase.  Mantle/eyes/web are
fixed.  Frame 0 == base art exactly; the cycle wraps seamlessly.

Preview: renders a contact sheet of all frames plus a side-by-side
frame0/frame4 detail so the motion reads before anything is written.
"""
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]  # games/dodge
SPR = ROOT / "assets" / "sprites"
W, H = 24, 21
N_FRAMES = 8
WEB_ROW = 13

AMP_TIP = 2.0
ROW_LAG = math.pi / 5      # wave phase advance per row down the arm
TENT_LAG = math.pi / 2     # phase offset between tentacles


def load_base():
    data = (SPR / "skull.spr").read_bytes()
    assert len(data) == 64
    return [[(data[r * 3 + c // 8] >> (7 - c % 8)) & 1 for c in range(W)]
            for r in range(H)]


def components_below_web(grid):
    seen = [[False] * W for _ in range(H)]
    comps = []
    for r in range(WEB_ROW + 1, H):
        for c in range(W):
            if grid[r][c] and not seen[r][c]:
                stack = [(r, c)]
                seen[r][c] = True
                pix = []
                while stack:
                    y, x = stack.pop()
                    pix.append((y, x))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = y + dy, x + dx
                            if (WEB_ROW + 1 <= ny < H and 0 <= nx < W
                                    and grid[ny][nx] and not seen[ny][nx]):
                                seen[ny][nx] = True
                                stack.append((ny, nx))
                comps.append(pix)
    comps.sort(key=lambda p: p[0][1])
    return comps


def sweep_pixels(grid):
    left, right = [], []
    for r in range(10, WEB_ROW + 1):
        for c in range(W):
            if grid[r][c]:
                if c <= 5:
                    left.append((r, c))
                elif c >= 18:
                    right.append((r, c))
    return left, right


def rows_of(pix):
    d = {}
    for (r, c) in pix:
        d.setdefault(r, []).append(c)
    return {r: sorted(cols) for r, cols in d.items()}


def bridge(grid, ra, ca, rb, cb):
    """Draw an 8-connected connector between (ra,ca) and (rb,cb)."""
    if ra == rb:
        for c in range(min(ca, cb), max(ca, cb) + 1):
            grid[ra][c] = 1
        return
    # rows differ by 1: endpoints + intermediate for wide leans
    grid[ra][ca] = 1
    grid[rb][cb] = 1
    if abs(cb - ca) >= 2:
        mid = (ca + cb) // 2
        grid[rb][mid] = 1


def render_frames(base):
    tents = components_below_web(base)
    left, right = sweep_pixels(base)
    frames = []

    for f in range(N_FRAMES):
        grid = [row[:] for row in base]

        for t, pix in enumerate(tents):
            rmap = rows_of(pix)
            rows = sorted(rmap)
            r0, rN = rows[0], rows[-1]
            span = max(1, rN - r0)
            amp_tip = min(AMP_TIP, max(1.0, span / 2.5))

            # displace each row's run, preserving its width/shape
            placed = {}  # row -> list of new cols
            for r in rows:
                cols = rmap[r]
                depth = (r - r0) / span
                phase = (2 * math.pi * f / N_FRAMES
                         + t * TENT_LAG + (r - r0) * ROW_LAG)
                phase0 = t * TENT_LAG + (r - r0) * ROW_LAG
                dx = int(round(amp_tip * depth *
                               (math.sin(phase) - math.sin(phase0))))
                for c in cols:
                    grid[r][c] = 0
                placed[r] = [c + dx for c in cols]

            # place, then bridge gaps between consecutive rows
            for r in rows:
                for nc in placed[r]:
                    if 0 <= nc < W:
                        grid[r][nc] = 1

            for i in range(len(rows) - 1):
                ra, rb = rows[i], rows[i + 1]
                ca_set = placed[ra]
                cb_set = placed[rb]
                # 8-connected iff some pair is within 1 column
                connected = any(abs(a - b) <= 1
                                for a in ca_set for b in cb_set)
                if not connected and ca_set and cb_set:
                    ca = min(ca_set, key=lambda a: min(abs(a - b) for b in cb_set))
                    cb = min(cb_set, key=lambda b: min(abs(a - b) for a in ca_set))
                    bridge(grid, ra, ca, rb, cb)

        # side sweeps: paddle horizontally, anti-phase
        for side, pix in (("L", left), ("R", right)):
            phase = 2 * math.pi * f / N_FRAMES + (math.pi if side == "R" else 0.0)
            phase0 = math.pi if side == "R" else 0.0
            dx = int(round(1.5 * (math.sin(phase) - math.sin(phase0))))
            for (r, c) in pix:
                grid[r][c] = 0
            for (r, c) in pix:
                nc = c + dx
                if 0 <= nc < W:
                    grid[r][nc] = 1

        frames.append(grid)
    assert frames[0] == base
    return frames


def to_spr(grid):
    out = bytearray(64)
    for r in range(H):
        for c in range(W):
            if grid[r][c]:
                out[r * 3 + c // 8] |= 1 << (7 - c % 8)
    out[63] = 0x01
    return bytes(out)


def preview_sheet(frames, out_path):
    from PIL import Image
    scale = 14
    fw, fh = W * scale, H * scale
    sheet = Image.new("RGB", (fw * len(frames), fh), (16, 16, 16))
    for i, grid in enumerate(frames):
        img = Image.new("RGB", (W, H), (16, 16, 16))
        px = img.load()
        for r in range(H):
            for c in range(W):
                if grid[r][c]:
                    px[c, r] = (255, 255, 255)
        sheet.paste(img.resize((fw, fh), Image.NEAREST), (i * fw, 0))
    sheet.save(out_path)


def preview_diff(base, frame, out_path):
    """frame 0 vs one animated frame side by side, moved pixels red."""
    from PIL import Image
    scale = 14
    pair = Image.new("RGB", (W * scale * 2 + scale, H * scale), (16, 16, 16))
    for i, grid in enumerate((base, frame)):
        img = Image.new("RGB", (W, H), (16, 16, 16))
        px = img.load()
        for r in range(H):
            for c in range(W):
                v = grid[r][c]
                px[c, r] = (255, 255, 255) if v else (16, 16, 16)
        pair.paste(img.resize((W * scale, H * scale), Image.NEAREST),
                   (i * (W * scale + scale), 0))
    pair.save(out_path)


def main():
    base = load_base()
    frames = render_frames(base)
    preview_sheet(frames, ROOT / "sprite_edit" / "octopus_wave_preview.png")
    preview_diff(base, frames[4], ROOT / "sprite_edit" / "octopus_wave_extreme.png")
    print("previews written")

    if "--write" in sys.argv:
        for i in range(1, N_FRAMES):
            (SPR / f"skull{i}.spr").write_bytes(to_spr(frames[i]))
            print(f"wrote skull{i}.spr")
    else:
        print("dry run — pass --write to save skull1-7.spr")


if __name__ == "__main__":
    main()
