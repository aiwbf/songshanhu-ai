from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import docx
import xlrd
from pypdf import PdfReader

from .catalog import SOURCE_SPECS, SourceSpec
from .models import ChunkRecord, SourceRecord, SourceType, StalenessFlag
from .text import chunk_text, collapse_spaces


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")

TAG_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("a1", "A1"),
    ("a2", "A2"),
    ("a3", "A3"),
    ("b1", "B1"),
    ("b2", "B2"),
    ("b3", "B3"),
    ("c类", "C类"),
    ("积分", "积分入学"),
    ("优才卡", "优才卡"),
    ("优粤卡", "优粤卡"),
    ("荣誉市民", "荣誉市民"),
    ("香港", "香港"),
    ("澳门", "澳门"),
    ("台湾", "台湾学生"),
    ("华侨", "华侨华人"),
    ("华人", "华侨华人"),
    ("锁定", "房产锁定"),
    ("解锁", "房产解锁"),
    ("单位账号", "单位账号"),
    ("管理员", "单位管理员"),
    ("审核", "审核"),
    ("修改资料", "报名资料修改"),
    ("报名资料", "报名资料修改"),
    ("转学", "转学"),
    ("幼儿园", "幼儿园"),
    ("小学", "小学"),
    ("初中", "初中"),
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _active_cycle_year(specs: tuple[SourceSpec, ...]) -> int | None:
    years = [
        spec.year
        for spec in specs
        if spec.year is not None
        and spec.source_type in {SourceType.ANNUAL_GUIDE, SourceType.OPERATION_GUIDE, SourceType.FAQ}
    ]
    return max(years) if years else None


def _priority_bucket(spec: SourceSpec, active_cycle_year: int | None) -> int:
    if active_cycle_year is not None and spec.year == active_cycle_year:
        if spec.source_type in {SourceType.ANNUAL_GUIDE, SourceType.OPERATION_GUIDE, SourceType.FAQ}:
            return 1
        if spec.source_id == "policy_dg_preferential_summary_2024":
            return 2
    if spec.source_type == SourceType.POLICY:
        return 3
    return 4


def _staleness_flag(spec: SourceSpec, today: date, active_cycle_year: int | None) -> StalenessFlag:
    expiry = _parse_date(spec.expiry_date)
    if expiry and expiry < today:
        return StalenessFlag.EXPIRED
    if spec.year is None:
        return StalenessFlag.UNKNOWN
    if active_cycle_year is not None and spec.year < active_cycle_year:
        return StalenessFlag.HISTORICAL
    return StalenessFlag.CURRENT


def _build_source_record(root: Path, spec: SourceSpec, today: date, active_cycle_year: int | None) -> SourceRecord:
    return SourceRecord(
        source_id=spec.source_id,
        title=spec.title,
        source_type=spec.source_type,
        year=spec.year,
        effective_date=spec.effective_date,
        expiry_date=spec.expiry_date,
        scope=spec.scope,
        authority_rank=spec.authority_rank,
        reliability_rank=spec.reliability_rank,
        staleness_flag=_staleness_flag(spec=spec, today=today, active_cycle_year=active_cycle_year),
        file_path=str((root / spec.relative_path).resolve()),
        priority_bucket=_priority_bucket(spec=spec, active_cycle_year=active_cycle_year),
    )


def _extract_tags(*values: str, extra_tags: tuple[str, ...] = ()) -> list[str]:
    tags = set(extra_tags)
    combined = " ".join(value for value in values if value)
    lowered = combined.lower()
    for needle, tag in TAG_KEYWORDS:
        if needle in lowered:
            tags.add(tag)
    return sorted(tags)


def _heading_from_page(source_title: str, text: str) -> str:
    raw_lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not raw_lines:
        return source_title
    for line in raw_lines[:4]:
        clean = collapse_spaces(line)
        if 4 <= len(clean) <= 60:
            return clean
    return source_title


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Unable to decode CSV file: {path}") from last_error


def _load_xls_rows(path: Path) -> list[dict[str, Any]]:
    workbook = xlrd.open_workbook(path)
    if workbook.nsheets == 0:
        return []
    sheet = workbook.sheet_by_index(0)
    if sheet.nrows == 0:
        return []
    headers = [collapse_spaces(str(sheet.cell_value(0, column))) for column in range(sheet.ncols)]
    rows: list[dict[str, Any]] = []
    for row_index in range(1, sheet.nrows):
        row_payload: dict[str, Any] = {}
        for column_index, header in enumerate(headers):
            cell = sheet.cell_value(row_index, column_index)
            if isinstance(cell, float) and cell.is_integer():
                cell = int(cell)
            row_payload[header] = cell
        rows.append(row_payload)
    return rows


