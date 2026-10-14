"""Client-local adapter for claimed-lane source commands."""

from __future__ import annotations

import importlib
from yoke_cli.commands._helpers import show_delegate_help
from typing import List


def _source_runner():
    return importlib.import_module("yoke_core.tools.source_dev_run")


def source_dev_run(args: List[str]) -> int:
    return _source_runner().main(args)


def ruff_changed(args: List[str]) -> int:
    if show_delegate_help(
        args,
        "yoke dev ruff-changed [--base REF] [--workdir PATH] [--fix-format | --format-check]",
        "Run from the registered claimed source lane; checks use its locked environment.",
    ):
        return 0
    return _source_runner().run(
        ["python3", "-m", "yoke_core.tools.ruff_changed", *args]
    )


def import_check(args: List[str]) -> int:
    if show_delegate_help(
        args,
        "yoke dev import-check MODULE [MODULE ...]",
        "Run from the registered claimed source lane; checks use its locked environment.",
    ):
        return 0
    return _source_runner().run(
        ["python3", "-m", "yoke_core.tools.import_check", *args]
    )


__all__ = ["import_check", "ruff_changed", "source_dev_run"]
