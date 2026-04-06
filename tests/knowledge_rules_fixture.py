from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from packages.knowledge import KnowledgeStore, import_sources
from packages.rules.engine import RuleEngine


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = get_settings()
BUNDLE_PATH = SETTINGS.knowledge_bundle_path
REFERENCE_DATE = "2026-03-08"

_STORE: KnowledgeStore | None = None
_ENGINE: RuleEngine | None = None


def get_store() -> KnowledgeStore:
    global _STORE
    if _STORE is None:
        if not BUNDLE_PATH.exists():
            import_sources(root=ROOT, output_path=BUNDLE_PATH, reference_date=REFERENCE_DATE)
        _STORE = KnowledgeStore.from_bundle(BUNDLE_PATH)
    return _STORE


def get_engine() -> RuleEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RuleEngine(bundle_path=BUNDLE_PATH, knowledge_store=get_store())
    return _ENGINE
