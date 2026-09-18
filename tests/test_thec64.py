"""Tests for the TheC64 customization kit (filename flags + CJM files)."""

import subprocess
import sys
from pathlib import Path

import pytest

from c64devk import thec64


# ---------------------------------------------------------------------------
# Filename flag parsing
# ---------------------------------------------------------------------------


def test_split_flags_plain_name():
    assert thec64.split_flags("game.d64") == ("game", [], ".d64")


def test_split_flags_flagged_name():
    assert thec64.split_flags("game_M6TPR5.d64") == ("game", ["M6", "TP", "R5"], ".d64")


def test_split_flags_underscore_separated():
    assert thec64.split_flags("game_M6_TP.d64") == ("game", ["M6", "TP"], ".d64")


def test_split_flags_stem_with_underscores():
    assert thec64.split_flags("my_game_v2_M6TP.d64") == (
        "my_game_v2", ["M6", "TP"], ".d64")


def test_split_flags_no_false_positive():
    # "game" does not parse as flags -> whole name is the stem.
    assert thec64.split_flags("my_game.d64") == ("my_game", [], ".d64")


def test_split_flags_stops_at_unknown_segment():
    assert thec64.split_flags("my_M6_game.d64") == ("my_M6_game", [], ".d64")


def test_split_flags_whole_name_is_not_flags():
    # If the entire name would be consumed as flags, keep it as the stem.
    assert thec64.split_flags("M6.d64") == ("M6", [], ".d64")


def test_split_flags_no_extension():
    assert thec64.split_flags("game_M6TP") == ("game", ["M6", "TP"], "")


def test_parse_flag_string_ok():
    assert thec64.parse_flag_string("M6TPR5P1") == ["M6", "TP", "R5", "P1"]


def test_parse_flag_string_rejects_junk():
    with pytest.raises(ValueError):
        thec64.parse_flag_string("M6XQ")


def test_dedupe_flags_preserves_order():
    assert thec64.dedupe_flags(["TP", "M6", "TP"]) == ["TP", "M6"]


def test_build_flag_name_roundtrip():
    name = thec64.build_flag_name("game", ["M6", "TP", "R5", "P1"], ".d64")
    assert name == "game_M6TPR5P1.d64"
    assert thec64.split_flags(name) == ("game", ["M6", "TP", "R5", "P1"], ".d64")


# ---------------------------------------------------------------------------
# Filename flag validation
# ---------------------------------------------------------------------------


def test_validate_flags_conflicting_models():
    errors = thec64.validate_flags(["M6", "MV"], ".d64")
    assert any("M6 and MV" in e for e in errors)


def test_validate_flags_conflicting_video():
    assert thec64.validate_flags(["TN", "TP"], ".d64")


def test_validate_flags_vic_bank_needs_vic():
    errors = thec64.validate_flags(["B1"], ".prg")
    assert any("only applies to a VIC 20" in e for e in errors)


def test_validate_flags_reu_needs_c64():
    errors = thec64.validate_flags(["R5"], ".d64")
    assert any("only applies to a C64" in e for e in errors)
    assert not thec64.validate_flags(["M6", "R5"], ".d64")


def test_validate_flags_reu_rejected_on_vic():
    errors = thec64.validate_flags(["MV", "RM"], ".d64")
    assert any("C64-only" in e for e in errors)


def test_validate_flags_disk_flags_need_disk_ext():
    errors = thec64.validate_flags(["M6", "AD", "RO"], ".prg")
    assert any("only apply to virtual disk" in e for e in errors)
    assert not thec64.validate_flags(["M6", "AD", "RO"], ".g64")


def test_validate_flags_geos_boot_set_valid():
    assert not thec64.validate_flags(["M6", "TP", "R5", "P1", "AD"], ".d64")


# ---------------------------------------------------------------------------
# CJM generation
# ---------------------------------------------------------------------------


def test_generate_cjm_geos_preset():
    text = thec64.PRESETS["geos"].generate()
    assert text == "X:64,pal,reu512\nJ:1M:\n"


def test_generate_cjm_joystick_preset():
    text = thec64.PRESETS["joystick"].generate()
    assert text.startswith("X:64\n")
    assert "J:2*:" in text
    # 15 comma-separated entries after the colon.
    buttons = text.split(":", 2)[2].strip().split(",")
    assert len(buttons) == 15


