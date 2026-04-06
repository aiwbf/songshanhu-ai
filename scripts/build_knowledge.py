from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import docx
from pypdf import PdfReader
import xlrd

ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORT))

from app.config import get_settings
from app.utils import extract_tokens, normalize_text, vectorize_text
from packages.knowledge.catalog import SOURCE_SPECS


SUPPORTED_SOURCE_SUFFIXES = {".csv", ".docx", ".pdf", ".xls", ".xlsx"}
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")

GUIDE_SECTION_SPECS: tuple[dict[str, Any], ...] = (
    {"section_id": "guide_admission_targets", "section_type": "招生对象", "section_title": "招生对象", "page_ranges": [(1, 2)], "keywords": ["招生对象", "入学对象", "申请对象", "年龄", "起始年级"]},
    {"section_id": "guide_transfer_limits", "section_type": "转学限制", "section_title": "转学限制", "page_ranges": [(1, 2)], "keywords": ["转学限制", "转学", "插班", "同一学段"]},
    {"section_id": "guide_category_rules", "section_type": "分类条件", "section_title": "分类条件", "page_ranges": [(2, 8)], "keywords": ["分类条件", "A1", "A2", "A3", "B1", "B2", "B3", "C类", "积分入学"]},
    {"section_id": "guide_property_locking", "section_type": "房产锁定", "section_title": "房产锁定", "page_ranges": [(11, 15)], "keywords": ["房产锁定", "学位房", "第一家庭", "房产解锁"]},
    {"section_id": "guide_registration_process", "section_type": "报名流程", "section_title": "报名流程", "page_ranges": [(16, 18), (36, 40)], "keywords": ["报名流程", "单位账号", "单位审核", "志愿填报", "平台流程"]},
    {"section_id": "guide_materials", "section_type": "材料清单", "section_title": "材料清单", "page_ranges": [(16, 16), (20, 35), (41, 42)], "keywords": ["材料清单", "所需材料", "上传材料", "户口簿", "出生证"]},
)

GUIDE_RULE_CARD_SPECS: tuple[dict[str, Any], ...] = (
    {"card_id": "guide_rule_a1", "card_type": "分类条件", "card_title": "A1类家庭户籍学童", "section_id": "guide_category_rules", "page_ranges": [(2, 3)], "keywords": ["A1", "家庭户籍", "房产地址一致"]},
    {"card_id": "guide_rule_a2", "card_type": "分类条件", "card_title": "A2类集体户籍人员", "section_id": "guide_category_rules", "page_ranges": [(2, 3)], "keywords": ["A2", "集体户", "父母在园区工作"]},
    {"card_id": "guide_rule_a3", "card_type": "分类条件", "card_title": "A3类其他松山湖户籍学童", "section_id": "guide_category_rules", "page_ranges": [(3, 3)], "keywords": ["A3", "其他松山湖户籍学童"]},
    {"card_id": "guide_rule_b1", "card_type": "分类条件", "card_title": "B1类企业人才子女", "section_id": "guide_category_rules", "page_ranges": [(3, 4)], "keywords": ["B1", "企业人才子女", "企业指标"]},
    {"card_id": "guide_rule_b2", "card_type": "分类条件", "card_title": "B2类优待及人才人员", "section_id": "guide_category_rules", "page_ranges": [(4, 6)], "keywords": ["B2", "优待政策", "优才卡", "优粤卡", "人才"]},
    {"card_id": "guide_rule_b3", "card_type": "分类条件", "card_title": "B3类企业积分制人才", "section_id": "guide_category_rules", "page_ranges": [(6, 7)], "keywords": ["B3", "企业积分制人才", "积分排序"]},
    {"card_id": "guide_rule_c", "card_type": "分类条件", "card_title": "C类积分入学", "section_id": "guide_category_rules", "page_ranges": [(6, 7)], "keywords": ["C类", "积分入学", "非户籍适龄儿童少年"]},
    {"card_id": "guide_rule_single_choice", "card_type": "申报限制", "card_title": "多项条件仅可任选一项申报", "section_id": "guide_category_rules", "page_ranges": [(4, 4)], "keywords": ["仅可任选一项", "不可重复申报", "同时符合多个类别"]},
    {"card_id": "guide_rule_property_locking", "card_type": "房产锁定", "card_title": "学位房锁定规则", "section_id": "guide_property_locking", "page_ranges": [(11, 15)], "keywords": ["房产锁定", "学位房", "毕业后解锁"]},
    {"card_id": "guide_rule_first_family", "card_type": "房产锁定", "card_title": "第一家庭认定规则", "section_id": "guide_property_locking", "page_ranges": [(12, 15)], "keywords": ["第一家庭", "祖父母", "外祖父母", "同一房产地址"]},
    {"card_id": "guide_rule_unit_account", "card_type": "报名流程", "card_title": "单位账号申请与审核", "section_id": "guide_registration_process", "page_ranges": [(36, 37)], "keywords": ["单位账号", "账号申请", "单位审核", "A2", "B类", "注册账号"]},
    {"card_id": "guide_rule_platform_application", "card_type": "报名流程", "card_title": "平台报名与志愿填报流程", "section_id": "guide_registration_process", "page_ranges": [(38, 40)], "keywords": ["平台报名", "报名号", "志愿填报", "初审", "复审", "录取结果"]},
    {"card_id": "guide_rule_basic_materials", "card_type": "材料清单", "card_title": "基础报名材料", "section_id": "guide_materials", "page_ranges": [(41, 42)], "keywords": ["基础材料", "户口簿", "出生证", "在读证明"]},
)

