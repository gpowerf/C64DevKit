"""Tests for the audio fingerprint analyzer (audio_diag).

The analyzer's job is the "ears": turn a WAV into per-window
(rms, peak_hz, centroid_hz, tonality) rows.  These tests synthesize
known signals (a 300 Hz tone, silence) and check the fingerprints
match the ground truth.
"""

import math
import struct
import wave
from pathlib import Path

import pytest

from c64devk.audio_diag import analyze_wav, print_fingerprint

RATE = 44100


def _write_wav(path: Path, samples) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(s))))
                               for s in samples))


@pytest.fixture()
def tone_wav(tmp_path: Path) -> Path:
    p = tmp_path / "tone.wav"
    t = 1.0
    n = int(RATE * t)
    samples = [6000 * math.sin(2 * math.pi * 300 * i / RATE) for i in range(n)]
    _write_wav(p, samples)
    return p


@pytest.fixture()
def silent_wav(tmp_path: Path) -> Path:
    p = tmp_path / "silence.wav"
    _write_wav(p, [0] * RATE)
    return p


def test_tone_fingerprint(tone_wav: Path):
    rows = analyze_wav(tone_wav)
    assert rows, "a 1 s tone must produce windows"
    peak = max(rows, key=lambda r: r[1])
    assert peak[1] > 100, "tone must register as loud"
    assert abs(peak[2] - 300) < 60, f"peak {peak[2]:.0f} Hz != ~300 Hz"
    assert peak[4] < 0.2, "a pure tone is tonal, not noise"


def test_silence_fingerprint(silent_wav: Path):
    rows = analyze_wav(silent_wav)
    assert rows
    assert all(r[1] == 0 and r[4] == 1.0 for r in rows), "silence must be flat"


def test_tonality_separates_noise_and_tone(tmp_path: Path):
    np = pytest.importorskip("numpy")
    noise_path = tmp_path / "noise.wav"
    rng = np.random.default_rng(42)
    samples = (3000 * rng.standard_normal(RATE)).astype(float)
    _write_wav(noise_path, samples)
    nf = analyze_wav(noise_path)
    p = tmp_path / "tone.wav"
    _write_wav(p, [6000 * math.sin(2 * math.pi * 300 * i / RATE) for i in range(RATE)])
    tr = analyze_wav(p)
    noise_tonality = sum(r[4] for r in nf) / len(nf)
    tone_tonality = sum(r[4] for r in tr) / len(tr)
    assert noise_tonality > tone_tonality * 2, (
        f"noise ({noise_tonality:.4f}) should be more tonal-flat than a "
        f"pure tone ({tone_tonality:.4f})")


def test_fingerprint_prints(capsys: pytest.CaptureFixture, tone_wav: Path):
    print_fingerprint(analyze_wav(tone_wav))
    out = capsys.readouterr().out
    assert "fingerprint" in out
    assert "peak=" in out
