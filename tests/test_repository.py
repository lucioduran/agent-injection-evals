import json
import re
import unittest
from pathlib import Path

from injection_evals.core import SECRET, STRATEGIES
from injection_evals.experiment import verify
from injection_evals.model import CONFIG, MODEL_ID, REVISION


class RepositoryTests(unittest.TestCase):
    def test_readme_contract_and_text(self):
        headings = re.findall(r"^## (.+)$", Path("README.md").read_text(), re.M)
        self.assertEqual(
            headings,
            [
                "Problem",
                "Scope",
                "Quick start",
                "Usage",
                "Architecture",
                "Reproduction",
                "Results",
                "Testing",
                "Limitations",
                "Contributing",
                "License",
            ],
        )
        paths = [Path("README.md"), Path("CONTRIBUTING.md"), Path("SECURITY.md")]
        for folder in ("injection_evals", "tests", "data", "docs", "results"):
            paths += [
                p for p in Path(folder).rglob("*") if p.suffix in (".py", ".md", ".json", ".jsonl")
            ]
        for path in paths:
            self.assertNotIn(chr(0x2014), path.read_text(encoding="utf-8"), str(path))

    def test_recorded_neural_evidence(self):
        for split, count in (("dev", 40), ("eval", 120)):
            path = Path("results") / split / "report.json"
            self.assertEqual(verify(path, Path("data/tasks.json"))["trials"], count)
            report = json.loads(path.read_text())
            metadata = report["metadata"]
            self.assertEqual(metadata["model_id"], MODEL_ID)
            self.assertEqual(metadata["model_revision"], REVISION)
            self.assertEqual(metadata["configuration"], CONFIG)
            self.assertEqual(
                metadata["model_files"], json.loads(Path("data/model-hashes.json").read_text())
            )
            self.assertFalse(metadata["working_tree_dirty"])
            rows = [
                json.loads(line) for line in path.with_name("trace.jsonl").read_text().splitlines()
            ]
            indexed = {(r["task_id"], r["variant"], r["strategy"]): r for r in rows}
            for row in rows:
                self.assertIsNone(row["error"])
                self.assertGreater(row["generation"]["input_tokens"], 0)
                self.assertGreater(row["generation"]["output_tokens"], 0)
                pair = {
                    "baseline": "policy",
                    "policy": "baseline",
                    "isolation": "combined",
                    "combined": "isolation",
                }[row["strategy"]]
                other = indexed[row["task_id"], row["variant"], pair]
                self.assertEqual(row["generation"]["output"], other["generation"]["output"])
            if split == "eval":
                for strategy in STRATEGIES:
                    group = [r for r in rows if r["strategy"] == strategy]
                    self.assertEqual(sum(SECRET in r["generation"]["output"] for r in group), 0)
