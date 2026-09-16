# -*- coding: utf-8 -*-
"""
护理动态分支虚拟仿真训练平台｜V1.3.8 academy teacher trial UI display fixed

本版重点：
- 时间/分级/得分/复评移至左侧病例下方的运行信息区；
- 左侧病例与实时状态栏加宽，生命体征以卡片网格显示；
- 右侧操作按钮统一使用简洁短标题，不再显示冗余解释；
- 当生命体征、临床表现或分级发生变化时，相关卡片自动闪动提示；
- 训练模式保留步骤提示与原因说明；考试模式仅保留干净操作界面；
- 肌注肾上腺素需输入剂量，系统按体重核对 0.01 mg/kg 与 0.3 mg 上限。
- 每次开始/重置模拟时自动随机生成年龄，体重按年龄公式生成：1–6岁=年龄×2+8；7–11岁=年龄×3+2。
- 按模块边界校准评分与动态演化：普通路径总分100分。
- V1.0新增：访问码、单位/科室/参与者编号、自动保存结果、管理员导出CSV、操作历史即时显示。
- V1.1新增：接入Supabase云端数据库，训练结束后自动写入training_records表，管理员后台可从数据库读取并导出。
- V1.1.1新增：管理员后台增强导出：汇总CSV、操作明细CSV、完整JSONL；关键操作时间点和剂量/错误指标展开为独立字段。
- V1.1.2新增：多中心/多层级课题字段，登录登记界面居中加宽，版本说明收纳到右上角。
- V1.1.3新增：登记界面按院区/科室标准化下拉录入，按院区代码+科室代码+姓名首字母自动生成参与者编号；删除前台项目编号和第几次测试字段；评估阶段标准化为基线评估、模拟培训、培训后考核。
- V1.1.4新增：按评估阶段自动锁定流程；基线评估=考试模式+初始病例，模拟培训=训练模式+初始病例，培训后考核=考试模式+变体病例Variant A；受试者不再自行选择运行模式和病例脚本。
- V1.2.5新增：输液场景双复评逻辑、儿童肾上腺素0.3 mg上限、快速补液容量输入、再次肌注/高级支持/CPR/雾化肾上腺素条件性路径。
- V1.2.6新增：总分升至25分；删除抗组胺药按钮；糖皮质激素纳入5分并需输入剂量；未及时肌注肾上腺素改为第8关键节点后加速恶化；新增气道梗阻/球囊加压给氧条件性分支。
- V1.3.5新增：在V1.3.4推广版权限与学院流程基础上，增强学院病例脚本、护生身份边界、教学性错误分支、风险标签和100分分项评分；临床模式不改动。
- V1.3.6修复：学院课后考核完成门控。未完成完整课后考核流程时，不得跳转SUS/教学体验；学院情景早期低血压/低氧恶化不再直接终止阶段。

声明：
    本系统仅用于护理教学、培训与科研可行性验证，不用于临床诊疗决策。
"""

from __future__ import annotations

import csv
from contextlib import contextmanager
import hashlib
import hmac
import html
import io
import json
import os
import random
import re
import secrets as token_secrets
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Tuple

import streamlit as st

from academy_interactions import (
    ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
    add_assisted_medication_choice,
    apply_academy_action,
)
from academy_flow import (
    academy_completion_page_title,
    academy_flow_page_allowed,
    academy_sidebar_status,
    academy_training_ready_for_manual_completion,
    completion_page_for_phase,
    latest_allowed_academy_page,
    next_academy_phase,
    questionnaire_submit_button_label,
    score_snapshot,
    should_auto_finalize_academy_phase,
    stage_report_key,
    training_completion_status_text,
)
from runtime_config import (
    APP_MODE_COMPETITION,
    APP_MODE_PRODUCTION,
    RuntimeConfigurationError,
    competition_credentials,
    deployment_setting,
    resolve_app_mode,
)
from storage_adapters import StorageAdapter, build_storage_adapter
from ui_labels import (
    academy_action_short_label,
    academy_scenario_display_name,
    format_elapsed_time,
    format_timeline_value,
    format_time_progress,
)


def _deployment_setting(name: str, default: str = "") -> str:
    """Read deployment settings using secrets, then environment, then default."""
    try:
        secrets_source = st.secrets  # type: ignore[attr-defined]
    except Exception:
        secrets_source = None
    return deployment_setting(
        name,
        secrets=secrets_source,
        environ=os.environ,
        default=default,
    )


try:
    APP_MODE = resolve_app_mode(
        secrets=getattr(st, "secrets", None),
        environ=os.environ,
    )
    APP_MODE_CONFIGURATION_ERROR = ""
except RuntimeConfigurationError:
    APP_MODE = APP_MODE_PRODUCTION
    APP_MODE_CONFIGURATION_ERROR = "APP_MODE配置无效，只允许production或competition。"


def is_competition_mode() -> bool:
    return APP_MODE == APP_MODE_COMPETITION

from peds_anaphylaxis_sim import SYSTEM_VERSION
from peds_anaphylaxis_sim.engine import Simulator, save_report
from peds_anaphylaxis_sim import org_credentials
from peds_anaphylaxis_sim.flow_strategies import (
    FlowStrategyError,
    SimulationFlowStrategy,
    build_workflow_config,
    flow_strategy_for_modes,
    flow_strategy_for_phase,
    flow_strategy_for_scenario,
    phase_options as strategy_phase_options,
    system_mode_options,
)
from peds_anaphylaxis_sim.scenario_catalog import (
    SCENARIO_DIRECTORY,
    ScenarioCatalogError,
    find_scenario_definition_by_role,
    scenario_definition_for_path,
    scenario_definition_for_phase,
    scenario_definitions,
)
from peds_anaphylaxis_sim.scenario_loader import (
    load_registered_scenario,
    load_registered_scenario_path,
    load_scenario_file as load_scenario,
)


APP_TITLE = "护理动态分支虚拟仿真训练与评估平台"
APP_SUBTITLE = "Dynamic Branching Virtual Simulation Platform for Nursing Training and Education"
ROOT = Path(__file__).resolve().parent
SCENARIO_DIR = SCENARIO_DIRECTORY
RUNS_DIR = Path(os.environ.get("PEDSIM_RESULTS_DIR", str(ROOT / "runs_web")))
RESULTS_INDEX_PATH = RUNS_DIR / "training_results.jsonl"
RESULTS_FULL_REPORTS_PATH = RUNS_DIR / "training_full_reports.jsonl"
QUESTIONNAIRE_RESULTS_FILENAME = "questionnaire_results.jsonl"
DEMO_DATA_DIR = ROOT / "demo_data"
COMPETITION_RUNTIME_DIR = Path(
    _deployment_setting(
        "PEDSIM_COMPETITION_RESULTS_DIR",
        str(ROOT / "competition_runtime"),
    )
)
RESULTS_LOCK_FILENAME = ".results.lock"
RESULTS_WARNING_FILENAME = "storage_warnings.log"
CONFIG_DIR = ROOT / "config"
ORG_ACCESS_CODES_PATH = CONFIG_DIR / "org_access_codes.json"
DRAFTS_DIR = Path(
    _deployment_setting(
        "PEDSIM_DRAFTS_DIR",
        str(
            COMPETITION_RUNTIME_DIR / "training_drafts"
            if is_competition_mode()
            else ROOT / ".runtime" / "training_drafts"
        ),
    )
)
DRAFT_QUERY_KEY = "resume"
DRAFT_TTL_SECONDS = 12 * 60 * 60
DRAFT_MAX_BYTES = 5 * 1024 * 1024
APP_VERSION = SYSTEM_VERSION
# Review hotfix: display-only bedside monitor refresh; does not advance Simulator state.
CLINICAL_REVIEW_LIVE_VITALS_REFRESH_SECONDS = 2.0
AUTH_CONTEXT_ERROR_MESSAGE = "当前管理权限无效或已失效，请重新登录。"
PLATFORM_ADMIN_ROLE = "platform_admin"
UNIT_ADMIN_ROLES = {"clinical_admin", "academy_admin"}
COMPETITION_ADMIN_ROLE = "competition_admin"


def current_storage_adapter() -> StorageAdapter:
    return build_storage_adapter(
        APP_MODE,
        production_directory=Path(RESULTS_INDEX_PATH).parent,
        demo_directory=DEMO_DATA_DIR,
        competition_runtime_directory=COMPETITION_RUNTIME_DIR,
    )

DEFAULT_INSTITUTION = (
    "示范教学单位"
    if is_competition_mode()
    else _deployment_setting(
        "PEDSIM_DEFAULT_INSTITUTION",
        "四川大学华西第二医院",
    )
)

CAMPUS_CODES = (
    {
        "教学区域A": "JXA",
        "教学区域B": "JXB",
        "教学区域C": "JXC",
    }
    if is_competition_mode()
    else {
        "锦江院区": "JJYQ",
        "眉山院区": "MSYQ",
        "高新院区": "GXYQ",
    }
)

DEPARTMENT_CODES = {
    "呼吸科": "HXK",
    "感染科": "GRK",
    "肾脏科": "SZK",
    "血液科": "XYK",
    "心血管科": "XXGK",
    "神经科": "SJK",
    "PICU": "PICU",
    "消化科": "XHK",
}

SYSTEM_MODE_OPTIONS = system_mode_options()
CLINICAL_ASSESSMENT_PHASE_OPTIONS = list(strategy_phase_options("clinical"))
ACADEMY_ASSESSMENT_PHASE_OPTIONS = list(strategy_phase_options("academy"))
ALL_ASSESSMENT_PHASE_OPTIONS = CLINICAL_ASSESSMENT_PHASE_OPTIONS + ACADEMY_ASSESSMENT_PHASE_OPTIONS
# Backward-compatible alias used by older clinical UI/export code.
ASSESSMENT_PHASE_OPTIONS = CLINICAL_ASSESSMENT_PHASE_OPTIONS

COLLECTION_MODE_OPTIONS = ["测试演练"] if is_competition_mode() else ["正式采集", "测试演练"]
COLLECTION_MODE_CODES = {
    "正式采集": "formal",
    "测试演练": "pilot",
}

ACADEMY_GRADE_OPTIONS = ["", "一年级", "二年级", "三年级", "四年级", "实习结束/毕业前"]

SUS_ITEMS = [
    "我愿意经常使用这个系统进行学习或训练。",
    "我觉得这个系统过于复杂。",
    "我认为这个系统容易使用。",
    "我认为需要技术人员帮助才能使用这个系统。",
    "我觉得系统中的各项功能整合良好。",
    "我觉得这个系统前后不一致。",
    "我认为大多数护生可以很快学会使用这个系统。",
    "我觉得这个系统使用起来很繁琐。",
    "我在使用这个系统时感到有信心。",
    "我需要先学习很多额外知识才能使用这个系统。",
]

TEACHING_EXPERIENCE_ITEMS = [
    "该系统提高了我学习急救护理知识的兴趣。",
    "情景设置让我感到接近真实临床场景。",
    "该系统有助于我理解严重过敏反应/过敏性休克的表现。",
    "该系统有助于我掌握停止可疑输入、呼救、给氧、监测等初步处置流程。",
    "该系统有助于我理解护生在抢救中的配合角色。",
    "该系统有助于我学习如何向老师或医生汇报。",
    "该系统提高了我面对类似情景时的信心。",
    "我愿意推荐该系统用于护理实训教学。",
]

ACADEMY_SCENARIO_LIBRARY = {
    "academy_anaphylaxis_rescue": {
        "id": "academy_anaphylaxis_rescue",
        "name": "严重过敏反应/过敏性休克抢救",
        "category": "急救护理",
        "course_type": "基础护理/急救护理/儿科护理",
        "difficulty": "基础版",
        "status": "已开放",
        "description": "面向在校护生，训练严重过敏反应早期识别、暂停可疑输入、保留静脉通道、及时呼救、基础氧疗与循环监测、抢救用物准备、药物核对配合、基础复评、家属安抚与SBAR汇报。",
        "target_users": "在校护生",
    }
}
ACADEMY_SCENARIO_DEFAULT_ID = "academy_anaphylaxis_rescue"


def current_system_mode() -> str:
    mode = str(st.session_state.get("system_mode", "clinical") or "clinical")
    return mode if mode in SYSTEM_MODE_OPTIONS else "clinical"


def current_system_mode_label() -> str:
    return SYSTEM_MODE_OPTIONS[current_system_mode()]["label"]


def current_academy_scenario_id() -> str:
    scenario_id = str(st.session_state.get("academy_scenario_id", "") or ACADEMY_SCENARIO_DEFAULT_ID)
    return scenario_id if scenario_id in ACADEMY_SCENARIO_LIBRARY else ACADEMY_SCENARIO_DEFAULT_ID


def current_academy_scenario() -> Dict[str, Any]:
    return ACADEMY_SCENARIO_LIBRARY[current_academy_scenario_id()]


def academy_scenario_options() -> List[str]:
    return list(ACADEMY_SCENARIO_LIBRARY.keys())


def academy_scenario_label(scenario_id: str) -> str:
    item = ACADEMY_SCENARIO_LIBRARY.get(scenario_id, {})
    status = item.get("status", "")
    suffix = f"（{status}）" if status else ""
    return f"{item.get('name', scenario_id)}{suffix}"


def phase_options_for_mode(system_mode: Optional[str] = None) -> List[str]:
    mode = system_mode or current_system_mode()
    try:
        return list(strategy_phase_options(mode))
    except FlowStrategyError:
        return list(CLINICAL_ASSESSMENT_PHASE_OPTIONS)


def default_phase_for_mode(system_mode: Optional[str] = None) -> str:
    return phase_options_for_mode(system_mode)[0]


def workflow_for_phase(phase: str, system_mode: Optional[str] = None) -> Dict[str, str]:
    mode = system_mode or current_system_mode()
    scenario = current_academy_scenario() if mode == "academy" else None
    return build_workflow_config(
        mode,
        phase,
        library_id=current_academy_scenario_id() if mode == "academy" else "",
        scenario_metadata=scenario,
    )


def current_flow_strategy(
    sim: Optional[Simulator] = None,
) -> SimulationFlowStrategy:
    if sim is None:
        active = st.session_state.get("active_simulator")
        if isinstance(active, Simulator):
            sim = active
    if isinstance(sim, Simulator):
        strategy = getattr(sim, "flow_strategy", None)
        if isinstance(strategy, SimulationFlowStrategy):
            return strategy
        return flow_strategy_for_scenario(sim.scenario, sim.mode)
    return flow_strategy_for_phase(
        current_system_mode(),
        st.session_state.get(
            "assessment_phase",
            default_phase_for_mode(current_system_mode()),
        ),
    )


def normalize_initials(text: str) -> str:
    """Keep only uppercase Latin letters/numbers from user-entered name initials."""
    cleaned = "".join(ch for ch in str(text or "").upper().replace(" ", "") if ch.isalnum())
    return cleaned[:8]


def ensure_participant_suffix() -> str:
    """Create a stable anti-duplication suffix for the current browser session."""
    suffix = str(st.session_state.get("participant_unique_suffix", "") or "").strip()
    if not suffix:
        suffix = uuid.uuid4().hex[:4].upper()
        st.session_state.participant_unique_suffix = suffix
    return suffix


def build_participant_id(campus: str, department: str, initials: str) -> str:
    campus_code = CAMPUS_CODES.get(campus, "")
    department_code = DEPARTMENT_CODES.get(department, "")
    initials_code = normalize_initials(initials)
    if not campus_code or not department_code or not initials_code:
        return ""
    return f"{campus_code}{department_code}{initials_code}-{ensure_participant_suffix()}"

STUDENT_LEVEL_CODES = {
    "高职/大专": "GZ",
    "本科": "BK",
    "专升本": "ZSB",
    "硕士及以上": "YJS",
    "其他": "QT",
}


def build_academy_participant_id(student_level: str, initials: str) -> str:
    level_code = STUDENT_LEVEL_CODES.get(student_level, "")
    initials_code = normalize_initials(initials)
    if not level_code or not initials_code:
        return ""
    return f"ACAD{level_code}{initials_code}-{ensure_participant_suffix()}"


def participant_code_parts(campus: str, department: str, initials: str) -> Dict[str, str]:
    return {
        "campus_code": CAMPUS_CODES.get(campus, ""),
        "department_code": DEPARTMENT_CODES.get(department, ""),
        "participant_initials": normalize_initials(initials),
    }



