from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.knowledge_rules_fixture import get_engine


class RealCaseDemoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()
        cls.cases = json.loads((Path(__file__).resolve().parents[1] / "data" / "demos" / "real_case_demos.json").read_text(encoding="utf-8"))

    def test_real_cases(self) -> None:
        for case in self.cases:
            with self.subTest(case_id=case["case_id"]):
                result = self.engine.classify_case(profile=case["profile"], question=case["question"])
                self.assertEqual(result.primary_case_code, case["expected_primary"])
                self.assertEqual(result.intent, case["expected_intent"])
                self.assertEqual(result.status, case["expected_status"])
                for expected_candidate in case["expected_candidates"]:
                    self.assertIn(expected_candidate, result.case_codes or result.candidate_case_codes)
                self.assertTrue(result.reason_chain)
