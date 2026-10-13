"""Atomic CLI read output bounds and explicit whole-answer opt-in."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

from yoke_contracts.registered_reads import READ_FUNCTION_IDS

# 350 displayed lines at the shared teaching width, including JSON output.
READ_OUTPUT_LIMIT_BYTES = 28_000
_FULL_OUTPUT = ContextVar("full_read_output", default=False)


@contextmanager
def read_output_scope(args: list[str]) -> Iterator[None]:
    token = _FULL_OUTPUT.set(
        "--full" in args[: args.index("--")] if "--" in args else "--full" in args
    )
    try:
        yield
    finally:
        _FULL_OUTPUT.reset(token)


def output_exceeds_limit(
    function: str, stdout: str, stderr: str, *, full: bool = False
) -> bool:
    return (
        function in READ_FUNCTION_IDS
        and not (full or _FULL_OUTPUT.get())
        and len((stdout + stderr).encode("utf-8")) > READ_OUTPUT_LIMIT_BYTES
    )


def full_output_requested() -> bool:
    return _FULL_OUTPUT.get()


def read_recovery(function: str) -> str:
    from yoke_cli.commands.registry import SUBCOMMAND_REGISTRY

    forms = [
        tokens for tokens, (name, _) in SUBCOMMAND_REGISTRY.items() if name == function
    ]
    tokens = (
        min(forms, key=lambda value: (len(value), value))
        if forms
        else tuple(function.replace("_", "-").split("."))
    )
    command = "yoke " + " ".join(tokens)
    return (
        f"Narrow {command} with its field/filter flags or a smaller --limit "
        f"where supported; run {command} --help for the exact recipe, "
        f"or add --full to request the entire answer explicitly."
    )
