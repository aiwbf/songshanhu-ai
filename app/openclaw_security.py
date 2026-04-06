from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SAFE_FALLBACK_MODES = {"safe_handoff", "dry_run_only"}


@dataclass(frozen=True)
class SecurityFinding:
    check_id: str
    title: str
    status: str
    detail: str


@dataclass(frozen=True)
class SecurityAssessment:
    delivery_allowed: bool
    findings: list[SecurityFinding]
    routing_key: str


class OpenClawSecurityPolicy:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.allowlist = payload.get("allowlist", {})
        self.group = payload.get("group", {})
        self.pairing = payload.get("pairing", {})
        self.fallback = payload.get("fallback", {})
        self.routing = payload.get("routing", {})

    @classmethod
    def from_path(cls, path: Path) -> "OpenClawSecurityPolicy":
        if not path.exists():
            return cls(default_policy_payload())
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def audit(self) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        allowlist_enabled = bool(self.allowlist.get("enabled", False))
        default_open_mode = bool(self.allowlist.get("default_open_mode", True))
        findings.append(
            self._finding(
                check_id="allowlist-default-closed",
                title="allowlist 默认关闭高风险开放模式",
                passed=allowlist_enabled and not default_open_mode,
                pass_detail="allowlist 已启用，且默认不是开放模式。",
                fail_detail="allowlist 未启用，或默认允许开放发送，存在高风险开放模式。",
            )
        )

        require_mention = bool(self.group.get("require_mention", False))
        findings.append(
            self._finding(
                check_id="group-require-mention",
                title="群聊 requireMention 已启用",
                passed=require_mention,
                pass_detail="群聊仅在明确提及时允许触发回复。",
                fail_detail="群聊未开启 requireMention，存在误触发与信息外泄风险。",
            )
        )

        pairing_enabled = bool(self.pairing.get("enabled", False))
        findings.append(
            self._finding(
                check_id="pairing-enabled",
                title="pairing 已启用",
                passed=pairing_enabled,
                pass_detail="高风险渠道要求 pairing 才允许发送。",
                fail_detail="pairing 未启用，无法确认当前请求来源是否可信。",
            )
        )

        fallback_mode = str(self.fallback.get("mode", "")).strip()
        allow_direct_answer = bool(self.fallback.get("allow_direct_answer", True))
        findings.append(
            self._finding(
                check_id="fallback-safe",
                title="fallback 配置安全",
                passed=fallback_mode in SAFE_FALLBACK_MODES and not allow_direct_answer,
                pass_detail="fallback 仅允许安全转人工或 dry-run，不允许直接放行答案。",
                fail_detail="fallback 允许直接回答或模式过宽，失败时可能把不安全回复直接发出。",
            )
        )

        routing_fields = tuple(str(item) for item in self.routing.get("session_key_fields", []))
        allow_cross_channel = bool(self.routing.get("allow_cross_channel_thread_reuse", False))
        routing_passed = (
            "channel" in routing_fields
            and "target" in routing_fields
            and any(field in routing_fields for field in ("conversation_id", "thread_id", "sender_id"))
            and not allow_cross_channel
        )
        findings.append(
            self._finding(
                check_id="routing-no-cross-session",
                title="渠道路由不会串会话",
                passed=routing_passed,
                pass_detail="路由键包含 channel、target 和会话区分字段，且禁止跨渠道复用线程。",
                fail_detail="路由键缺少隔离字段，或允许跨渠道复用线程，存在串会话风险。",
            )
        )
        return findings

    def assess_request(self, request: Any) -> SecurityAssessment:
        findings: list[SecurityFinding] = []
        delivery_allowed = True
        routing_key = self.routing_key(request)

        channel = str(getattr(request, "channel", "") or "")
        target = str(getattr(request, "target", "") or "")
        is_group = bool(getattr(request, "is_group", False))
        mentioned = bool(getattr(request, "mentioned", False))
        paired = bool(getattr(request, "paired", False))

        allowlist_enabled = bool(self.allowlist.get("enabled", False))
        protected_channels = {
            str(item)
            for item in self.allowlist.get("protected_channels", [])
        }
        channel_targets = {
            str(item)
            for item in self.allowlist.get("targets", {}).get(channel, [])
        }
        if allowlist_enabled and channel in protected_channels and target not in channel_targets:
            findings.append(
                SecurityFinding(
                    check_id="allowlist-target",
                    title="目标未在 allowlist 中",
                    status="fail",
                    detail=f"channel={channel} target={target} 不在允许发送名单内。",
                )
            )
            delivery_allowed = False

        require_mention = bool(self.group.get("require_mention", False))
        group_channels = {
            str(item)
            for item in self.group.get("channels", [])
        }
        if is_group and require_mention and channel in group_channels and not mentioned:
            findings.append(
                SecurityFinding(
                    check_id="group-mention",
                    title="群聊未显式提及机器人",
                    status="fail",
                    detail=f"channel={channel} target={target} 为群聊消息，但未满足 requireMention。",
                )
            )
            delivery_allowed = False

        pairing_enabled = bool(self.pairing.get("enabled", False))
        pairing_channels = {
            str(item)
            for item in self.pairing.get("channels", [])
        }
        if pairing_enabled and channel in pairing_channels and not paired:
            findings.append(
                SecurityFinding(
                    check_id="pairing",
                    title="pairing 未建立",
                    status="fail",
                    detail=f"channel={channel} 需要 pairing，但当前请求未声明 paired=true。",
                )
            )
            delivery_allowed = False

        if "scope=stateless" in routing_key:
            findings.append(
                SecurityFinding(
                    check_id="routing-discriminator",
                    title="请求缺少会话区分字段",
                    status="warn",
                    detail="当前路由键退化为 stateless，后续若接入多轮会话，需补充 conversation_id 或 thread_id。",
                )
            )

        return SecurityAssessment(
            delivery_allowed=delivery_allowed,
            findings=findings,
            routing_key=routing_key,
        )

    def routing_key(self, request: Any) -> str:
        values = {
            "channel": str(getattr(request, "channel", "") or ""),
            "target": str(getattr(request, "target", "") or ""),
            "conversation_id": str(getattr(request, "conversation_id", "") or ""),
            "thread_id": str(getattr(request, "thread_id", "") or ""),
            "sender_id": str(getattr(request, "sender_id", "") or ""),
        }

        parts: list[str] = []
        fields = [str(item) for item in self.routing.get("session_key_fields", [])]
        if not fields:
            fields = ["channel", "target", "conversation_id", "thread_id", "sender_id"]

        for field in fields:
            value = values.get(field, "")
            if value:
                parts.append(f"{field}={value}")

        if "channel" not in fields and values["channel"]:
            parts.insert(0, f"channel={values['channel']}")
        if "target" not in fields and values["target"]:
            parts.insert(1 if parts else 0, f"target={values['target']}")

        if not any(
            field in values and values[field]
            for field in ("conversation_id", "thread_id", "sender_id")
        ):
            parts.append("scope=stateless")
        return "|".join(parts)

    def _finding(
        self,
        *,
        check_id: str,
        title: str,
        passed: bool,
        pass_detail: str,
        fail_detail: str,
    ) -> SecurityFinding:
        return SecurityFinding(
            check_id=check_id,
            title=title,
            status="pass" if passed else "fail",
            detail=pass_detail if passed else fail_detail,
        )


def default_policy_payload() -> dict[str, Any]:
    return {
        "allowlist": {
            "enabled": True,
            "default_open_mode": False,
            "protected_channels": ["wechat", "feishu"],
            "targets": {
                "feishu": ["oc_test"],
                "wechat": ["oc_test"],
            },
        },
        "group": {
            "require_mention": True,
            "channels": ["wechat", "feishu"],
        },
        "pairing": {
            "enabled": True,
            "channels": ["wechat", "feishu"],
        },
        "fallback": {
            "mode": "safe_handoff",
            "allow_direct_answer": False,
        },
        "routing": {
            "session_key_fields": ["channel", "target", "conversation_id", "thread_id", "sender_id"],
            "allow_cross_channel_thread_reuse": False,
        },
    }
