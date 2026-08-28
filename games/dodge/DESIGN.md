# Sprite Dodge — Game Design

## Controls
- **WASD** — move player
- **FIRE** (joystick port 2) / **SPACE** (keyboard) — start game from the splash, restart (game over), trigger powerup charge
- **M** — cracked-menu level-select loader from the splash: digits 1-5
  jump, joystick up/down + fire/SPACE confirm, F1 backs out.  Starting at
  level n begins with that level's threshold score (256/512/1024/1536),
  its speed, and its enemy colour — no charge/life awards

## Visual zones
Three vertical stripes via color RAM on solid block characters:

| Zone | Columns | Color | Score | Notes |
|------|---------|-------|-------|-------|
| Score | 0-12 | Green (5) | +2/tick | Player X < 128 |
| Neutral | 13-27 | Black (0) | 0/tick | Player X 128–255 |
| DMZ | 28-39 | Animated | −5 on entry (floor 0) | Player X ≥ 224 |

### DMZ (Safe Zone)
Yars' Revenge style digital noise — full-zone colour-RAM refresh every 3 frames.
- 8-bit Galois LFSR (polynomial $2D) drives per-cell random colours.
- `dmz_init` seeds from VIC raster line, fills all 300 cells at boot.
- `dmz_do` walks all 288 cells (rows 1–24) every 3rd frame writing random
  colour values (0–15). Creates shifting TV-static interference.
- Player sprite renders on top via hardware priority.
- DMZ protects from ALL damage (enemy + asteroids) when player X ≥ 224.

- Border: dark gray (11)
- Background: black (0)
- HUD: white (1) on row 0

## Scoring
- Green zone: +2 every 20 frames (~2.5/sec at 50fps)
- Black zone: 0
- DMZ: −5 once when entering (X ≥ 224), then 0 while inside
- Score cannot go below 0
- No points on death

## Lives
- Start with 3
- Lose 1 on collision with enemy or asteroid
- DMZ (X ≥ 224) grants immunity to both
- 0 lives → GAME OVER
- GAME OVER: "GAME OVER" + "PRESS SPACE TO PLAY" centered
- SPACE restarts: lives=3, score=0, level=1, player at (160,120), enemy at (100,80) (loader-selected levels land via do_init on fresh starts)

## Levels
Level-ups fire every 256 points (when the score high byte crosses a new
value). Difficulty caps at level 5; the level counter keeps climbing and
the HUD shows the real number.

| Level | Score | Asteroids | Enemy Speed | Spawn Delay |
|-------|-------|-----------|-------------|-------------|
| 1 | 0–255 | 0 | 25 px/s | — |
| 2 | 256–511 | 1 | 25 px/s | 40 frames |
| 3 | 512–767 | 1 | 25 px/s | 30 frames |
| 4 | 768–1023 | 2 | 30 px/s | 25 frames |
| 5 | 1024–1279 | 3 | 35 px/s | 20 frames |
| 6+ | 1280+ | 3 | 35 px/s | 20 frames |

A short SID chirp (voice 3, triangle wave) plays on level‑up.
Enemy speed is fixed across all levels (removed the level‑3 ramp).
Difficulty tables only have 5 entries, so levels 6+ reuse the level‑5 row.
Reaching level 3+ awards one powerup charge (see Powerup below).

### Asteroids
- Up to 3 independent rock sprites (sprites 2/3/4, block $85).
- **Spawn from all 4 screen edges** at positions inside the visible
  playfield, on the true sprite-Y map (text window = sprite-Y 50..250):
  bottom (Y=228, row 22), top (spawn Y=50, 10 px behind the Y=60
  marker row 1 = 58-66, so the rock slides through the crosshair
  instead of popping in on it), left/right (X=24/224, right 6 px
  inside the DMZ threshold), with an inward velocity from a
  16‑angle table.  Side
  entries randomise within the visible band (Y 62‑226).
- Each angle is an LFSR‑picked (dx, dy) pair — diagonals, steep, shallow.
- Move in a straight line; despawn when exiting the opposite edge
  (the Y<10 sweep only catches upward rocks, so top entries at Y=0
  survive their first steps).
- Respawn after ~30 frames (~0.6 s at 50 fps).
- DMZ (player X ≥ 224) grants immunity — collision check returns early.
- Distance gate (18 px) prevents false‑positive hardware collisions.
- 16‑bit signed velocity, 8‑bit position with $D010 MSB per slot.
- Rock sprite data at $2140 (64 bytes), yellow/orange/light‑red colours.
- **Radar warning**: a crosshair marker sits at the exact arrival cell
  before the rock appears (top Y=60 crossing cell, bottom Y=228, sides
  X=24/224 — all
  inside the text window), fading to the next warning ~8 frames after a
  rock spawns, with a sonar ping on arrival.

## Death
- On collision: enemy teleports opposite player, player flashes 150 frames.
- Sound: voice 1 sawtooth, 5000 Hz, instant ADSR, 20 frames.
- Invincibility: 150 frames after respawn (~3 sec at 50 fps).
- 10‑frame invincibility on game restart.
- All invincibility flashes the player sprite (~6 Hz): flashing means immune.

