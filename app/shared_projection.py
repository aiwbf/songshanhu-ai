from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.models import (
    AnswerPayload as LegacyAnswerPayload,
    ChannelMode,
    CitationRef,
    EscalationAction,
    EscalationDecision as LegacyEscalationDecision,
    NormalizedAttachment,
    NormalizedMessage as LegacyNormalizedMessage,
    OrchestratorNormalizedMessage,
    RouteMode,
    RuleClassification,
    SessionUpdate,
    StudentFacts,
)
from app.knowledge import KnowledgeStore
from packages.shared.contracts import (
    AnswerPayload,
    AnswerStatus,
    ApplicationStage,
    AudienceType,
    CaseCategory,
    CaseProfile,
    ClassificationResult,
    ConversationMode,
    EscalationDecision,
    EscalationReason,
    EvidenceHit,
    FreshnessStatus,
    MessageAttachment,
    NormalizedActor,
    NormalizedMessage,
    PropertyLockStatus,
    RoutingPolicy,
    SpecialProgram,
    UnitAccountStatus,
)


CASE_CODE_PATTERN = re.compile(r"\b(A1|A2|A3|B1|B2|B3|C)\b", re.IGNORECASE)
PAGE_NUMBER_PATTERN = re.compile(r"(\d+)")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _conversation_mode_from_message(message: LegacyNormalizedMessage, route_mode: RouteMode) -> ConversationMode:
    if route_mode == RouteMode.ORGANIZATION_ADMIN:
        return ConversationMode.ADMIN
    if getattr(message, "peer", None) is not None and message.peer.peer_type == "group":
        return ConversationMode.GROUP
    if getattr(message, "channel_mode", None) == ChannelMode.GROUP:
        return ConversationMode.GROUP
    return ConversationMode.DM


def _channel_mode_to_conversation_mode(mode: ChannelMode | None) -> ConversationMode:
    if mode == ChannelMode.ADMIN:
        return ConversationMode.ADMIN
    if mode == ChannelMode.GROUP:
        return ConversationMode.GROUP
    return ConversationMode.DM


def _audience_type(message: LegacyNormalizedMessage, route_mode: RouteMode) -> AudienceType:
    sender = getattr(message, "sender", None)
    tags = {item.lower() for item in getattr(sender, "role_tags", [])}
    if not tags and getattr(message, "sender_role", None):
        tags = {str(message.sender_role).lower()}
    if route_mode == RouteMode.ORGANIZATION_ADMIN or tags & {"unit_admin", "organization_admin", "school_admin"}:
        return AudienceType.EMPLOYER_ADMIN
    if route_mode == RouteMode.OPERATIONS_SUPPORT or tags & {"operations", "human_support", "manual_support"}:
        return AudienceType.ADMISSIONS_STAFF
    return AudienceType.PARENT


def _application_stage(stage: str | None) -> ApplicationStage:
    value = (stage or "").lower()
    if not value:
        return ApplicationStage.UNKNOWN
    if any(token in value for token in ("幼儿园", "kindergarten")):
        return ApplicationStage.KINDERGARTEN
    if any(token in value for token in ("小学", "primary")):
        return ApplicationStage.PRIMARY
    if any(token in value for token in ("初中", "junior")):
        return ApplicationStage.JUNIOR
    if any(token in value for token in ("转学", "transfer", "非起始")):
        return ApplicationStage.TRANSFER
    return ApplicationStage.UNKNOWN


