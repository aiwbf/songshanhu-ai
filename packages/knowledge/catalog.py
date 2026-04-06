from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import SourceType


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    relative_path: str
    title: str
    source_type: SourceType
    year: int | None
    effective_date: str | None
    expiry_date: str | None
    scope: str
    authority_rank: int
    reliability_rank: int
    seed_text: str | None = None
    seed_tags: tuple[str, ...] = ()


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        source_id="policy_dg_youcai_2020",
        relative_path="1、入学政策参考资料（市级）/东莞市人民政府关于印发《东莞市优才卡管理暂行办法》的通知.pdf",
        title="东莞市优才卡管理暂行办法",
        source_type=SourceType.POLICY,
        year=2020,
        effective_date="2020-12-09",
        expiry_date=None,
        scope="东莞市优才卡持有人子女义务教育优待政策",
        authority_rank=1,
        reliability_rank=1,
        seed_tags=("优才卡", "B2"),
    ),
    SourceSpec(
        source_id="policy_dg_honorary_citizen_2021",
        relative_path="1、入学政策参考资料（市级）/东莞市人民政府关于印发《东莞市授予荣誉市民称号办法》的通知.pdf",
        title="东莞市授予荣誉市民称号办法",
        source_type=SourceType.POLICY,
        year=2021,
        effective_date="2021-01-15",
        expiry_date=None,
        scope="东莞市荣誉市民称号及相关子女入学优待",
        authority_rank=1,
        reliability_rank=1,
        seed_tags=("荣誉市民",),
    ),
    SourceSpec(
        source_id="policy_dg_points_2023",
        relative_path="1、入学政策参考资料（市级）/东莞市人民政府关于印发《东莞市非户籍适龄儿童少年积分入读公办义务教育学校实施方案》的通知.pdf",
        title="东莞市非户籍适龄儿童少年积分入读公办义务教育学校实施方案",
        source_type=SourceType.POLICY,
        year=2023,
        effective_date="2023-05-10",
        expiry_date=None,
        scope="东莞市非户籍适龄儿童少年积分入学政策",
        authority_rank=1,
        reliability_rank=1,
        seed_tags=("C类", "积分入学", "香港", "澳门", "台湾"),
    ),
    SourceSpec(
        source_id="policy_dg_talent_children_2019",
        relative_path="1、入学政策参考资料（市级）/东莞市人民政府办公室关于印发《东莞市高端人才和企业人才子女入学实施办法》的通知.pdf",
        title="东莞市高端人才和企业人才子女入学实施办法",
        source_type=SourceType.POLICY,
        year=2019,
        effective_date="2019-08-13",
        expiry_date=None,
        scope="东莞市高端人才和企业人才子女入学政策",
        authority_rank=1,
        reliability_rank=1,
        seed_tags=("B1", "B2", "高端人才", "香港", "澳门"),
    ),
    SourceSpec(
        source_id="policy_dg_overseas_chinese_2017",
        relative_path="1、入学政策参考资料（市级）/关于修订华侨华人子女及华侨学生在我市就读有关规定的通知.pdf",
        title="关于修订华侨华人子女及华侨学生在我市就读有关规定的通知",
        source_type=SourceType.POLICY,
        year=2017,
        effective_date="2017-01-01",
        expiry_date=None,
        scope="东莞市华侨华人子女及华侨学生就读义务教育政策",
        authority_rank=1,
        reliability_rank=1,
        seed_text="东教基函〔2017〕9号 关于修订华侨华人子女及华侨学生在我市就读有关规定的通知。",
        seed_tags=("华侨华人", "华侨学生"),
    ),
    SourceSpec(
        source_id="policy_dg_taiwan_2019",
        relative_path="1、入学政策参考资料（市级）/关于做好台湾学生申请就读我市义务教育阶段学校工作的通知.pdf",
        title="关于做好台湾学生申请就读我市义务教育阶段学校工作的通知",
        source_type=SourceType.POLICY,
        year=2019,
        effective_date="2019-03-28",
        expiry_date=None,
        scope="东莞市台湾学生义务教育阶段入学政策",
        authority_rank=1,
        reliability_rank=1,
        seed_text="东教基函〔2019〕13号 关于做好台湾学生申请就读我市义务教育阶段学校工作的通知。",
        seed_tags=("台湾学生", "B2"),
    ),
    SourceSpec(
        source_id="policy_gd_youyue_2023",
        relative_path="1、入学政策参考资料（市级）/广东省人民政府关于印发广东省人才优粤卡实施办法的通知.pdf",
        title="广东省人才优粤卡实施办法",
        source_type=SourceType.POLICY,
        year=2023,
        effective_date="2023-03-28",
        expiry_date=None,
        scope="广东省优粤卡持有人子女入学优待政策",
        authority_rank=1,
        reliability_rank=1,
        seed_text="粤府〔2023〕29号 广东省人民政府关于印发广东省人才优粤卡实施办法的通知。",
        seed_tags=("优粤卡", "B2"),
    ),
    SourceSpec(
        source_id="policy_dg_preferential_summary_2024",
        relative_path="1、入学政策参考资料（市级）/附件1义务教育阶段优待政策汇总表（2024）.pdf",
        title="2024年义务教育阶段优待政策汇总表",
        source_type=SourceType.POLICY,
        year=2024,
        effective_date="2024-03-07",
        expiry_date="2024-08-31",
        scope="东莞市2024义务教育优待政策汇总",
        authority_rank=2,
        reliability_rank=1,
        seed_tags=("优待政策", "台湾学生", "华侨华人", "优才卡", "优粤卡", "荣誉市民"),
    ),
    SourceSpec(
        source_id="guide_songshanhu_2024",
        relative_path="2、2024年松山湖公办学位申请指南/2024年松山湖中小学、幼儿园入学申请指南.pdf",
        title="2024年松山湖中小学、幼儿园入学申请指南",
        source_type=SourceType.ANNUAL_GUIDE,
        year=2024,
        effective_date="2024-05-07",
        expiry_date="2024-08-31",
        scope="松山湖2024秋季中小学与幼儿园招生申请指南",
        authority_rank=2,
        reliability_rank=1,
        seed_tags=("A1", "A2", "A3", "B1", "B2", "B3", "C类"),
    ),
    SourceSpec(
        source_id="ops_songshanhu_platform_2024",
        relative_path="3、2024年松山湖及东莞市招生入学平台操作指引/2024年松山湖及东莞市招生入学平台操作指引.pdf",
        title="2024年松山湖及东莞市招生入学平台操作指引",
        source_type=SourceType.OPERATION_GUIDE,
        year=2024,
        effective_date="2024-05-07",
        expiry_date="2024-08-31",
        scope="松山湖2024秋季招生平台操作流程",
        authority_rank=2,
        reliability_rank=1,
        seed_tags=("平台步骤", "单位账号", "报名资料修改"),
    ),
    SourceSpec(
        source_id="faq_songshanhu_infographic_2024",
        relative_path="4、一图读懂｜2024年松山湖中小学、幼儿园入学申请/一图读懂｜2024年松山湖中小学、幼儿园入学申请.pdf",
        title="一图读懂｜2024年松山湖中小学、幼儿园入学申请",
        source_type=SourceType.FAQ,
        year=2024,
        effective_date="2024-05-07",
        expiry_date="2024-08-31",
        scope="松山湖2024秋季招生图解说明",
        authority_rank=3,
        reliability_rank=2,
        seed_tags=("A1", "A2", "A3", "B类", "C类"),
    ),
    SourceSpec(
        source_id="faq_songshanhu_official_2024_part1",
        relative_path="5、答疑｜有关2024松山湖秋季招生，你可能想知道这些（一、二）/答疑｜有关2024松山湖秋季招生，你可能想知道这些.pdf",
        title="答疑｜有关2024松山湖秋季招生，你可能想知道这些",
        source_type=SourceType.FAQ,
        year=2024,
        effective_date="2024-05-07",
        expiry_date="2024-08-31",
        scope="松山湖2024官方招生答疑（上）",
        authority_rank=2,
        reliability_rank=1,
        seed_tags=("优才卡", "香港", "澳门", "房产解锁", "B3"),
    ),
    SourceSpec(
        source_id="faq_songshanhu_official_2024_part2",
        relative_path="5、答疑｜有关2024松山湖秋季招生，你可能想知道这些（一、二）/答疑｜有关2024松山湖秋季招生，你可能想知道这些（二）.pdf",
        title="答疑｜有关2024松山湖秋季招生，你可能想知道这些（二）",
        source_type=SourceType.FAQ,
        year=2024,
        effective_date="2024-05-10",
        expiry_date="2024-08-31",
        scope="松山湖2024官方招生答疑（下）",
        authority_rank=2,
        reliability_rank=1,
        seed_tags=("单位管理员", "报名资料修改", "房产锁定", "优才卡"),
    ),
    SourceSpec(
        source_id="business_faq_2024_csv",
        relative_path="机器人业务文档（2024合并修订版）.csv",
        title="机器人业务文档（2024合并修订版）CSV",
        source_type=SourceType.BUSINESS_FAQ,
        year=2024,
        effective_date="2024-05-07",
        expiry_date="2024-08-31",
        scope="内部咨询业务FAQ（CSV版）",
        authority_rank=4,
        reliability_rank=4,
    ),
    SourceSpec(
        source_id="business_faq_2024_xls",
        relative_path="机器人业务文档（2024合并修订版）.xls",
        title="机器人业务文档（2024合并修订版）XLS",
        source_type=SourceType.BUSINESS_FAQ,
        year=2024,
        effective_date="2024-05-07",
        expiry_date="2024-08-31",
        scope="内部咨询业务FAQ（XLS版）",
        authority_rank=4,
        reliability_rank=4,
    ),
    SourceSpec(
        source_id="business_doc_consulting_2024",
        relative_path="咨询服务相关情况.docx",
        title="咨询服务相关情况",
        source_type=SourceType.BUSINESS_FAQ,
        year=2024,
        effective_date="2024-05-01",
        expiry_date="2024-08-31",
        scope="内部咨询服务量统计",
        authority_rank=5,
        reliability_rank=5,
    ),
)


