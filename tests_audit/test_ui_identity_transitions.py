"""Real Streamlit AppTest, synthetic state only. NOT browser evidence.
Run: VE_WORKFLOW_ROOT=/path/to/source python -m unittest discover -s <this dir> -p test_ui_identity_transitions.py -v
Initial registration identity is seeded once; all subsequent transitions use real production widgets.
"""
import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
ROOT=Path(os.environ.get('VE_WORKFLOW_ROOT',str(Path(__file__).resolve().parents[1]))).resolve()
A=['allergy_identification','stop_infusion','call_help','high_flow_oxygen','connect_monitor','check_bp','prepare_rescue_equipment','academy_medication_check','academy_assisted_medication','academy_reassess','academy_family_communication','academy_sbar_handoff']
class IdentityTransitionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='ui-identity-audit-')
  cls.env=patch.dict(os.environ,dict(APP_MODE='production',PEDSIM_RESULTS_DIR=cls.tmp.name+'/runs',PEDSIM_DRAFTS_DIR=cls.tmp.name+'/drafts',SUPABASE_URL='',SUPABASE_KEY='',SUPABASE_ANON_KEY='',SUPABASE_SERVICE_ROLE_KEY=''));cls.env.start()
 @classmethod
 def tearDownClass(cls):cls.env.stop();cls.tmp.cleanup()
 def start(self,phase='课前测评'):
  role='academy_variant' if phase=='课后考核' else 'academy_initial';mode='coach' if phase=='模拟训练' else 'exam'
  code=f'''
import sys
sys.path.insert(0,{str(ROOT/'app')!r})
import streamlit as st
import streamlit_app as app
app.init_session()
if not st.session_state.get('_seed'):
 st.session_state.update(_seed=True,system_mode='academy',system_mode_selected=True,academy_scenario_selected=True,profile_completed=True,app_unlocked=True,participant_id='AUDIT-A',participant_initials='AAA',student_level='本科',student_grade='一年级',school_name='审计虚构学院',assessment_phase={phase!r},collection_mode='测试演练')
 st.session_state.participant_id=app.build_academy_participant_id('本科','AAA')
 app.start_simulation(app.scenario_path_by_role({role!r}),{mode!r},17,st.session_state.participant_id)
app.inject_compact_css()
def route():
 if not app.render_system_mode_selection_page():return
 if not app.render_academy_scenario_selection_page():return
 app.render_sidebar()
 if not st.session_state.profile_completed:app.render_participant_entry_page()
 elif st.session_state.active_simulator is None:app.render_intro()
 else:app.render_simulation()
route()
'''
  at=AppTest.from_string(code,default_timeout=20).run();self.assertFalse(at.exception);return at
 def button(self,at,label):
  bs=[b for b in at.button if b.label==label];self.assertEqual(len(bs),1,[b.label for b in at.button]);bs[0].click().run();self.assertFalse(at.exception)
 def action(self,at,aid):
  at.button(key=f'action_{at.session_state.session_id}_{aid}').click().run();self.assertFalse(at.exception)
 def complete(self,at,wrong=False):
  if wrong:self.action(at,'academy_reassess')
  for aid in A:self.action(at,aid)
  if at.session_state.assessment_phase=='模拟训练':self.button(at,'我已确认完成抢救');self.button(at,'确认结束')
 def test_new_learner_pretest_uses_own_current_report(self):
  at=self.start();self.complete(at)
  self.button(at,'重新填写对象信息')
  next(e for e in at.text_input if e.label=='姓名首字母（必填）').set_value('BBB')
  self.button(at,'保存信息并进入学院模式');new_id=at.session_state.participant_id
  self.button(at,'开始本阶段');self.complete(at,wrong=True)
  report=at.session_state.academy_stage_reports['pretest']
  self.assertEqual(report['session']['participant_id'],new_id,'Displayed phase report belongs to previous learner')
  self.assertEqual(report['session']['session_id'],at.session_state.session_id)
  self.assertEqual(report['score'],95)
  self.assertEqual(next(e.value for e in at.metric if e.label=='最终得分'),'95/100')
 def test_same_learner_explicit_redo_replaces_displayed_phase(self):
  at=self.start();self.complete(at);old_sid=at.session_state.session_id;old_pid=at.session_state.participant_id
  self.button(at,'重新填写对象信息');self.button(at,'保存信息并进入学院模式')
  self.assertEqual(at.session_state.participant_id,old_pid)
  self.button(at,'开始本阶段');self.complete(at,wrong=True)
  self.assertNotEqual(old_sid,at.session_state.session_id)
  self.assertEqual(at.session_state.academy_stage_reports['pretest']['session']['session_id'],at.session_state.session_id)
 def test_independent_academy_stages_have_completion_page(self):
  for phase,page,label in [('模拟训练','training_complete','进入课后考核'),('课后考核','posttest_result','进入SUS及教学体验评价')]:
   with self.subTest(phase=phase):
    at=self.start(phase);self.complete(at)
    # Registration currently permits each phase independently. These must not silently blank.
    self.assertTrue(at.session_state.ended)
    self.assertEqual(at.session_state.academy_flow_page,page)
    self.assertIn('返回登记页',[b.label for b in at.button])
    self.assertTrue(any('独立阶段' in e.value for e in at.markdown))
    self.assertNotIn(label,[b.label for b in at.button])
 def test_pretest_then_direct_posttest_displays_current_posttest(self):
  at=self.start();self.complete(at)
  self.button(at,'重新填写对象信息')
  next(e for e in at.selectbox if e.label=='评估阶段（必填）').select('课后考核')
  self.button(at,'保存信息并进入学院模式');self.button(at,'开始本阶段');self.complete(at,wrong=True)
  self.assertEqual(at.session_state.assessment_phase,'课后考核')
  self.assertEqual(at.session_state.academy_flow_page,'posttest_result')
  self.assertEqual(next(e.value for e in at.metric if e.label=='最终得分'),'95/100')
  self.assertTrue(any('课后考核完成（独立阶段）' in e.value for e in at.markdown))
 def test_three_stage_continuity_and_second_learner_reset(self):
  at=self.start();self.complete(at);pid=at.session_state.participant_id
  self.button(at,'进入模拟训练');self.assertEqual(at.session_state.participant_id,pid)
  self.complete(at);self.button(at,'进入课后考核');self.complete(at)
  self.assertEqual(set(at.session_state.academy_stage_reports),{'pretest','training','posttest'})
  self.button(at,'进入SUS及教学体验评价');self.button(at,'提交评价')
  self.assertEqual(at.session_state.academy_flow_page,'flow_complete')
  self.button(at,'更换学员')
  self.assertFalse(at.session_state.academy_stage_reports)
  self.assertFalse(at.session_state.academy_post_evaluation_completed)
  self.assertFalse(at.session_state.sus_score)
 def test_mode_switch_clears_academy_report_identity(self):
  at=self.start();self.complete(at)
  self.button(at,'重新填写对象信息');self.button(at,'切换临床/学院模式');self.button(at,'进入临床模式')
  self.assertFalse(at.session_state.academy_stage_reports)
  self.assertFalse(at.session_state.prior_experience_survey_completed)
  self.button(at,'切换临床/学院模式');self.button(at,'进入学院模式');self.button(at,'进入该情景')
  self.assertFalse(at.session_state.academy_stage_reports)
  self.assertEqual(at.session_state.assessment_phase,'课前测评')
if __name__=='__main__':unittest.main(verbosity=2)
