from __future__ import annotations

import unittest

from app.assistant import AdmissionsAssistant
from app.config import get_settings
from app.knowledge import KnowledgeStore
from app.llm_client import SynthesizedPayload
from app.models import AskRequest
from app.rules import RuleEngine
from scripts.build_knowledge import build_knowledge


class FakeSynthesizer:
    def __init__(self, payload: SynthesizedPayload | None) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


def build_assistant(*, synthesizer=None) -> AdmissionsAssistant:
    settings = get_settings()
    if not settings.knowledge_path.exists():
        build_knowledge(root=settings.root_dir, output_path=settings.knowledge_path)
    return AdmissionsAssistant(
        settings=settings,
        rules=RuleEngine.from_path(settings.rules_path),
        knowledge=KnowledgeStore.from_path(settings.knowledge_path),
        synthesizer=synthesizer,
    )


class AssistantLlmTestCase(unittest.TestCase):
    def test_general_knowledge_question_is_answered_from_knowledge(self) -> None:
        assistant = build_assistant(synthesizer=None)
        response = assistant.answer(AskRequest(question="A1类和A3类有什么区别？"))
        self.assertEqual(response.status.value, "answered")
        self.assertTrue(response.citations)
        self.assertIn("2025年松山湖中小学、幼儿园入学申请指南", response.citations[0].title)

    def test_category_definition_question_explains_meaning(self) -> None:
        assistant = build_assistant(synthesizer=None)
        response = assistant.answer(AskRequest(question="A3类是什么意思？"))
        self.assertEqual(response.status.value, "answered")
        self.assertIn("A3", response.conclusion)
        self.assertTrue(response.citations)

    def test_transfer_question_uses_application_guide_as_primary_citation(self) -> None:
        assistant = build_assistant(synthesizer=None)
        response = assistant.answer(AskRequest(question="什么情况下不能申请松山湖公办中小学转学？"))
        self.assertEqual(response.status.value, "answered")
        self.assertTrue(response.citations)
        self.assertIn("2025年松山湖中小学、幼儿园入学申请指南", response.citations[0].title)

    def test_special_policy_question_keeps_special_policy_source(self) -> None:
        assistant = build_assistant(synthesizer=None)
        response = assistant.answer(AskRequest(question="华侨华人子女如何申请园区学位？"))
        self.assertEqual(response.status.value, "answered")
        self.assertTrue(any("2025年关于修订华侨华人子女及华侨学生在我市就读有关规定的通知" in citation.title for citation in response.citations))

    def test_cross_year_policy_comparison_does_not_answer_directly(self) -> None:
        assistant = build_assistant(synthesizer=None)
        response = assistant.answer(AskRequest(question="B3 大专学历连续工作满 5 年截至 2023 年 4 月 30 日，这个时间在 2024 也还是一样吗？"))
        self.assertEqual(response.status.value, "handoff")

    def test_generic_b3_and_c_double_application_question_is_answered(self) -> None:
        assistant = build_assistant(synthesizer=None)
        response = assistant.answer(AskRequest(question="松山湖的B3类企业积分制人才和C类东莞市非户籍适龄儿童少年积分制入学可以同时申请吗？"))
        self.assertEqual(response.status.value, "answered")

    def test_case_specific_b3_and_c_double_application_question_requires_more_info(self) -> None:
        assistant = build_assistant(synthesizer=None)
        response = assistant.answer(AskRequest(question="如果孩子是非东莞户籍，家长在松山湖工作，B3 和 C 能同时报吗？你直接给我一个确定答案。"))
        self.assertEqual(response.status.value, "need_info")

    def test_prefer_llm_uses_grounded_synthesizer_when_payload_is_safe(self) -> None:
        synthesizer = FakeSynthesizer(
            SynthesizedPayload(
                status="answered",
                question_type="转学",
                initial_conclusion="先直接说结论：这类问题要先看当年转学限制和受理范围。",
                eligibility_or_issue="按当前命中的资料，系统可以先解释规则，但最终仍以平台审核和学位供给为准。",
                judgement_basis=["申请指南强调转学不能脱离当年受理条件单独判断。"],
                required_materials=["学生学籍信息", "在读证明"],
                next_actions=["先核对孩子所在学段和是否属于政策限制情形。"],
                risk_alerts=["当前回答只依据 2025 年资料，不冒充最新年度政策。"],
                follow_up_questions=[],
                evidence_ids=["EV1"],
            )
        )
        assistant = build_assistant(synthesizer=synthesizer)
        response = assistant.answer(AskRequest(question="什么情况下不能申请松山湖公办中小学转学？", prefer_llm=True))
        self.assertTrue(synthesizer.calls)
        self.assertTrue(response.used_llm)
        self.assertEqual(response.resolution_source, "grounded_llm")
        self.assertEqual(len(response.citations), 1)

    def test_prefer_llm_falls_back_when_synthesizer_changes_status(self) -> None:
        synthesizer = FakeSynthesizer(
            SynthesizedPayload(
                status="handoff",
                question_type="转学",
                initial_conclusion="这条结论不应被采用。",
                eligibility_or_issue="这条结论不应被采用。",
                judgement_basis=["这条结论不应被采用。"],
                required_materials=[],
                next_actions=["这条结论不应被采用。"],
                risk_alerts=[],
                follow_up_questions=[],
                evidence_ids=["EV1"],
            )
        )
        assistant = build_assistant(synthesizer=synthesizer)
        response = assistant.answer(AskRequest(question="什么情况下不能申请松山湖公办中小学转学？", prefer_llm=True))
        self.assertFalse(response.used_llm)


if __name__ == "__main__":
    unittest.main()
