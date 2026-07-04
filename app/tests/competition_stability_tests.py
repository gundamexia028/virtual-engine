from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402
from academy_flow import (  # noqa: E402
    academy_completion_page_title,
    academy_flow_page_allowed,
    academy_sidebar_status,
    questionnaire_submit_button_label,
    should_auto_finalize_academy_phase,
    training_completion_status_text,
    latest_allowed_academy_page,
)
from academy_interactions import (  # noqa: E402
    ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
    ACADEMY_ASSISTED_MEDICATION_FULL_LABEL,
    add_assisted_medication_choice,
    apply_academy_action,
)
from peds_anaphylaxis_sim.engine import Simulator  # noqa: E402
from peds_anaphylaxis_sim.scenario_loader import load_registered_scenario  # noqa: E402
from peds_anaphylaxis_sim.time_format import (  # noqa: E402
    format_elapsed_time,
    format_timeline_value,
)
from ui_labels import format_time_progress  # noqa: E402


ACADEMY_INITIAL = app.scenario_path_by_role("academy_initial")
ACADEMY_VARIANT = app.scenario_path_by_role("academy_variant")


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class FakeStreamlit(SimpleNamespace):
    def __init__(self):
        super().__init__(
            session_state=State(),
            query_params={},
            context=SimpleNamespace(
                headers={
                    "User-Agent": "competition-stability-tests",
                    "Accept-Language": "zh-CN",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                }
            ),
            secrets={},
        )


def academy_simulator(mode: str = "exam", *, variant: bool = False) -> Simulator:
    scenario_id = (
        "peds_ward_allergy_academy_variant"
        if variant
        else "peds_ward_allergy_academy_initial"
    )
    return Simulator(load_registered_scenario(scenario_id), mode=mode, seed=123)


def run_compliant_path(
    simulator: Simulator,
    *,
    include_wait: bool = False,
) -> None:
    for action_id in (
        "allergy_identification",
        "call_help",
        "stop_infusion",
        "high_flow_oxygen",
        "connect_monitor",
        "check_bp",
        "prepare_rescue_equipment",
    ):
        simulator.apply_action(action_id)
        simulator.tick()
    if include_wait:
        simulator.apply_action("watch_only")
        simulator.tick()
    result = apply_academy_action(
        simulator,
        ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
    )
    if result["executed"]:
        simulator.tick()
    for action_id in (
        "academy_reassess",
        "academy_family_communication",
        "academy_sbar_handoff",
    ):
        simulator.apply_action(action_id)
        simulator.tick()


