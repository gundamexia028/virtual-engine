"""Real Streamlit AppTest control visibility/cancellation; not browser proof."""
import copy, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
ROOT=Path(os.environ.get('VE_WORKFLOW_ROOT',Path(__file__).resolve().parents[1])).resolve()
class UiControlTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='ui-controls-')
  cls.env=patch.dict(os.environ,dict(APP_MODE='production',VE_AUDIT_BROWSER_FIXTURE='1',PEDSIM_RESULTS_DIR=cls.tmp.name+'/runs',PEDSIM_DRAFTS_DIR=cls.tmp.name+'/drafts',SUPABASE_URL='',SUPABASE_KEY='',SUPABASE_ANON_KEY='',SUPABASE_SERVICE_ROLE_KEY=''));cls.env.start()
 @classmethod
 def tearDownClass(cls):cls.env.stop();cls.tmp.cleanup()
 def start(self,case):
  at=AppTest.from_file(str(ROOT/'tests_audit/browser_fixture_app.py'),default_timeout=20).run();at.selectbox[0].select(case).run();self.assertFalse(at.exception);return at
 def action(self,at,aid):
  at.button(key=f'action_{at.session_state.session_id}_{aid}').click().run();self.assertFalse(at.exception)
 def visible(self,at,aid):return any(b.key==f'action_{at.session_state.session_id}_{aid}' for b in at.button)
 def test_clinical_pending_input_cancel_reopen_matrix(self):
  for role in ('initial','variant'):
   for mode in ('coach','exam'):
    for aid,kind in [('im_epinephrine','epinephrine'),('fluid_bolus','fluid'),('steroid','steroid')]:
     with self.subTest(role=role,mode=mode,aid=aid):
      at=self.start(f'clinical_{role}_{mode}');sid=at.session_state.session_id
      before=copy.deepcopy(at.session_state.active_simulator.to_snapshot())
      self.action(at,aid)
      controls=[b for b in at.button if b.key and (b.key.startswith(f'action_{sid}_') or b.key==f'advance_time_{sid}')]
      self.assertTrue(controls);self.assertTrue(all(b.disabled for b in controls))
      at.number_input[0].set_value(1.0).run();at.button(key=f'cancel_{kind}_{sid}').click().run()
      self.assertEqual(before,at.session_state.active_simulator.to_snapshot());self.assertFalse(at.number_input)
      self.assertFalse(at.button(key=f'advance_time_{sid}').disabled)
      self.action(at,aid);self.assertEqual(before,at.session_state.active_simulator.to_snapshot())
      at.button(key=f'cancel_{kind}_{sid}').click().run();self.action(at,'call_help')
      first=at.session_state.active_simulator.state.t;self.action(at,'call_help')
      self.assertEqual(first,at.session_state.active_simulator.state.t)
 def test_academy_conditional_actions_follow_state(self):
  for role in ('initial','variant'):
   for mode in ('coach','exam'):
    with self.subTest(role=role,mode=mode):
     at=self.start(f'academy_{role}_{mode}')
     self.assertTrue(self.visible(at,'continue_infusion'));self.assertTrue(self.visible(at,'ask_family_first'))
     self.assertFalse(self.visible(at,'academy_restore_iv'))
     self.action(at,'stop_infusion')
     self.assertFalse(self.visible(at,'continue_infusion'));self.assertFalse(self.visible(at,'ask_family_first'))
     self.action(at,'call_help');self.assertFalse(self.visible(at,'send_family_for_help'))
     self.action(at,'remove_iv');self.assertTrue(self.visible(at,'academy_restore_iv'))
     self.action(at,'academy_restore_iv');self.assertFalse(self.visible(at,'academy_restore_iv'))
     self.action(at,'prepare_rescue_equipment');self.assertFalse(self.visible(at,'prepare_steroid_antihistamine_only'))
if __name__=='__main__':unittest.main(verbosity=2)
