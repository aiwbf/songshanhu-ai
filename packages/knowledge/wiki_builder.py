from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .store import KnowledgeStore


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-") or "unknown"


def _markdown_link(label: str, target: str) -> str:
    return f"[{label}]({target})"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _source_chunks(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in bundle.get("chunks", []):
        grouped[str(chunk["source_id"])].append(chunk)
    return grouped


def _chunk_tags(chunks: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for chunk in chunks:
        counter.update(str(tag) for tag in chunk.get("tags", []) if str(tag).strip())
    return [tag for tag, _ in counter.most_common(16)]


def _page_label(page: object) -> str:
    if page in (None, "", 0):
        return "未标注页码"
    return f"第 {page} 页"


def _chunk_outline(chunks: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for chunk in chunks[:8]:
        heading = str(chunk.get("heading") or "").strip() or "未命名片段"
        lines.append(f"- {heading}（{_page_label(chunk.get('page'))}）")
    return lines or ["- 暂无切片"]


def _relative_raw_path(root: Path, raw_path: str) -> str:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(root).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


def _source_page(*, root: Path, source, chunks: list[dict[str, Any]], today: str) -> str:
    tags = _chunk_tags(chunks)
    year_link = (
        _markdown_link(str(source.year), f"../years/{source.year}.md")
        if source.year is not None
        else "未知"
    )
    topic_links = [
        _markdown_link(tag, f"../topics/{_slugify(tag)}.md")
        for tag in tags[:8]
    ]
    return "\n".join(
        [
            f"# {source.title}",
            "",
            "## Summary",
            f"- `source_id`: `{source.source_id}`",
            f"- `source_type`: `{source.source_type.value}`",
            f"- `year`: `{source.year}`",
            f"- `staleness_flag`: `{source.staleness_flag.value}`",
            f"- `priority_bucket`: `{source.priority_bucket}`",
            "",
            "## Key facts",
            f"- 适用范围: {source.scope}",
            f"- 生效日期: {source.effective_date or '未知'}",
            f"- 失效日期: {source.expiry_date or '未知'}",
            f"- 权威等级: {source.authority_rank}",
            f"- 可靠性等级: {source.reliability_rank}",
            "",
            "## Detailed notes",
            f"- 切片数量: {len(chunks)}",
            f"- 高频标签: {'、'.join(tags) if tags else '无'}",
            "- 代表性片段:",
            *_chunk_outline(chunks),
            "",
            "## Relationships",
            f"- 年份页面: {year_link}",
            *[
                f"- 主题页面: {link}"
                for link in topic_links
            ],
            "",
            "## Sources",
            f"- 原始文件: `{_relative_raw_path(root, source.file_path)}`",
            "",
            "## Last updated",
            today,
        ]
    )


def _topic_page(
    *,
    topic: str,
    source_ids: list[str],
    source_lookup: dict[str, Any],
    chunks_by_source: dict[str, list[dict[str, Any]]],
    today: str,
) -> str:
    related_sources = [source_lookup[source_id] for source_id in source_ids]
    related_sources.sort(key=lambda item: (item.year or 0, -item.priority_bucket, item.title), reverse=True)

    representative_lines: list[str] = []
    for source in related_sources[:10]:
        chunks = chunks_by_source.get(source.source_id, [])
        sample = chunks[0] if chunks else {}
        heading = str(sample.get("heading") or source.title).strip() or source.title
        representative_lines.append(
            f"- `{source.source_id}` / {source.title} / {_page_label(sample.get('page'))} / {heading}"
        )

    covered_years = sorted({source.year for source in related_sources if source.year is not None})
    return "\n".join(
        [
            f"# {topic}",
            "",
            "## Summary",
            f"- 关联知识源数量: {len(related_sources)}",
            f"- 覆盖年份: {'、'.join(str(year) for year in covered_years) if covered_years else '未知'}",
            "",
            "## Key facts",
            *[
                f"- {_markdown_link(source.title, f'../sources/{source.source_id}.md')}"
                for source in related_sources[:12]
            ],
            "",
            "## Detailed notes",
            "- 代表性片段:",
            *(representative_lines or ["- 暂无片段"]),
            "",
            "## Relationships",
            *[
                f"- 年份页面: {_markdown_link(str(year), f'../years/{year}.md')}"
                for year in covered_years
            ],
            "",
            "## Sources",
            *[
                f"- `{source.source_id}`"
                for source in related_sources[:12]
            ],
            "",
            "## Last updated",
            today,
        ]
    )


def _year_page(*, year: int, sources: list[Any], today: str) -> str:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for source in sources:
        grouped[source.source_type.value].append(source)

    lines = [
        f"# {year}",
        "",
        "## Summary",
        f"- 知识源数量: {len(sources)}",
        "",
        "## Key facts",
    ]
    for source_type in sorted(grouped):
        lines.append(f"- `{source_type}`: {len(grouped[source_type])}")

    lines.extend(["", "## Detailed notes"])
    for source_type in sorted(grouped):
        lines.append(f"### {source_type}")
        for source in sorted(grouped[source_type], key=lambda item: (item.priority_bucket, item.title)):
            lines.append(f"- {_markdown_link(source.title, f'../sources/{source.source_id}.md')}")
        lines.append("")

    lines.extend(["## Last updated", today])
    return "\n".join(lines)


def _build_index(
    *,
    wiki_dir: Path,
    store: KnowledgeStore,
    topic_index: dict[str, set[str]],
    year_index: dict[int, list[Any]],
    today: str,
) -> str:
    year_links = [
        f"- {_markdown_link(str(year), f'years/{year}.md')}"
        for year in sorted(year_index)
    ]
    topic_links = [
        f"- {_markdown_link(topic, f'topics/{_slugify(topic)}.md')}"
        for topic in sorted(topic_index)
    ]
    source_links = [
        f"- {_markdown_link(source.title, f'sources/{source.source_id}.md')}"
        for source in sorted(
            store.sources,
            key=lambda item: (item.year or 0, -item.priority_bucket, item.title),
            reverse=True,
        )
    ]

    knowledge_rebuild_link = "knowledge-rebuild.md" if (wiki_dir / "knowledge-rebuild.md").exists() else "runtime-rewrite.md"
    return "\n".join(
        [
            "# 知识库索引",
            "",
            "## Summary",
            f"- 知识源总数: {len(store.sources)}",
            f"- 片段总数: {len(store.chunks)}",
            f"- 当前活跃招生年度: {store.active_cycle_year}",
            "",
            "## Key facts",
            "- 证据层保留原始 PDF / DOCX / CSV / XLS 等文件。",
            "- 结构化层保留 source / chunk / tag / year 关系，供程序回答时引用。",
            "- Markdown 层提供按来源、主题、年份浏览的人工可读索引。",
            "",
            "## Detailed notes",
            "- 年份入口:",
            *(year_links or ["- 暂无年份页面"]),
            "",
            "- 主题入口:",
            *(topic_links[:40] or ["- 暂无主题页面"]),
            "",
            "- 运行与维护:",
            f"- {_markdown_link('知识库重建说明', knowledge_rebuild_link)}",
            f"- {_markdown_link('运行时重写说明', 'runtime-rewrite.md')}",
            f"- {_markdown_link('工作日志', 'log.md')}",
            "",
            "## Sources",
            *source_links,
            "",
            "## Last updated",
            today,
        ]
    )


def _update_log(*, wiki_dir: Path, store: KnowledgeStore, stats: dict[str, int], today: str) -> None:
    log_path = wiki_dir / "log.md"
    header = "# 工作日志"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else header + "\n"
    existing_body = existing[len(header):].lstrip() if existing.startswith(header) else existing
    entry = "\n".join(
        [
            f"## {today} 重建 Markdown 知识库",
            "",
            f"- 活跃招生年度: `{store.active_cycle_year}`",
            f"- 来源页: `{stats['source_page_count']}`",
            f"- 主题页: `{stats['topic_page_count']}`",
            f"- 年份页: `{stats['year_page_count']}`",
            "- 已同步更新 `wiki/index.md`、`wiki/sources/`、`wiki/topics/`、`wiki/years/`。",
            "- 当前回答程序应优先引用结构化知识和官方来源，不把业务 FAQ 当成高优先级政策依据。",
            "",
        ]
    )
    if entry.strip() in existing_body:
        return
    _write(log_path, "\n".join([header, "", entry, existing_body.strip()]))


def rebuild_markdown_knowledge_base(
    *,
    root: Path,
    bundle_path: Path,
    wiki_dir: Path,
) -> dict[str, int]:
    root = root.resolve()
    bundle_path = bundle_path.resolve()
    wiki_dir = wiki_dir.resolve()

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    store = KnowledgeStore.from_bundle(bundle_path)
    chunks_by_source = _source_chunks(bundle)
    source_lookup = {source.source_id: source for source in store.sources}
    today = date.today().isoformat()

    sources_dir = wiki_dir / "sources"
    topics_dir = wiki_dir / "topics"
    years_dir = wiki_dir / "years"

    topic_index: dict[str, set[str]] = defaultdict(set)
    year_index: dict[int, list[Any]] = defaultdict(list)

    for source in store.sources:
        chunks = chunks_by_source.get(source.source_id, [])
        for tag in _chunk_tags(chunks):
            topic_index[tag].add(source.source_id)
        if source.year is not None:
            year_index[int(source.year)].append(source)
        _write(
            sources_dir / f"{source.source_id}.md",
            _source_page(root=root, source=source, chunks=chunks, today=today),
        )

    for topic, source_ids in sorted(topic_index.items(), key=lambda item: item[0]):
        _write(
            topics_dir / f"{_slugify(topic)}.md",
            _topic_page(
                topic=topic,
                source_ids=sorted(source_ids),
                source_lookup=source_lookup,
                chunks_by_source=chunks_by_source,
                today=today,
            ),
        )

    for year, year_sources in sorted(year_index.items()):
        _write(years_dir / f"{year}.md", _year_page(year=year, sources=year_sources, today=today))

    _write(
        wiki_dir / "index.md",
        _build_index(
            wiki_dir=wiki_dir,
            store=store,
            topic_index=topic_index,
            year_index=year_index,
            today=today,
        ),
    )

    stats = {
        "source_page_count": len(store.sources),
        "topic_page_count": len(topic_index),
        "year_page_count": len(year_index),
    }
    _update_log(wiki_dir=wiki_dir, store=store, stats=stats, today=today)
    return stats
