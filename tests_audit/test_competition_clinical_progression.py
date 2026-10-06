"""Actual competition app entry and complete clinical phases, synthetic data only.
Real Streamlit AppTest; not a browser test.
"""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
ROOT=Path(os.environ.get('VE_WORKFLOW_ROOT',str(Path(__file__).resolve().parents[1]))).resolve()
CLINICAL=['stop_infusion','call_help','abc_assess','high_flow_oxygen','shock_position','connect_monitor','check_bp','im_epinephrine','fluid_bolus','reassess_first','bronchodilator','steroid','reassess_second','family_explain','sbar_handoff']
class CompetitionClinicalProgressionTests(unittest.TestCase):
 def click(self,at,label):
  bs=[b for b in at.button if b.label==label];self.assertEqual(len(bs),1,[b.label for b in at.button]);bs[0].click().run();self.assertFalse(at.exception,str(at.exception))
 def finish(self,at):
  for aid in CLINICAL:
   sid=at.session_state.session_id
   at.button(key=f'action_{sid}_{aid}').click().run();self.assertFalse(at.exception,str(at.exception))
   if aid in ('im_epinephrine','fluid_bolus','steroid'):
    w=at.session_state.active_simulator.state.weight_kg
    kind,label,value={'im_epinephrine':('epinephrine','本次肌注总剂量（mg）',min(w*.01,.3)),'fluid_bolus':('fluid','本次快速补液容量（ml）',w*10),'steroid':('steroid','本次甲泼尼龙剂量（mg）',min(w,40))}[aid]
    next(n for n in at.number_input if n.label==label).set_value(float(value))
    at.button(key=f'confirm_{kind}_{sid}').click().run();self.assertFalse(at.exception,str(at.exception))
    if aid=='steroid':
     history='\n'.join(e.value for e in at.markdown if 'history-panel' in e.value)
     self.assertNotIn('steroid_dose_verified',history)
     self.assertIn('糖皮质激素剂量确认',history)
  self.assertEqual(at.session_state.active_simulator.build_report()['score'],100)
 def test_full_anonymous_clinical_course(self):
  with tempfile.TemporaryDirectory(prefix='clinical-course-') as tmp:
   with patch.dict(os.environ,{'APP_MODE':'competition','PEDSIM_RESULTS_DIR':tmp+'/production','PEDSIM_COMPETITION_RESULTS_DIR':tmp+'/competition','PEDSIM_DRAFTS_DIR':tmp+'/drafts','SUPABASE_URL':'','SUPABASE_KEY':'','SUPABASE_ANON_KEY':'','SUPABASE_SERVICE_ROLE_KEY':''}):
    at=AppTest.from_file(str(ROOT/'app/streamlit_app.py'),default_timeout=20)
    at.secrets.update({'APP_MODE':'competition','COMPETITION_REVIEW_CODE':'SYNTHETIC_ONLY','COMPETITION_ADMIN_CODE':'SYNTHETIC_ADMIN_ONLY','AUTH_CONTEXT_SIGNING_KEY':'synthetic-local-only-signing-key-with-length-over32'})
    at.run();at.text_input[0].set_value('SYNTHETIC_ONLY')
    self.click(at,'进入评审体验');self.click(at,'进入临床模式演示');self.click(at,'开始本阶段')
    pid=at.session_state.participant_id;sid=at.session_state.session_id
    self.finish(at)
    self.assertTrue(at.session_state.pending_prior_experience_survey)
    for sel in at.selectbox:sel.select('否')
    self.click(at,'提交补充信息并完成基线评估')
    self.assertTrue(at.session_state.ended)
    self.click(at,'继续后续流程')
    self.assertTrue(at.session_state.profile_completed,'Anonymous competition flow incorrectly enters production-style registration')
    self.assertEqual(at.session_state.participant_id,pid)
    self.assertEqual(at.session_state.assessment_phase,'模拟培训')
    self.assertNotEqual(at.session_state.session_id,sid)
    self.assertIsNotNone(at.session_state.active_simulator)
    self.finish(at);self.click(at,'继续后续流程')
    self.assertEqual(at.session_state.assessment_phase,'培训后考核')
    self.assertEqual(at.session_state.participant_id,pid)
    self.finish(at)
    self.assertTrue(at.session_state.ended)
    self.assertNotIn('继续后续流程',[b.label for b in at.button])
    report=copy.deepcopy(at.session_state.last_report)
    at.run();self.assertEqual(report,at.session_state.last_report)
    tables=[t.value for t in at.table if '单位' in t.value.columns and '指标' in t.value.columns]
    self.assertEqual(len(tables),1)
    rows={r['指标']:r for r in tables[0].to_dict('records')}
    self.assertEqual(rows['糖皮质激素剂量下限']['单位'],'mg')
    self.assertNotIn(':',rows['糖皮质激素剂量下限']['数值'])
    self.assertEqual(float(rows['糖皮质激素剂量下限']['数值']),report['key_timeline']['steroid_min_mg'])
    self.assertEqual(rows['糖皮质激素']['单位'],'mm:ss')
    self.assertEqual(rows['糖皮质激素剂量上限']['单位'],'mg')
    self.assertNotIn(':',rows['糖皮质激素剂量上限']['数值'])
    self.assertTrue(all(any('\u4e00'<=c<='\u9fff' for c in label) for label in rows))
    feedback=next(t.value for t in at.table if '现有反馈' in t.value.columns)
    shown='\n'.join(feedback['现有反馈'].astype(str))
    self.assertIn('药物选择',shown);self.assertNotIn('drug_selection',shown)
    raw_reasons=[str(a.get('reason','')) for a in report['clinical_pathway_flags']['score_awards']]
    self.assertTrue(any('drug_selection' in r for r in raw_reasons))
    self.assertEqual(report,at.session_state.last_report)
    old_final_sid=at.session_state.session_id
    self.click(at,'重新开始本阶段');self.click(at,'继续当前阶段')
    self.assertEqual(old_final_sid,at.session_state.session_id)
    self.assertEqual(report,at.session_state.last_report)
    self.click(at,'重新开始本阶段');self.click(at,'确认重新开始')
    self.assertEqual(at.session_state.participant_id,pid)
    self.assertNotEqual(at.session_state.session_id,old_final_sid)
    self.assertEqual(set(at.session_state.competition_clinical_completed_stages),{'基线评估','模拟培训'})
    self.assertEqual(at.session_state.active_simulator.state.t,0)
    self.finish(at)
    self.assertNotIn('继续后续流程',[b.label for b in at.button])
    self.click(at,'更换演示学员')
    self.assertNotEqual(at.session_state.participant_id,pid)
    self.assertEqual(at.session_state.assessment_phase,'基线评估')
    self.assertFalse(at.session_state.competition_clinical_completed_stages)
    self.assertFalse(at.session_state.prior_experience_survey_completed)
    self.assertFalse(Path(tmp+'/production').exists())
 def test_reject_stale_or_incomplete_transition_without_mutating(self):
  code=r"""
import sys,copy
sys.path.insert(0,ROOT_APP)
import streamlit as st
import streamlit_app as app
from unittest.mock import patch
app.init_session()
with patch.object(app,'APP_MODE','competition'):
 base=dict(system_mode='clinical',assessment_phase='模拟培训',participant_id='COMP-SYNTHETIC',session_id='training-current',completion_id='completion-current',ended=True,result_saved=True,pending_prior_experience_survey=False,prior_experience_survey_completed=True,competition_clinical_completed_stages={'基线评估':{'session_id':'baseline-old','completion_id':'baseline-marker'},'模拟培训':{'session_id':'training-current','completion_id':'completion-current'}})
 st.session_state.update(copy.deepcopy(base))
 report={'session':{key:base[key] for key in ('assessment_phase','participant_id','session_id','completion_id')}}
 assert app._next_competition_clinical_phase(report)=='培训后考核'
 for key in report['session']:
  corrupt=copy.deepcopy(report);corrupt['session'][key]='stale-or-other'
  assert not app.continue_after_clinical_result(corrupt,'success'),key
  assert all(st.session_state.get(k)==v for k,v in base.items()),key
 for key,value in [('ended',False),('result_saved',False),('prior_experience_survey_completed',False),('pending_prior_experience_survey',True),('competition_clinical_completed_stages',{'模拟培训':base['competition_clinical_completed_stages']['模拟培训']})]:
  st.session_state.update(copy.deepcopy(base));st.session_state[key]=value
  assert not app.continue_after_clinical_result(report,'success'),key
  assert st.session_state.session_id=='training-current'
 st.session_state.checked_rejections=True
""".replace('ROOT_APP',repr(str(ROOT/'app')))
  at=AppTest.from_string(code,default_timeout=20).run()
  self.assertFalse(at.exception,str(at.exception));self.assertTrue(at.session_state.checked_rejections)
if __name__=='__main__':unittest.main(verbosity=2)
