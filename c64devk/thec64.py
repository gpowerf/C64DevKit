"""TheC64 customization kit — filename flags and CJM files.

Implements the official THEC64/THEVIC20 customization formats as
documented in the firmware v1.6.1 user manual (chapter 8, "Using
cartridge, disk, tape and program files"):

- Filename flags: two-character codes appended to a media filename
  before the extension (e.g. ``game_M6TPR5P1.d64``).
- CJM files: sidecar text files with the same basename as the media
  file (``game.cjm`` for ``game.d64``) that configure the virtual
  machine, joystick functions and display shift.

Precedence when THEC64 loads a file (manual p. 72):

1. a CJM file for the specific file,
2. otherwise ``thec64-default.cjm`` in the file's folder (or the
   nearest parent folder),
3. otherwise filename flags on the media filename,
4. otherwise built-in defaults.

A CJM therefore always trumps filename flags — the tools in this
module warn when both mechanisms target the same media file.

Note: REU options (``R5``/``R2``/``RM`` flags, ``reu*`` CJM values)
require firmware 1.5.1 or later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Filename flags
# ---------------------------------------------------------------------------

#: Two-character filename flags and what they do (manual pp. 58–62).
FLAG_DESCRIPTIONS: dict[str, str] = {
    "M6": "computer model: C64 (THEC64 only)",
    "MV": "computer model: VIC 20 (THEC64 only)",
    "TN": "video standard: NTSC",
    "TP": "video standard: PAL",
    "J1": "primary joystick port #1",
    "J2": "primary joystick port #2",
    "JA": "enable additional joysticks in user-port #3 and #4 (C64 only)",
    "P1": "1351 mouse connected to port #1 (joystick moves to #2)",
    "P2": "1351 mouse connected to port #2 (joystick moves to #1)",
    "AD": "accurate disk mode — slower, more accurate loading (d64/g64 only)",
    "RO": "disk is read-only (write-protected)",
    "CD": "multi-disk continuation — not the first disk of a set",
    "FH": "full-height display (squeezes borders into the 720p image)",
    "B0": "VIC 20 expanded memory bank 0 (+3 kB)",
    "B1": "VIC 20 expanded memory bank 1 (+8 kB)",
    "B2": "VIC 20 expanded memory bank 2 (+8 kB)",
    "B3": "VIC 20 expanded memory bank 3 (+8 kB)",
    "B5": "VIC 20 expanded memory bank 5 (+8 kB)",
    "R5": "C64 REU: 512 kB (fw >= 1.5.1)",
    "R2": "C64 REU: 2 MB (fw >= 1.5.1)",
    "RM": "C64 REU: 16 MB (fw >= 1.5.1)",
    "NI": "hide the drive icon during disk loading",
    "NS": "disable audio scaling",
}

#: Flag pairs that must not be combined.
MUTUALLY_EXCLUSIVE: list[tuple[str, str]] = [
    ("M6", "MV"),
    ("TN", "TP"),
    ("J1", "J2"),
    ("P1", "P2"),
]

#: Flags that only make sense on a VIC 20 program.
VIC_ONLY: set[str] = {"B0", "B1", "B2", "B3", "B5"}

#: Flags that only make sense on a C64 program.
C64_ONLY: set[str] = {"JA", "R5", "R2", "RM"}

#: Flags that only apply to virtual disk files.
DISK_ONLY: set[str] = {"AD", "RO", "CD"}

#: Extensions treated as virtual disks for DISK_ONLY validation.
DISK_EXTS: set[str] = {".d64", ".g64"}

#: Extensions flags are meaningful for (informational).
MEDIA_EXTS: set[str] = {".d64", ".g64", ".prg", ".tap", ".crt"}

#: Long CLI option -> flag code (used by ``c64devk flags``).
FLAG_LONG_OPTIONS: list[tuple[str, str]] = [
    ("--c64", "M6"),
    ("--vic20", "MV"),
    ("--ntsc", "TN"),
    ("--pal", "TP"),
    ("--j1", "J1"),
    ("--j2", "J2"),
    ("--extra-joysticks", "JA"),
    ("--mouse1", "P1"),
    ("--mouse2", "P2"),
    ("--accurate-disk", "AD"),
    ("--read-only", "RO"),
    ("--continuation", "CD"),
    ("--full-height", "FH"),
    ("--no-icon", "NI"),
    ("--no-audio-scale", "NS"),
]


def split_flags(filename: str) -> tuple[str, list[str], str]:
    """Split a media filename into ``(stem, flags, ext)``.

    Flags are read from the trailing underscore-separated segment(s),
    which must parse entirely as known two-character codes — either
    concatenated (``M6TPR5``) or underscore-separated (``M6_TP_R5``).
    Segments are consumed right-to-left until one does not parse, so
    ordinary stems containing underscores are left untouched.
    """
    stem, _, ext = filename.rpartition(".")
    if not stem:
        stem, ext = filename, ""
    else:
        ext = "." + ext

    flags: list[str] = []
    parts = stem.rsplit("_", 1)
    while len(parts) == 2 and _parse_flag_segment(parts[1]) is not None:
        codes = _parse_flag_segment(parts[1])
        flags = codes + flags
        stem = parts[0]
        if not stem:
            # The whole name would vanish — treat as no flags.
            return filename[: -len(ext)] if ext else filename, [], ext
        parts = stem.rsplit("_", 1)
    return stem, flags, ext


def _parse_flag_segment(segment: str) -> list[str] | None:
    """Parse one underscore-separated filename segment as flag codes.

    Returns the codes, or ``None`` if the segment is not entirely
    composed of known two-character flags.
    """
    if not segment:
        return None
    codes: list[str] = []
    for chunk in segment.split("_"):
        if len(chunk) == 0 or len(chunk) % 2 != 0:
            return None
        for i in range(0, len(chunk), 2):
            code = chunk[i : i + 2].upper()
            if code not in FLAG_DESCRIPTIONS:
                return None
            codes.append(code)
    return codes


def dedupe_flags(flags: list[str]) -> list[str]:
    """Remove duplicate flags, preserving first occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            out.append(flag)
    return out


