import csv
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PEDSIM_RESULTS_DIR", str(ROOT.parent / "V1.3.8_full_workflow_temp"))
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402
from peds_anaphylaxis_sim.engine import Simulator, load_scenario  # noqa: E402
from peds_anaphylaxis_sim.scenario_catalog import (  # noqa: E402
    scenario_definitions,
)


CLINICAL_SCENARIOS = [
    definition.path
    for definition in scenario_definitions("clinical")
]
ACADEMY_SCENARIOS = [
    definition.path
    for definition in scenario_definitions("academy")
]
CLINICAL_STANDARD_ACTIONS = [
    "stop_infusion",
    "call_help",
    "abc_assess",
    "high_flow_oxygen",
    "shock_position",
    "connect_monitor",
    "check_bp",
]
ACADEMY_STANDARD_ACTIONS = [
    "allergy_identification",
    "stop_infusion",
    "call_help",
    "high_flow_oxygen",
    "connect_monitor",
    "check_bp",
    "prepare_rescue_equipment",
    "academy_reassess",
    "academy_family_communication",
    "academy_sbar_handoff",
]


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


def fake_streamlit(state=None, secrets=None):
    return SimpleNamespace(session_state=State(state or {}), secrets=secrets or {})


def tick_action(sim, action_id):
    sim.apply_action(action_id)
    sim.tick()


def run_clinical_standard(path, mode="exam"):
    sim = Simulator(load_scenario(str(path)), mode=mode, seed=123)
    for action_id in CLINICAL_STANDARD_ACTIONS:
        tick_action(sim, action_id)
    target = round(min(0.01 * sim.state.weight_kg, 0.3), 3)
    sim.apply_epinephrine_dose(target)
    sim.tick()
    sim.apply_fluid_bolus_volume(15 * sim.state.weight_kg)
    sim.tick()
    tick_action(sim, "reassess_first")
    tick_action(sim, "bronchodilator")
    sim.apply_steroid_dose(min(1.5 * sim.state.weight_kg, 60))
    sim.tick()
    tick_action(sim, "reassess_second")
    tick_action(sim, "family_explain")
    tick_action(sim, "sbar_handoff")
    return sim


def run_academy_standard(path, mode="exam"):
    sim = Simulator(load_scenario(str(path)), mode=mode, seed=123)
    for action_id in ACADEMY_STANDARD_ACTIONS:
        tick_action(sim, action_id)
    return sim


def synthetic_report(
    session_id,
    system_mode,
    phase,
    institution="",
    department="",
    school="",
    organization_id="",
):
    return {
        "scenario_id": "auto_test_scenario",
        "scenario_title": "自动测试情景",
        "scenario_version": "AUTO-TEST",
        "scenario_script_name": "自动测试脚本",
        "mode": "exam",
        "end_reason": "success",
        "score": 88,
        "raw_score": 88,
        "max_score": 100,
        "penalties": 0,
        "final_grade": "II",
        "end_time_seconds": 300,
        "patient": {"age_years": 8, "weight_kg": 26},
        "key_timeline": {"reassess_count": 2},
        "process_safety_issues": [],
        "critical_missing": [],
        "log": [{"t": 0, "kind": "system", "message": "AUTO_TEST_DATA", "data": {}}],
        "session": {
            "session_id": session_id,
            "participant_id": "AUTO-TEST-001",
            "system_mode": system_mode,
            "organization_type": system_mode,
            "organization_id": organization_id,
            "system_mode_label": "学院模式" if system_mode == "academy" else "临床模式",
            "assessment_phase": phase,
            "collection_mode": "测试演练",
            "collection_mode_code": "pilot",
            "institution": institution,
            "department": department,
            "school_name": school,
            "app_version": "V1.3.8",
            "collection_note": "自动测试数据",
        },
    }


