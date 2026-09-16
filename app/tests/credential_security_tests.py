import ast
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class DummySessionState(dict):
    def __getattr__(self, key):
        return self.get(key, "")

    def __setattr__(self, key, value):
        self[key] = value


def _cache_passthrough(*args, **kwargs):
    def wrapper(func):
        return func
    return wrapper


class DummyStreamlit(types.SimpleNamespace):
    def __getattr__(self, name):
        def noop(*args, **kwargs):
            return None
        return noop


if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = DummyStreamlit(
        session_state=DummySessionState(),
        secrets={},
        cache_resource=_cache_passthrough,
        cache_data=_cache_passthrough,
        fragment=_cache_passthrough,
    )


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit_app as app  # noqa: E402


TEST_ACCESS = "LocalAccess-7f2Qm9"
TEST_ADMIN = "Admin-4vX!8pL2s"


class StopSignal(RuntimeError):
    pass


class RaisingSecrets:
    def get(self, name, default=None):
        raise RuntimeError("simulated secrets read failure")


class AuthTestStreamlit(DummyStreamlit):
    def __init__(self, secrets):
        super().__init__(session_state=DummySessionState(), secrets=secrets)
        self.errors = []
        self.captions = []

    def error(self, message):
        self.errors.append(str(message))

    def caption(self, message):
        self.captions.append(str(message))

    def stop(self):
        raise StopSignal("streamlit execution stopped")


@contextmanager
def auth_context(secrets, environment=None):
    fake_st = AuthTestStreamlit(secrets)
    with patch.object(app, "st", fake_st), patch.dict(os.environ, environment or {}, clear=True):
        yield fake_st