SPECIAL_RULE_CARD_SPECS: dict[str, tuple[dict[str, Any], ...]] = {
    "policy_dg_taiwan_2019": ({"card_id": "policy_taiwan_application_path", "card_type": "台湾学生", "card_title": "台湾学生义务教育申请路径", "section_id": "policy_taiwan", "page_ranges": [], "keywords": ["台湾学生", "义务教育", "申请就读"]}, {"card_id": "policy_taiwan_materials", "card_type": "台湾学生", "card_title": "台湾学生申请材料", "section_id": "policy_taiwan", "page_ranges": [], "keywords": ["台湾学生", "申请材料", "通行证", "居住证"]}),
    "policy_dg_overseas_chinese_2017": ({"card_id": "policy_overseas_chinese_path", "card_type": "华侨华人", "card_title": "华侨华人子女及华侨学生申请路径", "section_id": "policy_overseas_chinese", "page_ranges": [], "keywords": ["华侨华人", "华侨学生", "申请就读"]},),
    "policy_dg_youcai_2020": ({"card_id": "policy_youcai_children_priority", "card_type": "优才卡", "card_title": "优才卡持卡人子女教育优待", "section_id": "policy_youcai", "page_ranges": [], "keywords": ["优才卡", "子女入学", "教育优待", "B2"]},),
    "policy_gd_youyue_2023": ({"card_id": "policy_youyue_children_priority", "card_type": "优粤卡", "card_title": "优粤卡持卡人子女教育待遇", "section_id": "policy_youyue", "page_ranges": [], "keywords": ["优粤卡", "子女入学", "教育待遇", "B2"]},),
    "policy_dg_points_2023": ({"card_id": "policy_points_admission_scope", "card_type": "积分入学", "card_title": "非户籍适龄儿童少年积分入学基本适用范围", "section_id": "policy_points", "page_ranges": [], "keywords": ["积分入学", "非户籍", "公办义务教育", "C类"]},),
    "ops_songshanhu_platform_2024": ({"card_id": "ops_platform_unit_admin_review", "card_type": "平台操作", "card_title": "单位账号注册与管理员审核", "section_id": "ops_platform_flow", "page_ranges": [], "keywords": ["单位账号", "管理员审核", "A2", "B类", "账号注册"]},),
    "policy_gd_youyue_2025": ({"card_id": "policy_youyue_children_priority_2025", "card_type": "优粤卡", "card_title": "优粤卡持卡人子女教育待遇", "section_id": "policy_youyue_2025", "page_ranges": [], "keywords": ["优粤卡", "子女入学", "教育待遇", "B2"]},),
    "policy_dg_guanai_talent_2025": ({"card_id": "policy_guanai_talent_children_priority_2025", "card_type": "莞爱人才", "card_title": "莞爱人才子女教育优待", "section_id": "policy_guanai_2025", "page_ranges": [], "keywords": ["莞爱人才", "子女教育", "人才服务", "B2"]},),
    "policy_dg_overseas_chinese_2025": ({"card_id": "policy_overseas_chinese_path_2025", "card_type": "华侨华人", "card_title": "华侨华人子女及华侨学生申请路径", "section_id": "policy_overseas_chinese_2025", "page_ranges": [], "keywords": ["华侨华人", "华侨学生", "申请就读"]},),
    "policy_dg_talent_children_2025": ({"card_id": "policy_talent_children_path_2025", "card_type": "企业人才", "card_title": "企业人才子女入学实施路径", "section_id": "policy_talent_children_2025", "page_ranges": [], "keywords": ["企业人才子女", "B1", "B2"]},),
    "policy_dg_points_2025": ({"card_id": "policy_points_admission_scope_2025", "card_type": "积分入学", "card_title": "非户籍适龄儿童少年积分入学基本适用范围", "section_id": "policy_points_2025", "page_ranges": [], "keywords": ["积分入学", "非户籍", "公办义务教育", "C类"]},),
    "policy_dg_honorary_citizen_2025": ({"card_id": "policy_honorary_citizen_priority_2025", "card_type": "荣誉市民", "card_title": "荣誉市民相关子女入学优待", "section_id": "policy_honorary_2025", "page_ranges": [], "keywords": ["荣誉市民", "子女入学", "B2"]},),
}


