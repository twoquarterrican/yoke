"""Machine key-value configuration helpers used by API adapters."""

from pathlib import Path
from typing import Dict
from yoke_core.domain import runtime_settings


def parse_config_file(config_path: str | Path) -> Dict[str, str]:
    return runtime_settings.read_all(config_path=Path(config_path))


def config_path_from_db_path(db_path: str | Path) -> Path:
    """Return the legacy fixture config path adjacent to an explicit test DB."""
    return Path(db_path).resolve().parent / "config"
