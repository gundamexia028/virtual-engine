"""Real engine paths through the unchanged extracted presentation functions.

VE_WORKFLOW_ROOT selects a source tree in a fresh Python process. This tests
production history-row construction, not browser pixels or Streamlit lifecycle.
Clinical event paths use registered cases without state injection. The unknown
code case is explicitly diagnostic. No source files or real data are mutated.
"""
from __future__ import annotations
import ast
import copy
import itertools
import os
import re
from pathlib import Path
import sys
import unittest

ROOT = Path(os.environ.get('VE_WORKFLOW_ROOT', Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / 'app'))
from peds_anaphylaxis_sim.engine import Simulator
from peds_anaphylaxis_sim.scenario_loader import load_scenario_by_role
from peds_anaphylaxis_sim.flow_strategies import SimulationFlowStrategy, flow_strategy_for_scenario
from peds_anaphylaxis_sim.time_format import format_elapsed_time
from ui_labels import academy_action_short_label

# Execute actual function bodies unchanged without starting app I/O. All called
# label/flow helpers are actual production implementations, not test doubles.
_source = ROOT / 'app/streamlit_app.py'
_tree = ast.parse(_source.read_text())
_names = {'current_flow_strategy', 'display_action_label', 'action_label_map', 'get_action_history_rows', '_result_feedback_text', '_issue_text', '_missing_text', '_result_completion_notice', '_coach_prompt_for_display'}
_dicts = {'ACTION_LABELS_CN', '_HISTORY_RESULT_LABELS_CN', '_HISTORY_EVENT_LABELS_CN', '_RESULT_ACTION_LABELS_CN', 'RESULT_END_REASON_LABELS'}
_nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
for _node in _tree.body:
    if isinstance(_node, ast.FunctionDef) and _node.name in _names:
        _nodes.append(_node)
    elif isinstance(_node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in _dicts for t in _node.targets):
        _nodes.append(_node)
_namespace = dict(re=re, Simulator=Simulator, SimulationFlowStrategy=SimulationFlowStrategy,
                  flow_strategy_for_scenario=flow_strategy_for_scenario,
                  format_elapsed_time=format_elapsed_time,
                  academy_action_short_label=academy_action_short_label)
exec(compile(ast.fix_missing_locations(ast.Module(body=_nodes, type_ignores=[])), str(_source), 'exec'), _namespace)
history_rows = _namespace['get_action_history_rows']

PATHS = {
    'fluid_valid': ('valid', 'valid_volume', '补液量在本例范围内'),
    'fluid_no_iv': ('invalid', 'no_iv_access', '静脉通路不可用'),
    'fluid_before': ('timing_error', 'used_before_first_line_epinephrine', '未先完成有效肌注肾上腺素'),
    'fluid_under': ('under', 'insufficient_volume', '补液量不足'),
    'fluid_over': ('over', 'excessive_volume', '补液量超过本例范围'),
    'repeat_soon': ('too_soon', None, '得分 +0'),
    'repeat_premature': ('not_indicated', 'premature', '再次给药前置步骤尚未完成'),
    'repeat_unneeded': ('not_indicated', 'not_indicated', '当前暂不需要再次肌注'),
    'repeat_valid': ('valid', 'effective', '剂量已确认有效'),
    'repeat_under': ('underdose', 'ineffective', '剂量不足，本次未计为有效'),
    'repeat_high': ('dose_high', 'dose_high_effect_recorded', '剂量偏高，已记录模拟药物作用'),
    'repeat_over': ('overdose', 'serious_medication_error', '严重用药安全事件'),
}
TITLES = {
    'fluid_before': '有效肌注肾上腺素前的补液操作',
    'repeat_soon': '再次肌注间隔不足',
    'repeat_under': '再次肌注肾上腺素剂量不足',
    'repeat_high': '再次肌注肾上腺素剂量偏高',
    'repeat_over': '再次肌注肾上腺素过量',
}