def validate_flags(flags: list[str], ext: str) -> list[str]:
    """Validate a flag set against the manual's rules.

    Returns a list of human-readable error messages (empty when valid).
    """
    errors: list[str] = []
    flags = dedupe_flags(flags)
    known = set(flags) & set(FLAG_DESCRIPTIONS)

    for a, b in MUTUALLY_EXCLUSIVE:
        if a in known and b in known:
            errors.append(
                f"conflicting flags {a} and {b}: '{FLAG_DESCRIPTIONS[a]}' "
                f"vs '{FLAG_DESCRIPTIONS[b]}'"
            )

    vic = "MV" in known
    c64 = "M6" in known
    for flag in known & VIC_ONLY:
        if not vic:
            errors.append(
                f"flag {flag} ({FLAG_DESCRIPTIONS[flag]}) only applies to a "
                "VIC 20 program — add MV"
            )
    for flag in known & C64_ONLY:
        if not c64:
            if vic:
                errors.append(
                    f"flag {flag} ({FLAG_DESCRIPTIONS[flag]}) is C64-only "
                    "but the model flag is MV"
                )
            else:
                errors.append(
                    f"flag {flag} ({FLAG_DESCRIPTIONS[flag]}) only applies "
                    "to a C64 program — add M6"
                )

    disk_flags = known & DISK_ONLY
    if disk_flags and ext.lower() not in DISK_EXTS:
        names = ", ".join(sorted(disk_flags))
        errors.append(
            f"flags {names} only apply to virtual disk files (.d64/.g64), "
            f"not '{ext or '(no extension)'}'"
        )

    return errors


def build_flag_name(stem: str, flags: list[str], ext: str) -> str:
    """Assemble a media filename from a stem, flag codes and extension.

    The flags are joined without extra separators per the manual's
    canonical form (``game_M6TPR5P1.d64``).
    """
    flags = dedupe_flags(flags)
    if flags:
        return f"{stem}_{''.join(flags)}{ext}"
    return f"{stem}{ext}"


def parse_flag_string(raw: str) -> list[str]:
    """Parse a raw flag string such as ``M6TPR5P1`` or ``M6_TP_R5``.

    Raises ``ValueError`` on anything that does not parse as known flags.
    """
    codes = _parse_flag_segment(raw.strip("_ "))
    if codes is None:
        raise ValueError(
            f"'{raw}' does not parse as known two-character flags "
            f"(valid: {', '.join(sorted(FLAG_DESCRIPTIONS))})"
        )
    return dedupe_flags(codes)


# ---------------------------------------------------------------------------
# CJM files
# ---------------------------------------------------------------------------

