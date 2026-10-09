import importlib
from pathlib import Path
import tempfile
import unittest

m = importlib.import_module("research.model_research_2026_10_09.verify")


class CoverageTests(unittest.TestCase):
    def test_missing_and_extra_evidence_are_rejected(self):
        with tempfile.TemporaryDirectory() as location:
            folder = Path(location)
            expected = {"a.json", "b.json"}
            (folder / "a.json").touch()
            with self.assertRaisesRegex(ValueError, "Incomplete or extra evidence"):
                m.require_names(folder, "*.json", expected)
            (folder / "b.json").touch()
            m.require_names(folder, "*.json", expected)
            (folder / "unplanned.json").touch()
            with self.assertRaisesRegex(ValueError, "Incomplete or extra evidence"):
                m.require_names(folder, "*.json", expected)


if __name__ == "__main__":
    unittest.main()
