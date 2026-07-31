"""YAML spec parser — reads project specs into a structured data model."""

from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class MemoryLayout:
    code_start: int = 0x0801
    code_end: int = 0xCFFF
    sprite_data: int = 0x2000
    charset: int = 0x3800
    screen_ram: int = 0x0400

    @classmethod
    def from_dict(cls, d: dict | None) -> "MemoryLayout":
        if not d:
            return cls()
        return cls(
            code_start=_parse_int(d.get("code_start", "0x0801")),
            code_end=_parse_int(d.get("code_end", "0xCFFF")),
            sprite_data=_parse_int(d.get("sprite_data", "0x2000")),
            charset=_parse_int(d.get("charset", "0x3800")),
            screen_ram=_parse_int(d.get("screen_ram", "0x0400")),
        )


@dataclass
class ScreenConfig:
    mode: str = "hires"
    charset_addr: int = 0x3800
    screen_ram: int = 0x0400
    background_color: int = 0
    border_color: int = 0
    multicolor: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> "ScreenConfig":
        if not d:
            return cls()
        return cls(
            mode=d.get("mode", "hires"),
            charset_addr=_parse_int(d.get("charset", "0x3800")),
            screen_ram=_parse_int(d.get("screen_ram", "0x0400")),
            background_color=_parse_int(d.get("background_color", "0")),
            border_color=_parse_int(d.get("border_color", "0")),
            multicolor=d.get("multicolor", False),
        )


@dataclass
class SpriteDef:
    name: str
    index: int
    x: int = 160
    y: int = 120
    color: int = 7
    multicolor: bool = False
    multicolor1: int = 0
    multicolor2: int = 0
    enabled: bool = True
    priority: bool = False
    expand_x: bool = False
    expand_y: bool = False
    data_file: str = ""

    @classmethod
    def from_dict(cls, d: dict, idx: int) -> "SpriteDef":
        return cls(
            name=d.get("name", f"sprite_{idx}"),
            index=d.get("index", idx),
            x=_parse_int(d.get("x", "160")),
            y=_parse_int(d.get("y", "120")),
            color=_parse_int(d.get("color", "7")),
            multicolor=d.get("multicolor", False),
            multicolor1=_parse_int(d.get("multicolor_1", "0")),
            multicolor2=_parse_int(d.get("multicolor_2", "0")),
            enabled=d.get("enabled", True),
            priority=d.get("priority", False),
            expand_x=d.get("expand_x", False),
            expand_y=d.get("expand_y", False),
            data_file=d.get("data_file", _default_sprite_path(idx)),
        )


@dataclass
class Action:
    type: str
    params: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, action_data) -> "Action":
        if isinstance(action_data, str):
            return cls(type=action_data)
        if isinstance(action_data, dict):
            if len(action_data) == 0:
                return cls(type="")
            action_type, value = next(iter(action_data.items()))
            params = cls._normalize_params(action_type, value)
            return cls(type=action_type, params=params)
        raise ValueError(f"Invalid action format: {action_data}")

    @staticmethod
    def _normalize_params(action_type: str, value) -> dict:
        if value is None:
            return {}
        if isinstance(value, str):
            return Action._params_for_type(action_type, value)
        if isinstance(value, int):
            return Action._params_for_type(action_type, value)
        if isinstance(value, dict):
            return value
        return {"value": value}

    @staticmethod
    def _params_for_type(action_type: str, value) -> dict:
        if action_type == "read_joystick":
            return {"port": str(value)}
        elif action_type == "update_sprite":
            return {"sprite": str(value)}
        elif action_type == "inc_score":
            return {"amount": int(value)}
        elif action_type == "check_collision":
            return {"sprites": str(value).split(",")}
        else:
            return {"value": value}


@dataclass
class BehaviorDef:
    name: str
    type: str
    actions: list[Action] = field(default_factory=list)
    collision_sprites: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "BehaviorDef":
        btype = d.get("type", "on_frame")
        raw_actions = d.get("actions", [])
        parsed = []
        for a in raw_actions:
            try:
                parsed.append(Action.from_yaml(a))
            except (ValueError, TypeError):
                pass

        sprites = d.get("sprites", d.get("collision_sprites", []))

        return cls(
            name=d.get("name", "unnamed"),
            type=btype,
            actions=parsed,
            collision_sprites=list(sprites) if sprites else [],
        )


