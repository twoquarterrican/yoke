"""Interpreter selection happens before duration splitting."""

from types import SimpleNamespace
from unittest.mock import Mock

from runtime import ci_test_selection as selection


def _item(node_id, fixtures=()):
    return SimpleNamespace(
        nodeid=node_id, fixturenames=fixtures, get_closest_marker=lambda _: None
    )


def test_oldest_leg_deselects_repository_and_wheel_checks(monkeypatch):
    monkeypatch.setenv("YOKE_CI_PYTHON_SCOPE", "interpreter")
    independent = [
        _item("tests/teaching_prototype/test_map.py::test_links"),
        _item("runtime/api/test_runtime.py::test_installed", ["product_venv"]),
        _item("runtime/api/domain/test_path_snapshots.py::test_graph"),
        _item("runtime/api/engines/test_doctor_hc_paths.py::test_tree"),
        _item("runtime/api/test_doc_hygiene.py::test_links"),
        _item("runtime/api/test_command_teaching.py::test_recipe"),
    ]
    runtime = _item("runtime/api/test_service_client.py::test_parser")
    items = independent + [runtime]
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=Mock()))
    selection.pytest_collection_modifyitems(config, items)
    assert items == [runtime]
    config.hook.pytest_deselected.assert_called_once_with(items=independent)


def test_latest_and_local_runs_keep_every_test(monkeypatch):
    monkeypatch.delenv("YOKE_CI_PYTHON_SCOPE", raising=False)
    items = [_item("tests/teaching_prototype/test_map.py::test_links")]
    selection.pytest_collection_modifyitems(None, items)
    assert len(items) == 1
