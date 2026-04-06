from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.server import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an end-to-end demo flow without starting external services.")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "data" / "generated" / "demo_flow_latest.json"),
        help="Where to write the demo flow output JSON.",
    )
    args = parser.parse_args()

    client = TestClient(app)

    latest_policy = client.post(
        "/ask",
        json={"question": "2026年最新政策有变化吗？"},
    ).json()

    first_chat = client.post(
        "/chat",
        json={"message": "我家孩子属于哪一类？"},
    ).json()
    second_chat = client.post(
        "/chat",
        json={
            "conversation_id": first_chat["conversation_id"],
            "facts": {
                "child_hukou": "东莞其他镇街",
                "parent_work_in_songshanhu": True,
                "has_songshanhu_property": False,
                "stage": "小学一年级",
                "is_transfer": False,
            },
            "message": "补充这些条件后请继续判断。",
        },
    ).json()

    openclaw_dm = client.post(
        "/openclaw/inbound",
        json={
            "channel": "feishu",
            "target": "oc_test",
            "source_session_id": "demo-parent-001",
            "sender_id": "demo-parent-001",
            "paired": True,
            "message": "什么情况下不能申请松山湖公办中小学转学？",
            "dry_run": True,
        },
    ).json()

    payload = {
        "latest_policy": {
            "status": latest_policy["status"],
            "resolution_source": latest_policy["resolution_source"],
            "citations": len(latest_policy["citations"]),
        },
        "chat_follow_up": {
            "conversation_id": first_chat["conversation_id"],
            "first_status": first_chat["reply"]["status"],
            "second_status": second_chat["reply"]["status"],
            "remembered_facts": second_chat["remembered_facts"],
        },
        "openclaw_dm": {
            "conversation_id": openclaw_dm["conversation_id"],
            "delivery_allowed": openclaw_dm["delivery_allowed"],
            "routing_key": openclaw_dm["routing_key"],
            "reply_preview": openclaw_dm["reply_text"][:220],
        },
    }

    output_path = Path(args.out).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_path": str(output_path), "summary": payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