@dataclass
class ProjectSpec:
    name: str = ""
    output: str = "main.prg"
    memory: MemoryLayout = field(default_factory=MemoryLayout)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    sprites: list[SpriteDef] = field(default_factory=list)
    behaviors: list[BehaviorDef] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)
    routines: list[str] = field(default_factory=list)
    project_dir: Path = field(default_factory=Path)
    basic: bool = True

    @classmethod
    def from_dir(cls, project_dir: Path) -> "ProjectSpec":
        config_path = project_dir / "c64devk.yaml"
        spec = cls(project_dir=project_dir.resolve())

        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            spec.name = config.get("project", {}).get("name", project_dir.name)
            spec.output = config.get("project", {}).get("output", "main.prg")
            spec.basic = config.get("basic", True)
            spec.memory = MemoryLayout.from_dict(config.get("memory"))
            spec.screen = ScreenConfig.from_dict(config.get("screen"))
            spec.constraints = config.get("constraints", [])
            spec.routines = config.get("routines", [])

        spec_dir = project_dir / "spec"
        if spec_dir.exists():
            spec._load_sprites(project_dir)
            spec._load_behaviors(project_dir)

        return spec

    def _load_sprites(self, project_dir: Path) -> None:
        sprites_path = project_dir / "spec" / "sprites.yaml"
        if not sprites_path.exists():
            return
        with open(sprites_path) as f:
            data = yaml.safe_load(f)
        if not data or "sprites" not in data:
            return
        for i, s in enumerate(data["sprites"]):
            self.sprites.append(SpriteDef.from_dict(s, i))

    def _load_behaviors(self, project_dir: Path) -> None:
        behavior_path = project_dir / "spec" / "behaviors.yaml"
        if not behavior_path.exists():
            return
        with open(behavior_path) as f:
            data = yaml.safe_load(f)
        if not data or "behaviors" not in data:
            return
        for b in data["behaviors"]:
            self.behaviors.append(BehaviorDef.from_dict(b))

    @property
    def code_end(self) -> int:
        return self.memory.code_end

    @property
    def code_start(self) -> int:
        return self.memory.code_start

    @property
    def bas10_str(self) -> str:
        addr = self.memory.code_start
        result = []
        for i, d in enumerate(str(addr)):
            result.append(f"${ord(d):02x}")
        return ", ".join(result)


def _parse_int(val: int | str) -> int:
    if isinstance(val, int):
        return val
    val = str(val).strip()
    if val.startswith("0x") or val.startswith("0X"):
        return int(val, 16)
    if val.startswith("$"):
        return int(val[1:], 16)
    if val.startswith("%"):
        return int(val[1:], 2)
    return int(val)


def _default_sprite_path(idx: int) -> str:
    return f"assets/sprites/sprite{idx}.spr"


# ============================================================
# Note-to-SID-frequency conversion
# ============================================================

NOTE_NAMES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
              "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}

_NOTE_ALIASES = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#"}

_PAL_CLOCK = 985248.0
_SID_SCALE = 16777216.0


def note_to_sid_freq(note_str: str) -> int:
    """Convert a note name like 'C-4', 'A#3', 'Db-5' to a SID frequency value."""
    note_str = str(note_str).strip().upper()
    for flat, sharp in _NOTE_ALIASES.items():
        if note_str.startswith(flat):
            note_str = sharp + note_str[2:]
            break

    import re
    m = re.match(r"^([A-G][#]?)-?(\d)$", note_str)
    if not m:
        try:
            return _parse_int(note_str)
        except ValueError:
            return 0

    name, octave_str = m.groups()
    octave = int(octave_str)
    semitone = NOTE_NAMES.get(name, 0)
    midi = semitone + (octave + 1) * 12
    freq_hz = 440.0 * (2 ** ((midi - 69) / 12.0))
    sid_freq = int(freq_hz * _SID_SCALE / _PAL_CLOCK + 0.5)
    sid_freq = max(0, min(65535, sid_freq))
    return sid_freq