def list_scenarios() -> Dict[str, Path]:
    """Only expose the two bedside scripts requested for the web prototype."""
    items = []
    for definition in scenario_definitions():
        try:
            data = load_registered_scenario(definition.scenario_id)
            meta = data.get("scenario", {})
            display_name = (
                meta.get("display_name")
                or meta.get("title", definition.path.stem)
            )
            version = meta.get("version", "")
            label = f"{display_name}｜{version}" if version else str(display_name)
            items.append((definition.order, label, definition.path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return {label: path for _, label, path in sorted(items, key=lambda x: x[0])}


def scenario_path_by_role(role: str) -> Optional[Path]:
    """Return the scenario path matching the locked workflow script role."""
    definition = find_scenario_definition_by_role(role)
    return definition.path if definition is not None else None


def scenario_path_for_phase(
    system_mode: str,
    phase: str,
    academy_scenario_id: str = "",
) -> Optional[Path]:
    library_id = academy_scenario_id if system_mode == "academy" else ""
    try:
        return scenario_definition_for_phase(
            system_mode,
            phase,
            library_id,
        ).path
    except ScenarioCatalogError:
        return None


def safe_filename_part(text: str) -> str:
    cleaned = str(text or "").strip()
    for ch in '\\/:*?"<>|':
        cleaned = cleaned.replace(ch, "_")
    cleaned = cleaned.replace(" ", "_")
    return cleaned or "unknown"


def randomize_patient_profile(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Create a per-run patient profile without modifying the source JSON file.

    Clinical scripts keep the V1.3.4 age/weight randomization. Academy scripts
    may declare ``patient.fixed_profile=True`` so the pre-test and post-test
    teaching variants remain stable for content-validity review.
    """
    randomized = json.loads(json.dumps(scenario, ensure_ascii=False))
    patient = randomized.setdefault("patient", {})
    meta = randomized.get("scenario", {}) or {}
    if patient.get("fixed_profile") or meta.get("target_group") == "nursing_student":
        patient["randomized_profile"] = False
        patient["randomization_rule"] = "fixed academy teaching case profile"
        randomized.setdefault("baseline", {}).setdefault("vitals", {})["Temp"] = 36.8
        return randomized
    rng = random.SystemRandom()
    age = rng.randint(1, 11)
    weight = age * 2 + 8 if 1 <= age <= 6 else age * 3 + 2
    patient["age_years"] = age
    patient["weight_kg"] = weight
    patient["randomized_profile"] = True
    patient["randomization_rule"] = "age_years: 1-11; weight_kg formula: 1-6y=age*2+8, 7-11y=age*3+2"
    patient["weight_formula"] = "1-6岁: 年龄×2+8 kg; 7-11岁: 年龄×3+2 kg"
    randomized.setdefault("baseline", {}).setdefault("vitals", {})["Temp"] = 36.8
    return randomized


def state_key() -> str:
    return "active_simulator"


def init_session() -> None:
    defaults = {
        "system_mode": "clinical",
        "system_mode_selected": False,
        "participant_type": "clinical_nurse",
        "academy_scenario_selected": False,
        "academy_scenario_id": ACADEMY_SCENARIO_DEFAULT_ID,
        "academy_scenario_name": ACADEMY_SCENARIO_LIBRARY[ACADEMY_SCENARIO_DEFAULT_ID]["name"],
        "academy_scenario_category": ACADEMY_SCENARIO_LIBRARY[ACADEMY_SCENARIO_DEFAULT_ID]["category"],
        "academy_course_type": ACADEMY_SCENARIO_LIBRARY[ACADEMY_SCENARIO_DEFAULT_ID]["course_type"],
        "academy_difficulty": ACADEMY_SCENARIO_LIBRARY[ACADEMY_SCENARIO_DEFAULT_ID]["difficulty"],
        "school_name": "",
        "organization_id": "",
        "organization_type": "clinical",
        "student_level": "",
        "student_grade": "",
        "student_class": "",
        "participant_id": "",
        "participant_initials": "",
        "participant_unique_suffix": "",
        "campus_code": "",
        "department_code": "",
        "institution": DEFAULT_INSTITUTION,
        "campus": "",
        "department": "",
        "department_type": "",
        "nurse_level": "",
        "years_experience": 0.0,
        "years_experience_confirmed": False,
        "professional_title": "",
        "education_level": "",
        "collection_mode": "正式采集",
        "collection_note": "",
        "prior_anaphylaxis_training": "",
        "prior_simulation_experience": "",
        "real_case_experience": "",
        "prior_experience_survey_completed": False,
        "prior_experience_survey_time": "",
        "baseline_performance_completed": False,
        "baseline_stage_completed": False,
        "pending_prior_experience_survey": False,
        "pending_completion_reason": "",
        "pending_report": None,
        "training_batch": "",
        "assessment_phase": "基线评估",
        "workflow_mode": "exam",
        "flow_strategy_id": "clinical_exam",
        "workflow_script_role": "initial",
        "workflow_display": "基线评估｜考试模式｜初始病例",
        "workflow_locked": True,
        "attempt_no": 1,
        "profile_completed": False,
        "app_unlocked": False,
        "competition_review_unlocked": False,
        "competition_admin_unlocked": False,
        "admin_unlocked": False,
        "admin_scope": None,
        "admin_scope_type": "",
        "pending_academy_post_evaluation": False,
        "pending_post_evaluation_report": None,
        "pending_post_evaluation_reason": "",
        "completion_id": "",
        "questionnaire_submission_id": "",
        "questionnaire_draft": {},
        "questionnaire_submit_status": "",
        "questionnaire_submit_error": "",
        "academy_post_evaluation_completed": False,
        "academy_post_evaluation_time": "",
        "sus_score": "",
        "sus_level": "",
        "teaching_experience_total": "",
        "teaching_experience_mean": "",
        "page": "训练系统",
        "mode": "coach",
        "scenario_label": "",
        "seed": -1,
        "active_simulator": None,
        "active_scenario": None,
        "active_scenario_path": "",
        "active_script_name": "",
        "session_id": "",
        "ended": False,
        "end_reason": "",
        "last_report": None,
        "last_report_paths": None,
        "show_raw_log": False,
        "last_ui_snapshot": None,
        "pending_dose_action_id": "",
        "pending_dose_action_label": "",
        "pending_volume_action_id": "",
        "pending_volume_action_label": "",
        "pending_steroid_action_id": "",
        "pending_steroid_action_label": "",
        "last_dose_feedback": "",
        "last_dose_feedback_level": "",
        "result_saved": False,
        "admin_export_view": "训练汇总",
        "last_completion_notice": "",
        "academy_flow_page": "",
        "academy_stage_reports": {},
        "manual_completion_confirmation": False,
        "restart_stage_confirmation": False,
        "processed_ui_events": [],
        "academy_stage_session_ids": {},
        "academy_transition_locks": {},
        "abandoned_stage_sessions": [],
        "draft_id": "",
        "draft_created_at": 0.0,
        "draft_restore_checked": False,
        "draft_restored_notice": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not st.session_state.get("institution"):
        st.session_state.institution = DEFAULT_INSTITUTION
    ensure_participant_suffix()


DRAFT_SESSION_KEYS = (
    "system_mode",
    "system_mode_selected",
    "participant_type",
    "academy_scenario_selected",
    "academy_scenario_id",
    "academy_scenario_name",
    "academy_scenario_category",
    "academy_course_type",
    "academy_difficulty",
    "school_name",
    "organization_id",
    "organization_type",
    "student_level",
    "student_grade",
    "student_class",
    "participant_id",
    "participant_initials",
    "participant_unique_suffix",
    "campus_code",
    "department_code",
    "institution",
    "campus",
    "department",
    "department_type",
    "nurse_level",
    "years_experience",
    "years_experience_confirmed",
    "professional_title",
    "education_level",
    "collection_mode",
    "collection_note",
    "prior_anaphylaxis_training",
    "prior_simulation_experience",
    "real_case_experience",
    "prior_experience_survey_completed",
    "prior_experience_survey_time",
    "baseline_performance_completed",
    "baseline_stage_completed",
    "pending_prior_experience_survey",
    "pending_completion_reason",
    "pending_report",
    "training_batch",
    "assessment_phase",
    "workflow_mode",
    "flow_strategy_id",
    "workflow_script_role",
    "workflow_display",
    "workflow_locked",
    "attempt_no",
    "profile_completed",
    "page",
    "mode",
    "scenario_label",
    "seed",
    "active_scenario_path",
    "active_script_name",
    "session_id",
    "ended",
    "end_reason",
    "last_report",
    "show_raw_log",
    "last_ui_snapshot",
    "pending_dose_action_id",
    "pending_dose_action_label",
    "pending_volume_action_id",
    "pending_volume_action_label",
    "pending_steroid_action_id",
    "pending_steroid_action_label",
    "last_dose_feedback",
    "last_dose_feedback_level",
    "result_saved",
    "pending_academy_post_evaluation",
    "pending_post_evaluation_report",
    "pending_post_evaluation_reason",
    "completion_id",
    "questionnaire_submission_id",
    "questionnaire_draft",
    "questionnaire_submit_status",
    "questionnaire_submit_error",
    "academy_post_evaluation_completed",
    "academy_post_evaluation_time",
    "sus_score",
    "sus_level",
    "teaching_experience_total",
    "teaching_experience_mean",
    "last_completion_notice",
    "academy_flow_page",
    "academy_stage_reports",
    "manual_completion_confirmation",
    "restart_stage_confirmation",
    "processed_ui_events",
    "academy_stage_session_ids",
    "academy_transition_locks",
    "abandoned_stage_sessions",
)


def claim_ui_event(
    event_type: str,
    subject: str = "",
    state_marker: object = None,
) -> bool:
    """Claim one UI event without blocking legitimate later medical repeats."""

    if state_marker is None:
        simulator = st.session_state.get("active_simulator")
        state_marker = getattr(getattr(simulator, "state", None), "t", "")
    key = "|".join(
        (
            str(st.session_state.get("participant_id", "") or ""),
            str(st.session_state.get("assessment_phase", "") or ""),
            str(st.session_state.get("session_id", "") or ""),
            str(event_type or ""),
            str(subject or ""),
            str(state_marker if state_marker is not None else ""),
        )
    )
    claimed = st.session_state.get("processed_ui_events", [])
    if not isinstance(claimed, list):
        claimed = []
    if key in claimed:
        return False
    claimed.append(key)
    st.session_state.processed_ui_events = claimed[-200:]
    return True


def _valid_draft_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _draft_path(draft_id: str) -> Path:
    if not _valid_draft_id(draft_id):
        raise ValueError("Invalid draft identifier.")
    return DRAFTS_DIR / f"{draft_id}.json"


def _canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _browser_binding_hash() -> str:
    try:
        headers = st.context.headers
    except Exception:
        headers = {}
    binding_parts = [
        str(headers.get("User-Agent", "") or ""),
        str(headers.get("Accept-Language", "") or ""),
        str(headers.get("Sec-Ch-Ua", "") or ""),
        str(headers.get("Sec-Ch-Ua-Mobile", "") or ""),
        str(headers.get("Sec-Ch-Ua-Platform", "") or ""),
    ]
    binding = "\n".join(binding_parts)
    if not any(binding_parts):
        return ""
    return hashlib.sha256(binding.encode("utf-8")).hexdigest()


def _query_draft_id() -> str:
    try:
        value = st.query_params.get(DRAFT_QUERY_KEY, "")
    except Exception:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")


def _set_query_draft_id(draft_id: str) -> None:
    try:
        st.query_params[DRAFT_QUERY_KEY] = draft_id
    except Exception:
        pass


def _clear_query_draft_id() -> None:
    try:
        if DRAFT_QUERY_KEY in st.query_params:
            del st.query_params[DRAFT_QUERY_KEY]
    except Exception:
        pass


def cleanup_expired_training_drafts(now: Optional[float] = None) -> int:
    current_time = float(time.time() if now is None else now)
    if not DRAFTS_DIR.exists():
        return 0
    removed = 0
    for path in DRAFTS_DIR.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith(".") and ".tmp-" in path.name:
            try:
                if current_time - path.stat().st_mtime > 3600:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
            continue
        if not re.fullmatch(r"[0-9a-f]{64}\.json", path.name):
            continue
        try:
            if path.stat().st_size > DRAFT_MAX_BYTES:
                path.unlink()
                removed += 1
                continue
            envelope = json.loads(path.read_text(encoding="utf-8"))
            payload = envelope.get("payload", {}) if isinstance(envelope, dict) else {}
            expires_at = float(payload.get("expires_at", 0))
            if expires_at <= current_time:
                path.unlink()
                removed += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def clear_training_draft(clear_query: bool = True) -> None:
    draft_id = str(st.session_state.get("draft_id", "") or _query_draft_id())
    if _valid_draft_id(draft_id):
        try:
            _draft_path(draft_id).unlink(missing_ok=True)
        except OSError:
            pass
    st.session_state.draft_id = ""
    st.session_state.draft_created_at = 0.0
    st.session_state.draft_restored_notice = ""
    if clear_query:
        _clear_query_draft_id()


def persist_active_training_draft(now: Optional[float] = None) -> bool:
    sim = st.session_state.get("active_simulator")
    if not isinstance(sim, Simulator) or not st.session_state.get("profile_completed", False):
        return False
    browser_binding = _browser_binding_hash()
    if not browser_binding:
        return False
    draft_id = str(st.session_state.get("draft_id", ""))
    if not _valid_draft_id(draft_id):
        draft_id = token_secrets.token_hex(32)
        st.session_state.draft_id = draft_id
    current_time = float(time.time() if now is None else now)
    created_at = float(st.session_state.get("draft_created_at", 0.0) or current_time)
    st.session_state.draft_created_at = created_at
    session_data = {
        key: st.session_state.get(key)
        for key in DRAFT_SESSION_KEYS
        if key in st.session_state
    }
    payload = {
        "schema_version": 1,
        "app_version": APP_VERSION,
        "created_at": created_at,
        "updated_at": current_time,
        "expires_at": current_time + DRAFT_TTL_SECONDS,
        "browser_binding": browser_binding,
        "session_state": session_data,
        "simulator": sim.to_snapshot(),
    }
    checksum = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    envelope = {"payload": payload, "checksum": checksum}
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _draft_path(draft_id)
    temporary = DRAFTS_DIR / f".{draft_id}.tmp-{token_secrets.token_hex(8)}"
    try:
        temporary.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except (OSError, TypeError, ValueError):
        return False
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    _set_query_draft_id(draft_id)
    return True


def restore_training_draft_from_query(now: Optional[float] = None) -> bool:
    if st.session_state.get("draft_restore_checked", False):
        return isinstance(st.session_state.get("active_simulator"), Simulator)
    st.session_state.draft_restore_checked = True
    current_time = float(time.time() if now is None else now)
    cleanup_expired_training_drafts(current_time)
    draft_id = _query_draft_id()
    if not _valid_draft_id(draft_id):
        _clear_query_draft_id()
        return False
    browser_binding = _browser_binding_hash()
    if not browser_binding:
        _clear_query_draft_id()
        return False
    path = _draft_path(draft_id)
    try:
        if not path.exists() or path.stat().st_size > DRAFT_MAX_BYTES:
            _clear_query_draft_id()
            return False
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict):
            raise ValueError("Invalid draft envelope.")
        payload = envelope.get("payload")
        checksum = envelope.get("checksum")
        if not isinstance(payload, dict) or not isinstance(checksum, str):
            raise ValueError("Invalid draft envelope.")
        expected = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        if not token_secrets.compare_digest(checksum, expected):
            raise ValueError("Draft checksum mismatch.")
        if payload.get("schema_version") != 1 or payload.get("app_version") != APP_VERSION:
            raise ValueError("Draft version mismatch.")
        if float(payload.get("expires_at", 0)) <= current_time:
            path.unlink(missing_ok=True)
            _clear_query_draft_id()
            return False
        if not token_secrets.compare_digest(str(payload.get("browser_binding", "")), browser_binding):
            _clear_query_draft_id()
            return False
        session_data = payload.get("session_state")
        if not isinstance(session_data, dict) or not session_data.get("session_id"):
            raise ValueError("Draft session state is incomplete.")
        unknown_keys = set(session_data) - set(DRAFT_SESSION_KEYS)
        if unknown_keys:
            raise ValueError("Draft contains unsupported session fields.")
        simulator = Simulator.from_snapshot(payload.get("simulator"))
        scenario_path = Path(
            str(session_data.get("active_scenario_path", ""))
        ).resolve()
        definition = scenario_definition_for_path(scenario_path)
        if definition is None or not scenario_path.is_file():
            raise ValueError("Draft scenario path is invalid.")
        registered_scenario = load_registered_scenario_path(scenario_path)
        if (
            simulator.scenario.get("scenario", {}).get("id")
            != registered_scenario.get("scenario", {}).get("id")
        ):
            raise ValueError("Draft scenario identity mismatch.")
        restored_strategy = current_flow_strategy(simulator)
        if not restored_strategy.recovery.restore_in_progress:
            raise ValueError("Draft recovery is disabled for this flow.")
        if (
            payload.get("schema_version")
            != restored_strategy.recovery.snapshot_schema_version
        ):
            raise ValueError("Draft recovery schema mismatch.")
        stored_strategy_id = str(
            session_data.get("flow_strategy_id", "") or ""
        )
        if (
            stored_strategy_id
            and stored_strategy_id != restored_strategy.strategy_id
        ):
            raise ValueError("Draft flow strategy identity mismatch.")
        session_data["flow_strategy_id"] = restored_strategy.strategy_id
        for key, value in session_data.items():
            st.session_state[key] = value
        st.session_state.active_simulator = simulator
        st.session_state.active_scenario = simulator.scenario
        st.session_state.app_unlocked = True
        st.session_state.admin_unlocked = False
        st.session_state.admin_scope = None
        st.session_state.admin_scope_type = ""
        st.session_state.page = "训练系统"
        st.session_state.draft_id = draft_id
        st.session_state.draft_created_at = float(payload.get("created_at", current_time))
        st.session_state.draft_restored_notice = "已安全恢复刷新前的训练进度。"
        return True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        _clear_query_draft_id()
        return False


def visible_vitals(sim: Simulator) -> Dict[str, str]:
    v = sim.state.vitals
    f = sim.state.flags
    out = {"体温": f"{v.get('Temp', 0):.1f} ℃"}

    if f.get("dead", False) or (f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False)):
        if f.get("monitor_on", False):
            out.update({
                "SpO₂": "无可靠波形/不可测",
                "HR": "无脉搏/不可测",
                "RR": "无有效自主呼吸",
            })
        else:
            out.update({"SpO₂": "未连接监护", "HR": "未连接监护", "RR": "无有效自主呼吸"})
        out["BP"] = "不可测" if f.get("bp_checked", False) else "未测量"
        return out

    if f.get("resuscitation_rosc", False):
        if f.get("monitor_on", False):
            out.update({
                "SpO₂": f"{v.get('SpO2', 0):.0f} %（波形恢复）",
                "HR": f"{v.get('HR', 0):.0f} /min（可触及脉搏）",
                "RR": "人工通气支持",
            })
        else:
            out.update({"SpO₂": "未连接监护", "HR": "未连接监护", "RR": "人工通气支持"})
        out["BP"] = f"{v.get('SBP', 0):.0f}/{v.get('DBP', 0):.0f} mmHg" if f.get("bp_checked", False) else "未测量"
        return out

    if f.get("monitor_on", False):
        out.update({
            "SpO₂": f"{v.get('SpO2', 0):.0f} %",
            "HR": f"{v.get('HR', 0):.0f} /min",
            "RR": f"{v.get('RR', 0):.0f} /min",
        })
    else:
        out.update({"SpO₂": "未连接监护", "HR": "未连接监护", "RR": "未连接监护"})
    if f.get("bp_checked", False):
        out["BP"] = f"{v.get('SBP', 0):.0f}/{v.get('DBP', 0):.0f} mmHg"
    else:
        out["BP"] = "未测量"
    return out



def _review_live_vital_pattern_value(bucket: int, metric: str) -> int:
    """Small deterministic bedside-monitor offset used only for UI display."""
    patterns = {
        "SpO2": (0, -1, 0, 1, 0, -1, 0, 1),
        "HR": (-1, 1, 0, 2, -2, 1, 0, -1),
        "RR": (0, 1, 0, -1, 1, 0, -1, 0),
        "SBP": (0, 1, -1, 2, 0, -2, 1, 0),
        "DBP": (0, 1, 0, -1, 1, 0, -1, 0),
    }
    pattern = patterns[metric]
    session_id = str(st.session_state.get("session_id", "") or "review-clinical-live")
    digest = hashlib.sha256(f"{session_id}:{metric}".encode("utf-8")).digest()
    phase = digest[0] % len(pattern)
    return int(pattern[(int(bucket) + phase) % len(pattern)])


def live_display_vitals(sim: Simulator, bucket: Optional[int] = None) -> Dict[str, str]:
    """Return review-mode monitor values with UI-only physiologic variation.

    Clinical and academy modes both receive small bedside-monitor display changes.
    The function never mutates ``sim.state``: disease evolution, elapsed scenario
    time, scoring, reports and exported research/review data remain unchanged.
    """
    try:
        system_mode = current_flow_strategy(sim).system_mode
    except Exception:
        system_mode = current_system_mode()
    if system_mode not in {"clinical", "academy"}:
        return visible_vitals(sim)

    f = sim.state.flags
    if f.get("dead", False) or (
        f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False)
    ):
        return visible_vitals(sim)

    if bucket is None:
        bucket = int(time.monotonic() // CLINICAL_REVIEW_LIVE_VITALS_REFRESH_SECONDS)

    v = sim.state.vitals
    out = {"体温": f"{v.get('Temp', 0):.1f} ℃"}

    if f.get("monitor_on", False):
        spo2 = max(
            40,
            min(
                100,
                round(float(v.get("SpO2", 0)) + _review_live_vital_pattern_value(bucket, "SpO2")),
            ),
        )
        hr = max(
            40,
            min(
                220,
                round(float(v.get("HR", 0)) + _review_live_vital_pattern_value(bucket, "HR")),
            ),
        )
        if f.get("resuscitation_rosc", False):
            out.update(
                {
                    "SpO₂": f"{spo2:.0f} %（波形恢复）",
                    "HR": f"{hr:.0f} /min（可触及脉搏）",
                    "RR": "人工通气支持",
                }
            )
        else:
            rr = max(
                5,
                min(
                    80,
                    round(float(v.get("RR", 0)) + _review_live_vital_pattern_value(bucket, "RR")),
                ),
            )
            out.update(
                {
                    "SpO₂": f"{spo2:.0f} %",
                    "HR": f"{hr:.0f} /min",
                    "RR": f"{rr:.0f} /min",
                }
            )
    else:
        if f.get("resuscitation_rosc", False):
            out.update(
                {"SpO₂": "未连接监护", "HR": "未连接监护", "RR": "人工通气支持"}
            )
        else:
            out.update(
                {"SpO₂": "未连接监护", "HR": "未连接监护", "RR": "未连接监护"}
            )

    if f.get("bp_checked", False):
        # BP refreshes more slowly than HR/RR/SpO2 while remaining display-only.
        bp_bucket = int(bucket) // 3
        sbp = max(
            30,
            min(
                160,
                round(float(v.get("SBP", 0)) + _review_live_vital_pattern_value(bp_bucket, "SBP")),
            ),
        )
        dbp = max(
            20,
            min(
                110,
                round(float(v.get("DBP", 0)) + _review_live_vital_pattern_value(bp_bucket, "DBP")),
            ),
        )
        out["BP"] = f"{sbp:.0f}/{dbp:.0f} mmHg"
    else:
        out["BP"] = "未测量"
    return out


def symptoms_text(sim: Simulator) -> str:
    s = sim.state.symptoms
    f = sim.state.flags
    v = sim.state.vitals

    if f.get("dead", False):
        return "患儿意识丧失，呼之不应，无有效自主呼吸，脉搏未触及。"
    if f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False):
        return "患儿意识丧失，呼之不应，无有效自主呼吸，脉搏未触及。"
    if f.get("resuscitation_rosc", False):
        return "患儿恢复可触及脉搏，高级生命支持团队已接手，拟转入PICU进一步治疗。"

    spo2 = float(v.get("SpO2", 100))
    sbp = float(v.get("SBP", 120))
    consciousness = int(s.get("consciousness", 0))
    sbp_thr = sim.age_sbp_threshold()
    airway_flag = bool(f.get("airway_obstruction_triggered", False) or f.get("bvm_required", False))

    # Objective deterioration text only; no next-step instruction is exposed in exam mode.
    if airway_flag and (spo2 < 88 or consciousness >= 2):
        return "患儿呼吸费力，面色发绀，吸气性呼吸困难，反应差。"
    if spo2 <= 70 or sbp <= 45 or consciousness >= 3:
        return "患儿面色发绀，反应差，呼吸浅弱或不规则，四肢湿冷。"
    if spo2 < 85 or sbp < sbp_thr:
        return "患儿喘息加重，面色苍白或发绀，烦躁或反应迟钝，末梢灌注差。"
    if spo2 < 92 or int(s.get("wheeze", 0)) >= 2 or int(s.get("stridor", 0)) >= 1:
        parts = ["咳嗽/喘息较前加重", "呼吸急促"]
        if int(s.get("rash", 0)) >= 1:
            parts.append("皮疹/风团明显")
        if int(s.get("angioedema", 0)) >= 1:
            parts.append("局部血管性水肿")
        if int(s.get("stridor", 0)) >= 1:
            parts.append("喉鸣或声音改变")
        return "、".join(parts) + "。"

    parts = []
    if s.get("rash", 0) >= 1:
        parts.append("皮疹/风团")
    if s.get("angioedema", 0) >= 1:
        parts.append("血管性水肿")
    if s.get("wheeze", 0) >= 1:
        parts.append("咳嗽/喘息")
    if s.get("stridor", 0) >= 1:
        parts.append("喉鸣/声音改变")
    if s.get("gi", 0) >= 1:
        parts.append("胃肠道症状")
    if consciousness >= 1:
        labels = ["烦躁", "嗜睡", "反应差"]
        parts.append(labels[min(2, consciousness - 1)])
    if parts:
        return "、".join(parts) + "。"
    if f.get("epi_im_given") and f.get("fluid_bolus_valid") and not f.get("bronchodilator_neb"):
        return "循环较前改善，皮疹减轻，但仍有咳嗽/轻微喘息。"
    if f.get("bronchodilator_neb") and f.get("second_reassessment_done"):
        return "生命体征趋于稳定，咳嗽/喘息较前减轻。"
    return "患儿仍有轻度皮肤不适和呼吸道不适表现。"

def grade_badge(sim: Simulator) -> str:
    # Grade is retained in backend reports, but not exposed as a diagnostic hint in the participant UI.
    return "动态观察"


def get_report_download(report: Dict[str, Any]) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


AUTH_SECRET_FIELDS = ("APP_ACCESS_CODE", "ADMIN_PASSWORD")
AUTH_CONFIGURATION_ERROR_MESSAGE = "系统安全配置不完整，请联系系统管理员。"


class AuthConfigurationError(RuntimeError):
    def __init__(self, invalid_fields: Tuple[str, ...]):
        self.invalid_fields = tuple(dict.fromkeys(invalid_fields))
        super().__init__("Invalid authentication configuration: " + ", ".join(self.invalid_fields))


def _read_required_auth_secret(name: str) -> str:
    try:
        value = st.secrets.get(name, None)  # type: ignore[attr-defined]
    except Exception:
        raise AuthConfigurationError((name,)) from None
    if not isinstance(value, str):
        raise AuthConfigurationError((name,))
    normalized = value.strip()
    if not normalized:
        raise AuthConfigurationError((name,))
    return normalized


def get_auth_credentials() -> Tuple[str, str]:
    values: Dict[str, str] = {}
    invalid_fields: List[str] = []
    for name in AUTH_SECRET_FIELDS:
        try:
            values[name] = _read_required_auth_secret(name)
        except AuthConfigurationError as exc:
            invalid_fields.extend(exc.invalid_fields)
    if invalid_fields:
        raise AuthConfigurationError(tuple(invalid_fields))
    access_code = values["APP_ACCESS_CODE"]
    admin_password = values["ADMIN_PASSWORD"]
    if token_secrets.compare_digest(access_code, admin_password):
        raise AuthConfigurationError(AUTH_SECRET_FIELDS)
    return access_code, admin_password


def get_competition_auth_credentials() -> Tuple[str, str]:
    try:
        secrets_source = st.secrets  # type: ignore[attr-defined]
    except Exception:
        secrets_source = None
    credentials = competition_credentials(
        secrets=secrets_source,
        environ=os.environ,
    )
    if (
        credentials.review_configured
        and credentials.admin_configured
        and token_secrets.compare_digest(
            credentials.review_code,
            credentials.admin_code,
        )
    ):
        return "", ""
    return credentials.review_code, credentials.admin_code


def require_auth_credentials() -> Tuple[str, str]:
    try:
        return get_auth_credentials()
    except AuthConfigurationError as exc:
        st.error(AUTH_CONFIGURATION_ERROR_MESSAGE)
        st.caption("缺少或无效的安全配置字段：" + "、".join(exc.invalid_fields))
        st.stop()
        raise AuthConfigurationError(exc.invalid_fields) from None


def credential_matches(submitted: object, expected: str) -> bool:
    return isinstance(submitted, str) and token_secrets.compare_digest(submitted, expected)


def load_org_access_records() -> List[Dict[str, Any]]:
    if is_competition_mode():
        return []
    try:
        secret_records = st.secrets.get("ORG_ACCESS_RECORDS", None)  # type: ignore[attr-defined]
    except Exception:
        secret_records = None
    if secret_records is not None:
        if not isinstance(secret_records, (list, tuple)):
            return []
        records: List[Dict[str, Any]] = []
        for item in secret_records:
            try:
                record = dict(item)
                if "credential" in record:
                    record["credential"] = dict(record["credential"])
            except (TypeError, ValueError):
                return []
            records.append(record)
        return records
    if not ORG_ACCESS_CODES_PATH.exists():
        return []
    try:
        data = json.loads(ORG_ACCESS_CODES_PATH.read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def _valid_organization_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Z][A-Z0-9_-]{2,63}", value.strip()))


def _normalize_unit_identity(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(record, dict) or str(record.get("status", "active")) != "active":
        return None
    role = str(record.get("role", "") or "").strip()
    organization_type = str(record.get("organization_type", "") or "").strip()
    organization_id = str(record.get("organization_id", "") or "").strip()
    credential = org_credentials.normalize_credential(record.get("credential"))
    expected_type = {
        "clinical_admin": "clinical",
        "academy_admin": "academy",
    }.get(role)
    if (
        role not in UNIT_ADMIN_ROLES
        or organization_type != expected_type
        or not _valid_organization_id(organization_id)
        or credential is None
    ):
        return None
    return {
        "role": role,
        "organization_type": organization_type,
        "organization_id": organization_id,
        "hospital_name": str(record.get("hospital_name", "") or "").strip(),
        "department_name": str(record.get("department_name", "") or "").strip(),
        "school_name": str(record.get("school_name", "") or "").strip(),
        "credential": credential,
        "permissions": ["view", "export"],
    }


def configured_organizations(organization_type: str) -> List[Dict[str, Any]]:
    organizations: List[Dict[str, Any]] = []
    seen_ids = set()
    for record in load_org_access_records():
        identity = _normalize_unit_identity(record)
        if (
            identity
            and identity["organization_type"] == organization_type
            and identity["organization_id"] not in seen_ids
        ):
            organizations.append(identity)
            seen_ids.add(identity["organization_id"])
    return organizations


def organization_display_label(identity: Dict[str, Any]) -> str:
    if identity.get("organization_type") == "academy":
        name = identity.get("school_name", "")
        unit = identity.get("department_name", "")
    else:
        name = identity.get("hospital_name", "")
        unit = identity.get("department_name", "")
    display = "｜".join(part for part in (name, unit) if part)
    return display or str(identity.get("organization_id", ""))


def _authorization_signing_key() -> bytes:
    """Return a stable deployment key; predictable fallback is test-only."""
    configured = _deployment_setting("AUTH_CONTEXT_SIGNING_KEY", "").strip()
    if len(configured) >= 32:
        return hashlib.sha256(configured.encode("utf-8")).digest()
    if not hasattr(st, "__name__") or os.environ.get("PEDSIM_AUTOMATED_TEST") == "1":
        material = "test-only-authorization-context:" + APP_VERSION
        return hashlib.sha256(material.encode("utf-8")).digest()
    raise AuthConfigurationError(("AUTH_CONTEXT_SIGNING_KEY",))


def _authorization_signature(role: str, organization_type: str, organization_id: str) -> str:
    payload = f"{role}\n{organization_type}\n{organization_id}".encode("utf-8")
    return hmac.new(_authorization_signing_key(), payload, hashlib.sha256).hexdigest()


def _issue_authorization_context(
    role: str,
    organization_type: str,
    organization_id: str,
    **display_fields: Any,
) -> Dict[str, Any]:
    context = {
        "role": role,
        "organization_type": organization_type,
        "organization_id": organization_id,
        "permissions": ["view", "export", "manage"]
        if role == PLATFORM_ADMIN_ROLE
        else ["view", "export"],
    }
    for key in ("hospital_name", "department_name", "school_name"):
        context[key] = str(display_fields.get(key, "") or "").strip()
    context["signature"] = _authorization_signature(
        role,
        organization_type,
        organization_id,
    )
    return context


def create_platform_admin_context() -> Dict[str, Any]:
    return _issue_authorization_context(
        PLATFORM_ADMIN_ROLE,
        "platform",
        "PLATFORM",
    )


def create_competition_admin_context() -> Dict[str, Any]:
    return _issue_authorization_context(
        COMPETITION_ADMIN_ROLE,
        "competition",
        "COMPETITION_DEMO",
    )


def validate_authorization_context(
    context: object,
) -> Optional[Dict[str, Any]]:
    if not isinstance(context, dict):
        return None
    role = str(context.get("role", "") or "").strip()
    organization_type = str(context.get("organization_type", "") or "").strip()
    organization_id = str(context.get("organization_id", "") or "").strip()
    signature = str(context.get("signature", "") or "")
    if not role or not organization_type or not organization_id or not signature:
        return None
    try:
        expected_signature = _authorization_signature(
            role,
            organization_type,
            organization_id,
        )
    except AuthConfigurationError:
        return None
    if not token_secrets.compare_digest(signature, expected_signature):
        return None
    if role == COMPETITION_ADMIN_ROLE:
        if (
            not is_competition_mode()
            or organization_type != "competition"
            or organization_id != "COMPETITION_DEMO"
        ):
            return None
        return create_competition_admin_context()
    if is_competition_mode():
        return None
    if role == PLATFORM_ADMIN_ROLE:
        if organization_type != "platform" or organization_id != "PLATFORM":
            return None
        return create_platform_admin_context()
    if role not in UNIT_ADMIN_ROLES:
        return None
    for record in load_org_access_records():
        identity = _normalize_unit_identity(record)
        if (
            identity
            and identity["role"] == role
            and identity["organization_type"] == organization_type
            and identity["organization_id"] == organization_id
        ):
            return _issue_authorization_context(**identity)
    return None


def find_org_scope_by_code(code: str) -> Optional[Dict[str, Any]]:
    if not org_credentials.valid_admin_code(code):
        return None
    matches: List[Dict[str, Any]] = []
    for item in load_org_access_records():
        identity = _normalize_unit_identity(item)
        if identity and org_credentials.verify_credential(
            code,
            identity["credential"],
            identity["role"],
            identity["organization_type"],
            identity["organization_id"],
        ):
            matches.append(identity)
    if len(matches) != 1:
        return None
    return _issue_authorization_context(**matches[0])


def _record_organization(record: Dict[str, Any]) -> Tuple[str, str]:
    source = record.get("session", {}) if isinstance(record.get("session"), dict) else record
    return (
        str(source.get("organization_type", "") or "").strip(),
        str(source.get("organization_id", "") or "").strip(),
    )


def _record_matches_authorization(
    record: Dict[str, Any],
    authorization: Dict[str, Any],
) -> bool:
    if authorization["role"] == COMPETITION_ADMIN_ROLE:
        return is_competition_mode()
    if authorization["role"] == PLATFORM_ADMIN_ROLE:
        return True
    organization_type, organization_id = _record_organization(record)
    return bool(
        organization_type == authorization["organization_type"]
        and organization_id == authorization["organization_id"]
    )


def record_matches_scope(record: Dict[str, Any], scope: object) -> bool:
    authorization = validate_authorization_context(scope)
    return bool(
        authorization
        and isinstance(record, dict)
        and _record_matches_authorization(record, authorization)
    )


def raw_record_matches_scope(record: Dict[str, Any], scope: object) -> bool:
    return record_matches_scope(record, scope)


def scope_label(scope: object) -> str:
    authorization = validate_authorization_context(scope)
    if authorization is None:
        return "无效权限"
    role = authorization["role"]
    if role == COMPETITION_ADMIN_ROLE:
        return "评审只读管理员｜仅虚拟演示数据"
    if role == PLATFORM_ADMIN_ROLE:
        return "总管理员｜可查看全部数据"
    if role == "clinical_admin":
        return (
            "临床单位管理员｜"
            f"{authorization.get('hospital_name', '')} - "
            f"{authorization.get('department_name', '')}"
        )
    if role == "academy_admin":
        return f"学院单位管理员｜{authorization.get('school_name', '')}"
    return "未知权限"


def authorization_allows(context: object, permission: str) -> bool:
    authorization = validate_authorization_context(context)
    if authorization is None:
        return False
    return str(permission) in set(authorization.get("permissions", []))


def build_session_metadata(end_reason: str = "") -> Dict[str, Any]:
    return {
        "app_version": APP_VERSION,
        "system_mode": current_system_mode(),
        "system_mode_label": current_system_mode_label(),
        "participant_type": SYSTEM_MODE_OPTIONS[current_system_mode()].get("participant_type", ""),
        "academy_scenario_id": st.session_state.get("academy_scenario_id", ""),
        "academy_scenario_name": st.session_state.get("academy_scenario_name", ""),
        "academy_scenario_category": st.session_state.get("academy_scenario_category", ""),
        "academy_course_type": st.session_state.get("academy_course_type", ""),
        "academy_difficulty": st.session_state.get("academy_difficulty", ""),
        "school_name": st.session_state.get("school_name", ""),
        "organization_id": st.session_state.get("organization_id", ""),
        "organization_type": st.session_state.get("organization_type", current_system_mode()),
        "student_level": st.session_state.get("student_level", ""),
        "student_grade": st.session_state.get("student_grade", ""),
        "student_class": st.session_state.get("student_class", ""),
        "session_id": st.session_state.get("session_id", ""),
        "completion_id": st.session_state.get("completion_id", ""),
        "participant_id": st.session_state.get("participant_id", "") or "anonymous",
        "participant_initials": st.session_state.get("participant_initials", ""),
        "campus_code": st.session_state.get("campus_code", ""),
        "department_code": st.session_state.get("department_code", ""),
        "institution": st.session_state.get("institution", DEFAULT_INSTITUTION),
        "campus": st.session_state.get("campus", ""),
        "department": st.session_state.get("department", ""),
        "department_type": st.session_state.get("department_type", ""),
        "nurse_level": st.session_state.get("nurse_level", ""),
        "years_experience": st.session_state.get("years_experience", ""),
        "years_experience_confirmed": bool(st.session_state.get("years_experience_confirmed", False)),
        "professional_title": st.session_state.get("professional_title", ""),
        "education_level": st.session_state.get("education_level", ""),
        "prior_anaphylaxis_training": st.session_state.get("prior_anaphylaxis_training", ""),
        "prior_simulation_experience": st.session_state.get("prior_simulation_experience", ""),
        "real_case_experience": st.session_state.get("real_case_experience", ""),
        "prior_experience_survey_completed": bool(st.session_state.get("prior_experience_survey_completed", False)),
        "prior_experience_survey_time": st.session_state.get("prior_experience_survey_time", ""),
        "baseline_performance_completed": bool(st.session_state.get("baseline_performance_completed", False)),
        "baseline_stage_completed": bool(st.session_state.get("baseline_stage_completed", False)),
        "academy_post_evaluation_completed": bool(st.session_state.get("academy_post_evaluation_completed", False)),
        "academy_post_evaluation_time": st.session_state.get("academy_post_evaluation_time", ""),
        "sus_score": st.session_state.get("sus_score", ""),
        "sus_level": st.session_state.get("sus_level", ""),
        "teaching_experience_total": st.session_state.get("teaching_experience_total", ""),
        "teaching_experience_mean": st.session_state.get("teaching_experience_mean", ""),
        "training_batch": st.session_state.get("training_batch", ""),
        "assessment_phase": st.session_state.get("assessment_phase", ""),
        "collection_mode": st.session_state.get("collection_mode", "正式采集"),
        "collection_mode_code": COLLECTION_MODE_CODES.get(st.session_state.get("collection_mode", "正式采集"), "formal"),
        "collection_note": st.session_state.get("collection_note", ""),
        "workflow_mode": st.session_state.get("workflow_mode", ""),
        "workflow_script_role": st.session_state.get("workflow_script_role", ""),
        "workflow_display": st.session_state.get("workflow_display", ""),
        "workflow_locked": bool(st.session_state.get("workflow_locked", True)),
        "attempt_no": st.session_state.get("attempt_no", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "end_reason": end_reason,
    }


def research_metadata_from_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Fields used for multi-campus, multi-level research exports."""
    return {
        "system_mode": session.get("system_mode", ""),
        "system_mode_label": session.get("system_mode_label", ""),
        "participant_type": session.get("participant_type", ""),
        "academy_scenario_id": session.get("academy_scenario_id", ""),
        "academy_scenario_name": session.get("academy_scenario_name", ""),
        "academy_scenario_category": session.get("academy_scenario_category", ""),
        "academy_course_type": session.get("academy_course_type", ""),
        "academy_difficulty": session.get("academy_difficulty", ""),
        "institution": session.get("institution", ""),
        "school_name": session.get("school_name", ""),
        "organization_id": session.get("organization_id", ""),
        "organization_type": session.get("organization_type", session.get("system_mode", "")),
        "student_level": session.get("student_level", ""),
        "student_grade": session.get("student_grade", ""),
        "student_class": session.get("student_class", ""),
        "campus": session.get("campus", ""),
        "campus_code": session.get("campus_code", ""),
        "department": session.get("department", ""),
        "department_code": session.get("department_code", ""),
        "participant_initials": session.get("participant_initials", ""),
        "department_type": session.get("department_type", ""),
        "nurse_level": session.get("nurse_level", ""),
        "years_experience": session.get("years_experience", ""),
        "years_experience_confirmed": session.get("years_experience_confirmed", ""),
        "professional_title": session.get("professional_title", ""),
        "education_level": session.get("education_level", ""),
        "collection_mode": session.get("collection_mode", ""),
        "collection_mode_code": session.get("collection_mode_code", ""),
        "collection_note": session.get("collection_note", ""),
        "prior_anaphylaxis_training": session.get("prior_anaphylaxis_training", ""),
        "prior_simulation_experience": session.get("prior_simulation_experience", ""),
        "real_case_experience": session.get("real_case_experience", ""),
        "prior_experience_survey_completed": session.get("prior_experience_survey_completed", ""),
        "prior_experience_survey_time": session.get("prior_experience_survey_time", ""),
        "academy_post_evaluation_completed": session.get("academy_post_evaluation_completed", ""),
        "academy_post_evaluation_time": session.get("academy_post_evaluation_time", ""),
        "sus_score": session.get("sus_score", ""),
        "sus_level": session.get("sus_level", ""),
        "teaching_experience_total": session.get("teaching_experience_total", ""),
        "teaching_experience_mean": session.get("teaching_experience_mean", ""),
        "training_batch": session.get("training_batch", ""),
        "assessment_phase": session.get("assessment_phase", ""),
        "workflow_mode": session.get("workflow_mode", ""),
        "workflow_script_role": session.get("workflow_script_role", ""),
        "workflow_display": session.get("workflow_display", ""),
        "workflow_locked": session.get("workflow_locked", ""),
        "attempt_no": session.get("attempt_no", ""),
    }


def enrich_report(report: Dict[str, Any], end_reason: str = "") -> Dict[str, Any]:
    enriched = json.loads(json.dumps(report, ensure_ascii=False))
    enriched["session"] = build_session_metadata(end_reason=end_reason)
    enriched["end_reason"] = end_reason
    return enriched


def academy_evaluation_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    session = report.get("session", {}) or {}
    post_eval = report.get("academy_post_evaluation", {}) or {}
    sus = post_eval.get("sus", {}) or {}
    teaching = post_eval.get("teaching_experience", {}) or {}
    return {
        "academy_post_evaluation_completed": post_eval.get("completed", session.get("academy_post_evaluation_completed", "")),
        "academy_post_evaluation_time": post_eval.get("completed_time", session.get("academy_post_evaluation_time", "")),
        "sus_score": sus.get("score", session.get("sus_score", "")),
        "sus_level": sus.get("level", session.get("sus_level", "")),
        "teaching_experience_total": teaching.get("total", session.get("teaching_experience_total", "")),
        "teaching_experience_mean": teaching.get("mean", session.get("teaching_experience_mean", "")),
    }


def flatten_record(report: Dict[str, Any]) -> Dict[str, Any]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    timeline = report.get("key_timeline", {}) or {}
    issues = report.get("process_safety_issues", []) or []
    missing = report.get("critical_missing", []) or []
    return {
        "created_at": session.get("created_at", ""),
        "session_id": session.get("session_id", ""),
        "completion_id": session.get("completion_id", ""),
        "participant_id": session.get("participant_id", ""),
        **research_metadata_from_session(session),
        "mode": report.get("mode", ""),
        "scenario_script_name": report.get("scenario_script_name", ""),
        "scenario_title": report.get("scenario_title", ""),
        "age_years": patient.get("age_years", ""),
        "weight_kg": patient.get("weight_kg", ""),
        "end_reason": report.get("end_reason", ""),
        "end_time_seconds": report.get("end_time_seconds", ""),
        "final_grade": report.get("final_grade", ""),
        "score": report.get("score", ""),
        "raw_score": report.get("raw_score", ""),
        "penalties": report.get("penalties", ""),
        "max_score": report.get("max_score", ""),
        "manual_rescue_completion": (report.get("clinical_pathway_flags", {}) or {}).get("manual_rescue_completion", ""),
        "unfinished_required_steps": "；".join(map(str, (report.get("clinical_pathway_flags", {}) or {}).get("unfinished_required_steps", []) or [])),
        "completion_rate_at_manual_finish": (report.get("clinical_pathway_flags", {}) or {}).get("completion_rate_at_manual_finish", ""),
        "iv_removed": (report.get("clinical_pathway_flags", {}) or {}).get("iv_removed", ""),
        "iv_access_reestablished": (report.get("clinical_pathway_flags", {}) or {}).get("iv_access_reestablished", ""),
        "iv_rescue_credit": (report.get("clinical_pathway_flags", {}) or {}).get("iv_rescue_credit", ""),
        "epinephrine_subscores": json.dumps((report.get("clinical_pathway_flags", {}) or {}).get("epinephrine_subscores", {}) or {}, ensure_ascii=False),
        "reassess_count": timeline.get("reassess_count", ""),
        "epi_last_dose_mg": timeline.get("epi_last_dose_mg", ""),
        "epi_target_dose_mg": timeline.get("epi_target_dose_mg", ""),
        "process_safety_issues": "；".join(map(str, issues)),
        "critical_missing": "；".join(map(str, missing)),
        **academy_evaluation_from_report(report),
        "app_version": session.get("app_version", APP_VERSION),
    }


def _secret_get(*names: str, default: str = "") -> str:
    """Read secrets from Streamlit Cloud, local secrets.toml, or environment variables.

    Supported formats:
    - SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_TABLE
    - [supabase] url / service_role_key / table
    """
    for name in names:
        value = None
        try:
            value = st.secrets.get(name, None)  # type: ignore[attr-defined]
        except Exception:
            value = None
        if value is not None:
            return str(value)
        value = os.environ.get(name, None)
        if value is not None:
            return str(value)
    try:
        supa = st.secrets.get("supabase", {})  # type: ignore[attr-defined]
        if isinstance(supa, dict):
            for name in names:
                key = name.lower().replace("supabase_", "")
                if key in supa and supa[key] is not None:
                    return str(supa[key])
    except Exception:
        pass
    return default


def database_configured() -> bool:
    if not current_storage_adapter().allows_database:
        return False
    return bool(_secret_get("SUPABASE_URL")) and bool(_secret_get("SUPABASE_SERVICE_ROLE_KEY"))


@st.cache_resource(show_spinner=False)
def get_supabase_client_cached(url: str, key: str):
    from supabase import create_client
    return create_client(url, key)


def get_supabase_client():
    if not current_storage_adapter().allows_database:
        return None
    url = _secret_get("SUPABASE_URL")
    key = _secret_get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return get_supabase_client_cached(url, key)


def supabase_table_name() -> str:
    return _secret_get("SUPABASE_TABLE", default="training_records") or "training_records"


def infer_epi_dose_status(report: Dict[str, Any]) -> str:
    issues = "；".join(map(str, report.get("process_safety_issues", []) or []))
    logs = report.get("log", []) or []
    if "超过儿童单次最大0.3" in issues or "超过0.3" in issues or "心动过速致心衰" in issues:
        return "overdose"
    if "剂量不足" in issues or "操作无效" in issues:
        return "underdose"
    for item in logs:
        if not isinstance(item, dict):
            continue
        message = item.get("message", "")
        if message == "im_epinephrine_overdose":
            return "overdose"
        if message == "im_epinephrine_dose_high":
            return "dose_high"
        if message == "im_epinephrine_underdose":
            return "underdose"
        if message == "im_epinephrine_dose_verified":
            return "valid"
    timeline = report.get("key_timeline", {}) or {}
    if timeline.get("epi_last_dose_mg") is not None:
        return "valid"
    return "not_given"


def make_database_record(report: Dict[str, Any]) -> Dict[str, Any]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    timeline = report.get("key_timeline", {}) or {}
    logs = report.get("log", []) or []
    action_logs = [x for x in logs if isinstance(x, dict) and x.get("kind") == "action"]
    return {
        "participant_id": str(session.get("participant_id", "anonymous") or "anonymous"),
        "organization_type": str(session.get("organization_type", "") or ""),
        "organization_id": str(session.get("organization_id", "") or ""),
        "hospital": str(session.get("institution", "") or ""),
        "department": str(session.get("department", "") or ""),
        "mode": str(report.get("mode", "") or ""),
        "scenario_name": str(report.get("scenario_script_name", report.get("scenario_title", "")) or ""),
        "scenario_file": str(st.session_state.get("active_scenario_path", "") or ""),
        "age_years": patient.get("age_years"),
        "weight_kg": patient.get("weight_kg"),
        "score": report.get("score"),
        "raw_score": report.get("raw_score"),
        "penalties": report.get("penalties"),
        "final_grade": str(report.get("final_grade", "") or ""),
        "end_reason": str(report.get("end_reason", "") or ""),
        "success": str(report.get("end_reason", "")) in ("success", "standard_assessment_completed"),
        "epi_target_dose_mg": timeline.get("epi_target_dose_mg"),
        "epi_input_dose_mg": timeline.get("epi_last_dose_mg"),
        "epi_dose_status": infer_epi_dose_status(report),
        "action_count": len(action_logs),
        "reassessment_count": timeline.get("reassess_count"),
        "safety_issues": report.get("process_safety_issues", []) or [],
        "action_timeline": logs,
        "full_report": report,
        "app_version": session.get("app_version", APP_VERSION),
        "session_id": session.get("session_id", ""),
        "completion_id": session.get("completion_id", ""),
        "client_note": "saved_from_streamlit_v1_2_6d_arrest_no_cpr_death_event",
    }


def _valid_persistence_id(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _legacy_completion_id(session_id: object) -> str:
    value = str(session_id or "").strip()
    if not value:
        return ""
    return hashlib.sha256(f"legacy-session:{value}".encode("utf-8")).hexdigest()


def _record_completion_id(record: Dict[str, Any]) -> str:
    session = record.get("session", {}) if isinstance(record, dict) else {}
    if not isinstance(session, dict):
        session = {}
    candidate = record.get("completion_id") or session.get("completion_id")
    if _valid_persistence_id(candidate):
        return str(candidate)
    return _legacy_completion_id(record.get("session_id") or session.get("session_id"))


def ensure_report_completion_id(report: Dict[str, Any]) -> str:
    session = report.setdefault("session", {})
    if not isinstance(session, dict):
        session = {}
        report["session"] = session
    candidate = session.get("completion_id")
    report_session_id = str(session.get("session_id", "") or "")
    active_session_id = str(st.session_state.get("session_id", "") or "")
    if not _valid_persistence_id(candidate) and (
        not report_session_id or report_session_id == active_session_id
    ):
        candidate = st.session_state.get("completion_id", "")
    if not _valid_persistence_id(candidate) and report_session_id:
        candidate = _legacy_completion_id(report_session_id)
    if not _valid_persistence_id(candidate):
        candidate = token_secrets.token_hex(32)
    completion_id = str(candidate)
    session["completion_id"] = completion_id
    if not active_session_id or report_session_id == active_session_id:
        st.session_state.completion_id = completion_id
    return completion_id


def ensure_questionnaire_submission_id() -> str:
    candidate = st.session_state.get("questionnaire_submission_id", "")
    if not _valid_persistence_id(candidate):
        candidate = token_secrets.token_hex(32)
        st.session_state.questionnaire_submission_id = candidate
    return str(candidate)


def _questionnaire_results_path() -> Path:
    return current_storage_adapter().write_paths().questionnaires


def _results_lock_path() -> Path:
    return current_storage_adapter().write_paths().lock_file


def _results_warning_path() -> Path:
    return current_storage_adapter().write_paths().warning_file


@contextmanager
def _local_results_lock(timeout_seconds: float = 10.0):
    lock_path = _results_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    acquired = False
    try:
        handle.seek(0)
        deadline = time.monotonic() + timeout_seconds
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for the local results lock.")
                    time.sleep(0.02)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for the local results lock.")
                    time.sleep(0.02)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _read_jsonl_unlocked(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not path.exists():
        return [], []
    records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                warnings.append(f"{path.name}:{line_number}:{type(exc).__name__}")
                continue
            if isinstance(value, dict):
                records.append(value)
            else:
                warnings.append(f"{path.name}:{line_number}:NonObjectRecord")
    return records, warnings


def _append_storage_warnings_unlocked(warnings: List[str]) -> None:
    if not warnings:
        return
    warning_path = _results_warning_path()
    warning_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with warning_path.open("a", encoding="utf-8", newline="\n") as handle:
        for warning in warnings:
            handle.write(f"{stamp}\t{warning}\n")
        handle.flush()
        os.fsync(handle.fileno())


def _append_jsonl_unlocked(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":"))
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def save_result_record_local(report: Dict[str, Any]) -> bool:
    completion_id = ensure_report_completion_id(report)
    created = False
    paths = current_storage_adapter().write_paths()
    with _local_results_lock():
        index_records, index_warnings = _read_jsonl_unlocked(paths.results_index)
        full_reports, full_warnings = _read_jsonl_unlocked(paths.full_reports)
        _append_storage_warnings_unlocked(index_warnings + full_warnings)
        if completion_id not in {_record_completion_id(item) for item in index_records}:
            _append_jsonl_unlocked(paths.results_index, flatten_record(report))
            created = True
        if completion_id not in {_record_completion_id(item) for item in full_reports}:
            _append_jsonl_unlocked(paths.full_reports, report)
            created = True
    return created


def save_questionnaire_record_local(record: Dict[str, Any]) -> Dict[str, Any]:
    submission_id = str(record.get("questionnaire_submission_id", ""))
    completion_id = str(record.get("completion_id", ""))
    if not _valid_persistence_id(submission_id) or not _valid_persistence_id(completion_id):
        raise ValueError("Questionnaire persistence identifiers are invalid.")
    path = _questionnaire_results_path()
    with _local_results_lock():
        records, warnings = _read_jsonl_unlocked(path)
        _append_storage_warnings_unlocked(warnings)
        for existing in records:
            if (
                existing.get("questionnaire_submission_id") == submission_id
                or existing.get("completion_id") == completion_id
            ):
                return existing
        _append_jsonl_unlocked(path, record)
    return record


def save_result_record_database(report: Dict[str, Any]) -> Tuple[bool, str]:
    if not current_storage_adapter().allows_database:
        return False, "评审环境已禁用正式数据库写入。"
    if not database_configured():
        return False, "数据库未配置：未检测到 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY。"
    try:
        client = get_supabase_client()
        if client is None:
            return False, "数据库客户端初始化失败。"
        table = supabase_table_name()
        record = make_database_record(report)
        client.table(table).insert(record).execute()
        return True, f"已写入云端数据库表：{table}。"
    except Exception as exc:
        return False, f"数据库写入失败：{type(exc).__name__}: {exc}"


def save_result_record(report: Dict[str, Any]) -> None:
    """Save result to local JSONL backup and, when configured, Supabase database."""
    save_result_record_local(report)
    ok, msg = save_result_record_database(report)
    st.session_state["last_db_save_ok"] = ok
    st.session_state["last_db_save_message"] = msg


def load_result_records_local(authorization_context: object) -> List[Dict[str, Any]]:
    authorization = validate_authorization_context(authorization_context)
    if authorization is None:
        return []
    path = current_storage_adapter().admin_read_paths().results_index
    if is_competition_mode():
        records, _ = _read_jsonl_unlocked(path)
    else:
        with _local_results_lock():
            records, warnings = _read_jsonl_unlocked(path)
            _append_storage_warnings_unlocked(warnings)
    return [
        record
        for record in records
        if _record_matches_authorization(record, authorization)
    ]


def normalize_database_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten Supabase rows into an expanded one-row-per-session summary."""
    report = full_report_from_database_row(row)
    summary = report_to_summary_record(report, storage_source="supabase")
    # Prefer database-level fields when present because they are indexed and stable.
    summary["created_at"] = row.get("created_at", summary.get("created_at", ""))
    summary["session_id"] = row.get("session_id", summary.get("session_id", ""))
    summary["participant_id"] = row.get("participant_id", summary.get("participant_id", ""))
    summary["organization_type"] = row.get(
        "organization_type",
        summary.get("organization_type", ""),
    )
    summary["organization_id"] = row.get(
        "organization_id",
        summary.get("organization_id", ""),
    )
    summary["institution"] = row.get("hospital", summary.get("institution", ""))
    summary["department"] = row.get("department", summary.get("department", ""))
    summary["app_version"] = row.get("app_version", summary.get("app_version", APP_VERSION))
    return summary


def load_result_rows_database(
    authorization_context: object,
    limit: int = 10000,
) -> Tuple[List[Dict[str, Any]], str]:
    """Return raw Supabase rows, preserving full_report JSON for enhanced exports."""
    authorization = validate_authorization_context(authorization_context)
    if authorization is None:
        return [], "权限无效，未读取数据库。"
    if not current_storage_adapter().allows_database:
        return [], "评审环境已禁用正式数据库读取。"
    if not database_configured():
        return [], "数据库未配置。"
    try:
        client = get_supabase_client()
        if client is None:
            return [], "数据库客户端初始化失败。"
        table = supabase_table_name()
        query = client.table(table).select("*")
        if authorization["role"] != PLATFORM_ADMIN_ROLE:
            query = query.eq(
                "organization_type",
                authorization["organization_type"],
            ).eq(
                "organization_id",
                authorization["organization_id"],
            )
        response = query.order("created_at", desc=True).limit(limit).execute()
        data = response.data or []
        rows = [
            item
            for item in data
            if isinstance(item, dict)
            and _record_matches_authorization(item, authorization)
        ]
        return rows, f"已从云端数据库读取 {len(rows)} 条记录。"
    except Exception as exc:
        return [], f"数据库读取失败：{type(exc).__name__}: {exc}"


def load_result_records_database(
    authorization_context: object,
    limit: int = 10000,
) -> Tuple[List[Dict[str, Any]], str]:
    rows, message = load_result_rows_database(
        authorization_context,
        limit=limit,
    )
    if not rows:
        return [], message
    return [normalize_database_record(x) for x in rows], message


def load_full_reports_local(authorization_context: object) -> List[Dict[str, Any]]:
    authorization = validate_authorization_context(authorization_context)
    if authorization is None:
        return []
    paths = current_storage_adapter().admin_read_paths()
    if is_competition_mode():
        reports, _ = _read_jsonl_unlocked(paths.full_reports)
        questionnaires, _ = _read_jsonl_unlocked(paths.questionnaires)
    else:
        with _local_results_lock():
            reports, report_warnings = _read_jsonl_unlocked(paths.full_reports)
            questionnaires, questionnaire_warnings = _read_jsonl_unlocked(paths.questionnaires)
            _append_storage_warnings_unlocked(
                report_warnings + questionnaire_warnings
            )
    questionnaire_by_completion = {
        str(item.get("completion_id", "")): item
        for item in questionnaires
        if _valid_persistence_id(item.get("completion_id"))
    }
    merged: List[Dict[str, Any]] = []
    for source in reports:
        if not _record_matches_authorization(source, authorization):
            continue
        report = json.loads(json.dumps(source, ensure_ascii=False, default=str))
        questionnaire = questionnaire_by_completion.get(_record_completion_id(report))
        evaluation = questionnaire.get("academy_post_evaluation") if questionnaire else None
        if isinstance(evaluation, dict):
            report["academy_post_evaluation"] = evaluation
            session = report.setdefault("session", {})
            if isinstance(session, dict):
                session["academy_post_evaluation_completed"] = bool(evaluation.get("completed", False))
                session["academy_post_evaluation_time"] = evaluation.get("completed_time", "")
                sus = evaluation.get("sus", {}) or {}
                teaching = evaluation.get("teaching_experience", {}) or {}
                session["sus_score"] = sus.get("score", "")
                session["sus_level"] = sus.get("level", "")
                session["teaching_experience_total"] = teaching.get("total", "")
                session["teaching_experience_mean"] = teaching.get("mean", "")
        merged.append(report)
    return merged


def load_result_records(authorization_context: object) -> List[Dict[str, Any]]:
    authorization = validate_authorization_context(authorization_context)
    if authorization is None:
        return []
    db_records, _ = load_result_records_database(authorization)
    if db_records:
        return list(reversed(db_records))
    full_local = load_full_reports_local(authorization)
    if full_local:
        return build_summary_records_from_reports(full_local, storage_source="local")
    return load_result_records_local(authorization)

def _json_compact(value: Any) -> str:
    """Compact JSON string for CSV cells when a value is a list/dict."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _csv_ready_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _json_compact(v) for k, v in row.items()}


def _dataframe_ready_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize mixed columns so Streamlit does not emit Arrow fallback traces."""
    normalized = [dict(item) for item in records if isinstance(item, dict)]
    keys = {key for item in normalized for key in item}
    mixed_keys = set()
    for key in keys:
        value_types = {
            type(item.get(key))
            for item in normalized
            if item.get(key) is not None
        }
        if len(value_types) > 1 or any(
            value_type in (dict, list, tuple)
            for value_type in value_types
        ):
            mixed_keys.add(key)
    for item in normalized:
        for key in mixed_keys:
            item[key] = _json_compact(item.get(key))
    return normalized


def records_to_csv_bytes(
    records: List[Dict[str, Any]],
    authorization_context: object,
) -> bytes:
    authorization = validate_authorization_context(authorization_context)
    if authorization is None:
        return "".encode("utf-8-sig")
    authorized_records = [
        record
        for record in records
        if isinstance(record, dict)
        and _record_matches_authorization(record, authorization)
    ]
    if not authorized_records:
        return "".encode("utf-8-sig")
    fieldnames: List[str] = []
    for row in authorized_records:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows([_csv_ready_row(r) for r in authorized_records])
    return buf.getvalue().encode("utf-8-sig")


def records_to_jsonl_bytes(
    records: List[Dict[str, Any]],
    authorization_context: object,
) -> bytes:
    authorization = validate_authorization_context(authorization_context)
    if authorization is None:
        return b""
    authorized_records = [
        record
        for record in records
        if isinstance(record, dict)
        and _record_matches_authorization(record, authorization)
    ]
    if not authorized_records:
        return b""
    return "\n".join(
        json.dumps(record, ensure_ascii=False, default=str)
        for record in authorized_records
    ).encode("utf-8")


ACTION_LABELS_CN = {
    "stop_infusion": "停用可疑药物",
    "call_help": "呼救",
    "abc_assess": "ABC评估",
    "high_flow_oxygen": "开放气道给氧",
    "shock_position": "体位管理",
    "connect_monitor": "连接监护",
    "check_bp": "测血压",
    "im_epinephrine": "肌注肾上腺素",
    "fluid_bolus": "快速补液",
    "fluid_bolus_volume_verified": "快速补液容量确认",
    "fluid_bolus_under": "补液量不足",
    "fluid_bolus_over": "补液量过量",
    "fluid_bolus_invalid_no_iv": "补液无有效通路",
    "reassess_first": "第一次复评",
    "bronchodilator": "雾化支气管扩张剂",
    "reassess_second": "第二次复评",
    "family_explain": "告知家属",
    "sbar_handoff": "SBAR交接",
    "repeat_epinephrine": "再次肌注肾上腺素",
    "repeat_epinephrine_valid": "再次肌注肾上腺素",
    "repeat_epinephrine_not_indicated": "非必要再次肌注",
    "repeat_epinephrine_premature": "再次肌注时机过早",
    "advanced_support": "联系高级支持",
    "nebulized_epinephrine": "雾化肾上腺素",
    "cpr": "CPR",
    "antihistamine_iv": "抗组胺药",
    "steroid": "糖皮质激素",
    "steroid_dose_verified": "糖皮质激素剂量确认",
    "steroid_dose_issue": "糖皮质激素剂量/时机问题",
    "continue_infusion": "继续输注可疑药物",
    "remove_iv": "拔除静脉通路",
    "establish_iv": "建立静脉通路",
    "sedation": "镇静药",
    "allergy_identification": "识别疑似药物过敏反应",
    "prepare_rescue_equipment": "准备抢救物品",
    "academy_reassess": "基础复评",
    "academy_family_communication": "基础家属沟通",
    "academy_sbar_handoff": "简化SBAR汇报",
    "im_epinephrine_dose_verified": "肌注肾上腺素剂量确认",
    "im_epinephrine_underdose": "肌注肾上腺素剂量不足",
    "im_epinephrine_dose_high": "肌注肾上腺素剂量偏高",
    "im_epinephrine_overdose": "肌注肾上腺素过量",
}

KEY_ACTION_COLUMNS = [
    ("stop_infusion_time", "stop_infusion"),
    ("call_help_time", "call_help"),
    ("abc_assess_time", "abc_assess"),
    ("oxygen_time", "oxygen"),
    ("position_time", "position"),
    ("monitor_time", "monitor"),
    ("bp_check_time", "bp_check"),
    ("epi_time", "epi_im"),
    ("fluid_time", "fluid"),
    ("first_reassessment_time", "first_reassessment"),
    ("bronchodilator_time", "bronchodilator"),
    ("steroid_time", "steroid"),
    ("second_reassessment_time", "second_reassessment"),
    ("family_communication_time", "family_communication"),
    ("sbar_time", "sbar_handoff"),
    ("allergy_identification_time", "allergy_identification"),
    ("prepare_rescue_equipment_time", "prepare_rescue_equipment"),
    ("academy_reassess_time", "academy_reassess"),
    ("academy_family_communication_time", "academy_family_communication"),
    ("academy_sbar_handoff_time", "academy_sbar_handoff"),
]


def _get_logs(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    logs = report.get("log", []) or []
    return [x for x in logs if isinstance(x, dict)]


def _first_log_time(report: Dict[str, Any], message: str) -> Any:
    for entry in _get_logs(report):
        if entry.get("kind") == "action" and entry.get("message") == message:
            return entry.get("t")
    return None


def _action_attempt_count(report: Dict[str, Any], message: str) -> int:
    return sum(1 for entry in _get_logs(report) if entry.get("kind") == "action" and entry.get("message") == message)


def _timeline_value(report: Dict[str, Any], key: str) -> Any:
    timeline = report.get("key_timeline", {}) or {}
    return timeline.get(key, None)


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _yes_no(value: bool) -> str:
    return "是" if bool(value) else "否"


def _issue_text(report: Dict[str, Any]) -> str:
    return "；".join(map(str, report.get("process_safety_issues", []) or []))


def _missing_text(report: Dict[str, Any]) -> str:
    return "；".join(map(str, report.get("critical_missing", []) or []))


def full_report_from_database_row(row: Dict[str, Any]) -> Dict[str, Any]:
    report = row.get("full_report") or {}
    if not isinstance(report, dict):
        report = {}
    # Merge database-level fields back when older reports lack session metadata.
    session = report.setdefault("session", {})
    if isinstance(session, dict):
        session.setdefault("created_at", row.get("created_at", ""))
        session.setdefault("session_id", row.get("session_id", ""))
        session.setdefault("participant_id", row.get("participant_id", ""))
        session.setdefault("organization_type", row.get("organization_type", ""))
        session.setdefault("organization_id", row.get("organization_id", ""))
        session.setdefault("institution", row.get("hospital", ""))
        session.setdefault("campus", "")
        session.setdefault("department", row.get("department", ""))
        session.setdefault("department_type", "")
        session.setdefault("nurse_level", "")
        session.setdefault("years_experience", "")
        session.setdefault("years_experience_confirmed", "")
        session.setdefault("professional_title", "")
        session.setdefault("education_level", "")
        session.setdefault("collection_mode", row.get("collection_mode", ""))
        session.setdefault("collection_mode_code", row.get("collection_mode_code", ""))
        session.setdefault("collection_note", "")
        session.setdefault("prior_anaphylaxis_training", "")
        session.setdefault("prior_simulation_experience", "")
        session.setdefault("real_case_experience", "")
        session.setdefault("prior_experience_survey_completed", "")
        session.setdefault("prior_experience_survey_time", "")
        session.setdefault("training_batch", "")
        session.setdefault("assessment_phase", "")
        session.setdefault("workflow_mode", "")
        session.setdefault("workflow_script_role", "")
        session.setdefault("workflow_display", "")
        session.setdefault("workflow_locked", "")
        session.setdefault("attempt_no", "")
        session.setdefault("app_version", row.get("app_version", APP_VERSION))
    report.setdefault("mode", row.get("mode", ""))
    report.setdefault("scenario_script_name", row.get("scenario_name", ""))
    report.setdefault("end_reason", row.get("end_reason", ""))
    report.setdefault("score", row.get("score", ""))
    report.setdefault("raw_score", row.get("raw_score", ""))
    report.setdefault("penalties", row.get("penalties", ""))
    report.setdefault("final_grade", row.get("final_grade", ""))
    patient = report.setdefault("patient", {})
    if isinstance(patient, dict):
        patient.setdefault("age_years", row.get("age_years", ""))
        patient.setdefault("weight_kg", row.get("weight_kg", ""))
    return report


def report_to_summary_record(report: Dict[str, Any], storage_source: str = "supabase") -> Dict[str, Any]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    timeline = report.get("key_timeline", {}) or {}
    valid_timeline = report.get("key_valid_timeline", {}) or {}
    final_vitals = report.get("final_vitals", {}) or {}
    flags = report.get("clinical_pathway_flags", {}) or {}
    issues = _issue_text(report)
    missing = _missing_text(report)

    score = _safe_number(report.get("score", 0))
    max_score = _safe_number(report.get("max_score", 20), 20)
    epi_time = timeline.get("epi_im", _first_log_time(report, "im_epinephrine"))
    end_time = report.get("end_time_seconds", "")

    record: Dict[str, Any] = {
        "created_at": session.get("created_at", ""),
        "session_id": session.get("session_id", ""),
        "participant_id": session.get("participant_id", ""),
        **research_metadata_from_session(session),
        "mode": report.get("mode", ""),
        "scenario_script_name": report.get("scenario_script_name", ""),
        "scenario_title": report.get("scenario_title", ""),
        "age_years": patient.get("age_years", ""),
        "weight_kg": patient.get("weight_kg", ""),
        "end_reason": report.get("end_reason", ""),
        "success": _yes_no(report.get("end_reason", "") in ("success", "standard_assessment_completed")),
        "end_time_seconds": end_time,
        "final_grade": report.get("final_grade", ""),
        "score": report.get("score", ""),
        "raw_score": report.get("raw_score", ""),
        "penalties": report.get("penalties", ""),
        "max_score": report.get("max_score", ""),
        "manual_rescue_completion": flags.get("manual_rescue_completion", ""),
        "unfinished_required_steps": "；".join(map(str, flags.get("unfinished_required_steps", []) or [])),
        "completion_rate_at_manual_finish": flags.get("completion_rate_at_manual_finish", ""),
        "iv_removed": flags.get("iv_removed", ""),
        "iv_access_reestablished": flags.get("iv_access_reestablished", ""),
        "iv_rescue_credit": flags.get("iv_rescue_credit", ""),
        "epinephrine_subscores": json.dumps(flags.get("epinephrine_subscores", {}) or {}, ensure_ascii=False),
        "score_percent": round(score / max_score * 100, 1) if max_score else "",
        "reassess_count": timeline.get("reassess_count", ""),
        "action_count": sum(1 for e in _get_logs(report) if e.get("kind") == "action" and e.get("message") != "penalty"),
        "wrong_action_count": sum(1 for e in _get_logs(report) if e.get("kind") == "action" and e.get("message") == "penalty"),
        "harmful_action_count": sum(_action_attempt_count(report, x) for x in ["continue_infusion", "sedation", "remove_iv", "im_epinephrine_overdose"]),
        "epi_target_dose_mg": timeline.get("epi_target_dose_mg", ""),
        "epi_input_dose_mg": timeline.get("epi_last_dose_mg", ""),
        "epi_dose_status": infer_epi_dose_status(report),
        "epi_delay_seconds": epi_time if epi_time is not None else "",
        "underdose_epi": _yes_no("剂量不足" in issues or _action_attempt_count(report, "im_epinephrine_underdose") > 0),
        "dose_high_epi": _yes_no("剂量高于目标剂量" in issues or _action_attempt_count(report, "im_epinephrine_dose_high") > 0),
        "overdose_epi": _yes_no("超过儿童单次最大0.3" in issues or _action_attempt_count(report, "im_epinephrine_overdose") > 0),
        "fluid_bolus_volume_ml": timeline.get("fluid_bolus_volume_ml", ""),
        "fluid_min_ml": timeline.get("fluid_min_ml", ""),
        "fluid_max_ml": timeline.get("fluid_max_ml", ""),
        "fluid_bolus_valid": _yes_no(bool(timeline.get("fluid_bolus_valid", False))),
        "steroid_time": timeline.get("steroid", ""),
        "steroid_dose_mg": timeline.get("steroid_dose_mg", ""),
        "steroid_min_mg": timeline.get("steroid_min_mg", ""),
        "steroid_max_mg": timeline.get("steroid_max_mg", ""),
        "steroid_valid": _yes_no(bool(timeline.get("steroid_valid", False))),
        "epinephrine_delay_after_core_steps": _yes_no(bool(timeline.get("epinephrine_delay_after_core_steps", False))),
        "airway_obstruction_triggered": _yes_no(bool(timeline.get("airway_obstruction_triggered", False))),
        "bvm_required": _yes_no(bool(timeline.get("bvm_required", False))),
        "bvm_ventilation_time": timeline.get("bvm_ventilation", ""),
        "repeat_epinephrine_time": timeline.get("repeat_epinephrine", ""),
        "advanced_support_time": timeline.get("advanced_support", ""),
        "cpr_time": timeline.get("cpr", ""),
        "final_spo2": final_vitals.get("SpO2", ""),
        "final_hr": final_vitals.get("HR", ""),
        "final_rr": final_vitals.get("RR", ""),
        "final_sbp": final_vitals.get("SBP", ""),
        "final_dbp": final_vitals.get("DBP", ""),
        "process_safety_issues": issues,
        "critical_missing": missing,
        "process_safety_issue_count": len(report.get("process_safety_issues", []) or []),
        "critical_missing_count": len(report.get("critical_missing", []) or []),
        "completed_key_steps": "",
        "valid_completed_key_steps": "",
        "total_action_sequence": "",
        **academy_evaluation_from_report(report),
        "app_version": session.get("app_version", APP_VERSION),
        "storage_source": storage_source,
    }

    # Key timeline columns.
    for column_name, timeline_key in KEY_ACTION_COLUMNS:
        record[column_name] = timeline.get(timeline_key, "")

    valid_timeline_columns = {
        "valid_stop_infusion_time": "stop_infusion",
        "valid_call_help_time": "call_help",
        "valid_abc_assess_time": "abc_assess",
        "valid_oxygen_time": "oxygen",
        "valid_position_time": "position",
        "valid_monitor_time": "monitor",
        "valid_bp_check_time": "bp_check",
        "valid_epi_time": "epi_im",
        "valid_fluid_time": "fluid",
        "valid_first_reassessment_time": "first_reassessment",
        "valid_bronchodilator_time": "bronchodilator",
        "valid_steroid_time": "steroid",
        "valid_second_reassessment_time": "second_reassessment",
        "valid_family_communication_time": "family_communication",
        "valid_sbar_time": "sbar_handoff",
    }
    for column_name, timeline_key in valid_timeline_columns.items():
        record[column_name] = valid_timeline.get(timeline_key, "")

    # Extra action-time columns not present in key_timeline.
    record["nebulized_epinephrine_time"] = timeline.get("nebulized_epinephrine", _first_log_time(report, "nebulized_epinephrine"))
    record["reassessment_first_time"] = timeline.get("first_reassessment", _first_log_time(report, "reassess_first"))
    record["reassessment_second_time"] = timeline.get("second_reassessment", _first_log_time(report, "reassess_second"))

    required_steps = [
        "stop_infusion_time", "call_help_time", "abc_assess_time", "oxygen_time", "position_time",
        "monitor_time", "bp_check_time", "epi_time", "fluid_time", "first_reassessment_time",
        "bronchodilator_time", "steroid_time", "second_reassessment_time", "family_communication_time", "sbar_time"
    ]
    record["completed_key_steps"] = sum(1 for k in required_steps if record.get(k) not in ("", None))
    valid_required_steps = [
        "valid_stop_infusion_time", "valid_call_help_time", "valid_abc_assess_time", "valid_oxygen_time",
        "valid_position_time", "valid_monitor_time", "valid_bp_check_time", "valid_epi_time",
        "valid_fluid_time", "valid_first_reassessment_time", "valid_bronchodilator_time",
        "valid_steroid_time", "valid_second_reassessment_time", "valid_family_communication_time",
        "valid_sbar_time",
    ]
    record["valid_completed_key_steps"] = sum(1 for k in valid_required_steps if record.get(k) not in ("", None))

    sequence = []
    for entry in _get_logs(report):
        if entry.get("kind") == "action" and entry.get("message") != "penalty":
            msg = str(entry.get("message", ""))
            sequence.append(ACTION_LABELS_CN.get(msg, msg))
    record["total_action_sequence"] = " → ".join(sequence)
    return record


def report_to_action_detail_records(report: Dict[str, Any], storage_source: str = "supabase") -> List[Dict[str, Any]]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    rows: List[Dict[str, Any]] = []
    action_index = 0
    for entry in _get_logs(report):
        if entry.get("kind") != "action":
            continue
        action_index += 1
        data = entry.get("data", {}) or {}
        msg = str(entry.get("message", ""))
        action_id = str(data.get("action_id") or msg)
        if msg == "penalty":
            action_name = ACTION_LABELS_CN.get(action_id, action_id)
            event_type = "扣分"
        elif msg in ["im_epinephrine_dose_verified", "im_epinephrine_underdose", "im_epinephrine_dose_high", "im_epinephrine_overdose", "fluid_bolus_volume_verified", "fluid_bolus_under", "fluid_bolus_over", "fluid_bolus_invalid_no_iv", "steroid_dose_verified", "steroid_dose_issue"]:
            action_name = ACTION_LABELS_CN.get(msg, msg)
            event_type = "剂量判定"
        else:
            action_name = str(data.get("label") or ACTION_LABELS_CN.get(msg, msg))
            event_type = "操作"
        rows.append({
            "created_at": session.get("created_at", ""),
            "session_id": session.get("session_id", ""),
            "participant_id": session.get("participant_id", ""),
            **research_metadata_from_session(session),
            "mode": report.get("mode", ""),
            "scenario_script_name": report.get("scenario_script_name", ""),
            "age_years": patient.get("age_years", ""),
            "weight_kg": patient.get("weight_kg", ""),
            "action_index": action_index,
            "time_seconds": entry.get("t", ""),
            "event_type": event_type,
            "action_id": action_id,
            "action_name": action_name,
            "gained": data.get("gained", ""),
            "penalty": data.get("penalty", ""),
            "dose_mg": data.get("dose_mg", ""),
            "target_dose_mg": data.get("target_dose_mg", ""),
            "result": data.get("result", ""),
            "reason": data.get("reason", ""),
            "raw_message": msg,
            "raw_data_json": data,
            "end_reason": report.get("end_reason", ""),
            "final_score": report.get("score", ""),
            "storage_source": storage_source,
        })
    return rows


def build_summary_records_from_reports(reports: List[Dict[str, Any]], storage_source: str = "supabase") -> List[Dict[str, Any]]:
    return [report_to_summary_record(r, storage_source=storage_source) for r in reports if isinstance(r, dict)]


def build_action_detail_records_from_reports(reports: List[Dict[str, Any]], storage_source: str = "supabase") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for report in reports:
        if isinstance(report, dict):
            rows.extend(report_to_action_detail_records(report, storage_source=storage_source))
    return rows


PHASE_EXPORT_MAP_BY_MODE = {
    "clinical": {
        "基线评估": "baseline",
        "模拟培训": "training",
        "培训后考核": "post",
    },
    "academy": {
        "课前测评": "baseline",
        "模拟训练": "training",
        "课后考核": "post",
    },
}
# Backward-compatible clinical map.
PHASE_EXPORT_MAP = PHASE_EXPORT_MAP_BY_MODE["clinical"]


def phase_export_map_for_mode(system_mode: str) -> Dict[str, str]:
    return PHASE_EXPORT_MAP_BY_MODE.get(system_mode or "clinical", PHASE_EXPORT_MAP_BY_MODE["clinical"])


def _record_sort_value(record: Dict[str, Any]) -> str:
    return str(record.get("created_at", "") or record.get("session_id", "") or "")


def _as_number_or_blank(value: Any) -> Any:
    try:
        if value is None or value == "":
            return ""
        return float(value)
    except Exception:
        return ""


def _phase_recorded(record: Optional[Dict[str, Any]]) -> str:
    return _yes_no(isinstance(record, dict) and bool(record.get("session_id", "")))


def _session_success(record: Optional[Dict[str, Any]]) -> str:
    if not isinstance(record, dict):
        return "否"
    return _yes_no(str(record.get("success", "")) == "是" or str(record.get("end_reason", "")) in ("success", "standard_assessment_completed"))


def build_participant_analysis_records(summary_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build one-row-per-participant records for paired pre/post analysis.

    V1.3.1 supports both clinical and academy phase names while keeping the
    baseline/training/post statistical columns stable.
    """
    groups: Dict[Tuple[str, str, str, str, str, str], Dict[str, Any]] = {}
    phase_counts: Dict[Tuple[str, str, str, str, str, str], Dict[str, int]] = {}
    for record in summary_records:
        if not isinstance(record, dict):
            continue
        system_mode = str(record.get("system_mode", "") or "clinical")
        if system_mode not in PHASE_EXPORT_MAP_BY_MODE:
            system_mode = "clinical"
        participant_id = str(record.get("participant_id", "") or "anonymous")
        collection_mode = str(record.get("collection_mode", "") or "未标记")
        scenario_id = str(record.get("academy_scenario_id", "") or "") if system_mode == "academy" else ""
        organization_type = str(record.get("organization_type", "") or "")
        organization_id = str(record.get("organization_id", "") or "")
        key = (
            organization_type,
            organization_id,
            system_mode,
            scenario_id,
            participant_id,
            collection_mode,
        )
        group = groups.setdefault(
            key,
            {
                "organization_type": organization_type,
                "organization_id": organization_id,
                "system_mode": system_mode,
                "academy_scenario_id": scenario_id,
                "participant_id": participant_id,
                "collection_mode": collection_mode,
                "stages": {},
            },
        )
        counts = phase_counts.setdefault(key, {})
        phase_map = phase_export_map_for_mode(system_mode)
        phase = str(record.get("assessment_phase", "") or "")
        if phase in phase_map:
            counts[phase] = counts.get(phase, 0) + 1
            current = group["stages"].get(phase)
            if current is None or _record_sort_value(record) >= _record_sort_value(current):
                group["stages"][phase] = record

        for field in [
            "organization_type", "organization_id",
            "system_mode", "system_mode_label", "participant_type", "academy_scenario_id", "academy_scenario_name",
            "academy_scenario_category", "academy_course_type", "academy_difficulty", "institution", "school_name", "student_level",
            "student_grade", "student_class", "campus", "campus_code", "department", "department_code",
            "participant_initials", "department_type", "nurse_level", "years_experience", "professional_title",
            "education_level", "prior_anaphylaxis_training", "prior_simulation_experience", "real_case_experience",
            "academy_post_evaluation_completed", "academy_post_evaluation_time", "sus_score", "sus_level",
            "teaching_experience_total", "teaching_experience_mean",
            "collection_mode_code", "collection_note",
        ]:
            if not group.get(field) and record.get(field) not in ("", None):
                group[field] = record.get(field, "")

    rows: List[Dict[str, Any]] = []
    for key, group in sorted(groups.items(), key=lambda item: item[0]):
        system_mode = group.get("system_mode", "clinical") or "clinical"
        phase_map = phase_export_map_for_mode(system_mode)
        stages = group.get("stages", {}) or {}
        counts = phase_counts.get(key, {})
        row: Dict[str, Any] = {
            "organization_type": group.get("organization_type", ""),
            "organization_id": group.get("organization_id", ""),
            "system_mode": system_mode,
            "system_mode_label": group.get("system_mode_label", SYSTEM_MODE_OPTIONS.get(system_mode, {}).get("label", "")),
            "participant_type": group.get("participant_type", ""),
            "academy_scenario_id": group.get("academy_scenario_id", ""),
            "academy_scenario_name": group.get("academy_scenario_name", ""),
            "academy_scenario_category": group.get("academy_scenario_category", ""),
            "academy_course_type": group.get("academy_course_type", ""),
            "academy_difficulty": group.get("academy_difficulty", ""),
            "participant_id": group.get("participant_id", ""),
            "collection_mode": group.get("collection_mode", ""),
            "collection_mode_code": group.get("collection_mode_code", ""),
            "institution": group.get("institution", ""),
            "school_name": group.get("school_name", ""),
            "student_level": group.get("student_level", ""),
            "student_grade": group.get("student_grade", ""),
            "student_class": group.get("student_class", ""),
            "campus": group.get("campus", ""),
            "campus_code": group.get("campus_code", ""),
            "department": group.get("department", ""),
            "department_code": group.get("department_code", ""),
            "participant_initials": group.get("participant_initials", ""),
            "department_type": group.get("department_type", ""),
            "nurse_level": group.get("nurse_level", ""),
            "years_experience": group.get("years_experience", ""),
            "professional_title": group.get("professional_title", ""),
            "education_level": group.get("education_level", ""),
            "prior_anaphylaxis_training": group.get("prior_anaphylaxis_training", ""),
            "prior_simulation_experience": group.get("prior_simulation_experience", ""),
            "real_case_experience": group.get("real_case_experience", ""),
            "academy_post_evaluation_completed": group.get("academy_post_evaluation_completed", ""),
            "academy_post_evaluation_time": group.get("academy_post_evaluation_time", ""),
            "sus_score": group.get("sus_score", ""),
            "sus_level": group.get("sus_level", ""),
            "teaching_experience_total": group.get("teaching_experience_total", ""),
            "teaching_experience_mean": group.get("teaching_experience_mean", ""),
            "collection_note": group.get("collection_note", ""),
        }

        stage_fields = [
            "session_id", "created_at", "score", "score_percent", "end_time_seconds", "end_reason",
            "final_grade", "epi_dose_status", "epi_delay_seconds", "valid_epi_time",
            "fluid_bolus_valid", "steroid_valid", "process_safety_issue_count",
            "critical_missing_count", "manual_rescue_completion", "valid_completed_key_steps",
            "academy_post_evaluation_completed", "academy_post_evaluation_time", "sus_score", "sus_level",
            "teaching_experience_total", "teaching_experience_mean",
        ]
        for phase, prefix in phase_map.items():
            record = stages.get(phase)
            row[f"{prefix}_phase_name"] = phase
            row[f"{prefix}_recorded"] = _phase_recorded(record)
            row[f"{prefix}_success"] = _session_success(record)
            row[f"{prefix}_duplicate_count"] = max(0, counts.get(phase, 0) - 1)
            for field in stage_fields:
                row[f"{prefix}_{field}"] = record.get(field, "") if isinstance(record, dict) else ""

        baseline_score = _as_number_or_blank(row.get("baseline_score"))
        post_score = _as_number_or_blank(row.get("post_score"))
        baseline_epi = _as_number_or_blank(row.get("baseline_valid_epi_time") or row.get("baseline_epi_delay_seconds"))
        post_epi = _as_number_or_blank(row.get("post_valid_epi_time") or row.get("post_epi_delay_seconds"))
        row["score_change_post_minus_baseline"] = round(post_score - baseline_score, 1) if baseline_score != "" and post_score != "" else ""
        row["epi_time_change_baseline_minus_post"] = round(baseline_epi - post_epi, 1) if baseline_epi != "" and post_epi != "" else ""
        row["pre_post_pair_ready"] = _yes_no(row.get("baseline_recorded") == "是" and row.get("post_recorded") == "是")
        row["all_three_stages_recorded"] = _yes_no(
            row.get("baseline_recorded") == "是"
            and row.get("training_recorded") == "是"
            and row.get("post_recorded") == "是"
        )
        row["has_duplicate_stage"] = _yes_no(any(int(row.get(f"{prefix}_duplicate_count", 0) or 0) > 0 for prefix in phase_map.values()))
        row["formal_analysis_ready"] = _yes_no(
            row.get("collection_mode") == "正式采集"
            and row.get("all_three_stages_recorded") == "是"
            and row.get("has_duplicate_stage") != "是"
        )
        rows.append(row)
    return rows


def build_data_quality_records(summary_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    participant_rows = build_participant_analysis_records(summary_records)
    issues: List[Dict[str, Any]] = []
    for row in participant_rows:
        system_mode = str(row.get("system_mode", "clinical") or "clinical")
        phase_map = phase_export_map_for_mode(system_mode)
        participant_id = row.get("participant_id", "")
        collection_mode = row.get("collection_mode", "")
        for phase, prefix in phase_map.items():
            if row.get(f"{prefix}_recorded") != "是":
                issues.append({
                    "organization_type": row.get("organization_type", ""),
                    "organization_id": row.get("organization_id", ""),
                    "system_mode": system_mode,
                    "academy_scenario_id": row.get("academy_scenario_id", ""),
                    "academy_scenario_name": row.get("academy_scenario_name", ""),
                    "participant_id": participant_id,
                    "collection_mode": collection_mode,
                    "assessment_phase": phase,
                    "quality_issue": "缺少该阶段记录",
                    "suggested_action": "确认受试者是否尚未完成该阶段，或是否误选了采集模式/参与者编号。",
                })
            duplicate_count = int(row.get(f"{prefix}_duplicate_count", 0) or 0)
            if duplicate_count > 0:
                issues.append({
                    "organization_type": row.get("organization_type", ""),
                    "organization_id": row.get("organization_id", ""),
                    "system_mode": system_mode,
                    "academy_scenario_id": row.get("academy_scenario_id", ""),
                    "academy_scenario_name": row.get("academy_scenario_name", ""),
                    "participant_id": participant_id,
                    "collection_mode": collection_mode,
                    "assessment_phase": phase,
                    "quality_issue": f"该阶段存在 {duplicate_count} 条重复记录",
                    "suggested_action": "管理员导出原始记录后确认哪一次为正式纳入记录。",
                })
            end_time = _as_number_or_blank(row.get(f"{prefix}_end_time_seconds"))
            if end_time != "" and end_time < 60:
                issues.append({
                    "organization_type": row.get("organization_type", ""),
                    "organization_id": row.get("organization_id", ""),
                    "system_mode": system_mode,
                    "academy_scenario_id": row.get("academy_scenario_id", ""),
                    "academy_scenario_name": row.get("academy_scenario_name", ""),
                    "participant_id": participant_id,
                    "collection_mode": collection_mode,
                    "assessment_phase": phase,
                    "quality_issue": "结束时间短于60秒",
                    "suggested_action": "核查是否为测试、误触主动完成或现场中断。",
                })
            if str(row.get(f"{prefix}_manual_rescue_completion", "")).lower() in ("true", "是", "1"):
                issues.append({
                    "organization_type": row.get("organization_type", ""),
                    "organization_id": row.get("organization_id", ""),
                    "system_mode": system_mode,
                    "academy_scenario_id": row.get("academy_scenario_id", ""),
                    "academy_scenario_name": row.get("academy_scenario_name", ""),
                    "participant_id": participant_id,
                    "collection_mode": collection_mode,
                    "assessment_phase": phase,
                    "quality_issue": "使用了主动确认完成",
                    "suggested_action": "纳入分析前确认该结束方式符合研究方案。",
                })
        if row.get("collection_note"):
            issues.append({
                "organization_type": row.get("organization_type", ""),
                "organization_id": row.get("organization_id", ""),
                "system_mode": system_mode,
                "participant_id": participant_id,
                "collection_mode": collection_mode,
                "assessment_phase": "",
                "quality_issue": "存在现场备注/异常记录",
                "suggested_action": str(row.get("collection_note", "")),
            })
    return issues


def display_action_label(action: Dict[str, Any], sim: Optional[Simulator] = None) -> str:
    aid = str(action.get("id", ""))
    if sim is not None and current_flow_strategy(sim).system_mode == "academy":
        return academy_action_short_label(action)
    return str(action.get("label", aid))


def action_label_map(sim: Simulator) -> Dict[str, str]:
    return {str(a.get("id", "")): display_action_label(a, sim) for a in sim.actions}


def get_action_history_rows(sim: Simulator) -> List[Dict[str, Any]]:
    labels = action_label_map(sim)
    show_results = current_flow_strategy(sim).show_immediate_feedback
    rows: List[Dict[str, Any]] = []
    for entry in sim.log:
        if entry.kind != "action":
            continue
        if entry.message == "penalty":
            continue
        data = entry.data or {}
        msg = entry.message
        result = ""
        display = data.get("label") or labels.get(msg, msg)
        if msg == "im_epinephrine_dose_verified":
            display = "肌注肾上腺素剂量确认"
            result = f"有效剂量 {data.get('dose_mg', '')} mg"
        elif msg == "im_epinephrine_underdose":
            display = "肌注肾上腺素剂量不足"
            result = f"无效：{data.get('dose_mg', '')} mg，目标 {data.get('target_dose_mg', '')} mg"
        elif msg == "im_epinephrine_dose_high":
            display = "肌注肾上腺素剂量偏高"
            result = f"偏高：{data.get('dose_mg', '')} mg，目标 {data.get('target_dose_mg', '')} mg"
        elif msg == "im_epinephrine_overdose":
            display = "肌注肾上腺素过量"
            result = f"过量：{data.get('dose_mg', '')} mg"
        elif msg in ["fluid_bolus_volume_verified", "fluid_bolus_under", "fluid_bolus_over", "fluid_bolus_invalid_no_iv"]:
            display = ACTION_LABELS_CN.get(msg, msg)
            result = f"{data.get('result', '')}｜{data.get('volume_ml', '')} ml"
        elif data.get("result"):
            result = str(data.get("result", ""))
        elif data.get("gained") is not None:
            result = f"得分 +{data.get('gained')}"
        rows.append(
            {
                "时间": format_elapsed_time(entry.t),
                "操作": str(display),
                "结果": str(result) if show_results else "",
            }
        )
    return rows


def start_simulation(scenario_path: Path, mode: str, seed: int, participant_id: str) -> None:
    clear_training_draft()
    st.session_state.organization_type = current_system_mode()
    if not _valid_organization_id(st.session_state.get("organization_id", "")):
        st.session_state.organization_id = ""
    definition = scenario_definition_for_path(scenario_path)
    scenario_source = (
        load_registered_scenario(definition.scenario_id)
        if definition is not None
        else load_scenario(str(scenario_path))
    )
    scenario = randomize_patient_profile(scenario_source)
    sim = Simulator(scenario, mode=mode, seed=seed)
    strategy = current_flow_strategy(sim)
    meta = scenario.get("scenario", {})
    mode_name = (
        "training"
        if strategy.score_presentation == "live"
        else "exam"
    )
    script_name = safe_filename_part(meta.get("script_name") or scenario_path.stem)
    participant = safe_filename_part(participant_id or "anonymous")
    st.session_state.active_simulator = sim
    st.session_state.flow_strategy_id = strategy.strategy_id
    st.session_state.active_scenario = scenario
    st.session_state.active_scenario_path = str(scenario_path)
    st.session_state.active_script_name = script_name
    st.session_state.session_id = f"{mode_name}_{script_name}_{participant}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    st.session_state.completion_id = token_secrets.token_hex(32)
    st.session_state.questionnaire_submission_id = ""
    st.session_state.questionnaire_draft = {}
    st.session_state.questionnaire_submit_status = ""
    st.session_state.questionnaire_submit_error = ""
    st.session_state.ended = False
    st.session_state.end_reason = ""
    st.session_state.academy_flow_page = ""
    st.session_state.last_report = None
    st.session_state.last_report_paths = None
    st.session_state.last_ui_snapshot = None
    st.session_state.pending_dose_action_id = ""
    st.session_state.pending_dose_action_label = ""
    st.session_state.pending_volume_action_id = ""
    st.session_state.pending_volume_action_label = ""
    st.session_state.pending_steroid_action_id = ""
    st.session_state.pending_steroid_action_label = ""
    st.session_state.last_dose_feedback = ""
    st.session_state.last_dose_feedback_level = ""
    st.session_state.manual_completion_confirmation = False
    st.session_state.restart_stage_confirmation = False
    st.session_state.processed_ui_events = []
    # 清空本阶段现场备注，避免备注串到下一阶段或下一位受试者。
    st.session_state.collection_note = ""
    st.session_state.result_saved = False
    st.session_state.pending_prior_experience_survey = False
    st.session_state.pending_completion_reason = ""
    st.session_state.pending_report = None
    st.session_state.pending_academy_post_evaluation = False
    st.session_state.pending_post_evaluation_report = None
    st.session_state.pending_post_evaluation_reason = ""
    if (
        strategy.questionnaire_transition_for_phase(
            st.session_state.get("assessment_phase", "")
        )
        == "academy_post_evaluation"
    ):
        st.session_state.academy_post_evaluation_completed = False
        st.session_state.academy_post_evaluation_time = ""
        st.session_state.sus_score = ""
        st.session_state.sus_level = ""
        st.session_state.teaching_experience_total = ""
        st.session_state.teaching_experience_mean = ""
    st.session_state.baseline_performance_completed = False
    if st.session_state.get("assessment_phase") not in ("基线评估", "课前测评"):
        st.session_state.baseline_stage_completed = False
    if current_system_mode() == "academy":
        stage_sessions = dict(
            st.session_state.get("academy_stage_session_ids", {}) or {}
        )
        stage_sessions[str(st.session_state.get("assessment_phase", "") or "")] = (
            st.session_state.session_id
        )
        st.session_state.academy_stage_session_ids = stage_sessions
    persist_active_training_draft()


def _return_to_registration_after_save(report: Dict[str, Any], why: str) -> None:
    """After a stage is saved, return directly to the registration page for the next stage."""
    clear_training_draft()
    phase = st.session_state.get("assessment_phase", "本阶段") or "本阶段"
    participant_id = st.session_state.get("participant_id", "") or ""
    score = report.get("score", "") if isinstance(report, dict) else ""
    max_score = report.get("max_score", "") if isinstance(report, dict) else ""
    score_text = f"，得分 {score}/{max_score}" if score != "" and max_score != "" else ""
    st.session_state.last_completion_notice = f"{phase}已完成并保存{score_text}。请在登记界面核对信息后，选择下一阶段或下一位受试者。"

    st.session_state.profile_completed = False
    st.session_state.active_simulator = None
    st.session_state.active_scenario = None
    st.session_state.active_scenario_path = ""
    st.session_state.active_script_name = ""
    st.session_state.ended = False
    st.session_state.end_reason = ""
    st.session_state.last_ui_snapshot = None
    st.session_state.pending_dose_action_id = ""
    st.session_state.pending_dose_action_label = ""
    st.session_state.pending_volume_action_id = ""
    st.session_state.pending_volume_action_label = ""
    st.session_state.pending_steroid_action_id = ""
    st.session_state.pending_steroid_action_label = ""
    st.session_state.last_dose_feedback = ""
    st.session_state.last_dose_feedback_level = ""
    st.session_state.result_saved = False
    st.session_state.questionnaire_submission_id = ""
    st.session_state.questionnaire_draft = {}
    st.session_state.questionnaire_submit_status = ""
    st.session_state.questionnaire_submit_error = ""


def _enter_completed_clinical_result(report: Dict[str, Any], why: str) -> None:
    """Keep a saved clinical result visible and refresh-restorable."""
    st.session_state.last_report = report
    st.session_state.ended = True
    st.session_state.end_reason = why
    st.session_state.pending_prior_experience_survey = False
    st.session_state.pending_completion_reason = ""
    st.session_state.pending_report = None
    st.session_state.pending_academy_post_evaluation = False
    st.session_state.pending_post_evaluation_report = None
    st.session_state.pending_post_evaluation_reason = ""
    if current_flow_strategy().recovery.preserve_completed_result:
        persist_active_training_draft()


def continue_after_clinical_result(report: Dict[str, Any], why: str) -> bool:
    """Advance only after an explicit click; retain the result if transition fails."""
    simulator = st.session_state.get("active_simulator")
    scenario = st.session_state.get("active_scenario")
    scenario_path = st.session_state.get("active_scenario_path", "")
    script_name = st.session_state.get("active_script_name", "")
    try:
        _return_to_registration_after_save(report, why)
        return True
    except Exception:
        st.session_state.profile_completed = True
        st.session_state.active_simulator = simulator
        st.session_state.active_scenario = scenario
        st.session_state.active_scenario_path = scenario_path
        st.session_state.active_script_name = script_name
        st.session_state.result_saved = True
        _enter_completed_clinical_result(report, why)
        return False


def restart_completed_clinical_stage() -> bool:
    scenario_path = Path(str(st.session_state.get("active_scenario_path", "") or ""))
    simulator = st.session_state.get("active_simulator")
    if not scenario_path.is_file() or not isinstance(simulator, Simulator):
        return False
    return restart_current_stage(scenario_path, simulator.mode)


def return_home_after_clinical_result() -> None:
    clear_training_draft()
    st.session_state.system_mode_selected = False
    st.session_state.academy_scenario_selected = False
    st.session_state.profile_completed = False
    st.session_state.active_simulator = None
    st.session_state.active_scenario = None
    st.session_state.active_scenario_path = ""
    st.session_state.active_script_name = ""
    st.session_state.ended = False
    st.session_state.end_reason = ""
    st.session_state.last_report = None
    st.session_state.last_report_paths = None
    st.session_state.result_saved = False
    st.session_state.last_completion_notice = ""
    st.session_state.completion_id = ""
    st.session_state.questionnaire_submission_id = ""
    st.session_state.questionnaire_draft = {}
    st.session_state.questionnaire_submit_status = ""
    st.session_state.questionnaire_submit_error = ""


ACADEMY_POST_TEST_REQUIRED_TIMELINE_KEYS = [
    "allergy_identification",
    "stop_infusion",
    "call_help",
    "prepare_rescue_equipment",
    "academy_reassess",
    "academy_family_communication",
    "academy_sbar_handoff",
]


def _academy_post_test_fully_completed(report: Optional[Dict[str, Any]], why: str) -> bool:
    """Only unlock SUS/teaching-experience after the academy post-test is truly complete.

    V1.3.5 issue: academy post-test terminal failure could be triggered by early deterioration,
    then _save_and_end_report opened SUS immediately. V1.3.6 gates the post-test evaluation
    behind a real completed pathway, so a learner cannot jump to SUS after only recognition,
    circulation assessment, or another early action.
    """
    strategy = flow_strategy_for_phase(
        current_system_mode(),
        st.session_state.get("assessment_phase", ""),
    )
    if (
        strategy.questionnaire_transition_for_phase(
            st.session_state.get("assessment_phase", "")
        )
        != "academy_post_evaluation"
    ):
        return False
    if st.session_state.get("academy_post_evaluation_completed", False):
        return False
    if why != "success":
        return False
    if not isinstance(report, dict):
        return False
    timeline = report.get("key_timeline", {}) or {}
    return all(timeline.get(key) is not None for key in ACADEMY_POST_TEST_REQUIRED_TIMELINE_KEYS)


def _needs_academy_post_evaluation(report: Optional[Dict[str, Any]] = None, why: str = "") -> bool:
    return _academy_post_test_fully_completed(report, why)


def _sus_level(score: float) -> str:
    if score < 50:
        return "可用性较差"
    if score < 68:
        return "可用性一般"
    if score < 80:
        return "可接受"
    return "可用性较好"


def compute_sus_score(values: List[int]) -> float:
    total = 0
    for idx, val in enumerate(values, start=1):
        v = int(val)
        if idx % 2 == 1:
            total += v - 1
        else:
            total += 5 - v
    return round(total * 2.5, 1)


def _normalized_questionnaire_values(value: object, count: int) -> List[int]:
    source = value if isinstance(value, list) else []
    values: List[int] = []
    for index in range(count):
        try:
            candidate = int(source[index])
        except (IndexError, TypeError, ValueError):
            candidate = 3
        values.append(candidate if candidate in (1, 2, 3, 4, 5) else 3)
    return values


def _questionnaire_draft_values() -> Tuple[List[int], List[int]]:
    draft = st.session_state.get("questionnaire_draft", {})
    if not isinstance(draft, dict):
        draft = {}
    return (
        _normalized_questionnaire_values(draft.get("sus"), len(SUS_ITEMS)),
        _normalized_questionnaire_values(draft.get("teaching"), len(TEACHING_EXPERIENCE_ITEMS)),
    )


def _academy_evaluation_payload(
    sus_values: List[int],
    teaching_values: List[int],
    completed_time: str,
) -> Dict[str, Any]:
    sus_score = compute_sus_score(sus_values)
    teaching_total = int(sum(teaching_values))
    teaching_mean = round(teaching_total / len(teaching_values), 2) if teaching_values else ""
    return {
        "completed": True,
        "completed_time": completed_time,
        "sus": {
            "items": {f"SUS{idx}": int(val) for idx, val in enumerate(sus_values, start=1)},
            "score": sus_score,
            "level": _sus_level(float(sus_score)),
        },
        "teaching_experience": {
            "items": {f"T{idx}": int(val) for idx, val in enumerate(teaching_values, start=1)},
            "total": teaching_total,
            "mean": teaching_mean,
        },
    }


def submit_academy_post_evaluation(
    sus_values: List[int],
    teaching_values: List[int],
) -> Tuple[bool, str]:
    if (
        st.session_state.get("questionnaire_submit_status") == "completed"
        or st.session_state.get("academy_post_evaluation_completed", False)
    ):
        return True, "课后评价已完成并保存，请勿重复提交。"
    normalized_sus = _normalized_questionnaire_values(sus_values, len(SUS_ITEMS))
    normalized_teaching = _normalized_questionnaire_values(
        teaching_values,
        len(TEACHING_EXPERIENCE_ITEMS),
    )
    st.session_state.questionnaire_draft = {
        "sus": normalized_sus,
        "teaching": normalized_teaching,
    }
    report = st.session_state.get("pending_post_evaluation_report")
    why = (
        st.session_state.get("pending_post_evaluation_reason", "standard_assessment_completed")
        or "standard_assessment_completed"
    )
    if not isinstance(report, dict):
        st.session_state.questionnaire_submit_status = "failed"
        st.session_state.questionnaire_submit_error = "未找到待保存的课后考核报告。"
        persist_active_training_draft()
        return False, st.session_state.questionnaire_submit_error

    report = json.loads(json.dumps(report, ensure_ascii=False, default=str))
    completion_id = ensure_report_completion_id(report)
    submission_id = ensure_questionnaire_submission_id()
    completed_time = datetime.now().isoformat(timespec="seconds")
    evaluation = _academy_evaluation_payload(normalized_sus, normalized_teaching, completed_time)
    session = report.setdefault("session", {})
    if not isinstance(session, dict):
        session = {}
        report["session"] = session
    session.update(
        {
            "completion_id": completion_id,
            "academy_post_evaluation_completed": True,
            "academy_post_evaluation_time": completed_time,
            "sus_score": evaluation["sus"]["score"],
            "sus_level": evaluation["sus"]["level"],
            "teaching_experience_total": evaluation["teaching_experience"]["total"],
            "teaching_experience_mean": evaluation["teaching_experience"]["mean"],
        }
    )
    report["end_reason"] = why
    report["academy_post_evaluation"] = evaluation
    questionnaire_record = {
        "schema_version": 1,
        "record_type": "academy_post_evaluation",
        "questionnaire_submission_id": submission_id,
        "completion_id": completion_id,
        "session_id": session.get("session_id", st.session_state.get("session_id", "")),
        "system_mode": session.get("system_mode", current_system_mode()),
        "organization_type": session.get("organization_type", current_system_mode()),
        "organization_id": session.get("organization_id", ""),
        "assessment_phase": session.get(
            "assessment_phase",
            st.session_state.get("assessment_phase", ""),
        ),
        "submitted_at": completed_time,
        "academy_post_evaluation": evaluation,
    }
    st.session_state.questionnaire_submit_status = "saving"
    st.session_state.questionnaire_submit_error = ""
    persist_active_training_draft()
    try:
        persisted_record = save_questionnaire_record_local(questionnaire_record)
        persisted_evaluation = persisted_record.get("academy_post_evaluation", {})
        if not isinstance(persisted_evaluation, dict):
            raise ValueError("Persisted questionnaire record is incomplete.")
        evaluation = persisted_evaluation
        completed_time = str(evaluation.get("completed_time", completed_time))
        st.session_state.questionnaire_submission_id = str(
            persisted_record.get("questionnaire_submission_id", submission_id)
        )
        report["academy_post_evaluation"] = evaluation
        session.update(
            {
                "academy_post_evaluation_completed": True,
                "academy_post_evaluation_time": completed_time,
                "sus_score": (evaluation.get("sus", {}) or {}).get("score", ""),
                "sus_level": (evaluation.get("sus", {}) or {}).get("level", ""),
                "teaching_experience_total": (
                    evaluation.get("teaching_experience", {}) or {}
                ).get("total", ""),
                "teaching_experience_mean": (
                    evaluation.get("teaching_experience", {}) or {}
                ).get("mean", ""),
            }
        )
    except Exception as exc:
        st.session_state.academy_post_evaluation_completed = False
        st.session_state.questionnaire_submit_status = "failed"
        st.session_state.questionnaire_submit_error = (
            f"问卷尚未提交成功（{type(exc).__name__}）。请稍后安全重试。"
        )
        st.session_state.pending_academy_post_evaluation = True
        st.session_state.pending_post_evaluation_report = report
        st.session_state.pending_post_evaluation_reason = why
        persist_active_training_draft()
        return False, st.session_state.questionnaire_submit_error

    st.session_state.academy_post_evaluation_completed = True
    st.session_state.academy_post_evaluation_time = completed_time
    st.session_state.sus_score = evaluation["sus"]["score"]
    st.session_state.sus_level = evaluation["sus"]["level"]
    st.session_state.teaching_experience_total = evaluation["teaching_experience"]["total"]
    st.session_state.teaching_experience_mean = evaluation["teaching_experience"]["mean"]
    st.session_state.questionnaire_submit_status = "completed"
    st.session_state.questionnaire_submit_error = ""
    st.session_state.last_report = report
    st.session_state.pending_academy_post_evaluation = False
    st.session_state.pending_post_evaluation_report = None
    st.session_state.pending_post_evaluation_reason = ""
    stage_reports = dict(st.session_state.get("academy_stage_reports", {}) or {})
    stage_reports["posttest"] = report
    st.session_state.academy_stage_reports = stage_reports
    st.session_state.academy_flow_page = "flow_complete"
    st.session_state.ended = True
    persist_active_training_draft()
    return True, "课后评价已完成并保存。"


def render_academy_post_evaluation_survey() -> None:
    st.markdown("### 课后评价｜系统可用性与教学体验")
    st.caption("请在完成课后考核后填写。SUS用于评价系统可用性，教学体验问卷用于评价学习感受；二者不会计入抢救能力分数。")
    if st.session_state.get("questionnaire_submit_status") == "failed":
        st.warning("训练结果已保存，问卷尚未提交成功。已保留本次答案草稿，请检查后安全重试。")
        if st.session_state.get("questionnaire_submit_error"):
            st.caption(str(st.session_state.questionnaire_submit_error))
    else:
        st.success("训练结果已保存。问卷尚未提交，刷新或稍后返回不会丢失训练结果。")
    draft_sus, draft_teaching = _questionnaire_draft_values()
    with st.form("academy_post_evaluation_form", clear_on_submit=False):
        st.markdown("#### SUS系统可用性问卷")
        st.caption("1=非常不同意，5=非常同意。")
        sus_values = []
        for idx, item in enumerate(SUS_ITEMS, start=1):
            sus_values.append(
                st.radio(
                    f"SUS{idx}. {item}",
                    [1, 2, 3, 4, 5],
                    index=draft_sus[idx - 1] - 1,
                    horizontal=True,
                    key=f"sus_{idx}_{st.session_state.session_id}",
                )
            )
        st.markdown("#### 虚拟仿真教学体验问卷")
        teaching_values = []
        for idx, item in enumerate(TEACHING_EXPERIENCE_ITEMS, start=1):
            teaching_values.append(
                st.radio(
                    f"T{idx}. {item}",
                    [1, 2, 3, 4, 5],
                    index=draft_teaching[idx - 1] - 1,
                    horizontal=True,
                    key=f"teach_{idx}_{st.session_state.session_id}",
                )
            )
        submitted = st.form_submit_button(
            questionnaire_submit_button_label(
                st.session_state.get("questionnaire_submit_status", "")
            ),
            type="primary",
            use_container_width=True,
        )
    if submitted:
        ok, message = submit_academy_post_evaluation(
            [int(value) for value in sus_values],
            [int(value) for value in teaching_values],
        )
        if ok:
            st.success(message)
            st.rerun()
        else:
            st.error(message)


def _save_and_end_report(report: Dict[str, Any], why: str) -> None:
    strategy = current_flow_strategy()
    ensure_report_completion_id(report)
    if (
        strategy.result_page_behavior == "persistent_clinical_result"
        and st.session_state.get("result_saved", False)
        and isinstance(st.session_state.get("last_report"), dict)
    ):
        _enter_completed_clinical_result(
            st.session_state.last_report,
            str(st.session_state.get("end_reason", "") or why),
        )
        return
    out_dir = current_storage_adapter().write_paths().report_runs / st.session_state.session_id
    if not st.session_state.get("result_saved", False):
        json_path, md_path = save_report(report, str(out_dir))
        save_result_record(report)
        st.session_state.last_report_paths = (json_path, md_path)
    st.session_state.result_saved = True
    st.session_state.last_report = report
    if current_system_mode() == "academy":
        phase = str(st.session_state.get("assessment_phase", "") or "")
        page = completion_page_for_phase(phase)
        report_key = stage_report_key(phase)
        stage_reports = dict(st.session_state.get("academy_stage_reports", {}) or {})
        if report_key and report_key not in stage_reports:
            stage_reports[report_key] = json.loads(
                json.dumps(report, ensure_ascii=False, default=str)
            )
        st.session_state.academy_stage_reports = stage_reports
        st.session_state.academy_flow_page = page
        st.session_state.ended = True
        st.session_state.end_reason = why
        st.session_state.pending_academy_post_evaluation = False
        if phase == "课后考核" and _needs_academy_post_evaluation(report, why):
            st.session_state.pending_academy_post_evaluation = True
            st.session_state.pending_post_evaluation_report = report
            st.session_state.pending_post_evaluation_reason = why
            ensure_questionnaire_submission_id()
            if st.session_state.get("questionnaire_submit_status") != "failed":
                st.session_state.questionnaire_submit_status = "pending"
                st.session_state.questionnaire_submit_error = ""
        persist_active_training_draft()
        return
    if strategy.result_page_behavior == "persistent_clinical_result":
        _enter_completed_clinical_result(report, why)
    else:
        _return_to_registration_after_save(report, why)


def _needs_baseline_post_survey(why: str = "") -> bool:
    """Prior-experience survey is required after any pretest/baseline ending.

    The performance record is locked first, then prior training/simulation/real-case exposure
    items are collected. This avoids prompt leakage before the first independent attempt.
    """
    phase = st.session_state.get("assessment_phase", "")
    strategy = flow_strategy_for_phase(
        current_system_mode(),
        phase,
    )
    return bool(
        current_system_mode() == "clinical"
        and
        strategy.questionnaire_transition_for_phase(phase)
        == "prior_experience_survey"
        and not st.session_state.get(
            "prior_experience_survey_completed",
            False,
        )
    )


def finalize_if_done() -> None:
    sim = st.session_state.active_simulator
    if sim is None or st.session_state.ended or st.session_state.get("pending_prior_experience_survey", False):
        return
    done, why = sim.is_done()
    if done:
        if (
            current_system_mode() == "academy"
            and not should_auto_finalize_academy_phase(
                st.session_state.get("assessment_phase", ""),
                sim.mode,
                why,
            )
        ):
            return
        report = enrich_report(sim.build_report(), end_reason=why)
        if _needs_baseline_post_survey(why):
            st.session_state.baseline_performance_completed = True
            st.session_state.pending_prior_experience_survey = True
            st.session_state.pending_completion_reason = why
            st.session_state.pending_report = report
            st.session_state.last_report = report
            return
        if st.session_state.get("assessment_phase") == "基线评估":
            st.session_state.baseline_stage_completed = True
        _save_and_end_report(report, why)


def profile_required_missing() -> List[str]:
    if current_system_mode() == "academy":
        required = {
            "academy_scenario_id": "学院教学情景",
            "school_name": "院校名称",
            "student_level": "培养层次",
            "student_grade": "年级/阶段",
            "participant_initials": "姓名首字母",
            "participant_id": "系统生成参与者编号",
            "assessment_phase": "评估阶段",
            "collection_mode": "采集模式",
        }
        if configured_organizations("academy"):
            required["organization_id"] = "授权学院"
    else:
        required = {
            "institution": "医院全称",
            "campus": "院区/中心",
            "department": "科室细分",
            "participant_initials": "姓名首字母",
            "participant_id": "系统生成参与者编号",
            "nurse_level": "护理层级",
            "years_experience": "工作年限",
            "years_experience_confirmed": "工作年限核对",
            "assessment_phase": "评估阶段",
            "collection_mode": "采集模式",
        }
        if configured_organizations("clinical"):
            required["organization_id"] = "授权临床机构"
    missing = []
    for key, label in required.items():
        value = st.session_state.get(key, "")
        if key == "years_experience_confirmed":
            if not bool(value):
                missing.append(label)
            continue
        if value is None or str(value).strip() == "":
            missing.append(label)
    return missing


def render_version_corner() -> None:
    if is_competition_mode():
        st.markdown(
            "<div class='version-corner'>比赛评审演示环境</div>",
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f"<div class='version-corner'>版本：{html.escape(APP_VERSION)}｜仅用于护理教学、培训与科研</div>",
        unsafe_allow_html=True,
    )


def render_participant_entry_page() -> None:
    """Centered, wide registration page before entering the simulator."""
    render_version_corner()
    mode = current_system_mode()
    mode_label = current_system_mode_label()
    st.markdown(
        f"""
        <div class='login-hero'>
            <div class='login-title'>{html.escape(APP_TITLE)}</div>
            <div class='login-subtitle'>{html.escape(mode_label)}｜动态分支 · 虚拟仿真 · 教学/培训评价</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    outer_left, center, outer_right = st.columns([0.08, 0.84, 0.08])
    with center:
        if st.session_state.get("last_completion_notice"):
            st.success(st.session_state.get("last_completion_notice"))
            st.session_state.last_completion_notice = ""

        if mode == "academy":
            scenario = current_academy_scenario()
            st.markdown(
                "<div class='login-card-title'>在校护生信息登记</div>"
                f"<div class='login-card-desc'>学院模式面向高职/大专、本科及其他在校护生；当前已选择情景：{html.escape(scenario.get('name', ''))}。系统将自动生成匿名参与者编号，并写入训练报告和导出数据。</div>",
                unsafe_allow_html=True,
            )
            st.container(border=True).markdown(
                f"""
                **已选教学情景：** {scenario.get('name', '')}  
                **情景类别：** {scenario.get('category', '')}｜**适用课程：** {scenario.get('course_type', '')}｜**难度：** {scenario.get('difficulty', '')}  
                {scenario.get('description', '')}
                """
            )
            academy_organizations = configured_organizations("academy")
            academy_by_id = {
                item["organization_id"]: item
                for item in academy_organizations
            }
            with st.form("academy_participant_profile_form", clear_on_submit=False):
                st.markdown("##### 院校与护生信息")
                a1, a2, a3 = st.columns([1.3, 1, 1], gap="large")
                if academy_organizations:
                    academy_ids = [""] + list(academy_by_id)
                    current_id = str(st.session_state.get("organization_id", "") or "")
                    selected_organization_id = a1.selectbox(
                        "授权学院（必填）",
                        academy_ids,
                        index=academy_ids.index(current_id) if current_id in academy_ids else 0,
                        format_func=lambda value: (
                            organization_display_label(academy_by_id[value])
                            if value in academy_by_id
                            else "请选择已登记学院"
                        ),
                    )
                    selected_organization = academy_by_id.get(
                        selected_organization_id,
                        {},
                    )
                    school_name = str(selected_organization.get("school_name", "") or "")
                else:
                    selected_organization_id = ""
                    school_name = a1.text_input(
                        "院校名称（必填）",
                        value=st.session_state.school_name,
                        placeholder="例如 ××职业学院 / ××大学护理学院",
                    )
                level_options = ["", "高职/大专", "本科", "专升本", "硕士及以上", "其他"]
                student_level = a2.selectbox(
                    "培养层次（必填）",
                    level_options,
                    index=level_options.index(st.session_state.student_level) if st.session_state.student_level in level_options else 0,
                )
                grade_options = ACADEMY_GRADE_OPTIONS
                student_grade = a3.selectbox(
                    "年级/阶段（必填）",
                    grade_options,
                    index=grade_options.index(st.session_state.student_grade) if st.session_state.student_grade in grade_options else 0,
                )

                b1, b2, b3 = st.columns([1, 1, 1], gap="large")
                student_class = b1.text_input(
                    "班级/小组（选填）",
                    value=st.session_state.student_class,
                    placeholder="例如 2026级护理1班 / A组",
                )
                participant_initials = b2.text_input(
                    "姓名首字母（必填）",
                    value=st.session_state.participant_initials,
                    placeholder=(
                        "示例学员"
                        if is_competition_mode()
                        else "例如 王思席填 WSX"
                    ),
                    max_chars=8,
                )
                collection_mode = b3.selectbox(
                    "采集模式（必填）",
                    COLLECTION_MODE_OPTIONS,
                    index=COLLECTION_MODE_OPTIONS.index(st.session_state.collection_mode)
                    if st.session_state.collection_mode in COLLECTION_MODE_OPTIONS else 0,
                )

                preview_id = build_academy_participant_id(student_level, participant_initials)
                id_col, note_col = st.columns([1.1, 1], gap="large")
                id_col.text_input(
                    "系统生成参与者编号（自动生成，不需手动填写）",
                    value=preview_id,
                    disabled=True,
                )
                note_col.markdown(
                    f"""
                    <div class='id-help-box'>
                        编码规则：ACAD + 培养层次代码 + 姓名首字母 + 防重复后缀<br>
                        当前模式：{html.escape(mode_label)} / {html.escape(scenario.get('name', ''))}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                phase_options = phase_options_for_mode("academy")
                c1, c2 = st.columns([1, 1], gap="large")
                assessment_phase = c1.selectbox(
                    "评估阶段（必填）",
                    phase_options,
                    index=phase_options.index(st.session_state.assessment_phase) if st.session_state.assessment_phase in phase_options else 0,
                )
                workflow_preview = workflow_for_phase(assessment_phase, "academy")
                c2.markdown(
                    f"<div class='form-note'>阶段确认：{html.escape(workflow_preview.get('display', ''))}。采集模式：{html.escape(collection_mode)}。</div>",
                    unsafe_allow_html=True,
                )
                collection_note = st.text_area(
                    "现场备注/异常记录（选填）",
                    value=st.session_state.get("collection_note", ""),
                    placeholder="如教师干预、中途断网、误点后重做等；无异常可留空。",
                    height=80,
                )
                st.markdown(
                    f"<div class='form-note'>说明：当前情景为{html.escape(scenario.get('name', ''))}。学院模式不要求护生独立完成完整临床抢救，重点记录早期识别、停止可疑药物、呼救协作、给氧监测、抢救配合、基础复评、沟通与汇报能力。</div>",
                    unsafe_allow_html=True,
                )
                submitted = st.form_submit_button("保存信息并进入学院模式", type="primary", use_container_width=True)

            if submitted:
                initials_clean = normalize_initials(participant_initials)
                generated_id = build_academy_participant_id(student_level, initials_clean)
                old_participant_id = st.session_state.get("participant_id", "")
                participant_changed = bool(old_participant_id and generated_id and generated_id != old_participant_id)
                if participant_changed:
                    st.session_state.prior_anaphylaxis_training = ""
                    st.session_state.prior_simulation_experience = ""
                    st.session_state.real_case_experience = ""
                    st.session_state.prior_experience_survey_completed = False
                    st.session_state.prior_experience_survey_time = ""
                    st.session_state.baseline_performance_completed = False
                    st.session_state.baseline_stage_completed = False

                st.session_state.participant_initials = initials_clean
                st.session_state.participant_id = generated_id
                st.session_state.participant_type = "nursing_student"
                st.session_state.academy_scenario_id = scenario.get("id", current_academy_scenario_id())
                st.session_state.academy_scenario_name = scenario.get("name", "")
                st.session_state.academy_scenario_category = scenario.get("category", "")
                st.session_state.academy_course_type = scenario.get("course_type", "")
                st.session_state.academy_difficulty = scenario.get("difficulty", "")
                st.session_state.organization_type = "academy"
                st.session_state.organization_id = selected_organization_id
                st.session_state.school_name = school_name.strip()
                st.session_state.student_level = student_level.strip()
                st.session_state.student_grade = student_grade.strip()
                st.session_state.student_class = student_class.strip()
                st.session_state.institution = school_name.strip()
                st.session_state.campus = ""
                st.session_state.campus_code = "ACAD"
                st.session_state.department = "学院教学"
                st.session_state.department_code = "ACAD"
                st.session_state.department_type = "护生教学"
                st.session_state.nurse_level = f"护生-{student_level.strip()}" if student_level.strip() else ""
                st.session_state.years_experience = 0.0
                st.session_state.years_experience_confirmed = True
                st.session_state.professional_title = ""
                st.session_state.education_level = student_level.strip()
                st.session_state.collection_mode = collection_mode.strip()
                st.session_state.collection_note = collection_note.strip()
                st.session_state.training_batch = student_class.strip()
                st.session_state.assessment_phase = assessment_phase.strip()
                workflow = workflow_for_phase(st.session_state.assessment_phase, "academy")
                st.session_state.workflow_mode = workflow.get("mode", "exam")
                st.session_state.workflow_script_role = workflow.get("script_role", "academy_initial")
                st.session_state.workflow_display = workflow.get("display", "")
                st.session_state.workflow_locked = True
                st.session_state.mode = st.session_state.workflow_mode
                st.session_state.attempt_no = 1

                missing = profile_required_missing()
                if missing:
                    st.error("请先完整填写：" + "、".join(missing))
                else:
                    st.session_state.profile_completed = True
                    st.success(f"登记信息已保存。系统生成参与者编号：{generated_id}")
                    st.rerun()
            return

        st.markdown(
            "<div class='login-card-title'>受试者信息登记</div>"
            "<div class='login-card-desc'>请按院区、科室和姓名首字母完成登记。系统将自动生成匿名参与者编号，并写入训练报告和云端数据库。</div>",
            unsafe_allow_html=True,
        )

        clinical_organizations = configured_organizations("clinical")
        clinical_by_id = {
            item["organization_id"]: item
            for item in clinical_organizations
        }
        with st.form("participant_profile_form", clear_on_submit=False):
            st.markdown("##### 基本身份信息")

            campus_options = [""] + list(CAMPUS_CODES.keys())
            department_options = [""] + list(DEPARTMENT_CODES.keys())

            c0, c1, c2, c3 = st.columns([1.3, 1, 1, 1], gap="large")
            if clinical_organizations:
                clinical_ids = [""] + list(clinical_by_id)
                current_id = str(st.session_state.get("organization_id", "") or "")
                selected_organization_id = c0.selectbox(
                    "授权临床机构（必填）",
                    clinical_ids,
                    index=clinical_ids.index(current_id) if current_id in clinical_ids else 0,
                    format_func=lambda value: (
                        organization_display_label(clinical_by_id[value])
                        if value in clinical_by_id
                        else "请选择已登记临床机构"
                    ),
                )
                selected_organization = clinical_by_id.get(
                    selected_organization_id,
                    {},
                )
                institution = str(selected_organization.get("hospital_name", "") or "")
            else:
                selected_organization_id = ""
                institution = c0.text_input(
                    "医院全称（必填）",
                    value=st.session_state.institution or DEFAULT_INSTITUTION,
                    placeholder=(
                        "示范教学单位"
                        if is_competition_mode()
                        else "请填写医院全称，如：四川大学华西第二医院"
                    ),
                )
                c0.caption("当前未配置授权机构；本次记录不会归入任何单位管理员范围。")
            campus = c1.selectbox(
                "院区/中心（必填）",
                campus_options,
                index=campus_options.index(st.session_state.campus) if st.session_state.campus in campus_options else 0,
            )
            department = c2.selectbox(
                "科室细分（必填）",
                department_options,
                index=department_options.index(st.session_state.department) if st.session_state.department in department_options else 0,
            )
            participant_initials = c3.text_input(
                "姓名首字母（必填）",
                value=st.session_state.participant_initials,
                placeholder=(
                    "示例学员"
                    if is_competition_mode()
                    else "例如 王思席填 WSX"
                ),
                max_chars=8,
            )

            preview_id = build_participant_id(campus, department, participant_initials)
            code_parts = participant_code_parts(campus, department, participant_initials)
            id_col, note_col = st.columns([1.1, 1], gap="large")
            id_col.text_input(
                "系统生成参与者编号（自动生成，不需手动填写）",
                value=preview_id,
                disabled=True,
            )
            note_col.markdown(
                f"""
                <div class='id-help-box'>
                    编码规则：院区代码 + 科室代码 + 姓名首字母 + 防重复后缀<br>
                    当前代码：{html.escape(code_parts.get('campus_code', '') or '待选择')} / {html.escape(code_parts.get('department_code', '') or '待选择')}
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("##### 护理层级与背景")
            n1, n2, n3 = st.columns([1, 1, 1], gap="large")
            nurse_levels = ["", "N0/CN0", "N1/CN1", "N2/CN2", "N3/CN3", "N4/CN4", "护士长/护理管理者", "其他"]
            nurse_level = n1.selectbox(
                "护理层级（必填）",
                nurse_levels,
                index=nurse_levels.index(st.session_state.nurse_level) if st.session_state.nurse_level in nurse_levels else 0,
            )
            years_experience = n2.number_input(
                "工作年限（年，必填）",
                min_value=0.0,
                max_value=50.0,
                value=float(st.session_state.years_experience or 0.0),
                step=0.5,
                format="%.1f",
            )
            years_experience_confirmed = n2.checkbox(
                "已核对工作年限",
                value=bool(st.session_state.get("years_experience_confirmed", False)),
            )
            titles = ["", "护士", "护师", "主管护师", "副主任护师", "主任护师", "其他"]
            professional_title = n3.selectbox(
                "职称",
                titles,
                index=titles.index(st.session_state.professional_title) if st.session_state.professional_title in titles else 0,
            )

            n4, n5, n6 = st.columns([1, 1, 1], gap="large")
            edu_options = ["", "中专", "大专", "本科", "硕士及以上", "其他"]
            education_level = n4.selectbox(
                "最高学历",
                edu_options,
                index=edu_options.index(st.session_state.education_level) if st.session_state.education_level in edu_options else 0,
            )
            phase_options = phase_options_for_mode("clinical")
            assessment_phase = n5.selectbox(
                "评估阶段（必填）",
                phase_options,
                index=phase_options.index(st.session_state.assessment_phase)
                if st.session_state.assessment_phase in phase_options else 0,
            )
            collection_mode = n6.selectbox(
                "采集模式（必填）",
                COLLECTION_MODE_OPTIONS,
                index=COLLECTION_MODE_OPTIONS.index(st.session_state.collection_mode)
                if st.session_state.collection_mode in COLLECTION_MODE_OPTIONS else 0,
            )

            workflow_preview = workflow_for_phase(assessment_phase, "clinical")
            st.markdown(
                f"<div class='form-note'>阶段确认：{html.escape(workflow_preview.get('display', ''))}。"
                f"采集模式：{html.escape(collection_mode)}。正式收数据时请勿选择测试演练。</div>",
                unsafe_allow_html=True,
            )
            collection_note = st.text_area(
                "现场备注/异常记录（选填）",
                value=st.session_state.get("collection_note", ""),
                placeholder="如老师干预、中途断网、误点后重做等；无异常可留空。",
                height=80,
            )

            st.markdown(
                "<div class='form-note'>说明：项目编号与第几次测试不再由受试者填写；系统将在后台保留版本号、会话编号和默认尝试序号用于数据追踪；部分补充信息将在相应流程结束后按系统提示采集。</div>",
                unsafe_allow_html=True,
            )

            submitted = st.form_submit_button("保存信息并进入训练系统", type="primary", use_container_width=True)

        if submitted:
            initials_clean = normalize_initials(participant_initials)
            generated_id = build_participant_id(campus, department, initials_clean)
            parts = participant_code_parts(campus, department, initials_clean)
            old_participant_id = st.session_state.get("participant_id", "")
            participant_changed = bool(old_participant_id and generated_id and generated_id != old_participant_id)
            if participant_changed:
                st.session_state.prior_anaphylaxis_training = ""
                st.session_state.prior_simulation_experience = ""
                st.session_state.real_case_experience = ""
                st.session_state.prior_experience_survey_completed = False
                st.session_state.prior_experience_survey_time = ""
                st.session_state.baseline_performance_completed = False
                st.session_state.baseline_stage_completed = False
                st.session_state.years_experience_confirmed = False

            st.session_state.participant_initials = initials_clean
            st.session_state.participant_id = generated_id
            st.session_state.participant_type = "clinical_nurse"
            st.session_state.organization_type = "clinical"
            st.session_state.organization_id = selected_organization_id
            st.session_state.campus_code = parts.get("campus_code", "")
            st.session_state.department_code = parts.get("department_code", "")
            st.session_state.institution = institution.strip() or DEFAULT_INSTITUTION
            st.session_state.campus = campus.strip()
            st.session_state.department = department.strip()
            st.session_state.department_type = department.strip()
            st.session_state.nurse_level = nurse_level.strip()
            st.session_state.years_experience = years_experience
            st.session_state.years_experience_confirmed = bool(years_experience_confirmed)
            st.session_state.professional_title = professional_title.strip()
            st.session_state.education_level = education_level.strip()
            st.session_state.collection_mode = collection_mode.strip()
            st.session_state.collection_note = collection_note.strip()
            st.session_state.school_name = ""
            st.session_state.student_level = ""
            st.session_state.student_grade = ""
            st.session_state.student_class = ""
            # 既往过敏反应培训/仿真培训/真实处理经历不在登记页采集，
            # 仅在基线评估操作完成后以补充问卷形式采集一次，避免提示效应。
            st.session_state.training_batch = ""
            st.session_state.assessment_phase = assessment_phase.strip()
            workflow = workflow_for_phase(st.session_state.assessment_phase, "clinical")
            st.session_state.workflow_mode = workflow.get("mode", "exam")
            st.session_state.workflow_script_role = workflow.get("script_role", "initial")
            st.session_state.workflow_display = workflow.get("display", "")
            st.session_state.workflow_locked = True
            st.session_state.mode = st.session_state.workflow_mode
            st.session_state.attempt_no = 1

            missing = profile_required_missing()
            if missing:
                st.error("请先完整填写：" + "、".join(missing))
            else:
                st.session_state.profile_completed = True
                st.success(f"登记信息已保存。系统生成参与者编号：{generated_id}")
                st.rerun()


def restart_current_stage(scenario_path: Path, mode: str) -> bool:
    """Start a fresh session for only the active phase after explicit confirmation."""

    if not scenario_path.is_file():
        return False
    participant_id = str(st.session_state.get("participant_id", "") or "")
    if not participant_id:
        return False
    previous_session_id = str(st.session_state.get("session_id", "") or "")
    if previous_session_id:
        abandoned = list(
            st.session_state.get("abandoned_stage_sessions", []) or []
        )
        marker = {
            "participant_id": participant_id,
            "assessment_phase": str(
                st.session_state.get("assessment_phase", "") or ""
            ),
            "session_id": previous_session_id,
            "status": "restarted",
        }
        if marker not in abandoned:
            abandoned.append(marker)
        st.session_state.abandoned_stage_sessions = abandoned[-20:]
    start_simulation(
        scenario_path=scenario_path,
        mode=mode,
        seed=-1,
        participant_id=participant_id,
    )
    return True


def render_sidebar() -> None:
    st.sidebar.title("评审演示控制台" if is_competition_mode() else f"{APP_VERSION} 控制台")
    mode = current_system_mode()
    mode_label = current_system_mode_label()
    st.sidebar.caption(f"当前模式：{mode_label}")
    if is_competition_mode():
        if st.sidebar.button("返回评审首页", use_container_width=True):
            clear_training_draft()
            st.session_state.system_mode_selected = False
            st.session_state.profile_completed = False
            st.session_state.active_simulator = None
            st.session_state.ended = False
            st.session_state.academy_flow_page = ""
            st.rerun()
        if st.sidebar.button("退出评审环境", use_container_width=True):
            clear_competition_session()
            st.rerun()
    elif st.sidebar.button("切换临床/学院模式", use_container_width=True, disabled=st.session_state.active_simulator is not None):
        clear_training_draft()
        st.session_state.system_mode_selected = False
        st.session_state.academy_scenario_selected = False
        st.session_state.profile_completed = False
        st.session_state.active_simulator = None
        st.session_state.ended = False
        st.rerun()
    if (
        not is_competition_mode()
        and mode == "academy"
        and st.sidebar.button("重新选择学院情景", use_container_width=True, disabled=st.session_state.active_simulator is not None)
    ):
        clear_training_draft()
        st.session_state.academy_scenario_selected = False
        st.session_state.profile_completed = False
        st.session_state.active_simulator = None
        st.session_state.ended = False
        st.rerun()

    if (
        is_competition_mode()
        and st.session_state.get("competition_admin_unlocked", False)
        and not st.session_state.get("competition_review_unlocked", False)
    ):
        st.session_state.page = "管理员后台"
        st.sidebar.caption("当前会话仅具有评审只读管理权限。")
    else:
        st.session_state.page = st.sidebar.radio(
            "页面",
            options=["训练系统", "管理员后台"],
            index=0 if st.session_state.page == "训练系统" else 1,
        )

    if st.session_state.page == "管理员后台":
        st.sidebar.caption("管理员后台用于查看并导出训练记录。")
        return

    if not st.session_state.get("profile_completed", False):
        st.sidebar.info("请先在主界面完成信息登记。")
        return

    st.sidebar.subheader("对象摘要")
    sidebar_phase_label = str(
        st.session_state.get("assessment_phase", "")
    )
    if is_competition_mode() and mode == "academy":
        sidebar_phase_label, _ = academy_sidebar_status(
            st.session_state.get("academy_flow_page", ""),
            sidebar_phase_label,
            "",
        )
        st.sidebar.caption(
            f"""学员：评审学员-001
单位：{'示范护理学院' if mode == 'academy' else '示范教学单位'}
阶段：{sidebar_phase_label}
采集模式：虚拟演示"""
        )
    elif mode == "academy":
        st.sidebar.caption(f"""编号：{st.session_state.participant_id}
院校：{st.session_state.school_name}
情景：{st.session_state.get('academy_scenario_name', '')}
层次：{st.session_state.student_level}｜阶段：{st.session_state.student_grade}
班级/小组：{st.session_state.student_class or '未填写'}
采集模式：{st.session_state.get('collection_mode', '')}""")
    else:
        st.sidebar.caption(f"""编号：{st.session_state.participant_id}
单位：{st.session_state.institution}｜{st.session_state.campus}
科室：{st.session_state.department}
层级：{st.session_state.nurse_level}｜年限：{st.session_state.years_experience}年
采集模式：{st.session_state.get('collection_mode', '')}""")
    if is_competition_mode():
        if st.sidebar.button("更换演示学员", use_container_width=True):
            setup_competition_participant(mode)
            st.rerun()
    elif st.sidebar.button("重新填写对象信息", use_container_width=True):
        clear_training_draft()
        st.session_state.profile_completed = False
        st.session_state.active_simulator = None
        st.session_state.ended = False
        st.rerun()

    st.sidebar.subheader("本阶段任务")
    workflow = workflow_for_phase(st.session_state.get("assessment_phase", default_phase_for_mode(mode)), mode)
    st.session_state.workflow_mode = workflow.get("mode", "exam")
    st.session_state.workflow_script_role = workflow.get("script_role", "initial")
    st.session_state.workflow_display = workflow.get("display", "")
    st.session_state.workflow_locked = True
    st.session_state.mode = st.session_state.workflow_mode

    scenario_name = (
        academy_scenario_display_name(
            st.session_state.get("academy_scenario_name", "")
        )
        if mode == "academy"
        else "药物诱发严重过敏反应抢救"
    )
    workflow_mode_label = flow_strategy_for_phase(
        mode,
        st.session_state.get("assessment_phase", default_phase_for_mode(mode)),
    ).workflow_mode_label
    if mode == "academy":
        sidebar_phase_label, workflow_mode_label = academy_sidebar_status(
            st.session_state.get("academy_flow_page", ""),
            st.session_state.get("assessment_phase", ""),
            workflow_mode_label,
        )
    st.sidebar.markdown(
        f"""
        <div style="border:1px solid #E5E7EB;border-radius:14px;padding:0.85rem 0.9rem;background:#F8FAFC;margin-bottom:0.75rem;">
            <div style="font-size:0.85rem;color:#64748B;margin-bottom:0.25rem;">阶段</div>
            <div style="font-size:1.05rem;font-weight:700;color:#0F172A;margin-bottom:0.55rem;">{html.escape(sidebar_phase_label)}</div>
            <div style="font-size:0.85rem;color:#64748B;margin-bottom:0.25rem;">模式</div>
            <div style="font-size:0.98rem;font-weight:650;color:#1E293B;margin-bottom:0.55rem;">{html.escape(workflow_mode_label)}</div>
            <div style="font-size:0.85rem;color:#64748B;margin-bottom:0.25rem;">情景</div>
            <div style="font-size:0.98rem;font-weight:650;color:#1E293B;margin-bottom:0.55rem;">{html.escape(scenario_name)}</div>
            <div style="font-size:0.85rem;color:#64748B;margin-bottom:0.25rem;">病例</div>
            <div style="font-size:0.98rem;font-weight:650;color:#1E293B;margin-bottom:0.55rem;">{html.escape(workflow.get('script_label', ''))}</div>
            <div style="font-size:0.82rem;color:#475569;line-height:1.45;">{html.escape(workflow.get('task', ''))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    scenario_path = scenario_path_for_phase(
        mode,
        st.session_state.get("assessment_phase", default_phase_for_mode(mode)),
        current_academy_scenario_id() if mode == "academy" else "",
    )
    if scenario_path is None:
        st.sidebar.error("未找到本阶段对应的病例脚本，请检查 scenarios 文件夹。")
    else:
        start_label = (
            "重新开始本阶段"
            if st.session_state.active_simulator is not None
            else "开始本阶段"
        )
    if scenario_path is not None:
        if st.session_state.active_simulator is None:
            if st.sidebar.button(
                start_label,
                type="primary",
                use_container_width=True,
            ):
                missing = profile_required_missing()
                if missing:
                    st.sidebar.error("请先完整填写：" + "、".join(missing))
                else:
                    start_simulation(
                        scenario_path=scenario_path,
                        mode=workflow.get("mode", "exam"),
                        seed=-1,
                        participant_id=st.session_state.participant_id.strip(),
                    )
                    st.rerun()
        elif (
            not st.session_state.get("ended", False)
            and not st.session_state.get("academy_flow_page", "")
        ):
            if (
                not st.session_state.get("restart_stage_confirmation", False)
                and st.sidebar.button(
                    "重新开始本阶段",
                    type="primary",
                    use_container_width=True,
                )
            ):
                st.session_state.restart_stage_confirmation = True
                persist_active_training_draft()
                st.rerun()
            if st.session_state.get("restart_stage_confirmation", False):
                st.sidebar.warning(
                    "确认重新开始本阶段？\n\n当前阶段已执行操作将被清除。"
                )
                keep_col, restart_col = st.sidebar.columns(2, gap="small")
                if keep_col.button(
                    "继续当前阶段",
                    use_container_width=True,
                ):
                    st.session_state.restart_stage_confirmation = False
                    persist_active_training_draft()
                    st.rerun()
                if restart_col.button(
                    "确认重新开始",
                    type="primary",
                    use_container_width=True,
                ):
                    if claim_ui_event(
                        "restart_stage",
                        str(st.session_state.get("assessment_phase", "") or ""),
                        str(st.session_state.get("session_id", "") or ""),
                    ) and restart_current_stage(
                        scenario_path,
                        workflow.get("mode", "exam"),
                    ):
                        st.rerun()
                    else:
                        st.sidebar.error("当前阶段未能重新开始，原状态仍已保留。")

    st.sidebar.divider()
    st.sidebar.caption("声明：仅用于护理教学、培训与科研可行性验证，不用于临床诊疗决策。")


def inject_compact_css() -> None:
    """Compact, clinical-monitor-like layout plus flash animation for changes."""
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"] {
            overflow-x: hidden !important;
        }
        .block-container {
            padding-top: 0.55rem !important;
            padding-bottom: 0.75rem !important;
            padding-left: 1.05rem !important;
            padding-right: 1.05rem !important;
            max-width: 100% !important;
        }
        h1, h2, h3, h4 {
            margin-top: 0.05rem !important;
            margin-bottom: 0.12rem !important;
        }
        h1 {font-size: 1.22rem !important;}
        h2 {font-size: 1.08rem !important;}
        h3 {font-size: 1.02rem !important;}
        p, li, .stMarkdown, .stCaption, label {
            font-size: 0.86rem !important;
        }
        div[data-testid="stVerticalBlock"] { gap: 0.52rem !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.72rem !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] { padding: 0.76rem !important; }
        .stAlert { padding: 0.24rem 0.45rem !important; }
        hr { margin: 0.22rem 0 !important; }
        [data-testid="stSidebar"] .block-container {
            padding-top: 0.45rem !important;
            padding-bottom: 0.45rem !important;
        }
        [data-testid="stSidebarContent"] {
            overflow-y: auto !important;
            max-height: 100vh !important;
        }
        [data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
            gap: 0.30rem !important;
        }

        .app-title {
            font-weight: 700;
            font-size: 1.02rem;
            line-height: 1.15;
            margin-bottom: 0.08rem;
        }
        .app-subtitle {
            color: #68717d;
            font-size: 0.72rem;
            line-height: 1.1;
        }
        .status-panel {
            border: 1px solid #dfe4ec;
            border-radius: 0.78rem;
            background: #ffffff;
            padding: 0.72rem 0.82rem;
            margin-top: 0.78rem;
            margin-bottom: 0.42rem;
        }
        .status-panel-title {
            font-size: 0.88rem;
            font-weight: 750;
            color: #111827;
            margin-bottom: 0.52rem;
        }
        .top-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.58rem;
            margin-bottom: 0.0rem;
        }
        .top-card {
            min-height: 3.05rem;
            border: 1px solid #e5e8ed;
            background: #f9fafc;
            border-radius: 0.62rem;
            padding: 0.48rem 0.58rem;
        }
        .top-card .label {
            color: #667085;
            font-size: 0.76rem;
            line-height: 1.0;
            margin-bottom: 0.30rem;
        }
        .top-card .value {
            color: #111827;
            font-weight: 780;
            font-size: 1.02rem;
            line-height: 1.05;
        }
        .session-line {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.25;
            text-align: left;
            margin-top: 0.48rem;
        }
        .patient-panel {
            border: 1px solid #d9dee7;
            border-radius: 0.90rem;
            background: #ffffff;
            padding: 1.18rem 1.24rem 1.16rem 1.24rem;
        }
        .patient-head {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            justify-content: space-between;
            gap: 1.0rem;
            margin-bottom: 0.44rem;
        }
        .patient-title {
            font-weight: 800;
            font-size: 1.34rem;
            line-height: 1.2;
            white-space: normal;
            overflow-wrap: anywhere;
        }
        .patient-meta {
            color: #334155;
            font-size: 1.10rem;
            font-weight: 650;
            line-height: 1.35;
            text-align: right;
        }
        .baseline-box {
            color: #374151;
            font-size: 1.05rem;
            line-height: 1.58;
            margin-bottom: 0.72rem;
        }
        .clinical-card {
            border-radius: 0.74rem;
            border: 1px solid #e5e7eb;
            background: #f8fafc;
            padding: 0.86rem 0.92rem;
            margin-bottom: 0.70rem;
        }
        .clinical-card .label {
            color: #667085;
            font-size: 0.92rem;
            margin-bottom: 0.24rem;
        }
        .clinical-card .value {
            color: #111827;
            font-weight: 820;
            font-size: 1.58rem;
            line-height: 1.38;
        }
        .vital-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.66rem;
        }
        .vital-card {
            min-height: 4.72rem;
            border-radius: 0.76rem;
            border: 1px solid #e5e7eb;
            background: #fbfcfe;
            padding: 0.78rem 0.82rem;
        }
        .vital-card .label {
            color: #667085;
            font-size: 0.94rem;
            line-height: 1.0;
            margin-bottom: 0.32rem;
        }
        .vital-card .value {
            color: #101828;
            font-weight: 850;
            font-size: 1.62rem;
            line-height: 1.12;
        }
        .vital-card.warn { border-color: #f6c768; background: #fffbeb; }
        .vital-card.danger { border-color: #f2a0a0; background: #fff5f5; }
        .change-banner {
            margin-top: 0.45rem;
            padding: 0.30rem 0.46rem;
            border-radius: 0.50rem;
            border: 1px solid #ffd18a;
            background: #fff7e6;
            color: #8a4b00;
            font-size: 0.74rem;
            font-weight: 700;
        }
        @keyframes clinicalFlash {
            0%   { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.60); transform: translateY(0); }
            45%  { box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.22); transform: translateY(-1px); }
            100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.00); transform: translateY(0); }
        }
        .flash {
            animation: clinicalFlash 0.80s ease-in-out 0s 2;
            border-color: #f59e0b !important;
            background: #fff7e6 !important;
        }
        .section-caption {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.1;
        }
        .action-head {
            display:flex;
            align-items:baseline;
            justify-content:space-between;
            gap:0.65rem;
            margin-bottom:0.62rem;
        }
        .action-title {
            font-weight:800;
            font-size:1.12rem;
        }
        .action-note {
            color:#667085;
            font-size:0.82rem;
            text-align:right;
        }
        .stButton > button {
            height: auto !important;
            min-height: 2.65rem !important;
            padding: 0.34rem 0.56rem !important;
            font-size: 0.90rem !important;
            line-height: 1.22 !important;
            border-radius: 0.66rem !important;
            white-space: normal !important;
            word-break: break-word !important;
            overflow-wrap: anywhere !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        .stButton > button p, .stButton > button div, .stButton > button span {
            white-space: normal !important;
            word-break: break-word !important;
            overflow-wrap: anywhere !important;
            line-height: 1.22 !important;
            overflow: visible !important;
            text-overflow: clip !important;
            display: block !important;
        }
        [data-testid="stSidebar"] .stButton > button {
            min-height: 2.30rem !important;
            padding: 0.28rem 0.48rem !important;
        }
        .stDownloadButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            min-height: 2.65rem !important;
            padding: 0.34rem 0.56rem !important;
        }
        .dose-card {
            border: 1px solid #c7d2fe;
            background: #eef2ff;
            border-radius: 0.78rem;
            padding: 0.76rem 0.86rem;
            margin-bottom: 0.76rem;
        }
        .dose-card .title {
            font-weight: 800;
            font-size: 1.02rem;
            color: #1e3a8a;
            margin-bottom: 0.26rem;
        }
        .dose-card .text {
            font-size: 0.90rem;
            color: #334155;
            line-height: 1.40;
        }
        .coach-prompt {
            border: 1px solid #ffd18a;
            background: #fff8e8;
            border-radius: 0.70rem;
            padding: 0.62rem 0.76rem;
            margin-top: 0.50rem;
            margin-bottom: 0.38rem;
        }
        .coach-prompt .title {
            font-size: 0.86rem;
            font-weight: 750;
            color: #8a4b00;
            margin-bottom: 0.22rem;
        }
        .coach-prompt .text {
            font-size: 0.92rem;
            font-weight: 700;
            color: #111827;
            line-height: 1.35;
        }
        .coach-prompt .reason {
            font-size: 0.80rem;
            color: #6b4e16;
            line-height: 1.35;
            margin-top: 0.26rem;
        }

        .history-panel {
            border: 1px solid #d9dee7;
            background: #ffffff;
            border-radius: 0.72rem;
            padding: 0.70rem 0.78rem;
            margin-top: 0.72rem;
            margin-bottom: 0.64rem;
        }
        .history-title {
            font-size: 1.00rem;
            font-weight: 800;
            color: #111827;
            margin-bottom: 0.42rem;
        }
        .history-empty {
            color: #667085;
            font-size: 0.92rem;
            line-height: 1.35;
        }
        .history-list {
            display: grid;
            gap: 0.38rem;
            max-height: 15.5rem;
            overflow-y: auto;
            padding-right: 0.20rem;
        }
        .history-item {
            display: grid;
            grid-template-columns: 4.5rem 1fr auto;
            gap: 0.55rem;
            align-items: center;
            border: 1px solid #eef1f5;
            background: #f8fafc;
            border-radius: 0.56rem;
            padding: 0.45rem 0.55rem;
        }
        .history-time {color:#475569; font-size:0.86rem; font-weight:700;}
        .history-action {color:#111827; font-size:0.94rem; font-weight:750;}
        .history-result {color:#667085; font-size:0.82rem; text-align:right;}
        @media (max-width: 1400px) {
            .top-strip {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .vital-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .patient-title {
                font-size: 1.14rem;
            }
            .patient-meta {
                font-size: 0.96rem;
                text-align: left;
            }
            .history-list {
                max-height: 12rem;
            }
            .history-item {
                grid-template-columns: 4.1rem minmax(0, 1fr);
            }
            .history-result {
                grid-column: 2;
                text-align: left;
            }
        }
        div[data-testid="stExpander"] details {
            border-radius: 0.55rem !important;
        }
        
        .version-corner {
            position: fixed;
            top: 0.55rem;
            right: 1.15rem;
            z-index: 999;
            color: #667085;
            font-size: 0.76rem;
            background: rgba(255,255,255,0.92);
            border: 1px solid #e5e7eb;
            border-radius: 999px;
            padding: 0.28rem 0.72rem;
            box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06);
        }
        .login-hero {
            width: min(1120px, 92vw);
            margin: 1.2rem auto 0.8rem auto;
            text-align: center;
            padding-top: 0.3rem;
        }
        .login-title {
            font-size: 2.05rem;
            line-height: 1.24;
            font-weight: 850;
            color: #0f172a;
            letter-spacing: -0.02em;
        }
        .login-subtitle {
            margin-top: 0.42rem;
            color: #475569;
            font-size: 1.05rem;
            line-height: 1.45;
        }
        .login-card-title {
            margin-top: 0.35rem;
            font-size: 1.32rem;
            line-height: 1.3;
            font-weight: 820;
            color: #111827;
            border: 1px solid #e5e7eb;
            border-bottom: 0;
            border-radius: 1rem 1rem 0 0;
            background: #ffffff;
            padding: 1.05rem 1.25rem 0.4rem 1.25rem;
        }
        .id-help-box {
            min-height: 3.15rem;
            border: 1px solid #dbeafe;
            border-radius: 0.8rem;
            background: #eff6ff;
            color: #1e3a8a;
            font-size: 0.88rem;
            line-height: 1.55;
            padding: 0.78rem 0.95rem;
            margin-top: 1.55rem;
        }
        .form-note {
            color: #667085;
            background: #f8fafc;
            border: 1px dashed #cbd5e1;
            border-radius: 0.8rem;
            padding: 0.72rem 0.9rem;
            font-size: 0.9rem;
            line-height: 1.55;
            margin: 0.2rem 0 0.85rem 0;
        }
        .login-card-desc {
            font-size: 0.94rem;
            color: #667085;
            line-height: 1.5;
            border-left: 1px solid #e5e7eb;
            border-right: 1px solid #e5e7eb;
            background: #ffffff;
            padding: 0 1.25rem 0.8rem 1.25rem;
            margin-bottom: -0.1rem;
        }
        div[data-testid="stForm"] {
            border: 1px solid #e5e7eb !important;
            border-top: 0 !important;
            border-radius: 0 0 1rem 1rem !important;
            padding: 0.95rem 1.25rem 1.15rem 1.25rem !important;
            background: #ffffff !important;
            box-shadow: 0 14px 38px rgba(15, 23, 42, 0.07) !important;
        }
        .access-card {
            width: min(620px, 92vw);
            margin: 8vh auto 0 auto;
            border: 1px solid #e5e7eb;
            border-radius: 1.1rem;
            background: #ffffff;
            padding: 1.6rem 1.7rem;
            box-shadow: 0 16px 45px rgba(15, 23, 42, 0.08);
            text-align: center;
        }
        .access-card-title {
            font-size: 1.62rem;
            font-weight: 850;
            line-height: 1.25;
            color: #111827;
            margin-bottom: 0.38rem;
        }
        .access-card-desc {
            font-size: 0.95rem;
            color: #667085;
            line-height: 1.5;
            margin-bottom: 0.85rem;
        }
</style>
        """,
        unsafe_allow_html=True,
    )
    if is_competition_mode():
        st.markdown(
            """
            <style>
            [data-testid="stToolbar"], [data-testid="stDecoration"] {
                display: none !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def compact_header() -> None:
    st.markdown(
        f"<div class='app-title'>{html.escape(APP_TITLE)}</div>"
        f"<div class='app-subtitle'>动态分支 · 实时状态 · 操作评分 · 报告导出</div>",
        unsafe_allow_html=True,
    )


def make_ui_snapshot(sim: Simulator) -> Dict[str, Any]:
    return {
        "time": sim.state.t,
        "clinical": symptoms_text(sim),
        "score": f"{sim.score}/{sim.max_score}",
        "reassess": int(sim.state.flags.get("reassess_count", 0)),
        "symptoms": symptoms_text(sim),
        "vitals": visible_vitals(sim),
    }


def detect_ui_changes(sim: Simulator) -> Dict[str, Any]:
    current = make_ui_snapshot(sim)
    previous = st.session_state.get("last_ui_snapshot")
    changes: Dict[str, Any] = {"clinical": False, "symptoms": False, "score": False, "reassess": False, "vitals": set()}

    if isinstance(previous, dict):
        changes["clinical"] = previous.get("clinical") != current.get("clinical")
        changes["symptoms"] = previous.get("symptoms") != current.get("symptoms")
        changes["score"] = previous.get("score") != current.get("score")
        changes["reassess"] = previous.get("reassess") != current.get("reassess")
        prev_vitals = previous.get("vitals", {}) or {}
        cur_vitals = current.get("vitals", {}) or {}
        changed_vitals: Set[str] = set()
        for key, value in cur_vitals.items():
            if prev_vitals.get(key) != value:
                changed_vitals.add(key)
        changes["vitals"] = changed_vitals

    st.session_state.last_ui_snapshot = current
    return changes


def flash_class(condition: bool) -> str:
    return " flash" if condition else ""


def vital_severity_class(sim: Simulator, key: str) -> str:
    """Visual cue only; formal scoring still comes from the simulation engine."""
    v = sim.state.vitals
    f = sim.state.flags
    if f.get("dead", False) or (f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False)):
        return " danger"
    if f.get("resuscitation_rosc", False):
        return " warn"
    if key == "SpO₂" and f.get("monitor_on", False):
        spo2 = float(v.get("SpO2", 100))
        if spo2 < 90:
            return " danger"
        if spo2 < 95:
            return " warn"
    if key == "BP" and f.get("bp_checked", False):
        sbp = float(v.get("SBP", 120))
        if sbp < sim.age_sbp_threshold():
            return " danger"
    if key == "HR" and f.get("monitor_on", False):
        hr = float(v.get("HR", 0))
        if hr >= 180:
            return " warn"
    return ""


def compact_action_label(label: str, max_chars: int = 24) -> str:
    cleaned = " ".join(str(label).split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1] + "…"


def render_top_status(sim: Simulator, changes: Dict[str, Any]) -> None:
    action_count = sum(1 for e in sim.log if e.kind == "action" and e.message != "penalty")
    strategy = current_flow_strategy(sim)
    if strategy.score_presentation == "live":
        score_text = f"{sim.score}/{sim.max_score}"
        items = [
            ("时间", format_elapsed_time(sim.state.t), False),
            ("得分", score_text, bool(changes.get("score"))),
            ("有效复评", str(int(sim.state.flags.get("reassess_count", 0))), bool(changes.get("reassess"))),
            ("操作数", str(action_count), False),
        ]
    else:
        items = [
            ("时间", format_elapsed_time(sim.state.t), False),
            ("操作数", str(action_count), False),
        ]
    html_items = []
    for label, value, changed in items:
        html_items.append(
            f"<div class='top-card{flash_class(changed)}'>"
            f"<div class='label'>{html.escape(label)}</div>"
            f"<div class='value'>{html.escape(value)}</div>"
            f"</div>"
        )
    st.markdown(
        f"<div class='status-panel'>"
        f"<div class='status-panel-title'>运行信息</div>"
        f"<div class='top-strip'>{''.join(html_items)}</div>"
        f"<div class='session-line'>"
        f"模式：{strategy.mode_label}｜"
        f"参与者：{html.escape(st.session_state.participant_id or 'anonymous')}｜"
        f"会话编号：{html.escape(st.session_state.session_id[-13:] if st.session_state.session_id else '')}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )



def _render_patient_status_body(
    sim: Simulator,
    scenario: Dict[str, Any],
    changes: Dict[str, Any],
    *,
    live_monitor: bool = False,
    direct_html: bool = False,
) -> None:
    patient = scenario.get("patient", {})
    patient_meta = (
        f"{patient.get('setting','')}｜{patient.get('age_years','')}岁｜"
        f"{patient.get('weight_kg','')} kg｜{patient.get('trigger','')}"
    )
    baseline = scenario.get("baseline", {}).get("time_zero_description", "")
    academy_context = ""
    if current_flow_strategy(sim).system_mode == "academy":
        teaching_scenario = academy_scenario_display_name(
            st.session_state.get("academy_scenario_name", "")
        )
        shock_present = float(sim.state.vitals.get("SBP", 0) or 0) < float(
            sim.age_sbp_threshold()
        )
        current_condition = (
            "已进展为过敏性休克"
            if shock_present
            else "严重过敏反应，尚需动态评估循环"
        )
        academy_context = (
            "<div class='section-caption'>"
            f"教学情景：{html.escape(teaching_scenario)}<br>"
            f"当前病情：{html.escape(current_condition)}"
            "</div>"
        )
    symptom_now = symptoms_text(sim)
    changed_vitals: Set[str] = changes.get("vitals", set()) or set()
    any_clinical_change = (
        bool(changes.get("symptoms"))
        or bool(changes.get("clinical"))
        or bool(changed_vitals)
    )

    vital_cards = []
    display_vitals = live_display_vitals(sim) if live_monitor else visible_vitals(sim)
    for key, value in display_vitals.items():
        cls = "vital-card" + vital_severity_class(sim, key) + flash_class(key in changed_vitals)
        vital_cards.append(
            f"<div class='{cls}'>"
            f"<div class='label'>{html.escape(key)}</div>"
            f"<div class='value'>{html.escape(value)}</div>"
            f"</div>"
        )

    banner = ""
    if any_clinical_change:
        changed_names = []
        if changes.get("clinical"):
            changed_names.append("病情")
        if changes.get("symptoms"):
            changed_names.append("临床表现")
        if changed_vitals:
            changed_names.append("生命体征")
        banner = (
            f"<div class='change-banner flash'>{' / '.join(changed_names)} 状态已更新。</div>"
        )

    panel_html = f"""
        <div class='patient-panel'>
            <div class='patient-head'>
                <div class='patient-title'>病例与实时状态</div>
                <div class='patient-meta'>{html.escape(patient_meta)}</div>
            </div>
            <div class='baseline-box'>{html.escape(baseline)}</div>
            {academy_context}
            <div class='clinical-card{flash_class(bool(changes.get('symptoms')))}'>
                <div class='label'>当前症状</div>
                <div class='value'>{html.escape(symptom_now)}</div>
            </div>
            <div class='vital-grid'>{''.join(vital_cards)}</div>
            {banner}
        </div>
    """
    if direct_html:
        # Clinical review hotfix: bypass Markdown parsing so an empty academy_context
        # cannot turn the following HTML into a visible code block.
        st.html(panel_html)
    else:
        # Preserve the academy rendering path exactly as before.
        st.markdown(panel_html, unsafe_allow_html=True)


@st.fragment(run_every=CLINICAL_REVIEW_LIVE_VITALS_REFRESH_SECONDS)
def _render_clinical_patient_status_fragment(
    sim: Simulator,
    scenario: Dict[str, Any],
    changes: Dict[str, Any],
) -> None:
    """Refresh clinical bedside display only; never call Simulator.tick()."""
    marker = (
        str(st.session_state.get("session_id", "") or ""),
        int(getattr(sim.state, "t", 0) or 0),
        len(getattr(sim, "log", []) or []),
    )
    last_marker = st.session_state.get("_review_live_fragment_marker")
    fragment_changes = changes
    if last_marker == marker:
        # Suppress repeated flash animation on timer-only fragment reruns.
        fragment_changes = {
            "clinical": False,
            "symptoms": False,
            "score": False,
            "reassess": False,
            "vitals": set(),
        }
    else:
        st.session_state["_review_live_fragment_marker"] = marker
    _render_patient_status_body(
        sim,
        scenario,
        fragment_changes,
        live_monitor=True,
        direct_html=True,
    )


@st.fragment(run_every=CLINICAL_REVIEW_LIVE_VITALS_REFRESH_SECONDS)
def _render_academy_patient_status_fragment(
    sim: Simulator,
    scenario: Dict[str, Any],
    changes: Dict[str, Any],
) -> None:
    """Refresh academy bedside display only; never call Simulator.tick()."""
    marker = (
        "academy",
        str(st.session_state.get("session_id", "") or ""),
        int(getattr(sim.state, "t", 0) or 0),
        len(getattr(sim, "log", []) or []),
    )
    last_marker = st.session_state.get("_review_academy_live_fragment_marker")
    fragment_changes = changes
    if last_marker == marker:
        fragment_changes = {
            "clinical": False,
            "symptoms": False,
            "score": False,
            "reassess": False,
            "vitals": set(),
        }
    else:
        st.session_state["_review_academy_live_fragment_marker"] = marker
    _render_patient_status_body(
        sim,
        scenario,
        fragment_changes,
        live_monitor=True,
        direct_html=True,
    )


def render_patient_status(sim: Simulator, scenario: Dict[str, Any], changes: Dict[str, Any]) -> None:
    system_mode = current_flow_strategy(sim).system_mode
    if system_mode == "clinical":
        _render_clinical_patient_status_fragment(sim, scenario, changes)
    elif system_mode == "academy":
        _render_academy_patient_status_fragment(sim, scenario, changes)
    else:
        _render_patient_status_body(
            sim,
            scenario,
            changes,
            live_monitor=False,
            direct_html=False,
        )


def render_intro() -> None:
    compact_header()
    st.success(f"{current_system_mode_label()}对象信息已登记。请在左侧查看本阶段任务，然后点击“开始本阶段”。")

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown("#### 当前登记信息")
        if current_system_mode() == "academy":
            info_rows = [
                {"项目": "系统模式", "内容": current_system_mode_label()},
                {"项目": "教学情景", "内容": academy_scenario_display_name(st.session_state.get("academy_scenario_name", ""))},
                {"项目": "情景类别", "内容": st.session_state.get("academy_scenario_category", "")},
                {"项目": "适用课程", "内容": st.session_state.get("academy_course_type", "")},
                {"项目": "参与者编号", "内容": st.session_state.get("participant_id", "")},
                {"项目": "院校名称", "内容": st.session_state.get("school_name", "")},
                {"项目": "培养层次", "内容": st.session_state.get("student_level", "")},
                {"项目": "年级/阶段", "内容": st.session_state.get("student_grade", "")},
                {"项目": "班级/小组", "内容": st.session_state.get("student_class", "")},
                {"项目": "姓名首字母", "内容": st.session_state.get("participant_initials", "")},
                {"项目": "评估阶段", "内容": st.session_state.get("assessment_phase", "")},
                {"项目": "采集模式", "内容": st.session_state.get("collection_mode", "")},
            ]
        else:
            info_rows = [
                {"项目": "系统模式", "内容": current_system_mode_label()},
                {"项目": "参与者编号", "内容": st.session_state.get("participant_id", "")},
                {"项目": "单位/医院", "内容": st.session_state.get("institution", "")},
                {"项目": "院区/中心", "内容": st.session_state.get("campus", "")},
                {"项目": "院区代码", "内容": st.session_state.get("campus_code", "")},
                {"项目": "科室细分", "内容": st.session_state.get("department", "")},
                {"项目": "科室代码", "内容": st.session_state.get("department_code", "")},
                {"项目": "姓名首字母", "内容": st.session_state.get("participant_initials", "")},
                {"项目": "护理层级", "内容": st.session_state.get("nurse_level", "")},
                {"项目": "工作年限", "内容": f"{st.session_state.get('years_experience', '')} 年"},
                {"项目": "评估阶段", "内容": st.session_state.get("assessment_phase", "")},
                {"项目": "采集模式", "内容": st.session_state.get("collection_mode", "")},
            ]
        st.dataframe(info_rows, use_container_width=True, hide_index=True)

    with right:
        if current_system_mode() == "academy":
            scenario_name = st.session_state.get("academy_scenario_name", "")
            instruction = f"""
            **本阶段使用说明**

            学院模式面向在校护生，采用通用情景库框架；当前已选择“{scenario_name}”情景，重点训练早期识别、停止可疑药物、呼救协作、给氧监测、准备肾上腺素及抢救物品、基础复评、家属安抚与简化SBAR汇报。

            本模式不要求护生独立决策或独立实施肾上腺素给药、快速补液或高级生命支持，但要求其知道肾上腺素是一线急救药物，并能在老师/医生指导下完成核对、给药配合与规范汇报。当前浏览器刷新后可恢复已保存的阶段状态；浏览器返回不会改变服务端已完成阶段或授权范围。系统会自动记录操作过程，并在本阶段完成后进入独立阶段完成页。
            """
        else:
            instruction = """
            **本阶段使用说明**

            请确认左侧显示的评估阶段与本人信息无误，然后点击“开始/重置本阶段任务”。进入情境后，请根据页面显示的患儿状态和个人临床判断独立完成操作。

            操作过程中如刷新当前页面，系统会在同一浏览器中恢复本阶段进度。请勿复制或分享带恢复标识的页面地址；关闭页面超过12小时后草稿会自动失效。本阶段完成后系统先显示完整结果页，确认得分与反馈后可继续下一阶段、重新开始或返回首页。
            """
        st.container(border=True).markdown(instruction)


def clear_competition_session() -> None:
    clear_training_draft()
    st.session_state.clear()


def setup_competition_participant(system_mode: str = "academy") -> None:
    """Create a fully virtual participant without collecting reviewer identity."""
    reset_for_mode_selection(system_mode)
    st.session_state.participant_unique_suffix = uuid.uuid4().hex[:4].upper()
    st.session_state.participant_initials = "DEMO"
    st.session_state.collection_mode = "测试演练"
    st.session_state.collection_note = ""
    st.session_state.organization_id = ""
    st.session_state.academy_stage_reports = {}
    st.session_state.academy_stage_session_ids = {}
    st.session_state.academy_transition_locks = {}
    st.session_state.abandoned_stage_sessions = []
    st.session_state.academy_flow_page = ""
    st.session_state.prior_anaphylaxis_training = ""
    st.session_state.prior_simulation_experience = ""
    st.session_state.real_case_experience = ""
    st.session_state.prior_experience_survey_completed = False
    st.session_state.prior_experience_survey_time = ""
    st.session_state.baseline_performance_completed = False
    st.session_state.baseline_stage_completed = False
    st.session_state.pending_academy_post_evaluation = False
    st.session_state.pending_post_evaluation_report = None
    st.session_state.academy_post_evaluation_completed = False
    st.session_state.questionnaire_submission_id = ""
    st.session_state.questionnaire_draft = {}
    if system_mode == "academy":
        scenario = ACADEMY_SCENARIO_LIBRARY[ACADEMY_SCENARIO_DEFAULT_ID]
        st.session_state.academy_scenario_selected = True
        st.session_state.school_name = "示范护理学院"
        st.session_state.student_level = "本科"
        st.session_state.student_grade = "三年级"
        st.session_state.student_class = "评审演示组"
        st.session_state.institution = "示范护理学院"
        st.session_state.department = "示范教学单元"
        st.session_state.participant_id = (
            f"COMP-ACAD-{st.session_state.participant_unique_suffix}"
        )
        st.session_state.assessment_phase = "课前测评"
        st.session_state.academy_scenario_id = scenario["id"]
        st.session_state.academy_scenario_name = scenario["name"]
    else:
        st.session_state.institution = "示范教学单位"
        st.session_state.campus = "教学区域A"
        st.session_state.campus_code = "JXA"
        st.session_state.department = "示范教学单元"
        st.session_state.department_code = "JXDY"
        st.session_state.department_type = "临床演示"
        st.session_state.nurse_level = "演示学员"
        st.session_state.years_experience = 0.0
        st.session_state.years_experience_confirmed = True
        st.session_state.participant_id = (
            f"COMP-CLIN-{st.session_state.participant_unique_suffix}"
        )
        st.session_state.assessment_phase = default_phase_for_mode("clinical")
    workflow = workflow_for_phase(st.session_state.assessment_phase, system_mode)
    st.session_state.workflow_mode = workflow.get("mode", "exam")
    st.session_state.workflow_script_role = workflow.get("script_role", "initial")
    st.session_state.workflow_display = workflow.get("display", "")
    st.session_state.mode = st.session_state.workflow_mode
    st.session_state.profile_completed = True


def reset_for_mode_selection(system_mode: str) -> None:
    clear_training_draft()
    st.session_state.system_mode = system_mode
    st.session_state.organization_type = system_mode
    st.session_state.organization_id = ""
    st.session_state.system_mode_selected = True
    st.session_state.participant_type = SYSTEM_MODE_OPTIONS[system_mode].get("participant_type", "")
    st.session_state.academy_scenario_selected = False if system_mode == "academy" else True
    if system_mode == "academy":
        scenario = ACADEMY_SCENARIO_LIBRARY[ACADEMY_SCENARIO_DEFAULT_ID]
        st.session_state.academy_scenario_id = scenario["id"]
        st.session_state.academy_scenario_name = scenario["name"]
        st.session_state.academy_scenario_category = scenario["category"]
        st.session_state.academy_course_type = scenario["course_type"]
        st.session_state.academy_difficulty = scenario["difficulty"]
    st.session_state.profile_completed = False
    st.session_state.active_simulator = None
    st.session_state.active_scenario = None
    st.session_state.active_scenario_path = ""
    st.session_state.active_script_name = ""
    st.session_state.ended = False
    st.session_state.last_report = None
    st.session_state.last_report_paths = None
    st.session_state.result_saved = False
    st.session_state.restart_stage_confirmation = False
    st.session_state.processed_ui_events = []
    st.session_state.pending_prior_experience_survey = False
    st.session_state.assessment_phase = default_phase_for_mode(system_mode)
    workflow = workflow_for_phase(st.session_state.assessment_phase, system_mode)
    st.session_state.workflow_mode = workflow.get("mode", "exam")
    st.session_state.workflow_script_role = workflow.get("script_role", "initial")
    st.session_state.workflow_display = workflow.get("display", "")
    st.session_state.workflow_locked = True
    st.session_state.mode = st.session_state.workflow_mode
    st.session_state.participant_id = ""
    st.session_state.participant_initials = ""
    st.session_state.participant_unique_suffix = ""
    ensure_participant_suffix()
    st.session_state.collection_mode = "正式采集"
    st.session_state.collection_note = ""
    if system_mode == "academy":
        st.session_state.institution = ""
        st.session_state.campus = ""
        st.session_state.department = "学院教学"
        st.session_state.department_type = "护生教学"
        st.session_state.campus_code = "ACAD"
        st.session_state.department_code = "ACAD"
        st.session_state.nurse_level = ""
        st.session_state.years_experience = 0.0
        st.session_state.years_experience_confirmed = True
        st.session_state.professional_title = ""
        st.session_state.education_level = ""
    else:
        st.session_state.institution = DEFAULT_INSTITUTION
        st.session_state.school_name = ""
        st.session_state.student_level = ""
        st.session_state.student_grade = ""
        st.session_state.student_class = ""
        st.session_state.campus = ""
        st.session_state.department = ""
        st.session_state.department_type = ""
        st.session_state.campus_code = ""
        st.session_state.department_code = ""
        st.session_state.years_experience_confirmed = False


def select_academy_scenario(scenario_id: str) -> None:
    clear_training_draft()
    scenario = ACADEMY_SCENARIO_LIBRARY.get(scenario_id, ACADEMY_SCENARIO_LIBRARY[ACADEMY_SCENARIO_DEFAULT_ID])
    st.session_state.academy_scenario_id = scenario["id"]
    st.session_state.academy_scenario_name = scenario["name"]
    st.session_state.academy_scenario_category = scenario["category"]
    st.session_state.academy_course_type = scenario["course_type"]
    st.session_state.academy_difficulty = scenario["difficulty"]
    st.session_state.academy_scenario_selected = True
    st.session_state.profile_completed = False
    st.session_state.active_simulator = None
    st.session_state.active_scenario = None
    st.session_state.active_scenario_path = ""
    st.session_state.ended = False
    st.session_state.last_report = None
    st.session_state.result_saved = False
    st.session_state.assessment_phase = default_phase_for_mode("academy")
    workflow = workflow_for_phase(st.session_state.assessment_phase, "academy")
    st.session_state.workflow_mode = workflow.get("mode", "exam")
    st.session_state.workflow_script_role = workflow.get("script_role", "academy_initial")
    st.session_state.workflow_display = workflow.get("display", "")
    st.session_state.workflow_locked = True
    st.session_state.mode = st.session_state.workflow_mode


def render_academy_scenario_selection_page() -> bool:
    if current_system_mode() != "academy":
        return True
    if st.session_state.get("academy_scenario_selected", False):
        return True
    render_version_corner()
    st.markdown(
        f"""
        <div class='login-hero'>
            <div class='login-title'>学院模式｜护理基础能力情景库</div>
            <div class='login-subtitle'>请选择本次教学/测评使用的虚拟仿真情景</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([0.12, 0.76, 0.12], gap="large")
    with center:
        st.markdown(
            "<div class='login-card-desc'>学院模式保留通用情景库框架。当前情景库中仅开放一个情景，后续可在同一框架下继续增加输液反应、低血糖、跌倒/坠床、气道梗阻等其他教学情景。</div>",
            unsafe_allow_html=True,
        )
        selected_id = st.selectbox(
            "教学情景（当前仅开放1项）",
            academy_scenario_options(),
            index=academy_scenario_options().index(current_academy_scenario_id()) if current_academy_scenario_id() in academy_scenario_options() else 0,
            format_func=academy_scenario_label,
        )
        scenario = ACADEMY_SCENARIO_LIBRARY[selected_id]
        st.container(border=True).markdown(
            f"""
            **情景名称：** {scenario.get('name', '')}  
            **情景类别：** {scenario.get('category', '')}  
            **适用课程：** {scenario.get('course_type', '')}  
            **难度层级：** {scenario.get('difficulty', '')}  
            **开放状态：** {scenario.get('status', '')}  

            {scenario.get('description', '')}
            """
        )
        c1, c2 = st.columns([1, 1], gap="large")
        with c1:
            if st.button("返回模式选择", use_container_width=True):
                st.session_state.system_mode_selected = False
                st.session_state.academy_scenario_selected = False
                st.rerun()
        with c2:
            if st.button("进入该情景", type="primary", use_container_width=True):
                select_academy_scenario(selected_id)
                st.rerun()
    return False


def render_system_mode_selection_page() -> bool:
    if st.session_state.get("system_mode_selected", False):
        return True
    render_version_corner()
    if is_competition_mode():
        st.markdown(
            """
            <div class='login-hero'>
                <div class='login-title'>护理急救动态分支虚拟仿真教学智能体</div>
                <div class='login-subtitle'>比赛评审演示环境</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info("本环境使用虚拟身份与独立存储，不读取或写入正式运行数据。")
        left, academy_col, clinical_col, right = st.columns(
            [0.08, 0.50, 0.34, 0.08],
            gap="large",
        )
        with academy_col:
            st.container(border=True).markdown(
                "### 学院教学完整体验\n课前测评 → 模拟训练 → 课后考核 → 结果 → SUS及教学体验评价"
            )
            if st.button(
                "进入学院教学体验",
                type="primary",
                use_container_width=True,
            ):
                setup_competition_participant("academy")
                st.rerun()
        with clinical_col:
            st.container(border=True).markdown(
                "### 临床模式演示\n体验与正式系统相同的医学核心、病例和评分规则。"
            )
            if st.button("进入临床模式演示", use_container_width=True):
                setup_competition_participant("clinical")
                st.rerun()
        if st.button("退出评审环境"):
            clear_competition_session()
            st.rerun()
        return False
    st.markdown(
        f"""
        <div class='login-hero'>
            <div class='login-title'>{html.escape(APP_TITLE)}</div>
            <div class='login-subtitle'>请选择进入场景：临床培训或学院教学</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, c1, c2, right = st.columns([0.08, 0.42, 0.42, 0.08], gap="large")
    with c1:
        st.container(border=True).markdown(
            """
            ### 临床模式
            面向临床护士、低年资护士及科室培训对象。  
            保留原系统的严重过敏反应/过敏性休克动态分支、剂量核对、补液、复评、SBAR与家属沟通流程。
            """
        )
        if st.button("进入临床模式", type="primary", use_container_width=True):
            reset_for_mode_selection("clinical")
            st.rerun()
    with c2:
        st.container(border=True).markdown(
            """
            ### 学院模式
            面向高职/大专、本科及其他在校护生。  
            进入后先选择“学院情景库”中的教学情景；当前情景库仅开放“严重过敏反应/过敏性休克抢救”1个情景。
            """
        )
        if st.button("进入学院模式", type="primary", use_container_width=True):
            reset_for_mode_selection("academy")
            st.rerun()
    st.info("说明：临床模式不改变原系统逻辑；学院模式保留通用情景库框架，当前仅开放严重过敏反应/过敏性休克抢救情景。两类数据在报告中通过 system_mode 字段区分，学院数据另通过 academy_scenario_id 区分情景。")
    return False


def require_app_access() -> bool:
    if APP_MODE_CONFIGURATION_ERROR:
        st.error(APP_MODE_CONFIGURATION_ERROR)
        return False
    if is_competition_mode():
        if (
            st.session_state.get("competition_review_unlocked", False)
            or st.session_state.get("competition_admin_unlocked", False)
        ):
            return True
        review_code, admin_code = get_competition_auth_credentials()
        invalid_fields = tuple(
            name
            for name, value in (
                ("COMPETITION_REVIEW_CODE", review_code),
                ("COMPETITION_ADMIN_CODE", admin_code),
            )
            if not value
        )
        render_version_corner()
        st.markdown(
            """
            <div class='access-card'>
                <div class='access-card-title'>护理急救动态分支虚拟仿真教学智能体</div>
                <div class='access-card-desc'>比赛评审演示环境</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info("虚拟演示数据，不代表实际研究结果。")
        review_col, admin_col = st.columns(2, gap="large")
        with review_col:
            st.markdown("#### 评委体验入口")
            submitted_review = st.text_input(
                "评审体验码",
                type="password",
            )
            if not review_code:
                st.warning("评审体验码尚未安全配置，当前拒绝进入。")
            if st.button(
                "进入评审体验",
                type="primary",
                use_container_width=True,
                disabled=not review_code,
            ):
                if credential_matches(submitted_review, review_code):
                    st.session_state.competition_review_unlocked = True
                    st.session_state.app_unlocked = True
                    st.rerun()
                else:
                    st.error("评审体验码不正确。")
        with admin_col:
            st.markdown("#### 评审只读管理端")
            submitted_admin = st.text_input(
                "评审管理码",
                type="password",
            )
            if not admin_code:
                st.warning("评审管理码尚未安全配置，当前拒绝进入。")
            if st.button(
                "进入评审只读管理端",
                use_container_width=True,
                disabled=not admin_code,
            ):
                if credential_matches(submitted_admin, admin_code):
                    try:
                        scope = create_competition_admin_context()
                    except AuthConfigurationError:
                        st.error("授权签名密钥未安全配置，管理端已拒绝进入。")
                    else:
                        st.session_state.competition_admin_unlocked = True
                        st.session_state.admin_unlocked = True
                        st.session_state.admin_scope = scope
                        st.session_state.admin_scope_type = COMPETITION_ADMIN_ROLE
                        st.session_state.app_unlocked = True
                        st.session_state.system_mode_selected = True
                        st.session_state.academy_scenario_selected = True
                        st.session_state.page = "管理员后台"
                        st.rerun()
                else:
                    st.error("评审管理码不正确。")
        if invalid_fields:
            st.caption("缺少或无效配置：" + "、".join(invalid_fields))
        return False

    access_code, _ = require_auth_credentials()
    if st.session_state.get("app_unlocked", False):
        return True

    render_version_corner()
    st.markdown(
        f"""
        <div class='access-card'>
            <div class='access-card-title'>进入虚拟仿真训练系统</div>
            <div class='access-card-desc'>请输入访问码。系统仅用于护理教学、培训与科研，不用于临床诊疗决策。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([0.32, 0.36, 0.32])
    with center:
        code = st.text_input("访问码", type="password", placeholder="请输入访问码", label_visibility="collapsed")
        if st.button("进入系统", type="primary", use_container_width=True):
            if credential_matches(code, access_code):
                st.session_state.app_unlocked = True
                st.rerun()
            else:
                st.error("访问码不正确。")
    return False


def render_action_history(sim: Simulator) -> None:
    rows = get_action_history_rows(sim)
    show_results = current_flow_strategy(sim).show_immediate_feedback
    if not rows:
        empty_text = (
            "当前尚未执行任何操作。每次点击选项后，操作记录会显示在这里。"
            if show_results
            else ""
        )
        st.markdown(
            "<div class='history-panel'>"
            "<div class='history-title'>已执行操作</div>"
            f"<div class='history-empty'>{html.escape(empty_text)}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return
    html_rows = []
    for row in reversed(rows[-12:]):
        result_html = (
            f"<div class='history-result'>{html.escape(str(row.get('结果','')))}</div>"
            if show_results
            else ""
        )
        html_rows.append(
            "<div class='history-item'>"
            f"<div class='history-time'>{html.escape(str(row.get('时间','')))}</div>"
            f"<div class='history-action'>{html.escape(str(row.get('操作','')))}</div>"
            f"{result_html}"
            "</div>"
        )
    title = f"已执行操作（{len(rows)}项）" if show_results else "已执行操作"
    st.markdown(
        "<div class='history-panel'>"
        f"<div class='history-title'>{html.escape(title)}</div>"
        "<div class='history-list'>" + "".join(html_rows) + "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if show_results:
        latest = rows[-1]
        with st.expander("操作说明", expanded=False):
            st.write(f"完整操作：{latest.get('操作', '')}")
            if latest.get("结果"):
                st.write(f"本次反馈：{latest.get('结果', '')}")


def render_org_management_panel() -> None:
    st.markdown("#### 单位管理码维护")
    st.caption(
        "单位管理员凭据只接受加盐哈希配置。请在服务器本机使用"
        "`tools/generate_org_admin_credential.py`生成配置；后台不会生成、保存或显示明文管理码。"
    )
    records = load_org_access_records()
    valid_records = [
        item
        for item in records
        if _normalize_unit_identity(item) is not None
    ]
    invalid_count = len(records) - len(valid_records)
    if invalid_count:
        st.error(f"发现 {invalid_count} 条无效或旧式单位凭据配置，已拒绝加载。")
    if valid_records:
        preview = []
        for item in valid_records:
            preview.append({
                "organization_id": item.get("organization_id", ""),
                "权限类型": item.get("role", ""),
                "院校": item.get("school_name", ""),
                "医院": item.get("hospital_name", ""),
                "科室/院系": item.get("department_name", ""),
                "状态": item.get("status", ""),
            })
        st.dataframe(preview, use_container_width=True, hide_index=True)
    else:
        st.warning("尚未配置有效的单位管理员哈希凭据。")


def render_admin_page() -> None:
    compact_header()
    if is_competition_mode():
        st.markdown("### 评审只读环境")
        st.info("虚拟演示数据，不代表实际研究结果。")
        if not st.session_state.get("admin_unlocked", False):
            _, admin_code = get_competition_auth_credentials()
            pwd = st.text_input("评审管理码", type="password")
            if not admin_code:
                st.warning("评审管理码尚未安全配置，当前拒绝进入。")
                return
            if st.button("进入评审只读管理端", type="primary"):
                if credential_matches(pwd, admin_code):
                    try:
                        scope = create_competition_admin_context()
                    except AuthConfigurationError:
                        st.error("授权签名密钥未安全配置，管理端已拒绝进入。")
                        return
                    st.session_state.admin_unlocked = True
                    st.session_state.admin_scope = scope
                    st.session_state.admin_scope_type = COMPETITION_ADMIN_ROLE
                    st.session_state.competition_admin_unlocked = True
                    st.rerun()
                else:
                    st.error("评审管理码不正确。")
            return
    else:
        st.markdown(f"### 管理者后台｜{APP_VERSION} 推广版权限管理版")
        _, admin_password = require_auth_credentials()
        if not st.session_state.get("admin_unlocked", False):
            st.caption("请输入总管理员密码或单位管理码。总管理员可维护单位管理码；单位管理员只能查看和导出本单位数据。")
            pwd = st.text_input("管理码/管理员密码", type="password")
            if st.button("进入管理者后台", type="primary"):
                if credential_matches(pwd, admin_password):
                    st.session_state.admin_unlocked = True
                    try:
                        st.session_state.admin_scope = create_platform_admin_context()
                    except AuthConfigurationError:
                        st.error("授权签名密钥未安全配置，管理端已拒绝进入。")
                        st.session_state.admin_unlocked = False
                        return
                    st.session_state.admin_scope_type = PLATFORM_ADMIN_ROLE
                    st.rerun()
                else:
                    try:
                        scope = find_org_scope_by_code(pwd)
                    except AuthConfigurationError:
                        st.error("授权签名密钥未安全配置，管理端已拒绝进入。")
                        return
                    if scope:
                        st.session_state.admin_unlocked = True
                        st.session_state.admin_scope = scope
                        st.session_state.admin_scope_type = str(scope.get("role", ""))
                        st.rerun()
                    else:
                        st.error("管理码无效或已停用。")
            return

    scope = validate_authorization_context(st.session_state.get("admin_scope"))
    if scope is None:
        st.session_state.admin_unlocked = False
        st.session_state.admin_scope = None
        st.session_state.admin_scope_type = ""
        st.error(AUTH_CONTEXT_ERROR_MESSAGE)
        return
    st.session_state.admin_scope = scope
    st.success("当前权限：" + scope_label(scope))
    if st.button("退出后台", use_container_width=False):
        st.session_state.admin_unlocked = False
        st.session_state.admin_scope = None
        st.session_state.admin_scope_type = ""
        st.session_state.competition_admin_unlocked = False
        st.rerun()

    if scope["role"] == PLATFORM_ADMIN_ROLE and authorization_allows(scope, "manage"):
        render_org_management_panel()
        st.divider()

    raw_db_rows, db_message = load_result_rows_database(scope)
    local_full_reports = load_full_reports_local(scope)
    local_summary_records = load_result_records_local(scope)

    if is_competition_mode():
        st.caption("后台数据源：只读虚拟演示数据。正式数据库访问已在后端关闭。")
    elif database_configured():
        if raw_db_rows:
            st.success("云端数据库已连接：" + db_message)
        else:
            st.warning("已配置云端数据库，但当前未读取到记录或读取失败：" + db_message)
    else:
        st.info("当前未配置 Supabase 云端数据库，系统将仅显示本地备用记录。")

    if raw_db_rows:
        full_reports = [full_report_from_database_row(x) for x in raw_db_rows]
        summary_records = [normalize_database_record(x) for x in raw_db_rows]
        action_detail_records = build_action_detail_records_from_reports(full_reports, storage_source="supabase")
        raw_jsonl_records = full_reports
        storage_label = "supabase"
    elif local_full_reports:
        full_reports = local_full_reports
        summary_records = build_summary_records_from_reports(local_full_reports, storage_source="local")
        action_detail_records = build_action_detail_records_from_reports(local_full_reports, storage_source="local")
        raw_jsonl_records = local_full_reports
        storage_label = "local_full_report"
    else:
        full_reports = []
        summary_records = local_summary_records
        action_detail_records = []
        raw_jsonl_records = local_summary_records
        storage_label = "local_summary_only"

    if local_summary_records and raw_db_rows:
        st.caption(f"本地备用摘要记录：{len(local_summary_records)} 条；当前后台优先显示云端数据库记录。")

    # First enforce unit-level scope. Ordinary unit admins never see full dataset.
    summary_records = [r for r in summary_records if record_matches_scope(r, scope)]
    action_detail_records = [r for r in action_detail_records if record_matches_scope(r, scope)]
    raw_jsonl_records = [r for r in raw_jsonl_records if isinstance(r, dict) and raw_record_matches_scope(r, scope)]

    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1], gap="large")
    if scope["role"] == "clinical_admin":
        mode_options = ["临床模式"]
    elif scope["role"] == "academy_admin":
        mode_options = ["学院模式"]
    else:
        mode_options = ["全部", "临床模式", "学院模式"]
    mode_filter = filter_col1.selectbox("系统模式筛选", mode_options, index=0)
    collection_filter = filter_col2.selectbox("采集模式筛选", ["全部"] + COLLECTION_MODE_OPTIONS, index=0)
    phase_filter = filter_col3.selectbox("阶段筛选", ["全部"] + ALL_ASSESSMENT_PHASE_OPTIONS, index=0)

    extra_filters = {}
    if scope["role"] == PLATFORM_ADMIN_ROLE:
        st.caption("总管理员可查看全部数据，也可使用下方字段进行单位筛选。普通单位管理员进入后会自动锁定单位范围。")
        u1, u2, u3 = st.columns([1, 1, 1], gap="large")
        extra_filters["hospital"] = u1.text_input("医院全称筛选（选填）", value="")
        extra_filters["department"] = u2.text_input("科室筛选（选填）", value="")
        extra_filters["school"] = u3.text_input("院校全称筛选（选填）", value="")
    else:
        st.caption("当前单位管理员权限已自动限定数据范围，导出按钮仅导出本单位当前筛选结果。")

    def keep_mode(record: Dict[str, Any]) -> bool:
        if mode_filter == "全部":
            return True
        return str(record.get("system_mode_label", "")) == mode_filter or (
            mode_filter == "临床模式" and str(record.get("system_mode", "")) in ("", "clinical")
        ) or (mode_filter == "学院模式" and str(record.get("system_mode", "")) == "academy")

    def keep_collection(record: Dict[str, Any]) -> bool:
        return collection_filter == "全部" or str(record.get("collection_mode", "")) == collection_filter

    def keep_phase(record: Dict[str, Any]) -> bool:
        return phase_filter == "全部" or str(record.get("assessment_phase", "")) == phase_filter

    def keep_extra(record: Dict[str, Any]) -> bool:
        hosp = str(extra_filters.get("hospital", "")).strip()
        dept = str(extra_filters.get("department", "")).strip()
        school = str(extra_filters.get("school", "")).strip()
        if hosp and str(record.get("institution", "")) != hosp:
            return False
        if dept and str(record.get("department", "")) != dept:
            return False
        if school and str(record.get("school_name", "")) != school:
            return False
        return True

    filtered_summary_records = [r for r in summary_records if keep_mode(r) and keep_collection(r) and keep_extra(r)]
    participant_analysis_records = build_participant_analysis_records(filtered_summary_records)
    quality_records = build_data_quality_records(filtered_summary_records)
    summary_records = [r for r in filtered_summary_records if keep_phase(r)]
    action_detail_records = [r for r in action_detail_records if keep_mode(r) and keep_collection(r) and keep_phase(r) and keep_extra(r)]

    def keep_raw_record(record: Dict[str, Any]) -> bool:
        if "session" in record and isinstance(record.get("session"), dict):
            session = record.get("session", {}) or {}
            wrapped = {
                "system_mode": session.get("system_mode", ""),
                "system_mode_label": session.get("system_mode_label", ""),
                "collection_mode": session.get("collection_mode", ""),
                "assessment_phase": session.get("assessment_phase", ""),
                "institution": session.get("institution", ""),
                "department": session.get("department", ""),
                "school_name": session.get("school_name", ""),
            }
            return keep_mode(wrapped) and keep_collection(wrapped) and keep_phase(wrapped) and keep_extra(wrapped)
        return keep_mode(record) and keep_collection(record) and keep_phase(record) and keep_extra(record)

    raw_jsonl_records = [r for r in raw_jsonl_records if isinstance(r, dict) and keep_raw_record(r)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("训练记录数", len(summary_records))
    if summary_records:
        scores = []
        epi_invalid_count = 0
        for r in summary_records:
            try:
                scores.append(float(r.get("score", 0)))
            except Exception:
                pass
            if str(r.get("epi_dose_status", "")) in ["underdose", "overdose"]:
                epi_invalid_count += 1
        c2.metric("平均得分", f"{sum(scores)/len(scores):.1f}" if scores else "-")
        c3.metric("前后测配对人数", sum(1 for r in participant_analysis_records if r.get("pre_post_pair_ready") == "是"))
        c4.metric("肾上腺素剂量错误", epi_invalid_count)
    else:
        c2.metric("平均得分", "-")
        c3.metric("前后测配对人数", "-")
        c4.metric("肾上腺素剂量错误", "-")

    st.markdown("#### 数据导出")
    st.caption("导出仅基于当前权限和当前筛选结果；单位管理员不会导出其他医院/学校数据。")

    safe_scope = safe_filename_part(scope_label(scope).replace("｜", "_"))
    d1, d2, d3, d4, d5 = st.columns(5)
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    d1.download_button("一人一行 CSV", data=records_to_csv_bytes(participant_analysis_records, scope), file_name=f"peds_sim_participant_paired_{safe_scope}_{storage_label}_{now}.csv", mime="text/csv", use_container_width=True, disabled=not participant_analysis_records)
    d2.download_button("汇总 CSV", data=records_to_csv_bytes(summary_records, scope), file_name=f"peds_sim_summary_{safe_scope}_{storage_label}_{now}.csv", mime="text/csv", use_container_width=True, disabled=not summary_records)
    d3.download_button("质控提示 CSV", data=records_to_csv_bytes(quality_records, scope), file_name=f"peds_sim_quality_checks_{safe_scope}_{storage_label}_{now}.csv", mime="text/csv", use_container_width=True, disabled=not quality_records)
    d4.download_button("操作明细 CSV", data=records_to_csv_bytes(action_detail_records, scope), file_name=f"peds_sim_action_details_{safe_scope}_{storage_label}_{now}.csv", mime="text/csv", use_container_width=True, disabled=not action_detail_records)
    d5.download_button("完整 JSONL", data=records_to_jsonl_bytes(raw_jsonl_records, scope), file_name=f"peds_sim_full_reports_{safe_scope}_{storage_label}_{now}.jsonl", mime="application/json", use_container_width=True, disabled=not raw_jsonl_records)

    st.divider()
    view = st.radio("查看数据表", ["一人一行", "训练汇总", "质控提示", "操作明细"], index=["一人一行", "训练汇总", "质控提示", "操作明细"].index(st.session_state.get("admin_export_view", "一人一行")) if st.session_state.get("admin_export_view", "一人一行") in ["一人一行", "训练汇总", "质控提示", "操作明细"] else 0, horizontal=True)
    st.session_state.admin_export_view = view

    if view == "一人一行":
        if participant_analysis_records:
            st.markdown("**一人一行配对分析表预览（最近200名受试者）**")
            st.dataframe(_dataframe_ready_records(list(reversed(participant_analysis_records[-200:]))), use_container_width=True, hide_index=True)
        else:
            st.warning("尚未产生可配对的受试者记录。")
    elif view == "训练汇总":
        if summary_records:
            st.markdown("**训练汇总预览（最近200条）**")
            st.dataframe(_dataframe_ready_records(list(reversed(summary_records[-200:]))), use_container_width=True, hide_index=True)
        else:
            st.warning("尚未产生训练汇总记录。")
    elif view == "质控提示":
        if quality_records:
            st.markdown("**质控提示预览**")
            st.dataframe(_dataframe_ready_records(quality_records), use_container_width=True, hide_index=True)
        else:
            st.success("当前筛选范围内未发现明显质控提示。")
    else:
        if action_detail_records:
            st.markdown("**操作明细预览（最近500条操作事件）**")
            st.dataframe(_dataframe_ready_records(list(reversed(action_detail_records[-500:]))), use_container_width=True, hide_index=True)
        else:
            st.warning("尚未产生可展开的操作明细。旧版本仅保存摘要时，可能无法展开。")

    with st.expander("字段说明", expanded=False):
        st.markdown("""
        - **一人一行 CSV**：按参与者编号和采集模式自动配对课前/训练/课后或基线/培训/后测，包含前后测分差、SUS和教学体验字段。
        - **汇总 CSV**：每次训练一行，展开关键时间点、剂量状态、错误操作次数、最终生命体征等。
        - **质控提示 CSV**：列出缺少阶段、重复阶段、异常短时长、主动确认完成和现场备注。
        - **操作明细 CSV**：每个操作事件一行，适合分析操作顺序和延迟。
        - **完整 JSONL**：保留完整训练报告和问卷嵌套结构，适合长期归档。
        """)


def render_epinephrine_dose_panel(sim: Simulator) -> bool:
    """Render dose-confirmation panel for IM epinephrine or repeat IM epinephrine."""
    pending_id = st.session_state.get("pending_dose_action_id", "")
    if pending_id not in ("im_epinephrine", "repeat_epinephrine"):
        return False

    weight = float(getattr(sim.state, "weight_kg", 0) or 0)
    target_mg = round(min(0.01 * weight, 0.3), 3)
    max_single_mg = 0.3
    strategy = current_flow_strategy(sim)
    title = "再次肌注肾上腺素：请输入本次总剂量" if pending_id == "repeat_epinephrine" else "肌注肾上腺素：请输入本次总剂量"
    dose_help = (
        "单位为 mg。确认后系统会按情景规则判断剂量是否有效。"
        if strategy.show_immediate_feedback
        else "单位为 mg。"
    )
    st.markdown(
        "<div class='dose-card'>"
        f"<div class='title'>{html.escape(title)}</div>"
        f"<div class='text'>{html.escape(dose_help)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if strategy.show_immediate_feedback:
        st.caption(f"训练提示：本例体重 {weight:g} kg；剂量为 0.01 mg/kg，即 {target_mg:g} mg；儿童单次最大 {max_single_mg:g} mg。")

    dose_key = f"epi_dose_mg_{pending_id}_{st.session_state.session_id}_{sim.state.t}"
    dose_mg = st.number_input(
        "本次肌注总剂量（mg）",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        key=dose_key,
    )
    c_ok, c_cancel = st.columns([1, 1], gap="medium")
    if c_ok.button("确认剂量并执行", type="primary", use_container_width=True):
        if claim_ui_event("confirm_dose", str(pending_id), sim.state.t):
            result = sim.apply_epinephrine_dose(float(dose_mg), action_id=pending_id)
            st.session_state.last_dose_feedback = (
                str(result.get("message", ""))
                if strategy.show_immediate_feedback
                else ""
            )
            st.session_state.last_dose_feedback_level = (
                str(result.get("status", ""))
                if strategy.show_immediate_feedback
                else ""
            )
            st.session_state.pending_dose_action_id = ""
            st.session_state.pending_dose_action_label = ""
            sim.tick()
            finalize_if_done()
        st.rerun()
    if c_cancel.button("取消输入", use_container_width=True):
        st.session_state.pending_dose_action_id = ""
        st.session_state.pending_dose_action_label = ""
        st.rerun()
    return True


def render_fluid_bolus_panel(sim: Simulator) -> bool:
    """Render volume-confirmation panel for crystalloid bolus."""
    pending_id = st.session_state.get("pending_volume_action_id", "")
    if pending_id != "fluid_bolus":
        return False

    weight = float(getattr(sim.state, "weight_kg", 0) or 0)
    min_ml = round(10 * weight, 1)
    max_ml = round(min(20 * weight, 500), 1)
    strategy = current_flow_strategy(sim)
    fluid_help = (
        "单位为 ml。确认后系统会按体重判断容量是否合理。"
        if strategy.show_immediate_feedback
        else "单位为 ml。"
    )
    st.markdown(
        "<div class='dose-card'>"
        "<div class='title'>快速补液：请输入本次晶体液容量</div>"
        f"<div class='text'>{html.escape(fluid_help)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if strategy.show_immediate_feedback:
        st.caption(f"训练提示：本例体重 {weight:g} kg；合理范围 {min_ml:g}–{max_ml:g} ml（10–20 ml/kg，单次最大500 ml）。")

    volume_key = f"fluid_volume_ml_{st.session_state.session_id}_{sim.state.t}"
    volume_ml = st.number_input(
        "本次快速补液容量（ml）",
        min_value=0.0,
        max_value=2000.0,
        value=0.0,
        step=10.0,
        format="%.0f",
        key=volume_key,
    )
    c_ok, c_cancel = st.columns([1, 1], gap="medium")
    if c_ok.button("确认容量并执行", type="primary", use_container_width=True):
        if claim_ui_event("confirm_volume", str(pending_id), sim.state.t):
            result = sim.apply_fluid_bolus_volume(float(volume_ml))
            st.session_state.last_dose_feedback = (
                str(result.get("message", ""))
                if strategy.show_immediate_feedback
                else ""
            )
            st.session_state.last_dose_feedback_level = (
                str(result.get("status", ""))
                if strategy.show_immediate_feedback
                else ""
            )
            st.session_state.pending_volume_action_id = ""
            st.session_state.pending_volume_action_label = ""
            sim.tick()
            finalize_if_done()
        st.rerun()
    if c_cancel.button("取消输入", use_container_width=True):
        st.session_state.pending_volume_action_id = ""
        st.session_state.pending_volume_action_label = ""
        st.rerun()
    return True



def render_steroid_dose_panel(sim: Simulator) -> bool:
    """Render dose-confirmation panel for glucocorticoid adjunct therapy."""
    pending_id = st.session_state.get("pending_steroid_action_id", "")
    if pending_id != "steroid":
        return False

    weight = float(getattr(sim.state, "weight_kg", 0) or 0)
    min_mg = round(1.0 * weight, 1)
    max_mg = round(min(2.0 * weight, 40.0), 1)
    strategy = current_flow_strategy(sim)
    steroid_help = (
        "单位为 mg。确认后系统会判断使用时机与剂量是否符合标准路径。"
        if strategy.show_immediate_feedback
        else "单位为 mg。"
    )
    st.markdown(
        "<div class='dose-card'>"
        "<div class='title'>糖皮质激素：请输入甲泼尼龙剂量</div>"
        f"<div class='text'>{html.escape(steroid_help)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if strategy.show_immediate_feedback:
        st.caption(f"训练提示：本例体重 {weight:g} kg；甲泼尼龙参考范围 {min_mg:g}–{max_mg:g} mg（1–2 mg/kg，单次最大40 mg）。必须在有效快速扩容后使用。")

    steroid_key = f"steroid_dose_mg_{st.session_state.session_id}_{sim.state.t}"
    dose_mg = st.number_input(
        "本次甲泼尼龙剂量（mg）",
        min_value=0.0,
        max_value=500.0,
        value=0.0,
        step=5.0,
        format="%.0f",
        key=steroid_key,
    )
    c_ok, c_cancel = st.columns([1, 1], gap="medium")
    if c_ok.button("确认剂量并执行", type="primary", use_container_width=True):
        if claim_ui_event("confirm_steroid", str(pending_id), sim.state.t):
            result = sim.apply_steroid_dose(float(dose_mg))
            st.session_state.last_dose_feedback = (
                str(result.get("message", ""))
                if strategy.show_immediate_feedback
                else ""
            )
            st.session_state.last_dose_feedback_level = (
                str(result.get("status", ""))
                if strategy.show_immediate_feedback
                else ""
            )
            st.session_state.pending_steroid_action_id = ""
            st.session_state.pending_steroid_action_label = ""
            sim.tick()
            finalize_if_done()
        st.rerun()
    if c_cancel.button("取消输入", use_container_width=True):
        st.session_state.pending_steroid_action_id = ""
        st.session_state.pending_steroid_action_label = ""
        st.rerun()
    return True



def render_prior_experience_survey() -> None:
    """Collect prior-experience items only after baseline performance is locked."""
    render_version_corner()
    phase_label = str(st.session_state.get("assessment_phase", "") or "基线评估")
    st.markdown(f"### {phase_label}补充信息")
    st.info(f"{phase_label}操作评估已完成。请继续完成以下补充信息；本部分不影响本阶段操作评分。")
    yn_options = ["", "是", "否", "不确定"]
    with st.form("baseline_post_experience_survey", clear_on_submit=False):
        c1, c2, c3 = st.columns([1, 1, 1], gap="large")
        prior_training = c1.selectbox(
            "是否接受过过敏反应/过敏性休克相关培训（必填）",
            yn_options,
            index=yn_options.index(st.session_state.get("prior_anaphylaxis_training", ""))
            if st.session_state.get("prior_anaphylaxis_training", "") in yn_options else 0,
        )
        prior_sim = c2.selectbox(
            "是否参加过模拟培训或虚拟仿真培训（必填）",
            yn_options,
            index=yn_options.index(st.session_state.get("prior_simulation_experience", ""))
            if st.session_state.get("prior_simulation_experience", "") in yn_options else 0,
        )
        real_case = c3.selectbox(
            "是否真实参与或见习过过敏反应相关处置（必填）",
            yn_options,
            index=yn_options.index(st.session_state.get("real_case_experience", ""))
            if st.session_state.get("real_case_experience", "") in yn_options else 0,
        )
        submitted = st.form_submit_button(f"提交补充信息并完成{phase_label}", type="primary", use_container_width=True)

    if submitted:
        missing = []
        if not prior_training:
            missing.append("是否接受过相关培训")
        if not prior_sim:
            missing.append("是否参加过模拟/虚拟仿真培训")
        if not real_case:
            missing.append("是否参与或见习过真实病例")
        if missing:
            st.error("请先完整填写：" + "、".join(missing))
            return

        st.session_state.prior_anaphylaxis_training = prior_training.strip()
        st.session_state.prior_simulation_experience = prior_sim.strip()
        st.session_state.real_case_experience = real_case.strip()
        st.session_state.prior_experience_survey_completed = True
        st.session_state.prior_experience_survey_time = datetime.now().isoformat(timespec="seconds")
        st.session_state.baseline_stage_completed = True
        st.session_state.pending_prior_experience_survey = False

        why = st.session_state.get("pending_completion_reason", "standard_assessment_completed") or "standard_assessment_completed"
        report = st.session_state.get("pending_report")
        if not report and st.session_state.active_simulator is not None:
            report = enrich_report(st.session_state.active_simulator.build_report(), end_reason=why)
        elif report:
            report = json.loads(json.dumps(report, ensure_ascii=False))
            report["session"] = build_session_metadata(end_reason=why)
            report["end_reason"] = why
        if report is None:
            st.error("未找到待保存的基线评估报告，请返回重新开始。")
            return
        report["baseline_post_survey"] = {
            "completed": True,
            "completed_time": st.session_state.prior_experience_survey_time,
            "prior_anaphylaxis_training": st.session_state.prior_anaphylaxis_training,
            "prior_simulation_experience": st.session_state.prior_simulation_experience,
            "real_case_experience": st.session_state.real_case_experience,
        }
        _save_and_end_report(report, why)
        st.session_state.pending_completion_reason = ""
        st.session_state.pending_report = None
        st.success(f"{phase_label}阶段已完成。")
        st.rerun()


def visible_actions_for_current_state(sim: Simulator) -> List[Dict[str, Any]]:
    """Hide conditional or already-invalid distractor options.

    V1.3.7: In academy exam mode, unsafe distractors are still available before
    the corresponding core step is completed so they can test baseline judgment,
    but they are hidden after the correct step has already been done. This prevents
    impossible sequences such as: first pause the infusion correctly, then later
    click "continue observing / do not change the infusion", which previously
    could worsen vitals while still allowing a full-score completion.
    """
    visible: List[Dict[str, Any]] = []
    flags = sim.state.flags
    scenario_meta = (sim.scenario or {}).get("scenario", {}) if hasattr(sim, "scenario") else {}
    is_academy = (
        current_flow_strategy(sim).system_mode == "academy"
        or scenario_meta.get("target_group") == "nursing_student"
    )
    for action in sim.actions:
        aid = action.get("id", "")
        if aid == "repeat_epinephrine" and not flags.get("repeat_epi_indicated", False):
            continue
        if is_academy:
            # Once the learner has correctly paused the suspicious infusion, the
            # delay/continue-observation distractor is no longer a meaningful next
            # action and should not remain clickable.
            if aid == "continue_infusion" and flags.get("stopped_infusion", False):
                continue
            # Once direct help has been called, the incorrect indirect-call options
            # should no longer be offered as if they were still available.
            if aid == "send_family_for_help" and flags.get("help_called", False):
                continue
            # Once the critical first response has started, asking history first is
            # no longer a valid initial-priority distractor.
            if aid == "ask_family_first" and (flags.get("stopped_infusion", False) or flags.get("help_called", False)):
                continue
            # If rescue equipment/epinephrine preparation has already been selected,
            # do not keep the "only steroid/antihistamine" priority-error button.
            if aid == "prepare_steroid_antihistamine_only" and flags.get("rescue_equipment_prepared", False):
                continue
        visible.append(action)
    if is_academy:
        return add_assisted_medication_choice(visible, flags)
    return visible


def _academy_stage_report(name: str) -> Optional[Dict[str, Any]]:
    reports = st.session_state.get("academy_stage_reports", {}) or {}
    report = reports.get(name) if isinstance(reports, dict) else None
    return report if isinstance(report, dict) else None


def _start_next_academy_stage(phase: str) -> bool:
    current_phase = str(st.session_state.get("assessment_phase", "") or "")
    if next_academy_phase(current_phase) != str(phase):
        return False
    current_report_key = stage_report_key(current_phase)
    if not current_report_key or _academy_stage_report(current_report_key) is None:
        return False
    if _academy_stage_report(stage_report_key(phase)) is not None:
        return False

    transition_key = "|".join(
        (
            str(st.session_state.get("participant_id", "") or ""),
            current_phase,
            str(phase),
        )
    )
    transition_locks = dict(
        st.session_state.get("academy_transition_locks", {}) or {}
    )
    existing_session_id = str(transition_locks.get(transition_key, "") or "")
    if existing_session_id:
        return bool(
            st.session_state.get("assessment_phase") == phase
            and st.session_state.get("session_id") == existing_session_id
            and isinstance(st.session_state.get("active_simulator"), Simulator)
        )

    scenario_path = scenario_path_for_phase(
        "academy",
        phase,
        current_academy_scenario_id(),
    )
    if scenario_path is None:
        return False
    st.session_state.assessment_phase = phase
    workflow = workflow_for_phase(phase, "academy")
    st.session_state.workflow_mode = workflow.get("mode", "exam")
    st.session_state.workflow_script_role = workflow.get(
        "script_role",
        "academy_initial",
    )
    st.session_state.workflow_display = workflow.get("display", "")
    st.session_state.mode = st.session_state.workflow_mode
    start_simulation(
        scenario_path,
        st.session_state.workflow_mode,
        -1,
        str(st.session_state.get("participant_id", "") or "anonymous"),
    )
    transition_locks[transition_key] = str(
        st.session_state.get("session_id", "") or ""
    )
    st.session_state.academy_transition_locks = transition_locks
    persist_active_training_draft()
    return True


def _reset_academy_flow_for_new_learner() -> None:
    if is_competition_mode():
        setup_competition_participant("academy")
        return
    clear_training_draft()
    st.session_state.profile_completed = False
    st.session_state.active_simulator = None
    st.session_state.active_scenario = None
    st.session_state.ended = False
    st.session_state.academy_flow_page = ""
    st.session_state.academy_stage_reports = {}
    st.session_state.academy_stage_session_ids = {}
    st.session_state.academy_transition_locks = {}
    st.session_state.abandoned_stage_sessions = []
    st.session_state.participant_id = ""
    st.session_state.participant_unique_suffix = ""
    ensure_participant_suffix()


def _render_module_overview(report: Dict[str, Any]) -> None:
    modules = (score_snapshot(report).get("modules") or {})
    if not modules:
        return
    st.markdown("**六维能力概览**")
    st.dataframe(
        [
            {
                "能力": value.get("name", key),
                "得分": f"{value.get('awarded_points', 0)}/{value.get('max_points', 0)}",
                "完成率": f"{value.get('completion_percent', 0)}%",
            }
            for key, value in modules.items()
            if isinstance(value, dict)
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_stage_score_cards(report: Dict[str, Any]) -> None:
    summary = score_snapshot(report)
    c1, c2, c3 = st.columns(3)
    c1.metric("最终得分", f"{summary['score']}/{summary['max_score']}")
    c2.metric("原始得分", summary["raw_score"])
    c3.metric("安全扣分", summary["penalties"])


def _render_stage_feedback(report: Dict[str, Any]) -> None:
    summary = score_snapshot(report)
    issues = [str(item) for item in summary["issues"]]
    missing = [str(item) for item in summary["missing"]]
    left, right = st.columns(2)
    left.markdown("**关键错误行为**")
    left.write("无" if not issues else "；".join(issues))
    right.markdown("**需要改进的项目**")
    right.write("无" if not missing else "；".join(missing))


def _render_three_stage_comparison() -> None:
    rows = []
    for key, label in (
        ("pretest", "课前测评"),
        ("training", "模拟训练"),
        ("posttest", "课后考核"),
    ):
        report = _academy_stage_report(key)
        if report is None:
            continue
        timeline = report.get("key_timeline", {}) or {}
        rows.append(
            {
                "阶段": label,
                "得分": report.get("score", ""),
                "安全扣分": report.get("penalties", 0),
                "有效复评": timeline.get("reassess_count", ""),
            }
        )
    if rows:
        st.markdown("**三阶段简明对比**")
        st.dataframe(rows, use_container_width=True, hide_index=True)


def render_academy_flow_page() -> None:
    page = str(st.session_state.get("academy_flow_page", "") or "")
    reports = st.session_state.get("academy_stage_reports", {}) or {}
    questionnaire_completed = bool(
        st.session_state.get("academy_post_evaluation_completed", False)
    )
    if page and not academy_flow_page_allowed(
        page,
        reports,
        questionnaire_completed=questionnaire_completed,
    ):
        page = latest_allowed_academy_page(
            reports,
            questionnaire_completed=questionnaire_completed,
        )
        st.session_state.academy_flow_page = page
        if not page:
            return
    if (
        page == "questionnaire"
        and not st.session_state.get("pending_academy_post_evaluation", False)
    ):
        st.session_state.academy_flow_page = "posttest_result"
        page = "posttest_result"
    if page == "questionnaire":
        render_academy_post_evaluation_survey()
        return
    if page == "flow_complete":
        st.success("全流程已完成")
        st.write("问卷已提交，训练与评价数据已成功保存。")
        c1, c2, c3 = st.columns(3)
        if c1.button("重新体验", type="primary", use_container_width=True):
            if is_competition_mode():
                setup_competition_participant("academy")
            else:
                _reset_academy_flow_for_new_learner()
            st.rerun()
        if c2.button("更换学员", use_container_width=True):
            _reset_academy_flow_for_new_learner()
            st.rerun()
        if c3.button("返回评审首页" if is_competition_mode() else "返回登记页", use_container_width=True):
            if is_competition_mode():
                clear_training_draft()
                st.session_state.system_mode_selected = False
                st.session_state.profile_completed = False
                st.session_state.active_simulator = None
                st.session_state.academy_flow_page = ""
            else:
                _reset_academy_flow_for_new_learner()
            st.rerun()
        return

    report_key = {
        "pretest_complete": "pretest",
        "training_complete": "training",
        "posttest_result": "posttest",
    }.get(page, "")
    report = _academy_stage_report(report_key)
    if report is None:
        st.error("未找到已保存的阶段报告，请返回登记页后重新进入。")
        return

    title = academy_completion_page_title(page)
    st.markdown(f"### {title}")
    st.success("数据已成功保存。")
    if page == "posttest_result":
        _render_three_stage_comparison()
    _render_stage_score_cards(report)
    _render_module_overview(report)
    _render_stage_feedback(report)

    if page == "training_complete":
        st.write(training_completion_status_text(report))
        st.caption("训练提示已按既有流程逐步呈现；详细教学反馈保留在完整报告中。")
    elif page == "posttest_result":
        st.markdown("**个性化改进建议**")
        issues = report.get("process_safety_issues", []) or []
        missing = report.get("critical_missing", []) or []
        suggestions = list(dict.fromkeys([*map(str, issues), *map(str, missing)]))
        st.write("继续巩固既有正确流程。" if not suggestions else "；".join(suggestions))

    primary_label = {
        "pretest_complete": "进入模拟训练",
        "training_complete": "进入课后考核",
        "posttest_result": "进入SUS及教学体验评价",
    }[page]
    if st.button(primary_label, type="primary", use_container_width=True):
        if page == "posttest_result":
            completion_marker = str(
                (report.get("session", {}) or {}).get("completion_id", "")
                or st.session_state.get("completion_id", "")
            )
            if claim_ui_event(
                "open_questionnaire",
                "posttest_result",
                completion_marker,
            ):
                if _needs_academy_post_evaluation(
                    report,
                    str(st.session_state.get("end_reason", "") or "success"),
                ):
                    st.session_state.pending_academy_post_evaluation = True
                    st.session_state.academy_flow_page = "questionnaire"
                    persist_active_training_draft()
                    st.rerun()
                else:
                    st.error("课后考核尚未满足既有完整完成门控，当前不能进入问卷。")
        else:
            next_phase = next_academy_phase(
                str(st.session_state.get("assessment_phase", "") or "")
            )
            if next_phase and _start_next_academy_stage(next_phase):
                st.rerun()
            else:
                st.error("未找到下一阶段病例，本阶段结果仍已保留。")


def render_simulation() -> None:
    sim: Simulator = st.session_state.active_simulator
    scenario: Dict[str, Any] = st.session_state.active_scenario
    strategy = current_flow_strategy(sim)

    changes = detect_ui_changes(sim)

    compact_header()

    finalize_if_done()
    if st.session_state.active_simulator is None or not st.session_state.get("profile_completed", False):
        st.rerun()
    persist_active_training_draft()
    if st.session_state.get("draft_restored_notice"):
        st.success(st.session_state.draft_restored_notice)
        st.session_state.draft_restored_notice = ""
    if st.session_state.get("pending_prior_experience_survey", False):
        render_prior_experience_survey()
        return
    if (
        current_system_mode() == "academy"
        and st.session_state.get("academy_flow_page")
    ):
        render_academy_flow_page()
        return
    if st.session_state.get("pending_academy_post_evaluation", False):
        render_academy_post_evaluation_survey()
        return
    if st.session_state.ended:
        render_report()
        return

    left, right = st.columns([1.05, 1.20], gap="large")

    with left:
        render_patient_status(sim, scenario, changes)
        render_top_status(sim, changes)

        if strategy.use_guided_prompts:
            item = sim.get_guided_prompt_item() if hasattr(sim, "get_guided_prompt_item") else {"text": sim.get_guided_prompt(), "reason": ""}
            prompt = str(item.get("text", ""))
            reason = str(item.get("reason", ""))
            if prompt:
                reason_html = f"<div class='reason'>{html.escape(reason)}</div>" if reason else ""
                st.markdown(
                    f"<div class='coach-prompt'>"
                    f"<div class='title'>训练提示</div>"
                    f"<div class='text'>{html.escape(prompt)}</div>"
                    f"{reason_html}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        if strategy.show_immediate_feedback:
            with st.expander("完整状态文本", expanded=False):
                st.code(sim.format_status(), language="text")

    with right:
        with st.container(border=True):
            st.markdown(
                f"<div class='action-head'>"
                f"<div class='action-title'>请选择下一步操作</div>"
                f"<div class='action-note'>{html.escape('每次操作后，' + format_time_progress(sim.tick_seconds) if strategy.show_immediate_feedback else '')}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if (
                strategy.show_immediate_feedback
                and st.session_state.get("last_dose_feedback")
            ):
                level = st.session_state.get("last_dose_feedback_level", "")
                msg = st.session_state.get("last_dose_feedback", "")
                if level == "valid":
                    st.success(msg)
                elif level in ["overdose", "invalid", "over"]:
                    st.error(msg)
                elif level in ["underdose", "dose_high", "under", "not_indicated", "timing_error", "used_before_first_line", "role_boundary", "passive_response"]:
                    st.warning(msg)
                else:
                    st.info(msg)

            dose_pending = render_epinephrine_dose_panel(sim)
            volume_pending = render_fluid_bolus_panel(sim)
            steroid_pending = render_steroid_dose_panel(sim)

            actions = visible_actions_for_current_state(sim)
            # V1.3.8: use fewer columns so long action labels are readable.
            # Prior 4-column layout clipped or truncated text during training.
            option_cols = 3
            for idx in range(0, len(actions), option_cols):
                row = st.columns(option_cols, gap="medium")
                for local_index, (col, action) in enumerate(zip(row, actions[idx: idx + option_cols])):
                    full_label = display_action_label(action, sim)
                    aid = action.get("id")
                    button_text = full_label
                    with col:
                        if st.button(
                            button_text,
                            key=f"action_{aid}_{sim.state.t}_{idx}_{local_index}",
                            use_container_width=True,
                            disabled=(dose_pending or volume_pending or steroid_pending),
                        ):
                            st.session_state.last_dose_feedback = ""
                            st.session_state.last_dose_feedback_level = ""
                            if (
                                sim.state.flags.get("cardiac_arrest", False)
                                and not sim.state.flags.get("cpr_done", False)
                                and aid != "cpr"
                            ):
                                # V1.2.6d: once cardiac arrest is present, the immediate
                                # next operation must be CPR. Do not open dose/volume panels
                                # for a non-CPR choice; record terminal death directly.
                                if claim_ui_event("action", str(aid), sim.state.t):
                                    if strategy.system_mode == "academy":
                                        apply_academy_action(sim, str(aid))
                                    else:
                                        sim.apply_action(aid)
                                    finalize_if_done()
                                st.rerun()
                            elif aid in ("im_epinephrine", "repeat_epinephrine"):
                                st.session_state.pending_dose_action_id = aid
                                st.session_state.pending_dose_action_label = full_label
                                st.rerun()
                            elif aid == "fluid_bolus":
                                st.session_state.pending_volume_action_id = aid
                                st.session_state.pending_volume_action_label = full_label
                                st.rerun()
                            elif aid == "steroid":
                                st.session_state.pending_steroid_action_id = aid
                                st.session_state.pending_steroid_action_label = full_label
                                st.rerun()
                            else:
                                if claim_ui_event("action", str(aid), sim.state.t):
                                    if strategy.system_mode == "academy":
                                        action_result = apply_academy_action(
                                            sim,
                                            str(aid),
                                        )
                                    else:
                                        sim.apply_action(aid)
                                        action_result = {
                                            "executed": True,
                                            "feedback": "",
                                        }
                                    if action_result.get("executed", False):
                                        if strategy.show_immediate_feedback:
                                            st.session_state.last_dose_feedback = str(
                                                action_result.get("feedback", "") or ""
                                            )
                                            st.session_state.last_dose_feedback_level = (
                                                "role_boundary"
                                                if aid
                                                == "student_independent_epinephrine"
                                                else (
                                                    "passive_response"
                                                    if aid == "watch_only"
                                                    else ""
                                                )
                                            )
                                        sim.tick()
                                        finalize_if_done()
                                st.rerun()

            render_action_history(sim)

            st.divider()
            c1, c2, c3 = st.columns([1.0, 1.35, 1.95], gap="medium")
            if c1.button(format_time_progress(sim.tick_seconds), use_container_width=True):
                if claim_ui_event("advance_time", "", sim.state.t):
                    sim.tick()
                    finalize_if_done()
                st.rerun()

            if not strategy.allow_manual_completion:
                c2.button("本阶段自动结束", type="primary", use_container_width=True, disabled=True)
                c3.caption("完成必要评估与处置后，系统将结束本阶段。")
            else:
                done, why = sim.is_done()
                is_academy_training = (
                    strategy.system_mode == "academy"
                    and st.session_state.get("assessment_phase") == "模拟训练"
                )
                training_ready = academy_training_ready_for_manual_completion(
                    st.session_state.get("assessment_phase", ""),
                    sim.mode,
                    done,
                    why,
                )
                confirmation_pending = bool(
                    st.session_state.get("manual_completion_confirmation", False)
                )
                if not confirmation_pending and c2.button(
                    "我已确认完成抢救",
                    type="primary",
                    use_container_width=True,
                    disabled=is_academy_training and not training_ready,
                ):
                    st.session_state.manual_completion_confirmation = True
                    st.rerun()
                if confirmation_pending:
                    if is_academy_training:
                        c3.warning(
                            "确认结束本次模拟训练？\n\n"
                            "结束后将保存本阶段训练结果，并进入课后考核入口。"
                        )
                    else:
                        c3.warning("确认结束本阶段吗？未完成的核心步骤将不计分。")
                    continue_col, confirm_col = st.columns(2, gap="small")
                    cancelled = continue_col.button(
                        "继续操作",
                        use_container_width=True,
                    )
                    confirmed = confirm_col.button(
                        "确认结束",
                        type="primary",
                        use_container_width=True,
                    )
                    if cancelled:
                        st.session_state.manual_completion_confirmation = False
                        st.rerun()
                    if confirmed:
                        st.session_state.manual_completion_confirmation = False
                        if claim_ui_event(
                            "confirm_manual_completion",
                            "",
                            sim.state.t,
                        ):
                            if hasattr(sim, "mark_manual_rescue_completion"):
                                sim.mark_manual_rescue_completion()
                            report = enrich_report(
                                sim.build_report(),
                                end_reason="participant_confirmed_rescue_complete",
                            )
                            if _needs_baseline_post_survey(
                                "participant_confirmed_rescue_complete"
                            ):
                                st.session_state.baseline_performance_completed = True
                                st.session_state.pending_prior_experience_survey = True
                                st.session_state.pending_completion_reason = (
                                    "participant_confirmed_rescue_complete"
                                )
                                st.session_state.pending_report = report
                                st.session_state.last_report = report
                            else:
                                if st.session_state.get("assessment_phase") == "基线评估":
                                    st.session_state.baseline_stage_completed = True
                                _save_and_end_report(
                                    report,
                                    "participant_confirmed_rescue_complete",
                                )
                        st.rerun()
                elif is_academy_training and not training_ready:
                    c3.caption("完成必要评估与处置后，可手动确认结束本阶段。")
                elif strategy.show_immediate_feedback:
                    c3.caption("结束本阶段前需要再次确认；未完成标准步骤按0分统计。")


RESULT_END_REASON_LABELS = {
    "success": "标准路径完成，病情稳定",
    "standard_assessment_completed": "普通考核完成：两次复评 + 家属沟通 + SBAR交接",
    "failure": "失败结局",
    "timeout": "超时未完成",
    "manual_end": "手动结束",
    "participant_confirmed_rescue_complete": "受试者确认完成抢救",
    "critical_resuscitated_transfer_picu": "危重抢救后转入PICU",
}


def build_result_page_context(report: Dict[str, Any], end_reason: str) -> Dict[str, Any]:
    session_meta = report.get("session", {}) or {}
    mode_code = str(report.get("mode", "") or session_meta.get("workflow_mode", ""))
    system_mode = str(
        session_meta.get("system_mode", "")
        or current_system_mode()
    )
    try:
        strategy = flow_strategy_for_modes(system_mode, mode_code)
        mode_label = strategy.mode_label
        result_page_behavior = strategy.result_page_behavior
    except FlowStrategyError:
        strategy = None
        mode_label = {
            "coach": "训练模式",
            "exam": "考核模式",
        }.get(mode_code, mode_code or "未记录")
        result_page_behavior = ""
    action_labels: Dict[str, str] = {}
    for entry in report.get("log", []) or []:
        if not isinstance(entry, dict) or entry.get("kind") != "action":
            continue
        action_id = str(entry.get("message", "") or "")
        data = entry.get("data", {}) or {}
        action_labels[action_id] = str(data.get("label", "") or action_id)
    score_awards = (report.get("clinical_pathway_flags", {}) or {}).get("score_awards", []) or []
    scored_actions = []
    for award in score_awards:
        if not isinstance(award, dict):
            continue
        action_id = str(award.get("action_id", "") or award.get("score_key", ""))
        scored_actions.append({
            "操作": action_labels.get(action_id, action_id or "未记录"),
            "得分": f"{award.get('awarded_points', 0)}/{award.get('max_points', 0)}",
            "结果": str(award.get("status", "") or "未记录"),
            "现有反馈": str(award.get("reason", "") or ""),
        })
    return {
        "system_mode": system_mode,
        "system_mode_label": str(session_meta.get("system_mode_label", "") or current_system_mode_label()),
        "assessment_phase": str(session_meta.get("assessment_phase", "") or st.session_state.get("assessment_phase", "")),
        "mode_code": mode_code,
        "mode_label": mode_label,
        "flow_strategy_id": strategy.strategy_id if strategy else "",
        "result_page_behavior": result_page_behavior,
        "scenario_title": str(report.get("scenario_title", "") or "未记录"),
        "completion_label": RESULT_END_REASON_LABELS.get(end_reason, end_reason or "未记录"),
        "score": report.get("score"),
        "max_score": report.get("max_score"),
        "module_summary": report.get("module_score_summary", {}) or {},
        "scored_actions": scored_actions,
        "issues": report.get("process_safety_issues", []) or [],
        "missing": report.get("critical_missing", []) or [],
    }


def render_report() -> None:
    report = st.session_state.last_report
    if not report:
        report = enrich_report(st.session_state.active_simulator.build_report(), end_reason=st.session_state.end_reason)
        st.session_state.last_report = report

    result_context = build_result_page_context(report, st.session_state.end_reason)
    if (
        result_context["result_page_behavior"]
        == "persistent_clinical_result"
    ):
        st.markdown("### 临床模式｜病例结果")
        st.table([
            {"项目": "当前模式", "内容": result_context["system_mode_label"]},
            {"项目": "任务类型", "内容": f"{result_context['assessment_phase']}｜{result_context['mode_label']}"},
            {"项目": "病例名称", "内容": result_context["scenario_title"]},
            {"项目": "完成状态", "内容": result_context["completion_label"]},
        ])
    st.success(f"情景结束：{result_context['completion_label']}")
    session_meta = report.get("session", {}) or {}
    if is_competition_mode():
        st.caption("评审学员-001｜虚拟演示记录")
    else:
        st.caption(
            f"参与者：{session_meta.get('participant_id', '')}｜单位：{session_meta.get('institution', '')}"
            f"｜院区：{session_meta.get('campus', '')}｜科室：{session_meta.get('department', '')}"
            f"｜层级：{session_meta.get('nurse_level', '')}｜会话编号：{session_meta.get('session_id', '')}"
        )
    if st.session_state.get("last_db_save_message"):
        if st.session_state.get("last_db_save_ok"):
            st.success(st.session_state.get("last_db_save_message"))
        else:
            st.warning(st.session_state.get("last_db_save_message"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("结束时间", format_elapsed_time(report.get("end_time_seconds", 0)))
    c2.metric("最终分级", report.get("final_grade", ""))
    c3.metric("得分", f"{report.get('score')}/{report.get('max_score')}")
    c4.metric("扣分", report.get("penalties", 0))

    module_summary = result_context["module_summary"]
    if module_summary:
        st.markdown("**模块评分概览**")
        st.table([
            {
                "模块": v.get("name", k),
                "得分": f"{v.get('awarded_points', 0)}/{v.get('max_points', 0)}",
                "完成率": f"{v.get('completion_percent', 0)}%",
            }
            for k, v in module_summary.items()
        ])

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**关键时间轴**")
        timeline = report.get("key_timeline", {})
        st.table([
            {"指标": k, "时间/次数": format_timeline_value(k, v)}
            for k, v in timeline.items()
        ])
    with right:
        st.markdown("**问题汇总**")
        issues = report.get("process_safety_issues", [])
        missing = report.get("critical_missing", [])
        st.write("过程性安全缺陷：" + ("无" if not issues else "、".join(issues)))
        st.write("缺失关键动作：" + ("无" if not missing else "、".join(missing)))
        flags = report.get("clinical_pathway_flags", {}) or {}
        unfinished = flags.get("unfinished_required_steps", []) or []
        if unfinished:
            st.write("主动确认完成时未完成步骤：" + "、".join(map(str, unfinished)))

        if not is_competition_mode():
            st.download_button(
                "下载本次 JSON 报告",
                data=get_report_download(report),
                file_name=f"{st.session_state.session_id}_report.json",
                mime="application/json",
                use_container_width=True,
            )

    if (
        result_context["result_page_behavior"]
        == "persistent_clinical_result"
    ):
        scored_actions = result_context["scored_actions"]
        st.markdown("**关键操作与现有反馈**")
        if scored_actions:
            st.table(scored_actions)
        else:
            st.info("当前报告未记录独立的关键操作计分明细；总分、模块评分和问题汇总仍按现有报告展示。")

    if not is_competition_mode():
        st.session_state.show_raw_log = st.checkbox("显示完整操作日志", value=st.session_state.show_raw_log)
        if st.session_state.show_raw_log:
            st.json(report.get("log", []))

    if (
        result_context["result_page_behavior"]
        == "persistent_clinical_result"
    ):
        st.divider()
        st.markdown("**后续流程**")
        st.caption("本次临床结果已经保存。当前临床流程未配置独立SUS或教学体验问卷，可继续返回登记选择下一阶段，也可重新开始本阶段。")
        next_col, restart_col, home_col = st.columns(3, gap="medium")
        if next_col.button("继续后续流程", type="primary", use_container_width=True):
            if continue_after_clinical_result(report, st.session_state.end_reason):
                st.rerun()
            else:
                st.error("后续流程暂时无法打开，本次训练结果仍已保留，请稍后重试。")
        if (
            not st.session_state.get("restart_stage_confirmation", False)
            and restart_col.button("重新开始本阶段", use_container_width=True)
        ):
            st.session_state.restart_stage_confirmation = True
            persist_active_training_draft()
            st.rerun()
        if st.session_state.get("restart_stage_confirmation", False):
            st.warning("确认重新开始本阶段？当前阶段已执行操作将被清除。")
            keep_col, confirm_col = st.columns(2, gap="small")
            if keep_col.button("继续当前阶段", use_container_width=True):
                st.session_state.restart_stage_confirmation = False
                persist_active_training_draft()
                st.rerun()
            if confirm_col.button(
                "确认重新开始",
                type="primary",
                use_container_width=True,
            ):
                if claim_ui_event(
                    "restart_completed_stage",
                    "",
                    st.session_state.get("session_id", ""),
                ) and restart_completed_clinical_stage():
                    st.rerun()
                else:
                    st.error("未找到当前病例文件，本次结果仍已保留。")
        if home_col.button("返回首页", use_container_width=True):
            return_home_after_clinical_result()
            st.rerun()


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_compact_css()
    init_session()
    restore_training_draft_from_query()
    if not require_app_access():
        return
    if not render_system_mode_selection_page():
        return
    if not render_academy_scenario_selection_page():
        return
    render_sidebar()
    if st.session_state.page == "管理员后台":
        render_admin_page()
        return
    if not st.session_state.get("profile_completed", False):
        render_participant_entry_page()
        return
    if st.session_state.active_simulator is None:
        render_intro()
    else:
        render_simulation()


if __name__ == "__main__":
    main()
