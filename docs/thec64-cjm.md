# TheC64 CJM files

A CJM file is a plain-text sidecar that configures how
THEC64/THEVIC20 runs a virtual media file. It can do everything a
filename flag can, plus two things flags cannot: **joystick button
remapping** and **vertical display shift**.

Naming rules:

- Same folder as the media file, same basename, `.cjm` extension:
  `c64-disk.d64` ↔ `c64-disk.cjm`. The match must be *exact* — a CJM
  whose basename differs from the media filename is silently ignored.
- `thec64-default.cjm` applies to every file in its folder (and is
  inherited from parent folders when a subfolder has none).

Source: official *THEC64 & THEVIC20 User Manual v1.6.1*, chapter 8,
"CJMs for individual files" / "CJMs for multiple files" (pp. 63–72).

## Tool

```bash
c64devk cjm --preset geos --name GEOS64-20.d64 --out /usb/GEOS
c64devk cjm --preset joystick --name mygame
c64devk cjm --c64 --video pal --reu 2048 --name mygame
c64devk cjm --c64 --buttons "W,S,A,D,SP" --port 1 --name keyboard-game
c64devk cjm --preset geos --default --out /usb/GEOS   # thec64-default.cjm
```

Presets: `joystick` (C64 default port 2, every button fires, C =
RUN/STOP), `wasd` (the manual's own keyboard-game map), `two-stick`
(SNES-style dual-stick layout), `geos` (1351 mouse + REU). Short
`--buttons` lists are padded with empty entries to the required 15.

## Format

Each line is `type:value[,value]`. A typical file:

```
X:64,ntsc,accuratedisk,driveicon
J:1*:JU,JD,JL,JR,JF,JF,1,2,JF,A,B,C,JF,4,5
J:2:JU,JD,JL,JR,JF,JF,F1,F2,JF,1,2,3,JF,F3,F4
V:12
```

### X: — computer configuration

All values are **case sensitive and must be lowercase**.

| Value | Meaning |
|-------|---------|
| `64` | C64 model (THEC64 only) |
| `vic` | VIC 20 model (THEC64 only) |
| `pal` / `ntsc` | video standard of the program |
| `driveicon` | show the drive icon during disk access |
| `readonly` | disk is read-only |
| `accuratedisk` | accurate (slower) disk emulation |
| `fullheight` | full-height display |
| `noaudioscale` | disable audio scaling |
| `bank0`–`bank3`, `bank5` | VIC 20 RAM banks (combinable) |
| `3k` `4k` `8k` `16k` `24k` `32k` `35k` | direct VIC 20 RAM size |
| `reu512` / `reu2048` / `reu16384` | C64 REU (fw ≥ 1.5.1) |

`bank*`/`*k` require `vic`; `reu*` require `64`.

### V: — vertical display shift

Integer display lines. Ranges: C64 −15..+17, VIC 20 PAL −16..+16,
VIC 20 NTSC −13..0. Above +6 on NTSC C64 programs may exhibit display
problems at the bottom of the screen.

### J: — joystick configuration

```
J:<port>[*]:<up>,<down>,<left>,<right>,<fireL>,<fireR>,<TL>,<TR>,<lsh>,<rsh>,<A>,<B>,<C>,<lstick>,<rstick>
```

- Exactly **15 comma-separated entries**; any entry may be empty.
- `*` after the port marks the **primary** joystick — exactly one
  per file.
- C64: ports 1–4 (3/4 are user-port joysticks, enabled implicitly by
  the CJM). VIC 20: port 1 only, and it must be the primary.
- 1351 mouse markers: `J:1M:` or `J:2M:` (note the trailing colon).
  A connected joystick is moved to the other port.

**Critical:** if a CJM exists but contains no `J:` line, joysticks
and USB controllers do *not* work for that program at all. (A mouse
marker alone is fine for mouse-driven programs like GEOS.)

### Key IDs

| Group | IDs |
|-------|-----|
| Directions/fire | `JU` `JD` `JL` `JR` `JF` |
| Function keys | `F1`–`F8` |
| Alphanumerics | `A`–`Z`, `0`–`9` |
| Special keys | `SP` space, `EN` return, `CT` ctrl, `RS` run/stop, `RE` restore |
| Shifts/lock | `SL` left shift, `SR` right shift, `SS` shift lock |
| Cursor | `CU` `CD` `CL` `CR` |
| Editing/other | `HM` clr/home, `DL` inst/del, `CM` C= key, `CO` comma, `PO` £, `AL` arrow left, `AU` arrow up |

## Precedence

1. CJM for the specific file
2. `thec64-default.cjm` in the folder (then parent folders, up to the USB root)
3. filename flags on the media filename
4. built-in defaults

A CJM **trumps** filename flags — do not mix them unintentionally.
If you use flags for per-disk behaviour inside a folder that has a
default CJM, the CJM's overlapping settings win.

## Worked example: GEOS 64 v2.0

GEOS needs its pointer (1351 mouse) and wants REU. For a USB stick:

```
USB:/
└── GEOS/
    ├── GEOS64-20.d64
    └── GEOS64-20.cjm
```

```bash
c64devk cjm --preset geos --name GEOS64-20.d64 --out /media/usb/GEOS
```

produces `GEOS64-20.cjm`:

```
X:64,pal,reu512
J:1M:
```

Swap `--reu 2048`/`--reu 16m` for more RAM (fw ≥ 1.5.1); stock GEOS
2.0 exploits what its REU driver detects. Using `J:1M:` rather than a
button map keeps the CJM minimal and mouse-driven — exactly what GEOS
expects. To give *every* disk in the GEOS folder the same treatment,
add `--default` to write `thec64-default.cjm` instead.
