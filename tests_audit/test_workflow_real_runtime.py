"""Real Streamlit AppTest C03/C04 regressions, explicitly NOT browser evidence.

Uses the guarded, synthetic-participant fixture and production render/callbacks.
Run in a fresh process with real Streamlit installed. VE_WORKFLOW_ROOT selects
an immutable baseline source tree; all persistence goes to a disposable folder.
"""
from __future__ import annotations
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REAL_STREAMLIT = importlib.util.find_spec('streamlit') is not None
CLINICAL = ['stop_infusion', 'call_help', 'abc_assess', 'high_flow_oxygen', 'shock_position', 'connect_monitor', 'check_bp', 'im_epinephrine', 'fluid_bolus', 'reassess_first', 'bronchodilator', 'steroid', 'reassess_second', 'family_explain', 'sbar_handoff']
ACADEMY = ['allergy_identification', 'stop_infusion', 'call_help', 'high_flow_oxygen', 'connect_monitor', 'check_bp', 'prepare_rescue_equipment', 'academy_medication_check', 'academy_assisted_medication', 'academy_reassess', 'academy_family_communication', 'academy_sbar_handoff']


@unittest.skipUnless(REAL_STREAMLIT, 'Real Streamlit runtime unavailable; no mock substituted')
class WorkflowRealRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='workflow-apptest-')
        cls.env = patch.dict(os.environ, {
            'APP_MODE': 'production', 'VE_AUDIT_BROWSER_FIXTURE': '1',
            'PEDSIM_RESULTS_DIR': str(Path(cls.tmp.name) / 'runs'),
            'PEDSIM_DRAFTS_DIR': str(Path(cls.tmp.name) / 'drafts'),
            'SUPABASE_URL': '', 'SUPABASE_KEY': '', 'SUPABASE_ANON_KEY': '',
            'SUPABASE_SERVICE_ROLE_KEY': '',
        })
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.tmp.cleanup()

    def start(self, case):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(HERE / 'browser_fixture_app.py'), default_timeout=15).run()
        self.assertEqual(len(at.exception), 0, str(at.exception))
        if at.selectbox[0].value != case:
            at.selectbox[0].select(case).run()
        self.assertEqual(len(at.exception), 0, str(at.exception))
        return at

    def click_label(self, at, label):
        buttons = [b for b in at.button if b.label == label]
        self.assertEqual(len(buttons), 1, f'Expected one {label}; actual {[b.label for b in at.button]}')
        buttons[0].click().run()
        self.assertEqual(len(at.exception), 0, str(at.exception))

    def action(self, at, aid):
        sid = at.session_state.session_id
        before = at.session_state.active_simulator.state.t
        at.button(key=f'action_{sid}_{aid}').click().run()
        self.assertEqual(len(at.exception), 0, str(at.exception))
        if aid in ('im_epinephrine', 'fluid_bolus', 'steroid'):
            w = at.session_state.active_simulator.state.weight_kg
            kind, label, value = {
                'im_epinephrine': ('epinephrine', '本次肌注总剂量（mg）', min(.01 * w, .3)),
                'fluid_bolus': ('fluid', '本次快速补液容量（ml）', 10 * w),
                'steroid': ('steroid', '本次甲泼尼龙剂量（mg）', min(w, 40)),
            }[aid]
            matches = [n for n in at.number_input if n.label == label]
            self.assertEqual(len(matches), 1)
            matches[0].set_value(float(value))
            at.button(key=f'confirm_{kind}_{sid}').click().run()
            self.assertEqual(len(at.exception), 0, str(at.exception))
        return before, at.session_state.active_simulator.state.t

    def test_c03_training_terminal_return_view_stays_readonly_and_reset_reopens(self):
        for case in ('clinical_initial_coach', 'clinical_variant_coach',
                     'academy_initial_coach', 'academy_variant_coach'):
            with self.subTest(case=case):
                at = self.start(case)
                for aid in ACADEMY if case.startswith('academy') else CLINICAL:
                    self.action(at, aid)
                sim = at.session_state.active_simulator
                self.assertTrue(sim.is_done()[0])
                frozen = copy.deepcopy(sim.to_snapshot())
                sid = at.session_state.session_id
                if case.startswith('academy'):
                    self.click_label(at, '我已确认完成抢救')
                    self.assertNotIn('继续操作', [b.label for b in at.button])
                    self.click_label(at, '返回查看')
                    self.assertFalse(at.session_state.manual_completion_confirmation)
                    controls = [b for b in at.button if b.key and (b.key.startswith(f'action_{sid}_') or b.key == f'advance_time_{sid}')]
                    self.assertTrue(controls)
                    self.assertTrue(all(b.disabled for b in controls))
                else:
                    # Clinical successful training already auto-enters its result
                    # page; preserve that separate workflow rather than inventing
                    # an academy-style manual-confirmation step.
                    self.assertTrue(at.session_state.ended)
                    self.assertFalse(any(b.key and b.key.startswith(f'action_{sid}_') for b in at.button))
                    self.assertNotIn('继续操作', [b.label for b in at.button])
                self.assertEqual(frozen, at.session_state.active_simulator.to_snapshot())
                at.run()  # a real rerender must not advance the completed episode
                self.assertEqual(frozen, at.session_state.active_simulator.to_snapshot())
                self.click_label(at, '重新开始审计病例')
                self.assertNotEqual(at.session_state.session_id, sid)
                self.assertEqual(at.session_state.active_simulator.state.t, 0)
                self.assertFalse(at.session_state.active_simulator.is_done()[0])
                self.assertFalse(at.button(key=f'advance_time_{at.session_state.session_id}').disabled)
                self.action(at, 'stop_infusion')
                self.assertEqual(at.session_state.active_simulator.state.t, 30)

    def test_c03_unfinished_clinical_cancel_still_allows_actions(self):
        at = self.start('clinical_initial_coach')
        self.click_label(at, '我已确认完成抢救')
        self.click_label(at, '继续操作')
        self.assertNotIn('返回查看', [b.label for b in at.button])
        self.assertFalse(at.session_state.manual_completion_confirmation)
        self.action(at, 'stop_infusion')
        self.assertEqual(at.session_state.active_simulator.state.t, 30)

    def test_c04_real_academy_reassessment_callback_advances_without_rescoring(self):
        for role in ('initial', 'variant'):
            for mode in ('coach', 'exam'):
                case = f'academy_{role}_{mode}'
                with self.subTest(case=case):
                    at = self.start(case)
                    for aid in ACADEMY[:-2]:
                        self.action(at, aid)
                    sim = at.session_state.active_simulator
                    score, first_valid = sim.score, sim.action_valid_time['academy_reassess']
                    awards = copy.deepcopy(sim.state.flags.get('score_awards', []))
                    for _ in range(2):
                        before_t, after_t = self.action(at, 'academy_reassess')
                        self.assertEqual(after_t, before_t + sim.tick_seconds)
                        sim = at.session_state.active_simulator
                        self.assertEqual(sim.score, score)
                        self.assertEqual(sim.action_valid_time['academy_reassess'], first_valid)
                        self.assertEqual(sim.state.flags.get('score_awards', []), awards)
                        latest = next(e for e in reversed(sim.log) if e.kind == 'action')
                        self.assertEqual(latest.message, 'academy_reassess')
                        self.assertEqual(latest.data['status'], 'valid')
                        self.assertEqual(latest.data['gained'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