def make_event(role, mode, key):
    sim = Simulator(load_scenario_by_role(role), mode=mode, seed=17)
    dose = round(min(.01 * sim.state.weight_kg, .3), 3)
    volume = sim.state.weight_kg * 10
    sim.apply_action('stop_infusion')
    if key.startswith('repeat_') and key not in ('repeat_soon', 'repeat_premature'):
        sim.apply_epinephrine_dose(dose)
        sim.apply_fluid_bolus_volume(volume)
        sim.tick()
        sim.apply_action('reassess_first')
        while sim.state.t < 300 and not sim.is_done()[0]:
            sim.tick()
        if key != 'repeat_unneeded':
            sim.apply_action('continue_infusion')
            sim.tick()
        result = sim.apply_epinephrine_dose(
            {'repeat_under': 0, 'repeat_high': dose + .06, 'repeat_over': .31}.get(key, dose),
            action_id='repeat_epinephrine')
    elif key == 'repeat_premature':
        result = sim.apply_epinephrine_dose(dose, action_id='repeat_epinephrine')
    elif key == 'repeat_soon':
        sim.apply_epinephrine_dose(dose)
        result = sim.apply_epinephrine_dose(dose, action_id='repeat_epinephrine')
    else:
        if key != 'fluid_before':
            sim.apply_epinephrine_dose(dose)
        if key == 'fluid_no_iv':
            sim.apply_action('remove_iv')
        result = sim.apply_fluid_bolus_volume(
            {'fluid_under': 0, 'fluid_over': min(sim.state.weight_kg * 20, 500) + 1}.get(key, volume))
    return sim, result

class HistoryFeedbackLabelsTests(unittest.TestCase):
    def test_coach_all_natural_result_enums_and_five_titles_are_chinese(self):
        for role, key in itertools.product(('initial', 'variant'), PATHS):
            with self.subTest(role=role, path=key):
                sim, result = make_event(role, 'coach', key)
                status, raw, expected = PATHS[key]
                self.assertEqual(result['status'], status)
                self.assertEqual(sim.log[-1].data.get('result'), raw)
                row = history_rows(sim)[-1]
                self.assertIn(expected, row['结果'])
                self.assertTrue(any('\u4e00' <= c <= '\u9fff' for c in row['操作']))
                if key in TITLES:
                    self.assertEqual(row['操作'], TITLES[key])
                if raw:
                    self.assertNotIn(raw, row['结果'])
                if key in ('fluid_valid', 'fluid_no_iv', 'fluid_under', 'fluid_over'):
                    self.assertTrue(row['结果'].endswith(f"{sim.log[-1].data['volume_ml']} ml"))

    def test_exam_retains_chinese_titles_without_showing_results(self):
        for role, key in itertools.product(('initial', 'variant'), PATHS):
            with self.subTest(role=role, path=key):
                sim, result = make_event(role, 'exam', key)
                self.assertEqual(result['status'], PATHS[key][0])
                rows = history_rows(sim)
                self.assertTrue(all(row['结果'] == '' for row in rows))
                self.assertTrue(any('\u4e00' <= c <= '\u9fff' for c in rows[-1]['操作']))
                if key in TITLES:
                    self.assertEqual(rows[-1]['操作'], TITLES[key])

    def test_history_render_preserves_snapshot_report_log_scores_and_raw_doses(self):
        for role, mode, key in itertools.product(('initial', 'variant'), ('coach', 'exam'), PATHS):
            with self.subTest(role=role, mode=mode, path=key):
                sim, _ = make_event(role, mode, key)
                before = (sim.to_snapshot(), sim.build_report(), copy.deepcopy(sim.log), sim.score, sim.penalties)
                history_rows(sim)
                history_rows(sim)
                after = (sim.to_snapshot(), sim.build_report(), sim.log, sim.score, sim.penalties)
                self.assertEqual(before, after)
                self.assertEqual(sim.log[-1].data.get('result'), PATHS[key][1])

    def test_unknown_diagnostic_codes_fall_back_without_mutating_log(self):
        for mode in ('coach', 'exam'):
            sim = Simulator(load_scenario_by_role('initial'), mode=mode, seed=17)
            sim._log('action', 'unknown_diagnostic_event', {'result': 'unknown_diagnostic_result'})
            before = sim.to_snapshot()
            row = history_rows(sim)[-1]
            self.assertEqual(row['操作'], 'unknown_diagnostic_event')
            self.assertEqual(row['结果'], 'unknown_diagnostic_result' if mode == 'coach' else '')
            self.assertEqual(sim.to_snapshot(), before)
        # Explicit malformed/legacy diagnostic data, not natural clinical cases.
        # Existing fluid-row formatting preserved these falsy values verbatim.
        for mode, raw in itertools.product(('coach', 'exam'), (None, 0, False)):
            with self.subTest(mode=mode, diagnostic_fluid_result=raw):
                sim = Simulator(load_scenario_by_role('initial'), mode=mode, seed=17)
                sim._log('action', 'fluid_bolus_volume_verified',
                         {'result': raw, 'volume_ml': 140.0})
                before = (sim.to_snapshot(), sim.build_report(), copy.deepcopy(sim.log))
                row = history_rows(sim)[-1]
                self.assertEqual(row['操作'], '快速补液容量确认')
                self.assertEqual(row['结果'], f'{raw}｜140.0 ml' if mode == 'coach' else '')
                self.assertEqual((sim.to_snapshot(), sim.build_report(), sim.log), before)
                self.assertIs(sim.log[-1].data['result'], raw)

