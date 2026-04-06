from __future__ import annotations

import unittest

from app.models import (
    AnswerPayload,
    AnswerStatus,
    ChannelMode,
    CitationRef,
    EscalationAction,
    EscalationDecision,
)
from apps.api.channel_output import render_answer_for_channel


class ChannelOutputTestCase(unittest.TestCase):
    def build_answer(self, status: AnswerStatus = AnswerStatus.ANSWERED) -> AnswerPayload:
        return AnswerPayload(
            status=status,
            scope="admissions_consultation",
            question_type="类别判断",
            initial_conclusion="按你现在提供的信息，可以先按 A1 路径理解。",
            eligibility_or_issue="当前问题更接近 A1 方向，但最终仍以官方审核为准。",
            judgement_basis=[
                "申请指南写明，家庭户与房产关系需要按对应类别核验。",
                "系统命中的证据来自已导入的官方申请指南。",
            ],
            required_materials=["户口簿", "房产证明"],
            next_actions=["先核对户籍和房产关系。", "再按 A1 路径准备材料。"],
            risk_alerts=["当前回答仅依据 2024 年资料，不冒充最新年度口径。"],
            human_support="如需人工协助，可联系松山湖招生服务热线。",
            follow_up_questions=["孩子户籍在哪里？", "房产在谁名下？"],
        )

    def build_escalation(
        self,
        action: EscalationAction = EscalationAction.NONE,
        confidence: float = 0.91,
        summary: str = "当前无需人工转接，可按现有证据给出克制回答。",
    ) -> EscalationDecision:
        return EscalationDecision(
            action=action,
            should_handoff=action == EscalationAction.HANDOFF_HUMAN,
            reasons=["demo_reason"] if action != EscalationAction.NONE else [],
            summary=summary,
            confidence=confidence,
            official_contact="松山湖招生服务热线",
        )

    def build_citations(self) -> list[CitationRef]:
        return [
            CitationRef(
                source_id="src-009",
                title="2024年松山湖中小学、幼儿园入学申请指南",
                page="第 15 页",
                chunk_id="src-009-pdf-0015",
                quote_snippet="房产及家庭关系按对应类别核验。",
            )
        ]

    def test_private_answered_reply_uses_structured_sections(self) -> None:
        text = render_answer_for_channel(
            trace_id="trace-001",
            answer=self.build_answer(),
            citations=self.build_citations(),
            escalation=self.build_escalation(),
            mode=ChannelMode.PRIVATE,
        )
        self.assertIn("【结论】", text)
        self.assertIn("【当前判断】", text)
        self.assertIn("【判断依据】", text)
        self.assertIn("【下一步】", text)
        self.assertIn("【人工协助】", text)
        self.assertIn("【引用】", text)
        self.assertIn("房产及家庭关系按对应类别核验", text)

    def test_private_need_info_reply_calls_for_missing_fields(self) -> None:
        answer = self.build_answer(status=AnswerStatus.NEED_INFO)
        answer.initial_conclusion = "现在还不能直接判断你属于哪一类。"
        answer.eligibility_or_issue = "信息补齐前，我不会直接硬判 A/B/C。"
        text = render_answer_for_channel(
            trace_id="trace-002",
            answer=answer,
            citations=self.build_citations(),
            escalation=self.build_escalation(
                action=EscalationAction.ASK_FOLLOW_UP,
                confidence=0.52,
                summary="当前缺少关键信息，需要继续追问。",
            ),
            mode=ChannelMode.PRIVATE,
        )
        self.assertIn("【还需要你补充】", text)
        self.assertIn("孩子户籍在哪里？", text)
        self.assertIn("房产在谁名下？", text)
        self.assertIn("【下一步】", text)

    def test_group_handoff_reply_stays_short_and_avoids_citations(self) -> None:
        answer = self.build_answer(status=AnswerStatus.HANDOFF)
        answer.initial_conclusion = "这类问题建议转人工复核。"
        text = render_answer_for_channel(
            trace_id="trace-003",
            answer=answer,
            citations=self.build_citations(),
            escalation=self.build_escalation(
                action=EscalationAction.HANDOFF_HUMAN,
                confidence=0.31,
                summary="涉及最新政策或人工审核状态，机器人不做强答。",
            ),
            mode=ChannelMode.GROUP,
        )
        self.assertIn("【结论】", text)
        self.assertIn("【原因】", text)
        self.assertIn("【人工】", text)
        self.assertNotIn("【引用】", text)

    def test_admin_reply_includes_trace_and_escalation_summary(self) -> None:
        text = render_answer_for_channel(
            trace_id="trace-004",
            answer=self.build_answer(),
            citations=self.build_citations(),
            escalation=self.build_escalation(),
            mode=ChannelMode.ADMIN,
        )
        self.assertIn("【会话信息】", text)
        self.assertIn("Trace ID：trace-004", text)
        self.assertIn("【转接原因】", text)
        self.assertIn("【引用】", text)


if __name__ == "__main__":
    unittest.main()
