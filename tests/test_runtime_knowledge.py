from __future__ import annotations

import unittest

from app.assistant import AdmissionsAssistant
from app.config import get_settings
from app.knowledge import KnowledgeStore
from app.models import AskRequest
from app.rules import RuleEngine
from scripts.build_knowledge import build_knowledge


class RuntimeKnowledgeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = get_settings()
        build_knowledge(root=cls.settings.root_dir, output_path=cls.settings.knowledge_path)
        cls.active_store = KnowledgeStore.from_path(cls.settings.knowledge_path)
        cls.store_2024 = KnowledgeStore.from_path(cls.settings.knowledge_path.parent / "knowledge_base_2024.json")
        cls.assistant = AdmissionsAssistant(
            settings=cls.settings,
            rules=RuleEngine.from_path(cls.settings.rules_path),
            knowledge=cls.active_store,
            synthesizer=None,
        )

    def test_active_runtime_contains_2025_business_pdf(self) -> None:
        file_names = {source["file_name"] for source in self.active_store.sources}
        self.assertIn("2025年机器人业务文档（2025合并修订版）(1).pdf", file_names)
        self.assertIn("机器人业务文档（2024合并修订版）.csv", file_names)

    def test_2024_bundle_keeps_business_csv_and_xls(self) -> None:
        file_names = {source["file_name"] for source in self.store_2024.sources}
        self.assertIn("机器人业务文档（2024合并修订版）.csv", file_names)
        self.assertIn("机器人业务文档（2024合并修订版）.xls", file_names)

    def test_2024_bundle_can_still_hit_business_faq(self) -> None:
        hits = self.store_2024.search_faq("以前同一学段已经安排过免费学位，还能申请松山湖公办转学吗？", top_k=1)
        self.assertTrue(hits)
        self.assertIn("转学", hits[0].record["question"])

    def test_2025_active_runtime_answers_from_guide_and_policy(self) -> None:
        response = self.assistant.answer(AskRequest(question="A2类是什么意思？"))
        self.assertEqual(response.status.value, "answered")
        self.assertTrue(response.citations)
        self.assertTrue(any("2025年松山湖中小学、幼儿园入学申请指南" in citation.title for citation in response.citations))


if __name__ == "__main__":
    unittest.main()
