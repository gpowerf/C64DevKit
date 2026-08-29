# Changelog — C64DevKit

Historical change log in the spirit of OpenSpec: every change is a
semantic unit with a date-prefixed ID, a **What** (the concrete
change), and a **Why** (the problem or intent it addressed).  Commit
hashes link each entry back to the git record.

**Conventions**

- One entry per change (a change may span several commits).
- ID: `YYYY-MM-DD · short slug`, newest first.
- **What** — behaviour, files, systems touched.
- **Why** — the motivation.  For bug fixes, the symptom.
- **Commits** — the contributing hashes.
- Maintain by hand: when you commit a change, append its entry at the
  top of the list.  `git log --oneline` remains the raw record.

---

## 2026-08-28 · asteroids: no radar marker on level 1

- **Bug:** the radar crosshair appeared on level 1 even though no rocks
  exist there.  Root cause: `ast_update`'s post-spawn pre-roll ran
  whenever `ast_warn_dir == 255 && ast_pdly == 0` — which is always
  true on a level-1 fresh start, since `ast_spawn` is a no-op below
  level 2.  The warning was rolled every spawn-timer cycle and the
  marker just sat at a cell warning for a rock that could never exist.
- **What:** the post-spawn pre-roll in `ast_update` is now gated on
  `level >= 2` (single point fix — `ast_preview` itself stays
  ungated; its other two call sites, `level_update` and the linger
  expiry, cannot fire on level 1).  `no_asteroids_at_level_1`
  extended with `ast_warn_dir == 255` and radar sprite parked at
  `$d00a/$d00b = 0/250`; specs (behaviors.yaml, ASSEMBLY.md,
  DESIGN.md) documented the level-1 no-warning rule.
- **Why:** a warning for nothing undercuts the game's honest telegraphs
  and reads as a bug.
- **Commits:** (this change set)

---

## 2026-08-28 · asteroids: top rock spawns behind the radar marker (Y=50)

- **What:** top-edge asteroids now materialise at sprite-Y **50**, 10 px
  behind the Y=60 marker cell, and slide down through the crosshair.
  Both spawn paths changed: `ast_spawn`'s pre-rolled path subtracts 10
  from `ast_warn_y` when `ast_warn_dir == 1`, and the random-pick path
  uses Y=50 outright.  `ast_preview` still rolls the marker at Y=60 —
  it is now the crossing cell.  Specs (behaviors.yaml, DESIGN.md,
  ASSEMBLY.md) and the `top_spawn_enters_at_top_border` test synced.
- **Why:** the rock popped in ON the marker (dodging past the glance
  warning — visually it appeared in front of, or exactly at, the
  crosshair).  Spawning behind the marker keeps the warning cell clear
  so the arrival always reads as the warned rock crossing the border.
- **Commits:** (this change set)

---

## 2026-08-28 · asteroids: entry cells realigned (top 60, bottom 228, right X=224)

- **What:** the asteroid top entry (marker + rock spawn) moved from
  sprite-Y 62 to **60** — row 1 (58-66) on the corrected sprite-Y map,
  flush edge-to-edge with the HUD row; the bottom entry moved from 234
  to **228** — row 22 (226-234), 6 px above its old baseline so it
  clears the bottom text-row edge; the right entry moved from X=230 to
  **224** — 6 px left of the DMZ threshold.  Both paths (`ast_spawn` and
  `ast_preview`) changed together so marker and rock still share one
  exact cell; tests/docs synced.
- **Why:** the markers rendered off the natural grid cells the player
  perceives — top sat 2 px low against the HUD, bottom 4 px low against
  the last text row.  Alignment fix, no behaviour change.
- **Commits:** (this change set)

---

## 2026-08-28 · asteroids: one rock per marker (warning consumption fix)

- **Bug:** from the first level with asteroids onwards, several rocks
  left from a single radar marker on every level.  Root cause: the
  marker-linger change (3a25a78) stopped `ast_spawn` from clearing the
  pre-rolled warning and moved the re-pre-roll into the spawn path —
  but `ast_pdly` ticked **once per spawn** instead of once per frame,
  and the pre-rolled cell was never marked used.  Result: up to 8
  spawns reused the same `ast_warn_x/y` + `ast_next_vx/vy`, so rocks
  (and at L4+ whole clusters) poured out of one cell at 24–40-frame
  intervals.
- **Fix (`routines/game_logic.acme`):** the warning is now CONSUMED at
  spawn (`ast_warn_dir = 255` + `ast_pdly = 8` claim); `ast_update`
  decrements the linger **per frame** and re-pre-rolls the next
  warning when it expires; `radar_do` keeps the crosshair on the
  consumed cell while the rock crosses it (linger-aware visibility);
  `restart()` and the level transition reset `ast_pdly` with the warn
  state.  Every pre-roll feeds exactly one spawn.
