# Sprite Dodge — Assembly Reference

A technical walkthrough of the 6502 assembly techniques used in the dodge game.
All code lives in `routines/game_logic.acme` (~2200 lines).  This document extracts
the reusable patterns and explains the architecture.

---

## File Layout & Memory

```
Lines 1–4     Comment header
Line 5         jmp gstart          ← skip variable data
Lines 8–70     !byte variables     ← 49 game-state variables (incl. start_level)
Lines 69–73    Constants (GAME_PLAYING=0, GAME_DYING=1, GAME_OVER=2, GAME_SPLASH=3, GAME_TRANSITION=4)
Lines 76–189   gstart:             ← frame dispatcher (jsr chain + state switch)
Lines 212–385  init_once / do_init ← one-shot screen setup
Lines 390–477  do_play + pwr_check ← PLAYING state + fire/shift powerup trigger (after collisions)
Lines 478–508  do_die:             ← DYING state (flash + timer; pwr_key edge-resync at respawn)
Lines 508–629  do_over:            ← GAME_OVER state (draw + wait; fire → splash via release gate)
Lines 630–750  restart:            ← reset all state on replay (level/speed/score → level 1 fresh start)
Lines 751–937  keyboard_read:      ← WASD keyboard scan + joystick port 2
Lines 938–1032 enemy_do:           ← enemy chase AI
Lines 1033–1105 score_do:          ← zone-based scoring
Lines 1106–1199 collision_do:      ← player–enemy collision
Lines 1200–1328 do_transition:     ← "LEVEL X" screen (1–2 digit display)
Lines 1329–1343 sound_tick:        ← legacy sound timer
Lines 1344–1413 level_update:      ← level thresholds (every 256 pts, uncapped counter)
Lines 1414–1426 ast_angles:        ← 32-entry spawn direction table (+ rock_ptrs)
Lines 1427–1720 ast_spawn:         ← asteroid spawning (consumes one pre-rolled warning)
Lines 1721–1726 ast_tmp:           ← spawn scratch vars
Lines 1727–1827 ast_preview:       ← next-spawn position pre-roll
Lines 1828–2033 ast_update:        ← marker-linger tick, spawn timer, movement + despawn
Lines 2034–2065 ast_update tail:   ← rock-rotation tick + per-slot pointer loop + $D015 sync
Lines 2066–2165 ast_collision:     ← player–asteroid collision
Lines 2166–2218 radar_do:          ← radar warning indicator (linger-aware)
Lines 2219–2230 lfsr_tick:         ← Galois LFSR RNG
Lines 2231–2259 dmz_init:          ← DMZ colour RAM init fill
Lines 2260–2296 dmz_do:            ← DMZ per-frame static refresh
Lines 2297–2482 d_mul40 + splash preamble: ← row × 40 multiply, splash block kickoff ($2A00)
Lines 2483–2587 do_splash/splash_wait: ← title screen (owns the frame loop)
Lines 2588–3117 menu_wait / loader_draw / menu_puts / menu_marker ← cracked level-select loader + splash_bars/draw_splash
Lines 3118+     title_load + sound data + rock/radar sprite data
```

---

## Core 6502 Patterns

### 1. Fractional Speed Accumulator

Used by the enemy AI to move at sub-pixel rates.  The accumulator
builds up a fraction each frame; movement only happens when it
overflows (carry set).

```asm
speed_frac: !byte 128   ; 128/256 × 50 fps = 25 px/s
speed_ctr:  !byte 0     ; fractional accumulator

e_active:
    clc
    lda speed_ctr
    adc speed_frac       ; add fraction each frame
    sta speed_ctr
    bcc e_done           ; no carry = skip movement this frame

    ;; carry set → move one pixel
    lda $d000            ; player X
    cmp enemy_x
    beq e_chy            ; equal → skip X move
    bcc e_ml             ; player left of enemy → move enemy left
    inc enemy_x          ; player right of enemy → move enemy right
    jmp e_chy
e_ml:
    dec enemy_x
```

**Why it works**:  `128 + 128 = 256 → carry` every other frame (level 1–3).
At level 5 (`speed_frac = 179`): `179 → 358 → 537 → 716 → ...` more carries
per cycle → faster movement.  No floating-point needed.

---

### 2. Distance Gate (Collision Filtering)

