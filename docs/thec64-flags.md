# TheC64 filename flags

Filename flags are the quickest way to customize how THEC64/THEVIC20
treats a media file: two-character codes appended to the filename
before the extension.

```
game_M6TPR5P1.d64
      └┬┘ └┬┘ └┬┘ └┬┘
       M6  TP  R5  P1
```

In the File loader and Media access the flags are *not shown* —
`game_M6TPR5P1.d64` simply appears as **game** with the right icon.

Source: official *THEC64 & THEVIC20 User Manual v1.6.1*, chapter 8,
"Filename flags for individual files" (pp. 58–62).

## Tool

```bash
c64devk flags <file...> [options]         # preview the flagged name
c64devk flags <file...> [options] --rename  # rename in place
c64devk flags <file...> [options] --copy DIR  # staged copy under the new name
c64devk flags <file> --strip --rename     # remove the flag suffix
c64devk flags <file> --explain            # decode existing flags
```

Options mirror the codes one-to-one (`--c64`, `--pal`, `--reu 512`,
`--mouse1`, `--accurate-disk`, ...), or pass a raw set with
`--set M6TPR5P1`. New options are **merged** with any flags already on
the file. Without `--rename`/`--copy` nothing is modified.

## The flags

| Code | Meaning | Notes |
|------|---------|-------|
| `M6` | computer model: C64 | THEC64 only |
| `MV` | computer model: VIC 20 | THEC64 only |
| `TN` | video: NTSC | |
| `TP` | video: PAL | |
| `J1` | primary joystick port #1 | C64 default is #2 |
| `J2` | primary joystick port #2 | |
| `JA` | enable user-port joysticks #3/#4 | C64 only |
| `P1` | 1351 mouse in port #1 | joystick moves to #2 |
| `P2` | 1351 mouse in port #2 | joystick moves to #1 |
| `AD` | accurate (slower) disk mode | `.d64`/`.g64` only |
| `RO` | disk read-only | `.d64`/`.g64` only |
| `CD` | multi-disk continuation (not first disk) | `.d64`/`.g64` only |
| `FH` | full-height display | squeezes borders into 720p |
| `B0` `B1` `B2` `B3` `B5` | VIC 20 RAM banks (+3/8/8/8/8 kB) | VIC 20 only, combinable |
| `R5` | C64 REU 512 kB | fw ≥ 1.5.1 |
| `R2` | C64 REU 2 MB | fw ≥ 1.5.1 |
| `RM` | C64 REU 16 MB | fw ≥ 1.5.1 |
| `NI` | hide drive icon during disk access | |
| `NS` | disable audio scaling | |

## Rules

- Flags can appear in any order after a single underscore; the tool
  also understands underscore-separated variants (`game_M6_TP.d64`).
- Conflicts are rejected: `M6`+`MV`, `TN`+`TP`, `J1`+`J2`, `P1`+`P2`.
- `B*` flags require `MV`; `JA`/`R*` flags require `M6`.
- `AD`/`RO`/`CD` only apply to `.d64`/`.g64` files.

## Flags or CJM?

| Situation | Use |
|-----------|-----|
| Per-file settings that travel with the file | **flags** |
| Media that gets swapped mid-session (flags apply on insert, p. 73) | **flags** |
| Joystick button remapping | **CJM** (flags cannot remap buttons) |
| Vertical display shift without full-height squeeze | **CJM** (`V:`) |
| One configuration for a whole folder | **CJM** (`thec64-default.cjm`) |

Precedence: file CJM > `thec64-default.cjm` (inherited up the folder
tree) > filename flags > defaults. A CJM always wins — avoid keeping
both on the same file unless the overlap is intentional (the tool
warns when a matching `.cjm` sits next to the media file).

## Worked example: GEOS 64 v2.0

GEOS is mouse-driven and benefits from REU:

```bash
c64devk flags GEOS64-20.d64 --c64 --pal --reu 512 --mouse1 --rename
# -> GEOS64-20_M6TPR5P1.d64
```

The result in the File loader is still shown as **GEOS64-20**, boots a
C64 PAL with a 512 kB REU detected at startup, and uses a connected
USB mouse as the 1351 pointer in port #1. Bump `--reu 16m` (→ `RM`)
for the maximum RAM TheC64 can offer; stock GEOS 2.0 exploits what its
REU driver detects, so `R5` is the safe choice, while larger sizes
prepare the machine for CONFIGURE/MegaPatch-style setups.

Utility disks for the same GEOS session usually want at most:

```bash
c64devk flags "Utilities.d64" --accurate-disk --read-only --rename
```
