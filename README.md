# C64DevKit

Spec-driven development framework for the Commodore 64. Write YAML specs describing your game/program — sprites, screen layout, input, behaviors — and `c64devk` compiles them to 6502 assembly via ACME, producing a ready-to-run `.prg` file for VICE.

```
$ c64devk new mygame
$ cd mygame
$ c64devk build    # validates spec → compiles → produces .prg + .sym + .lbl
$ c64devk run      # launches in VICE
$ c64devk test     # runs static verification
$ c64devk clean    # removes output/
```

## Requirements

| Tool | Status | Install |
|------|--------|---------|
| Python 3.10+ | `python3` | Built-in on most distros |
| ACME 0.96+ | 6502 cross-assembler | `sudo apt install acme` or compile from [GitHub](https://github.com/jan0sch/acme-crossassembler) |
| VICE | C64 emulator | `sudo apt install vice` (provides `x64sc`) |
| PyYAML | YAML parser | `pip install pyyaml` (may already be installed) |

Run `c64devk doctor` to check that all dependencies are found.

## Quick start

```bash
# 1. Verify toolchain
bin/c64devk doctor

# 2. Create a project
bin/c64devk new mygame

# 3. Edit the spec (sprites, behaviors, screen config)
# 4. Build and run
bin/c64devk run --project mygame
```

## Spec-driven workflow

The main loop: edit YAML → build → run. No assembly required.

```bash
vim spec/sprites.yaml      # add a sprite, change color or position
vim spec/behaviors.yaml    # add movement, collision, sound
c64devk build              # regenerate + compile → .prg in ~1s
c64devk run                # test in VICE
```

**Example: adding collision detection in 30 seconds**

Edit `spec/behaviors.yaml`:
```yaml
behaviors:
  - name: move_player
    type: on_frame
    actions:
      - update_sprite: player

  - name: on_hit
    type: on_collision
    sprites: [player, enemy]
    actions:
      - inc_score: 10
      - play_sound: {voice: 1, note: "C-4", waveform: triangle, duration: 10}
```

`c64devk build && c64devk run` — now colliding sprites play a sound and add score.

**When you need custom logic**, write assembly in `routines/game_logic.acme`.
This file is called every frame and never overwritten by the build.
See `skills/SKILL.md` for the full spec language reference and 8 C64 code patterns.

## Project structure

```
mygame/
├── c64devk.yaml           # Project config (memory map, screen mode, output)
├── spec/                  # YAML spec files (source of truth)
│   ├── game.yaml          # Screen config: mode, colors, charset
│   ├── sprites.yaml       # Sprite definitions: position, color, data
│   └── behaviors.yaml     # Behaviors and game logic
├── routines/              # Custom 6502 assembly (never overwritten)
│   └── game_logic.acme    # Called every frame, write your code here
├── assets/                # Binary assets
│   └── sprites/           # .spr files (raw 64-byte sprite data)
└── output/                # Generated files (safe to gitignore)
    ├── src/               # Generated .acme assembly
    └── build/             # Compiled .prg file
```

## Spec language overview

### c64devk.yaml — project config

```yaml
project:
  name: "MyGame"
  output: "mygame.prg"

memory:
  code_start: 0x0801       # standard BASIC start
  code_end: 0xCFFF         # keep below $D000 (I/O area)
  sprite_data: 0x2000      # must be 64-byte aligned

screen:
  mode: hires              # hires | multicolor | text
  background_color: 0      # 0-15
  border_color: 0          # 0-15

basic: true                # include BASIC SYS header
```

### spec/sprites.yaml — sprite definitions

```yaml
sprites:
  - name: player
    index: 0               # 0-7 (VIC-II sprite number)
    x: 160                 # X position (0-511)
    y: 120                 # Y position (0-255)
    color: 7               # Color index (0-15)
    multicolor: false
    enabled: true
    data_file: "assets/sprites/player.spr"
```

### spec/behaviors.yaml — game behaviors

```yaml
behaviors:
  - name: move_player
    type: on_frame
    actions:
      - update_sprite: player

  - name: reset_on_hit
    type: on_collision
    sprites: [player, enemy]
    actions:
      - set_sprite_pos:
          sprite: player
          x: 160
          y: 120
      - inc_score: 10
```

**Action types**: `read_joystick`, `update_sprite`, `set_sprite_pos`, `inc_score`, `play_sound`, `check_collision`

**Behavior types**: `on_frame` (runs every frame), `on_collision` (fires when two sprites overlap)

## How it works

```
c64devk.yaml ─┬─┐
sprites.yaml ─┤ │
behaviors.yaml┘ │
                ▼
        ┌──────────────┐
        │  Spec Parser  │  Python: YAML → ProjectSpec dataclass
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │   CodeGen     │  Python: ProjectSpec → ACME assembly string
        └──────┬───────┘
               │
               ▼         macros/c64devk.acme ─> macros/*.acme (copied)
        ┌──────────────┐
        │     ACME      │  6502 assembler: .acme → .prg (CBM format)
        └──────┬───────┘
               ▼
           main.prg  ─────> x64sc (VICE emulator)
```

## Macro library

The framework ships a macro library that abstracts C64 hardware registers:

| Macro | Description |
|-------|-------------|
| `+c64_wait_frame` | Wait for next raster frame IRQ |
| `+c64_set_border N` | Set border color (0-15) |
| `+c64_set_background N` | Set background color (0-15) |
| `+c64_clear_screen $0400, 32` | Clear screen RAM with a fill character |
| `+c64_wait_raster N` | Wait for raster line N |
| `+c64_sprite_enable_all` | Enable all 8 sprites |
| `+c64_sprite_disable_all` | Disable all sprites |
| `+c64_sprite_set I, X, Y` | Set sprite I position to (X, Y) |
| `+c64_sprite_set_color I, C` | Set sprite I color to C |
| `+c64_joy_check JOY_UP, .skip` | Branch to `.skip` if UP not pressed |
| `+c64_sprite_placeholder N` | Emit 64 bytes of placeholder sprite data |

Joystick constants: `JOY_UP`, `JOY_DOWN`, `JOY_LEFT`, `JOY_RIGHT`, `JOY_FIRE`

## C64 colors

| # | Color | # | Color | # | Color | # | Color |
|---|-------|---|-------|---|-------|---|-------|
| 0 | Black | 4 | Purple | 8 | Orange | 12 | Mid Gray |
| 1 | White | 5 | Green | 9 | Brown | 13 | Light Green |
| 2 | Red | 6 | Blue | 10 | Light Red | 14 | Light Blue |
| 3 | Cyan | 7 | Yellow | 11 | Dark Gray | 15 | Light Gray |

## Custom assembly

Write 6502 code in `routines/game_logic.acme`. This is called once per frame (50/60 Hz) after joystick input is read but before sprites are updated. Additional `.acme` files in `routines/` are included at the end of the generated code.

The generated code provides these labels you can use:
- `frame_ready` — byte, set to 1 on each raster IRQ
- `joystick_state` — byte, joystick port 2 state (active high)
- `joystick_prev` — byte, previous frame's joystick state

## Key constraints

- Sprite data must be at an address divisible by 64
- VIC-II sees memory in 16KB banks; ensure screen RAM and sprite data are in the same bank or adjacent banks
- Keep code below $D000 (the I/O region) unless using bank switching
- The stack is at $01FF growing downward (384 bytes available)
- Generation uses raster IRQ at line 0 for frame timing

## Testing

```bash
c64devk test           # Build + run static verification
```

`c64devk test` runs 6 static verification checks after building:

| Test | Checks |
|------|--------|
| `symbols_present` | All required labels exist in the binary |
| `prg_structure` | Correct CBM load address and file size |
| `sprite_data_at_correct_address` | Sprite data at the configured memory location |
| `sprite_init_present` | `init_sprites` routine exists |
| `behavior_handlers_present` | Collision handlers exist for each `on_collision` behavior |
| `spec_validation` | Sprite indices unique, positions in range, memory aligned |

Additional tests go in `spec/tests.yaml`. Live VICE testing is supported when a display (or xvfb) is available, falling back to static mode automatically.

### Agent verification (eyes and ears)

The framework ships two tools for agent-driven verification of running
code.  **Use a vision-capable model** so `shot` output can actually be
seen (screenshots are useless to a text-only model), and use `audio`
for anything you cannot see:

```bash
c64devk shot            # eyes: PNG of the game window (vision model required)
c64devk audio --scene still   # ears: record + fingerprint the game's audio
c64devk audio --scene moving  # compare a second scenario
```

`c64devk audio` drives a scripted scenario via the VICE monitor (a
monitor-driven kill, still vs moving), records the real PCM output
through ALSA, and prints a per-window spectrogram fingerprint
(RMS / peak / centroid / tonality) so two sound states can be compared
objectively — distinguishing, say, a rising alarm sweep from an
explosion thud.  Requires `x64sc` with a working ALSA output, `arecord`,
and (for analysis) numpy.  Without a vision model, pair with a human
or use the numeric fingerprints alone.

## Architecture

See `docs/ARCHITECTURE.md` for design decisions, data flow, and extension points.

## Roadmap

- [x] Project scaffold & toolchain (`doctor`, `new`, `build`, `run`, `clean`, `setup`)
- [x] VIC-II sprite setup and joystick/keyboard input
- [x] ACME macro library (VIC, CIA, SID register constants + utility macros)
- [x] VICE remote monitor bridge (`ViceMonitor` class)
- [x] Test runner — static verification + spec validation (6 checks)
- [ ] Live VICE testing — headless runtime test execution (requires xvfb)
- [x] SID sound — note-to-frequency table, ADSR envelopes, gate, volume, duration tracking
- [x] Behavior DSL compiler — 7 action types (update_sprite, set_sprite_pos, inc_score, play_sound, check_collision, display_text, read_joystick)
- [x] Collision detection (hardware sprite-sprite with cooldown + handler dispatch)
- [x] Multi-sprite support (via behavior DSL, each sprite gets individual pointer)
- [x] Character/text display — `display_text` action writes to screen RAM with color
- [x] Spec validation — memory bounds, sprite indices, position ranges, name references
- [x] VICE label file output + fixed variable addresses
- [x] OpenCode skill packaged (`bin/install-skill`)
- [x] C64 code pattern recipes in SKILL.md (8 patterns)
- [x] Sprite Dodge example game (760 lines, state machine, zones, scoring)
- [ ] Image-based regression testing (VICE screenshot diffing)

## License

MIT
