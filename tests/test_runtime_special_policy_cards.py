from __future__ import annotations

import unittest

from app.assistant import AdmissionsAssistant
from app.config import get_settings
from app.knowledge import KnowledgeStore
from app.models import AskRequest
from app.rules import RuleEngine
from scripts.build_knowledge import build_knowledge


class RuntimeSpecialPolicyCardsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = get_settings()
        build_knowledge(root=cls.settings.root_dir, output_path=cls.settings.knowledge_path)
        cls.store = KnowledgeStore.from_path(cls.settings.knowledge_path)
        cls.assistant = AdmissionsAssistant(
            settings=cls.settings,
            rules=RuleEngine.from_path(cls.settings.rules_path),
            knowledge=cls.store,
            synthesizer=None,
        )

    def source_by_catalog_id(self, catalog_source_id: str) -> dict[str, object]:
        return next(source for source in self.store.sources if source.get("catalog_source_id") == catalog_source_id)

    def test_2025_special_policy_sources_expose_rule_cards(self) -> None:
        expectations = {
            "policy_dg_overseas_chinese_2025": "华侨华人子女及华侨学生申请路径",
            "policy_gd_youyue_2025": "优粤卡持卡人子女教育待遇",
            "policy_dg_points_2025": "非户籍适龄儿童少年积分入学基本适用范围",
            "policy_dg_honorary_citizen_2025": "荣誉市民相关子女入学优待",
        }
        for catalog_source_id, expected_title in expectations.items():
            with self.subTest(catalog_source_id=catalog_source_id):
                source = self.source_by_catalog_id(catalog_source_id)
                titles = {card.get("card_title") for card in source.get("structured_rule_cards", [])}
                self.assertIn(expected_title, titles)

    def test_assistant_keeps_special_policy_citations(self) -> None:
        queries = [
            ("优粤卡持有人子女入学优待参照什么政策？", "2025年广东省人民政府关于印发广东省人才优粤卡实施办法的通知"),
            ("华侨华人子女如何申请园区学位？", "2025年关于修订华侨华人子女及华侨学生在我市就读有关规定的通知"),
        ]
        for question, expected_title in queries:
            with self.subTest(question=question):
                response = self.assistant.answer(AskRequest(question=question))
                self.assertTrue(response.citations)
                self.assertTrue(any(expected_title in citation.title for citation in response.citations))


if __name__ == "__main__":
    unittest.main()
