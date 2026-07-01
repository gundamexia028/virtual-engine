from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys
import tomllib
import unittest

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SYSTEM_VERSION = "V1.3.8"
PACKAGE_VERSION = "1.3.8"

HISTORICAL_FILE_HASHES = {
    "docs/V1.2.11_research_collection_locked_notes.md": "195b5f68e8aff707462f2414f34f06f995e7eb34b45e6b74e09c3a028d86a343",
    "docs/V1.3.1_dual_mode_qc_update.md": "77e61cf68b94eecb008e33e3b531c801c913dcf27b78f9968f0e84adf6527d48",
    "docs/V1.3.2_academy_anaphylaxis_rescue_update.md": "633481265b2edc5df4f897d436313b0e310ed775c3c185a7e4beb6a6284177c4",
    "docs/V1.3.3_academy_scenario_library_update.md": "3b344fd71f473f23377c17f484971e39da17c626eec898c51231ed4c3b73c832",
    "docs/V1.3.4_promotion_admin_academy_flow_update.md": "8c86bdcdfda05d1e8ad321b71bd395e7439d109e918a9b76a813d496dfe00b31",
    "docs/V1.3.5_academy_branching_enhanced_update.md": "5444635acb6227c111f7365961c3601b6a0c1467de4cad6f5b52bab4cee95729",
    "docs/V1.3.6_academy_post_test_completion_gate_fix.md": "5f172c4a10513069cc8dfe2c28c967ac06918c79f47811912d5241b892c98b10",
    "docs/V1.3.7_academy_safety_scoring_fix.md": "d6d8f04bc0d3e4c66467c4ae415103bb1e5528e907c0eec92444bfb0aa669868",
    "docs/V1.3.8_academy_teacher_trial_manual.md": "57ec27a7d506dec870fdc9274d54177aad77e1753c9a24cee9b84430248ad1d0",
    "docs/V1.3.8_academy_teacher_trial_ui_display_fix.md": "f186639cb65887a8a142c987f0beea30be176d9516249a1752033d92189e28ad",
    "peds_anaphylaxis_sim/README.md": "f44b13b33e1f3b987e39a39ff3548f7ae22d7a12b8b8c764de403782894ceb11",
}

SCENARIO_FILE_HASHES = {
    "peds_anaphylaxis_sim/scenarios/peds_ward_allergy_academy_initial.json": "ea4b0602126b2d9d93c4a9eb56b7bf95d4b52b6caea3d67acc0b372687adebee",
    "peds_anaphylaxis_sim/scenarios/peds_ward_allergy_academy_variant.json": "694d19aa42be2ca3151bf730d9eb9836031e4adc578a4a7359948c68b1b4e475",
    "peds_anaphylaxis_sim/scenarios/peds_ward_anaphylaxis_iv_initial.json": "6d181f88c8b6c3820927c58e98faa8464d8ac89501e0f67f4c5b108b511c7113",
    "peds_anaphylaxis_sim/scenarios/peds_ward_anaphylaxis_iv_variantA.json": "add6094c640b995958c213ae179b3424797e6434cd0fa676a91230c5643b402d",
}


def file_hash(relative_path: str) -> str:
    return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()


def assignment_value(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node.value
    raise AssertionError(f"Assignment not found: {name}")


class VersionConsistencyTests(unittest.TestCase):
    def test_package_metadata_defines_system_version(self):
        tree = ast.parse((ROOT / "peds_anaphylaxis_sim/__init__.py").read_text(encoding="utf-8"))
        package_value = assignment_value(tree, "__version__")
        system_value = assignment_value(tree, "SYSTEM_VERSION")
        self.assertIsInstance(package_value, ast.Constant)
        self.assertEqual(package_value.value, PACKAGE_VERSION)
        self.assertIsInstance(system_value, ast.JoinedStr)
        self.assertEqual(ast.unparse(system_value), "f'V{__version__}'")

    def test_application_uses_package_version_as_single_source(self):
        source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        app_value = assignment_value(tree, "APP_VERSION")
        self.assertIsInstance(app_value, ast.Name)
        self.assertEqual(app_value.id, "SYSTEM_VERSION")
        self.assertIn("from peds_anaphylaxis_sim import SYSTEM_VERSION", source)
        self.assertNotIn('APP_VERSION = "V', source)

    def test_page_version_displays_use_app_version(self):
        source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn("版本：{html.escape(APP_VERSION)}", source)
        self.assertIn('st.sidebar.title(f"{APP_VERSION} 控制台")', source)
        self.assertIn("管理者后台｜{APP_VERSION} 推广版权限管理版", source)
        self.assertNotIn("V1.3.3 控制台", source)
        self.assertNotIn("管理者后台｜V1.3.4", source)

    def test_readme_current_version_is_aligned(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith(f"# 护理动态分支虚拟仿真教学与培训系统｜{SYSTEM_VERSION}\n"))
        self.assertIn(f"当前系统版本：**{SYSTEM_VERSION}**", readme)
        self.assertIn("## V1.3.5 更新摘要", readme)

    def test_historical_version_documents_are_unchanged(self):
        actual = {path: file_hash(path) for path in HISTORICAL_FILE_HASHES}
        self.assertEqual(actual, HISTORICAL_FILE_HASHES)

    def test_scenario_and_schema_versions_are_unchanged(self):
        actual = {path: file_hash(path) for path in SCENARIO_FILE_HASHES}
        self.assertEqual(actual, SCENARIO_FILE_HASHES)
        for path in SCENARIO_FILE_HASHES:
            payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)

    def test_local_app_smoke_shows_aligned_version_and_mode_entries(self):
        access_code = tomllib.loads(
            (ROOT / ".streamlit/secrets.toml").read_text(encoding="utf-8")
        )["APP_ACCESS_CODE"]
        app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=15).run()
        version_markdown = [
            item.value
            for item in app.markdown
            if "<div class='version-corner'>版本：" in item.value
        ]
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            version_markdown,
            [
                "<div class='version-corner'>"
                f"版本：{SYSTEM_VERSION}｜仅用于护理教学、培训与科研</div>"
            ],
        )

        app.text_input[0].input("invalid-version-smoke")
        app.button[0].click().run()
        self.assertIn("访问码不正确。", [item.value for item in app.error])

        app.text_input[0].input(access_code)
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            [button.label for button in app.button],
            ["进入临床模式", "进入学院模式"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
