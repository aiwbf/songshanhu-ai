from __future__ import annotations

from pathlib import Path

from packages.knowledge import KnowledgeStore, import_sources
from packages.knowledge.text import collapse_spaces, normalize_text

from .models import FIELD_LABELS, AnswerContext, CaseProfile, ClassificationResult
from .templates import build_materials_template, build_risk_template, build_steps_template


CATEGORY_PRIORITY = ["A1", "A2", "A3", "B1", "B2", "B3", "C"]
SPECIAL_CASES = {
    "房产锁定",
    "房产解锁",
    "单位账号注册与审核",
    "报名资料修改",
    "华侨华人",
    "台湾学生",
    "香港/澳门学童",
    "优才卡",
    "优粤卡",
    "荣誉市民",
}
DEFAULT_BUNDLE_PATH = Path(__file__).resolve().parents[2] / "data" / "generated" / "knowledge_bundle.json"
DEFAULT_REFERENCE_DATE = "2026-03-08"


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for item in items:
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def _normalize_stage(value: str | None) -> str | None:
    if not value:
        return None
    text = collapse_spaces(value)
    if _contains_any(text, ("幼儿园", "小班", "中班", "大班")):
        return "幼儿园"
    if _contains_any(text, ("初中一年级", "初一", "初中")):
        return "初中一年级"
    if _contains_any(text, ("小学一年级", "小一", "一年级")) and "初" not in text:
        return "小学一年级"
    if _contains_any(text, ("转学", "插班", "非起始年级", "二年级", "三年级", "四年级", "五年级", "六年级", "七年级", "八年级", "九年级")):
        return "非起始年级"
    return None


def _normalize_hukou(value: str | None) -> str | None:
    if not value:
        return None
    text = collapse_spaces(value)
    if _contains_any(text, ("非松山湖", "不在松山湖")):
        return "非松山湖"
    if "香港" in text:
        return "香港"
    if "澳门" in text:
        return "澳门"
    if "台湾" in text:
        return "台湾"
    if _contains_any(text, ("华侨", "华人")):
        return "华侨华人"
    if _contains_any(text, ("松山湖家庭户", "家庭户")):
        return "松山湖家庭户"
    if _contains_any(text, ("松山湖集体户", "礼宾路2号", "集体户")):
        return "松山湖集体户"
    if _contains_any(text, ("松山湖户籍", "户籍在松山湖", "户口在松山湖")):
        return "松山湖户籍"
    if _contains_any(text, ("东莞其他镇街", "东莞镇街", "东莞本地")):
        return "东莞其他镇街"
    if _contains_any(text, ("非东莞", "国内非东莞", "东莞市外")):
        return "非东莞"
    if _contains_any(text, ("松山湖",)):
        return "松山湖"
    return text


