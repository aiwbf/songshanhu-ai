from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import ConsultationOrchestratorResponse, NormalizedMessage, RouteMode


class OpenClawInboundAttachment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    attachment_id: str = Field(alias="attachmentId")
    type: str
    name: Optional[str] = None
    mime_type: Optional[str] = Field(default=None, alias="mimeType")
    url: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, alias="sizeBytes")
    checksum: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)


class OpenClawInboundSender(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    sender_id: str = Field(alias="senderId")
    display_name: Optional[str] = Field(default=None, alias="displayName")
    role_tags: list[str] = Field(default_factory=list, alias="roleTags")
    paired: bool = False


class OpenClawInboundConversation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    peer_id: str = Field(alias="peerId")
    peer_type: str = Field(default="unknown", alias="peerType")
    thread_id: Optional[str] = Field(default=None, alias="threadId")


class OpenClawInboundMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    message_id: str = Field(alias="messageId")
    type: str = "text"
    text: str = ""
    mentions: list[str] = Field(default_factory=list)
    attachments: list[OpenClawInboundAttachment] = Field(default_factory=list)


class OpenClawStandardMessageEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event_id: str = Field(alias="eventId")
    occurred_at: str = Field(alias="occurredAt")
    channel: str
    binding: str = "default"
    sender: OpenClawInboundSender
    conversation: OpenClawInboundConversation
    message: OpenClawInboundMessage
    metadata: dict[str, object] = Field(default_factory=dict)
    prefer_llm: bool = Field(default=False, alias="preferLlm")


class GatewayInboundResponse(BaseModel):
    request_id: str
    accepted: bool
    route_mode: RouteMode
    routed_agent: str
    response_status: str
    escalation: bool = False
    degraded: bool = False
    degradation_code: Optional[str] = None
    reply_text: str
    normalized_message: Optional[NormalizedMessage] = None
    orchestrator_response: Optional[ConsultationOrchestratorResponse] = None
    audit_events: list[str] = Field(default_factory=list)
