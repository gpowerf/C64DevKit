---
name: c64devk
description: Spec-driven Commodore 64 development framework. Use when the user asks to create a C64 game, C64 program, C64 demo, or any Commodore 64 software. Also use for C64 debugging, 6502 assembly, VIC-II sprites, SID sound, or any task involving the c64devk command (new, build, run, test, clean, doctor). Projects are defined in YAML specs and compiled to 6502 assembly.
---

# C64DevKit Skill

C64DevKit is a spec-driven development framework for the Commodore 64. Users define their program in YAML specs. The framework generates 6502 assembly via ACME and produces a runnable `.prg` file for VICE.

## Installation

```bash
# Required tools
sudo apt install vice          # C64 emulator (x64sc)
sudo apt install acme          # 6502 cross-assembler (or compile from source)

# Framework
git clone <repo> C64DevKit
cd C64DevKit
bin/c64devk doctor              # verify toolchain
```

If `acme` is not available via apt, compile from source:
```bash
git clone --depth 1 --branch 0.96.5 https://github.com/jan0sch/acme-crossassembler.git
cd acme-crossassembler/src && make -j$(nproc)
cp acme ~/.local/bin/
```

## Commands

```
c64devk doctor                Check all tool dependencies and report versions
c64devk new <name> [-d DIR]   Scaffold a new project
c64devk build [-p DIR]        Parse specs, generate .asm, assemble, produce .prg
c64devk run [-p DIR] [--headless]  Build then launch in VICE
c64devk test [-p DIR]         Run test assertions (under development)
c64devk --version             Print version
```

## Project Structure

```
mygame/
├── c64devk.yaml              Project-level configuration
├── spec/                     YAML spec files (the source of truth)
│   ├── game.yaml             Screen mode, colors, charset
│   ├── sprites.yaml          Sprite definitions (position, color, data)
│   └── behaviors.yaml        High-level behavior definitions
├── routines/                 Custom 6502 assembly (NEVER overwritten by build)
│   └── game_logic.acme       Called once per frame, write game logic here
├── assets/                   Binary assets
│   └── sprites/              .spr files (raw 64-byte sprite data)
└── output/                   Generated files (safe to gitignore)
    ├── src/                  Generated .acme assembly files
    │   ├── main.acme         Main generated assembly
    │   ├── macros/           Copied macro library
    │   └── routines/         Copied user routines
    └── build/                Compiled output
        └── <name>.prg        Ready-to-run C64 program
```

---

## Complete Spec Language Reference

### `c64devk.yaml` — Project Configuration

```yaml
project:
  name: "MyGame"             # Required: project identifier
  output: "mygame.prg"       # Output .prg filename

memory:
  code_start: 0x0801         # Where machine code starts ($0801 = BASIC area)
  code_end: 0xCFFF           # End of code area (must be < $D000 for I/O to work)
  sprite_data: 0x2000        # Sprite data address (MUST be 64-byte aligned)
  charset: 0x3800            # Character set data address
  screen_ram: 0x0400         # Screen RAM address

screen:
  mode: hires                # "hires" (320x200) | "multicolor" (160x200) | "text" (40x25)
  charset: 0x3800            # Charset data address (defaults to memory.charset)
  screen_ram: 0x0400         # Screen RAM address (defaults to memory.screen_ram)
  background_color: 0        # Background color index (0-15)
  border_color: 0            # Border color index (0-15)

basic: true                  # Include BASIC SYS header (set false for cartridge targets)

# Optional: declare named routines for inclusion
routines:
  - enemies
  - collision
```

**Value formats**: All numeric values accept decimal (10), hex (0x10, $10), or binary (%00010000).

**Memory alignment rules**:
- `sprite_data` MUST be divisible by 64 (e.g., $2000, $2040, $2080, ...)
- `charset` must be on a 2KB boundary within its VIC bank ($0000, $0800, $1000, $1800, $2000, $2800, $3000, $3800)
- `screen_ram` must be on a 1KB boundary within its VIC bank ($0000, $0400, $0800, $0C00, $1000, ...)

**VIC bank restrictions**: The VIC-II chip sees memory in 16KB banks. Screen RAM and charset must be in the same VIC bank. If using sprites, the sprite pointers are in the last 8 bytes of screen RAM ($03F8-$03FF relative to the VIC bank start). The sprite data itself is pointed to by a byte value (sprite_data_address / 64).

### `spec/game.yaml` — Screen Configuration

```yaml
mode: hires                     # REQUIRED: "hires", "multicolor", or "text"
charset: 0x3800                 # Character set location in memory
screen_ram: 0x0400              # Screen RAM location
background_color: 0             # 0-15 (black to light gray)
border_color: 0                 # 0-15
```

All values in `game.yaml` are overridden by `c64devk.yaml` if present.

### `spec/sprites.yaml` — Sprite Definitions

```yaml
sprites:
  - name: player                # Human-readable identifier
    index: 0                    # VIC-II sprite number (0-7)
    x: 160                      # Initial X position (0-511; MSB via $D010)
    y: 120                      # Initial Y position (0-255)
    color: 7                    # Sprite color (0-15)
    multicolor: false           # Enable multicolor sprite mode
    multicolor_1: 0             # Shared multicolor 1 (if multicolor: true)
    multicolor_2: 0             # Shared multicolor 2 (if multicolor: true)
    enabled: true               # Sprite visibility (controls $D015 bit)
    priority: false             # Foreground (false) or background (true) priority
    expand_x: false             # Double sprite width
    expand_y: false             # Double sprite height
    data_file: "assets/sprites/player.spr"  # Path to 64-byte sprite data
```

