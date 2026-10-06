"""Actual application entry, competition credentials and buttons; no fixture.
Synthetic temporary persistence only. AppTest is not browser evidence.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(os.environ.get('VE_WORKFLOW_ROOT', Path(__file__).resolve().parents[1])).resolve()

class CompetitionEntryRuntimeTests(unittest.TestCase):
    def test_actual_competition_clinical_and_academy_entry(self):
        with tempfile.TemporaryDirectory(prefix='competition-entry-') as tmp:
            env = {'APP_MODE': 'competition', 'PEDSIM_RESULTS_DIR': tmp+'/production',
                   'PEDSIM_COMPETITION_RESULTS_DIR': tmp+'/demo', 'PEDSIM_DRAFTS_DIR': tmp+'/drafts',
                   'SUPABASE_URL': '', 'SUPABASE_KEY': '', 'SUPABASE_ANON_KEY': '', 'SUPABASE_SERVICE_ROLE_KEY': ''}
            with patch.dict(os.environ, env):
                for mode, label in [('clinical','进入临床模式演示'),('academy','进入学院教学体验')]:
                    with self.subTest(mode=mode):
                        at = AppTest.from_file(str(ROOT/'app/streamlit_app.py'), default_timeout=20)
                        at.secrets.update({'APP_MODE':'competition', 'COMPETITION_REVIEW_CODE':'SYNTHETIC_REVIEW_ONLY',
                            'COMPETITION_ADMIN_CODE':'SYNTHETIC_ADMIN_ONLY',
                            'AUTH_CONTEXT_SIGNING_KEY':'synthetic-signing-key-long-enough-for-isolated-runtime'})
                        at.run()
                        self.assertFalse(at.exception)
                        def click(text):
                            buttons = [b for b in at.button if b.label == text]
                            self.assertEqual(len(buttons), 1, [b.label for b in at.button])
                            buttons[0].click().run()
                            self.assertFalse(at.exception, str(at.exception))
                        at.text_input[0].set_value('SYNTHETIC_REVIEW_ONLY')
                        click('进入评审体验'); click(label); click('开始本阶段')
                        sim = at.session_state.active_simulator
                        self.assertEqual(type(sim).__module__, 'peds_anaphylaxis_sim.engine')
                        self.assertTrue(callable(getattr(sim, 'display_score', None)))
                        self.assertEqual(sim.display_score(), 0)
                        self.assertEqual(at.session_state.system_mode, mode)
                        self.assertTrue(at.session_state.participant_id.startswith('COMP-'))
                        sid = at.session_state.session_id
                        at.button(key=f'action_{sid}_stop_infusion').click().run()
                        self.assertFalse(at.exception)
                        self.assertTrue(at.session_state.active_simulator.state.flags['stopped_infusion'])
                        snapshot = at.session_state.active_simulator.to_snapshot()
                        at.run()  # ordinary rerender must preserve same session and score
                        self.assertFalse(at.exception)
                        self.assertEqual(sid, at.session_state.session_id)
                        self.assertEqual(snapshot, at.session_state.active_simulator.to_snapshot())
                self.assertFalse(Path(tmp+'/production/training_results.jsonl').exists())

    def test_old_release_draft_is_rejected_without_deleting_bytes(self):
        code = r"""
import streamlit as st, tempfile, json, hashlib
from pathlib import Path
from unittest.mock import patch
import streamlit_app as app
app.init_session()
with tempfile.TemporaryDirectory(prefix='draft-version-boundary-') as tmp:
 with patch.object(app, 'DRAFTS_DIR', Path(tmp)), patch.object(app, '_browser_binding_hash', return_value='synthetic-same-browser'):
  app.reset_for_mode_selection('clinical')
  st.session_state.update(profile_completed=True, participant_id='SYNTHETIC_VERSION')
  app.start_simulation(app.scenario_path_by_role('initial'), 'exam', 12, 'SYNTHETIC_VERSION')
  assert app.persist_active_training_draft(now=1000)
  did=st.session_state.draft_id
  path=app._draft_path(did)
  original=json.loads(path.read_text())
  for field in ('app_version','engine_revision'):
   envelope=json.loads(json.dumps(original))
   if field=='app_version': envelope['payload']['app_version']='V1.3.9-audit.2'
   else: envelope['payload']['simulator']['engine_revision']='1.3.9-audit.2'
   envelope['checksum']=hashlib.sha256(app._canonical_json(envelope['payload']).encode()).hexdigest()
   path.write_text(json.dumps(envelope))
   before=path.read_bytes()
   st.session_state.clear();app.init_session();st.query_params[app.DRAFT_QUERY_KEY]=did
   assert not app.restore_training_draft_from_query(now=1001)
   assert path.read_bytes()==before
   assert st.session_state.active_simulator is None
st.session_state.checked_old_release_drafts=True
"""
        import sys
        with patch.object(sys, 'path', [str(ROOT/'app'), *sys.path]):
            at=AppTest.from_string(code, default_timeout=20).run()
        self.assertFalse(at.exception, str(at.exception))
        self.assertTrue(at.session_state.checked_old_release_drafts)

    def test_snapshot_engine_revision_matches_package_and_rejects_old(self):
        from peds_anaphylaxis_sim import __version__
        from peds_anaphylaxis_sim.integrity import ENGINE_REVISION
        from test_integrity import make
        self.assertEqual(ENGINE_REVISION, __version__)
        sim = make('initial', 'exam')
        snap = sim.to_snapshot()
        self.assertEqual(type(sim).from_snapshot(snap).to_snapshot(), snap)
        snap['engine_revision'] = '1.3.9-audit.2'
        with self.assertRaises(ValueError): type(sim).from_snapshot(snap)

if __name__ == '__main__': unittest.main(verbosity=2)
