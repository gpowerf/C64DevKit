# C64DevKit Architecture

## Design philosophy

C64DevKit is a **template-driven code generator**. The spec language (YAML) is the single source of truth. The generator produces readable ACME assembly that a human could have written. The generated code is never edited — custom logic lives in `routines/*.acme` which the generator includes but never overwrites.

This differs from a traditional compiler in two ways:
1. **Readable output**: The generated `.acme` is meant to be understood, not just consumed. If the code generator breaks, you can read the output and fix it.
2. **Passthrough**: `routines/` provides an escape hatch for anything the spec language can't express yet.

## Component diagram

```
┌─────────────────────────────────────────────────────────────┐
│                          User                               │
│                    (YAML specs + .acme routines)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      c64devk (CLI)                          │
│  bin/c64devk  ─┬─  c64devk/cli.py      argparse commands    │
│                ├─  c64devk/spec_parser.py  YAML → dataclass │
│                ├─  c64devk/codegen.py       IR → ACME .asm  │
│                ├─  c64devk/config.py        path resolution  │
│                └─  c64devk/vice_bridge.py   VICE TCP bridge │
└──────────────────────────┬──────────────────────────────────┘
                           │ subprocess
                ┌──────────┼───────────┐
                ▼          ▼           ▼
         ┌──────────┐ ┌────────┐ ┌─────────┐
         │   ACME    │ │  VICE  │ │  VICE   │
         │ assembler │ │  GUI   │ │ headless │
         └──────────┘ └────────┘ └────┬────┘
                                      │ TCP :6510
                                      │ remote monitor
```

## Data flow

### 1. `c64devk new <name>`

```
c64devk/templates/project/
    ├── c64devk.yaml
    ├── spec/
    │   ├── game.yaml
    │   ├── sprites.yaml
    │   └── behaviors.yaml
    └── routines/
        └── game_logic.acme

        │ shutil.copytree + template substitution
        ▼

<name>/
    ├── c64devk.yaml         "{{name}}" → <name>
    ├── spec/...
    └── routines/...
```

### 2. `c64devk build`

```
Phase 1: Spec Loading
────────────────────
c64devk.yaml  ─┐
spec/*.yaml   ─┤  →  ProjectSpec (dataclass with nested MemoryLayout,
                │      ScreenConfig, SpriteDef[], BehaviorDef[])
                ▼

Phase 2: Code Generation
────────────────────────
ProjectSpec  ──→  generate_assembly() ──→  main.acme (string)
                │
                │  pipeline:
                │    _emit_header()        ; boilerplate
                │    _emit_basic_header()  ; BASIC SYS
                │    _emit_init()          ; screen, IRQ, sprites
                │    _emit_irq_handler()   ; raster IRQ
                │    _emit_variables()     ; frame_ready, joystick_state
                │    _emit_main_loop()     ; wait frame → read joy → logic → sprites
                │    _emit_sprite_init()   ; VIC-II sprite registers
                │    _emit_joystick_read() ; CIA1 $dc00 reader
                │    _emit_sprite_update() ; joystick → sprite position
                │    _emit_user_routines() ; !source from routines/
                │    _emit_sprite_data()   ; sprite binary data at configured addr
                │
                ▼
           output/src/main.acme

Phase 3: Assembly
─────────────────
output/src/main.acme  ──→  acme -f cbm -o output/build/<name>.prg
output/src/macros/*.acme

  Macro resolution:
    main.acme:
      !source "macros/c64devk.acme"
        └─ !source "macros/vic.acme"
        └─ !source "macros/cia.acme"
        └─ !source "macros/sid.acme"
        └─ !source "macros/memory.acme"

  All !source paths are relative to ACME's CWD, which is set to output/src/.

Phase 4: Output
───────────────
output/build/<name>.prg  (CBM format: 2-byte load address + data)
```

### 3. `c64devk run`

```
build pipeline  ──→  x64sc -autostart output/build/<name>.prg
```

### 4. `c64devk test` (planned)

```
build pipeline  ──→  x64sc -remotemonitor output/build/<name>.prg
                          │ (headless)
                          │
                     ViceMonitor.connect()  ──→  TCP 127.0.0.1:6510
                          │
                     ViceMonitor.send("m $0400")  ──→  reads screen RAM
                     ViceMonitor.send("break $0810")  ──→  set breakpoints
                     
                     Test assertions:
                       - memory values match expected
                       - sprite positions correct after N frames
                       - screen content matches reference
```

## Key data structures

### ProjectSpec

```python
@dataclass
class ProjectSpec:
    name: str                           # project name
    output: str                         # output .prg filename
    memory: MemoryLayout                # code, sprite, charset, screen addresses
    screen: ScreenConfig                # mode, colors
    sprites: list[SpriteDef]            # up to 8 C64 sprites
    behaviors: list[BehaviorDef]        # behavior definitions
    constraints: list[dict]             # memory/cycle budgets (unused)
    routines: list[str]                 # passthrough routine names
    project_dir: Path                   # filesystem location
    basic: bool                         # include BASIC header
```

### MemoryLayout

