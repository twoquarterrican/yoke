"""Stored native-selector Levels converge without preserving the fallback path."""

import importlib
from yoke_contracts.levels import levels_payload, default_levels

migration = importlib.import_module(
    "yoke_core.domain.migrations.0071_model_effort_levels"
)


def test_legacy_variants_fold_and_fallback_is_retired():
    old = [
        {
            "name": "JUNIOR",
            "glyph": "🐥",
            "options": [
                {
                    "surface": "cursor-cli",
                    "model": "grok-4.7-high",
                    "reasoning_effort": "high",
                    "context_window_tokens": None,
                    "fallback": {
                        "surface": "cursor-cli",
                        "model": "claude-opus-5-5-medium",
                        "reasoning_effort": "medium",
                    },
                },
                {
                    "surface": "cursor-cli",
                    "model": "grok-4.7-high-fast",
                    "reasoning_effort": "high",
                    "context_window_tokens": None,
                },
            ],
        }
    ]
    assert migration.converged(old) == [
        {
            "name": "JUNIOR",
            "glyph": "🐥",
            "options": [{"model": "grok-4.7", "min_effort": "high"}],
        }
    ]


def test_current_document_is_idempotent():
    current = levels_payload(default_levels())
    assert migration.converged(current) == current
    assert migration.converged(migration.converged(current)) == current


def test_duplicate_native_surface_rows_keep_the_lower_threshold():
    old = [
        {
            "name": "SENIOR",
            "glyph": "🦉",
            "options": [
                {
                    "surface": "claude-cli",
                    "model": "claude-opus-5-5",
                    "reasoning_effort": "high",
                },
                {
                    "surface": "cursor-cli",
                    "model": "claude-opus-5-5-medium",
                    "reasoning_effort": "medium",
                },
            ],
        }
    ]
    assert migration.converged(old)[0]["options"] == [
        {"model": "claude-opus-5-5", "min_effort": "medium"}
    ]