**Sprite data format**: 64 bytes per sprite (63 bytes of pixel data + 1 padding byte). Each bit corresponds to a pixel: 1 = sprite color, 0 = transparent. Bytes are stored top-to-bottom, left-to-right within each byte (MSB = leftmost pixel).

For multicolor sprites, each pixel is 2 bits (pairs of bits), giving effectively 12x21 resolution. Pixel values: 00 = transparent, 01 = multicolor 1, 10 = sprite color, 11 = multicolor 2.

**X position > 255**: The high bit of X position is stored in register $D010 (one bit per sprite). The codegen handles this automatically.

### `spec/behaviors.yaml` — Behavior Definitions

Behaviors are compiled directly to 6502 assembly. Define what happens each frame and how to respond to collisions.

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
      - set_sprite_pos: {sprite: player, x: 160, y: 120}
      - inc_score: 10
```

**Behavior types:**
| Type | Trigger | Purpose |
|------|---------|---------|
| `on_frame` | Every frame (50/60Hz) | Movement, input reading, continuous logic |
| `on_collision` | Hardware sprite-sprite collision | Score, lives, reset position, effects |
| `on_input` | Joystick/keyboard event | (planned) Menu navigation, discrete actions |

When multiple `on_collision` behaviors reference the same sprite pair, all their actions run together on collision. Collision bits are auto-cleared each frame.

#### Supported actions

All actions are compiled to optimized 6502 assembly:

**`read_joystick`** — read joystick state
```yaml
- read_joystick: port2     # "port1" or "port2"
```
Sets `joystick_state` byte. Done automatically before behaviors_update if any behavior needs it.

**`update_sprite`** — map joystick to sprite movement
```yaml
- update_sprite: player    # sprite name (references sprites.yaml)
```
Generates UP/DOWN/LEFT/RIGHT checks and increments/decrements the sprite's VIC-II position registers directly.

**`set_sprite_pos`** — absolute sprite positioning
```yaml
- set_sprite_pos:
    sprite: player
    x: 160
    y: 120
```
Sets the sprite to an absolute position. Handles MSB of X ($D010) automatically. Used in collision handlers to reset position.

**`inc_score`** — modify 16-bit score
```yaml
- inc_score: 10            # positive or negative
```
Adds to the 16-bit `score` variable (allocated automatically). Negative values subtract. Wraps on overflow.

**`play_sound`** — trigger a SID note
```yaml
- play_sound:
    voice: 1               # 1-3
    frequency: 1000        # SID frequency value (16-bit)
    waveform: triangle     # triangle | saw | pulse | noise
```
Sets frequency, waveform, and gate on the specified SID voice. Volume is set to maximum ($0F). No duration tracking yet — the note stays on until overwritten.

**`check_collision`** — inline collision check
```yaml
- check_collision:
    sprites: [player, enemy]
    handler: player_enemy_hit   # label for handler subroutine
```
Checks for collision between two sprites. If detected, acknowledges the collision and branches to the named handler. (For simple inline dispatch; prefer on_collision behavior type.)

### Color Reference

```
0:  COLOR_BLACK      (black)
1:  COLOR_WHITE      (white)
2:  COLOR_RED        (red)
3:  COLOR_CYAN       (cyan)
4:  COLOR_PURPLE     (purple)
5:  COLOR_GREEN      (green)
6:  COLOR_BLUE       (blue)
7:  COLOR_YELLOW     (yellow)
8:  COLOR_ORANGE     (orange)
9:  COLOR_BROWN      (brown)
10: COLOR_LIGHT_RED   (light red)
11: COLOR_DARK_GRAY   (dark gray)
12: COLOR_MID_GRAY    (mid gray)
13: COLOR_LIGHT_GREEN (light green)
14: COLOR_LIGHT_BLUE  (light blue)
15: COLOR_LIGHT_GRAY  (light gray)
```

---

## Macro Library Reference (ACME)

All macros are available when `!source "macros/c64devk.acme"` is included in the generated assembly.

### Frame Synchronization

```
+c64_wait_frame
```
Waits for a raster IRQ. Blocks until `frame_ready` is set to 1, then clears it. Must be called from `main_loop` (the generated code does this automatically).

### Screen

```
+c64_clear_screen $0400, 32
```
Fills 1000 bytes starting at given address with the given value. For use:
- `+c64_clear_screen $0400, 32` — fill screen with space character
- `+c64_clear_screen $d800, 0` — clear color RAM to black

```
+c64_set_border 0
+c64_set_background 0
```
Sets border/background color. Accepts values 0-15.

```
+c64_set_multicolor 1, 2
```
Sets multicolor background colors 1 and 2 (registers $D022, $D023). Only effective when multicolor mode is active.

```
+c64_wait_raster 120
```
Busy-waits until the raster reaches the specified line. Used for raster effects or to avoid tearing.

### Sprites

```
+c64_sprite_enable_all
+c64_sprite_disable_all
```
Enable/disable all 8 sprites by writing to $D015.

```
+c64_sprite_set 0, 160, 120
```
Set sprite position. Parameters: sprite index (0-7), X position (0-255), Y position (0-255). Note: this only sets the low byte of X; the MSB of X ($D010) must be handled separately.

```
+c64_sprite_set_color 0, 7
```
Set sprite color. Parameters: sprite index, color (0-15).

```
+c64_sprite_set_pointer 0, $2000
```
Set sprite data pointer in screen RAM. Parameters: sprite index, absolute memory address of sprite data (must be 64-byte aligned). Computes `addr / 64` and stores it at `screen_start + $03F8 + index`.

```
+c64_sprite_placeholder 0
```
Emits 64 bytes of placeholder sprite data: 63 bytes of $FF (filled) + 1 byte of $00 (padding). Creates a solid 24x21 rectangle. Use when no .spr file is provided.

### Joystick (CIA)

Joystick direction constants (available after including c64devk.acme):
```
JOY_UP    = %00000001
JOY_DOWN  = %00000010
JOY_LEFT  = %00000100
JOY_RIGHT = %00001000
JOY_FIRE  = %00010000
```

```
+c64_joy_check JOY_UP, .skip_up
```
Checks if the specified joystick direction is active. If NOT active, branches to the given label. Requires `joystick_state` to be loaded with the current joystick value (active high). Usage pattern:

```asm
    lda $dc00          ; read joystick port 2
    eor #$ff           ; invert (active high)
    sta joystick_state

    +c64_joy_check JOY_FIRE, .no_fire
    ; fire button pressed
    inc score