The VIC-II `$D01E` collision register fires on ANY pixel-line overlap, even when
visible shapes are far apart.  A distance gate rejects false positives by
requiring sprites to be within 18 pixels.

```asm
    ;; abs(player_X − enemy_X) < 18
    lda $d000            ; player X
    sec
    sbc $d002            ; subtract enemy X
    bcs .dx_ok           ; if result >= 0, skip negation
    eor #$FF             ; abs = −result  (two's complement invert)
    adc #1               ;               +1
.dx_ok:
    cmp #18
    bcs c_no             ; too far → no collision

    ;; same check for Y
    lda $d001
    sec
    sbc $d003
    bcs .dy_ok
    eor #$FF
    adc #1
.dy_ok:
    cmp #18
    bcs c_no

    ;; both axes < 18 → real collision
```

**Key detail**:  The `eor #$FF / adc #1` is 8-bit two's complement negation
(equivalent to `−A`).  Works because a 6502 `sbc` with the carry set from `sec`
produces the correct result; `eor #$FF` toggles all bits, `adc #1` adds the +1
that completes two's complement.

---

### 3. 9-Bit X Positioning ($D010 MSB)

Sprites can have X positions 0–511.  The low 8 bits go in `$D000/$D002/…`,
the high bit (MSB) goes in a separate register `$D010` — one bit per sprite.

```asm
    ;; Move player right
    lda $d000
    cmp #255             ; about to overflow?
    bne .inc_right
    inc $d000            ; X = 0, MSB now set
    lda $d010
    ora #$01             ; set bit 0 (sprite 0 MSB)
    sta $d010
    jmp kdone
.inc_right:
    inc $d000

    ;; Move player left
    lda $d000
    bne .dec_left
    lda $d010
    and #$01             ; MSB set?
    beq k3               ; no → at left edge, stop
    dec $d010            ; clear MSB
    dec $d000            ; X = 255
    jmp k3
.dec_left:
    dec $d000
```

**For asteroids**: three software MSB bits in `ast_msb` variable, synced to
`$D010` bits 2–4 each frame in `ast_update`.  The asteroid system tracks
X entirely in software (`ast_x[3]`) with `ast_msb` for the overflow bit.

---

### 4. Edge Detection (Press vs Hold)

Reads the keyboard or joystick and detects the *transition* from not-pressed
to pressed — avoids re-triggering every frame while held.

```asm
fire_was:   !byte $10    ; $10 = was not pressed

    ;; Read joystick fire (active low)
    lda #$00
    sta $dc02             ; port A = all inputs
    lda $dc00
    and #$10              ; bit 4 = fire (0 = pressed)
    tax
    lda #$ff
    sta $dc02             ; restore keyboard mode

    txa
    beq in_down           ; fire pressed → check edge

    ;; Not pressed → reset state
    lda #1
    sta btn_was
    jmp main

in_down:
    lda btn_was           ; was it already pressed?
    beq main              ; yes → ignore (hold, not edge)
    ;; Fresh press detected
    lda #0
    sta btn_was
    ;; → trigger action
```

The dodge game uses this pattern in three places:
- `pwr_check` — fire/SPACE keyboard-fire edge (`pwr_key`)
- Sound demo — preset cycling (`btn_was`)
- Radar ping — indicator appears (`radar_was`)

---

### 5. Galois 8-Bit LFSR (Random Number Generator)

Fast, deterministic, zero-page-free PRNG.  Each call advances the seed by
one step.  The polynomial `$2D` gives a maximum-length sequence (255 states).

```asm
dmz_seed:   !byte $5A     ; LFSR state (never zero)

lfsr_tick:
    lda dmz_seed
    lsr                    ; shift right, bit 0 → carry
    bcc d_noe              ; if carry clear, skip XOR
    eor #$2D               ; polynomial feedback
d_noe:
    sta dmz_seed
    bne d_done             ; result must never be zero
    lda #$5A               ; recover from terminal state
    sta dmz_seed
d_done:
    rts
```

Uses:
- DMZ colour static — random colour per cell every 3rd frame
- Asteroid spawn — random edge position (mask to range)
- Asteroid direction — random angle from ast_angles table
- Splash bar shimmer — LFSR for side-bar colours

