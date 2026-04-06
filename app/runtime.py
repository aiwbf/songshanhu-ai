from __future__ import annotations

from pathlib import Path

from app.assistant import AdmissionsAssistant
from app.chat import ChatService, ConversationStore
from app.config import get_settings
from app.knowledge import KnowledgeStore
from app.llm_client import LLMSynthesizer
from app.openclaw_bridge import OpenClawBridge
from app.ops import OperationsService
from app.rules import RuleEngine
from packages.knowledge import import_sources, rebuild_markdown_knowledge_base
from scripts.build_knowledge import build_knowledge


DEFAULT_REFERENCE_DATE = "2026-03-08"


class Runtime:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.rules: RuleEngine | None = None
        self.system_prompt = ""
        self.assistant: AdmissionsAssistant | None = None
        self.store = ConversationStore(path=self.settings.conversation_store_path)
        self.operations = OperationsService(
            path=self.settings.operations_store_path,
            knowledge_year=self.settings.knowledge_year,
        )
        self.chat_service: ChatService | None = None
        self.openclaw_bridge = OpenClawBridge(self.settings)
        self.reload()

    @property
    def web_dir(self) -> Path:
        return self.settings.root_dir / "apps" / "web" / "src"

    def reload(
        self,
        *,
        rebuild_knowledge: bool = False,
        rebuild_bundle: bool = False,
    ) -> None:
        self.rules = RuleEngine.from_path(self.settings.rules_path)
        self.system_prompt = self.settings.system_prompt_path.read_text(encoding="utf-8")

        if rebuild_knowledge or not self.settings.knowledge_path.exists():
            build_knowledge(
                root=self.settings.root_dir,
                output_path=self.settings.knowledge_path,
            )
        if rebuild_bundle or not self.settings.knowledge_bundle_path.exists():
            import_sources(
                root=self.settings.root_dir,
                output_path=self.settings.knowledge_bundle_path,
                reference_date=DEFAULT_REFERENCE_DATE,
            )
        if self.settings.knowledge_bundle_path.exists():
            rebuild_markdown_knowledge_base(
                root=self.settings.root_dir,
                bundle_path=self.settings.knowledge_bundle_path,
                wiki_dir=self.settings.root_dir / "wiki",
            )

        knowledge = KnowledgeStore.from_path(self.settings.knowledge_path)
        knowledge.alias_records_provider = self.operations.list_alias_payloads

        synthesizer = None
        if self.settings.llm_enabled:
            synthesizer = LLMSynthesizer(
                settings=self.settings,
                system_prompt=self.system_prompt,
            )

        self.assistant = AdmissionsAssistant(
            settings=self.settings,
            rules=self.rules,
            knowledge=knowledge,
            synthesizer=synthesizer,
        )
        self.chat_service = ChatService(
            assistant=self.assistant,
            rules=self.rules,
            store=self.store,
            operations=self.operations,
        )

    def ingest(self) -> dict[str, object]:
        knowledge_payload = build_knowledge(
            root=self.settings.root_dir,
            output_path=self.settings.knowledge_path,
        )
        bundle_payload = import_sources(
            root=self.settings.root_dir,
            output_path=self.settings.knowledge_bundle_path,
            reference_date=DEFAULT_REFERENCE_DATE,
        )
        rebuild_markdown_knowledge_base(
            root=self.settings.root_dir,
            bundle_path=self.settings.knowledge_bundle_path,
            wiki_dir=self.settings.root_dir / "wiki",
        )
        self.reload()
        return {
            "knowledge": knowledge_payload,
            "bundle": bundle_payload,
        }