.no_fire:
```

The generated code provides this pattern in `read_joystick:` and stores the state in `joystick_state`.

### SID (Sound) — Register Constants Only

SID register addresses are defined as constants:
```
SID_BASE = $d400

SID_FREQ_LO_1  = $d400    Voice 1 frequency low byte
SID_FREQ_HI_1  = $d401    Voice 1 frequency high byte
SID_PW_LO_1    = $d402    Voice 1 pulse width low
SID_PW_HI_1    = $d403    Voice 1 pulse width high
SID_CTRL_1     = $d404    Voice 1 control (waveform + gate)
SID_ATK_DEC_1  = $d405    Voice 1 attack/decay
SID_SUST_REL_1 = $d406    Voice 1 sustain/release

SID_FREQ_LO_2  = $d407    Voice 2 (same structure as voice 1)
SID_FREQ_HI_2  = $d408
SID_PW_LO_2    = $d409
SID_PW_HI_2    = $d40a
SID_CTRL_2     = $d40b
SID_ATK_DEC_2  = $d40c
SID_SUST_REL_2 = $d40d

SID_FREQ_LO_3  = $d40e    Voice 3 (same structure)
SID_FREQ_HI_3  = $d40f
SID_PW_LO_3    = $d410
SID_PW_HI_3    = $d411
SID_CTRL_3     = $d412
SID_ATK_DEC_3  = $d413
SID_SUST_REL_3 = $d414

SID_CUTOFF_LO  = $d415    Filter cutoff low byte
SID_CUTOFF_HI  = $d416    Filter cutoff high byte
SID_RES_FILT   = $d417    Resonance and filter control
SID_VOL_MODE   = $d418    Volume and filter mode
```

SID waveform constants:
```
SID_WAVE_TRIANGLE = %00010000
SID_WAVE_SAW      = %00100000
SID_WAVE_PULSE    = %01000000
SID_WAVE_NOISE    = %10000000
SID_GATE_ON       = %00000001
```

No sound macros exist yet. Write directly to SID registers for now.

### Memory (Bank Switching)

```
+c64_bank_rom_enable
```
Enable KERNAL and BASIC ROM, I/O visible. Standard configuration. Writes $37 to $01.

```
+c64_bank_all_ram
```
Disable all ROM, all RAM visible. Writes $35 to $01. Used when you need the memory under BASIC/KERNAL ROM.

```
+c64_bank_io_ram
```
Disable ROM but keep I/O visible, RAM at $A000-$BFFF and $E000-$FFFF. Writes $34 to $01.

Memory constants:
```
C64_RAM         = $0000
C64_ROM_BASIC   = $a000
C64_ROM_KERNAL  = $e000
C64_IO          = $d000
C64_CHARSET_ROM = $d000
```

### VIC-II Register Constants

Available after `!source "macros/vic.acme"`:
```
VIC_BASE = $d000

SPRITE_X_LO       = $d000   (base of sprite X low bytes)
SPRITE_Y          = $d001   (base of sprite Y)
SPRITE_X_HI       = $d010   (MSB of sprite X)
SCREEN_CTRL1      = $d011   (screen control 1: VScroll, 25/24 rows, screen on/off)
RASTER_LINE       = $d012   (current raster line)
LIGHTPEN_X        = $d013   (light pen X)
LIGHTPEN_Y        = $d014   (light pen Y)
SPRITE_ENABLE     = $d015   (sprite enable bits)
SCREEN_CTRL2      = $d016   (screen control 2: HScroll, 40/38 cols, multicolor)
SPRITE_EXPAND_Y   = $d017   (sprite double-height)
MEMORY_PTRS       = $d018   (screen/charset memory pointers within VIC bank)
IRQ_STATUS        = $d019   (interrupt status/acknowledge)
IRQ_ENABLE        = $d01a   (interrupt enable)
SPRITE_PRIORITY   = $d01b   (sprite-to-background priority)
SPRITE_MULTICOLOR = $d01c   (sprite multicolor enable)
SPRITE_EXPAND_X   = $d01d   (sprite double-width)
SPRITE_SPRITE_COLL= $d01e   (sprite-sprite collision)
SPRITE_DATA_COLL  = $d01f   (sprite-data collision)
BORDER_COLOR      = $d020   (border color)
BACKGROUND_COLOR  = $d021   (background color 0)
BACKGROUND_COLOR1 = $d022   (extra background color 1)
BACKGROUND_COLOR2 = $d023   (extra background color 2)
BACKGROUND_COLOR3 = $d024   (extra background color 3)
SPRITE_MULTICOLOR0= $d025   (sprite multicolor 0)
SPRITE_MULTICOLOR1= $d026   (sprite multicolor 1)
SPRITE_COLOR0     = $d027   (sprite 0 color)
...
SPRITE_COLOR7     = $d02e   (sprite 7 color)
```

### CIA Register Constants

```
CIA1_BASE = $dc00

