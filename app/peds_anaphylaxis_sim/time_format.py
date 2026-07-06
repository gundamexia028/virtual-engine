from __future__ import annotations

from typing import Any


def format_elapsed_time(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60:02d}:{total % 60:02d}"


def format_timeline_value(key: object, value: Any) -> str:
    if value is None:
        return ""
    name = str(key or "")
    if isinstance(value, bool):
        return str(value)
    non_time_tokens = (
        "dose_mg",
        "volume_ml",
        "_min_ml",
        "_max_ml",
        "_count",
        "_valid",
        "_triggered",
        "_required",
    )
    if isinstance(value, (int, float)) and not any(
        token in name for token in non_time_tokens
    ):
        return format_elapsed_time(value)
    return str(value)
