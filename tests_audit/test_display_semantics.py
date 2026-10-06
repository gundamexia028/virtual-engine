"""Presentation boundaries; CSS assertions are NOT pixel/browser validation."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
ROOT=Path(os.environ.get('VE_WORKFLOW_ROOT', Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0,str(ROOT/'app'))
from peds_anaphylaxis_sim.time_format import format_timeline_value

class DisplaySemanticsTests(unittest.TestCase):
    def test_doses_are_not_times_and_suffix_boundaries(self):
        for key,value,expected in [
            ('steroid_min_mg',16,'16'),('steroid_max_mg',32,'32'),
            ('epi_target_dose_mg',.16,'0.16'),('fluid_min_ml',160,'160'),
            ('fluid_max_ml',320,'320'),('reassess_count',2,'2'),
            ('example_min',3,'3'),('example_sec',30,'00:30'),
            ('example_seconds',65,'01:05'),('stop_infusion',0,'00:00'),
            ('stop_infusion',None,''),('steroid_min_mg',None,''),
            ('steroid_min_mg',0,'0'),('steroid_min_mg','', ''),
            ('unknown_numeric',16,'16'),('admin_count',1,'1')]:
            with self.subTest(key=key,value=value):self.assertEqual(format_timeline_value(key,value),expected)

    def test_all_registered_report_timeline_labels_are_localized_and_units_explicit(self):
        from peds_anaphylaxis_sim.engine import Simulator
        from ui_labels import TIMELINE_LABELS_CN,timeline_display_rows
        for path in (ROOT/'app/peds_anaphylaxis_sim/scenarios').glob('*.json'):
            scenario=json.loads(path.read_text())
            report=Simulator(scenario,'exam',17).build_report(); timeline=report['key_timeline']
            with self.subTest(path=path.name):
                self.assertFalse(set(timeline)-set(TIMELINE_LABELS_CN))
                before=copy.deepcopy(timeline); rows=timeline_display_rows(timeline)
                self.assertEqual(before,timeline)
                self.assertEqual(len(rows),len(timeline))
                for row in rows:self.assertTrue(any('\u4e00'<=c<='\u9fff' for c in row['指标']))
        values={'steroid_min_mg':16,'steroid_max_mg':32,'fluid_min_ml':160,'reassess_count':2,'stop_infusion':30}
        self.assertEqual([(r['数值'],r['单位']) for r in timeline_display_rows(values)],
                         [('16','mg'),('32','mg'),('160','ml'),('2','次'),('00:30','mm:ss')])

    def test_exact_existing_score_component_translation_preserves_detail(self):
        from ui_labels import score_feedback_label
        self.assertEqual(score_feedback_label('肾上腺素分项评分：drug_selection；按标准顺序完成。'),
                         '肾上腺素分项评分：药物选择；按标准顺序完成。')
        self.assertEqual(score_feedback_label('full'),'全分')
        self.assertEqual(score_feedback_label('unknown'),'unknown')

    def test_action_css_is_scoped_and_full_label_help_retained(self):
        source=(ROOT/'app/streamlit_app.py').read_text()
        self.assertIn('[class*="st-key-action_"] button {',source)
        self.assertIn('[class*="st-key-action_"] button p {',source)
        self.assertIn('button_text = full_label',source)
        self.assertIn('help=str(action.get("label", ""))',source)
        self.assertIn('st.columns([1.0, 1.8, 1.5], gap="medium")',source)
        self.assertIn('labels.get(msg, ACTION_LABELS_CN.get(msg, msg))',source)

if __name__=='__main__':unittest.main(verbosity=2)