def _normalize_location(value: str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "松山湖" if value else "无"
    text = collapse_spaces(str(value))
    if _contains_any(text, ("松山湖", "园区")):
        if _contains_any(text, ("不在", "没有", "无", "非")) and "松山湖" in text:
            return "非松山湖"
        return "松山湖"
    if _contains_any(text, ("没有", "无房", "无")):
        return "无"
    return text


def _normalize_statuses(values: list[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        candidates = [piece for piece in values.replace("、", ",").replace("，", ",").split(",") if piece.strip()]
    else:
        candidates = [str(piece) for piece in values if piece]
    statuses: list[str] = []
    for item in candidates:
        text = collapse_spaces(item)
        if "优才卡" in text:
            statuses.append("优才卡")
        elif "优粤卡" in text:
            statuses.append("优粤卡")
        elif "荣誉市民" in text:
            statuses.append("荣誉市民")
        elif _contains_any(text, ("高端人才", "博士", "副高级", "职称", "机关事业单位", "在编在职", "优待政策", "人才")):
            statuses.append(text)
        elif _contains_any(text, ("台湾", "华侨", "华人")):
            statuses.append(text)
        else:
            statuses.append(text)
    return _unique(statuses)


def _has_songshanhu_link(profile: CaseProfile) -> bool:
    return any(
        value == "松山湖"
        for value in (profile.work_location, profile.property_location, profile.guardian_hukou)
    )


def _is_non_dongguan(child_hukou: str | None) -> bool:
    return child_hukou in {"非东莞", "香港", "澳门", "台湾", "华侨华人"}


def _has_preferential(profile: CaseProfile) -> bool:
    tags = set(profile.preferential_statuses)
    return bool(tags & {"优才卡", "优粤卡", "荣誉市民"}) or any(
        _contains_any(item, ("人才", "职称", "博士", "机关事业单位", "优待")) for item in tags
    )


class RuleEngine:
    def __init__(self, bundle_path: Path | None = None, knowledge_store: KnowledgeStore | None = None) -> None:
        self.bundle_path = bundle_path or DEFAULT_BUNDLE_PATH
        if knowledge_store is None:
            if not self.bundle_path.exists():
                import_sources(
                    root=self.bundle_path.parents[2],
                    output_path=self.bundle_path,
                    reference_date=DEFAULT_REFERENCE_DATE,
                )
            knowledge_store = KnowledgeStore.from_bundle(self.bundle_path)
        self.knowledge_store = knowledge_store

    def classify_case(self, profile: CaseProfile | dict[str, object] | None, question: str) -> ClassificationResult:
        provided_profile = profile if isinstance(profile, CaseProfile) else CaseProfile.from_dict(profile if isinstance(profile, dict) else {})
        extracted_profile = self._extract_from_question(question)
        merged = self._normalize_profile(provided_profile.merge(extracted_profile))
        intent = self._detect_intent(question)
        reason_chain: list[str] = [f"intent={intent}，基于问题关键词完成路由。"]
        warnings: list[str] = []

        explicit_codes = self._extract_explicit_case_mentions(question)
        special_codes = self._special_case_codes(merged, question, intent, reason_chain)
        category_codes, additional_questions = self._category_candidates(merged, question, reason_chain)
        if intent in {"materials", "steps"} and explicit_codes and not category_codes:
            category_codes = explicit_codes
            reason_chain.append("问题已显式指定类别，按该类别生成材料/步骤模板，但不等同于资格已经核验。")
        combined_codes = _unique(special_codes + category_codes)

        minimal_missing = self._minimal_follow_up_fields(intent=intent, profile=merged, explicit_codes=explicit_codes, category_codes=category_codes)
        additional_follow_up_fields = [FIELD_LABELS.get(field, field) for field in additional_questions]

        status = "classified"
        primary_case = self._select_primary_case(explicit_codes, special_codes, category_codes)
        if not combined_codes:
            primary_case = "UNRESOLVED"
            status = "need_follow_up"
            reason_chain.append("现有信息无法命中任何稳定规则，保持未落类。")
        elif minimal_missing:
            status = "need_follow_up"
            reason_chain.append("最少必要字段仍有缺失，先补信息再给最终结论。")
        elif additional_follow_up_fields and primary_case in {"B3", "C", "UNRESOLVED"}:
            status = "need_follow_up"
            reason_chain.append("B 类 / C 类仍需补充指标或优待信息才能稳定定类。")

        if self.knowledge_store.active_cycle_year and self.knowledge_store.active_cycle_year < 2026:
            warnings.append(
                f"当前知识库的最新招生年度为 {self.knowledge_store.active_cycle_year}，相对 {DEFAULT_REFERENCE_DATE} 已属于历史资料。"
            )

        return ClassificationResult(
            intent=intent,
            status=status,
            primary_case_code=primary_case,
            case_codes=combined_codes,
            candidate_case_codes=category_codes,
            minimal_follow_up_fields=minimal_missing,
            additional_follow_up_fields=_unique(additional_follow_up_fields),
            reason_chain=_unique(reason_chain),
            warnings=_unique(warnings),
            normalized_profile=merged.to_dict(),
        )

    def retrieve_evidence(self, question: str, profile: CaseProfile | dict[str, object] | None) -> dict[str, object]:
        result = self.classify_case(profile=profile, question=question)
        merged_profile = CaseProfile.from_dict(result.normalized_profile)
        evidence = self.knowledge_store.retrieve(
            question=question,
            profile_terms=merged_profile.profile_terms(),
            case_codes=result.case_codes or result.candidate_case_codes,
            intent=result.intent,
        )
        return evidence.to_dict()

    def build_answer_context(self, result: ClassificationResult | dict[str, object], evidence: dict[str, object]) -> AnswerContext:
        result_obj = result if isinstance(result, ClassificationResult) else ClassificationResult(**result)
        profile = CaseProfile.from_dict(result_obj.normalized_profile)
        evidence_warnings = list(evidence.get("warnings", []))
        source_priority_notes = [
            f"优先级顺序：{self.knowledge_store.active_cycle_year} 年指南/答疑/操作指引 > {self.knowledge_store.active_cycle_year} 年优待政策汇总表 > 原始政策文件 > 业务FAQ。",
            "业务 FAQ 仅用于补充解释，不能覆盖规则或原始政策结论。",
        ]
        context = AnswerContext(
            result=result_obj.to_dict(),
            evidence=evidence,
            source_priority_notes=source_priority_notes,
            materials_template=build_materials_template(result_obj, profile),
            steps_template=build_steps_template(result_obj, profile),
            risk_template=build_risk_template(result_obj, evidence_warnings, profile),
            warnings=_unique(result_obj.warnings + evidence_warnings),
        )
        return context

    def _detect_intent(self, question: str) -> str:
        text = collapse_spaces(question)
        if "解锁" in text:
            return "property_unlock"
        if "锁定" in text:
            return "property_lock"
        if _contains_any(text, ("修改资料", "资料有误", "上传的资料有误", "报名资料修改")):
            return "application_edit"
        if _contains_any(text, ("企业账号", "单位账号", "管理员", "单位审核", "开通账号")):
            return "unit_account"
        if _contains_any(text, ("报名申请后需要做什么", "提交报名申请后需要做什么")) and _contains_any(text, ("A2", "B类", "B1", "B2", "B3")):
            return "unit_account"
        if _contains_any(text, ("所需资料", "什么资料", "材料", "清单")):
            return "materials"
        if _contains_any(text, ("怎么报名", "流程", "步骤", "操作", "平台", "注册网址")):
            return "steps"
        return "case_classification"

    def _extract_from_question(self, question: str) -> CaseProfile:
        text = collapse_spaces(question)
        profile = CaseProfile()
        profile.stage = _normalize_stage(text)
        if _contains_any(text, ("转学", "插班", "非起始年级", "二年级", "三年级", "四年级", "五年级", "六年级", "七年级", "八年级", "九年级")):
            profile.is_transfer_or_non_starting = True
        elif _contains_any(text, ("小学一年级", "初中一年级", "小一", "初一", "幼儿园")):
            profile.is_transfer_or_non_starting = False

        if "台湾" in text:
            profile.child_hukou = "台湾"
            profile.preferential_statuses.append("台湾学生")
        elif "香港" in text:
            profile.child_hukou = "香港"
        elif "澳门" in text:
            profile.child_hukou = "澳门"
        elif _contains_any(text, ("华侨", "华人")):
            profile.child_hukou = "华侨华人"
            profile.preferential_statuses.append("华侨华人")
        elif _contains_any(text, ("东莞其他镇街", "东莞本地户籍", "东莞户籍")):
            profile.child_hukou = "东莞其他镇街"
        elif _contains_any(text, ("非东莞", "国内非东莞", "东莞市外")):
            profile.child_hukou = "非东莞"
        elif _contains_any(text, ("礼宾路2号", "集体户")):
            profile.child_hukou = "松山湖集体户"
            profile.hukou_type = "集体户"
        elif _contains_any(text, ("家庭户", "户籍在松山湖", "户口在松山湖")):
            profile.child_hukou = "松山湖家庭户" if "家庭户" in text else "松山湖户籍"
            if "家庭户" in text:
                profile.hukou_type = "家庭户"
        if _contains_any(text, ("户籍跟爷爷", "户籍跟奶奶", "户口跟爷爷", "户口跟奶奶")):
            profile.child_hukou = "松山湖家庭户"
            profile.hukou_type = "家庭户"

        if _contains_any(text, ("父母户籍不在松山湖", "监护人户籍不在松山湖", "全家户籍都不在松山湖")):
            profile.guardian_hukou = "非松山湖"
        elif _contains_any(text, ("父母双方是松山湖户籍", "父母有一方户籍在松山湖", "监护人户籍在松山湖")):
            profile.guardian_hukou = "松山湖"

        if _contains_any(text, ("不在松山湖工作", "不在园区工作", "目前无业")):
            profile.work_location = "非松山湖"
        elif _contains_any(text, ("在松山湖工作", "在园区工作", "工作地在松山湖", "服务地在松山湖")):
            profile.work_location = "松山湖"

        if _contains_any(text, ("在园区有房产", "在松山湖有房产", "有房产", "自有房产所在地在松山湖", "拥有产权清晰的自有居所")):
            profile.property_location = "松山湖"
        if _contains_any(text, ("没有房产", "无房", "园区没有房产", "父母名下无房")):
            profile.property_location = "无"

        if _contains_any(text, ("房产属于爷爷", "房产属于奶奶", "祖父母", "外祖父母")):
            profile.property_owner_relation = "祖辈"
            profile.property_location = "松山湖"
        elif _contains_any(text, ("父母名下", "家长名下")):
            profile.property_owner_relation = "父母"
        elif _contains_any(text, ("非直系亲属",)):
            profile.property_owner_relation = "非直系亲属"

        if _contains_any(text, ("已被锁定", "房子被锁定", "房产已被锁定")):
            profile.property_locked = True
        elif "解锁" in text:
            profile.property_locked = True

        if "管理员" in text:
            profile.is_unit_admin = True

        if _contains_any(text, ("入学指标", "企业有名额", "B1类名额", "获得入学指标")):
            profile.employer_has_b1_quota = True

        inferred_statuses = []
        if "优才卡" in text:
            inferred_statuses.append("优才卡")
        if "优粤卡" in text:
            inferred_statuses.append("优粤卡")
        if "荣誉市民" in text:
            inferred_statuses.append("荣誉市民")
        if _contains_any(text, ("高端人才", "博士", "副高级", "职称", "机关事业单位", "在编在职", "人才标准")):
            inferred_statuses.append("人才/优待对象")
        profile.preferential_statuses.extend(inferred_statuses)
        profile.preferential_statuses = _normalize_statuses(profile.preferential_statuses)
        return profile

    def _normalize_profile(self, profile: CaseProfile) -> CaseProfile:
        return CaseProfile(
            stage=_normalize_stage(profile.stage),
            child_hukou=_normalize_hukou(profile.child_hukou),
            guardian_hukou=_normalize_hukou(profile.guardian_hukou),
            work_location=_normalize_location(profile.work_location),
            property_location=_normalize_location(profile.property_location),
            preferential_statuses=_normalize_statuses(profile.preferential_statuses),
            is_unit_admin=profile.is_unit_admin,
            is_transfer_or_non_starting=profile.is_transfer_or_non_starting,
            employer_has_b1_quota=profile.employer_has_b1_quota,
            hukou_type=profile.hukou_type,
            property_owner_relation=profile.property_owner_relation,
            property_locked=profile.property_locked,
            facts=dict(profile.facts),
        )

    def _extract_explicit_case_mentions(self, question: str) -> list[str]:
        text = normalize_text(question).upper()
        mentions = []
        for code in CATEGORY_PRIORITY:
            if normalize_text(code) in text.lower():
                mentions.append(code)
        return mentions

    def _special_case_codes(
        self,
        profile: CaseProfile,
        question: str,
        intent: str,
        reason_chain: list[str],
    ) -> list[str]:
        codes: list[str] = []
        if intent == "property_unlock":
            codes.append("房产解锁")
            reason_chain.append("问题命中“解锁”操作关键词，优先走房产解锁规则。")
        elif intent == "property_lock":
            codes.append("房产锁定")
            reason_chain.append("问题命中“锁定”操作关键词，优先走房产锁定规则。")
        if intent == "unit_account":
            codes.append("单位账号注册与审核")
            reason_chain.append("问题涉及企业/单位账号或管理员审核，归入单位账号注册与审核。")
        if intent == "application_edit":
            codes.append("报名资料修改")
            reason_chain.append("问题涉及报名资料修正，归入报名资料修改规则。")
        if profile.child_hukou == "台湾" or "台湾学生" in profile.preferential_statuses:
            codes.append("台湾学生")
            reason_chain.append("学童命中台湾身份，触发台湾学生专项规则。")
        if profile.child_hukou == "华侨华人" or "华侨华人" in profile.preferential_statuses:
            codes.append("华侨华人")
            reason_chain.append("学童命中华侨/华人身份，触发华侨华人专项规则。")
        if profile.child_hukou in {"香港", "澳门"}:
            codes.append("香港/澳门学童")
            reason_chain.append("学童为香港/澳门户籍，触发港澳学童专项规则。")
        if "优才卡" in profile.preferential_statuses:
            codes.append("优才卡")
            reason_chain.append("问题或画像命中优才卡。")
        if "优粤卡" in profile.preferential_statuses:
            codes.append("优粤卡")
            reason_chain.append("问题或画像命中优粤卡。")
        if "荣誉市民" in profile.preferential_statuses:
            codes.append("荣誉市民")
            reason_chain.append("问题或画像命中荣誉市民。")
        return _unique(codes)

    def _category_candidates(self, profile: CaseProfile, question: str, reason_chain: list[str]) -> tuple[list[str], list[str]]:
        candidates: list[str] = []
        additional_questions: list[str] = []

        child_hukou = profile.child_hukou
        if child_hukou in {"松山湖家庭户", "松山湖户籍"}:
            if profile.hukou_type == "家庭户" or child_hukou == "松山湖家庭户":
                if profile.property_location == "松山湖":
                    if profile.property_owner_relation == "非直系亲属":
                        candidates.append("A3")
                        reason_chain.append("学童为松山湖家庭户，但房产权属为非直系关系，按 A3 候选。")
                    else:
                        candidates.append("A1")
                        reason_chain.append("学童为松山湖家庭户且房产在松山湖，满足 A1 基本条件。")
                        if profile.property_owner_relation is None:
                            additional_questions.append("property_owner_relation")
                elif profile.property_location == "无":
                    candidates.append("A3")
                    reason_chain.append("学童为松山湖家庭户但无匹配房产信息，按 A3 候选。")
                else:
                    additional_questions.append("property_location")
            else:
                additional_questions.append("hukou_type")

        if child_hukou == "松山湖集体户":
            if profile.work_location == "松山湖":
                candidates.append("A2")
                reason_chain.append("学童为松山湖集体户且监护人在园区工作，满足 A2 基本条件。")
            elif profile.work_location == "非松山湖":
                candidates.append("A3")
                reason_chain.append("学童为松山湖集体户但当前无园区工作关系，转入 A3 候选。")
            else:
                additional_questions.append("work_location")

        if child_hukou in {"东莞其他镇街", "非东莞", "香港", "澳门"} and profile.work_location == "松山湖":
            if profile.employer_has_b1_quota and child_hukou in {"非东莞", "香港", "澳门"}:
                candidates.append("B1")
                reason_chain.append("学童为非本市/港澳户籍且单位具备 B1 指标，命中 B1。")
            if _has_preferential(profile):
                candidates.append("B2")
                reason_chain.append("监护人在园区工作且具有人才/优待身份，命中 B2。")
            if not _has_preferential(profile):
                candidates.append("B3")
                reason_chain.append("监护人在园区工作但未命中 B2 优待身份，保留 B3 候选。")
            if profile.employer_has_b1_quota is None and child_hukou in {"非东莞", "香港", "澳门"}:
                additional_questions.append("employer_has_b1_quota")
            if not profile.preferential_statuses:
                additional_questions.append("preferential_statuses")

        if child_hukou in {"非东莞", "香港", "澳门", "台湾"} and _has_songshanhu_link(profile):
            candidates.append("C")
            reason_chain.append("学童为非东莞/港澳台户籍且家庭与松山湖存在工作/居住/户籍/房产关联，命中 C 类候选。")

        if "优才卡" in profile.preferential_statuses or "优粤卡" in profile.preferential_statuses or "荣誉市民" in profile.preferential_statuses:
            if profile.work_location == "松山湖" or profile.property_location == "松山湖":
                candidates.append("B2")
                reason_chain.append("优才卡/优粤卡/荣誉市民在松山湖存在工作或房产链接，按 B2 处理。")
            else:
                additional_questions.append("work_location")
                additional_questions.append("property_location")

        if child_hukou == "台湾" and profile.work_location == "松山湖":
            candidates.append("B2")
            reason_chain.append("台湾学生在园区工作/投资情形按 B2 资料路径处理。")

        if child_hukou == "华侨华人":
            reason_chain.append("华侨华人子女需走市侨务局登记及教育部门统筹，不直接映射常规 A/B/C。")

        if not candidates and _contains_any(question, ("A1", "A2", "A3", "B1", "B2", "B3", "C类")):
            reason_chain.append("问题提到了类别代码，但画像字段不足以验证该类别是否成立。")

        ordered = [code for code in CATEGORY_PRIORITY if code in candidates]
        return _unique(ordered), _unique(additional_questions)

    def _minimal_follow_up_fields(
        self,
        intent: str,
        profile: CaseProfile,
        explicit_codes: list[str],
        category_codes: list[str],
    ) -> list[str]:
        if intent in {"property_lock", "property_unlock", "unit_account", "application_edit"}:
            return []

        if intent == "materials" and (explicit_codes or category_codes or profile.preferential_statuses):
            return []

        if len(category_codes) == 1:
            return []
        if explicit_codes and category_codes:
            return []
        if category_codes and set(category_codes) <= {"A1", "A2", "A3", "B2"}:
            return []

        required = ["stage", "child_hukou", "guardian_hukou", "work_location", "property_location"]
        if not explicit_codes:
            required.append("preferential_statuses")
        if intent in {"case_classification", "materials"}:
            required.append("is_transfer_or_non_starting")

        missing = []
        payload = profile.to_dict()
        for field in required:
            value = payload.get(field)
            if value in (None, "", [], {}):
                missing.append(FIELD_LABELS[field])
        return _unique(missing)

    def _select_primary_case(self, explicit_codes: list[str], special_codes: list[str], category_codes: list[str]) -> str:
        for code in explicit_codes:
            if code in category_codes:
                return code
        if special_codes:
            for code in special_codes:
                if code in {"房产解锁", "房产锁定", "单位账号注册与审核", "报名资料修改"}:
                    return code
        if special_codes and ("香港/澳门学童" in special_codes or "台湾学生" in special_codes or "华侨华人" in special_codes):
            if not category_codes or len(category_codes) > 1:
                for code in ("台湾学生", "华侨华人", "香港/澳门学童"):
                    if code in special_codes:
                        return code
        if category_codes:
            return category_codes[0]
        if special_codes:
            return special_codes[0]
        return "UNRESOLVED"


_DEFAULT_ENGINE: RuleEngine | None = None


def _engine() -> RuleEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = RuleEngine()
    return _DEFAULT_ENGINE


def classify_case(profile: CaseProfile | dict[str, object] | None, question: str) -> dict[str, object]:
    return _engine().classify_case(profile=profile, question=question).to_dict()


def retrieve_evidence(question: str, profile: CaseProfile | dict[str, object] | None) -> dict[str, object]:
    return _engine().retrieve_evidence(question=question, profile=profile)


def build_answer_context(result: ClassificationResult | dict[str, object], evidence: dict[str, object]) -> dict[str, object]:
    return _engine().build_answer_context(result=result, evidence=evidence).to_dict()
