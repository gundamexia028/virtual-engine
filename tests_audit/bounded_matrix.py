"""Deterministic bounded enumeration. NEVER describes all possible histories.

Each JSONL record preserves tested inputs + actual state trajectory/digest. No
random sampling. The limits are part of the test contract, not coverage claims.
"""
from __future__ import annotations
import argparse,copy,hashlib,itertools,json,math,sys,time,traceback
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_integrity import make,ROLES
from test_pathways import ACADEMY_PATH,CLINICAL_PATH,step
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.integrity import assert_finite_tree

SELECTED=('stopped_infusion','help_called','bp_checked','rescue_equipment_prepared','academy_medication_checked',
 'academy_assisted_medication_done','epi_im_given','fluid_bolus_valid','first_reassessment_done',
 'second_reassessment_done','academy_reassessment_done','academy_sbar_done','cardiac_arrest','dead','cpr_done',
 'bvm_done','advanced_support_contacted','resuscitation_rosc')

def view(s):
 return {'t':s.state.t,'score':s.display_score(),'vitals':copy.deepcopy(s.state.vitals),
 'grade':s.state.grade,'flags':{k:s.state.flags.get(k) for k in SELECTED if k in s.state.flags},
 'valid':dict(s.action_valid_time),'end':s.is_done()}

def invariant(s):
 assert 0<=s.score<=s.max_score
 assert 0<=s.display_score()<=s.max_score
 assert 0<=s.state.t<=s.scenario['end_conditions']['max_time_seconds']
 assert_finite_tree(s.state.vitals);assert_finite_tree(s.state.flags)
 assert all(0<=at<=s.state.t for at in s.action_valid_time.values())
 assert not any(e.message=='rule_eval_error' for e in s.log)
 if 'im_epinephrine' in s.action_valid_time:assert s.state.flags['epi_im_given']
 if s._is_academy_basic_case():
  f=s.state.flags
  if f.get('academy_assisted_medication_done'):
   assert f['rescue_equipment_prepared'] and f['academy_medication_checked'] and f['help_called']
  if f.get('academy_reassessment_done'):
   assert s.action_valid_time['academy_reassess']>=s.action_valid_time['academy_assisted_medication']+s.tick_seconds
  if s.is_done()[1]=='success':
   assert all(a in s.action_valid_time for a in ACADEMY_PATH)
   assert s.state.vitals['SpO2']>=95 and s.state.vitals['SBP']>=s.age_sbp_threshold()
   if f.get('order_violations') or f.get('academy_safety_penalty_points'):assert s.display_score()<100

