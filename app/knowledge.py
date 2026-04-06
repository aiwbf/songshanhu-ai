from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from app.utils import compact_snippet, cosine_similarity, extract_tokens, normalize_text, similarity, token_overlap, vectorize_text


@dataclass(frozen=True)
class RankedHit:
    record: dict[str, Any]
    score: float


def _query_clauses(query: str) -> list[str]:
    clauses: list[str] = []
    for part in re.split(r"[，。！？；、,.!?\n\r\t ]+", query or ""):
        normalized = normalize_text(part)
        if len(normalized) >= 3:
            clauses.append(normalized)
    return clauses[:8]


def _faq_search_text(faq: dict[str, Any]) -> str:
    if faq.get("search_text"):
        return str(faq["search_text"])
    parts = [faq.get("question", ""), faq.get("answer", ""), faq.get("category", ""), faq.get("change_type", ""), faq.get("notes", "")]
    return "\n".join(str(part).strip() for part in parts if str(part).strip())


def _faq_snippet(faq: dict[str, Any], *, limit: int = 220) -> str:
    parts: list[str] = []
    if faq.get("category"):
        parts.append(f"可报类别：{faq['category']}")
    if faq.get("answer"):
        parts.append(str(faq["answer"]))
    if faq.get("notes"):
        parts.append(f"备注：{faq['notes']}")
    if faq.get("change_type"):
        parts.append(f"问题情况：{faq['change_type']}")
    return compact_snippet(" ".join(parts), limit=limit)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _query_markers(query: str) -> list[str]:
    markers = ["优才卡", "优粤卡", "华侨", "华人", "台湾", "香港", "澳门", "积分", "单位账号", "管理员审核", "房产锁定", "转学"]
    return [marker for marker in markers if marker in (query or "")]


