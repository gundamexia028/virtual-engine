import sys,json,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.repo/'app'))
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.scenario_loader import load_scenario_by_role
rows=[]
for role in ('initial','variant'):
 for mode in ('coach','exam'):
  d=load_scenario_by_role(role);d['patient'].update(age_years=1,weight_kg=10)
  s=Simulator(d,mode=mode,seed=17);s.apply_action('stop_infusion');r=s.apply_epinephrine_dose(.09)
  rows.append({'role':role,'mode':mode,'age':1,'weight':10,'target':.1,'inclusive_lower':.09,'result':r})
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(rows,ensure_ascii=False,indent=2,allow_nan=False));print(a.out.read_text())
