"""CSS scope contracts, not a substitute for real pointer/browser acceptance."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ActionHelpPointerScopeTests(unittest.TestCase):
 def test_readonly_action_help_rule_retains_trigger_role_and_interactive_exclusions(self):
  source=(ROOT/'app/streamlit_app.py').read_text()
  selector='body:has([class*="st-key-action_"] [data-testid="stTooltipHoverTarget"][aria-describedby]) [data-overlay-container="true"] [role="tooltip"] [data-testid="stTooltipContent"]:not(:has(a, button, input, select, textarea, [role="button"], [contenteditable="true"], [tabindex]:not([tabindex="-1"])))'
  self.assertEqual(source.count(selector),2)
  self.assertIn(selector+' * {\n            pointer-events: none !important;',source)
  self.assertNotRegex(source,r'\[data-overlay-container[^\]]*\]\s*\{[^}]*pointer-events\s*:\s*none')
 def test_help_and_widget_click_contracts_are_unchanged(self):
  source=(ROOT/'app/streamlit_app.py').read_text()
  self.assertIn('help=str(action.get("label", ""))',source)
  self.assertIn('button_text = full_label',source)
  self.assertIn('on_click=_dispatch_ui_command',source)
  self.assertNotIn('force=True',source)
  self.assertNotIn('force: true',source)
 def test_only_explicitly_exiting_readonly_tooltip_content_is_hidden(self):
  source=(ROOT/'app/streamlit_app.py').read_text()
  selector='[data-overlay-container="true"] [role="tooltip"][data-exiting="true"] > [data-testid="stTooltipContent"]:not(:has(a, button, input, select, textarea, [role="button"], [contenteditable="true"], [tabindex]:not([tabindex="-1"])))'
  self.assertEqual(source.count(selector),2)
  self.assertIn(selector+' * {\n            visibility: hidden !important;\n            pointer-events: none !important;',source)
  block=source[source.index('/* Hide only text help'):source.index('[data-testid="stSidebar"] .stButton > button')]
  self.assertNotIn('display: none',block)
  self.assertNotIn('body:has',block)
  self.assertNotIn('aria-hidden',block)
if __name__=='__main__':unittest.main(verbosity=2)
