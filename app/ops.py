from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.models import (
    FAQAliasListResponse,
    FAQAliasRecord,
    FAQAliasUpsertRequest,
    OperationsDashboardResponse,
    RateMetric,
    RepairItemCreateRequest,
    RepairItemListResponse,
    RepairItemRecord,
    StaleDocumentAlert,
    TakeoverStatus,
    UnmatchedQuestionItem,
    ConversationSummary,
    HotQuestionItem,
)
from app.utils import normalize_text


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationsService:
    def __init__(self, path: Path, *, knowledge_year: int) -> None:
        self.path = path
        self.knowledge_year = knowledge_year
        self._lock = Lock()
        self._payload = self._load()

    def _default_payload(self) -> dict[str, list[dict[str, object]]]:
        return {
            "events": [],
            "faq_aliases": [],
            "repair_items": [],
        }

    def _load(self) -> dict[str, list[dict[str, object]]]:
        if not self.path.exists():
            return self._default_payload()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._default_payload()
        merged = self._default_payload()
        for key in merged:
            value = payload.get(key, [])
            merged[key] = value if isinstance(value, list) else []
        return merged

    def _persist_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_event(
        self,
        *,
        question: str,
        effective_question: str,
        answer,
        conversation_id: str | None,
        channel: str,
        entry_point: str,
        is_openclaw: bool,
        source_session_id: str | None = None,
        source_target: str | None = None,
    ) -> None:
        timestamp = utc_now_iso()
        stale_documents: list[dict[str, str]] = []
        current_year = datetime.now(timezone.utc).year
        if current_year > self.knowledge_year:
            for item in answer.evidence:
                file_name = item.file_name.lower()
                if file_name.endswith(".csv"):
                    continue
                stale_documents.append(
                    {
                        "file_name": item.file_name,
                        "source_id": item.source_id,
                    }
                )
        event = {
            "event_id": uuid4().hex,
            "timestamp": timestamp,
            "question": question,
            "effective_question": effective_question,
            "normalized_question": normalize_text(effective_question or question),
            "conversation_id": conversation_id,
            "channel": channel,
            "entry_point": entry_point,
            "is_openclaw": is_openclaw,
            "source_session_id": source_session_id,
            "source_target": source_target,
            "status": answer.status.value,
            "question_type": answer.question_type,
            "matched_faq_ids": list(answer.matched_faq_ids),
            "resolution_source": answer.resolution_source,
            "used_llm": answer.used_llm,
            "stale_documents": stale_documents,
        }
        with self._lock:
            self._payload["events"].append(event)
            self._persist_locked()

    def list_alias_payloads(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {
                    "alias": str(item.get("alias", "")),
                    "faq_id": str(item.get("faq_id", "")),
                    "faq_question": str(item.get("faq_question", "")),
                    "note": str(item.get("note", "")),
                }
                for item in self._payload["faq_aliases"]
            ]

    def list_aliases(self) -> FAQAliasListResponse:
        with self._lock:
            items = [FAQAliasRecord(**item) for item in self._payload["faq_aliases"]]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return FAQAliasListResponse(items=items)

    def upsert_alias(self, request: FAQAliasUpsertRequest) -> FAQAliasRecord:
        normalized_alias = normalize_text(request.alias)
        now = utc_now_iso()
        with self._lock:
            for item in self._payload["faq_aliases"]:
                if normalize_text(str(item.get("alias", ""))) == normalized_alias and item.get("faq_id") == request.faq_id:
                    item["faq_question"] = request.faq_question
                    item["note"] = request.note
                    item["updated_at"] = now
                    self._persist_locked()
                    return FAQAliasRecord(**item)
            record = FAQAliasRecord(
                alias_id=uuid4().hex,
                alias=request.alias,
                faq_id=request.faq_id,
                faq_question=request.faq_question,
                note=request.note,
                created_at=now,
                updated_at=now,
            )
            self._payload["faq_aliases"].append(record.model_dump())
            self._persist_locked()
        return record

    def list_repair_items(self) -> RepairItemListResponse:
        with self._lock:
            items = [RepairItemRecord(**item) for item in self._payload["repair_items"]]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return RepairItemListResponse(items=items)

    def create_repair_item(self, request: RepairItemCreateRequest) -> RepairItemRecord:
        now = utc_now_iso()
        record = RepairItemRecord(
            repair_id=uuid4().hex,
            conversation_id=request.conversation_id,
            kind=request.kind,
            title=request.title,
            problem=request.problem,
            proposed_fix=request.proposed_fix,
            manual_reply=request.manual_reply,
            source_channel=request.source_channel,
            status="open",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._payload["repair_items"].append(record.model_dump())
            self._persist_locked()
        if request.create_alias and request.alias_faq_id and request.alias_faq_question:
            self.upsert_alias(
                FAQAliasUpsertRequest(
                    alias=request.create_alias,
                    faq_id=request.alias_faq_id,
                    faq_question=request.alias_faq_question,
                    note=request.alias_note,
                )
            )
        return record

    def dashboard(self, *, conversations: list[object]) -> OperationsDashboardResponse:
        with self._lock:
            events = list(self._payload["events"])
            alias_items = [FAQAliasRecord(**item) for item in self._payload["faq_aliases"]]
            repair_items = [RepairItemRecord(**item) for item in self._payload["repair_items"]]

        total_events = len(events)
        faq_hits = sum(1 for event in events if event.get("matched_faq_ids"))
        rule_hits = sum(
            1
            for event in events
            if str(event.get("resolution_source", "")).startswith("rule_")
        )

        hot_buckets: dict[str, dict[str, object]] = {}
        unmatched_buckets: dict[str, dict[str, object]] = {}
        stale_buckets: dict[str, dict[str, object]] = {}
        for event in events:
            bucket_key = str(event.get("normalized_question") or "")
            if not bucket_key:
                continue
            hot = hot_buckets.setdefault(
                bucket_key,
                {
                    "question": event.get("effective_question") or event.get("question") or "",
                    "hits": 0,
                    "channels": set(),
                    "statuses": set(),
                    "last_seen_at": "",
                },
            )
            hot["hits"] = int(hot["hits"]) + 1
            hot["channels"].add(str(event.get("channel") or "web"))
            hot["statuses"].add(str(event.get("status") or ""))
            hot["last_seen_at"] = max(str(hot["last_seen_at"]), str(event.get("timestamp") or ""))

            is_unmatched = (
                not event.get("matched_faq_ids")
                and str(event.get("status")) != "answered"
            )
            if is_unmatched:
                unmatched = unmatched_buckets.setdefault(
                    bucket_key,
                    {
                        "question": event.get("effective_question") or event.get("question") or "",
                        "hits": 0,
                        "last_seen_at": "",
                        "last_status": "",
                        "conversation_id": event.get("conversation_id"),
                        "channel": event.get("channel"),
                    },
                )
                unmatched["hits"] = int(unmatched["hits"]) + 1
                unmatched["last_seen_at"] = max(
                    str(unmatched["last_seen_at"]),
                    str(event.get("timestamp") or ""),
                )
                unmatched["last_status"] = str(event.get("status") or "")
                unmatched["conversation_id"] = event.get("conversation_id")
                unmatched["channel"] = event.get("channel")

            for stale in event.get("stale_documents", []):
                file_name = str(stale.get("file_name") or "")
                if not file_name:
                    continue
                record = stale_buckets.setdefault(
                    file_name,
                    {
                        "file_name": file_name,
                        "hits": 0,
                        "last_seen_at": "",
                        "source_ids": set(),
                    },
                )
                record["hits"] = int(record["hits"]) + 1
                record["last_seen_at"] = max(
                    str(record["last_seen_at"]),
                    str(event.get("timestamp") or ""),
                )
                source_id = str(stale.get("source_id") or "")
                if source_id:
                    record["source_ids"].add(source_id)

        question_heat = [
            HotQuestionItem(
                question=str(item["question"]),
                hits=int(item["hits"]),
                channels=sorted(item["channels"]),
                statuses=sorted(item["statuses"]),
                last_seen_at=str(item["last_seen_at"]),
            )
            for item in hot_buckets.values()
        ]
        question_heat.sort(key=lambda item: (-item.hits, item.question))

        unmatched_pool = [
            UnmatchedQuestionItem(
                question=str(item["question"]),
                hits=int(item["hits"]),
                last_seen_at=str(item["last_seen_at"]),
                last_status=str(item["last_status"]),
                conversation_id=item["conversation_id"],
                channel=item["channel"],
            )
            for item in unmatched_buckets.values()
        ]
        unmatched_pool.sort(key=lambda item: (-item.hits, item.question))

        stale_document_alerts = [
            StaleDocumentAlert(
                file_name=str(item["file_name"]),
                hits=int(item["hits"]),
                last_seen_at=str(item["last_seen_at"]),
                source_ids=sorted(item["source_ids"]),
            )
            for item in stale_buckets.values()
        ]
        stale_document_alerts.sort(key=lambda item: (-item.hits, item.file_name))

        openclaw_conversations = sum(1 for item in conversations if bool(getattr(item, "is_openclaw", False)))
        takeover_queue: list[ConversationSummary] = []
        for item in conversations:
            last_answer = getattr(item, "last_answer", None)
            manual_takeover = bool(getattr(item, "manual_takeover", False))
            takeover_status = getattr(item, "takeover_status", TakeoverStatus.BOT)
            needs_attention = manual_takeover or (
                bool(getattr(item, "is_openclaw", False))
                and last_answer is not None
                and last_answer.status.value in {"handoff", "need_info"}
            )
            if not needs_attention:
                continue
            preview = ""
            if last_answer is not None:
                preview = last_answer.customer_reply or last_answer.conclusion
            takeover_queue.append(
                ConversationSummary(
                    conversation_id=getattr(item, "conversation_id"),
                    title=getattr(item, "title", "新对话"),
                    updated_at=getattr(item, "updated_at", ""),
                    preview=preview[:120],
                    status=last_answer.status if last_answer is not None else None,
                    channel=getattr(item, "channel", "web"),
                    entry_point=getattr(item, "entry_point", "quick_qa"),
                    is_openclaw=bool(getattr(item, "is_openclaw", False)),
                    source_session_id=getattr(item, "source_session_id", None),
                    source_target=getattr(item, "source_target", None),
                    manual_takeover=manual_takeover,
                    takeover_status=takeover_status if isinstance(takeover_status, TakeoverStatus) else TakeoverStatus(str(takeover_status)),
                    takeover_by=getattr(item, "takeover_by", None),
                    last_resolution_source=getattr(item, "last_resolution_source", None),
                    last_question_type=getattr(item, "last_question_type", None),
                )
            )
        takeover_queue.sort(key=lambda item: item.updated_at, reverse=True)

        pending_takeovers = sum(
            1
            for item in takeover_queue
            if item.takeover_status in {TakeoverStatus.REQUESTED, TakeoverStatus.HUMAN}
            or item.manual_takeover
        )

        alias_items.sort(key=lambda item: item.updated_at, reverse=True)
        repair_items.sort(key=lambda item: item.updated_at, reverse=True)

        return OperationsDashboardResponse(
            total_events=total_events,
            total_conversations=len(conversations),
            openclaw_conversations=openclaw_conversations,
            pending_takeovers=pending_takeovers,
            faq_hit_rate=self._rate_metric("FAQ 命中率", faq_hits, total_events),
            rule_hit_rate=self._rate_metric("规则命中率", rule_hits, total_events),
            question_heat=question_heat[:10],
            unmatched_pool=unmatched_pool[:10],
            stale_document_alerts=stale_document_alerts[:10],
            takeover_queue=takeover_queue[:10],
            faq_aliases=alias_items[:20],
            repair_items=repair_items[:20],
        )

    def _rate_metric(self, label: str, numerator: int, denominator: int) -> RateMetric:
        ratio = 0.0 if denominator <= 0 else round((numerator / denominator) * 100, 2)
        return RateMetric(
            label=label,
            numerator=numerator,
            denominator=denominator,
            ratio=ratio,
        )
