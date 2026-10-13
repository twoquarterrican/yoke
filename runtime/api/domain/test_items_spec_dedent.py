"""Spec write-path dedent tests.

``yoke_core.domain.items.update_structured_field`` runs incoming ``spec``
content through ``textwrap.dedent`` so uniformly indented heredoc content
round-trips without its leading prefix. Other structured fields are
deliberately left byte-exact.
"""

from __future__ import annotations

from pathlib import Path

from runtime.api.fixtures.file_test_db import init_test_db
from yoke_core.domain import items

import pytest

pytestmark = pytest.mark.usefixtures("bound_project_context")


@pytest.fixture
def db_path(tmp_path: Path):
    with init_test_db(tmp_path) as path:
        yield path


def _seed_item(db_path: str, item_id: int, title: str) -> None:
    items.insert_item(
        item_id=item_id,
        title=title,
        workflow="issue",
        project="yoke",
        db_path=db_path,
    )


def test_spec_write_dedents_uniform_leading_prefix(db_path: str) -> None:
    _seed_item(db_path, 42, "Indented spec item")

    indented_spec = (
        "    # Spec: Indented spec item\n"
        "\n"
        "    ## Acceptance Criteria\n"
        "    - [ ] AC-1: First\n"
        "    - [ ] AC-2: Second\n"
    )
    items.update_structured_field(42, "spec", indented_spec, db_path=db_path)

    stored = items.query_item(42, "spec", db_path=db_path)
    assert "\n    - [ ] AC-1" not in stored
    assert stored.startswith("# Spec: Indented spec item")
    assert "\n- [ ] AC-1: First" in stored
    assert "\n- [ ] AC-2: Second" in stored


def test_spec_write_leaves_column_zero_content_untouched(db_path: str) -> None:
    _seed_item(db_path, 43, "Already flat spec")

    flat_spec = (
        "# Spec: Already flat spec\n"
        "\n"
        "## Acceptance Criteria\n"
        "- [ ] AC-1: First\n"
        "- [ ] AC-2: Second\n"
    )
    items.update_structured_field(43, "spec", flat_spec, db_path=db_path)

    stored = items.query_item(43, "spec", db_path=db_path)
    assert stored == flat_spec


def test_spec_write_preserves_mixed_indentation(db_path: str) -> None:
    """textwrap.dedent only strips the *common* leading prefix. A spec with
    some column-zero lines keeps its column-zero structure intact — only
    the intentionally indented sub-blocks keep their relative indent."""
    _seed_item(db_path, 44, "Mixed spec")

    mixed_spec = (
        "# Spec: Mixed spec\n"
        "\n"
        "## Example\n"
        "\n"
        "    indented code block\n"
        "\n"
        "## Acceptance Criteria\n"
        "- [ ] AC-1: First\n"
    )
    items.update_structured_field(44, "spec", mixed_spec, db_path=db_path)

    stored = items.query_item(44, "spec", db_path=db_path)
    # Common prefix is empty, so nothing changes.
    assert stored == mixed_spec
    assert "    indented code block" in stored


def test_non_spec_structured_field_is_not_dedented(db_path: str) -> None:
    """scopes the dedent to ``spec`` only; other structured
    fields must round-trip byte-exact until explicit need extends the
    behavior."""
    _seed_item(db_path, 45, "Design spec item")

    indented_design = "    ## Design\n    - First\n    - Second\n"
    items.update_structured_field(45, "design_spec", indented_design, db_path=db_path)

    stored = items.query_item(45, "design_spec", db_path=db_path)
    assert stored == indented_design
