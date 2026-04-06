from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    NEED_INFO = "need_info"
    HANDOFF = "handoff"
    OUT_OF_SCOPE = "out_of_scope"


class EscalationAction(str, Enum):
    NONE = "none"
    ASK_FOLLOW_UP = "ask_follow_up"
    HANDOFF_HUMAN = "handoff_human"
    SCOPE_REDIRECT = "scope_redirect"


class ChannelMode(str, Enum):
    PRIVATE = "private"
    GROUP = "group"
    ADMIN = "admin"


class TakeoverStatus(str, Enum):
    BOT = "bot"
    REQUESTED = "requested"
    HUMAN = "human"
    RESOLVED = "resolved"


class StudentFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    child_hukou: Optional[str] = None
    parent_hukou: Optional[str] = None
    parent_work_in_songshanhu: Optional[bool] = None
    employer_type: Optional[str] = None
    has_songshanhu_property: Optional[bool] = None
    property_owner: Optional[str] = None
    stage: Optional[str] = None
    is_transfer: Optional[bool] = None
    special_status: list[str] = Field(default_factory=list)
    dongguan_household: Optional[bool] = None


class ProfileConflict(BaseModel):
    field_name: str
    existing_value: str
    incoming_value: str
    source: str


class SessionContext(BaseModel):
    conversation_id: Optional[str] = None
    remembered_profile: StudentFacts = Field(default_factory=StudentFacts)
    asked_missing_fields: list[str] = Field(default_factory=list)
    follow_up_rounds: int = Field(default=0, ge=0)
    last_intent: Optional[str] = None
    last_scope: Optional[str] = None
    last_escalation_reasons: list[str] = Field(default_factory=list)


class CitationRef(BaseModel):
    source_id: str
    title: str
    page: Optional[str] = None
    chunk_id: str
    quote_snippet: str


class RuleClassification(BaseModel):
    scope: str
    intent: str
    is_case_specific: bool = False
    is_latest_request: bool = False
    asks_for_probability: bool = False
    asks_for_human: bool = False
    platform_status_requires_manual_check: bool = False
    policy_conflict_detected: bool = False
    profile_conflicts: list[ProfileConflict] = Field(default_factory=list)
    missing_critical_fields: list[str] = Field(default_factory=list)


class AnswerPayload(BaseModel):
    status: AnswerStatus
    scope: str
    question_type: str
    initial_conclusion: str
    eligibility_or_issue: str
    judgement_basis: list[str] = Field(default_factory=list)
    required_materials: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    risk_alerts: list[str] = Field(default_factory=list)
    human_support: str
    follow_up_questions: list[str] = Field(default_factory=list)


class EscalationDecision(BaseModel):
    action: EscalationAction
    should_handoff: bool
    reasons: list[str] = Field(default_factory=list)
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    official_contact: str


class SessionUpdate(BaseModel):
    conversation_id: Optional[str] = None
    retained_profile: StudentFacts = Field(default_factory=StudentFacts)
    last_intent: Optional[str] = None
    last_scope: Optional[str] = None
    asked_missing_fields: list[str] = Field(default_factory=list)
    follow_up_rounds: int = Field(default=0, ge=0)
    flags: list[str] = Field(default_factory=list)


class OrchestratorNormalizedMessage(BaseModel):
    message_id: Optional[str] = None
    channel: str = "web"
    channel_mode: ChannelMode = ChannelMode.PRIVATE
    target: Optional[str] = None
    text: str = Field(min_length=1)
    sender_role: str = "user"
    timestamp: Optional[str] = None


class ConsultationOrchestrateRequest(BaseModel):
    normalized_message: OrchestratorNormalizedMessage
    session_context: SessionContext = Field(default_factory=SessionContext)
    user_profile: StudentFacts = Field(default_factory=StudentFacts)
    prefer_llm: bool = False
    top_k: int = Field(default=5, ge=1, le=10)


class ConsultationOrchestrateResponse(BaseModel):
    trace_id: str
    answer_payload: AnswerPayload
    escalation_decision: EscalationDecision
    citations: list[CitationRef] = Field(default_factory=list)
    session_update: SessionUpdate = Field(default_factory=SessionUpdate)
    rule_classification: RuleClassification
    confidence: float = Field(ge=0.0, le=1.0)
    audit_log_path: str


class EvidenceRef(BaseModel):
    source_id: str
    file_name: str
    source_tier: int
    citation: str
    snippet: str
    score: Optional[float] = None
    source_url: Optional[str] = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    facts: StudentFacts = Field(default_factory=StudentFacts)
    session_context: SessionContext = Field(default_factory=SessionContext)
    prefer_llm: bool = False
    top_k: int = Field(default=5, ge=1, le=10)
    conversation_id: Optional[str] = None
    channel: str = "web"
    channel_mode: ChannelMode = ChannelMode.PRIVATE
    entry_point: str = "quick_qa"
    source_session_id: Optional[str] = None
    source_target: Optional[str] = None
    is_openclaw: bool = False


