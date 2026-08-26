# Sprite Frame Specs — dodge

All sprites: **24×21 pixels, hi-res** (1-bit per pixel, 64 bytes per file).
Each `.spr` file = 63 bytes of pixel data + 1 pad byte.

## Reference Art (frame 0)

The existing sprites are your reference for each direction's silhouette.
Keep the outline and overall shape consistent across frames.

## Ship — Frame 1 (trail)

| File | Direction | Block | Pixel buffer |
|------|-----------|-------|--------------|
| `ship_r.spr` | Right | $80 | Clean hull, no trail (idle pose) |
| `ship_r1.spr` | Right | $85 | Exhaust trail |
| `ship_l.spr` | Left  | $81 | Clean hull, no trail (idle pose) |
| `ship_l1.spr` | Left  | $86 | Exhaust trail |
| `ship_u.spr` | Up    | $82 | Clean hull, no trail (idle pose) |
| `ship_u1.spr` | Up    | $87 | Exhaust trail |
| `ship_d.spr` | Down  | $83 | Clean hull, no trail (idle pose) |
| `ship_d1.spr` | Down  | $88 | Exhaust trail |

### Animation: movement-gated 2-frame cycle

- **Moving** (`state == PLAYING`, sprite position changed this frame):
  frames alternate every 2 frames (25 Hz flicker at 50 Hz) — the two
  trail positions blend on the phosphor, reading as translucent
  exhaust.
- **Stationary** (no position delta, or outside PLAYING): frozen on
  frame 0 — the trail is completely hidden.

Movement is detected by comparing sprite 0's VIC position against
`prev_x`/`prev_y` at the end of `keyboard_read` (`player_moving`).
The gate lives in `anim_update`.  l1/d1 are hand-drawn variants, not
mechanical mirrors of r1/u1.

## Enemy (Octopus) — Frames 1-7

The enemy art is an octopus (sprite files keep the historical `skull*`
prefix): mantle dome with two eyes, a web where the arms merge, two
side sweeps flaring out, and hanging tentacles below.

| File | Block | Pixel buffer |
|------|-------|--------------|
| `skull.spr` | $84 | Rest pose (hand-drawn) |
| `skull1.spr` | $89 | Wave frame 1 |
| `skull2.spr` | $8A | Wave frame 2 |
| `skull3.spr` | $8B | Wave frame 3 |
| `skull4.spr` | $8C | Wave frame 4 |
| `skull5.spr` | $8D | Wave frame 5 |
| `skull6.spr` | $8E | Wave frame 6 |
| `skull7.spr` | $8F | Wave frame 7 |

### Animation: 8-frame cycle (0–7), advances every 6 frames (48-frame loop at 50Hz)

### Design direction

Frame 0 is the hand-drawn rest pose.  Frames 1-7 are a traveling-wave
swim: each tentacle's per-row pixel runs are displaced horizontally by
a sine wave whose amplitude ramps from the web anchor (zero) to the tip
and whose phase advances down the arm, so the wave visibly travels
down the tentacles.  Adjacent rows lean by at most one pixel and any
diagonal gap is bridged, so the arms bend smoothly and never tear.
The side sweeps paddle horizontally in anti-phase; the mantle, eyes
and web stay fixed.  Frame 8 wraps seamlessly to the rest pose.

`skull_manual.gif` (in `sprite_edit/`) preserves the pre-ripple
hand-drawn frames; the generator is `tools/octopus_wave.py` —
regenerate by re-running it against `skull.spr`, then `pack`.  Tune
`AMP_TIP`, `ROW_LAG` and `TENT_LAG` for a different feel.

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