def _special_programs(statuses: list[str]) -> list[SpecialProgram]:
    values: list[SpecialProgram] = []
    for item in statuses:
        if "优才" in item or "浼樻墠" in item:
            values.append(SpecialProgram.TALENT_CARD)
        if "优粤" in item or "浼樼菠" in item:
            values.append(SpecialProgram.GUANGDONG_TALENT_CARD)
        if "华侨" in item or "华人" in item or "鍗庝鲸" in item or "鍗庝汉" in item:
            values.append(SpecialProgram.OVERSEAS_CHINESE)
        if "台湾" in item or "鍙版咕" in item:
            values.append(SpecialProgram.TAIWAN_STUDENT)
        if "香港" in item or "澳门" in item or "棣欐腐" in item or "婢抽棬" in item:
            values.append(SpecialProgram.HK_MACAO_CHILD)
        if "积分" in item or "绉垎" in item:
            values.append(SpecialProgram.POINTS_ADMISSION)
        if "房产锁定" in item or "閿佸畾" in item:
            values.append(SpecialProgram.PROPERTY_LOCK)
        if "房产解锁" in item or "瑙ｉ攣" in item:
            values.append(SpecialProgram.PROPERTY_UNLOCK)
        if "资料修改" in item or "淇敼" in item:
            values.append(SpecialProgram.PROFILE_UPDATE)
        if "单位账号" in item or "鍗曚綅璐﹀彿" in item:
            values.append(SpecialProgram.UNIT_ACCOUNT_REGISTRATION)
        if "管理员审核" in item or "瀹℃牳" in item:
            values.append(SpecialProgram.UNIT_ADMIN_REVIEW)
    return list(dict.fromkeys(values))


def _property_lock_status(answer: LegacyAnswerPayload, facts: StudentFacts) -> PropertyLockStatus:
    text = " ".join(
        filter(
            None,
            [
                answer.question_type,
                answer.initial_conclusion,
                answer.eligibility_or_issue,
            ],
        )
    )
    if "解锁" in text or "瑙ｉ攣" in text:
        return PropertyLockStatus.LOCKED
    if "锁定" in text or "閿佸畾" in text:
        return PropertyLockStatus.LOCKED
    if facts.has_songshanhu_property is False:
        return PropertyLockStatus.NOT_APPLICABLE
    return PropertyLockStatus.UNKNOWN


def _unit_account_status(answer: LegacyAnswerPayload) -> UnitAccountStatus:
    text = " ".join(
        filter(
            None,
            [
                answer.question_type,
                answer.initial_conclusion,
                answer.eligibility_or_issue,
            ],
        )
    )
    if "单位账号" not in text and "鍗曚綅璐﹀彿" not in text and "管理员" not in text and "绠＄悊鍛?" not in text:
        return UnitAccountStatus.NOT_APPLICABLE
    if "审核中" in text or "待审核" in text or "瀹℃牳涓?" in text or "寰呭鏍?" in text:
        return UnitAccountStatus.PENDING_REVIEW
    if "通过" in text or "approved" in text:
        return UnitAccountStatus.APPROVED
    if "驳回" in text or "rejected" in text:
        return UnitAccountStatus.REJECTED
    return UnitAccountStatus.UNREGISTERED


def _freshness_status(answer: LegacyAnswerPayload, citations: list[CitationRef]) -> FreshnessStatus:
    joined = " ".join(answer.risk_alerts + [item.title for item in citations] + [item.page or "" for item in citations])
    if any(token in joined for token in ("2024", "历史", "鍘嗗彶", "过期", "杩囨湡")):
        return FreshnessStatus.HISTORICAL_ONLY
    return FreshnessStatus.UNKNOWN


def _answer_status(status: Any) -> AnswerStatus:
    raw = getattr(status, "value", status)
    if raw == "out_of_scope":
        return AnswerStatus.OUT_OF_SCOPE
    if raw == "need_info":
        return AnswerStatus.NEED_INFO
    if raw == "handoff":
        return AnswerStatus.HANDOFF
    if raw == "answered":
        return AnswerStatus.ANSWERED
    return AnswerStatus.UNAVAILABLE


