"""Invalid teaching models report all references before rendering or writing."""

from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "docs/teaching/tools"


@pytest.mark.parametrize("args", [[], ["--check"], ["--live"]])
def test_dangling_references_fail_before_rendering(monkeypatch, tmp_path, capsys, args):
    monkeypatch.syspath_prepend(str(TOOLS))
    import build

    loaded = build.load()
    loaded.concepts["documentation"]["surface_refs"] = [
        "missing-surface",
        "another-missing-surface",
    ]
    loaded.gaps["shared-access"]["related_scenarios"] = ["missing-scenario"]
    monkeypatch.setattr(build, "load", lambda: loaded)
    views = tmp_path / "views"
    views.mkdir()
    existing = views / "index.html"
    existing.write_text("existing views")
    monkeypatch.setattr(build, "VIEWS_ROOT", views)
    monkeypatch.setattr(build, "LIVE_ROOT", tmp_path / "live")

    def refuse_render(*_args, **_kwargs):
        pytest.fail("invalid model reached rendering")

    monkeypatch.setattr(build, "Pages", refuse_render)
    assert build.main(args) == 1
    output = capsys.readouterr().out
    assert output.count("DANGLING_REFERENCE:") == 3
    for target in ("missing-surface", "another-missing-surface", "missing-scenario"):
        assert target in output
    assert "docs/teaching/model/concepts/documentation.json:documentation" in output
    assert "docs/teaching/model/gaps/shared-access.json:shared-access" in output
    assert "surface_refs" in output
    assert "related_scenarios" in output
    assert "Fix the model" in output
    assert "--check" in output
    assert "Traceback" not in output
    assert existing.read_text() == "existing views"
    assert list(views.iterdir()) == [existing]
    assert not build.LIVE_ROOT.exists()
