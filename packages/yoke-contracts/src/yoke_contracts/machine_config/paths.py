"""Shared machine-home selection and config mutation ownership."""

from __future__ import annotations

import os
from pathlib import Path

from yoke_contracts.machine_config.schema import DEFAULT_CONFIG_NAME


CONFIG_FILE_ENV = "YOKE_MACHINE_CONFIG_FILE"
HOME_ENV = "YOKE_MACHINE_HOME"


class MachineConfigOwnershipError(RuntimeError):
    """A config mutation targets another machine home."""


def yoke_home() -> Path:
    explicit = os.environ.get(HOME_ENV, "").strip()
    return Path(explicit).expanduser() if explicit else Path.home() / ".yoke"


def config_path(explicit: str | Path | None = None) -> Path:
    """Resolve explicit path, isolated home, config-file env, then default."""
    home = yoke_home()
    if explicit is not None:
        selected = Path(explicit).expanduser()
        return selected if selected.is_absolute() else home / selected
    if os.environ.get(HOME_ENV, "").strip():
        return home / DEFAULT_CONFIG_NAME
    override = os.environ.get(CONFIG_FILE_ENV, "").strip()
    if override:
        selected = Path(override).expanduser()
        return selected if selected.is_absolute() else home / selected
    return home / DEFAULT_CONFIG_NAME


def assert_write_owned(selected: str | Path) -> None:
    """An explicit machine home confines all config writes to that home.

    Resolve physical paths so a symlink or '..' cannot escape the boundary.
    Without a home override an operator can select a config explicitly.
    """
    if not os.environ.get(HOME_ENV, "").strip():
        return
    try:
        home = yoke_home().resolve()
        target = Path(selected).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise MachineConfigOwnershipError(
            f"machine_config_ownership_unresolved: cannot resolve {selected}; "
            "repair the config path and machine-home symlinks, then retry."
        ) from exc
    if not target.is_relative_to(home):
        raise MachineConfigOwnershipError(
            f"machine_config_not_owned: {target} is outside the selected machine "
            f"home {home}; remove --config or select a config inside "
            f"{HOME_ENV} before retrying."
        )
