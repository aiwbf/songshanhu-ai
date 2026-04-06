from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.assistant import AdmissionsAssistant
from app.models import (
    AnswerStatus,
    AskRequest,
    AskResponse,
    ConsultationOrchestratorRequest,
    ConsultationOrchestratorResponse,
    RouteMode,
)


@dataclass(frozen=True)
class AgentProfile:
    name: str
    escalation_default: bool = False


class ConsultationOrchestrator:
    def __init__(self, assistant: AdmissionsAssistant) -> None:
        self.assistant = assistant
        self.agent_profiles = {
            RouteMode.PARENT_CONSULTATION: AgentProfile(name="admissions-consultation"),
            RouteMode.ORGANIZATION_ADMIN: AgentProfile(name="organization-review-process"),
            RouteMode.OPERATIONS_SUPPORT: AgentProfile(name="operations-console", escalation_default=False),
        }

    def orchestrate(self, request: ConsultationOrchestratorRequest) -> ConsultationOrchestratorResponse:
        profile = self.agent_profiles.get(
            request.route_mode,
            AgentProfile(name=request.fallback_agent, escalation_default=True),
        )
        answer = self._dispatch_to_agent(request=request, agent_profile=profile)
        response_status = self._status_from_answer(answer)
        escalation = profile.escalation_default or answer.status in {
            AnswerStatus.HANDOFF,
            AnswerStatus.OUT_OF_SCOPE,
        }
        return ConsultationOrchestratorResponse(
            request_id=uuid4().hex,
            route_mode=request.route_mode,
            routed_agent=profile.name,
            response_status=response_status,
            escalation=escalation,
            reply_text=answer.customer_reply or answer.conclusion,
            answer=answer,
            metadata={
                "channel": request.normalized_message.channel,
                "session_key": request.normalized_message.session.session_key,
                "binding": request.normalized_message.binding,
            },
        )

    def _dispatch_to_agent(
        self,
        *,
        request: ConsultationOrchestratorRequest,
        agent_profile: AgentProfile,
    ) -> AskResponse:
        message = request.normalized_message
        if message.kind == "voice":
            return self.assistant.build_response(
                status=AnswerStatus.NEED_INFO,
                question_type="voice_placeholder",
                conclusion="当前渠道已接收语音占位消息，但尚未启用语音转写。",
                consultation_advice="请补充文字描述，或由人工客服继续跟进。",
                cannot_confirm_reason="语音内容尚未被转写为可检索文本，当前无法进行自动判断。",
                missing_fields=["请补充文字内容"],
                evidence=[],
                conditions=[],
                risk_notice=["语音处理能力尚未启用，当前仅保留附件元数据。"],
                next_step="补充文字后可继续在同一会话内咨询。",
            )

        answer = self.assistant.answer(
            AskRequest(
                question=message.text or self._attachment_summary(message.attachments),
                facts=request.facts,
                prefer_llm=request.prefer_llm,
            )
        )
        if request.route_mode != RouteMode.PARENT_CONSULTATION:
            answer.risk_notice = list(
                dict.fromkeys(
                    [
                        *answer.risk_notice,
                        f"当前消息已通过 {agent_profile.name} profile 进入咨询编排层。",
                    ]
                )
            )
        return answer

    def _attachment_summary(self, attachments: list[object]) -> str:
        if not attachments:
            return "未提供文本内容。"
        return f"收到 {len(attachments)} 个附件，请结合附件元数据进行人工复核。"

    def _status_from_answer(self, answer: AskResponse) -> str:
        if answer.status == AnswerStatus.ANSWERED:
            return "answered"
        if answer.status == AnswerStatus.NEED_INFO:
            return "need_info"
        return "handoff"
