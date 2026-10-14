"""Keep interpreter-independent repository checks on the newest CI leg."""

import os

import pytest


def version_independent(node_id: str, fixtures=()) -> bool:
    path = node_id.split("::", 1)[0]
    name = path.rsplit("/", 1)[-1]
    return (
        "product_wheelhouse" in fixtures
        or "product_venv" in fixtures
        or path.startswith("tests/teaching_prototype/")
        or name.endswith("_docs.py")
        or "_teaching" in name
        or name.startswith(
            (
                "test_path_snapshot",
                "test_install_bundle",
                "test_doctor_hc_",
                "test_doc_",
                "test_docs_",
                "test_generated_",
            )
        )
        or name
        in {
            "test_doctor_project_check_execution.py",
            "test_generated_block_render.py",
            "test_atlas_render_docs.py",
            "test_disposable_generated_paths_policy.py",
        }
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "ci_version_independent: repository and installed-wheel checks"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    if os.environ.get("YOKE_CI_PYTHON_SCOPE") != "interpreter":
        return
    kept, deselected = [], []
    for item in items:
        independent = version_independent(
            item.nodeid, item.fixturenames
        ) or item.get_closest_marker("ci_version_independent")
        (deselected if independent else kept).append(item)
    items[:] = kept
    config.hook.pytest_deselected(items=deselected)
