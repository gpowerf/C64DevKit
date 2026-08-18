# Sprite Dodge — Assembly Reference

A technical walkthrough of the 6502 assembly techniques used in the dodge game.
All code lives in `routines/game_logic.acme` (~2200 lines).  This document extracts
the reusable patterns and explains the architecture.

---

## File Layout & Memory

```
Lines 1–6     Comment header, CHEAT_KEYS constant
Line 7         jmp gstart          ← skip variable data
Lines 10–54    !byte variables     ← 45 game-state variables
Lines 56–60    Constants (GAME_PLAYING=0, GAME_DYING=1, GAME_OVER=2, GAME_SPLASH=3)
Lines 62–93    gstart:             ← frame dispatcher (jsr chain + state switch)
Lines 96–207   init_once / do_init ← one-shot screen setup
Lines 212–219  do_play:            ← PLAYING state dispatch
Lines 224–268  do_die:             ← DYING state (flash + timer)
Lines 273–304  do_over:            ← GAME_OVER state (draw + wait)
Lines 306–346  draw_gameover       ← screen text + colour RAM
Lines 349–445  restart:            ← reset all state on replay
Lines 450–528  keyboard_read:      ← WASD keyboard scan
Lines 529–612  (joystick port 2)   ← inline joystick reads
Lines 617–691  enemy_do:           ← enemy chase AI
Lines 696–764  score_do:           ← zone-based scoring
Lines 769–871  collision_do:       ← player–enemy collision
Lines 876–885  sound_tick:         ← legacy sound timer
Lines 890–931  level_update:       ← level thresholds
Lines 936–944  ast_angles:         ← 32-entry spawn direction table
Lines 949–1176 ast_spawn:          ← asteroid spawning
Lines 1183–1271 ast_preview:       ← next-spawn position pre-roll
Lines 1273–1443 ast_update:        ← asteroid movement + despawn
Lines 1445–1585 ast_collision:     ← player–asteroid collision
Lines 1590–1646 radar_do:          ← radar warning indicator
Lines 1651–1661 lfsr_tick:         ← Galois LFSR RNG
Lines 1663–1690 dmz_init:         ← DMZ colour RAM init fill
Lines 1692–1727 dmz_do:            ← DMZ per-frame static refresh
Lines 1729–1757 d_mul40:           ← row × 40 multiply
Lines 1766–2024 cheat_keys:        ← SPACE level-cycle debug
Lines 2029–2044 chk_sid:           ← cheat level-up sound
Lines 2048–2214 do_splash / draw_splash / splash_bars  ← splash screen
Lines 2216     * = $2140 → rock.spr binary data
Lines 2220     * = $2180 → radar sprite data
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
- `cheat_keys` — SPACE level cycle (`cheat_spc`)
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

**Note**: The dodge game's `chk_sid` uses a cleaner approach — `jmp sfx_ping`
from a `jsr`-called subroutine.  The `jsr chk_sid` already pushed the return
address; `jmp sfx_ping` forwards it; `sfx_ping`'s `RTS` returns to `cheat_keys`.
No manual stack manipulation needed.

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

**Edge determination** from velocity sign:
```asm
    lda ast_vy
    bpl .not_bottom       ; dy ≥ 0 → not bottom
    lda #210              ; bottom edge Y
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
On actual spawn, `ast_spawn` uses the pre-rolled values if `ast_warn_dir != 255`,
then clears it.  This decouples the visual warning from the spawn timing.

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

    ;; Check SPACE to start
    lda #$7f
    sta $dc00
    lda $dc01
    and #$10
    beq .ds_start

    ;; Check joystick fire
    lda #$00
    sta $dc02
    lda $dc00
    and #$10
    tax
    lda #$ff
    sta $dc02
    txa
    bne .ds_wait          ; loop forever until input

.ds_start:
    lda #0
    sta init_done         ; force do_init to re-run
    lda #$03
    sta $d015             ; enable sprites 0+1
    lda #GAME_PLAYING
    sta state
    rts                   ; return to main_loop — splash never runs again
```

The `init_done = 0` flag forces `do_init` to re-run on the next frame,
overwriting the splash screen with the game's 3-zone colour RAM layout.

---

### Powerup (`pwr_check` + unified invincibility flash)

An invincibility **charge**, not an item: reaching level 3+ sets `pwr_avail`,
and FIRE (joystick port 2) or LEFT SHIFT spends it for 2 seconds (100 frames)
of immunity.

**Award** — in `level_update`, right after `inc level`:
```asm
    lda level
    cmp #3
    bcc .no_charge
    lda #1
    sta pwr_avail        ; capped at 1 — next level-up refreshes
.no_charge:
```

**Trigger** — `pwr_check` runs every PLAYING frame.  It reads both input
sources (fire via `$DC02=$00` input mode; LEFT SHIFT via column `$FD`,
row bit `$80`) and combines them with the `cheat_spc` edge-detection
pattern: `pwr_key` is 0 while held, 1 when released, so a charge can
never auto-fire while the button is held down.

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
| Multi-frame | `sfx_ping` | `jsr sfx_ping`, then `sfx_tick_all` each frame | Handled internally |
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
over_text:  !scr "game over", 0
space_text: !scr "press space to play", 0
```
The restart routine restores the zone colours by re-painting rows 12–13
with the 3-zone pattern, then clears the text area back to solid blocks.

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
$21C0+         Sound preset subroutines
$3800–$3FFF    ROM charset copy (2 KB)
$D800–$DBE7    Colour RAM (1 KB nybbles)
```
