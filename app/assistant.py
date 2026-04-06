from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.knowledge import KnowledgeStore
from app.llm_client import LLMSynthesizer, SynthesizedPayload
from app.models import (
    AnswerPayload,
    AnswerStatus,
    AskRequest,
    AskResponse,
    ChannelMode,
    CitationRef,
    ConsultationOrchestratorRequest,
    ConsultationOrchestratorResponse,
    EscalationAction,
    EscalationDecision,
    EvidenceRef,
    NormalizedMessage,
    NormalizedPeer,
    NormalizedSender,
    NormalizedSession,
    RouteMode,
    RuleClassification,
    SessionUpdate,
    StudentFacts,
)
from app.rules import RuleEngine
from app.shared_projection import build_shared_contract_snapshot
from app.utils import compact_snippet, extract_tokens, similarity, token_overlap
from apps.api.audit import AuditLogger
from apps.api.channel_output import render_answer_for_channel
from packages.knowledge import KnowledgeStore as StructuredKnowledgeStore
from packages.knowledge import import_sources, rebuild_markdown_knowledge_base
from packages.rules.engine import RuleEngine as StructuredRuleEngine


PROBABILITY_PATTERNS = ("概率", "录取率", "稳不稳", "包过", "一定能", "保录", "百分之百")
HUMAN_PATTERNS = ("人工", "客服", "老师", "转人工", "人工协助", "人工核验")
PLATFORM_STATUS_PATTERNS = (
    "审核状态",
    "待审核",
    "审核中",
    "名额",
    "剩余学位",
    "还有没有位",
    "平台现在",
    "系统打不开",
    "登录不上",
    "页面报错",
    "当前状态",
)
LATEST_PATTERNS = ("最新", "今年", "当前政策", "现在政策", "目前政策")
HISTORICAL_COMPARISON_PATTERNS = ("还是一样", "是否一样", "沿用", "有变化", "有没有变化", "对比", "比较")
DEFINITION_PATTERNS = ("是什么", "什么意思", "含义", "定义", "如何理解")
COMPARISON_PATTERNS = ("区别", "差别", "不同", "对比", "怎么区分")
CASE_SPECIFIC_PATTERNS = ("我家", "我们家", "孩子", "家长", "如果", "帮我判断", "给我一个确定答案", "这种情况")
ADMISSIONS_HINTS = (
    "招生",
    "入学",
    "学位",
    "报名",
    "转学",
    "插班",
    "平台",
    "户籍",
    "房产",
    "积分",
    "幼儿园",
    "小学",
    "初中",
    "材料",
    "资格",
    "类别",
    "A1",
    "A2",
    "A3",
    "B1",
    "B2",
    "B3",
    "C类",
)
SPECIAL_SOURCE_KEYWORDS = {
    "policy_gd_youyue_2025": ("优粤卡", "优粤"),
    "policy_dg_overseas_chinese_2025": ("华侨", "华人", "华侨学生", "华侨华人"),
    "policy_dg_taiwan_2019": ("台湾", "台胞"),
    "policy_dg_honorary_citizen_2025": ("荣誉市民",),
    "policy_dg_points_2025": ("积分入学", "积分", "C类"),
}
CATEGORY_PATTERN = re.compile(r"(A1|A2|A3|B1|B2|B3)", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
DEFAULT_REFERENCE_DATE = "2026-03-08"


@dataclass(frozen=True)
class EvidenceCandidate:
    source_id: str
    title: str
    page: str | None
    chunk_id: str
    quote_snippet: str
    source_tier: int
    score: float
    source_kind: str
    catalog_source_id: str | None = None


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _merge_student_facts(*facts_list: StudentFacts) -> StudentFacts:
    merged = StudentFacts()
    payload = merged.model_dump()
    for facts in facts_list:
        current = facts.model_dump()
        for key, value in current.items():
            if key == "special_status":
                payload[key] = sorted(set((payload.get(key) or []) + (value or [])))
                continue
            if value is not None and value != "":
                payload[key] = value
    return StudentFacts(**payload)


@dataclass
class AdmissionsAssistant:
    settings: Settings
    rules: RuleEngine
    knowledge: KnowledgeStore
    synthesizer: LLMSynthesizer | None = None
    orchestrator: "AdmissionsAssistant" = field(init=False)
    structured_knowledge: StructuredKnowledgeStore = field(init=False)
    structured_rules: StructuredRuleEngine = field(init=False)
    audit_logger: AuditLogger = field(init=False)
    catalog_source_map: dict[str, str] = field(init=False, default_factory=dict)
    documents_by_source: dict[str, list[dict[str, Any]]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._ensure_bundle_ready()
        self.structured_knowledge = StructuredKnowledgeStore.from_bundle(self.settings.knowledge_bundle_path)
        self.structured_rules = StructuredRuleEngine(
            bundle_path=self.settings.knowledge_bundle_path,
            knowledge_store=self.structured_knowledge,
        )
        self.audit_logger = AuditLogger(self.settings.audit_log_path)
        self.orchestrator = self

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for document in self.knowledge.documents:
            grouped[str(document["source_id"])].append(document)
        self.documents_by_source = dict(grouped)
        self.catalog_source_map = {
            str(source.get("catalog_source_id")): str(source["source_id"])
            for source in self.knowledge.sources
            if source.get("catalog_source_id")
        }

    def _ensure_bundle_ready(self) -> None:
        if not self.settings.knowledge_bundle_path.exists():
            import_sources(
                root=self.settings.root_dir,
                output_path=self.settings.knowledge_bundle_path,
                reference_date=DEFAULT_REFERENCE_DATE,
            )
        rebuild_markdown_knowledge_base(
            root=self.settings.root_dir,
            bundle_path=self.settings.knowledge_bundle_path,
            wiki_dir=self.settings.root_dir / "wiki",
        )

    def answer(self, request: AskRequest) -> AskResponse:
        response = self.orchestrate(
            ConsultationOrchestratorRequest(
                normalized_message=self.build_normalized_message(request),
                route_mode=RouteMode.PARENT_CONSULTATION,
                facts=request.facts,
                session_context=request.session_context,
                prefer_llm=request.prefer_llm,
                metadata={"top_k": request.top_k, "entry_point": request.entry_point},
            )
        )
        return response.answer

    def extract_freeform_facts(self, text: str) -> StudentFacts:
        if hasattr(self.rules, "extract_facts"):
            return self.rules.extract_facts(text)
        return StudentFacts()

    def orchestrate(self, request: ConsultationOrchestratorRequest) -> ConsultationOrchestratorResponse:
        trace_id = uuid4().hex
        question = request.normalized_message.text.strip()
        top_k = self._resolve_top_k(request.metadata.get("top_k"))
        route_mode = request.route_mode
        channel_mode = self.resolve_channel_mode(request)

        extracted_facts = self.extract_freeform_facts(question)
        facts = _merge_student_facts(request.session_context.remembered_profile, request.facts, extracted_facts)
        question_type = self._detect_question_type(question)
        explicit_case_codes = self._explicit_case_codes(question)
        special_catalog_ids = self._special_catalog_ids(question)
        mentioned_years = self._mentioned_years(question)

        structured_profile = self._structured_profile(facts)
        structured_result = self.structured_rules.classify_case(profile=structured_profile, question=question)
        structured_evidence = self.structured_rules.retrieve_evidence(question=question, profile=structured_profile)
        structured_context = self.structured_rules.build_answer_context(
            result=structured_result,
            evidence=structured_evidence,
        ).to_dict()

        scope = self._scope_for(question, question_type)
        is_case_specific = self._is_case_specific(question)
        is_latest_request = self._is_latest_request(question)
        asks_for_probability = any(pattern in question for pattern in PROBABILITY_PATTERNS)
        asks_for_human = any(pattern in question for pattern in HUMAN_PATTERNS)
        platform_status_requires_manual_check = any(pattern in question for pattern in PLATFORM_STATUS_PATTERNS)
        policy_conflict_detected = bool(structured_evidence.get("conflict_detected")) or self._is_cross_year_comparison(
            question,
            mentioned_years,
        )

        missing_fields = self._missing_fields(
            question=question,
            is_case_specific=is_case_specific,
            explicit_case_codes=explicit_case_codes,
            structured_result=structured_result.to_dict(),
        )

        rule_classification = RuleClassification(
            scope=scope,
            intent=question_type,
            is_case_specific=is_case_specific,
            is_latest_request=is_latest_request,
            asks_for_probability=asks_for_probability,
            asks_for_human=asks_for_human,
            platform_status_requires_manual_check=platform_status_requires_manual_check,
            policy_conflict_detected=policy_conflict_detected,
            profile_conflicts=[],
            missing_critical_fields=list(missing_fields),
        )

        candidates = self._collect_evidence(
            question=question,
            top_k=max(6, top_k + 2),
            structured_evidence=structured_evidence,
            special_catalog_ids=special_catalog_ids,
        )
        selected_candidates = self._select_candidates(
            question=question,
            candidates=candidates,
            special_catalog_ids=special_catalog_ids,
            top_k=top_k,
        )
        citations = [self._candidate_to_citation(candidate) for candidate in selected_candidates]

        status = self._decide_status(
            scope=scope,
            classification=rule_classification,
            missing_fields=missing_fields,
            mentioned_years=mentioned_years,
        )
        confidence = self._confidence_for(status=status, citations=citations, missing_fields=missing_fields)

        answer_payload = self._build_answer_payload(
            question=question,
            question_type=question_type,
            status=status,
            facts=facts,
            explicit_case_codes=explicit_case_codes,
            citations=citations,
            missing_fields=missing_fields,
            structured_context=structured_context,
            mentioned_years=mentioned_years,
            special_catalog_ids=special_catalog_ids,
            scope=scope,
        )

        refined = self.refine_with_synthesizer(
            question=question,
            facts=facts,
            answer_payload=answer_payload,
            citations=citations,
            rule_classification=rule_classification,
            prefer_llm=request.prefer_llm,
        )
        used_llm = False
        if refined is not None:
            answer_payload, citations = refined
            used_llm = True

        escalation = self._build_escalation_decision(
            question=question,
            status=answer_payload.status,
            missing_fields=missing_fields,
            scope=scope,
            mentioned_years=mentioned_years,
            confidence=confidence,
        )
        session_update = self._build_session_update(
            request=request,
            facts=facts,
            answer_payload=answer_payload,
            missing_fields=missing_fields,
            question_type=question_type,
            scope=scope,
        )

        answer = self.to_ask_response(
            trace_id=trace_id,
            answer=answer_payload,
            citations=citations,
            escalation=escalation,
            session_update=session_update,
            rule_classification=rule_classification,
            confidence=confidence,
            used_llm=used_llm,
            question=request.normalized_message.text,
        )
        reply_text = render_answer_for_channel(
            trace_id=trace_id,
            answer=answer_payload,
            citations=citations,
            escalation=escalation,
            mode=channel_mode,
        )
        shared_snapshot = build_shared_contract_snapshot(
            trace_id=trace_id,
            message=request.normalized_message,
            route_mode=route_mode,
            routed_agent=self.routed_agent_for(route_mode),
            fallback_agent=request.fallback_agent,
            facts=request.facts,
            answer=answer_payload,
            escalation=escalation,
            citations=citations,
            session_update=session_update,
            classification=rule_classification,
            confidence=confidence,
            knowledge=self.knowledge,
            rendered_text=reply_text,
        )
        audit_log_path = self._persist_audit_log(
            trace_id=trace_id,
            question=question,
            question_type=question_type,
            status=answer_payload.status.value,
            citations=citations,
            scope=scope,
            confidence=confidence,
            missing_fields=missing_fields,
        )

        return ConsultationOrchestratorResponse(
            request_id=trace_id,
            route_mode=route_mode,
            routed_agent=self.routed_agent_for(route_mode),
            response_status=self.gateway_status(answer.status),
            escalation=escalation.should_handoff,
            degradation_code=None,
            reply_text=reply_text,
            answer=answer,
            answer_payload=answer_payload,
            escalation_decision=escalation,
            citations=citations,
            session_update=session_update,
            rule_classification=rule_classification,
            confidence=confidence,
            audit_log_path=audit_log_path,
            metadata={
                **request.metadata,
                "channel_mode": channel_mode.value,
                "session_context": request.session_context.model_dump(mode="json"),
                "shared_contracts": shared_snapshot,
            },
        )

    def refine_with_synthesizer(
        self,
        *,
        question: str,
        facts: StudentFacts,
        answer_payload: AnswerPayload,
        citations: list[CitationRef],
        rule_classification: RuleClassification,
        prefer_llm: bool,
    ) -> tuple[AnswerPayload, list[CitationRef]] | None:
        if not self.should_use_synthesizer(
            answer_payload=answer_payload,
            citations=citations,
            rule_classification=rule_classification,
            prefer_llm=prefer_llm,
        ):
            return None

        evidence_payload = self.build_synthesis_evidence(citations)
        if not evidence_payload:
            return None

        synthesized = self.synthesizer.synthesize(
            question=question,
            question_type=answer_payload.question_type,
            facts=facts,
            draft_answer=answer_payload.model_dump(mode="json"),
            evidence=evidence_payload,
        )
        if synthesized is None or synthesized.status != answer_payload.status.value:
            return None

        selected_citations = self.select_synthesized_citations(
            citations=citations,
            evidence_ids=synthesized.evidence_ids,
        )
        refined_answer = self.merge_synthesized_answer(base=answer_payload, synthesized=synthesized)
        return refined_answer, selected_citations

    def should_use_synthesizer(
        self,
        *,
        answer_payload: AnswerPayload,
        citations: list[CitationRef],
        rule_classification: RuleClassification,
        prefer_llm: bool,
    ) -> bool:
        if self.synthesizer is None or not prefer_llm:
            return False
        if answer_payload.status in {AnswerStatus.OUT_OF_SCOPE, AnswerStatus.HANDOFF} and not citations:
            return False
        if rule_classification.is_latest_request:
            return False
        if rule_classification.platform_status_requires_manual_check:
            return False
        if rule_classification.asks_for_probability:
            return False
        return True

    def build_synthesis_evidence(self, citations: list[CitationRef]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for item in citations:
            source_meta = self.knowledge.source_map.get(item.source_id, {})
            payload.append(
                {
                    "source_id": item.source_id,
                    "file_name": source_meta.get("file_name", item.title),
                    "source_tier": int(source_meta.get("source_tier") or 99),
                    "citation": item.page or item.chunk_id,
                    "snippet": item.quote_snippet,
                }
            )
        return payload

    def select_synthesized_citations(
        self,
        *,
        citations: list[CitationRef],
        evidence_ids: list[str],
    ) -> list[CitationRef]:
        if not evidence_ids:
            return list(citations)
        selected: list[CitationRef] = []
        for evidence_id in evidence_ids:
            if not evidence_id.startswith("EV"):
                continue
            try:
                index = int(evidence_id[2:]) - 1
            except ValueError:
                continue
            if 0 <= index < len(citations):
                selected.append(citations[index])
        return selected or list(citations)

    def merge_synthesized_answer(self, *, base: AnswerPayload, synthesized: SynthesizedPayload) -> AnswerPayload:
        return AnswerPayload(
            status=base.status,
            scope=base.scope,
            question_type=synthesized.question_type or base.question_type,
            initial_conclusion=synthesized.initial_conclusion or base.initial_conclusion,
            eligibility_or_issue=synthesized.eligibility_or_issue or base.eligibility_or_issue,
            judgement_basis=synthesized.judgement_basis or list(base.judgement_basis),
            required_materials=synthesized.required_materials or list(base.required_materials),
            next_actions=synthesized.next_actions or list(base.next_actions),
            risk_alerts=synthesized.risk_alerts or list(base.risk_alerts),
            human_support=base.human_support,
            follow_up_questions=synthesized.follow_up_questions or list(base.follow_up_questions),
        )

    def to_ask_response(
        self,
        *,
        trace_id: str,
        answer: AnswerPayload,
        citations: list[CitationRef],
        escalation: EscalationDecision,
        session_update: SessionUpdate,
        rule_classification: RuleClassification,
        confidence: float,
        used_llm: bool,
        question: str,
    ) -> AskResponse:
        consultation_advice = "；".join(answer.next_actions[:2]) or answer.human_support
        next_step = "；".join(answer.next_actions) or answer.human_support
        matched_faq_ids = [
            item.chunk_id
            for item in citations
            if item.chunk_id.lower().startswith("faq")
        ]
        return AskResponse(
            status=answer.status,
            question_type=answer.question_type,
            conclusion=answer.initial_conclusion,
            consultation_advice=consultation_advice,
            cannot_confirm_reason=escalation.summary,
            missing_fields=list(answer.follow_up_questions),
            evidence=[self.to_evidence_ref(item) for item in citations],
            applicable_conditions=self.facts_to_conditions(session_update.retained_profile),
            risk_notice=list(answer.risk_alerts),
            next_step=next_step,
            matched_faq_ids=matched_faq_ids,
            used_llm=used_llm,
            customer_reply=render_answer_for_channel(
                trace_id=trace_id,
                answer=answer,
                citations=citations,
                escalation=escalation,
                mode=ChannelMode.PRIVATE,
            ),
            handoff_message=self.compose_handoff_message(question=question, answer=answer, escalation=escalation),
            preliminary_judgement=answer.initial_conclusion,
            reportable_categories=self.infer_reportable_categories(answer=answer, facts=session_update.retained_profile),
            materials_checklist=list(answer.required_materials),
            operation_steps=list(answer.next_actions),
            human_consultation=answer.human_support,
            resolution_source=self.infer_resolution_source(
                answer=answer,
                citations=citations,
                used_llm=used_llm,
            ),
            trace_id=trace_id,
            confidence=confidence,
            answer_payload=answer,
            escalation_decision=escalation,
            citations=citations,
            session_update=session_update,
            rule_classification=rule_classification,
        )

    def to_evidence_ref(self, item: CitationRef) -> EvidenceRef:
        source = self.knowledge.source_map.get(item.source_id, {})
        return EvidenceRef(
            source_id=item.source_id,
            file_name=str(source.get("file_name", item.title)),
            source_tier=int(source.get("source_tier") or 99),
            citation=item.page or item.chunk_id,
            snippet=item.quote_snippet,
            score=None,
        )

    def facts_to_conditions(self, facts: StudentFacts) -> list[str]:
        items: list[str] = []
        if facts.child_hukou:
            items.append(f"孩子户籍：{facts.child_hukou}")
        if facts.parent_hukou:
            items.append(f"家长户籍：{facts.parent_hukou}")
        if facts.parent_work_in_songshanhu is not None:
            items.append(f"家长是否在松山湖工作：{'是' if facts.parent_work_in_songshanhu else '否'}")
        if facts.has_songshanhu_property is not None:
            items.append(f"是否有松山湖房产：{'是' if facts.has_songshanhu_property else '否'}")
        if facts.property_owner:
            items.append(f"房产权属：{facts.property_owner}")
        if facts.stage:
            items.append(f"申请学段：{facts.stage}")
        if facts.is_transfer is not None:
            items.append(f"是否转学：{'是' if facts.is_transfer else '否'}")
        if facts.special_status:
            items.append(f"特殊情形：{'、'.join(facts.special_status)}")
        return items

    def infer_reportable_categories(self, *, answer: AnswerPayload, facts: StudentFacts) -> list[str]:
        explicit = self._explicit_case_codes(answer.initial_conclusion)
        if explicit:
            return explicit
        candidates: list[str] = []
        if facts.child_hukou and "松山湖" in facts.child_hukou:
            candidates.append("A类")
        if facts.parent_work_in_songshanhu:
            candidates.append("B类")
        if facts.dongguan_household is False:
            candidates.append("C类")
        if answer.question_type:
            candidates.append(answer.question_type)
        return _dedupe_preserve_order(candidates)[:4]

    def infer_resolution_source(
        self,
        *,
        answer: AnswerPayload,
        citations: list[CitationRef],
        used_llm: bool,
    ) -> str:
        if used_llm and citations:
            return "grounded_llm"
        if any(item.chunk_id.lower().startswith("faq") for item in citations):
            return "faq_match"
        if answer.status == AnswerStatus.NEED_INFO:
            return "rule_missing_fields"
        if answer.status in {AnswerStatus.HANDOFF, AnswerStatus.OUT_OF_SCOPE}:
            return "rule_handoff"
        if citations:
            return "policy_citation"
        return "rule_only"

    def compose_handoff_message(
        self,
        *,
        question: str,
        answer: AnswerPayload,
        escalation: EscalationDecision,
    ) -> str:
        if not escalation.should_handoff:
            return f"当前无须人工转接。如后续涉及平台实时状态或年度变化，可联系 {self.settings.official_contact}。"
        return (
            f"建议人工继续跟进。问题：{question} "
            f"当前结论：{answer.initial_conclusion} "
            f"原因：{escalation.summary} "
            f"联系方式：{self.settings.official_contact}"
        )

    def build_normalized_message(self, request: AskRequest) -> NormalizedMessage:
        conversation_id = request.conversation_id or "web-session"
        return NormalizedMessage(
            event_id=conversation_id,
            message_id=conversation_id,
            occurred_at="",
            channel=request.channel,
            binding=request.entry_point,
            kind="text",
            text=request.question,
            mentions_bot=False,
            peer=NormalizedPeer(peer_id=request.source_target or conversation_id, peer_type="direct"),
            session=NormalizedSession(session_key=conversation_id, scope="sender", sender_isolated=True),
            sender=NormalizedSender(sender_id=request.source_session_id or conversation_id),
            attachments=[],
            metadata={"is_openclaw": request.is_openclaw},
        )

    def _resolve_top_k(self, value: object) -> int:
        if isinstance(value, int):
            return max(1, min(10, value))
        return 5

    def _detect_question_type(self, question: str) -> str:
        if self._is_latest_request(question):
            return "最新政策概览"
        if hasattr(self.rules, "detect_intent"):
            return self.rules.detect_intent(question)
        return "招生咨询"

    def _scope_for(self, question: str, question_type: str) -> str:
        if question_type == "超出范围":
            return "out_of_scope"
        if any(hint in question for hint in ADMISSIONS_HINTS):
            return "admissions_consultation"
        return "admissions_consultation"

    def _is_latest_request(self, question: str) -> bool:
        if hasattr(self.rules, "is_latest_request") and self.rules.is_latest_request(question):
            return True
        return any(pattern in question for pattern in LATEST_PATTERNS)

    def _is_case_specific(self, question: str) -> bool:
        if hasattr(self.rules, "is_case_specific") and self.rules.is_case_specific(question):
            return True
        return any(pattern in question for pattern in CASE_SPECIFIC_PATTERNS)

    def _is_cross_year_comparison(self, question: str, mentioned_years: list[int]) -> bool:
        if len(set(mentioned_years)) >= 2:
            return True
        return any(pattern in question for pattern in HISTORICAL_COMPARISON_PATTERNS)

    def _mentioned_years(self, question: str) -> list[int]:
        return [int(item) for item in YEAR_PATTERN.findall(question)]

    def _explicit_case_codes(self, text: str) -> list[str]:
        matches = [match.upper() for match in CATEGORY_PATTERN.findall(text or "")]
        if "C类" in text or "C 类" in text:
            matches.append("C")
        return _dedupe_preserve_order(matches)

    def _special_catalog_ids(self, question: str) -> list[str]:
        matched: list[str] = []
        for catalog_id, keywords in SPECIAL_SOURCE_KEYWORDS.items():
            if any(keyword in question for keyword in keywords):
                matched.append(catalog_id)
        return matched

    def _structured_profile(self, facts: StudentFacts) -> dict[str, Any]:
        property_owner_relation = None
        if facts.property_owner == "祖辈":
            property_owner_relation = "祖辈"
        elif facts.property_owner == "父母":
            property_owner_relation = "父母"
        employer_has_b1_quota = None
        if any(token in facts.special_status for token in ("企业指标", "B1", "企业名额")):
            employer_has_b1_quota = True
        return {
            "stage": facts.stage,
            "child_hukou": facts.child_hukou,
            "guardian_hukou": facts.parent_hukou,
            "work_location": "松山湖" if facts.parent_work_in_songshanhu is True else "非松山湖" if facts.parent_work_in_songshanhu is False else None,
            "property_location": "松山湖" if facts.has_songshanhu_property is True else "无" if facts.has_songshanhu_property is False else None,
            "preferential_statuses": list(facts.special_status),
            "is_transfer_or_non_starting": facts.is_transfer,
            "employer_has_b1_quota": employer_has_b1_quota,
            "property_owner_relation": property_owner_relation,
            "facts": {},
        }

    def _missing_fields(
        self,
        *,
        question: str,
        is_case_specific: bool,
        explicit_case_codes: list[str],
        structured_result: dict[str, Any],
    ) -> list[str]:
        if not is_case_specific:
            return []
        if explicit_case_codes and (
            any(pattern in question for pattern in DEFINITION_PATTERNS)
            or any(pattern in question for pattern in COMPARISON_PATTERNS)
        ):
            return []
        missing = list(structured_result.get("minimal_follow_up_fields") or [])
        if missing:
            return missing[:3]
        extra = list(structured_result.get("additional_follow_up_fields") or [])
        return extra[:3]

    def _collect_evidence(
        self,
        *,
        question: str,
        top_k: int,
        structured_evidence: dict[str, Any],
        special_catalog_ids: list[str],
    ) -> list[EvidenceCandidate]:
        candidates: list[EvidenceCandidate] = []
        candidates.extend(self._legacy_document_candidates(question=question, top_k=top_k))
        candidates.extend(self._legacy_faq_candidates(question=question, top_k=min(3, top_k)))
        candidates.extend(self._structured_candidates(structured_evidence))
        for catalog_source_id in special_catalog_ids:
            candidates.extend(self._source_scoped_candidates(question=question, catalog_source_id=catalog_source_id))
        if self._is_latest_request(question):
            candidates.extend(
                self._source_scoped_candidates(
                    question=question,
                    catalog_source_id=f"guide_songshanhu_{self.settings.knowledge_year}",
                )
            )
        return candidates

    def _legacy_document_candidates(self, *, question: str, top_k: int) -> list[EvidenceCandidate]:
        candidates: list[EvidenceCandidate] = []
        for hit in self.knowledge.search_documents(question, top_k=top_k):
            record = hit.record
            source = self.knowledge.source_for(record["source_id"])
            candidates.append(
                EvidenceCandidate(
                    source_id=str(record["source_id"]),
                    title=str(source.get("title") or record.get("title") or source.get("file_name") or ""),
                    page=str(record.get("citation") or ""),
                    chunk_id=str(record.get("chunk_id") or f"{record['source_id']}-chunk"),
                    quote_snippet=compact_snippet(str(record.get("text") or ""), limit=180),
                    source_tier=int(source.get("source_tier") or 99),
                    score=float(hit.score),
                    source_kind="legacy_document",
                    catalog_source_id=str(source.get("catalog_source_id") or ""),
                )
            )
        return candidates

    def _legacy_faq_candidates(self, *, question: str, top_k: int) -> list[EvidenceCandidate]:
        candidates: list[EvidenceCandidate] = []
        for hit in self.knowledge.search_faq(question, top_k=top_k):
            faq = hit.record
            source = self.knowledge.source_for(faq["source_id"])
            snippet_parts = [str(faq.get("answer") or "")]
            if faq.get("notes"):
                snippet_parts.append(str(faq["notes"]))
            candidates.append(
                EvidenceCandidate(
                    source_id=str(faq["source_id"]),
                    title=str(source.get("title") or source.get("file_name") or faq.get("question") or "FAQ"),
                    page=f"FAQ 第 {faq.get('row_number')} 条",
                    chunk_id=str(faq.get("faq_id") or f"faq-{faq.get('row_number')}"),
                    quote_snippet=compact_snippet(" ".join(snippet_parts), limit=160),
                    source_tier=int(source.get("source_tier") or 99),
                    score=float(hit.score),
                    source_kind="faq",
                    catalog_source_id=str(source.get("catalog_source_id") or ""),
                )
            )
        return candidates

    def _structured_candidates(self, structured_evidence: dict[str, Any]) -> list[EvidenceCandidate]:
        candidates: list[EvidenceCandidate] = []
        for hit in structured_evidence.get("hits", [])[:8]:
            legacy_source_id = self.catalog_source_map.get(str(hit["source_id"]))
            source_meta = self.knowledge.source_for(legacy_source_id) if legacy_source_id else {}
            candidates.append(
                EvidenceCandidate(
                    source_id=str(legacy_source_id or hit["source_id"]),
                    title=str(source_meta.get("title") or hit.get("title") or hit.get("source_id") or ""),
                    page=str(hit.get("citation") or ""),
                    chunk_id=f"{hit.get('source_id')}::{hit.get('page') or hit.get('heading') or 'chunk'}",
                    quote_snippet=compact_snippet(str(hit.get("text") or ""), limit=180),
                    source_tier=int(source_meta.get("source_tier") or hit.get("priority_bucket") or 99),
                    score=float(hit.get("score") or 0.0),
                    source_kind="structured_document",
                    catalog_source_id=str(source_meta.get("catalog_source_id") or hit.get("source_id") or ""),
                )
            )
        return candidates

    def _source_scoped_candidates(self, *, question: str, catalog_source_id: str) -> list[EvidenceCandidate]:
        source_id = self.catalog_source_map.get(catalog_source_id)
        if not source_id:
            return []
        source = self.knowledge.source_for(source_id)
        question_tokens = extract_tokens(question)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for document in self.documents_by_source.get(source_id, []):
            text = str(document.get("text") or "")
            title = str(document.get("title") or source.get("title") or "")
            section_text = " ".join(
                str(item)
                for field in ("section_titles", "section_types", "section_keywords", "rule_card_titles", "rule_card_terms")
                for item in (document.get(field) or [])
            )
            score = token_overlap(question_tokens, set(document.get("tokens") or extract_tokens(text))) * 1.4
            score += similarity(question, title) * 0.7
            score += similarity(question, section_text) * 0.9
            score += similarity(question, text) * 0.2
            if str(document.get("citation") or "").startswith("规则卡片"):
                score += 0.25
            if str(document.get("citation") or "").startswith("章节摘要"):
                score += 0.18
            ranked.append((score, document))
        ranked.sort(key=lambda item: item[0], reverse=True)

        results: list[EvidenceCandidate] = []
        for score, document in ranked[:2]:
            results.append(
                EvidenceCandidate(
                    source_id=source_id,
                    title=str(source.get("title") or source.get("file_name") or ""),
                    page=str(document.get("citation") or ""),
                    chunk_id=str(document.get("chunk_id") or f"{source_id}-chunk"),
                    quote_snippet=compact_snippet(str(document.get("text") or ""), limit=180),
                    source_tier=int(source.get("source_tier") or 99),
                    score=round(score + 0.6, 4),
                    source_kind="source_priority",
                    catalog_source_id=catalog_source_id,
                )
            )
        return results

    def _select_candidates(
        self,
        *,
        question: str,
        candidates: list[EvidenceCandidate],
        special_catalog_ids: list[str],
        top_k: int,
    ) -> list[EvidenceCandidate]:
        question_tokens = extract_tokens(question)
        explicit_case_codes = set(self._explicit_case_codes(question))
        active_guide_id = f"guide_songshanhu_{self.settings.knowledge_year}"

        def rank(item: EvidenceCandidate) -> tuple[float, int, int, str]:
            source_meta = self.knowledge.source_map.get(item.source_id, {})
            marker_text = " ".join(
                [
                    item.title,
                    item.page or "",
                    item.quote_snippet,
                    str(source_meta.get("scope") or ""),
                    " ".join(source_meta.get("seed_tags") or []),
                ]
            )
            marker_tokens = extract_tokens(marker_text)
            score = float(item.score)
            score += token_overlap(question_tokens, marker_tokens) * 1.4
            score += similarity(question, marker_text) * 0.35
            if item.catalog_source_id in special_catalog_ids:
                score += 2.2
            if item.catalog_source_id == active_guide_id:
                score += 0.9
            if item.source_kind == "source_priority":
                score += 0.7
            if item.source_kind == "faq":
                score -= 0.35
            if explicit_case_codes and any(code in marker_text for code in explicit_case_codes):
                score += 0.55
            if item.source_tier <= 2:
                score += 0.35
            return (round(score, 6), -item.source_tier, 0 if item.source_kind != "faq" else 1, item.title)

        ordered = sorted(candidates, key=rank, reverse=True)
        selected: list[EvidenceCandidate] = []
        seen = set()
        for item in ordered:
            dedupe_key = (item.source_id, item.page, item.chunk_id, item.title)
            if dedupe_key in seen:
                continue
            if special_catalog_ids and item.source_kind == "faq" and selected:
                continue
            selected.append(item)
            seen.add(dedupe_key)
            if len(selected) >= max(3, top_k):
                break

        official = [item for item in selected if item.source_tier <= 4]
        final = official[:top_k] if official else selected[:top_k]
        return final or selected[:top_k]

    def _candidate_to_citation(self, item: EvidenceCandidate) -> CitationRef:
        return CitationRef(
            source_id=item.source_id,
            title=item.title,
            page=item.page,
            chunk_id=item.chunk_id,
            quote_snippet=item.quote_snippet,
        )

    def _decide_status(
        self,
        *,
        scope: str,
        classification: RuleClassification,
        missing_fields: list[str],
        mentioned_years: list[int],
    ) -> AnswerStatus:
        if scope == "out_of_scope":
            return AnswerStatus.OUT_OF_SCOPE
        if classification.platform_status_requires_manual_check:
            return AnswerStatus.HANDOFF
        if classification.asks_for_probability or classification.asks_for_human:
            return AnswerStatus.HANDOFF
        if classification.policy_conflict_detected and mentioned_years:
            return AnswerStatus.HANDOFF
        if classification.is_latest_request and (
            any(year > self.settings.knowledge_year for year in mentioned_years)
            or classification.policy_conflict_detected
        ):
            return AnswerStatus.HANDOFF
        if missing_fields:
            return AnswerStatus.NEED_INFO
        return AnswerStatus.ANSWERED

    def _confidence_for(
        self,
        *,
        status: AnswerStatus,
        citations: list[CitationRef],
        missing_fields: list[str],
    ) -> float:
        if status == AnswerStatus.OUT_OF_SCOPE:
            return 0.35
        if status == AnswerStatus.HANDOFF:
            return 0.45 if citations else 0.25
        if status == AnswerStatus.NEED_INFO:
            return 0.4 if missing_fields else 0.5
        if len(citations) >= 2:
            return 0.9
        if citations:
            return 0.82
        return 0.6

    def _build_answer_payload(
        self,
        *,
        question: str,
        question_type: str,
        status: AnswerStatus,
        facts: StudentFacts,
        explicit_case_codes: list[str],
        citations: list[CitationRef],
        missing_fields: list[str],
        structured_context: dict[str, Any],
        mentioned_years: list[int],
        special_catalog_ids: list[str],
        scope: str,
    ) -> AnswerPayload:
        human_support = f"如需人工复核，请联系 {self.settings.official_contact}。"
        follow_up_questions = self._follow_up_questions(missing_fields)
        judgement_basis = self._judgement_basis(citations)
        risk_alerts = _dedupe_preserve_order(
            list(structured_context.get("warnings", []))
            + list(structured_context.get("risk_template", []))
            + [f"本回答严格限制在已入库的 {self.settings.knowledge_year} 年及历史资料范围内。"]
        )[:4]
        required_materials = _dedupe_preserve_order(list(structured_context.get("materials_template", [])))[:5]
        next_actions = _dedupe_preserve_order(list(structured_context.get("steps_template", [])))[:4]

        if status == AnswerStatus.OUT_OF_SCOPE:
            return AnswerPayload(
                status=status,
                scope=scope,
                question_type=question_type,
                initial_conclusion="先直接说结论：这个问题不在当前招生咨询范围内。",
                eligibility_or_issue="当前系统只处理松山湖/东莞入学政策、分类、材料、流程和转学咨询。",
                judgement_basis=["当前问题未命中招生范围关键词，也没有可靠的本地知识依据。"],
                required_materials=[],
                next_actions=["请改问入学资格、类别、材料、流程、转学或平台操作相关问题。"],
                risk_alerts=risk_alerts[:2],
                human_support=human_support,
                follow_up_questions=[],
            )

        if status == AnswerStatus.HANDOFF and self._is_latest_request(question):
            referenced_year = max(mentioned_years) if mentioned_years else self.settings.knowledge_year
            return AnswerPayload(
                status=status,
                scope=scope,
                question_type="最新政策概览",
                initial_conclusion=f"先直接说结论：当前系统可直接引用的最新材料是 {self.settings.knowledge_year} 年资料。",
                eligibility_or_issue=(
                    f"如果你问的是 {referenced_year} 年或跨年度变化，这里不能把 "
                    f"{self.settings.knowledge_year} 年口径直接当成更新年度政策。"
                ),
                judgement_basis=judgement_basis or ["系统已锁定为只依据本地知识库回答，不补外部实时政策。"],
                required_materials=[],
                next_actions=[
                    f"先以 {self.settings.knowledge_year} 年申请指南和已入库政策理解当前规则。",
                    "如需确认更新年度变化，请转人工按最新公告复核。",
                ],
                risk_alerts=risk_alerts[:4],
                human_support=human_support,
                follow_up_questions=[],
            )

        if status == AnswerStatus.HANDOFF:
            return AnswerPayload(
                status=status,
                scope=scope,
                question_type=question_type,
                initial_conclusion="先直接说结论：这类问题不适合直接给确定答复，建议人工复核。",
                eligibility_or_issue="当前问题涉及实时状态、概率承诺或高不确定性场景，系统不做强答。",
                judgement_basis=judgement_basis or ["当前场景超出稳妥自动答复边界。"],
                required_materials=[],
                next_actions=[
                    "把当前问题和已知事实一并交给人工客服复核。",
                    "如涉及平台状态或审核结果，以官方页面和人工答复为准。",
                ],
                risk_alerts=risk_alerts[:4],
                human_support=human_support,
                follow_up_questions=[],
            )

        if status == AnswerStatus.NEED_INFO:
            return AnswerPayload(
                status=status,
                scope=scope,
                question_type=question_type,
                initial_conclusion="先直接说结论：现在还不能直接给你确定结论。",
                eligibility_or_issue="要继续做精确判断，至少还需要补齐这几个关键事实。",
                judgement_basis=judgement_basis or ["现有信息不足以稳定落类或判断资格。"],
                required_materials=[],
                next_actions=["按顺序补充关键事实后，我再继续精确判断。"],
                risk_alerts=risk_alerts[:4],
                human_support=human_support,
                follow_up_questions=follow_up_questions,
            )

        initial_conclusion, eligibility_or_issue = self._answered_summary(
            question=question,
            question_type=question_type,
            explicit_case_codes=explicit_case_codes,
            citations=citations,
            special_catalog_ids=special_catalog_ids,
        )
        if not next_actions:
            next_actions = [
                "先按当前命中的官方资料核对自己是否符合对应条件。",
                "正式提交前，再结合平台审核要求逐项准备材料。",
            ]
        if not required_materials and question_type in {"材料清单", "转学", "积分入学", "报名资格判断"}:
            required_materials = [
                "学童及监护人户籍证明或户口簿",
                "工作、房产、社保或学籍等对应证明材料",
            ]
        return AnswerPayload(
            status=status,
            scope=scope,
            question_type=question_type,
            initial_conclusion=initial_conclusion,
            eligibility_or_issue=eligibility_or_issue,
            judgement_basis=judgement_basis,
            required_materials=required_materials,
            next_actions=next_actions,
            risk_alerts=risk_alerts[:4],
            human_support=human_support,
            follow_up_questions=[],
        )

    def _answered_summary(
        self,
        *,
        question: str,
        question_type: str,
        explicit_case_codes: list[str],
        citations: list[CitationRef],
        special_catalog_ids: list[str],
    ) -> tuple[str, str]:
        citation_summary = self._citation_summary(citations)
        if len(explicit_case_codes) > 1 or (
            explicit_case_codes and any(pattern in question for pattern in COMPARISON_PATTERNS)
        ):
            joined = " 和 ".join(explicit_case_codes)
            return (
                f"先直接说结论：{joined} 的差别要以当年分类条件和对应规则卡片理解。",
                citation_summary,
            )
        if explicit_case_codes:
            joined = "、".join(explicit_case_codes)
            return (
                f"先直接说结论：{joined} 的含义可以直接按当年申请指南里的分类条件理解。",
                citation_summary,
            )
        if special_catalog_ids:
            return (
                "先直接说结论：这类问题应优先引用对应专项政策，不应该只看普通报名 FAQ。",
                citation_summary,
            )
        if "转学" in question or question_type == "转学":
            return (
                "先直接说结论：转学问题要先看当年转学限制和受理范围。",
                citation_summary,
            )
        if "房产" in question and "锁定" in question:
            return (
                "先直接说结论：房产锁定类问题要以当年申请指南里的房产规则卡片为准。",
                citation_summary,
            )
        if "单位账号" in question or "企业账号" in question:
            return (
                "先直接说结论：单位账号问题应优先看申请指南里的单位账号规则卡片。",
                citation_summary,
            )
        return (
            "先直接说结论：这个问题可以先按当前命中的官方资料理解。",
            citation_summary,
        )

    def _citation_summary(self, citations: list[CitationRef]) -> str:
        if not citations:
            return "当前没有足够强的本地证据片段，建议转人工进一步核对。"
        first = citations[0]
        page = f" / {first.page}" if first.page else ""
        return f"当前优先依据《{first.title}》{page}：{compact_snippet(first.quote_snippet, limit=120)}"

    def _judgement_basis(self, citations: list[CitationRef]) -> list[str]:
        basis = [
            f"{item.title}{f' / {item.page}' if item.page else ''}：{compact_snippet(item.quote_snippet, limit=120)}"
            for item in citations[:3]
        ]
        return basis or ["当前未命中可直接展示的证据片段。"]

    def _follow_up_questions(self, missing_fields: list[str]) -> list[str]:
        if hasattr(self.rules, "minimal_questions_for"):
            return self.rules.minimal_questions_for(missing_fields)[:3]
        return [f"请补充：{field}" for field in missing_fields[:3]]

    def _build_escalation_decision(
        self,
        *,
        question: str,
        status: AnswerStatus,
        missing_fields: list[str],
        scope: str,
        mentioned_years: list[int],
        confidence: float,
    ) -> EscalationDecision:
        if status == AnswerStatus.OUT_OF_SCOPE:
            return EscalationDecision(
                action=EscalationAction.SCOPE_REDIRECT,
                should_handoff=True,
                reasons=["out_of_scope"],
                summary="当前系统只处理松山湖/东莞入学咨询，超出范围的问题建议人工转接。",
                confidence=confidence,
                official_contact=self.settings.official_contact,
            )
        if status == AnswerStatus.NEED_INFO:
            return EscalationDecision(
                action=EscalationAction.ASK_FOLLOW_UP,
                should_handoff=False,
                reasons=["missing_required_facts"],
                summary=f"还缺少关键信息：{'、'.join(missing_fields)}。",
                confidence=confidence,
                official_contact=self.settings.official_contact,
            )
        if status == AnswerStatus.HANDOFF:
            reason = "manual_review_required"
            if self._is_latest_request(question) and mentioned_years:
                reason = "cross_year_policy_boundary"
            return EscalationDecision(
                action=EscalationAction.HANDOFF_HUMAN,
                should_handoff=True,
                reasons=[reason],
                summary="当前问题需要人工复核，系统不直接给确定答复。",
                confidence=confidence,
                official_contact=self.settings.official_contact,
            )
        return EscalationDecision(
            action=EscalationAction.NONE,
            should_handoff=False,
            reasons=["grounded_answer"],
            summary="当前结论仅依据已入库资料，不替代平台实时审核和人工复核。",
            confidence=confidence,
            official_contact=self.settings.official_contact,
        )

    def _build_session_update(
        self,
        *,
        request: ConsultationOrchestratorRequest,
        facts: StudentFacts,
        answer_payload: AnswerPayload,
        missing_fields: list[str],
        question_type: str,
        scope: str,
    ) -> SessionUpdate:
        follow_up_rounds = request.session_context.follow_up_rounds
        if answer_payload.status == AnswerStatus.NEED_INFO:
            follow_up_rounds += 1
        elif answer_payload.status == AnswerStatus.ANSWERED:
            follow_up_rounds = 0

        flags = ["structured_bundle", "markdown_kb"]
        if answer_payload.status == AnswerStatus.HANDOFF and self._is_latest_request(request.normalized_message.text):
            flags.append("latest_policy_boundary")

        return SessionUpdate(
            conversation_id=request.session_context.conversation_id or request.normalized_message.message_id,
            retained_profile=facts,
            last_intent=question_type,
            last_scope=scope,
            asked_missing_fields=list(missing_fields),
            follow_up_rounds=follow_up_rounds,
            flags=flags,
        )

    def _persist_audit_log(
        self,
        *,
        trace_id: str,
        question: str,
        question_type: str,
        status: str,
        citations: list[CitationRef],
        scope: str,
        confidence: float,
        missing_fields: list[str],
    ) -> str:
        return self.audit_logger.append(
            {
                "trace_id": trace_id,
                "question": question,
                "question_type": question_type,
                "status": status,
                "scope": scope,
                "confidence": confidence,
                "missing_fields": missing_fields,
                "citations": [item.model_dump(mode="json") for item in citations],
            }
        )

    def resolve_channel_mode(self, request: ConsultationOrchestratorRequest) -> ChannelMode:
        peer_type = request.normalized_message.peer.peer_type
        if request.route_mode == RouteMode.ORGANIZATION_ADMIN:
            return ChannelMode.ADMIN
        if peer_type == "group":
            return ChannelMode.GROUP
        return ChannelMode.PRIVATE

    def routed_agent_for(self, route_mode: RouteMode) -> str:
        mapping = {
            RouteMode.PARENT_CONSULTATION: "admissions-consultation",
            RouteMode.ORGANIZATION_ADMIN: "admissions-consultation-admin",
            RouteMode.OPERATIONS_SUPPORT: "admissions-operations-support",
        }
        return mapping.get(route_mode, "admissions-consultation")

    def gateway_status(self, status: AnswerStatus) -> str:
        if status == AnswerStatus.OUT_OF_SCOPE:
            return "handoff"
        return status.value
