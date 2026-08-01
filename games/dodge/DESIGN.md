# Sprite Dodge — Game Design

## Controls
- **WASD** — move player
- **SPACE** — restart after game over (at game over screen only)

## Visual zones
Three vertical stripes via color RAM on solid block characters:

| Zone | Columns | Color | Score | Notes |
|------|---------|-------|-------|-------|
| Score | 0-12 | Green (5) | +2/tick | Player X < 128, MSB=0 |
| Neutral | 13-27 | Black (0) | 0/tick | Player X 128-255, MSB=0 |
| DMZ | 28-39 | Animated | -5 on entry (floor 0) | Player X >= 256 (MSB=1) |

### DMZ (Safe Zone)
The safe zone displays animated digital noise in the style of Yars' Revenge:
- 3 random cells per frame are written with a pseudo-random PETSCII
  character ($80-$BF) and a cycling colour from an 8-entry palette
  (blue, light blue, cyan, purple, orange, light red, grey, white).
- An 8-bit Galois LFSR (polynomial $2D) drives the randomness.
- The cell pointer wraps after covering all 300 safe-zone cells
  (12 columns × 25 rows), creating a shifting static-noise effect.
- The player sprite renders on top of the noise via hardware priority.
- At boot, `dmz_init` fills the entire zone with LFSR-generated colours
  so the effect is visible immediately.

- Border: dark gray (11)
- Background: black (0)
- Score header: white (1) on row 0

## Scoring
- Green zone: +2 every 20 frames (~2.5/sec at 50fps)
- Black zone: 0
- Safe zone: -5 once when entering, then 0 while inside
- Score cannot go below 0
- No points on death

## Lives
- Start with 3
- Lose 1 on collision with enemy
- 0 lives → GAME OVER
- GAME OVER: "GAME OVER" + "PRESS SPACE TO PLAY" centered
- SPACE restarts: lives=3, score=0, player at (160,120), enemy at (100,80)

## Death
- On collision: enemy teleports opposite player, player flashes for 150 frames
- Sound: saw wave short blast (20 frames)
- Invincibility: 150 frames after respawn (3sec at 50fps)
- 10-frame invincibility on game restart

## Enemy AI
- Starts at (100, 80)
- Chases player at 1px every 2 frames (approximately)
- Clamped to visible area: X 24-200, Y 50-229

> Clamping X to 200 keeps the enemy sprite (24px wide, right edge at X+23) out of the blue safe zone, which starts at col 28 (pixel 224).
- Cannot follow player past X=200 (safe zone boundary)

## Player movement
- 9-bit X positioning with $D010 MSB
- Bounds: X 24-320, Y 50-229
- Direct VIC-II register writes from keyboard reader

### Directional sprites
The player has 4 directional spaceship sprites that change with movement:
| Direction | Key | Sprite File | Sprite Block |
|-----------|-----|-------------|--------------|
| Right | D | `ship_r.spr` | $80 ($2000) |
| Left | A | `ship_l.spr` | $81 ($2040) |
| Up | W | `ship_u.spr` | $82 ($2080) |
| Down | S | `ship_d.spr` | $83 ($20C0) |

A `player_dir` variable (0=right, 1=left, 2=up, 3=down) is set by
`keyboard_read` on each successful movement.  After keyboard input,
the sprite pointer at $07F8 is updated to `$80 + player_dir` so the
VIC-II displays the correct orientation.

## HUD display
Handled by the behavior DSL (`spec/behaviors.yaml`):
```yaml
behaviors:
  - name: hud
    type: on_frame
    actions:
      - display_text: {text: "score:", row: 0, col: 0, color: 1}
      - display_number: {variable: score, row: 0, col: 6, digits: 5, color: 1}
      - display_text: {text: "  lives:", row: 0, col: 11, color: 1}
      - display_number: {variable: lives, row: 0, col: 19, digits: 1, color: 1, size: 1}
```
The score and lives values update live every frame via `display_number`.
No custom assembly needed for the HUD — the framework emits the decimal
conversion and screen RAM writes.

## Memory layout
```
$0801-$0BFF: code + variables
$0C00: frame_ready, joystick_state, joystick_prev (framework)
$0C1C: init_sprites
$0C40: behaviors_update
$0D95+: game_logic routine (routines/game_logic.acme)
  includes dmz variables (seed, color, row, col),
  dmz_init, dmz_do, lfsr_tick, and dmz_colors table
$2000-$203F: player right  sprite  (block $80)
$2040-$207F: player left   sprite  (block $81)
$2080-$20BF: player up     sprite  (block $82)
$20C0-$20FF: player down   sprite  (block $83)
$2100-$213F: enemy skull   sprite  (block $84)
$3800-$3FFF: copied ROM charset (2KB)
```

## State machine
```
PLAYING (0) → keyboard, enemy AI, scoring, collision
                ↓ collision
DYING (1)    → player flashes, 150-frame timer
                ↓ lives > 0    ↓ lives = 0
              PLAYING (0)   GAME_OVER (2)
GAME_OVER (2) → show text, wait for SPACE → restart → PLAYING (0)
```

## Sound
- Death: voice 1 sawtooth, 5000Hz, instant ADSR, 20 frames
- Gate-off via per-frame snd_timer decrement

## Files
- `c64devk.yaml` — project config (memory, screen, sprites setup)
- `spec/sprites.yaml` — sprite definitions (player directional + enemy)
- `spec/game.yaml` — screen mode + colors (documentary)
- `spec/behaviors.yaml` — HUD display (display_text + display_number actions)
- `assets/sprites/ship_r.spr` — spaceship facing right
- `assets/sprites/ship_l.spr` — spaceship facing left
- `assets/sprites/ship_u.spr` — spaceship facing up
- `assets/sprites/ship_d.spr` — spaceship facing down
- `assets/sprites/skull.spr` — enemy skull
- `routines/game_logic.acme` — full game implementation (~630 lines)
