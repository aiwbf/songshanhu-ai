from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import APP_NAME, APP_VERSION
from app.admin_session import (
    ADMIN_SESSION_COOKIE,
    admin_login_enabled,
    clear_admin_cookie,
    create_admin_token as build_admin_token,
    read_admin_token,
    require_admin_session,
    set_admin_cookie,
)
from app.models import (
    AskRequest,
    AskResponse,
    AdminLoginRequest,
    AdminSessionResponse,
    ChatRequest,
    ChatResponse,
    ConsultationOrchestratorRequest,
    ConsultationOrchestratorResponse,
    ConversationListResponse,
    ConversationStateResponse,
    FAQAliasListResponse,
    FAQAliasRecord,
    FAQAliasUpsertRequest,
    HealthResponse,
    IngestResponse,
    ManualTakeoverRequest,
    OpenClawMessageRequest,
    OpenClawMessageResponse,
    OperationsDashboardResponse,
    RepairItemCreateRequest,
    RepairItemListResponse,
    RepairItemRecord,
)
from app.runtime import Runtime


def create_admin_token(username: str, *, expires_at: int | None = None, last_seen_at: int | None = None) -> str:
    return build_admin_token(
        runtime.settings,
        username,
        expires_at=expires_at,
        last_seen_at=last_seen_at,
    )


