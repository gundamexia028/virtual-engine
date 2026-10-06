from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, Iterable, List

ACADEMY_ASSISTED_MEDICATION_ACTION_ID = "academy_assisted_medication"
ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID = ACADEMY_ASSISTED_MEDICATION_ACTION_ID
ACADEMY_ASSISTED_MEDICATION_SHORT_LABEL = "配合完成给药"
ACADEMY_ASSISTED_MEDICATION_FULL_LABEL = "核对无误后，在老师/医生指导下配合完成肾上腺素肌内给药，并确认实际给药完成"
ACADEMY_ASSISTED_MEDICATION_RESULT = "已在老师/医生指导下配合完成实际给药；与准备、核对分别记录。"

def assisted_medication_action() -> Dict[str, Any]:
    return {"id": ACADEMY_ASSISTED_MEDICATION_ACTION_ID, "label": ACADEMY_ASSISTED_MEDICATION_FULL_LABEL,
            "presentation_only": False, "core_action_id": ACADEMY_ASSISTED_MEDICATION_CORE_ACTION_ID}

def add_assisted_medication_choice(actions: Iterable[Dict[str, Any]], flags: Dict[str, Any]) -> List[Dict[str, Any]]:
    # The action already belongs to the registered scenario. Never inject a duplicate.
    return deepcopy(list(actions))

def is_assisted_medication_action(action_id: object) -> bool:
    return str(action_id or "") == ACADEMY_ASSISTED_MEDICATION_ACTION_ID

def apply_academy_action(simulator: Any, action_id: str) -> Dict[str, Any]:
    before = len(simulator.log)
    simulator.apply_action(action_id)
    latest = next((e for e in reversed(simulator.log[before:]) if e.kind == "action"), None)
    status = (latest.data or {}).get("status", "") if latest else "terminal"
    if latest and latest.message == "unknown_action":
        status = "unknown_action"
    return {"executed": latest is not None and status not in {"already_completed", "terminal", "unknown_action"},
            "valid_completion": status == "valid" or action_id in simulator.action_valid_time,
            "presented_action_id": str(action_id), "core_action_id": str(action_id),
            "feedback": str((latest.data or {}).get("result", "")) if latest else "本轮已结束。"}
