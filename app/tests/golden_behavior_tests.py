from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault(
    "PEDSIM_RESULTS_DIR",
    str(ROOT.parent / "V1.3.8_golden_behavior_temp"),
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402
from peds_anaphylaxis_sim.engine import Simulator  # noqa: E402
from peds_anaphylaxis_sim.scenario_catalog import (  # noqa: E402
    scenario_definition,
)
from peds_anaphylaxis_sim.scenario_loader import (  # noqa: E402
    load_registered_scenario,
)


GOLDEN_PATH = ROOT / "tests" / "golden" / "v1_3_8_behavior_baseline.json"
GOLDEN_CONTRACT_VERSION = 1

CLINICAL_STANDARD_STEPS = [
    ("action", "stop_infusion"),
    ("action", "call_help"),
    ("action", "abc_assess"),
    ("action", "high_flow_oxygen"),
    ("action", "shock_position"),
    ("action", "connect_monitor"),
    ("action", "check_bp"),
    ("epinephrine", "im_epinephrine"),
    ("fluid", "fluid_bolus"),
    ("action", "reassess_first"),
    ("action", "bronchodilator"),
    ("steroid", "steroid"),
    ("action", "reassess_second"),
    ("action", "family_explain"),
    ("action", "sbar_handoff"),
]
ACADEMY_STANDARD_STEPS = [
    ("action", "allergy_identification"),
    ("action", "stop_infusion"),
    ("action", "call_help"),
    ("action", "high_flow_oxygen"),
    ("action", "connect_monitor"),
    ("action", "check_bp"),
    ("action", "prepare_rescue_equipment"),
    ("action", "academy_reassess"),
    ("action", "academy_family_communication"),
    ("action", "academy_sbar_handoff"),
]

FLOW_DEFINITIONS = {
    "clinical_training": {
        "system_mode": "clinical",
        "system_mode_label": "临床模式",
        "assessment_phase": "模拟培训",
        "workflow_mode": "coach",
        "scenario_id": "peds_ward_anaphylaxis_iv_initial",
        "standard_steps": CLINICAL_STANDARD_STEPS,
        "error_prefix": [("action", "continue_infusion")],
        "branch_prefix": [
            ("action", "remove_iv"),
            ("action", "establish_iv"),
        ],
    },
    "clinical_exam": {
        "system_mode": "clinical",
        "system_mode_label": "临床模式",
        "assessment_phase": "培训后考核",
        "workflow_mode": "exam",
        "scenario_id": "peds_ward_anaphylaxis_iv_variantA",
        "standard_steps": CLINICAL_STANDARD_STEPS,
        "error_prefix": [("action", "continue_infusion")],
        "branch_prefix": [
            ("action", "remove_iv"),
            ("action", "establish_iv"),
        ],
    },
    "academy_training": {
        "system_mode": "academy",
        "system_mode_label": "学院模式",
        "assessment_phase": "模拟训练",
        "workflow_mode": "coach",
        "scenario_id": "peds_ward_allergy_academy_initial",
        "standard_steps": ACADEMY_STANDARD_STEPS,
        "error_prefix": [("action", "watch_only")],
        "branch_prefix": [("action", "student_independent_epinephrine")],
    },
    "academy_exam": {
        "system_mode": "academy",
        "system_mode_label": "学院模式",
        "assessment_phase": "课后考核",
        "workflow_mode": "exam",
        "scenario_id": "peds_ward_allergy_academy_variant",
        "standard_steps": ACADEMY_STANDARD_STEPS,
        "error_prefix": [("action", "watch_only")],
        "branch_prefix": [("action", "student_independent_epinephrine")],
    },
}
PATH_KINDS = ("ideal", "typical_error", "critical_branch")
FORBIDDEN_SNAPSHOT_TERMS = (
    "APP_ACCESS_CODE",
    "ADMIN_PASSWORD",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "SERVICE_ROLE",
    "session_id",
    "draft_id",
    "completion_id",
    "questionnaire_submission_id",
    "timestamp",
    "created_at",
    "updated_at",
    "D:\\",
    "C:\\",
)


def _apply_step(sim: Simulator, step: tuple[str, str]) -> str:
    step_type, action_id = step
    if step_type == "action":
        sim.apply_action(action_id)
    elif step_type == "epinephrine":
        target = round(min(0.01 * sim.state.weight_kg, 0.3), 3)
        sim.apply_epinephrine_dose(target, action_id)
    elif step_type == "fluid":
        sim.apply_fluid_bolus_volume(15 * sim.state.weight_kg)
    elif step_type == "steroid":
        sim.apply_steroid_dose(min(1.5 * sim.state.weight_kg, 60))
    else:
        raise AssertionError(f"Unknown golden step type: {step_type}")
    sim.tick()
    return action_id


def _normalized_module_scores(report: dict) -> dict:
    return {
        module_id: {
            "max_points": summary.get("max_points", 0),
            "awarded_points": summary.get("awarded_points", 0),
            "completion_percent": summary.get("completion_percent", 0),
        }
        for module_id, summary in sorted(
            (report.get("module_score_summary", {}) or {}).items()
        )
    }


def _normalized_feedback(report: dict) -> dict:
    notable_events = []
    for entry in report.get("log", []) or []:
        if entry.get("kind") != "action":
            continue
        data = entry.get("data", {}) or {}
        item = {"action_id": entry.get("message", "")}
        for key in ("status", "reason", "feedback"):
            if data.get(key) not in (None, ""):
                item[key] = data[key]
        if len(item) > 1:
            notable_events.append(item)
    return {
        "notable_events": notable_events,
        "process_safety_issues": list(report.get("process_safety_issues", []) or []),
        "critical_missing": list(report.get("critical_missing", []) or []),
    }


def build_normalized_snapshot(flow_id: str, path_kind: str) -> dict:
    definition = FLOW_DEFINITIONS[flow_id]
    catalog_entry = scenario_definition(definition["scenario_id"])
    sim = Simulator(
        load_registered_scenario(catalog_entry.scenario_id),
        mode=definition["workflow_mode"],
        seed=123,
    )

    if path_kind == "ideal":
        prefix = []
    elif path_kind == "typical_error":
        prefix = definition["error_prefix"]
    elif path_kind == "critical_branch":
        prefix = definition["branch_prefix"]
    else:
        raise AssertionError(f"Unknown path kind: {path_kind}")

    executed = []
    for step in [*prefix, *definition["standard_steps"]]:
        executed.append(_apply_step(sim, step))

    done, end_reason = sim.is_done()
    report = sim.build_report()
    report["session"] = {
        "system_mode": definition["system_mode"],
        "system_mode_label": definition["system_mode_label"],
        "assessment_phase": definition["assessment_phase"],
        "workflow_mode": definition["workflow_mode"],
    }
    result_context = app.build_result_page_context(report, end_reason)
    completion_marker = "completed" if done else "incomplete"
    return {
        "contract_version": GOLDEN_CONTRACT_VERSION,
        "flow_id": flow_id,
        "path_kind": path_kind,
        "scenario_file": catalog_entry.file_name,
        "scenario_id": report["scenario_id"],
        "system_mode": definition["system_mode"],
        "workflow_mode": definition["workflow_mode"],
        "node_sequence": [
            "baseline",
            *[f"action:{action_id}" for action_id in executed],
            f"result:{completion_marker}",
        ],
        "key_choices": list(executed),
        "score": {
            "total": report["score"],
            "raw": report["raw_score"],
            "maximum": report["max_score"],
            "penalties": report["penalties"],
            "dimensions": _normalized_module_scores(report),
        },
        "final_state": {
            "time_seconds": report["end_time_seconds"],
            "grade": report["final_grade"],
            "vitals": copy.deepcopy(report["final_vitals"]),
            "symptoms": copy.deepcopy(report["final_symptoms"]),
            "outcome_class": report["outcome_class"],
        },
        "completion": {
            "done": done,
            "end_reason": end_reason,
            "critical_missing": list(report["critical_missing"]),
        },
        "key_feedback": _normalized_feedback(report),
        "result_page": {
            "system_mode": result_context["system_mode"],
            "system_mode_label": result_context["system_mode_label"],
            "assessment_phase": result_context["assessment_phase"],
            "mode_code": result_context["mode_code"],
            "mode_label": result_context["mode_label"],
            "scenario_title": result_context["scenario_title"],
            "completion_label": result_context["completion_label"],
            "score": result_context["score"],
            "max_score": result_context["max_score"],
            "module_ids": sorted(_normalized_module_scores(report)),
            "issues": list(result_context["issues"]),
            "missing": list(result_context["missing"]),
        },
    }


def build_all_snapshots() -> dict:
    return {
        f"{flow_id}__{path_kind}": build_normalized_snapshot(flow_id, path_kind)
        for flow_id in FLOW_DEFINITIONS
        for path_kind in PATH_KINDS
    }


def load_golden_snapshots() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


class GoldenBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = load_golden_snapshots()
        cls.actual = build_all_snapshots()

    def test_snapshot_manifest_covers_four_flows_and_twelve_paths(self):
        expected_names = {
            f"{flow_id}__{path_kind}"
            for flow_id in FLOW_DEFINITIONS
            for path_kind in PATH_KINDS
        }
        self.assertEqual(set(self.golden), expected_names)
        self.assertEqual(set(self.actual), expected_names)

    def test_snapshots_exclude_nondeterministic_and_sensitive_fields(self):
        serialized = json.dumps(self.golden, ensure_ascii=False, sort_keys=True)
        for forbidden in FORBIDDEN_SNAPSHOT_TERMS:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_result_page_core_fields_are_locked_for_every_path(self):
        required = {
            "system_mode",
            "system_mode_label",
            "assessment_phase",
            "mode_code",
            "mode_label",
            "scenario_title",
            "completion_label",
            "score",
            "max_score",
            "module_ids",
            "issues",
            "missing",
        }
        for name, snapshot in self.golden.items():
            with self.subTest(snapshot=name):
                self.assertEqual(set(snapshot["result_page"]), required)

    def test_all_golden_paths_reach_a_declared_completion(self):
        for name, snapshot in self.golden.items():
            with self.subTest(snapshot=name):
                self.assertTrue(snapshot["completion"]["done"])
                self.assertIn(
                    snapshot["completion"]["end_reason"],
                    {"success", "standard_assessment_completed"},
                )


def _add_path_test(snapshot_name: str) -> None:
    def test_path(self):
        self.assertEqual(self.actual[snapshot_name], self.golden[snapshot_name])

    test_path.__name__ = f"test_golden_{snapshot_name}"
    test_path.__doc__ = f"Lock normalized behavior for {snapshot_name}."
    setattr(GoldenBehaviorTests, test_path.__name__, test_path)


for _flow_id in FLOW_DEFINITIONS:
    for _path_kind in PATH_KINDS:
        _add_path_test(f"{_flow_id}__{_path_kind}")


if __name__ == "__main__":
    if "--emit" in sys.argv:
        print(
            json.dumps(
                build_all_snapshots(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        unittest.main(verbosity=2)
