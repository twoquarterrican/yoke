"""Shared constants and primitives for project board-art generation."""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass
from typing import List


from yoke_contracts.project_contract.board_art.config import BLACK, WHITE
from yoke_contracts.project_contract.board_art.font_pool import (
    ASCII_FIGLET_FONTS as ASCII_FIGLET_FONTS,
)
from yoke_contracts.project_contract.board_art._data import _MASTER_MAP_GLYPHS


MAX_ART_WORD_LEN = 8
FALLBACK_ART_WORD = "PROJECT"
ASCII_VARIANT_COUNT = 1
MIXED_VARIANT_COUNT = 1
MIXED_VARIANT_GAP = 2
# Emoji canvas budget for the image-to-art downsample pipeline (cols * rows =
# area cap). Independent of the product wordmark: it sizes the grid an arbitrary
# image is downsampled onto, not the YOKE header glyphs.
CURRENT_YOKE_MASTER_MAP_COLUMNS = 47
# Visual width of the rendered YOKE master-map wordmark. ``_master_map_lines``
# lays out one leading border column plus, per letter, the hand-tuned glyph
# cells and a trailing separator column, and every cell renders as a 2-wide
# emoji square. Derived from the actual glyph geometry so the variant-width
# invariant tracks the wordmark instead of the image canvas.
_YOKE_WORDMARK = "YOKE"
_MASTER_MAP_GLYPH_WIDTH = len(_MASTER_MAP_GLYPHS[_YOKE_WORDMARK[0]][0])
CURRENT_YOKE_MASTER_MAP_VISUAL_WIDTH = (
    1 + len(_YOKE_WORDMARK) * (_MASTER_MAP_GLYPH_WIDTH + 1)
) * 2
# Default visual-width ceiling for board-art variant generation — the interactive
# ``yoke board art variant create`` command, the library helpers, and
# onboarding seed art (``render_board_art``) all default to this bound. Kept
# separate from the master-map width so generated variants may run wider than the
# YOKE header; the generator still rejects anything above this bound.
DEFAULT_VARIANT_MAX_WIDTH = 140


@dataclass(frozen=True)
class BoardArtVariant:
    """A generated board-art variant plus the parts needed to reroll it."""

    kind: str
    text: str
    word: str
    font: str | None = None
    emoji_index: int | None = None
    ascii_art: str | None = None
    emoji_column: str | None = None


_ART_HEADER = """\
# Board header art — read by the Yoke board renderer on every rebuild.
# Render tuning (bucket weights, frontier window) lives in project-policy.settings.board;
# to pin a variant, set art_override there (e.g. frontier, rainbow_letters,
# ascii_1, mixed_1).
#
# Sections:
#   ## Master Map  -- emoji grid of {white} (fill target) and {black} (structural) cells;
#                     drives the frontier progress fill and rainbow modes.
#   ## Emoji       -- hand-drawn standalone emoji grids, rendered verbatim.
#   ## ASCII       -- raw monospace text art (no dimension constraints).
#   ## Mixed       -- text + emoji, pasted like ASCII art.
#
# A "# weight:N" line immediately above a section header weights that variant
# within its bucket; once any variant in a bucket carries a weight, unweighted
# variants in that bucket fall to 0. "# weight-disabled:N" is ignored (parked).
"""


def _tokens(value: str | None) -> List[str]:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[A-Za-z0-9]+", ascii_value.upper())


def choose_art_word(
    display_name: str,
    *,
    slug: str | None = None,
    max_len: int = MAX_ART_WORD_LEN,
) -> str:
    """Choose the word rendered in a new project's board art."""

    tokens = _tokens(display_name) or _tokens(slug)
    joined = "".join(tokens)
    if 1 <= len(joined) <= max_len:
        return joined

    acronym = "".join(token[0] for token in tokens if token)
    if len(tokens) > 1 and 2 <= len(acronym) <= max_len:
        return acronym

    if joined:
        return joined[:max_len]

    return FALLBACK_ART_WORD


# Header art (ASCII / Mixed / image-backed) renders through pyfiglet and a
# width-fit check, so it tolerates far longer text than the master map's fixed
# glyph grid — this cap only bounds runaway input; the generators still reject
# anything that does not fit ``max_width``.
MAX_HEADER_ART_WORD_LEN = 24

_VOWELS = frozenset("AEIOU")


def _drop_vowels_to_fit(word: str, max_len: int) -> str:
    """Shorten an over-long token: keep the first letter, drop interior vowels
    right-to-left until it fits, then hard-cut. Deterministic."""
    if len(word) <= max_len:
        return word
    first, rest = word[:1], list(word[1:])
    while len(rest) + len(first) > max_len:
        drop_at = next(
            (i for i in range(len(rest) - 1, -1, -1) if rest[i] in _VOWELS), None
        )
        if drop_at is None:
            break
        del rest[drop_at]
    return (first + "".join(rest))[:max_len]


