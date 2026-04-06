from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    POLICY = "policy"
    ANNUAL_GUIDE = "annual_guide"
    OPERATION_GUIDE = "operation_guide"
    FAQ = "faq"
    BUSINESS_FAQ = "business_faq"


class StalenessFlag(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    source_type: SourceType
    year: int | None
    effective_date: str | None
    expiry_date: str | None
    scope: str
    authority_rank: int
    reliability_rank: int
    staleness_flag: StalenessFlag
    file_path: str
    priority_bucket: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_type"] = self.source_type.value
        payload["staleness_flag"] = self.staleness_flag.value
        return payload


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    source_id: str
    page: int | None
    heading: str
    text: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceHit:
    source_id: str
    title: str
    source_type: str
    page: int | None
    heading: str
    text: str
    tags: list[str]
    score: float
    priority_bucket: int
    authority_rank: int
    reliability_rank: int
    staleness_flag: str
    citation: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceResult:
    hits: list[EvidenceHit]
    warnings: list[str]
    high_risk_staleness: bool
    conflict_detected: bool
    active_cycle_year: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": [hit.to_dict() for hit in self.hits],
            "warnings": list(self.warnings),
            "high_risk_staleness": self.high_risk_staleness,
            "conflict_detected": self.conflict_detected,
            "active_cycle_year": self.active_cycle_year,
        }
