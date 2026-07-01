import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PEDSIM_RESULTS_DIR", str(ROOT.parent / "V1.3.8_org_credential_temp"))
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402


CLINICAL_CODE = secrets.token_urlsafe(24) + "Aa1!"
ACADEMY_CODE = secrets.token_urlsafe(24) + "Bb2!"
WRONG_CODE = secrets.token_urlsafe(24) + "Cc3!"
LEGACY_CODE = "-".join(("ACD", "DEMO", "NURS", "7!Legacy"))


def credential(code, role, organization_type, organization_id):
    return app.org_credentials.build_credential(
        code,
        role,
        organization_type,
        organization_id,
        iterations=1_000,
    )


def record(
    code=CLINICAL_CODE,
    role="clinical_admin",
    organization_type="clinical",
    organization_id="CLN_SECURE_A",
):
    return {
        "organization_id": organization_id,
        "organization_type": organization_type,
        "role": role,
        "hospital_name": "自动测试安全医院" if organization_type == "clinical" else "",
        "department_name": "自动测试护理单元",
        "school_name": "自动测试安全学院" if organization_type == "academy" else "",
        "credential": credential(
            code,
            role,
            organization_type,
            organization_id,
        ),
        "permissions": ["view", "export"],
        "status": "active",
    }


class OrgCredentialSecurityTests(unittest.TestCase):
    def setUp(self):
        self.min_iterations = patch.object(
            app.org_credentials,
            "MIN_ITERATIONS",
            1_000,
        )
        self.min_iterations.start()
        self.temp = tempfile.TemporaryDirectory(prefix="v138-org-code-", dir=ROOT.parent)
        self.config = Path(self.temp.name) / "org_access_codes.json"
        self.path_patch = patch.object(app, "ORG_ACCESS_CODES_PATH", self.config)
        self.st_patch = patch.object(app, "st", SimpleNamespace(secrets={}))
        self.path_patch.start()
        self.st_patch.start()

    def tearDown(self):
        self.st_patch.stop()
        self.path_patch.stop()
        self.temp.cleanup()
        self.min_iterations.stop()

    def write(self, records):
        self.config.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_01_correct_clinical_hash_enters_bound_scope(self):
        self.write([record()])
        scope = app.find_org_scope_by_code(CLINICAL_CODE)
        self.assertEqual(scope["role"], "clinical_admin")
        self.assertEqual(scope["organization_type"], "clinical")
        self.assertEqual(scope["organization_id"], "CLN_SECURE_A")

    def test_02_correct_academy_hash_enters_bound_scope(self):
        self.write([
            record(
                ACADEMY_CODE,
                "academy_admin",
                "academy",
                "ACD_SECURE_A",
            )
        ])
        scope = app.find_org_scope_by_code(ACADEMY_CODE)
        self.assertEqual(scope["role"], "academy_admin")
        self.assertEqual(scope["organization_type"], "academy")
        self.assertEqual(scope["organization_id"], "ACD_SECURE_A")

    def test_03_wrong_code_is_rejected(self):
        self.write([record()])
        self.assertIsNone(app.find_org_scope_by_code(WRONG_CODE))

    def test_04_plaintext_configuration_is_rejected(self):
        item = record()
        item.pop("credential")
        item["admin_code"] = CLINICAL_CODE
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_05_legacy_unsalted_sha256_configuration_is_rejected(self):
        item = record()
        item.pop("credential")
        item["admin_code_hash"] = "0" * 64
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_06_legacy_default_style_code_cannot_be_used(self):
        item = record()
        item.pop("credential")
        item["admin_code"] = LEGACY_CODE
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(LEGACY_CODE))

    def test_07_missing_salt_is_rejected(self):
        item = record()
        item["credential"].pop("salt")
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_08_missing_digest_is_rejected(self):
        item = record()
        item["credential"].pop("digest")
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_09_missing_or_invalid_organization_id_is_rejected(self):
        missing = record()
        missing.pop("organization_id")
        invalid = record()
        invalid["organization_id"] = "invalid organization"
        for item in (missing, invalid):
            with self.subTest(organization_id=item.get("organization_id", "missing")):
                self.write([item])
                self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_10_missing_role_is_rejected(self):
        item = record()
        item.pop("role")
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_11_missing_organization_type_is_rejected(self):
        item = record()
        item.pop("organization_type")
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_12_clinical_credential_cannot_authenticate_academy_identity(self):
        item = record()
        item["role"] = "academy_admin"
        item["organization_type"] = "academy"
        item["organization_id"] = "ACD_SECURE_A"
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_13_unit_credential_cannot_create_platform_scope(self):
        item = record()
        item["role"] = "platform_admin"
        item["organization_type"] = "platform"
        item["organization_id"] = "PLATFORM"
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_14_same_code_uses_distinct_salts_and_ambiguous_login_is_rejected(self):
        first = record()
        second = record(
            CLINICAL_CODE,
            "clinical_admin",
            "clinical",
            "CLN_SECURE_B",
        )
        self.assertNotEqual(first["credential"]["salt"], second["credential"]["salt"])
        self.assertNotEqual(first["credential"]["digest"], second["credential"]["digest"])
        self.write([first, second])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_15_invalid_iteration_count_is_rejected(self):
        item = record()
        item["credential"]["iterations"] = 999
        self.write([item])
        self.assertIsNone(app.find_org_scope_by_code(CLINICAL_CODE))

    def test_16_digest_comparison_uses_constant_time_primitive(self):
        item = record()
        with patch.object(
            app.org_credentials.secrets,
            "compare_digest",
            wraps=app.org_credentials.secrets.compare_digest,
        ) as compare:
            self.assertTrue(
                app.org_credentials.verify_credential(
                    CLINICAL_CODE,
                    item["credential"],
                    item["role"],
                    item["organization_type"],
                    item["organization_id"],
                )
            )
        compare.assert_called_once()

    def test_17_generator_uses_getpass_and_never_outputs_plaintext(self):
        tool_path = ROOT / "tools" / "generate_org_admin_credential.py"
        spec = importlib.util.spec_from_file_location("org_code_tool", tool_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        argv = [
            str(tool_path),
            "--role",
            "clinical_admin",
            "--organization-type",
            "clinical",
            "--organization-id",
            "CLN_TOOL_A",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(sys, "argv", argv), \
                patch.object(module, "getpass", side_effect=[CLINICAL_CODE, CLINICAL_CODE]), \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(module.main(), 0)
        output = stdout.getvalue()
        parsed = json.loads(output)
        self.assertNotIn(CLINICAL_CODE, output)
        self.assertIn("credential", parsed)
        self.assertEqual(stderr.getvalue(), "")

    def test_18_source_and_runtime_artifacts_have_no_usable_plaintext_code(self):
        source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        tool_source = (
            ROOT / "tools" / "generate_org_admin_credential.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('item.get("admin_code")', source)
        self.assertNotIn("admin_code_hash", source)
        self.assertNotIn("import streamlit_app", tool_source)
        item = record()
        serialized = json.dumps(item, ensure_ascii=False)
        self.assertNotIn(CLINICAL_CODE, serialized)

    def test_19_hashed_record_can_be_loaded_from_streamlit_secrets(self):
        item = record()
        with patch.object(
            app,
            "st",
            SimpleNamespace(secrets={"ORG_ACCESS_RECORDS": [item]}),
        ):
            scope = app.find_org_scope_by_code(CLINICAL_CODE)
        self.assertEqual(scope["organization_id"], "CLN_SECURE_A")

    def test_20_generator_toml_output_is_valid_secrets_structure(self):
        tool_path = ROOT / "tools" / "generate_org_admin_credential.py"
        spec = importlib.util.spec_from_file_location("org_code_tool_toml", tool_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        argv = [
            str(tool_path),
            "--role",
            "academy_admin",
            "--organization-type",
            "academy",
            "--organization-id",
            "ACD_TOOL_A",
            "--format",
            "toml",
        ]
        stdout = io.StringIO()
        with patch.object(sys, "argv", argv), \
                patch.object(module, "getpass", side_effect=[ACADEMY_CODE, ACADEMY_CODE]), \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(module.main(), 0)
        output = stdout.getvalue()
        parsed = tomllib.loads(output)
        self.assertNotIn(ACADEMY_CODE, output)
        self.assertEqual(
            parsed["ORG_ACCESS_RECORDS"][0]["organization_id"],
            "ACD_TOOL_A",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
