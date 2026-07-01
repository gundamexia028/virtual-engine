from __future__ import annotations

import argparse
from getpass import getpass
import json
from pathlib import Path
import sys
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from peds_anaphylaxis_sim.org_credentials import build_credential  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a salted unit-administrator credential record.",
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=("clinical_admin", "academy_admin"),
    )
    parser.add_argument(
        "--organization-type",
        required=True,
        choices=("clinical", "academy"),
    )
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--hospital-name", default="")
    parser.add_argument("--department-name", default="")
    parser.add_argument("--school-name", default="")
    parser.add_argument(
        "--format",
        choices=("json", "toml"),
        default="json",
    )
    return parser.parse_args()


def build_record(args: argparse.Namespace, code: str) -> Dict[str, Any]:
    credential = build_credential(
        code,
        args.role,
        args.organization_type,
        args.organization_id,
    )
    return {
        "organization_id": args.organization_id,
        "organization_type": args.organization_type,
        "role": args.role,
        "school_name": args.school_name,
        "hospital_name": args.hospital_name,
        "department_name": args.department_name,
        "credential": credential,
        "permissions": ["view", "export"],
        "status": "active",
    }


def _toml_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def record_to_toml(record: Dict[str, Any]) -> str:
    lines = ["[[ORG_ACCESS_RECORDS]]"]
    for key in (
        "organization_id",
        "organization_type",
        "role",
        "school_name",
        "hospital_name",
        "department_name",
    ):
        lines.append(f"{key} = {_toml_string(record[key])}")
    permissions = ", ".join(_toml_string(item) for item in record["permissions"])
    lines.append(f"permissions = [{permissions}]")
    lines.append(f"status = {_toml_string(record['status'])}")
    lines.append("")
    lines.append("[ORG_ACCESS_RECORDS.credential]")
    credential = record["credential"]
    lines.append(f"algorithm = {_toml_string(credential['algorithm'])}")
    lines.append(f"iterations = {credential['iterations']}")
    lines.append(f"salt = {_toml_string(credential['salt'])}")
    lines.append(f"digest = {_toml_string(credential['digest'])}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    first = getpass("Unit administrator management code: ")
    second = getpass("Confirm management code: ")
    if first != second:
        print("Management codes do not match.", file=sys.stderr)
        return 2
    try:
        record = build_record(args, first)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.format == "toml":
        print(record_to_toml(record))
    else:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
