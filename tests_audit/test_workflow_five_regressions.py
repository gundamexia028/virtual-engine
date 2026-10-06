"""C01-C05 executable contracts against either candidate or immutable baseline.

Run with VE_WORKFLOW_ROOT=/absolute/source/root to test another source tree.
Uses real engine/controller; UI rendering is covered by browser_workflow_regressions.
Synthetic cases only. No network, storage, or medical-rubric changes.
"""
from __future__ import annotations
import copy
import hashlib
import itertools
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(os.environ.get('VE_WORKFLOW_ROOT', Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / 'app'))
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.scenario_loader import load_scenario_by_role
from ui_commands import execute_command, revision

ROLES = ('initial', 'variant', 'academy_initial', 'academy_variant')
MODES = ('coach', 'exam')
CLINICAL = ['stop_infusion', 'call_help', 'abc_assess', 'high_flow_oxygen', 'shock_position', 'connect_monitor', 'check_bp', 'im_epinephrine', 'fluid_bolus', 'reassess_first', 'bronchodilator', 'steroid', 'reassess_second', 'family_explain', 'sbar_handoff']
ACADEMY = ['allergy_identification', 'stop_infusion', 'call_help', 'high_flow_oxygen', 'connect_monitor', 'check_bp', 'prepare_rescue_equipment', 'academy_medication_check', 'academy_assisted_medication', 'academy_reassess', 'academy_family_communication', 'academy_sbar_handoff']


def make(role='initial', mode='coach'):
    return Simulator(load_scenario_by_role(role), mode=mode, seed=17)


def step(sim, aid, tick=True):
    if aid == 'im_epinephrine':
        result = sim.apply_epinephrine_dose(round(min(.01 * sim.state.weight_kg, .3), 3))
    elif aid == 'fluid_bolus':
        result = sim.apply_fluid_bolus_volume(10 * sim.state.weight_kg)
    elif aid == 'steroid':
        result = sim.apply_steroid_dose(min(sim.state.weight_kg, 40))
    else:
        result = sim.apply_action(aid)
    if tick:
        sim.tick()
    return result


def standard(sim, skip=()):
    for aid in ACADEMY if sim._is_academy_basic_case() else CLINICAL:
        if aid not in skip:
            step(sim, aid)
    return sim


def state(sim, session='workflow-run'):
    return {'active_simulator': sim, 'session_id': session, 'ended': False,
            'manual_completion_confirmation': False}


def command(s, cmd, aid='', value=None):
    return execute_command(s, s['session_id'], revision(s['active_simulator']), cmd, aid, value)


