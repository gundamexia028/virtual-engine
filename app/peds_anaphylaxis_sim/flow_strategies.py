from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

try:
    from .scenario_catalog import scenario_definition_for_phase
except ImportError:  # pragma: no cover - direct engine.py compatibility
    from scenario_catalog import scenario_definition_for_phase  # type: ignore


class FlowStrategyError(ValueError):
    pass


@dataclass(frozen=True)
class SessionRecoveryPolicy:
    restore_in_progress: bool
    preserve_completed_result: bool
    preserve_pending_questionnaire: bool
    clear_on_return_home: bool
    snapshot_schema_version: int = 1


@dataclass(frozen=True)
class SimulationFlowStrategy:
    strategy_id: str
    system_mode: str
    simulator_mode: str
    mode_label: str
    workflow_mode_label: str
    show_immediate_feedback: bool
    score_presentation: str
    error_handling: str
    end_condition_policy: str
    allow_manual_completion: bool
    allow_cli_manual_completion: bool
    result_page_behavior: str
    questionnaire_transitions: Tuple[Tuple[str, str], ...]
    recovery: SessionRecoveryPolicy
    use_guided_prompts: bool
    shuffle_actions: bool
    use_neutral_action_labels: bool

    def questionnaire_transition_for_phase(self, phase: str) -> str:
        return dict(self.questionnaire_transitions).get(str(phase), "none")


@dataclass(frozen=True)
class SystemModeDefinition:
    system_mode: str
    label: str
    subtitle: str
    participant_type: str


@dataclass(frozen=True)
class FlowPhaseDefinition:
    system_mode: str
    phase: str
    strategy_id: str
    script_label: str
    task: str


TRAINING_RECOVERY = SessionRecoveryPolicy(
    restore_in_progress=True,
    preserve_completed_result=False,
    preserve_pending_questionnaire=False,
    clear_on_return_home=True,
)
CLINICAL_RESULT_RECOVERY = SessionRecoveryPolicy(
    restore_in_progress=True,
    preserve_completed_result=True,
    preserve_pending_questionnaire=False,
    clear_on_return_home=True,
)
ACADEMY_EXAM_RECOVERY = SessionRecoveryPolicy(
    restore_in_progress=True,
    preserve_completed_result=False,
    preserve_pending_questionnaire=True,
    clear_on_return_home=True,
)


FLOW_STRATEGIES: Tuple[SimulationFlowStrategy, ...] = (
    SimulationFlowStrategy(
        strategy_id="clinical_training",
        system_mode="clinical",
        simulator_mode="coach",
        mode_label="训练模式",
        workflow_mode_label="训练模式",
        show_immediate_feedback=True,
        score_presentation="live",
        error_handling="immediate_explanatory",
        end_condition_policy="scenario_standard_or_manual",
        allow_manual_completion=True,
        allow_cli_manual_completion=True,
        result_page_behavior="persistent_clinical_result",
        questionnaire_transitions=(),
        recovery=CLINICAL_RESULT_RECOVERY,
        use_guided_prompts=True,
        shuffle_actions=False,
        use_neutral_action_labels=False,
    ),
    SimulationFlowStrategy(
        strategy_id="clinical_exam",
        system_mode="clinical",
        simulator_mode="exam",
        mode_label="考核模式",
        workflow_mode_label="考试模式",
        show_immediate_feedback=False,
        score_presentation="result_only",
        error_handling="deferred_record_only",
        end_condition_policy="scenario_standard_or_manual",
        allow_manual_completion=True,
        allow_cli_manual_completion=False,
        result_page_behavior="persistent_clinical_result",
        questionnaire_transitions=(
            ("基线评估", "prior_experience_survey"),
        ),
        recovery=CLINICAL_RESULT_RECOVERY,
        use_guided_prompts=False,
        shuffle_actions=True,
        use_neutral_action_labels=False,
    ),
    SimulationFlowStrategy(
        strategy_id="academy_training",
        system_mode="academy",
        simulator_mode="coach",
        mode_label="训练模式",
        workflow_mode_label="训练模式",
        show_immediate_feedback=True,
        score_presentation="live",
        error_handling="immediate_explanatory",
        end_condition_policy="scenario_standard_or_manual",
        allow_manual_completion=True,
        allow_cli_manual_completion=True,
        result_page_behavior="return_to_registration",
        questionnaire_transitions=(),
        recovery=TRAINING_RECOVERY,
        use_guided_prompts=True,
        shuffle_actions=False,
        use_neutral_action_labels=False,
    ),
    SimulationFlowStrategy(
        strategy_id="academy_exam",
        system_mode="academy",
        simulator_mode="exam",
        mode_label="考核模式",
        workflow_mode_label="考试模式",
        show_immediate_feedback=False,
        score_presentation="result_only",
        error_handling="deferred_record_only",
        end_condition_policy="scenario_auto_only",
        allow_manual_completion=False,
        allow_cli_manual_completion=False,
        result_page_behavior="return_to_registration",
        questionnaire_transitions=(
            ("课前测评", "prior_experience_survey"),
            ("课后考核", "academy_post_evaluation"),
        ),
        recovery=ACADEMY_EXAM_RECOVERY,
        use_guided_prompts=False,
        shuffle_actions=True,
        use_neutral_action_labels=True,
    ),
)