#: Key/function IDs that may be assigned to joystick buttons (manual p. 69).
CJM_KEY_IDS: set[str] = (
    {"JU", "JD", "JL", "JR", "JF"}
    | {f"F{n}" for n in range(1, 9)}
    | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    | set("0123456789")
    | {"SP", "EN", "CT", "RS", "RE", "SL", "SR", "SS", "HM", "DL",
       "CU", "CD", "CL", "CR", "CM", "CO", "PO", "AL", "AU"}
)

#: The 15 joystick button positions in mandatory CJM order (manual p. 68).
JOYSTICK_POSITIONS: list[str] = [
    "up", "down", "left", "right",
    "fire_left", "fire_right",
    "top_left", "top_right",
    "left_shoulder", "right_shoulder",
    "a", "b", "c",
    "left_stick", "right_stick",
]

#: X: options common to all computer models (manual p. 65).
CJM_X_COMMON: set[str] = {
    "driveicon", "readonly", "accuratedisk", "fullheight", "noaudioscale",
}

#: X: options specific to the VIC 20 (manual p. 65).
CJM_X_VIC: set[str] = {
    "bank0", "bank1", "bank2", "bank3", "bank5",
    "3k", "4k", "8k", "16k", "24k", "32k", "35k",
}

#: X: options specific to the C64 (manual p. 65, fw >= 1.5.1 for REU).
CJM_X_C64: set[str] = {"reu512", "reu2048", "reu16384"}

#: Vertical display shift ranges per model and video standard (manual p. 66).
CJM_V_RANGES: dict[tuple[str, str | None], tuple[int, int]] = {
    ("c64", None): (-15, 17),
    ("c64", "pal"): (-15, 17),
    ("c64", "ntsc"): (-15, 17),
    ("vic20", "pal"): (-16, 16),
    ("vic20", "ntsc"): (-13, 0),
}

#: Name of the folder-wide default CJM file (manual p. 71).
CJM_DEFAULT_FILENAME = "thec64-default.cjm"


@dataclass
class Joystick:
    """One J: line — a joystick port and its 15 button assignments.

    Button entries are CJM key IDs (or "" for an unused position) in
    :data:`JOYSTICK_POSITIONS` order.
    """

    port: int
    primary: bool
    buttons: list[str] = field(default_factory=lambda: [""] * 15)

    def line(self) -> str:
        marker = "*" if self.primary else ""
        return f"J:{self.port}{marker}:{','.join(self.buttons)}"


@dataclass
class CjmConfig:
    """Everything a CJM file can express (manual pp. 64–70)."""

    computer: str | None = None        # "c64" | "vic20"
    video: str | None = None           # "pal" | "ntsc"
    options: list[str] = field(default_factory=list)   # X: extras
    vertical_shift: int | None = None  # V:
    joysticks: list[Joystick] = field(default_factory=list)
    mouse: int | None = None           # 1 or 2 → J:<n>M:

    def generate(self) -> str:
        """Render the CJM file contents."""
        lines: list[str] = []

        x_values: list[str] = []
        if self.computer == "c64":
            x_values.append("64")
        elif self.computer == "vic20":
            x_values.append("vic")
        if self.video:
            x_values.append(self.video)
        x_values.extend(self.options)
        if x_values:
            lines.append("X:" + ",".join(x_values))

        for joy in self.joysticks:
            lines.append(joy.line())
        if self.mouse is not None:
            lines.append(f"J:{self.mouse}M:")

        if self.vertical_shift is not None:
            lines.append(f"V:{self.vertical_shift}")

        return "\n".join(lines) + "\n" if lines else ""


