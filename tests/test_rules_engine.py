from __future__ import annotations

import unittest

from tests.knowledge_rules_fixture import get_engine


class RulesEngineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()

    def test_a1_classification(self) -> None:
        result = self.engine.classify_case(
            profile={},
            question="父母不在松山湖工作，且户籍不在松山湖，孩子户籍在松山湖（户籍跟爷爷），父母园区没有房产（房产属于爷爷）属于哪类？",
        )
        self.assertEqual(result.primary_case_code, "A1")
        self.assertIn("A1", result.case_codes)
        self.assertFalse(result.minimal_follow_up_fields)
        self.assertTrue(result.reason_chain)

    def test_a3_classification(self) -> None:
        result = self.engine.classify_case(
            profile={
                "child_hukou": "松山湖家庭户",
                "property_location": "松山湖",
                "property_owner_relation": "非直系亲属",
            },
            question="A3类中“学童和父（母）是松山湖家庭户，但学童与房产所有人非直系亲属关系”是什么意思？",
        )
        self.assertEqual(result.primary_case_code, "A3")
        self.assertEqual(result.status, "classified")

    def test_b1_b2_b3_c_paths(self) -> None:
        cases = [
            (
                "B1",
                {},
                "小孩户口在国内非东莞市，家长在园区工作，工作时间一年以上，且所在单位根据有关规定具有入学指标。所需资料?",
            ),
            (
                "B2",
                {},
                "我有优才卡，工作地在松山湖，可以申请松山湖的学位吗？",
            ),
            (
                "B3",
                {
                    "child_hukou": "非东莞",
                    "work_location": "松山湖",
                    "preferential_statuses": [],
                },
                "B3积分制人才",
            ),
            (
                "C",
                {
                    "child_hukou": "非东莞",
                },
                "父母不在松山湖工作，全家户籍都不在松山湖，但在园区有房产，属于哪类？",
            ),
        ]
        for expected_primary, profile, question in cases:
            with self.subTest(expected_primary=expected_primary):
                result = self.engine.classify_case(profile=profile, question=question)
                self.assertEqual(result.primary_case_code, expected_primary)

    def test_special_population_rules(self) -> None:
        cases = [
            ("台湾学生", {}, "台湾籍子女入学怎样申请？"),
            ("华侨华人", {}, "华人华侨子女如何申请园区学位？"),
            (
                "香港/澳门学童",
                {
                    "child_hukou": "香港",
                    "guardian_hukou": "松山湖",
                    "work_location": "松山湖",
                    "property_location": "松山湖",
                },
                "孩子是香港/澳门户籍，父母服务地/居住地/户籍地在松山湖或在松山湖拥有产权清晰的自有居所，如何申请入学？",
            ),
        ]
        for expected_primary, profile, question in cases:
            with self.subTest(expected_primary=expected_primary):
                result = self.engine.classify_case(profile=profile, question=question)
                self.assertEqual(result.primary_case_code, expected_primary)
                self.assertTrue(result.reason_chain)

    def test_operational_rules(self) -> None:
        cases = [
            ("房产锁定", "怎么知道我的房子是否被锁定？"),
            ("房产解锁", "如何对学位申请房进行解锁？"),
            ("单位账号注册与审核", "如何申请企业账号？"),
            ("报名资料修改", "报名时，我发现我上传的资料有误，如何进行修改？"),
        ]
        for expected_primary, question in cases:
            with self.subTest(expected_primary=expected_primary):
                result = self.engine.classify_case(profile={}, question=question)
                self.assertEqual(result.primary_case_code, expected_primary)
                self.assertEqual(result.status, "classified")

    def test_vague_question_only_asks_minimal_fields(self) -> None:
        result = self.engine.classify_case(profile={}, question="我家孩子属于哪类？")
        self.assertEqual(result.status, "need_follow_up")
        self.assertEqual(
            result.minimal_follow_up_fields,
            ["学段", "学童户籍", "监护人户籍", "工作地", "房产所在地", "是否属于人才/优待对象", "是否为转学/非起始年级"],
        )
