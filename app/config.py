from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PROMPTS_DIR = ROOT_DIR / "prompts"
ENV_PATH = ROOT_DIR / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_local_base_url(base_url: str) -> bool:
    try:
        hostname = (urlparse(base_url).hostname or "").strip().lower()
    except ValueError:
        return False
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _resolve_llm_enabled(*, provider: str, base_url: str, api_key: str) -> bool:
    explicit = os.getenv("LLM_ENABLE")
    if explicit is not None:
        return _env_bool("LLM_ENABLE", default=False)
    if provider == "ollama" and _is_local_base_url(base_url):
        return True
    return bool(api_key.strip())


def _knowledge_path_for(year: int) -> Path:
    return DATA_DIR / "generated" / f"knowledge_base_{year}.json"


def _knowledge_bundle_path_for(year: int) -> Path:
    return DATA_DIR / "generated" / f"knowledge_bundle_{year}.json"


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    rules_path: Path
    system_prompt_path: Path
    repair_prompt_path: Path
    knowledge_path: Path
    knowledge_bundle_path: Path
    knowledge_manifest_path: Path
    latest_policy_fallback_path: Path
    openclaw_policy_path: Path
    audit_log_path: Path
    runtime_dir: Path
    conversation_store_path: Path
    operations_store_path: Path
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_enabled: bool
    default_model: str
    knowledge_year: int
    available_knowledge_years: tuple[int, ...]
    admin_username: str
    admin_password: str
    admin_session_secret: str
    admin_session_ttl_hours: int
    admin_session_idle_minutes: int
    openclaw_enabled: bool
    openclaw_command: str
    official_contact: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv(ENV_PATH)
    runtime_dir = DATA_DIR / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    llm_provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower() or "ollama"
    llm_base_url = (
        os.getenv("OLLAMA_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or "https://ollama.com/v1"
    ).strip().rstrip("/")
    llm_api_key = (
        os.getenv("OLLAMA_API_KEY")
        or os.getenv("LLM_API_KEY")
        or ""
    ).strip()
    default_model = (
        os.getenv("OLLAMA_MODEL")
        or os.getenv("LLM_MODEL")
        or "minimax-m2.5:cloud"
    ).strip() or "minimax-m2.5:cloud"
    llm_enabled = _resolve_llm_enabled(
        provider=llm_provider,
        base_url=llm_base_url,
        api_key=llm_api_key,
    )
    admin_username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    admin_session_secret = (
        os.getenv("ADMIN_SESSION_SECRET", "").strip()
        or os.getenv("OPENCLAW_SHARED_TOKEN", "").strip()
        or admin_password
    )

    available_knowledge_years = (2024, 2025)
    active_knowledge_year = int(
        os.getenv("ACTIVE_KNOWLEDGE_YEAR")
        or os.getenv("KNOWLEDGE_YEAR")
        or "2025"
    )
    if active_knowledge_year not in available_knowledge_years:
        active_knowledge_year = max(available_knowledge_years)

    return Settings(
        root_dir=ROOT_DIR,
        rules_path=DATA_DIR / "seed" / "rules.json",
        system_prompt_path=PROMPTS_DIR / "runtime-system-prompt.md",
        repair_prompt_path=PROMPTS_DIR / "runtime-repair-prompt.md",
        knowledge_path=_knowledge_path_for(active_knowledge_year),
        knowledge_bundle_path=_knowledge_bundle_path_for(active_knowledge_year),
        knowledge_manifest_path=DATA_DIR / "generated" / "knowledge_manifest.json",
        latest_policy_fallback_path=DATA_DIR / "seed" / "latest_policy_fallback.json",
        openclaw_policy_path=DATA_DIR / "seed" / "openclaw_policy.json",
        audit_log_path=DATA_DIR / "generated" / "audit" / "consultation_orchestrator.jsonl",
        runtime_dir=runtime_dir,
        conversation_store_path=runtime_dir / "conversations.json",
        operations_store_path=runtime_dir / "operations.json",
        llm_provider=llm_provider,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_enabled=llm_enabled,
        default_model=default_model,
        knowledge_year=active_knowledge_year,
        available_knowledge_years=available_knowledge_years,
        admin_username=admin_username,
        admin_password=admin_password,
        admin_session_secret=admin_session_secret,
        admin_session_ttl_hours=int(os.getenv("ADMIN_SESSION_TTL_HOURS", "12").strip() or "12"),
        admin_session_idle_minutes=int(os.getenv("ADMIN_SESSION_IDLE_MINUTES", "60").strip() or "60"),
        openclaw_enabled=_env_bool("OPENCLAW_ENABLE_SEND", default=False),
        openclaw_command=os.getenv("OPENCLAW_COMMAND", "openclaw.cmd").strip() or "openclaw.cmd",
        official_contact=os.getenv("OFFICIAL_CONTACT", "松山湖招生服务热线：0769-38881212").strip()
        or "松山湖招生服务热线：0769-38881212",
    )
