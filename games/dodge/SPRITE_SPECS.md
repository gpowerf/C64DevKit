# Sprite Frame Specs — dodge

All sprites: **24×21 pixels, hi-res** (1-bit per pixel, 64 bytes per file).
Each `.spr` file = 63 bytes of pixel data + 1 unused byte.

## Reference Art (frame 0)

The existing sprites are your reference for each direction's silhouette.
Keep the outline and overall shape consistent across frames.

## Ship — Frame 1 (alternate animation)

| File | Direction | Block | Pixel buffer |
|------|-----------|-------|--------------|
| `ship_r1.spr` | Right | $85 | Copy `ship_r.spr`, tweak details |
| `ship_l1.spr` | Left  | $86 | Copy `ship_l.spr`, tweak details |
| `ship_u1.spr` | Up    | $87 | Copy `ship_u.spr`, tweak details |
| `ship_d1.spr` | Down  | $88 | Copy `ship_d.spr`, tweak details |

### Animation: 2-frame cycle, alternates every 8 frames (~7.5 fps at 50Hz)

### Design direction

frame 0 is the "base" pose. frame 1 should be the "action" pose.
Subtle differences are enough to read as animation:

- **Right/Left**: Shift the exhaust/engine glow 1 pixel narrower, or
  tilt the nose or wings by 1 pixel up/down.
- **Up/Down**: Shift the wingtip/fin details by 1 pixel, or
  make the engine nozzles flare open/closed.
- The silhouette MUST match frame 0 within ±1 pixel to avoid
  looking like the ship warps.
- 2-4 pixels changed from frame 0 is usually enough.

## Enemy (Skull) — Frames 1-3

| File | Block | Pixel buffer |
|------|-------|--------------|
| `skull1.spr` | $89 | Copy `skull.spr`, tweak details |
| `skull2.spr` | $8A | Copy `skull.spr`, tweak details |
| `skull3.spr` | $8B | Copy `skull.spr`, tweak details |

### Animation: 4-frame cycle, advances every 6 frames (~8.3 fps at 50Hz)

### Design direction

frame 0 is the "closed jaw" pose. Alternate frames should open the jaw:

- **frame 1**: Jaw drops 1-2 pixels, eyes widen
- **frame 2**: Jaw drops 2-3 pixels, eyes at widest
- **frame 3**: Jaw at max, eyes slightly narrowed (peak of open)
- Cycle reads as: closed → opening → open → wide-open → closed

Keep the cranium (top dome) and cheekbones identical across all frames.
Only the jaw and eyes change.

## Export

Save each as a 64-byte raw `.spr` file in `games/dodge/assets/sprites/`.
In Spritemate, use "Export → Raw binary (.spr)" with the C64 sprite
template (24×21, hi-res).

## Verification

After placing the files, run:
```bash
c64devk build -p games/dodge
c64devk run -p games/dodge
```

The animation uses the new frames automatically — no code changes needed.
