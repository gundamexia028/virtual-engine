from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from peds_anaphylaxis_sim.engine import Simulator  # noqa: E402
from peds_anaphylaxis_sim.flow_strategies import (  # noqa: E402
    FLOW_PHASE_DEFINITIONS,
    FLOW_STRATEGIES,
    FlowStrategyError,
    build_workflow_config,
    flow_phase_definition,
    flow_strategies,
    flow_strategy,
    flow_strategy_for_modes,
    flow_strategy_for_phase,
    flow_strategy_for_scenario,
    infer_system_mode,
    phase_options,
    system_mode_options,
    validate_flow_strategies,
)
from peds_anaphylaxis_sim.scenario_loader import (  # noqa: E402
    load_registered_scenario,
)


FLOW_SCENARIOS = {
    "clinical_training": (
        "peds_ward_anaphylaxis_iv_initial",
        "coach",
    ),
    "clinical_exam": (
        "peds_ward_anaphylaxis_iv_variantA",
        "exam",
    ),
    "academy_training": (
        "peds_ward_allergy_academy_initial",
        "coach",
    ),
    "academy_exam": (
        "peds_ward_allergy_academy_variant",
        "exam",
    ),
}


class FlowStrategyTests(unittest.TestCase):
    def test_exactly_four_current_flow_strategies_exist(self):
        self.assertEqual(
            [strategy.strategy_id for strategy in flow_strategies()],
            [
                "clinical_training",
                "clinical_exam",
                "academy_training",
                "academy_exam",
            ],
        )

    def test_all_four_mode_combinations_are_unique(self):
        combinations = {
            (strategy.system_mode, strategy.simulator_mode)
            for strategy in flow_strategies()
        }
        self.assertEqual(
            combinations,
            {
                ("clinical", "coach"),
                ("clinical", "exam"),
                ("academy", "coach"),
                ("academy", "exam"),
            },
        )

    def test_strategy_interface_covers_required_behavior_contracts(self):
        required_text_fields = (
            "strategy_id",
            "system_mode",
            "simulator_mode",
            "mode_label",
            "workflow_mode_label",
            "score_presentation",
            "error_handling",
            "end_condition_policy",
            "result_page_behavior",
        )
        for strategy in flow_strategies():
            with self.subTest(strategy=strategy.strategy_id):
                for field_name in required_text_fields:
                    self.assertTrue(str(getattr(strategy, field_name)).strip())
                self.assertEqual(
                    strategy.recovery.snapshot_schema_version,
                    1,
                )

    def test_system_mode_metadata_is_preserved(self):
        self.assertEqual(
            system_mode_options(),
            {
                "clinical": {
                    "label": "临床模式",
                    "subtitle": "面向临床护士/低年资护士，保留原严重过敏反应动态分支处置流程。",
                    "participant_type": "clinical_nurse",
                },
                "academy": {
                    "label": "学院模式",
                    "subtitle": "面向在校护生，进入通用情景库后选择教学情景；当前仅开放严重过敏反应/过敏性休克抢救。",
                    "participant_type": "nursing_student",
                },
            },
        )

    def test_phase_options_are_preserved(self):
        self.assertEqual(
            phase_options("clinical"),
            ("基线评估", "模拟培训", "培训后考核"),
        )
        self.assertEqual(
            phase_options("academy"),
            ("课前测评", "模拟训练", "课后考核"),
        )

    def test_phase_to_strategy_mapping_is_preserved(self):
        expected = {
            ("clinical", "基线评估"): "clinical_exam",
            ("clinical", "模拟培训"): "clinical_training",
            ("clinical", "培训后考核"): "clinical_exam",
            ("academy", "课前测评"): "academy_exam",
            ("academy", "模拟训练"): "academy_training",
            ("academy", "课后考核"): "academy_exam",
        }
        actual = {
            (phase.system_mode, phase.phase): phase.strategy_id
            for phase in FLOW_PHASE_DEFINITIONS
        }
        self.assertEqual(actual, expected)

    def test_clinical_workflow_metadata_is_preserved(self):
        baseline = build_workflow_config("clinical", "基线评估")
        training = build_workflow_config("clinical", "模拟培训")
        post_test = build_workflow_config("clinical", "培训后考核")
        self.assertEqual(
            (
                baseline["mode"],
                baseline["script_role"],
                baseline["display"],
            ),
            ("exam", "initial", "基线评估｜考试模式｜初始病例"),
        )
        self.assertEqual(
            (
                training["mode"],
                training["script_role"],
                training["display"],
            ),
            ("coach", "initial", "模拟培训｜训练模式｜初始病例"),
        )
        self.assertEqual(
            (
                post_test["mode"],
                post_test["script_role"],
                post_test["display"],
            ),
            (
                "exam",
                "variant",
                "培训后考核｜考试模式｜变体病例 Variant A",
            ),
        )

    def test_academy_workflow_metadata_is_preserved(self):
        metadata = {
            "id": "academy_anaphylaxis_rescue",
            "name": "严重过敏反应/过敏性休克抢救",
            "category": "急救护理",
            "course_type": "基础护理/急救护理/儿科护理",
            "difficulty": "基础版",
        }
        training = build_workflow_config(
            "academy",
            "模拟训练",
            library_id="academy_anaphylaxis_rescue",
            scenario_metadata=metadata,
        )
        post_test = build_workflow_config(
            "academy",
            "课后考核",
            library_id="academy_anaphylaxis_rescue",
            scenario_metadata=metadata,
        )
        self.assertEqual(
            (
                training["mode"],
                training["script_role"],
                training["display"],
            ),
            (
                "coach",
                "academy_initial",
                "模拟训练｜训练模式｜严重过敏反应/过敏性休克抢救｜过敏性休克抢救基础病例",
            ),
        )
        self.assertEqual(
            (
                post_test["mode"],
                post_test["script_role"],
                post_test["display"],
            ),
            (
                "exam",
                "academy_variant",
                "课后考核｜考试模式｜严重过敏反应/过敏性休克抢救｜过敏性休克抢救变体病例",
            ),
        )

    def test_invalid_phase_falls_back_to_existing_default_phase(self):
        self.assertEqual(
            flow_phase_definition("clinical", "unknown").phase,
            "基线评估",
        )
        self.assertEqual(
            flow_phase_definition("academy", "unknown").phase,
            "课前测评",
        )

    def test_unknown_strategy_and_modes_are_rejected(self):
        with self.assertRaises(FlowStrategyError):
            flow_strategy("unknown")
        with self.assertRaises(FlowStrategyError):
            flow_strategy_for_modes("clinical", "unknown")
        with self.assertRaises(FlowStrategyError):
            phase_options("unknown")

    def test_duplicate_strategy_id_is_rejected(self):
        entries = list(FLOW_STRATEGIES)
        entries[1] = replace(
            entries[1],
            strategy_id=entries[0].strategy_id,
        )
        with self.assertRaisesRegex(FlowStrategyError, "ids must be unique"):
            validate_flow_strategies(entries)

    def test_duplicate_strategy_mode_combination_is_rejected(self):
        entries = list(FLOW_STRATEGIES)
        entries[1] = replace(
            entries[1],
            system_mode=entries[0].system_mode,
            simulator_mode=entries[0].simulator_mode,
        )
        with self.assertRaisesRegex(
            FlowStrategyError,
            "mode combinations must be unique",
        ):
            validate_flow_strategies(entries)

    def test_duplicate_phase_mapping_is_rejected(self):
        phases = FLOW_PHASE_DEFINITIONS + (FLOW_PHASE_DEFINITIONS[0],)
        with self.assertRaisesRegex(
            FlowStrategyError,
            "Duplicate flow phase mapping",
        ):
            validate_flow_strategies(FLOW_STRATEGIES, phases)

    def test_phase_cannot_reference_other_system_strategy(self):
        phases = list(FLOW_PHASE_DEFINITIONS)
        phases[0] = replace(phases[0], strategy_id="academy_exam")
        with self.assertRaisesRegex(
            FlowStrategyError,
            "Flow phase strategy is invalid",
        ):
            validate_flow_strategies(FLOW_STRATEGIES, phases)

    def test_scenario_audience_inference_preserves_current_modes(self):
        clinical = load_registered_scenario(
            "peds_ward_anaphylaxis_iv_initial"
        )
        academy = load_registered_scenario(
            "peds_ward_allergy_academy_initial"
        )
        self.assertEqual(infer_system_mode(clinical), "clinical")
        self.assertEqual(infer_system_mode(academy), "academy")

    def test_each_flow_binds_the_expected_strategy_to_simulator(self):
        for strategy_id, (scenario_id, simulator_mode) in FLOW_SCENARIOS.items():
            with self.subTest(strategy=strategy_id):
                scenario = load_registered_scenario(scenario_id)
                simulator = Simulator(
                    scenario,
                    mode=simulator_mode,
                    seed=123,
                )
                self.assertEqual(
                    simulator.flow_strategy.strategy_id,
                    strategy_id,
                )
                self.assertIs(
                    flow_strategy_for_scenario(scenario, simulator_mode),
                    flow_strategy(strategy_id),
                )

    def test_training_flows_keep_guided_prompts_and_immediate_feedback(self):
        for strategy_id in ("clinical_training", "academy_training"):
            strategy = flow_strategy(strategy_id)
            with self.subTest(strategy=strategy_id):
                self.assertTrue(strategy.use_guided_prompts)
                self.assertTrue(strategy.show_immediate_feedback)
                self.assertEqual(strategy.score_presentation, "live")
                self.assertEqual(
                    strategy.error_handling,
                    "immediate_explanatory",
                )

    def test_exam_flows_keep_deferred_feedback_and_result_only_scores(self):
        for strategy_id in ("clinical_exam", "academy_exam"):
            strategy = flow_strategy(strategy_id)
            with self.subTest(strategy=strategy_id):
                self.assertFalse(strategy.use_guided_prompts)
                self.assertFalse(strategy.show_immediate_feedback)
                self.assertEqual(
                    strategy.score_presentation,
                    "result_only",
                )
                self.assertEqual(
                    strategy.error_handling,
                    "deferred_record_only",
                )

    def test_training_keeps_action_order_and_exam_keeps_seeded_shuffle(self):
        scenario = load_registered_scenario(
            "peds_ward_anaphylaxis_iv_initial"
        )
        original = [action["id"] for action in scenario["actions"]]
        training = Simulator(scenario, mode="coach", seed=123)
        exam_a = Simulator(scenario, mode="exam", seed=123)
        exam_b = Simulator(scenario, mode="exam", seed=123)
        self.assertEqual(training.action_order_labels, original)
        self.assertEqual(
            exam_a.action_order_labels,
            exam_b.action_order_labels,
        )
        self.assertNotEqual(exam_a.action_order_labels, original)

    def test_manual_completion_policy_is_preserved(self):
        self.assertTrue(
            flow_strategy("clinical_training").allow_manual_completion
        )
        self.assertTrue(
            flow_strategy("clinical_exam").allow_manual_completion
        )
        self.assertTrue(
            flow_strategy("academy_training").allow_manual_completion
        )
        self.assertFalse(
            flow_strategy("academy_exam").allow_manual_completion
        )

    def test_result_page_behavior_is_preserved(self):
        self.assertEqual(
            flow_strategy("clinical_training").result_page_behavior,
            "persistent_clinical_result",
        )
        self.assertEqual(
            flow_strategy("clinical_exam").result_page_behavior,
            "persistent_clinical_result",
        )
        self.assertEqual(
            flow_strategy("academy_training").result_page_behavior,
            "return_to_registration",
        )
        self.assertEqual(
            flow_strategy("academy_exam").result_page_behavior,
            "return_to_registration",
        )

    def test_questionnaire_transitions_are_phase_specific(self):
        self.assertEqual(
            flow_strategy_for_phase(
                "clinical",
                "基线评估",
            ).questionnaire_transition_for_phase("基线评估"),
            "prior_experience_survey",
        )
        self.assertEqual(
            flow_strategy_for_phase(
                "academy",
                "课前测评",
            ).questionnaire_transition_for_phase("课前测评"),
            "prior_experience_survey",
        )
        self.assertEqual(
            flow_strategy_for_phase(
                "academy",
                "课后考核",
            ).questionnaire_transition_for_phase("课后考核"),
            "academy_post_evaluation",
        )
        self.assertEqual(
            flow_strategy_for_phase(
                "clinical",
                "培训后考核",
            ).questionnaire_transition_for_phase("培训后考核"),
            "none",
        )

    def test_session_recovery_rules_are_explicit_for_all_flows(self):
        for strategy in flow_strategies():
            with self.subTest(strategy=strategy.strategy_id):
                self.assertTrue(strategy.recovery.restore_in_progress)
                self.assertTrue(strategy.recovery.clear_on_return_home)
                self.assertEqual(
                    strategy.recovery.snapshot_schema_version,
                    1,
                )
        self.assertTrue(
            flow_strategy("clinical_exam").recovery.preserve_completed_result
        )
        self.assertTrue(
            flow_strategy(
                "academy_exam"
            ).recovery.preserve_pending_questionnaire
        )

    def test_snapshot_schema_is_unchanged_and_strategy_is_reconstructed(self):
        scenario = load_registered_scenario(
            "peds_ward_allergy_academy_variant"
        )
        simulator = Simulator(scenario, mode="exam", seed=123)
        snapshot = simulator.to_snapshot()
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertNotIn("flow_strategy", snapshot)
        restored = Simulator.from_snapshot(snapshot)
        self.assertEqual(
            restored.flow_strategy.strategy_id,
            "academy_exam",
        )

    def test_only_academy_exam_uses_neutral_action_labels(self):
        neutral = [
            strategy.strategy_id
            for strategy in flow_strategies()
            if strategy.use_neutral_action_labels
        ]
        self.assertEqual(neutral, ["academy_exam"])

    def test_app_no_longer_defines_distributed_workflow_rules(self):
        source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn("WORKFLOW_RULES =", source)
        self.assertNotIn('"phase_script_roles":', source)
        self.assertNotIn('"phase_script_labels":', source)
        self.assertNotIn('"phase_tasks":', source)

    def test_app_and_engine_do_not_repeat_direct_simulator_mode_checks(self):
        app_source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        engine_source = (
            ROOT / "peds_anaphylaxis_sim" / "engine.py"
        ).read_text(encoding="utf-8")
        for fragment in (
            'sim.mode == "coach"',
            'sim.mode == "exam"',
            'sim.mode != "coach"',
            'sim.mode != "exam"',
        ):
            self.assertNotIn(fragment, app_source)
        for fragment in (
            'self.mode == "coach"',
            'self.mode == "exam"',
            'self.mode != "coach"',
            'self.mode != "exam"',
            'if mode == "exam":',
            "if mode == 'coach':",
        ):
            self.assertNotIn(fragment, engine_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
