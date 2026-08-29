"""c64devk audio diagnostics — "ears" for headless agent-driven sound work.

Headless agents cannot hear.  This module records the REAL PCM output of
a VICE session (VICE -sound via ALSA) while a scripted monitor scenario
drives the game (a still vs a moving death, by default), then
fingerprints the audio — per-window RMS, dominant peak, spectral
centroid and tonality — so two sound states can be compared
objectively (alarm vs boom, note sequences, masked tails).

Typical use:

    c64devk audio -p games/dodge --scene still --out /tmp/kill_still.wav
    c64devk audio -p games/dodge --scene moving --out /tmp/kill_moving.wav
    # then diff the printed fingerprints

Pair it with `c64devk shot` for the visual side — run the whole
toolchain with a VISION-CAPABLE model so the screenshots can actually
be seen (see the README note "Agent verification").

Requirements: x64sc with a working ALSA output device, `arecord`,
numpy (analysis only — degrades gracefully without it).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .vice_bridge import ViceMonitor, launch_headless, parse_symbols

# ---------------------------------------------------------------------------
# Monitoring helpers (same wire protocol as the test harness)
# ---------------------------------------------------------------------------

class _Scene:
    """Drives a scripted death scenario via the VICE remote monitor."""

    def __init__(self, prg: Path, symbols: dict):
        self.prg = prg
        self.sym = symbols

    def addr(self, label: str) -> int:
        try:
            return self.sym[label]
        except KeyError:
            raise SystemExit(f"no symbol named '{label}' in the build") from None

    def connect(self, retries: int = 5) -> tuple[subprocess.Popen | None, "ViceMonitor | None"]:
        # the headless autostart/keybuf race means some launches never
        # start the program — retry with a fresh process until we can
        # park inside the splash loop
        for attempt in range(retries):
            proc = launch_headless(self.prg, sound=True)
            if proc is None:
                return None, None
            time.sleep(5.0)
            mon = ViceMonitor()
            if mon.connect(timeout=5.0):
                mon.send("")
                if self._park(mon, "splash_wait"):
                    return proc, mon
            self._kill(proc)
            print(f"[audio] launch {attempt + 1} missed the splash, retrying",
                  file=sys.stderr)
        return None, None

    @staticmethod
    def _kill(proc: subprocess.Popen | None) -> None:
        if not proc or proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def _park(self, mon: ViceMonitor, label: str, timeout: float = 6.0) -> bool:
        """Break+g back-to-back at `label` — the monitor stops on entry."""
        mon._sock.sendall(f"break ${self.addr(label):04X}\n".encode())
        mon._sock.sendall(b"g\n")
        ok = self._wait_stop(mon, timeout)
        mon.disable_breakpoints()
        time.sleep(0.25)
        return ok

    @staticmethod
    def _wait_stop(mon: ViceMonitor, timeout: float = 6.0) -> bool:
        import socket

        mon._sock.settimeout(0.2)
        buf = b""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                buf += mon._sock.recv(4096)
            except (socket.timeout, OSError):
                pass
            if b"Stop on exec" in buf:
                return True
        return False

    def enter_playing(self, mon: ViceMonitor) -> bool:
        mon.poke(self.addr("state"), 0)          # harness-style splash exit
        time.sleep(1.0)
        return self._park(mon, "game_logic")


def _record(duration: float, out: Path) -> subprocess.Popen | None:
    if shutil.which("arecord") is None:
        print("audio: 'arecord' not found (ALSA utils) — cannot capture PCM",
              file=sys.stderr)
        return None
    handle = open(out, "wb")
    rec = subprocess.Popen(
        ["arecord", "-D", "default", "-f", "S16_LE", "-r", "44100",
         "-c", "1", "-t", "wav", "-d", str(int(duration)), "-"],
        stdout=handle, stderr=subprocess.DEVNULL)
    return rec


def _shutdown(proc: subprocess.Popen | None, rec: subprocess.Popen | None) -> None:
    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            pass
    if rec is not None:
        try:
            rec.wait(timeout=5)
        except Exception:
            rec.kill()


def _drive(project: Path, scene: str, duration: float, out: Path) -> Path:
    build_dir = project / "output" / "build"
    prg = build_dir / f"{project.name}.prg"
    sym = build_dir / (prg.name.replace(".prg", ".sym"))
    if not prg.exists():
        raise SystemExit(f"audio: build first — no {prg}")
    symbols = parse_symbols(sym)
    driver = _Scene(prg, symbols)
    proc, mon = driver.connect()
    if mon is None:
        raise SystemExit("audio: could not start a VICE session with sound")
    try:
        rec = None
        if not driver.enter_playing(mon):
            raise SystemExit("audio: game never reached the play loop")
        ex = mon.peek(0xD002)
        ey = mon.peek(0xD001)
        nx, ny = (ex + 4) & 0xFF, (ey + 2) & 0xFF
        if scene == "moving":
            # a few parked frames with position deltas so the engine
            # (thrust rumble) actually sounds before the kill
            for j in range(10):
                px = (nx + j) & 0xFF
                mon.poke(0xD000, px)
                mon.poke(0xD001, ny)
                mon.poke(driver.addr("prev_x"), (px - 1) & 0xFF)
                mon.poke(driver.addr("prev_y"), ny)
                mon.poke(driver.addr("hit_timer"), 0)
                driver._park(mon, "game_logic")
        mon.poke(0xD000, nx)
        mon.poke(0xD001, ny)
        mon.poke(driver.addr("hit_timer"), 0)
        mon.poke(driver.addr("pwr_avail"), 0)    # level-1 style: no charge
        mon.poke(driver.addr("prev_x"), (nx - 1) & 0xFF if scene == "moving" else nx)
        mon.poke(driver.addr("prev_y"), ny)
        print(f"[audio] armed {scene}; free-running {duration:.0f}s")
        rec = _record(duration, out)
        mon.send("g")                            # free run through the kill
        time.sleep(duration - 0.5)
        # confirm the kill actually happened
        driver._park(mon, "game_logic")
        lives = mon.peek(driver.addr("lives"))
        if lives is not None and lives < 3:
            print(f"[audio] kill confirmed (lives={lives})")
        elif lives is None:
            print("[audio] could not verify the kill (race?) — capture kept anyway",
                  file=sys.stderr)
        else:
            print(f"[audio] WARNING: no kill detected (lives={lives})",
                  file=sys.stderr)
    finally:
        _shutdown(proc, rec)
    return out


# ---------------------------------------------------------------------------
# Analysis — the spectrogram fingerprint (the "ear")
# ---------------------------------------------------------------------------

def analyze_wav(path: Path, win: int = 1024, step: int = 882) -> list[tuple[float, float, float, float, float]]:
    """Per-window (t, rms, peak_hz, centroid_hz, tonality) fingerprint."""
    try:
        import numpy as np
        import wave as wavemod
    except ImportError:
        raise SystemExit("audio: analysis needs numpy (pip install numpy)")

    w = wavemod.open(str(path))
    n = w.getnframes()
    rate = w.getframerate()
    data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64)
    w.close()
    rows = []
    for i in range(0, len(data) - win, step):
        seg = data[i:i + win]
        if np.max(np.abs(seg)) < 40:
            rows.append((i / rate, 0.0, 0.0, 0.0, 1.0))
            continue
        wf = seg * np.hanning(win)
        sp = np.abs(np.fft.rfft(wf))
        fr = np.fft.rfftfreq(win, 1 / rate)
        rows.append((
            i / rate,
            float(np.sqrt(np.mean(wf ** 2))),
            float(fr[np.argmax(sp)]),
            float(np.sum(fr * sp ** 2) / np.sum(sp ** 2)),
            float(np.exp(np.mean(np.log(sp + 1e-9))) / (np.mean(sp) + 1e-9)),
        ))
    return rows


def print_fingerprint(rows: list[tuple[float, float, float, float, float]]) -> None:
    """Print a compact event summary: cluster loud windows, show the
    per-event blast profile (t0, duration, max rms, peak Hz, tonality)."""
    loud = [r for r in rows if r[1] > 100]
    print("\nfingerprint (events = loud windows clustered < 0.6 s apart):")
    if rows:
        peak = max(rows, key=lambda r: r[1])
        print(f"  loudest window: t={peak[0]:.2f}s  rms={peak[1]:.0f}  "
              f"peak={peak[2]:.0f} Hz  tonality={peak[4]:.3f}")
    else:
        print("  (no windows)")
    if not loud:
        print("  (no loud events captured — the scene may not have fired)")
        return
    events: list[list[tuple[float, float, float, float, float]]] = []
    for r in loud:
        if events and r[0] - events[-1][-1][0] < 0.6:
            events[-1].append(r)
        else:
            events.append([r])
    for i, ev in enumerate(events, 1):
        t0, t1 = ev[0][0], ev[-1][0]
        mx = max(ev, key=lambda r: r[1])
        print(f"  {i}. event t={t0:6.2f}-{t1:6.2f}s  dur={t1 - t0:4.2f}s  "
              f"maxrms={mx[1]:6.0f}  peak={mx[2]:7.0f} Hz  "
              f"tonality={(sum(r[4] for r in ev) / len(ev)):.3f}")


def print_trace(rows: list[tuple[float, float, float, float, float]],
                window_before: float = 0.35, window_after: float = 0.9) -> None:
    """Print the raw per-window trace around the loudest event
    (for hand-reading note sequences)."""
    if not rows:
        return
    peak = max(rows, key=lambda r: r[1])
    band = [r for r in rows if peak[0] - window_before <= r[0] <= peak[0] + window_after]
    print(f"\ntrace around t={peak[0]:.2f}s:")
    print("  t      rms    peakHz  centroid  tonality")
    for r in band:
        if r[1] > 20:
            print(f"  {r[0]:6.2f} {r[1]:6.0f} {r[2]:7.0f} {r[3]:8.0f}  {r[4]:.3f}")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def run(project: Path, scene: str, out: Path, duration: float,
        analyze: bool) -> None:
    if shutil.which("arecord") is None:
        raise SystemExit("audio: 'arecord' not found — install alsa-utils")
    if shutil.which("x64sc") is None:
        raise SystemExit("audio: x64sc not found — install vice")
    wav = out.resolve()
    wav.parent.mkdir(parents=True, exist_ok=True)
    _drive(project, scene, duration, wav)
    if analyze:
        try:
            rows = analyze_wav(wav)
        except SystemExit as e:
            print(e)
            return
        print(f"\nwav: {wav}")
        print_fingerprint(rows)
        print_trace(rows)
