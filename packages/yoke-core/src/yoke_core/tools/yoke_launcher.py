#!/usr/bin/env python3
"""Standard-library launcher for the public installer's released CLI.

Ordinary commands use uv's yoke-cli environment in isolated Python mode.
YOKE_SOURCE_DEV=1 explicitly opts an operator into YOKE_HOME source imports;
claimed-lane checks use ``yoke dev run`` instead.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_YOKE_HOME = None
RELEASE_RECOVERY = "install the released CLI with `curl -fsSL https://upyoke.com/install | sh`, then retry"
RELEASE_ENTRY = """
import sys
try:
    from yoke_cli.config.install_binding import detect
    binding = detect()
    from yoke_cli.main import main
except (ImportError, OSError) as exc:
    sys.exit("released_cli_unavailable: " + str(exc) + "; " + sys.argv[1])
if binding["kind"] != "packaged_wheel" or not binding["version"]:
    sys.exit("released_cli_required: uv's yoke-cli environment is not a versioned wheel; " + sys.argv[1])
sys.exit(main(sys.argv[2:]) or 0)
"""


def _run_release() -> int:
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    try:
        result = subprocess.run(
            [uv, "tool", "dir"], capture_output=True, text=True, check=True, timeout=5
        )
        tool_root = Path(result.stdout.strip())
        if not tool_root.is_absolute():
            raise ValueError("uv tool dir returned no absolute tool directory")
        python = tool_root / "yoke-cli" / "bin" / "python3"
        if not python.is_file():
            raise FileNotFoundError(f"released CLI interpreter missing: {python}")
        os.execv(
            str(python),
            [str(python), "-I", "-c", RELEASE_ENTRY, RELEASE_RECOVERY, *sys.argv[1:]],
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"released_cli_unavailable: {exc}; {RELEASE_RECOVERY}", file=sys.stderr)
        return 2
    return 0  # exec replaces this process


def _resolve_yoke_home() -> Path:
    return Path(
        os.environ.get("YOKE_HOME") or DEFAULT_YOKE_HOME or os.path.expanduser("~/yoke")
    )


def _source_paths(home: Path) -> list[Path]:
    package_root = home / "packages"
    paths = []
    if package_root.is_dir():
        paths.extend(sorted(src for src in package_root.glob("*/src") if src.is_dir()))
    paths.append(home)
    return paths


def _prepend_source_paths(home: Path) -> None:
    for path in reversed(_source_paths(home)):
        raw = str(path)
        if raw not in sys.path:
            sys.path.insert(0, raw)


def main() -> int:
    if os.environ.get("YOKE_SOURCE_DEV") != "1":
        return _run_release()
    home = _resolve_yoke_home()
    if not (home / "packages/yoke-cli/src/yoke_cli/__init__.py").is_file():
        print(
            f"source_cli_unavailable: YOKE_HOME names no CLI source at {home}; "
            "set YOKE_HOME to the source checkout or unset YOKE_SOURCE_DEV "
            "to run the released CLI",
            file=sys.stderr,
        )
        return 2
    _prepend_source_paths(home)
    print(f"source authority: explicit operator opt-in at {home}", file=sys.stderr)
    try:
        from yoke_cli.main import main as cli_main
    except ImportError as exc:
        print(
            f"source_cli_unavailable: {exc}; prepare the source environment "
            "and run checks with `yoke dev run -- <command>`",
            file=sys.stderr,
        )
        return 2

    return int(cli_main(sys.argv[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
