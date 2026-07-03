from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple


SCENARIO_DIRECTORY = Path(__file__).resolve().parent / "scenarios"
ALLOWED_SYSTEM_MODES = {"clinical", "academy"}


class ScenarioCatalogError(ValueError):
    pass


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    script_role: str
    file_name: str
    system_mode: str
    phases: Tuple[str, ...]
    order: int
    library_id: str = ""

    @property
    def path(self) -> Path:
        return SCENARIO_DIRECTORY / self.file_name


SCENARIO_DEFINITIONS: Tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        scenario_id="peds_ward_anaphylaxis_iv_initial",
        script_role="initial",
        file_name="peds_ward_anaphylaxis_iv_initial.json",
        system_mode="clinical",
        phases=("基线评估", "模拟培训"),
        order=0,
    ),
    ScenarioDefinition(
        scenario_id="peds_ward_anaphylaxis_iv_variantA",
        script_role="variant",
        file_name="peds_ward_anaphylaxis_iv_variantA.json",
        system_mode="clinical",
        phases=("培训后考核",),
        order=1,
    ),
    ScenarioDefinition(
        scenario_id="peds_ward_allergy_academy_initial",
        script_role="academy_initial",
        file_name="peds_ward_allergy_academy_initial.json",
        system_mode="academy",
        phases=("课前测评", "模拟训练"),
        order=2,
        library_id="academy_anaphylaxis_rescue",
    ),
    ScenarioDefinition(
        scenario_id="peds_ward_allergy_academy_variant",
        script_role="academy_variant",
        file_name="peds_ward_allergy_academy_variant.json",
        system_mode="academy",
        phases=("课后考核",),
        order=3,
        library_id="academy_anaphylaxis_rescue",
    ),
)


def validate_scenario_definitions(
    definitions: Sequence[ScenarioDefinition],
) -> Tuple[ScenarioDefinition, ...]:
    entries = tuple(definitions)
    if not entries:
        raise ScenarioCatalogError("Scenario catalog must not be empty.")

    scenario_ids: set[str] = set()
    script_roles: set[str] = set()
    file_names: set[str] = set()
    phase_keys: set[tuple[str, str, str]] = set()
    orders: set[int] = set()

    for entry in entries:
        if not entry.scenario_id.strip():
            raise ScenarioCatalogError("Scenario id must not be empty.")
        if entry.scenario_id in scenario_ids:
            raise ScenarioCatalogError(
                f"Duplicate scenario id: {entry.scenario_id}"
            )
        scenario_ids.add(entry.scenario_id)

        if not entry.script_role.strip():
            raise ScenarioCatalogError("Script role must not be empty.")
        if entry.script_role in script_roles:
            raise ScenarioCatalogError(
                f"Duplicate script role: {entry.script_role}"
            )
        script_roles.add(entry.script_role)

        if Path(entry.file_name).name != entry.file_name:
            raise ScenarioCatalogError(
                f"Scenario file must be a direct catalog file: {entry.file_name}"
            )
        if Path(entry.file_name).suffix.lower() != ".json":
            raise ScenarioCatalogError(
                f"Registered scenario must be JSON: {entry.file_name}"
            )
        if entry.file_name in file_names:
            raise ScenarioCatalogError(
                f"Duplicate scenario file: {entry.file_name}"
            )
        file_names.add(entry.file_name)

        if entry.system_mode not in ALLOWED_SYSTEM_MODES:
            raise ScenarioCatalogError(
                f"Unsupported system mode: {entry.system_mode}"
            )
        if entry.system_mode == "academy" and not entry.library_id.strip():
            raise ScenarioCatalogError(
                f"Academy scenario requires library_id: {entry.scenario_id}"
            )
        if not entry.phases or any(not phase.strip() for phase in entry.phases):
            raise ScenarioCatalogError(
                f"Scenario phases must not be empty: {entry.scenario_id}"
            )
        for phase in entry.phases:
            phase_key = (entry.system_mode, entry.library_id, phase)
            if phase_key in phase_keys:
                raise ScenarioCatalogError(
                    "Duplicate scenario phase mapping: "
                    f"{entry.system_mode}/{entry.library_id}/{phase}"
                )
            phase_keys.add(phase_key)

        if entry.order in orders:
            raise ScenarioCatalogError(f"Duplicate scenario order: {entry.order}")
        orders.add(entry.order)

    return tuple(sorted(entries, key=lambda item: item.order))


_VALIDATED_DEFINITIONS = validate_scenario_definitions(SCENARIO_DEFINITIONS)
_BY_ID = {entry.scenario_id: entry for entry in _VALIDATED_DEFINITIONS}
_BY_ROLE = {entry.script_role: entry for entry in _VALIDATED_DEFINITIONS}
_BY_PATH = {entry.path.resolve(): entry for entry in _VALIDATED_DEFINITIONS}
_BY_PHASE = {
    (entry.system_mode, entry.library_id, phase): entry
    for entry in _VALIDATED_DEFINITIONS
    for phase in entry.phases
}


def scenario_definitions(
    system_mode: Optional[str] = None,
) -> Tuple[ScenarioDefinition, ...]:
    if system_mode is None:
        return _VALIDATED_DEFINITIONS
    if system_mode not in ALLOWED_SYSTEM_MODES:
        return ()
    return tuple(
        entry
        for entry in _VALIDATED_DEFINITIONS
        if entry.system_mode == system_mode
    )


def scenario_definition(scenario_id: str) -> ScenarioDefinition:
    try:
        return _BY_ID[str(scenario_id)]
    except KeyError as exc:
        raise ScenarioCatalogError(
            f"Unknown scenario id: {scenario_id}"
        ) from exc


def scenario_definition_by_role(script_role: str) -> ScenarioDefinition:
    try:
        return _BY_ROLE[str(script_role)]
    except KeyError as exc:
        raise ScenarioCatalogError(
            f"Unknown script role: {script_role}"
        ) from exc


def find_scenario_definition_by_role(
    script_role: str,
) -> Optional[ScenarioDefinition]:
    return _BY_ROLE.get(str(script_role))


def scenario_definition_for_phase(
    system_mode: str,
    phase: str,
    library_id: str = "",
) -> ScenarioDefinition:
    key = (str(system_mode), str(library_id), str(phase))
    try:
        return _BY_PHASE[key]
    except KeyError as exc:
        raise ScenarioCatalogError(
            "Unknown scenario phase mapping: "
            f"{system_mode}/{library_id}/{phase}"
        ) from exc


def scenario_definition_for_path(
    path: str | Path,
) -> Optional[ScenarioDefinition]:
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return _BY_PATH.get(resolved)


def iter_scenario_paths(
    definitions: Optional[Iterable[ScenarioDefinition]] = None,
) -> Tuple[Path, ...]:
    entries = (
        tuple(definitions)
        if definitions is not None
        else _VALIDATED_DEFINITIONS
    )
    return tuple(entry.path for entry in entries)