class Recorder:
 def __init__(self,out,section):
  self.out=out;self.section=section;out.mkdir(parents=True,exist_ok=True);self.file=(out/(section+'.jsonl')).open('w')
  self.counts=Counter();self.failures=[];self.rules=defaultdict(set);self.outcomes=Counter();self.start=time.monotonic()
 def run(self,case_id,inputs,fn):
  try:
   s,trajectory=fn();invariant(s)
   for e in s.log:
    if e.message=='rule_applied':self.rules[s.scenario['scenario']['script_role']].add(e.data['rule'])
   self.outcomes[s.is_done()[1] or 'running']+=1
   data={'id':case_id,'inputs':inputs,'status':'PASS','trajectory':trajectory,'final':view(s)}
   data['final_state_sha256']=hashlib.sha256(json.dumps(s.to_snapshot(),sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
  except Exception as exc:
   data={'id':case_id,'inputs':inputs,'status':'FAIL','error':repr(exc),'traceback':traceback.format_exc()};self.failures.append(data)
  self.file.write(json.dumps(data,ensure_ascii=False,allow_nan=False)+'\n');self.counts[data['status']]+=1
 def close(self,boundary):
  self.file.close()
  result={'section':self.section,'boundary':boundary,'counts':dict(self.counts),'failures':self.failures,
          'executed_rules':{k:sorted(v) for k,v in self.rules.items()},'terminal_counts':dict(self.outcomes),
          'elapsed_seconds':round(time.monotonic()-self.start,3),'random_sampling':False,'browser_test':False}
  (self.out/(self.section+'_summary.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
  print(json.dumps({k:v for k,v in result.items() if k not in ('failures','executed_rules')},ensure_ascii=False))
  return bool(self.failures)

def pairs(r):
 for role,mode in itertools.product(ROLES,('coach','exam')):
  ids=[a['id'] for a in make(role,mode).actions]
  for tick_each,(a,b) in itertools.product((False,True),itertools.product(ids,repeat=2)):
   def run(role=role,mode=mode,tick_each=tick_each,a=a,b=b):
    s=make(role,mode);trace=[view(s)]
    for aid in (a,b):step(s,aid,tick=tick_each);invariant(s);trace.append(view(s))
    return s,trace
   r.run(f'{role}:{mode}:{int(tick_each)}:{a}>{b}',{'role':role,'mode':mode,'actions':[a,b],'tick_after_each':tick_each},run)
 return r.close('All ordered pairs with replacement from the fresh state: clinical 24^2×4 configs×2 timing variants + academy 20^2×4×2 = 7,808 histories. Numeric actions use canonical valid values. No arbitrary depth or all patient profiles in this section.')

def permutations(r):
 tail=ACADEMY_PATH[6:]
 for role,mode in itertools.product(('academy_initial','academy_variant'),('coach','exam')):
  for order in itertools.permutations(tail):
   def run(role=role,mode=mode,order=order):
    s=make(role,mode);trace=[]
    for aid in (*ACADEMY_PATH[:6],*order):step(s,aid);invariant(s);trace.append(view(s))
    if order==tuple(tail):assert s.is_done()==(True,'success') and s.display_score()==100
    else:assert s.is_done()[1]!='success' and s.display_score()<100
    return s,trace
   r.run(f'{role}:{mode}:'+'>'.join(order),{'role':role,'mode':mode,'prefix':ACADEMY_PATH[:6],'permutation':order},run)
 return r.close('All 6! permutations, once each, of academy preparation/check/admin/reassessment/family/SBAR, after the same valid six-action prefix; 720×2 academy cases×2 modes = 2,880 histories; one 30s tick after each action. Not permutations of every system action or arbitrary repeats.')

def numerics(r):
 for role,mode,age in itertools.product(('initial','variant'),('coach','exam'),range(1,12)):
  weight=age*2+8 if age<=6 else age*3+2
  target=round(min(.01*weight,.3),3)
  for method,values in [
   ('apply_epinephrine_dose',[0,round(target-.011,3),round(target-.01,3),target,round(target+.01,3),round(target+.011,3),.3,.301]),
   ('apply_fluid_bolus_volume',[0,10*weight-.1,10*weight,(10*weight+min(20*weight,500))/2,min(20*weight,500),min(20*weight,500)+.1,500,500.1]),
   ('apply_steroid_dose',[0,weight-.1,float(weight),(weight+min(2*weight,40))/2,min(2*weight,40),min(2*weight,40)+.1,40,40.1])]:
   for idx,value in enumerate(values):
    def run(role=role,mode=mode,age=age,weight=weight,method=method,value=value,target=target):
     scenario=make(role,mode).scenario;scenario['patient'].update(age_years=age,weight_kg=weight)
     s=Simulator(scenario,mode=mode,seed=17);s.apply_action('stop_infusion')
     if method!='apply_epinephrine_dose':s.apply_epinephrine_dose(target);s.tick()
     if method=='apply_steroid_dose':s.apply_fluid_bolus_volume(10*weight);s.tick()
     before=view(s);result=getattr(s,method)(value)
     if method=='apply_epinephrine_dose':
      expected='overdose' if value>.3+1e-9 else ('underdose' if value<round(target-.01,3) else ('dose_high' if value>round(target+.01,3) else 'valid'))
     else:
      low=10*weight if method=='apply_fluid_bolus_volume' else weight
      high=min(20*weight,500) if method=='apply_fluid_bolus_volume' else min(2*weight,40)
      expected='under' if value<low else ('over' if value>high else 'valid')
     assert result['status']==expected,(result,expected,age,weight)
     return s,[before,{'input':value,'result':result},view(s)]
    r.run(f'{role}:{mode}:age{age}:{method}:{idx}',{'role':role,'mode':mode,'age':age,'weight':weight,'method':method,'value':value},run)
 return r.close('11 actually generated clinical age/weight pairs × 2 cases × 2 modes × 3 numeric APIs × 8 boundary probes = 1,056 trials. Inclusive endpoints checked independently. Separate unit tests cover NaN/Inf/bool/malformed values. Not all real-valued doses.')

def time_paths(r):
 for role,mode in itertools.product(ROLES,('coach','exam')):
  for prefix in ([],['stop_infusion','call_help'],['stop_infusion','call_help','high_flow_oxygen']):
   def run(role=role,mode=mode,prefix=prefix):
    s=make(role,mode);trace=[]
    for aid in prefix:s.apply_action(aid)
    for _ in range(int(s.scenario['end_conditions']['max_time_seconds'])//s.tick_seconds+2):
     old=s.state.t;s.tick();invariant(s);trace.append(view(s));assert s.state.t>=old
     if s.is_done()[0]:
      before=s.to_snapshot();s.tick();assert s.to_snapshot()==before;break
    assert s.is_done()[0]
    return s,trace
   r.run(f'{role}:{mode}:'+','.join(prefix or ['untreated']),{'role':role,'mode':mode,'zero_time_prefix':prefix},run)
 return r.close('24 complete trajectories: 4 cases ×2 modes ×3 fixed prefixes, advancing every reachable 30s step until the engine terminates (not forcing time past death). Terminal extra tick must be a no-op. Does not enumerate every history at each time.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--section',choices=['pairs','permutations','numerics','time_paths'],required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();sys.exit(1 if globals()[a.section](Recorder(a.out,a.section)) else 0)