def _slugify_source_id(file_name: str) -> str:
    stem = Path(file_name).stem.lower()
    stem = re.sub(r"\(.*?\)", "", stem)
    if "松山湖中小学" in file_name and "申请指南" in file_name:
        return "guide_songshanhu_2025"
    if "机器人业务文档" in file_name:
        return "business_faq_2025_pdf"
    if "优粤卡" in file_name:
        return "policy_gd_youyue_2025"
    if "莞爱人才" in file_name:
        return "policy_dg_guanai_talent_2025"
    if "华侨华人" in file_name:
        return "policy_dg_overseas_chinese_2025"
    if "企业人才子女入学实施办法" in file_name:
        return "policy_dg_talent_children_2025"
    if "积分入读公办义务教育学校实施方案" in file_name:
        return "policy_dg_points_2025"
    if "荣誉市民" in file_name:
        return "policy_dg_honorary_citizen_2025"
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_") or "policy_2025"


def _source_type_for_2025(file_name: str) -> SourceType:
    if "申请指南" in file_name:
        return SourceType.ANNUAL_GUIDE
    if "业务文档" in file_name:
        return SourceType.BUSINESS_FAQ
    if "答疑" in file_name or "一图读懂" in file_name:
        return SourceType.FAQ
    if "操作指引" in file_name:
        return SourceType.OPERATION_GUIDE
    return SourceType.POLICY


