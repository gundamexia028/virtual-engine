from __future__ import annotations

from typing import Any, Dict

from academy_interactions import (
    ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
    ACADEMY_ASSISTED_MEDICATION_SHORT_LABEL,
)
from peds_anaphylaxis_sim.time_format import (
    format_elapsed_time,
    format_timeline_value,
    timeline_unit,
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


# Presentation-only labels; raw report keys and numerical values remain unchanged.
TIMELINE_LABELS_CN = {
    "stop_infusion": "停用可疑药物", "call_help": "呼救", "abc_assess": "ABC评估",
    "oxygen": "开放气道给氧", "position": "体位管理", "monitor": "连接监护",
    "bp_check": "测量血压", "epi_im": "肌注肾上腺素", "fluid": "快速补液",
    "epi_last_dose_mg": "最近一次肾上腺素剂量", "epi_target_dose_mg": "肾上腺素目标剂量",
    "epi_dose_high_event": "肾上腺素剂量偏高事件", "serious_medication_error": "严重用药错误",
    "fluid_bolus_volume_ml": "快速补液容量", "fluid_min_ml": "补液容量下限",
    "fluid_max_ml": "补液容量上限", "fluid_bolus_valid": "快速补液有效",
    "first_reassessment": "第一次复评", "second_reassessment": "第二次复评",
    "reassess_count": "复评次数", "bronchodilator": "雾化支气管扩张剂",
    "steroid": "糖皮质激素", "steroid_dose_mg": "糖皮质激素剂量",
    "steroid_min_mg": "糖皮质激素剂量下限", "steroid_max_mg": "糖皮质激素剂量上限",
    "steroid_valid": "糖皮质激素使用有效", "nebulized_epinephrine": "雾化肾上腺素",
    "repeat_epinephrine": "再次肌注肾上腺素", "advanced_support": "联系高级支持",
    "advanced_support_indicated_time_sec": "首次出现高级支持指征",
    "advanced_support_indicated_reason": "首次高级支持指征原因",
    "advanced_support_current_reason": "当前高级支持指征原因",
    "bvm_ventilation": "球囊通气", "cpr": "心肺复苏",
    "allergy_identification": "识别疑似药物过敏反应", "prepare_rescue_equipment": "准备抢救物品",
    "academy_reassess": "基础复评", "academy_family_communication": "基础家属沟通",
    "academy_sbar_handoff": "简化SBAR汇报", "ask_family_first": "先询问相关病史",
    "send_family_for_help": "请家属寻找支援", "prepare_steroid_antihistamine_only": "优先准备辅助药物",
    "student_independent_epinephrine": "独立完成急救注射", "watch_only": "等待老师处理",
    "cardiac_arrest_time_sec": "心搏骤停时间", "resuscitation_rosc_time_sec": "自主循环恢复时间",
    "epinephrine_delay_after_core_steps": "核心步骤后肾上腺素延迟",
    "airway_obstruction_triggered": "已出现气道梗阻", "bvm_required": "需要球囊通气",
    "family_communication": "家属沟通", "sbar_handoff": "SBAR交接",
    "im_epinephrine_dose_verified_time": "肌注肾上腺素剂量确认时间",
    "fluid_bolus_volume_verified_time": "快速补液容量确认时间", "establish_iv": "建立静脉通路",
}

EVENT_VALUE_LABELS_CN = {
    "full": "全分", "delayed": "延迟计分", "no_score": "不计分",
    "drug_selection": "药物选择", "route_correct": "给药途径正确", "timing": "给药时机",
    "dose_correct": "剂量正确", "dose_accuracy": "剂量准确性",
    "cardiac_arrest": "心搏骤停", "post_arrest_transfer_picu": "心搏骤停复苏后转入PICU",
    "bvm_required_or_ventilation_failure": "需要球囊通气或通气衰竭",
    "airway_obstruction": "气道梗阻", "current_severe_hypoxemia": "当前严重低氧血症",
    "current_hypotension_below_age_threshold": "当前血压低于年龄对应阈值",
    "current_significant_stridor": "当前明显喉鸣", "current_altered_consciousness": "当前意识改变",
    "unresolved_after_repeat_epinephrine": "再次使用肾上腺素后仍未缓解",
    "bvm_ventilation_done_for_critical_branch": "危重分支已完成球囊通气",
}


def timeline_display_rows(timeline: Dict[str, Any]) -> list[Dict[str, str]]:
    rows = []
    for key, value in timeline.items():
        display = ("是" if value else "否") if isinstance(value, bool) else format_timeline_value(key, value)
        display = EVENT_VALUE_LABELS_CN.get(display, display)
        rows.append({"指标": TIMELINE_LABELS_CN.get(key, key), "数值": display,
                     "单位": timeline_unit(key, value)})
    return rows


def score_feedback_label(value: object) -> str:
    text = str(value or "")
    prefix = "肾上腺素分项评分："
    if text.startswith(prefix):
        component, separator, detail = text[len(prefix):].partition("；")
        return prefix + EVENT_VALUE_LABELS_CN.get(component, component) + separator + detail
    return EVENT_VALUE_LABELS_CN.get(text, text)