def validate_cjm(config: CjmConfig) -> list[str]:
    """Validate a :class:`CjmConfig` against the manual's rules.

    Returns a list of human-readable error messages (empty when valid).
    """
    errors: list[str] = []

    if config.computer not in (None, "c64", "vic20"):
        errors.append(f"unknown computer '{config.computer}' (use c64 or vic20)")
    if config.video not in (None, "pal", "ntsc"):
        errors.append(f"unknown video standard '{config.video}' (use pal or ntsc)")

    for option in config.options:
        if option in CJM_X_VIC and config.computer != "vic20":
            errors.append(
                f"X option '{option}' only works on a VIC 20 — set computer=vic20"
            )
        elif option in CJM_X_C64 and config.computer != "c64":
            errors.append(
                f"X option '{option}' only works on a C64 — set computer=c64"
            )
        elif (
            option not in CJM_X_COMMON
            and option not in CJM_X_VIC
            and option not in CJM_X_C64
        ):
            errors.append(
                f"unknown X option '{option}' (valid: "
                f"{', '.join(sorted(CJM_X_COMMON | CJM_X_VIC | CJM_X_C64))})"
            )

    if config.vertical_shift is not None:
        if config.computer is None:
            errors.append("vertical_shift requires computer to be set (c64/vic20)")
        else:
            lo, hi = CJM_V_RANGES.get((config.computer, config.video), (-15, 17))
            if not lo <= config.vertical_shift <= hi:
                errors.append(
                    f"vertical_shift {config.vertical_shift} outside "
                    f"{lo}..{hi} for {config.computer}/{config.video or 'default video'}"
                )

    if config.mouse not in (None, 1, 2):
        errors.append(f"mouse port must be 1 or 2, not {config.mouse}")

    primaries = [j for j in config.joysticks if j.primary]
    if config.joysticks and len(primaries) != 1:
        errors.append(
            "exactly one joystick must be the primary (marked with *)"
        )

    for joy in config.joysticks:
        if joy.port not in (1, 2, 3, 4):
            errors.append(f"joystick port {joy.port} out of range 1-4")
        if config.computer == "vic20" and joy.port != 1:
            errors.append(
                f"VIC 20 games allow only a single joystick in port 1 "
                f"(got port {joy.port})"
            )
        if len(joy.buttons) != 15:
            errors.append(
                f"joystick port {joy.port} needs 15 button entries "
                f"(got {len(joy.buttons)}) — order: "
                f"{', '.join(JOYSTICK_POSITIONS)}"
            )
        for pos, entry in zip(JOYSTICK_POSITIONS, joy.buttons):
            entry = entry.strip().upper()
            if entry and entry not in CJM_KEY_IDS:
                errors.append(
                    f"joystick port {joy.port} {pos}: '{entry}' is not a "
                    "valid key ID"
                )

    if config.mouse is not None and config.joysticks:
        ports = {j.port for j in config.joysticks}
        if config.mouse in ports:
            errors.append(
                f"mouse is on port {config.mouse} but a joystick is also "
                f"configured there — THEC64 moves the joystick to the "
                f"other port; configure the joystick accordingly"
            )

    return errors


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

#: Standard port-2 mapping: all buttons fire, C = RUN/STOP.
DEFAULT_JOYSTICK_BUTTONS = [
    "JU", "JD", "JL", "JR",
    "JF", "JF",
    "JF", "JF",
    "JF", "JF",
    "JF", "JF", "RS",
    "JF", "JF",
]

#: The manual's own keyboard-game example (VIC 20 style, port 1).
WASD_BUTTONS = ["W", "S", "A", "D", "I", "K", "J", "L",
                "CT", "1", "2", "3", "", "EN", "4"]

#: Two-stick controller layout (CubicleNate's PETSCII Robots SNES map,
#: left stick moves, right stick aims/fires).
TWO_STICK_BUTTONS = ["I", "K", "J", "L", "Z", "M", "W", "A",
                     "Z", "S", "D", "SP", "M", "F3", "F1"]

#: Ready-made CJM configurations.
PRESETS: dict[str, CjmConfig] = {
    # C64 default primary port is #2; every button acts as fire.
    "joystick": CjmConfig(
        computer="c64",
        joysticks=[Joystick(port=2, primary=True,
                            buttons=list(DEFAULT_JOYSTICK_BUTTONS))],
    ),
    "wasd": CjmConfig(
        computer="c64",
        joysticks=[Joystick(port=1, primary=True,
                            buttons=list(WASD_BUTTONS))],
    ),
    "two-stick": CjmConfig(
        computer="c64",
        joysticks=[Joystick(port=2, primary=True,
                            buttons=list(TWO_STICK_BUTTONS))],
    ),
    # GEOS is mouse-driven: 1351 mouse in port 1, REU enabled.
    "geos": CjmConfig(
        computer="c64",
        video="pal",
        options=["reu512"],
        mouse=1,
    ),
}

#: REU CLI choice -> CJM X option.
REU_CHOICES = {"512": "reu512", "2048": "reu2048", "16m": "reu16384"}

#: REU CLI choice -> filename flag.
REU_FLAG_CHOICES = {"512": "R5", "2048": "R2", "16m": "RM"}

#: VIC-20 bank CLI number -> filename flag.
VIC_BANK_FLAGS = {0: "B0", 1: "B1", 2: "B2", 3: "B3", 5: "B5"}
