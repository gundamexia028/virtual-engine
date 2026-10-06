"""Loopback-only Playwright runner, with real Streamlit, screenshots and trace.
This runner is DELIVERED but was runtime-blocked in the audit environment.
A fixture seeds cases for real rendering; production entry auth/mode smoke runs
separately. Fixture coverage must never be labeled full registration E2E.
"""
from __future__ import annotations
import argparse,importlib.util,json,os,re,secrets,shutil,socket,subprocess,sys,tempfile,time,traceback,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ACADEMY=['allergy_identification','stop_infusion','call_help','high_flow_oxygen','connect_monitor','check_bp','prepare_rescue_equipment','academy_medication_check','academy_assisted_medication','academy_reassess','academy_family_communication','academy_sbar_handoff']
CLINICAL=['stop_infusion','call_help','abc_assess','high_flow_oxygen','shock_position','connect_monitor','check_bp','im_epinephrine','fluid_bolus','reassess_first','bronchodilator','steroid','reassess_second','family_explain','sbar_handoff']
CASES=[f'{system}_{role}_{mode}' for system in ('clinical','academy') for role in ('initial','variant') for mode in ('coach','exam')]
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--chromium');p.add_argument('--repo',type=Path,default=ROOT,help='Read-only source root; always cloned for testing');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 missing=[x for x in ('streamlit','playwright') if importlib.util.find_spec(x) is None]
 status={'status':'BLOCKED','missing':missing,'app_interaction_cases_executed':0,'production_auth_smoke_executed':False,'case_results':[],'fixture_scope':'real production rendering with seeded synthetic participant/phase; not full registration E2E','online_writes':False,'workflow_defect_checks':[],'source_root':str(a.repo.resolve())}
 exe=a.chromium or shutil.which('chromium') or shutil.which('chromium-browser')
 if exe:
  q=subprocess.run([exe,'--version'],capture_output=True,text=True);status['chromium_version']=q.stdout.strip()
 if missing:
  status['reason']='Missing real application runtime; NO fake Streamlit/server substituted.'
  (out/'browser_result.json').write_text(json.dumps(status,indent=2,ensure_ascii=False));print(json.dumps(status,ensure_ascii=False));return 2
 from playwright.sync_api import sync_playwright,expect
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
   clone=Path(tmp)/'repo';shutil.copytree(a.repo.resolve(),clone,ignore=shutil.ignore_patterns('__pycache__','.git','.venv','audit_results','htmlcov','runs','runs_web','.runtime','secrets.toml','org_access_codes.json'))
   # The current test fixture observes the selected source tree without editing it.
   shutil.copy2(ROOT/'tests_audit/browser_fixture_app.py',clone/'tests_audit/browser_fixture_app.py')
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
    # Production entry E2E: real registration, learner replacement, and refresh.
    # No fixture reset and no direct session-state seeding in these checks.
    def click_text(label):page.get_by_role('button',name=label,exact=True).click()
    def select_text(label,value):
     page.get_by_label(label,exact=True).click();page.get_by_role('option',name=value,exact=True).click()
    def action_key(aid):
     page.wait_for_function('(aid)=>Array.from(document.querySelectorAll("[class*=st-key-action_]")).flatMap(n=>Array.from(n.classList)).filter(c=>c.startsWith("st-key-action_")&&c.endsWith("_"+aid)).length===1',arg=aid,timeout=15000)
     return page.locator('[class*="st-key-action_"]').evaluate_all('(nodes,aid)=>{let a=nodes.flatMap(n=>Array.from(n.classList)).filter(c=>c.startsWith("st-key-action_")&&c.endsWith("_"+aid));if(a.length!==1)throw Error("Expected one action key: "+aid+"; "+a);return a[0]}',aid)
    def real_action(aid,completion=''):
     key=action_key(aid);before_history=page.locator('.history-panel').inner_text()
     if aid in ('im_epinephrine','fluid_bolus','steroid'):
      match=re.search(r'(\d+(?:\.\d+)?)\s*kg',page.locator('.patient-meta').inner_text())
      assert match,'Patient body weight must be visible before dosing'
      weight=float(match.group(1))
     page.locator('.'+key).get_by_role('button').click()
     if aid in ('im_epinephrine','fluid_bolus','steroid'):
      kind,label,value={'im_epinephrine':('epinephrine','本次肌注总剂量（mg）',min(weight*.01,.3)),
                        'fluid_bolus':('fluid','本次快速补液容量（ml）',weight*10),
                        'steroid':('steroid','本次甲泼尼龙剂量（mg）',min(weight,40))}[aid]
      page.get_by_role('spinbutton',name=label,exact=True).fill(str(value))
      sid=key[len('st-key-action_'):-(len(aid)+1)]
      page.locator(f'.st-key-confirm_{kind}_{sid}').get_by_role('button').click()
     if completion:expect(page.get_by_text(completion,exact=True)).to_be_visible(timeout=15000)
     else:expect(page.locator('.history-panel')).not_to_have_text(before_history,use_inner_text=True,timeout=15000)
     expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    def finish_academy(completion='',skip=()):
     for aid in ACADEMY:
      if aid not in skip:real_action(aid,completion if aid==ACADEMY[-1] else '')
    def assert_score(value):
     card=page.locator('[data-testid="stMetric"]').filter(has=page.get_by_text('最终得分',exact=True))
     expect(card.get_by_text(value,exact=True)).to_be_visible()
    click_text('进入学院模式');click_text('进入该情景')
    page.get_by_label('院校名称（必填）',exact=True).fill('离线审计虚构学院')
    select_text('培养层次（必填）','本科');select_text('年级/阶段（必填）','一年级')
    page.get_by_label('姓名首字母（必填）',exact=True).fill('AAA')
    select_text('采集模式（必填）','测试演练')
    click_text('保存信息并进入学院模式');click_text('开始本阶段')
    real_action('allergy_identification');real_action('stop_infusion')
    saved_key=action_key('call_help');saved_history=page.locator('.history-panel').inner_text()
    saved_url=page.url
    assert 'resume=' in saved_url,saved_url
    page.reload()
    expect(page.locator('.'+saved_key).get_by_role('button')).to_be_visible(timeout=15000)
    expect(page.locator('.history-panel')).to_have_text(saved_history,use_inner_text=True,timeout=15000)
    assert page.url==saved_url
    status.setdefault('production_flow_checks',[]).append({'check':'production_refresh_preserves_session_and_action_history','status':'PASS'})
    finish_academy('课前测评完成',skip=('allergy_identification','stop_infusion'));assert_score('100/100')
    click_text('重新填写对象信息')
    page.get_by_label('姓名首字母（必填）',exact=True).fill('BBB')
    click_text('保存信息并进入学院模式');click_text('开始本阶段')
    real_action('academy_reassess');finish_academy('课前测评完成');assert_score('95/100')
    status['production_flow_checks'].append({'check':'new_learner_result_is_current_95_not_previous_100','status':'PASS'})
    page.screenshot(path=str(out/'production_new_learner_result.png'),full_page=True)
    # Only synthetic data lives on this temporary competition server.
    competition_env=dict(env,APP_MODE='competition',COMPETITION_REVIEW_CODE=secrets.token_urlsafe(24),COMPETITION_ADMIN_CODE=secrets.token_urlsafe(32))
    competition=server(clone/'app/streamlit_app.py',competition_env,clone/'app','competition_entry')
    # Exclude this synthetic login from trace, just like production credentials.
    context.tracing.stop(path=str(out/'production_flow_trace.zip'))
    page.goto(competition);page.get_by_label('评审体验码',exact=True).fill(competition_env['COMPETITION_REVIEW_CODE']);click_text('进入评审体验')
    expect(page.get_by_role('button',name='进入学院教学体验',exact=True)).to_be_visible()
    context.tracing.start(screenshots=True,snapshots=True,sources=True)
    # Fresh competition clinical entry must use the complete live Simulator class.
    # Never replace this with fixture seeding: process/module-cache failures occur
    # at the real entrance and may be absent from isolated imported AppTest apps.
    click_text('进入临床模式演示');click_text('开始本阶段')
    expect(page.locator('.vital-grid')).to_be_visible(timeout=15000)
    expect(page.locator('.action-head')).to_be_visible(timeout=15000)
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    clinical_labels={a['id']:a['label'] for a in json.loads((clone/'app/peds_anaphylaxis_sim/scenarios/peds_ward_anaphylaxis_iv_initial.json').read_text())['actions']}
    for viewport in ({'width':1180,'height':757},{'width':1366,'height':768},{'width':390,'height':844}):
     page.set_viewport_size(viewport)
     collapse=page.locator('[data-testid="stSidebarCollapseButton"] button')
     if viewport['width']==390 and collapse.count() and collapse.is_visible():collapse.click()
     expect(page.locator('.vital-grid')).to_be_visible(timeout=15000)
     expect(page.locator('.action-head')).to_be_visible(timeout=15000)
     label_geometry=page.locator('[class*="st-key-action_"] button').evaluate_all("""nodes=>nodes.filter(n=>n.getClientRects().length&&getComputedStyle(n).visibility!=='hidden').map(button=>{
      let b=button.getBoundingClientRect();let texts=Array.from(button.querySelectorAll('p,[data-testid="stMarkdownContainer"]')).filter(n=>n.getClientRects().length);
      return {key:Array.from(button.closest('[class*=st-key-action_]').classList).find(c=>c.startsWith('st-key-action_')),label:button.innerText,left:b.left,right:b.right,top:b.top,bottom:b.bottom,viewport:innerWidth,texts:texts.map(n=>{let r=n.getBoundingClientRect(),c=getComputedStyle(n);return {text:n.innerText,whiteSpace:c.whiteSpace,overflow:c.overflow,textOverflow:c.textOverflow,scrollWidth:n.scrollWidth,clientWidth:n.clientWidth,left:r.left,right:r.right,top:r.top,bottom:r.bottom}})}
     })""")
     assert label_geometry,'No visible action buttons in viewport'
     for button in label_geometry:
      matching=[label for aid,label in clinical_labels.items() if button['key'].endswith('_'+aid)]
      assert len(matching)==1 and re.sub(r'\s+','',button['label'])==re.sub(r'\s+','',matching[0]),button
      assert button['label'].strip() and button['left']>=-1 and button['right']<=button['viewport']+1,button
      assert button['texts'],button
      for text_geometry in button['texts']:
       assert text_geometry['textOverflow']!='ellipsis' and text_geometry['whiteSpace']!='nowrap',button
       assert text_geometry['scrollWidth']<=text_geometry['clientWidth']+1,button
       assert text_geometry['left']>=button['left']-1 and text_geometry['right']<=button['right']+1,button
       assert text_geometry['top']>=button['top']-1 and text_geometry['bottom']<=button['bottom']+1,button
     size=f"{viewport['width']}x{viewport['height']}"
     (out/('clinical_action_geometry_'+size+'.json')).write_text(json.dumps(label_geometry,ensure_ascii=False,indent=2))
     page.screenshot(path=str(out/('competition_clinical_labels_'+size+'.png')),full_page=True)
     status.setdefault('competition_flow_checks',[]).append({'check':'clinical_action_labels_no_ellipsis_or_overflow','viewport':viewport,'buttons':len(label_geometry),'status':'PASS'})
    page.set_viewport_size({'width':1440,'height':1100})
    expand=page.locator('[data-testid="stSidebarCollapsedControl"] button')
    if expand.count() and expand.is_visible():expand.click()
    last_stage_key=''
    for clinical_phase in ('基线评估','模拟培训','培训后考核'):
     phase_key=action_key('stop_infusion')
     assert phase_key!=last_stage_key,'Each clinical phase requires a fresh session'
     last_stage_key=phase_key
     for clinical_aid in CLINICAL:
      terminal=('基线评估补充信息' if clinical_phase=='基线评估' else '临床模式｜病例结果') if clinical_aid==CLINICAL[-1] else ''
      real_action(clinical_aid,terminal)
     if clinical_phase=='基线评估':
      for label in ('是否接受过过敏反应/过敏性休克相关培训（必填）','是否参加过模拟培训或虚拟仿真培训（必填）','是否真实参与或见习过过敏反应相关处置（必填）'):
       select_text(label,'否')
      click_text('提交补充信息并完成基线评估')
     expect(page.get_by_text('临床模式｜病例结果',exact=True)).to_be_visible()
     score_card=page.locator('[data-testid="stMetric"]').filter(has=page.get_by_text('得分',exact=True))
     expect(score_card.get_by_text('100/100',exact=True)).to_be_visible()
     page.screenshot(path=str(out/('competition_clinical_'+clinical_phase+'_complete.png')),full_page=True)
     status.setdefault('competition_flow_checks',[]).append({'check':'clinical_anonymous_phase_completed','phase':clinical_phase,'score':100,'status':'PASS'})
     if clinical_phase!='培训后考核':
      click_text('继续后续流程')
      expect(page.locator('.action-head')).to_be_visible(timeout=15000)
      expect(page.get_by_role('button',name='保存信息并进入训练系统',exact=True)).to_have_count(0)
      expect(page.get_by_label('科室细分（必填）',exact=True)).to_have_count(0)
      expect(page.locator('[data-testid="stException"]')).to_have_count(0)
     else:
      expect(page.get_by_role('button',name='继续后续流程',exact=True)).to_have_count(0)
    status['competition_flow_checks'].append({'check':'clinical_anonymous_baseline_training_posttest_terminal_route','status':'PASS'})
    page.locator('[data-testid="stMain"]').get_by_role('button',name='返回评审首页',exact=True).click()
    expect(page.get_by_role('button',name='进入学院教学体验',exact=True)).to_be_visible()
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    click_text('进入学院教学体验');click_text('开始本阶段')
    finish_academy('课前测评完成');assert_score('100/100');click_text('进入模拟训练')
    finish_academy();click_text('我已确认完成抢救');click_text('返回查看')
    expect(page.locator('.'+action_key('stop_infusion')).get_by_role('button')).to_be_disabled()
    click_text('我已确认完成抢救');click_text('确认结束')
    expect(page.get_by_text('模拟训练完成',exact=True)).to_be_visible();click_text('进入课后考核')
    finish_academy('课后考核结果与三阶段对比');assert_score('100/100')
    click_text('进入SUS及教学体验评价');click_text('提交评价')
    expect(page.get_by_text('全流程已完成',exact=True)).to_be_visible()
    page.screenshot(path=str(out/'competition_full_course_complete.png'),full_page=True)
    status.setdefault('competition_flow_checks',[]).append({'check':'anonymous_pretest_training_posttest_questionnaire_complete','status':'PASS'})
    click_text('重新体验');expect(page.get_by_role('button',name='开始本阶段',exact=True)).to_be_visible()
    status['competition_flow_checks'].append({'check':'restart_anonymous_course','status':'PASS'})
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
    def reset_case():
     before=read();page.get_by_role('button',name='重新开始审计病例',exact=True).click();changed(before)
     fresh=read();assert fresh['t']==0 and fresh['score']==0 and fresh['session_id']!=before['session_id'],fresh
     assert not fresh['flags'].get('order_violations',{}),fresh
    def select_case(case):
     if read()['case']!=case:
      page.get_by_label('审计病例组合',exact=True).click();page.get_by_role('option',name=case,exact=True).click();page.wait_for_function('(c)=>document.querySelector("#audit-state")&&JSON.parse(document.querySelector("#audit-state").textContent).case===c',arg=case)
    def advance():
     before=read();page.locator(f'.st-key-advance_time_{before["session_id"]}').get_by_role('button').click();changed(before)
     assert read()['t']==before['t']+30,(before,read())
    for case in CASES:
     if read()['case']!=case:
      page.get_by_label('审计病例组合',exact=True).click();page.get_by_role('option',name=case,exact=True).click();page.wait_for_function('(c)=>document.querySelector("#audit-state")&&JSON.parse(document.querySelector("#audit-state").textContent).case===c',arg=case)
     for aid in ACADEMY if case.startswith('academy') else CLINICAL:
      action(aid)
      if aid=='academy_reassess':
       before_repeat=read();action(aid);after_repeat=read()
       assert after_repeat['t']==before_repeat['t']+30 and after_repeat['score']==before_repeat['score'],(case,before_repeat,after_repeat)
       assert after_repeat['log_n']>before_repeat['log_n'] and after_repeat['valid']['academy_reassess']==before_repeat['valid']['academy_reassess']
       assert after_repeat['last_actions'][-1]['status']=='valid' and after_repeat['last_actions'][-1]['gained']==0
       status['workflow_defect_checks'].append({'check':'C04_repeat_reassessment','case':case,'status':'PASS'})
     final=read();assert final['end'][0] and final['score']==100,(case,final)
     status['case_results'].append({'case':case,'status':'PASS','t':final['t'],'score':final['score'],'end':final['end']});status['app_interaction_cases_executed']+=1
     page.screenshot(path=str(out/(case+'.png')),full_page=True)
     if case.startswith('academy') and case.endswith('_coach'):
      frozen=read();page.get_by_role('button',name='我已确认完成抢救',exact=True).click()
      expect(page.get_by_role('button',name='返回查看',exact=True)).to_be_visible()
      assert page.get_by_role('button',name='继续操作',exact=True).count()==0
      page.screenshot(path=str(out/(case+'_terminal_return_view.png')),full_page=True)
      page.get_by_role('button',name='返回查看',exact=True).click()
      expect(page.get_by_role('button',name='我已确认完成抢救',exact=True)).to_be_visible()
      for key in ('t','score','log_n','vitals','valid','end'):
       assert read()[key]==frozen[key],(case,key,read()[key],frozen[key])
      expect(page.locator(f'.st-key-advance_time_{frozen["session_id"]}').get_by_role('button')).to_be_disabled()
      for aid in ACADEMY if case.startswith('academy') else CLINICAL:
       expect(page.locator(f'.st-key-action_{frozen["session_id"]}_{aid}').get_by_role('button')).to_be_disabled()
      status['workflow_defect_checks'].append({'check':'C03_terminal_return_view','case':case,'status':'PASS'})
    # Defect-focused UI paths are distinct from the eight complete paths above.
    for case in CASES:
     select_case(case);reset_case()
     if case.startswith('clinical'):
      for omitted in ('abc_assess','shock_position'):
       for aid in CLINICAL:
        if aid!=omitted:action(aid)
       observed=read();assert observed['end'][1] not in ('success','standard_assessment_completed'),(case,omitted,observed)
       assert observed['critical_missing'],(case,omitted,observed)
       status['workflow_defect_checks'].append({'check':'C01_missing_'+omitted,'case':case,'status':'PASS'})
       reset_case()
      for aid in ('stop_infusion','call_help','high_flow_oxygen','continue_infusion'):action(aid)
      resumed=read();assert resumed['flags']['infusion_running'] is True and resumed['flags']['stopped_infusion'] is False,resumed
      for _ in range(4):advance()
      after_wait=read();assert after_wait['vitals']['SBP']<resumed['vitals']['SBP'],(resumed,after_wait)
      status['workflow_defect_checks'].append({'check':'C02_resume_no_freeze','case':case,'status':'PASS'})
      reset_case()
     else:
      # A real premature click, followed by a full corrective path.
      action('academy_reassess')
      for aid in ACADEMY:action(aid)
      recovered=read();assert recovered['end'][0] and recovered['score']<100,recovered
      reason=recovered['flags']['order_violations']['academy_reassess']['reason']
      assert any(reason in issue for issue in recovered['process_safety_issues']),recovered
      status['workflow_defect_checks'].append({'check':'C05_corrected_history_visible','case':case,'status':'PASS'})
      reset_case();action('stop_infusion')
      assert page.locator(f'.st-key-action_{read()["session_id"]}_continue_infusion').count()==0
      assert read()['flags']['infusion_running'] is False and read()['flags']['stopped_infusion'] is True
      status['workflow_defect_checks'].append({'check':'academy_continue_observation_isolation','case':case,'status':'PASS'})
    # An idle render and rapid action sequence must preserve all principal regions.
    before_reset=read();page.get_by_role('button',name='重新开始审计病例',exact=True).click();changed(before_reset)
    action('stop_infusion');action('call_help');before=read()
    for _ in range(6):
     old=read();page.locator(f'.st-key-advance_time_{old["session_id"]}').get_by_role('button').click();changed(old)
    after=read();assert after['vitals']!=before['vitals']
    time.sleep(3);expect(page.locator('.vital-grid')).to_be_visible(timeout=15000);expect(page.locator('.action-head')).to_be_visible(timeout=15000)
    page.screenshot(path=str(out/'continuous_actions_complete_page.png'),full_page=True)
    page.reload();read()
    # The markdown oracle can mount before the independently lazy-loaded st.html panel.
    # Require both actual rendered regions to become visible; state alone is not readiness.
    expect(page.locator('.vital-grid')).to_be_visible(timeout=15000)
    expect(page.locator('.action-head')).to_be_visible(timeout=15000)
    page.screenshot(path=str(out/'refresh_complete_page.png'),full_page=True)
    assert not console,console
    (out/'page_errors.json').write_text(json.dumps(console,ensure_ascii=False,indent=2))
    context.tracing.stop(path=str(out/'playwright_trace.zip'));context.close();browser.close()
    status['status']='PASS_SCOPED_BROWSER_INTEGRATION';status['reason']='Production entry auth/mode smoke + eight seeded workflows + C01-C05 defect checks and reset isolation. Added production learner-change/refresh and competition complete-course E2E; admin and clinical full registration remain outside scope.'
 except Exception as exc:
  status.update(status='FAIL',error=repr(exc),traceback=traceback.format_exc())
  try:
   # Fixture-only synthetic state and region counts; never collect login inputs/secrets.
   status['failure_region_counts']={selector:page.locator(selector).count() for selector in ('#audit-state','.vital-grid','.action-head')}
   if status['failure_region_counts']['#audit-state']==1:
    status['failure_observed_state']=json.loads(page.locator('#audit-state').inner_text(timeout=1000))
  except Exception:pass
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
