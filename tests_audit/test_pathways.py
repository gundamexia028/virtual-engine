"""Directed, independently asserted pathway tests. Not exhaustive histories."""
import copy
import itertools
import unittest
from test_integrity import make, ROLES
from academy_interactions import apply_academy_action, add_assisted_medication_choice
from peds_anaphylaxis_sim.scenario_loader import load_scenario_for_phase
from peds_anaphylaxis_sim.engine import Simulator

ACADEMY_PATH=['allergy_identification','stop_infusion','call_help','high_flow_oxygen','connect_monitor','check_bp','prepare_rescue_equipment','academy_medication_check','academy_assisted_medication','academy_reassess','academy_family_communication','academy_sbar_handoff']
CLINICAL_PATH=['stop_infusion','call_help','abc_assess','high_flow_oxygen','shock_position','connect_monitor','check_bp','im_epinephrine','fluid_bolus','reassess_first','bronchodilator','steroid','reassess_second','family_explain','sbar_handoff']

def step(s,aid,tick=True):
    if aid=='im_epinephrine':s.apply_epinephrine_dose(round(min(.01*s.state.weight_kg,.3),3))
    elif aid=='fluid_bolus':s.apply_fluid_bolus_volume(10*s.state.weight_kg)
    elif aid=='steroid':s.apply_steroid_dose(min(s.state.weight_kg,40))
    else:s.apply_action(aid)
    if tick:s.tick()

def standard(s):
    for aid in ACADEMY_PATH if s._is_academy_basic_case() else CLINICAL_PATH:step(s,aid)
    for _ in range(30):
        if s.is_done()[0]:break
        s.tick()
    return s

