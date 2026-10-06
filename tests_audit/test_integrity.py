"""Executable regression contracts; stdlib unittest, no UI mocks."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.scenario_loader import load_scenario_by_role
from peds_anaphylaxis_sim.integrity import safe_eval
from academy_flow import score_snapshot

ROLES = ('initial','variant','academy_initial','academy_variant')
def make(role='initial', mode='coach'):
    return Simulator(load_scenario_by_role(role), mode=mode, seed=17)

class IntegrityTests(unittest.TestCase):
    def test_nonfinite_rejected_without_mutation(self):
        for role in ROLES:
            for mode in ('coach','exam'):
                for method in ('apply_epinephrine_dose','apply_fluid_bolus_volume','apply_steroid_dose'):
                    for value in (float('nan'), float('inf'), float('-inf'), 'NaN', 'Infinity', '-Infinity', True, None, '', [], -1):
                        with self.subTest(role=role,mode=mode,method=method,value=repr(value)):
                            s=make(role,mode);before=s.to_snapshot()
                            result=getattr(s,method)(value)
                            self.assertEqual(result['status'],'invalid_input')
                            self.assertEqual(before,s.to_snapshot())
                            json.dumps(result,allow_nan=False)
    def test_owned_snapshots_and_reports(self):
        for role in ROLES:
            for mode in ('coach','exam'):
                with self.subTest(role=role,mode=mode):
                    s=make(role,mode);s.apply_action('stop_infusion')
                    snap=s.to_snapshot();restored=Simulator.from_snapshot(snap)
                    snap['state']['vitals']['SBP']=999
                    snap['state']['flags']['foreign']={'nested':[1]}
                    snap['scenario']['actions'][0]['label']='foreign'
                    snap['log'][0]['data']['mode']='foreign'
                    self.assertNotEqual(s.state.vitals['SBP'],999)
                    self.assertNotEqual(restored.state.vitals['SBP'],999)
                    self.assertNotIn('foreign',s.state.flags)
                    self.assertNotIn('foreign',restored.state.flags)
                    report=s.build_report(); report['final_vitals']['SBP']=777
                    report['log'][0]['data']['mode']='foreign'
                    self.assertNotEqual(s.state.vitals['SBP'],777)
                    self.assertNotEqual(s.log[0].data['mode'],'foreign')
    def test_scenario_and_score_snapshot_ownership(self):
        scenario=load_scenario_by_role('initial');s=Simulator(scenario)
        scenario['baseline']['flags']['new']=[1]
        scenario['actions'][0]['label']='bad'
        self.assertNotIn('new',s.state.flags)
        self.assertNotEqual(s.actions[0]['label'],'bad')
        report={'score':80,'raw_score':90,'penalties':10,'module_score_summary':{'x':[1]}}
        out=score_snapshot(report);out['modules']['x'].append(2)
        self.assertEqual(report['module_score_summary']['x'],[1])
        self.assertEqual(out['raw_score'],90)
    def test_nonfinite_and_old_snapshots_rejected(self):
        s=make()
        for field in ('weight_kg',):
            snap=s.to_snapshot();snap['state'][field]=float('nan')
            with self.assertRaises(ValueError):Simulator.from_snapshot(snap)
        snap=s.to_snapshot();snap.pop('engine_revision')
        with self.assertRaises(ValueError):Simulator.from_snapshot(snap)
    def test_expressions_restrict_introspection(self):
        for expr in ("(1).__class__.__name__ == 'int'", "__import__('os')", "[x for x in []]", "2 ** 1000000", "flags.__dict__"):
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):safe_eval(expr,{})
        self.assertTrue(safe_eval('t >= 30 and t % 30 == 0',{'t':60}))
    def test_duplicate_support_does_not_stack(self):
        for role in ('initial','variant'):
            s=make(role);s.apply_action('shock_position');v=copy.deepcopy(s.state.vitals);score=s.score
            for _ in range(20):s.apply_action('shock_position')
            self.assertEqual(v,s.state.vitals);self.assertEqual(score,s.score)
    def test_duplicate_drug_does_not_stack(self):
        s=make();s.apply_action('stop_infusion');dose=min(.01*s.state.weight_kg,.3)
        self.assertEqual(s.apply_epinephrine_dose(dose)['status'],'valid')
        before=s.to_snapshot()
        self.assertEqual(s.apply_epinephrine_dose(dose)['status'],'already_completed')
        self.assertEqual(before,s.to_snapshot())
    def test_premature_cpr_not_completed(self):
        s=make();s.apply_action('cpr');self.assertFalse(s.state.flags['cpr_done'])
        s.apply_action('bvm_ventilation');self.assertFalse(s.state.flags['bvm_done'])
    def test_failed_terminal_immutable(self):
        s=make();s.apply_epinephrine_dose(1);before=s.to_snapshot()
        s.tick();s.apply_action('stop_infusion');s.apply_epinephrine_dose(.1)
        self.assertEqual(before,s.to_snapshot())

if __name__=='__main__':unittest.main(verbosity=2)