CIA1_PRA     = $dc00   ; Data port A (joystick port 2, Paddle)
CIA1_PRB     = $dc01   ; Data port B (keyboard row, joystick port 1)
CIA1_DDRA    = $dc02   ; Data direction A
CIA1_DDRB    = $dc03   ; Data direction B
CIA1_TIMER_A_LO = $dc04
CIA1_TIMER_A_HI = $dc05
CIA1_TIMER_B_LO = $dc06
CIA1_TIMER_B_HI = $dc07
CIA1_ICR     = $dc0d   ; Interrupt control register
CIA1_CRA     = $dc0e   ; Control register A
CIA1_CRB     = $dc0f   ; Control register B

CIA2_BASE = $dd00

CIA2_PRA     = $dd00   ; Data port A (VIC bank select, RS-232)
CIA2_PRB     = $dd01   ; Data port B (user port)
CIA2_DDRA    = $dd02
CIA2_DDRB    = $dd03
```

---

## Code Generation Details

`c64devk build` runs three phases:

### Phase 1: Spec Loading
1. Reads `c64devk.yaml` → extracts project name, memory layout, screen config
2. Reads `spec/sprites.yaml` → creates `SpriteDef` list
3. Reads `spec/behaviors.yaml` → creates `BehaviorDef` list with typed `Action` objects
4. All parsed into a `ProjectSpec` dataclass

### Phase 2: Assembly Generation

**When behaviors exist** (behavior DSL path — the `behaviors.yaml` `actions` list is non-empty):
| Emitter | Output |
|---------|--------|
| `_emit_header` | ASCII header comment, `!source` macro include |
| `_emit_basic_header` | C64 BASIC `SYS` line at `code_start` |
| `_emit_init` | `sei`, screen/IRQ/sprite setup, `jsr init_sprites` |
| `_emit_irq_handler` | Raster IRQ: ack + inc `frame_ready` + KERNAL jump |
| `_emit_behavior_variables` | `frame_ready`, `joystick_state`, `joystick_prev`, `score` (16-bit if needed) |
| `_emit_behavior_main_loop` | Joystick read + `jsr behaviors_update` + `jsr game_logic` |
| `_emit_sprite_init_behavior` | VIC-II sprite register init for all sprites |
| `_emit_behavior_frame` | `behaviors_update:` (on_frame actions + collision checks) |
| `_emit_behavior_update_sprites` | `update_sprites:` stub — behavior handles movement |
| `_emit_collision_handlers` | Per-collision subroutines (set_sprite_pos, inc_score, play_sound) |

**When no behaviors exist** (hardcoded fallback):
| Emitter | Output |
|---------|--------|
| `_emit_variables` | `frame_ready`, `joystick_state`, `joystick_prev` |
| `_emit_main_loop` | Frame sync + `jsr read_joystick` + `jsr game_logic` + `jsr update_sprites` |
| `_emit_sprite_init` | VIC-II sprite register setup |
| `_emit_joystick_read` | CIA1 $DC00 read subroutine |
| `_emit_sprite_update` | Joystick → position for sprite 0 only |

### Phase 3: Assembly
1. Copie `routines/` to `output/src/routines/`
2. Copies `macros/` to `output/src/macros/`
3. Runs: `acme -f cbm -o output/build/<name>.prg output/src/main.acme`

### Generated Memory Layout
```
$0801         BASIC SYS header (12-13 bytes)
$080D         jmp init
$0810         init: (screen config, IRQ setup, VIC bank, sprite pointers)
              irq: (raster IRQ handler)
              Variables (3 bytes)
              main_loop: (frame sync, input, logic, sprite update)
              init_sprites: (sprite position/color/enable)
              read_joystick: (read $DC00)
              update_sprites: (joystick → position)
              game_logic: (user code from routines/)
...
$2000         Sprite data (64 bytes/sprite, filled or from .spr files)
```

### Runtime variables
- `frame_ready` — byte, set to 1 each raster frame by IRQ handler
- `joystick_state` — byte, joystick port 2 state (active high)
- `joystick_prev` — byte, previous frame's joystick state

These are at labels following the IRQ handler code, so their exact address depends on the code size. Accessible by name in ACME.

---

## C64 Hardware Reference

### Memory Map
```
$0000-$00FF   Zero page (fast addressing, pointer storage)
$0100-$01FF   Stack (grows down from $01FF)
$0200-$03FF   Operating system variables
$0400-$07FF   Screen RAM (default, configurable)
$0800-$9FFF   BASIC RAM (program area, ~38KB available)
$A000-$BFFF   BASIC ROM (or RAM if banked out)
$C000-$CFFF   Upper RAM (free for code/data)
$D000-$DFFF   I/O area (VIC-II, SID, CIA, color RAM)
$E000-$FFFF   KERNAL ROM (or RAM if banked out)
```

### I/O Region ($D000-$DFFF)
```
$D000-$D02E   VIC-II (video controller)
$D400-$D41C   SID (sound chip)
$D800-$DBFF   Color RAM (1K nybbles, only low 4 bits used)
$DC00-$DC0F   CIA #1 (keyboard, joystick)
$DD00-$DD0F   CIA #2 (serial bus, user port, VIC bank)
```

### VIC-II Bank Configuration
The VIC-II sees memory in 16KB banks. The bank is selected by CIA2 bits 0-1 ($DD00):
```
$DD00 bits 0-1: 00 = bank 3 ($C000-$FFFF)
                01 = bank 2 ($8000-$BFFF)
                10 = bank 1 ($4000-$7FFF)
                11 = bank 0 ($0000-$3FFF)

