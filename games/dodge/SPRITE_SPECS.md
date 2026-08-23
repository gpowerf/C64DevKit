# Sprite Frame Specs — dodge

All sprites: **24×21 pixels, hi-res** (1-bit per pixel, 64 bytes per file).
Each `.spr` file = 63 bytes of pixel data + 1 pad byte.

## Reference Art (frame 0)

The existing sprites are your reference for each direction's silhouette.
Keep the outline and overall shape consistent across frames.

## Ship — Frame 1 (alternate animation)

| File | Direction | Block | Pixel buffer |
|------|-----------|-------|--------------|
| `ship_r1.spr` | Right | $85 | Exhaust streak shifts, claw pinches |
| `ship_l1.spr` | Left  | $86 | Independently drawn left variant |
| `ship_u1.spr` | Up    | $87 | V-flare plume cuts out, glint slides |
| `ship_d1.spr` | Down  | $88 | Independently drawn down variant |

### Animation: 2-frame cycle, alternates every 2 frames (25 Hz — trails read as translucent)

### Design direction

frame 0 is the "base" pose. frame 1 is the "surge" pose — the engine
fires for one cycle:

- **Right/Left**: The diagonal exhaust streak along the hull shifts/
  blinks one cycle step (pixels move along the streak), and the nose
  claw prongs pinch 1px toward the body.
- **Up/Down**: The V-shaped engine flare under the hull cuts out (off
  pulse), and the canopy glint slides one row.
- The silhouette matches frame 0 within ±1 pixel.
- l1/d1 are hand-drawn variants matching the base art's left/down
  orientation — not mechanical mirrors of r1/u1.

## Enemy (Octopus) — Frames 1-6

The enemy art is an octopus (sprite files keep the historical `skull*`
prefix): mantle dome with two eyes, a web where the arms merge, two
side sweeps flaring out, and hanging tentacle tips below.

| File | Block | Pixel buffer |
|------|-------|--------------|
| `skull.spr` | $84 | Rest pose |
| `skull1.spr` | $89 | Tentacles spreading |
| `skull2.spr` | $8A | Tentacles spreading |
| `skull3.spr` | $8B | Web open, tips out |
| `skull4.spr` | $8C | Wide |
| `skull5.spr` | $8D | Wide |
| `skull6.spr` | $8E | Widest |

### Animation: 7-frame cycle (0–6), advances every 6 frames (42-frame loop at 50Hz)

### Design direction

Frame 0 is the resting pose.  Frames 1-6 are hand-drawn: the tentacles
spread progressively — the web opens wider and the tips shift outward.
Frame 6 is the widest; the cycle wraps straight back to the rest pose
of frame 0.  Mantle and eyes stay fixed throughout.

Block $8F ($23C0) is free, reserved for future animation frames.

## Editing workflow (LibreSprite round trip)

`tools/sprtool.py` converts between the `.spr` files and animated GIFs
that LibreSprite (or any pixel editor) can open.  Each GIF is one sprite
set — frame 0 first, then the animation frames — at **native C64
resolution (24×21)**: one image pixel per sprite pixel, so every brush
stroke lands on a real pixel.  White = solid pixel, black = transparent;
the VIC-II colour comes from `spec/sprites.yaml`, not the art.

```bash
python3 tools/sprtool.py unpack    # .spr -> sprite_edit/*.gif
# edit sprite_edit/skull.gif in LibreSprite, save back over the GIF
python3 tools/sprtool.py pack      # GIF -> .spr (also accepts zoomed PNG strips)
c64devk build -p games/dodge
```

LibreSprite tips:
- The canvas opens at 24×21 — **zoom in immediately** (`+` key,
  Ctrl+wheel, or the magnifier in the bottom bar; ~1600% is comfortable).
  Zoom is only a view setting; the sprite stays 24×21.
- Frames of the GIF land in the timeline; switch with `,` / `.` or by
  clicking the timeline.
- Turn on **Onion Skin** (timeline panel) to see frame 0 as a ghost
  while editing frame 1 — that is how you keep the silhouette within
  ±1 pixel.
- Pencil `B`, brush size 1, draw white; black (or eraser `E`) is
  transparent.
- Do not resize the canvas — it must stay 24×21.
- Save as GIF over the same file.  A zoomed PNG sprite-sheet export
  also works — `pack` auto-detects the scale — but GIFs keep the
  frames stacked for you.
- `python3 tools/sprtool.py render skull1` prints an ASCII preview of
  any `.spr` straight from the command line.

The radar crosshair is inline data in `routines/game_logic.acme`
(`* = $2440`), not a `.spr` file — edit it there.

## Export

All frames are 64-byte raw `.spr` files in `games/dodge/assets/sprites/`
(63 bytes of pixel data + pad byte, $00 for rock.spr and $01 elsewhere —
the pad is unused by VIC-II). To tweak, use the LibreSprite round trip
above, or edit the base `.spr` files directly in Spritemate
("Export → Raw binary (.spr)", 24×21, hi-res) — the frame-1 files are
standalone copies.

## Wiring

The animation frames are emitted by `routines/game_logic.acme`
(`!bin` directives at blocks $85-$8E, after the DSL-managed base
frames at $80-$84). Pointer math in `gstart` selects the block:
`$07F8 = $80 + player_dir + ship_frame*5` and
`$07F9 = $84 + enemy_frame` (+4 skip when > 0, frames 0–6).

## Verification

After changing any frame file, run:
```bash
c64devk build -p games/dodge
c64devk run -p games/dodge
```

Ship: hold a direction — the sprite flickers every 8 frames.
Enemy: watch the skull — jaw cycles every 6 frames.
