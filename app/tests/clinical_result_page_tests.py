import json
from pathlib import Path
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402


CLINICAL_INITIAL = ROOT / "peds_anaphylaxis_sim" / "scenarios" / "peds_ward_anaphylaxis_iv_initial.json"
ACADEMY_INITIAL = ROOT / "peds_anaphylaxis_sim" / "scenarios" / "peds_ward_allergy_academy_initial.json"


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class FakeStreamlit(SimpleNamespace):
    def __init__(self, browser="browser-a", query=None):
        super().__init__(
            session_state=State(),
            query_params=dict(query or {}),
            context=SimpleNamespace(
                headers={
                    "User-Agent": f"test-browser/{browser}",
                    "Accept-Language": "zh-CN",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                }
            ),
            secrets={},
        )


class ClinicalResultPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v138-result-page-", dir=ROOT.parent)
        self.temp_path = Path(self.temp.name)
        self.patches = [
            patch.object(app, "DRAFTS_DIR", self.temp_path / "drafts"),
            patch.object(app, "RUNS_DIR", self.temp_path / "runs"),
            patch.object(app, "RESULTS_INDEX_PATH", self.temp_path / "training_results.jsonl"),
            patch.object(app, "RESULTS_FULL_REPORTS_PATH", self.temp_path / "training_full_reports.jsonl"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _start(self, system_mode="clinical", mode="coach", phase="模拟培训"):
        fake = FakeStreamlit()
        app.st = fake
        app.init_session()
        fake.session_state.update(
            system_mode=system_mode,
            system_mode_selected=True,
            participant_type="clinical_nurse" if system_mode == "clinical" else "nursing_student",
            academy_scenario_selected=True,
            academy_scenario_id=app.ACADEMY_SCENARIO_DEFAULT_ID,
            academy_scenario_name="严重过敏反应/过敏性休克抢救",
            profile_completed=True,
            app_unlocked=True,
            page="训练系统",
            assessment_phase=phase,
            workflow_mode=mode,
            workflow_display=f"{phase}｜{'训练模式' if mode == 'coach' else '考核模式'}",
            mode=mode,
            participant_id=f"AUTO-{system_mode}-{mode}",
            participant_initials="AUT",
            institution="自动测试医院" if system_mode == "clinical" else "",
            campus="自动测试院区" if system_mode == "clinical" else "",
            department="自动测试科室" if system_mode == "clinical" else "学院教学",
            nurse_level="N1" if system_mode == "clinical" else "",
            years_experience=1,
            years_experience_confirmed=True,
            school_name="自动测试护理学院" if system_mode == "academy" else "",
            student_level="本科" if system_mode == "academy" else "",
            student_grade="二年级" if system_mode == "academy" else "",
            collection_mode="测试演练",
        )
        scenario = CLINICAL_INITIAL if system_mode == "clinical" else ACADEMY_INITIAL
        app.start_simulation(scenario, mode, 123, fake.session_state.participant_id)
        return fake

    def _report(self, fake, reason="participant_confirmed_rescue_complete"):
        return app.enrich_report(fake.session_state.active_simulator.build_report(), end_reason=reason)

    def _complete(self, fake, report, reason="participant_confirmed_rescue_complete"):
        with patch.object(app, "save_report", return_value=("auto.json", "auto.md")), patch.object(
            app, "save_result_record", return_value=None
        ):
            app._save_and_end_report(report, reason)

    def test_clinical_training_completion_enters_result_page_state(self):
        fake = self._start(mode="coach", phase="模拟培训")
        report = self._report(fake)
        self._complete(fake, report)
        self.assertTrue(fake.session_state.ended)
        self.assertTrue(fake.session_state.result_saved)
        self.assertIsNotNone(fake.session_state.active_simulator)
        self.assertEqual(fake.session_state.last_report["mode"], "coach")

    def test_clinical_exam_completion_enters_result_page_state(self):
        fake = self._start(mode="exam", phase="培训后考核")
        report = self._report(fake, "standard_assessment_completed")
        self._complete(fake, report, "standard_assessment_completed")
        self.assertTrue(fake.session_state.ended)
        self.assertEqual(fake.session_state.end_reason, "standard_assessment_completed")
        self.assertEqual(fake.session_state.last_report["mode"], "exam")

    def test_total_score_is_not_recalculated(self):
        fake = self._start(mode="coach")
        sim = fake.session_state.active_simulator
        sim.apply_action("stop_infusion")
        sim.tick()
        report = self._report(fake)
        expected = (report["score"], report["max_score"], report["penalties"])
        self._complete(fake, report)
        actual = fake.session_state.last_report
        self.assertEqual((actual["score"], actual["max_score"], actual["penalties"]), expected)

    def test_module_scores_are_preserved(self):
        fake = self._start(mode="coach")
        fake.session_state.active_simulator.apply_action("stop_infusion")
        report = self._report(fake)
        expected = json.loads(json.dumps(report["module_score_summary"], ensure_ascii=False))
        self._complete(fake, report)
        context = app.build_result_page_context(fake.session_state.last_report, fake.session_state.end_reason)
        self.assertEqual(context["module_summary"], expected)

    def test_completed_result_restores_after_refresh(self):
        fake = self._start(mode="coach")
        report = self._report(fake)
        self._complete(fake, report)
        query = dict(fake.query_params)
        refreshed = FakeStreamlit(query=query)
        app.st = refreshed
        app.init_session()
        self.assertTrue(app.restore_training_draft_from_query())
        self.assertTrue(refreshed.session_state.ended)
        self.assertTrue(refreshed.session_state.result_saved)
        self.assertEqual(refreshed.session_state.last_report["score"], report["score"])

    def test_repeated_completion_does_not_save_twice(self):
        fake = self._start(mode="coach")
        report = self._report(fake)
        with patch.object(app, "save_report", return_value=("auto.json", "auto.md")) as save_report_mock, patch.object(
            app, "save_result_record", return_value=None
        ) as save_record_mock:
            app._save_and_end_report(report, "participant_confirmed_rescue_complete")
            app._save_and_end_report(
                {**report, "score": report["score"] + 1},
                "participant_confirmed_rescue_complete",
            )
        self.assertEqual(save_report_mock.call_count, 1)
        self.assertEqual(save_record_mock.call_count, 1)
        self.assertEqual(fake.session_state.last_report["score"], report["score"])

    def test_return_home_clears_completed_flow(self):
        fake = self._start(mode="coach")
        self._complete(fake, self._report(fake))
        app.return_home_after_clinical_result()
        self.assertFalse(fake.session_state.system_mode_selected)
        self.assertFalse(fake.session_state.profile_completed)
        self.assertIsNone(fake.session_state.active_simulator)
        self.assertFalse(fake.session_state.ended)
        self.assertNotIn(app.DRAFT_QUERY_KEY, fake.query_params)

    def test_restart_creates_new_flow(self):
        fake = self._start(mode="coach")
        self._complete(fake, self._report(fake))
        old_session = fake.session_state.session_id
        old_draft = fake.session_state.draft_id
        self.assertTrue(app.restart_completed_clinical_stage())
        self.assertNotEqual(fake.session_state.session_id, old_session)
        self.assertNotEqual(fake.session_state.draft_id, old_draft)
        self.assertFalse(fake.session_state.ended)
        self.assertFalse(fake.session_state.result_saved)
        self.assertEqual(fake.session_state.active_simulator.state.t, 0)

    def test_follow_up_entry_returns_to_registration(self):
        fake = self._start(mode="coach")
        report = self._report(fake)
        self._complete(fake, report)
        self.assertTrue(app.continue_after_clinical_result(report, fake.session_state.end_reason))
        self.assertFalse(fake.session_state.profile_completed)
        self.assertIsNone(fake.session_state.active_simulator)
        self.assertFalse(fake.session_state.ended)

    def test_follow_up_failure_retains_result(self):
        fake = self._start(mode="coach")
        report = self._report(fake)
        self._complete(fake, report)
        with patch.object(app, "_return_to_registration_after_save", side_effect=RuntimeError("AUTO_TEST")):
            self.assertFalse(app.continue_after_clinical_result(report, fake.session_state.end_reason))
        self.assertTrue(fake.session_state.ended)
        self.assertTrue(fake.session_state.result_saved)
        self.assertEqual(fake.session_state.last_report["score"], report["score"])
        self.assertIsNotNone(fake.session_state.active_simulator)

    def test_academy_training_completion_behavior_is_unchanged(self):
        fake = self._start(system_mode="academy", mode="coach", phase="模拟教学")
        self._complete(fake, self._report(fake))
        self.assertFalse(fake.session_state.profile_completed)
        self.assertIsNone(fake.session_state.active_simulator)
        self.assertFalse(fake.session_state.ended)

    def test_academy_exam_completion_behavior_is_unchanged(self):
        fake = self._start(system_mode="academy", mode="exam", phase="课前测评")
        self._complete(fake, self._report(fake), "standard_assessment_completed")
        self.assertFalse(fake.session_state.profile_completed)
        self.assertIsNone(fake.session_state.active_simulator)
        self.assertFalse(fake.session_state.ended)

    def test_result_context_uses_existing_report_fields(self):
        fake = self._start(mode="coach")
        sim = fake.session_state.active_simulator
        sim.apply_action("stop_infusion")
        sim.tick()
        report = self._report(fake)
        context = app.build_result_page_context(report, "participant_confirmed_rescue_complete")
        self.assertEqual(context["system_mode"], "clinical")
        self.assertEqual(context["mode_label"], "训练模式")
        self.assertEqual(context["scenario_title"], report["scenario_title"])
        self.assertEqual(context["score"], report["score"])
        self.assertEqual(context["module_summary"], report["module_score_summary"])
        self.assertTrue(context["scored_actions"])

    def test_tests_leave_no_result_files(self):
        fake = self._start(mode="coach")
        self._complete(fake, self._report(fake))
        self.assertFalse((self.temp_path / "training_results.jsonl").exists())
        self.assertFalse((self.temp_path / "training_full_reports.jsonl").exists())

    def test_streamlit_ui_clinical_training_reaches_complete_result_page(self):
        access_code = tomllib.loads(
            (ROOT / ".streamlit" / "secrets.toml").read_text(encoding="utf-8")
        )["APP_ACCESS_CODE"]
        app_test = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=20).run()
        app_test.text_input[0].input(access_code)
        app_test.button[0].click().run()

        button_labels = [item.label for item in app_test.button]
        app_test.button[button_labels.index("进入临床模式")].click().run()

        scenario = app.load_scenario(str(CLINICAL_INITIAL))
        simulator = app.Simulator(scenario, mode="coach", seed=123)
        simulator.apply_action("stop_infusion")
        report = simulator.build_report()
        report["session"] = {
            "system_mode": "clinical",
            "system_mode_label": "临床模式",
            "assessment_phase": "模拟培训",
            "workflow_mode": "coach",
            "participant_id": "AUTO-APPTEST",
            "institution": "自动测试医院",
            "campus": "自动测试院区",
            "department": "自动测试科室",
            "nurse_level": "N1/CN1",
            "session_id": "AUTO-APPTEST-RESULT",
        }
        report["end_reason"] = "participant_confirmed_rescue_complete"
        completed_state = {
            "profile_completed": True,
            "active_simulator": simulator,
            "active_scenario": scenario,
            "active_scenario_path": str(CLINICAL_INITIAL),
            "active_script_name": "initial",
            "session_id": "AUTO-APPTEST-RESULT",
            "ended": True,
            "end_reason": "participant_confirmed_rescue_complete",
            "last_report": report,
            "result_saved": True,
            "participant_id": "AUTO-APPTEST",
            "participant_initials": "AUT",
            "institution": "自动测试医院",
            "campus": "自动测试院区",
            "department": "自动测试科室",
            "nurse_level": "N1/CN1",
            "years_experience": 1,
            "years_experience_confirmed": True,
            "collection_mode": "测试演练",
            "assessment_phase": "模拟培训",
            "workflow_mode": "coach",
            "workflow_display": "模拟培训｜训练模式｜初始病例",
            "page": "训练系统",
        }
        for key, value in completed_state.items():
            app_test.session_state[key] = value
        app_test.run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertTrue(any("临床模式｜病例结果" in item.value for item in app_test.markdown))
        result_buttons = [item.label for item in app_test.button]
        self.assertIn("继续后续流程", result_buttons)
        self.assertIn("重新开始本阶段", result_buttons)
        self.assertIn("返回首页", result_buttons)
        self.assertIn("得分", [item.label for item in app_test.metric])
        app_test.run()
        self.assertEqual(len(app_test.exception), 0)
        self.assertTrue(any("临床模式｜病例结果" in item.value for item in app_test.markdown))


if __name__ == "__main__":
    unittest.main(verbosity=2)