def test_generate_cjm_empty_button_entries():
    joy = thec64.Joystick(port=1, primary=True, buttons=thec64.WASD_BUTTONS)
    config = thec64.CjmConfig(computer="c64", joysticks=[joy])
    assert "J:1*:W,S,A,D,I,K,J,L,CT,1,2,3,,EN,4" in config.generate()


def test_generate_cjm_vic20_with_banks():
    config = thec64.CjmConfig(computer="vic20", video="pal",
                              options=["bank1", "bank2", "fullheight"])
    assert config.generate() == "X:vic,pal,bank1,bank2,fullheight\n"


def test_generate_cjm_vertical_shift():
    config = thec64.CjmConfig(computer="c64", vertical_shift=12)
    assert config.generate() == "X:64\nV:12\n"


def test_generate_cjm_mouse_port2():
    config = thec64.CjmConfig(mouse=2)
    assert config.generate() == "J:2M:\n"


# ---------------------------------------------------------------------------
# CJM validation
# ---------------------------------------------------------------------------


def test_validate_cjm_reu_needs_c64():
    config = thec64.CjmConfig(computer="vic20", options=["reu512"])
    assert any("only works on a C64" in e for e in thec64.validate_cjm(config))


def test_validate_cjm_banks_need_vic():
    config = thec64.CjmConfig(computer="c64", options=["bank1"])
    assert any("only works on a VIC 20" in e for e in thec64.validate_cjm(config))


def test_validate_cjm_unknown_option():
    config = thec64.CjmConfig(computer="c64", options=["warpdrive"])
    assert any("unknown X option" in e for e in thec64.validate_cjm(config))


def test_validate_cjm_vertical_shift_ranges():
    ok = thec64.CjmConfig(computer="c64", vertical_shift=17)
    assert not thec64.validate_cjm(ok)
    bad = thec64.CjmConfig(computer="c64", vertical_shift=18)
    assert any("outside" in e for e in thec64.validate_cjm(bad))
    vic_ntsc = thec64.CjmConfig(computer="vic20", video="ntsc", vertical_shift=1)
    assert any("outside" in e for e in thec64.validate_cjm(vic_ntsc))
    vic_ntsc_ok = thec64.CjmConfig(computer="vic20", video="ntsc",
                                   vertical_shift=0)
    assert not thec64.validate_cjm(vic_ntsc_ok)


def test_validate_cjm_needs_exactly_one_primary():
    config = thec64.CjmConfig(
        computer="c64",
        joysticks=[
            thec64.Joystick(port=1, primary=False),
            thec64.Joystick(port=2, primary=False),
        ],
    )
    assert any("exactly one joystick" in e for e in thec64.validate_cjm(config))
    config.joysticks[1].primary = True
    assert not thec64.validate_cjm(config)


def test_validate_cjm_vic20_single_port():
    config = thec64.CjmConfig(
        computer="vic20",
        joysticks=[thec64.Joystick(port=2, primary=True)],
    )
    assert any("only port 1" in e or "port 1" in e
               for e in thec64.validate_cjm(config))


def test_validate_cjm_wrong_button_count():
    config = thec64.CjmConfig(
        computer="c64",
        joysticks=[thec64.Joystick(port=1, primary=True, buttons=["JU"])],
    )
    assert any("15 button entries" in e for e in thec64.validate_cjm(config))


def test_validate_cjm_bad_key_id():
    buttons = list(thec64.DEFAULT_JOYSTICK_BUTTONS)
    buttons[4] = "XX"
    config = thec64.CjmConfig(
        computer="c64",
        joysticks=[thec64.Joystick(port=2, primary=True, buttons=buttons)],
    )
    assert any("not a valid key ID" in e for e in thec64.validate_cjm(config))


def test_validate_cjm_mouse_and_joystick_same_port():
    config = thec64.CjmConfig(
        computer="c64",
        joysticks=[thec64.Joystick(port=1, primary=True)],
        mouse=1,
    )
    assert any("mouse is on port 1" in e for e in thec64.validate_cjm(config))
    config.joysticks[0].port = 2
    assert not thec64.validate_cjm(config)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


CLI = [str(Path(__file__).resolve().parent.parent / "bin" / "c64devk")]


