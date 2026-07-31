"""Tests for spec parser."""

import pytest
from pathlib import Path
from c64devk.spec_parser import (
    ProjectSpec,
    MemoryLayout,
    ScreenConfig,
    SpriteDef,
    BehaviorDef,
    Action,
    _parse_int,
    note_to_sid_freq,
)


def test_parse_int_hex():
    assert _parse_int("0x0801") == 0x0801
    assert _parse_int("$0801") == 0x0801
    assert _parse_int("0xC000") == 0xC000


def test_parse_int_decimal():
    assert _parse_int("10") == 10
    assert _parse_int(42) == 42


def test_parse_int_binary():
    assert _parse_int("%00000001") == 1


def test_memory_layout_defaults():
    m = MemoryLayout()
    assert m.code_start == 0x0801
    assert m.sprite_data == 0x2000


def test_memory_layout_from_dict():
    m = MemoryLayout.from_dict({"code_start": "$1000", "code_end": "$8000"})
    assert m.code_start == 0x1000
    assert m.code_end == 0x8000


def test_screen_config_defaults():
    s = ScreenConfig()
    assert s.mode == "hires"
    assert s.background_color == 0


def test_sprite_def_from_dict():
    s = SpriteDef.from_dict({"name": "player", "index": 0, "x": "160", "y": "120"}, 0)
    assert s.name == "player"
    assert s.x == 160


def test_empty_project():
    p = ProjectSpec(name="test", project_dir=Path("/tmp"))
    assert p.name == "test"
    assert len(p.sprites) == 0


class TestActionParsing:
    def test_action_from_string(self):
        a = Action.from_yaml("read_joystick")
        assert a.type == "read_joystick"
        assert a.params == {}

    def test_action_from_dict_simple(self):
        a = Action.from_yaml({"read_joystick": "port2"})
        assert a.type == "read_joystick"
        assert a.params["port"] == "port2"

    def test_action_from_dict_int_value(self):
        a = Action.from_yaml({"inc_score": 10})
        assert a.type == "inc_score"
        assert a.params["amount"] == 10

    def test_action_negative_score(self):
        a = Action.from_yaml({"inc_score": -1})
        assert a.type == "inc_score"
        assert a.params["amount"] == -1

    def test_action_update_sprite(self):
        a = Action.from_yaml({"update_sprite": "player"})
        assert a.type == "update_sprite"
        assert a.params["sprite"] == "player"

    def test_action_nested_dict(self):
        a = Action.from_yaml({
            "set_sprite_pos": {"sprite": "player", "x": 100, "y": 50}
        })
        assert a.type == "set_sprite_pos"
        assert a.params["sprite"] == "player"
        assert a.params["x"] == 100
        assert a.params["y"] == 50

    def test_action_play_sound(self):
        a = Action.from_yaml({
            "play_sound": {"voice": 1, "frequency": 1000, "waveform": "triangle"}
        })
        assert a.type == "play_sound"
        assert a.params["voice"] == 1
        assert a.params["frequency"] == 1000
        assert a.params["waveform"] == "triangle"

    def test_action_check_collision_string(self):
        a = Action.from_yaml({"check_collision": "player,enemy"})
        assert a.type == "check_collision"
        assert a.params["sprites"] == ["player", "enemy"]

    def test_action_empty_dict(self):
        a = Action.from_yaml({})
        assert a.type == ""


