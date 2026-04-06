from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from gateway_config import GatewaySettings, load_gateway_settings
from gateway_models import GatewayInboundResponse, OpenClawStandardMessageEvent
from gateway_service import GatewayAccessDenied, GatewayService


def create_app(
    *,
    config_path: str | None = None,
    settings: GatewaySettings | None = None,
    orchestrator_client=None,
) -> FastAPI:
    resolved_settings = settings or load_gateway_settings(config_path or os.getenv("OPENCLAW_GATEWAY_CONFIG"))
    service = GatewayService(resolved_settings, orchestrator_client=orchestrator_client)

    app = FastAPI(title="openclaw-gateway-adapter", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "orchestrator_base_url": resolved_settings.service.orchestrator_base_url,
            "orchestrator_path": resolved_settings.service.orchestrator_path,
            "default_deny": resolved_settings.security.default_deny,
            "require_mention": resolved_settings.routing.group.require_mention,
            "per_sender_session": resolved_settings.routing.per_sender_session,
        }

    @app.post("/events/openclaw", response_model=GatewayInboundResponse)
    def openclaw_event(event: OpenClawStandardMessageEvent, request: Request) -> GatewayInboundResponse:
        shared_token = request.headers.get(resolved_settings.security.header_name)
        try:
            return service.handle_event(event=event, shared_token=shared_token)
        except GatewayAccessDenied as exc:
            raise HTTPException(status_code=403, detail={"code": exc.code, "message": exc.message}) from exc

    return app


app = create_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_gateway_settings(os.getenv("OPENCLAW_GATEWAY_CONFIG"))
    uvicorn.run(
        create_app(settings=settings),
        host=settings.service.listen_host,
        port=settings.service.listen_port,
    )