def build_source_hint_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for spec in SOURCE_SPECS:
        payload = {"catalog_source_id": spec.source_id, "title": spec.title, "source_type": spec.source_type.value, "year": spec.year, "effective_date": spec.effective_date, "expiry_date": spec.expiry_date, "scope": spec.scope, "authority_rank": spec.authority_rank, "reliability_rank": spec.reliability_rank, "seed_text": (spec.seed_text or "").strip(), "seed_tags": [tag for tag in spec.seed_tags if tag]}
        relative_path = spec.relative_path.replace("\\", "/")
        index[relative_path] = payload
        index[Path(relative_path).name] = payload
    return index


def load_rules() -> dict[str, Any]:
    settings = get_settings()
    return json.loads(settings.rules_path.read_text(encoding="utf-8"))


def iter_source_files(root: Path) -> list[Path]:
    files = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES]
    for folder in root.iterdir():
        if folder.is_dir():
            files.extend(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES)
    return sorted(files)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Unable to decode CSV: {path}") from last_error


def normalize_sheet_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def load_xls_rows(path: Path) -> list[dict[str, str]]:
    workbook = xlrd.open_workbook(str(path))
    if workbook.nsheets == 0:
        return []
    sheet = workbook.sheet_by_index(0)
    if sheet.nrows == 0:
        return []
    headers = [normalize_sheet_value(sheet.cell_value(0, column)) for column in range(sheet.ncols)]
    rows: list[dict[str, str]] = []
    for row_index in range(1, sheet.nrows):
        payload: dict[str, str] = {}
        for column_index, header in enumerate(headers):
            payload[header] = normalize_sheet_value(sheet.cell_value(row_index, column_index))
        rows.append(payload)
    return rows


