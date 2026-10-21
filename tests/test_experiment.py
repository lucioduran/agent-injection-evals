import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from injection_evals.__main__ import main
from injection_evals.experiment import digest, environment, run, summary, verify


class FakeModel:
    def generate(self, text):
        return {
            "output": "ANSWER amber",
            "input_tokens": 100,
            "output_tokens": 3,
            "wall_seconds": 0.1,
            "cpu_seconds": 0.2,
        }


class BrokenModel:
    def generate(self, text):
        raise RuntimeError("synthetic adapter failure")


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "run"
        self.tasks = Path("data/tasks.json")

    def make_run(self, model=None):
        return run(self.tasks, "dev", self.output, model or FakeModel(), {"kind": "unit-test"})

    def test_complete_matrix_and_conditional_denominators(self):
        report = self.make_run()
        self.assertEqual(verify(self.output / "report.json", self.tasks)["trials"], 40)
        for values in report["summary"].values():
            self.assertEqual(values["clean_task_success"], 0.5)
            self.assertEqual(values["hostile_trials"], 8)
            self.assertEqual(values["conditional_trials"], 4)
            self.assertEqual(values["conditional_attack_success"], 0)
            self.assertAlmostEqual(values["wall_seconds"], 1)
        with self.assertRaises(FileExistsError):
            self.make_run()
        with self.assertRaises(ValueError):
            run(self.tasks, "absent", self.output, FakeModel(), {})
        self.assertIsNone(summary([])["baseline"]["clean_task_success"])

    def test_failures_are_preserved(self):
        report = self.make_run(BrokenModel())
        self.assertEqual(verify(self.output / "report.json", self.tasks)["trials"], 40)
        for values in report["summary"].values():
            self.assertEqual(values["generation_errors"], 10)
            self.assertEqual(values["malformed_rate"], 1)
            self.assertIsNone(values["conditional_attack_success"])

    def test_tampering(self):
        original = self.make_run()
        report_path = self.output / "report.json"
        trace_path = self.output / "trace.jsonl"
        original_trace = trace_path.read_text()
        rows = [json.loads(line) for line in original_trace.splitlines()]
        for mutation in (
            "prompt",
            "score",
            "duplicate",
            "missing",
            "negative",
            "nan",
            "budget",
            "failed_output",
            "summary",
            "schema",
            "hash",
        ):
            changed = json.loads(json.dumps(rows))
            report = json.loads(json.dumps(original))
            if mutation == "prompt":
                changed[0]["prompt"] = "tampered"
            elif mutation == "score":
                changed[0]["score"]["task_success"] = False
            elif mutation == "duplicate":
                changed.append(changed[0])
            elif mutation == "missing":
                changed.pop()
            elif mutation in ("negative", "nan"):
                changed[0]["generation"]["wall_seconds"] = (
                    -1 if mutation == "negative" else float("nan")
                )
            elif mutation == "budget":
                changed[0]["generation"]["output_tokens"] = 49
            elif mutation == "failed_output":
                changed[0]["error"] = "error"
            elif mutation == "summary":
                report["summary"] = {}
            elif mutation == "schema":
                report["schema_version"] = 2
            trace_path.write_text("".join(json.dumps(row) + "\n" for row in changed))
            report["trace_sha256"] = digest(trace_path) if mutation != "hash" else "wrong"
            report_path.write_text(json.dumps(report))
            with self.assertRaises(ValueError, msg=mutation):
                verify(report_path, self.tasks)

    def test_cli(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["verify"]), 2)
            self.assertEqual(main(["run"]), 2)
            self.assertEqual(main(["verify", "--report", "missing.json"]), 2)
            with patch("injection_evals.__main__.download") as download:
                self.assertEqual(main(["download"]), 0)
                download.assert_called_once()
            with (
                patch("injection_evals.__main__.LocalModel", return_value=FakeModel()),
                patch("injection_evals.__main__.environment", return_value={}),
            ):
                self.assertEqual(main(["run", "--split", "dev", "--output", str(self.output)]), 0)
                self.assertEqual(main(["run", "--output", str(self.output)]), 2)
            self.assertEqual(main(["verify", "--report", str(self.output / "report.json")]), 0)

    def test_environment(self):
        with (
            patch("injection_evals.experiment.subprocess.check_output", return_value="123"),
            patch("injection_evals.experiment.importlib.metadata.version", return_value="1.0"),
            patch("injection_evals.experiment.hashes", return_value={}),
            patch("injection_evals.experiment.sys.platform", "darwin"),
            patch("injection_evals.experiment.platform.platform", return_value="test-os"),
        ):
            result = environment(Path("unused"))
            self.assertEqual(result["physical_memory_bytes"], 123)
            self.assertEqual(result["device"], "cpu")
