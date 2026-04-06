from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.assistant import AdmissionsAssistant
from app.models import (
    AskRequest,
    AskResponse,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    ConversationListResponse,
    ConversationStateResponse,
    ConversationSummary,
    SessionContext,
    StudentFacts,
    TakeoverStatus,
)
from app.rules import RuleEngine


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def overlay_facts(base: StudentFacts, update: StudentFacts) -> StudentFacts:
    merged = base.model_dump()
    patch = update.model_dump()
    for key, value in patch.items():
        if key == "special_status":
            merged[key] = sorted(set((merged.get(key) or []) + (value or [])))
            continue
        if value is not None and value != "":
            merged[key] = value
    return StudentFacts(**merged)


@dataclass
class ConversationSession:
    conversation_id: str
    facts: StudentFacts = field(default_factory=StudentFacts)
    history: list[ChatTurn] = field(default_factory=list)
    root_question: str = ""
    last_answer: AskResponse | None = None
    follow_up_rounds: int = 0
    last_intent: str | None = None
    last_scope: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    title: str = "新对话"
    channel: str = "web"
    entry_point: str = "quick_qa"
    is_openclaw: bool = False
    source_session_id: str | None = None
    source_target: str | None = None
    manual_takeover: bool = False
    takeover_status: TakeoverStatus = TakeoverStatus.BOT
    takeover_by: str | None = None
    takeover_note: str = ""
    last_resolution_source: str | None = None
    last_question_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "facts": self.facts.model_dump(),
            "history": [item.model_dump(mode="json") for item in self.history],
            "root_question": self.root_question,
            "last_answer": self.last_answer.model_dump(mode="json") if self.last_answer is not None else None,
            "follow_up_rounds": self.follow_up_rounds,
            "last_intent": self.last_intent,
            "last_scope": self.last_scope,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
            "channel": self.channel,
            "entry_point": self.entry_point,
            "is_openclaw": self.is_openclaw,
            "source_session_id": self.source_session_id,
            "source_target": self.source_target,
            "manual_takeover": self.manual_takeover,
            "takeover_status": self.takeover_status.value,
            "takeover_by": self.takeover_by,
            "takeover_note": self.takeover_note,
            "last_resolution_source": self.last_resolution_source,
            "last_question_type": self.last_question_type,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ConversationSession":
        return cls(
            conversation_id=str(payload.get("conversation_id") or uuid4().hex),
            facts=StudentFacts.model_validate(payload.get("facts") or {}),
            history=[ChatTurn.model_validate(item) for item in payload.get("history", [])],
            root_question=str(payload.get("root_question") or ""),
            last_answer=AskResponse.model_validate(payload["last_answer"]) if payload.get("last_answer") else None,
            follow_up_rounds=int(payload.get("follow_up_rounds") or 0),
            last_intent=payload.get("last_intent"),
            last_scope=payload.get("last_scope"),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            title=str(payload.get("title") or "新对话"),
            channel=str(payload.get("channel") or "web"),
            entry_point=str(payload.get("entry_point") or "quick_qa"),
            is_openclaw=bool(payload.get("is_openclaw", False)),
            source_session_id=payload.get("source_session_id"),
            source_target=payload.get("source_target"),
            manual_takeover=bool(payload.get("manual_takeover", False)),
            takeover_status=TakeoverStatus(str(payload.get("takeover_status") or TakeoverStatus.BOT.value)),
            takeover_by=payload.get("takeover_by"),
            takeover_note=str(payload.get("takeover_note") or ""),
            last_resolution_source=payload.get("last_resolution_source"),
            last_question_type=payload.get("last_question_type"),
        )


class ConversationStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._items: dict[str, ConversationSession] = {}
        self._lock = Lock()
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        items = payload.get("items", [])
        if not isinstance(items, list):
            return
        with self._lock:
            for raw in items:
                session = ConversationSession.from_dict(raw)
                self._items[session.conversation_id] = session

    def _persist_locked(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self._items.values(), key=lambda item: item.updated_at, reverse=True)
        self.path.write_text(
            json.dumps({"items": [item.to_dict() for item in ordered]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(self, conversation_id: str | None = None) -> ConversationSession:
        session = ConversationSession(conversation_id=conversation_id or uuid4().hex)
        with self._lock:
            self._items[session.conversation_id] = session
            self._persist_locked()
        return session

    def get_or_create(self, conversation_id: str | None, *, reset: bool = False) -> ConversationSession:
        if not conversation_id:
            return self.create()
        with self._lock:
            if reset or conversation_id not in self._items:
                session = ConversationSession(conversation_id=conversation_id)
                self._items[conversation_id] = session
                self._persist_locked()
                return session
            return self._items[conversation_id]

    def get(self, conversation_id: str) -> ConversationSession | None:
        with self._lock:
            return self._items.get(conversation_id)

    def list(self) -> list[ConversationSession]:
        with self._lock:
            return sorted(self._items.values(), key=lambda item: item.updated_at, reverse=True)

    def save(self, session: ConversationSession) -> None:
        with self._lock:
            self._items[session.conversation_id] = session
            self._persist_locked()

    def mark_takeover(
        self,
        conversation_id: str,
        *,
        agent_name: str,
        note: str,
        status: TakeoverStatus,
    ) -> ConversationSession | None:
        with self._lock:
            session = self._items.get(conversation_id)
            if session is None:
                return None
            session.manual_takeover = status != TakeoverStatus.BOT
            session.takeover_status = status
            session.takeover_by = agent_name
            session.takeover_note = note
            session.updated_at = utc_now_iso()
            self._persist_locked()
            return session


class ChatService:
    CONTEXTUAL_PREFIXES = (
        "那",
        "那如果",
        "如果",
        "这种情况",
        "这种的话",
        "那么",
        "然后",
        "补充",
        "更正",
        "纠正",
        "修改",
        "重新",
        "不是",
    )
    QUESTION_MARKERS = ("？", "?", "什么", "如何", "怎么", "哪里", "吗", "是否", "能否", "可以", "属于", "申请", "政策", "依据", "流程")

    def __init__(self, assistant: AdmissionsAssistant, rules: RuleEngine, store: ConversationStore, operations=None) -> None:
        self.assistant = assistant
        self.rules = rules
        self.store = store
        self.operations = operations

    def chat(self, request: ChatRequest) -> ChatResponse:
        session = self.store.get_or_create(request.conversation_id, reset=request.reset)
        message = request.message.strip()
        self._apply_request_metadata(session=session, request=request)
        extracted_facts = self.assistant.orchestrator.extract_freeform_facts(message)

        session.facts = overlay_facts(session.facts, request.facts)
        session.facts = overlay_facts(session.facts, extracted_facts)

        effective_question = self._effective_question(session, message)
        facts_for_turn = session.facts if self._should_use_context(session, message) else overlay_facts(StudentFacts(), extracted_facts)

        answer = self.assistant.answer(
            AskRequest(
                question=effective_question,
                facts=facts_for_turn,
                session_context=SessionContext(
                    conversation_id=session.conversation_id,
                    remembered_profile=session.facts,
                    asked_missing_fields=session.last_answer.session_update.asked_missing_fields if session.last_answer and session.last_answer.session_update else [],
                    follow_up_rounds=session.follow_up_rounds,
                    last_intent=session.last_intent,
                    last_scope=session.last_scope,
                    last_escalation_reasons=(
                        session.last_answer.escalation_decision.reasons
                        if session.last_answer and session.last_answer.escalation_decision
                        else []
                    ),
                ),
                prefer_llm=request.prefer_llm,
                top_k=request.top_k,
                conversation_id=session.conversation_id,
                channel=session.channel,
                channel_mode=request.channel_mode,
                entry_point=session.entry_point,
                source_session_id=session.source_session_id,
                source_target=session.source_target,
                is_openclaw=session.is_openclaw,
            )
        )

        if answer.session_update is not None:
            session.facts = answer.session_update.retained_profile
            session.follow_up_rounds = answer.session_update.follow_up_rounds
            session.last_intent = answer.session_update.last_intent
            session.last_scope = answer.session_update.last_scope

        if self._is_new_root_question(session, message):
            session.root_question = message
            session.title = self._title_from_message(message)
        elif not session.root_question:
            session.root_question = effective_question

        session.history.append(ChatTurn(role="user", content=message, timestamp=utc_now_iso()))
        session.history.append(
            ChatTurn(
                role="assistant",
                content=answer.customer_reply or answer.conclusion,
                timestamp=utc_now_iso(),
                answer=answer,
            )
        )
        session.last_answer = answer
        session.updated_at = utc_now_iso()
        session.last_resolution_source = answer.resolution_source
        session.last_question_type = answer.question_type
        self.store.save(session)

        if self.operations is not None:
            self.operations.record_event(
                question=message,
                effective_question=effective_question,
                answer=answer,
                conversation_id=session.conversation_id,
                channel=session.channel,
                entry_point=session.entry_point,
                is_openclaw=session.is_openclaw,
                source_session_id=session.source_session_id,
                source_target=session.source_target,
            )

        return ChatResponse(
            conversation_id=session.conversation_id,
            reply=answer,
            history=list(session.history),
            remembered_facts=session.facts,
            effective_question=effective_question,
        )

    def snapshot(self, conversation_id: str) -> ConversationStateResponse | None:
        session = self.store.get(conversation_id)
        if session is None:
            return None
        return ConversationStateResponse(
            conversation_id=session.conversation_id,
            title=session.title,
            updated_at=session.updated_at,
            history=list(session.history),
            remembered_facts=session.facts,
            channel=session.channel,
            entry_point=session.entry_point,
            is_openclaw=session.is_openclaw,
            source_session_id=session.source_session_id,
            source_target=session.source_target,
            manual_takeover=session.manual_takeover,
            takeover_status=session.takeover_status,
            takeover_by=session.takeover_by,
            takeover_note=session.takeover_note,
            last_resolution_source=session.last_resolution_source,
            last_question_type=session.last_question_type,
        )

    def summaries(self) -> ConversationListResponse:
        items: list[ConversationSummary] = []
        for session in self.store.list():
            preview = ""
            if session.last_answer is not None:
                preview = session.last_answer.customer_reply or session.last_answer.conclusion
            elif session.history:
                preview = session.history[-1].content
            items.append(
                ConversationSummary(
                    conversation_id=session.conversation_id,
                    title=session.title or "新对话",
                    updated_at=session.updated_at,
                    preview=preview[:120],
                    status=session.last_answer.status if session.last_answer else None,
                    channel=session.channel,
                    entry_point=session.entry_point,
                    is_openclaw=session.is_openclaw,
                    source_session_id=session.source_session_id,
                    source_target=session.source_target,
                    manual_takeover=session.manual_takeover,
                    takeover_status=session.takeover_status,
                    takeover_by=session.takeover_by,
                    last_resolution_source=session.last_resolution_source,
                    last_question_type=session.last_question_type,
                )
            )
        return ConversationListResponse(items=items)

    def mark_takeover(
        self,
        conversation_id: str,
        *,
        agent_name: str,
        note: str,
        status: TakeoverStatus,
    ) -> ConversationStateResponse | None:
        session = self.store.mark_takeover(
            conversation_id,
            agent_name=agent_name,
            note=note,
            status=status,
        )
        if session is None:
            return None
        return self.snapshot(conversation_id)

    def _apply_request_metadata(self, *, session: ConversationSession, request: ChatRequest) -> None:
        session.channel = request.channel or session.channel or "web"
        session.entry_point = request.entry_point or session.entry_point or "quick_qa"
        session.is_openclaw = bool(session.is_openclaw or request.is_openclaw)
        if request.source_session_id:
            session.source_session_id = request.source_session_id
        if request.source_target:
            session.source_target = request.source_target

    def _effective_question(self, session: ConversationSession, message: str) -> str:
        if not session.root_question:
            return message
        if self._should_thread_with_context(session, message):
            return session.root_question
        return message

    def _should_use_context(self, session: ConversationSession, message: str) -> bool:
        if not session.root_question:
            return False
        if self._should_thread_with_context(session, message):
            return True
        return self.rules.is_case_specific(message)

    def _should_thread_with_context(self, session: ConversationSession, message: str) -> bool:
        if not session.root_question:
            return False
        stripped = message.strip()
        if session.last_answer and session.last_answer.status.value == "need_info":
            return True
        if any(stripped.startswith(prefix) for prefix in self.CONTEXTUAL_PREFIXES):
            return True
        return not self._looks_like_new_question(stripped)

    def _is_new_root_question(self, session: ConversationSession, message: str) -> bool:
        if not session.root_question:
            return True
        return not self._should_thread_with_context(session, message)

    def _looks_like_new_question(self, message: str) -> bool:
        return any(marker in message for marker in self.QUESTION_MARKERS)

    def _title_from_message(self, message: str) -> str:
        compact = " ".join(message.strip().split())
        return compact[:24] if compact else "新对话"
