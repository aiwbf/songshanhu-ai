from __future__ import annotations

import json
import unittest
from pathlib import Path


class EvalDatasetUnitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_core_dataset_covers_required_topics(self) -> None:
        payload = json.loads((self.root / "evals" / "datasets" / "core_regression.json").read_text(encoding="utf-8"))
        tags = {tag for case in payload["cases"] for tag in case.get("coverage_tags", [])}
        required = {
            "A1",
            "A2",
            "A3",
            "B1",
            "B2",
            "B3",
            "C",
            "优才卡",
            "优粤卡",
            "香港/澳门学童",
            "台湾学生",
            "华侨华人",
            "房产锁定",
            "解锁",
            "资料修改",
            "单位账号注册与审核",
            "B1 名额查询",
            "同时申请 B3 与 C",
            "群聊中模糊发问",
            "非招生问题误入",
            "历史政策误问为当前政策",
        }
        self.assertTrue(required.issubset(tags))

    def test_failure_mode_library_contains_top_20(self) -> None:
        payload = json.loads((self.root / "evals" / "failure_modes" / "top20.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["failure_modes"]), 20)
        ids = {item["id"] for item in payload["failure_modes"]}
        self.assertIn("faq_as_policy", ids)
        self.assertIn("channel_route_mixup", ids)


if __name__ == "__main__":
    unittest.main()