- **Spec/tests synced:** `spec/behaviors.yaml` (variable entry +
  spawn/preview/radar docs), `spec/tests.yaml` (3 new regression
  tests: consumption, no-reuse across spawns, per-frame linger tick),
  `ASSEMBLY.md` (layout + asteroid system docs).
- **Commits:** (this change set)

---

- **Sprite-Y map corrected (the actual root cause of every round's
  complaints):** the C64 text window spans sprite-Y **50..250** when
  rows are 8 px — row 0 = 50-58 … row 24 = 242-250.  All previous
  coordinates (0/16/21/24/110/176/190/210…) were computed against a
  0-based field, so top markers/rocks rendered above the top border and
  bottoms showed up 1/4–1/3 of a screen high on real hardware: the
  "above the border" & "spawns far up" reports were literally correct.
  Entries now: TOP Y=62 (row 1, below the HUD), BOTTOM Y=234 (row 23),
  sides X=24/230 × Y 62-226, marker = exact warn cell.
- **No-marker regression fixed:** the marker-linger ast_pdly countdown
  skipped the preview entirely when nothing had claimed a warning yet
  (fresh start at level ≥2 via the loader: warn_dir=255 forever → no
  markers at all).  `beq .pd_d` now falls through to jsr ast_preview
  when ast_pdly==0, so the pre-roll always happens.
- **Verified visually** (X11 captures of real level-5 play): crosshair
  rendering one row below the HUD, rocks spawning there and descending.
- **Commits:** (this change set)

---
## 2026-08-26 · radar/entries: in-field cells, marker linger, edge-class fix

- **Edge classification by angle GROUP** (0-7 bottom, 8-15 top, 16-23
  right, 24-31 left) in both ast_preview and ast_spawn — the old sign
  tests sent down-left top angles to the right branch (markers/rocks in
  the DMZ) and horizontal angles with dy≠0 to top/bottom.  Byte-verified
  in the built PRG (spawn $1853 / preview $19CC ladders).
- **Entry cells moved INSIDE the visible playfield** — top Y=24
  (row 3), bottom Y=176 (row 22), right X=230, left X=24 — previous
  values (top 16/0, bottom 210) sat at the border line and rendered
  differently depending on the window's border crop, reading as "above
  the border" / "far off the edge" on some setups.  Never any border
  dependence now.
- **Marker linger**: when a rock spawns, its warning stays displayed on
  the arrival cell for ~8 frames (ast_pdly) while the rock crosses it,
  then the next warning pre-rolls — the marker no longer teleports to
  the next edge at the exact spawn frame.
- **Tests**: all four marker/spawn tests pinned to the new cells
  ((100,24) / (120,176) markers; spawns 27/174 after first move).
- **Verified live**: captures show the top marker at row ~3 and the rock
  descending exactly from it; level-5 cycles running.
- **Commits:** (this change set)

---
## 2026-08-26 · asteroid edge classification fixed (root cause, finally)

- **What:** Edges are now classified by the ANGLE GROUP INDEX, not sign
  tests.  The 32-entry ast_angles table is grouped 0-7 bottom, 8-15
  top, 16-23 right, 24-31 left — but the old classifier routed
  diagonals by dy/dx signs, so a down-left TOP-angle (dx=-1/-2, e.g.
  the (255,2)/(254,2) entries) fell into the RIGHT-edge branch:
  warning+spawn landed at X=230 in the DMZ while the rock flew
  down-left, top warnings went missing for those picks, and several
  horizontal-group angles with dy≠0 misrouted to top/bottom.  This is
  the source of the recurring "markers in the DMZ / wrong edges /
  shifted" complaints across all previous coordinate tuning — the
  coordinates were fine once grouped correctly.
