from __future__ import annotations

import unittest

from app.config import get_settings
from app.knowledge import KnowledgeStore
from scripts.build_knowledge import build_knowledge


class RuntimePdfCoverageTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = get_settings()
        build_knowledge(root=cls.settings.root_dir, output_path=cls.settings.knowledge_path)
        cls.store = KnowledgeStore.from_path(cls.settings.knowledge_path)

    def test_all_pdf_sources_have_runtime_chunks(self) -> None:
        pdf_sources = [source for source in self.store.sources if source.get("suffix") == ".pdf"]
        self.assertGreaterEqual(len(pdf_sources), 21)
        for source in pdf_sources:
            with self.subTest(source=source["file_name"]):
                self.assertTrue(any(doc["source_id"] == source["source_id"] for doc in self.store.documents))

    def test_special_policy_sources_have_runtime_representations(self) -> None:
        expected = ["关于修订华侨华人子女及华侨学生在我市就读有关规定的通知.pdf", "关于做好台湾学生申请就读我市义务教育阶段学校工作的通知.pdf", "广东省人民政府关于印发广东省人才优粤卡实施办法的通知.pdf"]
        file_names = {source["file_name"] for source in self.store.sources}
        for file_name in expected:
            with self.subTest(file_name=file_name):
                self.assertIn(file_name, file_names)

    def test_pdf_source_metadata_is_available_at_runtime(self) -> None:
        pdf_sources = [source for source in self.store.sources if source.get("suffix") == ".pdf"]
        for source in pdf_sources:
            with self.subTest(source=source["file_name"]):
                self.assertTrue(source.get("title"))
                self.assertIn("source_type", source)
                self.assertIn("scope", source)
                self.assertIn("seed_tags", source)


if __name__ == "__main__":
    unittest.main()