class PathwayTests(unittest.TestCase):
    def test_standard_paths_all_cases_both_modes(self):
        for role,mode in itertools.product(ROLES,('coach','exam')):
            with self.subTest(role=role,mode=mode):
                s=standard(make(role,mode))
                self.assertIn(s.is_done()[1],('success','standard_assessment_completed'))
                self.assertEqual(s.build_report()['score'],100)
                self.assertEqual(s._unfinished_required_steps(),[])
                self.assertTrue(s.state.vitals['SpO2']>=95)
                self.assertTrue(s.state.vitals['SBP']>=s.age_sbp_threshold())
    def test_phase_mapping_and_terminal(self):
        for system,phase,mode in [('clinical','基线评估','exam'),('clinical','模拟培训','coach'),('clinical','培训后考核','exam'),('academy','课前测评','exam'),('academy','模拟训练','coach'),('academy','课后考核','exam')]:
            with self.subTest(phase=phase):
                d=load_scenario_for_phase(system,phase,'academy_anaphylaxis_rescue' if system=='academy' else '')
                s=standard(Simulator(d,mode=mode,seed=7));self.assertTrue(s.is_done()[0]);self.assertEqual(s.build_report()['score'],100)
    def test_all_11_reachable_clinical_patient_profiles(self):
        for role,mode,age in itertools.product(('initial','variant'),('coach','exam'),range(1,12)):
            with self.subTest(role=role,mode=mode,age=age):
                d=make(role,mode).scenario;d['patient']['age_years']=age;d['patient']['weight_kg']=age*2+8 if age<=6 else age*3+2
                s=standard(Simulator(d,mode=mode,seed=23))
                self.assertTrue(s.is_done()[0]);self.assertEqual(s.build_report()['score'],100)
    def test_stopping_and_calling_does_not_freeze(self):
        for role,mode in itertools.product(('academy_initial','academy_variant'),('coach','exam')):
            s=make(role,mode);s.apply_action('stop_infusion');s.apply_action('call_help');v=copy.deepcopy(s.state.vitals)
            for _ in range(12):s.tick()
            self.assertLess(s.state.vitals['SBP'],v['SBP']);self.assertGreater(s.state.vitals['HR'],v['HR'])
            self.assertFalse(s.state.flags['epi_im_given'])
    def test_measurement_not_treatment(self):
        for role,mode in itertools.product(ROLES,('coach','exam')):
            a=make(role,mode);b=make(role,mode)
            for s in (a,b):
                for aid in ('stop_infusion','call_help','high_flow_oxygen'):s.apply_action(aid)
            a.apply_action('check_bp');self.assertFalse(a.state.flags['bp_checked'])
            for _ in range(6):a.tick();b.tick()
            self.assertEqual(a.state.vitals,b.state.vitals)
            self.assertEqual(a.state.symptoms,b.state.symptoms)
            self.assertTrue(a.state.flags['bp_checked'])
    def test_bp_is_available_after_this_measurement(self):
        s=make('academy_initial');s.apply_action('stop_infusion');s.apply_action('call_help')
        for _ in range(5):s.tick()
        s.apply_action('check_bp');self.assertFalse(s.state.flags['bp_checked']);self.assertNotIn('check_bp',s.action_valid_time)
        s.tick();self.assertTrue(s.state.flags['bp_checked']);self.assertEqual(s.action_valid_time['check_bp'],180)
    def test_preparation_check_and_actual_administration_distinct(self):
        for role in ('academy_initial','academy_variant'):
            s=make(role);s.apply_action('stop_infusion');s.apply_action('call_help')
            s.apply_action('prepare_rescue_equipment');self.assertTrue(s.state.flags['rescue_equipment_prepared'])
            self.assertFalse(s.state.flags['academy_medication_checked']);self.assertFalse(s.state.flags['epi_im_given'])
            s.apply_action('academy_medication_check');self.assertTrue(s.state.flags['academy_medication_checked']);self.assertFalse(s.state.flags['epi_im_given'])
            r=apply_academy_action(s,'academy_assisted_medication');self.assertTrue(r['valid_completion'])
            self.assertTrue(s.state.flags['epi_im_given']);self.assertEqual(s.state.flags['epi_im_doses'],1)
            v=copy.deepcopy(s.state.vitals);r=apply_academy_action(s,'academy_assisted_medication')
            self.assertFalse(r['executed']);self.assertEqual(v,s.state.vitals)
            ids=[a['id'] for a in add_assisted_medication_choice(s.actions,s.state.flags)];self.assertEqual(len(ids),len(set(ids)))
    def test_out_of_order_cannot_finish_and_remediation_not_perfect(self):
        for role,mode in itertools.product(ROLES,('coach','exam')):
            s=make(role,mode)
            early=['academy_reassess','academy_sbar_handoff','academy_family_communication'] if s._is_academy_basic_case() else ['reassess_first','reassess_second','sbar_handoff','family_explain']
            for aid in early:s.apply_action(aid)
            self.assertFalse(s.is_done()[0]);self.assertEqual(s.score,0)
            self.assertTrue(s.state.flags['order_violations'])
            standard(s);self.assertLess(s.build_report()['score'],100)
            self.assertTrue(s.is_done()[0])
    def test_original_bypass_has_no_actual_medication_and_no_success(self):
        for role in ('academy_initial','academy_variant'):
            s=make(role)
            for aid in ['academy_reassess','academy_sbar_handoff','academy_family_communication','allergy_identification','stop_infusion','call_help','high_flow_oxygen','connect_monitor','check_bp','prepare_rescue_equipment']:step(s,aid)
            self.assertLess(s.score,100);self.assertNotEqual(s.is_done()[1],'success')
            self.assertFalse(s.state.flags['academy_assisted_medication_done'])
    def test_same_time_reassessments_not_two_observations(self):
        s=make();s.apply_action('stop_infusion');s.apply_epinephrine_dose(.01*s.state.weight_kg);s.apply_fluid_bolus_volume(10*s.state.weight_kg)
        s.apply_action('reassess_first');self.assertFalse(s.state.flags['first_reassessment_done'])
        s.tick();s.apply_action('reassess_first');self.assertTrue(s.state.flags['first_reassessment_done'])
        s.apply_action('reassess_second');self.assertFalse(s.state.flags['second_reassessment_done'])
        s.tick();s.apply_action('reassess_second');self.assertTrue(s.state.flags['second_reassessment_done'])
    def test_late_valid_completion_is_not_lost(self):
        s=make('academy_initial');s.state.t=150;s.apply_action('call_help')
        self.assertIn('call_help',s.action_valid_time);self.assertLess(s.score,10)
    def test_removed_iv_not_magically_restored_by_stopping(self):
        for role in ('academy_initial','academy_variant'):
            s=make(role);s.apply_action('remove_iv');s.apply_action('stop_infusion')
            self.assertFalse(s.state.flags['iv_access'])
            s.apply_action('call_help');s.apply_action('academy_restore_iv');self.assertTrue(s.state.flags['iv_access'])
            self.assertGreater(s.state.flags['academy_safety_penalty_points'],0)
    def test_manual_completion_denominator(self):
        s=make('academy_initial');s.mark_manual_rescue_completion()
        self.assertEqual(s.state.flags['completion_rate_at_manual_finish'],0)
        s=make('academy_initial');s.apply_action('call_help');s.mark_manual_rescue_completion()
        self.assertEqual(s.state.flags['completion_rate_at_manual_finish'],8.3)
    def test_no_medication_continues_after_330_seconds(self):
        for role in ('initial','variant'):
            s=make(role);s.apply_action('stop_infusion');s.apply_action('call_help');s.apply_action('high_flow_oxygen')
            for _ in range(12):s.tick()
            before=s.state.vitals['SBP'];s.tick();s.tick();self.assertLess(s.state.vitals['SBP'],before)
    def test_drug_repeat_interval(self):
        s=make();s.apply_action('stop_infusion');s.apply_epinephrine_dose(.01*s.state.weight_kg)
        n=s.state.flags['epi_im_doses'];r=s.apply_epinephrine_dose(.01*s.state.weight_kg,action_id='repeat_epinephrine')
        self.assertEqual(r['status'],'too_soon');self.assertEqual(s.state.flags['epi_im_doses'],n)
    def test_all_actions_report_finite_all_cases_modes(self):
        for role,mode in itertools.product(ROLES,('coach','exam')):
            for a in make(role,mode).actions:
                with self.subTest(role=role,mode=mode,action=a['id']):
                    s=make(role,mode);s.apply_action(a['id']);s.tick();s.build_report();s.to_snapshot()
                    self.assertFalse(any(e.message=='rule_eval_error' for e in s.log))

if __name__=='__main__':unittest.main(verbosity=2)
