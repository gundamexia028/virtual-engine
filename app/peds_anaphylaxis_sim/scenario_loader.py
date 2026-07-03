from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    from .scenario_catalog import (
        ScenarioCatalogError,
        ScenarioDefinition,
        scenario_definition,
        scenario_definition_by_role,
        scenario_definition_for_phase,
        scenario_definition_for_path,
    )
except ImportError:  # pragma: no cover - direct engine.py compatibility
    from scenario_catalog import (  # type: ignore
        ScenarioCatalogError,
        ScenarioDefinition,
        scenario_definition,
        scenario_definition_by_role,
        scenario_definition_for_phase,
        scenario_definition_for_path,
    )


class ScenarioLoadError(ValueError):
    pass


def load_scenario_file(path: str | Path) -> Dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        with source.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    else:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "YAML scenario requires PyYAML. Install with: pip install pyyaml\n"
                f"Original error: {exc}"
            ) from exc
        with source.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ScenarioLoadError(
            f"Scenario root must be an object: {source}"
        )
    return loaded


def _validate_registered_metadata(
    definition: ScenarioDefinition,
    scenario: Dict[str, Any],
) -> Dict[str, Any]:
    metadata = scenario.get("scenario")
    if not isinstance(metadata, dict):
        raise ScenarioLoadError(
            f"Registered scenario metadata is missing: {definition.file_name}"
        )
    actual_id = str(metadata.get("id", ""))
    actual_role = str(metadata.get("script_role", ""))
    if actual_id != definition.scenario_id:
        raise ScenarioLoadError(
            "Registered scenario id mismatch: "
            f"{definition.scenario_id} != {actual_id}"
        )
    if actual_role != definition.script_role:
        raise ScenarioLoadError(
            "Registered script role mismatch: "
            f"{definition.script_role} != {actual_role}"
        )
    return scenario


def load_registered_scenario(scenario_id: str) -> Dict[str, Any]:
    definition = scenario_definition(scenario_id)
    return _validate_registered_metadata(
        definition,
        load_scenario_file(definition.path),
    )


def load_scenario_by_role(script_role: str) -> Dict[str, Any]:
    definition = scenario_definition_by_role(script_role)
    return load_registered_scenario(definition.scenario_id)


def load_scenario_for_phase(
    system_mode: str,
    phase: str,
    library_id: str = "",
) -> Dict[str, Any]:
    definition = scenario_definition_for_phase(
        system_mode,
        phase,
        library_id,
    )
    return load_registered_scenario(definition.scenario_id)


def load_registered_scenario_path(path: str | Path) -> Dict[str, Any]:
    definition = scenario_definition_for_path(path)
    if definition is None:
        raise ScenarioCatalogError(
            f"Scenario path is not registered: {path}"
        )
    return load_registered_scenario(definition.scenario_id)