**Generating a bounded random value** (e.g. 40–167):
```asm
    jsr lfsr_tick
    and #$7F               ; 0–127
    clc
    adc #40                ; 40–167
    sta ast_warn_x         ; pre-rolled spawn X
```

The `and` mask gets a power-of-2 range, then `adc` shifts the window.
Works for any range where the mask size is a power of 2.

---

### 6. Indirect Jump with Return (Sound Dispatch)

The sound demo uses a jump table to call presets by index.  A bare `jmp (ptr)`
would lose the return path — the fix pushes a return address first.

```asm
jtbl:
    !word sfx_beep, sfx_boop, sfx_coin, sfx_hit
    !word sfx_explosion, sfx_alarm, sfx_laser, sfx_powerup

    ;; dispatch by preset_idx
    lda preset_idx
    asl
    tax
    lda jtbl, x           ; address lo
    sta jptr
    lda jtbl+1, x         ; address hi
    sta jptr+1

    ;; Push return address, then jump
    lda #>sound_done
    pha
    lda #<sound_done
    pha
    jmp (jptr)             ; preset's RTS returns to sound_done

sound_done:
    jmp main
```

The CPU pushes high byte first, then low.  `RTS` pops low then high and
adds 1 (because `JSR` pushes `PC−1`).  Pushing the exact target address works
because `RTS` pulls the address and jumps to `addr+1`.  Since we pushed
`sound_done−1`?  No — we pushed the exact address.  `RTS` increments the
popped PC by 1 automatically.  This is standard 6502 trickery: push
`(target−1)` for RTS to land on `target`.  **If the preset returns to the wrong
address, the pushed value needs `−1`**.

---

### 7. State Machine Dispatch

The main frame dispatcher (`gstart:`) routes execution to one of four
state handlers.  A `cmp / bne / jmp` chain is the standard C64 pattern.

```asm
    lda state
    cmp #GAME_SPLASH
    bne g0
    jmp do_splash         ; splash owns its own frame loop
g0:
    ;; ... input, AI, scoring, radar ... (runs for all non-splash states)
    lda state
    cmp #GAME_PLAYING
    bne g1
    jmp do_play
g1:
    cmp #GAME_DYING
    bne g2
    jmp do_die
g2:
    cmp #GAME_OVER
    bne gdone
    jmp do_over
gdone:
    rts
```

**Why `jmp` not `jsr`**:  The handlers (`do_play`, `do_die`, etc.) all end with
`rts`.  Using `jmp` means their `rts` returns directly to the caller of
`game_logic` (the framework main loop).  If `jsr` were used, the handler
would return to `gstart` which would return to `game_logic` — one extra
frame of indirection.  The `jmp` keeps the stack depth constant.

---

## Subsystem Walkthroughs

### Player Input (`keyboard_read`)

**Both keyboard and joystick are active simultaneously.**  There's no
exclusive mode — moving with WASD then grabbing the joystick just works.

**Keyboard scan** uses CIA1 column-write / row-read:
```asm
    ;; W (UP): column 1 ($FD), row 1 ($02)
    lda #$fd
    sta $dc00             ; pull column 1 low
    lda $dc01             ; read rows
    and #$02              ; row 1 = W key
    bne k1                ; not pressed → next check

    ;; W pressed → move up
    lda $d001             ; player Y
    cmp #58               ; upper bound
    bcc k1
    dec $d001
    lda #2
    sta player_dir        ; update directional sprite
```

**Joystick port 2** switches CIA port A to input mode:
```asm
    lda #$00
    sta $dc02             ; port A = all inputs
    lda $dc00             ; read joystick state (active low)
    eor #$ff              ; invert → active high
    tax                   ; save
    lda #$ff
    sta $dc02             ; restore keyboard mode
    ;; now test bits 0–3 (UP/DOWN/LEFT/RIGHT)
```

The joystick check mirrors the keyboard checks — same bounds, same `player_dir`
updates, same `$D010` handling.

**Directional sprites**: `player_dir` (0=right, 1=left, 2=up, 3=down) selects
one of four 64-byte sprite data blocks.  The sprite pointer at `$07F8` is set:
```asm
    lda player_dir
    clc
    adc #$80              ; base pointer for sprite 0 ($2000/64 = $80)
    sta $07F8
```
The framework's `data_files` system places the four `.spr` files consecutively
at `$2000`, `$2040`, `$2080`, `$20C0` — so `$80 + dir` maps to the correct block.

