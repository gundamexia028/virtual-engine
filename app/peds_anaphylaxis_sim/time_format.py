from __future__ import annotations

from typing import Any


def format_elapsed_time(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError, OverflowError):
        total = 0
    return f"{total // 60:02d}:{total % 60:02d}"


def format_timeline_value(key: object, value: Any) -> str:
    if value is None:
        return ""
    name = str(key or "")
    if isinstance(value, bool):
        return str(value)
    # Units are suffixes: steroid_min_mg is a dose, never a minute value.
    if name.endswith(("_mg", "_ml", "_count", "_min", "_minutes")):
        return str(value)
    if isinstance(value, (int, float)) and (
        name in TIMELINE_TIME_KEYS or name.endswith(("_time", "_sec", "_seconds"))
    ):
        return format_elapsed_time(value)
    return str(value)


TIMELINE_TIME_KEYS = frozenset({
    "stop_infusion", "call_help", "abc_assess", "oxygen", "position", "monitor",
    "bp_check", "epi_im", "fluid", "first_reassessment", "second_reassessment",
    "bronchodilator", "steroid", "nebulized_epinephrine", "repeat_epinephrine",
    "advanced_support", "bvm_ventilation", "cpr", "allergy_identification",
    "prepare_rescue_equipment", "academy_reassess", "academy_family_communication",
    "academy_sbar_handoff", "ask_family_first", "send_family_for_help",
    "prepare_steroid_antihistamine_only", "student_independent_epinephrine", "watch_only",
    "family_communication", "sbar_handoff", "establish_iv",
})


def timeline_unit(key: object, value: Any) -> str:
    name = str(key or "")
    if name.endswith("_mg"):
        return "mg"
    if name.endswith("_ml"):
        return "ml"
    if name.endswith("_count"):
        return "次"
    if name.endswith(("_min", "_minutes")):
        return "min"
    if isinstance(value, bool):
        return "是/否"
    if name in TIMELINE_TIME_KEYS or name.endswith(("_time", "_sec", "_seconds")):
        return "mm:ss"
    return ""
