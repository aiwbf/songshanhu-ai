from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ConversationMode(str, Enum):
    DM = "dm"
    GROUP = "group"
    ADMIN = "admin"


class AudienceType(str, Enum):
    PARENT = "parent"
    EMPLOYER_ADMIN = "employer_admin"
    ADMISSIONS_STAFF = "admissions_staff"
    UNKNOWN = "unknown"


class ApplicationStage(str, Enum):
    KINDERGARTEN = "kindergarten"
    PRIMARY = "primary"
    JUNIOR = "junior"
    TRANSFER = "transfer"
    UNKNOWN = "unknown"


class CaseCategory(str, Enum):
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    C = "C"
    UNRESOLVED = "UNRESOLVED"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    HISTORICAL_ONLY = "historical_only"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SpecialProgram(str, Enum):
    TALENT_CARD = "talent_card"
    GUANGDONG_TALENT_CARD = "guangdong_talent_card"
    OVERSEAS_CHINESE = "overseas_chinese"
    TAIWAN_STUDENT = "taiwan_student"
    HK_MACAO_CHILD = "hk_macao_child"
    POINTS_ADMISSION = "points_admission"
    PROPERTY_LOCK = "property_lock"
    PROPERTY_UNLOCK = "property_unlock"
    PROFILE_UPDATE = "profile_update"
    UNIT_ACCOUNT_REGISTRATION = "unit_account_registration"
    UNIT_ADMIN_REVIEW = "unit_admin_review"


class PropertyLockStatus(str, Enum):
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class UnitAccountStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    UNREGISTERED = "unregistered"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    NEED_INFO = "need_info"
    HANDOFF = "handoff"
    OUT_OF_SCOPE = "out_of_scope"
    UNAVAILABLE = "unavailable"


class EscalationReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    MISSING_REQUIRED_FACTS = "missing_required_facts"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    NO_CURRENT_POLICY = "no_current_policy"
    NO_GROUNDED_EVIDENCE = "no_grounded_evidence"
    POLICY_INTERPRETATION_RISK = "policy_interpretation_risk"
    OUT_OF_SCOPE = "out_of_scope"
    SERVICE_DEGRADED = "service_degraded"
    USER_REQUESTED_HUMAN = "user_requested_human"


class NormalizedActor(ContractModel):
    actor_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    display_name: str | None = None
    org_id: str | None = None
    is_admin: bool = False


class MessageAttachment(ContractModel):
    attachment_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    mime_type: str | None = None
    url: str | None = None
    checksum: str | None = None


class RoutingPolicy(ContractModel):
    agent_profile_id: str = Field(min_length=1)
    fallback_agent_profile_id: str | None = None
    conversation_mode: ConversationMode
    pairing_enabled: bool = False
    require_mention: bool = False
    allowlist_id: str | None = None
    binding_id: str | None = None


class NormalizedMessage(ContractModel):
    schema_version: str = "2026-03-08"
    message_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    channel_message_id: str = Field(min_length=1)
    conversation_mode: ConversationMode
    channel_space_id: str = Field(min_length=1)
    peer_id: str = Field(min_length=1)
    thread_id: str | None = None
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    sender: NormalizedActor
    text: str = Field(min_length=1)
    mentions: list[str] = Field(default_factory=list)
    attachments: list[MessageAttachment] = Field(default_factory=list)
    received_at: datetime
    routing: RoutingPolicy
    raw_payload_ref: str | None = None
    safety_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseProfile(ContractModel):
    case_id: str = Field(min_length=1)
    audience_type: AudienceType = AudienceType.UNKNOWN
    requested_school_year: int | None = Field(default=None, ge=2024, le=2100)
    application_stage: ApplicationStage = ApplicationStage.UNKNOWN
    student_hukou_region: str | None = None
    parent_hukou_region: str | None = None
    resides_in_songshanhu: bool | None = None
    works_in_songshanhu: bool | None = None
    has_property_in_songshanhu: bool | None = None
    property_lock_status: PropertyLockStatus = PropertyLockStatus.UNKNOWN
    unit_account_status: UnitAccountStatus = UnitAccountStatus.NOT_APPLICABLE
    special_programs: list[SpecialProgram] = Field(default_factory=list)
    intent_tags: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    pii_redacted_summary: str | None = None
    last_updated_at: datetime | None = None


class ClassificationResult(ContractModel):
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    category_code: CaseCategory
    confidence: float = Field(ge=0.0, le=1.0)
    requires_clarification: bool = False
    manual_review_required: bool = False
    rule_hits: list[str] = Field(default_factory=list)
    matched_special_programs: list[SpecialProgram] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    disqualifiers: list[str] = Field(default_factory=list)
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    rationale: str = Field(min_length=1)
    generated_at: datetime


class EvidenceHit(ContractModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    page: int = Field(ge=1)
    chunk_id: str = Field(min_length=1)
    snippet: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    policy_priority: int = Field(default=99, ge=0)
    effective_from: date | None = None
    effective_to: date | None = None
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnswerPayload(ContractModel):
    answer_id: str = Field(min_length=1)
    status: AnswerStatus
    answer_strategy: str = Field(min_length=1)
    category_statement: str = Field(min_length=1)
    basis_explanation: str = Field(min_length=1)
    operation_guidance: list[str] = Field(default_factory=list)
    material_checklist: list[str] = Field(default_factory=list)
    evidence: list[EvidenceHit] = Field(default_factory=list)
    risk_notices: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    escalation_preview: str | None = None
    rendered_text: str | None = None
    created_at: datetime


class EscalationDecision(ContractModel):
    decision_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    escalate: bool = True
    reasons: list[EscalationReason] = Field(default_factory=list)
    target_queue: str = Field(min_length=1)
    handoff_summary: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    required_context_refs: list[str] = Field(default_factory=list)
    sla_minutes: int | None = Field(default=None, ge=1)
    decided_at: datetime
