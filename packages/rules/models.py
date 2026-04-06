from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


FIELD_LABELS = {
    "stage": "学段",
    "child_hukou": "学童户籍",
    "guardian_hukou": "监护人户籍",
    "work_location": "工作地",
    "property_location": "房产所在地",
    "preferential_statuses": "是否属于人才/优待对象",
    "is_unit_admin": "是否为单位管理员",
    "is_transfer_or_non_starting": "是否为转学/非起始年级",
    "employer_has_b1_quota": "单位是否具备 B1 指标",
    "hukou_type": "户籍类型（家庭户/集体户）",
    "property_owner_relation": "房产权属关系",
    "property_locked": "房产是否已锁定",
}


@dataclass
class CaseProfile:
    stage: str | None = None
    child_hukou: str | None = None
    guardian_hukou: str | None = None
    work_location: str | None = None
    property_location: str | None = None
    preferential_statuses: list[str] = field(default_factory=list)
    is_unit_admin: bool | None = None
    is_transfer_or_non_starting: bool | None = None
    employer_has_b1_quota: bool | None = None
    hukou_type: str | None = None
    property_owner_relation: str | None = None
    property_locked: bool | None = None
    facts: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "CaseProfile":
        if not payload:
            return cls()
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def merge(self, other: "CaseProfile") -> "CaseProfile":
        current = self.to_dict()
        incoming = other.to_dict()
        for key, value in incoming.items():
            if key == "preferential_statuses":
                current[key] = sorted(set((current.get(key) or []) + (value or [])))
                continue
            if current.get(key) in (None, "", [], {}):
                current[key] = value
        return CaseProfile(**current)

    def profile_terms(self) -> list[str]:
        values: list[str] = []
        for key, value in self.to_dict().items():
            if key == "facts":
                continue
            if isinstance(value, list):
                values.extend(str(item) for item in value if item)
            elif isinstance(value, bool):
                values.append("是" if value else "否")
            elif value:
                values.append(str(value))
        return values


@dataclass
class ClassificationResult:
    intent: str
    status: str
    primary_case_code: str
    case_codes: list[str] = field(default_factory=list)
    candidate_case_codes: list[str] = field(default_factory=list)
    minimal_follow_up_fields: list[str] = field(default_factory=list)
    additional_follow_up_fields: list[str] = field(default_factory=list)
    reason_chain: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_profile: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerContext:
    result: dict[str, Any]
    evidence: dict[str, Any]
    source_priority_notes: list[str]
    materials_template: list[str]
    steps_template: list[str]
    risk_template: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
