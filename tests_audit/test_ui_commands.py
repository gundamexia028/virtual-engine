"""Real command-controller tests. These are NOT browser/Streamlit runtime tests."""
import ast
from pathlib import Path
import unittest
from test_integrity import make, ROLES
from ui_commands import execute_command, revision, pending_input

class UICommandTests(unittest.TestCase):
    def state(self,role='initial'):
        return {'active_simulator':make(role),'session_id':'offline-1','ended':False}
    def call(self,state,cmd,aid='',value=None):
        return execute_command(state,state['session_id'],revision(state['active_simulator']),cmd,aid,value)
    def test_stale_revision_drops_duplicate_time(self):
        state=self.state();s=state['active_simulator'];old=revision(s)
        self.assertTrue(execute_command(state,'offline-1',old,'action','stop_infusion')['accepted'])
        before=s.to_snapshot()
        self.assertEqual(execute_command(state,'offline-1',old,'action','call_help')['status'],'stale_event')
        self.assertEqual(before,s.to_snapshot())
    def test_previous_session_cannot_affect_new_mode(self):
        state=self.state('academy_initial');s=state['active_simulator'];old=revision(s)
        state['active_simulator']=make('variant');state['session_id']='offline-2';before=state['active_simulator'].to_snapshot()
        r=execute_command(state,'offline-1',old,'action','stop_infusion')
        self.assertEqual(r['status'],'stale_event');self.assertEqual(before,state['active_simulator'].to_snapshot())
    def test_invalid_dose_keeps_panel_and_accepts_correct_retry(self):
        state=self.state();s=state['active_simulator'];self.call(state,'action','stop_infusion')
        self.call(state,'action','im_epinephrine');self.assertTrue(pending_input(state));before=s.to_snapshot()
        r=self.call(state,'epinephrine','im_epinephrine',float('nan'))
        self.assertEqual(r['status'],'invalid_input');self.assertEqual(before,s.to_snapshot());self.assertTrue(pending_input(state))
        r=self.call(state,'epinephrine','im_epinephrine',.01*s.state.weight_kg)
        self.assertTrue(r['accepted']);self.assertFalse(pending_input(state));self.assertTrue(s.state.flags['epi_im_given'])
    def test_pending_input_blocks_time_and_actions(self):
        for aid in ('im_epinephrine','fluid_bolus','steroid'):
            state=self.state();s=state['active_simulator'];self.call(state,'action',aid);before=s.to_snapshot()
            self.assertEqual(self.call(state,'advance_time')['status'],'input_pending')
            self.assertEqual(self.call(state,'action','call_help')['status'],'input_pending')
            self.assertEqual(before,s.to_snapshot());self.call(state,'cancel');self.assertFalse(pending_input(state))
            self.assertEqual(before,s.to_snapshot())
    def test_completed_action_does_not_tick_again(self):
        state=self.state();self.call(state,'action','shock_position');s=state['active_simulator'];v=dict(s.state.vitals);t=s.state.t
        r=self.call(state,'action','shock_position');self.assertFalse(r['accepted']);self.assertEqual(t,s.state.t);self.assertEqual(v,s.state.vitals)
    def test_terminal_command_immutable(self):
        state=self.state();s=state['active_simulator'];s.apply_epinephrine_dose(1);before=s.to_snapshot()
        for command in ('advance_time','action','epinephrine'):
            self.assertFalse(self.call(state,command,'stop_infusion')['accepted'])
        self.assertEqual(before,s.to_snapshot())
    def test_academy_three_states_through_real_controller(self):
        state=self.state('academy_initial');s=state['active_simulator']
        for aid in ('stop_infusion','call_help','prepare_rescue_equipment'):self.call(state,'action',aid)
        self.assertFalse(s.state.flags['academy_medication_checked']);self.assertFalse(s.state.flags['epi_im_given'])
        self.call(state,'action','academy_medication_check');self.assertFalse(s.state.flags['epi_im_given'])
        self.call(state,'action','academy_assisted_medication');self.assertTrue(s.state.flags['epi_im_given'])
    def test_net_score_same_as_report(self):
        s=make('academy_initial');s.apply_action('allergy_identification');s.apply_action('remove_iv')
        self.assertEqual(s.display_score(),s.build_report()['score']);self.assertLess(s.display_score(),s.score)
    def test_no_timer_fragment_and_callbacks_are_wired(self):
        path=Path(__file__).resolve().parents[1]/'app/streamlit_app.py';text=path.read_text();tree=ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for dec in node.decorator_list:self.assertNotIn('run_every',ast.unparse(dec))
        self.assertIn('on_click=_dispatch_ui_command',text)
        self.assertNotIn('key=f"action_{aid}_{sim.state.t}',text)
        helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='live_display_vitals')
        self.assertIn('return visible_vitals(sim)',ast.unparse(helper))
    def test_confirmation_requires_current_panel(self):
        state=self.state();s=state['active_simulator'];before=s.to_snapshot()
        self.assertEqual(self.call(state,'epinephrine','im_epinephrine',.1)['status'],'stale_event')
        self.assertEqual(before,s.to_snapshot())

if __name__=='__main__':unittest.main(verbosity=2)