class TestBehaviorDef:
    def test_behavior_from_dict(self):
        d = {
            "name": "move_player",
            "type": "on_frame",
            "actions": [
                {"read_joystick": "port2"},
                {"update_sprite": "player"},
            ],
        }
        b = BehaviorDef.from_dict(d)
        assert b.name == "move_player"
        assert b.type == "on_frame"
        assert len(b.actions) == 2
        assert b.actions[0].type == "read_joystick"
        assert b.actions[1].type == "update_sprite"

    def test_behavior_collision_sprites(self):
        d = {
            "name": "hit",
            "type": "on_collision",
            "sprites": ["player", "enemy"],
            "actions": [{"inc_score": 10}],
        }
        b = BehaviorDef.from_dict(d)
        assert b.type == "on_collision"
        assert b.collision_sprites == ["player", "enemy"]
        assert len(b.actions) == 1

    def test_behavior_collision_sprites_alias(self):
        d = {
            "name": "hit",
            "type": "on_collision",
            "collision_sprites": ["a", "b"],
            "actions": [],
        }
        b = BehaviorDef.from_dict(d)
        assert b.collision_sprites == ["a", "b"]

    def test_behavior_empty_actions(self):
        d = {"name": "empty", "type": "on_frame", "actions": []}
        b = BehaviorDef.from_dict(d)
        assert len(b.actions) == 0

    def test_project_with_behaviors(self, tmp_path):
        project_dir = tmp_path / "testproj"
        project_dir.mkdir()
        config = {"project": {"name": "test"}}
        import yaml
        with open(project_dir / "c64devk.yaml", "w") as f:
            yaml.dump(config, f)

        spec_dir = project_dir / "spec"
        spec_dir.mkdir()
        with open(spec_dir / "sprites.yaml", "w") as f:
            yaml.dump({
                "sprites": [
                    {"name": "player", "index": 0},
                    {"name": "enemy", "index": 1},
                ]
            }, f)
        with open(spec_dir / "behaviors.yaml", "w") as f:
            yaml.dump({
                "behaviors": [
                    {
                        "name": "move",
                        "type": "on_frame",
                        "actions": ["update_sprite"],
                    },
                    {
                        "name": "hit",
                        "type": "on_collision",
                        "sprites": ["player", "enemy"],
                        "actions": [{"inc_score": 10}],
                    },
                ]
            }, f)

        p = ProjectSpec.from_dir(project_dir)
        assert len(p.sprites) == 2
        assert len(p.behaviors) == 2
        assert p.behaviors[0].type == "on_frame"
        assert p.behaviors[1].type == "on_collision"
        assert p.behaviors[1].collision_sprites == ["player", "enemy"]


class TestNoteToSidFreq:
    def test_c4_middle_c(self):
        # C-4 = MIDI 60 = ~261.63 Hz
        # SID freq = 261.63 * 16777216 / 985248 ≈ 4455
        f = note_to_sid_freq("C-4")
        assert abs(f - 4455) <= 1, f"C-4 expected ~4455, got {f}"

    def test_a4(self):
        # A-4 = MIDI 69 = 440 Hz
        # SID freq = 440 * 16777216 / 985248 ≈ 7491
        f = note_to_sid_freq("A-4")
        assert abs(f - 7492) <= 1, f"A-4 expected ~7492, got {f}"

    def test_c3(self):
        f = note_to_sid_freq("C-3")
        assert abs(f - 2228) <= 1, f"C-3 expected ~2228, got {f}"

    def test_sharp(self):
        # C#4 = MIDI 61
        f = note_to_sid_freq("C#-4")
        assert f > 4455  # should be higher than C-4

    def test_flat_aliased_to_sharp(self):
        # Db-4 = C#4
        f_flat = note_to_sid_freq("Db-4")
        f_sharp = note_to_sid_freq("C#-4")
        assert f_flat == f_sharp

    def test_invalid_note_returns_fallback(self):
        assert note_to_sid_freq("ZZ") == 0
        assert note_to_sid_freq("") == 0

    def test_raw_number_passthrough(self):
        assert note_to_sid_freq("1000") == 1000
        assert note_to_sid_freq("0x2000") == 0x2000

    def test_low_note_c2(self):
        f = note_to_sid_freq("C-2")
        # C-2 = MIDI 36 = 65.41 Hz → SID freq ≈ 1114
        assert 1100 < f < 1200

    def test_high_note_b7(self):
        f = note_to_sid_freq("B-7")
        assert 62000 < f < 65536


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
