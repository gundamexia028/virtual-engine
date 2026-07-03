from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from peds_anaphylaxis_sim.scenario_catalog import (  # noqa: E402
    SCENARIO_DIRECTORY,
    scenario_definitions,
)
from peds_anaphylaxis_sim.scenario_loader import (  # noqa: E402
    load_registered_scenario,
)


SCENARIO_DIR = SCENARIO_DIRECTORY
EXPECTED_SCENARIO_HASHES = {
    "peds_ward_allergy_academy_initial.json": "ea4b0602126b2d9d93c4a9eb56b7bf95d4b52b6caea3d67acc0b372687adebee",
    "peds_ward_allergy_academy_variant.json": "694d19aa42be2ca3151bf730d9eb9836031e4adc578a4a7359948c68b1b4e475",
    "peds_ward_anaphylaxis_iv_initial.json": "6d181f88c8b6c3820927c58e98faa8464d8ac89501e0f67f4c5b108b511c7113",
    "peds_ward_anaphylaxis_iv_variantA.json": "add6094c640b995958c213ae179b3424797e6434cd0fa676a91230c5643b402d",
}
EXPECTED_VITAL_KEYS = {"HR", "RR", "SBP", "DBP", "SpO2", "Temp"}
ALLOWED_SCRIPT_ROLES = {"initial", "variant", "academy_initial", "academy_variant"}
ALLOWED_TARGET_GROUPS = {"", "clinical_nurse", "nursing_student"}
EFFECT_VITAL_FIELDS = {"delta_vitals", "set_vitals"}


class ScenarioContractError(ValueError):
    pass


def load_documents() -> dict[str, dict]:
    return {
        definition.file_name: load_registered_scenario(definition.scenario_id)
        for definition in scenario_definitions()
    }


