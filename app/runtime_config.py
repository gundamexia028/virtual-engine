from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional


APP_MODE_PRODUCTION = "production"
APP_MODE_COMPETITION = "competition"
VALID_APP_MODES = (APP_MODE_PRODUCTION, APP_MODE_COMPETITION)
TRUE_VALUES = {"1", "true", "yes", "on"}


class RuntimeConfigurationError(ValueError):
    """Raised when an explicitly configured runtime mode is invalid."""


def _mapping_value(source: Optional[Mapping[str, Any]], name: str) -> Any:
    if source is None:
        return None
    try:
        return source.get(name, None)
    except Exception:
        return None


def deployment_setting(
    name: str,
    *,
    secrets: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
    default: str = "",
) -> str:
    """Read deployment settings with Streamlit secrets taking priority."""
    secret_value = _mapping_value(secrets, name)
    if secret_value is not None:
        return str(secret_value)
    environment = os.environ if environ is None else environ
    env_value = environment.get(name)
    if env_value is not None:
        return str(env_value)
    return str(default)


def resolve_app_mode(
    *,
    secrets: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Resolve APP_MODE and translate the deprecated review-mode flag."""
    explicit = deployment_setting(
        "APP_MODE",
        secrets=secrets,
        environ=environ,
        default="",
    ).strip().lower()
    if explicit:
        if explicit not in VALID_APP_MODES:
            raise RuntimeConfigurationError("APP_MODE must be production or competition.")
        return explicit
    legacy = deployment_setting(
        "PEDSIM_PUBLIC_REVIEW_MODE",
        secrets=secrets,
        environ=environ,
        default="false",
    ).strip().lower()
    return APP_MODE_COMPETITION if legacy in TRUE_VALUES else APP_MODE_PRODUCTION


@dataclass(frozen=True)
class CompetitionCredentials:
    review_code: str
    admin_code: str

    @property
    def review_configured(self) -> bool:
        return bool(self.review_code)

    @property
    def admin_configured(self) -> bool:
        return bool(self.admin_code)


def competition_credentials(
    *,
    secrets: Optional[Mapping[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> CompetitionCredentials:
    return CompetitionCredentials(
        review_code=deployment_setting(
            "COMPETITION_REVIEW_CODE",
            secrets=secrets,
            environ=environ,
        ).strip(),
        admin_code=deployment_setting(
            "COMPETITION_ADMIN_CODE",
            secrets=secrets,
            environ=environ,
        ).strip(),
    )
