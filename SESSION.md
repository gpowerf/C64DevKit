# Session State — C64DevKit

## What we built

**C64DevKit** — spec-driven Commodore 64 development framework. YAML specs compile to 6502 assembly via ACME, producing runnable `.prg` files for VICE.

**Repo**: `https://github.com/gpowerf/C64DevKit` (main branch, 40+ commits)

## Framework commands

```
c64devk setup      Install all dependencies (ACME, VICE ROMs, PATH)
c64devk doctor     Check toolchain
c64devk new <name> Scaffold a new C64 project from templates
c64devk build      Parse YAML → generate .asm → compile via ACME → .prg + .sym + .lbl
c64devk run        Build + launch in VICE
c64devk test       Build + 6 static verification checks + optional live VICE testing
c64devk clean      Remove output/ directory
```

Entry point: `bin/c64devk` (Python). Package: `c64devk/` (cli, codegen, spec_parser, vice_bridge, test_runner, config, templates).

## Behavior DSL — 7 action types (all compile to 6502 assembly)

| Action | YAML example | What it does |
|--------|-------------|-------------|
| `update_sprite` | `update_sprite: player` | WASD/joystick → sprite position |
| `set_sprite_pos` | `set_sprite_pos: {sprite: player, x: 160, y: 120}` | Absolute sprite positioning with $D010 MSB |
| `inc_score` | `inc_score: 10` | 16-bit score variable (positive or negative, floor 0) |
| `play_sound` | `play_sound: {voice: 1, note: "c-4", waveform: triangle, duration: 10, adsr: pluck}` | SID note with ADSR + duration tracking |
| `check_collision` | `check_collision: {sprites: [player, enemy]}` | Hardware $D01E collision check with handler dispatch |
| `display_text` | `display_text: {text: "score:", row: 0, col: 0, color: 1}` | Write text to screen RAM, auto-copies ROM charset. **Must use lowercase** (!scr only converts a-z) |
| `display_number` | `display_number: {variable: score, row: 0, col: 6, digits: 5, color: 1}` | Live decimal display of 8/16-bit variable, updates each frame |

Behavior types: `on_frame` (every frame), `on_collision` (sprite overlap triggers handler with all actions).

## Macro library (ACME)

`macros/c64devk.acme` — master include, pulls in `vic.acme`, `cia.acme`, `sid.acme`, `memory.acme`.

Key macros: `+c64_wait_frame`, `+c64_sprite_enable_all`, `+c64_joy_check`, `+c64_play_note`, `+c64_adsr`, `+c64_gate_on`/`off`, `+c64_sid_tick`, `+c64_sid_volume`, `+c64_sound_tick_all`, `+c64_clear_screen`, `+c64_set_border`, `+c64_set_background`, `+c64_wait_raster`.

SID note frequency table: 72 notes (C-2 to B-7), PAL C64 clock. In macro `+c64_note_table_data`.

## Test runner

6 static verification checks per build: symbols present, PRG structure, sprite data address, sprite init presence, behavior handler presence, spec validation (memory bounds, sprite ranges, name references).

Live VICE testing: each test case launches a fresh VICE instance to avoid inter-test state corruption. VICE monitor uses "g" (go) to continue, "delete N" to remove breakpoints. Socket drain handled with proper prompt draining. Requires xvfb for headless operation.

## VICE launcher

Mode 1 (inject to RAM) + `-keybuf "sys<addr>\r"` — computes init address from BASIC SYS header, injects PRG, auto-types SYS command. ROM symlinks auto-created in `~/.c64devk/roms/`.

## Sprite Dodge game (`games/dodge/`)

Complete game with keyboard controls, enemy AI, scoring zones, lives, game over, restart.

**Controls**: WASD to move, SPACE to restart at game over.

**3 zones** (color RAM on solid block characters):
- Green (cols 0-12): score zone — +2/tick
- Black (cols 13-27): neutral — 0/tick
- Blue (cols 28-39): safe — -5 on entry, 0 while inside. Enemy can't follow past X=255.

**HUD**: `display_text` + `display_number` actions from behaviors.yaml — "score:" + 5-digit score + "lives:" + 1-digit lives, white on row 0.

**Game logic** (`routines/game_logic.acme`, ~600 lines): keyboard input (WASD, 9-bit X with $D010), enemy AI (chase, clamped 24-255), collision (opposite-side respawn, 150-frame invincibility, state machine PLAYING/DYING/GAME_OVER), sound (death saw), zone scoring, game over screen + restart.

