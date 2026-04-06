from __future__ import annotations

import unittest
from pathlib import Path

from app.models import OpenClawMessageRequest
from app.openclaw_security import OpenClawSecurityPolicy


class OpenClawSecurityTestCase(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.secure_policy = OpenClawSecurityPolicy.from_path(root / "evals" / "openclaw" / "policy.secure.json")
        self.insecure_policy = OpenClawSecurityPolicy.from_path(root / "evals" / "openclaw" / "policy.insecure.json")

    def test_secure_policy_passes_all_audits(self) -> None:
        findings = self.secure_policy.audit()
        self.assertTrue(findings)
        self.assertTrue(all(item.status == "pass" for item in findings))

    def test_insecure_policy_fails_all_required_checks(self) -> None:
        findings = self.insecure_policy.audit()
        self.assertEqual(len(findings), 5)
        self.assertTrue(all(item.status == "fail" for item in findings))

    def test_group_message_without_mention_is_blocked(self) -> None:
        assessment = self.secure_policy.assess_request(
            OpenClawMessageRequest(
                channel="feishu",
                target="random-group",
                message="这种情况能上吗？",
                is_group=True,
                mentioned=False,
                paired=False,
                dry_run=False,
            )
        )
        self.assertFalse(assessment.delivery_allowed)
        joined = "\n".join(item.detail for item in assessment.findings)
        self.assertIn("requireMention", joined)
        self.assertIn("pairing", joined)


if __name__ == "__main__":
    unittest.main()