def _escalation_reasons(
    escalation: LegacyEscalationDecision,
    classification: RuleClassification | None,
    answer: LegacyAnswerPayload,
) -> list[EscalationReason]:
    mapped: list[EscalationReason] = []
    raw_reasons = [str(item) for item in escalation.reasons]
    combined = " ".join(raw_reasons + [answer.initial_conclusion, answer.eligibility_or_issue])
    if classification and classification.missing_critical_fields:
        mapped.append(EscalationReason.MISSING_REQUIRED_FACTS)
    if classification and classification.policy_conflict_detected:
        mapped.append(EscalationReason.CONFLICTING_EVIDENCE)
    if classification and classification.is_latest_request:
        mapped.append(EscalationReason.NO_CURRENT_POLICY)
    if classification and classification.platform_status_requires_manual_check:
        mapped.append(EscalationReason.POLICY_INTERPRETATION_RISK)
    if classification and classification.scope == "out_of_scope":
        mapped.append(EscalationReason.OUT_OF_SCOPE)
    if any(token in combined for token in ("low_confidence", "置信", "confidence")):
        mapped.append(EscalationReason.LOW_CONFIDENCE)
    if any(token in combined for token in ("user_requested_human", "人工", "浜哄伐")):
        mapped.append(EscalationReason.USER_REQUESTED_HUMAN)
    if escalation.action == EscalationAction.SCOPE_REDIRECT:
        mapped.append(EscalationReason.OUT_OF_SCOPE)
    if escalation.action == EscalationAction.ASK_FOLLOW_UP and EscalationReason.MISSING_REQUIRED_FACTS not in mapped:
        mapped.append(EscalationReason.MISSING_REQUIRED_FACTS)
    if escalation.action == EscalationAction.HANDOFF_HUMAN and not mapped:
        mapped.append(EscalationReason.POLICY_INTERPRETATION_RISK)
    return list(dict.fromkeys(mapped))


def _parse_page_number(page: str | None) -> int:
    if not page:
        return 1
    match = PAGE_NUMBER_PATTERN.search(page)
    if not match:
        return 1
    return max(1, int(match.group(1)))


def _infer_case_category(answer: LegacyAnswerPayload, classification: RuleClassification | None) -> CaseCategory:
    text = " ".join(
        filter(
            None,
            [
                answer.question_type,
                answer.initial_conclusion,
                answer.eligibility_or_issue,
                *(classification.missing_critical_fields if classification else []),
            ],
        )
    )
    match = CASE_CODE_PATTERN.search(text)
    if match:
        return CaseCategory(match.group(1).upper())
    if "C类" in text or "C绫?" in text:
        return CaseCategory.C
    return CaseCategory.UNRESOLVED


def _attachments(items: list[NormalizedAttachment]) -> list[MessageAttachment]:
    attachments: list[MessageAttachment] = []
    for item in items:
        attachments.append(
            MessageAttachment(
                attachment_id=item.attachment_id,
                kind=item.type,
                name=item.name or item.attachment_id,
                mime_type=item.mime_type,
                url=item.url,
                checksum=item.checksum,
            )
        )
    return attachments


