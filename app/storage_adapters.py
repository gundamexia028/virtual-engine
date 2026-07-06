from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runtime_config import APP_MODE_COMPETITION, APP_MODE_PRODUCTION


QUESTIONNAIRE_FILENAME = "questionnaire_results.jsonl"


@dataclass(frozen=True)
class StoragePaths:
    results_index: Path
    full_reports: Path
    questionnaires: Path
    report_runs: Path
    lock_file: Path
    warning_file: Path


class StorageAdapter:
    app_mode = ""
    allows_database = False
    read_only_admin = False

    def write_paths(self) -> StoragePaths:
        raise NotImplementedError

    def admin_read_paths(self) -> StoragePaths:
        raise NotImplementedError


def _paths(directory: Path) -> StoragePaths:
    base = Path(directory)
    return StoragePaths(
        results_index=base / "training_results.jsonl",
        full_reports=base / "training_full_reports.jsonl",
        questionnaires=base / QUESTIONNAIRE_FILENAME,
        report_runs=base / "reports",
        lock_file=base / ".results.lock",
        warning_file=base / "storage_warnings.log",
    )


class ProductionStorageAdapter(StorageAdapter):
    app_mode = APP_MODE_PRODUCTION
    allows_database = True
    read_only_admin = False

    def __init__(self, runtime_directory: Path):
        self._runtime_paths = _paths(runtime_directory)

    def write_paths(self) -> StoragePaths:
        return self._runtime_paths

    def admin_read_paths(self) -> StoragePaths:
        return self._runtime_paths


class CompetitionStorageAdapter(StorageAdapter):
    app_mode = APP_MODE_COMPETITION
    allows_database = False
    read_only_admin = True

    def __init__(self, demo_directory: Path, runtime_directory: Path):
        self._demo_paths = _paths(demo_directory)
        self._runtime_paths = _paths(runtime_directory)

    def write_paths(self) -> StoragePaths:
        return self._runtime_paths

    def admin_read_paths(self) -> StoragePaths:
        # The review backend deliberately shows only immutable preset demo data.
        return self._demo_paths


def build_storage_adapter(
    app_mode: str,
    *,
    production_directory: Path,
    demo_directory: Path,
    competition_runtime_directory: Path,
) -> StorageAdapter:
    if app_mode == APP_MODE_COMPETITION:
        return CompetitionStorageAdapter(demo_directory, competition_runtime_directory)
    if app_mode == APP_MODE_PRODUCTION:
        return ProductionStorageAdapter(production_directory)
    raise ValueError("Unsupported APP_MODE.")
