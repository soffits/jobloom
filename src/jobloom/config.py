from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_state_dir

from .errors import EXIT_CONFIG, JobLoomError

APP = "jobloom"
CONFIG_NAME = "config.toml"


@dataclass(slots=True)
class Paths:
    config_dir: Path
    config_file: Path
    state_dir: Path
    database_file: Path


def paths() -> Paths:
    config_home = (
        Path(os.environ["XDG_CONFIG_HOME"])
        if os.environ.get("XDG_CONFIG_HOME")
        else Path(user_config_dir(APP))
    )
    state_home = (
        Path(os.environ["XDG_STATE_HOME"])
        if os.environ.get("XDG_STATE_HOME")
        else Path(user_state_dir(APP))
    )
    config_dir = config_home / APP if config_home.name != APP else config_home
    state_dir = state_home / APP if state_home.name != APP else state_home
    return Paths(config_dir, config_dir / CONFIG_NAME, state_dir, state_dir / "jobs.sqlite3")


EXAMPLE_CONFIG = """# JobLoom example configuration. Do not put passwords, cookies, or tokens here.
[providers.linkedin_linked]
executable = "linked"
timeout_seconds = 20
"""


def ensure_private_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
    except OSError as exc:
        raise JobLoomError(str(exc), EXIT_CONFIG, "config_error") from None


def write_private_file(path: Path, text: str, force: bool = False) -> None:
    if path.is_symlink():
        raise JobLoomError(
            f"Refusing to write symlink config at {path}", EXIT_CONFIG, "config_error"
        )
    if path.exists() and not force:
        raise JobLoomError(
            f"Config already exists at {path}",
            EXIT_CONFIG,
            "config_exists",
            "Use --force to overwrite the non-secret example config.",
        )
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if force else os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        raise JobLoomError(
            f"Config already exists at {path}",
            EXIT_CONFIG,
            "config_exists",
            "Use --force to overwrite the non-secret example config.",
        ) from None
    except OSError as exc:
        raise JobLoomError(str(exc), EXIT_CONFIG, "config_error") from None


def init_files(force: bool = False) -> Paths:
    p = paths()
    ensure_private_dir(p.config_dir)
    ensure_private_dir(p.state_dir)
    write_private_file(p.config_file, EXAMPLE_CONFIG, force=force)
    return p


def load_config() -> dict[str, Any]:
    p = paths()
    if p.config_file.is_symlink():
        raise JobLoomError(
            f"Refusing to read symlink config at {p.config_file}", EXIT_CONFIG, "config_error"
        )
    if not p.config_file.exists():
        return {}
    try:
        return tomllib.loads(p.config_file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise JobLoomError(str(exc), EXIT_CONFIG, "config_invalid") from None
    except OSError as exc:
        raise JobLoomError(str(exc), EXIT_CONFIG, "config_error") from None


def mode(path: Path) -> str | None:
    try:
        return oct(stat.S_IMODE(path.stat().st_mode))
    except OSError:
        return None
