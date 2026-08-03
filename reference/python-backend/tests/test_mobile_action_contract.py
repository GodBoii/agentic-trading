import ast
import importlib.util
import re
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent


def load_contract_module():
    path = BACKEND_DIR / "mobile_action_contract.py"
    spec = importlib.util.spec_from_file_location("mobile_action_contract_for_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MobileActionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_contract_module()

    def test_go_home_is_intentionally_unexposed(self):
        self.assertNotIn("go_home", self.contract.EXPOSED_ACTIONS)
        self.assertIn("go_home", self.contract.INTENTIONALLY_UNEXPOSED_NATIVE_ACTIONS)

        toolkit_tree = ast.parse((BACKEND_DIR / "mobile_tools.py").read_text(encoding="utf-8"))
        public_methods = {
            node.name
            for node in ast.walk(toolkit_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
        }
        self.assertNotIn("go_home", public_methods)

    def test_every_exposed_action_has_a_backend_tool_method(self):
        toolkit_tree = ast.parse((BACKEND_DIR / "mobile_tools.py").read_text(encoding="utf-8"))
        public_methods = {
            node.name
            for node in ast.walk(toolkit_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
        }
        self.assertEqual(set(self.contract.EXPOSED_ACTIONS), public_methods)

    def test_native_policy_and_backend_contract_versions_match(self):
        java = (ROOT / "android/app/src/main/java/com/aetheria/ai/MobileActionPolicy.java").read_text(encoding="utf-8")
        match = re.search(r"CONTRACT_VERSION\s*=\s*(\d+)", java)
        self.assertIsNotNone(match)
        self.assertEqual(self.contract.CONTRACT_VERSION, int(match.group(1)))

    def test_native_policy_mentions_every_exposed_action(self):
        java = (ROOT / "android/app/src/main/java/com/aetheria/ai/MobileActionPolicy.java").read_text(encoding="utf-8")
        missing = [action for action in self.contract.EXPOSED_ACTIONS if f'"{action}"' not in java]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
