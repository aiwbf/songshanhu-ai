from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.models import ConsultationOrchestratorResponse
from app.server import app as orchestrator_app


GATEWAY_DIR = Path(__file__).resolve().parents[1] / "apps" / "gateway-adapter"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

import main as gateway_main
from gateway_config import GatewaySettings
from gateway_service import OrchestratorApiError


def sample_gateway_settings() -> GatewaySettings:
    return GatewaySettings.model_validate(
        {
            "service": {
                "listenHost": "127.0.0.1",
                "listenPort": 8010,
                "orchestratorBaseUrl": "http://127.0.0.1:8000",
                "orchestratorPath": "/api/consultation/orchestrate",
                "timeoutMs": 6000,
            },
            "security": {
                "defaultDeny": True,
                "headerName": "X-OpenClaw-Token",
                "sharedToken": "test-token",
                "allowlist": {
                    "channels": ["feishu"],
                    "senders": [],
                    "peers": [],
                },
                "pairing": {
                    "required": True,
                    "trustedSenders": ["ops-console"],
                    "metadataKey": "paired",
                },
            },
            "routing": {
                "group": {"requireMention": True},
                "perSenderSession": True,
                "fallbackAgent": "fallback-human-handoff",
                "channelBindings": {
                    "default": {
                        "routeMode": "parent_consultation",
                        "requireMention": True,
                        "perSenderSession": True,
                    }
                },
            },
        }
    )


class LocalOrchestratorClient:
    def __init__(self) -> None:
        self.client = TestClient(orchestrator_app)

    def orchestrate(self, request):
        response = self.client.post(
            "/api/consultation/orchestrate",
            json=request.model_dump(mode="json"),
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        return ConsultationOrchestratorResponse.model_validate(response.json())


class UnavailableOrchestratorClient:
    def orchestrate(self, request):
        raise OrchestratorApiError("api_unavailable", "backend unavailable", 503)


class GatewayAdapterIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = sample_gateway_settings()

    def test_private_chat_routes_to_parent_consultation_agent(self) -> None:
        client = TestClient(
            gateway_main.create_app(
                settings=self.settings,
                orchestrator_client=LocalOrchestratorClient(),
            )
        )
        response = client.post(
            "/events/openclaw",
            headers={"X-OpenClaw-Token": "test-token"},
            json={
                "eventId": "evt-direct-001",
                "occurredAt": "2026-03-08T10:00:00Z",
                "channel": "feishu",
                "binding": "default",
                "sender": {
                    "senderId": "parent-001",
                    "displayName": "Parent A",
                    "paired": True,
                },
                "conversation": {
                    "peerId": "dm-parent-001",
                    "peerType": "direct",
                },
                "message": {
                    "messageId": "msg-direct-001",
                    "type": "text",
                    "text": "什么情况下不能申请松山湖公办中小学转学？",
                },
                "metadata": {},
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["route_mode"], "parent_consultation")
        self.assertEqual(payload["routed_agent"], "admissions-consultation")
        self.assertIn("parent-001", payload["normalized_message"]["session"]["session_key"])
        self.assertEqual(payload["normalized_message"]["kind"], "text")
        self.assertIn("incoming_message", payload["audit_events"])
        self.assertIn("normalized_message", payload["audit_events"])
        self.assertIn("routed_agent", payload["audit_events"])
        self.assertIn("response_status", payload["audit_events"])

    def test_group_message_with_mention_routes_normally(self) -> None:
        client = TestClient(
            gateway_main.create_app(
                settings=self.settings,
                orchestrator_client=LocalOrchestratorClient(),
            )
        )
        response = client.post(
            "/events/openclaw",
            headers={"X-OpenClaw-Token": "test-token"},
            json={
                "eventId": "evt-group-001",
                "occurredAt": "2026-03-08T10:01:00Z",
                "channel": "feishu",
                "binding": "default",
                "sender": {
                    "senderId": "parent-002",
                    "displayName": "Parent B",
                    "paired": True,
                },
                "conversation": {
                    "peerId": "group-001",
                    "peerType": "group",
                },
                "message": {
                    "messageId": "msg-group-001",
                    "type": "text",
                    "text": "@招生机器人 转学有哪些限制？",
                    "mentions": ["admissions-bot"],
                },
                "metadata": {},
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["route_mode"], "parent_consultation")
        self.assertTrue(payload["normalized_message"]["mentions_bot"])
        self.assertTrue(payload["normalized_message"]["peer"]["require_mention"])
        self.assertEqual(payload["normalized_message"]["peer"]["peer_type"], "group")
        self.assertEqual(payload["routed_agent"], "admissions-consultation")

    def test_api_unavailable_returns_degraded_fallback_reply(self) -> None:
        client = TestClient(
            gateway_main.create_app(
                settings=self.settings,
                orchestrator_client=UnavailableOrchestratorClient(),
            )
        )
        response = client.post(
            "/events/openclaw",
            headers={"X-OpenClaw-Token": "test-token"},
            json={
                "eventId": "evt-fallback-001",
                "occurredAt": "2026-03-08T10:02:00Z",
                "channel": "feishu",
                "binding": "default",
                "sender": {
                    "senderId": "parent-003",
                    "displayName": "Parent C",
                    "paired": True,
                },
                "conversation": {
                    "peerId": "dm-parent-003",
                    "peerType": "direct",
                },
                "message": {
                    "messageId": "msg-fallback-001",
                    "type": "text",
                    "text": "请问报名流程是什么？",
                },
                "metadata": {},
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["accepted"])
        self.assertTrue(payload["degraded"])
        self.assertEqual(payload["response_status"], "degraded")
        self.assertEqual(payload["degradation_code"], "api_unavailable")
        self.assertEqual(payload["routed_agent"], "fallback-human-handoff")
        self.assertTrue(payload["escalation"])
        self.assertIn("当前咨询服务不可用", payload["reply_text"])


if __name__ == "__main__":
    unittest.main()