SYSTEM_MODE_DEFINITIONS: Tuple[SystemModeDefinition, ...] = (
    SystemModeDefinition(
        system_mode="clinical",
        label="临床模式",
        subtitle="面向临床护士/低年资护士，保留原严重过敏反应动态分支处置流程。",
        participant_type="clinical_nurse",
    ),
    SystemModeDefinition(
        system_mode="academy",
        label="学院模式",
        subtitle="面向在校护生，进入通用情景库后选择教学情景；当前仅开放严重过敏反应/过敏性休克抢救。",
        participant_type="nursing_student",
    ),
)


FLOW_PHASE_DEFINITIONS: Tuple[FlowPhaseDefinition, ...] = (
    FlowPhaseDefinition(
        system_mode="clinical",
        phase="基线评估",
        strategy_id="clinical_exam",
        script_label="初始病例",
        task="请按考试要求独立完成初始病例处置。系统不会提供步骤原因提示。",
    ),
    FlowPhaseDefinition(
        system_mode="clinical",
        phase="模拟培训",
        strategy_id="clinical_training",
        script_label="初始病例",
        task="请在训练模式下完成初始病例。系统将提供必要的步骤提示与复盘信息。",
    ),
    FlowPhaseDefinition(
        system_mode="clinical",
        phase="培训后考核",
        strategy_id="clinical_exam",
        script_label="变体病例 Variant A",
        task="请按考试要求独立完成变体病例处置。系统不会提供步骤原因提示。",
    ),
    FlowPhaseDefinition(
        system_mode="academy",
        phase="课前测评",
        strategy_id="academy_exam",
        script_label="过敏性休克抢救基础病例",
        task="请根据患儿表现独立判断当前异常情况，并完成暂停可疑输入、呼救、氧疗监测、抢救配合、复评与汇报；不要求护生独立用药。",
    ),
    FlowPhaseDefinition(
        system_mode="academy",
        phase="模拟训练",
        strategy_id="academy_training",
        script_label="过敏性休克抢救基础病例",
        task="请在训练模式下完成过敏性休克抢救基础教学训练。系统将提供步骤提示与原因说明。",
    ),
    FlowPhaseDefinition(
        system_mode="academy",
        phase="课后考核",
        strategy_id="academy_exam",
        script_label="过敏性休克抢救变体病例",
        task="请按考试要求独立完成变体病例，重点体现严重过敏反应早期识别、抢救启动、规范汇报与协作意识。",
    ),
)


def validate_flow_strategies(
    strategies: Sequence[SimulationFlowStrategy],
    phases: Sequence[FlowPhaseDefinition] = FLOW_PHASE_DEFINITIONS,
) -> Tuple[SimulationFlowStrategy, ...]:
    entries = tuple(strategies)
    if len(entries) != 4:
        raise FlowStrategyError("Exactly four simulation flow strategies are required.")

    ids = [entry.strategy_id for entry in entries]
    combinations = [
        (entry.system_mode, entry.simulator_mode)
        for entry in entries
    ]
    if len(ids) != len(set(ids)):
        raise FlowStrategyError("Flow strategy ids must be unique.")
    if len(combinations) != len(set(combinations)):
        raise FlowStrategyError("Flow strategy mode combinations must be unique.")
    if set(combinations) != {
        ("clinical", "coach"),
        ("clinical", "exam"),
        ("academy", "coach"),
        ("academy", "exam"),
    }:
        raise FlowStrategyError("Flow strategies must cover all four current flows.")

    strategy_by_id = {entry.strategy_id: entry for entry in entries}
    phase_keys: set[tuple[str, str]] = set()
    for phase in phases:
        key = (phase.system_mode, phase.phase)
        if key in phase_keys:
            raise FlowStrategyError(f"Duplicate flow phase mapping: {key}")
        phase_keys.add(key)
        strategy = strategy_by_id.get(phase.strategy_id)
        if strategy is None or strategy.system_mode != phase.system_mode:
            raise FlowStrategyError(
                f"Flow phase strategy is invalid: {phase.system_mode}/{phase.phase}"
            )

    return entries


