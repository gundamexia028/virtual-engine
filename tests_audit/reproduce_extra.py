"""Additional audit reproducers. Source is selected explicitly; no network/UI mocks."""
import sys,json,copy,hashlib,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.repo/'app'))
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.scenario_loader import load_scenario_by_role
out=[]
def make():return Simulator(load_scenario_by_role('initial'),mode='coach',seed=17)
def add(name,data):out.append({'id':name,**data})
s=make();s.apply_action('stop_infusion');r=s.apply_epinephrine_dose(.01);add('F10_UNDERDOSE_VALID_TIMELINE',{'fixture':'reachable engine API, no injected state','status':r['status'],'epi_given':s.state.flags['epi_im_given'],'action_valid_time':copy.deepcopy(s.action_valid_time)})
s=make();snap=s.to_snapshot();snap['action_valid_time']['im_epinephrine']=99999
try:restored=Simulator.from_snapshot(snap);result={'accepted':True,'timeline':restored.action_valid_time}
except ValueError as e:result={'accepted':False,'error':str(e)}
add('F11_FUTURE_SNAPSHOT_TIME',{'fixture':'mutated input snapshot validation test',**result})
s=make();s.state.vitals.update(SpO2=80,SBP=60,DBP=35);s.state.symptoms.update(stridor=3,consciousness=2);s.state.flags['airway_compromise']=True
trace=[]
for _ in range(3):s.apply_action('bvm_ventilation');trace.append({'vitals':copy.deepcopy(s.state.vitals),'status':s.log[-1].data.get('status')})
add('F12_REPEAT_BVM_EFFECT',{'fixture':'synthetic airway-obstruction branch state; not claimed naturally reached', 'trace':trace})
s=make();s.apply_epinephrine_dose(1);before=s.to_snapshot();s.mark_manual_rescue_completion();add('F13_TERMINAL_MANUAL_MUTATION',{'fixture':'actual overdose failure then manual-finish API','mutated':before!=s.to_snapshot(),'end':s.is_done()})
# Correct the underdose within the same time step, then finish the original clinical path.
s=make()
for aid in ['stop_infusion','call_help','abc_assess','high_flow_oxygen','shock_position','connect_monitor','check_bp']:s.apply_action(aid);s.tick()
r1=s.apply_epinephrine_dose(.01);r2=s.apply_epinephrine_dose(round(min(.01*s.state.weight_kg,.3),3));s.tick();s.apply_fluid_bolus_volume(10*s.state.weight_kg);s.tick()
for aid in ['reassess_first','bronchodilator']:s.apply_action(aid);s.tick()
s.apply_steroid_dose(min(s.state.weight_kg,40));s.tick()
for aid in ['reassess_second','family_explain','sbar_handoff']:s.apply_action(aid);s.tick()
add('F14_WRONG_DOSE_RETRY_PERFECT',{'fixture':'reachable engine API, immediate corrected retry (UI normally adds a tick)','first_status':r1['status'],'retry_status':r2['status'],'score':s.build_report()['score'],'end':s.is_done(),'subscores':s.state.flags.get('epinephrine_subscores')})
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps({'repo':str(a.repo),'engine_sha256':hashlib.sha256((a.repo/'app/peds_anaphylaxis_sim/engine.py').read_bytes()).hexdigest(),'observations':out},ensure_ascii=False,indent=2,allow_nan=False));print(a.out.read_text())
