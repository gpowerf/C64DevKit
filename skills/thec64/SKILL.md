---
name: thec64
description: Prepare media files for THEC64/THEVIC20 (TheC64 Maxi/Mini) using filename flags and CJM configuration files. Use when the user mentions TheC64, THEC64 Maxi/Mini, THEVIC20, CJM files, filename flags, REU on TheC64, joystick remapping for TheC64, or deploying a C64 program/game/disk image to TheC64 USB stick. Covers both c64devk CLI tools (c64devk flags, c64devk cjm) and the underlying official formats.
---

# TheC64 Skill

Prepare and customize media files (`.d64`, `.g64`, `.prg`, `.tap`,
`.crt`) for THEC64/THEVIC20 hardware using the two official
customization mechanisms, driven by validated c64devk tools. All
format knowledge comes from the official firmware v1.6.1 user manual
(chapter 8); full reference: `docs/thec64-flags.md` and
`docs/thec64-cjm.md`.

## Decision guide — flags or CJM?

| Need | Mechanism |
|------|-----------|
| Per-file settings that travel with the file; media swapped mid-session | **filename flags** |
| Joystick button remapping (any key → any button) | **CJM** |
| Vertical display shift without full-height squeeze | **CJM** (`V:`) |
| One configuration for every file in a folder | **CJM** (`thec64-default.cjm`) |

Precedence on the console: file CJM > `thec64-default.cjm` (inherited
up the folder tree) > filename flags > defaults. A CJM always wins —
never leave both on the same file unintentionally. Also remember: a
CJM with no `J:` line disables joysticks for that program (a lone
`J:1M:` mouse marker is fine for mouse-driven software like GEOS).

## Tool 1 — `c64devk flags`

Two-character codes appended to the filename before the extension
(`game_M6TPR5P1.d64`); hidden by the console UI, which shows the clean
name. **Preview is the default** — nothing changes without
`--rename` or `--copy DIR`.

```bash
c64devk flags GEOS64-20.d64 --c64 --pal --reu 512 --mouse1   # preview
c64devk flags GEOS64-20.d64 --c64 --pal --reu 512 --mouse1 --rename
c64devk flags game.d64 --explain              # decode existing flags
c64devk flags game_M6TP.d64 --strip --rename  # remove flag suffix
c64devk flags game.d64 --set M6TPR5P1 --rename  # replace wholesale
```

Option → code map: `--c64`/`--vic20` → M6/MV, `--pal`/`--ntsc` →
TP/TN, `--j1`/`--j2` → J1/J2, `--mouse1`/`--mouse2` → P1/P2,
`--extra-joysticks` → JA, `--accurate-disk`/`--read-only`/
`--continuation` → AD/RO/CD, `--full-height` → FH,
`--no-icon`/`--no-audio-scale` → NI/NS, `--bank 0..5` (repeatable) →
B*, `--reu 512\|2048\|16m` → R5/R2/RM.

Validation rules enforced (errors cite the manual rule): no
M6+MV, TN+TP, J1+J2, P1+P2; `B*` needs MV; `JA`/`R*` need M6;
AD/RO/CD only on `.d64`/`.g64`. New options merge with flags already
on the filename; parsing accepts concatenated (`M6TP`) and separated
(`M6_TP`) forms and walks segments right-to-left so normal stems with
underscores are safe.

## Tool 2 — `c64devk cjm`

A CJM is a text sidecar with the **same basename** as the media file
(`GEOS64-20.d64` ↔ `GEOS64-20.cjm`) or the folder-wide
`thec64-default.cjm` (via `--default`). The name must match exactly or
the console ignores the file.

```bash
c64devk cjm --preset geos --name GEOS64-20.d64 --out /usb/GEOS
c64devk cjm --preset joystick --name mygame        # port 2, all buttons fire
c64devk cjm --c64 --video pal --reu 2048 --name mygame
c64devk cjm --c64 --buttons "W,S,A,D,SP" --port 1 --name kbdgame
c64devk cjm --preset geos --default --out /usb/GEOS
```

Presets: `joystick`, `wasd`, `two-stick`, `geos` (1351 mouse port 1 +
`reu512`). Short `--buttons` lists are padded to the mandatory 15
positions (up, down, left, right, fireL, fireR, TL, TR, lsh, rsh, A,
B, C, lstick, rstick). Key IDs: JU JD JL JR JF, F1–F8, A–Z, 0–9, SP,
EN, CT, RS, RE, SL, SR, SS, HM, DL, CU CD CL CR, CM, CO, PO, AL, AU.

Generated format — `X:` (computer/video/options, lowercase), `J:`
lines (`J:<port>[*]:<15 entries>`; C64 ports 1–4, VIC 20 port 1 only
and primary), `J:<n>M:` mouse markers, `V:` vertical shift (C64
−15..+17, VIC PAL −16..+16, VIC NTSC −13..0). X options: `64`, `vic`,
`pal`, `ntsc`, `driveicon`, `readonly`, `accuratedisk`, `fullheight`,
`noaudioscale`, VIC `bank0-3,5`/`3k–35k`, C64 `reu512/reu2048/
reu16384` (fw ≥ 1.5.1).

## Worked example — GEOS 64 v2.0 on TheC64 Maxi

GEOS is mouse-driven and benefits from REU. Flags route:

```bash
c64devk flags GEOS64-20.d64 --c64 --pal --reu 512 --mouse1 --rename
```

CJM route (preferred when you may add more GEOS disks to the folder):

```bash
c64devk cjm --preset geos --default --out /usb/GEOS
```

producing `thec64-default.cjm`:

```
X:64,pal,reu512
J:1M:
```

Boot disk `GEOS64-20.d64` then boots a C64 PAL with the REU present
and the USB mouse as the 1351 pointer. `--reu 16m` (RM/reu16384)
gives the maximum RAM the machine can offer; stock GEOS 2.0 exploits
what its REU driver detects, so `512` is the safe default while
larger sizes suit CONFIGURE/MegaPatch-style setups. Note the REU
contents do not persist across power cycles.

## Tips

- Verify with `--explain` after renaming; the console hides flags, so
  the filename is the only record of the configuration.
- `--copy DIR` builds a clean USB-staging tree while leaving originals
  untouched.
- When a `.cjm` exists next to a media file, the flags tool prints a
  reminder that the CJM wins.