class AcademyMedicationCooperationTests(unittest.TestCase):
    def test_assisted_medication_is_hidden_before_preparation(self):
        sim = academy_simulator()
        action_ids = [
            action["id"]
            for action in add_assisted_medication_choice(
                sim.actions,
                sim.state.flags,
            )
        ]
        self.assertNotIn(ACADEMY_ASSISTED_MEDICATION_ACTION_ID, action_ids)

    def test_assisted_medication_appears_after_preparation(self):
        sim = academy_simulator()
        sim.apply_action("prepare_rescue_equipment")
        action_ids = [
            action["id"]
            for action in add_assisted_medication_choice(
                sim.actions,
                sim.state.flags,
            )
        ]
        self.assertIn(ACADEMY_ASSISTED_MEDICATION_ACTION_ID, action_ids)
        self.assertIn("student_independent_epinephrine", action_ids)

    def test_assisted_medication_maps_to_existing_core_action(self):
        sim = academy_simulator()
        sim.apply_action("prepare_rescue_equipment")
        result = apply_academy_action(
            sim,
            ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
        )
        self.assertTrue(result["executed"])
        self.assertEqual(result["core_action_id"], "prepare_rescue_equipment")
        self.assertTrue(sim.state.flags["rescue_equipment_prepared"])
        self.assertTrue(sim.state.flags["academy_assisted_medication_done"])
        self.assertEqual(sim.log[-1].message, "prepare_rescue_equipment")
        self.assertEqual(
            sim.log[-1].data["label"],
            ACADEMY_ASSISTED_MEDICATION_FULL_LABEL,
        )

    def test_assisted_medication_ui_repeat_is_idempotent(self):
        sim = academy_simulator()
        sim.apply_action("prepare_rescue_equipment")
        first = apply_academy_action(
            sim,
            ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
        )
        action_count = len(sim.log)
        second = apply_academy_action(
            sim,
            ACADEMY_ASSISTED_MEDICATION_ACTION_ID,
        )
        self.assertTrue(first["executed"])
        self.assertFalse(second["executed"])
        self.assertEqual(len(sim.log), action_count)

    def test_pretest_completes_without_independent_injection(self):
        sim = academy_simulator("exam")
        run_compliant_path(sim)
        self.assertEqual(sim.is_done(), (True, "success"))
        self.assertNotIn(
            "student_independent_epinephrine",
            sim.action_first_time,
        )

    def test_training_completes_without_independent_injection(self):
        sim = academy_simulator("coach")
        run_compliant_path(sim)
        self.assertEqual(sim.is_done(), (True, "success"))
        self.assertNotIn(
            "student_independent_epinephrine",
            sim.action_first_time,
        )

    def test_posttest_completes_without_independent_injection(self):
        sim = academy_simulator("exam", variant=True)
        run_compliant_path(sim)
        self.assertEqual(sim.is_done(), (True, "success"))
        self.assertNotIn(
            "student_independent_epinephrine",
            sim.action_first_time,
        )

    def test_waiting_does_not_prevent_later_medication_cooperation(self):
        sim = academy_simulator("exam")
        run_compliant_path(sim, include_wait=True)
        self.assertEqual(sim.is_done(), (True, "success"))
        self.assertTrue(sim.state.flags["academy_assisted_medication_done"])
        self.assertTrue(sim.state.flags["watch_only_no_rescue_cooperation"])

    def test_independent_injection_is_recoverable_role_boundary_error(self):
        sim = academy_simulator("coach")
        result = apply_academy_action(
            sim,
            "student_independent_epinephrine",
        )
        self.assertIn("护生应呼救", result["feedback"])
        run_compliant_path(sim)
        self.assertEqual(sim.is_done(), (True, "success"))
        self.assertTrue(sim.state.flags["student_role_boundary_risk"])

    def test_each_nonterminal_academy_error_keeps_core_actions_recoverable(self):
        errors = (
            "continue_infusion",
            "ask_family_first",
            "send_family_for_help",
            "prepare_steroid_antihistamine_only",
            "student_independent_epinephrine",
            "watch_only",
            "remove_iv",
        )
        core_ids = {
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
        }
        for action_id in errors:
            with self.subTest(action_id=action_id):
                sim = academy_simulator("coach")
                sim.apply_action(action_id)
                sim.tick()
                visible = {
                    action["id"]
                    for action in app.visible_actions_for_current_state(sim)
                }
                self.assertTrue(core_ids.issubset(visible))


class FeedbackAndTimeTests(unittest.TestCase):
    def setUp(self):
        self.original_st = app.st
        app.st = FakeStreamlit()
        app.init_session()

    def tearDown(self):
        app.st = self.original_st

    def test_training_history_explains_role_boundary(self):
        sim = academy_simulator("coach")
        sim.apply_action("student_independent_epinephrine")
        rows = app.get_action_history_rows(sim)
        self.assertIn("护生应呼救", rows[-1]["结果"])

    def test_exam_history_does_not_reveal_role_boundary_answer(self):
        sim = academy_simulator("exam")
        sim.apply_action("student_independent_epinephrine")
        rows = app.get_action_history_rows(sim)
        self.assertEqual(rows[-1]["结果"], "")

    def test_elapsed_time_boundaries(self):
        expected = {
            0: "00:00",
            59: "00:59",
            60: "01:00",
            90: "01:30",
            330: "05:30",
        }
        for seconds, label in expected.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(format_elapsed_time(seconds), label)

    def test_time_progress_uses_shared_formatter(self):
        self.assertEqual(format_time_progress(30), "时间推进 00:30")

    def test_report_timeline_formats_times_but_not_counts_or_doses(self):
        self.assertEqual(format_timeline_value("academy_reassess", 270), "04:30")
        self.assertEqual(format_timeline_value("reassess_count", 2), "2")
        self.assertEqual(format_timeline_value("epi_last_dose_mg", 0.15), "0.15")


class FlowOrderAndIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.original_st = app.st
        self.temp = tempfile.TemporaryDirectory(
            prefix="competition-stability-",
            dir=ROOT.parent,
        )
        self.fake = FakeStreamlit()
        app.st = self.fake
        app.init_session()
        self.fake.session_state.update(
            system_mode="academy",
            system_mode_selected=True,
            participant_type="nursing_student",
            academy_scenario_selected=True,
            academy_scenario_id=app.ACADEMY_SCENARIO_DEFAULT_ID,
            academy_scenario_name="严重过敏反应/过敏性休克抢救",
            profile_completed=True,
            app_unlocked=True,
            page="训练系统",
            assessment_phase="课前测评",
            workflow_mode="exam",
            mode="exam",
            participant_id="AUTO-STABLE-001",
            participant_initials="AUT",
            school_name="自动测试护理学院",
            student_level="本科",
            student_grade="三年级",
            collection_mode="测试演练",
        )
        self.drafts = Path(self.temp.name) / "drafts"
        self.draft_patch = patch.object(app, "DRAFTS_DIR", self.drafts)
        self.draft_patch.start()

    def tearDown(self):
        self.draft_patch.stop()
        app.st = self.original_st
        self.temp.cleanup()

    def _start(self, phase: str, mode: str, path: Path) -> None:
        self.fake.session_state.assessment_phase = phase
        self.fake.session_state.workflow_mode = mode
        self.fake.session_state.mode = mode
        app.start_simulation(path, mode, 123, self.fake.session_state.participant_id)

    def test_ui_event_double_click_is_claimed_once(self):
        self._start("课前测评", "exam", ACADEMY_INITIAL)
        self.assertTrue(app.claim_ui_event("action", "call_help", 0))
        self.assertFalse(app.claim_ui_event("action", "call_help", 0))

    def test_legitimate_repeat_at_later_time_is_not_blocked(self):
        self._start("模拟训练", "coach", ACADEMY_INITIAL)
        self.assertTrue(app.claim_ui_event("action", "academy_reassess", 30))
        self.assertTrue(app.claim_ui_event("action", "academy_reassess", 60))

    def test_restart_preserves_participant_and_previous_stage_report(self):
        self.fake.session_state.academy_stage_reports = {
            "pretest": {"session": {"session_id": "pre-complete"}}
        }
        self._start("模拟训练", "coach", ACADEMY_INITIAL)
        participant = self.fake.session_state.participant_id
        old_session = self.fake.session_state.session_id
        self.fake.session_state.active_simulator.apply_action("call_help")
        self.fake.session_state.active_simulator.tick()
        self.assertTrue(app.restart_current_stage(ACADEMY_INITIAL, "coach"))
        self.assertEqual(self.fake.session_state.participant_id, participant)
        self.assertNotEqual(self.fake.session_state.session_id, old_session)
        self.assertIn(
            "pretest",
            self.fake.session_state.academy_stage_reports,
        )
        self.assertEqual(self.fake.session_state.active_simulator.state.t, 0)
        self.assertEqual(
            self.fake.session_state.abandoned_stage_sessions[-1]["session_id"],
            old_session,
        )

    def test_restart_is_safe_in_all_three_academy_phases(self):
        cases = (
            ("课前测评", "exam", ACADEMY_INITIAL),
            ("模拟训练", "coach", ACADEMY_INITIAL),
            ("课后考核", "exam", ACADEMY_VARIANT),
        )
        for phase, mode, path in cases:
            with self.subTest(phase=phase):
                self.fake.session_state.academy_stage_reports = {
                    "pretest": {"session": {"session_id": "kept-pre"}}
                } if phase != "课前测评" else {}
                self._start(phase, mode, path)
                participant = self.fake.session_state.participant_id
                self.fake.session_state.active_simulator.apply_action("call_help")
                self.fake.session_state.active_simulator.tick()
                self.assertTrue(app.restart_current_stage(path, mode))
                self.assertEqual(self.fake.session_state.participant_id, participant)
                self.assertEqual(self.fake.session_state.active_simulator.state.t, 0)
                if phase != "课前测评":
                    self.assertIn(
                        "pretest",
                        self.fake.session_state.academy_stage_reports,
                    )

    def test_restart_confirmation_cancel_state_does_not_mutate_simulator(self):
        self._start("课后考核", "exam", ACADEMY_VARIANT)
        sim = self.fake.session_state.active_simulator
        sim.apply_action("call_help")
        sim.tick()
        before = sim.to_snapshot()
        self.fake.session_state.restart_stage_confirmation = True
        self.fake.session_state.restart_stage_confirmation = False
        self.assertEqual(sim.to_snapshot(), before)

    def test_next_stage_requires_completed_current_report(self):
        self._start("课前测评", "exam", ACADEMY_INITIAL)
        self.assertFalse(app._start_next_academy_stage("模拟训练"))

    def test_next_stage_double_request_creates_one_session(self):
        self._start("课前测评", "exam", ACADEMY_INITIAL)
        self.fake.session_state.academy_stage_reports = {
            "pretest": {"session": {"completion_id": "p" * 64}}
        }
        self.assertTrue(app._start_next_academy_stage("模拟训练"))
        first_session = self.fake.session_state.session_id
        self.assertFalse(app._start_next_academy_stage("模拟训练"))
        self.assertEqual(self.fake.session_state.session_id, first_session)

    def test_academy_pretest_goes_directly_to_completion_contract(self):
        self._start("课前测评", "exam", ACADEMY_INITIAL)
        self.assertFalse(app._needs_baseline_post_survey("success"))

    def test_training_core_completion_waits_for_manual_confirmation(self):
        self._start("模拟训练", "coach", ACADEMY_INITIAL)
        sim = self.fake.session_state.active_simulator
        run_compliant_path(sim)
        self.assertEqual(sim.is_done(), (True, "success"))
        before = sim.to_snapshot()
        with patch.object(app, "_save_and_end_report") as save_and_end:
            app.finalize_if_done()
        save_and_end.assert_not_called()
        self.assertFalse(self.fake.session_state.ended)
        self.assertEqual(self.fake.session_state.academy_flow_page, "")
        self.assertEqual(sim.to_snapshot(), before)

    def test_pretest_and_posttest_still_auto_finalize(self):
        cases = (
            ("课前测评", ACADEMY_INITIAL),
            ("课后考核", ACADEMY_VARIANT),
        )
        for phase, path in cases:
            with self.subTest(phase=phase):
                self._start(phase, "exam", path)
                run_compliant_path(self.fake.session_state.active_simulator)
                with patch.object(app, "_save_and_end_report") as save_and_end:
                    app.finalize_if_done()
                save_and_end.assert_called_once()

    def test_continue_manual_confirmation_preserves_training_state(self):
        self._start("模拟训练", "coach", ACADEMY_INITIAL)
        sim = self.fake.session_state.active_simulator
        run_compliant_path(sim)
        before = sim.to_snapshot()
        self.fake.session_state.manual_completion_confirmation = True
        self.fake.session_state.manual_completion_confirmation = False
        self.assertEqual(sim.to_snapshot(), before)
        self.assertFalse(self.fake.session_state.result_saved)

    def test_confirm_training_completion_saves_only_once(self):
        self._start("模拟训练", "coach", ACADEMY_INITIAL)
        sim = self.fake.session_state.active_simulator
        run_compliant_path(sim)
        sim.mark_manual_rescue_completion()
        report = app.enrich_report(
            sim.build_report(),
            end_reason="participant_confirmed_rescue_complete",
        )
        with patch.object(
            app,
            "save_report",
            return_value=("training.json", "training.md"),
        ) as save_report, patch.object(
            app,
            "save_result_record",
            return_value=None,
        ) as save_record:
            app._save_and_end_report(
                report,
                "participant_confirmed_rescue_complete",
            )
            app._save_and_end_report(
                report,
                "participant_confirmed_rescue_complete",
            )
        save_report.assert_called_once()
        save_record.assert_called_once()
        self.assertEqual(
            self.fake.session_state.academy_flow_page,
            "training_complete",
        )

    def test_flow_pages_cannot_skip_stage_order(self):
        reports = {"pretest": {}}
        self.assertTrue(academy_flow_page_allowed("pretest_complete", reports))
        self.assertFalse(academy_flow_page_allowed("training_complete", reports))
        self.assertFalse(academy_flow_page_allowed("posttest_result", reports))
        self.assertFalse(academy_flow_page_allowed("questionnaire", reports))

    def test_questionnaire_requires_all_three_reports(self):
        reports = {
            "pretest": {},
            "training": {},
            "posttest": {},
        }
        self.assertTrue(academy_flow_page_allowed("questionnaire", reports))
        self.assertEqual(latest_allowed_academy_page(reports), "posttest_result")

    def test_flow_complete_requires_questionnaire_completion(self):
        reports = {
            "pretest": {},
            "training": {},
            "posttest": {},
        }
        self.assertFalse(academy_flow_page_allowed("flow_complete", reports))
        self.assertTrue(
            academy_flow_page_allowed(
                "flow_complete",
                reports,
                questionnaire_completed=True,
            )
        )

    def test_three_stage_flow_keeps_participant_and_uses_distinct_sessions(self):
        participant = self.fake.session_state.participant_id
        session_ids = []
        with patch.object(
            app,
            "save_report",
            return_value=("auto.json", "auto.md"),
        ), patch.object(app, "save_result_record", return_value=None):
            self._start("课前测评", "exam", ACADEMY_INITIAL)
            run_compliant_path(self.fake.session_state.active_simulator)
            pre_report = app.enrich_report(
                self.fake.session_state.active_simulator.build_report(),
                end_reason="success",
            )
            app._save_and_end_report(pre_report, "success")
            session_ids.append(self.fake.session_state.session_id)
            self.assertEqual(
                self.fake.session_state.academy_flow_page,
                "pretest_complete",
            )
            self.assertFalse(
                self.fake.session_state.pending_academy_post_evaluation
            )

            self.assertTrue(app._start_next_academy_stage("模拟训练"))
            run_compliant_path(self.fake.session_state.active_simulator)
            training_report = app.enrich_report(
                self.fake.session_state.active_simulator.build_report(),
                end_reason="success",
            )
            app._save_and_end_report(training_report, "success")
            session_ids.append(self.fake.session_state.session_id)
            self.assertEqual(
                self.fake.session_state.academy_flow_page,
                "training_complete",
            )
            self.assertFalse(
                self.fake.session_state.pending_academy_post_evaluation
            )

            self.assertTrue(app._start_next_academy_stage("课后考核"))
            run_compliant_path(self.fake.session_state.active_simulator)
            post_report = app.enrich_report(
                self.fake.session_state.active_simulator.build_report(),
                end_reason="success",
            )
            app._save_and_end_report(post_report, "success")
            session_ids.append(self.fake.session_state.session_id)

        self.assertEqual(self.fake.session_state.participant_id, participant)
        self.assertEqual(len(set(session_ids)), 3)
        self.assertEqual(
            self.fake.session_state.academy_flow_page,
            "posttest_result",
        )
        self.assertEqual(
            set(self.fake.session_state.academy_stage_reports),
            {"pretest", "training", "posttest"},
        )
        self.assertTrue(
            self.fake.session_state.pending_academy_post_evaluation
        )

    def test_academy_completion_page_restores_without_resaving(self):
        with patch.object(
            app,
            "save_report",
            return_value=("auto.json", "auto.md"),
        ), patch.object(app, "save_result_record", return_value=None):
            self._start("课前测评", "exam", ACADEMY_INITIAL)
            run_compliant_path(self.fake.session_state.active_simulator)
            report = app.enrich_report(
                self.fake.session_state.active_simulator.build_report(),
                end_reason="success",
            )
            app._save_and_end_report(report, "success")
        query = dict(self.fake.query_params)
        refreshed = FakeStreamlit()
        refreshed.query_params.update(query)
        app.st = refreshed
        app.init_session()
        self.assertTrue(app.restore_training_draft_from_query())
        self.assertEqual(
            refreshed.session_state.academy_flow_page,
            "pretest_complete",
        )
        self.assertTrue(refreshed.session_state.result_saved)
        self.assertIn("pretest", refreshed.session_state.academy_stage_reports)

    def test_completion_page_text_and_result_title_are_user_facing(self):
        for empty_value in (None, "None", "null", [], "[]"):
            with self.subTest(empty_value=empty_value):
                report = {
                    "clinical_pathway_flags": {
                        "completion_rate_at_manual_finish": empty_value,
                    },
                    "key_timeline": {"reassess_count": 1},
                }
                text = training_completion_status_text(report)
                self.assertEqual(text, "有效复评次数：1次。")
                for internal_value in ("None", "null", "[]"):
                    self.assertNotIn(internal_value, text)
        self.assertEqual(
            academy_completion_page_title("posttest_result"),
            "课后考核结果与三阶段对比",
        )

    def test_questionnaire_button_copy_and_current_neutral_defaults(self):
        self.assertEqual(questionnaire_submit_button_label("pending"), "提交评价")
        self.assertEqual(
            questionnaire_submit_button_label("failed"),
            "重新提交评价",
        )
        self.assertEqual(
            app._normalized_questionnaire_values(None, 3),
            [3, 3, 3],
        )

    def test_completed_flow_has_completed_sidebar_labels(self):
        self.assertEqual(
            academy_sidebar_status(
                "flow_complete",
                "课后考核",
                "考试模式",
            ),
            ("全流程完成", "已完成"),
        )

    def test_training_failure_and_manual_confirmation_remain_finalizable(self):
        self.assertTrue(
            should_auto_finalize_academy_phase(
                "模拟训练",
                "coach",
                "failure",
            )
        )
        self.assertTrue(
            should_auto_finalize_academy_phase(
                "模拟训练",
                "coach",
                "participant_confirmed_rescue_complete",
            )
        )


class EntryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.original_st = app.st
        self.fake = FakeStreamlit()
        app.st = self.fake
        app.init_session()

    def tearDown(self):
        app.st = self.original_st

    def test_production_mode_keeps_clinical_and_academy_entry_options(self):
        self.assertEqual(
            set(app.SYSTEM_MODE_OPTIONS),
            {"clinical", "academy"},
        )

    def test_competition_participant_uses_only_virtual_identity(self):
        with patch.object(app, "APP_MODE", "competition"):
            app.setup_competition_participant("academy")
        state = self.fake.session_state
        self.assertTrue(state.participant_id.startswith("COMP-ACAD-"))
        self.assertEqual(state.school_name, "示范护理学院")
        self.assertEqual(state.collection_mode, "测试演练")
        self.assertNotEqual(state.institution, app.DEFAULT_INSTITUTION)

    def test_questionnaire_repeat_after_completion_is_stable(self):
        self.fake.session_state.questionnaire_submit_status = "completed"
        self.fake.session_state.academy_post_evaluation_completed = True
        ok, message = app.submit_academy_post_evaluation(
            [3] * len(app.SUS_ITEMS),
            [3] * len(app.TEACHING_EXPERIENCE_ITEMS),
        )
        self.assertTrue(ok)
        self.assertIn("请勿重复提交", message)

    def test_leaving_competition_clears_review_and_admin_authority(self):
        self.fake.session_state.competition_review_unlocked = True
        self.fake.session_state.competition_admin_unlocked = True
        self.fake.session_state.admin_unlocked = True
        self.fake.session_state.admin_scope = {"role": "competition_admin"}
        with patch.object(app, "APP_MODE", "competition"):
            app.clear_competition_session()
        self.assertFalse(self.fake.session_state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
