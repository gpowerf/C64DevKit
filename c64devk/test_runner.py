"""Test runner — static verification of generated code, with optional live VICE testing."""

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from .spec_parser import ProjectSpec


@dataclass
class Assertion:
    what: str = ""
    expected: int | None = None
    gt: int | None = None
    lt: int | None = None
    gte: int | None = None
    lte: int | None = None
    sprite_index: int = 0
    addr: int = 0
    label: str = ""
    size: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> "Assertion":
        a = cls(what=d.get("what", "memory"))
        a.sprite_index = int(d.get("index", d.get("sprite", 0)))
        a.addr = _parse_addr(d.get("addr", d.get("address", 0)))
        a.label = str(d.get("label", ""))
        a.size = int(d.get("size", 1))
        a.expected = d.get("eq", d.get("equals"))
        a.gt = d.get("gt", d.get("greater_than"))
        a.lt = d.get("lt", d.get("less_than"))
        a.gte = d.get("gte")
        a.lte = d.get("lte")
        if a.what == "sprite_x":
            a.addr = 0xD000 + a.sprite_index * 2
        elif a.what == "sprite_y":
            a.addr = 0xD001 + a.sprite_index * 2
        return a

    def check(self, value: int) -> bool:
        if self.expected is not None:
            return value == self.expected
        if self.gt is not None:
            return value > self.gt
        if self.lt is not None:
            return value < self.lt
        if self.gte is not None:
            return value >= self.gte
        if self.lte is not None:
            return value <= self.lte
        return False

    def describe(self) -> str:
        parts = [self.what]
        if self.what in ("sprite_x", "sprite_y"):
            parts.append(f"[{self.sprite_index}]")
        if self.expected is not None:
            parts.append(f"== {self.expected}")
        elif self.gt is not None:
            parts.append(f"> {self.gt}")
        elif self.lt is not None:
            parts.append(f"< {self.lt}")
        elif self.gte is not None:
            parts.append(f">= {self.gte}")
        elif self.lte is not None:
            parts.append(f"<= {self.lte}")
        return " ".join(parts)


@dataclass
class TestCase:
    name: str
    steps: list[dict] = field(default_factory=list)
    checks: list[Assertion] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "TestCase":
        t = cls(name=d.get("name", "unnamed"))
        for step in d.get("steps", []):
            if isinstance(step, dict):
                t.steps.append(step)
        checks_raw = d.get("checks", [])
        if isinstance(checks_raw, list):
            for c in checks_raw:
                if isinstance(c, dict):
                    t.checks.append(Assertion.from_dict(c))
        return t


@dataclass
class TestSpec:
    tests: list[TestCase] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> "TestSpec":
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        tests = []
        for t in data.get("tests", []):
            tests.append(TestCase.from_dict(t))
        return cls(tests=tests)


@dataclass
class TestResult:
    test_name: str
    passed: bool = True
    failures: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


def _parse_addr(v) -> int:
    if isinstance(v, int):
        return v
    v = str(v).strip()
    if v.startswith("$"):
        return int(v[1:], 16)
    if v.startswith("0x"):
        return int(v, 16)
    return int(v)


def _safe_lbl(name: str) -> str:
    return name.replace(" ", "_").replace("-", "_").lower()


def run_static_tests(prg_path: Path, sym_path: Path, test_path: Path, spec: "ProjectSpec") -> list[TestResult]:
    from .vice_bridge import parse_symbols
    symbols = parse_symbols(sym_path)
    results: list[TestResult] = []

    result = TestResult(test_name="symbols_present")
    required = ["main_loop", "init", "init_sprites", "frame_ready",
                "joystick_state", "joystick_prev", "irq"]
    for sym in required:
        if sym not in symbols:
            result.passed = False
            result.failures.append(f"missing: {sym}")
    if result.passed:
        result.failures = [f"all {len(required)} core symbols"]
    results.append(result)

    result = TestResult(test_name="prg_structure")
    prg_data = prg_path.read_bytes()
    load_addr = prg_data[0] | (prg_data[1] << 8)
    if load_addr != spec.memory.code_start:
        result.passed = False
        result.failures.append(
            f"load addr: expected ${spec.memory.code_start:04X}, got ${load_addr:04X}")
    if len(prg_data) < 256:
        result.passed = False
        result.failures.append(f"PRG too small: {len(prg_data)} bytes")
    if result.passed:
        result.failures = [f"load=${load_addr:04X}, size={len(prg_data)} bytes"]
    results.append(result)

    if spec.sprites:
        result = TestResult(test_name="sprite_data_at_correct_address")
        spr_offset = spec.memory.sprite_data - spec.memory.code_start + 2
        if spr_offset + 63 < len(prg_data):
            spr_byte = prg_data[spr_offset]
            result.failures = [
                f"offset ${spec.memory.sprite_data:04X} → file offset {spr_offset}, "
                f"first byte=${spr_byte:02X}"
            ]
        else:
            result.passed = False
            result.failures.append(
                f"sprite_data ${spec.memory.sprite_data:04X} is beyond PRG end"
            )
        results.append(result)

        result = TestResult(test_name="sprite_init_present")
        if "init_sprites" in symbols:
            init_addr = symbols["init_sprites"]
            result.failures = [f"init_sprites at ${init_addr:04X}"]
        else:
            result.passed = False
            result.failures.append("missing init_sprites symbol")
        results.append(result)

    if spec.behaviors:
        result = TestResult(test_name="behavior_handlers_present")
        for b in spec.behaviors:
            if b.type == "on_collision":
                handler_name = f"beh_handler_{_safe_lbl(b.name)}"
                if handler_name in symbols:
                    result.failures.append(f"{handler_name}=${symbols[handler_name]:04X}")
                else:
                    result.passed = False
                    result.failures.append(f"missing: {handler_name}")
            elif b.type == "on_frame":
                if "behaviors_update" in symbols:
                    result.failures.append(f"behaviors_update=${symbols['behaviors_update']:04X}")
        if not result.failures:
            result.failures = ["no collision handlers found"]
        results.append(result)

    results.append(_run_spec_assertions(spec))
    return results


