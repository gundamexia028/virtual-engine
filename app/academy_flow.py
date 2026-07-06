from __future__ import annotations

from typing import Any, Dict, Optional


ACADEMY_PHASES = ("课前测评", "模拟训练", "课后考核")
ACADEMY_COMPLETION_PAGES = {
    "课前测评": "pretest_complete",
    "模拟训练": "training_complete",
    "课后考核": "posttest_result",
}
ACADEMY_TRAINING_CORE_COMPLETION_REASONS = {
    "success",
    "standard_assessment_completed",
}


def next_academy_phase(phase: str) -> Optional[str]:
    try:
        index = ACADEMY_PHASES.index(str(phase))
    except ValueError:
        return None
    return ACADEMY_PHASES[index + 1] if index + 1 < len(ACADEMY_PHASES) else None


def completion_page_for_phase(phase: str) -> str:
    return ACADEMY_COMPLETION_PAGES.get(str(phase), "")


def stage_report_key(phase: str) -> str:
    return {
        "课前测评": "pretest",
        "模拟训练": "training",
        "课后考核": "posttest",
    }.get(str(phase), "")


def should_auto_finalize_academy_phase(
    phase: str,
    simulator_mode: str,
    end_reason: str,
) -> bool:
    """Keep successful academy training on the simulation page for confirmation."""
    is_training_success = (
        str(phase) == "模拟训练"
        and str(simulator_mode) == "coach"
        and str(end_reason) in ACADEMY_TRAINING_CORE_COMPLETION_REASONS
    )
    return not is_training_success


def academy_training_ready_for_manual_completion(
    phase: str,
    simulator_mode: str,
    done: bool,
    end_reason: str,
) -> bool:
    return bool(
        done
        and str(phase) == "模拟训练"
        and str(simulator_mode) == "coach"
        and str(end_reason) in ACADEMY_TRAINING_CORE_COMPLETION_REASONS
    )


def academy_completion_page_title(page: str) -> str:
    return {
        "pretest_complete": "课前测评完成",
        "training_complete": "模拟训练完成",
        "posttest_result": "课后考核结果与三阶段对比",
    }.get(str(page), "")


def training_completion_status_text(report: Dict[str, Any]) -> str:
    flags = report.get("clinical_pathway_flags", {}) or {}
    timeline = report.get("key_timeline", {}) or {}
    parts = []

    def is_displayable(value: Any) -> bool:
        if value in (None, "", [], {}):
            return False
        return str(value).strip().lower() not in {"none", "null", "[]", "{}"}

    completion_rate = flags.get("completion_rate_at_manual_finish")
    if is_displayable(completion_rate):
        rate_text = str(completion_rate)
        if not rate_text.endswith("%"):
            rate_text = f"{rate_text}%"
        parts.append(f"核心步骤完成率：{rate_text}")

    reassess_count = timeline.get("reassess_count")
    if is_displayable(reassess_count):
        parts.append(f"有效复评次数：{reassess_count}次")

    if not parts:
        return "本阶段训练结果已保存。"
    return "；".join(parts) + "。"


def questionnaire_submit_button_label(status: str) -> str:
    return "重新提交评价" if str(status) == "failed" else "提交评价"


def academy_sidebar_status(
    flow_page: str,
    phase_label: str,
    mode_label: str,
) -> tuple[str, str]:
    if str(flow_page) == "flow_complete":
        return "全流程完成", "已完成"
    return str(phase_label), str(mode_label)


def academy_flow_page_allowed(
    page: str,
    stage_reports: Dict[str, Any],
    *,
    questionnaire_completed: bool = False,
) -> bool:
    reports = stage_reports if isinstance(stage_reports, dict) else {}
    completed = {
        key
        for key in ("pretest", "training", "posttest")
        if isinstance(reports.get(key), dict)
    }
    required = {
        "pretest_complete": {"pretest"},
        "training_complete": {"pretest", "training"},
        "posttest_result": {"pretest", "training", "posttest"},
        "questionnaire": {"pretest", "training", "posttest"},
        "flow_complete": {"pretest", "training", "posttest"},
    }.get(str(page))
    if required is None or not required.issubset(completed):
        return False
    if page == "flow_complete":
        return bool(questionnaire_completed)
    return True


def latest_allowed_academy_page(
    stage_reports: Dict[str, Any],
    *,
    questionnaire_completed: bool = False,
) -> str:
    if questionnaire_completed and academy_flow_page_allowed(
        "flow_complete",
        stage_reports,
        questionnaire_completed=True,
    ):
        return "flow_complete"
    for page in ("posttest_result", "training_complete", "pretest_complete"):
        if academy_flow_page_allowed(page, stage_reports):
            return page
    return ""


def score_snapshot(report: Dict[str, Any]) -> Dict[str, Any]:
    score = report.get("score", 0)
    penalty = report.get("penalties", 0)
    try:
        raw_score = float(score or 0) + abs(float(penalty or 0))
        if raw_score.is_integer():
            raw_score = int(raw_score)
    except (TypeError, ValueError):
        raw_score = score
    return {
        "score": score,
        "raw_score": raw_score,
        "penalties": penalty,
        "max_score": report.get("max_score", ""),
        "modules": report.get("module_score_summary", {}) or {},
        "issues": report.get("process_safety_issues", []) or [],
        "missing": report.get("critical_missing", []) or [],
    }
