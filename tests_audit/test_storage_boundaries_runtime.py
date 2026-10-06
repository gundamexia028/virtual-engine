"""Real Streamlit AppTest storage-boundary regressions. No browser or live DB.
All participants are synthetic; filesystem writes use a temporary directory and
network connect is disabled. Cloud transport is explicitly mocked.
"""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = r"""
import streamlit as st, sys, json, copy, tempfile
from pathlib import Path
from unittest.mock import patch
import os
sys.path.insert(0,str(Path(os.environ['VE_STORAGE_AUDIT_ROOT']) / 'app'))
import streamlit_app as app
st.secrets={"AUTH_CONTEXT_SIGNING_KEY":"synthetic-audit-signing-key-long-enough"}
app.init_session()
results={}
# Production flow reset is an actual action helper, no UI doubles.
st.session_state.update(prior_experience_survey_completed=True,prior_anaphylaxis_training='OLD_PERSON_YES',participant_id='OLD_PERSON')
app.reset_for_mode_selection('clinical')
results['mode_reset']={'prior_completed':st.session_state.prior_experience_survey_completed,'prior_value':st.session_state.prior_anaphylaxis_training,'participant_id':st.session_state.participant_id,'needs_new_baseline_survey':app._needs_baseline_post_survey()}
st.session_state.update(system_mode='academy',participant_id='OLD_ACADEMY',prior_experience_survey_completed=True,prior_anaphylaxis_training='OLD_PERSON_YES',academy_post_evaluation_completed=True,sus_score=100)
app._reset_academy_flow_for_new_learner()
results['new_learner_reset']={'prior_completed':st.session_state.prior_experience_survey_completed,'prior_value':st.session_state.prior_anaphylaxis_training,'sus_score':st.session_state.sus_score,'evaluation_completed':st.session_state.academy_post_evaluation_completed}
# Build real report from real engine; persist only fabricated records.
app.reset_for_mode_selection('academy')
st.session_state.update(profile_completed=True,assessment_phase='课后考核',participant_id='SYNTHETIC',organization_id='TEST_ORG')
app.start_simulation(app.scenario_path_by_role('academy_variant'),'exam',17,'SYNTHETIC')
report=app.enrich_report(st.session_state.active_simulator.build_report(),end_reason='standard_assessment_completed')
app.ensure_report_completion_id(report)
app.save_result_record_local(report)
st.session_state.pending_post_evaluation_report=report
st.session_state.pending_post_evaluation_reason='standard_assessment_completed'
st.session_state.academy_post_evaluation_completed=False
ok,msg=app.submit_academy_post_evaluation([5,1]*5,[5]*len(app.TEACHING_EXPERIENCE_ITEMS))
ctx=app.create_platform_admin_context()
merged=app.load_full_reports_local(ctx)[0]
results['local_sus']={'ok':ok,'merged_sus':merged['session']['sus_score'],'base_report_sus':report['session']['sus_score']}
# Simulate external adapter response only, no network. Cloud row was written pre-questionnaire.
row=app.make_database_record(report)
with patch.object(app,'load_result_records_database',return_value=([app.normalize_database_record(row)],'synthetic')):
    loaded=app.load_result_records(ctx)
results['cloud_sus']={'loaded_sus':loaded[0].get('sus_score'),'local_completed_sus':merged['session']['sus_score']}
# Repeat submission must preserve first persisted answers.
ok2,msg2=app.submit_academy_post_evaluation([1,5]*5,[1]*len(app.TEACHING_EXPERIENCE_ITEMS))
qrecords,_=app._read_jsonl_unlocked(app._questionnaire_results_path())
results['sus_repeat']={'ok':ok2,'record_count':len(qrecords),'score':qrecords[0]['academy_post_evaluation']['sus']['score']}
# An interrupted trailing write must not swallow the next complete report.
paths=app.current_storage_adapter().write_paths()
with paths.full_reports.open('a') as f:f.write('{"interrupted":')
report2=copy.deepcopy(report);report2['session']['session_id']='SYNTHETIC_SECOND';report2['session']['completion_id']='b'*64
created=app.save_result_record_local(report2)
records,warnings=app._read_jsonl_unlocked(paths.full_reports)
results['interrupted_tail']={'reported_created':created,'full_count':len(records),'new_report_retrievable':any(x['session']['session_id']=='SYNTHETIC_SECOND' for x in records),'warning_count':len(warnings),'index_count':len(app._read_jsonl_unlocked(paths.results_index)[0])}
# Draft directory failure must be observed, not disguised as browser failure.
obstacle=Path(os.environ['PEDSIM_RESULTS_DIR']).parent/('storage-audit-obstacle-'+str(__import__('os').getpid()));obstacle.write_text('synthetic')
with patch.object(app,'DRAFTS_DIR',obstacle/'drafts'),patch.object(app,'_browser_binding_hash',return_value='synthetic-binding'):
    try: result=app.persist_active_training_draft();results['draft_mkdir_failure']={'return':result,'failure_flag':st.session_state.get('draft_save_failed',False)}
    except Exception as exc: results['draft_mkdir_failure']={'exception':type(exc).__name__}
# Missing questionnaire answers coerced to neutral scores by submission boundary.
st.session_state.update(questionnaire_submit_status='',academy_post_evaluation_completed=False,questionnaire_submission_id='',pending_post_evaluation_report=report2)
ok3,_=app.submit_academy_post_evaluation([],[])
results['empty_sus']={'accepted':ok3,'score':st.session_state.sus_score}
# Authority and competition storage boundaries, synthetic data only.
results['unauthorized']={'local':len(app.load_result_records_local(None)),'full':len(app.load_full_reports_local({})),'csv_bytes':len(app.records_to_csv_bytes([report],None)),'jsonl_bytes':len(app.records_to_jsonl_bytes([report],None))}
forged=dict(ctx,role='academy_admin')
results['tampered_context_valid']=app.validate_authorization_context(forged) is not None
with patch.object(app,'APP_MODE','competition'):
    cctx=app.create_competition_admin_context()
    altered=dict(cctx,permissions=['view','export','manage'])
    comp_paths=app.current_storage_adapter().write_paths()
    results['competition']={'production_ctx_valid':app.validate_authorization_context(ctx) is not None,'manage_allowed':app.authorization_allows(altered,'manage'),'different_write_dir':comp_paths.results_index.parent!=paths.results_index.parent,'read_dir_is_demo':app.current_storage_adapter().admin_read_paths().results_index.parent==app.DEMO_DATA_DIR,'db_read':app.load_result_rows_database(cctx)[0],'db_write_ok':app.save_result_record_database(report)[0]}
    app.setup_competition_participant('academy')
    results['anonymous_demo']={'profile_complete':st.session_state.profile_completed,'id_prefix':st.session_state.participant_id.startswith('COMP-ACAD-'),'initials':st.session_state.participant_initials,'collection_mode':st.session_state.collection_mode,'old_survey_cleared':not st.session_state.prior_experience_survey_completed,'stage_reports_empty':not st.session_state.academy_stage_reports}
# Actual local write plus mocked remote transport records repeat insert intent.
class FakeClient:
    def __init__(self): self.rows=[]
    def table(self,*args):return self
    def insert(self,record):self.rows.append(copy.deepcopy(record));return self
    def execute(self):return None
client=FakeClient()
with patch.object(app,'database_configured',return_value=True),patch.object(app,'get_supabase_client',return_value=client):
    app.save_result_record(report);app.save_result_record(report)
results['cloud_duplicate_intent']={'insert_calls':len(client.rows),'same_completion_id':client.rows[0]['completion_id']==client.rows[1]['completion_id']}

# Questionnaire storage fault keeps the pending work retryable.
app.reset_for_mode_selection('academy')
st.session_state.update(profile_completed=True,assessment_phase='课后考核',participant_id='SYNTHETIC_RETRY')
app.start_simulation(app.scenario_path_by_role('academy_variant'),'exam',22,'SYNTHETIC_RETRY')
r3=app.enrich_report(st.session_state.active_simulator.build_report(),end_reason='standard_assessment_completed')
app.ensure_report_completion_id(r3)
st.session_state.pending_post_evaluation_report=r3
with patch.object(app,'save_questionnaire_record_local',side_effect=OSError('synthetic disk failure')):
    failure_ok,_=app.submit_academy_post_evaluation([4]*10,[4]*len(app.TEACHING_EXPERIENCE_ITEMS))
failed_state={'returned_ok':failure_ok,'pending':st.session_state.pending_academy_post_evaluation,'completed':st.session_state.academy_post_evaluation_completed,'draft_sus':st.session_state.questionnaire_draft['sus']}
retry_ok,_=app.submit_academy_post_evaluation([4]*10,[4]*len(app.TEACHING_EXPERIENCE_ITEMS))
results['questionnaire_fault_retry']={'failed_state':failed_state,'retry_ok':retry_ok,'final_status':st.session_state.questionnaire_submit_status}
# Recovery uses the real snapshot serializer and local files; only HTTP binding is supplied.
with patch.object(app,'_browser_binding_hash',return_value='synthetic-browser-A'):
    saved=app.persist_active_training_draft(now=1000)
    did=st.session_state.draft_id
    sid=st.session_state.session_id
    snap=st.session_state.active_simulator.to_snapshot()
    st.session_state.clear();app.init_session();st.query_params[app.DRAFT_QUERY_KEY]=did
    restored=app.restore_training_draft_from_query(now=1001)
    results['draft_restore']={'failure_flag_cleared':not st.session_state.get('draft_save_failed',False),'saved':saved,'restored':restored,'same_session':st.session_state.session_id==sid,'same_snapshot':st.session_state.active_simulator.to_snapshot()==snap,'admin_unlocked':st.session_state.admin_unlocked,'sus_completed':st.session_state.academy_post_evaluation_completed}
with patch.object(app,'_browser_binding_hash',return_value='synthetic-browser-B'):
    st.session_state.clear();app.init_session();st.query_params[app.DRAFT_QUERY_KEY]=did
    results['different_binding_denied']=not app.restore_training_draft_from_query(now=1002)
with patch.object(app,'_browser_binding_hash',return_value='synthetic-browser-A'):
    st.session_state.clear();app.init_session();st.query_params[app.DRAFT_QUERY_KEY]=did
    results['expired_draft_denied']=not app.restore_training_draft_from_query(now=1000+app.DRAFT_TTL_SECONDS+1)


# Crash can also truncate UTF-8 midway, not merely JSON syntax.
utf8_bad=Path(os.environ['PEDSIM_RESULTS_DIR']).parent/('audit-bad-utf8-'+str(__import__('os').getpid())+'.jsonl')
utf8_bad.write_bytes(b'{"ok":1}\n'+bytes([0xe4]))
try:
    records,warnings=app._read_jsonl_unlocked(utf8_bad)
    results['truncated_utf8']={'records':len(records),'warnings':len(warnings)}
except Exception as exc:
    results['truncated_utf8']={'exception':type(exc).__name__}

# Malicious/mismatched local evaluation must never cross identity boundaries.
base=copy.deepcopy(report)
base['score']=71
local=copy.deepcopy(merged)
local['score']=999
mismatch_results={}
for field in ('completion_id','session_id','organization_type','organization_id','participant_id'):
    bad=copy.deepcopy(local)
    bad['session'][field]='different-'+field
    overlay=app._merge_local_evaluation(base,[bad]) if hasattr(app,'_merge_local_evaluation') else copy.deepcopy(base)
    mismatch_results[field]={'no_evaluation':'academy_post_evaluation' not in overlay,'score_unchanged':overlay['score']==71}
matched=app._merge_local_evaluation(base,[local]) if hasattr(app,'_merge_local_evaluation') else copy.deepcopy(base)
results['overlay_ownership']={'mismatches':mismatch_results,'matched_sus':matched['session']['sus_score'],'matched_score_unchanged':matched['score']==71,'source_not_mutated':'academy_post_evaluation' not in base}
# Strict validation: malformed answers cannot write a questionnaire.
invalid=[[],[3]*9,[3]*11,[0]*10,[6]*10,[True]*10,[3.0]*10,['3']*10,None,(3,)*10]
invalid_results=[]
for candidate in invalid:
    st.session_state.update(questionnaire_submit_status='',academy_post_evaluation_completed=False,pending_post_evaluation_report=copy.deepcopy(report2))
    before=len(app._read_jsonl_unlocked(app._questionnaire_results_path())[0])
    accepted,_=app.submit_academy_post_evaluation(candidate,[3]*len(app.TEACHING_EXPERIENCE_ITEMS))
    after=len(app._read_jsonl_unlocked(app._questionnaire_results_path())[0])
    invalid_results.append({'accepted':accepted,'unchanged_rows':before==after,'not_completed':not st.session_state.academy_post_evaluation_completed})
results['strict_invalid_answers']=invalid_results



# Preserve every original byte and keep valid new records after all tail types.
tails=[b'',b'{"old":1}',b'{"broken":',b'{"old":1}\n'+bytes([0xe4]),b'{"old":1}\n\n']
results['tail_matrix']=[]
for i,tail in enumerate(tails):
    path=Path(os.environ['PEDSIM_RESULTS_DIR']).parent / f'tail-{i}.jsonl'
    path.write_bytes(tail)
    app._append_jsonl_unlocked(path,{'new':2})
    try:
        found,warnings=app._read_jsonl_unlocked(path)
        results['tail_matrix'].append({'original_bytes_preserved':path.read_bytes().startswith(tail),'new_retrievable':{'new':2} in found})
    except Exception as exc:
        results['tail_matrix'].append({'exception':type(exc).__name__})

st.session_state.audit_storage_results=results
"""

