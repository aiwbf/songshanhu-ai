from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EvidenceHit, EvidenceResult, SourceRecord, SourceType, StalenessFlag
from .text import compact_snippet, extract_tokens, normalize_text, similarity, token_overlap


def _source_from_dict(payload: dict[str, Any]) -> SourceRecord:
    return SourceRecord(
        source_id=payload["source_id"],
        title=payload["title"],
        source_type=SourceType(payload["source_type"]),
        year=payload.get("year"),
        effective_date=payload.get("effective_date"),
        expiry_date=payload.get("expiry_date"),
        scope=payload["scope"],
        authority_rank=int(payload["authority_rank"]),
        reliability_rank=int(payload["reliability_rank"]),
        staleness_flag=StalenessFlag(payload["staleness_flag"]),
        file_path=payload["file_path"],
        priority_bucket=int(payload["priority_bucket"]),
    )


class KnowledgeStore:
    def __init__(self, bundle: dict[str, Any]) -> None:
        self.bundle = bundle
        self.reference_date = bundle.get("reference_date")
        self.active_cycle_year = bundle.get("active_cycle_year")
        self.sources = [_source_from_dict(item) for item in bundle.get("sources", [])]
        self.chunks = bundle.get("chunks", [])
        self.source_map = {source.source_id: source for source in self.sources}
        self._token_cache = {
            chunk["chunk_id"]: extract_tokens(f"{chunk['heading']} {chunk['text']} {' '.join(chunk.get('tags', []))}")
            for chunk in self.chunks
        }

    @classmethod
    def from_bundle(cls, path: Path) -> "KnowledgeStore":
        bundle = json.loads(path.read_text(encoding="utf-8"))
        return cls(bundle)

    def stats(self) -> dict[str, Any]:
        return dict(self.bundle.get("stats", {}))

    def retrieve(
        self,
        question: str,
        profile_terms: list[str] | None = None,
        case_codes: list[str] | None = None,
        intent: str | None = None,
        top_k: int = 8,
    ) -> EvidenceResult:
        profile_terms = profile_terms or []
        case_codes = case_codes or []
        query_parts = [question, " ".join(profile_terms), " ".join(case_codes), intent or ""]
        query_text = " ".join(part for part in query_parts if part)
        query_norm = normalize_text(query_text)
        query_tokens = extract_tokens(query_text)
        case_tokens = set(case_codes) | set(profile_terms)

        ranked: list[EvidenceHit] = []
        for chunk in self.chunks:
            source = self.source_map[chunk["source_id"]]
            chunk_tokens = self._token_cache[chunk["chunk_id"]]
            chunk_tags = set(chunk.get("tags", []))
            score = 0.0
            reasons: list[str] = []
            if query_norm and query_norm in normalize_text(chunk["text"]):
                score += 1.2
                reasons.append("query-substring")
            overlap = token_overlap(query_tokens, chunk_tokens)
            if overlap:
                score += overlap * 2.1
                reasons.append("token-overlap")
            heading_similarity = similarity(question, chunk["heading"])
            if heading_similarity:
                score += heading_similarity * 0.9
            text_similarity = similarity(question, chunk["text"])
            if text_similarity:
                score += text_similarity * 0.2
            if case_tokens and chunk_tags:
                tag_match = len(case_tokens & chunk_tags)
                if tag_match:
                    score += min(1.0, tag_match * 0.35)
                    reasons.append("case-tag-match")
            priority_weight = {1: 0.8, 2: 0.55, 3: 0.3, 4: 0.05}[source.priority_bucket]
            score += priority_weight
            if source.source_type == SourceType.BUSINESS_FAQ:
                score -= 0.2
            if intent and intent in chunk_tags:
                score += 0.2
            if score <= 0.28:
                continue
            citation_page = f"第 {chunk['page']} 项" if source.source_type == SourceType.BUSINESS_FAQ else f"第 {chunk['page']} 页"
            ranked.append(
                EvidenceHit(
                    source_id=source.source_id,
                    title=source.title,
                    source_type=source.source_type.value,
                    page=chunk.get("page"),
                    heading=chunk["heading"],
                    text=compact_snippet(chunk["text"], limit=320),
                    tags=list(chunk.get("tags", [])),
                    score=round(score, 4),
                    priority_bucket=source.priority_bucket,
                    authority_rank=source.authority_rank,
                    reliability_rank=source.reliability_rank,
                    staleness_flag=source.staleness_flag.value,
                    citation=f"{source.title} {citation_page}",
                    reasons=reasons,
                )
            )

        ranked.sort(key=lambda hit: (-hit.score, hit.priority_bucket, hit.authority_rank, hit.reliability_rank))
        deduped: list[EvidenceHit] = []
        seen = set()
        for hit in ranked:
            dedupe_key = (normalize_text(hit.heading), normalize_text(hit.text))
            if dedupe_key in seen:
                continue
            deduped.append(hit)
            seen.add(dedupe_key)
            if len(deduped) >= top_k:
                break

        warnings: list[str] = []
        high_risk_staleness = any(hit.staleness_flag == StalenessFlag.EXPIRED.value for hit in deduped)
        if high_risk_staleness:
            warnings.append("命中的 2024 年资料已过有效期，返回 high_risk_staleness。")

        has_current_operational = any(hit.priority_bucket == 1 for hit in deduped)
        has_old_policy = any(hit.priority_bucket >= 3 for hit in deduped)
        conflict_detected = False
        if has_current_operational and has_old_policy:
            conflict_detected = True
            warnings.append(
                f"当前年度资料与旧政策/业务FAQ并存，已优先采用 {self.active_cycle_year} 年度指南/答疑/操作口径。"
            )

        has_business = any(hit.source_type == SourceType.BUSINESS_FAQ.value for hit in deduped)
        if has_business:
            warnings.append("业务 FAQ 仅作为辅助解释层，不覆盖原始政策或当年官方口径。")

        official_case_tags = set()
        business_case_tags = set()
        tracked_tags = {"A1", "A2", "A3", "B1", "B2", "B3", "C类"}
        for hit in deduped:
            current = tracked_tags & set(hit.tags)
            if hit.source_type == SourceType.BUSINESS_FAQ.value:
                business_case_tags |= current
            else:
                official_case_tags |= current
        if official_case_tags and business_case_tags and business_case_tags - official_case_tags:
            conflict_detected = True
            warnings.append("业务 FAQ 与官方资料的类别标记存在偏差，已抑制 FAQ 结论覆盖。")

        return EvidenceResult(
            hits=deduped,
            warnings=warnings,
            high_risk_staleness=high_risk_staleness,
            conflict_detected=conflict_detected,
            active_cycle_year=self.active_cycle_year,
        )