class ResultFeedbackLabelsTests(unittest.TestCase):
    def test_all_37_registered_actions_have_display_labels(self):
        labels = _namespace['_RESULT_ACTION_LABELS_CN']
        translate = _namespace['_result_feedback_text']
        actions = set()
        for role in ('initial', 'variant', 'academy_initial', 'academy_variant'):
            actions.update(a['id'] for a in load_scenario_by_role(role)['actions'])
        self.assertEqual(len(actions), 37)
        self.assertFalse(actions - set(labels))
        for aid in actions:
            with self.subTest(action_id=aid):
                self.assertEqual(translate(aid), labels[aid])
                self.assertNotEqual(translate(aid), aid)
                self.assertEqual(translate(aid + ':原始中文说明'), '原始中文说明')
                self.assertEqual(translate(aid + ':'), labels[aid])

    def test_real_report_missing_safety_manual_feedback_preserves_raw_and_exports(self):
        translate = _namespace['_result_feedback_text']
        for role, mode in itertools.product(('initial', 'variant', 'academy_initial', 'academy_variant'), ('coach', 'exam')):
            with self.subTest(role=role, mode=mode):
                sim = Simulator(load_scenario_by_role(role), mode=mode, seed=17)
                sim.apply_action('remove_iv')
                sim.apply_action('academy_sbar_handoff' if role.startswith('academy') else 'reassess_first')
                sim.mark_manual_rescue_completion()
                report = sim.build_report()
                before = (sim.to_snapshot(), copy.deepcopy(report), copy.deepcopy(sim.log))
                raw_issues = _namespace['_issue_text'](report)
                raw_missing = _namespace['_missing_text'](report)
                fields = [report['critical_missing'], report['process_safety_issues'],
                          report['clinical_pathway_flags']['unfinished_required_steps']]
                self.assertTrue(all(fields))
                for values in fields:
                    shown = [translate(item) for item in values]
                    self.assertEqual(len(shown), len(values))
                    for text in shown:
                        tokens = set(re.findall(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*(?![A-Za-z0-9_])', text))
                        self.assertFalse(tokens & set(_namespace['_RESULT_ACTION_LABELS_CN']))
                self.assertEqual((sim.to_snapshot(), report, sim.log), before)
                self.assertEqual(_namespace['_issue_text'](report), raw_issues)
                self.assertEqual(_namespace['_missing_text'](report), raw_missing)
                self.assertEqual(raw_missing, '；'.join(report['critical_missing']))

    def test_97_point_manual_finish_missing_abc_displays_abc_assessment(self):
        path = ['stop_infusion', 'call_help', 'high_flow_oxygen', 'shock_position',
                'connect_monitor', 'check_bp', 'im_epinephrine', 'fluid_bolus',
                'reassess_first', 'bronchodilator', 'steroid', 'reassess_second',
                'family_explain', 'sbar_handoff']
        for mode in ('coach', 'exam'):
            sim = Simulator(load_scenario_by_role('initial'), mode=mode, seed=17)
            for aid in path:
                if aid == 'im_epinephrine':
                    sim.apply_epinephrine_dose(round(min(.01 * sim.state.weight_kg, .3), 3))
                elif aid == 'fluid_bolus':
                    sim.apply_fluid_bolus_volume(10 * sim.state.weight_kg)
                elif aid == 'steroid':
                    sim.apply_steroid_dose(min(sim.state.weight_kg, 40))
                else:
                    sim.apply_action(aid)
                sim.tick()
            self.assertEqual(sim.display_score(), 97)
            self.assertFalse(sim.is_done()[0])
            sim.mark_manual_rescue_completion()
            report = sim.build_report()
            before = copy.deepcopy(report)
            self.assertIn('abc_assess', report['critical_missing'])
            missing = [_namespace['_result_feedback_text'](x) for x in report['critical_missing']]
            unfinished = [_namespace['_result_feedback_text'](x) for x in report['clinical_pathway_flags']['unfinished_required_steps']]
            self.assertIn('ABC评估', missing)
            self.assertIn('ABC评估', unfinished)
            self.assertNotIn('abc_assess', '、'.join(missing + unfinished))
            self.assertEqual(report, before)
            self.assertEqual(report['score'], 97)

    def test_unknown_tokens_substrings_and_original_descriptions_preserved(self):
        translate = _namespace['_result_feedback_text']
        unchanged = ['future_abc_assess', 'abc_assess_future', 'xabc_assess',
                     'abc_assess2', '2abc_assess', 'unknown-abc_assess', 'abc_assess-unknown', 'unknown_action:原始中文说明',
                     '未知字段 future_abc_assess 尚未完成', 'ABC评估尚未完成',
                     '剂量0.14 mg，时间00:30', '']
        for value in unchanged:
            with self.subTest(value=value):
                self.assertEqual(translate(value), value)
        self.assertEqual(translate('未完成abc_assess，请补做'), '未完成ABC评估，请补做')
        self.assertEqual(translate('(abc_assess)'), '(ABC评估)')
        self.assertEqual(translate('abc_assess:原始中文描述，应保留'), '原始中文描述，应保留')

class CompletionPresentationTests(unittest.TestCase):
    @staticmethod
    def step(sim, aid):
        if aid == 'im_epinephrine':
            sim.apply_epinephrine_dose(round(min(.01 * sim.state.weight_kg, .3), 3))
        elif aid == 'fluid_bolus':
            sim.apply_fluid_bolus_volume(10 * sim.state.weight_kg)
        elif aid == 'steroid':
            sim.apply_steroid_dose(min(sim.state.weight_kg, 40))
        else:
            sim.apply_action(aid)
        sim.tick()

    def real_terminal_cases(self, mode):
        # All cases follow real engine commands/time; no metadata/state injection.
        clinical = ['stop_infusion', 'call_help', 'abc_assess', 'high_flow_oxygen',
                    'shock_position', 'connect_monitor', 'check_bp', 'im_epinephrine',
                    'fluid_bolus', 'reassess_first', 'bronchodilator', 'steroid',
                    'reassess_second', 'family_explain', 'sbar_handoff']
        academy = ['allergy_identification', 'stop_infusion', 'call_help', 'high_flow_oxygen',
                   'connect_monitor', 'check_bp', 'prepare_rescue_equipment',
                   'academy_medication_check', 'academy_assisted_medication',
                   'academy_reassess', 'academy_family_communication', 'academy_sbar_handoff']
        cases = []
        for role in ('initial', 'variant', 'academy_initial', 'academy_variant'):
            sim = Simulator(load_scenario_by_role(role), mode=mode, seed=17)
            for aid in academy if role.startswith('academy') else clinical:
                self.step(sim, aid)
            cases.append(('clean_' + role, sim, 'success'))
        manual = Simulator(load_scenario_by_role('initial'), mode=mode, seed=17)
        for aid in clinical:
            if aid != 'abc_assess':
                self.step(manual, aid)
        self.assertEqual(manual.display_score(), 97)
        manual.mark_manual_rescue_completion()
        cases.append(('manual_97', manual, 'warning'))
        timeout = Simulator(load_scenario_by_role('initial'), mode=mode, seed=17)
        for aid in ('stop_infusion', 'high_flow_oxygen', 'im_epinephrine'):
            self.step(timeout, aid)
        for _ in range(35):
            if timeout.is_done()[0]:
                break
            timeout.tick()
        self.assertEqual(timeout.is_done()[1], 'timeout')
        cases.append(('timeout', timeout, 'warning'))
        overdose = Simulator(load_scenario_by_role('initial'), mode=mode, seed=17)
        overdose.apply_epinephrine_dose(.31)
        self.assertEqual(overdose.is_done()[1], 'failure')
        cases.append(('overdose', overdose, 'error'))
        for route in ('death', 'picu'):
            sim = Simulator(load_scenario_by_role('initial'), mode=mode, seed=17)
            for _ in range(35):
                if sim.state.flags.get('cardiac_arrest') or sim.is_done()[0]:
                    break
                sim.tick()
            self.assertTrue(sim.state.flags['cardiac_arrest'])
            if route == 'death':
                sim.tick()
                self.assertTrue(sim.state.flags['dead'])
            else:
                for aid in ('cpr', 'bvm_ventilation', 'advanced_support'):
                    self.step(sim, aid)
                self.assertEqual(sim.is_done()[1], 'critical_resuscitated_transfer_picu')
            cases.append((route, sim, 'error' if route == 'death' else 'warning'))
        return cases

    def test_real_terminal_severity_and_coach_prompt_preserve_report_and_state(self):
        notice = _namespace['_result_completion_notice']
        prompt = _namespace['_coach_prompt_for_display']
        for mode in ('coach', 'exam'):
            for name, sim, expected in self.real_terminal_cases(mode):
                with self.subTest(mode=mode, path=name):
                    done, reason = sim.is_done()
                    self.assertTrue(done)
                    report = sim.build_report()
                    before = (sim.to_snapshot(), copy.deepcopy(report), copy.deepcopy(sim.log))
                    level, text = notice(report, reason)
                    self.assertEqual(level, expected)
                    self.assertTrue(text)
                    item = {'text': '继续复评观察', 'reason': '既有流程提示', 'extra': 17}
                    item_before = dict(item)
                    shown = prompt(sim, item)
                    self.assertEqual(shown, {'text': '本轮已结束，可查看记录并确认结束。', 'reason': ''})
                    self.assertEqual(item, item_before)
                    self.assertEqual((sim.to_snapshot(), report, sim.log), before)

    def test_nonterminal_prompt_is_copy_and_does_not_change_engine_or_c04(self):
        prompt = _namespace['_coach_prompt_for_display']
        for role, mode in itertools.product(('initial', 'variant', 'academy_initial', 'academy_variant'), ('coach', 'exam')):
            sim = Simulator(load_scenario_by_role(role), mode=mode, seed=17)
            self.assertFalse(sim.is_done()[0])
            before = sim.to_snapshot()
            item = {'text': '原有复评观察提示', 'reason': '原有原因', 'extra': 17}
            shown = prompt(sim, item)
            self.assertEqual(shown, item)
            self.assertIsNot(shown, item)
            shown['text'] = '测试修改返回副本'
            self.assertEqual(item['text'], '原有复评观察提示')
            self.assertEqual(sim.to_snapshot(), before)
        # Existing C04 observation remains repeatable before finishing the case.
        sim = Simulator(load_scenario_by_role('academy_initial'), mode='coach', seed=17)
        for aid in ['allergy_identification', 'stop_infusion', 'call_help', 'high_flow_oxygen',
                    'connect_monitor', 'check_bp', 'prepare_rescue_equipment',
                    'academy_medication_check', 'academy_assisted_medication', 'academy_reassess']:
            self.step(sim, aid)
        self.assertFalse(sim.is_done()[0])
        count = sim.state.flags['reassess_count']
        first = sim.action_valid_time['academy_reassess']
        score = sim.score
        before = sim.to_snapshot()
        self.assertEqual(prompt(sim, {'text': '继续观察'})['text'], '继续观察')
        self.assertEqual(sim.to_snapshot(), before)
        self.step(sim, 'academy_reassess')
        self.assertEqual(sim.state.flags['reassess_count'], count + 1)
        self.assertEqual(sim.action_valid_time['academy_reassess'], first)
        self.assertEqual(sim.score, score)

    def test_synthetic_metadata_precedence_types_and_score_independence(self):
        # Explicit synthetic metadata boundary cases, not naturally reached paths.
        notice = _namespace['_result_completion_notice']
        cases = [
            ({'end_reason': 'success'}, 'failure', 'success'),
            ({'end_reason': 'failure', 'session': {'end_reason': 'success'}}, 'success', 'error'),
            ({'session': {'end_reason': 'failure'}}, 'success', 'error'),
            ({'end_reason': 'success', 'session': {'end_reason': 'failure'}}, 'failure', 'success'),
            ({'score': 0, 'final_grade': 'IV'}, 'success', 'success'),
            ({'score': 100, 'final_grade': 'I'}, 'failure', 'error'),
            ({'score': 100, 'final_grade': 'IV'}, 'unknown_reason', 'info'),
            ({}, 'standard_assessment_completed', 'success'),
            ({}, 'manual_end', 'warning'),
            ({}, 'participant_confirmed_rescue_complete', 'warning'),
            ({}, 'timeout', 'warning'),
            ({}, 'critical_resuscitated_transfer_picu', 'warning'),
            ({'outcome_class': 'critical_resuscitated_transfer_picu'}, 'success', 'warning'),
            ({'process_safety_issues': ['既有问题']}, 'success', 'warning'),
            ({'critical_missing': ['abc_assess']}, 'success', 'warning'),
            ({'clinical_pathway_flags': {'unfinished_required_steps': ['abc_assess:ABC评估']}}, 'success', 'warning'),
            ({'death_event': True}, 'success', 'error'),
            ({'death_after_arrest_without_cpr': True}, 'manual_end', 'error'),
            ({'outcome_class': 'death_from_scenario_rule'}, 'success', 'error'),
            ({'outcome_class': 'death_after_cardiac_arrest_without_cpr'}, 'success', 'error'),
            ({'key_timeline': {'serious_medication_error': True}}, 'success', 'error'),
            ({'key_timeline': {'serious_medication_error': True}}, 'failure', 'error'),
            ({'death_event': 'False', 'death_after_arrest_without_cpr': 'False',
              'key_timeline': {'serious_medication_error': 'False'}}, 'success', 'success'),
            ({'death_event': 'True', 'death_after_arrest_without_cpr': 1,
              'key_timeline': {'serious_medication_error': 1}}, 'success', 'success'),
            ({'outcome_class': 'unknown_death_description'}, 'unknown_reason', 'info'),
            ({'session': None, 'key_timeline': None, 'clinical_pathway_flags': None}, 'success', 'success'),
            ({}, '', 'info'),
        ]
        for report, reason, expected in cases:
            with self.subTest(report=report, reason=reason):
                before = copy.deepcopy(report)
                self.assertEqual(notice(report, reason)[0], expected)
                self.assertEqual(report, before)

    def test_exam_in_progress_has_no_coach_helper_or_outcome_banner_call(self):
        # Structural call-site check, not a claim of actual browser rendering.
        parents = {}
        for node in ast.walk(_tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        def ancestors(node):
            while node in parents:
                node = parents[node]
                yield node
        calls = [n for n in ast.walk(_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        prompt_calls = [n for n in calls if n.func.id == '_coach_prompt_for_display']
        self.assertEqual(len(prompt_calls), 1)
        self.assertTrue(any(isinstance(n, ast.If) and ast.unparse(n.test) == 'strategy.use_guided_prompts'
                            for n in ancestors(prompt_calls[0])))
        notice_calls = [n for n in calls if n.func.id == '_result_completion_notice']
        self.assertEqual(len(notice_calls), 1)
        self.assertEqual(next(n.name for n in ancestors(notice_calls[0]) if isinstance(n, ast.FunctionDef)), 'render_report')
        for role in ('initial', 'variant', 'academy_initial', 'academy_variant'):
            sim = Simulator(load_scenario_by_role(role), mode='exam', seed=17)
            self.assertFalse(sim.flow_strategy.use_guided_prompts)
            self.assertFalse(sim.flow_strategy.show_immediate_feedback)

if __name__ == '__main__':
    unittest.main(verbosity=2)