class KnowledgeStore:
    def __init__(self, bundle: dict[str, Any]) -> None:
        self.bundle = bundle
        self.sources = bundle.get("sources", [])
        self.faqs = bundle.get("faqs", [])
        self.documents = bundle.get("documents", [])
        self.source_map = {source["source_id"]: source for source in self.sources}
        self.active_cycle_year = int(bundle.get("active_cycle_year") or 2025)
        self.available_cycle_years = [int(item) for item in bundle.get("available_cycle_years", [])]
        self.alias_records_provider = None

    @classmethod
    def from_path(cls, path: Path) -> "KnowledgeStore":
        if not path.exists():
            raise FileNotFoundError(f"Knowledge base not found: {path}")
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def source_for(self, source_id: str) -> dict[str, Any]:
        return self.source_map[source_id]

    def stats(self) -> dict[str, int | list[int]]:
        return {
            "faq_count": len(self.faqs),
            "document_chunk_count": len(self.documents),
            "source_count": len(self.sources),
            "active_cycle_year": self.active_cycle_year,
            "available_cycle_years": list(self.available_cycle_years),
        }

    def search_faq(self, query: str, top_k: int = 5, alias_records: list[dict[str, str]] | None = None) -> list[RankedHit]:
        query_norm = normalize_text(query)
        query_tokens = extract_tokens(query)
        query_vector = vectorize_text(query)
        clauses = _query_clauses(query)
        if alias_records is None and callable(self.alias_records_provider):
            alias_records = self.alias_records_provider()
        alias_map: dict[str, list[str]] = {}
        for item in alias_records or []:
            faq_id = item.get("faq_id", "")
            alias = item.get("alias", "")
            if faq_id and alias:
                alias_map.setdefault(faq_id, []).append(alias)

        ranked: list[RankedHit] = []
        for faq in self.faqs:
            question = str(faq.get("question") or "")
            answer = str(faq.get("answer") or "")
            search_text = _faq_search_text(faq)
            faq_norm = faq.get("normalized_question") or normalize_text(question)
            answer_norm = faq.get("normalized_answer") or normalize_text(answer)
            search_norm = faq.get("normalized_search_text") or normalize_text(search_text)
            faq_tokens = set(faq.get("tokens") or extract_tokens(question))
            search_tokens = set(faq.get("search_tokens") or extract_tokens(search_text))
            score = 0.0
            if query_norm == faq_norm:
                score += 1.5
            if query_norm and query_norm in search_norm:
                score += 0.85
            if query_norm and query_norm in answer_norm:
                score += 0.55
            for clause in clauses:
                if clause in search_norm:
                    score += 0.18
            score += token_overlap(query_tokens, faq_tokens) * 0.95
            score += token_overlap(query_tokens, search_tokens) * 1.25
            score += similarity(query, question) * 0.72
            score += similarity(query, search_text) * 0.35
            score += cosine_similarity(query_vector, faq.get("vector")) * 1.35
            for alias in alias_map.get(faq.get("faq_id", ""), []):
                alias_norm = normalize_text(alias)
                alias_tokens = extract_tokens(alias)
                if query_norm == alias_norm:
                    score += 1.2
                if query_norm and (query_norm in alias_norm or alias_norm in query_norm):
                    score += 0.45
                score += token_overlap(query_tokens, alias_tokens) * 0.6
                score += similarity(query, alias) * 0.5
            if score > 0.08:
                ranked.append(RankedHit(record=faq, score=round(score, 4)))
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def search_documents(self, query: str, top_k: int = 6) -> list[RankedHit]:
        query_norm = normalize_text(query)
        query_tokens = extract_tokens(query)
        query_vector = vectorize_text(query)
        clauses = _query_clauses(query)
        markers = _query_markers(query)
        ranked: list[RankedHit] = []
        for doc in self.documents:
            text = str(doc.get("text") or "")
            doc_norm = doc.get("normalized_text") or normalize_text(text)
            doc_tokens = set(doc.get("tokens") or extract_tokens(text))
            title = str(doc.get("title") or "")
            title_norm = normalize_text(title)
            title_tokens = extract_tokens(title)
            section_text = " ".join(_string_list(doc.get("section_titles")) + _string_list(doc.get("section_types")) + _string_list(doc.get("section_keywords")) + _string_list(doc.get("section_title")) + _string_list(doc.get("section_type")))
            rule_card_text = " ".join(_string_list(doc.get("rule_card_titles")) + _string_list(doc.get("rule_card_types")) + _string_list(doc.get("rule_card_terms")) + _string_list(doc.get("rule_card_title")) + _string_list(doc.get("rule_card_type")))
            source = self.source_for(doc["source_id"])
            source_title = str(source.get("title") or "")
            source_scope = str(source.get("scope") or "")
            source_tags = " ".join(_string_list(source.get("seed_tags")))
            score = 0.0
            if query_norm and query_norm in doc_norm:
                score += 0.9
            if query_norm and query_norm in title_norm:
                score += 0.75
            for clause in clauses:
                if clause in doc_norm:
                    score += 0.12
                if clause in normalize_text(section_text):
                    score += 0.22
                if clause in normalize_text(rule_card_text):
                    score += 0.28
                if clause in normalize_text(source_title):
                    score += 0.16
            score += token_overlap(query_tokens, doc_tokens) * 1.1
            score += token_overlap(query_tokens, title_tokens) * 0.6
            score += token_overlap(query_tokens, extract_tokens(section_text)) * 0.95
            score += token_overlap(query_tokens, extract_tokens(rule_card_text)) * 1.05
            score += token_overlap(query_tokens, extract_tokens(source_title)) * 0.52
            score += token_overlap(query_tokens, extract_tokens(source_scope)) * 0.42
            score += token_overlap(query_tokens, extract_tokens(source_tags)) * 0.4
            score += similarity(query, title) * 0.42
            score += similarity(query, section_text) * 0.5
            score += similarity(query, rule_card_text) * 0.62
            score += similarity(query, source_title) * 0.28
            score += cosine_similarity(query_vector, doc.get("vector")) * 1.45
            marker_text = " ".join([source_title, source_scope, source_tags, section_text, rule_card_text, text])
            marker_hits = sum(1 for marker in markers if marker and marker in marker_text)
            if marker_hits:
                score += marker_hits * 0.75
            elif markers and source.get("source_type") == "annual_guide":
                score -= 0.18
            tier_bonus = max(0, 7 - int(source.get("source_tier") or 6)) * 0.06
            score += tier_bonus
            if str(doc.get("citation") or "").startswith("章节摘要："):
                score += 0.15
            if str(doc.get("citation") or "").startswith("规则卡片："):
                score += 0.18
            if score > 0.08:
                ranked.append(RankedHit(record=doc, score=round(score, 4)))
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def faq_conflict(self, hits: list[RankedHit]) -> bool:
        if len(hits) < 2:
            return False
        first, second = hits[0], hits[1]
        if first.score < 0.95 or second.score < 0.9:
            return False
        if second.score < first.score * 0.75:
            return False
        first_answer = normalize_text(first.record.get("answer", ""))
        second_answer = normalize_text(second.record.get("answer", ""))
        return first_answer != second_answer

    def evidence_from_faq(self, hit: RankedHit) -> dict[str, Any]:
        faq = hit.record
        source = self.source_for(faq["source_id"])
        return {
            "source_id": faq["source_id"],
            "file_name": source["file_name"],
            "source_tier": source["source_tier"],
            "citation": f"FAQ 第 {faq['row_number']} 条",
            "snippet": _faq_snippet(faq),
            "score": round(hit.score, 4),
        }

    def evidence_from_document(self, hit: RankedHit) -> dict[str, Any]:
        doc = hit.record
        source = self.source_for(doc["source_id"])
        return {
            "source_id": doc["source_id"],
            "file_name": source["file_name"],
            "source_tier": source["source_tier"],
            "citation": doc["citation"],
            "snippet": compact_snippet(doc["text"], limit=520),
            "score": round(hit.score, 4),
        }