def resolve_project_art_word(
    display_name: str = "",
    *,
    slug: str | None = None,
    short_code: str | None = None,
    max_len: int = MAX_ART_WORD_LEN,
) -> str:
    """Pick a board-art word from a project's name forms, most-recognizable first.

    Walks a ladder of candidate forms and returns the first that is
    ``1..max_len`` alphanumerics:

      1. the whole display name (tokens joined)
      2. the first word of the display name
      3. the display-name acronym (initials)
      4. the slug's first segment
      5. the short code (public item prefix, e.g. ``EXT``)

    If none fit, falls back to vowel-dropping truncation of the best human
    candidate, then to :data:`FALLBACK_ART_WORD`. Every form is normalized to
    uppercase alphanumerics so the result is a valid master-map glyph word.
    """
    display_tokens = _tokens(display_name)
    slug_tokens = _tokens(slug)

    candidates: List[str] = ["".join(display_tokens)]
    if display_tokens:
        candidates.append(display_tokens[0])
    if len(display_tokens) > 1:
        candidates.append("".join(token[0] for token in display_tokens))
    if slug_tokens:
        candidates.append(slug_tokens[0])
    code = "".join(_tokens(short_code))
    if code:
        candidates.append(code)

    for candidate in candidates:
        if 1 <= len(candidate) <= max_len:
            return candidate

    best = next((candidate for candidate in candidates if candidate), "")
    if best:
        truncated = _drop_vowels_to_fit(best, max_len)
        if truncated:
            return truncated
    return FALLBACK_ART_WORD[:max_len]


def normalize_master_map_word(value: str, *, max_len: int = MAX_ART_WORD_LEN) -> str:
    """Coerce free text to a master-map word: uppercase glyph-set alphanumerics,
    capped to ``max_len``. Returns ``""`` when nothing usable remains."""
    return "".join(_tokens(value))[:max_len]


def normalize_header_art_word(
    value: str, *, max_len: int = MAX_HEADER_ART_WORD_LEN
) -> str:
    """Coerce free text to a header-art word: letters, numbers, and single
    spaces, uppercased, capped to ``max_len``. Header art renders through
    pyfiglet so spaces and longer words are fine; the empty string maps to
    ``""`` so callers can fall back to the default word."""
    upper = "".join(ch if (ch.isalnum() or ch == " ") else " " for ch in value.upper())
    return " ".join(upper.split())[:max_len]


def _master_map_lines(word: str) -> List[str]:
    rows: List[str] = []
    for row_index in range(len(next(iter(_MASTER_MAP_GLYPHS.values())))):
        cells = ["."]
        for letter in word:
            cells.append(_MASTER_MAP_GLYPHS[letter][row_index])
            cells.append(".")
        rows.append("".join(cells))
    border = "." * len(rows[0])
    rows.insert(0, border)
    rows.append(border)
    return [row.replace("X", WHITE).replace(".", BLACK) for row in rows]


def _digest_for(seed_text: str) -> bytes:
    return hashlib.sha256(seed_text.encode("utf-8")).digest()


def _digest_for_parts(*parts: str) -> bytes:
    return _digest_for("\0".join(parts))


def _resolve_seed(seed_text: str | None) -> str:
    return seed_text if seed_text is not None else secrets.token_hex(16)


def _is_wide_char(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x1F300 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2B1B <= cp <= 0x2B1C
        or 0x2B50 <= cp <= 0x2B55
        or 0x1100 <= cp <= 0x115F
        or 0x2E80 <= cp <= 0x303E
        or 0x3040 <= cp <= 0xA4CF
        or 0xAC00 <= cp <= 0xD7AF
        or 0xF900 <= cp <= 0xFAFF
        or 0xFF00 <= cp <= 0xFF60
        or 0xFFE0 <= cp <= 0xFFE6
    )


def _visual_width(text: str) -> int:
    return sum(2 if _is_wide_char(ch) else 1 for ch in text)


def _art_visual_width(text: str) -> int:
    return max((_visual_width(line) for line in text.splitlines()), default=0)


def _fits_header_width(text: str, max_width: int) -> bool:
    return _art_visual_width(text) <= max_width


def _pad_to_width(text: str, width: int) -> str:
    return text + " " * max(0, width - _visual_width(text))


def _trim_lines(lines: list[str] | tuple[str, ...]) -> List[str]:
    start = 0
    end = len(lines) - 1
    while start <= end and not lines[start].strip():
        start += 1
    while end >= start and not lines[end].strip():
        end -= 1
    return list(lines[start : end + 1])
