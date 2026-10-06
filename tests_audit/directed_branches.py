"""Named branch witnesses, explicitly separating natural paths and injected fixtures."""
import argparse,sys,itertools
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from bounded_matrix import Recorder,view,invariant
from test_integrity import make,ROLES
from test_pathways import ACADEMY_PATH,CLINICAL_PATH,step,standard

def main(out):
 r=Recorder(out,'directed_branches')
 for role,mode in itertools.product(ROLES,('coach','exam')):
  def normal(role=role,mode=mode):
   s=make(role,mode);trace=[]
   for aid in ACADEMY_PATH if s._is_academy_basic_case() else CLINICAL_PATH:step(s,aid);trace.append(view(s))
   assert s.is_done()[0] and s.display_score()==100;return s,trace
  r.run(f'{role}:{mode}:standard',{'kind':'natural path','role':role,'mode':mode},normal)
 for role,mode in itertools.product(('initial','variant'),('coach','exam')):
  for response in ('cpr_bvm_als','no_cpr_action','no_cpr_time'):
   def arrest(role=role,mode=mode,response=response):
    s=make(role,mode);trace=[]
    for _ in range(50):
     if s.state.flags.get('cardiac_arrest') or s.is_done()[0]:break
     s.tick();trace.append(view(s))
    assert s.state.flags['cardiac_arrest'] and not s.is_done()[0]
    if response=='cpr_bvm_als':
     for aid in ('cpr','bvm_ventilation','advanced_support'):step(s,aid);trace.append(view(s))
     assert s.is_done()==(True,'critical_resuscitated_transfer_picu')
    elif response=='no_cpr_action':s.apply_action('call_help');trace.append(view(s));assert s.state.flags['dead']
    else:s.tick();trace.append(view(s));assert s.state.flags['dead']
    before=s.to_snapshot();s.tick();s.apply_action('cpr');assert s.to_snapshot()==before
    return s,trace
   r.run(f'{role}:{mode}:{response}',{'kind':'natural untreated path to arrest','role':role,'mode':mode,'response':response},arrest)
  def airway(role=role,mode=mode):
   s=make(role,mode);trace=[]
   for aid in CLINICAL_PATH[:7]:step(s,aid);trace.append(view(s))
   s.apply_steroid_dose(min(s.state.weight_kg,40));s.tick();trace.append(view(s))
   for _ in range(15):
    if s._bvm_indicated() or s.is_done()[0]:break
    s.tick();trace.append(view(s))
   assert s._bvm_indicated() and not s.is_done()[0]
   if s.state.flags['cardiac_arrest']:s.apply_action('cpr')
   s.apply_action('bvm_ventilation');s.apply_epinephrine_dose(min(.01*s.state.weight_kg,.3));s.apply_action('nebulized_epinephrine');s.apply_action('advanced_support')
   for _ in range(8):s.tick();trace.append(view(s))
   assert s.state.flags['bvm_done'];return s,trace
  r.run(f'{role}:{mode}:airway_adjunct',{'kind':'natural delay via wrong-order steroid after seven core steps','role':role,'mode':mode},airway)
  def line(role=role,mode=mode):
   s=make(role,mode);trace=[]
   s.apply_action('remove_iv');s.apply_epinephrine_dose(min(.01*s.state.weight_kg,.3));res=s.apply_fluid_bolus_volume(10*s.state.weight_kg);trace.append({'result':res,**view(s)})
   assert not s.state.flags['fluid_bolus_valid'];s.tick();s.apply_action('establish_iv');s.apply_fluid_bolus_volume(10*s.state.weight_kg);s.tick();trace.append(view(s))
   assert s.state.flags['iv_access'] and s.state.flags['fluid_bolus_valid'];return s,trace
  r.run(f'{role}:{mode}:iv_lost_restored',{'kind':'natural IV-loss path','role':role,'mode':mode},line)
  for t in (299,300,301):
   def repeat(role=role,mode=mode,t=t):
    s=make(role,mode);s.apply_action('stop_infusion');s.apply_epinephrine_dose(min(.01*s.state.weight_kg,.3));s.apply_fluid_bolus_volume(10*s.state.weight_kg);s.tick();s.apply_action('reassess_first')
    s.state.t=t;s.state.vitals['SpO2']=94;s.state.vitals['SBP']=s.age_sbp_threshold()-1
    before=view(s);n=s.state.flags['epi_im_doses'];result=s.apply_epinephrine_dose(min(.01*s.state.weight_kg,.3),action_id='repeat_epinephrine')
    assert result['status']==('too_soon' if t<300 else 'valid')
    assert s.state.flags['epi_im_doses']==n+(0 if t<300 else 1)
    return s,[before,{'result':result},view(s)]
   r.run(f'{role}:{mode}:repeat_at_{t}',{'kind':'synthetic interval fixture; 299/301 are not reachable 30-second tick times','t':t,'role':role,'mode':mode},repeat)
 for role,mode in itertools.product(('academy_initial','academy_variant'),('coach','exam')):
  for wrong in ('continue_infusion','ask_family_first','send_family_for_help','prepare_steroid_antihistamine_only','student_independent_epinephrine','watch_only','remove_iv'):
   def recover(role=role,mode=mode,wrong=wrong):
    s=make(role,mode);step(s,wrong);trace=[view(s)]
    for aid in ACADEMY_PATH:
     step(s,aid);trace.append(view(s))
     if aid=='call_help' and wrong=='remove_iv':s.apply_action('academy_restore_iv');trace.append(view(s))
    for _ in range(10):
     if s.is_done()[0]:break
     s.tick();trace.append(view(s))
    assert s.display_score()<100 and s.state.flags['academy_safety_penalty_points']>0
    assert s.is_done()==(True,'success'),(wrong,s.is_done(),s._unfinished_required_steps())
    return s,trace
   r.run(f'{role}:{mode}:recover_{wrong}',{'kind':'natural unsafe action + supervised remedial path','role':role,'mode':mode,'wrong':wrong},recover)
 return r.close('68 named witnesses: 8 standard; 12 natural arrest/CPR/ROSC-or-omission; 4 natural airway/adjunct; 4 natural IV loss/recovery; 12 explicitly synthetic repeat-dose interval boundaries; 28 natural academy unsafe-action/remediation paths. No claim of all reachable histories.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();sys.exit(1 if main(a.out) else 0)