Note: inverted! Writing %11 to bits 0-1 selects bank 0.
```

Within each VIC bank, $D018 selects screen RAM (upper 4 bits) and charset (lower 4 bits):
```
$D018 = (screen_offset << 4) | charset_offset
Where offsets are relative to VIC bank start:
  screen_offset = (screen_addr % 16384) / 1024   (1KB granularity)
  charset_offset = (charset_addr % 16384) / 1024 (2KB granularity for charsets, but some use 1KB)
```

### Sprite Pointers
Sprite data pointers live in the last 8 bytes of screen RAM (relative to VIC bank):
```
Pointer location = screen_start + $03F8 + sprite_index
Pointer value = sprite_data_addr / 64
```

### Joystick Reading
```
Joystick Port 1: CIA1 $DC01 (keyboard matrix column read)
Joystick Port 2: CIA1 $DC00 (data port A)

Reading port 2 (active low):
  bit 0: UP
  bit 1: DOWN
  bit 2: LEFT
  bit 3: RIGHT
  bit 4: FIRE
  
To convert to active high: EOR #$FF
```

### Color RAM
$D800-$DBE8 (1000 bytes at 25 rows x 40 cols). Each byte is a nybble (low 4 bits = color 0-15, high 4 bits are unused/undefined).

---

## 6502 Assembly Quick Reference

### Registers
```
A   Accumulator (8-bit) — primary arithmetic
X   Index register (8-bit) — counting, indexing
Y   Index register (8-bit) — indexing, secondary
PC  Program counter (16-bit)
SP  Stack pointer (8-bit, $01xx)
SR  Status register: NV_BDIZC
    N=Negative, V=oVerflow, _=unused, B=Break, D=Decimal, I=Interrupt, Z=Zero, C=Carry
```

### Essential Instructions

**Load/Store:**
```
LDA #$42      ; Load A immediate
LDA $0400     ; Load A absolute
LDA $0400,X   ; Load A absolute,X
LDA $04,X     ; Load A zero-page,X
LDA ($04),Y   ; Load A indirect,Y
LDX / LDY     ; Same patterns
STA / STX / STY  ; Store
```

**Arithmetic:**
```
ADC #$10      ; Add with carry (A = A + value + C)
SBC #$10      ; Subtract with carry (A = A - value - (1-C))
INC $0400     ; Increment memory
DEC $0400     ; Decrement memory
INX / DEX     ; Increment/decrement X
INY / DEY     ; Increment/decrement Y
```

**Branching (signed 8-bit offset, -128 to +127):**
```
BEQ label     ; Branch if equal (Z=1)
BNE label     ; Branch if not equal (Z=0)
BCS label     ; Branch if carry set (C=1)
BCC label     ; Branch if carry clear (C=0)
BMI label     ; Branch if minus (N=1)
BPL label     ; Branch if plus (N=0)
BVS / BVC     ; Branch if overflow set/clear
```

**Comparison:**
```
CMP #$10      ; Compare A with value (sets N,Z,C)
CPX / CPY     ; Compare X/Y with value
BIT $0400     ; Bit test (sets N=$D7, V=$D6, Z=A&mem)
```

**Jumps:**
```
JMP $1000     ; Absolute jump
JSR $1000     ; Jump to subroutine (pushes return address -1)
RTS           ; Return from subroutine
RTI           ; Return from interrupt
```

**Stack:**
```
PHA / PLA     ; Push/pull A
PHP / PLP     ; Push/pull flags
TXA / TAX     ; Transfer X ↔ A
TYA / TAY     ; Transfer Y ↔ A
```

**Bitwise:**
```
AND #$0F      ; Logical AND
ORA #$F0      ; Logical OR
EOR #$FF      ; Exclusive OR (toggle bits)
ASL           ; Arithmetic shift left (A or memory, C ← bit7, 0 → bit0)
LSR           ; Logical shift right (A or memory, bit0 → C, 0 → bit7)
ROL / ROR     ; Rotate left/right through carry
```

**Flags:**
```
CLC / SEC     ; Clear/set carry
CLI / SEI     ; Clear/set interrupt disable
CLD / SED     ; Clear/set decimal mode
CLV           ; Clear overflow
```

### ACME-Specific Directives
```
!source "file.acme"           ; Include another file
!byte $01, $02, $03           ; Emit bytes
!word $1234                   ; Emit 16-bit word (little-endian)
!fill 100, $00                ; Fill 100 bytes with $00
!bin "data.bin"               ; Include binary file
!macro name .param1, .param2 { ... }  ; Define macro
+name arg1, arg2              ; Call macro
* = $1000                     ; Set origin address
!if / !else / !endif          ; Conditional assembly
.                             ; Current program counter
```

### Common Patterns

**16-bit operations:**
```asm
; 16-bit addition: result += value
    clc
    lda result_lo
    adc value_lo
    sta result_lo
    lda result_hi
    adc value_hi
    sta result_hi