def _build_business_faq_chunks(spec: SourceSpec, rows: list[dict[str, Any]]) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for index, row in enumerate(rows, start=1):
        question = collapse_spaces(str(row.get("常见问题") or ""))
        answer = collapse_spaces(str(row.get("标准答案") or ""))
        category = collapse_spaces(str(row.get("可报类别") or ""))
        if not question or not answer:
            continue
        chunk_id = f"{spec.source_id}-faq-{index:03d}"
        tags = _extract_tags(question, answer, category)
        if category:
            tags.append(category)
        chunks.append(
            ChunkRecord(
                chunk_id=chunk_id,
                source_id=spec.source_id,
                page=int(row.get("序号") or index),
                heading=question,
                text=f"问题：{question}\n答案：{answer}",
                tags=sorted(set(tags)),
            )
        )
    return chunks


def _build_docx_chunks(spec: SourceSpec, path: Path) -> list[ChunkRecord]:
    document = docx.Document(str(path))
    paragraphs = [collapse_spaces(paragraph.text) for paragraph in document.paragraphs if paragraph.text.strip()]
    text = "\n".join(paragraphs)
    chunks: list[ChunkRecord] = []
    for index, piece in enumerate(chunk_text(text, limit=500), start=1):
        chunks.append(
            ChunkRecord(
                chunk_id=f"{spec.source_id}-docx-{index:03d}",
                source_id=spec.source_id,
                page=index,
                heading=paragraphs[0] if paragraphs else spec.title,
                text=piece,
                tags=_extract_tags(spec.title, piece),
            )
        )
    return chunks


def _build_pdf_chunks(spec: SourceSpec, path: Path) -> list[ChunkRecord]:
    reader = PdfReader(str(path))
    chunks: list[ChunkRecord] = []
    chunk_index = 0
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        heading = _heading_from_page(spec.title, page_text)
        for piece in chunk_text(page_text):
            chunk_index += 1
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{spec.source_id}-pdf-{chunk_index:03d}",
                    source_id=spec.source_id,
                    page=page_number,
                    heading=heading,
                    text=collapse_spaces(piece),
                    tags=_extract_tags(spec.title, heading, piece, extra_tags=spec.seed_tags),
                )
            )
    if not chunks and spec.seed_text:
        chunks.append(
            ChunkRecord(
                chunk_id=f"{spec.source_id}-seed-001",
                source_id=spec.source_id,
                page=1,
                heading=spec.title,
                text=spec.seed_text,
                tags=_extract_tags(spec.title, spec.seed_text, extra_tags=spec.seed_tags),
            )
        )
    return chunks


def _import_chunks(spec: SourceSpec, path: Path) -> list[ChunkRecord]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _build_business_faq_chunks(spec=spec, rows=_load_csv_rows(path))
    if suffix == ".xls":
        return _build_business_faq_chunks(spec=spec, rows=_load_xls_rows(path))
    if suffix == ".docx":
        return _build_docx_chunks(spec=spec, path=path)
    if suffix == ".pdf":
        return _build_pdf_chunks(spec=spec, path=path)
    raise ValueError(f"Unsupported source type: {path}")


def import_sources(root: Path, output_path: Path, reference_date: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    output_path = output_path.resolve()
    today = date.fromisoformat(reference_date) if reference_date else date.today()
    active_cycle_year = _active_cycle_year(SOURCE_SPECS)

    source_records: list[SourceRecord] = []
    chunk_records: list[ChunkRecord] = []
    for spec in SOURCE_SPECS:
        path = root / spec.relative_path
        if not path.exists():
            raise FileNotFoundError(f"Missing required source file: {path}")
        source_records.append(_build_source_record(root=root, spec=spec, today=today, active_cycle_year=active_cycle_year))
        chunk_records.extend(_import_chunks(spec=spec, path=path))

    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "reference_date": today.isoformat(),
        "active_cycle_year": active_cycle_year,
        "sources": [record.to_dict() for record in source_records],
        "chunks": [record.to_dict() for record in chunk_records],
        "stats": {
            "source_count": len(source_records),
            "chunk_count": len(chunk_records),
            "business_faq_chunk_count": sum(1 for chunk in chunk_records if chunk.source_id.startswith("business_faq_")),
            "source_priority_summary": {
                "current_cycle_operational_sources": sum(1 for record in source_records if record.priority_bucket == 1),
                "current_cycle_preferential_summary_sources": sum(1 for record in source_records if record.priority_bucket == 2),
                "raw_policy_sources": sum(1 for record in source_records if record.priority_bucket == 3),
                "business_sources": sum(1 for record in source_records if record.priority_bucket == 4),
            },
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import admission sources into the structured knowledge bundle.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]), help="Workspace root")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[2] / "data" / "generated" / "knowledge_bundle.json"),
        help="Output JSON bundle path",
    )
    parser.add_argument("--reference-date", default=None, help="Reference date in YYYY-MM-DD")
    args = parser.parse_args()

    payload = import_sources(root=Path(args.root), output_path=Path(args.out), reference_date=args.reference_date)
    print(
        json.dumps(
            {
                "output_path": str(Path(args.out).resolve()),
                "source_count": payload["stats"]["source_count"],
                "chunk_count": payload["stats"]["chunk_count"],
                "business_faq_chunk_count": payload["stats"]["business_faq_chunk_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
