from __future__ import annotations

import unittest
from datetime import datetime

from packages.shared.contracts import (
    CaseCategory,
    ClassificationResult,
    ConversationMode,
    NormalizedActor,
    NormalizedMessage,
    RoutingPolicy,
)


class SharedContractsTestCase(unittest.TestCase):
    def test_normalized_message_schema(self) -> None:
        payload = NormalizedMessage(
            message_id="msg-001",
            trace_id="trace-001",
            channel="openclaw:wechat",
            channel_message_id="raw-001",
            conversation_mode=ConversationMode.DM,
            channel_space_id="dm-001",
            peer_id="user-001",
            sender=NormalizedActor(actor_id="user-001", role="parent"),
            text="我家孩子应该属于哪一类？",
            received_at=datetime(2026, 3, 8, 12, 0, 0),
            routing=RoutingPolicy(
                agent_profile_id="parent-default",
                conversation_mode=ConversationMode.DM,
            ),
        )

        self.assertEqual(payload.channel, "openclaw:wechat")
        self.assertEqual(payload.routing.agent_profile_id, "parent-default")

    def test_classification_result_supports_required_categories(self) -> None:
        payload = ClassificationResult(
            run_id="run-001",
            case_id="case-001",
            intent="category_check",
            category_code=CaseCategory.B2,
            confidence=0.62,
            rationale="Current facts are incomplete, so this stays tentative.",
            generated_at=datetime(2026, 3, 8, 12, 0, 0),
        )

        self.assertEqual(payload.category_code, "B2")


if __name__ == "__main__":
    unittest.main()
