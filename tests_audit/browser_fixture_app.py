"""Local-only REAL Streamlit component integration fixture; no mock framework.
Uses production render_simulation/callbacks/storage, with explicit synthetic
participant/phase seeding. Not a substitute for production registration E2E.
Never deployed: the environment guard fails closed outside the audit runner.
"""
import os,sys,json,html
from pathlib import Path
if os.environ.get('VE_AUDIT_BROWSER_FIXTURE')!='1':
 raise RuntimeError('This test fixture is not a production entry point.')
ROOT=Path(os.environ.get('VE_WORKFLOW_ROOT',Path(__file__).resolve().parents[1])).resolve();sys.path.insert(0,str(ROOT/'app'))
import streamlit as st
import streamlit_app as app
from peds_anaphylaxis_sim.scenario_loader import load_scenario_by_role
CASES={
 'clinical_initial_coach':('initial','clinical','coach','模拟培训'),
 'clinical_initial_exam':('initial','clinical','exam','基线评估'),
 'clinical_variant_coach':('variant','clinical','coach','模拟培训'),
 'clinical_variant_exam':('variant','clinical','exam','培训后考核'),
 'academy_initial_coach':('academy_initial','academy','coach','模拟训练'),
 'academy_initial_exam':('academy_initial','academy','exam','课前测评'),
 'academy_variant_coach':('academy_variant','academy','coach','模拟训练'),
 'academy_variant_exam':('academy_variant','academy','exam','课后考核')}
def seed(case):
 for k in list(st.session_state):
  if k!='audit_case':del st.session_state[k]
 app.init_session();role,system,mode,phase=CASES[case]
 st.session_state.update(system_mode=system,system_mode_selected=True,participant_type='nursing_student' if system=='academy' else 'clinical_nurse',academy_scenario_selected=True,academy_scenario_id=app.ACADEMY_SCENARIO_DEFAULT_ID,academy_scenario_name='本地审计合成病例',profile_completed=True,app_unlocked=True,page='训练系统',assessment_phase=phase,workflow_mode=mode,workflow_display=phase,mode=mode,participant_id='AUDIT-SYNTHETIC',participant_initials='AUT',school_name='合成测试学院',institution='合成测试医院',collection_mode='测试演练')
 app.start_simulation(app.scenario_path_by_role(role),mode,17,'AUDIT-SYNTHETIC')
 st.session_state['_audit_seeded']=case

def choose():seed(st.session_state.audit_case)
st.set_page_config(page_title='Virtual-Engine local real-browser fixture',layout='wide');app.inject_compact_css()
app.init_session()
if not st.session_state.get('_audit_seeded'):seed(next(iter(CASES)))
st.sidebar.selectbox('审计病例组合',list(CASES),key='audit_case',on_change=choose)
st.sidebar.button('重新开始审计病例',on_click=lambda:seed(st.session_state.audit_case))
sim=st.session_state.active_simulator
app.render_simulation()
# A DOM oracle observes the real simulator after rendering; never replaces UI logic.
report=sim.build_report()
state={'session_id':st.session_state.get('session_id'),'case':st.session_state.get('_audit_seeded'),'t':sim.state.t,'log_n':len(sim.log),'score':sim.display_score(),'vitals':sim.state.vitals,'flags':sim.state.flags,'valid':sim.action_valid_time,'weight':sim.state.weight_kg,'end':sim.is_done(),'critical_missing':report['critical_missing'],'process_safety_issues':report['process_safety_issues'],'last_actions':[dict(e.data,action_id=e.message) for e in sim.log if e.kind=='action'][-5:]}
st.markdown('<div id="audit-state" style="white-space:pre-wrap">'+html.escape(json.dumps(state,ensure_ascii=False,allow_nan=False))+'</div>',unsafe_allow_html=True)
