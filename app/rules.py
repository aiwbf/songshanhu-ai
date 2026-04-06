from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import StudentFacts
from app.utils import normalize_text


@dataclass(frozen=True)
class IntentRule:
    name: str
    keywords: tuple[str, ...]
    required_fields: tuple[str, ...]


class RuleEngine:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.knowledge_year = int(payload.get("knowledge_year", 2025))
        self.latest_patterns = tuple(payload.get("latest_patterns", []))
        self.handoff_patterns = tuple(payload.get("handoff_patterns", []))
        self.field_labels = payload.get("field_labels", {})
        self.intent_rules = [
            IntentRule(
                name=item["name"],
                keywords=tuple(item.get("keywords", [])),
                required_fields=tuple(item.get("required_fields", [])),
            )
            for item in payload.get("intents", [])
        ]
        self.official_contact = payload.get("official_contact", "建议联系官方渠道复核。")

    @classmethod
    def from_path(cls, path: Path) -> "RuleEngine":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def is_latest_request(self, question: str) -> bool:
        normalized = normalize_text(question)
        if any(normalize_text(pattern) in normalized for pattern in self.latest_patterns):
            return True
        latest_words = ("最新", "今年", "当前", "现在", "目前")
        policy_words = ("政策", "口径", "规定", "变化", "安排", "招生")
        has_latest_word = any(word in question for word in latest_words)
        has_policy_word = any(word in question for word in policy_words)
        return has_latest_word and has_policy_word

    def should_force_handoff(self, question: str) -> bool:
        return any(pattern in question for pattern in self.handoff_patterns)

    def detect_intent(self, question: str) -> str:
        normalized = normalize_text(question)
        if any(key in question for key in ("买房补贴", "购房补贴", "房补", "高考奖金", "大学奖励", "贷款")):
            return "超出范围"
        if any(key in question for key in ("企业名额", "管理员账号", "单位账号", "企业账号", "修改资料", "审核不通过")):
            return "平台操作"
        if any(key in question for key in ("提交报名申请后需要做什么", "报名申请后需要做什么", "如何申请企业账号")):
            return "平台操作"
        if "解锁" in question:
            return "房产锁定/解锁"
        if "锁定" in question and "房产" in question:
            return "房产锁定/解锁"
        if any(key in question for key in ("会公布排名吗", "按什么时间计算", "按什么政策口径理解", "根据排名安排学校")):
            return "政策依据查询"
        if any(key in question for key in ("如何申请", "怎样申请")) and any(
            key in question for key in ("台湾", "华侨", "华人", "香港", "澳门", "优才卡", "优粤卡")
        ):
            return "政策依据查询"
        if "积分" in question or "C类" in question:
            return "积分入学"
        scored: list[tuple[str, float]] = []
        for rule in self.intent_rules:
            score = 0.0
            for keyword in rule.keywords:
                keyword_norm = normalize_text(keyword)
                if keyword_norm and keyword_norm in normalized:
                    score += 1.0
            if score > 0:
                scored.append((rule.name, score))
        if not scored:
            return "政策依据查询" if any(key in question for key in ("依据", "来源", "根据什么")) else "报名资格判断"
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[0][0]

    def extract_facts(self, question: str) -> StudentFacts:
        facts = StudentFacts()
        text = question
        if "孩子与父母都有松山湖户籍" in text or "父母双方是松山湖户籍" in text:
            facts.child_hukou = "松山湖"
            facts.parent_hukou = "松山湖"
        if "不是转学" in text or "非转学" in text:
            facts.is_transfer = False
        elif "转学" in text or "插班" in text:
            facts.is_transfer = True
            facts.stage = facts.stage or "转学"
        if "幼儿园" in text:
            facts.stage = "幼儿园"
        elif "小学一年级" in text or "小学" in text:
            facts.stage = "小学"
        elif "初中一年级" in text or "初中" in text:
            facts.stage = "初中"

        if (
            "父母在松山湖工作" in text
            or "在园区工作" in text
            or "工作地在松山湖" in text
            or "工作单位在松山湖" in text
            or "服务地在松山湖" in text
            or "父母在松山湖机关和事业单位工作" in text
        ):
            facts.parent_work_in_songshanhu = True
        if "父母不在松山湖工作" in text or "不在园区工作" in text:
            facts.parent_work_in_songshanhu = False

        if "房产属于爷爷" in text or "爷爷名下" in text or "祖父母名下" in text:
            facts.has_songshanhu_property = True
        elif "园区没有房产" in text or "没有房产" in text or "无房产" in text:
            facts.has_songshanhu_property = False
        elif (
            "在园区有房产" in text
            or "有松山湖房产" in text
            or "有房产" in text
            or "拥有产权清晰的自有居所" in text
            or "在松山湖拥有产权清晰的自有居所" in text
        ):
            facts.has_songshanhu_property = True

        if "房产属于爷爷" in text or "跟爷爷" in text:
            facts.property_owner = "祖辈"
        elif "父母名下无房产" in text:
            facts.property_owner = "非父母"
        elif "父母在松山湖拥有产权清晰的自有居所" in text or "父母有房产" in text:
            facts.property_owner = "父母"

        if "全家户籍都不在松山湖" in text or "户籍不在松山湖" in text:
            facts.parent_hukou = "非松山湖"
        if "全家均无园区户籍" in text:
            facts.parent_hukou = "非松山湖"
        if "父母有一方户籍在松山湖" in text:
            facts.parent_hukou = "父母一方松山湖户籍"
        if "父母是松山湖家庭户籍" in text or "全家是松山湖家庭户籍" in text:
            facts.parent_hukou = "松山湖家庭户籍"

        if (
            "孩子户籍在松山湖" in text
            or "学童户籍在松山湖" in text
            or "孩子与父母都有松山湖户籍" in text
        ):
            facts.child_hukou = "松山湖"
        elif "孩子户籍不在松山湖" in text or "学童户籍不在松山湖" in text:
            facts.child_hukou = "非松山湖"
        elif "孩子是东莞其他镇街户籍" in text:
            facts.child_hukou = "东莞其他镇街"
            facts.dongguan_household = True
        elif "孩子是东莞户籍" in text:
            facts.child_hukou = "东莞"
            facts.dongguan_household = True
        elif "孩子是非东莞户籍" in text:
            facts.child_hukou = "非东莞"
            facts.dongguan_household = False
        elif "学童户籍在东莞市外" in text:
            facts.child_hukou = "东莞市外"
            facts.dongguan_household = False
        elif "学童户籍在东莞其他镇街" in text:
            facts.child_hukou = "东莞其他镇街"
            facts.dongguan_household = True
        elif "香港" in text:
            facts.child_hukou = "香港"
            facts.dongguan_household = False
        elif "澳门" in text:
            facts.child_hukou = "澳门"
            facts.dongguan_household = False
        elif "台湾" in text:
            facts.child_hukou = "台湾"
            facts.dongguan_household = False
        elif "华侨" in text or "华人" in text:
            facts.child_hukou = "华侨华人"
            facts.dongguan_household = False

        if "在松山湖居住" in text and facts.dongguan_household is None:
            facts.dongguan_household = False

        if "非东莞户籍" in text:
            facts.dongguan_household = False
        if "东莞户籍" in text and "非东莞户籍" not in text:
            facts.dongguan_household = True

        specials: list[str] = []
        for keyword in (
            "B2类人才",
            "B2类",
            "B2.2",
            "企业指标",
            "优才卡",
            "优粤卡",
            "优待政策",
            "积分入学",
            "积分",
            "企业名额",
            "机关和事业单位",
            "台湾",
            "华侨",
            "华人",
            "香港",
            "澳门",
        ):
            if keyword in text:
                specials.append(keyword)
        if specials:
            facts.special_status = sorted(set(specials))

        return facts

    def merge_facts(self, provided: StudentFacts, extracted: StudentFacts) -> StudentFacts:
        merged = provided.model_dump()
        inferred = extracted.model_dump()
        for key, value in inferred.items():
            if key == "special_status":
                merged[key] = sorted(set((merged.get(key) or []) + (value or [])))
                continue
            if merged.get(key) in (None, "", []):
                merged[key] = value
        return StudentFacts(**merged)

    def is_case_specific(self, question: str) -> bool:
        if any(
            pattern in question
            for pattern in (
                "如何申请",
                "怎样申请",
                "按什么时间计算",
                "按什么政策口径理解",
                "会公布排名吗",
                "如何对学位申请房进行解锁",
                "什么情况下房产会被锁定",
                "哪种类型所在的单位需注册单位账号",
                "提交报名申请后需要做什么工作",
                "企业如何查询B1类企业名额",
                "上传的资料有误",
            )
        ):
            return False
        patterns = (
            "我",
            "我们",
            "孩子",
            "父母",
            "全家",
            "属于哪类",
            "可以报吗",
            "能否申请",
            "这种情况",
        )
        return any(pattern in question for pattern in patterns)

    def missing_fields_for(self, intent_name: str, facts: StudentFacts) -> list[str]:
        intent = next((item for item in self.intent_rules if item.name == intent_name), None)
        if intent is None:
            return []
        payload = facts.model_dump()
        missing: list[str] = []
        for field_name in intent.required_fields:
            value = payload.get(field_name)
            if value is None or value == "" or value == []:
                missing.append(self.field_labels.get(field_name, field_name))
        return missing

    def minimal_questions_for(self, missing_fields: list[str]) -> list[str]:
        mapping = {
            "孩子户籍所在地": "孩子户籍在哪里？",
            "父母户籍所在地": "父母户籍在哪里？",
            "父母是否在松山湖工作": "父母是否在松山湖工作？",
            "是否有松山湖房产": "是否有松山湖房产？",
            "房产权属关系": "产权在谁名下？",
            "申请学段或年级": "申请的是幼儿园、小学一年级，还是转学？",
            "是否为转学": "这次是否属于转学？",
            "是否属于人才、优待、企业指标等特殊情形": "是否涉及人才、优待、企业指标或积分等特殊情形？",
        }
        return [mapping.get(item, item) for item in missing_fields]

    def next_step_for_handoff(self) -> str:
        return f"建议联系人工复核；可优先咨询 {self.official_contact}。"

    def risk_notice_base(self) -> list[str]:
        return [f"本回答仅依据 {self.knowledge_year} 年资料。"]


def find_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text