def _seed_tags_for_2025(file_name: str) -> tuple[str, ...]:
    tags: list[str] = []
    if "申请指南" in file_name:
        tags.extend(["A1", "A2", "A3", "B1", "B2", "B3", "C类"])
    if "业务文档" in file_name:
        tags.extend(["FAQ", "常见判断"])
    if "优粤卡" in file_name:
        tags.extend(["优粤卡", "B2"])
    if "莞爱人才" in file_name:
        tags.extend(["莞爱人才", "B2"])
    if "华侨华人" in file_name:
        tags.extend(["华侨华人"])
    if "企业人才子女入学实施办法" in file_name:
        tags.extend(["B1", "B2"])
    if "积分入读公办义务教育学校实施方案" in file_name:
        tags.extend(["C类", "积分入学"])
    if "荣誉市民" in file_name:
        tags.extend(["荣誉市民", "B2"])
    return tuple(dict.fromkeys(tags))


def _scope_for_2025(file_name: str) -> str:
    if "申请指南" in file_name:
        return "松山湖 2025 秋季中小学与幼儿园招生申请指南"
    if "业务文档" in file_name:
        return "2025 招生咨询业务 FAQ 与常见判断"
    if "优粤卡" in file_name:
        return "2025 优粤卡相关子女入学优待政策"
    if "莞爱人才" in file_name:
        return "2025 莞爱人才服务保障与子女教育优待政策"
    if "华侨华人" in file_name:
        return "2025 华侨华人子女及华侨学生就读政策"
    if "企业人才子女入学实施办法" in file_name:
        return "2025 企业人才子女入学实施办法"
    if "积分入读公办义务教育学校实施方案" in file_name:
        return "2025 非户籍适龄儿童少年积分入学政策"
    if "荣誉市民" in file_name:
        return "2025 荣誉市民相关入学优待政策"
    return "2025 招生政策参考资料"


def _build_dynamic_2025_specs() -> tuple[SourceSpec, ...]:
    root = Path(__file__).resolve().parents[2]
    policy_dir = root / "2025年入学政策相关资料"
    if not policy_dir.exists():
        return ()

    specs: list[SourceSpec] = []
    for path in sorted(policy_dir.glob("*.pdf")):
        file_name = path.name
        source_type = _source_type_for_2025(file_name)
        specs.append(
            SourceSpec(
                source_id=_slugify_source_id(file_name),
                relative_path=str(path.relative_to(root)).replace("\\", "/"),
                title=path.stem,
                source_type=source_type,
                year=2025,
                effective_date="2025-01-01",
                expiry_date="2025-12-31" if source_type in {SourceType.ANNUAL_GUIDE, SourceType.FAQ, SourceType.OPERATION_GUIDE, SourceType.BUSINESS_FAQ} else None,
                scope=_scope_for_2025(file_name),
                authority_rank=2 if source_type in {SourceType.ANNUAL_GUIDE, SourceType.OPERATION_GUIDE, SourceType.FAQ} else 1,
                reliability_rank=2 if source_type == SourceType.BUSINESS_FAQ else 1,
                seed_tags=_seed_tags_for_2025(file_name),
            )
        )
    return tuple(specs)


SOURCE_SPECS = SOURCE_SPECS + _build_dynamic_2025_specs()
