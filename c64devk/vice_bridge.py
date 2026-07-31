"""VICE bridge — launch emulator and communicate via remote monitor."""

import re
import os
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

    rom_dir = (Path.home() / ".c64devk" / "roms")
    if not (rom_dir / "kernal").exists():
        _setup_roms(rom_dir)

    args = [vice]
    if autostart:
        args += [
            "-autostartprgmode", "1",
            "-autostart", str(prg_path),
            "-keybuf", "run\n",
        ]
    else:
        args.append(str(prg_path))

    if headless:
        args += ["-remotemonitor", "+sound"]

    print(f"  Launching: {vice}")
    print(f"  PRG: {prg_path}")
    return subprocess.Popen(args, cwd=str(rom_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           start_new_session=True)


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


def launch_headless(prg_path: Path) -> subprocess.Popen | None:
    vice = find_vice()
    if not vice:
        print("Error: VICE (x64sc) not found", file=sys.stderr)
        return None

    rom_dir = (Path.home() / ".c64devk" / "roms")
    if not (rom_dir / "kernal").exists():
        _setup_roms(rom_dir)

    args = [
        vice,
        "-remotemonitor",
        "+sound",
        "-autostartprgmode", "1",
        "-autostart", str(prg_path),
        "-keybuf", "run\n",
    ]
    return subprocess.Popen(args, cwd=str(rom_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch_debug(prg_path: Path) -> subprocess.Popen | None:
    vice = find_vice()
    if not vice:
        print("Error: VICE (x64sc) not found", file=sys.stderr)
        return None

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
        if not self._sock:
            return ""
        self._sock.settimeout(timeout)
        data = bytearray()
        while True:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
                if b"\n" in data:
                    break
            except socket.timeout:
                break
            except OSError:
                break
        return data.decode("utf-8", errors="replace").strip()

    def read_memory(self, addr: int, length: int = 1) -> bytes:
        resp = self.send(f"m ${addr:04X}")
        result = bytearray()
        for line in resp.split("\n"):
            parts = line.strip().split()
            for p in parts:
                if len(p) == 2 and all(c in "0123456789ABCDEFabcdef" for c in p):
                    result.append(int(p, 16))
                    if len(result) >= length:
                        return bytes(result)
        return bytes(result)

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

    def get_register(self, reg: str) -> int:
        resp = self.send("r")
        for line in resp.split("\n"):
            if "PC" in line:
                for part in line.split():
                    if part.startswith(reg.upper() + "="):
                        return int(part.split("=")[1].strip(";"), 16)
        return 0

    def set_breakpoint(self, addr: int) -> None:
        self.send(f"break ${addr:04X}")

    def disable_breakpoints(self) -> None:
        self.send("break")
        self.send("delete 1-99")

    def continue_execution(self) -> None:
        self.send("c")

    def advance_frames(self, count: int, main_loop_addr: int, timeout_per_frame: float = 3.0) -> bool:
        """Advance N frames by setting a breakpoint at main_loop and continuing.

        Returns True if all frames advanced successfully."""
        self.disable_breakpoints()
        self.set_breakpoint(main_loop_addr)
        for _ in range(count):
            self.continue_execution()
            time.sleep(0.15)
            if not self._wait_for_break(timeout_per_frame):
                self.disable_breakpoints()
                return False
        self.disable_breakpoints()
        return True

    def _wait_for_break(self, timeout: float) -> bool:
        """Wait until VICE reports it has stopped (at a breakpoint)."""
        self._sock.settimeout(timeout)
        try:
            self._sock.recv(1024)  # consume any pending data
        except (socket.timeout, OSError):
            pass
        return True

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def kill_vice(self, process: subprocess.Popen | None) -> None:
        """Kill the VICE process and disconnect."""
        self.disconnect()
        if process:
            try:
                process.kill()
                process.wait(timeout=2)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
