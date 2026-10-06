from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402
from peds_anaphylaxis_sim import engine  # noqa: E402
from peds_anaphylaxis_sim.scenario_catalog import (  # noqa: E402
    SCENARIO_DEFINITIONS,
    SCENARIO_DIRECTORY,
    ScenarioCatalogError,
    scenario_definition,
    scenario_definition_by_role,
    scenario_definition_for_path,
    scenario_definition_for_phase,
    scenario_definitions,
    validate_scenario_definitions,
)
from peds_anaphylaxis_sim import scenario_loader  # noqa: E402


EXPECTED_HASHES = {
    "peds_ward_allergy_academy_initial.json": "3921241d529b28d8d4309455eab6a017e4899faa89779e12d336f1712e8d976b",
    "peds_ward_allergy_academy_variant.json": "c379745d516e060df4b630674a223d0b01cb9d082032db2ddb172d34149e1e5f",
    "peds_ward_anaphylaxis_iv_initial.json": "38c4d0e94e4b6e4fe4e5e2013ccd2f779b3f268673e5ea3d22cde567fb5432b1",
    "peds_ward_anaphylaxis_iv_variantA.json": "07fc8f012712160fe03d27dae81270429725249c0f61c3b4a307d6687f735d8b",
}


class ScenarioCatalogAndLoaderTests(unittest.TestCase):
    def test_catalog_contains_exactly_four_registered_scenarios(self):
        self.assertEqual(len(scenario_definitions()), 4)
        self.assertEqual(
            {entry.file_name for entry in scenario_definitions()},
            set(EXPECTED_HASHES),
        )

    def test_catalog_order_preserves_existing_role_order(self):
        self.assertEqual(
            [entry.script_role for entry in scenario_definitions()],
            ["initial", "variant", "academy_initial", "academy_variant"],
        )

    def test_ids_roles_files_and_orders_are_unique(self):
        entries = scenario_definitions()
        for values in (
            [entry.scenario_id for entry in entries],
            [entry.script_role for entry in entries],
            [entry.file_name for entry in entries],
            [entry.order for entry in entries],
        ):
            self.assertEqual(len(values), len(set(values)))

    def test_phase_mappings_are_unique_and_complete(self):
        mappings = [
            (entry.system_mode, entry.library_id, phase)
            for entry in scenario_definitions()
            for phase in entry.phases
        ]
        self.assertEqual(len(mappings), 6)
        self.assertEqual(len(mappings), len(set(mappings)))

    def test_registered_files_exist_directly_in_scenario_directory(self):
        for entry in scenario_definitions():
            with self.subTest(scenario=entry.scenario_id):
                self.assertTrue(entry.path.is_file())
                self.assertEqual(entry.path.parent.resolve(), SCENARIO_DIRECTORY.resolve())

    def test_registered_metadata_matches_catalog_identity(self):
        for entry in scenario_definitions():
            with self.subTest(scenario=entry.scenario_id):
                loaded = scenario_loader.load_registered_scenario(entry.scenario_id)
                metadata = loaded["scenario"]
                self.assertEqual(metadata["id"], entry.scenario_id)
                self.assertEqual(metadata["script_role"], entry.script_role)

    def test_loading_by_id_matches_direct_utf8_json_load(self):
        for entry in scenario_definitions():
            with self.subTest(scenario=entry.scenario_id):
                expected = json.loads(entry.path.read_text(encoding="utf-8"))
                actual = scenario_loader.load_registered_scenario(entry.scenario_id)
                self.assertEqual(actual, expected)

    def test_loading_by_role_uses_the_same_registered_definition(self):
        for entry in scenario_definitions():
            with self.subTest(role=entry.script_role):
                self.assertEqual(
                    scenario_loader.load_scenario_by_role(entry.script_role),
                    scenario_loader.load_registered_scenario(entry.scenario_id),
                )

    def test_clinical_phase_resolution_preserves_current_mapping(self):
        expected = {
            "基线评估": "peds_ward_anaphylaxis_iv_initial",
            "模拟培训": "peds_ward_anaphylaxis_iv_initial",
            "培训后考核": "peds_ward_anaphylaxis_iv_variantA",
        }
        actual = {
            phase: scenario_definition_for_phase("clinical", phase).scenario_id
            for phase in expected
        }
        self.assertEqual(actual, expected)

    def test_academy_phase_resolution_preserves_current_mapping(self):
        library_id = "academy_anaphylaxis_rescue"
        expected = {
            "课前测评": "peds_ward_allergy_academy_initial",
            "模拟训练": "peds_ward_allergy_academy_initial",
            "课后考核": "peds_ward_allergy_academy_variant",
        }
        actual = {
            phase: scenario_definition_for_phase(
                "academy",
                phase,
                library_id,
            ).scenario_id
            for phase in expected
        }
        self.assertEqual(actual, expected)

    def test_unknown_scenario_id_is_rejected(self):
        with self.assertRaisesRegex(ScenarioCatalogError, "Unknown scenario id"):
            scenario_definition("unknown")

    def test_unknown_script_role_is_rejected(self):
        with self.assertRaisesRegex(ScenarioCatalogError, "Unknown script role"):
            scenario_definition_by_role("unknown")

    def test_unknown_phase_mapping_is_rejected(self):
        with self.assertRaisesRegex(
            ScenarioCatalogError,
            "Unknown scenario phase mapping",
        ):
            scenario_definition_for_phase("clinical", "unknown")

    def test_unregistered_path_is_rejected(self):
        self.assertIsNone(scenario_definition_for_path(ROOT / "README.md"))
        with self.assertRaisesRegex(
            ScenarioCatalogError,
            "Scenario path is not registered",
        ):
            scenario_loader.load_registered_scenario_path(ROOT / "README.md")

    def test_duplicate_scenario_id_is_rejected(self):
        entries = list(SCENARIO_DEFINITIONS)
        entries[1] = replace(
            entries[1],
            scenario_id=entries[0].scenario_id,
        )
        with self.assertRaisesRegex(ScenarioCatalogError, "Duplicate scenario id"):
            validate_scenario_definitions(entries)

    def test_duplicate_phase_mapping_is_rejected(self):
        entries = list(SCENARIO_DEFINITIONS)
        entries[1] = replace(entries[1], phases=("基线评估",))
        with self.assertRaisesRegex(
            ScenarioCatalogError,
            "Duplicate scenario phase mapping",
        ):
            validate_scenario_definitions(entries)

    def test_catalog_rejects_path_traversal_file_names(self):
        entries = list(SCENARIO_DEFINITIONS)
        entries[0] = replace(entries[0], file_name="../outside.json")
        with self.assertRaisesRegex(
            ScenarioCatalogError,
            "direct catalog file",
        ):
            validate_scenario_definitions(entries)

    def test_registered_loader_rejects_metadata_mismatch(self):
        entry = scenario_definitions()[0]
        mismatched = {
            "scenario": {
                "id": "different",
                "script_role": entry.script_role,
            }
        }
        with patch.object(
            scenario_loader,
            "load_scenario_file",
            return_value=mismatched,
        ):
            with self.assertRaisesRegex(
                scenario_loader.ScenarioLoadError,
                "scenario id mismatch",
            ):
                scenario_loader.load_registered_scenario(entry.scenario_id)

    def test_engine_load_scenario_delegates_to_loader(self):
        sentinel = {"scenario": {"id": "delegated"}}
        with patch.object(
            engine,
            "load_scenario_file",
            return_value=sentinel,
        ) as delegated:
            self.assertIs(engine.load_scenario("fixture.json"), sentinel)
        delegated.assert_called_once_with("fixture.json")

    def test_streamlit_catalog_wrappers_do_not_scan_the_directory(self):
        source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn('SCENARIO_DIR.glob("*.json")', source)
        self.assertEqual(len(app.list_scenarios()), 4)
        for entry in scenario_definitions():
            self.assertEqual(
                app.scenario_path_by_role(entry.script_role),
                entry.path,
            )

    def test_streamlit_phase_routing_uses_registered_paths(self):
        self.assertEqual(
            app.scenario_path_for_phase("clinical", "模拟培训"),
            scenario_definition("peds_ward_anaphylaxis_iv_initial").path,
        )
        self.assertEqual(
            app.scenario_path_for_phase(
                "academy",
                "课后考核",
                "academy_anaphylaxis_rescue",
            ),
            scenario_definition("peds_ward_allergy_academy_variant").path,
        )
        self.assertIsNone(
            app.scenario_path_for_phase("academy", "课后考核", "unknown")
        )

    def test_registered_content_counts_and_hashes_are_unchanged(self):
        action_count = 0
        rule_count = 0
        actual_hashes = {}
        for entry in scenario_definitions():
            loaded = scenario_loader.load_registered_scenario(entry.scenario_id)
            action_count += len(loaded["actions"])
            rule_count += len(loaded["dynamics"]["rules"])
            actual_hashes[entry.file_name] = hashlib.sha256(
                entry.path.read_bytes()
            ).hexdigest()
        self.assertEqual(action_count, 88)
        self.assertEqual(rule_count, 50)
        self.assertEqual(actual_hashes, EXPECTED_HASHES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
