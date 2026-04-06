from __future__ import annotations

import unittest
from pathlib import Path

from app.evaluation import evaluate_dataset


class RedTeamSuiteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.dataset = self.root / "evals" / "datasets" / "redteam.json"
        self.failure_modes = self.root / "evals" / "failure_modes" / "top20.json"
        self.policy = self.root / "data" / "seed" / "openclaw_policy.json"

    def test_redteam_suite_runs(self) -> None:
        summary = evaluate_dataset(
            dataset_path=self.dataset,
            failure_modes_path=self.failure_modes,
            policy_path=self.policy,
        )
        self.assertGreaterEqual(summary["total_cases"], 10)
        self.assertIn("hallucination_rate", summary["metrics"])

    def test_selected_safety_cases_pass(self) -> None:
        summary = evaluate_dataset(
            dataset_path=self.dataset,
            failure_modes_path=self.failure_modes,
            policy_path=self.policy,
        )
        cases = {item["id"]: item for item in summary["results"]}
        self.assertTrue(cases["rt-group-pii-no-echo"]["overall_pass"])
        self.assertTrue(cases["rt-openclaw-mentionless-group"]["overall_pass"])
        self.assertTrue(cases["rt-openclaw-unpaired-direct"]["overall_pass"])
        self.assertTrue(cases["rt-openclaw-routing-key"]["overall_pass"])


if __name__ == "__main__":
    unittest.main()
