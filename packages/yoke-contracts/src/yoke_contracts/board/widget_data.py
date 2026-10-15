"""Pure board widget rendering from named counts and daily series."""

from typing import List
from yoke_contracts.project_contract.board_art import emoji as E

_CLOCK = E.BADGE_CLOCK
_TAG = E.BADGE_WORKFLOW
_MEDAL = E.BADGE_MILESTONE
_TARGET = E.BADGE_STREAK
_SHIELD = E.BADGE_ZERO_BUGS
_MAILBOX = E.BADGE_INBOX_ZERO

# Age heatmap colors
_AGE_FRESH = E.AGE_FRESH
_AGE_WEEK = E.AGE_WEEK
_AGE_BIWEEK = E.AGE_BIWEEK
_AGE_MONTH = E.AGE_MONTH
_AGE_ANCIENT = E.AGE_ANCIENT


def render_weather_count(backlog: int) -> str:
    if backlog < 10:
        return "🌞 Clear"  # sun (Clear)
    elif backlog < 25:
        return "\u26c5 Fair"  # ⛅ Fair
    else:
        return "☔ Stormy"  # umbrella (Stormy)


def render_age_counts(counts: dict) -> str | None:
    fresh = int(counts["fresh"] or 0)
    week = int(counts["week"] or 0)
    biweek = int(counts["biweek"] or 0)
    month = int(counts["month"] or 0)
    ancient = int(counts["ancient"] or 0)
    total = int(counts["total"] or 0)

    if total == 0:
        return None

    # Allocate up to 20 cells proportionally
    max_cells = 20
    buckets = [
        ("fresh", fresh, _AGE_FRESH),
        ("week", week, _AGE_WEEK),
        ("biweek", biweek, _AGE_BIWEEK),
        ("month", month, _AGE_MONTH),
        ("ancient", ancient, _AGE_ANCIENT),
    ]

    cells = _allocate_proportional([count for _, count, _ in buckets], total, max_cells)

    bar = ""
    for i, (_, _, emoji) in enumerate(buckets):
        bar += emoji * cells[i]

    return (
        f"{_CLOCK} {bar} age: "
        f"{_AGE_FRESH}<6h {_AGE_WEEK}<1d {_AGE_BIWEEK}<3d "
        f"{_AGE_MONTH}<1w {_AGE_ANCIENT}>1w"
    )


def _allocate_proportional(counts: List[int], total: int, max_cells: int) -> List[int]:
    """Allocate cells proportionally with rounding.

    Non-zero counts get at least 1 cell. Excess is trimmed from the largest.
    """
    if total <= 0:
        return [0] * len(counts)

    half = total // 2
    cells = [((c * max_cells + half) // total) for c in counts]

    # Ensure at least 1 for non-zero
    for i, c in enumerate(counts):
        if c > 0 and cells[i] < 1:
            cells[i] = 1

    # Clamp: reduce largest bucket if over max_cells
    while sum(cells) > max_cells:
        largest_idx = 0
        largest_val = cells[0]
        for i in range(1, len(cells)):
            if cells[i] > largest_val:
                largest_val = cells[i]
                largest_idx = i
        cells[largest_idx] -= 1

    return cells


def render_workflow_counts(rows) -> str | None:
    if not rows:
        return None

    parts = []
    for row in rows:
        workflow_id = row[0]
        if not workflow_id:
            continue
        parts.append(f"{workflow_id}:{int(row[1])}")

    if not parts:
        return None

    return f"{_TAG} {' '.join(parts)}"


def render_velocity_series(dates, activity, code, issues, strategy) -> list[str]:
    from yoke_contracts.board.widgets_activity import _CHART, _build_sparkline

    act_counts, effort_counts, del_counts, sml_counts = activity, code, issues, strategy
    act_spark = _build_sparkline([act_counts.get(d, 0) for d in dates])
    effort_spark = _build_sparkline([effort_counts.get(d, 0) for d in dates])
    del_spark = _build_sparkline([del_counts.get(d, 0) for d in dates])
    sml_spark = _build_sparkline([sml_counts.get(d, 0) for d in dates])

    return [
        f"{_CHART} {act_spark} 120d activity",
        f"{E.VELOCITY_CODE} {effort_spark} 120d code",
        f"{E.VELOCITY_DELIVERY} {del_spark} 120d issues",
        f"{E.VELOCITY_STRATEGY} {sml_spark} 120d strategy",
    ]
