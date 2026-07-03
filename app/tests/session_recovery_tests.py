import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402
from peds_anaphylaxis_sim.scenario_catalog import (  # noqa: E402
    scenario_definition,
)


CLINICAL_INITIAL = scenario_definition(
    "peds_ward_anaphylaxis_iv_initial"
).path
CLINICAL_VARIANT = scenario_definition(
    "peds_ward_anaphylaxis_iv_variantA"
).path
ACADEMY_INITIAL = scenario_definition(
    "peds_ward_allergy_academy_initial"
).path
ACADEMY_VARIANT = scenario_definition(
    "peds_ward_allergy_academy_variant"
).path


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class FakeStreamlit(SimpleNamespace):
    def __init__(self, cookie="browser-a", query=None, secrets=None):
        super().__init__(
            session_state=State(),
            query_params=dict(query or {}),
            context=SimpleNamespace(
                headers={
                    "User-Agent": f"test-browser/{cookie}",
                    "Accept-Language": "zh-CN",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                }
            ),
            secrets=secrets or {},
        )


def checksum_payload(payload):
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SessionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v138-drafts-", dir=ROOT.parent)
        self.drafts_dir = Path(self.temp.name)
        self.drafts_patch = patch.object(app, "DRAFTS_DIR", self.drafts_dir)
        self.drafts_patch.start()

    def tearDown(self):
        self.drafts_patch.stop()
        self.temp.cleanup()

    def _start(self, system_mode, phase, mode, scenario_path, cookie="browser-a"):
        fake = FakeStreamlit(cookie=cookie)
        app.st = fake
        app.init_session()
        fake.session_state.update(
            system_mode=system_mode,
            system_mode_selected=True,
            participant_type="nursing_student" if system_mode == "academy" else "clinical_nurse",
            academy_scenario_selected=True,
            academy_scenario_id=app.ACADEMY_SCENARIO_DEFAULT_ID,
            academy_scenario_name="严重过敏反应/过敏性休克抢救",
            profile_completed=True,
            app_unlocked=True,
            page="训练系统",
            assessment_phase=phase,
            workflow_mode=mode,
            mode=mode,
            participant_id=f"AUTO-{system_mode}-{mode}",
            participant_initials="AUT",
            institution="自动测试医院" if system_mode == "clinical" else "",
            campus="自动测试院区" if system_mode == "clinical" else "",
            department="自动测试科室" if system_mode == "clinical" else "学院教学",
            school_name="自动测试护理学院" if system_mode == "academy" else "",
            student_level="本科" if system_mode == "academy" else "",
            student_grade="二年级" if system_mode == "academy" else "",
            nurse_level="N1" if system_mode == "clinical" else "",
            years_experience=1,
            years_experience_confirmed=True,
            collection_mode="测试演练",
        )
        app.start_simulation(scenario_path, mode, 123, fake.session_state.participant_id)
        return fake

    def _exercise_and_restore(self, system_mode, phase, mode, scenario_path):
        original = self._start(system_mode, phase, mode, scenario_path)
        sim = original.session_state.active_simulator
        action_id = "allergy_identification" if system_mode == "academy" else "stop_infusion"
        sim.apply_action(action_id)
        sim.tick()
        original.session_state.last_dose_feedback = "自动测试反馈"
        original.session_state.last_dose_feedback_level = "info"
        self.assertTrue(app.persist_active_training_draft())

        before = {
            "t": sim.state.t,
            "score": sim.score,
            "penalties": sim.penalties,
            "flags": json.loads(json.dumps(sim.state.flags, ensure_ascii=False)),
            "actions": dict(sim.action_first_time),
            "session_id": original.session_state.session_id,
            "draft_id": original.session_state.draft_id,
        }
        refreshed = FakeStreamlit(cookie="browser-a", query=original.query_params)
        app.st = refreshed
        app.init_session()
        self.assertTrue(app.restore_training_draft_from_query())
        restored = refreshed.session_state.active_simulator
        self.assertEqual(refreshed.session_state.system_mode, system_mode)
        self.assertEqual(refreshed.session_state.assessment_phase, phase)
        self.assertEqual(restored.mode, mode)
        self.assertEqual(restored.state.t, before["t"])
        self.assertEqual(restored.score, before["score"])
        self.assertEqual(restored.penalties, before["penalties"])
        self.assertEqual(restored.state.flags, before["flags"])
        self.assertEqual(restored.action_first_time, before["actions"])
        self.assertEqual(refreshed.session_state.session_id, before["session_id"])
        self.assertEqual(refreshed.session_state.draft_id, before["draft_id"])
        self.assertEqual(refreshed.session_state.last_dose_feedback, "自动测试反馈")
        self.assertTrue(refreshed.session_state.app_unlocked)
        self.assertFalse(refreshed.session_state.admin_unlocked)

    def test_clinical_training_refresh_restore(self):
        self._exercise_and_restore("clinical", "模拟培训", "coach", CLINICAL_INITIAL)

    def test_clinical_exam_refresh_restore(self):
        self._exercise_and_restore("clinical", "培训后考核", "exam", CLINICAL_VARIANT)

    def test_academy_training_refresh_restore(self):
        self._exercise_and_restore("academy", "模拟训练", "coach", ACADEMY_INITIAL)

    def test_academy_exam_refresh_restore(self):
        self._exercise_and_restore("academy", "课后考核", "exam", ACADEMY_VARIANT)

    def test_new_browser_session_without_identifier_cannot_restore(self):
        original = self._start("clinical", "模拟培训", "coach", CLINICAL_INITIAL)
        draft_path = app._draft_path(original.session_state.draft_id)
        self.assertTrue(draft_path.exists())
        other = FakeStreamlit(cookie="browser-b")
        app.st = other
        app.init_session()
        self.assertFalse(app.restore_training_draft_from_query())
        self.assertIsNone(other.session_state.active_simulator)
        self.assertTrue(draft_path.exists())

    def test_same_identifier_in_different_browser_is_rejected(self):
        original = self._start("clinical", "模拟培训", "coach", CLINICAL_INITIAL)
        draft_path = app._draft_path(original.session_state.draft_id)
        other = FakeStreamlit(cookie="browser-b", query=original.query_params)
        app.st = other
        app.init_session()
        self.assertFalse(app.restore_training_draft_from_query())
        self.assertIsNone(other.session_state.active_simulator)
        self.assertNotIn(app.DRAFT_QUERY_KEY, other.query_params)
        self.assertTrue(draft_path.exists())

    def test_invalid_and_damaged_recovery_data_fail_safely(self):
        invalid = FakeStreamlit(query={app.DRAFT_QUERY_KEY: "../../invalid"})
        app.st = invalid
        app.init_session()
        self.assertFalse(app.restore_training_draft_from_query())
        self.assertNotIn(app.DRAFT_QUERY_KEY, invalid.query_params)

        draft_id = "a" * 64
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        damaged_path = app._draft_path(draft_id)
        damaged_path.write_text("{not-json", encoding="utf-8")
        damaged = FakeStreamlit(query={app.DRAFT_QUERY_KEY: draft_id})
        app.st = damaged
        app.init_session()
        self.assertFalse(app.restore_training_draft_from_query())
        self.assertFalse(damaged_path.exists())
        self.assertIsNone(damaged.session_state.active_simulator)

    def test_expired_draft_is_removed(self):
        old_time = 1_700_000_000.0
        with patch.object(app.time, "time", return_value=old_time):
            original = self._start("clinical", "模拟培训", "coach", CLINICAL_INITIAL)
        draft_path = app._draft_path(original.session_state.draft_id)
        self.assertTrue(draft_path.exists())
        refreshed = FakeStreamlit(cookie="browser-a", query=original.query_params)
        app.st = refreshed
        app.init_session()
        self.assertFalse(
            app.restore_training_draft_from_query(now=old_time + app.DRAFT_TTL_SECONDS + 1)
        )
        self.assertFalse(draft_path.exists())
        self.assertNotIn(app.DRAFT_QUERY_KEY, refreshed.query_params)

    def test_completion_converts_draft_to_refreshable_result(self):
        fake = self._start("clinical", "模拟培训", "coach", CLINICAL_INITIAL)
        draft_path = app._draft_path(fake.session_state.draft_id)
        report = fake.session_state.active_simulator.build_report()
        with patch.object(app, "save_report", return_value=("auto.json", "auto.md")), patch.object(
            app, "save_result_record", return_value=None
        ):
            app._save_and_end_report(report, "participant_confirmed_rescue_complete")
        self.assertTrue(draft_path.exists())
        self.assertIn(app.DRAFT_QUERY_KEY, fake.query_params)
        self.assertIsNotNone(fake.session_state.active_simulator)
        self.assertTrue(fake.session_state.ended)
        self.assertTrue(fake.session_state.result_saved)

        refreshed = FakeStreamlit(cookie="browser-a", query=fake.query_params)
        app.st = refreshed
        app.init_session()
        self.assertTrue(app.restore_training_draft_from_query())
        self.assertTrue(refreshed.session_state.ended)
        self.assertTrue(refreshed.session_state.result_saved)
        self.assertEqual(
            refreshed.session_state.last_report["score"],
            fake.session_state.last_report["score"],
        )

    def test_reset_creates_fresh_draft_and_state(self):
        fake = self._start("clinical", "模拟培训", "coach", CLINICAL_INITIAL)
        first_id = fake.session_state.draft_id
        first_path = app._draft_path(first_id)
        fake.session_state.active_simulator.apply_action("stop_infusion")
        fake.session_state.active_simulator.tick()
        app.persist_active_training_draft()
        app.start_simulation(CLINICAL_INITIAL, "coach", 456, fake.session_state.participant_id)
        self.assertNotEqual(fake.session_state.draft_id, first_id)
        self.assertFalse(first_path.exists())
        self.assertEqual(fake.session_state.active_simulator.state.t, 0)
        self.assertEqual(fake.session_state.active_simulator.score, 0)
        self.assertEqual(fake.session_state.active_simulator.action_first_time, {})

    def test_secrets_and_admin_state_are_not_persisted(self):
        secret_access = "LOCAL-ACCESS-DO-NOT-PERSIST"
        secret_admin = "LOCAL-ADMIN-DO-NOT-PERSIST"
        fake = self._start("academy", "模拟训练", "coach", ACADEMY_INITIAL)
        fake.secrets = {
            "APP_ACCESS_CODE": secret_access,
            "ADMIN_PASSWORD": secret_admin,
        }
        fake.session_state.admin_unlocked = True
        fake.session_state.admin_scope = {"code_type": "super_admin"}
        self.assertTrue(app.persist_active_training_draft())
        raw = app._draft_path(fake.session_state.draft_id).read_text(encoding="utf-8")
        self.assertNotIn(secret_access, raw)
        self.assertNotIn(secret_admin, raw)
        self.assertNotIn("APP_ACCESS_CODE", raw)
        self.assertNotIn("ADMIN_PASSWORD", raw)
        self.assertNotIn("admin_unlocked", raw)
        self.assertNotIn("admin_scope", raw)

    def test_checksum_tampering_is_rejected(self):
        original = self._start("clinical", "培训后考核", "exam", CLINICAL_VARIANT)
        draft_path = app._draft_path(original.session_state.draft_id)
        envelope = json.loads(draft_path.read_text(encoding="utf-8"))
        envelope["payload"]["session_state"]["assessment_phase"] = "被篡改"
        draft_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        refreshed = FakeStreamlit(cookie="browser-a", query=original.query_params)
        app.st = refreshed
        app.init_session()
        self.assertFalse(app.restore_training_draft_from_query())
        self.assertFalse(draft_path.exists())

    def test_valid_expiry_rewrite_helper(self):
        original = self._start("clinical", "模拟培训", "coach", CLINICAL_INITIAL)
        draft_path = app._draft_path(original.session_state.draft_id)
        envelope = json.loads(draft_path.read_text(encoding="utf-8"))
        envelope["checksum"] = checksum_payload(envelope["payload"])
        draft_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        self.assertTrue(draft_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