---

### Enemy AI (`enemy_do`)

Chases the player at fractional speed.  Uses software X/Y variables
(`enemy_x`, `enemy_y`) for sub-pixel precision; writes to VIC registers
on movement frames only.

**Colour pulsation** at level 5+:
```asm
    lda level
    cmp #5
    bcc .no_pulse
    inc pulse_ctr
    lda pulse_ctr
    and #$08             ; bit 3 toggles every 8 frames
    beq .red
    lda #10              ; light red
    bne .p_set
.red:
    lda #2               ; red
.p_set:
    sta $D028
```

**Movement** happens only when the speed accumulator overflows.
The enemy compares its software position to the player's **VIC
register** position (not the software variable — the player writes
directly to `$D000/$D001`):
```asm
    lda $d000            ; player's hardware X
    cmp enemy_x          ; enemy's software X
    beq e_chy            ; aligned → no X move
    bcc e_ml             ; player left → move enemy left
    inc enemy_x
    jmp e_chy
e_ml:
    dec enemy_x
```
After X and Y moves, the enemy clamps to visible bounds and writes
to `$D002/$D003`.

**Why software variables**:  The fractional speed system skips frames — if
`enemy_x` were read from `$D002`, the intermediate accumulator state
would be lost between frames.  Software variables persist across all frames.

---

### Collision (`collision_do` + `ast_collision`)

Three layers of protection against false positives:

1. **DMZ immunity**: player at X ≥ 224 (or MSB set) → no collision
2. **Cooldown timer**: `hit_timer` prevents re-triggering for 150 frames
3. **Distance gate**: hardware collision is ignored if sprites are >18 px apart

The collision register is read once and saved to `c_saved`:
```asm
    lda $d01e
    sta c_saved           ; save — VIC auto-clears on next write
    and #$02              ; sprite 0 vs sprite 1
    beq c_no              ; no collision
```

Then `ast_collision` (called in the same frame) reuses `c_saved`:
```asm
    lda c_saved
    and #$1C              ; sprite 0 vs sprites 2/3/4
    beq .ac_done
```

**Death response**: decrements lives, respawns enemy opposite the player,
plays `sfx_explosion`, transitions to `GAME_DYING`.

**Respawn logic** — enemy appears on the far side from the player:
```asm
    lda $d000             ; player X
    cmp #128
    bcc .spawn_right      ; player on left → enemy spawns right
    lda #50               ; player on right → enemy spawns left
    jmp .spawn_x
.spawn_right:
    lda #200
.spawn_x:
    sta enemy_x
```

---

### Scoring (`score_do`)

Three-zone system determined by player X position:

| Zone | X range | Behaviour |
|------|---------|-----------|
| DMZ | ≥ 224 or MSB=1 | −5 on entry, no score |
| Neutral | 128–223 | No score |
| Score | 24–127 | Tiered every 20 frames |

**DMZ entry tracking** uses `last_safe` — on first frame the player is
in the DMZ while `last_safe==0`, apply the penalty and set `last_safe=1`.
On leaving, `last_safe=0` rearms the penalty.

**Tiered score rates** (`zone_ticks` tracks consecutive score-zone frames):
```asm
    inc zone_ticks
    lda zone_ticks
    cmp #38              ; 38+ ticks → +5/frame
    bcs .pts5
    cmp #13              ; 13–37 ticks → +3/frame
    bcs .pts3
    lda #2               ; 0–12 ticks → +2/frame
    bne .add
```

**Why `cmp` ranges**:  `cmp #38; bcs` means "if zone_ticks ≥ 38."  Then
`cmp #13; bcs` means "if zone_ticks ≥ 13 (and we already know < 38)."
The fallthrough gives +2 for 0–12.  This is the standard 6502 range
pattern — branch on the high cut first, then work down.

---

### Asteroid System (`ast_spawn` + `ast_update` + `ast_preview`)

Three independent sprites (indices 2–4) managed by bitmask `ast_active`.

**Spawn direction table** (`ast_angles`): 32 signed-byte (dx, dy) pairs
covering four directions, each with multiple speed variants.
Picked by XOR-ing CIA timer with raster line for initial randomness,
then LFSR for per-cell variation.