```

**Delay loop:**
```asm
    ldx #$ff
.delay:
    ldy #$ff
.inner:
    dey
    bne .inner
    dex
    bne .delay
```

**Copy memory block:**
```asm
    ldx #0
.copy:
    lda source,x
    sta dest,x
    lda source+$100,x
    sta dest+$100,x
    inx
    bne .copy
```

**Indexed addressing with 16-bit pointer:**
```asm
    ; ptr = $02 (zp)
    lda #<array
    sta $02
    lda #>array
    sta $03
    ldy #0
    lda ($02),y    ; Load byte from array[y]
```

---

## Custom Assembly Patterns

### Writing game_logic.acme

The `game_logic:` subroutine is called every frame, after joystick is read but before sprites are updated. It is a standard 6502 subroutine — use `JSR` to call subroutines, end with `RTS`.

**Accessing joystick:**
```asm
    lda joystick_state
    and #JOY_FIRE
    beq .no_fire
    ; fire button pressed this frame
    ; check joystick_prev for edge detection
.no_fire:
    rts
```

**Edge detection (button just pressed vs held):**
```asm
    lda joystick_prev    ; previous frame state
    and #JOY_FIRE
    bne .was_held        ; already held last frame

    lda joystick_state   ; current frame
    and #JOY_FIRE
    beq .not_pressed     ; not pressed now either

    ; FIRE just pressed (not held last frame, pressed now)
    jsr do_fire_action
    rts

.was_held:
    rts
.not_pressed:
    rts
```

**Adding new sprite variables:**
```asm
    ; Declare new variables after the generated ones
my_counter:  !byte 0
my_score:    !byte 0
```

**Moving a sprite manually (not via joystick):**
```asm
    ; Move sprite 1 (Y at $D003) downward
    inc $d003

    ; Move sprite 1 (X at $D002) right
    inc $d002

    ; X position with MSB handling:
    inc $d002           ; increment low byte
    bne .no_overflow
    lda $d010
    ora #%00000010      ; set bit for sprite 1
    sta $d010
.no_overflow:
```

---

## VICE Remote Monitor (for testing)

VICE supports a TCP remote monitor on port 6510. Launch with `-remotemonitor`:

```bash
x64sc -remotemonitor mygame.prg
```

The `c64devk/vice_bridge.py` module provides a Python client:

```python
from c64devk.vice_bridge import ViceMonitor

mon = ViceMonitor()
mon.connect()
mon.set_breakpoint(0x0810)
screen = mon.read_memory(0x0400, 1000)  # read screen RAM
mon.write_memory(0xd020, 0x01)          # set border to white
mon.continue_execution()
mon.disconnect()
```

Monitor commands (text over TCP):
```
m $0400           ; memory dump at $0400
> $d020 $01       ; write $01 to $d020
r                 ; read CPU registers
break $0810       ; set breakpoint
c                 ; continue
step              ; single step
```

---

## Architecture

### Component Graph
```
User Spec Files (YAML)
    │
    ▼
spec_parser.py  ──→ ProjectSpec dataclass
    │                  (MemoryLayout, ScreenConfig, SpriteDef[], BehaviorDef[])
    ▼
codegen.py  ──→ generate_assembly()  ──→  main.acme string
    │                  writes to output/src/main.acme
    │                  copies macros/ and routines/ to output/src/
    ▼
acme -f cbm  ──→ output/build/<name>.prg
    │                  (2-byte CBM load address header + binary)
    ▼
x64sc -autostart <name>.prg

Testing path:
x64sc -remotemonitor <name>.prg
    │                  (headless, TCP :6510)
    ▼
vice_bridge.ViceMonitor
    │                  (connect, read_memory, write_memory, breakpoints)
    ▼
test_runner.py (planned)
    │                  (assertion engine, frame counting, screen diffing)
    ▼
