from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


WORD_RE = re.compile(r"[A-Za-z0-9_]+")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")
SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.lower().strip()
    return SPACE_RE.sub("", normalized)


def collapse_spaces(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return SPACE_RE.sub(" ", normalized).strip()


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
        for index in range(len(clean) - 1):
            tokens.add(clean[index : index + 2])
        for index in range(len(clean) - 2):
            tokens.add(clean[index : index + 3])
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


def compact_snippet(text: str, limit: int = 220) -> str:
    collapsed = collapse_spaces(text)
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def chunk_text(text: str, limit: int = 900) -> list[str]:
    cleaned = collapse_spaces((text or "").replace("\u3000", " ").replace("\xa0", " "))
    if not cleaned:
        return []
    chunks: list[str] = []
    current = ""
    sentences = re.split(r"(?<=[。；!?])", cleaned)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(sentence) <= limit:
            current = sentence
            continue
        start = 0
        while start < len(sentence):
            chunks.append(sentence[start : start + limit])
            start += limit
        current = ""
    if current:
        chunks.append(current)
    return chunks
