"""Independent title and spec sources for item filing."""

from __future__ import annotations

import argparse

from yoke_cli.commands.text_file import resolve_one_text_source, resolve_text_file


def resolve_create_text(parsed: argparse.Namespace, shortcut: str | None):
    title = parsed.title
    workflow = shortcut or parsed.workflow
    positional_spec = parsed.spec if shortcut else None
    if parsed.title_file:
        if shortcut:
            if parsed.spec is not None:
                raise ValueError(
                    "SPEC_SOURCE_AMBIGUOUS: with --title-file use one SPEC, "
                    "--spec-file PATH or --stdin"
                )
            positional_spec = title
        elif parsed.workflow is None:
            workflow = title
        elif title is not None:
            raise ValueError("TITLE_SOURCE_AMBIGUOUS: pass TITLE or --title-file PATH")
        title = None
    if title is None and not parsed.title_file:
        raise ValueError("TITLE_REQUIRED: add TITLE or --title-file PATH")
    if not workflow:
        raise ValueError("WORKFLOW_REQUIRED: add WORKFLOW after TITLE")
    try:
        title = resolve_text_file(title, parsed.title_file, "--title-file")
        spec = None
        if positional_spec is not None or parsed.spec_file or parsed.stdin:
            spec = resolve_one_text_source(
                positional=positional_spec,
                file_path=parsed.spec_file,
                stdin=parsed.stdin,
                positional_label="SPEC",
                file_flag="--spec-file",
            )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(
            f"ITEM_TEXT_SOURCE_INVALID: {exc}. Use --title-file PATH for title "
            "and --spec-file PATH or --stdin for spec."
        ) from exc
    if not title or not title.strip():
        raise ValueError("TITLE_REQUIRED: add a nonblank TITLE or --title-file PATH")
    if workflow in ("dash", "task") and not (spec or "").strip():
        raise ValueError(
            "SPEC_REQUIRED: add --spec-file PATH or --stdin with a nonblank spec"
        )
    return title.strip(), workflow, spec
