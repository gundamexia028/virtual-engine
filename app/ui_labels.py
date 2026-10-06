from __future__ import annotations

from typing import Any, Dict

from academy_interactions import (
    ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
    ACADEMY_ASSISTED_MEDICATION_SHORT_LABEL,
)
from peds_anaphylaxis_sim.time_format import (
    format_elapsed_time,
    format_timeline_value,
)


ACADEMY_ACTION_SHORT_LABELS = {
    "allergy_identification": "识别严重过敏反应",
    "stop_infusion": "暂停可疑输入并保留通道",
    "call_help": "立即呼叫支援",
    "high_flow_oxygen": "体位管理与基础给氧",
    "connect_monitor": "连接监护并观察",
    "check_bp": "测量血压与循环评估",
    "prepare_rescue_equipment": "准备抢救物品（未核对/给药）",
    "academy_medication_check": "老师指导下完成用药核对",
    "academy_restore_iv": "老师指导下配合重建通路",
    ACADEMY_ASSISTED_MEDICATION_ACTION_ID: ACADEMY_ASSISTED_MEDICATION_SHORT_LABEL,
    "academy_reassess": "复测并综合复评",
    "academy_family_communication": "复评后向家属总结告知",
    "academy_sbar_handoff": "完成阶段结束SBAR交接",
    "continue_infusion": "继续观察",
    "remove_iv": "直接拔除静脉通路",
    "ask_family_first": "先询问相关病史",
    "send_family_for_help": "请家属寻找支援",
    "prepare_steroid_antihistamine_only": "优先准备辅助药物",
    "student_independent_epinephrine": "独立完成急救注射",
    "watch_only": "等待老师处理",
}


def academy_action_short_label(action: Dict[str, Any]) -> str:
    action_id = str(action.get("id", "") or "")
    return ACADEMY_ACTION_SHORT_LABELS.get(
        action_id,
        str(action.get("label", action_id)),
    )


def format_time_progress(seconds: Any) -> str:
    return f"时间推进 {format_elapsed_time(seconds)}"


def academy_scenario_display_name(name: object) -> str:
    value = str(name or "").strip()
    if value == "严重过敏反应/过敏性休克抢救":
        return "药物诱发严重过敏反应（过敏性休克）抢救"
    return value
