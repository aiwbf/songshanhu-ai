from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from app.evaluation import evaluate_dataset, write_report


class EvalRegressionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.dataset = self.root / "evals" / "datasets" / "core_regression.json"
        self.failure_modes = self.root / "evals" / "failure_modes" / "top20.json"
        self.policy = self.root / "data" / "seed" / "openclaw_policy.json"

    def test_core_eval_runs_and_writes_reports(self) -> None:
        summary = evaluate_dataset(
            dataset_path=self.dataset,
            failure_modes_path=self.failure_modes,
            policy_path=self.policy,
        )
        self.assertGreaterEqual(summary["total_cases"], 20)
        self.assertIn("classification_accuracy", summary["metrics"])
        self.assertIn("citation_correctness", summary["metrics"])
        self.assertIsNotNone(summary["policy_audit"])

        tmpdir = self.root / "data" / "generated" / "tmp_eval_regression"
        if tmpdir.exists():
            shutil.rmtree(tmpdir)
        tmpdir.mkdir(parents=True, exist_ok=True)
        try:
            write_report(
                summary,
                json_path=tmpdir / "eval.json",
                markdown_path=tmpdir / "eval.md",
            )
            self.assertTrue((tmpdir / "eval.json").exists())
            self.assertTrue((tmpdir / "eval.md").exists())
        finally:
            if tmpdir.exists():
                shutil.rmtree(tmpdir)

    def test_timeliness_release_blocker_case_is_present(self) -> None:
        summary = evaluate_dataset(
            dataset_path=self.dataset,
            failure_modes_path=self.failure_modes,
            policy_path=self.policy,
        )
        cases = {item["id"]: item for item in summary["results"]}
        self.assertIn("historical-policy-asked-as-current", cases)
        self.assertTrue(cases["historical-policy-asked-as-current"]["handoff_considered"])


if __name__ == "__main__":
    unittest.main()
