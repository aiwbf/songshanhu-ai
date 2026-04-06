from __future__ import annotations

import unittest

from app.assistant import AdmissionsAssistant
from app.config import get_settings
from app.knowledge import KnowledgeStore
from app.models import AskRequest
from app.rules import RuleEngine
from scripts.build_knowledge import build_knowledge


class RuntimeGuideSectionsTestCase(unittest.TestCase):
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
        cls.active_guide = next(
            source
            for source in cls.active_store.sources
            if source.get("source_type") == "annual_guide" and int(source.get("cycle_year") or 0) == 2025
        )

    def test_active_runtime_uses_2025_guide(self) -> None:
        self.assertEqual(self.settings.knowledge_year, 2025)
        self.assertEqual(self.active_store.active_cycle_year, 2025)
        self.assertEqual(self.active_guide.get("catalog_source_id"), "guide_songshanhu_2025")

    def test_guide_source_exposes_structured_sections(self) -> None:
        titles = {section.get("section_title") for section in self.active_guide.get("structured_sections", [])}
        self.assertTrue({"招生对象", "分类条件", "材料清单", "报名流程", "转学限制", "房产锁定"}.issubset(titles))

    def test_guide_source_exposes_structured_rule_cards(self) -> None:
        titles = {card.get("card_title") for card in self.active_guide.get("structured_rule_cards", [])}
        self.assertTrue({"A1类家庭户籍学童", "A2类集体户籍人员", "多项条件仅可任选一项申报", "单位账号申请与审核", "学位房锁定规则"}.issubset(titles))

    def test_property_lock_query_hits_active_guide(self) -> None:
        hits = self.active_store.search_documents("房产锁定规则是什么", top_k=5)
        self.assertTrue(hits)
        self.assertTrue(any(self.active_store.source_for(hit.record["source_id"]).get("catalog_source_id") == "guide_songshanhu_2025" for hit in hits))

    def test_unit_account_query_hits_active_guide_rule_card(self) -> None:
        hits = self.active_store.search_documents("单位账号怎么注册和审核", top_k=8)
        self.assertTrue(hits)
        self.assertTrue(any(hit.record.get("rule_card_id") == "guide_rule_unit_account" for hit in hits))

    def test_assistant_uses_2025_guide_citations(self) -> None:
        response = self.assistant.answer(AskRequest(question="房产锁定规则是什么？"))
        self.assertEqual(response.status.value, "answered")
        self.assertTrue(response.citations)
        self.assertTrue(any("2025年松山湖中小学、幼儿园入学申请指南" in citation.title for citation in response.citations))

    def test_2024_bundle_is_preserved(self) -> None:
        guide_2024 = next(source for source in self.store_2024.sources if source.get("catalog_source_id") == "guide_songshanhu_2024")
        self.assertEqual(self.store_2024.active_cycle_year, 2024)
        self.assertEqual(guide_2024.get("cycle_year"), 2024)


if __name__ == "__main__":
    unittest.main()
