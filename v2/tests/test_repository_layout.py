from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v2"


class RepositoryLayoutTests(unittest.TestCase):
    def test_source_branch_has_one_product_tree(self) -> None:
        allowed = {".github", ".gitignore", "README.md", "index.html", "v2"}
        visible = {path.name for path in ROOT.iterdir() if path.name != ".git"}
        self.assertEqual(visible, allowed)
        for retired in ("v1", "v3", "soe-radar", "v2-hourly-dashboard"):
            self.assertFalse((ROOT / retired).exists())

    def test_tracked_files_exclude_runtime_and_binary_source_documents(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        paths = [
            Path(value.decode())
            for value in result.stdout.split(b"\0")
            if value
        ]
        forbidden_parts = {
            "__pycache__",
            ".runtime",
            "raw-documents",
            "runs",
            "releases",
            "outputs",
        }
        for path in paths:
            self.assertFalse(forbidden_parts.intersection(path.parts), path)
            self.assertNotIn(path.suffix.lower(), {".pdf", ".txt"}, path)
            self.assertLess((ROOT / path).stat().st_size, 5 * 1024 * 1024, path)

    def test_v2_contract_has_no_legacy_runtime_path(self) -> None:
        contract = json.loads(
            (V2 / "config/source-contract.json").read_text(encoding="utf-8")
        )
        serialized = json.dumps(contract, ensure_ascii=False).lower()
        self.assertNotIn('"v1', serialized)
        self.assertNotIn('"v3', serialized)
        self.assertTrue(
            all(
                str(value).startswith("v2/")
                for key, value in contract.items()
                if key.endswith(("Directory", "Universe", "Taxonomy", "Events"))
                or key
                in {
                    "privateAnnual",
                    "eventStore",
                    "observationPool",
                    "maSources",
                    "tenderSources",
                }
            )
        )

    def test_public_readme_identifies_v2_as_current(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("主分支只保留 V2", readme)
        self.assertIn("53fb935994d3", readme)
        self.assertIn("不进入主分支", readme)


if __name__ == "__main__":
    unittest.main()
