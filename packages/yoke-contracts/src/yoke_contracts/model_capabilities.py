"""Declared cross-provider model capability ordering for session labels.

Ranks are operator policy, not measured benchmark or latency claims. Speed
is an ordinal: standard=0, fast=1. Unknown models/efforts prove no dominance.
Native selector parsing stays with the existing shared Cursor parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from yoke_contracts.session_control.native_model_parsers import (
    cursor_selector_without_effort,
    cursor_token_effort,
)


@dataclass(frozen=True)
class ModelCapability:
    rank: int
    speed: int


MODEL_CAPABILITIES = MappingProxyType(
    {
        "claude-haiku-5-5": ModelCapability(1, 0),
        "gpt-6-luna": ModelCapability(1, 0),
        "grok-4.7": ModelCapability(2, 0),
        "gpt-5.6-terra": ModelCapability(2, 0),
        "claude-sonnet-5-5": ModelCapability(2, 0),
        "claude-opus-5-5": ModelCapability(3, 0),
        "gpt-6.1-sol": ModelCapability(3, 0),
        "claude-fable-5-1": ModelCapability(4, 0),
        "gpt-6-astra": ModelCapability(4, 0),
    }
)
EFFORT_RANKS = MappingProxyType(
    {
        "none": 0,
        "minimal": 1,
        "low": 2,
        "medium": 3,
        "high": 4,
        "xhigh": 5,
        "extra-high": 5,
        "max": 6,
        "ultra": 7,
    }
)


def selection_capability(model: str, effort: str | None) -> tuple[int, int, int] | None:
    """Return the declared model, speed and effort ordinals, if all are known."""
    token = model.strip().lower()
    encoded = cursor_token_effort(token)
    effort_name = (effort or encoded or "").strip().lower()
    if encoded and effort_name != encoded:
        return None
    base = cursor_selector_without_effort(token).removesuffix("-fast")
    capability = MODEL_CAPABILITIES.get(base)
    effort_rank = EFFORT_RANKS.get(effort_name)
    if capability is None or effort_rank is None:
        return None
    speed = capability.speed + int(token.endswith("-fast"))
    return capability.rank, speed, effort_rank


def selection_dominates(actual: tuple[int, int, int], model: str, effort: str) -> bool:
    """Require equality or improvement on every axis of a declared option."""
    required = selection_capability(model, effort)
    return required is not None and all(a >= b for a, b in zip(actual, required))
