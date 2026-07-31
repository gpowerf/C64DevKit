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
| Safe | 28-39 | Blue (6) | -5 on entry (floor 0) | Player X >= 256 (MSB=1) |

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
- Clamped to visible area: X 24-255, Y 50-229
- Cannot follow player past X=255 (safe zone escape)

## Player movement
- 9-bit X positioning with $D010 MSB
- Bounds: X 24-320, Y 50-229
- Direct VIC-II register writes from keyboard reader

## Screen
- VIC bank 0: screen at $0400, charset at $3800
- ROM charset ($D000) copied to $3800 at startup (char ROM visible via $01=$33)
- Solid block characters ($A0) fill screen for color RAM visibility
- 40×25 character display

## Memory layout
```
$0801-$0BFF: code + variables
$0C00: frame_ready, joystick_state, joystick_prev (framework)
$0C06+: game_logic routine (routines/game_logic.acme)
$2000: sprite data (64 bytes each)
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
- `spec/sprites.yaml` — sprite definitions (player + enemy)
- `spec/game.yaml` — screen mode + colors (documentary)
- `spec/behaviors.yaml` — empty (all logic hand-coded)
- `routines/game_logic.acme` — full game implementation (~760 lines)