def _message_text(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    return getattr(message, "text", "") or "(empty)"


def _message_channel(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    return getattr(message, "channel", "web") or "web"


def _message_id(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    return getattr(message, "message_id", "local-message") or "local-message"


def _message_trace_id(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    return getattr(message, "event_id", None) or _message_id(message)


def _peer_id(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    peer = getattr(message, "peer", None)
    if peer is not None:
        return peer.peer_id
    return getattr(message, "target", None) or _message_channel(message)


def _thread_id(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str | None:
    peer = getattr(message, "peer", None)
    if peer is not None:
        return peer.thread_id
    return None


def _sender_id(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    sender = getattr(message, "sender", None)
    if sender is not None:
        return sender.sender_id
    return getattr(message, "target", None) or "anonymous"


def _sender_display_name(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str | None:
    sender = getattr(message, "sender", None)
    if sender is not None:
        return sender.display_name
    return None


def _sender_role(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    sender = getattr(message, "sender", None)
    if sender is not None and sender.role_tags:
        return sender.role_tags[0]
    return getattr(message, "sender_role", None) or "user"


def _sender_paired(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> bool:
    sender = getattr(message, "sender", None)
    if sender is not None:
        return bool(sender.paired)
    return False


def _binding_id(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    return getattr(message, "binding", None) or getattr(message, "channel", "web")


def _attachments_from_message(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> list[MessageAttachment]:
    items = getattr(message, "attachments", None)
    if not items:
        return []
    return _attachments(items)


def _mentions(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> list[str]:
    metadata = getattr(message, "metadata", {}) or {}
    if isinstance(metadata.get("mentions"), list):
        return list(metadata["mentions"])
    return []


def _require_mention(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> bool:
    peer = getattr(message, "peer", None)
    if peer is not None:
        return bool(peer.require_mention)
    return getattr(message, "channel_mode", None) == ChannelMode.GROUP


def _session_key(message: LegacyNormalizedMessage | OrchestratorNormalizedMessage) -> str:
    session = getattr(message, "session", None)
    if session is not None:
        return session.session_key
    return f"{_message_channel(message)}:{_peer_id(message)}:{_sender_id(message)}"


def project_normalized_message(
    *,
    message: LegacyNormalizedMessage | OrchestratorNormalizedMessage,
    route_mode: RouteMode,
    routed_agent: str,
    fallback_agent: str | None,
) -> NormalizedMessage:
    conversation_mode = _conversation_mode_from_message(message, route_mode)
    return NormalizedMessage(
        message_id=_message_id(message),
        trace_id=_message_trace_id(message),
        channel=_message_channel(message),
        channel_message_id=_message_id(message),
        conversation_mode=conversation_mode,
        channel_space_id=_peer_id(message) or _binding_id(message),
        peer_id=_peer_id(message),
        thread_id=_thread_id(message),
        sender=NormalizedActor(
            actor_id=_sender_id(message),
            role=_sender_role(message),
            display_name=_sender_display_name(message),
            is_admin=conversation_mode == ConversationMode.ADMIN,
        ),
        text=_message_text(message),
        mentions=_mentions(message),
        attachments=_attachments_from_message(message),
        received_at=_utc_now(),
        routing=RoutingPolicy(
            agent_profile_id=routed_agent,
            fallback_agent_profile_id=fallback_agent,
            conversation_mode=conversation_mode,
            pairing_enabled=_sender_paired(message),
            require_mention=_require_mention(message),
            binding_id=_binding_id(message),
        ),
        raw_payload_ref=f"{_message_channel(message)}:{_message_id(message)}",
        safety_flags=[
            flag
            for flag in [
                "mentions_bot" if bool(getattr(message, "mentions_bot", False)) else "",
                "group_require_mention" if _require_mention(message) else "",
                "paired_sender" if _sender_paired(message) else "",
            ]
            if flag
        ],
        metadata=dict(getattr(message, "metadata", {}) or {}),
    )


def project_case_profile(
    *,
    facts: StudentFacts,
    message: LegacyNormalizedMessage | OrchestratorNormalizedMessage,
    route_mode: RouteMode,
    answer: LegacyAnswerPayload,
    session_update: SessionUpdate | None,
) -> CaseProfile:
    current_facts = session_update.retained_profile if session_update is not None else facts
    return CaseProfile(
        case_id=session_update.conversation_id if session_update and session_update.conversation_id else _session_key(message),
        audience_type=_audience_type(message, route_mode),
        requested_school_year=2024,
        application_stage=_application_stage(current_facts.stage),
        student_hukou_region=current_facts.child_hukou,
        parent_hukou_region=current_facts.parent_hukou,
        resides_in_songshanhu=current_facts.has_songshanhu_property,
        works_in_songshanhu=current_facts.parent_work_in_songshanhu,
        has_property_in_songshanhu=current_facts.has_songshanhu_property,
        property_lock_status=_property_lock_status(answer, current_facts),
        unit_account_status=_unit_account_status(answer),
        special_programs=_special_programs(current_facts.special_status),
        intent_tags=[tag for tag in [answer.question_type, answer.scope] if tag],
        facts=current_facts.model_dump(exclude_none=True),
        missing_fields=list(session_update.asked_missing_fields if session_update else []),
        evidence_requirements=["source_id", "title", "page", "chunk_id"],
        pii_redacted_summary="; ".join(
            filter(
                None,
                [
                    current_facts.child_hukou,
                    current_facts.parent_hukou,
                    current_facts.stage,
                ],
            )
        )
        or None,
        last_updated_at=_utc_now(),
    )


def project_evidence_hits(*, citations: list[CitationRef], knowledge: KnowledgeStore | None) -> list[EvidenceHit]:
    results: list[EvidenceHit] = []
    for item in citations:
        source_meta = knowledge.source_for(item.source_id) if knowledge is not None and item.source_id in knowledge.source_map else {}
        results.append(
            EvidenceHit(
                source_id=item.source_id,
                title=item.title,
                page=_parse_page_number(item.page),
                chunk_id=item.chunk_id,
                snippet=item.quote_snippet,
                source_type=str(source_meta.get("suffix") or source_meta.get("source_type") or "document"),
                score=None,
                policy_priority=int(source_meta.get("source_tier") or 99),
                freshness_status=FreshnessStatus.HISTORICAL_ONLY
                if "2024" in (item.title or "") or "2024" in (item.page or "")
                else FreshnessStatus.UNKNOWN,
                metadata={
                    "raw_page": item.page,
                    "file_name": source_meta.get("file_name"),
                    "source_tier": source_meta.get("source_tier"),
                },
            )
        )
    return results


def project_classification(
    *,
    trace_id: str,
    message: LegacyNormalizedMessage | OrchestratorNormalizedMessage,
    classification: RuleClassification | None,
    answer: LegacyAnswerPayload,
    session_update: SessionUpdate | None,
    confidence: float | None,
) -> ClassificationResult:
    current_facts = session_update.retained_profile if session_update is not None else StudentFacts()
    rationale_parts = [
        classification.intent if classification else answer.question_type,
        answer.initial_conclusion,
        answer.eligibility_or_issue,
    ]
    return ClassificationResult(
        run_id=trace_id,
        case_id=session_update.conversation_id if session_update and session_update.conversation_id else _session_key(message),
        intent=classification.intent if classification else answer.question_type or "unknown",
        category_code=_infer_case_category(answer, classification),
        confidence=float(confidence if confidence is not None else 0.0),
        requires_clarification=bool(classification.missing_critical_fields if classification else answer.follow_up_questions),
        manual_review_required=bool(
            classification.platform_status_requires_manual_check if classification else False
        ),
        rule_hits=[
            item
            for item in [
                classification.intent if classification else "",
                "latest_request" if classification and classification.is_latest_request else "",
                "scope_out" if classification and classification.scope == "out_of_scope" else "",
                "manual_review" if classification and classification.platform_status_requires_manual_check else "",
            ]
            if item
        ],
        matched_special_programs=_special_programs(current_facts.special_status),
        missing_fields=list(classification.missing_critical_fields if classification else answer.follow_up_questions),
        disqualifiers=[
            item.field_name
            for item in (classification.profile_conflicts if classification else [])
        ],
        freshness_status=_freshness_status(answer, []),
        rationale=" | ".join(part for part in rationale_parts if part),
        generated_at=_utc_now(),
    )


def project_answer_payload(
    *,
    trace_id: str,
    answer: LegacyAnswerPayload,
    evidence_hits: list[EvidenceHit],
    rendered_text: str | None = None,
    escalation_preview: str | None = None,
) -> AnswerPayload:
    basis = " ".join(answer.judgement_basis).strip() or answer.eligibility_or_issue
    return AnswerPayload(
        answer_id=trace_id,
        status=_answer_status(answer.status),
        answer_strategy="rule_first_grounded_answer",
        category_statement=answer.initial_conclusion,
        basis_explanation=basis,
        operation_guidance=list(answer.next_actions),
        material_checklist=list(answer.required_materials),
        evidence=evidence_hits,
        risk_notices=list(answer.risk_alerts),
        follow_up_questions=list(answer.follow_up_questions),
        escalation_preview=escalation_preview,
        rendered_text=rendered_text,
        created_at=_utc_now(),
    )


def project_escalation_decision(
    *,
    message: LegacyNormalizedMessage | OrchestratorNormalizedMessage,
    route_mode: RouteMode,
    answer: LegacyAnswerPayload,
    escalation: LegacyEscalationDecision,
    classification: RuleClassification | None,
    citations: list[CitationRef],
    session_update: SessionUpdate | None,
) -> EscalationDecision:
    queue_name = {
        RouteMode.PARENT_CONSULTATION: "parent-consultation-handoff",
        RouteMode.ORGANIZATION_ADMIN: "organization-admin-review",
        RouteMode.OPERATIONS_SUPPORT: "operations-console",
    }.get(route_mode, "parent-consultation-handoff")
    if escalation.action == EscalationAction.ASK_FOLLOW_UP:
        queue_name = "follow-up-clarification"
    if escalation.action == EscalationAction.SCOPE_REDIRECT:
        queue_name = "scope-redirect"
    return EscalationDecision(
        decision_id=f"esc-{_message_id(message)}",
        case_id=session_update.conversation_id if session_update and session_update.conversation_id else _session_key(message),
        escalate=bool(escalation.should_handoff or escalation.action != EscalationAction.NONE),
        reasons=_escalation_reasons(escalation, classification, answer),
        target_queue=queue_name,
        handoff_summary=escalation.summary,
        user_message=answer.human_support,
        required_context_refs=[item.chunk_id for item in citations],
        sla_minutes=30 if escalation.should_handoff else None,
        decided_at=_utc_now(),
    )


def build_shared_contract_snapshot(
    *,
    trace_id: str,
    message: LegacyNormalizedMessage | OrchestratorNormalizedMessage,
    route_mode: RouteMode,
    routed_agent: str,
    fallback_agent: str | None,
    facts: StudentFacts,
    answer: LegacyAnswerPayload,
    escalation: LegacyEscalationDecision,
    citations: list[CitationRef],
    session_update: SessionUpdate | None,
    classification: RuleClassification | None,
    confidence: float | None,
    knowledge: KnowledgeStore | None = None,
    rendered_text: str | None = None,
) -> dict[str, Any]:
    normalized_message = project_normalized_message(
        message=message,
        route_mode=route_mode,
        routed_agent=routed_agent,
        fallback_agent=fallback_agent,
    )
    evidence_hits = project_evidence_hits(citations=citations, knowledge=knowledge)
    case_profile = project_case_profile(
        facts=facts,
        message=message,
        route_mode=route_mode,
        answer=answer,
        session_update=session_update,
    )
    classification_result = project_classification(
        trace_id=trace_id,
        message=message,
        classification=classification,
        answer=answer,
        session_update=session_update,
        confidence=confidence,
    )
    escalation_decision = project_escalation_decision(
        message=message,
        route_mode=route_mode,
        answer=answer,
        escalation=escalation,
        classification=classification,
        citations=citations,
        session_update=session_update,
    )
    answer_payload = project_answer_payload(
        trace_id=trace_id,
        answer=answer,
        evidence_hits=evidence_hits,
        rendered_text=rendered_text,
        escalation_preview=escalation.summary,
    )
    return {
        "normalized_message": normalized_message.model_dump(mode="json"),
        "case_profile": case_profile.model_dump(mode="json"),
        "classification_result": classification_result.model_dump(mode="json"),
        "evidence_hits": [item.model_dump(mode="json") for item in evidence_hits],
        "answer_payload": answer_payload.model_dump(mode="json"),
        "escalation_decision": escalation_decision.model_dump(mode="json"),
    }
