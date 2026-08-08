# dodge — Roadmap

## Animation — Alternate Sprite Frames

Sprite animation is implemented (2-frame ship, 4-frame enemy) but currently
reuses the same `.spr` files for all frames. These need to be drawn:

### Ship frames (2 frames per direction, 8 sprites total)

| File | Block | Description |
|------|-------|-------------|
| `assets/sprites/ship_r1.spr` | $85 | Ship right, frame 2 |
| `assets/sprites/ship_l1.spr` | $86 | Ship left, frame 2 |
| `assets/sprites/ship_u1.spr` | $87 | Ship up, frame 2 |
| `assets/sprites/ship_d1.spr` | $88 | Ship down, frame 2 |

Frame 0 uses the existing files: `ship_r.spr`, `ship_l.spr`, `ship_u.spr`, `ship_d.spr`.

### Enemy frames (4 frames total)

| File | Block | Description |
|------|-------|-------------|
| `assets/sprites/skull1.spr` | $89 | Skull frame 2 |
| `assets/sprites/skull2.spr` | $8A | Skull frame 3 |
| `assets/sprites/skull3.spr` | $8B | Skull frame 4 |

Frame 0 uses the existing `skull.spr`.

### How to create

1. Draw each frame in Spritemate (24x21, multicolor).
2. Export as 64-byte raw `.spr` to `games/dodge/assets/sprites/`.
3. `c64devk build` — the `!bin` directives in `game_logic.acme` pick
   up the new filenames automatically.
4. No code changes needed once the files exist.

### Memory layout

```
$2000-$23FF: all sprite data
  $80 ship_r0  $84 skull0   $88 ship_d1   $8C rock
  $81 ship_r1  $85 ship_r1  $89 skull1    $8D radar
  $82 ship_l0  $86 ship_l1  $8A skull2
  $83 ship_l1  $87 ship_u1  $8B skull3
```

