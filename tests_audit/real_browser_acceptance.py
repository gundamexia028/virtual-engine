"""Loopback-only Playwright runner, with real Streamlit, screenshots and trace.
This runner is DELIVERED but was runtime-blocked in the audit environment.
A fixture seeds cases for real rendering; production entry auth/mode smoke runs
separately. Fixture coverage must never be labeled full registration E2E.
"""
from __future__ import annotations
import argparse,importlib.util,json,os,secrets,shutil,socket,subprocess,sys,tempfile,time,traceback,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ACADEMY=['allergy_identification','stop_infusion','call_help','high_flow_oxygen','connect_monitor','check_bp','prepare_rescue_equipment','academy_medication_check','academy_assisted_medication','academy_reassess','academy_family_communication','academy_sbar_handoff']
CLINICAL=['stop_infusion','call_help','abc_assess','high_flow_oxygen','shock_position','connect_monitor','check_bp','im_epinephrine','fluid_bolus','reassess_first','bronchodilator','steroid','reassess_second','family_explain','sbar_handoff']
CASES=[f'{system}_{role}_{mode}' for system in ('clinical','academy') for role in ('initial','variant') for mode in ('coach','exam')]
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--chromium');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 missing=[x for x in ('streamlit','playwright') if importlib.util.find_spec(x) is None]
 status={'status':'BLOCKED','missing':missing,'app_interaction_cases_executed':0,'production_auth_smoke_executed':False,'case_results':[],'fixture_scope':'real production rendering with seeded synthetic participant/phase; not full registration E2E','online_writes':False}
 exe=a.chromium or shutil.which('chromium') or shutil.which('chromium-browser')
 if exe:
  q=subprocess.run([exe,'--version'],capture_output=True,text=True);status['chromium_version']=q.stdout.strip()
 if missing:
  status['reason']='Missing real application runtime; NO fake Streamlit/server substituted.'
  (out/'browser_result.json').write_text(json.dumps(status,indent=2,ensure_ascii=False));print(json.dumps(status,ensure_ascii=False));return 2
 from playwright.sync_api import sync_playwright
 processes=[];handles=[]
 def port():
  with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
 def server(entry,env,cwd,name):
  n=port();log=(out/(name+'_server.log')).open('w');handles.append(log)
  proc=subprocess.Popen([sys.executable,'-m','streamlit','run',str(entry),'--server.address=127.0.0.1',f'--server.port={n}','--server.headless=true','--server.fileWatcherType=none','--browser.gatherUsageStats=false'],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT);processes.append(proc)
  for _ in range(150):
   if proc.poll() is not None:raise RuntimeError(name+' server exited; see log')
   try:
    if urllib.request.urlopen(f'http://127.0.0.1:{n}/_stcore/health',timeout=1).status==200:return f'http://127.0.0.1:{n}'
   except OSError:pass
   time.sleep(.2)
  raise RuntimeError(name+' server startup timeout')
 try:
  with tempfile.TemporaryDirectory(prefix='ve-browser-offline-') as tmp:
   clone=Path(tmp)/'repo';shutil.copytree(ROOT,clone,ignore=shutil.ignore_patterns('__pycache__','.git','.venv','audit_results','htmlcov','runs','runs_web','.runtime','secrets.toml','org_access_codes.json'))
   env=dict(os.environ);env.update(APP_MODE='production',VE_AUDIT_BROWSER_FIXTURE='1',APP_ACCESS_CODE=secrets.token_urlsafe(24),ADMIN_PASSWORD=secrets.token_urlsafe(32),AUTH_CONTEXT_SIGNING_KEY=secrets.token_urlsafe(40),PEDSIM_RESULTS_DIR=str(Path(tmp)/'runs'),PEDSIM_DRAFTS_DIR=str(Path(tmp)/'drafts'))
   for k in ('SUPABASE_URL','SUPABASE_KEY','SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY'):env[k]=''
   # Production authentication intentionally reads st.secrets, not environment fallbacks.
   # Supply only synthetic credentials inside this disposable clone; never log them.
   auth_file=clone/'app/.streamlit/secrets.toml'
   auth_file.parent.mkdir(parents=True,exist_ok=True)
   auth_file.touch(mode=0o600,exist_ok=False)
   auth_file.write_text('\n'.join(f'{key} = {json.dumps(env[key])}' for key in
       ('APP_ACCESS_CODE','ADMIN_PASSWORD','AUTH_CONTEXT_SIGNING_KEY'))+'\n',encoding='utf-8')
   pw=sync_playwright().start()
   if True:
    browser=pw.chromium.launch(headless=True,**({'executable_path':exe} if exe else {}))
    context=browser.new_context(viewport={'width':1440,'height':1100})
    # Block all non-loopback HTTP traffic, including optional analytics/storage.
    context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(('http://127.0.0.1:','http://localhost:','data:','blob:')) else route.abort())
    page=context.new_page();console=[];page.on('pageerror',lambda err:console.append(str(err)))
    actual=server(clone/'app/streamlit_app.py',env,clone/'app','production_entry')
    page.goto(actual);page.get_by_label('访问码',exact=True).fill(env['APP_ACCESS_CODE']);page.get_by_role('button',name='进入系统',exact=True).click()
    page.get_by_role('button',name='进入临床模式',exact=True).wait_for();page.get_by_role('button',name='进入学院模式',exact=True).wait_for()
    status['production_auth_smoke_executed']=True;page.screenshot(path=str(out/'production_entry_modes.png'),full_page=True)
    # Start trace after login so the synthetic access-code fill is not recorded.
    context.tracing.start(screenshots=True,snapshots=True,sources=True)
    fixture=server(clone/'tests_audit/browser_fixture_app.py',env,clone/'app','fixture')
    page.goto(fixture)
    def read():return json.loads(page.locator('#audit-state').inner_text(timeout=15000))
    def changed(prev):
     page.wait_for_function('(old)=>{let e=document.querySelector("#audit-state");if(!e)return false;let s=JSON.parse(e.textContent);return s.session_id!==old.session_id||s.log_n!==old.log_n||s.t!==old.t}',arg=prev,timeout=15000)
    # Help-enabled Streamlit buttons have desktop/mobile DOM copies. Role locators
    # exclude the hidden copy while still failing if multiple accessible buttons exist.
    def action(aid):
     before=read();sid=before['session_id'];page.locator(f'.st-key-action_{sid}_{aid}').get_by_role('button').click()
     if aid in ('im_epinephrine','fluid_bolus','steroid'):
      kind={'im_epinephrine':'epinephrine','fluid_bolus':'fluid','steroid':'steroid'}[aid]
      v=min(.01*before['weight'],.3) if aid=='im_epinephrine' else (10*before['weight'] if aid=='fluid_bolus' else min(before['weight'],40))
      input_label={'epinephrine':'本次肌注总剂量（mg）','fluid':'本次快速补液容量（ml）','steroid':'本次甲泼尼龙剂量（mg）'}[kind]
      page.get_by_role('spinbutton',name=input_label,exact=True).fill(str(v));page.locator(f'.st-key-confirm_{kind}_{sid}').get_by_role('button').click()
     changed(before)
    for case in CASES:
     if read()['case']!=case:
      page.get_by_label('审计病例组合',exact=True).click();page.get_by_role('option',name=case,exact=True).click();page.wait_for_function('(c)=>document.querySelector("#audit-state")&&JSON.parse(document.querySelector("#audit-state").textContent).case===c',arg=case)
     for aid in ACADEMY if case.startswith('academy') else CLINICAL:action(aid)
     final=read();assert final['end'][0] and final['score']==100,(case,final)
     status['case_results'].append({'case':case,'status':'PASS','t':final['t'],'score':final['score'],'end':final['end']});status['app_interaction_cases_executed']+=1
     page.screenshot(path=str(out/(case+'.png')),full_page=True)
    # An idle render and rapid action sequence must preserve all principal regions.
    before_reset=read();page.get_by_role('button',name='重新开始审计病例',exact=True).click();changed(before_reset)
    action('stop_infusion');action('call_help');before=read()
    for _ in range(6):
     old=read();page.locator(f'.st-key-advance_time_{old["session_id"]}').get_by_role('button').click();changed(old)
    after=read();assert after['vitals']!=before['vitals']
    time.sleep(3);assert page.locator('.vital-grid').count()>0 and page.locator('.action-head').count()>0
    page.screenshot(path=str(out/'continuous_actions_complete_page.png'),full_page=True)
    page.reload();read();assert page.locator('.vital-grid').count()>0
    assert not console,console
    (out/'page_errors.json').write_text(json.dumps(console,ensure_ascii=False,indent=2))
    context.tracing.stop(path=str(out/'playwright_trace.zip'));context.close();browser.close()
    status['status']='PASS_SCOPED_BROWSER_INTEGRATION';status['reason']='Production entry auth/mode smoke + eight seeded case/mode render workflows. Full registration/SUS/admin E2E still outside this fixture.'
 except Exception as exc:
  status.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
  try:page.screenshot(path=str(out/'failure.png'),full_page=True);context.tracing.stop(path=str(out/'failure_trace.zip'))
  except Exception:pass
 finally:
  try:pw.stop()
  except Exception:pass
  for proc in processes:
   proc.terminate()
   try:proc.wait(timeout=5)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
  for h in handles:h.close()
  (out/'browser_result.json').write_text(json.dumps(status,indent=2,ensure_ascii=False))
 print(json.dumps(status,ensure_ascii=False));return 0 if status['status'].startswith('PASS_') else 1
if __name__=='__main__':sys.exit(main())
