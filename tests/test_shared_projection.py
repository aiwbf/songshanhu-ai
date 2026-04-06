from __future__ import annotations

import unittest

from app.models import (
    AnswerPayload,
    AnswerStatus,
    CitationRef,
    EscalationAction,
    EscalationDecision,
    NormalizedMessage,
    NormalizedPeer,
    NormalizedSender,
    NormalizedSession,
    RouteMode,
    RuleClassification,
    SessionUpdate,
    StudentFacts,
)
from app.shared_projection import build_shared_contract_snapshot


class SharedProjectionTestCase(unittest.TestCase):
    def test_runtime_models_project_to_shared_contracts(self) -> None:
        snapshot = build_shared_contract_snapshot(
            trace_id="trace-001",
            message=NormalizedMessage(
                event_id="evt-001",
                message_id="msg-001",
                occurred_at="2026-03-08T10:00:00Z",
                channel="openclaw:wechat",
                binding="default",
                text="我家孩子属于哪一类？",
                peer=NormalizedPeer(peer_id="dm-001", peer_type="direct"),
                session=NormalizedSession(session_key="dm-001:user-001"),
                sender=NormalizedSender(sender_id="user-001", role_tags=["parent"], paired=True),
            ),
            route_mode=RouteMode.PARENT_CONSULTATION,
            routed_agent="admissions-consultation",
            fallback_agent="fallback-human-handoff",
            facts=StudentFacts(child_hukou="东莞其他镇街", stage="小学一年级"),
            answer=AnswerPayload(
                status=AnswerStatus.NEED_INFO,
                scope="admissions_consultation",
                question_type="类别判断",
                initial_conclusion="当前信息不足，暂不能稳定分类。",
                eligibility_or_issue="需要先补充关键事实。",
                judgement_basis=["缺少户籍、工作地与房产信息。"],
                required_materials=[],
                next_actions=["请先补充孩子户籍、家长工作地和房产情况。"],
                risk_alerts=["仅依据 2024 年资料，不能冒充最新政策。"],
                human_support="如需人工协助，请联系招生热线。",
                follow_up_questions=["孩子户籍在哪里？", "家长是否在松山湖工作？"],
            ),
            escalation=EscalationDecision(
                action=EscalationAction.ASK_FOLLOW_UP,
                should_handoff=True,
                reasons=["missing_required_facts"],
                summary="缺少关键事实，必须先补问。",
                confidence=0.42,
                official_contact="招生热线",
            ),
            citations=[
                CitationRef(
                    source_id="src-001",
                    title="2024年松山湖中小学、幼儿园入学申请指南",
                    page="第 3 页",
                    chunk_id="src-001-pdf-0003",
                    quote_snippet="申请对象需按对应类别准备资料。",
                )
            ],
            session_update=SessionUpdate(
                conversation_id="conv-001",
                retained_profile=StudentFacts(child_hukou="东莞其他镇街", stage="小学一年级"),
                last_intent="类别判断",
                last_scope="admissions_consultation",
                asked_missing_fields=["孩子户籍所在地", "家长是否在松山湖工作"],
                follow_up_rounds=1,
                flags=["missing_required_facts"],
            ),
            classification=RuleClassification(
                scope="admissions_consultation",
                intent="类别判断",
                is_case_specific=True,
                missing_critical_fields=["孩子户籍所在地", "家长是否在松山湖工作"],
            ),
            confidence=0.42,
            knowledge=None,
            rendered_text="当前信息不足，暂不能稳定分类。",
        )

        self.assertIn("normalized_message", snapshot)
        self.assertIn("case_profile", snapshot)
        self.assertIn("classification_result", snapshot)
        self.assertIn("evidence_hits", snapshot)
        self.assertIn("answer_payload", snapshot)
        self.assertIn("escalation_decision", snapshot)
        self.assertEqual(snapshot["answer_payload"]["status"], "need_info")
        self.assertEqual(snapshot["evidence_hits"][0]["source_id"], "src-001")
        self.assertEqual(snapshot["classification_result"]["intent"], "类别判断")


if __name__ == "__main__":
    unittest.main()