def _run(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(CLI + list(argv), capture_output=True, text=True,
                          cwd=str(cwd) if cwd else None)


def test_cli_flags_preview_and_rename(tmp_path):
    disk = tmp_path / "game.d64"
    disk.touch()
    out = _run("flags", "game.d64", "--c64", "--pal", "--reu", "512", "--j1",
               cwd=tmp_path)
    assert out.returncode == 0
    assert "game_M6TPJ1R5.d64" in out.stdout
    assert "preview only" in out.stdout
    # Preview must not touch the file.
    assert disk.exists()
    assert not (tmp_path / "game_M6TPJ1R5.d64").exists()

    out = _run("flags", "game.d64", "--c64", "--pal", "--reu", "512", "--j1",
               "--rename", cwd=tmp_path)
    assert out.returncode == 0
    assert not disk.exists()
    assert (tmp_path / "game_M6TPJ1R5.d64").exists()


def test_cli_flags_copy_and_strip_roundtrip(tmp_path):
    disk = tmp_path / "game_M6TP.d64"
    disk.touch()
    staged = tmp_path / "out"
    out = _run("flags", "game_M6TP.d64", "--accurate-disk", "--copy", "out",
               cwd=tmp_path)
    assert out.returncode == 0
    assert (staged / "game_M6TPAD.d64").exists()
    assert disk.exists()  # copy leaves the original alone
    # An unchanged name is a no-op for --copy.
    out = _run("flags", "game_M6TP.d64", "--copy", "out", cwd=tmp_path)
    assert out.returncode == 0
    assert "(unchanged)" in out.stdout

    out = _run("flags", "game_M6TP.d64", "--strip", "--rename", cwd=tmp_path)
    assert out.returncode == 0
    assert (tmp_path / "game.d64").exists()
    assert not disk.exists()


def test_cli_flags_explain(tmp_path):
    (tmp_path / "game_M6TPR5.d64").touch()
    out = _run("flags", "game_M6TPR5.d64", "--explain", cwd=tmp_path)
    assert out.returncode == 0
    for code in ("M6", "TP", "R5"):
        assert code in out.stdout


def test_cli_flags_rejects_conflict(tmp_path):
    (tmp_path / "game.d64").touch()
    out = _run("flags", "game.d64", "--c64", "--vic20", cwd=tmp_path)
    assert out.returncode != 0  # argparse rejects the group
    out = _run("flags", "game.d64", "--vic20", "--reu", "512", cwd=tmp_path)
    assert out.returncode == 1
    assert "C64-only" in out.stderr


def test_cli_cjm_geos(tmp_path):
    out = _run("cjm", "--preset", "geos", "--name", "GEOS64-20.d64",
               "--out", str(tmp_path))
    assert out.returncode == 0
    written = tmp_path / "GEOS64-20.cjm"
    assert written.exists()
    assert written.read_text() == "X:64,pal,reu512\nJ:1M:\n"


def test_cli_cjm_keeps_flags_in_name(tmp_path):
    out = _run("cjm", "--preset", "joystick", "--name", "game_M6TP.d64",
               "--out", str(tmp_path))
    assert out.returncode == 0
    assert (tmp_path / "game_M6TP.cjm").exists()


def test_cli_cjm_default(tmp_path):
    out = _run("cjm", "--preset", "geos", "--default", "--out", str(tmp_path))
    assert out.returncode == 0
    assert (tmp_path / thec64.CJM_DEFAULT_FILENAME).exists()


def test_cli_cjm_requires_name(tmp_path):
    out = _run("cjm", "--preset", "joystick", "--out", str(tmp_path))
    assert out.returncode == 1
    assert "--name" in out.stderr


def test_cli_cjm_custom_buttons(tmp_path):
    out = _run("cjm", "--c64", "--buttons", "W,S,A,D,SP", "--port", "1",
               "--name", "game", "--out", str(tmp_path))
    assert out.returncode == 0
    content = (tmp_path / "game.cjm").read_text()
    # Short button lists are padded to 15 entries.
    assert "J:1*:W,S,A,D,SP" in content
    assert len(content.split(":", 2)[2].strip().split(",")) == 15


def test_cli_cjm_rejects_bad_button(tmp_path):
    out = _run("cjm", "--c64", "--buttons", "W,S,A,D,ZZ", "--name", "game",
               "--out", str(tmp_path))
    assert out.returncode == 1
    assert "not a valid key ID" in out.stderr
