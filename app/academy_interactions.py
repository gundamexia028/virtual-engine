from __future__ import annotations

from typing import Any, Dict, Iterable, List


ACADEMY_ASSISTED_MEDICATION_ACTION_ID = "academy_assisted_medication"
ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID = "prepare_rescue_equipment"
ACADEMY_ASSISTED_MEDICATION_SHORT_LABEL = "配合完成给药"
ACADEMY_ASSISTED_MEDICATION_FULL_LABEL = (
    "在老师/医生指导下核对患儿体重、药名、剂量和给药途径，"
    "并配合完成肾上腺素肌内注射。"
)
ACADEMY_ASSISTED_MEDICATION_RESULT = (
    "已在护生角色边界内完成药物核对与给药配合。"
)


def assisted_medication_action() -> Dict[str, Any]:
    """Return a presentation-only academy action.

    The action deliberately maps to the existing rescue-preparation core action.
    It does not add or rename a scenario action id and does not alter scoring,
    dose, route, timing, vital-sign, or completion rules.
    """

    return {
        "id": ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
        "label": ACADEMY_ASSISTED_MEDICATION_FULL_LABEL,
        "presentation_only": True,
        "core_action_id": ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID,
    }


def add_assisted_medication_choice(
    actions: Iterable[Dict[str, Any]],
    flags: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Expose the compliant cooperation choice after rescue preparation."""

    visible = [dict(action) for action in actions]
    if not flags.get("rescue_equipment_prepared", False):
        return visible
    if flags.get("academy_assisted_medication_done", False):
        return visible

    virtual_action = assisted_medication_action()
    insert_at = len(visible)
    for index, action in enumerate(visible):
        if action.get("id") in {"student_independent_epinephrine", "watch_only"}:
            insert_at = index
            break
    visible.insert(insert_at, virtual_action)
    return visible


def is_assisted_medication_action(action_id: object) -> bool:
    return str(action_id or "") == ACADEMY_ASSISTED_MEDICATION_ACTION_ID


def apply_academy_action(simulator: Any, action_id: str) -> Dict[str, Any]:
    """Apply an academy UI action while preserving the scenario contract."""

    if not is_assisted_medication_action(action_id):
        simulator.apply_action(action_id)
        return {
            "executed": True,
            "presented_action_id": str(action_id),
            "core_action_id": str(action_id),
            "feedback": _latest_action_feedback(simulator),
        }

    flags = simulator.state.flags
    if not flags.get("rescue_equipment_prepared", False):
        return {
            "executed": False,
            "presented_action_id": ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
            "core_action_id": ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID,
            "feedback": "",
        }
    if flags.get("academy_assisted_medication_done", False):
        return {
            "executed": False,
            "presented_action_id": ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
            "core_action_id": ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID,
            "feedback": ACADEMY_ASSISTED_MEDICATION_RESULT,
        }

    simulator.apply_action(ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID)
    flags["academy_assisted_medication_done"] = True
    flags["drug_check_cooperation"] = True

    for entry in reversed(simulator.log):
        if (
            entry.kind == "action"
            and entry.message == ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID
        ):
            data = dict(entry.data or {})
            data.update(
                {
                    "label": ACADEMY_ASSISTED_MEDICATION_FULL_LABEL,
                    "status": "role_appropriate_medication_cooperation",
                    "result": ACADEMY_ASSISTED_MEDICATION_RESULT,
                    "presentation_action_id": ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
                }
            )
            entry.data = data
            break

    return {
        "executed": True,
        "presented_action_id": ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
        "core_action_id": ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID,
        "feedback": ACADEMY_ASSISTED_MEDICATION_RESULT,
    }


def _latest_action_feedback(simulator: Any) -> str:
    for entry in reversed(simulator.log):
        if entry.kind == "action":
            return str((entry.data or {}).get("result", "") or "")
    return ""
