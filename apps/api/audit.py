from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any


PHONE_RE = re.compile(r"1[3-9]\d{9}")
LONG_DIGIT_RE = re.compile(r"\b\d{8,}\b")


def redact_sensitive_text(text: str) -> str:
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", text or "")
    redacted = LONG_DIGIT_RE.sub("[REDACTED_NUMBER]", redacted)
    return redacted


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def append(self, payload: dict[str, Any]) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return str(self.path)
