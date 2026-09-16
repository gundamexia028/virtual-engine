from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402


class State(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class DummySim:
    def __init__(self):
        self.state = SimpleNamespace(
            t=90,
            vitals={"Temp": 36.8, "SpO2": 94, "HR": 142, "RR": 32, "SBP": 82, "DBP": 48},
            flags={
                "dead": False,
                "cardiac_arrest": False,
                "resuscitation_rosc": False,
                "monitor_on": True,
                "bp_checked": True,
            },
            symptoms={"rash": 1, "angioedema": 0, "wheeze": 1, "stridor": 0, "gi": 0, "consciousness": 0},
        )
        self.log = []
        self.score = 0
        self.max_score = 100

    def age_sbp_threshold(self):
        return 84


class ReviewLiveVitalsHotfixTests(unittest.TestCase):
    def setUp(self):
        try:
            app.st.session_state.clear()
            app.st.session_state["session_id"] = "REVIEW-HOTFIX-TEST"
        except Exception:
            pass

    def test_clinical_live_display_changes_without_mutating_simulator(self):
        sim = DummySim()
        before_vitals = deepcopy(sim.state.vitals)
        before_t = sim.state.t
        with patch.object(app, "current_flow_strategy", return_value=SimpleNamespace(system_mode="clinical")):
            first = app.live_display_vitals(sim, bucket=10)
            second = app.live_display_vitals(sim, bucket=11)
        self.assertNotEqual(first, second)
        self.assertEqual(sim.state.vitals, before_vitals)
        self.assertEqual(sim.state.t, before_t)

    def test_academy_live_display_changes_without_mutating_simulator(self):
        sim = DummySim()
        before_vitals = deepcopy(sim.state.vitals)
        before_t = sim.state.t
        with patch.object(app, "current_flow_strategy", return_value=SimpleNamespace(system_mode="academy")):
            first = app.live_display_vitals(sim, bucket=10)
            second = app.live_display_vitals(sim, bucket=11)
        self.assertNotEqual(first, second)
        self.assertEqual(sim.state.vitals, before_vitals)
        self.assertEqual(sim.state.t, before_t)

    def test_clinical_renderer_uses_direct_html(self):
        sim = DummySim()
        scenario = {
            "patient": {"setting": "儿科普通病区（床旁）", "age_years": 5, "weight_kg": 18, "trigger": "静脉用药后出现症状"},
            "baseline": {"time_zero_description": "测试病例"},
        }
        changes = {"clinical": False, "symptoms": False, "score": False, "reassess": False, "vitals": set()}
        with (
            patch.object(app, "current_flow_strategy", return_value=SimpleNamespace(system_mode="clinical")),
            patch.object(app, "symptoms_text", return_value="皮疹/风团、咳嗽/喘息。"),
            patch.object(app.st, "html") as html_mock,
            patch.object(app.st, "markdown") as markdown_mock,
        ):
            app._render_patient_status_body(sim, scenario, changes, live_monitor=True, direct_html=True)
        html_mock.assert_called_once()
        markdown_mock.assert_not_called()
        rendered = str(html_mock.call_args.args[0])
        self.assertIn("clinical-card", rendered)
        self.assertIn("vital-grid", rendered)
        self.assertNotIn("```", rendered)

    def test_academy_renderer_uses_direct_html_and_keeps_context(self):
        sim = DummySim()
        scenario = {
            "patient": {"setting": "儿科普通病房/护理实训室", "age_years": 5, "weight_kg": 18, "trigger": "静脉用药后出现症状"},
            "baseline": {"time_zero_description": "学院测试病例"},
        }
        changes = {"clinical": False, "symptoms": False, "score": False, "reassess": False, "vitals": set()}
        app.st.session_state["academy_scenario_name"] = "严重过敏反应/过敏性休克抢救"
        with (
            patch.object(app, "current_flow_strategy", return_value=SimpleNamespace(system_mode="academy")),
            patch.object(app, "academy_scenario_display_name", return_value="严重过敏反应/过敏性休克抢救"),
            patch.object(app, "symptoms_text", return_value="皮疹/风团、咳嗽/喘息、烦躁。"),
            patch.object(app.st, "html") as html_mock,
            patch.object(app.st, "markdown") as markdown_mock,
        ):
            app._render_patient_status_body(sim, scenario, changes, live_monitor=True, direct_html=True)
        html_mock.assert_called_once()
        markdown_mock.assert_not_called()
        rendered = str(html_mock.call_args.args[0])
        self.assertIn("教学情景", rendered)
        self.assertIn("vital-grid", rendered)



if __name__ == "__main__":
    unittest.main()