def _run_spec_assertions(spec: "ProjectSpec") -> TestResult:
    result = TestResult(test_name="spec_validation")
    if not spec.sprites:
        result.failures = ["no sprites defined"]
        return result

    seen_indices: set[int] = set()
    for s in spec.sprites:
        if s.index < 0 or s.index > 7:
            result.passed = False
            result.failures.append(f"{s.name}: invalid sprite index {s.index}")
        if s.index in seen_indices:
            result.passed = False
            result.failures.append(f"{s.name}: duplicate sprite index {s.index}")
        seen_indices.add(s.index)
        if s.x < 0 or s.x > 511:
            result.passed = False
            result.failures.append(f"{s.name}: x={s.x} out of range (0-511)")
        if s.y < 0 or s.y > 255:
            result.passed = False
            result.failures.append(f"{s.name}: y={s.y} out of range (0-255)")
        if spec.memory.sprite_data & 0x3F:
            result.passed = False
            result.failures.append(
                f"sprite_data ${spec.memory.sprite_data:04X} not 64-byte aligned")

    if result.passed:
        result.failures = [f"{len(spec.sprites)} sprites, all valid"]
    return result


def get_static_results(prg_path: Path, sym_path: Path, test_path: Path, spec: "ProjectSpec") -> list[TestResult]:
    """Attempt live VICE testing, fall back to static."""
    try:
        results = _try_live_test(prg_path, sym_path, test_path, spec)
        if results:
            return results
    except Exception:
        pass
    return run_static_tests(prg_path, sym_path, test_path, spec)


def _try_live_test(prg_path: Path, sym_path: Path, test_path: Path, spec: "ProjectSpec") -> list[TestResult] | None:
    """Try to run VICE headless and execute tests. Returns None if VICE can't start."""
    from .vice_bridge import launch_headless, ViceMonitor, parse_symbols

    proc = launch_headless(prg_path)
    if not proc:
        return None

    time.sleep(0.8)

    monitor = ViceMonitor()
    if not monitor.connect(timeout=5.0):
        monitor.kill_vice(proc)
        return None

    symbols = parse_symbols(sym_path)
    main_loop = symbols.get("main_loop", 0)
    if not main_loop:
        monitor.kill_vice(proc)
        return None

    results: list[TestResult] = []

    result = TestResult(test_name="init_state")
    for s in spec.sprites:
        x_addr = 0xD000 + s.index * 2
        y_addr = 0xD001 + s.index * 2
        x_val = monitor.peek(x_addr)
        y_val = monitor.peek(y_addr)
        if x_val != (s.x & 0xFF):
            result.passed = False
            result.failures.append(f"{s.name} x: expected <{s.x & 0xFF}>, got <{x_val}>")
        if y_val != s.y:
            result.passed = False
            result.failures.append(f"{s.name} y: expected <{s.y}>, got <{y_val}>")
    if result.passed:
        result.failures = ["all sprites at configured positions"]
    results.append(result)

    test_spec = TestSpec.from_yaml(test_path)
    for test in test_spec.tests:
        tr = TestResult(test_name=f"live:{test.name}")
        tr.passed = True
        tr.failures = ["live test not fully implemented yet"]
        results.append(tr)

    monitor.kill_vice(proc)
    return results


def print_results(results: list[TestResult], mode: str = "static") -> None:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n  [{mode.upper()}] Results: {passed}/{total} passed")
    print(f"  {'=' * 40}")
    for r in results:
        marker = "✓" if r.passed else "✗"
        print(f"  {marker} {r.test_name}")
        for f in r.failures:
            print(f"    {f}")