**Sprites**: Player uses 4 directional spaceship sprites — `ship_r.spr` (right/$80), `ship_l.spr` (left/$81), `ship_u.spr` (up/$82), `ship_d.spr` (down/$83). Enemy uses `skull.spr` ($84). `player_dir` variable tracks direction (0-3), and the sprite pointer $07F8 is updated each frame.

**Sprites spec**: Extended `SpriteDef` with `data_files: dict` for multi-sprite support. The `codegen.py` `_emit_sprite_data` emits 4 blocks for sprites with `data_files`, and `_emit_sprite_memory_setup` calculates correct 64-byte-block pointers accounting for multi-block sprites.

**Screen**: VIC bank 0, ROM charset copied to $3800 by framework codegen. Solid block chars ($A0) fill screen for color RAM visibility. Dark gray border ($D020=11).

**Design doc**: `DESIGN.md` — single source of truth for all game mechanics.

## Known bugs & quirks

- **VICE kill crash** (fixed): `process.kill()` with `start_new_session=True` only killed parent process, leaving orphaned GTK/X11 children. Fixed with `os.killpg()` (SIGTERM → SIGKILL).
- **VICE remote monitor** (fixed): "c" command doesn't work — use "g" (go). `delete 1-99` is invalid — use individual `delete N`. Prompt `(C:$XXXX) ` lacks trailing newline — drains after each read.
- **Enemy safe zone entry** (fixed): Changed enemy max X clamp from 255 to 200.
- **Keyboard matrix**: WASD hard-coded in game_logic.acme. A=col1/row2 ($04), D=col2/row2 ($04), W=col1/row1 ($02), S=col1/row5 ($20). Same matrix in SKILL.md code patterns.
- **!scr lowercase**: ACME's `!scr` only converts a-z to PETSCII screen codes. Uppercase A-Z passes through as ASCII → graphics characters. Always use lowercase in YAML `display_text`.
- **Inline data**: Routines files must start with `jmp .start` to skip over variable declarations. `$00` byte executes as BRK → crash to BASIC READY.
- **Branch range**: ACME branches limited to ±127 bytes. Use `jmp` for longer jumps.
- **Zero-page addressing**: `sta ($zp),y` requires zp in $00-$FF. Use explicit $02-$03 instead of labels outside ZP.
- **VICE headless**: GTK3 VICE exits immediately without display. Live testing needs xvfb. `-autostartprgmode 1` + `-keybuf` works for GUI launch.
- **Sprite MSB**: $D010 bit can linger from uninitialized state. Always clear when setting enemy X < 256.
- **Codegen charset copy**: Uses `.ccloop:` label (was broken with `bne *-16`). Copy happens during `init:` with interrupts disabled, $01=$33.

## Architecture notes

**Two codegen paths** (selected by `_has_behaviors()`):
- **Behavior path**: behaviors.yaml has non-empty actions → `behaviors_update` subroutine + `sound_tick` + no-op `update_sprites`. Variables at $0C00 with conditional allocation (score, num_tmp, num_scr, sound_dur).
- **Hardcoded path**: empty behaviors → `jsr read_joystick` + `jsr game_logic` + `jsr update_sprites` (sprite 0 only).

**Variable layout** ($0C00+):
```
$0C00: frame_ready
$0C01: joystick_state
$0C02: joystick_prev
$0C03: score (2 bytes, if inc_score used)
       sound_dur_1/2/3 (if play_sound used)
       num_tmp (2) + num_scr (if display_number used)
```

## Files to know about

- `skills/SKILL.md` — 1,500+ line LLM reference (spec language, macro ref, C64 hardware, 6502 ISA, 8 code pattern recipes, spec writing tutorial)
- `docs/ARCHITECTURE.md` — Framework architecture, data flow, extension points
- `README.md` — Human-facing overview with quick start
- `DESIGN.md` — Game design doc for Sprite Dodge
- `bin/install-skill` — Links SKILL.md to `~/.config/opencode/skills/c64devk/`

## What's not done

- Live VICE testing (needs xvfb)
- Image-based regression testing
- ACME error → YAML spec mapping (line numbers from assembler errors to YAML keys)
- Background color actions (beyond border color)
- Music/sequence patterns for SID
- More game examples (pure-spec demo, sound jukebox)
- `c64devk init` (initialize existing directory as project)
- Sprite data generator (generate .spr from shape descriptions)

## How to continue

Run `c64devk run --project games/dodge` to play the game. Edit `spec/behaviors.yaml` to change HUD or add behaviors. Edit `routines/game_logic.acme` for custom game logic. Run `c64devk build && c64devk run` to iterate.

Framework code: `c64devk/cli.py` (commands), `c64devk/codegen.py` (assembly generation), `c64devk/spec_parser.py` (YAML parsing + note-to-frequency), `macros/` (ACME macro library).