class WorkflowFiveDefectTests(unittest.TestCase):
    def test_c01_clinical_missing_abc_or_position_cannot_succeed(self):
        for role, mode, omitted in itertools.product(ROLES[:2], MODES, ('abc_assess', 'shock_position')):
            with self.subTest(role=role, mode=mode, omitted=omitted):
                sim = standard(make(role, mode), (omitted,))
                self.assertNotIn(sim.is_done()[1], ('success', 'standard_assessment_completed'))
                self.assertTrue(sim._unfinished_required_steps())
                self.assertTrue(sim.build_report()['critical_missing'])

    def test_c01_all_eight_complete_paths_still_finish_at_full_score(self):
        for role, mode in itertools.product(ROLES, MODES):
            with self.subTest(role=role, mode=mode):
                sim = standard(make(role, mode))
                self.assertTrue(sim.is_done()[0])
                self.assertIn(sim.is_done()[1], ('success', 'standard_assessment_completed'))
                self.assertEqual(sim.build_report()['score'], 100)
                self.assertEqual(sim._unfinished_required_steps(), [])

    def test_c02_stop_continue_flags_are_consistent_all_eight(self):
        for role, mode in itertools.product(ROLES, MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                step(sim, 'stop_infusion')
                step(sim, 'call_help')
                step(sim, 'high_flow_oxygen')
                step(sim, 'continue_infusion')
                # The academy distractor is 'continue observing', not restarting
                # a stopped infusion. Preserve that distinct role contract.
                is_clinical = role in ROLES[:2]
                self.assertIs(sim.state.flags['infusion_running'], is_clinical)
                self.assertIs(sim.state.flags['stopped_infusion'], not is_clinical)
                self.assertTrue(sim._unfinished_required_steps())

    def test_c02_no_medication_deterioration_does_not_freeze_after_resume(self):
        for role, mode in itertools.product(ROLES, MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                for aid in ('stop_infusion', 'call_help', 'high_flow_oxygen', 'continue_infusion'):
                    step(sim, aid)
                t0, vitals = sim.state.t, copy.deepcopy(sim.state.vitals)
                for _ in range(6):
                    sim.tick()
                self.assertGreater(sim.state.t, t0)
                self.assertFalse(sim.state.flags['epi_im_given'])
                self.assertLess(sim.state.vitals['SBP'], vitals['SBP'])
                self.assertNotIn(sim.is_done()[1], ('success', 'standard_assessment_completed'))

    def test_c02_resume_then_stop_restores_state_without_rescoring(self):
        for role, mode in itertools.product(ROLES, MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                sim.apply_action('stop_infusion')
                sim.apply_action('continue_infusion')
                score, penalties = sim.score, sim.penalties
                sim.apply_action('stop_infusion')
                self.assertIs(sim.state.flags['infusion_running'], False)
                self.assertIs(sim.state.flags['stopped_infusion'], True)
                self.assertEqual(sim.score, score)
                self.assertEqual(sim.penalties, penalties)

    def test_c02_multiple_clinical_stop_resume_cycles_without_extra_score(self):
        for role, mode in itertools.product(ROLES[:2], MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                sim.apply_action('stop_infusion')
                score = sim.score
                first_stop = sim.action_valid_time['stop_infusion']
                for _ in range(3):
                    sim.apply_action('continue_infusion')
                    self.assertIs(sim.state.flags['infusion_running'], True)
                    self.assertIs(sim.state.flags['stopped_infusion'], False)
                    sim.apply_action('stop_infusion')
                    self.assertIs(sim.state.flags['infusion_running'], False)
                    self.assertIs(sim.state.flags['stopped_infusion'], True)
                    self.assertEqual(sim.score, score)
                    self.assertEqual(sim.action_valid_time['stop_infusion'], first_stop)

    def test_academy_scenario_bytes_preserve_baseline_contract(self):
        expected = {
            'peds_ward_allergy_academy_initial.json': '3921241d529b28d8d4309455eab6a017e4899faa89779e12d336f1712e8d976b',
            'peds_ward_allergy_academy_variant.json': 'c379745d516e060df4b630674a223d0b01cb9d082032db2ddb172d34149e1e5f',
        }
        for name, digest in expected.items():
            with self.subTest(scenario=name):
                content = (ROOT / 'app/peds_anaphylaxis_sim/scenarios' / name).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), digest)

    def test_c03_completed_run_rejects_all_mutable_commands(self):
        for role, mode in itertools.product(ROLES, MODES):
            with self.subTest(role=role, mode=mode):
                sim = standard(make(role, mode))
                self.assertTrue(sim.is_done()[0])
                s = state(sim)
                before = copy.deepcopy(sim.to_snapshot())
                for cmd, aid, value in [('action', 'stop_infusion', None), ('advance_time', '', None),
                                        ('epinephrine', 'im_epinephrine', .1), ('fluid', 'fluid_bolus', 100),
                                        ('steroid', 'steroid', 10)]:
                    r = command(s, cmd, aid, value)
                    self.assertEqual(r['status'], 'terminal')
                    self.assertFalse(r['accepted'])
                    self.assertFalse(r['tick_advanced'])
                self.assertEqual(before, sim.to_snapshot())

    def test_c03_terminal_confirmation_cancel_does_not_reopen_engine(self):
        for role in ROLES:
            with self.subTest(role=role):
                sim = standard(make(role, 'coach'))
                s = state(sim)
                before = copy.deepcopy(sim.to_snapshot())
                s['manual_completion_confirmation'] = True
                s['manual_completion_confirmation'] = False
                self.assertEqual(command(s, 'advance_time')['status'], 'terminal')
                self.assertEqual(before, sim.to_snapshot())

    def test_c03_render_source_offers_return_to_view_for_terminal_state(self):
        # A source contract catches the baseline UX promise; the real browser test
        # separately checks the rendered button and disabled controls.
        source = (ROOT / 'app/streamlit_app.py').read_text(encoding='utf-8')
        self.assertTrue('返回查看' in source, 'Terminal confirmation must offer 返回查看, not 继续操作')

    def test_c04_academy_repeat_reassessment_is_effective_and_unscored(self):
        for role, mode in itertools.product(ROLES[2:], MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                for aid in ACADEMY[:-2]:
                    step(sim, aid)
                s = state(sim)
                score = sim.score
                awards = copy.deepcopy(sim.state.flags.get('score_awards', []))
                first_valid = sim.action_valid_time['academy_reassess']
                for _ in range(3):
                    t0, log0 = sim.state.t, len(sim.log)
                    r = command(s, 'action', 'academy_reassess')
                    self.assertTrue(r['accepted'], r)
                    self.assertTrue(r['tick_advanced'], r)
                    self.assertEqual(sim.state.t, t0 + sim.tick_seconds)
                    entries = [e for e in sim.log[log0:] if e.kind == 'action' and e.message == 'academy_reassess']
                    self.assertEqual(len(entries), 1)
                    self.assertEqual(entries[0].data.get('status'), 'valid')
                    self.assertEqual(entries[0].data.get('gained'), 0)
                    self.assertEqual(sim.score, score)
                    self.assertEqual(sim.state.flags.get('score_awards', []), awards)
                    self.assertEqual(sim.action_valid_time['academy_reassess'], first_valid)

    def test_c04_repeated_event_replay_does_not_double_tick_or_log(self):
        for role, mode in itertools.product(ROLES[2:], MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                for aid in ACADEMY[:-2]:
                    step(sim, aid)
                s = state(sim)
                old = revision(sim)
                accepted = execute_command(s, s['session_id'], old, 'action', 'academy_reassess')
                self.assertTrue(accepted['accepted'])
                before = copy.deepcopy(sim.to_snapshot())
                self.assertEqual(execute_command(s, s['session_id'], old, 'action', 'academy_reassess')['status'], 'stale_event')
                self.assertEqual(before, sim.to_snapshot())

    def test_c04_clinical_reassessment_semantics_are_unchanged(self):
        for role, mode in itertools.product(ROLES[:2], MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                for aid in CLINICAL[:-2]:
                    step(sim, aid)
                score, first_valid = sim.score, sim.action_valid_time['reassess_second']
                s = state(sim)
                for _ in range(2):
                    before = sim.state.t
                    self.assertTrue(command(s, 'action', 'reassess_second')['accepted'])
                    self.assertEqual(sim.state.t, before + sim.tick_seconds)
                    self.assertEqual(sim.score, score)
                    self.assertEqual(sim.action_valid_time['reassess_second'], first_valid)
                self.assertNotIn('academy_reassess', sim.action_first_time)

    def test_c05_historical_order_violations_survive_correction_and_report(self):
        for role, mode in itertools.product(ROLES, MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                if role in ROLES[:2]:
                    # Isolate report persistence from the pre-existing severe
                    # epinephrine-delay branch: first deliver actual treatment.
                    for aid in CLINICAL[:8]:
                        step(sim, aid)
                early = ['academy_assisted_medication', 'academy_reassess', 'academy_family_communication', 'academy_sbar_handoff'] if role.startswith('academy') else ['reassess_first', 'reassess_second', 'family_explain', 'sbar_handoff']
                for aid in early:
                    step(sim, aid, tick=False)
                violations = copy.deepcopy(sim.state.flags['order_violations'])
                self.assertEqual(set(violations), set(early))
                if role in ROLES[:2]:
                    for aid in CLINICAL[8:]:
                        step(sim, aid)
                else:
                    standard(sim)
                report = sim.build_report()
                self.assertTrue(sim.is_done()[0])
                self.assertEqual(sim._unfinished_required_steps(), [])
                self.assertLess(report['score'], 100)
                self.assertEqual(report['clinical_pathway_flags']['order_violations'], violations)
                issues = '\n'.join(report['process_safety_issues'])
                if role.startswith('academy'):
                    for aid, value in violations.items():
                        self.assertTrue(aid in issues or value['reason'] in issues,
                                        f'{aid}: history disappeared from process_safety_issues: {issues}')
                else:
                    # C05 is scoped to academy summaries. Preserve the exact
                    # established clinical reporting and scoring contract.
                    self.assertEqual(report['process_safety_issues'], ['家属告知早于第二次复评'])
                    self.assertEqual((report['score'], report['raw_score'], report['penalties']), (88, 88, 0))

    def test_time_duplicate_reset_and_case_mode_isolation(self):
        for role, mode in itertools.product(ROLES, MODES):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                s = state(sim)
                old = revision(sim)
                self.assertTrue(execute_command(s, s['session_id'], old, 'action', 'stop_infusion')['accepted'])
                after_one = copy.deepcopy(sim.to_snapshot())
                self.assertEqual(execute_command(s, s['session_id'], old, 'action', 'stop_infusion')['status'], 'stale_event')
                self.assertEqual(after_one, sim.to_snapshot())
                self.assertEqual(sim.state.t, sim.tick_seconds)
                self.assertTrue(command(s, 'advance_time')['accepted'])
                self.assertEqual(sim.state.t, 2 * sim.tick_seconds)
                other_role = 'academy_initial' if role in ROLES[:2] else 'initial'
                fresh = make(other_role, 'exam' if mode == 'coach' else 'coach')
                s.update(active_simulator=fresh, session_id='reset-run')
                clean = copy.deepcopy(fresh.to_snapshot())
                self.assertEqual(execute_command(s, 'workflow-run', revision(sim), 'advance_time')['status'], 'stale_event')
                self.assertEqual(clean, fresh.to_snapshot())
                self.assertEqual(fresh.state.t, 0)
                self.assertEqual(fresh.score, 0)
                self.assertFalse(fresh.state.flags.get('order_violations', {}))
                self.assertIs(fresh.state.flags['infusion_running'], True)
                self.assertIs(fresh.state.flags['stopped_infusion'], False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
