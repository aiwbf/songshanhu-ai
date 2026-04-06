from __future__ import annotations

import json
import logging
from typing import Protocol
from uuid import uuid4

import httpx

from app.models import (
    AnswerStatus,
    AskResponse,
    ConsultationOrchestratorRequest,
    ConsultationOrchestratorResponse,
    NormalizedAttachment,
    NormalizedMessage,
    NormalizedPeer,
    NormalizedSender,
    NormalizedSession,
    RouteMode,
    StudentFacts,
)

from gateway_config import GatewaySettings
from gateway_models import GatewayInboundResponse, OpenClawStandardMessageEvent


LOGGER = logging.getLogger("openclaw.gateway.audit")
OPS_ROLE_TAGS = {"operations", "human_support", "manual_support", "客服", "人工客服"}
ADMIN_ROLE_TAGS = {"unit_admin", "organization_admin", "school_admin", "单位管理员"}


class GatewayAccessDenied(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OrchestratorApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class OrchestratorClient(Protocol):
    def orchestrate(self, request: ConsultationOrchestratorRequest) -> ConsultationOrchestratorResponse:
        ...


class HttpOrchestratorClient:
    def __init__(self, settings: GatewaySettings) -> None:
        self.base_url = settings.service.orchestrator_base_url.rstrip("/")
        self.path = settings.service.orchestrator_path
        self.timeout = max(settings.service.timeout_ms, 1000) / 1000.0

    def orchestrate(self, request: ConsultationOrchestratorRequest) -> ConsultationOrchestratorResponse:
        url = f"{self.base_url}{self.path}"
        try:
            response = httpx.post(
                url,
                json=request.model_dump(mode="json"),
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise OrchestratorApiError("api_timeout", "consultation orchestrator timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise OrchestratorApiError("api_unavailable", "consultation orchestrator is unavailable", 503) from exc

        if response.status_code >= 400:
            code = "api_unavailable"
            message = response.text
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            detail = payload.get("detail", payload)
            if isinstance(detail, dict):
                code = str(detail.get("code", code))
                message = str(detail.get("message", message))
            elif response.status_code == 504:
                code = "api_timeout"
            raise OrchestratorApiError(code, message, response.status_code)

        return ConsultationOrchestratorResponse.model_validate(response.json())


class GatewayService:
    def __init__(self, settings: GatewaySettings, orchestrator_client: OrchestratorClient | None = None) -> None:
        self.settings = settings
        self.orchestrator_client = orchestrator_client or HttpOrchestratorClient(settings)

    def handle_event(self, event: OpenClawStandardMessageEvent, shared_token: str | None) -> GatewayInboundResponse:
        request_id = uuid4().hex
        audit_events: list[str] = []
        self._audit(audit_events, "incoming_message", request_id, event.model_dump(mode="json", by_alias=True))
        self._check_shared_token(shared_token)

        binding = self.settings.binding_for(event.binding, event.channel)
        route_mode = self._resolve_route_mode(event, binding)
        normalized = self._normalize(event, binding)
        self._audit(audit_events, "normalized_message", request_id, normalized.model_dump(mode="json"))

        if self._should_ignore_group_message(normalized, binding):
            self._audit(
                audit_events,
                "response_status",
                request_id,
                {
                    "response_status": "ignored",
                    "escalation": False,
                    "reason": "group_require_mention",
                },
            )
            return GatewayInboundResponse(
                request_id=request_id,
                accepted=False,
                route_mode=route_mode,
                routed_agent=self.settings.routing.fallback_agent,
                response_status="ignored",
                reply_text="群聊消息未满足 @ 机器人条件，已按安全默认值忽略。",
                normalized_message=normalized,
                audit_events=audit_events,
            )

        self._check_allowlist(event)
        self._check_pairing(event)

        orchestrator_request = ConsultationOrchestratorRequest(
            normalized_message=normalized,
            route_mode=route_mode,
            facts=self._extract_facts(event),
            prefer_llm=event.prefer_llm,
            fallback_agent=self.settings.routing.fallback_agent,
            metadata={"channel_binding": event.binding},
        )

        try:
            orchestrator_response = self.orchestrator_client.orchestrate(orchestrator_request)
        except OrchestratorApiError as exc:
            degraded = self._build_degraded_response(
                request_id=request_id,
                route_mode=route_mode,
                normalized=normalized,
                code=exc.code,
            )
            self._audit(
                audit_events,
                "routed_agent",
                request_id,
                {"route_mode": route_mode.value, "routed_agent": degraded.routed_agent},
            )
            self._audit(
                audit_events,
                "response_status",
                request_id,
                {
                    "response_status": degraded.response_status,
                    "escalation": degraded.escalation,
                    "degradation_code": degraded.degradation_code,
                },
            )
            degraded.audit_events = audit_events
            return degraded

        self._audit(
            audit_events,
            "routed_agent",
            request_id,
            {"route_mode": route_mode.value, "routed_agent": orchestrator_response.routed_agent},
        )
        self._audit(
            audit_events,
            "response_status",
            request_id,
            {
                "response_status": orchestrator_response.response_status,
                "escalation": orchestrator_response.escalation,
                "degradation_code": orchestrator_response.degradation_code,
            },
        )

        return GatewayInboundResponse(
            request_id=request_id,
            accepted=True,
            route_mode=route_mode,
            routed_agent=orchestrator_response.routed_agent,
            response_status=orchestrator_response.response_status,
            escalation=orchestrator_response.escalation,
            degraded=orchestrator_response.response_status == "degraded",
            degradation_code=orchestrator_response.degradation_code,
            reply_text=orchestrator_response.reply_text,
            normalized_message=normalized,
            orchestrator_response=orchestrator_response,
            audit_events=audit_events,
        )

    def _check_shared_token(self, provided_token: str | None) -> None:
        expected = self.settings.security.shared_token.strip()
        if not expected:
            return
        if (provided_token or "").strip() != expected:
            raise GatewayAccessDenied("invalid_gateway_token", "invalid OpenClaw gateway token")

    def _check_allowlist(self, event: OpenClawStandardMessageEvent) -> None:
        allowlist = self.settings.security.allowlist
        if self.settings.security.default_deny:
            if not allowlist.channels:
                raise GatewayAccessDenied("allowlist_not_configured", "channel allowlist is required")
            if event.channel not in allowlist.channels:
                raise GatewayAccessDenied("channel_not_allowed", f"channel '{event.channel}' is not allowed")

        if allowlist.senders and event.sender.sender_id not in allowlist.senders:
            raise GatewayAccessDenied("sender_not_allowed", f"sender '{event.sender.sender_id}' is not allowed")

        if allowlist.peers and event.conversation.peer_id not in allowlist.peers:
            raise GatewayAccessDenied("peer_not_allowed", f"peer '{event.conversation.peer_id}' is not allowed")

    def _check_pairing(self, event: OpenClawStandardMessageEvent) -> None:
        pairing = self.settings.security.pairing
        if not pairing.required:
            return
        if event.sender.sender_id in pairing.trusted_senders:
            return
        paired = event.sender.paired or bool(event.metadata.get(pairing.metadata_key))
        if not paired:
            raise GatewayAccessDenied("pairing_required", "sender must complete pairing before using the gateway")

    def _resolve_route_mode(self, event: OpenClawStandardMessageEvent, binding) -> RouteMode:
        role_tags = set(event.sender.role_tags)
        if role_tags & OPS_ROLE_TAGS:
            return RouteMode.OPERATIONS_SUPPORT
        if role_tags & ADMIN_ROLE_TAGS:
            return RouteMode.ORGANIZATION_ADMIN
        return binding.route_mode

    def _normalize(self, event: OpenClawStandardMessageEvent, binding) -> NormalizedMessage:
        sender_isolated = (
            binding.per_sender_session
            if binding.per_sender_session is not None
            else self.settings.routing.per_sender_session
        )
        peer = NormalizedPeer(
            peer_id=event.conversation.peer_id,
            peer_type=self._peer_type(event.conversation.peer_type),
            thread_id=event.conversation.thread_id,
            require_mention=self._require_mention(binding),
        )
        session = NormalizedSession(
            session_key=self._session_key(event, sender_isolated),
            scope="sender" if sender_isolated else "peer",
            sender_isolated=sender_isolated,
        )
        attachments = [self._normalize_attachment(item) for item in event.message.attachments]
        kind = self._message_kind(event.message.type, attachments)
        return NormalizedMessage(
            event_id=event.event_id,
            message_id=event.message.message_id,
            occurred_at=event.occurred_at,
            channel=event.channel,
            binding=event.binding,
            kind=kind,
            text=event.message.text.strip(),
            mentions_bot=bool(event.message.mentions),
            peer=peer,
            session=session,
            sender=NormalizedSender(
                sender_id=event.sender.sender_id,
                display_name=event.sender.display_name,
                role_tags=event.sender.role_tags,
                paired=event.sender.paired or bool(event.metadata.get(self.settings.security.pairing.metadata_key)),
            ),
            attachments=attachments,
            metadata={
                **event.metadata,
                "raw_message_type": event.message.type,
                "mentions": event.message.mentions,
            },
        )

    def _normalize_attachment(self, attachment) -> NormalizedAttachment:
        attachment_type = attachment.type.lower()
        if attachment_type not in {"image", "document", "voice"}:
            attachment_type = "unknown"
        return NormalizedAttachment(
            attachment_id=attachment.attachment_id,
            type=attachment_type,
            name=attachment.name,
            mime_type=attachment.mime_type,
            url=attachment.url,
            size_bytes=attachment.size_bytes,
            checksum=attachment.checksum,
            metadata=attachment.metadata,
        )

    def _message_kind(self, message_type: str, attachments: list[NormalizedAttachment]) -> str:
        normalized = (message_type or "").lower()
        if normalized in {"text", "image", "document", "voice"}:
            return normalized
        if attachments:
            return attachments[0].type
        return "unknown"

    def _peer_type(self, peer_type: str) -> str:
        normalized = (peer_type or "unknown").lower()
        if normalized in {"direct", "group", "channel"}:
            return normalized
        return "unknown"

    def _require_mention(self, binding) -> bool:
        if binding.require_mention is not None:
            return binding.require_mention
        return self.settings.routing.group.require_mention

    def _session_key(self, event: OpenClawStandardMessageEvent, sender_isolated: bool) -> str:
        parts = [event.channel, event.binding, event.conversation.peer_id]
        if event.conversation.thread_id:
            parts.append(event.conversation.thread_id)
        if sender_isolated:
            parts.append(event.sender.sender_id)
        return ":".join(parts)

    def _should_ignore_group_message(self, normalized: NormalizedMessage, binding) -> bool:
        if normalized.peer.peer_type != "group":
            return False
        return self._require_mention(binding) and not normalized.mentions_bot

    def _extract_facts(self, event: OpenClawStandardMessageEvent) -> StudentFacts:
        facts = event.metadata.get("facts")
        if isinstance(facts, dict):
            return StudentFacts.model_validate(facts)
        return StudentFacts()

    def _build_degraded_response(
        self,
        *,
        request_id: str,
        route_mode: RouteMode,
        normalized: NormalizedMessage,
        code: str,
    ) -> GatewayInboundResponse:
        fallback_text = self._fallback_reply(code)
        answer = AskResponse(
            status=AnswerStatus.HANDOFF,
            question_type="gateway_degraded",
            conclusion=fallback_text,
            consultation_advice="请稍后重试，或转人工客服继续跟进。",
            cannot_confirm_reason="网关已收到消息，但后端咨询能力当前不可安全确认。",
            missing_fields=[],
            evidence=[],
            applicable_conditions=[
                f"channel={normalized.channel}",
                f"session={normalized.session.session_key}",
            ],
            risk_notice=[f"gateway degradation: {code}"],
            next_step="由 fallback agent 接管或等待后端恢复。",
            matched_faq_ids=[],
            used_llm=False,
            customer_reply=fallback_text,
            handoff_message=fallback_text,
        )
        orchestrator_response = ConsultationOrchestratorResponse(
            request_id=request_id,
            route_mode=route_mode,
            routed_agent=self.settings.routing.fallback_agent,
            response_status="degraded",
            escalation=True,
            degradation_code=code,
            reply_text=fallback_text,
            answer=answer,
            metadata={"fallback": True},
        )
        return GatewayInboundResponse(
            request_id=request_id,
            accepted=True,
            route_mode=route_mode,
            routed_agent=orchestrator_response.routed_agent,
            response_status=orchestrator_response.response_status,
            escalation=True,
            degraded=True,
            degradation_code=code,
            reply_text=fallback_text,
            normalized_message=normalized,
            orchestrator_response=orchestrator_response,
        )

    def _fallback_reply(self, code: str) -> str:
        replies = {
            "knowledge_unavailable": "当前知识库暂不可用，已为你转入人工跟进。",
            "api_timeout": "当前咨询服务响应超时，已切换到保守降级回复，请稍后重试。",
            "rule_engine_exception": "当前规则编排异常，已为你转人工复核。",
            "document_index_not_ready": "当前文档索引尚未就绪，建议稍后再试或转人工处理。",
            "api_unavailable": "当前咨询服务不可用，已切换到人工兜底流程。",
        }
        return replies.get(code, "当前咨询服务暂不可用，已转入保守兜底流程。")

    def _audit(self, audit_events: list[str], event_type: str, request_id: str, payload: dict[str, object]) -> None:
        LOGGER.info(
            json.dumps(
                {
                    "event_type": event_type,
                    "request_id": request_id,
                    **payload,
                },
                ensure_ascii=False,
            )
        )
        audit_events.append(event_type)