```asm
    ;; Random angle selection
    lda $dc04
    eor $d012             ; CIA timer XOR raster = good entropy
    and #$1F              ; 32 entries in table
    asl                   ; ×2 for (dx, dy) pair
    tax
    lda ast_angles, x     ; dx
    sta ast_vx
    lda ast_angles+1, x   ; dy
    sta ast_vy
```

**Edge determination** is grouped by ANGLE GROUP INDEX (0-7 bottom,
8-15 top, 16-23 right, 24-31 left), so `ast_spawn` and `ast_preview`
share ONE rule and a pre-rolled angle always warns on the edge it
spawns from.  The warn cell is the marker cell; for BOTTOM/LEFT/RIGHT
it is also the spawn cell, but TOP rocks materialise 10 px BEHIND it
(Y=50, `ast_spawn` subtracts 10 from `ast_warn_y` when
`ast_warn_dir == 1`) so the rock crosses the marker instead of popping
in on it.  Example (bottom edge):

```asm
    lda #228              ; bottom edge Y (row 22)
    sta ast_tmp
    jsr lfsr_tick
    and #$7F
    adc #40               ; random X 40–167
    sta ast_tmp2
```

**Movement** uses signed 8-bit addition with MSB tracking:
```asm
    ;; Move X (signed)
    lda ast_dx, x
    bmi .dx_neg           ; negative dx → dec with MSB clear
    clc
    lda ast_x, x
    adc ast_dx, x
    sta ast_x, x
    bcc .no_msb           ; no carry → X < 256
    lda ast_msb
    ora #$01              ; set MSB bit for this slot
    sta ast_msb
```

**Despawn**: asteroid leaves when Y < 10, Y > 235, or X < 8.
Right-edge despawn happens via Y bounds (dy ≠ 0) or X underflow
(asteroid reaches X < 8 moving left with dy = 0).

**Preview/radar**: `ast_preview` pre-computes the NEXT asteroid's spawn
position and stores it in `ast_warn_x`, `ast_warn_y`, `ast_warn_dir`.
The radar sprite reads these to show the warning indicator.
The post-spawn pre-roll in `ast_update` is gated on `level >= 2`:
level 1 has no asteroids (ast_spawn returns early), so it never rolls
a warning and the radar stays parked off-screen at (0, 250).

**Warning consumption (one rock per marker)**: on spawn, `ast_spawn`
uses the pre-rolled values if `ast_warn_dir != 255`, then immediately
CONSUMES the warning (`ast_warn_dir = 255`) and claims the marker
linger (`ast_pdly = 8`).  `ast_update` ticks the linger once per frame
— never once per spawn — and re-pre-rolls a fresh warning when it hits
0.  `radar_do` keeps the crosshair on the consumed cell while the rock
crosses it, then it jumps to the next cell.  This decouples the
visual warning from the spawn timing AND ensures each pre-roll feeds
exactly one spawn: rocks can never share a marker cell or velocity.
(Earlier revisions left the pre-roll in place and ticked the linger
per spawn — up to 8 rocks poured out of the same marker on every
level with asteroids.)

Example (consume + claim in `ast_spawn`):
```asm
    lda #255
    sta ast_warn_dir      ; warn once used — never reused
    lda #8
    sta ast_pdly          ; marker lingers on this cell 8 frames
```

**Rock rotation (3-frame tumble)**: every rock spins while it flies.
Two extra frames (`rock1.spr` +20°, `rock2.spr` −20°, generated by
`tools/rock_spin.py`) live in the free sprite slots at $3880/$38C0
(pointers $E2/$E3), directly before the sound presets at $3900 — the
build errors out if the data drifts across.  The animation lives at
the end of `ast_update` (after `.mv_done`, before the $D015 sync):

```asm
    dec ast_spin_ctr      ; 10-frame cadence (200 ms PAL)
    bne .spin_lp
    lda #10
    sta ast_spin_ctr
    inc ast_spin          ; phase 0..2
    lda ast_spin
    cmp #3
    bne .spin_lp
    lda #0
    sta ast_spin
.spin_lp:
    ldx #2                ; slot index doubles as phase offset
.sp_lp1:
    txa
    clc
    adc ast_spin          ; phase = (ast_spin + slot) mod 3
    cmp #3
    bcc .sp_ok
    sbc #3
.sp_ok:
    tay
    lda rock_ptrs, y      ; rock_ptrs = [$E0, $E2, $E3]
    sta $07FA, x
    dex
    bpl .sp_lp1
```

