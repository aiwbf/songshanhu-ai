from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from difflib import SequenceMatcher


WORD_RE = re.compile(r"[A-Za-z0-9_]+")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")
DEFAULT_VECTOR_DIMENSIONS = 256


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def extract_tokens(value: str) -> set[str]:
    text = unicodedata.normalize("NFKC", value or "").lower()
    tokens: set[str] = set()
    for word in WORD_RE.findall(text):
        tokens.add(word)
    for block in CHINESE_RE.findall(text):
        clean = block.strip()
        if not clean:
            continue
        if len(clean) == 1:
            tokens.add(clean)
            continue
        for idx in range(len(clean) - 1):
            tokens.add(clean[idx : idx + 2])
        for idx in range(len(clean) - 2):
            tokens.add(clean[idx : idx + 3])
    return tokens


def token_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def compact_snippet(text: str, limit: int = 180) -> str:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


def _hashed_index(token: str, *, dimensions: int = DEFAULT_VECTOR_DIMENSIONS) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % dimensions


def vectorize_text(value: str, *, dimensions: int = DEFAULT_VECTOR_DIMENSIONS) -> dict[str, float]:
    weighted: dict[int, float] = {}
    normalized = normalize_text(value)
    for token in extract_tokens(value):
        index = _hashed_index(token, dimensions=dimensions)
        weighted[index] = weighted.get(index, 0.0) + 1.0
    for offset in range(max(0, len(normalized) - 3)):
        gram = normalized[offset : offset + 4]
        if not gram:
            continue
        index = _hashed_index(gram, dimensions=dimensions)
        weighted[index] = weighted.get(index, 0.0) + 0.35
    norm = math.sqrt(sum(value * value for value in weighted.values()))
    if norm <= 0:
        return {}
    return {str(key): round(value / norm, 6) for key, value in weighted.items()}


def cosine_similarity(left: dict[str, float] | None, right: dict[str, float] | None) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    score = 0.0
    for key, value in left.items():
        score += float(value) * float(right.get(key, 0.0))
    return round(score, 6)