def _require_mapping(value, label: str, errors: list[str]) -> dict:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def _require_nonempty_text(value, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be non-empty text")
        return ""
    return value.strip()


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return duplicate


def _validate_explicit_graph(document: dict, errors: list[str]) -> dict:
    raw_nodes = document.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        errors.append("nodes must be a non-empty list")
        return {"graph_kind": "explicit", "node_count": 0, "option_count": 0}

    node_ids: list[str] = []
    option_ids: list[str] = []
    edges: dict[str, list[str]] = defaultdict(list)
    terminal_nodes: set[str] = set()
    for index, raw_node in enumerate(raw_nodes):
        node = _require_mapping(raw_node, f"nodes[{index}]", errors)
        node_id = _require_nonempty_text(node.get("id"), f"nodes[{index}].id", errors)
        if node_id:
            node_ids.append(node_id)
        options = node.get("options", [])
        if not isinstance(options, list):
            errors.append(f"nodes[{index}].options must be a list")
            options = []
        is_terminal = node.get("terminal", False)
        if not isinstance(is_terminal, bool):
            errors.append(f"nodes[{index}].terminal must be boolean")
        if is_terminal:
            terminal_nodes.add(node_id)
            if options:
                errors.append(f"terminal node {node_id!r} cannot define options")
        elif not options:
            errors.append(f"non-terminal node {node_id!r} must define options")
        for option_index, raw_option in enumerate(options):
            option = _require_mapping(
                raw_option,
                f"nodes[{index}].options[{option_index}]",
                errors,
            )
            option_id = _require_nonempty_text(
                option.get("id"),
                f"nodes[{index}].options[{option_index}].id",
                errors,
            )
            target = _require_nonempty_text(
                option.get("target_node_id"),
                f"nodes[{index}].options[{option_index}].target_node_id",
                errors,
            )
            if option_id:
                option_ids.append(option_id)
            if node_id and target:
                edges[node_id].append(target)

    duplicate_nodes = _duplicates(node_ids)
    duplicate_options = _duplicates(option_ids)
    if duplicate_nodes:
        errors.append(f"duplicate node ids: {sorted(duplicate_nodes)}")
    if duplicate_options:
        errors.append(f"duplicate option ids: {sorted(duplicate_options)}")

    node_id_set = set(node_ids)
    start_node_id = _require_nonempty_text(
        document.get("start_node_id"),
        "start_node_id",
        errors,
    )
    if start_node_id and start_node_id not in node_id_set:
        errors.append(f"start node does not exist: {start_node_id}")
    for source, targets in edges.items():
        for target in targets:
            if target not in node_id_set:
                errors.append(f"target node does not exist: {source} -> {target}")

    reachable: set[str] = set()
    if start_node_id in node_id_set:
        queue = deque([start_node_id])
        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            queue.extend(target for target in edges[current] if target in node_id_set)
        unreachable = node_id_set - reachable
        if unreachable:
            errors.append(f"unreachable nodes: {sorted(unreachable)}")
        if terminal_nodes and not (terminal_nodes & reachable):
            errors.append("no terminal node is reachable from the start node")
    if not terminal_nodes:
        errors.append("at least one terminal node is required")

    raw_allowed_edges = document.get("allowed_cycle_edges", [])
    allowed_edges: set[tuple[str, str]] = set()
    if not isinstance(raw_allowed_edges, list):
        errors.append("allowed_cycle_edges must be a list")
    else:
        for edge in raw_allowed_edges:
            if (
                not isinstance(edge, list)
                or len(edge) != 2
                or not all(isinstance(item, str) and item for item in edge)
            ):
                errors.append("allowed_cycle_edges entries must contain two node ids")
                continue
            allowed_edges.add((edge[0], edge[1]))

    color: dict[str, int] = {}

    def visit(node_id: str) -> None:
        color[node_id] = 1
        for target in edges[node_id]:
            if target not in node_id_set or (node_id, target) in allowed_edges:
                continue
            if color.get(target) == 1:
                errors.append(f"unapproved cycle edge: {node_id} -> {target}")
                continue
            if color.get(target, 0) == 0:
                visit(target)
        color[node_id] = 2

    if start_node_id in node_id_set:
        visit(start_node_id)

    return {
        "graph_kind": "explicit",
        "node_count": len(node_ids),
        "option_count": len(option_ids),
        "start_node_id": start_node_id,
        "terminal_node_ids": sorted(terminal_nodes),
    }


def validate_scenario_document(document: dict, source_name: str) -> dict:
    errors: list[str] = []
    if not isinstance(document, dict):
        raise ScenarioContractError(f"{source_name}: scenario root must be an object")

    if document.get("schema_version") != 1:
        errors.append("schema_version must remain 1")
    scenario = _require_mapping(document.get("scenario"), "scenario", errors)
    scenario_id = _require_nonempty_text(scenario.get("id"), "scenario.id", errors)
    _require_nonempty_text(scenario.get("title"), "scenario.title", errors)
    script_role = _require_nonempty_text(
        scenario.get("script_role"),
        "scenario.script_role",
        errors,
    )
    if script_role and script_role not in ALLOWED_SCRIPT_ROLES:
        errors.append(f"unsupported script role: {script_role}")
    target_group = str(scenario.get("target_group", "") or "")
    if target_group not in ALLOWED_TARGET_GROUPS:
        errors.append(f"unsupported target group: {target_group}")
    mode_defaults = _require_mapping(
        scenario.get("mode_defaults"),
        "scenario.mode_defaults",
        errors,
    )
    if not isinstance(mode_defaults.get("coach"), bool):
        errors.append("scenario.mode_defaults.coach must be boolean")

    baseline = _require_mapping(document.get("baseline"), "baseline", errors)
    _require_nonempty_text(
        baseline.get("time_zero_description"),
        "baseline.time_zero_description",
        errors,
    )
    vitals = _require_mapping(baseline.get("vitals"), "baseline.vitals", errors)
    symptoms = _require_mapping(baseline.get("symptoms"), "baseline.symptoms", errors)
    flags = _require_mapping(baseline.get("flags"), "baseline.flags", errors)
    if set(vitals) != EXPECTED_VITAL_KEYS:
        errors.append(
            f"baseline vital fields must equal {sorted(EXPECTED_VITAL_KEYS)}"
        )
    if not symptoms:
        errors.append("baseline.symptoms must not be empty")
    if not flags:
        errors.append("baseline.flags must not be empty")

    raw_actions = document.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        errors.append("actions must be a non-empty list")
        raw_actions = []
    action_ids: list[str] = []
    score_total = 0
    for index, raw_action in enumerate(raw_actions):
        action = _require_mapping(raw_action, f"actions[{index}]", errors)
        action_id = _require_nonempty_text(
            action.get("id"),
            f"actions[{index}].id",
            errors,
        )
        _require_nonempty_text(
            action.get("label"),
            f"actions[{index}].label",
            errors,
        )
        _require_nonempty_text(
            action.get("category"),
            f"actions[{index}].category",
            errors,
        )
        if action_id:
            action_ids.append(action_id)
        score = _require_mapping(
            action.get("score"),
            f"actions[{index}].score",
            errors,
        )
        points = score.get("points")
        if not isinstance(points, int) or isinstance(points, bool) or points < 0:
            errors.append(f"actions[{index}].score.points must be a non-negative integer")
        else:
            score_total += points
        time_window = score.get("time_window_seconds")
        if points and (
            not isinstance(time_window, int)
            or isinstance(time_window, bool)
            or time_window <= 0
        ):
            errors.append(
                f"actions[{index}].score.time_window_seconds must be a positive integer"
            )
        elif time_window is not None and (
            not isinstance(time_window, int)
            or isinstance(time_window, bool)
            or time_window <= 0
        ):
            errors.append(
                f"actions[{index}].score.time_window_seconds must be positive when present"
            )
        effects = _require_mapping(
            action.get("effects"),
            f"actions[{index}].effects",
            errors,
        )
        for field in EFFECT_VITAL_FIELDS:
            effect_vitals = effects.get(field, {})
            if not isinstance(effect_vitals, dict):
                errors.append(f"actions[{index}].effects.{field} must be an object")
            elif not set(effect_vitals).issubset(EXPECTED_VITAL_KEYS):
                errors.append(f"actions[{index}].effects.{field} uses unknown vital fields")
    duplicate_actions = _duplicates(action_ids)
    if duplicate_actions:
        errors.append(f"duplicate action ids: {sorted(duplicate_actions)}")
    if score_total != 100:
        errors.append(f"declared action score total must be 100, got {score_total}")

    dynamics = _require_mapping(document.get("dynamics"), "dynamics", errors)
    rules = dynamics.get("rules")
    if not isinstance(rules, list):
        errors.append("dynamics.rules must be a list")
        rules = []
    rule_names: list[str] = []
    for index, raw_rule in enumerate(rules):
        rule = _require_mapping(raw_rule, f"dynamics.rules[{index}]", errors)
        rule_name = _require_nonempty_text(
            rule.get("name"),
            f"dynamics.rules[{index}].name",
            errors,
        )
        _require_nonempty_text(
            rule.get("when"),
            f"dynamics.rules[{index}].when",
            errors,
        )
        effects = _require_mapping(
            rule.get("effects"),
            f"dynamics.rules[{index}].effects",
            errors,
        )
        if rule_name:
            rule_names.append(rule_name)
        for field in EFFECT_VITAL_FIELDS:
            effect_vitals = effects.get(field, {})
            if not isinstance(effect_vitals, dict):
                errors.append(f"dynamics.rules[{index}].effects.{field} must be an object")
            elif not set(effect_vitals).issubset(EXPECTED_VITAL_KEYS):
                errors.append(
                    f"dynamics.rules[{index}].effects.{field} uses unknown vital fields"
                )
    duplicate_rules = _duplicates(rule_names)
    if duplicate_rules:
        errors.append(f"duplicate dynamic rule names: {sorted(duplicate_rules)}")

    end_conditions = _require_mapping(
        document.get("end_conditions"),
        "end_conditions",
        errors,
    )
    _require_nonempty_text(
        end_conditions.get("success_when"),
        "end_conditions.success_when",
        errors,
    )
    _require_nonempty_text(
        end_conditions.get("failure_when"),
        "end_conditions.failure_when",
        errors,
    )
    max_time = end_conditions.get("max_time_seconds")
    if not isinstance(max_time, int) or isinstance(max_time, bool) or max_time <= 0:
        errors.append("end_conditions.max_time_seconds must be a positive integer")

    training = _require_mapping(document.get("training"), "training", errors)
    guided_prompts = training.get("guided_prompts")
    if not isinstance(guided_prompts, list) or not guided_prompts:
        errors.append("training.guided_prompts must be a non-empty list")
        guided_prompts = []
    for index, raw_prompt in enumerate(guided_prompts):
        prompt = _require_mapping(
            raw_prompt,
            f"training.guided_prompts[{index}]",
            errors,
        )
        _require_nonempty_text(
            prompt.get("text"),
            f"training.guided_prompts[{index}].text",
            errors,
        )
        _require_nonempty_text(
            prompt.get("reason"),
            f"training.guided_prompts[{index}].reason",
            errors,
        )
        _require_nonempty_text(
            prompt.get("done_when"),
            f"training.guided_prompts[{index}].done_when",
            errors,
        )

    module_scoring = document.get("module_scoring", {})
    if not isinstance(module_scoring, dict):
        errors.append("module_scoring must be an object when present")
        module_scoring = {}
    if module_scoring:
        module_max_total = 0
        for module_id, raw_module in module_scoring.items():
            _require_nonempty_text(module_id, "module_scoring id", errors)
            module = _require_mapping(
                raw_module,
                f"module_scoring.{module_id}",
                errors,
            )
            max_points = module.get("max_points")
            if (
                not isinstance(max_points, int)
                or isinstance(max_points, bool)
                or max_points <= 0
            ):
                errors.append(
                    f"module_scoring.{module_id}.max_points must be a positive integer"
                )
            else:
                module_max_total += max_points
            module_actions = module.get("actions")
            if not isinstance(module_actions, list) or not module_actions:
                errors.append(f"module_scoring.{module_id}.actions must be a non-empty list")
            else:
                unknown = set(module_actions) - set(action_ids)
                if unknown:
                    errors.append(
                        f"module_scoring.{module_id} references unknown actions: {sorted(unknown)}"
                    )
        if module_max_total != 100:
            errors.append(
                f"module scoring max total must be 100, got {module_max_total}"
            )

    if "nodes" in document or "start_node_id" in document:
        graph_summary = _validate_explicit_graph(document, errors)
    else:
        graph_summary = {
            "graph_kind": "legacy_action_state",
            "node_count": 1,
            "option_count": len(action_ids),
            "start_node_id": "baseline",
            "terminal_node_ids": ["success_when", "failure_when", "max_time_seconds"],
        }

    if errors:
        raise ScenarioContractError(f"{source_name}: " + "; ".join(errors))
    return {
        "source": source_name,
        "scenario_id": scenario_id,
        "script_role": script_role,
        "target_group": target_group,
        "action_ids": action_ids,
        "dynamic_rule_names": rule_names,
        "vital_keys": sorted(vitals),
        "score_total": score_total,
        **graph_summary,
    }


def explicit_graph_fixture() -> dict:
    return {
        "schema_version": 1,
        "scenario": {
            "id": "contract_fixture",
            "title": "Contract fixture",
            "script_role": "initial",
            "target_group": "clinical_nurse",
            "mode_defaults": {"coach": True},
        },
        "baseline": {
            "time_zero_description": "Start",
            "vitals": {key: 1 for key in EXPECTED_VITAL_KEYS},
            "symptoms": {"status": 0},
            "flags": {"started": True},
        },
        "actions": [
            {
                "id": "choose",
                "label": "Choose",
                "category": "critical_fixture",
                "score": {"points": 100, "time_window_seconds": 60},
                "effects": {},
            }
        ],
        "dynamics": {"rules": []},
        "end_conditions": {
            "success_when": "flags.started",
            "failure_when": "not flags.started",
            "max_time_seconds": 60,
        },
        "training": {
            "guided_prompts": [
                {
                    "text": "Choose an option",
                    "reason": "Contract fixture",
                    "done_when": "flags.started",
                }
            ]
        },
        "start_node_id": "start",
        "nodes": [
            {
                "id": "start",
                "options": [{"id": "go", "target_node_id": "finish"}],
            },
            {"id": "finish", "terminal": True, "options": []},
        ],
    }


class ScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = load_documents()
        cls.summaries = {
            name: validate_scenario_document(document, name)
            for name, document in cls.documents.items()
        }

    def test_discovers_exactly_four_current_scenario_scripts(self):
        self.assertEqual(set(self.documents), set(EXPECTED_SCENARIO_HASHES))

    def test_scenario_ids_are_globally_unique(self):
        ids = [summary["scenario_id"] for summary in self.summaries.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_script_roles_are_globally_unique(self):
        roles = [summary["script_role"] for summary in self.summaries.values()]
        self.assertEqual(len(roles), len(set(roles)))

    def test_all_current_scenarios_satisfy_the_contract(self):
        self.assertEqual(len(self.summaries), 4)

    def test_current_action_option_ids_are_unique(self):
        for summary in self.summaries.values():
            with self.subTest(source=summary["source"]):
                self.assertEqual(
                    len(summary["action_ids"]),
                    len(set(summary["action_ids"])),
                )

    def test_current_legacy_scenarios_have_an_implicit_start_state(self):
        for summary in self.summaries.values():
            with self.subTest(source=summary["source"]):
                self.assertEqual(summary["graph_kind"], "legacy_action_state")
                self.assertEqual(summary["start_node_id"], "baseline")
                self.assertEqual(summary["node_count"], 1)

    def test_current_terminal_conditions_are_present(self):
        for summary in self.summaries.values():
            with self.subTest(source=summary["source"]):
                self.assertEqual(
                    summary["terminal_node_ids"],
                    ["success_when", "failure_when", "max_time_seconds"],
                )

    def test_current_vital_sign_structures_are_consistent(self):
        vital_shapes = {
            tuple(summary["vital_keys"])
            for summary in self.summaries.values()
        }
        self.assertEqual(vital_shapes, {tuple(sorted(EXPECTED_VITAL_KEYS))})

    def test_current_score_totals_and_dimensions_are_valid(self):
        self.assertTrue(
            all(summary["score_total"] == 100 for summary in self.summaries.values())
        )

    def test_current_mode_and_audience_markers_are_valid(self):
        expected = {
            ("initial", ""),
            ("variant", ""),
            ("academy_initial", "nursing_student"),
            ("academy_variant", "nursing_student"),
        }
        actual = {
            (summary["script_role"], summary["target_group"])
            for summary in self.summaries.values()
        }
        self.assertEqual(actual, expected)

    def test_action_labels_form_the_required_feedback_identity(self):
        for source, document in self.documents.items():
            with self.subTest(source=source):
                labels = [action["label"].strip() for action in document["actions"]]
                categories = [action["category"].strip() for action in document["actions"]]
                self.assertTrue(all(labels))
                self.assertTrue(all(categories))

    def test_guided_feedback_prompts_are_complete(self):
        for source, document in self.documents.items():
            with self.subTest(source=source):
                prompts = document["training"]["guided_prompts"]
                self.assertTrue(prompts)
                self.assertTrue(
                    all(
                        prompt["text"].strip()
                        and prompt["reason"].strip()
                        and prompt["done_when"].strip()
                        for prompt in prompts
                    )
                )

    def test_explicit_graph_contract_accepts_a_valid_graph(self):
        summary = validate_scenario_document(explicit_graph_fixture(), "valid-graph")
        self.assertEqual(summary["graph_kind"], "explicit")
        self.assertEqual(summary["node_count"], 2)
        self.assertEqual(summary["option_count"], 1)

    def test_explicit_graph_contract_rejects_duplicate_ids(self):
        fixture = explicit_graph_fixture()
        fixture["nodes"].append(
            {
                "id": "finish",
                "terminal": True,
                "options": [],
            }
        )
        with self.assertRaisesRegex(ScenarioContractError, "duplicate node ids"):
            validate_scenario_document(fixture, "duplicate-node")

    def test_explicit_graph_contract_rejects_duplicate_option_ids(self):
        fixture = explicit_graph_fixture()
        fixture["nodes"][0]["options"].append(
            {"id": "go", "target_node_id": "finish"}
        )
        with self.assertRaisesRegex(ScenarioContractError, "duplicate option ids"):
            validate_scenario_document(fixture, "duplicate-option")

    def test_explicit_graph_contract_rejects_dangling_and_unreachable_nodes(self):
        fixture = explicit_graph_fixture()
        fixture["nodes"][0]["options"][0]["target_node_id"] = "missing"
        with self.assertRaisesRegex(ScenarioContractError, "target node does not exist"):
            validate_scenario_document(fixture, "dangling-target")

    def test_explicit_graph_contract_rejects_isolated_nodes(self):
        fixture = explicit_graph_fixture()
        fixture["nodes"].append(
            {
                "id": "orphan",
                "options": [{"id": "orphan-go", "target_node_id": "finish"}],
            }
        )
        with self.assertRaisesRegex(ScenarioContractError, "unreachable nodes"):
            validate_scenario_document(fixture, "unreachable-node")

    def test_explicit_graph_contract_rejects_unapproved_cycles(self):
        fixture = explicit_graph_fixture()
        fixture["nodes"][1] = {
            "id": "review",
            "options": [{"id": "back", "target_node_id": "start"}],
        }
        fixture["nodes"].append({"id": "finish", "terminal": True, "options": []})
        fixture["nodes"][0]["options"][0]["target_node_id"] = "review"
        fixture["nodes"][0]["options"].append(
            {"id": "complete", "target_node_id": "finish"}
        )
        with self.assertRaisesRegex(ScenarioContractError, "unapproved cycle"):
            validate_scenario_document(fixture, "cycle")

    def test_explicit_graph_contract_accepts_declared_cycle_edges(self):
        fixture = explicit_graph_fixture()
        fixture["nodes"][1] = {
            "id": "review",
            "options": [
                {"id": "back", "target_node_id": "start"},
                {"id": "complete", "target_node_id": "finish"},
            ],
        }
        fixture["nodes"].append({"id": "finish", "terminal": True, "options": []})
        fixture["nodes"][0]["options"][0]["target_node_id"] = "review"
        fixture["allowed_cycle_edges"] = [["review", "start"]]
        summary = validate_scenario_document(fixture, "allowed-cycle")
        self.assertEqual(summary["terminal_node_ids"], ["finish"])

    def test_scenario_source_hashes_are_unchanged(self):
        actual = {
            definition.file_name: hashlib.sha256(
                definition.path.read_bytes()
            ).hexdigest()
            for definition in scenario_definitions()
        }
        self.assertEqual(actual, EXPECTED_SCENARIO_HASHES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
