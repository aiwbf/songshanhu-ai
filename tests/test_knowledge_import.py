from __future__ import annotations

import unittest

from tests.knowledge_rules_fixture import get_store


class KnowledgeImportTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = get_store()

    def test_source_registry_fields(self) -> None:
        bundle = self.store.bundle
        self.assertEqual(bundle["active_cycle_year"], 2025)
        for source in bundle["sources"]:
            self.assertIn("source_id", source)
            self.assertIn("title", source)
            self.assertIn("source_type", source)
            self.assertIn("year", source)
            self.assertIn("effective_date", source)
            self.assertIn("scope", source)
            self.assertIn("priority_bucket", source)

    def test_bundle_includes_2025_sources(self) -> None:
        source_ids = {source["source_id"] for source in self.store.bundle["sources"]}
        self.assertIn("guide_songshanhu_2025", source_ids)
        self.assertIn("policy_gd_youyue_2025", source_ids)

    def test_bundle_retains_2024_business_sources(self) -> None:
        source_ids = {source["source_id"] for source in self.store.bundle["sources"]}
        self.assertIn("business_faq_2024_csv", source_ids)
        self.assertIn("business_faq_2024_xls", source_ids)


if __name__ == "__main__":
    unittest.main()
