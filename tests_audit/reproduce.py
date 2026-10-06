"""Original-package observations, not correctness assertions. No Streamlit substitute."""
import argparse,sys,json,math
from pathlib import Path
from copy import deepcopy
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--out',required=True);a=p.parse_args()
sys.path.insert(0,str(Path(a.repo)/'app'))
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.scenario_loader import load_scenario_by_role
from academy_interactions import apply_academy_action
out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
records=[]
def obs(s):
 return {'t':s.state.t,'vitals':deepcopy(s.state.vitals),'symptoms':deepcopy(s.state.symptoms),'flags':deepcopy(s.state.flags),'score':s.score,'done':s.is_done(),'report_score':s.build_report()['score']}
def make(role,mode='exam'):return Simulator(load_scenario_by_role(role),mode=mode,seed=42)
def step(s,aid,tick=True):
 if aid=='im_epinephrine':s.apply_epinephrine_dose(min(.01*s.state.weight_kg,.3))
 elif aid=='fluid_bolus':s.apply_fluid_bolus_volume(10*s.state.weight_kg)
 elif aid=='steroid':s.apply_steroid_dose(s.state.weight_kg)
 else:s.apply_action(aid)
 if tick:s.tick()
 return obs(s)
for role in ['academy_initial','academy_variant']:
 for mode in ['coach','exam']:
  s=make(role,mode);s.apply_action('stop_infusion');s.apply_action('call_help');trace=[obs(s)]
  for _ in range(12):s.tick();trace.append(obs(s))
  records.append({'id':'F01','role':role,'mode':mode,'actions':['stop_infusion','call_help']+['tick']*12,'unchanged_all_ticks':all(x['vitals']==trace[0]['vitals'] and x['symptoms']==trace[0]['symptoms'] for x in trace),'trace':trace})
  s=make(role,mode)
  for aid in ['stop_infusion','call_help','high_flow_oxygen','check_bp']:s.apply_action(aid)
  trace=[obs(s)]
  for _ in range(12):s.tick();trace.append(obs(s))
  records.append({'id':'F02','role':role,'mode':mode,'scope':'support plus BP, no administered medication; BP alone not assumed causal','actions':['stop_infusion','call_help','high_flow_oxygen','check_bp']+['tick']*12,'trace':trace})
  s=make(role,mode);order=['academy_reassess','academy_sbar_handoff','academy_family_communication','allergy_identification','stop_infusion','call_help','high_flow_oxygen','connect_monitor','check_bp','prepare_rescue_equipment'];trace=[]
  for aid in order:trace.append(step(s,aid))
  records.append({'id':'F03_academy','role':role,'mode':mode,'actions':order,'trace':trace})
  s=make(role,mode);s.apply_action('prepare_rescue_equipment');before=obs(s);r=apply_academy_action(s,'academy_assisted_medication');records.append({'id':'F04','role':role,'mode':mode,'before':before,'result':r,'after':obs(s),'log':[e.__dict__ for e in s.log]})
for role in ['initial','variant']:
 s=make(role);s.apply_action('reassess_first');trace=[obs(s)]
 order=['stop_infusion','call_help','abc_assess','high_flow_oxygen','shock_position','connect_monitor','check_bp','im_epinephrine','fluid_bolus','reassess_first','bronchodilator','steroid','reassess_second','family_explain','sbar_handoff']
 for aid in order:trace.append(step(s,aid))
 records.append({'id':'F03_clinical','role':role,'actions':['reassess_first']+order,'trace':trace})
for role in ['initial','academy_initial']:
 s=make(role);snap=s.to_snapshot();snap['state']['vitals']['SBP']=999;records.append({'id':'F05_snapshot','role':role,'mutation':'export.state.vitals.SBP=999','live_SBP_after':s.state.vitals['SBP']})
 s=make(role);s.apply_action('stop_infusion');report=s.build_report();report['log'][-1]['data']['audit_mutation']=True;records.append({'id':'F05_report','role':role,'live_log_mutated':s.log[-1].data.get('audit_mutation',False)})
 s=make(role);snap=s.to_snapshot();restored=Simulator.from_snapshot(snap);snap['state']['flags']['audit_mutation']=True;records.append({'id':'F05_restore','role':role,'restored_flags_mutated':restored.state.flags.get('audit_mutation',False)})
for method in ['apply_epinephrine_dose','apply_fluid_bolus_volume','apply_steroid_dose']:
 for value in [float('nan'),float('inf'),float('-inf')]:
  s=make('initial');s.apply_action('stop_infusion');s.apply_epinephrine_dose(.14) if method!='apply_epinephrine_dose' else None
  if method=='apply_steroid_dose':s.apply_fluid_bolus_volume(140)
  result=getattr(s,method)(value)
  records.append({'id':'F06','method':method,'input':repr(value),'result':result,'after':obs(s)})
# Additional deterministic faults: repeated supportive effect, early CPR carries over.
s=make('initial');s.apply_action('shock_position');before=obs(s);s.apply_action('shock_position');records.append({'id':'F08_repeat_position','before':before,'after':obs(s)})
s=make('initial');s.apply_action('cpr');records.append({'id':'F09_premature_CPR','after':obs(s)})
records.append({'id':'F07','status':'NOT_REPRODUCED_IN_REAL_APP_BROWSER','reason':'Streamlit absent; package installation and direct download failed. Static timer fragments exist; causality unproven.'})
def clean(v):
 if isinstance(v,float) and not math.isfinite(v):return {'nonfinite_float':repr(v)}
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [clean(x) for x in v]
 return v
(out/'observations.json').write_text(json.dumps(clean(records),ensure_ascii=False,indent=2,allow_nan=False))
for r in records:
 print(r['id'],r.get('role',r.get('method','')),r.get('mode',''),r.get('unchanged_all_ticks',''), ('end='+str(r['trace'][-1]['done'])+' score='+str(r['trace'][-1]['report_score'])) if r.get('trace') else r.get('result',r.get('status','')))
