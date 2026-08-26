# Session State — dodge (chrome splash title work, IN PROGRESS)

Handoff for the next model. Repo: `~/Coding/C64DevKit` (branch `dmz-backup`),
game at `games/dodge`. Read AGENTS.md first — spec-driven workflow
(spec/*.yaml is the source of truth; routines/ changes MUST be documented
in spec/behaviors.yaml; CHANGELOG.md gets an entry per change).

## Current task (uncommitted, chrome splash title — WORKING, verify + commit)

Chrome block-logo title for the splash screen ("LAST STAR SYSTEM" styled
after the marketing cover) — implemented and VERIFIED WORKING after two
bugs were fixed this session:

### RESOLVED BUGS (both were fallout from the charset/sprite memory move)
1. INVISIBLE SHIP: ship pointer `adc #$80` stayed stale → ship pointed at
   the charset ($2000). Fixed to `adc #$D0`. (My earlier pass targeted
   `#$B0` from the docs' block numbering — the code actually said `#$80`.)
2. GARBAGE ASTEROIDS: the framework's ROM-charset copy still went to
   $3800 (the rock block!) and overwrote rock.spr at boot with ROM glyph
   data. ROOT CAUSE: config precedence — the codegen reads the charset
   from `c64devk.yaml`'s `screen:` section (`spec.screen.charset_addr`),
   NOT `memory.charset`; `spec/game.yaml`'s screen block is DEAD config
   (from_dir only loads sprites/behaviors from spec/). Fixed by adding
   `screen.charset: 0x2000` (+ screen_ram) to `c64devk.yaml`.

### VERIFIED (live VICE)
- rock at $3800 byte-matches rock.spr; asteroid ptrs $E0/$E0/$E0;
  ship ptr $D0, skull $D4, rock $E0, radar $E1.
- Ship, octopus (8-frame fluid cycle), asteroid rock, radar crosshair,
  HUD, zones, DMZ, and the chrome splash title all render correctly.
- Chromed title: glyphs at $2580+ (charset $B0-$DF), codes/colours
  byte-verified in RAM.

### The charset/$D018 truth (learned the hard way)
- VIC charset address = **LOW NIBBLE of $D018 × $400** within the bank
  (bits 3-1 theory is WRONG — proven by the title rendering from $3D80
  with $D018=$1E). $D018=$18 → charset at $2000 ✓.
- Bank 0 is fully usable for charset at $0000-$3C00 (16 blocks × $400).
- The framework's ROM charset copy (codegen) targets
  `spec.screen.charset_addr` → `c64devk.yaml` `screen:.charset`.

### Memory layout (current)
| What | Address | Pointer |
|------|---------|---------|
| charset (ROM copy + custom glyphs) | $2000-$27FF | — |
| game code | $0801-$1F1B | — |
| extended code (strings/engine/splash/boom/title data) | $2900-$3020ish | — |
| sfx presets | ~$3020-$3145 | — |
| base sprites (codegen) | $3400-$353F | $D0-$D4 |
| ship frame 1 | $3540-$3600 | $D5-$D8 |
| skull frames 1-7 | $3640-$37C0 | $D9-$DF |
| rock | $3800 | $E0 |
| radar | $3840 | $E1 |

### Chrome title implementation details (all in games/dodge)
- `tools/title_font.py` — generator: LASTRYEM letters (DejaVu Serif Bold
  @ 64 downscaled to 16x24), 48 glyphs → `assets/title_font.bin`,
  preview at `sprite_edit/title_preview.png`.
- draw_splash: copies glyphs to $2580-$26FF (3 loops 128/128/128),
  draws 2x3 grid (16 letters × 2 cols × 3 rows) at $0544/$056C/$0594 with
  colours $D944/$D96C/$D994 (white/yellow/orange). title_text indices
  1-8 (0 = space). ds_title string removed.
- splash_bars narrowed cols 0-3 / 36-39 (was clobbering the title's edge
  colour every frame).

### Uncommitted working-tree files (all part of this feature)
- games/dodge/c64devk.yaml (screen.charset 0x2000, screen_ram 0x0400,
  memory.sprite_data 0x3400)
- games/dodge/spec/game.yaml (same charset — kept in sync although dead)
- games/dodge/routines/game_logic.acme (title draw, pointer fixes,
  sprite origins $3540+, narrowed splash bars)
- games/dodge/spec/sprites.yaml, spec/behaviors.yaml (block map $D0-$E1)
- games/dodge/tools/title_font.py (new), assets/title_font.bin (new)
- c64devk/vice_bridge.py (read_memory chunking for big dumps)
NEXT: do a full player-style pass (c64devk run), then commit everything
with a CHANGELOG entry (memory layout + chrome title + fixes).

## VICE testing environment quirks (hard-learned, save you hours)

- MONITOR PORT 6510 IS SINGLE-INSTANCE. Failed test asserts skip
  kill_vice → leaked VICE instances hold the port → later runs connect to
  the STALE instance (different build! wrong variable addresses!) = chaos.
  ALWAYS: `pgrep -c x64sc` first, `kill -9` strays, wrap tests in try/finally
  with kill_vice.
- Autostart/keybuf `sys2061` flakes: sometimes the PRG loads but never
  runs (screen shows the BASIC banner). Robust start: connect, check
  state (PRG initial value = GAME_SPLASH=3, present even before running);
  if not running, `mon.send("g $0810")` to jump to init. Retry the launch
  up to 3× if the PRG didn't load (state reads 0, $0801 not the stub).
- The floating joystick ($DC00 on port 2 with no joystick) randomly
  presses FIRE/moves — the splash exits itself, the ship drifts, deaths
  happen. For clean captures: repeatedly poke `$DC00 = $FF`
  (hold-all-released) in a thread, or accept randomness.
- Any monitor command (peek/r/send) PAUSES the CPU. To capture a rendered
  frame: resume (`send "g"`), sleep ~1.5-2s for the game to draw, THEN
  capture (`capture_vice_window(path, proc.pid)` — Xlib, no pause). Capturing
  while paused freezes the frame mid-draw (that was the "LASI SIAK" ghost).
- vice_bridge read_memory is now preamble-immune and chunks large reads;
  get_register parses the current `.;PC AA XX YY SP` format (+ legacy
  tokens); launchers resolve PRG paths absolute. Any first-read-after-a-
  breakpoint-stop crash shows as garbage bytes — the fixed parser handles it.
- Animation/sound state tests: breakpoint at a label (e.g. `anim_update`,
  `boom_tick`), `g` to park, poke, resume — the proven per-frame technique.
- The `.lbl` file does NOT contain local labels (only top-level + vars) —
  single-stepping from a parked `PC` with `z` works for inner labels, or
  compute the address from the sym + instruction offsets.

## Game mechanics state (all committed & working before the title work)

- Binary level thresholds: 256 / 512 / 1024 / +512 per level after.
- L5 ceiling: spawn interval 24 (softened), 3 concurrent asteroids, ±3
  px/frame speeds, octopus 35 px/s pulsing red, +1 life per level-up at
  L5+ (cap 9). Lives never refilled before this.
- Sounds: SID v2 engine noise rumble (direction-tuned + LFSR churn),
  death_boom (v3 noise sweep + v2 sub-drop, 60f, border flash),
  sfx_coin level-up chime (terminates now), enemy respawn silent.
- Enemies named `skull*` files but are an OCTOPUS. 8-frame fluid tentacle
  cycle (octopus_wave.py generated, skull1-7.spr at $89-$8F blocks).
- CHANGELOG.md: full OpenSpec-style history (check it for prior entries;
  add one per committed change).