The per-slot offset stops simultaneous rocks tumbling in lockstep;
inactive slots are hidden by $D015 so writing all three pointers
every frame is harmless.  `restart()` resets both new vars.  NTSC
runs the same 10 frames at 60 fps (~167 ms) — cosmetic difference.

---

### DMZ Visual Noise (`dmz_do` + `dmz_init`)

The safe zone (cols 28–39, rows 1–24) displays continuous colour-RAM static
à la Yars' Revenge.  288 cells refreshed every 3rd frame.

```asm
dmz_do:
    dec dmz_timer
    bne d_skip            ; wait 3 frames between refreshes
    lda #3
    sta dmz_timer

    lda #1                ; start at row 1 (row 0 is HUD)
    sta d_ri
dr_row:
    lda d_ri
    jsr d_mul40           ; $57/$58 = row × 40
    clc
    lda $57
    adc #28               ; start at column 28
    sta $57
    lda $58
    adc #>$D800           ; colour RAM base
    sta $58

    ldy #11               ; 12 cells per row (cols 28–39)
dr_col:
    jsr lfsr_tick
    and #$0F              ; random colour 0–15
    sta ($57), y          ; write colour RAM via indirect pointer
    dey
    bpl dr_col

    inc d_ri
    lda d_ri
    cmp #25
    bne dr_row
d_skip:
    rts
```

**Why indirect addressing**:  Colour RAM at `$D800–$DBE7` is not at a
contiguous address (it snakes across $D800, $D900, $DA00, $DAE7).
The `d_mul40` subroutine computes `$57/$58 = row × 40`, then the
caller adds the column offset and colour RAM base.  This is cheaper
than a full 16-bit multiply each iteration.

**Row × 40 multiplication** (`d_mul40`):
```
row × 40 = row × (8 + 32) = (row << 3) + (row << 5)
```
Uses shifts instead of a loop — constant time, no variable iteration.

---

### Splash Screen (`do_splash`)

The splash screen owns its own frame loop — it never returns to the
framework main loop.  This prevents `behaviors_update` from running
during the splash, avoiding HUD text flicker.

```asm
do_splash:
    lda #$00
    sta $d015             ; hide all sprites
    lda splash_done
    bne .ds_wait
    inc splash_done
    jsr draw_splash       ; one-time screen draw

.ds_wait:
    lda frame_ready       ; own frame sync
    beq .ds_wait
    lda #0
    sta frame_ready

    jsr splash_bars       ; DMZ-style side shimmer
    jsr title_load        ; re-assert logo glyphs (init may wipe them)

    ;; Keyboard fire — SPACE (matrix line 7, bit 4)
    lda #$7f
    sta $dc00
    lda $dc01
    and #$10
    bne .ds_nospace
    jmp ds_start          ; trampoline: ds_start is out of beq range

.ds_nospace:
    ;; M (line 4, bit 4): open the cracked loader — line 4, NOT line 0,
    ;; because RETURN (the harness's typed CR) lives on line 0 and a
    ;; per-frame line-0 scan eats the boot typing
    lda #$ef
    sta $dc00
    lda $dc01
    and #$10
    beq ds_loader          ; jsr loader_draw → jmp menu_wait

    ;; Joystick fire (port 2, active low)
    lda #$00
    sta $dc02
    lda $dc00
    and #$10
    tax
    lda #$ff
    sta $dc02
    txa
    bne .ds_wait          ; loop forever until input

ds_start:
    lda #11
    sta $d020             ; border back to the game's dark grey
    lda start_level       ; 0 → 1
    bne .ds_lv
    lda #1
    sta start_level
.ds_lv:
    lda #0
    sta init_done         ; force do_init to re-run (consumes start_level)
    lda #$03
    sta $d015             ; enable sprites 0+1
    lda #GAME_PLAYING
    sta state
    rts                   ; return to main_loop — splash never runs again
```

`ds_start` is a **global** label: the loader loop (`menu_wait`) is a
separate local-label scope and needs to reach it — a `.ds_start` local
under `splash_wait` would be out of scope there.

