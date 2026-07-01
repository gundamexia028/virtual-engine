import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402


ACADEMY_SCENARIO = (
    ROOT
    / "peds_anaphylaxis_sim"
    / "scenarios"
    / "peds_ward_allergy_academy_variant.json"
)


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class FakeStreamlit(SimpleNamespace):
    def __init__(self, browser="questionnaire-browser", query=None):
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


def jsonl_records(path):
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


WORKER_CODE = r"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
import streamlit_app as app

class State(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value

app.st = SimpleNamespace(session_state=State(), secrets={})
payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if sys.argv[3] == "training":
    app.save_result_record_local(payload)
else:
    app.save_questionnaire_record_local(payload)
print("WORKER_OK")
"""


RESTORE_WORKER_CODE = r"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
import streamlit_app as app

class State(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value

app.st = SimpleNamespace(
    session_state=State(),
    query_params={app.DRAFT_QUERY_KEY: sys.argv[2]},
    context=SimpleNamespace(headers={
        "User-Agent": "test-browser/questionnaire-browser",
        "Accept-Language": "zh-CN",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }),
    secrets={},
)
app.init_session()
restored = app.restore_training_draft_from_query()
print("RESTORE_RESULT=" + json.dumps({
    "restored": restored,
    "pending": app.st.session_state.get("pending_academy_post_evaluation", False),
    "status": app.st.session_state.get("questionnaire_submit_status", ""),
    "draft": app.st.session_state.get("questionnaire_draft", {}),
}, ensure_ascii=False))
"""


class AcademyQuestionnaireIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v138-questionnaire-", dir=ROOT.parent)
        self.temp_path = Path(self.temp.name)
        self.runs = self.temp_path / "runs"
        self.drafts = self.temp_path / "drafts"
        self.index = self.runs / "training_results.jsonl"
        self.full = self.runs / "training_full_reports.jsonl"
        self.questionnaires = self.runs / app.QUESTIONNAIRE_RESULTS_FILENAME
        self.patches = [
            patch.object(app, "RUNS_DIR", self.runs),
            patch.object(app, "RESULTS_INDEX_PATH", self.index),
            patch.object(app, "RESULTS_FULL_REPORTS_PATH", self.full),
            patch.object(app, "DRAFTS_DIR", self.drafts),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _start_academy(self, mode="exam"):
        fake = FakeStreamlit()
        app.st = fake
        app.init_session()
        fake.session_state.update(
            system_mode="academy",
            system_mode_selected=True,
            participant_type="nursing_student",
            academy_scenario_selected=True,
            academy_scenario_id=app.ACADEMY_SCENARIO_DEFAULT_ID,
            academy_scenario_name="自动测试学院病例",
            profile_completed=True,
            app_unlocked=True,
            page="训练系统",
            assessment_phase="课后考核",
            workflow_mode=mode,
            workflow_display=f"课后考核｜{mode}",
            mode=mode,
            participant_id=f"AUTO-ACADEMY-{mode}",
            participant_initials="AUT",
            school_name="自动测试护理学院",
            student_level="本科",
            student_grade="二年级",
            collection_mode="测试演练",
        )
        app.start_simulation(ACADEMY_SCENARIO, mode, 123, fake.session_state.participant_id)
        report = app.enrich_report(
            fake.session_state.active_simulator.build_report(),
            end_reason="success",
        )
        for index, key in enumerate(app.ACADEMY_POST_TEST_REQUIRED_TIMELINE_KEYS, start=1):
            report.setdefault("key_timeline", {})[key] = index
        return fake, report

    def _enter_questionnaire(self, mode="exam"):
        fake, report = self._start_academy(mode)
        with patch.object(app, "save_report", return_value=("base.json", "base.md")), patch.object(
            app, "save_result_record_database", return_value=(False, "offline")
        ):
            app._save_and_end_report(report, "success")
        self.assertTrue(fake.session_state.result_saved)
        self.assertTrue(fake.session_state.pending_academy_post_evaluation)
        self.assertEqual(len(jsonl_records(self.full)), 1)
        return fake

    def test_academy_training_and_exam_failure_preserve_training_result(self):
        for mode in ("coach", "exam"):
            with self.subTest(mode=mode):
                self.runs.mkdir(parents=True, exist_ok=True)
                for path in (self.index, self.full, self.questionnaires):
                    path.unlink(missing_ok=True)
                fake = self._enter_questionnaire(mode)
                sus = [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]
                teaching = [4] * len(app.TEACHING_EXPERIENCE_ITEMS)
                with patch.object(
                    app,
                    "save_questionnaire_record_local",
                    side_effect=OSError("AUTO_TEST_WRITE_FAILURE"),
                ):
                    ok, message = app.submit_academy_post_evaluation(sus, teaching)
                self.assertFalse(ok)
                self.assertIn("尚未提交成功", message)
                self.assertEqual(len(jsonl_records(self.full)), 1)
                self.assertTrue(fake.session_state.pending_academy_post_evaluation)
                self.assertFalse(fake.session_state.academy_post_evaluation_completed)
                self.assertEqual(fake.session_state.questionnaire_draft["sus"], sus)
                self.assertEqual(fake.session_state.questionnaire_submit_status, "failed")

    def test_refresh_and_process_restart_restore_failed_questionnaire(self):
        fake = self._enter_questionnaire("exam")
        sus = [4] * len(app.SUS_ITEMS)
        teaching = [5] * len(app.TEACHING_EXPERIENCE_ITEMS)
        with patch.object(app, "save_questionnaire_record_local", side_effect=OSError("AUTO_FAIL")):
            app.submit_academy_post_evaluation(sus, teaching)
        draft_id = fake.session_state.draft_id
        self.assertTrue(app._draft_path(draft_id).exists())

        refreshed = FakeStreamlit(query=fake.query_params)
        app.st = refreshed
        app.init_session()
        self.assertTrue(app.restore_training_draft_from_query())
        self.assertTrue(refreshed.session_state.pending_academy_post_evaluation)
        self.assertEqual(refreshed.session_state.questionnaire_draft["teaching"], teaching)

        environment = os.environ.copy()
        environment["PEDSIM_DRAFTS_DIR"] = str(self.drafts)
        environment["PEDSIM_RESULTS_DIR"] = str(self.runs)
        process = subprocess.run(
            [sys.executable, "-c", RESTORE_WORKER_CODE, str(ROOT), draft_id],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        marker = next(
            line for line in process.stdout.splitlines() if line.startswith("RESTORE_RESULT=")
        )
        result = json.loads(marker.split("=", 1)[1])
        self.assertTrue(result["restored"])
        self.assertTrue(result["pending"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["draft"]["sus"], sus)

    def test_questionnaire_retry_succeeds_without_duplicate_training_or_survey(self):
        fake = self._enter_questionnaire("exam")
        sus = [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]
        teaching = [5] * len(app.TEACHING_EXPERIENCE_ITEMS)
        real_save = app.save_questionnaire_record_local

        def persist_then_fail(record):
            real_save(record)
            raise OSError("AUTO_POST_PERSIST_FAILURE")

        with patch.object(app, "save_questionnaire_record_local", side_effect=persist_then_fail):
            first_ok, _ = app.submit_academy_post_evaluation(sus, teaching)
        self.assertFalse(first_ok)
        self.assertEqual(len(jsonl_records(self.questionnaires)), 1)
        self.assertEqual(len(jsonl_records(self.full)), 1)
        first_submission_id = fake.session_state.questionnaire_submission_id

        retry_ok, _ = app.submit_academy_post_evaluation(sus, teaching)
        self.assertTrue(retry_ok)
        self.assertEqual(len(jsonl_records(self.questionnaires)), 1)
        self.assertEqual(len(jsonl_records(self.full)), 1)
        questionnaire = jsonl_records(self.questionnaires)[0]
        self.assertEqual(questionnaire["questionnaire_submission_id"], first_submission_id)
        merged = app.load_full_reports_local(app.create_platform_admin_context())
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["academy_post_evaluation"]["completed"])
        self.assertFalse(fake.session_state.profile_completed)

    def test_duplicate_questionnaire_retry_is_idempotent(self):
        completion_id = "a" * 64
        submission_id = "b" * 64
        record = {
            "schema_version": 1,
            "record_type": "academy_post_evaluation",
            "completion_id": completion_id,
            "questionnaire_submission_id": submission_id,
            "academy_post_evaluation": {"completed": True},
        }
        first = app.save_questionnaire_record_local(record)
        second = app.save_questionnaire_record_local(record)
        self.assertEqual(first, second)
        self.assertEqual(len(jsonl_records(self.questionnaires)), 1)

    def _run_workers(self, payload, kind, count=2):
        payload_path = self.temp_path / f"{kind}-{payload.get('completion_id', 'report')}.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        environment = os.environ.copy()
        environment["PEDSIM_RESULTS_DIR"] = str(self.runs)
        for name in (
            "SUPABASE_URL",
            "SUPABASE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        ):
            environment.pop(name, None)
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", WORKER_CODE, str(ROOT), str(payload_path), kind],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(count)
        ]
        outputs = [process.communicate(timeout=30) for process in processes]
        for process, (stdout, stderr) in zip(processes, outputs):
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn("WORKER_OK", stdout)

    def test_two_processes_save_same_completion_only_once(self):
        completion_id = "c" * 64
        report = {
            "score": 88,
            "max_score": 100,
            "session": {
                "session_id": "AUTO-CONCURRENT-SAME",
                "completion_id": completion_id,
                "system_mode": "academy",
            },
        }
        self._run_workers(report, "training")
        self.assertEqual(len(jsonl_records(self.index)), 1)
        self.assertEqual(len(jsonl_records(self.full)), 1)

    def test_two_processes_save_same_questionnaire_only_once(self):
        record = {
            "schema_version": 1,
            "record_type": "academy_post_evaluation",
            "completion_id": "1" * 64,
            "questionnaire_submission_id": "2" * 64,
            "academy_post_evaluation": {
                "completed": True,
                "sus": {"score": 80.0},
                "teaching_experience": {"total": 40},
            },
        }
        self._run_workers(record, "questionnaire")
        self.assertEqual(len(jsonl_records(self.questionnaires)), 1)

    def test_two_different_completion_ids_are_both_saved(self):
        for value in ("d", "e"):
            report = {
                "score": 90,
                "session": {
                    "session_id": f"AUTO-CONCURRENT-{value}",
                    "completion_id": value * 64,
                    "system_mode": "academy",
                },
            }
            self._run_workers(report, "training", count=1)
        self.assertEqual(len(jsonl_records(self.index)), 2)
        self.assertEqual(len(jsonl_records(self.full)), 2)

    def test_concurrent_jsonl_remains_parseable(self):
        for index in range(8):
            report = {
                "score": index,
                "session": {
                    "session_id": f"AUTO-PARSE-{index}",
                    "completion_id": f"{index:x}" * 64,
                    "system_mode": "academy",
                },
            }
            payload_path = self.temp_path / f"parse-{index}.json"
            payload_path.write_text(json.dumps(report), encoding="utf-8")
        environment = os.environ.copy()
        environment["PEDSIM_RESULTS_DIR"] = str(self.runs)
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    WORKER_CODE,
                    str(ROOT),
                    str(self.temp_path / f"parse-{index}.json"),
                    "training",
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for index in range(8)
        ]
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn("WORKER_OK", stdout)
        self.assertEqual(len(jsonl_records(self.index)), 8)
        self.assertEqual(len(jsonl_records(self.full)), 8)

    def test_corrupt_line_is_skipped_logged_and_existing_data_survives(self):
        self.runs.mkdir(parents=True, exist_ok=True)
        self.index.write_text("{damaged-json\n", encoding="utf-8")
        report = {
            "score": 77,
            "session": {
                "session_id": "AUTO-AFTER-DAMAGE",
                "completion_id": "f" * 64,
                "system_mode": "clinical",
            },
        }
        app.save_result_record_local(report)
        records = app.load_result_records_local(app.create_platform_admin_context())
        self.assertEqual(len(records), 1)
        warning_path = self.runs / app.RESULTS_WARNING_FILENAME
        self.assertTrue(warning_path.exists())
        self.assertIn("training_results.jsonl:1:JSONDecodeError", warning_path.read_text("utf-8"))

    def test_persistence_records_do_not_contain_secrets(self):
        fake = self._enter_questionnaire("exam")
        fake.secrets = {
            "APP_ACCESS_CODE": "AUTO-SECRET-ACCESS",
            "ADMIN_PASSWORD": "AUTO-SECRET-ADMIN",
        }
        ok, _ = app.submit_academy_post_evaluation(
            [3] * len(app.SUS_ITEMS),
            [3] * len(app.TEACHING_EXPERIENCE_ITEMS),
        )
        self.assertTrue(ok)
        stored = self.full.read_text("utf-8") + self.questionnaires.read_text("utf-8")
        self.assertNotIn("AUTO-SECRET-ACCESS", stored)
        self.assertNotIn("AUTO-SECRET-ADMIN", stored)
        self.assertNotIn("APP_ACCESS_CODE", stored)
        self.assertNotIn("ADMIN_PASSWORD", stored)


if __name__ == "__main__":
    unittest.main(verbosity=2)