```python
@dataclass
class MemoryLayout:
    code_start: int     # default $0801 (BASIC program area)
    code_end: int       # default $CFFF (before I/O at $D000)
    sprite_data: int    # default $2000 (64-byte aligned)
    charset: int        # default $3800
    screen_ram: int     # default $0400
```

### ScreenConfig

```python
@dataclass
class ScreenConfig:
    mode: str               # "hires", "multicolor", "text"
    charset_addr: int       # charset data location
    screen_ram: int         # screen RAM location
    background_color: int   # 0-15
    border_color: int       # 0-15
    multicolor: bool        # multicolor mode flag
```

### SpriteDef

```python
@dataclass
class SpriteDef:
    name: str          # identifier (used in behaviors)
    index: int         # VIC-II sprite number (0-7)
    x: int             # X position (0-511)
    y: int             # Y position (0-255)
    color: int         # sprite color (0-15)
    multicolor: bool   # multicolor sprite
    multicolor1: int   # multicolor 1 (shared)
    multicolor2: int   # multicolor 2 (shared)
    enabled: bool      # sprite visibility
    priority: bool     # foreground vs background
    expand_x: bool     # double-width
    expand_y: bool     # double-height
    data_file: str     # path to .spr binary data
```

## Generated assembly layout

The generated `main.acme` follows this memory layout:

```
Address       Content
───────────────────────────────────────
$0801         BASIC header: SYS <init_addr>
$080D         jmp init  (3 bytes)
$0810         init:  (sei, screen setup, IRQ config, sprite init)
              irq:   (raster IRQ handler)
              frame_ready, joystick_state, joystick_prev  (3 bytes)
              main_loop:  (infinite loop with frame sync)
              init_sprites:  (VIC-II register setup)
              read_joystick:  (CIA1 port read)
              update_sprites:  (joystick → position mapping)
              game_logic:  (!source routines/game_logic.acme)
...
$2000         Sprite data (64 bytes per sprite)
```

## Macro library design

The `macros/` directory provides four files that get copied into `output/src/macros/` during build:

| File | Purpose | Contents |
|------|---------|----------|
| `c64devk.acme` | Master include | `!source` directives + utility macros + constants |
| `vic.acme` | VIC-II video | Register constants (`VIC_BASE = $d000`), screen macros, sprite macros, raster macros, color constants |
| `cia.acme` | CIA I/O | Register constants (`CIA1_BASE = $dc00`), joystick constants |
| `sid.acme` | SID sound | Register constants (`SID_BASE = $d400`), waveform constants |
| `memory.acme` | Memory/banking | Bank switching macros, memory constants |

All paths in `!source` directives are relative to the ACME working directory (`output/src/`). The build process ensures all files are copied before assembly.

## VICE remote monitor protocol

VICE's remote monitor listens on TCP port 6510 when launched with `-remotemonitor`. The protocol is text-based:

| Command | Response | Purpose |
|---------|----------|---------|
| `m $0400` | `>C:0400  20 20 20 20 ...` | Memory dump (screen RAM) |
| `> $0400 $2a` | (none) | Write byte to memory |
| `break $0810` | `BREAK: 1  C:$0810` | Set breakpoint |
| `c` | (runs until break) | Continue execution |
| `r` | `  PC  SR AC XR YR SP ...` | Read CPU registers |

The `ViceMonitor` class wraps these commands:

```python
monitor = ViceMonitor()
monitor.connect(timeout=5.0)
monitor.set_breakpoint(0x0810)
monitor.continue_execution()
# ... program hits breakpoint ...
screen_ram = monitor.read_memory(0x0400, 40)  # read first line of screen
monitor.disconnect()
```

## Extension points

### Adding a new spec type

1. Define a dataclass in `spec_parser.py`
2. Add loading logic in `ProjectSpec.from_dir()` or a new `_load_*()` method
3. Add an `_emit_*()` function in `codegen.py` and call it from `generate_assembly()`
4. Update project templates in `c64devk/templates/project/spec/`
5. Update documentation

### Adding a new macro

1. Add macro definition to the appropriate `macros/*.acme` file
2. Document in `skills/SKILL.md` and `README.md`
3. Optionally add a Python helper in `codegen.py` that emits the macro call

### Adding a new command

1. Add subparser in `cli.py` `main()`
2. Add handler function (`cmd_*()`)
3. Add match arm in the main dispatch

## Design constraints

1. **No external Python dependencies beyond PyYAML**: The framework must work with a stock Python installation. No Jinja2, requests, or other third-party packages.

2. **Readable generated code**: The `.acme` output must be a valid standalone ACME project that can be assembled independently (with the macro library).

3. **Never overwrite user code**: `routines/` files are copied but never modified by the build process.

4. **CBM PRG format**: Output files use the standard C64 PRG format (2-byte little-endian load address followed by data).

5. **Idempotent builds**: Running `c64devk build` multiple times produces identical output.

## Current limitations

- Sprite update in codegen only handles the first sprite (index 0)
- Behavior actions (`behaviors.yaml`) are parsed but not compiled to assembly — game logic must be written by hand in `routines/`
- SID macros provide register constants only, no note-playing or instrument macros
- No support for multicolor bitmap mode or extended background color mode
- No disk I/O or multi-load game support
- No raster split or custom IRQ configuration beyond the default frame timer
