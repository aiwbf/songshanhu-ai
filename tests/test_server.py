from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from app.server import ADMIN_SESSION_COOKIE, app, create_admin_token, runtime


class ServerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["knowledge_loaded"])
        self.assertIn("llm_enabled", payload)
        self.assertIn("llm_provider", payload)
        self.assertIn("official_contact", payload)
        self.assertIn("charset=utf-8", response.headers.get("content-type", "").lower())

    def test_index_page(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", "").lower())
        self.assertIn("松山湖入学咨询", response.text)
        self.assertIn("资格预判", response.text)
        self.assertIn("/static/parent.js", response.text)
        self.assertNotIn("进入运营后台", response.text)

    def test_static_asset(self) -> None:
        response = self.client.get("/static/parent.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers.get("content-type", "").lower())
        self.assertIn("/conversations", response.text)

    def test_admin_page(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("运营后台登录", response.text)
        self.assertIn("/static/admin.js", response.text)

    def test_admin_session_defaults_to_login_screen(self) -> None:
        response = self.client.get("/admin/session")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["authenticated"])
        self.assertTrue(payload["login_enabled"])

    def test_admin_login_flow(self) -> None:
        response = self.client.post(
            "/admin/login",
            json={"username": "admin", "password": "wHRsj1zhZu2HbuMRW7"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["authenticated"])
        self.assertTrue(payload["login_enabled"])
        self.assertEqual(payload["username"], "admin")

    def test_admin_session_persists_until_timeout(self) -> None:
        login = self.client.post(
            "/admin/login",
            json={"username": "admin", "password": "wHRsj1zhZu2HbuMRW7"},
        )
        self.assertEqual(login.status_code, 200)
        session = self.client.get("/admin/session")
        self.assertEqual(session.status_code, 200)
        payload = session.json()
        self.assertTrue(payload["authenticated"])
        self.assertTrue(payload["login_enabled"])
        self.assertEqual(payload["username"], "admin")

    def test_admin_session_expires_after_idle_timeout(self) -> None:
        idle_seconds = runtime.settings.admin_session_idle_minutes * 60
        now = int(time.time())
        expires_at = now + 3600
        last_seen_at = now - idle_seconds - 1
        token = create_admin_token("admin", expires_at=expires_at, last_seen_at=last_seen_at)
        self.client.cookies.set(ADMIN_SESSION_COOKIE, token)
        session = self.client.get("/admin/session")
        self.assertEqual(session.status_code, 200)
        payload = session.json()
        self.assertFalse(payload["authenticated"])
        self.assertTrue(payload["login_enabled"])

    def test_admin_api_requires_authentication(self) -> None:
        response = self.client.get("/admin-api/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_orchestrator_endpoint_returns_structured_payload(self) -> None:
        response = self.client.post(
            "/api/consultation/orchestrate",
            json={
                "normalized_message": {
                    "event_id": "evt-001",
                    "message_id": "msg-001",
                    "occurred_at": "2026-03-08T10:00:00Z",
                    "channel": "openclaw:wechat",
                    "binding": "default",
                    "kind": "text",
                    "text": "什么情况下不能申请松山湖公办中小学转学？",
                    "mentions_bot": False,
                    "peer": {"peer_id": "dm-001", "peer_type": "direct"},
                    "session": {"session_key": "dm-001:user-001"},
                    "sender": {"sender_id": "user-001"},
                    "attachments": [],
                    "metadata": {},
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route_mode"], "parent_consultation")
        self.assertEqual(payload["routed_agent"], "admissions-consultation")
        self.assertTrue(payload["answer_payload"])
        self.assertTrue(payload["escalation_decision"])
        self.assertTrue(payload["citations"])
        self.assertTrue(payload["session_update"])
        self.assertIn("source_id", payload["citations"][0])
        self.assertIn("title", payload["citations"][0])
        self.assertIn("page", payload["citations"][0])
        self.assertIn("chunk_id", payload["citations"][0])
        self.assertIn("quote_snippet", payload["citations"][0])

    def test_exact_answer_uses_structured_citations(self) -> None:
        response = self.client.post(
            "/ask",
            json={"question": "什么情况下不能申请松山湖公办中小学转学？"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["question_type"], "转学")
        self.assertIn("转学", payload["conclusion"])
        self.assertTrue(payload["answer_payload"])
        self.assertTrue(payload["citations"])
        self.assertIn("【结论】", payload["customer_reply"])
        self.assertIn("【判断依据】", payload["customer_reply"])
        self.assertIn("【引用】", payload["customer_reply"])
        self.assertTrue(payload["consultation_advice"])
        self.assertTrue(payload["cannot_confirm_reason"])

    def test_latest_policy_returns_current_guidance(self) -> None:
        response = self.client.post(
            "/ask",
            json={"question": "2026 年最新政策有没有变化？"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["resolution_source"], {"rule_handoff", "policy_citation"})
        self.assertTrue(any(year in payload["conclusion"] for year in ("2024", "2025", "2026")))
        self.assertTrue(payload["consultation_advice"])
        self.assertTrue(payload["cannot_confirm_reason"])
        self.assertIn("【引用】", payload["customer_reply"])
        self.assertTrue(payload["answer_payload"]["risk_alerts"])

    def test_need_info_for_case_specific_question(self) -> None:
        response = self.client.post(
            "/ask",
            json={"question": "我家孩子能报哪一类？"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "need_info")
        self.assertGreaterEqual(len(payload["missing_fields"]), 1)
        self.assertLessEqual(len(payload["missing_fields"]), 3)
        self.assertIn("【还需要你补充】", payload["customer_reply"])
        self.assertTrue(payload["consultation_advice"])
        self.assertTrue(payload["cannot_confirm_reason"])

    def test_openclaw_inbound_dry_run_uses_channel_aware_format(self) -> None:
        response = self.client.post(
            "/openclaw/inbound",
            json={
                "channel": "feishu",
                "target": "oc_test",
                "message": "什么情况下不能申请松山湖公办中小学转学？",
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["channel"], "feishu")
        self.assertIn("run_openclaw_action.ps1", payload["command_preview"])
        self.assertIn("【结论】", payload["reply_text"])
        self.assertIn("【当前判断】", payload["reply_text"])
        self.assertIn("【人工协助】", payload["reply_text"])

    def test_chat_remembers_context(self) -> None:
        first = self.client.post("/chat", json={"message": "我家孩子能报哪一类？"})
        self.assertEqual(first.status_code, 200)
        first_payload = first.json()
        self.assertEqual(first_payload["reply"]["status"], "need_info")
        conversation_id = first_payload["conversation_id"]

        second = self.client.post(
            "/chat",
            json={
                "conversation_id": conversation_id,
                "message": "补充信息",
                "facts": {
                    "child_hukou": "东莞其他镇街",
                    "parent_work_in_songshanhu": True,
                    "has_songshanhu_property": False,
                    "stage": "小学一年级",
                    "is_transfer": False,
                },
            },
        )
        self.assertEqual(second.status_code, 200)
        second_payload = second.json()
        self.assertEqual(second_payload["conversation_id"], conversation_id)
        self.assertEqual(second_payload["reply"]["status"], "need_info")
        self.assertTrue(second_payload["remembered_facts"]["parent_work_in_songshanhu"])
        self.assertFalse(second_payload["remembered_facts"]["has_songshanhu_property"])
        self.assertFalse(second_payload["remembered_facts"]["is_transfer"])
        self.assertEqual(second_payload["remembered_facts"]["child_hukou"], "东莞其他镇街")
        self.assertNotEqual(second_payload["reply"]["missing_fields"], first_payload["reply"]["missing_fields"])
        self.assertEqual(len(second_payload["history"]), 4)

    def test_chat_state_endpoint(self) -> None:
        created = self.client.post("/chat", json={"message": "2024 年小学一年级入学对象是什么？"})
        conversation_id = created.json()["conversation_id"]
        snapshot = self.client.get(f"/chat/{conversation_id}")
        self.assertEqual(snapshot.status_code, 200)
        payload = snapshot.json()
        self.assertEqual(payload["conversation_id"], conversation_id)
        self.assertGreaterEqual(len(payload["history"]), 2)
        self.assertIn("channel", payload)
        self.assertIn("manual_takeover", payload)

    def test_conversation_list_endpoint(self) -> None:
        created = self.client.post("/chat", json={"message": "我家孩子能报哪一类？"})
        conversation_id = created.json()["conversation_id"]
        response = self.client.get("/conversations")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["items"])
        matched = next((item for item in payload["items"] if item["conversation_id"] == conversation_id), None)
        self.assertIsNotNone(matched)
        self.assertIn("channel", matched)
        self.assertIn("is_openclaw", matched)

    def test_ops_dashboard_and_takeover_flow(self) -> None:
        inbound = self.client.post(
            "/openclaw/inbound",
            json={
                "channel": "feishu",
                "target": "ops_demo",
                "source_session_id": "session-001",
                "message": "我家孩子能报哪一类？",
                "dry_run": True,
            },
        )
        self.assertEqual(inbound.status_code, 200)
        conversation_id = inbound.json()["conversation_id"]

        dashboard = self.client.get("/ops/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        payload = dashboard.json()
        self.assertGreaterEqual(payload["total_events"], 1)
        self.assertGreaterEqual(payload["openclaw_conversations"], 1)
        self.assertIn("faq_hit_rate", payload)
        self.assertIn("takeover_queue", payload)

        takeover = self.client.post(
            f"/ops/conversations/{conversation_id}/takeover",
            json={"agent_name": "人工客服", "note": "转人工复核", "status": "human"},
        )
        self.assertEqual(takeover.status_code, 200)
        takeover_payload = takeover.json()
        self.assertTrue(takeover_payload["manual_takeover"])
        self.assertEqual(takeover_payload["takeover_status"], "human")
        self.assertEqual(takeover_payload["channel"], "feishu")
        self.assertTrue(takeover_payload["is_openclaw"])

    def test_ops_alias_and_repair_item_endpoints(self) -> None:
        alias = self.client.post(
            "/ops/faq-aliases",
            json={
                "alias": "报名号怎么填",
                "faq_id": "faq-demo-001",
                "faq_question": "平台报名号怎么填写？",
                "note": "来自人工补充",
            },
        )
        self.assertEqual(alias.status_code, 200)
        alias_payload = alias.json()
        self.assertEqual(alias_payload["alias"], "报名号怎么填")

        alias_list = self.client.get("/ops/faq-aliases")
        self.assertEqual(alias_list.status_code, 200)
        self.assertTrue(any(item["alias"] == "报名号怎么填" for item in alias_list.json()["items"]))

        repair = self.client.post(
            "/ops/repair-items",
            json={
                "kind": "rule",
                "title": "补充 B 类缺失字段追问",
                "problem": "家长补充工作地和房产后，仍需继续追问父母户籍。",
                "proposed_fix": "将父母户籍作为 B 类判断的二轮追问必答项。",
                "manual_reply": "请先补充父母户籍后再判断。",
                "source_channel": "web",
            },
        )
        self.assertEqual(repair.status_code, 200)
        repair_payload = repair.json()
        self.assertEqual(repair_payload["kind"], "rule")

        repair_list = self.client.get("/ops/repair-items")
        self.assertEqual(repair_list.status_code, 200)
        self.assertTrue(any(item["title"] == "补充 B 类缺失字段追问" for item in repair_list.json()["items"]))


if __name__ == "__main__":
    unittest.main()
