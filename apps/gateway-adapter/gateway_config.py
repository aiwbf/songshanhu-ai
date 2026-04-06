from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import RouteMode


ENV_PATTERN = re.compile(r"\$\{(?P<name>[A-Z0-9_]+)(?::-(?P<default>[^}]*))?\}")
ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "openclaw.sample.json"


class AllowlistConfig(BaseModel):
    channels: list[str] = Field(default_factory=list)
    senders: list[str] = Field(default_factory=list)
    peers: list[str] = Field(default_factory=list)


class PairingConfig(BaseModel):
    required: bool = True
    trusted_senders: list[str] = Field(default_factory=list, alias="trustedSenders")
    metadata_key: str = Field(default="paired", alias="metadataKey")


class GroupConfig(BaseModel):
    require_mention: bool = Field(default=True, alias="requireMention")


class ChannelBindingConfig(BaseModel):
    route_mode: RouteMode = Field(default=RouteMode.PARENT_CONSULTATION, alias="routeMode")
    require_mention: Optional[bool] = Field(default=None, alias="requireMention")
    per_sender_session: Optional[bool] = Field(default=None, alias="perSenderSession")
    sender_roles: list[str] = Field(default_factory=list, alias="senderRoles")


class SecurityConfig(BaseModel):
    default_deny: bool = Field(default=True, alias="defaultDeny")
    header_name: str = Field(default="X-OpenClaw-Token", alias="headerName")
    shared_token: str = Field(default="", alias="sharedToken")
    allowlist: AllowlistConfig = Field(default_factory=AllowlistConfig)
    pairing: PairingConfig = Field(default_factory=PairingConfig)


class ServiceConfig(BaseModel):
    listen_host: str = Field(default="127.0.0.1", alias="listenHost")
    listen_port: int = Field(default=8010, alias="listenPort")
    orchestrator_base_url: str = Field(default="http://127.0.0.1:8000", alias="orchestratorBaseUrl")
    orchestrator_path: str = Field(default="/api/consultation/orchestrate", alias="orchestratorPath")
    timeout_ms: int = Field(default=6000, alias="timeoutMs")


class RoutingConfig(BaseModel):
    group: GroupConfig = Field(default_factory=GroupConfig)
    per_sender_session: bool = Field(default=True, alias="perSenderSession")
    fallback_agent: str = Field(default="fallback-human-handoff", alias="fallbackAgent")
    channel_bindings: dict[str, ChannelBindingConfig] = Field(default_factory=dict, alias="channelBindings")


class GatewaySettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    service: ServiceConfig = Field(default_factory=ServiceConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)

    def binding_for(self, binding_name: str, channel: str) -> ChannelBindingConfig:
        bindings = self.routing.channel_bindings
        if binding_name in bindings:
            return bindings[binding_name]
        if channel in bindings:
            return bindings[channel]
        if "default" in bindings:
            return bindings["default"]
        return ChannelBindingConfig()


def _resolve_env(value: object) -> object:
    if isinstance(value, dict):
        return {key: _resolve_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        default = match.group("default") or ""
        return os.getenv(name, default)

    return ENV_PATTERN.sub(replace, value)


def load_gateway_settings(config_path: str | Path | None = None) -> GatewaySettings:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return GatewaySettings()
    payload = json.loads(path.read_text(encoding="utf-8"))
    resolved = _resolve_env(payload)
    return GatewaySettings.model_validate(resolved)
