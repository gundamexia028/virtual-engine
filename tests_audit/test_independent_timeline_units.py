"""Independent real-report semantic checks, not pixel-level browser acceptance."""
import copy
import itertools
import unittest
from test_integrity import make, ROLES
from test_pathways import standard
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.time_format import format_timeline_value, timeline_unit
from ui_labels import timeline_display_rows, TIMELINE_LABELS_CN, EVENT_VALUE_LABELS_CN

class IndependentTimelineUnitsTests(unittest.TestCase):
    def check_report(self, sim):
        report = sim.build_report()
        original_report = copy.deepcopy(report)
        snapshot = sim.to_snapshot()
        timeline = report['key_timeline']
        rows = timeline_display_rows(timeline)
        self.assertEqual(report, original_report)
        self.assertEqual(sim.to_snapshot(), snapshot)
        self.assertEqual(len(rows), len(timeline))
        for (key, value), row in zip(timeline.items(), rows):
            self.assertEqual(row['指标'], TIMELINE_LABELS_CN[key])
            if value is None:
                self.assertEqual(row['数值'], '')
            elif isinstance(value, bool):
                self.assertEqual(row['数值'], '是' if value else '否')
                self.assertEqual(row['单位'], '是/否')
            elif key.endswith(('_mg', '_ml', '_count')):
                self.assertEqual(row['数值'], str(value))
                self.assertEqual(row['单位'], 'mg' if key.endswith('_mg') else 'ml' if key.endswith('_ml') else '次')
                self.assertNotIn(':', row['数值'])
            elif isinstance(value, (int, float)):
                self.assertEqual(row['单位'], 'mm:ss')
                minutes, seconds = map(int, row['数值'].split(':'))
                self.assertEqual(minutes * 60 + seconds, value)
            else:
                self.assertEqual(row['数值'], EVENT_VALUE_LABELS_CN.get(value, value))

    def test_actual_baseline_and_completed_reports_in_all_modes(self):
        for role, mode in itertools.product(ROLES, ('coach', 'exam')):
            with self.subTest(role=role, mode=mode):
                sim = make(role, mode)
                self.check_report(sim)
                standard(sim)
                self.assertTrue(sim.is_done()[0])
                self.check_report(sim)

    def test_all_supported_clinical_age_weight_profiles(self):
        for age in range(1, 12):
            with self.subTest(age=age):
                scenario = make().scenario
                scenario['patient']['age_years'] = age
                scenario['patient']['weight_kg'] = age * 2 + 8 if age <= 6 else age * 3 + 2
                sim = standard(Simulator(scenario, 'exam', 17))
                self.assertEqual(sim.display_score(), 100)
                self.check_report(sim)

    def test_zero_missing_unknown_and_unit_suffix_boundaries(self):
        cases = [
            ('steroid_min_mg', 0, '0', 'mg'),
            ('steroid_min_mg', None, '', 'mg'),
            ('example_time_mg', 16, '16', 'mg'),
            ('example_time_ml', 160, '160', 'ml'),
            ('example_seconds_count', 2, '2', '次'),
            ('duration_min', 3, '3', 'min'),
            ('duration_minutes', 3.5, '3.5', 'min'),
            ('duration_sec', 0, '00:00', 'mm:ss'),
            ('duration_seconds', 65, '01:05', 'mm:ss'),
            ('duration_sec', None, '', 'mm:ss'),
            ('stop_infusion', 0, '00:00', 'mm:ss'),
            ('stop_infusion', None, '', 'mm:ss'),
            ('unknown_numeric', 16, '16', ''),
            ('unknown_numeric', 0, '0', ''),
            ('unknown_numeric', None, '', ''),
            ('fluid_bolus_valid', False, 'False', '是/否'),
        ]
        for key, value, shown, unit in cases:
            with self.subTest(key=key, value=value):
                self.assertEqual(format_timeline_value(key, value), shown)
                self.assertEqual(timeline_unit(key, value), unit)

if __name__ == '__main__':
    unittest.main(verbosity=2)
