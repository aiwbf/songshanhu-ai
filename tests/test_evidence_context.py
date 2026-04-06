from __future__ import annotations

import unittest

from tests.knowledge_rules_fixture import get_engine


class EvidenceContextTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()

    def test_retrieve_evidence_prefers_official_sources(self) -> None:
        evidence = self.engine.retrieve_evidence(
            question="我有优才卡，工作地在松山湖，可以申请松山湖的学位吗？",
            profile={},
        )
        self.assertTrue(evidence["hits"])
        self.assertNotEqual(evidence["hits"][0]["source_type"], "business_faq")

    def test_retrieve_evidence_detects_current_cycle_warning(self) -> None:
        evidence = self.engine.retrieve_evidence(
            question="台湾学生入学怎样申请？",
            profile={},
        )
        self.assertTrue(any("2025" in item for item in evidence["warnings"]))

    def test_build_answer_context_returns_templates(self) -> None:
        result = self.engine.classify_case(
            profile={},
            question="如何申请企业账号？",
        )
        evidence = self.engine.retrieve_evidence(
            question="如何申请企业账号？",
            profile={},
        )
        context = self.engine.build_answer_context(result=result, evidence=evidence).to_dict()
        self.assertTrue(context["source_priority_notes"])
        self.assertTrue(context["steps_template"])
        self.assertTrue(context["risk_template"])


if __name__ == "__main__":
    unittest.main()