_VALIDATED_STRATEGIES = validate_flow_strategies(FLOW_STRATEGIES)
_BY_ID = {entry.strategy_id: entry for entry in _VALIDATED_STRATEGIES}
_BY_MODE = {
    (entry.system_mode, entry.simulator_mode): entry
    for entry in _VALIDATED_STRATEGIES
}
_SYSTEM_MODES = {
    entry.system_mode: entry
    for entry in SYSTEM_MODE_DEFINITIONS
}
_PHASES = {
    (entry.system_mode, entry.phase): entry
    for entry in FLOW_PHASE_DEFINITIONS
}


def flow_strategies() -> Tuple[SimulationFlowStrategy, ...]:
    return _VALIDATED_STRATEGIES


def flow_strategy(strategy_id: str) -> SimulationFlowStrategy:
    try:
        return _BY_ID[str(strategy_id)]
    except KeyError as exc:
        raise FlowStrategyError(f"Unknown flow strategy: {strategy_id}") from exc


def flow_strategy_for_modes(
    system_mode: str,
    simulator_mode: str,
) -> SimulationFlowStrategy:
    try:
        return _BY_MODE[(str(system_mode), str(simulator_mode))]
    except KeyError as exc:
        raise FlowStrategyError(
            f"Unknown flow strategy modes: {system_mode}/{simulator_mode}"
        ) from exc


def infer_system_mode(scenario: Mapping[str, Any]) -> str:
    metadata = scenario.get("scenario", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    target_group = str(metadata.get("target_group", ""))
    issue_profile = str(metadata.get("issue_profile", ""))
    return (
        "academy"
        if target_group == "nursing_student" or issue_profile.startswith("academy")
        else "clinical"
    )


def flow_strategy_for_scenario(
    scenario: Mapping[str, Any],
    simulator_mode: str,
) -> SimulationFlowStrategy:
    return flow_strategy_for_modes(
        infer_system_mode(scenario),
        simulator_mode,
    )


def system_mode_options() -> Dict[str, Dict[str, str]]:
    return {
        key: {
            "label": value.label,
            "subtitle": value.subtitle,
            "participant_type": value.participant_type,
        }
        for key, value in _SYSTEM_MODES.items()
    }


def phase_options(system_mode: str) -> Tuple[str, ...]:
    mode = str(system_mode)
    options = tuple(
        entry.phase
        for entry in FLOW_PHASE_DEFINITIONS
        if entry.system_mode == mode
    )
    if not options:
        raise FlowStrategyError(f"Unknown system mode: {system_mode}")
    return options


def flow_phase_definition(
    system_mode: str,
    phase: Optional[str] = None,
) -> FlowPhaseDefinition:
    mode = str(system_mode)
    options = phase_options(mode)
    resolved_phase = str(phase) if str(phase or "") in options else options[0]
    return _PHASES[(mode, resolved_phase)]


def flow_strategy_for_phase(
    system_mode: str,
    phase: Optional[str] = None,
) -> SimulationFlowStrategy:
    return flow_strategy(
        flow_phase_definition(system_mode, phase).strategy_id
    )


def build_workflow_config(
    system_mode: str,
    phase: Optional[str],
    *,
    library_id: str = "",
    scenario_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    phase_definition = flow_phase_definition(system_mode, phase)
    strategy = flow_strategy(phase_definition.strategy_id)
    scenario_definition = scenario_definition_for_phase(
        strategy.system_mode,
        phase_definition.phase,
        library_id if strategy.system_mode == "academy" else "",
    )

    result = {
        "strategy_id": strategy.strategy_id,
        "mode": strategy.simulator_mode,
        "script_role": scenario_definition.script_role,
        "script_label": phase_definition.script_label,
        "display": (
            f"{phase_definition.phase}｜{strategy.workflow_mode_label}｜"
            f"{phase_definition.script_label}"
        ),
        "task": phase_definition.task,
    }
    if strategy.system_mode != "academy":
        return result

    metadata = dict(scenario_metadata or {})
    scenario_name = str(metadata.get("name", "") or "学院情景")
    result.update({
        "display": (
            f"{phase_definition.phase}｜{strategy.workflow_mode_label}｜"
            f"{scenario_name}｜{phase_definition.script_label}"
        ),
        "scenario_id": str(metadata.get("id", "") or library_id),
        "scenario_name": str(metadata.get("name", "")),
        "scenario_category": str(metadata.get("category", "")),
        "course_type": str(metadata.get("course_type", "")),
        "difficulty": str(metadata.get("difficulty", "")),
    })
    return result