def function_call_names(function_name):
    tree = ast.parse((ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    names = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return names


class CredentialConfigurationTests(unittest.TestCase):
    def test_valid_credentials_are_loaded_and_trimmed(self):
        with auth_context({
            "APP_ACCESS_CODE": f"  {TEST_ACCESS}  ",
            "ADMIN_PASSWORD": f"  {TEST_ADMIN}  ",
        }):
            self.assertEqual(app.get_auth_credentials(), (TEST_ACCESS, TEST_ADMIN))

    def test_missing_access_code_fails(self):
        with auth_context({"ADMIN_PASSWORD": TEST_ADMIN}):
            with self.assertRaises(app.AuthConfigurationError) as caught:
                app.get_auth_credentials()
        self.assertEqual(caught.exception.invalid_fields, ("APP_ACCESS_CODE",))

    def test_missing_admin_password_fails(self):
        with auth_context({"APP_ACCESS_CODE": TEST_ACCESS}):
            with self.assertRaises(app.AuthConfigurationError) as caught:
                app.get_auth_credentials()
        self.assertEqual(caught.exception.invalid_fields, ("ADMIN_PASSWORD",))

    def test_both_credentials_missing_fails(self):
        with auth_context({}):
            with self.assertRaises(app.AuthConfigurationError) as caught:
                app.get_auth_credentials()
        self.assertEqual(
            caught.exception.invalid_fields,
            ("APP_ACCESS_CODE", "ADMIN_PASSWORD"),
        )

    def test_empty_access_code_fails(self):
        with auth_context({"APP_ACCESS_CODE": "", "ADMIN_PASSWORD": TEST_ADMIN}):
            with self.assertRaises(app.AuthConfigurationError) as caught:
                app.get_auth_credentials()
        self.assertEqual(caught.exception.invalid_fields, ("APP_ACCESS_CODE",))

    def test_empty_admin_password_fails(self):
        with auth_context({"APP_ACCESS_CODE": TEST_ACCESS, "ADMIN_PASSWORD": ""}):
            with self.assertRaises(app.AuthConfigurationError) as caught:
                app.get_auth_credentials()
        self.assertEqual(caught.exception.invalid_fields, ("ADMIN_PASSWORD",))

    def test_whitespace_only_credentials_fail(self):
        with auth_context({"APP_ACCESS_CODE": "   ", "ADMIN_PASSWORD": "\t"}):
            with self.assertRaises(app.AuthConfigurationError) as caught:
                app.get_auth_credentials()
        self.assertEqual(
            caught.exception.invalid_fields,
            ("APP_ACCESS_CODE", "ADMIN_PASSWORD"),
        )

    def test_non_string_credentials_fail(self):
        with auth_context({"APP_ACCESS_CODE": 1234, "ADMIN_PASSWORD": True}):
            with self.assertRaises(app.AuthConfigurationError):
                app.get_auth_credentials()

    def test_secrets_read_exception_fails_even_with_environment_values(self):
        environment = {
            "APP_ACCESS_CODE": TEST_ACCESS,
            "ADMIN_PASSWORD": TEST_ADMIN,
        }
        with auth_context(RaisingSecrets(), environment):
            with self.assertRaises(app.AuthConfigurationError):
                app.get_auth_credentials()

    def test_missing_secrets_cannot_fall_back_to_environment_values(self):
        environment = {
            "APP_ACCESS_CODE": TEST_ACCESS,
            "ADMIN_PASSWORD": TEST_ADMIN,
        }
        with auth_context({}, environment):
            with self.assertRaises(app.AuthConfigurationError) as caught:
                app.get_auth_credentials()
        self.assertEqual(
            caught.exception.invalid_fields,
            ("APP_ACCESS_CODE", "ADMIN_PASSWORD"),
        )

    def test_access_and_admin_credentials_must_differ(self):
        with auth_context({
            "APP_ACCESS_CODE": TEST_ACCESS,
            "ADMIN_PASSWORD": TEST_ACCESS,
        }):
            with self.assertRaises(app.AuthConfigurationError):
                app.get_auth_credentials()

    def test_missing_configuration_stops_ordinary_entry(self):
        with auth_context({}) as fake_st:
            with self.assertRaises(StopSignal):
                app.require_app_access()
        self.assertEqual(fake_st.errors, [app.AUTH_CONFIGURATION_ERROR_MESSAGE])

    def test_missing_configuration_stops_admin_entry(self):
        with auth_context({}) as fake_st, patch.object(app, "compact_header", lambda: None):
            with self.assertRaises(StopSignal):
                app.render_admin_page()
        self.assertEqual(fake_st.errors, [app.AUTH_CONFIGURATION_ERROR_MESSAGE])

    def test_configuration_error_does_not_expose_values(self):
        with auth_context({"APP_ACCESS_CODE": TEST_ACCESS}) as fake_st:
            with self.assertRaises(StopSignal):
                app.require_auth_credentials()
        visible_messages = "\n".join(fake_st.errors + fake_st.captions)
        self.assertNotIn(TEST_ACCESS, visible_messages)
        self.assertNotIn(TEST_ADMIN, visible_messages)
        self.assertIn("ADMIN_PASSWORD", visible_messages)

    def test_correct_access_code_matches(self):
        self.assertTrue(app.credential_matches(TEST_ACCESS, TEST_ACCESS))

    def test_wrong_access_code_is_rejected(self):
        self.assertFalse(app.credential_matches("wrong-access", TEST_ACCESS))

    def test_correct_admin_password_matches(self):
        self.assertTrue(app.credential_matches(TEST_ADMIN, TEST_ADMIN))

    def test_wrong_admin_password_is_rejected(self):
        self.assertFalse(app.credential_matches("wrong-admin", TEST_ADMIN))

    def test_access_flow_has_no_default_credential_reader(self):
        names = function_call_names("require_app_access")
        self.assertIn("require_auth_credentials", names)
        self.assertNotIn("get_secret_value", names)

    def test_admin_flow_has_no_default_credential_reader(self):
        names = function_call_names("render_admin_page")
        self.assertIn("require_auth_credentials", names)
        self.assertNotIn("get_secret_value", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