@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Real Streamlit required')
class StorageBoundariesRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        root=Path(os.environ.get('VE_WORKFLOW_ROOT', Path(__file__).resolve().parents[1])).resolve()
        cls.tmp=tempfile.TemporaryDirectory(prefix='audit-storage-boundaries-')
        old_cwd=os.getcwd(); old_secrets=st.secrets
        env={'APP_MODE':'production','VE_STORAGE_AUDIT_ROOT':str(root),
             'PEDSIM_RESULTS_DIR':cls.tmp.name+'/runs','PEDSIM_DRAFTS_DIR':cls.tmp.name+'/drafts',
             'PEDSIM_COMPETITION_RESULTS_DIR':cls.tmp.name+'/competition',
             'SUPABASE_URL':'','SUPABASE_KEY':'','SUPABASE_ANON_KEY':'','SUPABASE_SERVICE_ROLE_KEY':''}
        def blocked(*args,**kwargs): raise AssertionError('Network forbidden by isolated storage audit')
        old_module=sys.modules.pop('streamlit_app',None)
        try:
            os.chdir(cls.tmp.name)
            with patch.dict(os.environ,env),patch.object(socket.socket,'connect',blocked),patch.object(socket,'create_connection',blocked):
                at=AppTest.from_string(SCRIPT,default_timeout=30).run()
            if len(at.exception): raise AssertionError(str(at.exception))
            cls.r=at.session_state.audit_storage_results
        finally:
            os.chdir(old_cwd); st.secrets=old_secrets
            sys.modules.pop('streamlit_app',None)
            if old_module is not None: sys.modules['streamlit_app']=old_module
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_new_identity_clears_background_and_evaluation(self):
        self.assertFalse(self.r['mode_reset']['prior_completed'])
        self.assertEqual(self.r['mode_reset']['prior_value'],'')
        self.assertTrue(self.r['mode_reset']['needs_new_baseline_survey'])
        self.assertFalse(self.r['new_learner_reset']['evaluation_completed'])
        self.assertEqual(self.r['new_learner_reset']['sus_score'],'')

    def test_interrupted_jsonl_cannot_swallow_next_record(self):
        self.assertTrue(self.r['interrupted_tail']['new_report_retrievable'])
        self.assertEqual(self.r['interrupted_tail']['full_count'],2)
        self.assertEqual(self.r['interrupted_tail']['index_count'],2)

    def test_invalid_utf8_retains_prior_good_records(self):
        self.assertEqual(self.r['truncated_utf8'],{'records':1,'warnings':1})

    def test_cloud_sus_overlay_matches_local_completed_evaluation(self):
        self.assertEqual(self.r['cloud_sus']['loaded_sus'],100)
        self.assertEqual(self.r['local_sus']['merged_sus'],100)

    def test_overlay_rejects_identity_mismatch_and_preserves_score(self):
        for field,result in self.r['overlay_ownership']['mismatches'].items():
            with self.subTest(field=field): self.assertTrue(all(result.values()))
        self.assertTrue(self.r['overlay_ownership']['matched_score_unchanged'])
        self.assertTrue(self.r['overlay_ownership']['source_not_mutated'])
        self.assertEqual(self.r['overlay_ownership']['matched_sus'],100)

    def test_draft_directory_failure_returns_false(self):
        self.assertFalse(self.r['draft_mkdir_failure'].get('return',True))
        self.assertTrue(self.r['draft_mkdir_failure'].get('failure_flag'))
        self.assertTrue(self.r['draft_restore']['failure_flag_cleared'])

    def test_invalid_answers_do_not_write_or_mark_completed(self):
        self.assertFalse(self.r['empty_sus']['accepted'])
        for result in self.r['strict_invalid_answers']:
            self.assertFalse(result['accepted'])
            self.assertTrue(result['unchanged_rows'])
            self.assertTrue(result['not_completed'])

    def test_questionnaire_retries_are_idempotent(self):
        self.assertEqual(self.r['sus_repeat']['record_count'],1)
        self.assertEqual(self.r['sus_repeat']['score'],100)
        failure=self.r['questionnaire_fault_retry']['failed_state']
        self.assertFalse(failure['returned_ok']);self.assertTrue(failure['pending']);self.assertFalse(failure['completed'])
        self.assertEqual(failure['draft_sus'],[4]*10)
        self.assertTrue(self.r['questionnaire_fault_retry']['retry_ok'])

    def test_competition_readonly_and_unauthorized_boundaries(self):
        self.assertFalse(self.r['tampered_context_valid'])
        self.assertEqual(self.r['unauthorized'],{'local':0,'full':0,'csv_bytes':3,'jsonl_bytes':0})
        c=self.r['competition']
        self.assertFalse(c['production_ctx_valid']);self.assertFalse(c['manage_allowed'])
        self.assertTrue(c['different_write_dir']);self.assertTrue(c['read_dir_is_demo'])
        self.assertFalse(c['db_write_ok']);self.assertEqual(c['db_read'],[])
        self.assertTrue(self.r['anonymous_demo']['old_survey_cleared'])
        self.assertTrue(self.r['anonymous_demo']['stage_reports_empty'])

    def test_all_jsonl_tail_variants_preserve_original_and_new_records(self):
        for result in self.r['tail_matrix']:
            self.assertEqual(result,{'original_bytes_preserved':True,'new_retrievable':True})

    def test_snapshot_recovery_preserves_state_without_admin(self):
        r=self.r['draft_restore']
        for key in ('saved','restored','same_session','same_snapshot','sus_completed'):self.assertTrue(r[key])
        self.assertFalse(r['admin_unlocked'])
        self.assertTrue(self.r['different_binding_denied']);self.assertTrue(self.r['expired_draft_denied'])

if __name__=='__main__': unittest.main()