- **Fix:** ast_preview and ast_spawn both classify by group index
  (TXA/LSR + CMP #8/#16/#24) — one rule everywhere.  Byte-verified in
  the assembled PRG ($1853 spawn, $19CC preview): ladders + the exact
  entry constants (dir 0/210, 1/16, 2/230, 3/24).
- **Also re-confirmed:** marker = exact warn cell for all edges; entry
  points fully visible (top 16, bottom 210, right 230, left 24);
  despawn direction guard in the binary; sound presets anchored post
  sprite data.
- **Tests:** existing poke-driven marker/spawn tests pass; live level-5
  observation shows right-edge warning+rock at the same cell.
- **Commits:** (this change set)

---
## 2026-08-26 · radar marker = exact entry point; top rocks enter at the border

- **What:** Asteroid entry points now match the radar warning exactly.
  Top rocks spawn flush with the top border (Y=110 → Y=0, entering
  downward right under the HUD row) instead of popping in at mid-field;
  side entries clamp to the visible band (Y 50-190, was 50-229 — rocks
  could previously enter below the screen and stay invisible); and
  radar_do positions the marker at the rock's ENTRY POINT on the
  visible screen: (warn_x, warn_y) clamped into the band Y=10..190 —
  below the HUD row, above the bottom overflow.  The raw spawn coords
  sit at/behind the edges by design (top Y=0 arrives over the HUD,
  bottom Y=210 climbs in from below), so a marker pinned to them sat
  ON the HUD text or off-screen.  The old per-edge pins (top Y=59,
  bottom Y=229, right X=230) drifted 19-51 px from the real entry —
  the "rock appears in front of the radar" bug (the top spawn was
  moved 50→110 in d9cd3d9 without moving the radar pin).
- **Also:** the despawn Y<10 sweep is now gated on direction (dy<0
  only) — top rocks entering at Y=0 would otherwise be killed by their
  own first movement step.
- **Why:** rocks visibly materialised ahead of their radar marker,
  breaking the warning's purpose; top entries appeared mid-field.
- **Tests:** radar_marker_matches_warn_top,
  radar_marker_bottom_clamped_to_entry_band,
  top_spawn_enters_flush_and_survives,
  bottom_spawn_enters_below_screen (poke-driven, deterministic).
- **Commits:** (this change set)

---
## 2026-08-26 · SPACE = keyboard fire; cheat keys removed; cracked-loader level select

- **What:** The SPACE-bar level-cycle cheat (`cheat_keys` + `chk_sid` +
  `CHEAT_KEYS`) is gone, and keyboard fire is now SPACE across the board
  (powerup trigger — LEFT SHIFT retired).  Level select ships as a
  cracked-loader screen: **M** on the splash opens it (white border,
  "***** start level *****", ">" marker); digits 1-5 jump straight to a
  level, joystick up/down + fire/SPACE confirm, F1 backs out.  Starting
  at level n applies its speed, threshold score (256/512/1024/1536) and
  enemy colour via `do_init` consuming `start_level` — no charge/life
  awards (transition-only).  Game-over restart always resets to level 1.
- **Framework fix (the actual crash):** sound_presets emitted linearly
  after game_logic — once game_logic grew past ~$3024 the section
  crossed $3400 and `_emit_sprite_data` overwrote the running sound
  code; `sfx_tick_all` became sprite bytes (`BRK` → READY., the
  "SYS2061" symptom).  `_emit_sound_presets` now anchors the section at
  `memory.sound_presets` (default $3900, dodge: $3900; ~$400 bytes,
  overflow-guarded) above all sprite data.
- **Loader hardening (lessons from the first cut):** menu strings typed
  in lowercase (`!scr` stores bytes as typed — uppercase renders as
  graphics garbage in this charset); loader entry on **M** (matrix
  line 4) — line 0 is RETURN's line and the harness types "sys2061\r"
  at boot, so a line-0 scan ate the CR; menu input runs edge detection
  with an arming frame (`menu_prev`/`menu_armed`) so floating or stuck
  joystick lines can't phantom-confirm a level; branch trampolines where
  the grew block outgrew beq range.
- **Verified:** deterministic VICE-monitor boot (`g 080D`), loader screen
  drawn and stable through an 8s phantom-input soak (state stays 3),
  level-plumbing poke test (start_level=5 → level 5, speed 179, score
  $0600, playing), static 6/6, spec check PASS.
- **Commits:** (this change set)

---
---
---


## 2026-08-26 · splash title glyphs: Orbitron, distinct & uniform scale

- **What:** The chrome splash title "LAST STAR SYSTEM" is now rendered
  from the Orbitron variable font at weight ExtraBold (downloaded to
  `games/dodge/tools/fonts/`, plus Russo One / Audiowide / Michroma /
  Rajdhani as reviewed candidates via `title_font.py --compare`).
  Two glyph bugs fixed on the way:
  1. **Blobby, merged letters** — the 8-neighbour post-render dilation
     (+1px on a 16px letter ≈ +50% stroke fat, sealed counters) is
     dropped from the live path; each letter is downscaled from a
     large render and padded (1px gutter, 2px inter-letter spacing)
     instead of being width-fit edge-to-edge.
  2. **Letter size disparity ("SYSTEM")** — per-letter width-fit scaled
     each cap independently (Orbitron ExtraBold caps are near-square
     blocks: E 43×46, L/A/S/T/R 46×46, M 52×46, Y 53×46), making E
     taller and Y/M shorter.  `build_letters` now computes ONE shared
     scale (`_uniform_scale`: ≤13px cap height, ≤15px width) so all
     letters share a cap height with natural width variation, like the
     cover logo.
- **Why:** The `splash_stays_until_space` and boot-time screenshot
  checks all passed, but the title read as a smear rather than the
  cover's angular sci-fi letterforms; and within "SYSTEM" the Y/M/E
  visibly mismatched the rest of the title.
- **Commits:** `13b7c8b`, `2cb355f`, + this session's uniform-scale
  commit (see git log).  Assets: `assets/title_font.bin` regenerated.

## 2026-08-25 · chrome block-logo splash title + charset relocation

- **What:** The splash title "LAST STAR SYSTEM" is now drawn in chrome
  block letters (2 cols x 3 rows of custom 8x8 glyphs per letter,
  16x24 px, rows 8-10, cols 4-35) with a white/yellow/orange gradient
  via colour RAM — styled after the marketing cover.  Generator at
  `games/dodge/tools/title_font.py` (DejaVu Serif Bold → 48 glyphs →
  `assets/title_font.bin`).  The splash shimmer bars narrowed from
  cols 0-5/34-39 to 0-3/36-39 so they no longer clobber the title's
  edge colours.
- **Why:** The plain text title didn't match the game's own marketing
  cover; the cover's chrome treatment needed custom glyphs.
- **Under the hood — memory relocation (root of two bugs):** the
  charset moved from $3800 (never read by the VIC — all text came from
  the char ROM through the VIC view) to $2000, and all sprite data
  (20KB region) moved from $2000 to $3400 with new pointer constants
  ($D0/$D4/$E0/$E1).  Key truth: the VIC charset base = LOW NIBBLE of
  $D018 × $400 within the bank, so $2000 is addressable (low nibble 8).
  Config precedence trap: the codegen reads the charset from
  `c64devk.yaml`'s `screen:` section (spec.screen.charset_addr), NOT
  `memory.charset`; `spec/game.yaml`'s screen block is dead config.
  Two fixes rode along: the ship pointer `adc #$80` → `#$D0`
  (invisible ship), and the charset copy now targets $2000 so the rock
  at $3800 is no longer overwritten at boot (garbage asteroids).
- **What else:** `vice_bridge.read_memory` now chunks large dumps
  (VICE's `m` command prints a fixed window per call).
- **Commits:** *(landed together — see git log)*

## 2026-08-25 · level-5 softening + survival reward

- **What:** The level-5 asteroid spawn interval softens from 20 to 24
  frames (`level_spawns` last row), and every level-up at level 5 or
  beyond grants +1 life (capped at 9 — the HUD life counter is one
  digit).  The L5 signature stays: 3 concurrent rocks, ±3 px/frame
  speeds, pulsing red octopus.
- **Why:** The L4→L5 step stacked three difficulty levers at once
  (count, speed cap, spawn rate) — a cliff rather than a slope, and
  at the ceiling there was nothing to practice toward.  The spawn
  softening trims the on-screen rock density ~15% without touching
  the L5 signature; the life reward makes climbing at the ceiling
  pay.  Lives were never refilled before, so ceiling runs kept
  getting shorter.
- **Commits:** *(landed together — see git log)*

## 2026-08-25 · vice_bridge: visual capture (model can see the game)

- **What:** The framework can now grab the VICE video window as a PNG:
  `capture_vice_window(path, pid)` / `ViceMonitor.screenshot()` use
  python-xlib to grab the innermost video window (PID-targeted via
  xdotool, correct with multiple VICE instances open), and a new
  `c64devk shot` command (build → launch → wait → capture) wraps it.
  No external screenshot tools needed.
- **Why:** All framework verification was numeric (memory/registers);
  nothing could look at the game.  A model (or CI) can now visually
  confirm splash text, sprite art, HUD and zone rendering.
- **Commits:** *(landed together — see git log)*

## 2026-08-25 · death boom: layered explosion + border flash

- **What:** Player death now plays a 60-frame layered boom
  (`death_boom`/`boom_tick` in the extended RAM area) instead of the
  small single-voice `sfx_explosion`: voice 3 noise sweeps $18 → $7E
  with a sustain fade over the last 24 frames, voice 2 pulse
  sub-drops $04 → $40 (~240 Hz → 60 Hz), and the border flashes
  red/white at 25 Hz for the first 40 frames.  Both death paths
  trigger it (enemy collision and asteroid hit — the second handler
  was still playing the old sound).  `engine_do` yields voice 2
  while `boom_tmr > 0`; `boom_tick` is a no-op when inactive so it
  never clobbers voice-3 presets.  Sweeps are computed from the
  countdown and stored with plain STA — never INC a SID register
  (read-modify-write on write-only registers reads bus garbage on
  real hardware; VICE exposed the bug while testing).
- **Why:** The death explosion was a brief single-voice rumble with
  no impact; the game's biggest failure moment deserved the biggest
  sound.
- **Commits:** *(landed together — see git log)*

## 2026-08-25 · vice_bridge: robust monitor response parsing

- **What:** `vice_bridge` parses VICE monitor output layout-aware:
  memory dumps use per-row address arithmetic (breakpoint-stop
  preambles, disassembly lines and ASCII columns can no longer leak
  into reads); `get_register` understands the current
  `.;PC AA XX YY SP` register format with a legacy token fallback;
  all launchers resolve the PRG path to absolute (VICE's cwd is the
  ROM dir).  Parsers extracted to module-level functions with a
  pytest suite (`tests/test_vice_bridge.py`, real captured
  responses).
- **Why:** The first memory read after a breakpoint stop returned
  garbage (the `AD` opcode parsed out of the disassembly line) — it
  cost an hour of phantom bug-hunting; register reads always
  returned 0; relative PRG paths failed autostart silently.  These
  were the concrete blockers making `c64devk test` live mode
  unusable.
- **Commits:** *(landed together — see git log)*

## 2026-08-25 · level-3 asteroid colour

- **What:** Slot-0 rocks are level-coloured at spawn time: level 2
  yellow (7), level 3+ white (1).  Slots 1/2 keep their fixed
  orange/light-red so the tier progression (new colour per level) is
  preserved.  Written in `ast_spawn` so it survives the `do_init`
  re-run after each transition.
- **Why:** Level 3 played identically to level 2 (one yellow rock) —
  no sense of escalation.
- **Commits:** *(landed together — see git log)*

## 2026-08-25 · code-region headroom: splash relocation

- **What:** The splash block (do_splash / splash_wait / splash_bars /
  draw_splash, ~171 lines) relocated from the main $0801–$2000 code
  region to the extended RAM area at $2A00.  The `!if * > $2000`
  build guard now sits at the true end of the main region with
  ~243 bytes of headroom.
- **Why:** The L3 colour block pushed the code region past $2000 and
  the guard (added after the splash-text overwrite) correctly failed
  the build — proof the silent-corruption guard works.  Relocating
  once-per-boot code frees permanent headroom instead of shaving
  bytes.
- **Commits:** *(landed together — see git log)*

## 2026-08-25 · ship engine rumble + new-level coin chime

- **What:** Ship engine on SID voice 2 — noise-waveform "spaceship
  thrust" rumble whose base frequency is direction-tuned
  (`engine_freqs[player_dir]`: right mid, left deeper, up hissier,
  down deepest) and churned every frame by the framework LFSR.  Gates
  on while moving in PLAYING, off when idle/dying/transitioning.
  Level-up sound swapped from `sfx_ping` to `sfx_coin` (E-5 → A-5
  triangle chime) in both the score-threshold path and the SPACE
  cheat (`chk_sid` jmp-forward trick).  Routine lives in the extended
  RAM area ($2940).
- **Why:** The game was nearly silent and the ship made no sound at
  all; a fixed-frequency pulse read as a musical tone rather than
  thrust.
- **Commits:** `18a2760`

## 2026-08-24 · asteroid speed gate + splash text overwrite fix

- **What:** `ast_spawn` clamps both velocity components to |2|
  px/frame below level 5, reserving the ±3 speed variants for the max
  difficulty tier (covers both the random pick and the radar
  pre-rolled path).  Also fixed the splash title screen: the
  `ds_title`/`ds_press`/`ds_credit` strings had been pushed past
  $2000 by code growth and silently overwritten by `ship_r.spr`
  (the credit line rendered garbage).  Strings relocated to $2900 and
  a build-time guard added: `!if * > $2000 → !error`.
- **Why:** Level 4 spawned two fast rocks at once — a brutal
  difficulty spike; and the title screen broke after the variable
  block grew.  The guard turns a silent corruption class of bug into
  a build failure.
- **Commits:** `b135b4b`

## 2026-08-24 · movement-gated ship trail

- **What:** Ship frame 0 is the clean no-trail hull, frame 1 carries
  the exhaust trail.  `anim_update` flickers between them at 25 Hz
  only while `state == PLAYING` and `player_moving` — a flag set by
  position-delta detection (`prev_x`/`prev_y` vs $D000/$D001) at the
  end of `keyboard_read`.  Stationary (or outside PLAYING) freezes
  the sprite on frame 0 and the trail is completely hidden.
- **Why:** The trail flickered even while parked, which looked wrong;
  it should read as translucent exhaust only while flying.
- **Commits:** `3566cb0`

## 2026-08-23 · hand-drawn sprite animation

- **What:** Ship gets 4 hand-drawn frame-1 sprites (blocks $85–$88,
  2-frame cycle) and the enemy becomes an 8-block octopus with a
  hand-drawn 7-frame tentacle cycle (blocks $89–$8E, historical
  `skull*` filenames).  Rock/radar relocate to blocks $90/$91.
  `tools/sprtool.py` added: byte-perfect `.spr` ↔ animated GIF round
  trip for LibreSprite at native 24×21 resolution, plus an ASCII
  `render` preview.
- **Why:** The ship and enemy were static; the framework needed an
  artist-friendly edit loop for sprite frames.
- **Commits:** `96e09c7`

## 2026-08-18 · uncap level counter

- **What:** HUD and transition screens display levels 6+ as 2-digit
  numbers; the difficulty tier itself still caps at 5.
- **Why:** Leveling past 5 showed garbage in the HUD.
- **Commits:** `58f8cc9`

## 2026-08-18 · fire-triggered invincibility powerup

- **What:** At level 3+ the player gains a fire-triggered
  invincibility charge (2 seconds of flashing immunity, LEFT SHIFT
  also works); unified invincibility flash handling; level clamped
  at 5 for difficulty.
- **Why:** High levels needed a defensive tool beyond dodging.
- **Commits:** `f52c519`

## 2026-08-17 · SPRITE_SPECS.md

- **What:** Pixel-art specs for the alternate animation frames —
  design direction, block map, export workflow.
- **Why:** The animation plan needed to be written down before art
  was made (spec-first workflow).
- **Commits:** `f13c581`

## 2026-08-08 · sprite animation cycling

- **What:** 2-frame ship + 4-frame enemy animation cycling in
  `anim_update` (reusing the same art as placeholders);
  `ROADMAP.md` with alt-frame TODOs; rock sprite moved to block C,
  radar to block D.
- **Why:** Establish the animation plumbing so artists only need to
  drop in frame files later.
- **Commits:** `6fce297`

## 2026-08-08 · joystick fire restart + D64 generation

- **What:** Joystick fire restarts from game over; build auto-generates
  a `.d64`; transition score/colour fix.
- **Why:** Restart required the keyboard; floppy-image builds ease
  real-hardware testing.
- **Commits:** `a399e92`

## 2026-08-07 · level transition screen + game over simplification

- **What:** Dedicated 90-frame level-transition screen (countdown,
  position reset, asteroid clear); game-over flow simplified.
- **Why:** Level-ups were invisible; the game-over state machine was
  convoluted.
- **Commits:** `1facce4` (cleanup of stray backups: `9399b0f`)

## 2026-08-06 · ASSEMBLY.md

- **What:** 6502 technique reference and architecture walkthrough of
  the dodge codebase; AGENTS.md notes it must be maintained alongside
  routine changes.
- **Why:** Knowledge transfer — the assembly patterns were only in
  the code.
- **Commits:** `e07fbd2`, `43f18ce`

## 2026-08-05 · enemy colour pulse at level 5+

- **What:** Enemy sprite colour pulsates red ↔ light red every 8
  frames at level 5+; Y bounds raised to 58 to clear the HUD.
- **Why:** Max difficulty needed a visual threat indicator.
- **Commits:** `260185a`

## 2026-08-05 · Atari-style sound presets

- **What:** Sound preset library (zap, explode, drone, ping, plus
  coin/alarm/laser/powerup); `sfx_explosion` for death; `sfx_ping`
  fix so both notes play; radar boop; `sfx_tick_all` in the main
  loop; master volume fixes.
- **Why:** The game had no audio at all; presets give Atari-2600
  character with raw SID gating.
- **Commits:** `af4dc9e`

## 2026-08-05 · sprite art refresh

- **What:** New ship design (all 4 directions from Spritemate) and
  skull redesign; radar top-edge Y fix; score zone recoloured blue;
  HUD row black.
- **Why:** Placeholder blocks didn't read as a ship/skull.
- **Commits:** `3f6b0d5`, `d9cd3d9`

## 2026-08-05 · framework check + constraints

- **What:** `c64devk check` validation command; per-project
  `constraints.max_game_logic_lines`; sound-demo fixes.
- **Why:** Enforce spec consistency and code-size discipline before
  committing.
- **Commits:** `d6e038c`, `0bf6f29`

## 2026-08-05 · joystick port 2 + fractional speed

- **What:** Joystick port 2 support, fractional-speed enemy movement,
  zone scoring tick improvements.
- **Why:** Keyboard-only control and integer pixel steps limited feel
  and tuning.
- **Commits:** `18ca7b7`

## 2026-08-04 · framework DSL: sprite control actions

- **What:** `enable_sprite`/`disable_sprite` actions, `on_timer`
  trigger, collision cooldown, `NEXT_FREE_SPRITE` constant, zero-page
  map documentation.
- **Why:** Routine code was needed for things the DSL should express.
- **Commits:** `906e81d`

## 2026-08-04 · framework DSL: RNG + variable positioning

- **What:** Independent `random` LFSR variable; branch-distance tips
  on ACME "target out of range" errors; `set_sprite_pos` variable
  support.
- **Why:** RNG shared with other systems caused visual coupling;
  variable references made radar positioning possible.
- **Commits:** `72702f1`

## 2026-08-04 · radar warning indicator

- **What:** Sprite-based radar indicator at screen edges previewing
  the next asteroid spawn; right-edge despawn bug fix; right-edge
  radar at X=230 outside the DMZ.
- **Why:** Off-screen asteroid spawns felt unfair with no warning.
- **Commits:** `32c0d7b`, `e75fb04`

## 2026-08-03 · splash shimmer bars + own frame loop

- **What:** Splash screen runs its own frame loop (bypassing
  `behaviors_update` — no HUD flicker, no DMZ fight); DMZ-style
  shimmer side bars with black centre.
- **Why:** The splash fought the main loop and the DMZ system for
  the frame and the screen.
- **Commits:** `4ec9f06`, `fa23c24`

## 2026-08-03 · test runner crash detection

- **What:** Automatic crash detection after each frame advance in the
  live test runner.
- **Why:** Hangs hid crashes in live VICE tests.
- **Commits:** `e5ea310`

## 2026-08-03 · IRQ handler + memory corruption fixes

- **What:** Correct IRQ handler chaining into the KERNAL; splash,
  asteroid, and memory-corruption fixes (a custom handler replaced
  `JMP $EA31`, which had been corrupting KERNAL zero-page).
- **Why:** Random crashes and corruption traced to the IRQ path.
- **Commits:** `76738e8`, `a08caa7`, `4781fb4`

## 2026-08-01 · splash screen

- **What:** "LAST STAR SYSTEM" splash with SPACE-to-start; spec and
  design updated.
- **Why:** The game dropped straight into play with no title state.
- **Commits:** `751150f`

## 2026-08-01 · asteroid systems backup

- **What:** Asteroids + levels + DMZ protection + cheat keys landed
  as a consolidated state; directional sprites, VICE fixes, and the
  DMZ safe zone backed up.
- **Why:** Fast-moving multi-system work needed checkpoints.
- **Commits:** `e3a499e`, `6dfa1d3`

## 2026-08-01 · DESIGN.md rewrite + edge-spawning asteroids

- **What:** DESIGN.md rewritten as the full mechanics document;
  LFSR seeded from the raster line; asteroids spawn from all four
  edges.
- **Why:** The design doc had drifted from the game; fixed-seed RNG
  made runs repetitive.
- **Commits:** `587b475`

## 2026-08-01 · crash fixes: c_saved + LFSR + collision state

- **What:** Clear `c_saved` each frame, LFSR anti-stick guard,
  `ast_collision` state check.
- **Why:** Intermittent crashes from stale collision state and stuck
  RNG.
- **Commits:** `119a2b3`

## 2026-08-01 · SESSION.md + spec comment updates

- **What:** SESSION.md (full project state for the next session);
  spec comments corrected (charset copy by framework, HUD via DSL,
  test notes).
- **Why:** Handoff across sessions kept losing context.
- **Commits:** `a7a830f`, `42a6198`

## 2026-08-01 · HUD via behaviour DSL

- **What:** Manual HUD replaced with `display_text` +
  `display_number` DSL actions; crash fixes for `!scr` data executed
  as code (BRK $00) and a charset-copy branch offset; HUD spacing
  and lowercase PETSCII fixes.
- **Why:** Hand-rolled screen text was fragile (three separate
  crash classes) and the DSL should own text rendering.
- **Commits:** `d29a7cb`, `dbe3b73`, `69052ca`, `f4bf370`, `e179e0b`,
  `dcadda0`, `34b4826`

## 2026-08-01 · c64devk setup command

- **What:** `c64devk setup` — one-command dependency installer
  (ACME, VICE ROMs, PATH).
- **Why:** Manual toolchain setup was error-prone across machines.
- **Commits:** `5257f25`, `bd668b0`

## 2026-08-01 · roadmap + repo hygiene

- **What:** ROADMAP.md deduplicated with done items marked; an
  accidentally committed test project removed.
- **Why:** The roadmap had rotted; repo should not ship scratch.
- **Commits:** `0620295`, `3ac99d0`

## 2026-07-31 · spec tutorial + workflow docs

- **What:** Spec writing tutorial and spec-driven workflow docs.
- **Why:** The framework's central idea needed teaching material.
- **Commits:** `17e34f2`

## 2026-07-31 · shaped sprites + pointer fixes

- **What:** Diamond (player) and skull (enemy) sprite data, assets
  copied to the build; per-sprite data blocks; enemy MSB cleared so
  it cannot enter the safe zone.
- **Why:** Placeholder squares were unreadable; shared data blocks
  made sprites show each other's art.
- **Commits:** `b22517b`, `0cc18d9`, `18e1e7e`, `b19dfe1`

## 2026-07-31 · DESIGN.md + MIT license

- **What:** DESIGN.md as the single source of truth for mechanics;
  MIT license.
- **Why:** Mechanics lived only in code comments.
- **Commits:** `f3f3f64`, `d1c38b8`

## 2026-07-31 · three-zone scoring system

- **What:** Green score zone (+2), black neutral (0), blue safe/DMZ
  zone (score immunity, −5 entry penalty, floor 0); 9-bit X zone
  checks, solid-block zone colours, restart fix.
- **Why:** Risk/reward scoring: camping the safe zone should cost
  points, dodging in the green should pay.
- **Commits:** `1432b84`, `282a63d`, `2679b43`, `7fd0f07`, `bcdc838`,
  `337753b`, `77971b0`, `0a57426`, `764223a`

## 2026-07-31 · 9-bit X positioning + bounds

- **What:** X positioning past 255 via $D010 MSB, visible border,
  right bound raised to 255, bounded direct movement preventing wrap;
  longer invincibility with smart enemy respawn on collision.
- **Why:** The playfield should use the full sprite X range; edge
  wrap and unfair respawns felt broken.
- **Commits:** `1165065`, `0d43b6f`, `64e1bc5`, `c8c3272`

## 2026-07-31 · Survival Dodge gameplay

- **What:** Lives, on-screen text, game over, restart; restart resets
  position + invincibility; SPACE bar matrix fix; enemy visibility
  and reposition fixes.
- **Why:** The demo had no fail state — a game needs one.
- **Commits:** `74d8df9`, `ec3d421`, `a9d0a60`, `1984f03`

## 2026-07-31 · screen + keyboard fixes

- **What:** ROM charset copied to RAM at $3800 with bank 0; A/D
  keyboard matrix offsets corrected (were reading R and 6).
- **Why:** Text showed garbage and WASD was half-broken.
- **Commits:** `44ddb1b`, `d3d0c28`

## 2026-07-31 · WASD controls + game_logic structure

- **What:** WASD keyboard controls; all game logic consolidated in
  `routines/game_logic.acme`; crash fix for inline data executed as
  code; C64 code-pattern recipes added to SKILL.md.
- **Why:** Joystick-only input and scattered logic; data-as-code was
  crashing the 6502.
- **Commits:** `b2a597e`, `cc81a9a`, `a1a0f8d`, `44a85eb`

## 2026-07-31 · VICE autostart reliability

- **What:** Autostart saga: mode 1 RAM injection, then .d64 images,
  `-autostart-warp`, virtual-device modes, and finally mode 1 +
  `keybuf SYS<addr>` with `\r` (CR) return key, init address computed
  from the PRG.
- **Why:** Programs loaded but didn't RUN under VICE; each approach
  fixed one layer (drive emulation, key injection, line endings).
- **Commits:** `2aa6ed2`, `769e7fe`, `95eacce`, `5e4287b`, `1ce5279`,
  `1ac0bb4`, `5164b47`, `48ce6c3`

## 2026-07-31 · C64DevKit v0.1.0

- **What:** Initial framework: YAML specs → ACME assembly → `.prg`;
  VICE launch with ROM setup; the Sprite Dodge example game.
- **Why:** Spec-driven C64 development — the founding idea.
- **Commits:** `e6574a7`, `e088771`
