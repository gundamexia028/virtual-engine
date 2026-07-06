import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402
from academy_flow import (  # noqa: E402
    completion_page_for_phase,
    next_academy_phase,
    score_snapshot,
    stage_report_key,
)
from runtime_config import (  # noqa: E402
    RuntimeConfigurationError,
    competition_credentials,
    deployment_setting,
    resolve_app_mode,
)
from storage_adapters import (  # noqa: E402
    CompetitionStorageAdapter,
    ProductionStorageAdapter,
    build_storage_adapter,
)
from ui_labels import academy_action_short_label, format_elapsed_time  # noqa: E402


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class RuntimeModeTests(unittest.TestCase):
    def test_default_mode_is_production(self):
        self.assertEqual(resolve_app_mode(secrets={}, environ={}), "production")

    def test_explicit_competition_mode(self):
        self.assertEqual(
            resolve_app_mode(secrets={"APP_MODE": "competition"}, environ={}),
            "competition",
        )

    def test_secrets_take_priority_over_environment(self):
        self.assertEqual(
            resolve_app_mode(
                secrets={"APP_MODE": "production"},
                environ={"APP_MODE": "competition"},
            ),
            "production",
        )

    def test_legacy_true_translates_only_when_app_mode_missing(self):
        self.assertEqual(
            resolve_app_mode(
                secrets={"PEDSIM_PUBLIC_REVIEW_MODE": True},
                environ={},
            ),
            "competition",
        )

    def test_explicit_mode_overrides_legacy_flag(self):
        self.assertEqual(
            resolve_app_mode(
                secrets={
                    "APP_MODE": "production",
                    "PEDSIM_PUBLIC_REVIEW_MODE": True,
                },
                environ={},
            ),
            "production",
        )

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(RuntimeConfigurationError):
            resolve_app_mode(secrets={"APP_MODE": "review"}, environ={})

    def test_deployment_setting_uses_default_last(self):
        self.assertEqual(
            deployment_setting(
                "MISSING",
                secrets={},
                environ={},
                default="safe-default",
            ),
            "safe-default",
        )


class CompetitionCredentialTests(unittest.TestCase):
    def test_review_code_is_loaded(self):
        credentials = competition_credentials(
            secrets={"COMPETITION_REVIEW_CODE": "review-value"},
            environ={},
        )
        self.assertEqual(credentials.review_code, "review-value")
        self.assertTrue(credentials.review_configured)

    def test_missing_review_code_is_not_defaulted(self):
        credentials = competition_credentials(secrets={}, environ={})
        self.assertFalse(credentials.review_configured)
        self.assertEqual(credentials.review_code, "")

    def test_admin_code_is_loaded(self):
        credentials = competition_credentials(
            secrets={"COMPETITION_ADMIN_CODE": "admin-value"},
            environ={},
        )
        self.assertTrue(credentials.admin_configured)

    def test_missing_admin_code_is_not_defaulted(self):
        credentials = competition_credentials(secrets={}, environ={})
        self.assertFalse(credentials.admin_configured)

    def test_review_and_admin_codes_are_independent(self):
        credentials = competition_credentials(
            secrets={
                "COMPETITION_REVIEW_CODE": "review-value",
                "COMPETITION_ADMIN_CODE": "admin-value",
            },
            environ={},
        )
        self.assertNotEqual(credentials.review_code, credentials.admin_code)

    def test_same_review_and_admin_code_is_rejected_by_app(self):
        original = app.st
        app.st = SimpleNamespace(
            secrets={
                "COMPETITION_REVIEW_CODE": "same-value",
                "COMPETITION_ADMIN_CODE": "same-value",
            }
        )
        try:
            self.assertEqual(app.get_competition_auth_credentials(), ("", ""))
        finally:
            app.st = original

    def test_normal_runtime_requires_stable_signing_key(self):
        original = app.st
        app.st = SimpleNamespace(__name__="streamlit", secrets={})
        try:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(app.AuthConfigurationError):
                    app._authorization_signing_key()
        finally:
            app.st = original

    def test_configured_signing_key_is_stable(self):
        original = app.st
        app.st = SimpleNamespace(
            __name__="streamlit",
            secrets={"AUTH_CONTEXT_SIGNING_KEY": "x" * 40},
        )
        try:
            first = app._authorization_signing_key()
            second = app._authorization_signing_key()
            self.assertEqual(first, second)
        finally:
            app.st = original


class StorageIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="competition-mode-",
            dir=ROOT.parent,
        )
        base = Path(self.temp.name)
        self.production = base / "production"
        self.demo = base / "demo"
        self.competition = base / "competition"
        self.production.mkdir()
        self.demo.mkdir()
        self.fake = SimpleNamespace(session_state=State(), secrets={})
        app.st = self.fake
        app.init_session()
        self.patches = [
            patch.object(app, "APP_MODE", "competition"),
            patch.object(app, "RESULTS_INDEX_PATH", self.production / "training_results.jsonl"),
            patch.object(app, "RESULTS_FULL_REPORTS_PATH", self.production / "training_full_reports.jsonl"),
            patch.object(app, "DEMO_DATA_DIR", self.demo),
            patch.object(app, "COMPETITION_RUNTIME_DIR", self.competition),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    @staticmethod
    def _write(path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
            encoding="utf-8",
        )

    def _scope(self):
        return app.create_competition_admin_context()

    def test_competition_adapter_disables_database(self):
        adapter = app.current_storage_adapter()
        self.assertIsInstance(adapter, CompetitionStorageAdapter)
        self.assertFalse(adapter.allows_database)

    def test_competition_admin_reads_demo_summary_only(self):
        self._write(
            self.demo / "training_results.jsonl",
            [{"session_id": "demo", "organization_id": "DEMO"}],
        )
        self._write(
            self.production / "training_results.jsonl",
            [{"session_id": "formal", "organization_id": "FORMAL"}],
        )
        records = app.load_result_records_local(self._scope())
        self.assertEqual([item["session_id"] for item in records], ["demo"])

    def test_competition_admin_does_not_merge_runtime_experience(self):
        self._write(
            self.demo / "training_results.jsonl",
            [{"session_id": "demo"}],
        )
        self._write(
            self.competition / "training_results.jsonl",
            [{"session_id": "reviewer-runtime"}],
        )
        records = app.load_result_records_local(self._scope())
        self.assertEqual([item["session_id"] for item in records], ["demo"])

    def test_competition_full_reports_do_not_read_production(self):
        self._write(
            self.demo / "training_full_reports.jsonl",
            [{"session": {"session_id": "demo"}}],
        )
        self._write(
            self.production / "training_full_reports.jsonl",
            [{"session": {"session_id": "formal"}}],
        )
        reports = app.load_full_reports_local(self._scope())
        self.assertEqual(reports[0]["session"]["session_id"], "demo")
        self.assertEqual(len(reports), 1)

    def test_competition_save_writes_only_isolated_directory(self):
        report = {
            "session": {
                "session_id": "competition-session",
                "completion_id": "c" * 64,
            },
            "score": 1,
        }
        app.save_result_record_local(report)
        self.assertTrue((self.competition / "training_results.jsonl").exists())
        self.assertTrue((self.competition / "training_full_reports.jsonl").exists())
        self.assertFalse((self.production / "training_results.jsonl").exists())

    def test_competition_database_write_is_blocked_before_client(self):
        with patch.object(app, "get_supabase_client") as get_client:
            ok, message = app.save_result_record_database({"session": {}})
        self.assertFalse(ok)
        self.assertIn("禁用", message)
        get_client.assert_not_called()

    def test_competition_database_read_is_blocked_before_client(self):
        with patch.object(app, "get_supabase_client") as get_client:
            rows, message = app.load_result_rows_database(self._scope())
        self.assertEqual(rows, [])
        self.assertIn("禁用", message)
        get_client.assert_not_called()

    def test_competition_admin_has_no_manage_permission(self):
        scope = self._scope()
        self.assertTrue(app.authorization_allows(scope, "view"))
        self.assertTrue(app.authorization_allows(scope, "export"))
        self.assertFalse(app.authorization_allows(scope, "manage"))

    def test_production_adapter_never_reads_demo(self):
        adapter = build_storage_adapter(
            "production",
            production_directory=self.production,
            demo_directory=self.demo,
            competition_runtime_directory=self.competition,
        )
        self.assertIsInstance(adapter, ProductionStorageAdapter)
        self.assertEqual(
            adapter.admin_read_paths().results_index.parent,
            self.production,
        )


class AcademyFlowAndUiTests(unittest.TestCase):
    def test_academy_phase_sequence(self):
        self.assertEqual(next_academy_phase("课前测评"), "模拟训练")
        self.assertEqual(next_academy_phase("模拟训练"), "课后考核")
        self.assertIsNone(next_academy_phase("课后考核"))

    def test_completion_pages_are_explicit(self):
        self.assertEqual(completion_page_for_phase("课前测评"), "pretest_complete")
        self.assertEqual(completion_page_for_phase("模拟训练"), "training_complete")
        self.assertEqual(completion_page_for_phase("课后考核"), "posttest_result")

    def test_stage_report_keys_are_stable(self):
        self.assertEqual(stage_report_key("课前测评"), "pretest")
        self.assertEqual(stage_report_key("模拟训练"), "training")
        self.assertEqual(stage_report_key("课后考核"), "posttest")

    def test_score_snapshot_does_not_change_report_values(self):
        report = {"score": 80, "max_score": 100, "penalties": 5}
        snapshot = score_snapshot(report)
        self.assertEqual(snapshot["score"], 80)
        self.assertEqual(snapshot["raw_score"], 85)
        self.assertEqual(report["score"], 80)

    def test_short_label_uses_action_id(self):
        action = {
            "id": "student_independent_epinephrine",
            "label": "护生自行抽取并独立注射急救药物",
        }
        self.assertEqual(academy_action_short_label(action), "独立完成急救注射")

    def test_unknown_action_keeps_original_label(self):
        self.assertEqual(
            academy_action_short_label({"id": "future", "label": "原始文字"}),
            "原始文字",
        )

    def test_elapsed_time_is_consistent(self):
        self.assertEqual(format_elapsed_time(0), "00:00")
        self.assertEqual(format_elapsed_time(30), "00:30")
        self.assertEqual(format_elapsed_time(60), "01:00")

    def test_demo_data_contains_only_virtual_identity_markers(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "demo_data").glob("*.jsonl"))
        )
        self.assertIn("虚构", text)
        self.assertIn("示范护理学院", text)
        for forbidden in ("@gmail.com", "@qq.com", "四川大学华西第二医院"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    os.environ.setdefault("PEDSIM_AUTOMATED_TEST", "1")
    unittest.main(verbosity=2)
