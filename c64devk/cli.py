"""CLI entry point for c64devk."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import VERSION
from .config import (
    get_framework_dir,
    get_macros_dir,
    get_project_template_dir,
    get_output_src_dir,
    get_output_build_dir,
)
from .spec_parser import ProjectSpec
from .codegen import run_build


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="c64devk",
        description="Spec-driven C64 development framework",
    )
    parser.add_argument("--version", action="version", version=f"c64devk v{VERSION}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Check tool dependencies")
    p_new = sub.add_parser("new", help="Scaffold a new C64 project")
    p_new.add_argument("name", help="Project name")
    p_new.add_argument("--dir", "-d", default=".", help="Parent directory")
    p_build = sub.add_parser("build", help="Build .prg from specs")
    p_build.add_argument("--project", "-p", default=".", help="Project directory")
    p_run = sub.add_parser("run", help="Build and launch in VICE")
    p_run.add_argument("--project", "-p", default=".", help="Project directory")
    p_run.add_argument("--headless", action="store_true", help="Run without GUI")
    p_test = sub.add_parser("test", help="Run test assertions")
    p_test.add_argument("--project", "-p", default=".", help="Project directory")
    p_clean = sub.add_parser("clean", help="Remove output/ directory")
    p_clean.add_argument("--project", "-p", default=".", help="Project directory")
    sub.add_parser("setup", help="Install/configure all dependencies (ACME, VICE ROMs, PATH)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    match args.command:
        case "doctor":
            cmd_doctor()
        case "new":
            cmd_new(args.name, args.dir)
        case "build":
            cmd_build(args.project)
        case "run":
            cmd_run(args.project, args.headless)
        case "test":
            cmd_test(args.project)
        case "clean":
            cmd_clean(args.project)
        case "setup":
            cmd_setup()
        case _:
            parser.print_help()


def cmd_doctor() -> None:
    checks = {
        "Python": sys.version.split()[0],
        "ACME": _check_binary("acme", "--version"),
        "VICE (x64sc)": _check_binary("x64sc", "-help"),
        "VICE (x64)": _check_binary("x64", "-help"),
        "c1541": _check_binary("c1541", "-help"),
    }
    print("C64DevKit Doctor")
    print("=" * 40)
    all_ok = True
    for name, result in checks.items():
        status = "OK" if result else "MISSING"
        version = result.split("\n")[0][:60] if result else ""
        print(f"  {name:.<20} {status:.<8} {version}")
        if not result:
            all_ok = False
    print()
    if all_ok:
        print("All dependencies found.")
    else:
        print("Some dependencies are missing. Install them before building.")
    print(f"Framework dir: {get_framework_dir()}")


def cmd_new(name: str, parent: str) -> None:
    project_dir = Path(parent).resolve() / name
    if project_dir.exists():
        print(f"Error: '{project_dir}' already exists", file=sys.stderr)
        sys.exit(1)

    _copy_tree(get_project_template_dir(), project_dir)

    config_file = project_dir / "c64devk.yaml"
    content = config_file.read_text()
    content = content.replace("{{name}}", project_dir.name)
    config_file.write_text(content)

    print(f"Created project '{project_dir.name}' at {project_dir}")
    print(f"  c64devk.yaml        — project config")
    print(f"  spec/               — YAML spec files")
    print(f"  routines/           — custom assembly code")
    print(f"  assets/             — sprite, charset, music files")
    print()
    print(f"Next: cd {name} && c64devk build")


def cmd_build(project_path: str) -> None:
    project_dir = Path(project_path).resolve()
    if not project_dir.is_dir():
        print(f"Error: '{project_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    config = project_dir / "c64devk.yaml"
    if not config.exists():
        print(f"Error: no c64devk.yaml found in '{project_dir}'", file=sys.stderr)
        sys.exit(1)

    print(f"Building project: {project_dir.name}")
    spec = ProjectSpec.from_dir(project_dir)

    errors = _validate_spec(spec)
    if errors:
        for e in errors:
            print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)

    main_asm = run_build(spec)
    src_dir = get_output_src_dir(project_dir)
    build_dir = get_output_build_dir(project_dir)

    macros_src = src_dir / "macros" / "c64devk.acme"
    macros_src.parent.mkdir(parents=True, exist_ok=True)
    _copy_tree(get_macros_dir(), macros_src.parent)

    prg_path = build_dir / spec.output
    sym_path = build_dir / (spec.output.replace(".prg", ".sym"))
    lbl_path = build_dir / (spec.output.replace(".prg", ".lbl"))
    args = [
        "acme", "-f", "cbm",
        "-o", str(prg_path),
        "--symbollist", str(sym_path),
        "--vicelabels", str(lbl_path),
        str(main_asm),
    ]
    result = subprocess.run(args, capture_output=True, text=True, cwd=str(src_dir))

    if result.returncode == 0:
        size = prg_path.stat().st_size if prg_path.exists() else 0
        print(f"Build successful: {prg_path} ({size} bytes)")
    else:
        print(f"Build failed:")
        print(result.stderr or result.stdout)
        sys.exit(1)


def cmd_run(project_path: str, headless: bool) -> None:
    cmd_build(project_path)
    project_dir = Path(project_path).resolve()
    spec = ProjectSpec.from_dir(project_dir)
    build_dir = get_output_build_dir(project_dir)
    prg_path = build_dir / spec.output

    from .vice_bridge import launch_vice
    launch_vice(prg_path, headless=headless)


def cmd_test(project_path: str) -> None:
    project_dir = Path(project_path).resolve()
    if not (project_dir / "c64devk.yaml").exists():
        print(f"Error: no c64devk.yaml found in '{project_dir}'", file=sys.stderr)
        sys.exit(1)

    cmd_build(project_path)

    from .config import get_output_build_dir

    spec = ProjectSpec.from_dir(project_dir)
    build_dir = get_output_build_dir(project_dir)
    prg_path = build_dir / spec.output
    sym_path = build_dir / (spec.output.replace(".prg", ".sym"))

    if not prg_path.exists():
        print(f"Error: PRG not found at {prg_path}", file=sys.stderr)
        sys.exit(1)

    test_path = project_dir / "spec" / "tests.yaml"

    from .test_runner import get_static_results, print_results

    print(f"\n{'=' * 40}")
    print(f"Testing: {spec.name}")

    results = get_static_results(prg_path, sym_path, test_path, spec)
    mode = "static"
    if any(r.test_name.startswith("live:") for r in results):
        mode = "live"
    elif any(r.test_name == "init_state" for r in results):
        mode = "live"

    print_results(results, mode)

    failed = sum(1 for r in results if not r.passed)
    if failed:
        sys.exit(1)


def cmd_clean(project_path: str) -> None:
    project_dir = Path(project_path).resolve()
    output_dir = project_dir / "output"
    if not output_dir.exists():
        print("Nothing to clean.")
        return
    shutil.rmtree(output_dir)
    print(f"Removed {output_dir}")


def cmd_setup() -> None:
    """Install and configure all dependencies interactively."""
    from .config import get_framework_dir

    print("C64DevKit Setup\n")

    # 1. PyYAML
    print("--- Python dependencies ---")
    try:
        import yaml
        print("  PyYAML: installed")
    except ImportError:
        print("  PyYAML: installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml"],
                       capture_output=True)
        try:
            import yaml
            print("  PyYAML: installed")
        except ImportError:
            print("  PyYAML: FAILED — run: pip install pyyaml")

    # 2. ACME
    print("\n--- ACME assembler ---")
    acme_path = shutil.which("acme")
    if acme_path:
        result = subprocess.run([acme_path, "--version"], capture_output=True, text=True)
        ver = result.stdout.strip().split("\n")[0] if result.stdout else "unknown"
        print(f"  ACME: found ({ver})")
    else:
        print("  ACME: not found — compiling from source...")
        success = _install_acme()
        if success:
            print("  ACME: compiled and installed to ~/.local/bin")
        else:
            print("  ACME: FAILED — install manually: sudo apt install acme")
            print("         or: pip install acme")

    # 3. VICE ROMs
    print("\n--- VICE ROM files ---")
    vice = shutil.which("x64sc") or shutil.which("x64")
    if vice:
        print(f"  VICE: found ({vice})")
        rom_dir = Path.home() / ".c64devk" / "roms"
        succeed = True
        mapping = {
            "kernal-901227-03.bin": "kernal",
            "basic-901226-01.bin": "basic",
            "chargen-901225-01.bin": "chargen",
        }
        rom_src = Path("/usr/share/vice/C64")
        if not rom_src.exists():
            alt_dirs = ["/usr/share/vice/", "/usr/local/share/vice/"]
            for ad in alt_dirs:
                p = Path(ad) / "C64"
                if p.exists():
                    rom_src = p
                    break

        if rom_src.exists():
            rom_dir.mkdir(parents=True, exist_ok=True)
            for src_name, dst_name in mapping.items():
                src = rom_src / src_name
                dst = rom_dir / dst_name
                if not src.exists():
                    print(f"  ROM: {src_name} not found at {rom_src}")
                    succeed = False
                elif not dst.exists():
                    os.symlink(str(src), str(dst))
                    print(f"  ROM: {dst_name} → {src_name}")
                else:
                    print(f"  ROM: {dst_name} already set up")
        else:
            print(f"  ROM: C64 ROM directory not found (looked in {rom_src})")
            print(f"       Install VICE ROMs: sudo apt install vice")
            succeed = False

        if succeed:
            print("  VICE ROMs: ready")
    else:
        print("  VICE: not found — install: sudo apt install vice")

    # 4. PATH
    print("\n--- PATH setup ---")
    framework_bin = str(get_framework_dir() / "bin")
    path_parts = os.environ.get("PATH", "").split(":")
    if framework_bin in path_parts:
        print(f"  PATH: already includes {framework_bin}")
    else:
        rc_files = [Path.home() / f for f in [".bashrc", ".profile", ".zshrc"]]
        added = False
        for rc in rc_files:
            if rc.exists():
                content = rc.read_text()
                if framework_bin not in content:
                    with open(rc, "a") as f:
                        f.write(f'\nexport PATH="$PATH:{framework_bin}"  # c64devk\n')
                    print(f"  PATH: added to {rc}")
                    added = True
        if not added:
            print(f"  PATH: add this manually:")
            print(f'    export PATH="$PATH:{framework_bin}"')

    # 5. Verify
    print("\n--- Verification ---")
    cmd_doctor()
    print("\nSetup complete. Run 'c64devk new mygame' to create your first project.")


def _install_acme() -> bool:
    """Compile and install ACME to ~/.local/bin. Returns True on success."""

    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    target = local_bin / "acme"

    if target.exists():
        return True

    tmpdir = Path(tempfile.mkdtemp(prefix="acme_"))
    try:
        # Clone ACME
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", "0.96.5",
             "https://github.com/jan0sch/acme-crossassembler.git", str(tmpdir)],
            capture_output=True, timeout=30
        )
        srcdir = tmpdir / "src"
        if not srcdir.exists():
            return False

        subprocess.run(
            ["make", "-j", str(os.cpu_count() or 2), "-C", str(srcdir)],
            capture_output=True, timeout=60
        )
        acme_bin = srcdir / "acme"
        if acme_bin.exists():
            shutil.copy2(acme_bin, target)
            target.chmod(0o755)
            return True
    except (subprocess.TimeoutExpired, OSError):
        pass
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return False


def _check_binary(name: str, version_arg: str) -> str | None:
    try:
        result = subprocess.run(
            [name, version_arg],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout or result.stderr
        return output.strip().split("\n")[0] if output.strip() else "(found, no version output)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _validate_spec(spec: ProjectSpec) -> list[str]:
    errors: list[str] = []
    if not spec.name:
        errors.append("c64devk.yaml: project.name is required")

    mem = spec.memory
    if mem.code_start >= mem.code_end:
        errors.append(f"c64devk.yaml: memory.code_start (${mem.code_start:04X}) "
                       f"must be < memory.code_end (${mem.code_end:04X})")
    if mem.code_end > 0xCFFF:
        errors.append(f"c64devk.yaml: memory.code_end (${mem.code_end:04X}) "
                       "must be < $D000 to avoid I/O region")
    if mem.sprite_data & 0x3F:
        errors.append(f"c64devk.yaml: memory.sprite_data (${mem.sprite_data:04X}) "
                       "must be 64-byte aligned (divisible by $40)")

    seen: set[int] = set()
    for s in spec.sprites:
        if s.index < 0 or s.index > 7:
            errors.append(f"sprites.yaml: '{s.name}': index {s.index} must be 0-7")
        if s.index in seen:
            errors.append(f"sprites.yaml: '{s.name}': duplicate index {s.index}")
        seen.add(s.index)
        if s.x < 0 or s.x > 511:
            errors.append(f"sprites.yaml: '{s.name}': x={s.x} must be 0-511")
        if s.y < 0 or s.y > 255:
            errors.append(f"sprites.yaml: '{s.name}': y={s.y} must be 0-255")

    sprite_names = {s.name for s in spec.sprites}
    for b in spec.behaviors:
        for a in b.actions:
            for key in ("sprite", "sprites"):
                if key in a.params:
                    refs = a.params[key]
                    if isinstance(refs, str):
                        refs = [refs]
                    for ref in refs:
                        ref = ref.strip()
                        if ref and ref not in sprite_names and ref not in ("0", "1", "2", "3", "4", "5", "6", "7"):
                            errors.append(f"behaviors.yaml: '{b.name}' "
                                          f"references sprite '{ref}' which is not defined in sprites.yaml")
        for cs in b.collision_sprites:
            if cs not in sprite_names:
                errors.append(f"behaviors.yaml: '{b.name}' collision sprite "
                              f"'{cs}' is not defined in sprites.yaml")

    return errors


def _copy_tree(src: Path, dst: Path) -> None:
    if not dst.exists():
        dst.mkdir(parents=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _copy_tree(item, target)
        else:
            shutil.copy2(item, target)