def spreadsheet_rows(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_csv_rows(path)
    if suffix in {".xls", ".xlsx"}:
        return load_xls_rows(path)
    raise ValueError(f"Unsupported spreadsheet type: {path}")


def chunk_text(text: str, limit: int = 500) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    chunks: list[str] = []
    buffer = ""
    for part in parts:
        candidate = f"{buffer}\n{part}".strip() if buffer else part
        if len(candidate) <= limit:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
        if len(part) <= limit:
            buffer = part
            continue
        start = 0
        while start < len(part):
            chunks.append(part[start : start + limit])
            start += limit
        buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks


def detect_source_priority(relative_path: str, rules: dict[str, Any]) -> tuple[int, str]:
    for item in rules.get("source_priorities", []):
        if item["pattern"] in relative_path:
            return int(item["tier"]), item["label"]
    return 6, "其他补充文件"


def lookup_source_hint(*, relative_path: str, file_name: str, source_hint_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    hint = source_hint_index.get(relative_path) or source_hint_index.get(file_name)
    if hint:
        return dict(hint)
    year_match = re.search(r"(20\d{2})", f"{relative_path} {file_name}")
    year = int(year_match.group(1)) if year_match else (2025 if "2025年入学政策相关资料" in relative_path else 2024)
    source_type = "policy"
    if "申请指南" in file_name:
        source_type = "annual_guide"
    elif "操作指引" in file_name:
        source_type = "operation_guide"
    elif "机器人业务文档" in file_name:
        source_type = "business_faq"
    elif "答疑" in file_name or "一图读懂" in file_name:
        source_type = "faq"
    seed_tags = [tag for tag in ("A1", "A2", "A3", "B1", "B2", "B3", "C类", "积分入学", "优才卡", "优粤卡", "台湾学生", "华侨华人", "单位账号", "房产锁定") if tag in file_name]
    return {
        "catalog_source_id": f"{source_type}_{year}_{re.sub(r'[^a-z0-9]+', '_', normalize_text(file_name))[:40]}",
        "title": Path(file_name).stem,
        "source_type": source_type,
        "year": year,
        "effective_date": f"{year}-01-01",
        "expiry_date": f"{year}-12-31" if source_type in {"annual_guide", "operation_guide", "faq", "business_faq"} else None,
        "scope": Path(file_name).stem,
        "authority_rank": 2 if source_type in {"annual_guide", "operation_guide", "faq"} else 1,
        "reliability_rank": 2 if source_type == "business_faq" else 1,
        "seed_text": "",
        "seed_tags": seed_tags,
    }


def infer_cycle_year(relative_path: str, file_name: str) -> int:
    if "2025年入学政策相关资料" in relative_path:
        return 2025
    match = re.search(r"(20\d{2})", f"{relative_path} {file_name}")
    if match:
        year = int(match.group(1))
        if year in {2024, 2025}:
            return year
    return 2024


def infer_active_cycle_year(source_hint_index: dict[str, dict[str, Any]]) -> int:
    years = {int(item["year"]) for item in source_hint_index.values() if item.get("year") and int(item["year"]) in {2024, 2025}}
    return max(years) if years else 2024


def refine_source_priority(*, source_tier: int, source_label: str, source_type: str, cycle_year: int, active_cycle_year: int) -> tuple[int, str]:
    if source_tier < 6:
        return source_tier, source_label
    if cycle_year == active_cycle_year:
        if source_type == "annual_guide":
            return 1, f"{cycle_year} 年松山湖入学申请指南"
        if source_type in {"policy", "operation_guide"}:
            return 2, f"{cycle_year} 年政策与操作资料"
        if source_type == "faq":
            return 3, f"{cycle_year} 年答疑资料"
        if source_type == "business_faq":
            return 4, f"{cycle_year} 年业务 FAQ"
    if source_type == "business_faq":
        return 5, "历史业务 FAQ"
    return 6, "其他补充文件"


def is_application_guide(source_hint: dict[str, Any]) -> bool:
    catalog_source_id = str(source_hint.get("catalog_source_id") or "")
    title = str(source_hint.get("title") or "")
    return source_hint.get("source_type") == "annual_guide" and (catalog_source_id.startswith("guide_songshanhu_") or ("松山湖" in title and "申请指南" in title))


def build_structured_sections(source_hint: dict[str, Any]) -> list[dict[str, Any]]:
    if is_application_guide(source_hint):
        return [{"section_id": spec["section_id"], "section_type": spec["section_type"], "section_title": spec["section_title"], "page_ranges": [list(item) for item in spec["page_ranges"]], "keywords": list(spec["keywords"])} for spec in GUIDE_SECTION_SPECS]
    catalog_source_id = str(source_hint.get("catalog_source_id") or "")
    raw_specs = SPECIAL_RULE_CARD_SPECS.get(catalog_source_id, ())
    if not raw_specs:
        return []
    keywords: list[str] = []
    for spec in raw_specs:
        for keyword in spec.get("keywords", []):
            if keyword not in keywords:
                keywords.append(keyword)
    return [{"section_id": f"{catalog_source_id}_overview", "section_type": str(source_hint.get("source_type") or "policy"), "section_title": str(source_hint.get("title") or catalog_source_id), "page_ranges": [], "keywords": keywords[:12]}]


def build_structured_rule_cards(source_hint: dict[str, Any]) -> list[dict[str, Any]]:
    if is_application_guide(source_hint):
        return [{"card_id": spec["card_id"], "card_type": spec["card_type"], "card_title": spec["card_title"], "section_id": spec["section_id"], "page_ranges": [list(item) for item in spec["page_ranges"]], "keywords": list(spec["keywords"])} for spec in GUIDE_RULE_CARD_SPECS]
    catalog_source_id = str(source_hint.get("catalog_source_id") or "")
    return [{"card_id": spec["card_id"], "card_type": spec["card_type"], "card_title": spec["card_title"], "section_id": spec["section_id"], "page_ranges": [list(item) for item in spec.get("page_ranges", [])], "keywords": list(spec["keywords"])} for spec in SPECIAL_RULE_CARD_SPECS.get(catalog_source_id, ())]


def build_source_record(*, source_id: str, root: Path, path: Path, rules: dict[str, Any], source_hint_index: dict[str, dict[str, Any]], active_cycle_year: int) -> dict[str, Any]:
    relative_path = str(path.relative_to(root)).replace("\\", "/")
    source_hint = lookup_source_hint(relative_path=relative_path, file_name=path.name, source_hint_index=source_hint_index)
    cycle_year = infer_cycle_year(relative_path, path.name)
    source_tier, source_label = detect_source_priority(relative_path, rules)
    source_tier, source_label = refine_source_priority(source_tier=source_tier, source_label=source_label, source_type=str(source_hint.get("source_type") or ""), cycle_year=cycle_year, active_cycle_year=active_cycle_year)
    return {"source_id": source_id, "file_name": path.name, "relative_path": relative_path, "cycle_year": cycle_year, "source_tier": source_tier, "source_label": source_label, "suffix": path.suffix.lower(), "title": source_hint.get("title") or path.stem, "source_type": source_hint.get("source_type"), "year": source_hint.get("year"), "effective_date": source_hint.get("effective_date"), "expiry_date": source_hint.get("expiry_date"), "scope": source_hint.get("scope", ""), "authority_rank": source_hint.get("authority_rank"), "reliability_rank": source_hint.get("reliability_rank"), "seed_text": source_hint.get("seed_text", ""), "seed_tags": list(source_hint.get("seed_tags", [])), "catalog_source_id": source_hint.get("catalog_source_id"), "structured_sections": build_structured_sections(source_hint), "structured_rule_cards": build_structured_rule_cards(source_hint)}


def format_page_ranges(page_ranges: list[list[int]]) -> str:
    if not page_ranges:
        return "全文"
    parts: list[str] = []
    for start, end in page_ranges:
        parts.append(f"第 {start} 页" if start == end else f"第 {start}-{end} 页")
    return "、".join(parts)


def section_for_page(page_number: int) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for spec in GUIDE_SECTION_SPECS:
        for start, end in spec["page_ranges"]:
            if start <= page_number <= end:
                matched.append(spec)
                break
    return matched


def rule_cards_for_page(page_number: int) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for spec in GUIDE_RULE_CARD_SPECS:
        for start, end in spec["page_ranges"]:
            if start <= page_number <= end:
                matched.append(spec)
                break
    return matched


def build_section_metadata(page_number: int) -> dict[str, Any]:
    matched = section_for_page(page_number)
    if not matched:
        return {}
    primary = matched[0]
    keywords: list[str] = []
    for spec in matched:
        for keyword in spec["keywords"]:
            if keyword not in keywords:
                keywords.append(keyword)
    return {"section_id": primary["section_id"], "section_type": primary["section_type"], "section_title": primary["section_title"], "section_ids": [spec["section_id"] for spec in matched], "section_types": [spec["section_type"] for spec in matched], "section_titles": [spec["section_title"] for spec in matched], "section_keywords": keywords}


def build_rule_card_metadata(page_number: int) -> dict[str, Any]:
    matched = rule_cards_for_page(page_number)
    if not matched:
        return {}
    primary = matched[0]
    terms: list[str] = []
    for spec in matched:
        for keyword in spec["keywords"]:
            if keyword not in terms:
                terms.append(keyword)
    return {"rule_card_id": primary["card_id"], "rule_card_type": primary["card_type"], "rule_card_title": primary["card_title"], "rule_card_ids": [spec["card_id"] for spec in matched], "rule_card_types": [spec["card_type"] for spec in matched], "rule_card_titles": [spec["card_title"] for spec in matched], "rule_card_terms": terms, "rule_card_section_ids": [spec["section_id"] for spec in matched]}


def build_pdf_summary_text(source: dict[str, Any]) -> str:
    parts = [f"文件标题：{source['title']}", f"资料年度：{source['cycle_year']}", f"资料类型：{source.get('source_type') or 'policy'}"]
    if source.get("scope"):
        parts.append(f"适用范围：{source['scope']}")
    if source.get("effective_date"):
        parts.append(f"生效日期：{source['effective_date']}")
    if source.get("expiry_date"):
        parts.append(f"失效日期：{source['expiry_date']}")
    if source.get("seed_tags"):
        parts.append(f"关键词：{'、'.join(source['seed_tags'])}")
    return "\n".join(parts)


def build_section_summary_text(title: str, spec: dict[str, Any], page_texts: dict[int, str]) -> str:
    combined = "\n".join((page_texts.get(page_number) or "").strip() for start, end in spec["page_ranges"] for page_number in range(start, end + 1)).strip()
    excerpt = chunk_text(combined, limit=680)
    parts = [f"文件标题：{title}", f"章节：{spec['section_title']}", f"章节类型：{spec['section_type']}", f"覆盖页码：{format_page_ranges([list(item) for item in spec['page_ranges']])}", f"适用问题：{'、'.join(spec['keywords'])}"]
    if excerpt:
        parts.append(f"章节摘要：{excerpt[0]}")
    return "\n".join(parts)


def build_rule_card_summary_text(title: str, spec: dict[str, Any], page_texts: dict[int, str], source: dict[str, Any]) -> str:
    ranges = spec.get("page_ranges", [])
    combined = "\n".join((page_texts.get(page_number) or "").strip() for start, end in ranges for page_number in range(start, end + 1)).strip() or build_pdf_summary_text(source)
    excerpt = chunk_text(combined, limit=520)
    parts = [f"文件标题：{title}", f"规则卡片：{spec['card_title']}", f"卡片类型：{spec['card_type']}", f"所属章节：{spec.get('section_id') or 'overview'}", f"覆盖页码：{format_page_ranges([list(item) for item in ranges])}", f"适用问法：{'、'.join(spec['keywords'])}"]
    if excerpt:
        parts.append(f"规则摘要：{excerpt[0]}")
    return "\n".join(parts)


def faq_search_text(row: dict[str, str]) -> str:
    parts = [row.get("常见问题", ""), row.get("标准答案", ""), row.get("可报类别", ""), row.get("问题情况", ""), row.get("备注", "")]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def build_faq_records(path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    rows = spreadsheet_rows(path)
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        question = (row.get("常见问题") or "").strip()
        answer = (row.get("标准答案") or "").strip()
        if not question or not answer:
            continue
        search_text = faq_search_text(row)
        combined = "\n".join(part for part in [question, answer, row.get("可报类别", ""), row.get("问题情况", ""), row.get("备注", "")] if str(part).strip())
        records.append({"faq_id": f"{source['source_id']}-faq-{row_number:03d}", "source_id": source["source_id"], "cycle_year": source["cycle_year"], "row_number": int(float(row.get("序号") or row_number)), "question": question, "answer": answer, "category": (row.get("可报类别") or "").strip(), "change_type": (row.get("问题情况") or "").strip(), "notes": (row.get("备注") or "").strip(), "normalized_question": normalize_text(question), "normalized_answer": normalize_text(answer), "search_text": search_text, "normalized_search_text": normalize_text(search_text), "tokens": sorted(extract_tokens(question)), "search_tokens": sorted(extract_tokens(search_text)), "vector": vectorize_text(combined)})
    return records


def dedupe_faq_records(records: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_map = {source["source_id"]: source for source in sources}
    selected: dict[tuple[int, str, str], dict[str, Any]] = {}
    for record in records:
        key = (int(record["cycle_year"]), record.get("normalized_question", ""), record.get("normalized_answer", ""))
        existing = selected.get(key)
        if existing is None:
            selected[key] = record
            continue
        current_source = source_map[existing["source_id"]]
        incoming_source = source_map[record["source_id"]]
        current_rank = (int(current_source["source_tier"]), current_source["source_id"])
        incoming_rank = (int(incoming_source["source_tier"]), incoming_source["source_id"])
        if incoming_rank < current_rank:
            selected[key] = record
    return list(selected.values())


def build_pdf_chunks(path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    reader = PdfReader(str(path))
    title = str(source["title"])
    page_texts = {page_number: (page.extract_text() or "").strip() for page_number, page in enumerate(reader.pages, start=1)}
    records: list[dict[str, Any]] = [{"chunk_id": f"{source['source_id']}-pdf-summary", "source_id": source["source_id"], "cycle_year": source["cycle_year"], "title": title, "citation": "资料摘要", "text": build_pdf_summary_text(source), "normalized_text": normalize_text(build_pdf_summary_text(source)), "tokens": sorted(extract_tokens(build_pdf_summary_text(source))), "vector": vectorize_text(build_pdf_summary_text(source))}]
    for spec in source.get("structured_sections", []):
        summary = build_section_summary_text(title, spec, page_texts)
        records.append({"chunk_id": f"{source['source_id']}-section-{spec['section_id']}", "source_id": source["source_id"], "cycle_year": source["cycle_year"], "title": title, "citation": f"章节摘要：{spec['section_title']}（{format_page_ranges(spec['page_ranges'])}）", "text": summary, "normalized_text": normalize_text(summary), "tokens": sorted(extract_tokens(summary)), "vector": vectorize_text(summary), "section_id": spec["section_id"], "section_type": spec["section_type"], "section_title": spec["section_title"], "section_ids": [spec["section_id"]], "section_types": [spec["section_type"]], "section_titles": [spec["section_title"]], "section_keywords": list(spec["keywords"]), "page_ranges": [list(item) for item in spec["page_ranges"]]})
    for spec in source.get("structured_rule_cards", []):
        summary = build_rule_card_summary_text(title, spec, page_texts, source)
        records.append({"chunk_id": f"{source['source_id']}-rule-{spec['card_id']}", "source_id": source["source_id"], "cycle_year": source["cycle_year"], "title": title, "citation": f"规则卡片：{spec['card_title']}（{format_page_ranges(spec.get('page_ranges', []))}）", "text": summary, "normalized_text": normalize_text(summary), "tokens": sorted(extract_tokens(summary)), "vector": vectorize_text(summary), "rule_card_id": spec["card_id"], "rule_card_type": spec["card_type"], "rule_card_title": spec["card_title"], "rule_card_ids": [spec["card_id"]], "rule_card_types": [spec["card_type"]], "rule_card_titles": [spec["card_title"]], "rule_card_terms": list(spec["keywords"]), "rule_card_section_ids": [spec.get("section_id") or "overview"], "page_ranges": [list(item) for item in spec.get("page_ranges", [])]})
    chunk_index = 0
    for page_number, text in page_texts.items():
        section_meta = build_section_metadata(page_number) if is_application_guide(source) else {}
        rule_card_meta = build_rule_card_metadata(page_number) if is_application_guide(source) else {}
        for piece in chunk_text(text):
            chunk_index += 1
            records.append({"chunk_id": f"{source['source_id']}-pdf-{chunk_index:04d}", "source_id": source["source_id"], "cycle_year": source["cycle_year"], "title": title, "citation": f"第 {page_number} 页", "text": piece, "normalized_text": normalize_text(piece), "tokens": sorted(extract_tokens(piece)), "vector": vectorize_text(piece), "page_number": page_number, **section_meta, **rule_card_meta})
    if len(records) == 1 and source.get("seed_text"):
        seed_text = str(source["seed_text"]).strip()
        records.append({"chunk_id": f"{source['source_id']}-pdf-seed-0001", "source_id": source["source_id"], "cycle_year": source["cycle_year"], "title": title, "citation": "政策摘要", "text": seed_text, "normalized_text": normalize_text(seed_text), "tokens": sorted(extract_tokens(seed_text)), "vector": vectorize_text(seed_text)})
    return records


def build_docx_chunks(path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    document = docx.Document(str(path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    records: list[dict[str, Any]] = []
    for index, piece in enumerate(chunk_text("\n".join(paragraphs), limit=500), start=1):
        records.append({"chunk_id": f"{source['source_id']}-docx-{index:04d}", "source_id": source["source_id"], "cycle_year": source["cycle_year"], "title": source["title"], "citation": f"第 {index} 段", "text": piece, "normalized_text": normalize_text(piece), "tokens": sorted(extract_tokens(piece)), "vector": vectorize_text(piece)})
    return records


def build_payload(root: Path) -> dict[str, Any]:
    rules = load_rules()
    source_hint_index = build_source_hint_index()
    active_cycle_year = infer_active_cycle_year(source_hint_index)
    sources: list[dict[str, Any]] = []
    faqs: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    for index, path in enumerate(iter_source_files(root), start=1):
        source = build_source_record(source_id=f"src-{index:03d}", root=root, path=path, rules=rules, source_hint_index=source_hint_index, active_cycle_year=active_cycle_year)
        sources.append(source)
        suffix = path.suffix.lower()
        if suffix in {".csv", ".xls", ".xlsx"}:
            faqs.extend(build_faq_records(path, source))
        elif suffix == ".pdf":
            documents.extend(build_pdf_chunks(path, source))
        elif suffix == ".docx":
            documents.extend(build_docx_chunks(path, source))
    faqs = dedupe_faq_records(faqs, sources)
    available_cycle_years = sorted({int(source["cycle_year"]) for source in sources if int(source["cycle_year"]) in {2024, 2025}})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root), "active_cycle_year": active_cycle_year, "available_cycle_years": available_cycle_years, "sources": sources, "faqs": faqs, "documents": documents}


def filter_payload_by_cycle_year(payload: dict[str, Any], cycle_year: int) -> dict[str, Any]:
    available_years = sorted(int(item) for item in payload.get("available_cycle_years", []))
    if available_years and cycle_year == max(available_years):
        source_ids = {source["source_id"] for source in payload["sources"] if int(source.get("cycle_year") or 0) <= cycle_year}
    else:
        source_ids = {source["source_id"] for source in payload["sources"] if int(source.get("cycle_year") or 0) == cycle_year}
    return {"generated_at": payload["generated_at"], "root": payload["root"], "active_cycle_year": cycle_year, "available_cycle_years": list(payload.get("available_cycle_years", [])), "sources": [source for source in payload["sources"] if source["source_id"] in source_ids], "faqs": [faq for faq in payload["faqs"] if faq["source_id"] in source_ids], "documents": [doc for doc in payload["documents"] if doc["source_id"] in source_ids]}


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_yearly_payloads(payload: dict[str, Any], output_path: Path) -> None:
    output_dir = output_path.parent
    manifest = {"generated_at": payload["generated_at"], "available_cycle_years": payload.get("available_cycle_years", []), "active_cycle_year": payload.get("active_cycle_year"), "paths": {}}
    for cycle_year in payload.get("available_cycle_years", []):
        year_payload = filter_payload_by_cycle_year(payload, cycle_year)
        year_path = output_dir / f"knowledge_base_{cycle_year}.json"
        write_payload(year_path, year_payload)
        manifest["paths"][str(cycle_year)] = str(year_path)
    write_payload(output_dir / "knowledge_manifest.json", manifest)


def build_knowledge(root: Path, output_path: Path) -> dict[str, Any]:
    payload = build_payload(root.resolve())
    write_yearly_payloads(payload, output_path.resolve())
    active_year = get_settings().knowledge_year
    active_payload = filter_payload_by_cycle_year(payload, active_year)
    write_payload(output_path.resolve(), active_payload)
    write_payload(output_path.resolve().parent / "knowledge_base.json", active_payload)
    return active_payload


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Build local knowledge bases for 2024 and 2025.")
    parser.add_argument("--root", default=str(settings.root_dir), help="Workspace root to scan")
    parser.add_argument("--out", default=str(settings.knowledge_path), help="Active output JSON path")
    args = parser.parse_args()
    payload = build_knowledge(root=Path(args.root).resolve(), output_path=Path(args.out).resolve())
    print(json.dumps({"knowledge_path": str(Path(args.out).resolve()), "active_cycle_year": payload["active_cycle_year"], "available_cycle_years": payload.get("available_cycle_years", []), "faq_count": len(payload["faqs"]), "document_chunk_count": len(payload["documents"]), "source_count": len(payload["sources"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