class FullWorkflowValidationTests(unittest.TestCase):
    def test_authentication_accepts_only_configured_random_credentials(self):
        access = "AutoAccess-8Hk3vP0qZ"
        admin = "AutoAdmin-4!Lm8Qx2N7"
        with patch.object(app, "st", fake_streamlit(secrets={"APP_ACCESS_CODE": access, "ADMIN_PASSWORD": admin})):
            configured_access, configured_admin = app.get_auth_credentials()
            self.assertTrue(app.credential_matches(access, configured_access))
            self.assertTrue(app.credential_matches(admin, configured_admin))
            self.assertFalse(app.credential_matches("wrong-code", configured_access))
            self.assertFalse(app.credential_matches("wrong-password", configured_admin))

    def test_registration_required_fields_for_both_modes(self):
        clinical = {
            "system_mode": "clinical", "institution": "", "campus": "", "department": "",
            "participant_initials": "", "participant_id": "", "nurse_level": "",
            "years_experience": "", "years_experience_confirmed": False,
            "assessment_phase": "", "collection_mode": "",
        }
        fake = fake_streamlit(clinical)
        with patch.object(app, "st", fake):
            self.assertEqual(len(app.profile_required_missing()), 10)
            fake.session_state.update(
                institution="自动测试医院", campus="自动测试院区", department="自动测试科室",
                participant_initials="ATC", participant_id="AUTO-CLINICAL-001", nurse_level="N1",
                years_experience=1, years_experience_confirmed=True, assessment_phase="模拟培训",
                collection_mode="测试演练",
            )
            self.assertEqual(app.profile_required_missing(), [])

            fake.session_state = State({
                "system_mode": "academy", "academy_scenario_id": "", "school_name": "",
                "student_level": "", "student_grade": "", "participant_initials": "",
                "participant_id": "", "assessment_phase": "", "collection_mode": "",
            })
            self.assertEqual(len(app.profile_required_missing()), 8)
            fake.session_state.update(
                academy_scenario_id=app.ACADEMY_SCENARIO_DEFAULT_ID,
                school_name="自动测试护理学院", student_level="本科", student_grade="二年级",
                participant_initials="ATA", participant_id="AUTO-ACADEMY-001",
                assessment_phase="模拟训练", collection_mode="测试演练",
            )
            self.assertEqual(app.profile_required_missing(), [])

    def test_training_and_exam_workflow_mapping(self):
        fake = fake_streamlit({
            "system_mode": "academy",
            "academy_scenario_id": app.ACADEMY_SCENARIO_DEFAULT_ID,
        })
        with patch.object(app, "st", fake):
            self.assertEqual(app.workflow_for_phase("基线评估", "clinical")["mode"], "exam")
            self.assertEqual(app.workflow_for_phase("模拟培训", "clinical")["mode"], "coach")
            self.assertEqual(app.workflow_for_phase("培训后考核", "clinical")["script_role"], "variant")
            self.assertEqual(app.workflow_for_phase("课前测评", "academy")["mode"], "exam")
            self.assertEqual(app.workflow_for_phase("模拟训练", "academy")["mode"], "coach")
            self.assertEqual(app.workflow_for_phase("课后考核", "academy")["script_role"], "academy_variant")

    def test_clinical_complete_path_in_training_and_exam(self):
        for scenario_path in CLINICAL_SCENARIOS:
            for mode in ("coach", "exam"):
                with self.subTest(scenario=scenario_path.name, mode=mode):
                    sim = run_clinical_standard(scenario_path, mode)
                    done, reason = sim.is_done()
                    report = sim.build_report()
                    self.assertTrue(done)
                    self.assertEqual(reason, "standard_assessment_completed")
                    self.assertEqual(report["score"], 100)
                    self.assertEqual(report["critical_missing"], [])
                    self.assertGreaterEqual(report["key_timeline"]["reassess_count"], 2)
                    self.assertIsNotNone(report["key_timeline"]["sbar_handoff"])

    def test_academy_complete_path_in_training_and_exam(self):
        for scenario_path in ACADEMY_SCENARIOS:
            for mode in ("coach", "exam"):
                with self.subTest(scenario=scenario_path.name, mode=mode):
                    sim = run_academy_standard(scenario_path, mode)
                    done, reason = sim.is_done()
                    report = sim.build_report()
                    self.assertTrue(done)
                    self.assertEqual(reason, "success")
                    self.assertEqual(report["score"], 100)
                    self.assertEqual(report["critical_missing"], [])
                    self.assertIsNotNone(report["key_timeline"]["academy_reassess"])
                    self.assertIsNotNone(report["key_timeline"]["academy_sbar_handoff"])

    def test_clinical_error_feedback_vitals_and_score_penalty(self):
        sim = Simulator(load_scenario(str(CLINICAL_SCENARIOS[0])), mode="coach", seed=123)
        before = dict(sim.state.vitals)
        tick_action(sim, "continue_infusion")
        underdose = sim.apply_epinephrine_dose(0.01)
        premature_score = sim.score
        sim.apply_action("reassess_first")
        report = sim.build_report()
        self.assertEqual(underdose["status"], "underdose")
        self.assertNotEqual(sim.state.vitals, before)
        self.assertGreater(sim.penalties, 0)
        self.assertEqual(sim.score, premature_score)
        self.assertTrue(report["process_safety_issues"])
        self.assertTrue(any(entry.message == "continue_infusion" for entry in sim.log))

    def test_academy_unsafe_option_has_feedback_and_reduces_score(self):
        sim = Simulator(load_scenario(str(ACADEMY_SCENARIOS[0])), mode="coach", seed=123)
        tick_action(sim, "watch_only")
        for action_id in ACADEMY_STANDARD_ACTIONS:
            tick_action(sim, action_id)
        report = sim.build_report()
        self.assertTrue(sim.state.flags["academy_harmful_action_selected"])
        self.assertLess(report["score"], 100)
        self.assertTrue(report["process_safety_issues"])
        self.assertTrue(any(entry.message == "watch_only" for entry in sim.log))

    def test_score_dimensions_reassessment_and_sbar_prerequisites(self):
        scenario = load_scenario(str(CLINICAL_SCENARIOS[0]))
        early = Simulator(scenario, mode="exam", seed=123)
        early.apply_action("sbar_handoff")
        early.apply_action("family_explain")
        early.apply_action("reassess_second")
        self.assertFalse(early.state.flags.get("sbar_valid", False))
        self.assertFalse(early.state.flags.get("family_valid", False))
        self.assertFalse(early.state.flags.get("second_reassessment_done", False))
        summary = run_clinical_standard(CLINICAL_SCENARIOS[0]).build_report()["module_score_summary"]
        self.assertEqual(len(summary), 5)
        self.assertEqual(sum(item["max_points"] for item in summary.values()), 100)
        self.assertTrue(all(item["completion_percent"] == 100 for item in summary.values()))

    def test_all_declared_actions_execute_without_exception(self):
        exercised = 0
        for path in CLINICAL_SCENARIOS + ACADEMY_SCENARIOS:
            scenario = load_scenario(str(path))
            for action in scenario["actions"]:
                sim = Simulator(scenario, mode="coach", seed=123)
                action_id = action["id"]
                if action_id in ("im_epinephrine", "repeat_epinephrine"):
                    sim.apply_epinephrine_dose(round(min(0.01 * sim.state.weight_kg, 0.3), 3), action_id)
                elif action_id == "fluid_bolus":
                    sim.apply_fluid_bolus_volume(15 * sim.state.weight_kg)
                elif action_id == "steroid":
                    sim.apply_steroid_dose(min(1.5 * sim.state.weight_kg, 60))
                else:
                    sim.apply_action(action_id)
                exercised += 1
        self.assertEqual(exercised, 82)

    def test_sus_teaching_survey_calculation_and_completion_gate(self):
        self.assertEqual(app.compute_sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]), 100.0)
        report = run_academy_standard(ACADEMY_SCENARIOS[1]).build_report()
        fake = fake_streamlit({
            "system_mode": "academy",
            "assessment_phase": "课后考核",
            "academy_post_evaluation_completed": False,
        })
        with patch.object(app, "st", fake):
            self.assertTrue(app._academy_post_test_fully_completed(report, "success"))
            incomplete = json.loads(json.dumps(report))
            incomplete["key_timeline"]["academy_sbar_handoff"] = None
            self.assertFalse(app._academy_post_test_fully_completed(incomplete, "success"))
            self.assertFalse(app._academy_post_test_fully_completed(report, "failure"))

    def test_local_storage_history_and_exports(self):
        with tempfile.TemporaryDirectory(prefix="v138-flow-", dir=ROOT.parent) as temp:
            temp_path = Path(temp)
            with patch.object(app, "RUNS_DIR", temp_path), \
                    patch.object(app, "RESULTS_INDEX_PATH", temp_path / "training_results.jsonl"), \
                    patch.object(app, "RESULTS_FULL_REPORTS_PATH", temp_path / "training_full_reports.jsonl"):
                clinical = synthetic_report(
                    "AUTO-CLINICAL-001", "clinical", "培训后考核",
                    institution="自动测试医院", department="自动测试科室",
                )
                academy = synthetic_report(
                    "AUTO-ACADEMY-001", "academy", "课后考核", school="自动测试护理学院",
                )
                app.save_result_record_local(clinical)
                app.save_result_record_local(academy)
                authorization = app.create_platform_admin_context()
                loaded = app.load_result_records(authorization)
                self.assertEqual(len(loaded), 2)
                rows = list(csv.DictReader(io.StringIO(
                    app.records_to_csv_bytes(loaded, authorization).decode("utf-8-sig")
                )))
                objects = [
                    json.loads(line)
                    for line in app.records_to_jsonl_bytes(
                        loaded,
                        authorization,
                    ).decode("utf-8").splitlines()
                ]
                self.assertEqual(len(rows), 2)
                self.assertEqual(len(objects), 2)
                self.assertEqual({row["system_mode"] for row in rows}, {"clinical", "academy"})

    def test_clinical_academy_scope_isolation(self):
        with tempfile.TemporaryDirectory(prefix="v138-scope-", dir=ROOT.parent) as temp:
            config_path = Path(temp) / "org_access_codes.json"
            clinical_code = secrets.token_urlsafe(24) + "Aa1!"
            academy_code = secrets.token_urlsafe(24) + "Bb2!"
            with patch.object(app.org_credentials, "MIN_ITERATIONS", 1_000):
                config_path.write_text(json.dumps([
                    {
                        "organization_id": "CLN_AUTO_A",
                        "organization_type": "clinical",
                        "role": "clinical_admin",
                        "hospital_name": "自动测试医院",
                        "department_name": "自动测试科室",
                        "credential": app.org_credentials.build_credential(
                            clinical_code,
                            "clinical_admin",
                            "clinical",
                            "CLN_AUTO_A",
                            iterations=1_000,
                        ),
                        "status": "active",
                    },
                    {
                        "organization_id": "ACD_AUTO_A",
                        "organization_type": "academy",
                        "role": "academy_admin",
                        "school_name": "自动测试护理学院",
                        "credential": app.org_credentials.build_credential(
                            academy_code,
                            "academy_admin",
                            "academy",
                            "ACD_AUTO_A",
                            iterations=1_000,
                        ),
                        "status": "active",
                    },
                ], ensure_ascii=False), encoding="utf-8")
                with patch.object(app, "ORG_ACCESS_CODES_PATH", config_path):
                    clinical_scope = app.find_org_scope_by_code(clinical_code)
                    academy_scope = app.find_org_scope_by_code(academy_code)
                    clinical = {
                        "organization_type": "clinical",
                        "organization_id": "CLN_AUTO_A",
                    }
                    academy = {
                        "organization_type": "academy",
                        "organization_id": "ACD_AUTO_A",
                    }
                    self.assertTrue(app.record_matches_scope(clinical, clinical_scope))
                    self.assertFalse(app.record_matches_scope(academy, clinical_scope))
                    self.assertTrue(app.record_matches_scope(academy, academy_scope))
                    self.assertFalse(app.record_matches_scope(clinical, academy_scope))

    def test_no_supabase_local_fallback(self):
        supabase_names = (
            "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_TABLE",
        )
        environment = {key: value for key, value in os.environ.items() if key not in supabase_names}
        with patch.dict(os.environ, environment, clear=True), patch.object(app, "st", fake_streamlit(secrets={})):
            self.assertFalse(app.database_configured())
            self.assertIsNone(app.get_supabase_client())
            ok, message = app.save_result_record_database(
                synthetic_report("AUTO-OFFLINE", "clinical", "模拟培训")
            )
            self.assertFalse(ok)
            self.assertIn("数据库未配置", message)

    def test_invalid_engine_inputs_are_rejected_or_recorded(self):
        sim = Simulator(load_scenario(str(CLINICAL_SCENARIOS[0])), mode="exam", seed=123)
        sim.apply_action("")
        sim.apply_action("not-a-real-action")
        invalid_epi = sim.apply_epinephrine_dose("not-a-number")
        invalid_fluid = sim.apply_fluid_bolus_volume(-1)
        invalid_steroid = sim.apply_steroid_dose("not-a-number")
        self.assertIn(invalid_epi["status"], {"invalid", "underdose"})
        self.assertIn(invalid_fluid["status"], {"invalid", "under", "timing_error"})
        self.assertIn(invalid_steroid["status"], {"invalid", "under", "timing_error"})
        self.assertEqual(sum(entry.message == "unknown_action" for entry in sim.log), 2)

    def test_clinical_completion_enters_saved_result_state(self):
        state = {
            "system_mode": "clinical", "assessment_phase": "模拟培训",
            "session_id": "AUTO-RESULT-PAGE", "result_saved": False,
            "profile_completed": True, "active_simulator": object(),
            "active_scenario": {}, "ended": False,
        }
        fake = fake_streamlit(state)
        with patch.object(app, "st", fake), \
                patch.object(app, "save_report", return_value=("auto.json", "auto.md")), \
                patch.object(app, "save_result_record", return_value=None), \
                patch.object(app, "persist_active_training_draft", return_value=True):
            app._save_and_end_report(
                synthetic_report("AUTO-RESULT-PAGE", "clinical", "模拟培训"), "success"
            )
            self.assertTrue(fake.session_state.profile_completed)
            self.assertIsNotNone(fake.session_state.active_simulator)
            self.assertTrue(fake.session_state.ended)
            self.assertTrue(fake.session_state.result_saved)
            self.assertEqual(fake.session_state.end_reason, "success")
            self.assertEqual(fake.session_state.last_report["score"], 88)

    def test_duplicate_local_save_is_deduplicated(self):
        with tempfile.TemporaryDirectory(prefix="v138-duplicate-", dir=ROOT.parent) as temp:
            temp_path = Path(temp)
            with patch.object(app, "RUNS_DIR", temp_path), \
                    patch.object(app, "RESULTS_INDEX_PATH", temp_path / "training_results.jsonl"), \
                    patch.object(app, "RESULTS_FULL_REPORTS_PATH", temp_path / "training_full_reports.jsonl"):
                report = synthetic_report("AUTO-DUPLICATE", "clinical", "模拟培训")
                app.save_result_record_local(report)
                app.save_result_record_local(report)
                self.assertEqual(
                    len(app.load_full_reports_local(app.create_platform_admin_context())),
                    1,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
