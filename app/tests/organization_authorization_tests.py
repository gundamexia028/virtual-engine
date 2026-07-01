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
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PEDSIM_RESULTS_DIR", str(ROOT.parent / "V1.3.8_org_auth_temp"))
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402


CLINICAL_A_CODE = secrets.token_urlsafe(24) + "Aa1!"
CLINICAL_B_CODE = secrets.token_urlsafe(24) + "Bb2!"
ACADEMY_A_CODE = secrets.token_urlsafe(24) + "Cc3!"
ACADEMY_B_CODE = secrets.token_urlsafe(24) + "Dd4!"
INACTIVE_CODE = secrets.token_urlsafe(24) + "Ee5!"
LEGACY_SUPER_CODE = secrets.token_urlsafe(24) + "Ff6!"


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


def report(
    completion_char,
    organization_type,
    organization_id,
    display_name,
    system_mode=None,
):
    mode = system_mode or organization_type
    return {
        "scenario_id": "auto_org_isolation",
        "scenario_title": "自动权限隔离测试",
        "mode": "exam",
        "score": 80,
        "max_score": 100,
        "end_reason": "success",
        "session": {
            "session_id": f"AUTO-{organization_id}-{completion_char}",
            "completion_id": completion_char * 64,
            "participant_id": f"AUTO-{organization_id}",
            "organization_type": organization_type,
            "organization_id": organization_id,
            "system_mode": mode,
            "system_mode_label": "学院模式" if mode == "academy" else "临床模式",
            "assessment_phase": "课后考核" if mode == "academy" else "培训后考核",
            "collection_mode": "测试演练",
            "institution": display_name if mode == "clinical" else "",
            "school_name": display_name if mode == "academy" else "",
            "app_version": app.APP_VERSION,
        },
        "log": [],
    }


class OrganizationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.credential_min_patcher = patch.object(
            app.org_credentials,
            "MIN_ITERATIONS",
            1_000,
        )
        self.credential_min_patcher.start()
        self.temp = tempfile.TemporaryDirectory(prefix="v138-org-auth-", dir=ROOT.parent)
        self.root = Path(self.temp.name)
        self.runs = self.root / "runs"
        self.index = self.runs / "training_results.jsonl"
        self.full = self.runs / "training_full_reports.jsonl"
        self.config = self.root / "org_access_codes.json"
        self.records = [
            {
                "organization_id": "CLN_AUTO_A",
                "organization_type": "clinical",
                "role": "clinical_admin",
                "hospital_name": "自动测试同名单位",
                "department_name": "自动测试科室A",
                "credential": app.org_credentials.build_credential(
                    CLINICAL_A_CODE,
                    "clinical_admin",
                    "clinical",
                    "CLN_AUTO_A",
                    iterations=1_000,
                ),
                "status": "active",
            },
            {
                "organization_id": "CLN_AUTO_B",
                "organization_type": "clinical",
                "role": "clinical_admin",
                "hospital_name": "自动测试同名单位",
                "department_name": "自动测试科室B",
                "credential": app.org_credentials.build_credential(
                    CLINICAL_B_CODE,
                    "clinical_admin",
                    "clinical",
                    "CLN_AUTO_B",
                    iterations=1_000,
                ),
                "status": "active",
            },
            {
                "organization_id": "ACD_AUTO_A",
                "organization_type": "academy",
                "role": "academy_admin",
                "school_name": "自动测试学院",
                "credential": app.org_credentials.build_credential(
                    ACADEMY_A_CODE,
                    "academy_admin",
                    "academy",
                    "ACD_AUTO_A",
                    iterations=1_000,
                ),
                "status": "active",
            },
            {
                "organization_id": "ACD_AUTO_B",
                "organization_type": "academy",
                "role": "academy_admin",
                "school_name": "自动测试学院 ",
                "credential": app.org_credentials.build_credential(
                    ACADEMY_B_CODE,
                    "academy_admin",
                    "academy",
                    "ACD_AUTO_B",
                    iterations=1_000,
                ),
                "status": "active",
            },
            {
                "organization_id": "CLN_INACTIVE",
                "organization_type": "clinical",
                "role": "clinical_admin",
                "credential": app.org_credentials.build_credential(
                    INACTIVE_CODE,
                    "clinical_admin",
                    "clinical",
                    "CLN_INACTIVE",
                    iterations=1_000,
                ),
                "status": "inactive",
            },
        ]
        self.config.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.patchers = [
            patch.object(app, "RUNS_DIR", self.runs),
            patch.object(app, "RESULTS_INDEX_PATH", self.index),
            patch.object(app, "RESULTS_FULL_REPORTS_PATH", self.full),
            patch.object(app, "ORG_ACCESS_CODES_PATH", self.config),
            patch.object(
                app,
                "st",
                SimpleNamespace(secrets={}, session_state=State({})),
            ),
        ]
        for patcher in self.patchers:
            patcher.start()

        self.reports = [
            report("1", "clinical", "CLN_AUTO_A", "自动测试同名单位"),
            report("2", "clinical", "CLN_AUTO_B", "自动测试同名单位"),
            report("3", "academy", "ACD_AUTO_A", "自动测试学院"),
            report("4", "academy", "ACD_AUTO_B", "自动测试学院 "),
        ]
        for item in self.reports:
            app.save_result_record_local(item)
        self.clinical_a = app.find_org_scope_by_code(CLINICAL_A_CODE)
        self.clinical_b = app.find_org_scope_by_code(CLINICAL_B_CODE)
        self.academy_a = app.find_org_scope_by_code(ACADEMY_A_CODE)
        self.academy_b = app.find_org_scope_by_code(ACADEMY_B_CODE)
        self.platform = app.create_platform_admin_context()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()
        self.credential_min_patcher.stop()

    def ids(self, records):
        return {app._record_organization(item)[1] for item in records}

    def test_01_missing_scope_denied(self):
        self.assertEqual(app.load_result_records_local(None), [])

    def test_02_blank_scope_denied(self):
        self.assertEqual(app.load_result_records_local({}), [])

    def test_03_whitespace_scope_denied(self):
        context = {"role": " ", "organization_type": " ", "organization_id": " "}
        self.assertIsNone(app.validate_authorization_context(context))

    def test_04_illegal_scope_denied(self):
        context = app._issue_authorization_context("unknown", "clinical", "CLN_AUTO_A")
        self.assertIsNone(app.validate_authorization_context(context))

    def test_05_missing_scope_cannot_enter_admin(self):
        fake_st = MagicMock()
        fake_st.session_state = State({"admin_unlocked": True, "admin_scope": None})
        with patch.object(app, "st", fake_st), \
                patch.object(app, "compact_header"), \
                patch.object(app, "require_auth_credentials", return_value=("access", "admin")), \
                patch.object(app, "load_result_records_local") as loader:
            app.render_admin_page()
        loader.assert_not_called()
        self.assertFalse(fake_st.session_state.admin_unlocked)
        fake_st.error.assert_called_once_with(app.AUTH_CONTEXT_ERROR_MESSAGE)

    def test_06_clinical_a_reads_only_a(self):
        self.assertEqual(self.ids(app.load_result_records_local(self.clinical_a)), {"CLN_AUTO_A"})

    def test_07_clinical_b_reads_only_b(self):
        self.assertEqual(self.ids(app.load_result_records_local(self.clinical_b)), {"CLN_AUTO_B"})

    def test_08_academy_a_reads_only_a(self):
        self.assertEqual(self.ids(app.load_result_records_local(self.academy_a)), {"ACD_AUTO_A"})

    def test_09_academy_b_reads_only_b(self):
        self.assertEqual(self.ids(app.load_result_records_local(self.academy_b)), {"ACD_AUTO_B"})

    def test_10_clinical_cannot_read_academy(self):
        self.assertFalse(self.ids(app.load_result_records_local(self.clinical_a)) & {"ACD_AUTO_A", "ACD_AUTO_B"})

    def test_11_academy_cannot_read_clinical(self):
        self.assertFalse(self.ids(app.load_result_records_local(self.academy_a)) & {"CLN_AUTO_A", "CLN_AUTO_B"})

    def test_12_session_state_scope_tampering_denied(self):
        tampered = dict(self.clinical_a)
        tampered["organization_id"] = "CLN_AUTO_B"
        self.assertEqual(app.load_result_records_local(tampered), [])

    def test_13_url_or_form_values_cannot_create_scope(self):
        forged = {
            "role": "platform_admin",
            "organization_type": "platform",
            "organization_id": "PLATFORM",
        }
        self.assertIsNone(app.validate_authorization_context(forged))

    def test_14_direct_local_loader_enforces_filter(self):
        self.assertEqual(self.ids(app.load_full_reports_local(self.clinical_a)), {"CLN_AUTO_A"})

    def test_15_direct_csv_export_enforces_filter(self):
        payload = app.records_to_csv_bytes(
            [app.flatten_record(item) for item in self.reports],
            self.clinical_a,
        )
        rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        self.assertEqual({row["organization_id"] for row in rows}, {"CLN_AUTO_A"})

    def test_16_direct_jsonl_export_enforces_filter(self):
        payload = app.records_to_jsonl_bytes(self.reports, self.academy_a)
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
        self.assertEqual(self.ids(rows), {"ACD_AUTO_A"})

    def test_17_same_or_similar_names_do_not_cross_ids(self):
        self.assertEqual(self.ids(app.load_result_records_local(self.clinical_a)), {"CLN_AUTO_A"})
        self.assertEqual(self.ids(app.load_result_records_local(self.academy_a)), {"ACD_AUTO_A"})

    def test_18_unknown_organization_id_denied(self):
        context = app._issue_authorization_context(
            "clinical_admin",
            "clinical",
            "CLN_UNKNOWN",
        )
        self.assertEqual(app.load_result_records_local(context), [])

    def test_19_role_type_mismatch_denied(self):
        context = app._issue_authorization_context(
            "clinical_admin",
            "academy",
            "ACD_AUTO_A",
        )
        self.assertIsNone(app.validate_authorization_context(context))

    def test_20_ordinary_user_cannot_become_unit_admin(self):
        forged = {
            "role": "clinical_admin",
            "organization_type": "clinical",
            "organization_id": "CLN_AUTO_A",
        }
        self.assertEqual(app.load_result_records_local(forged), [])

    def test_21_unit_admin_cannot_become_platform_admin(self):
        tampered = dict(self.clinical_a)
        tampered["role"] = "platform_admin"
        tampered["organization_type"] = "platform"
        tampered["organization_id"] = "PLATFORM"
        self.assertIsNone(app.validate_authorization_context(tampered))

    def test_22_explicit_platform_admin_reads_all(self):
        self.assertEqual(
            self.ids(app.load_result_records_local(self.platform)),
            {"CLN_AUTO_A", "CLN_AUTO_B", "ACD_AUTO_A", "ACD_AUTO_B"},
        )

    def test_23_legacy_super_admin_record_is_rejected(self):
        legacy = {
            "org_id": "PLATFORM",
            "org_type": "all",
            "code_type": "super_admin",
            "admin_code_hash": "0" * 64,
            "admin_code": LEGACY_SUPER_CODE,
            "status": "active",
        }
        self.config.write_text(json.dumps([legacy]), encoding="utf-8")
        self.assertIsNone(app.find_org_scope_by_code(LEGACY_SUPER_CODE))

    def test_24_inactive_unit_code_is_rejected(self):
        self.assertIsNone(app.find_org_scope_by_code(INACTIVE_CODE))

    def test_25_questionnaire_merge_stays_in_authorized_unit(self):
        questionnaire = {
            "completion_id": "1" * 64,
            "questionnaire_submission_id": "a" * 64,
            "organization_type": "clinical",
            "organization_id": "CLN_AUTO_A",
            "academy_post_evaluation": {"completed": True},
        }
        app.save_questionnaire_record_local(questionnaire)
        loaded = app.load_full_reports_local(self.clinical_b)
        self.assertEqual(self.ids(loaded), {"CLN_AUTO_B"})
        self.assertNotIn("academy_post_evaluation", loaded[0])

    def test_26_summary_records_keep_organization_boundary(self):
        summaries = app.build_summary_records_from_reports(self.reports, storage_source="local")
        filtered = [item for item in summaries if app.record_matches_scope(item, self.clinical_a)]
        self.assertEqual(self.ids(filtered), {"CLN_AUTO_A"})

    def test_27_action_details_keep_organization_boundary(self):
        enriched = json.loads(json.dumps(self.reports))
        enriched[0]["log"] = [{"t": 1, "kind": "action", "message": "auto", "data": {}}]
        details = app.build_action_detail_records_from_reports(enriched, storage_source="local")
        filtered = [item for item in details if app.record_matches_scope(item, self.clinical_a)]
        self.assertEqual(self.ids(filtered), {"CLN_AUTO_A"})

    def test_28_statistics_and_quality_keep_organization_boundary(self):
        summaries = app.build_summary_records_from_reports(self.reports, storage_source="local")
        participants = app.build_participant_analysis_records(summaries)
        quality = app.build_data_quality_records(summaries)
        self.assertEqual(
            self.ids([item for item in participants if app.record_matches_scope(item, self.academy_a)]),
            {"ACD_AUTO_A"},
        )
        self.assertEqual(
            self.ids([item for item in quality if app.record_matches_scope(item, self.academy_a)]),
            {"ACD_AUTO_A"},
        )

    def test_29_invalid_scope_does_not_open_local_data_file(self):
        with patch.object(app, "_read_jsonl_unlocked") as reader:
            self.assertEqual(app.load_full_reports_local(None), [])
        reader.assert_not_called()

    def test_30_invalid_scope_does_not_initialize_database(self):
        with patch.object(app, "database_configured") as configured, \
                patch.object(app, "get_supabase_client") as client:
            rows, _ = app.load_result_rows_database(None)
        self.assertEqual(rows, [])
        configured.assert_not_called()
        client.assert_not_called()

    def test_31_ordinary_clinical_and_academy_registration_not_blocked(self):
        clinical = State({
            "system_mode": "clinical",
            "institution": "自动测试医院",
            "campus": "自动测试院区",
            "department": "自动测试科室",
            "participant_initials": "ATC",
            "participant_id": "AUTO-CLINICAL",
            "nurse_level": "N1",
            "years_experience": 1,
            "years_experience_confirmed": True,
            "assessment_phase": "模拟培训",
            "collection_mode": "测试演练",
            "organization_id": "CLN_AUTO_A",
        })
        fake_st = SimpleNamespace(session_state=clinical)
        with patch.object(app, "st", fake_st):
            self.assertEqual(app.profile_required_missing(), [])
            fake_st.session_state = State({
                "system_mode": "academy",
                "academy_scenario_id": app.ACADEMY_SCENARIO_DEFAULT_ID,
                "school_name": "自动测试学院",
                "student_level": "本科",
                "student_grade": "二年级",
                "participant_initials": "ATA",
                "participant_id": "AUTO-ACADEMY",
                "assessment_phase": "模拟训练",
                "collection_mode": "测试演练",
                "organization_id": "ACD_AUTO_A",
            })
            self.assertEqual(app.profile_required_missing(), [])

    def test_32_authorization_and_records_do_not_contain_secrets(self):
        text = json.dumps(
            {
                "authorization": self.clinical_a,
                "records": app.load_result_records_local(self.clinical_a),
            },
            ensure_ascii=False,
        )
        for field in ("APP_ACCESS_CODE", "ADMIN_PASSWORD", "SUPABASE_KEY"):
            self.assertNotIn(field, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