The `init_done = 0` flag forces `do_init` to re-run on the next frame,
overwriting the splash screen with the game's 3-zone colour RAM layout.
`do_init` now reads `start_level` (set by the loader) instead of
hardcoding level 1:
```
level = start_level (0/1 → 1, 2-5 → selected)
speed_frac = level_speeds[level-1]    (level > 5 clamps to the L5 row)
score = 0 for level 1, else the level's binary threshold
        (score+1 = $01/$02/$04/$06 → 256/512/1024/1536)
$D028 = light red at level 5+, red otherwise
```

---

### Powerup (`pwr_check` + unified invincibility flash)

An invincibility **charge**, not an item: reaching level 3+ sets `pwr_avail`,
and FIRE (joystick port 2) or SPACE (keyboard fire) spends it for 2 seconds
(100 frames) of immunity.

**Award** — in `level_update`, right after `inc level`:
```asm
    lda level
    cmp #3
    bcc .no_charge
    lda #1
    sta pwr_avail        ; capped at 1 — next level-up refreshes
.no_charge:
```

**Trigger** — `pwr_check` runs every PLAYING frame (in `do_play`, AFTER
the collision checks — a hit frame changes state to DYING before it
runs, so the charge arp can never overlay the death boom).  It reads
both input
sources (fire via `$DC02=$00` input mode; SPACE via matrix line 7, bit 4 —
the same read the splash uses) and combines them with the §4 edge-detection
pattern: `pwr_key` is 0 while held, 1 when released, so a charge can
never auto-fire while the button is held down.  The `do_die` respawn
path edge-resyncs `pwr_key` to the physical fire state, so a press held
through the dying window doesn't fire the arp right after the death
boom (defensive hardening — the real "alarm at death" was the death
boom's own voice-2 PULSE sweeping UP, which read as a rising siren once
the noise crack faded; it now sweeps down as an explosion thud, see
`boom_tick`).

```asm
.pressed:
    lda #$ff
    sta $dc02            ; restore keyboard mode (idempotent)
    lda pwr_key
    beq .p_held          ; already down → no edge
    lda #0
    sta pwr_key
    lda pwr_avail
    beq .p_held
    lda #0
    sta pwr_avail        ; consume charge
    lda hit_timer
    cmp #100
    bcs .keep            ; keep the longer timer — max() trick
    lda #100             ; 2 seconds at 50 fps
    sta hit_timer
.keep:
    lda #0
    sta pwr_flash
    jsr sfx_powerup
.p_held:
    rts
```

**Why `hit_timer`?**  Both collision systems already gate on it —
setting it to 100 gives immunity with zero changes to `collision_do`
or `ast_collision`.  The `cmp #100 / bcs` is a branch-based `max()`:
triggering while already invincible never shortens the existing timer.

**Unified flash** — the end of `do_play` flashes sprite 0 whenever
`hit_timer > 0`, so *all* invincibility (powerup and the existing
150-frame post-respawn grace) is visually indicated:

```asm
    lda hit_timer
    beq .inv_off
    lda pwr_flash
    beq .f_toggle
    dec pwr_flash        ; 4-frame cycle ≈ 6 Hz
    jmp .inv_done
.f_toggle:
    lda $d015
    eor #$01             ; toggle sprite 0 enable
    sta $d015
    lda #4
    sta pwr_flash
    jmp .inv_done
.inv_off:
    lda $d015
    ora #$01             ; never end the flash on a hidden frame
    sta $d015
.inv_done:
    rts
```

`do_die` keeps its own `flash_tmr` toggle for the DYING state; the two
can never fight because `do_play` runs only in PLAYING.

**HUD indicator** — `gstart` writes a PETSCII "P" (`$10`) at `$0400+28`
with white colour when charged, space + black otherwise.  Safe because
the DSL HUD covers cols 0–26 and `dmz_do` covers rows 1–24.

---

## Sound System

The dodge game uses sound presets from `macros/sound_presets.acme`.
Three types coexist:

| Type | Example | Call pattern | Gate-off |
|------|---------|-------------|----------|
| Single-shot | `sfx_boop` | `jsr sfx_boop` | `sfx_gate_off` each frame |
| Multi-frame | `sfx_coin` | `jsr sfx_coin`, then `sfx_tick_all` each frame | Handled internally |
| Raw SID | death (old) | Direct `$D400` writes | `sound_tick` |

