"""Every setup screen declares a prompt, and both shells walk one flow list."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

import yoke_cli.config as config_package

pytest.importorskip("textual")

CONFIG_DIR = Path(config_package.__file__).parent
PROMPT_BUILDERS = {"_selection_view", "_goto_input"}


def _screen_modules() -> list[Path]:
    return sorted(
        path
        for path in CONFIG_DIR.glob("*.py")
        if path.name.startswith(("onboard_wizard", "onboard_github_copy", "setup_"))
    )


def _calls(name_filter):
    """Matching calls with their module and innermost enclosing function."""
    for path in _screen_modules():
        stack: list[tuple[ast.AST, str]] = [(ast.parse(path.read_text(encoding="utf-8")), "")]
        while stack:
            node, owner = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = node.name
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name_filter(name):
                    yield f"{path.name}:{owner or '<module>'}", node, name
            stack.extend((child, owner) for child in ast.iter_child_nodes(node))


def _key_expression(node: ast.Call, name: str) -> ast.expr | None:
    if name == "SetupPrompt":
        return next((kw.value for kw in node.keywords if kw.arg == "key"), None)
    if node.args:
        return node.args[0]
    return next((kw.value for kw in node.keywords if kw.arg == "key"), None)


def _string_constants() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in _screen_modules():
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        found[target.id] = node.value.value
    return found


def _prompt_sites() -> tuple[dict[str, list[str]], list[str]]:
    literal: dict[str, list[str]] = defaultdict(list)
    passed_through: list[str] = []
    constants = _string_constants()
    for site, node, name in _calls(lambda n: n == "SetupPrompt" or n in PROMPT_BUILDERS):
        key = _key_expression(node, name)
        if isinstance(key, ast.Name) and key.id in constants:
            key = ast.Constant(constants[key.id])
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if site not in literal[key.value]:
                literal[key.value].append(site)
        else:
            passed_through.append(f"{site} {name}({ast.unparse(key) if key else '<no key>'})")
    return literal, passed_through


def test_both_shells_compose_the_one_flow_list():
    from yoke_cli.config.onboard_wizard_app import OnboardWizardApp
    from yoke_cli.config.onboard_wizard_flows import SETUP_FLOWS
    from yoke_cli.config.setup_agent_shell import AgentSetup

    def flows(shell: type) -> tuple[type, ...]:
        return tuple(base for base in shell.__bases__ if base in SETUP_FLOWS)

    assert flows(OnboardWizardApp) == SETUP_FLOWS
    assert flows(AgentSetup) == SETUP_FLOWS
    assert len(SETUP_FLOWS) == len(set(SETUP_FLOWS))


def test_a_view_cannot_be_built_without_a_prompt():
    from yoke_cli.config.onboard_wizard_state import _View

    with pytest.raises(TypeError):
        _View()  # type: ignore[call-arg]
    for site, node, _ in _calls(lambda n: n == "_View"):
        has_prompt = bool(node.args) or any(kw.arg == "prompt" for kw in node.keywords)
        assert has_prompt, f"{site}:{node.lineno} builds a _View without a prompt"


def test_every_prompt_site_names_a_dotted_key_used_once():
    literal, passed_through = _prompt_sites()

    assert literal, "no prompt keys found; the scan is looking in the wrong place"
    duplicated = {key: sites for key, sites in literal.items() if len(sites) > 1}
    assert duplicated == {}
    malformed = [key for key in literal if "." not in key or key != key.strip() or " " in key]
    assert malformed == []
    # A key handed in by the caller is checked where the caller names it; a
    # formatted key still starts from a fixed dotted step name.
    for site in passed_through:
        assert "<no key>" not in site, site
        assert site.endswith("(key)") or "(f'" in site and "." in site.split("(f'")[1], site


def test_every_prompt_with_a_key_asks_something_or_is_a_progress_screen():
    from yoke_cli.config.setup_prompt import SetupPrompt

    answer_fields = {"choices", "input", "fields"}
    silent: list[str] = []
    for site, node, _ in _calls(lambda n: n == "SetupPrompt"):
        given = {kw.arg for kw in node.keywords}
        if not given & answer_fields:
            key = _key_expression(node, "SetupPrompt")
            silent.append(ast.unparse(key) if key is not None else f"{site}:{node.lineno}")
    assert SetupPrompt(key="t.x", step="t", title="t").answerable is False
    assert sorted(silent) == sorted(SILENT_PROMPT_KEYS), sorted(silent)


# Screens that ask nothing: progress, checks and dead-end errors. Agent mode
# reports reaching one as ``setup_step_failed`` with the screen's own message.
SILENT_PROMPT_KEYS = ["'review.error'", "APPLYING_KEY", "f'check.{group}'"]
