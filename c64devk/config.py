"""Framework configuration and path resolution."""

import os
from pathlib import Path


def get_framework_dir() -> Path:
    """Return the root directory of C64DevKit."""
    return Path(__file__).resolve().parent.parent


def get_macros_dir() -> Path:
    return get_framework_dir() / "macros"


def get_templates_dir() -> Path:
    return get_framework_dir() / "c64devk" / "templates"


def get_project_template_dir() -> Path:
    return get_templates_dir() / "project"


def get_user_config_dir() -> Path:
    path = Path.home() / ".c64devk"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_output_dir(project_dir: Path) -> Path:
    return project_dir / "output"


def get_output_src_dir(project_dir: Path) -> Path:
    return get_output_dir(project_dir) / "src"


def get_output_build_dir(project_dir: Path) -> Path:
    return get_output_dir(project_dir) / "build"