def create_app(runtime_instance: Runtime | None = None) -> FastAPI:
    active_runtime = runtime_instance or Runtime()
    web_dir = active_runtime.web_dir

    app = FastAPI(title=APP_NAME, version=APP_VERSION)
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.middleware("http")
    async def force_utf8_json_charset(request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "charset=" not in content_type.lower():
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/admin", include_in_schema=False)
    def admin_index() -> FileResponse:
        return FileResponse(web_dir / "admin.html")

    @app.get("/admin/session", response_model=AdminSessionResponse)
    def admin_session(request: Request, response: Response) -> AdminSessionResponse:
        session = read_admin_token(active_runtime.settings, request.cookies.get(ADMIN_SESSION_COOKIE))
        username = str(session["username"]) if session else None
        if session:
            set_admin_cookie(
                response,
                active_runtime.settings,
                username,
                expires_at=int(session["expires_at"]),
            )
        else:
            clear_admin_cookie(response)
        return AdminSessionResponse(
            authenticated=bool(username),
            login_enabled=admin_login_enabled(active_runtime.settings),
            username=username,
        )

    @app.post("/admin/login", response_model=AdminSessionResponse)
    def admin_login(request: AdminLoginRequest, response: Response) -> AdminSessionResponse:
        if not admin_login_enabled(active_runtime.settings):
            raise HTTPException(status_code=503, detail="admin login is not configured")
        if (
            request.username != active_runtime.settings.admin_username
            or request.password != active_runtime.settings.admin_password
        ):
            raise HTTPException(status_code=401, detail="invalid admin credentials")

        set_admin_cookie(response, active_runtime.settings, request.username)
        return AdminSessionResponse(
            authenticated=True,
            login_enabled=True,
            username=request.username,
        )

    @app.post("/admin/logout", response_model=AdminSessionResponse)
    def admin_logout(response: Response) -> AdminSessionResponse:
        clear_admin_cookie(response)
        return AdminSessionResponse(
            authenticated=False,
            login_enabled=admin_login_enabled(active_runtime.settings),
            username=None,
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        stats = active_runtime.assistant.knowledge.stats() if active_runtime.assistant else {}
        return HealthResponse(
            ok=True,
            knowledge_loaded=bool(stats),
            knowledge_year=active_runtime.settings.knowledge_year,
            available_knowledge_years=list(active_runtime.settings.available_knowledge_years),
            llm_enabled=active_runtime.settings.llm_enabled,
            llm_provider=active_runtime.settings.llm_provider,
            openclaw_enabled=active_runtime.settings.openclaw_enabled,
            default_model=active_runtime.settings.default_model,
            official_contact=active_runtime.settings.official_contact,
        )

    @app.post("/ingest", response_model=IngestResponse)
    def ingest() -> IngestResponse:
        payload = active_runtime.ingest()["knowledge"]
        return IngestResponse(
            knowledge_path=str(active_runtime.settings.knowledge_path),
            knowledge_year=active_runtime.settings.knowledge_year,
            available_knowledge_years=list(payload.get("available_cycle_years", [])),
            faq_count=len(payload["faqs"]),
            document_chunk_count=len(payload["documents"]),
            source_count=len(payload["sources"]),
        )

    @app.post("/api/consultation/orchestrate", response_model=ConsultationOrchestratorResponse)
    def orchestrate(request: ConsultationOrchestratorRequest) -> ConsultationOrchestratorResponse:
        return active_runtime.assistant.orchestrate(request)

    @app.post("/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        answer = active_runtime.assistant.answer(request)
        active_runtime.operations.record_event(
            question=request.question,
            effective_question=request.question,
            answer=answer,
            conversation_id=request.conversation_id,
            channel=request.channel,
            entry_point=request.entry_point,
            is_openclaw=request.is_openclaw,
            source_session_id=request.source_session_id,
            source_target=request.source_target,
        )
        return answer

    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        return active_runtime.chat_service.chat(request)

    @app.get("/chat/{conversation_id}", response_model=ConversationStateResponse)
    def chat_state(conversation_id: str) -> ConversationStateResponse:
        snapshot = active_runtime.chat_service.snapshot(conversation_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return snapshot

    @app.get("/conversations", response_model=ConversationListResponse)
    def conversation_list() -> ConversationListResponse:
        return active_runtime.chat_service.summaries()

    @app.get("/ops/dashboard", response_model=OperationsDashboardResponse)
    def ops_dashboard() -> OperationsDashboardResponse:
        return active_runtime.operations.dashboard(conversations=active_runtime.store.list())

    @app.get("/admin-api/dashboard", response_model=OperationsDashboardResponse)
    def admin_dashboard(request: Request, response: Response) -> OperationsDashboardResponse:
        require_admin_session(active_runtime.settings, request, response)
        return active_runtime.operations.dashboard(conversations=active_runtime.store.list())

    @app.get("/ops/faq-aliases", response_model=FAQAliasListResponse)
    def faq_alias_list() -> FAQAliasListResponse:
        return active_runtime.operations.list_aliases()

    @app.get("/admin-api/faq-aliases", response_model=FAQAliasListResponse)
    def admin_faq_alias_list(request: Request, response: Response) -> FAQAliasListResponse:
        require_admin_session(active_runtime.settings, request, response)
        return active_runtime.operations.list_aliases()

    @app.post("/ops/faq-aliases", response_model=FAQAliasRecord)
    def faq_alias_upsert(request: FAQAliasUpsertRequest) -> FAQAliasRecord:
        return active_runtime.operations.upsert_alias(request)

    @app.post("/admin-api/faq-aliases", response_model=FAQAliasRecord)
    def admin_faq_alias_upsert(
        request: Request,
        response: Response,
        payload: FAQAliasUpsertRequest,
    ) -> FAQAliasRecord:
        require_admin_session(active_runtime.settings, request, response)
        return active_runtime.operations.upsert_alias(payload)

    @app.get("/ops/repair-items", response_model=RepairItemListResponse)
    def repair_item_list() -> RepairItemListResponse:
        return active_runtime.operations.list_repair_items()

    @app.get("/admin-api/repair-items", response_model=RepairItemListResponse)
    def admin_repair_item_list(request: Request, response: Response) -> RepairItemListResponse:
        require_admin_session(active_runtime.settings, request, response)
        return active_runtime.operations.list_repair_items()

    @app.post("/ops/repair-items", response_model=RepairItemRecord)
    def repair_item_create(request: RepairItemCreateRequest) -> RepairItemRecord:
        return active_runtime.operations.create_repair_item(request)

    @app.post("/admin-api/repair-items", response_model=RepairItemRecord)
    def admin_repair_item_create(
        request: Request,
        response: Response,
        payload: RepairItemCreateRequest,
    ) -> RepairItemRecord:
        require_admin_session(active_runtime.settings, request, response)
        return active_runtime.operations.create_repair_item(payload)

    @app.post("/ops/conversations/{conversation_id}/takeover", response_model=ConversationStateResponse)
    def conversation_takeover(
        conversation_id: str,
        request: ManualTakeoverRequest,
    ) -> ConversationStateResponse:
        snapshot = active_runtime.chat_service.mark_takeover(
            conversation_id,
            agent_name=request.agent_name,
            note=request.note,
            status=request.status,
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return snapshot

    @app.get("/admin-api/conversations", response_model=ConversationListResponse)
    def admin_conversation_list(request: Request, response: Response) -> ConversationListResponse:
        require_admin_session(active_runtime.settings, request, response)
        return active_runtime.chat_service.summaries()

    @app.get("/admin-api/conversations/{conversation_id}", response_model=ConversationStateResponse)
    def admin_conversation_state(
        request: Request,
        response: Response,
        conversation_id: str,
    ) -> ConversationStateResponse:
        require_admin_session(active_runtime.settings, request, response)
        snapshot = active_runtime.chat_service.snapshot(conversation_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return snapshot

    @app.post("/admin-api/conversations/{conversation_id}/takeover", response_model=ConversationStateResponse)
    def admin_conversation_takeover(
        request: Request,
        response: Response,
        conversation_id: str,
        payload: ManualTakeoverRequest,
    ) -> ConversationStateResponse:
        require_admin_session(active_runtime.settings, request, response)
        snapshot = active_runtime.chat_service.mark_takeover(
            conversation_id,
            agent_name=payload.agent_name,
            note=payload.note,
            status=payload.status,
        )
        if snapshot is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return snapshot

    @app.post("/openclaw/inbound", response_model=OpenClawMessageResponse)
    def openclaw_inbound(request: OpenClawMessageRequest) -> OpenClawMessageResponse:
        conversation_id = request.conversation_id
        if not conversation_id:
            if request.source_session_id:
                conversation_id = f"openclaw::{request.channel}::{request.target}::{request.source_session_id}"
            elif request.thread_id:
                conversation_id = f"openclaw::{request.channel}::{request.target}::thread::{request.thread_id}"
            elif request.sender_id:
                conversation_id = f"openclaw::{request.channel}::{request.target}::sender::{request.sender_id}"
            else:
                conversation_id = f"openclaw::{request.channel}::{request.target}::stateless"
        chat_response = active_runtime.chat_service.chat(
            ChatRequest(
                conversation_id=conversation_id,
                message=request.message,
                facts=request.facts,
                prefer_llm=request.prefer_llm,
                reset=request.reset,
                channel=request.channel,
                channel_mode=request.channel_mode,
                entry_point="openclaw_inbound",
                source_session_id=request.source_session_id or request.sender_id or request.target,
                source_target=request.target,
                is_openclaw=True,
            )
        )
        return active_runtime.openclaw_bridge.build_response(
            request=request,
            answer=chat_response.reply,
            conversation_id=chat_response.conversation_id,
        )

    return app


runtime = Runtime()
app = create_app(runtime)
