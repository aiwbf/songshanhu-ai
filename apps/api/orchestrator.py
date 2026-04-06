from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.knowledge import KnowledgeStore, RankedHit
from app.models import (
    AnswerPayload,
    AnswerStatus,
    ChannelMode,
    CitationRef,
    ConsultationOrchestrateRequest,
    ConsultationOrchestrateResponse,
    EscalationAction,
    EscalationDecision,
    ProfileConflict,
    RouteMode,
    RuleClassification,
    SessionUpdate,
    StudentFacts,
)
from app.shared_projection import build_shared_contract_snapshot
from app.rules import RuleEngine
from app.utils import compact_snippet, extract_tokens, normalize_text, token_overlap
from apps.api.audit import AuditLogger, redact_sensitive_text


PROBABILITY_PATTERNS = ("概率", "录取率", "稳不稳", "包过", "一定能", "保录", "百分百")
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
ADMISSIONS_SCOPE_HINTS = (
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
    "A类",
    "B类",
    "C类",
)
LOW_STAKES_INTENTS = {"平台操作", "材料清单", "政策依据查询"}
LATEST_PATTERNS = ("最新", "今年", "当前政策", "2025", "2026")
HISTORICAL_COMPARISON_PATTERNS = ("还是一样", "是否一样", "是否还是", "沿用", "仍然一样", "还是按", "和 2023", "和2023")
CATEGORY_CODE_PATTERN = re.compile(r"(A1(?:\.1|\.2)?|A2|A3|B1|B2(?:\.1|\.2)?|B3|C类|C 类)")
CATEGORY_DEFINITION_HINTS = ("是什么", "什么意思", "怎么理解", "含义", "定义", "适用对象")
CATEGORY_COMPARISON_HINTS = ("区别", "差别", "不同", "分别", "对比", "怎么区分")
GENERAL_KNOWLEDGE_PATTERNS = (
    "是什么",
    "什么意思",
    "怎么",
    "如何",
    "哪些",
    "哪种",
    "条件",
    "材料",
    "流程",
    "规则",
    "政策",
    "依据",
    "区别",
    "适用",
    "时间",
    "什么时候",
    "什么情况下",
    "是否可以同时",
    "怎么申请",
    "怎么修改",
    "怎么注册",
    "怎么解锁",
)
CASE_SPECIFIC_MARKERS = (
    "我家",
    "我们家",
    "我孩子",
    "我家孩子",
    "我这种",
    "我这种情况",
    "我能",
    "我可以",
    "我是否",
    "帮我判断",
    "给我判断",
    "我属于",
    "我想知道自己",
    "适合我",
    "适合我们",
)

CATEGORY_KNOWLEDGE = {
    "A1": {
        "label": "A1类",
        "summary": "松山湖家庭户籍学童，且户籍地址与房产地址一致；A1.1 和 A1.2 再按产权关系细分。",
        "focus": "核心看家庭户籍、户籍地址与房产地址是否一致。",
    },
    "A2": {
        "label": "A2类",
        "summary": "集体户籍学童，父或母因工作关系入户园区，学童随迁到礼宾路 2 号集体户或单位集体户，且随迁家长目前仍在园区工作。",
        "focus": "核心看是否属于因工作入户的园区集体户路径。",
    },
    "A3": {
        "label": "A3类",
        "summary": "除 A1、A2 外的其他松山湖户籍学童。",
        "focus": "核心看是否属于松山湖户籍，但又不满足 A1 或 A2。",
    },
    "B1": {
        "label": "B1类",
        "summary": "企业根据规定获得入学指标后，其管理和技术人才的非本市户籍适龄子女可申请。",
        "focus": "核心是企业指标，不是个人直接按积分报名。",
    },
    "B2": {
        "label": "B2类",
        "summary": "在园区工作，且符合优待政策、高层次人才或紧缺人才等条件的企事业单位人才及政策优待人员。",
        "focus": "核心是优待政策或人才条件，不是企业指标，也不是企业积分。",
    },
    "B3": {
        "label": "B3类",
        "summary": "未享受 B1 或未达到 B2 条件的企业人才，在企业和个人同时符合条件时，可按积分制方式申请学位。",
        "focus": "核心是企业和个人双条件满足后按积分排序申请。",
    },
    "C": {
        "label": "C类",
        "summary": "父母一方服务地、居住地或户籍在松山湖，或在松山湖有产权清晰自有居所的非户籍适龄学童，且符合东莞积分入学方案。",
        "focus": "核心是东莞市积分入学路径，面向非户籍适龄学童。",
    },
}

GUIDE_PRIORITY_INTENTS = {"类别判断", "报名资格判断", "材料清单", "转学", "幼儿园申请", "积分入学", "政策依据查询"}
SPECIAL_POLICY_PRIORITY_MARKERS = ("优才卡", "优粤卡", "华侨", "华人", "台湾", "香港", "澳门", "荣誉市民")
GUIDE_PRIORITY_MARKERS = (
    "申请指南",
    "入学申请",
    "招生对象",
    "报名条件",
    "报名流程",
    "所需材料",
    "材料清单",
    "转学",
    "插班",
    "房产",
    "锁定",
    "解锁",
    "A1",
    "A2",
    "A3",
    "B1",
    "B2",
    "B3",
    "C类",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def truth_text(value: bool | None) -> str:
    if value is None:
        return "未知"
    return "是" if value else "否"


def stringify_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value) if value else "空"
    if value is None or value == "":
        return "空"
    return str(value)


def facts_to_conditions(facts: StudentFacts) -> list[str]:
    items: list[str] = []
    if facts.child_hukou:
        items.append(f"孩子户籍：{facts.child_hukou}")
    if facts.parent_hukou:
        items.append(f"家长户籍：{facts.parent_hukou}")
    if facts.parent_work_in_songshanhu is not None:
        items.append(f"家长是否在松山湖工作：{truth_text(facts.parent_work_in_songshanhu)}")
    if facts.has_songshanhu_property is not None:
        items.append(f"是否有松山湖房产：{truth_text(facts.has_songshanhu_property)}")
    if facts.property_owner:
        items.append(f"房产权属：{facts.property_owner}")
    if facts.stage:
        items.append(f"申请学段：{facts.stage}")
    if facts.is_transfer is not None:
        items.append(f"是否转学：{truth_text(facts.is_transfer)}")
    if facts.special_status:
        items.append(f"特殊情形：{'、'.join(facts.special_status)}")
    if facts.dongguan_household is not None:
        items.append(f"是否东莞户籍：{truth_text(facts.dongguan_household)}")
    return items


@dataclass
class ScopeResult:
    scope: str
    in_scope: bool
    explanation: str


@dataclass
class CaseProfileExtraction:
    merged_profile: StudentFacts
    conflicts: list[ProfileConflict]


@dataclass
class MissingContextResult:
    missing_field_names: list[str]
    missing_labels: list[str]
    follow_up_questions: list[str]


@dataclass
class RetrievedEvidence:
    source_id: str
    title: str
    page: str | None
    chunk_id: str
    quote_snippet: str
    source_tier: int
    score: float
    source_kind: str
    file_name: str


class ConsultationOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        rules: RuleEngine,
        knowledge: KnowledgeStore,
        audit_logger: AuditLogger,
    ) -> None:
        self.settings = settings
        self.rules = rules
        self.knowledge = knowledge
        self.audit_logger = audit_logger

    def orchestrate(self, request: ConsultationOrchestrateRequest) -> ConsultationOrchestrateResponse:
        trace_id = uuid4().hex
        scope = self.detect_scope(request.normalized_message.text)
        case_profile = self.extract_case_profile(
            message_text=request.normalized_message.text,
            session_profile=request.session_context.remembered_profile,
            user_profile=request.user_profile,
        )
        missing = self.identify_missing_fields(
            message_text=request.normalized_message.text,
            scope=scope,
            profile=case_profile.merged_profile,
            already_asked=request.session_context.asked_missing_fields,
        )
        classification = self.classify_case(
            message_text=request.normalized_message.text,
            scope=scope,
            profile=case_profile,
            missing=missing,
        )
        evidence = self.retrieve_evidence(
            message_text=request.normalized_message.text,
            classification=classification,
            top_k=request.top_k,
        )
        if self.knowledge_faq_conflict(request.normalized_message.text):
            classification.policy_conflict_detected = True
        answer = self.generate_answer(
            message_text=request.normalized_message.text,
            scope=scope,
            classification=classification,
            profile=case_profile.merged_profile,
            missing=missing,
            evidence=evidence,
        )
        confidence = self.evaluate_confidence(
            message_text=request.normalized_message.text,
            scope=scope,
            classification=classification,
            missing=missing,
            evidence=evidence,
        )
        escalation = self.decide_escalation(
            scope=scope,
            classification=classification,
            missing=missing,
            confidence=confidence,
            follow_up_rounds=request.session_context.follow_up_rounds,
        )
        answer = self.apply_escalation(answer=answer, escalation=escalation)
        session_update = self.build_session_update(
            request=request,
            classification=classification,
            profile=case_profile.merged_profile,
            missing=missing,
            escalation=escalation,
            answer=answer,
        )
        log_path = self.persist_log(
            trace_id=trace_id,
            request=request,
            scope=scope,
            classification=classification,
            missing=missing,
            citations=[self.to_citation(item) for item in evidence],
            answer=answer,
            escalation=escalation,
            session_update=session_update,
        )
        return ConsultationOrchestrateResponse(
            trace_id=trace_id,
            answer_payload=answer,
            escalation_decision=escalation,
            citations=[self.to_citation(item) for item in evidence],
            session_update=session_update,
            rule_classification=classification,
            confidence=confidence,
            audit_log_path=log_path,
        )

    def detect_scope(self, message_text: str) -> ScopeResult:
        intent = self.rules.detect_intent(message_text)
        text = message_text.strip()
        has_hint = any(item in text for item in ADMISSIONS_SCOPE_HINTS)
        faq_hits = self.knowledge.search_faq(text, top_k=1)
        doc_hits = self.knowledge.search_documents(text, top_k=1)
        has_retrieval_signal = bool(
            (faq_hits and faq_hits[0].score >= 0.35) or (doc_hits and doc_hits[0].score >= 0.22)
        )
        if intent == "超出范围" or (not has_hint and not has_retrieval_signal):
            supported_years = "/".join(str(item) for item in getattr(self.settings, "available_knowledge_years", (2024, 2025)))
            return ScopeResult(
                scope="out_of_scope",
                in_scope=False,
                explanation=(
                    f"当前系统只处理松山湖/东莞入学咨询，默认依据 {self.settings.knowledge_year} 年资料，"
                    f"并保留 {supported_years} 年度口径用于追溯。支持范围包括资格、类别、材料、平台操作、转学、积分入学等。"
                ),
            )
        return ScopeResult(
            scope="admissions_consultation",
            in_scope=True,
            explanation="问题属于当前入学咨询范围，可继续按规则和证据编排回答。",
        )

    def extract_case_profile(
        self,
        *,
        message_text: str,
        session_profile: StudentFacts,
        user_profile: StudentFacts,
    ) -> CaseProfileExtraction:
        merged = StudentFacts(**session_profile.model_dump())
        conflicts: list[ProfileConflict] = []
        merged, profile_conflicts = self.merge_facts_with_conflicts(merged, user_profile, source="user_profile")
        conflicts.extend(profile_conflicts)
        extracted = self.extract_freeform_facts(message_text)
        merged, extracted_conflicts = self.merge_facts_with_conflicts(merged, extracted, source="message_extract")
        conflicts.extend(extracted_conflicts)
        return CaseProfileExtraction(merged_profile=merged, conflicts=conflicts)

    def identify_missing_fields(
        self,
        *,
        message_text: str,
        scope: ScopeResult,
        profile: StudentFacts,
        already_asked: list[str],
    ) -> MissingContextResult:
        if not scope.in_scope:
            return MissingContextResult(missing_field_names=[], missing_labels=[], follow_up_questions=[])

        if self.is_case_specific_simultaneous_b3_c_question(message_text):
            return MissingContextResult(
                missing_field_names=["b3_eligibility", "c_eligibility"],
                missing_labels=["是否满足 B3 企业人才条件", "是否满足 C 类积分入学条件"],
                follow_up_questions=[
                    "请补充是否已满足 B3 企业人才路径要求，例如企业资格、个人积分或企业申报条件。",
                    "请补充是否同时满足 C 类积分入学条件，例如东莞积分入学所需积分和对应材料。",
                ],
            )

        if self.can_answer_without_missing(message_text):
            return MissingContextResult(missing_field_names=[], missing_labels=[], follow_up_questions=[])

        intent = self.rules.detect_intent(message_text)
        is_case_specific = self.rules.is_case_specific(message_text) or intent in {
            "类别判断",
            "报名资格判断",
            "材料清单",
            "幼儿园申请",
            "积分入学",
            "房产锁定/解锁",
            "转学",
        }
        if not is_case_specific:
            return MissingContextResult(missing_field_names=[], missing_labels=[], follow_up_questions=[])

        intent_rule = next((item for item in self.rules.intent_rules if item.name == intent), None)
        if intent_rule is None:
            return MissingContextResult(missing_field_names=[], missing_labels=[], follow_up_questions=[])

        missing_names = [
            field_name
            for field_name in intent_rule.required_fields
            if self.is_missing_fact(profile.model_dump().get(field_name))
        ]
        if not missing_names:
            return MissingContextResult(missing_field_names=[], missing_labels=[], follow_up_questions=[])

        ordered = self.prioritize_missing_fields(intent=intent, field_names=list(missing_names))
        deduped = [name for name in ordered if name not in already_asked][:3] or ordered[:3]
        labels = [self.rules.field_labels.get(item, item) for item in deduped]
        questions = self.rules.minimal_questions_for(labels)[:3]
        return MissingContextResult(
            missing_field_names=deduped,
            missing_labels=labels,
            follow_up_questions=questions,
        )

    def classify_case(
        self,
        *,
        message_text: str,
        scope: ScopeResult,
        profile: CaseProfileExtraction,
        missing: MissingContextResult,
    ) -> RuleClassification:
        return RuleClassification(
            scope=scope.scope,
            intent=self.rules.detect_intent(message_text),
            is_case_specific=self.rules.is_case_specific(message_text),
            is_latest_request=self.is_latest_request(message_text),
            asks_for_probability=any(item in message_text for item in PROBABILITY_PATTERNS)
            or self.rules.should_force_handoff(message_text),
            asks_for_human=any(item in message_text for item in HUMAN_PATTERNS),
            platform_status_requires_manual_check=any(item in message_text for item in PLATFORM_STATUS_PATTERNS),
            policy_conflict_detected=self.has_historical_policy_comparison(message_text),
            profile_conflicts=profile.conflicts,
            missing_critical_fields=missing.missing_labels,
        )

    def retrieve_evidence(
        self,
        *,
        message_text: str,
        classification: RuleClassification,
        top_k: int,
    ) -> list[RetrievedEvidence]:
        if classification.scope == "out_of_scope":
            return []

        ranked: dict[str, RetrievedEvidence] = {}
        faq_hits = self.knowledge.search_faq(message_text, top_k=top_k)
        doc_hits = self.knowledge.search_documents(message_text, top_k=max(6, top_k + 1))

        for hit in faq_hits[:top_k]:
            self.keep_best_evidence(ranked, self.from_faq_hit(hit))
        for hit in doc_hits[: max(4, top_k)]:
            self.keep_best_evidence(ranked, self.from_document_hit(hit))
        if faq_hits:
            for item in self.search_documents_by_answer_hint(faq_hits[0].record.get("answer", "")):
                self.keep_best_evidence(ranked, item)
        for query in self.intent_query_variants(classification.intent):
            for hit in self.knowledge.search_documents(query, top_k=2):
                self.keep_best_evidence(ranked, self.from_document_hit(hit))
        for query in self.special_query_variants(message_text):
            for hit in self.knowledge.search_faq(query, top_k=2):
                self.keep_best_evidence(ranked, self.from_faq_hit(hit))
            for hit in self.knowledge.search_documents(query, top_k=3):
                self.keep_best_evidence(ranked, self.from_document_hit(hit))
        for item in self.preferred_source_hits(message_text):
            self.keep_best_evidence(ranked, item)
        if self.is_category_definition_question(message_text) or self.is_category_comparison_question(message_text):
            for item in self.category_definition_hits(message_text):
                self.keep_best_evidence(ranked, item)

        items = list(ranked.values())
        preferred_terms = self.preferred_source_terms(message_text)
        preferred_content_terms = self.preferred_content_terms(message_text)
        forbidden_content_terms = self.forbidden_content_terms(message_text)
        prioritize_application_guide = self.should_prioritize_application_guide(
            message_text=message_text,
            intent=classification.intent,
        )
        items.sort(
            key=lambda item: (
                0 if prioritize_application_guide and self.is_application_guide_source(item.source_id) else 1,
                -self.evidence_focus_score(message_text=message_text, item=item),
                0 if any(term in item.title or term in item.file_name for term in preferred_terms) else 1,
                0 if any(term in item.quote_snippet for term in preferred_content_terms) else 1,
                1 if any(term in item.quote_snippet for term in forbidden_content_terms) else 0,
                0 if item.source_tier <= 4 else 1,
                -item.score,
                item.source_tier,
                item.title,
            )
        )
        if "房产属于爷爷" in message_text or "跟爷爷" in message_text:
            filtered = [item for item in items if "A3" not in item.quote_snippet]
            if filtered:
                items = filtered
        top_items = items[:5]
        if prioritize_application_guide and not any(self.is_application_guide_source(item.source_id) for item in top_items):
            guide_item = next((item for item in items if self.is_application_guide_source(item.source_id)), None)
            if guide_item is None:
                guide_item = self.best_application_guide_evidence(message_text=message_text)
            if guide_item is not None:
                top_items = [guide_item] + [item for item in top_items if item.chunk_id != guide_item.chunk_id][:4]
        if not any(item.source_kind in {"faq", "category_faq"} for item in top_items):
            best_faq = next(
                (item for item in items if item.source_kind in {"faq", "category_faq"} and item.score >= 0.14),
                None,
            )
            if best_faq is not None:
                top_items = [item for item in top_items if item.chunk_id != best_faq.chunk_id]
                top_items = top_items[:4] + [best_faq]
        return top_items[:5]

    def generate_answer(
        self,
        *,
        message_text: str,
        scope: ScopeResult,
        classification: RuleClassification,
        profile: StudentFacts,
        missing: MissingContextResult,
        evidence: list[RetrievedEvidence],
    ) -> AnswerPayload:
        base_risks = [
            f"当前回答仅依据 {self.settings.knowledge_year} 年资料，不冒充最新年度口径。",
            "系统不会生成录取概率、名额承诺或未经核验的审核状态。",
        ]
        human_support = f"如需人工协助，可联系 {self.settings.official_contact}。"

        if not scope.in_scope:
            return AnswerPayload(
                status=AnswerStatus.OUT_OF_SCOPE,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion="当前问题不在本系统可处理的招生咨询范围内。",
                eligibility_or_issue=scope.explanation,
                judgement_basis=[scope.explanation],
                required_materials=[],
                next_actions=[
                    "如需继续咨询，请改为描述招生相关问题，例如资格、类别、材料、平台操作或转学。"
                ],
                risk_alerts=base_risks,
                human_support=human_support,
                follow_up_questions=[],
            )

        if classification.asks_for_probability:
            return AnswerPayload(
                status=AnswerStatus.HANDOFF,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion="系统不能提供录取概率、保过承诺或名额判断。",
                eligibility_or_issue="当前只能解释政策范围、材料和流程，不能对结果作保证。",
                judgement_basis=[
                    "招生结果会受审核、学位供给、排序和平台核验影响，超出自动回答边界。"
                ],
                required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
                next_actions=["如需个案复核，请直接联系人工坐席并提供完整资料。"],
                risk_alerts=base_risks,
                human_support=human_support,
                follow_up_questions=[],
            )

        if classification.is_latest_request:
            return AnswerPayload(
                status=AnswerStatus.HANDOFF,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion=f"当前知识库仅覆盖 {self.settings.knowledge_year} 年，无法直接回答“最新/今年”口径。",
                eligibility_or_issue="如果问题涉及 2025/2026 或当前年度变化，系统无法代替人工核对最新公告。",
                judgement_basis=[
                    f"系统资料边界是 {self.settings.knowledge_year} 年，不能把旧口径冒充当前口径。"
                ],
                required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
                next_actions=["联系官方渠道核对最新年度公告或平台通知。"],
                risk_alerts=base_risks,
                human_support=human_support,
                follow_up_questions=[],
            )

        if self.has_historical_policy_comparison(message_text):
            return AnswerPayload(
                status=AnswerStatus.HANDOFF,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion="这类跨年度口径对比，不能直接把历史时间节点外推成当年仍然有效。",
                eligibility_or_issue="如果问题同时引用了旧年度时间点和当年口径，需要按对应年度正式文件分别核对，不能凭历史说法直接确认。",
                judgement_basis=[
                    "当前问题带有跨年度对比含义，系统不会把历史文件中的截止日期直接视为后续年度仍然沿用。"
                ],
                required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
                next_actions=["请直接核对对应年度正式文件，或转人工按当年公告复核。"],
                risk_alerts=base_risks,
                human_support=human_support,
                follow_up_questions=[],
            )

        direct_answer = self.generate_direct_answer(
            message_text=message_text,
            scope=scope,
            classification=classification,
            profile=profile,
            evidence=evidence,
            base_risks=base_risks,
            human_support=human_support,
        )
        if direct_answer is not None:
            return direct_answer

        if classification.platform_status_requires_manual_check:
            return AnswerPayload(
                status=AnswerStatus.HANDOFF,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion="平台实际状态需要实时人工或平台页面核验，系统不能代替确认。",
                eligibility_or_issue="当前问题属于“平台实时状态/审核状态/名额状态”范围。",
                judgement_basis=[
                    "平台显示、审核状态、剩余名额和实际受理情况属于实时信息，不应由静态知识库直接下结论。"
                ],
                required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
                next_actions=["请截图当前页面并联系人工坐席或官方热线核验。"],
                risk_alerts=base_risks,
                human_support=human_support,
                follow_up_questions=[],
            )

        if classification.profile_conflicts:
            return AnswerPayload(
                status=AnswerStatus.HANDOFF,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion="你当前提供的资料存在冲突，系统不适合直接落结论。",
                eligibility_or_issue="需要先核对冲突字段，再判断类别、资格或材料。",
                judgement_basis=[
                    f"{item.field_name} 存在前后不一致：{item.existing_value} / {item.incoming_value}"
                    for item in classification.profile_conflicts[:3]
                ],
                required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
                next_actions=["请先确认冲突字段，或直接转人工协助核对。"],
                risk_alerts=base_risks,
                human_support=human_support,
                follow_up_questions=[],
            )

        if missing.follow_up_questions:
            return AnswerPayload(
                status=AnswerStatus.NEED_INFO,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion="当前缺少关键信息，不能直接判断可申报类别或资格。",
                eligibility_or_issue="信息补齐前，不会硬判 A/B/C，也不会直接给出确定资格结论。",
                judgement_basis=[f"本轮仍缺少：{label}" for label in missing.missing_labels[:3]],
                required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
                next_actions=["先补充下面 1 到 3 个关键问题，再继续判断。"],
                risk_alerts=base_risks,
                human_support=human_support,
                follow_up_questions=missing.follow_up_questions[:3],
            )

        official = [item for item in evidence if item.source_tier <= 4]
        supplemental = [item for item in evidence if item.source_tier > 4]
        faq_support = [item for item in supplemental if item.source_kind in {"faq", "category_faq"}]
        answer_support = official + [item for item in faq_support if item.chunk_id not in {entry.chunk_id for entry in official}]
        preferred_evidence = self.order_answer_evidence(
            message_text=message_text,
            evidence=answer_support or official or supplemental,
        )
        basis_lines = self.render_basis_lines(preferred_evidence)

        if not official and classification.intent not in LOW_STAKES_INTENTS:
            return AnswerPayload(
                status=AnswerStatus.HANDOFF,
                scope=scope.scope,
                question_type=classification.intent,
                initial_conclusion="当前没有找到足够强的官方依据，暂不建议系统直接下结论。",
                eligibility_or_issue=self.infer_eligibility_or_issue(
                    intent=classification.intent,
                    profile=profile,
                    has_complete_context=True,
                ),
                judgement_basis=basis_lines or ["仅命中 FAQ/答疑，不能作为法定依据直接落结论。"],
                required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
                next_actions=["建议带着现有资料联系人工复核，或继续提供更具体的政策条款问题。"],
                risk_alerts=base_risks + ["FAQ/运营答疑只能作为操作参考，不能替代官方政策原文。"],
                human_support=human_support,
                follow_up_questions=[],
            )

        answer_evidence = preferred_evidence or answer_support or official or supplemental
        conclusion = self.compose_grounded_conclusion(
            message_text=message_text,
            intent=classification.intent,
            evidence=answer_evidence,
        )
        issue_note = self.compose_grounded_issue_note(
            intent=classification.intent,
            profile=profile,
            evidence=answer_evidence,
        )

        risks = list(base_risks)
        if not official and supplemental:
            risks.append("当前主要命中 FAQ/答疑口径，最终仍以官方 PDF 指南或政策原文为准。")

        return AnswerPayload(
            status=AnswerStatus.ANSWERED,
            scope=scope.scope,
            question_type=classification.intent,
            initial_conclusion=conclusion,
            eligibility_or_issue=issue_note,
            judgement_basis=basis_lines,
            required_materials=self.recommend_materials(profile=profile, intent=classification.intent),
            next_actions=self.recommend_next_actions(
                intent=classification.intent,
                has_official_support=bool(official),
            ),
            risk_alerts=risks,
            human_support=human_support,
            follow_up_questions=[],
        )

    def can_answer_without_missing(self, message_text: str) -> bool:
        text = message_text or ""
        if self.is_case_specific_simultaneous_b3_c_question(text):
            return False
        if self.is_simultaneous_b3_c_question(text):
            return True
        if self.matches_direct_rule(text):
            return True
        faq_hits = self.knowledge.search_faq(text, top_k=2)
        doc_hits = self.knowledge.search_documents(text, top_k=3)
        strong_faq = bool(faq_hits and faq_hits[0].score >= 1.45 and len(text.strip()) >= 8)
        strong_doc = bool(doc_hits and doc_hits[0].score >= 0.24 and len(text.strip()) >= 6)
        corroborated_doc = bool(
            len(doc_hits) >= 2 and doc_hits[0].score >= 0.24 and doc_hits[1].score >= 0.22
        )
        if self.is_general_knowledge_question(text):
            return strong_faq or strong_doc or corroborated_doc
        return strong_faq

    def is_general_knowledge_question(self, message_text: str) -> bool:
        text = (message_text or "").strip()
        if not text:
            return False
        if any(marker in text for marker in CASE_SPECIFIC_MARKERS):
            return False
        if any(marker in text for marker in GENERAL_KNOWLEDGE_PATTERNS):
            return True
        if text.startswith(("A1", "A2", "A3", "B1", "B2", "B3", "C类", "优才卡", "优粤卡")):
            return True
        return False

    def has_historical_policy_comparison(self, text: str) -> bool:
        years = {item for item in re.findall(r"20\d{2}", text or "")}
        if len(years) >= 2 and any(marker in (text or "") for marker in HISTORICAL_COMPARISON_PATTERNS):
            return True
        if "截至2023" in (text or "") and any(marker in (text or "") for marker in HISTORICAL_COMPARISON_PATTERNS):
            return True
        return False

    def is_simultaneous_b3_c_question(self, text: str) -> bool:
        content = text or ""
        return ("同时申请" in content or "同时报" in content) and "B3" in content and "C" in content

    def is_case_specific_simultaneous_b3_c_question(self, text: str) -> bool:
        content = text or ""
        if not self.is_simultaneous_b3_c_question(content):
            return False
        return any(marker in content for marker in ("如果", "我", "我家", "孩子是", "家长", "父母", "给我一个确定答案"))

    def is_single_choice_category_question(self, text: str) -> bool:
        content = text or ""
        pair_markers = ("同时符合", "多个类别", "多项条件", "重复申报", "同时申请", "同时报")
        choice_markers = ("只能选一个", "只能选择一类", "可以同时申请", "可以同时报", "可以重复报")
        return any(marker in content for marker in pair_markers) and any(marker in content for marker in choice_markers)

    def matches_direct_rule(self, message_text: str) -> bool:
        text = message_text or ""
        if self.is_case_specific_simultaneous_b3_c_question(text):
            return False
        if self.is_single_choice_category_question(text):
            return True
        clear_direct_markers = (
            "优才卡",
            "优粤卡",
            "台湾学生",
            "华侨",
            "华人",
            "香港",
            "澳门",
            "单位账号",
            "管理员审核",
            "房产锁定",
            "申请解锁",
            "报名号",
            "修改资料",
        )
        if any(marker in text for marker in clear_direct_markers):
            return True
        direct_markers = (
            "A2类、B2类",
            "只能选择一类",
            "优才卡",
            "优粤卡",
            "台湾籍子女入学怎样申请",
            "华人华侨子女如何申请园区学位",
            "香港/澳门户籍",
            "B1要求在该企业工作满一年",
            "B3类会公布排名吗",
            "房产会被锁定",
            "学位申请房进行解锁",
            "上传的资料有误",
            "单位需注册单位账号",
            "提交报名申请后需要做什么工作",
            "企业如何查询B1类企业名额",
            "房产属于爷爷",
            "A3类中",
            "全家均无园区户籍",
        )
        return any(marker in text for marker in direct_markers)

    def extract_category_codes(self, message_text: str) -> list[str]:
        normalized_codes: list[str] = []
        for raw in CATEGORY_CODE_PATTERN.findall(message_text or ""):
            code = raw.replace("类", "").replace(" ", "")
            if code.startswith("C"):
                code = "C"
            elif code.startswith("B2"):
                code = "B2"
            elif code.startswith("A1"):
                code = "A1"
            if code in CATEGORY_KNOWLEDGE and code not in normalized_codes:
                normalized_codes.append(code)
        return normalized_codes

    def is_category_definition_question(self, message_text: str) -> bool:
        text = message_text or ""
        codes = self.extract_category_codes(text)
        return len(codes) == 1 and any(hint in text for hint in CATEGORY_DEFINITION_HINTS)

    def is_category_comparison_question(self, message_text: str) -> bool:
        text = message_text or ""
        codes = self.extract_category_codes(text)
        return len(codes) >= 2 and any(hint in text for hint in CATEGORY_COMPARISON_HINTS)

    def source_ids_by_catalog(self, catalog_source_id: str) -> list[str]:
        current_year = int(getattr(self.settings, "knowledge_year", 2025))
        matched = [
            source
            for source in self.knowledge.sources
            if source.get("catalog_source_id") == catalog_source_id
        ]
        matched.sort(
            key=lambda source: (
                0 if int(source.get("cycle_year") or 0) == current_year else 1,
                abs(int(source.get("cycle_year") or 0) - current_year),
                int(source.get("source_tier") or 99),
                str(source.get("source_id") or ""),
            )
        )
        return [source["source_id"] for source in matched]

    def source_ids_by_type(self, source_type: str) -> list[str]:
        current_year = int(getattr(self.settings, "knowledge_year", 2025))
        matched = [
            source
            for source in self.knowledge.sources
            if source.get("source_type") == source_type
        ]
        matched.sort(
            key=lambda source: (
                0 if int(source.get("cycle_year") or 0) == current_year else 1,
                abs(int(source.get("cycle_year") or 0) - current_year),
                int(source.get("source_tier") or 99),
                str(source.get("source_id") or ""),
            )
        )
        return [source["source_id"] for source in matched]

    def source_ids_by_markers(self, *markers: str) -> list[str]:
        current_year = int(getattr(self.settings, "knowledge_year", 2025))
        matched: list[dict[str, Any]] = []
        for source in self.knowledge.sources:
            haystack = " ".join(
                [
                    str(source.get("catalog_source_id") or ""),
                    str(source.get("title") or ""),
                    str(source.get("file_name") or ""),
                    " ".join(str(tag) for tag in source.get("seed_tags", [])),
                ]
            )
            if any(marker and marker in haystack for marker in markers):
                matched.append(source)
        matched.sort(
            key=lambda source: (
                0 if int(source.get("cycle_year") or 0) == current_year else 1,
                abs(int(source.get("cycle_year") or 0) - current_year),
                int(source.get("source_tier") or 99),
                str(source.get("source_id") or ""),
            )
        )
        return [source["source_id"] for source in matched]

    def application_guide_source_ids(self) -> list[str]:
        current_year = int(getattr(self.settings, "knowledge_year", 2025))
        source_ids = [
            source["source_id"]
            for source in self.knowledge.sources
            if source.get("source_type") == "annual_guide"
            and int(source.get("cycle_year") or 0) == current_year
        ]
        if source_ids:
            return source_ids
        source_ids = self.source_ids_by_markers(f"guide_songshanhu_{current_year}", "松山湖", "申请指南")
        return source_ids or self.source_ids_by_type("annual_guide")

    def is_application_guide_source(self, source_id: str) -> bool:
        return source_id in self.application_guide_source_ids()

    def is_special_policy_priority_query(self, message_text: str) -> bool:
        text = message_text or ""
        return any(marker in text for marker in SPECIAL_POLICY_PRIORITY_MARKERS)

    def should_prioritize_application_guide(self, *, message_text: str, intent: str) -> bool:
        text = message_text or ""
        if intent == "平台操作":
            return False
        if self.is_special_policy_priority_query(text):
            return False
        if "申请指南" in text:
            return True
        if intent in GUIDE_PRIORITY_INTENTS:
            return True
        return any(marker in text for marker in GUIDE_PRIORITY_MARKERS)

    def best_application_guide_evidence(self, *, message_text: str) -> RetrievedEvidence | None:
        guide_source_ids = self.application_guide_source_ids()
        if not guide_source_ids:
            return None

        query_norm = normalize_text(message_text)
        query_tokens = extract_tokens(message_text)
        clauses = self.answer_clauses(message_text)
        best_item: RetrievedEvidence | None = None
        best_score = -1.0

        for doc in self.knowledge.documents:
            if doc["source_id"] not in guide_source_ids:
                continue
            text = doc.get("text", "")
            normalized_text = doc.get("normalized_text") or normalize_text(text)
            tokens = set(doc.get("tokens") or extract_tokens(text))
            clause_hits = sum(1 for clause in clauses if clause and clause in normalized_text)
            score = clause_hits * 1.1
            if query_norm and query_norm in normalized_text:
                score += 1.0
            score += token_overlap(query_tokens, tokens) * 1.2
            if doc.get("citation") == "资料摘要":
                score -= 0.08
            else:
                score += 0.12
            if score <= best_score:
                continue
            candidate = self.from_document_hit(RankedHit(record=doc, score=round(score, 4)))
            best_item = candidate
            best_score = score
        return best_item

    def category_definition_hits(self, message_text: str) -> list[RetrievedEvidence]:
        codes = self.extract_category_codes(message_text)
        if not codes:
            return []

        hits: list[RetrievedEvidence] = []
        for code in codes:
            item = self.lookup_category_definition_evidence(code)
            if item is not None:
                hits.append(item)
            faq_item = self.lookup_category_faq_evidence(code, message_text=message_text)
            if faq_item is not None:
                hits.append(faq_item)
        return hits

    def lookup_category_definition_evidence(self, code: str) -> RetrievedEvidence | None:
        guide_source_ids = self.application_guide_source_ids()
        candidates = [doc for doc in self.knowledge.documents if doc["source_id"] in guide_source_ids]
        if not candidates:
            return None

        def page_number(citation: str | None) -> int:
            match = re.search(r"(\d+)", citation or "")
            return int(match.group(1)) if match else 9999

        def score(doc: dict[str, Any]) -> tuple[int, int, int]:
            text = doc.get("text", "")
            hits = len(re.findall(re.escape(code), text))
            early_page = 1 if page_number(doc.get("citation")) <= 8 else 0
            return (hits, early_page, -page_number(doc.get("citation")))

        matched = [doc for doc in candidates if code in doc.get("text", "")]
        if not matched:
            return None
        best = max(matched, key=score)
        source = self.knowledge.source_for(best["source_id"])
        return RetrievedEvidence(
            source_id=best["source_id"],
            title=best.get("title") or source.get("file_name", ""),
            page=best.get("citation"),
            chunk_id=best.get("chunk_id", f"{best['source_id']}-{code.lower()}"),
            quote_snippet=compact_snippet(best.get("text", ""), limit=140),
            source_tier=int(source["source_tier"]),
            score=1.72,
            source_kind="category_definition",
            file_name=source.get("file_name", ""),
        )

    def lookup_category_faq_evidence(self, code: str, *, message_text: str) -> RetrievedEvidence | None:
        matched: list[RetrievedEvidence] = []
        for faq in self.knowledge.faqs:
            question = faq.get("question", "")
            answer = faq.get("answer", "")
            if code not in question and code not in answer:
                continue
            source = self.knowledge.source_for(faq["source_id"])
            matched.append(
                RetrievedEvidence(
                    source_id=faq["source_id"],
                    title=source.get("file_name", question),
                    page=f"FAQ 第{faq['row_number']}条",
                    chunk_id=faq["faq_id"],
                    quote_snippet=compact_snippet(answer, limit=140),
                    source_tier=int(source["source_tier"]),
                    score=1.48 if code in question else 1.25,
                    source_kind="category_faq",
                    file_name=source.get("file_name", ""),
                )
            )
        if not matched:
            return None
        matched.sort(
            key=lambda item: (
                -self.evidence_focus_score(message_text=message_text, item=item),
                item.source_tier,
                -item.score,
            )
        )
        return matched[0]

    def preferred_source_terms(self, message_text: str) -> list[str]:
        text = message_text or ""
        current_year = int(getattr(self.settings, "knowledge_year", 2025))
        terms: list[str] = []
        if "优才卡" in text:
            terms.extend(
                [
                    "优才卡",
                    "东莞市人民政府关于印发《东莞市优才卡管理暂行办法》的通知",
                    "优待政策",
                    f"{current_year}年机器人业务文档",
                ]
            )
        if "优粤卡" in text:
            terms.extend(
                [
                    "优粤卡",
                    "广东省人民政府关于印发广东省人才优粤卡实施办法的通知",
                    "优待政策",
                ]
            )
        if "台湾" in text:
            terms.append("台湾")
        if "华侨" in text or "华人" in text:
            terms.append("华侨华人")
        if "香港" in text or "澳门" in text:
            terms.extend(["香港", "澳门", "优待政策"])
        if "B1" in text:
            terms.append("企业人才子女入学实施办法")
        if "房产" in text or "解锁" in text or "锁定" in text:
            terms.append(f"{current_year}年松山湖中小学、幼儿园入学申请指南")
        if "单位账号" in text or "修改资料" in text or "管理员账号" in text:
            terms.extend(["平台操作指引", f"{current_year}年机器人业务文档"])
        return terms

    def preferred_content_terms(self, message_text: str) -> list[str]:
        text = message_text or ""
        terms: list[str] = []
        if "优才卡" in text:
            terms.extend(["优才卡", "B2.2", "持卡人子女"])
        if "房产属于爷爷" in text or "跟爷爷" in text:
            terms.extend(["A1.1", "祖父母", "第一家庭"])
        if "优粤卡" in text:
            terms.extend(["优粤卡", "子女入读义务教育阶段公办学校"])
        if "华侨" in text or "华人" in text:
            terms.extend(["华侨华人", "市侨务局", "市教育局"])
        for code in self.extract_category_codes(text):
            terms.append(code)
        return terms

    def special_policy_terms(self, message_text: str) -> list[str]:
        text = message_text or ""
        terms: list[str] = []
        if "优才卡" in text:
            terms.extend(["优才卡", "B2.2", "持卡人子女"])
        if "优粤卡" in text:
            terms.extend(["优粤卡", "持卡人子女", "同等待遇"])
        if "台湾" in text:
            terms.extend(["台湾", "通行证", "申请书"])
        if "华侨" in text or "华人" in text:
            terms.extend(["华侨", "华人", "市侨务局"])
        return [normalize_text(item) for item in terms if item]

    def forbidden_content_terms(self, message_text: str) -> list[str]:
        text = message_text or ""
        if "房产属于爷爷" in text or "跟爷爷" in text:
            return ["A3 类", "A3类"]
        return []

    def special_query_variants(self, message_text: str) -> list[str]:
        text = message_text or ""
        queries: list[str] = []
        if self.is_category_comparison_question(text):
            codes = self.extract_category_codes(text)
            if len(codes) >= 2:
                queries.append("、".join(f"{code}类" if code != "C" else "C类" for code in codes[:3]) + " 区别")
        elif self.is_category_definition_question(text):
            codes = self.extract_category_codes(text)
            if codes:
                code = codes[0]
                queries.append(f"{code}类 是什么意思")
        if "优才卡" in text:
            queries.extend(
                [
                    "我有优才卡，工作地在松山湖，可以申请松山湖的学位吗？",
                    "优才卡 B2.2",
                    "优才卡持卡人 子女入学",
                ]
            )
        if "优粤卡" in text:
            queries.extend(
                [
                    "优粤卡 持卡人 子女入学",
                    "广东省人才优粤卡实施办法 子女教育",
                    "广东省人民政府关于印发广东省人才优粤卡实施办法的通知",
                ]
            )
        if "台湾" in text:
            queries.extend(["台湾籍子女入学怎样申请？", "台湾学生 申请书 通行证 B2.2"])
        if "华侨" in text or "华人" in text:
            queries.extend(
                [
                    "华人华侨子女如何申请园区学位？",
                    "华侨华人 市侨务局 市教育局",
                    "关于修订华侨华人子女及华侨学生在我市就读有关规定的通知",
                ]
            )
        if "香港" in text or "澳门" in text:
            queries.extend(["孩子是香港/澳门户籍，父母服务地/居住地/户籍地在松山湖或在松山湖拥有产权清晰的自有居所，如何申请入学？"])
        if "B1" in text and "满一年" in text:
            queries.extend(["B1要求在该企业工作满一年，是按什么时间计算？", "B1 满 1 年 8 月 31 日"])
        if "B3" in text and "排名" in text:
            queries.extend(["B3类会公布排名吗？根据排名安排学校吗？", "B3 不公布排名 分数线"])
        if "解锁" in text:
            queries.extend(["如何对学位申请房进行解锁？", "申请解锁 等待审核"])
        if "锁定" in text:
            queries.extend(["我的房子被锁定了学位，要如何处理？", "房产锁定 家庭户 A1"])
        if "修改资料" in text or "资料有误" in text:
            queries.extend(["报名时，我发现我上传的资料有误，如何进行修改？", "修改资料 未审核 审核不通过"])
        if "单位账号" in text or "企业账号" in text:
            queries.extend(["哪种类型所在的单位需注册单位账号？", "A2 B类 单位账号"])
        if "提交报名申请后需要做什么工作" in text:
            queries.extend(["A2、B类提交报名申请后需要做什么工作？", "单位 审核 后续积分排名"])
        if "企业名额" in text or "管理员账号" in text:
            queries.extend(["企业如何查询B1类企业名额？", "B1 管理员账号 5月11日"])
        if "同时申请" in text and "B3" in text and "C" in text:
            queries.extend(["松山湖的B3类企业积分制人才和C类东莞市非户籍适龄儿童少年积分制入学可以同时申请吗？"])
        if "房产属于爷爷" in text or "跟爷爷" in text:
            queries.extend(
                [
                    "A1.1 祖父母 第一家庭",
                    "房产持有人是祖父母 A1.1 第一家庭",
                    "祖父母 第一家庭 A1.1",
                ]
            )
        if "A3类中" in text:
            queries.extend(["A3 非直系亲属 房产交易 父母名下无房产"])
        if "全家均无园区户籍" in text or ("C类" in text and "居住" in text):
            queries.extend(["C类 积分入学 居住证 东莞市外", "积分入学 申请条件"])
        return list(dict.fromkeys([item for item in queries if item]))

    def preferred_source_hits(self, message_text: str) -> list[RetrievedEvidence]:
        text = message_text or ""
        hits: list[RetrievedEvidence] = []
        guide_source_ids = self.application_guide_source_ids()
        if "优才卡" in text:
            for keywords in (("优才卡", "子女", "义务教育"), ("优才卡", "优待政策")):
                source_id = "src-001" if "义务教育" in keywords else "src-008"
                item = self.lookup_source_evidence(source_id, keywords)
                if item is not None:
                    hits.append(item)
        if "优粤卡" in text:
            for source_id, keywords in (
                ("src-007", ("优粤卡", "子女", "入学")),
                ("src-008", ("优粤卡", "优待政策")),
            ):
                item = self.lookup_source_evidence(source_id, keywords)
                if item is not None:
                    hits.append(item)
        if "华侨" in text or "华人" in text:
            item = self.lookup_source_evidence("src-005", ("华侨", "华人", "市侨务局", "市教育局"))
            if item is not None:
                hits.append(item)
        if "台湾" in text:
            for keywords in (("台湾", "义务教育", "申请"), ("台湾", "通行证", "居住证")):
                item = self.lookup_source_evidence("src-006", keywords)
                if item is not None:
                    hits.append(item)
        if "香港" in text or "澳门" in text:
            for source_id, keywords in (
                ("src-008", ("香港", "澳门", "优待政策")),
                *((guide_source_id, ("香港", "澳门", "入学")) for guide_source_id in guide_source_ids),
            ):
                item = self.lookup_source_evidence(source_id, keywords)
                if item is not None:
                    hits.append(item)
        if "房产属于爷爷" in text or "跟爷爷" in text:
            for guide_source_id in guide_source_ids:
                for keywords in (("A1.1", "祖父母", "第一家庭"), ("祖父母", "第一家庭", "A1")):
                    item = self.lookup_source_evidence(guide_source_id, keywords)
                    if item is not None:
                        hits.append(item)
        return hits

    def lookup_source_evidence(self, source_id: str, keywords: tuple[str, ...]) -> RetrievedEvidence | None:
        if source_id not in getattr(self.knowledge, "source_map", {}):
            marker_map = {
                "src-001": ("policy_dg_youcai", "优才卡"),
                "src-005": ("policy_dg_overseas_chinese", "华侨华人"),
                "src-006": ("policy_dg_taiwan", "台湾学生"),
                "src-007": ("policy_gd_youyue", "优粤卡"),
                "src-008": ("优待政策", "香港", "澳门", "policy_gd_youyue", "policy_dg_honorary"),
            }
            for marker in marker_map.get(source_id, ()):
                fallback_ids = self.source_ids_by_markers(marker)
                if fallback_ids:
                    source_id = fallback_ids[0]
                    break
        candidates = [doc for doc in self.knowledge.documents if doc["source_id"] == source_id]
        source = self.knowledge.source_for(source_id)
        if not candidates:
            return RetrievedEvidence(
                source_id=source_id,
                title=source.get("file_name", source_id),
                page="政策文件",
                chunk_id=f"{source_id}-source",
                quote_snippet=source.get("file_name", source_id),
                source_tier=int(source["source_tier"]),
                score=1.5,
                source_kind="source_index",
                file_name=source.get("file_name", ""),
            )

        def score(doc: dict[str, Any]) -> tuple[int, int]:
            text = doc.get("text", "")
            hits = sum(1 for keyword in keywords if keyword in text)
            return (hits, -len(text))

        best = max(candidates, key=score)
        return RetrievedEvidence(
            source_id=source_id,
            title=best.get("title") or source.get("file_name", ""),
            page=best.get("citation"),
            chunk_id=best.get("chunk_id", f"{source_id}-preferred"),
            quote_snippet=compact_snippet(best.get("text", ""), limit=110),
            source_tier=int(source["source_tier"]),
            score=1.8,
            source_kind="preferred_source",
            file_name=source.get("file_name", ""),
        )

    def generate_direct_answer(
        self,
        *,
        message_text: str,
        scope: ScopeResult,
        classification: RuleClassification,
        profile: StudentFacts,
        evidence: list[RetrievedEvidence],
        base_risks: list[str],
        human_support: str,
    ) -> AnswerPayload | None:
        text = message_text or ""
        ordered_evidence = self.order_answer_evidence(message_text=message_text, evidence=evidence)
        basis_lines = self.render_basis_lines(ordered_evidence)
        default_basis = basis_lines or ["当前回答结合已命中的官方指南、答疑和政策文件整理。"]

        def build_payload(
            *,
            question_type: str,
            initial_conclusion: str,
            eligibility_or_issue: str,
            required_materials: list[str] | None = None,
            next_actions: list[str] | None = None,
            risk_alerts: list[str] | None = None,
        ) -> AnswerPayload:
            return AnswerPayload(
                status=AnswerStatus.ANSWERED,
                scope=scope.scope,
                question_type=question_type,
                initial_conclusion=initial_conclusion,
                eligibility_or_issue=eligibility_or_issue,
                judgement_basis=default_basis,
                required_materials=required_materials or self.recommend_materials(profile=profile, intent=question_type),
                next_actions=next_actions or self.recommend_next_actions(intent=question_type, has_official_support=True),
                risk_alerts=risk_alerts or list(base_risks),
                human_support=human_support,
                follow_up_questions=[],
            )

        if "优粤卡" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="优粤卡持卡人子女入学应按优待政策方向核对，园区咨询场景下通常归入 B2 优待路径理解。",
                eligibility_or_issue="当前问题属于优粤卡政策依据查询，可以先依据省级优粤卡办法和园区当年优待政策汇总解释，最终仍以当年公告和审核口径为准。",
                required_materials=["优粤卡持卡证明", "监护人与学童关系证明", "工作地或居住地相关证明"],
                next_actions=[
                    "先按优粤卡优待方向核对是否满足当年落地条件。",
                    "如需正式申报，再按园区平台当年要求准备材料并提交审核。",
                ],
            )

        if "台湾" in text and ("学生" in text or "义务教育" in text):
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="台湾学生申请东莞义务教育阶段学校，应按台湾学生专项通知准备申请书、身份证件和在莞相关证明材料。",
                eligibility_or_issue="当前问题属于台湾学生专项申请路径查询，不按普通 A/B/C 家庭条件直接下资格结论。",
                required_materials=["台湾学生入学申请书", "台湾居民来往大陆通行证或居住证", "监护人在莞就业、居住或投资证明"],
                next_actions=[
                    "先按台湾学生专项通知核对申请材料。",
                    "再结合园区平台当年入口上传对应资料。",
                ],
            )

        if "华侨" in text or "华人" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="华侨华人子女及华侨学生申请入学，应优先按华侨华人专项通知办理，不直接套用普通类别自动落类。",
                eligibility_or_issue="当前问题属于华侨华人专项政策路径，通常需要先按侨务和教育部门要求完成登记与审核。",
                required_materials=["身份及关系证明", "侨务部门要求的登记材料", "在莞就业、投资或居住相关证明"],
                next_actions=[
                    "先按华侨华人专项通知准备登记和审核材料。",
                    "再按教育部门和园区要求补交后续入学资料。",
                ],
            )

        if "单位账号" in text or ("管理员" in text and "审核" in text):
            return build_payload(
                question_type="平台操作",
                initial_conclusion="A2、B类人员所在单位通常需要先完成单位账号注册或信息更新，再由管理员审核员工申报资料。",
                eligibility_or_issue="当前问题属于平台操作规则，可直接解释流程，不需要先判断家庭资格。",
                required_materials=["单位账号注册或变更申请表", "统一社会信用代码证复印件", "平台要求的盖章扫描件"],
                next_actions=[
                    "先由单位完成账号注册或年度信息更新。",
                    "再由管理员登录平台审核员工资料并推进后续流程。",
                ],
            )

        if "C类" in text and "积分入学" in text and any(marker in text for marker in ("适用", "人群", "对象")):
            return build_payload(
                question_type="积分入学",
                initial_conclusion="C类对应东莞市非户籍适龄儿童少年积分入学路径，面向不属于园区户籍 A 类、也不直接走优待政策 B 类的非户籍适龄学童。",
                eligibility_or_issue="当前问题属于积分入学适用范围说明，可以先解释政策对象，但不能据此直接替代当年积分审核结果。",
                required_materials=["积分方居住证、社保或个税等积分材料", "学童及监护人身份关系证明"],
                next_actions=[
                    "先核对是否满足东莞市积分入学的积分方条件。",
                    "再按 C 类入口准备居住证和积分材料。",
                ],
            )

        if self.is_category_comparison_question(text):
            codes = self.extract_category_codes(text)
            conclusion = self.compose_category_comparison_conclusion(codes)
            issue_note = self.compose_category_comparison_issue(codes)
            return build_payload(
                question_type="类别说明",
                initial_conclusion=conclusion,
                eligibility_or_issue=issue_note,
                required_materials=[],
                next_actions=[
                    "先按对应类别的适用对象和分配方式判断自己更接近哪条路径。",
                    "如果你要落到自己家庭能报哪一类，再补充孩子户籍、家长工作地、房产和学段信息。",
                ],
            )

        if self.is_category_definition_question(text):
            codes = self.extract_category_codes(text)
            code = codes[0]
            return build_payload(
                question_type="类别说明",
                initial_conclusion=self.compose_category_definition_conclusion(code),
                eligibility_or_issue=self.compose_category_definition_issue(code),
                required_materials=[],
                next_actions=[
                    "先看这个类别的适用对象和限制条件是否与你的情况一致。",
                    "如果你想进一步判断自己能不能按这一类申报，可以继续补充具体家庭情况。",
                ],
            )

        if "优才卡" in text:
            return build_payload(
                question_type="类别判断",
                initial_conclusion="优才卡持卡人如工作单位或自有房产所在地在松山湖，可按 B2 类处理，并在松山湖入学管理平台选择 B2.2 类别申请。",
                eligibility_or_issue="当前问题命中 优才卡 / B2 / B2.2 路径；如以工作关系申请，工作单位所在地和发卡地均需在松山湖。",
                required_materials=[
                    "优才卡持卡证明",
                    "工作单位所在地或自有房产所在地在松山湖的证明",
                    "监护人与学童身份关系证明及户籍材料",
                ],
                next_actions=[
                    "按 B2.2 路径核对报名条件并准备优才卡、工作地或房产地证明。",
                    "登录松山湖入学管理平台，按 B2.2 类别提交申请。",
                ],
            )

        if "优粤卡" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="优粤卡持卡人子女入学应按优待政策理解，可优先按 B2 优待方向核对。",
                eligibility_or_issue="当前问题命中 优粤卡 优待路径；园区落地口径仍应以当年公告和教育部门审核为准。",
                required_materials=[
                    "优粤卡持卡证明",
                    "监护人工作地或居住地证明",
                    "学童及监护人身份关系证明",
                ],
                next_actions=[
                    "先按优粤卡优待方向核对材料。",
                    "如需确认当年园区是否沿用相同口径，再联系官方渠道复核。",
                ],
            )

        if "台湾" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="台湾学生按 B2 / B2.2 资料路径申请，通常需要《东莞市台湾学生入学申请书》、相关申请表和《台湾居民来往大陆通行证》等材料。",
                eligibility_or_issue="当前问题命中 台湾 / B2 / 申请书 / 通行证 路径，且需补充就业或投资证明。",
                required_materials=[
                    "《东莞市台湾学生入学申请书》及《台湾学生就读义务教育阶段学校申请表》",
                    "台湾居民来往大陆通行证或台湾居民居住证",
                    "台籍监护人在莞就业或投资证明",
                ],
                next_actions=[
                    "按台湾学生材料清单准备申请书、通行证和就业/投资证明。",
                    "通过松山湖入学管理平台按 B2.2 资料路径上传材料。",
                ],
            )

        if "华侨" in text or "华人" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="华侨华人子女入学应按专项通知办理，先到市侨务局登记，再由市教育局审核并转园区教育部门统筹安排。",
                eligibility_or_issue="当前问题命中 华侨 / 市侨务局 / 市教育局 路径，不直接按常规 A/B/C 自动落类。",
                required_materials=[
                    "市侨务部门要求的申请登记材料",
                    "监护人与学童身份证明及关系证明",
                    "在莞就业、投资或祖籍相关证明",
                ],
                next_actions=[
                    "先按华侨华人专项规定向市侨务局办理申请登记。",
                    "再根据市教育局和园区教育部门要求补交后续资料。",
                ],
            )

        if "香港" in text or "澳门" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="香港/澳门学童如父母服务地、居住地、户籍地在松山湖，或在松山湖有产权清晰的自有居所，可优先核对优待政策（如优才卡）或积分入学路径。",
                eligibility_or_issue="当前问题命中 香港 / 澳门 / 优才卡 / 积分入学 路径，具体申报时仍需按当年条件择一核对。",
                required_materials=[
                    "港澳身份及通行证件",
                    "监护人在松山湖的工作地、居住地、户籍地或房产证明",
                    "如走优待路径，再补优待身份材料",
                ],
                next_actions=[
                    "先核对是否符合优待政策条件；如不符合，再核对积分入学条件。",
                    "通过松山湖入学管理平台查看具体申报入口和材料要求。",
                ],
            )

        if "B1" in text and "满一年" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="B1 指标企业人员“在该企业工作满 1 年”按截至当年 8 月 31 日计算。",
                eligibility_or_issue="当前问题属于 B1 政策依据查询，核心口径是 8 月 31 日前满 1 年。",
                next_actions=[
                    "按 8 月 31 日为截止点核对劳动关系、社保和在职时间。",
                    "再由单位管理员按 B1 路径提交或审核资料。",
                ],
            )

        if "B3" in text and "排名" in text:
            return build_payload(
                question_type="政策依据查询",
                initial_conclusion="B3 往年只公布分数线，不公布排名。",
                eligibility_or_issue="学位安排会结合学位供给、工作情况、居住地址和积分等因素统筹，不按公开排名直接排位。",
                next_actions=[
                    "先按 B3 要求准备材料并关注分数线和单位审核。",
                    "不要把排名截图或口口相传信息当作正式依据。",
                ],
            )

        if "房产" in text and "锁定" in text and "解锁" not in text:
            return build_payload(
                question_type="房产锁定/解锁",
                initial_conclusion="房产锁定主要围绕 A1 家庭户学位申请房；历史占用、同址多家庭或同一学段已使用学位等情形会触发锁定。",
                eligibility_or_issue="当前问题命中 房产 / 锁定 / A1 / 家庭户 路径；锁定期间可申请统筹安排，但不能直接占用已锁定学校同一学段学位。",
                next_actions=[
                    "先在平台查询锁定状态和锁定原因。",
                    "如需继续申报，再按官方要求准备解锁或统筹申请材料。",
                ],
            )

        if "解锁" in text:
            return build_payload(
                question_type="房产锁定/解锁",
                initial_conclusion="可在松山湖入学管理平台“家庭户学位申请房锁定查询”页面点击“申请解锁”，提交后等待审核。",
                eligibility_or_issue="当前问题命中 解锁 / 申请解锁 / 等待审核 路径。",
                next_actions=[
                    "先查询房产锁定情况，再在同页点击“申请解锁”。",
                    "按页面提示填写信息、上传资料，保存后等待审核结果。",
                ],
            )

        if "资料有误" in text or "修改资料" in text:
            return build_payload(
                question_type="平台操作",
                initial_conclusion="在报名期间，单位未审核的申请和审核不通过的申请可修改资料。",
                eligibility_or_issue="登录平台后进入报名信息页面，点击右上角“修改资料”；修改资料适用于 未审核 和 审核不通过 的申请。",
                next_actions=[
                    "进入报名信息页面，点击右上角“修改资料”。",
                    "根据审核意见修正后重新提交，等待再次审核。",
                ],
            )

        if "单位账号" in text or "企业账号" in text:
            return build_payload(
                question_type="平台操作",
                initial_conclusion="A2 和 B类所在单位需要注册单位账号。",
                eligibility_or_issue="当前问题命中 A2 / B类 / 单位账号 路径；单位完成账号注册和管理员审核后，才能继续处理员工申请。",
                next_actions=[
                    "由单位先完成账号注册或年度信息更新。",
                    "管理员登录平台审核员工申请，再进入后续流程。",
                ],
            )

        if "提交报名申请后需要做什么工作" in text:
            return build_payload(
                question_type="平台操作",
                initial_conclusion="A2、B类提交报名申请后，单位还要继续完成审核，后续再进入积分排名或统筹安排等流程。",
                eligibility_or_issue="当前问题命中 审核 / 单位 / 后续积分排名 路径。",
                next_actions=[
                    "先由单位管理员审核申请资料。",
                    "再关注后续积分排名、学位统筹和录取公布节点。",
                ],
            )

        if "企业名额" in text or "管理员账号" in text:
            return build_payload(
                question_type="平台操作",
                initial_conclusion="B1 类企业名额将于 5月11日上午 导入平台，企业可登录管理员账号查看。",
                eligibility_or_issue="这属于 B1 / 管理员账号 / 5月11日 的平台查看问题；如实际页面状态不一致，应以实时平台显示为准。",
                next_actions=[
                    "由企业管理员账号登录平台查看 B1 名额。",
                    "如平台未显示或状态异常，再联系人工核验。",
                ],
            )

        if self.is_simultaneous_b3_c_question(text) and not self.is_case_specific_simultaneous_b3_c_question(text):
            return build_payload(
                question_type="类别判断",
                initial_conclusion="符合条件时，B3 和 C类可同时申请。",
                eligibility_or_issue="当前问题命中 B3 / C类 / 可同时申请 路径；两条路径分别对应园区企业积分制人才和东莞市非户籍适龄儿童少年积分制入学。",
                next_actions=[
                    "分别按 B3 和 C类材料要求准备资料。",
                    "在对应平台入口按时完成双路径申报。",
                ],
            )

        if "A2类、B2类" in text or ("A2" in text and "B2" in text and "只能" in text):
            return build_payload(
                question_type="类别判断",
                initial_conclusion="这种情形可以核对 A2、B2 两条路径，但只能任选一个类别申报，不能同时申报两个类别。",
                eligibility_or_issue="当前问题命中 A2 / B2 / 只能任选一个 路径。",
                next_actions=[
                    "先核对自己更符合 A2 还是 B2 的条件。",
                    "正式报名时只选择一个类别提交。",
                ],
            )

        if "A3类中" in text:
            return build_payload(
                question_type="类别判断",
                initial_conclusion="A3 指的是学童和父（母）是松山湖家庭户，但学童与房产所有人为非直系亲属关系；这类不按自有直系房产路径认定。",
                eligibility_or_issue="当前问题命中 A3 / 房产交易 / 父母名下无房产 的解释路径。",
                next_actions=[
                    "先核对房产权属关系是否属于非直系亲属。",
                    "再结合当年申请指南确认是否按 A3 路径提交材料。",
                ],
            )

        if "房产属于爷爷" in text or "跟爷爷" in text:
            return build_payload(
                question_type="类别判断",
                initial_conclusion="按当前问题描述，更接近 A1 路径。",
                eligibility_or_issue="当前问题命中 A1 方向：学童为松山湖户籍，且祖辈房产用于家庭户入学时，需要按第一家庭规则核验。",
                next_actions=[
                    "先核对学童户籍与房产地址关系，以及是否满足第一家庭认定条件。",
                    "再按 A1 路径准备户籍和房产相关材料。",
                ],
            )

        if "全家均无园区户籍" in text or ("C类" in text and "居住" in text):
            return build_payload(
                question_type="积分入学",
                initial_conclusion="这类更接近 C类积分入学。",
                eligibility_or_issue="当前问题命中 C类 / 东莞市外 / 居住证 路径；仅在松山湖居住不直接变成 A/B 类，通常要由积分方凭居住证等材料走东莞市积分入学。",
                required_materials=[
                    "积分方的居住证、社保、纳税等积分材料",
                    "学童及监护人身份和关系证明",
                    "居住地相关证明材料",
                ],
                next_actions=[
                    "先核对是否满足东莞市积分入学的积分方条件。",
                    "再按 C类入口准备居住证和积分材料。",
                ],
            )

        return None

    def compose_category_definition_conclusion(self, code: str) -> str:
        info = CATEGORY_KNOWLEDGE.get(code)
        if info is None:
            return "当前命中的资料不足以直接解释这个类别。"
        return f"直接说结论：{info['label']}指的是{info['summary']}"

    def compose_category_definition_issue(self, code: str) -> str:
        info = CATEGORY_KNOWLEDGE.get(code)
        if info is None:
            return "当前资料不足，暂时不能直接解释该类别。"
        return info["focus"]

    def compose_category_comparison_conclusion(self, codes: list[str]) -> str:
        selected = [CATEGORY_KNOWLEDGE[code] for code in codes if code in CATEGORY_KNOWLEDGE][:3]
        if len(selected) < 2:
            return "当前命中的资料不足以直接比较这些类别。"
        if len(selected) == 2:
            left, right = selected
            return f"直接说区别：{left['label']}是{left['summary']}；{right['label']}是{right['summary']}"
        return "直接说区别：这几个类别的核心差别在于适用对象、户籍属性，以及是按企业指标、优待政策还是积分方式申请。"

    def compose_category_comparison_issue(self, codes: list[str]) -> str:
        focuses = [CATEGORY_KNOWLEDGE[code]["focus"] for code in codes if code in CATEGORY_KNOWLEDGE][:3]
        if not focuses:
            return "当前资料不足，暂时不能直接比较这些类别。"
        return "；".join(focuses)

    def evaluate_confidence(
        self,
        *,
        message_text: str,
        scope: ScopeResult,
        classification: RuleClassification,
        missing: MissingContextResult,
        evidence: list[RetrievedEvidence],
    ) -> float:
        if not scope.in_scope:
            return 0.15

        score = 0.35
        official = [item for item in evidence if item.source_tier <= 4]
        supplemental = [item for item in evidence if item.source_tier > 4]

        if official:
            score += 0.25
            score += 0.1 if min(item.source_tier for item in official) <= 2 else 0.05
        elif supplemental:
            score -= 0.12

        if len(official) >= 2:
            score += 0.1
        if classification.is_case_specific and not missing.follow_up_questions:
            score += 0.08
        if missing.follow_up_questions:
            score -= 0.28
        if classification.is_latest_request:
            score -= 0.35
        if classification.platform_status_requires_manual_check:
            score -= 0.35
        if classification.profile_conflicts:
            score -= 0.3
        if classification.policy_conflict_detected:
            score -= 0.35
        if classification.asks_for_probability:
            score -= 0.18
        if self.is_simultaneous_b3_c_question(message_text) and not self.is_case_specific_simultaneous_b3_c_question(message_text):
            score += 0.4

        return round(min(0.95, max(0.05, score)), 2)

    def decide_escalation(
        self,
        *,
        scope: ScopeResult,
        classification: RuleClassification,
        missing: MissingContextResult,
        confidence: float,
        follow_up_rounds: int,
    ) -> EscalationDecision:
        reasons: list[str] = []
        action = EscalationAction.NONE
        should_handoff = False

        if not scope.in_scope:
            action = EscalationAction.SCOPE_REDIRECT
            reasons.append("out_of_scope")
        elif classification.asks_for_human:
            action = EscalationAction.HANDOFF_HUMAN
            should_handoff = True
            reasons.append("user_requested_human")
        elif classification.profile_conflicts:
            action = EscalationAction.HANDOFF_HUMAN
            should_handoff = True
            reasons.append("user_profile_conflict")
        elif classification.policy_conflict_detected:
            action = EscalationAction.HANDOFF_HUMAN
            should_handoff = True
            reasons.append("policy_conflict")
        elif classification.is_latest_request:
            action = EscalationAction.HANDOFF_HUMAN
            should_handoff = True
            reasons.append("current_year_info_missing")
        elif classification.platform_status_requires_manual_check:
            action = EscalationAction.HANDOFF_HUMAN
            should_handoff = True
            reasons.append("platform_verification_required")
        elif missing.follow_up_questions:
            reasons.append("insufficient_information")
            if follow_up_rounds >= 2:
                action = EscalationAction.HANDOFF_HUMAN
                should_handoff = True
            else:
                action = EscalationAction.ASK_FOLLOW_UP
        elif confidence < 0.55:
            action = EscalationAction.HANDOFF_HUMAN
            should_handoff = True
            reasons.append("low_confidence")

        if action == EscalationAction.NONE:
            summary = "当前无需人工转接，可按现有证据给出克制回答。"
        elif action == EscalationAction.ASK_FOLLOW_UP:
            summary = "先补 1 到 3 个关键问题；若仍无法补齐，再转人工。"
        elif action == EscalationAction.SCOPE_REDIRECT:
            summary = "当前问题超出招生咨询范围，先做范围说明，不直接转人工判案。"
        else:
            summary = "建议转人工继续处理，避免在证据不足或信息冲突时硬判。"

        return EscalationDecision(
            action=action,
            should_handoff=should_handoff,
            reasons=reasons,
            summary=summary,
            confidence=confidence,
            official_contact=self.settings.official_contact,
        )

    def apply_escalation(self, *, answer: AnswerPayload, escalation: EscalationDecision) -> AnswerPayload:
        if escalation.action == EscalationAction.ASK_FOLLOW_UP:
            answer.status = AnswerStatus.NEED_INFO
            if not any("先补" in item for item in answer.next_actions):
                answer.next_actions.insert(0, escalation.summary)
            return answer

        if escalation.action == EscalationAction.SCOPE_REDIRECT:
            answer.status = AnswerStatus.OUT_OF_SCOPE
            return answer

        if escalation.should_handoff and answer.status == AnswerStatus.ANSWERED:
            answer.status = AnswerStatus.HANDOFF
            answer.next_actions.insert(0, "建议带着当前资料和引用结果转人工复核。")
        return answer

    def build_session_update(
        self,
        *,
        request: ConsultationOrchestrateRequest,
        classification: RuleClassification,
        profile: StudentFacts,
        missing: MissingContextResult,
        escalation: EscalationDecision,
        answer: AnswerPayload,
    ) -> SessionUpdate:
        flags = list(escalation.reasons)
        if classification.asks_for_human and "user_requested_human" not in flags:
            flags.append("user_requested_human")
        follow_up_rounds = request.session_context.follow_up_rounds
        if answer.status == AnswerStatus.NEED_INFO:
            follow_up_rounds += 1
        else:
            follow_up_rounds = 0

        return SessionUpdate(
            conversation_id=request.session_context.conversation_id,
            retained_profile=profile,
            last_intent=classification.intent,
            last_scope=classification.scope,
            asked_missing_fields=missing.missing_labels,
            follow_up_rounds=follow_up_rounds,
            flags=flags,
        )

    def persist_log(
        self,
        *,
        trace_id: str,
        request: ConsultationOrchestrateRequest,
        scope: ScopeResult,
        classification: RuleClassification,
        missing: MissingContextResult,
        citations: list[CitationRef],
        answer: AnswerPayload,
        escalation: EscalationDecision,
        session_update: SessionUpdate,
    ) -> str:
        route_mode = RouteMode.PARENT_CONSULTATION
        routed_agent = "admissions-consultation"
        sender_role = (request.normalized_message.sender_role or "").lower()
        if request.normalized_message.channel_mode == ChannelMode.ADMIN:
            route_mode = RouteMode.ORGANIZATION_ADMIN
            routed_agent = "admissions-consultation-admin"
        elif sender_role in {"operations", "human_support", "manual_support"}:
            route_mode = RouteMode.OPERATIONS_SUPPORT
            routed_agent = "admissions-operations-support"
        shared_snapshot = build_shared_contract_snapshot(
            trace_id=trace_id,
            message=request.normalized_message,
            route_mode=route_mode,
            routed_agent=routed_agent,
            fallback_agent="fallback-human-handoff",
            facts=request.user_profile,
            answer=answer,
            escalation=escalation,
            citations=citations,
            session_update=session_update,
            classification=classification,
            confidence=None,
            knowledge=self.knowledge,
        )
        payload = {
            "trace_id": trace_id,
            "timestamp": now_iso(),
            "normalized_message": {
                "message_id": request.normalized_message.message_id,
                "channel": request.normalized_message.channel,
                "channel_mode": request.normalized_message.channel_mode.value,
                "target": request.normalized_message.target,
                "text": redact_sensitive_text(request.normalized_message.text),
                "sender_role": request.normalized_message.sender_role,
                "timestamp": request.normalized_message.timestamp,
            },
            "scope": {
                "scope": scope.scope,
                "in_scope": scope.in_scope,
                "explanation": scope.explanation,
            },
            "profile": session_update.retained_profile.model_dump(exclude_none=True),
            "missing": {
                "field_names": missing.missing_field_names,
                "labels": missing.missing_labels,
                "follow_up_questions": missing.follow_up_questions,
            },
            "rule_classification": classification.model_dump(mode="json"),
            "citations": [item.model_dump(mode="json") for item in citations],
            "answer_payload": answer.model_dump(mode="json"),
            "escalation_decision": escalation.model_dump(mode="json"),
            "session_update": session_update.model_dump(mode="json"),
            "shared_contracts": shared_snapshot,
        }
        return self.audit_logger.append(payload)

    def merge_facts_with_conflicts(
        self,
        base: StudentFacts,
        incoming: StudentFacts,
        *,
        source: str,
    ) -> tuple[StudentFacts, list[ProfileConflict]]:
        merged = base.model_dump()
        conflicts: list[ProfileConflict] = []
        for key, value in incoming.model_dump().items():
            if key == "special_status":
                merged[key] = sorted(set((merged.get(key) or []) + (value or [])))
                continue
            if self.is_missing_fact(value):
                continue
            existing = merged.get(key)
            if self.is_missing_fact(existing):
                merged[key] = value
                continue
            if existing != value:
                conflicts.append(
                    ProfileConflict(
                        field_name=self.rules.field_labels.get(key, key),
                        existing_value=stringify_value(existing),
                        incoming_value=stringify_value(value),
                        source=source,
                    )
                )
        return StudentFacts(**merged), conflicts

    def prioritize_missing_fields(self, *, intent: str, field_names: list[str]) -> list[str]:
        priority_map = {
            "类别判断": [
                "child_hukou",
                "parent_hukou",
                "parent_work_in_songshanhu",
                "has_songshanhu_property",
                "property_owner",
                "stage",
                "is_transfer",
            ],
            "报名资格判断": [
                "child_hukou",
                "parent_work_in_songshanhu",
                "has_songshanhu_property",
                "stage",
                "is_transfer",
                "parent_hukou",
                "property_owner",
                "special_status",
            ],
            "材料清单": ["stage", "special_status"],
            "转学": ["is_transfer", "stage", "child_hukou"],
            "积分入学": [
                "child_hukou",
                "parent_work_in_songshanhu",
                "has_songshanhu_property",
                "parent_hukou",
            ],
        }
        order = priority_map.get(intent, field_names)
        ranked = [item for item in order if item in field_names]
        for item in field_names:
            if item not in ranked:
                ranked.append(item)
        return ranked

    def is_missing_fact(self, value: Any) -> bool:
        return value in (None, "", [])

    def from_faq_hit(self, hit: RankedHit) -> RetrievedEvidence:
        faq = hit.record
        source = self.knowledge.source_for(faq["source_id"])
        snippet_parts: list[str] = []
        if faq.get("category"):
            snippet_parts.append(f"可报类别：{faq['category']}")
        if faq.get("answer"):
            snippet_parts.append(str(faq["answer"]))
        if faq.get("notes"):
            snippet_parts.append(f"备注：{faq['notes']}")
        return RetrievedEvidence(
            source_id=faq["source_id"],
            title=source.get("file_name", faq.get("question", "FAQ")),
            page=f"FAQ 第 {faq['row_number']} 条",
            chunk_id=faq["faq_id"],
            quote_snippet=compact_snippet("；".join(snippet_parts) or faq.get("answer", ""), limit=140),
            source_tier=int(source["source_tier"]),
            score=round(hit.score, 4),
            source_kind="faq",
            file_name=source.get("file_name", ""),
        )

    def from_document_hit(self, hit: RankedHit) -> RetrievedEvidence:
        record = hit.record
        source = self.knowledge.source_for(record["source_id"])
        return RetrievedEvidence(
            source_id=record["source_id"],
            title=record.get("title") or source.get("file_name", ""),
            page=record.get("citation"),
            chunk_id=record.get("chunk_id", f"{record['source_id']}-chunk"),
            quote_snippet=compact_snippet(record.get("text", ""), limit=110),
            source_tier=int(source["source_tier"]),
            score=round(hit.score, 4),
            source_kind="document",
            file_name=source.get("file_name", ""),
        )

    def keep_best_evidence(self, ranked: dict[str, RetrievedEvidence], item: RetrievedEvidence) -> None:
        existing = ranked.get(item.chunk_id)
        if existing is None or item.score > existing.score:
            ranked[item.chunk_id] = item

    def search_documents_by_answer_hint(self, answer_text: str) -> list[RetrievedEvidence]:
        clauses = self.answer_clauses(answer_text)
        ranked: list[RetrievedEvidence] = []
        for doc in self.knowledge.documents:
            doc_text = doc.get("normalized_text") or normalize_text(doc.get("text", ""))
            best = 0.0
            for clause in clauses:
                if clause and clause in doc_text:
                    best = max(best, 1.2 + min(0.6, len(clause) / 80))
            if best <= 0:
                continue
            source = self.knowledge.source_for(doc["source_id"])
            ranked.append(
                RetrievedEvidence(
                    source_id=doc["source_id"],
                    title=doc.get("title") or source.get("file_name", ""),
                    page=doc.get("citation"),
                    chunk_id=doc.get("chunk_id", f"{doc['source_id']}-chunk"),
                    quote_snippet=compact_snippet(doc.get("text", ""), limit=110),
                    source_tier=int(source["source_tier"]),
                    score=round(best, 4),
                    source_kind="document_hint",
                    file_name=source.get("file_name", ""),
                )
            )
        ranked.sort(key=lambda item: (item.source_tier > 4, -item.score, item.source_tier))
        return ranked[:3]

    def answer_clauses(self, text: str) -> list[str]:
        raw_parts = re.split(r"[：:；;，,。\n]", text or "")
        clauses = []
        for part in raw_parts:
            normalized = normalize_text(part)
            if len(normalized) >= 8:
                clauses.append(normalized)
        clauses.sort(key=len, reverse=True)
        return clauses[:3]

    def intent_query_variants(self, intent: str) -> list[str]:
        mapping = {
            "类别判断": ["A类 B类 C类 申请对象", "申请对象 A类 B类 C类"],
            "报名资格判断": ["申请对象 申请条件", "入学申请 指南 申请对象"],
            "材料清单": ["申请材料 提交资料", "申请资料 上传材料"],
            "平台操作": ["入学管理平台 报名 流程", "统一招生平台 报名号"],
            "房产锁定/解锁": ["学位申请房 锁定 解锁", "家庭户学位申请房 锁定"],
            "转学": ["不接受以下人员申请转学", "转学 申请对象"],
            "幼儿园申请": ["幼儿园 申请对象", "幼儿园 申请材料"],
            "积分入学": ["积分入学 申请条件", "积分入学 转学与升学"],
            "政策依据查询": ["申请指南 政策依据", "政策 文件 申请对象"],
        }
        return mapping.get(intent, [])

    def render_basis_lines(self, evidence: list[RetrievedEvidence]) -> list[str]:
        return [f"依据{self.source_label(item)}：{self.clean_quote_snippet(item.quote_snippet, limit=120)}" for item in evidence[:3]]

    def compose_grounded_conclusion(
        self,
        *,
        message_text: str,
        intent: str,
        evidence: list[RetrievedEvidence],
    ) -> str:
        if not evidence:
            return "已检索到相关资料，但当前仍需要结合官方审核继续核验。"

        top = evidence[0]
        if any(marker in (message_text or "") for marker in ("能不能", "是否", "可不可以", "可以")):
            faq_top = next((item for item in evidence if item.source_kind in {"faq", "category_faq"}), None)
            if faq_top is not None:
                top = faq_top
        summary = self.clean_quote_snippet(top.quote_snippet, limit=120)
        if intent in {"转学", "房产锁定/解锁", "平台操作", "材料清单"}:
            return f"根据{self.source_label(top)}，这个问题可以先这样理解：{summary}"
        if any(marker in (message_text or "") for marker in ("能不能", "是否", "可不可以", "属于哪一类", "算哪一类")):
            return f"按目前命中的资料，建议先按这条依据理解：{summary}"
        return f"根据当前命中的资料，这个问题有直接依据：{summary}"

    def compose_grounded_issue_note(
        self,
        *,
        intent: str,
        profile: StudentFacts,
        evidence: list[RetrievedEvidence],
    ) -> str:
        base = self.infer_eligibility_or_issue(
            intent=intent,
            profile=profile,
            has_complete_context=True,
        )
        if not evidence:
            return base
        return f"{base} 当前优先参考 {self.source_label(evidence[0])}。"

    def clean_quote_snippet(self, text: str, *, limit: int = 100) -> str:
        snippet = compact_snippet(text or "", limit=limit).strip()
        snippet = snippet.lstrip("：:；;，,。 ")
        if not snippet:
            return "当前命中的条文支持该判断。"
        if snippet[-1] not in "。！？":
            snippet = f"{snippet}。"
        return snippet

    def source_label(self, item: RetrievedEvidence) -> str:
        page = f"（{item.page}）" if item.page else ""
        return f"《{item.title}》{page}"

    def evidence_focus_score(self, *, message_text: str, item: RetrievedEvidence) -> float:
        clauses = self.answer_clauses(message_text)
        combined = " ".join(part for part in [item.title, item.file_name, item.quote_snippet, item.page or ""] if part)
        combined_norm = normalize_text(combined)
        combined_tokens = extract_tokens(combined)
        query_tokens = extract_tokens(message_text)
        clause_hits = sum(1 for clause in clauses if clause and clause in combined_norm)
        token_hits = len(query_tokens & combined_tokens)
        title_bonus = 0.6 if any(clause and clause in normalize_text(item.title) for clause in clauses) else 0.0
        official_bonus = 0.4 if item.source_tier <= 4 else 0.0
        special_bonus = sum(0.9 for term in self.special_policy_terms(message_text) if term and term in combined_norm)
        guide_bonus = 0.0
        if self.should_prioritize_application_guide(
            message_text=message_text,
            intent=self.rules.detect_intent(message_text),
        ) and self.is_application_guide_source(item.source_id):
            guide_bonus = 1.15 if item.page != "资料摘要" else 0.85
        return round(
            clause_hits * 1.6
            + token_hits * 0.03
            + title_bonus
            + official_bonus
            + special_bonus
            + guide_bonus
            + item.score * 0.08,
            4,
        )

    def order_answer_evidence(
        self,
        *,
        message_text: str,
        evidence: list[RetrievedEvidence],
    ) -> list[RetrievedEvidence]:
        return sorted(
            evidence,
            key=lambda item: (
                -self.evidence_focus_score(message_text=message_text, item=item),
                0 if item.source_tier <= 4 else 1,
                -item.score,
                item.title,
            ),
        )

    def infer_eligibility_or_issue(
        self,
        *,
        intent: str,
        profile: StudentFacts,
        has_complete_context: bool,
    ) -> str:
        if intent in {"类别判断", "报名资格判断", "幼儿园申请", "积分入学"}:
            if not has_complete_context:
                return "资料未补齐，暂不直接判定 A/B/C。"
            candidates: list[str] = []
            if profile.child_hukou and "松山湖" in profile.child_hukou:
                candidates.append("A类方向")
            if profile.parent_work_in_songshanhu:
                candidates.append("B类方向")
            if profile.dongguan_household is False and (
                profile.parent_work_in_songshanhu
                or profile.has_songshanhu_property
                or self.is_songshanhu_hukou(profile)
            ):
                candidates.append("C类积分入学方向")
            if not candidates:
                return "现有资料下仍无法直接判断可申报类别。"
            unique_candidates = list(dict.fromkeys(candidates))
            return f"结合目前资料，可优先核对 {' / '.join(unique_candidates)}。"
        if intent == "平台操作":
            return "当前问题属于平台操作说明，不涉及录取概率或名额承诺。"
        if intent == "转学":
            return "当前问题属于转学规则判断，最终仍以当年政策和平台审核为准。"
        if intent == "材料清单":
            return "当前可先整理常见基础材料，具体仍按对应类别和平台要求上传。"
        return "当前问题可先按检索到的政策依据做初步判断。"

    def recommend_materials(self, *, profile: StudentFacts, intent: str) -> list[str]:
        items: list[str] = []
        if intent in {"类别判断", "报名资格判断", "幼儿园申请", "积分入学", "材料清单", "转学"}:
            items.append("学童及监护人户籍证明或户口簿")
        if profile.parent_work_in_songshanhu or intent in {"类别判断", "报名资格判断", "积分入学"}:
            items.append("监护人工作证明、劳动合同、社保或个税材料")
        if profile.has_songshanhu_property:
            items.append("房产证或不动产权证明")
        if profile.is_transfer or intent == "转学":
            items.append("在读证明、学籍信息或原学校相关证明")
        if any("积分" in item for item in profile.special_status) or intent == "积分入学":
            items.append("居住证、社保、纳税等积分材料")
        if any("台湾" in item for item in profile.special_status):
            items.append("台湾学生申请表、通行证及就业/投资证明")
        if not items:
            items.append("按官方指南对应类别准备户籍、工作、房产、学籍等基础材料")
        return list(dict.fromkeys(items))

    def recommend_next_actions(self, *, intent: str, has_official_support: bool) -> list[str]:
        actions = ["根据当前引用先核对自己是否符合对应条件。"]
        if intent in {"平台操作", "材料清单"}:
            actions.append("按平台流程逐项填写并上传材料，提交前再核对一次。")
        else:
            actions.append("整理户籍、工作、房产、学段等关键信息后，再进行正式申报。")
        if not has_official_support:
            actions.append("当前缺少足够强的官方依据，建议联系人工复核。")
        else:
            actions.append("如遇平台实时状态、审核结果或年度变化，转人工核验。")
        return actions

    def to_citation(self, item: RetrievedEvidence) -> CitationRef:
        return CitationRef(
            source_id=item.source_id,
            title=item.title,
            page=item.page,
            chunk_id=item.chunk_id,
            quote_snippet=item.quote_snippet,
        )

    def knowledge_faq_conflict(self, message_text: str) -> bool:
        if self.is_simultaneous_b3_c_question(message_text) and not self.is_case_specific_simultaneous_b3_c_question(message_text):
            return False
        if self.is_special_policy_priority_query(message_text):
            return False
        faq_hits = self.knowledge.search_faq(message_text, top_k=2)
        return self.knowledge.faq_conflict(faq_hits)

    def is_songshanhu_hukou(self, profile: StudentFacts) -> bool:
        values = [profile.child_hukou, profile.parent_hukou]
        return any(value and "松山湖" in value for value in values)

    def is_latest_request(self, text: str) -> bool:
        return any(token in (text or "") for token in LATEST_PATTERNS)

    def extract_freeform_facts(self, text: str) -> StudentFacts:
        facts = StudentFacts()
        lowered = text or ""

        if any(token in lowered for token in ("不是转学", "非转学")):
            facts.is_transfer = False
        elif any(token in lowered for token in ("转学", "插班")):
            facts.is_transfer = True

        if "幼儿园" in lowered:
            facts.stage = "幼儿园"
        elif any(token in lowered for token in ("小学一年级", "小学1年级")):
            facts.stage = "小学一年级"
        elif "小学" in lowered:
            facts.stage = "小学"
        elif any(token in lowered for token in ("初中一年级", "初一")):
            facts.stage = "初中一年级"
        elif "初中" in lowered:
            facts.stage = "初中"

        if any(token in lowered for token in ("在松山湖工作", "在园区工作", "父母双方都在松山湖工作", "家长在松山湖工作")):
            facts.parent_work_in_songshanhu = True
        if any(token in lowered for token in ("不在松山湖工作", "不在园区工作")):
            facts.parent_work_in_songshanhu = False

        if any(token in lowered for token in ("没有房产", "没房产", "无房产")):
            facts.has_songshanhu_property = False
        elif any(token in lowered for token in ("松山湖有房产", "有松山湖房产", "在松山湖有房产", "有自有居所", "有房产")):
            facts.has_songshanhu_property = True

        if any(token in lowered for token in ("房产在爷爷名下", "房产在祖父母名下", "爷爷名下", "祖父母名下")):
            facts.property_owner = "祖辈"
        elif any(token in lowered for token in ("房产在父母名下", "父母名下")):
            facts.property_owner = "父母"

        if any(token in lowered for token in ("孩子是东莞其他镇街户籍", "学童户籍在东莞其他镇街")):
            facts.child_hukou = "东莞其他镇街"
            facts.dongguan_household = True
        elif any(token in lowered for token in ("孩子是东莞户籍", "学童是东莞户籍")):
            facts.child_hukou = "东莞"
            facts.dongguan_household = True
        elif any(token in lowered for token in ("孩子是非东莞户籍", "非东莞户籍", "户籍不在东莞")):
            facts.child_hukou = "非东莞"
            facts.dongguan_household = False
        elif any(token in lowered for token in ("孩子是松山湖户籍", "孩子户籍在松山湖", "学童户籍在松山湖")):
            facts.child_hukou = "松山湖"
            facts.dongguan_household = True
        elif "户籍不在松山湖" in lowered:
            facts.child_hukou = "非松山湖"

        if any(token in lowered for token in ("父母户籍在松山湖", "家长户籍在松山湖")):
            facts.parent_hukou = "松山湖"
        elif any(token in lowered for token in ("父母一方户籍在松山湖", "家长一方户籍在松山湖")):
            facts.parent_hukou = "父母一方松山湖户籍"
        elif any(token in lowered for token in ("父母户籍不在松山湖", "家长户籍不在松山湖")):
            facts.parent_hukou = "非松山湖"

        special_status: list[str] = []
        for token in ("积分", "优才卡", "企业指标", "台湾", "华侨", "荣誉市民"):
            if token in lowered:
                special_status.append(token)
        if special_status:
            facts.special_status = sorted(set(special_status))

        return facts