test report
```

### Extension Points

**Adding a new emitter to codegen:**
1. Write `_emit_foo(spec, lines)` in `codegen.py`
2. Call it from `generate_assembly()`
3. If it needs new spec data, add a `_load_foo()` method to `ProjectSpec` in `spec_parser.py`

**Adding a new macro:**
1. Add `!macro c64_foo .p1, .p2 { ... }` to the appropriate `macros/*.acme` file
2. Document in this skill file and `README.md`

**Adding a new command:**
1. Add subparser in `cli.py main()`
2. Add handler `cmd_foo()` in `cli.py`
3. Add match arm in `main()` dispatch

---

## Current Limitations

1. **No multi-sprite joystick control in fallback path**: When behaviors DON'T exist, the hardcoded `update_sprites:` only handles `spec.sprites[0]`. Use the behavior DSL (`update_sprite:` action per sprite) for multi-sprite joystick control.

2. **No SID macros**: The SID macro file provides register constants only. The `play_sound` action sets frequency and gate but has no duration tracking, ADSR envelopes, or note-name-to-frequency conversion.

3. **No keyboard input**: Only joystick port 2 is read. Keyboard scanning must be implemented manually in routines.

4. **No multicolor bitmap mode**: Currently only hires character mode is supported in codegen (though multicolor character mode is partially supported via the `screen.mode` and `screen.multicolor` settings).

5. **No disk I/O or multi-load**: Single `.prg` output only. No support for loading additional data from disk.

6. **No raster splits**: The IRQ handler fires at raster line 0 only. Custom raster interrupts must be implemented manually.

7. **Variable placement is fragile**: `frame_ready`, `joystick_state`, and `joystick_prev` are placed immediately after the IRQ handler code. Adding significant code in `init:` could shift these addresses. Prefer explicit `* =` directives for critical data.

8. **X position limited to 255 outside behavior DSL**: The non-behavior `update_sprites:` routine uses `inc $d000`/`dec $d000` for X movement, which doesn't handle the $D010 MSB correctly. The behavior DSL's `set_sprite_pos` and `update_sprite` handle MSB correctly.

---

## Tips for OpenCode

### When a user asks to create a C64 game/program

1. First run `c64devk new <name>` to scaffold the project
2. Edit `c64devk.yaml` to set the project name, output filename, and memory layout
3. Define sprites in `spec/sprites.yaml` (name, position, color, data file)
4. Define behaviors in `spec/behaviors.yaml` (on_frame actions for input/movement, on_collision for score/reset)
5. For custom logic beyond what the behavior DSL covers, write code in `routines/game_logic.acme`
6. Run `c64devk build` and fix any errors
7. Run `c64devk run` to launch in VICE
8. Iterate: modify spec or routines, rebuild, rerun

### When the generated code doesn't do what's needed

The `routines/` directory is the escape hatch. Write any 6502 assembly there. Files in `routines/` are copied but never overwritten by the build process. `game_logic.acme` is special — it's called every frame from the main loop.

### When the spec language is too limited

Modify the framework itself:
- `spec_parser.py`: Add new fields to existing dataclasses, or new dataclasses
- `codegen.py`: Add new `_emit_*()` functions
- `macros/`: Add new ACME macros
- `skills/SKILL.md`: Document the new capability

### Common 6502 assembly gotchas

- **No 16-bit operations**: You must handle 16-bit math with `ADC`/`SBC` chains
- **Branch range limited**: Branches only reach -128 to +127 bytes; use `JMP` for longer jumps
- **X vs Y indexing**: `LDA $2000,X` uses X; `LDA ($02),Y` uses Y. They're not interchangeable
- **Stack depth**: Only 256 bytes of stack; recursion is impractical
- **No multiplication/division**: Use lookup tables or shift-add loops
- **NMI vs IRQ**: NMI on RESTORE key cannot be disabled; just `RTI` at the start of your program
- **$D019 write to ack**: Writing any value to $D019 acknowledges the interrupt; reading gives the status

---

## C64 Code Pattern Recipes

These are working, tested 6502 patterns for common C64 tasks. Copy and adapt them.

### Keyboard input (WASD → joystick_state)

Reads the C64 keyboard matrix using CIA1 ($dc00/$dc01). Sets `joystick_state`
to be consumed by the framework's `update_sprites` routine.

```asm
keyboard_read:
    lda #0
    sta joystick_state

    ;; W (up) — column 1 ($fd), row 1 ($02)
    lda #$fd
    sta $dc00
    lda $dc01
    and #$02
    bne k_chk_s
    lda joystick_state
    ora #JOY_UP
    sta joystick_state
k_chk_s:
    ;; S (down) — column 1 ($fd), row 5 ($20)
    lda #$fd
    sta $dc00
    lda $dc01
    and #$20
    bne k_chk_a
    lda joystick_state
    ora #JOY_DOWN
    sta joystick_state
k_chk_a:
    ;; A (left) — column 2 ($fb), row 1 ($02)
    lda #$fb
    sta $dc00
    lda $dc01
    and #$02
    bne k_chk_d
    lda joystick_state
    ora #JOY_LEFT
    sta joystick_state
k_chk_d:
    ;; D (right) — column 2 ($fb), row 3 ($08)
    lda #$fb
    sta $dc00
    lda $dc01
    and #$08
    bne k_done
    lda joystick_state
    ora #JOY_RIGHT
    sta joystick_state
k_done:
    rts
```

**Keyboard matrix reference:**
```
Column ($dc00 write):         Row ($dc01 read):
  $FE (bit 0 clear) = col 0     $01 (bit 0) = row 0  (DEL, RET, cursor keys)
  $FD (bit 1 clear) = col 1     $02 (bit 1) = row 1  (W, 3, A, 4, Z, S, E, shift)
  $FB (bit 2 clear) = col 2     $04 (bit 2) = row 2  (R, D, C, F, T, X)
  $F7 (bit 3 clear) = col 3     $08 (bit 3) = row 3  (5, 6, Y, G, space ...)
  $EF (bit 4 clear) = col 4     $10 (bit 4) = row 4
  $DF (bit 5 clear) = col 5     $20 (bit 5) = row 5  (S, U, H, J ...)
  $BF (bit 6 clear) = col 6     $40 (bit 6) = row 6
  $7F (bit 7 clear) = col 7     $80 (bit 7) = row 7  (1, stop, CTRL ...)
```

### Write text to screen RAM

Screen RAM at $0400-$07E7 (1000 bytes, 40x25). Each byte is a character code
(PETSCII). The charset is defined by the VIC-II memory pointer ($D018).

```asm
; Write "SCORE: 0000" to the top line of the screen
    ldx #0
txt_loop:
    lda score_text, x
    beq txt_done
    sta $0400, x         ; top-left corner of screen
    inx
    bne txt_loop         ; max 255 chars
txt_done:
    rts

score_text: !text "score: 0000", 0
```

**PETSCII quick reference:**
```
$20 = space  $30-$39 = 0-9  $01 = A  $02 = B ... $1A = Z
$00 = @     $1B = [         $1C = £          $1D = ]
$1E = ↑     $1F = ←
$41-$5A = a-z (lowercase in uppercase/graphics mode)
```

**Screen color RAM** at $D800-$DBE7 (1000 bytes, nybbles). Each byte sets
the foreground color (0-15) for the corresponding screen position.

```asm
; Set top line text color to yellow (7)
    ldx #0
    lda #7
col_loop:
    sta $d800, x
    inx
    cpx #40
    bne col_loop
```

### Sprite collision detection with cooldown

Reads $D01E (sprite-sprite collision register). Using a cooldown timer
prevents instant re-triggering.

```asm
hit_timer:  !byte 0       ; cooldown counter

check_collision:
    lda hit_timer
    beq c_check            ; cooldown expired, check
    dec hit_timer
    rts

c_check:
    lda $d01e               ; read collision register
    and #$03                ; sprite 0 + sprite 1 mask
    beq c_no_hit

    sta $d01e               ; acknowledge (write clears register)

    ;; --- collision response ---
    clc
    lda score
    adc #10
    sta score
    lda score+1
    adc #0
    sta score+1

    lda #30
    sta hit_timer           ; 30-frame cooldown

c_no_hit:
    rts
```

**Note**: `$D01E` reads return the collision state, then the register auto-clears
on the next write. Reading `$D01F` (sprite-data collision) works the same way.
Always `STA $D01E` after reading to ensure cleanup.

### SID sound — play a note with duration timer

```asm
snd_timer:  !byte 0

play_sound_c4:
    ;; C-4 frequency = 4455 ($1167)
    lda #<4455
    sta $D400               ; voice 1 freq lo
    lda #>4455
    sta $D401               ; voice 1 freq hi
    ;; ADSR: attack=2, decay=9
    lda #$29
    sta $D405
    ;; Sustain=8, release=0
    lda #$80
    sta $D406
    ;; Triangle wave + gate on
    lda #$11
    sta $D404
    ;; Master volume = 15
    lda #$0F
    sta $D418
    ;; 20 frame duration
    lda #20
    sta snd_timer
    rts

sound_tick:                 ; call once per frame
    lda snd_timer
    beq s_done
    dec snd_timer
    bne s_done
    ;; Gate off voice 1
    lda $D404
    and #$FE
    sta $D404
s_done:
    rts
```

### 16-bit score management

```asm
score:  !byte 0, 0         ; 16-bit little-endian

add_to_score:
    clc
    lda score
    adc #10                 ; low byte
    sta score
    lda score+1
    adc #0                  ; carry into high byte
    sta score+1
    rts

subtract_from_score:
    sec
    lda score
    sbc #10
    sta score
    lda score+1
    sbc #0
    sta score+1
    rts
```

### Pseudo-random number (using raster line)

```asm
; Returns random-ish byte in A. Uses VIC-II raster counter ($D012)
; which cycles 0-311 every frame.
get_random:
    lda $d012               ; raster line (changes rapidly)
    eor $dc04               ; CIA1 timer A lo (free-running)
    adc frame_ready         ; frame flag
    rts

; Get random position in range 24-231 for X
random_x:
    jsr get_random
    and #$7F                ; 0-127
    clc
    adc #50                 ; 50-177
    rts
```

### Simple state machine (playing → dying → game over)

```asm
GAME_PLAYING = 0
GAME_DYING   = 1
GAME_OVER    = 2

game_state:  !byte GAME_PLAYING
state_timer: !byte 0
lives:       !byte 3

game_logic:
    lda game_state
    cmp #GAME_PLAYING
    beq do_playing
    cmp #GAME_DYING
    beq do_dying
    cmp #GAME_OVER
    beq do_game_over
    rts

do_playing:
    ; ... normal game logic ...
    ; on death:
    dec lives
    lda lives
    beq .go_game_over
    lda #GAME_DYING
    sta game_state
    lda #60
    sta state_timer
    rts
.go_game_over:
    lda #GAME_OVER
    sta game_state
    rts

do_dying:
    ; flash sprites, wait
    dec state_timer
    bne .still_dying
    lda #GAME_PLAYING
    sta game_state
.still_dying:
    rts

do_game_over:
    ; wait for SPACE to restart
    lda #$EF               ; column for space bar
    sta $dc00
    lda $dc01
    and #$10
    bne .waiting
    ; restart
    lda #3
    sta lives
    lda #0
    sta score
    sta score+1
    lda #GAME_PLAYING
    sta game_state
.waiting:
    rts
```

### Inline variable data (avoid executing data as code)

When placing variable data at the top of a routine file included via `!source`,
always jump past it:

```asm
    jmp gcode              ; skip variable data

my_var:   !byte 0
counter:  !byte 0, 0

gcode:                     ; actual code starts here
    inc my_var
    rts
```

**Never do this:**
```asm
my_var:  !byte 100         ; CPU executes 100 ($64) as opcode!
counter: !byte 0
    lda my_var             ; this code is unreachable junk
```

The first byte of data gets executed as an instruction. `$64` on NMOS 6502 is
undefined (may crash/NOP). `$00` is BRK (causes KERNAL interrupt → back to BASIC).