## Powerup
- Reaching level 3 (or higher) awards one invincibility charge, capped at 1.
- Triggered manually with FIRE (joystick port 2) or SPACE (keyboard),
  edge‑detected so it cannot auto‑fire while held.
- Grants 2 seconds (100 frames) of invincibility via `hit_timer` — the
  collision systems need no special casing.
- If already invincible, the longer timer wins (`max(hit_timer, 100)`).
- `sfx_powerup` (ascending 4‑note arpeggio) plays on activation.
- A loader level‑start does not award charges (transition awards only).
- HUD shows a white "P" at row 0, col 28 while a charge is held.
- Unused charges persist through death and transitions; `restart` clears.

## Enemy AI
- Starts at (100, 80).
- Chases player at 1 px every 2 frames (speed_div = 2, fixed).
- Clamped to visible area: X 24–224, Y 50–229.
- Cannot follow player past X = 224 (DMZ boundary).

## Player movement
- 9‑bit X positioning with $D010 MSB.
- Bounds: X 24–320, Y 50–229.
- Direct VIC‑II register writes from keyboard reader.

### Directional sprites
The player has 4 directional spaceship sprites that change with movement:

| Direction | Key | Sprite File | Block |
|-----------|-----|-------------|-------|
| Right | D | `ship_r.spr` | $80 |
| Left | A | `ship_l.spr` | $81 |
| Up | W | `ship_u.spr` | $82 |
| Down | S | `ship_d.spr` | $83 |

A `player_dir` variable (0=right … 3=down) is set by `keyboard_read`
on each successful movement. The sprite pointer at $07F8 is updated to
`$80 + player_dir` so the VIC‑II displays the correct orientation.

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
      - display_text: {text: "lv:", row: 0, col: 22, color: 1}
      - display_number: {variable: level, row: 0, col: 25, digits: 2, color: 1, size: 1}
```

The powerup charge indicator ("P") at row 0, col 28 is written by
`game_logic.acme` (the DSL HUD only covers cols 0–26).

## Memory layout
```
$0801–$0BFF : code + variables
$0C00       : frame_ready, joystick_state, joystick_prev (framework)
$0C1C       : init_sprites
$0C40       : behaviors_update
$0D95+      : game_logic routine (~1650 lines)
$2000–$203F : player right  sprite  (block $80)
$2040–$207F : player left   sprite  (block $81)
$2080–$20BF : player up     sprite  (block $82)
$20C0–$20FF : player down   sprite  (block $83)
$2100–$213F : enemy skull   sprite  (block $84)
$2140–$217F : asteroid rock sprite  (block $85)
$3800–$3FFF : copied ROM charset (2 KB)
```

## State machine
```
SPLASH (3)   → "LAST STAR SYSTEM" + chrome logo + shimmer bars + DMZ
                 ↓ fire/SPACE = level 1 · 1‑5 = that level · F1 = loader menu
PLAYING (0)  → keyboard, enemy AI, scoring, collision
                 ↓ collision
DYING (1)     → player flashes, 150‑frame timer
                 ↓ lives > 0     ↓ lives = 0
               PLAYING (0)    GAME_OVER (2)
GAME_OVER (2) → show text, wait for SPACE → restart → PLAYING (0)
```

## Splash screen
- Black background with LFSR-placed decorative stars in upper/lower thirds.
- Cyan bars on rows 9 and 16 frame the title/subtitle area.
- Title "LAST STAR SYSTEM" in white at row 10, centered.
- Subtitle "press fire to play" (light grey, col 11) and loader hint
  "f1 or 1-5: level select" (row 16) frame the title.
- Cracked-loader menu (F1): white border, "START LEVEL 1-5" list with a
  ">" highlight; digits/jump, joystick up-down + fire/SPACE, F1 back.
- Frame loop only (no keyboard movement during splash).
- fire/SPACE or a digit transitions to PLAYING (at the chosen level);
  restart skips the splash.

## Sound
- Death: voice 1 sawtooth, 5000 Hz, instant ADSR, 20 frames.
- Level‑up: voice 3 triangle chirp, 8000 Hz, 15 frames.
- Gate‑off via per‑frame snd_timer decrement.

## Files
- `c64devk.yaml` — project config (memory, screen, sprites).
- `spec/sprites.yaml` — sprite definitions (player directional + enemy).
- `spec/game.yaml` — screen mode + colours (documentary).
- `spec/behaviors.yaml` — HUD display (display_text + display_number).
- `spec/tests.yaml` — 6 live‑VICE test cases.
- `assets/sprites/ship_r.spr` — spaceship right.
- `assets/sprites/ship_l.spr` — spaceship left.
- `assets/sprites/ship_u.spr` — spaceship up.
- `assets/sprites/ship_d.spr` — spaceship down.
- `assets/sprites/skull.spr` — enemy skull.
- `assets/sprites/rock.spr` — asteroid rock.
- `routines/game_logic.acme` — full game implementation (~1650 lines).
