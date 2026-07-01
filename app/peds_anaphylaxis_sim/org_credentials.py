from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from typing import Any, Dict, Optional


ALGORITHM = "pbkdf2_hmac_sha256"
DEFAULT_ITERATIONS = 600_000
MIN_ITERATIONS = 200_000
MAX_ITERATIONS = 2_000_000
SALT_BYTES = 16
DIGEST_BYTES = 32
MIN_CODE_LENGTH = 20
MAX_CODE_LENGTH = 256


def valid_admin_code(code: object) -> bool:
    if not isinstance(code, str):
        return False
    if code != code.strip() or not (MIN_CODE_LENGTH <= len(code) <= MAX_CODE_LENGTH):
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in code):
        return False
    character_classes = (
        any(char.islower() for char in code),
        any(char.isupper() for char in code),
        any(char.isdigit() for char in code),
        any(not char.isalnum() for char in code),
    )
    return sum(character_classes) >= 3


def valid_identity(role: object, organization_type: object, organization_id: object) -> bool:
    expected_type = {
        "clinical_admin": "clinical",
        "academy_admin": "academy",
    }.get(role)
    return bool(
        expected_type
        and organization_type == expected_type
        and isinstance(organization_id, str)
        and bool(re.fullmatch(r"[A-Z][A-Z0-9_-]{2,63}", organization_id))
    )


def _identity_binding(role: str, organization_type: str, organization_id: str) -> bytes:
    payload = json.dumps(
        [role, organization_type, organization_id],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return payload.encode("ascii")


def _derive_digest(
    code: str,
    salt: bytes,
    iterations: int,
    role: str,
    organization_type: str,
    organization_id: str,
) -> bytes:
    material = _identity_binding(role, organization_type, organization_id) + b"\0" + code.encode("utf-8")
    return hashlib.pbkdf2_hmac(
        "sha256",
        material,
        salt,
        iterations,
        dklen=DIGEST_BYTES,
    )


def build_credential(
    code: str,
    role: str,
    organization_type: str,
    organization_id: str,
    *,
    iterations: int = DEFAULT_ITERATIONS,
) -> Dict[str, Any]:
    if not valid_admin_code(code):
        raise ValueError("Management code does not meet the security requirements.")
    if not valid_identity(role, organization_type, organization_id):
        raise ValueError("Role and organization identity do not match.")
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        raise ValueError("PBKDF2 iteration count is outside the accepted range.")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive_digest(
        code,
        salt,
        iterations,
        role,
        organization_type,
        organization_id,
    )
    return {
        "algorithm": ALGORITHM,
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "digest": base64.b64encode(digest).decode("ascii"),
    }


def normalize_credential(value: object) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    if value.get("algorithm") != ALGORITHM:
        return None
    iterations = value.get("iterations")
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        return None
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        return None
    try:
        salt = base64.b64decode(str(value.get("salt", "")), validate=True)
        digest = base64.b64decode(str(value.get("digest", "")), validate=True)
    except (ValueError, TypeError):
        return None
    if len(salt) != SALT_BYTES or len(digest) != DIGEST_BYTES:
        return None
    return {
        "algorithm": ALGORITHM,
        "iterations": iterations,
        "salt": base64.b64encode(salt).decode("ascii"),
        "digest": base64.b64encode(digest).decode("ascii"),
    }


def verify_credential(
    code: object,
    credential: object,
    role: str,
    organization_type: str,
    organization_id: str,
) -> bool:
    if not valid_admin_code(code):
        return False
    if not valid_identity(role, organization_type, organization_id):
        return False
    normalized = normalize_credential(credential)
    if normalized is None:
        return False
    salt = base64.b64decode(normalized["salt"], validate=True)
    expected = base64.b64decode(normalized["digest"], validate=True)
    candidate = _derive_digest(
        code,
        salt,
        normalized["iterations"],
        role,
        organization_type,
        organization_id,
    )
    return secrets.compare_digest(candidate, expected)