**Frame loop integration**:
```asm
gstart:
    jsr sfx_gate_off      ; decrement sfx_dur, gate-off when zero
    jsr sfx_tick_all      ; dispatch to active multi-frame preset
```

**All presets now set `SID_VOL_MODE`** internally; `do_init` also sets it
as a baseline:
```asm
    lda #$0F
    sta $D418             ; master volume 15
```

---

## Visual Effects

### Colour RAM Zones

The 3-zone layout is painted once in `do_init` using a double-loop
(25 rows × 40 cols) with indirect addressing:
```asm
    lda #<$d800
    sta $02
    lda #>$d800
    sta $03
    ldx #25              ; 25 rows
z_row:
    ldy #0
    lda #6               ; blue — score zone
z_grn:
    sta ($02), y
    iny
    cpy #13
    bne z_grn
    lda #0               ; black — neutral
z_blk:
    sta ($02), y
    iny
    cpy #28
    bne z_blk
    lda #6               ; blue — DMZ
z_blu:
    sta ($02), y
    iny
    cpy #40
    bne z_blu
    ;; advance pointer by 40
    lda $02
    clc
    adc #40
    sta $02
    bcc z_nh
    inc $03
z_nh:
    dex
    bne z_row
```

### Sprite Flash on Death

Toggles sprite 0 visibility every 4 frames via exclusive-OR:
```asm
    lda $d015
    eor #$01             ; toggle sprite 0 enable bit
    sta $d015
```
The `eor` with a single bit inverts only that bit — all other sprites
are unaffected.  Runs for 150 frames (~3 seconds).

### Game Over Screen

Direct PETSCII text writes to screen RAM using `!scr` for conversion:
```asm
over_text:   !scr "game over", 0
over_prompt: !scr "press fire", 0
```
The title renders white at row 12 col 16; the prompt sits at row 13
col 15 in lt.grey (per-cell colour overwrite after the whole-row white
fill).  `behaviors_update` still runs every frame, so the HUD keeps
showing the final score.  On fire/SPACE, `ov_wait` first waits for the
press to lift — the RELEASE GATE polls `$DC01`/`$DC00` (ticking
`sound_tick`) until both SPACE and port-2 fire read released, because
the same press would otherwise re-trigger the splash's own start check
a frame later and skip the title (boots level 1 instantly).  Only then
does `ov_restart` call `restart()` (which resets all game state and
clears `start_level`), set `state = GAME_SPLASH` and `splash_done = 0`
so the splash block re-renders the title screen; the splash→play path
starts a fresh level-1 game via `do_init`.  The restart routine restores
the zone colours by re-painting rows 12–13 with the 3-zone pattern, then
clears the text area back to solid blocks.

---

## Memory Layout Reference

```
$0801–$0BFF   Framework code (generated from specs)
$0C00          Framework variables (frame_ready, joystick_state, random,
               sfx_dur, sfx_step, sfx_tmp, sfx_kind)
$0C53+         behaviors_update (HUD display code)
$0E00+         game_logic: → routines/game_logic.acme
               (gstart dispatcher + all subsystems)
$2000–$203F    ship_r.spr   (player right, pointer $80)
$2040–$207F    ship_l.spr   (player left,  pointer $81)
$2080–$20BF    ship_u.spr   (player up,    pointer $82)
$20C0–$20FF    ship_d.spr   (player down,  pointer $83)
$2100–$213F    skull.spr    (enemy,        pointer $84)
$2140–$217F    rock.spr     (asteroids,    pointer $85)
$2180–$21BF    Radar crosshair inline data (pointer $86)
$2900–$293F    Splash strings (ds_press / ds_hint / ds_credit)
$2940–$29FF    Ship-engine sound routine
$2A00–$31xx    Splash screen + cracked level-select loader (menu code,
               marker/puts helpers, menu strings at the block tail)
$3400–$353F    Codegen sprite blocks (ship ×4, skull — pointers $D0-$D4)
$3540–$37FF    Hand-drawn animation frames + rock (pointer $85-$8F bins)
$3800–$383F    Rock sprite (pointer $E0)
$3840–$3881    Radar crosshair sprite (pointer $E1)
$3900–$3Cxx    Sound preset subroutines (memory.sound_presets anchor)
$D800–$DBE7    Colour RAM (1 KB nybbles)
```