class AskResponse(BaseModel):
    status: AnswerStatus
    question_type: str
    conclusion: str
    consultation_advice: str
    cannot_confirm_reason: str
    missing_fields: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    applicable_conditions: list[str] = Field(default_factory=list)
    risk_notice: list[str] = Field(default_factory=list)
    next_step: str
    matched_faq_ids: list[str] = Field(default_factory=list)
    used_llm: bool = False
    customer_reply: str = ""
    handoff_message: str = ""
    command_preview: Optional[str] = None
    preliminary_judgement: str = ""
    reportable_categories: list[str] = Field(default_factory=list)
    materials_checklist: list[str] = Field(default_factory=list)
    operation_steps: list[str] = Field(default_factory=list)
    human_consultation: str = ""
    resolution_source: str = "unknown"
    trace_id: Optional[str] = None
    confidence: Optional[float] = None
    answer_payload: Optional[AnswerPayload] = None
    escalation_decision: Optional[EscalationDecision] = None
    citations: list[CitationRef] = Field(default_factory=list)
    session_update: Optional[SessionUpdate] = None
    rule_classification: Optional[RuleClassification] = None


class ChatTurn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    timestamp: str
    answer: Optional[AskResponse] = None


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(min_length=1)
    facts: StudentFacts = Field(default_factory=StudentFacts)
    prefer_llm: bool = False
    reset: bool = False
    top_k: int = Field(default=5, ge=1, le=10)
    channel: str = "web"
    channel_mode: ChannelMode = ChannelMode.PRIVATE
    entry_point: str = "quick_qa"
    source_session_id: Optional[str] = None
    source_target: Optional[str] = None
    is_openclaw: bool = False


class ChatResponse(BaseModel):
    conversation_id: str
    reply: AskResponse
    history: list[ChatTurn] = Field(default_factory=list)
    remembered_facts: StudentFacts = Field(default_factory=StudentFacts)
    effective_question: str


class ConversationStateResponse(BaseModel):
    conversation_id: str
    title: str = "新对话"
    updated_at: str = ""
    history: list[ChatTurn] = Field(default_factory=list)
    remembered_facts: StudentFacts = Field(default_factory=StudentFacts)
    channel: str = "web"
    entry_point: str = "quick_qa"
    is_openclaw: bool = False
    source_session_id: Optional[str] = None
    source_target: Optional[str] = None
    manual_takeover: bool = False
    takeover_status: TakeoverStatus = TakeoverStatus.BOT
    takeover_by: Optional[str] = None
    takeover_note: str = ""
    last_resolution_source: Optional[str] = None
    last_question_type: Optional[str] = None


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    updated_at: str
    preview: str
    status: Optional[AnswerStatus] = None
    channel: str = "web"
    entry_point: str = "quick_qa"
    is_openclaw: bool = False
    source_session_id: Optional[str] = None
    source_target: Optional[str] = None
    manual_takeover: bool = False
    takeover_status: TakeoverStatus = TakeoverStatus.BOT
    takeover_by: Optional[str] = None
    last_resolution_source: Optional[str] = None
    last_question_type: Optional[str] = None


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary] = Field(default_factory=list)


class IngestResponse(BaseModel):
    knowledge_path: str
    knowledge_year: int
    available_knowledge_years: list[int] = Field(default_factory=list)
    faq_count: int
    document_chunk_count: int
    source_count: int


class HealthResponse(BaseModel):
    ok: bool
    knowledge_loaded: bool
    knowledge_year: int
    available_knowledge_years: list[int] = Field(default_factory=list)
    llm_enabled: bool
    llm_provider: str
    openclaw_enabled: bool
    default_model: str
    official_contact: str


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdminSessionResponse(BaseModel):
    authenticated: bool
    login_enabled: bool
    username: Optional[str] = None


class OpenClawMessageRequest(BaseModel):
    channel: str
    target: str
    message: str
    channel_mode: ChannelMode = ChannelMode.PRIVATE
    facts: StudentFacts = Field(default_factory=StudentFacts)
    prefer_llm: bool = False
    dry_run: bool = True
    conversation_id: Optional[str] = None
    source_session_id: Optional[str] = None
    reset: bool = False
    sender_id: Optional[str] = None
    thread_id: Optional[str] = None
    mentioned: bool = False
    paired: bool = False
    is_group: bool = False


class OpenClawMessageResponse(BaseModel):
    conversation_id: str
    channel: str
    target: str
    dry_run: bool
    reply_text: str
    command_preview: str
    answer: AskResponse
    routing_key: Optional[str] = None
    delivery_allowed: bool = True
    security_findings: list[str] = Field(default_factory=list)


class RateMetric(BaseModel):
    label: str
    numerator: int
    denominator: int
    ratio: float


class HotQuestionItem(BaseModel):
    question: str
    hits: int
    channels: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    last_seen_at: str


class UnmatchedQuestionItem(BaseModel):
    question: str
    hits: int
    last_seen_at: str
    last_status: str
    conversation_id: Optional[str] = None
    channel: Optional[str] = None


class StaleDocumentAlert(BaseModel):
    file_name: str
    hits: int
    last_seen_at: str
    source_ids: list[str] = Field(default_factory=list)


