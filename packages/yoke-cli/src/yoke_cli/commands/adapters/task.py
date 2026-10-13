"""Task shortcut for the shared item filing command."""

from yoke_cli.commands.adapters.items_create import items_create


def task_file(args: list[str]) -> int:
    return items_create(args, shortcut="task")
