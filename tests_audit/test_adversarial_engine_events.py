"""Natural, registered-case regressions from independent adversarial audit.

These tests change no clinical threshold, scenario, or injected state.
"""
import itertools
import unittest
from test_integrity import make
from test_pathways import CLINICAL_PATH
from ui_commands import execute_command, revision

class NaturalClinicalEventTests(unittest.TestCase):
    def test_first_als_indication_at_zero_survives_tick_and_ui(self):
        for mode in ('coach', 'exam'):
            with self.subTest(mode=mode):
                sim = make('variant', mode)
                sim.apply_action('continue_infusion')
                self.assertEqual(sim.state.flags['advanced_support_indicated_time_sec'], 0)
                reason = sim.state.flags['advanced_support_indicated_reason']
                sim.tick()
                self.assertEqual(sim.state.flags['advanced_support_indicated_time_sec'], 0)
                self.assertEqual(sim.state.flags['advanced_support_indicated_reason'], reason)
                for _ in range(30):
                    if sim.state.flags.get('cardiac_arrest') or sim.is_done()[0]:
                        break
                    sim.tick()
                self.assertTrue(sim.state.flags['cardiac_arrest'])
                self.assertEqual(sim.state.flags['advanced_support_indicated_time_sec'], 0)
                self.assertEqual(sim.state.flags['advanced_support_indicated_reason'], reason)
                ui = make('variant', mode)
                state = {'active_simulator': ui, 'session_id': 'offline'}
                execute_command(state, 'offline', revision(ui), 'action', 'continue_infusion')
                self.assertEqual(ui.build_report()['clinical_pathway_flags']['advanced_support_indicated_time_sec'], 0)
                self.assertEqual(ui.build_report()['key_timeline']['advanced_support_indicated_time_sec'], 0)

    def test_natural_asphyxia_death_is_reported_without_false_cpr_omission(self):
        for role, mode in itertools.product(('initial', 'variant'), ('coach', 'exam')):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                state = {'active_simulator': sim, 'session_id': 'offline'}
                def call(command, action_id='', value=None):
                    return execute_command(state, 'offline', revision(sim), command, action_id, value)
                for aid in CLINICAL_PATH[:7]:
                    call('action', aid)
                call('action', 'steroid')
                call('steroid', 'steroid', sim.state.weight_kg)
                for _ in range(30):
                    if sim.state.flags.get('cardiac_arrest') or sim.is_done()[0]:
                        break
                    call('advance_time')
                self.assertTrue(sim.state.flags['cardiac_arrest'])
                call('action', 'cpr')
                for _ in range(30):
                    if sim.is_done()[0]:
                        break
                    call('advance_time')
                self.assertEqual(sim.is_done(), (True, 'failure'))
                self.assertTrue(sim.state.flags['dead'])
                self.assertEqual(sim.state.t, 480)
                report = sim.build_report()
                self.assertTrue(report['death_event'])
                self.assertEqual(report['death_time_sec'], 480)
                self.assertTrue(report['death_reason'])
                self.assertTrue(report['outcome_class'])
                self.assertFalse(report['death_after_arrest_without_cpr'])
                self.assertTrue(report['clinical_pathway_flags']['cpr_done'])
                before = sim.to_snapshot()
                sim.tick()
                sim.apply_action('bvm_ventilation')
                self.assertEqual(sim.to_snapshot(), before)

if __name__ == '__main__':
    unittest.main(verbosity=2)
