"""VICE bridge — launch emulator and communicate via remote monitor."""

import re
import os
import signal
import subprocess
import socket
import time
import sys
from pathlib import Path


VICE_BINARIES = ["x64sc", "x64"]
REMOTE_MONITOR_PORT = 6510


def find_vice() -> str:
    for name in VICE_BINARIES:
        p = subprocess.run(["which", name], capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    return ""


def launch_vice(prg_path: Path, headless: bool = False, autostart: bool = True) -> subprocess.Popen | None:
    vice = find_vice()
    if not vice:
        print("Error: VICE (x64sc) not found", file=sys.stderr)
        return None

    prg_path = Path(prg_path).resolve()  # VICE's cwd is the ROM dir — relative paths would silently fail

    rom_dir = (Path.home() / ".c64devk" / "roms")
    if not (rom_dir / "kernal").exists():
        _setup_roms(rom_dir)

    args = [vice]
    if autostart:
        init_addr = _read_init_from_prg(prg_path)
        args += [
            "-autostartprgmode", "1",
            "-autostart", str(prg_path),
            "-keybuf", f"sys{init_addr}\r",
        ]
    else:
        args.append(str(prg_path))

    if headless:
        args += ["-remotemonitor", "+sound"]

    print(f"  Launching: {vice}")
    print(f"  PRG: {prg_path}")
    return subprocess.Popen(args, cwd=str(rom_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           start_new_session=True)


def _read_init_from_prg(prg_path: Path) -> int:
    """Read the PRG file and compute the machine code init address
    (the first executable byte after the BASIC SYS header)."""
    data = prg_path.read_bytes()
    if len(data) < 4:
        return 2064
    load_addr = data[0] | (data[1] << 8)
    body = data[2:]
    num_digits = 0
    for i, b in enumerate(body):
        if b == 0x9E:  # SYS token
            for j in range(i + 1, min(i + 7, len(body))):
                if body[j] == 0:
                    num_digits = j - i - 1
                    break
            break
    if num_digits == 0:
        num_digits = 4
    header_size = 8 + num_digits  # link(2) + line(2) + SYS(1) + digits + EOL(1) + EOP(2)
    return load_addr + header_size


def _setup_roms(rom_dir: Path) -> None:
    rom_dir.mkdir(parents=True, exist_ok=True)
    roms_src = Path("/usr/share/vice/C64")
    mapping = {
        "kernal-901227-03.bin": "kernal",
        "basic-901226-01.bin": "basic",
        "chargen-901225-01.bin": "chargen",
    }
    for src_name, dst_name in mapping.items():
        src = roms_src / src_name
        dst = rom_dir / dst_name
        if src.exists() and not dst.exists():
            os.symlink(str(src), str(dst))


def launch_headless(prg_path: Path, sound: bool = False) -> subprocess.Popen | None:
    vice = find_vice()
    if not vice:
        print("Error: VICE (x64sc) not found", file=sys.stderr)
        return None

    prg_path = Path(prg_path).resolve()  # VICE's cwd is the ROM dir — relative paths would silently fail

    rom_dir = (Path.home() / ".c64devk" / "roms")
    if not (rom_dir / "kernal").exists():
        _setup_roms(rom_dir)

    init_addr = _read_init_from_prg(prg_path)
    sound_args = ["-sound", "-sounddev", "alsa"] if sound else ["+sound"]
    args = [
        vice,
        "-remotemonitor",
        *sound_args,
        "-autostartprgmode", "1",
        "-autostart", str(prg_path),
        "-keybuf", f"sys{init_addr}\r",
    ]
    return subprocess.Popen(args, cwd=str(rom_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def launch_debug(prg_path: Path) -> subprocess.Popen | None:
    vice = find_vice()
    if not vice:
        print("Error: VICE (x64sc) not found", file=sys.stderr)
        return None

    prg_path = Path(prg_path).resolve()

    args = [
        vice,
        "-remotemonitor",
        "-moncommands", '"break @$0000"',
        "+sound",
        str(prg_path),
    ]
    return subprocess.Popen(args)


def parse_symbols(path: Path) -> dict[str, int]:
    """Parse ACME --symbollist output into {label: address} dict."""
    symbols: dict[str, int] = {}
    if not path.exists():
        return symbols
    pattern = re.compile(r"^\s*(\S+)\s*=\s*\$([0-9A-Fa-f]+)")
    for line in path.read_text().splitlines():
        m = pattern.match(line)
        if m:
            symbols[m.group(1)] = int(m.group(2), 16)
    return symbols


# --- Monitor response parsing -------------------------------------------
# The VICE text monitor pollutes responses with extra material:
#   - after a breakpoint stop, the first response carries a stop message
#     ("#1 (Stop on exec ...)") and a disassembly line (".C:xxxx OP ..."),
#   - dump rows trail an ASCII column that can contain hex-looking
#     character pairs (e.g. bytes $41 $42 render as "AB").
# The parsers below are layout-aware so none of that leaks into data.

_DUMP_ADDR_RE = re.compile(r">C:([0-9a-fA-F]{4})")
_HEX_PAIR_CHARS = "0123456789abcdefABCDEF"


def _parse_memory_dump(resp: str, start: int, wanted: int) -> bytes:
    """Parse VICE monitor memory-dump output into raw bytes.

    Every dump row is labelled with its start address and rows are
    contiguous, so the real byte count of each row is known exactly
    (row size = address delta, trimmed at the requested range end).
    Anything after that count is display noise (breakpoint preambles,
    disassembly lines, the ASCII column) and is ignored.  Rows of
    16 or 32 bytes are both handled.
    """
    if wanted <= 0:
        return b""
    end = start + wanted
    rows: list[tuple[int, list[str]]] = []
    for line in resp.split("\n"):
        for m in _DUMP_ADDR_RE.finditer(line):
            addr = int(m.group(1), 16)
            tail = line[m.end():]
            toks = [t for t in tail.split()
                    if len(t) == 2 and all(c in _HEX_PAIR_CHARS for c in t)]
            rows.append((addr, toks))
    if not rows:
        return b""
    row = 16
    if len(rows) >= 2:
        row = max(16, rows[1][0] - rows[0][0])
    out = bytearray()
    for i, (addr, toks) in enumerate(rows):
        if i + 1 < len(rows):
            count = min(rows[i + 1][0] - addr, end - addr)
        else:
            count = max(0, end - addr)
        count = min(count, max(row, len(toks)))
        for t in toks[:count]:
            out.append(int(t, 16))
        if len(out) >= wanted:
            break
    return bytes(out[:wanted])


_REG_VALUE_RE = re.compile(
    r"^\.;([0-9a-fA-F]{4})\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})"
    r"\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})")
_REG_TOKEN_RE = re.compile(r"([A-Za-z]{1,3})=([0-9a-fA-F]+)")


def _parse_registers(resp: str) -> dict[str, int]:
    """Parse VICE monitor `r` output into {REG: value}.

    Current VICE format: value line starts '.;PC AA XX YY SP ...'
    (PC first, then A, X, Y, SP).  Older formats use 'PC=xxxx A=xx'
    tokens, handled as a fallback.
    """
    for line in resp.split("\n"):
        m = _REG_VALUE_RE.match(line.strip())
        if m:
            pc, a, x, y, sp = (int(g, 16) for g in m.groups())
            return {"PC": pc, "A": a, "X": x, "Y": y, "SP": sp}
    vals: dict[str, int] = {}
    for line in resp.split("\n"):
        for m in _REG_TOKEN_RE.finditer(line):
            vals[m.group(1).upper()] = int(m.group(2), 16)
    return vals


# --- Window capture (visual verification) --------------------------------
# VICE always opens an X11 window, even "headless" — the emulator's video
# output lives in the innermost child window of the top-level "x64sc"
# window.  Grabbing that area with Xlib gives an exact PNG of the frame
# the user sees, no external screenshot tools needed.


def _walk_windows(win):
    yield win
    for child in win.query_tree().children:
        yield from _walk_windows(child)


def _window_for_pid(disp, pid: int):
    """Window object for the newest x64sc window owned by `pid`."""
    try:
        out = subprocess.run(
            ["xdotool", "search", "--pid", str(pid), "--class", "x64sc"],
            capture_output=True, text=True, timeout=5)
        ids = [int(x) for x in out.stdout.split() if x.strip().isdigit()]
        if ids:
            return disp.create_resource_object("window", ids[-1])
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return None


def find_vice_window(pid: int | None = None):
    """Find the innermost video window of a VICE instance.

    When `pid` is given (the PID of the VICE process we launched), the
    window is matched by owner — the only reliable choice when several
    VICE windows are open.  Otherwise the newest 'x64sc' window in the
    tree is used.  Returns (display, window) or (None, None).
    """
    try:
        from Xlib import display as xdisplay
    except ImportError:
        return None, None
    try:
        disp = xdisplay.Display()
    except Exception:
        return None, None

    win = None
    if pid is not None:
        win = _window_for_pid(disp, pid)
    if win is None:
        # newest VICE process owns the newest window — try its PID first
        try:
            out = subprocess.run(["pgrep", "-n", "x64sc"],
                                 capture_output=True, text=True, timeout=5)
            newest = out.stdout.strip()
            if newest.isdigit():
                win = _window_for_pid(disp, int(newest))
        except (subprocess.SubprocessError, OSError):
            pass
    if win is None:
        # last resort: newest x64sc-classed window in the tree
        root = disp.screen().root
        cands = []
        for w in _walk_windows(root):
            try:
                wm = w.get_wm_class()
                if wm and wm[0].lower() == "x64sc" and w.get_geometry().width > 100:
                    cands.append(w)
            except Exception:
                pass
        if cands:
            win = cands[-1]
    if win is None:
        return None, None

    while True:
        kids = win.query_tree().children
        if not kids:
            return disp, win
        win = kids[-1]


def capture_vice_window(path, pid: int | None = None) -> bool:
    """Capture the VICE video window to a PNG at `path`.

    Returns True on success.  Requires python-xlib and PIL (Pillow).
    `pid` selects the VICE instance when several windows are open.
    """
    disp, win = find_vice_window(pid)
    if win is None:
        return False
    try:
        from PIL import Image
    except ImportError:
        return False
    geo = win.get_geometry()
    raw = win.get_image(0, 0, geo.width, geo.height, 2, 0xFFFFFFFF)
    img = Image.frombytes("RGB", (geo.width, geo.height), raw.data,
                          "raw", "BGRX")
    img.save(str(path))
    return True


class ViceMonitor:
    def __init__(self, host: str = "127.0.0.1", port: int = REMOTE_MONITOR_PORT):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None

    def connect(self, timeout: float = 5.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(timeout)
                self._sock.connect((self.host, self.port))
                return True
            except (ConnectionRefusedError, OSError):
                if self._sock:
                    self._sock.close()
                time.sleep(0.5)
        return False

    def send(self, cmd: str) -> str:
        if not self._sock:
            return ""
        self._sock.sendall((cmd + "\n").encode())
        return self._read_response()

    def _read_response(self, timeout: float = 2.0) -> str:
        """Read response from VICE monitor.

        VICE appends a prompt '(C:$XXXX) ' without a trailing newline
        after every response. We read the main response body first,
        then drain the trailing prompt to keep the socket clean."""
        if not self._sock:
            return ""
        self._sock.settimeout(timeout)
        data = bytearray()
        try:
            chunk = self._sock.recv(4096)
            if not chunk:
                return ""
            data.extend(chunk)
        except socket.timeout:
            return ""
        self._sock.settimeout(0.15)
        try:
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
        except (socket.timeout, OSError):
            pass
        return data.decode("utf-8", errors="replace").strip()

    def read_memory(self, addr: int, length: int = 1) -> bytes:
        """Read `length` bytes via the monitor's memory dump.

        VICE dumps a fixed window per `m` command, so large reads are
        chunked; each dump is parsed with address arithmetic (immune to
        breakpoint preambles and ASCII columns)."""
        result = bytearray()
        while len(result) < length:
            chunk_addr = addr + len(result)
            resp = self.send(f"m ${chunk_addr:04X}")
            chunk = _parse_memory_dump(resp, chunk_addr, length - len(result))
            if not chunk:
                break               # no progress — avoid spinning forever
            result.extend(chunk)
        return bytes(result[:length])

    def write_memory(self, addr: int, value: int) -> None:
        self.send(f"> ${addr:04X} ${value:02X}")

    def peek(self, addr: int, length: int = 1) -> int:
        """Read a value from memory. Returns int for 1 byte, or combine for multi-byte."""
        data = self.read_memory(addr, length)
        val = 0
        for i, b in enumerate(data):
            val |= b << (i * 8)
        return val

    def peek16(self, addr: int) -> int:
        """Read 16-bit little-endian value."""
        return self.peek(addr, 2)

    def poke(self, addr: int, value: int) -> None:
        self.write_memory(addr, value & 0xFF)

    def poke16(self, addr: int, value: int) -> None:
        self.write_memory(addr, value & 0xFF)
        self.write_memory(addr + 1, (value >> 8) & 0xFF)

    def get_register(self, reg: str) -> int:
        resp = self.send("r")
        return _parse_registers(resp).get(reg.upper(), 0)

    def set_breakpoint(self, addr: int) -> None:
        self.send(f"break ${addr:04X}")

    def disable_breakpoints(self) -> None:
        """Delete all possible breakpoints (1-5)."""
        if not self._sock:
            return
        for i in range(1, 6):
            self._sock.sendall(f"delete {i}\n".encode())
            self._sock.settimeout(0.3)
            try:
                self._sock.recv(4096)
            except (socket.timeout, OSError):
                pass
        self._drain()

    def continue_execution(self) -> None:
        self.send("g")

    def _drain(self) -> None:
        """Drain any pending data from socket. Restores original timeout."""
        if not self._sock:
            return
        old_timeout = self._sock.gettimeout()
        try:
            self._sock.settimeout(0.1)
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
        except (socket.timeout, OSError):
            pass
        finally:
            self._sock.settimeout(old_timeout)

    def step_frame(self, breakpoint_addr: int, timeout: float = 5.0) -> bool:
        """Advance one frame by breaking at the given address.

        Uses the raw VICE-monitor pattern: delete old breakpoints,
        sleep briefly, set a new breakpoint, sleep, resume with 'g',
        sleep, and drain the socket.  Returns True on success."""
        if not self._sock:
            return False
        self._drain()
        self.disable_breakpoints()
        self._sock.sendall(f"break ${breakpoint_addr:04X}\n".encode())
        time.sleep(0.2)
        self._drain()
        self._sock.sendall(b"g\n")
        time.sleep(0.3)
        self._drain()
        return True

    def advance_frames(self, count: int, main_loop_addr: int, timeout_per_frame: float = 5.0) -> bool:
        """Advance N frames by stepping through breakpoints at main_loop.

        Returns True if all frames advanced successfully."""
        self._drain()
        self.disable_breakpoints()
        for _ in range(count):
            if not self.step_frame(main_loop_addr, timeout_per_frame):
                self.disable_breakpoints()
                return False
        self.disable_breakpoints()
        return True

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def screenshot(self, path, pid: int | None = None) -> bool:
        """Capture the VICE video window to a PNG at `path`.

        Lets a model visually verify the running game: launch with
        -remotemonitor (VICE opens an X11 window even headless), then
        call this to grab the exact frame.  Pass the launched process's
        PID to target the right window when several VICE instances are
        open.  Returns True on success.
        """
        return capture_vice_window(path, pid)

    def kill_vice(self, process: subprocess.Popen | None) -> None:
        """Kill the VICE process group safely. SIGTERM first, then SIGKILL."""
        self.disconnect()
        if not process or process.poll() is not None:
            return
        try:
            pid = process.pid
            if pid:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    process.wait(timeout=3)
                except (ProcessLookupError, subprocess.TimeoutExpired, PermissionError):
                    pass
        finally:
            try:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
