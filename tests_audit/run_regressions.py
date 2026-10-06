"""Offline-safe regression entry. Real runtime is default; mocks require explicit opt-in.
Exit 0=all requested layers pass, 1=assertion failure, 2=runtime layer blocked.
"""
from __future__ import annotations
import argparse,importlib.util,json,os,re,secrets,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--unit-double',action='store_true');p.add_argument('--with-matrix',action='store_true');p.add_argument('--coverage',action='store_true');p.add_argument('--only',help='Comma-separated exact task names; omitted runs all requested tasks.');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 env=dict(os.environ);env.update(PYTHONDONTWRITEBYTECODE='1',APP_MODE='production',AUTH_CONTEXT_SIGNING_KEY=secrets.token_urlsafe(40),APP_ACCESS_CODE=secrets.token_urlsafe(24),ADMIN_PASSWORD=secrets.token_urlsafe(32))
 env.update({k:'' for k in ('SUPABASE_URL','SUPABASE_KEY','SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY')})
 env.update(PEDSIM_RESULTS_DIR=str(out/'scratch/runs'),PEDSIM_DRAFTS_DIR=str(out/'scratch/drafts'),PEDSIM_ORG_CREDENTIALS_DIR=str(out/'scratch/credentials'))
 env['VE_AUDIT_UNIT_DOUBLE']='1' if a.unit_double else '0'
 if a.coverage:env['COVERAGE_FILE']=str(out/'.coverage')
 results=[]
 selected=set(a.only.split(',')) if a.only else None
 known={'audit_unit',*(f.stem for f in (ROOT/'app/tests').glob('*.py'))}
 if a.with_matrix:known.update({'matrix_'+s for s in ('pairs','permutations','numerics','time_paths')}|{'directed_branches'})
 if selected and selected-known:p.error('Unknown or unrequested task(s): '+','.join(sorted(selected-known)))
 def run(name,cmd,kind):
  if selected is not None and name not in selected:return

  start=time.monotonic()
  try:
   q=subprocess.run(cmd,cwd=(ROOT/'app' if kind.endswith('legacy') or kind.startswith('unit_existing') else ROOT),env=env,capture_output=True,text=True,timeout=60);txt=q.stdout+q.stderr;rc=q.returncode
  except subprocess.TimeoutExpired as e:txt=str(e);rc=124
  (out/(name+'.log')).write_text(txt)
  tests=re.findall(r'Ran (\d+) tests?',txt)
  status='PASS' if rc==0 else ('BLOCKED_RUNTIME' if ('streamlit.testing' in txt or "No module named 'streamlit'" in txt) else 'FAIL')
  results.append({'name':name,'kind':kind,'status':status,'returncode':rc,'unittest_methods':int(tests[-1]) if tests else None,'seconds':round(time.monotonic()-start,3)})
  (out/'progress.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
  print(name,status,flush=True)
 def cv(cmd):return [sys.executable,'-m','coverage','run','--append','--branch','--source=app',*cmd] if a.coverage else [sys.executable,*cmd]
 run('audit_unit',cv(['-m','unittest','discover','-s','tests_audit','-v']),'actual_engine_and_controller_unit_tests')
 has_runtime=importlib.util.find_spec('streamlit') is not None
 for f in sorted((ROOT/'app/tests').glob('*.py')):
  if selected is not None and f.stem not in selected:continue
  if not a.unit_double and not has_runtime:
   (out/(f.stem+'.log')).write_text('BLOCKED: real Streamlit is not installed. No mock substituted.\n')
   results.append({'name':f.stem,'kind':'real_runtime_legacy','status':'BLOCKED_RUNTIME','returncode':2,'unittest_methods':None});continue
  boot=("import runpy;runpy.run_path("+repr(str(ROOT/'app/tests/credential_security_tests.py'))+",run_name='stub_bootstrap');") if a.unit_double else 'import streamlit;import runpy;'
  code="import sys;sys.argv=["+repr(str(f))+ "];sys.path.insert(0,"+repr(str(ROOT/'app'))+");"+boot
  # Legacy stress/concurrency scripts remain isolated and uninstrumented.
  # --coverage measures the directed audit unit suite only, not these scripts.
  code+="runpy.run_path("+repr(str(f))+",run_name='__main__')"
  run(f.stem,[sys.executable,'-c',code],'unit_existing_streamlit_double_NOT_BROWSER' if a.unit_double else 'real_runtime_legacy')
 if a.with_matrix:
  for section in ('pairs','permutations','numerics','time_paths'):
   run('matrix_'+section,([sys.executable]+['tests_audit/bounded_matrix.py','--section',section,'--out',str(out/'matrix')]),'bounded_deterministic_engine_enumeration')
  run('directed_branches',([sys.executable]+['tests_audit/directed_branches.py','--out',str(out/'matrix')]),'natural_witnesses_and_labeled_synthetic_fixtures')
 if a.coverage and (out/'.coverage').exists():
  # Keep the core aggregate and import per-script data without conflating coverage with browser testing.
  from coverage import CoverageData,Coverage
  data=CoverageData(basename=str(out/'.coverage'));data.read()
  for f in out.glob('.coverage.*'):
   part=CoverageData(basename=str(f));part.read();data.update(part)
  data.write();cov=Coverage(data_file=str(out/'.coverage'));cov.load();cov.json_report(outfile=str(out/'coverage.json'));cov.html_report(directory=str(out/'coverage_html'))
 summary={'requested_task_filter':sorted(selected) if selected else None,'unit_double_explicit':a.unit_double,'real_streamlit_installed':has_runtime,'browser_executed':False,'coverage_scope':'directed audit unit suite only; legacy scripts and bounded matrices are not instrumented','results':results,
 'status':'FAIL' if any(x['status']=='FAIL' for x in results) else ('BLOCKED_RUNTIME' if any(x['status']=='BLOCKED_RUNTIME' for x in results) else 'PASS_REQUESTED_LAYERS_ONLY')}
 (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));print('SUMMARY',summary['status'])
 return 1 if summary['status']=='FAIL' else (2 if summary['status']=='BLOCKED_RUNTIME' else 0)
if __name__=='__main__':sys.exit(main())
