import copy,itertools,unittest
from test_integrity import make,ROLES
from test_pathways import step,standard
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.integrity import safe_eval
from academy_interactions import apply_academy_action

class ExtendedIntegrityTests(unittest.TestCase):
    def test_partial_epinephrine_credit_not_effective_completion(self):
        for role,mode in itertools.product(('initial','variant'),('coach','exam')):
            s=make(role,mode);s.apply_action('stop_infusion');s.apply_epinephrine_dose(.001)
            self.assertNotIn('im_epinephrine',s.action_valid_time)
            self.assertFalse(s.state.flags['epi_im_given'])
            self.assertIn('im_epinephrine',s.build_report()['critical_missing'])
            s.tick();s.apply_epinephrine_dose(min(.01*s.state.weight_kg,.3))
            self.assertEqual(s.action_valid_time['im_epinephrine'],30)
            self.assertLess(s.state.flags['epinephrine_subscores']['dose_correct']['awarded_points'],8)
    def test_future_fractional_or_inconsistent_snapshots_rejected(self):
        s=make();s.apply_action('stop_infusion');s.tick()
        mutations=[lambda d:d['action_valid_time'].update(im_epinephrine=99999),
                   lambda d:d['state'].update(t=30.5),lambda d:d['state'].update(t=True),
                   lambda d:d['state']['vitals'].pop('HR'),lambda d:d['state'].update(weight_kg=999),
                   lambda d:d['log'][0].update(t=-1),lambda d:d['log'][0].update(t=99999),
                   lambda d:d['action_valid_time'].update(not_an_action=0),
                   lambda d:d['action_first_time'].update(stop_infusion=10)]
        for mutate in mutations:
            snap=s.to_snapshot();mutate(snap)
            with self.assertRaises(ValueError):Simulator.from_snapshot(snap)
    def test_roundtrip_all_reachable_standard_path_prefixes(self):
        from test_pathways import ACADEMY_PATH,CLINICAL_PATH
        for role,mode in itertools.product(ROLES,('coach','exam')):
            s=make(role,mode)
            for aid in ACADEMY_PATH if s._is_academy_basic_case() else CLINICAL_PATH:
                step(s,aid);snap=s.to_snapshot();self.assertEqual(Simulator.from_snapshot(snap).to_snapshot(),snap)
    def test_ventilation_duplicate_does_not_stack_in_synthetic_branch(self):
        for role in ('initial','variant'):
            s=make(role);s.state.vitals.update(SpO2=80,SBP=60,DBP=35);s.state.symptoms.update(stridor=3,consciousness=2);s.state.flags['airway_compromise']=True
            s.apply_action('bvm_ventilation');v=copy.deepcopy(s.state.vitals)
            for _ in range(5):s.apply_action('bvm_ventilation')
            self.assertEqual(s.state.vitals,v);self.assertIn('bvm_ventilation',s.action_valid_time)
    def test_manual_finish_failed_terminal_noop_and_success_idempotent(self):
        s=make();s.apply_epinephrine_dose(1);before=s.to_snapshot();s.mark_manual_rescue_completion();self.assertEqual(s.to_snapshot(),before)
        s=standard(make('academy_initial'));s.mark_manual_rescue_completion();before=s.to_snapshot();s.mark_manual_rescue_completion();self.assertEqual(s.to_snapshot(),before)
    def test_untrusted_expression_no_sequence_allocation(self):
        for expr in ("'a' * 1000000", "[1]*1000000", "flags.advanced_support_latest_reason * 1000000", "1000000000000000 > 0"):
            with self.assertRaises(ValueError):safe_eval(expr,{})
    def test_unknown_academy_action_not_executed(self):
        s=make('academy_initial');r=apply_academy_action(s,'NONEXISTENT');self.assertFalse(r['executed']);self.assertFalse(r['valid_completion'])
    def test_wrong_fluid_and_steroid_corrected_not_perfect_credit(self):
        for method,wrong,right,aid in [('apply_fluid_bolus_volume',0,180,'fluid_bolus'),('apply_steroid_dose',0,18,'steroid')]:
            s=make();s.apply_action('stop_infusion');s.apply_epinephrine_dose(min(.01*s.state.weight_kg,.3));s.tick()
            if aid=='steroid':s.apply_fluid_bolus_volume(10*s.state.weight_kg);s.tick()
            getattr(s,method)(wrong)
            getattr(s,method)(10*s.state.weight_kg if aid=='fluid_bolus' else min(s.state.weight_kg,40))
            self.assertIn(aid,s.state.flags['order_violations'])
            award=[a for a in s.state.flags['score_awards'] if a['action_id']==aid][-1]
            self.assertLess(award['awarded_points'],award['max_points'])

if __name__=='__main__':unittest.main(verbosity=2)