class FAQAliasRecord(BaseModel):
    alias_id: str
    alias: str
    faq_id: str
    faq_question: str
    note: str = ""
    created_at: str
    updated_at: str


class FAQAliasUpsertRequest(BaseModel):
    alias: str = Field(min_length=1)
    faq_id: str = Field(min_length=1)
    faq_question: str = Field(min_length=1)
    note: str = ""


class FAQAliasListResponse(BaseModel):
    items: list[FAQAliasRecord] = Field(default_factory=list)


class RepairItemRecord(BaseModel):
    repair_id: str
    conversation_id: Optional[str] = None
    kind: Literal["faq", "rule", "prompt", "manual"] = "manual"
    title: str
    problem: str
    proposed_fix: str
    manual_reply: str = ""
    source_channel: str = "web"
    status: Literal["open", "accepted", "dismissed"] = "open"
    created_at: str
    updated_at: str


class RepairItemCreateRequest(BaseModel):
    conversation_id: Optional[str] = None
    kind: Literal["faq", "rule", "prompt", "manual"] = "manual"
    title: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    proposed_fix: str = Field(min_length=1)
    manual_reply: str = ""
    source_channel: str = "web"
    create_alias: Optional[str] = None
    alias_faq_id: Optional[str] = None
    alias_faq_question: Optional[str] = None
    alias_note: str = ""


class RepairItemListResponse(BaseModel):
    items: list[RepairItemRecord] = Field(default_factory=list)


class ManualTakeoverRequest(BaseModel):
    agent_name: str = "人工客服"
    note: str = ""
    status: TakeoverStatus = TakeoverStatus.HUMAN


class OperationsDashboardResponse(BaseModel):
    total_events: int
    total_conversations: int
    openclaw_conversations: int
    pending_takeovers: int
    faq_hit_rate: RateMetric
    rule_hit_rate: RateMetric
    question_heat: list[HotQuestionItem] = Field(default_factory=list)
    unmatched_pool: list[UnmatchedQuestionItem] = Field(default_factory=list)
    stale_document_alerts: list[StaleDocumentAlert] = Field(default_factory=list)
    takeover_queue: list[ConversationSummary] = Field(default_factory=list)
    faq_aliases: list[FAQAliasRecord] = Field(default_factory=list)
    repair_items: list[RepairItemRecord] = Field(default_factory=list)


class NormalizedAttachment(BaseModel):
    attachment_id: str
    type: Literal["image", "document", "voice", "unknown"]
    name: Optional[str] = None
    mime_type: Optional[str] = None
    url: Optional[str] = None
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)


class NormalizedPeer(BaseModel):
    peer_id: str = "unknown-peer"
    peer_type: Literal["direct", "group", "channel", "unknown"] = "unknown"
    thread_id: Optional[str] = None
    require_mention: bool = False


class NormalizedSession(BaseModel):
    session_key: str = "web::stateless"
    scope: Literal["sender", "peer"] = "sender"
    sender_isolated: bool = True


class NormalizedSender(BaseModel):
    sender_id: str = "anonymous"
    display_name: Optional[str] = None
    role_tags: list[str] = Field(default_factory=list)
    paired: bool = False


class NormalizedMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str = "local-event"
    message_id: str = "local-message"
    occurred_at: str = ""
    channel: str = "web"
    binding: str = "local"
    kind: Literal["text", "image", "document", "voice", "unknown"] = "text"
    text: str = ""
    mentions_bot: bool = False
    peer: NormalizedPeer = Field(default_factory=NormalizedPeer)
    session: NormalizedSession = Field(default_factory=NormalizedSession)
    sender: NormalizedSender = Field(default_factory=NormalizedSender)
    attachments: list[NormalizedAttachment] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    channel_mode: ChannelMode = ChannelMode.PRIVATE
    target: str = "web"
    sender_role: str = "parent"
    timestamp: str = ""


class RouteMode(str, Enum):
    PARENT_CONSULTATION = "parent_consultation"
    ORGANIZATION_ADMIN = "organization_admin"
    OPERATIONS_SUPPORT = "operations_support"


class ConsultationOrchestratorRequest(BaseModel):
    normalized_message: NormalizedMessage
    route_mode: RouteMode = RouteMode.PARENT_CONSULTATION
    facts: StudentFacts = Field(default_factory=StudentFacts)
    session_context: SessionContext = Field(default_factory=SessionContext)
    prefer_llm: bool = False
    fallback_agent: str = "fallback-human-handoff"
    metadata: dict[str, object] = Field(default_factory=dict)


class ConsultationOrchestratorResponse(BaseModel):
    request_id: str
    route_mode: RouteMode
    routed_agent: str
    response_status: Literal["answered", "need_info", "handoff", "degraded"]
    escalation: bool = False
    degradation_code: Optional[str] = None
    reply_text: str
    answer: AskResponse
    answer_payload: Optional[AnswerPayload] = None
    escalation_decision: Optional[EscalationDecision] = None
    citations: list[CitationRef] = Field(default_factory=list)
    session_update: Optional[SessionUpdate] = None
    rule_classification: Optional[RuleClassification] = None
    confidence: Optional[float] = None
    audit_log_path: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
