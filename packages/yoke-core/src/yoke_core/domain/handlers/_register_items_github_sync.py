"""Handler registrations for ``items.github_sync``."""

from __future__ import annotations

from yoke_core.domain.handlers import items_github_sync, items_github_link


def register(registry) -> None:
    """Register item GitHub sync handlers via the given registry."""
    for entry in (*items_github_sync.REGISTRATIONS, *items_github_link.REGISTRATIONS):
        registry.register(**entry)
