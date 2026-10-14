"""Product-wheel help labels for non-product command surfaces."""

from __future__ import annotations

from pathlib import Path

from runtime.api.cli.test_yoke_product_distribution_wheel import (
    _assert_command,
    _product_env,
)


def test_product_wheel_help_labels_non_product_surfaces(
    tmp_path: Path,
    product_wheelhouse: Path,
    product_venv: Path,
) -> None:
    venv_dir = product_venv
    yoke = venv_dir / "bin" / "yoke"

    project = tmp_path / "external-project"
    machine_home = tmp_path / "home" / ".yoke"
    project.mkdir()
    machine_home.mkdir(parents=True)
    env = _product_env(machine_home=machine_home, venv_dir=venv_dir)

    top_help = _assert_command(yoke, project, env, ["--help"], 0)
    assert "yoke dev" in top_help.stdout
    assert "yoke qa" in top_help.stdout
    assert "yoke qa browser screenshot" not in top_help.stdout

    for args, expected in (
        (["dev", "--help"], "yoke dev setup [source-dev/admin]"),
        (["agents", "--help"], "yoke agents render [source-dev/admin]"),
        (["packets", "--help"], "yoke packets check [source-dev/admin]"),
        (["merge", "--help"], "yoke merge audit [source-dev/admin]"),
        (["resync", "--help"], "source-dev/admin command surface"),
        (["project", "--help"], "yoke project install"),
        (["projects", "--help"], "yoke projects create"),
        (["strategy", "doc", "--help"], "yoke strategy doc list"),
        (
            ["qa", "browser", "--help"],
            "yoke qa browser screenshot [client-local]",
        ),
        (
            ["github-actions", "secret", "--help"],
            "yoke github-actions secret set [source-dev/admin]",
        ),
    ):
        _assert_command(yoke, project, env, args, 0, expected)
