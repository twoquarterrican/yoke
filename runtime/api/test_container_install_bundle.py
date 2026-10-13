"""The runtime image's declared source tree must render a project bundle."""

import shutil
from pathlib import Path

import pytest

from yoke_core.domain.install_bundle import INSTALL_BUNDLE_SOURCE_DIRS
from yoke_core.domain.install_bundle_sources import (
    HARNESS_MANIFEST_SOURCES,
    INSTALL_BUNDLE_SOURCE_FILES,
    InstallBundleTreeError,
)
from yoke_core.tools.container_bundle_validation import (
    stage_source_files,
    verify_project_bundle,
)


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def image_tree(tmp_path):
    root = tmp_path / "server-tree"
    for relative in INSTALL_BUNDLE_SOURCE_DIRS:
        shutil.copytree(ROOT / relative, root / relative)
    stage_source_files(ROOT, root)
    return root


def test_staging_uses_all_canonical_standalone_inputs(tmp_path):
    stage_source_files(ROOT, tmp_path)
    assert sorted(
        str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file()
    ) == sorted(INSTALL_BUNDLE_SOURCE_FILES)
    for relative in HARNESS_MANIFEST_SOURCES:
        assert (tmp_path / relative).read_bytes() == (ROOT / relative).read_bytes()


def test_project_bundle_builds_against_image_tree(image_tree):
    bundle = verify_project_bundle(image_tree)
    assert bundle["project_slug"] == "image-check"
    assert bundle["project_contract_files"]


@pytest.mark.parametrize("relative", HARNESS_MANIFEST_SOURCES)
def test_missing_image_manifest_fails_bundle_gate(image_tree, relative):
    (image_tree / relative).unlink()
    with pytest.raises(
        InstallBundleTreeError, match="install_bundle_source_unreadable"
    ):
        verify_project_bundle(image_tree)


def test_docker_build_gates_the_real_runtime_tree():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "stage-source-files /build /bundle-source-files" in dockerfile
    assert "COPY --from=builder /bundle-source-files /srv/yoke-tree" in dockerfile
    gate = "RUN python -m yoke_core.tools.container_bundle_validation verify /srv/yoke-tree"
    assert gate in dockerfile
    assert dockerfile.index(gate) > dockerfile.index(
        "yoke_core.tools.product_wheel_validation"
    )
