from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.utils import compact_snippet


OFFICIAL_SEARCH_API = "http://search.gd.gov.cn/api/search/site"
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
ARTICLE_TITLE_RE = re.compile(r'<meta\s+name="ArticleTitle"\s+content="([^"]+)"', re.I)
PUB_DATE_RE = re.compile(r'<meta\s+name="PubDate"\s+content="([^"]+)"', re.I)
ZOOMCON_RE = re.compile(r'id="zoomcon"[^>]*>(.*?)</div>', re.I | re.S)


@dataclass(frozen=True)
class OfficialSearchSite:
    site_id: str
    gdbs_division: str
    gdbs_org_num: str
    service_area: int
    label: str


@dataclass
class PolicyItem:
    policy_year: int
    level: str
    title: str
    pub_date: str
    source_url: str
    summary_points: list[str]


@dataclass
class LatestPolicyDigest:
    conclusion: str
    consultation_advice: str
    cannot_confirm_reason: str
    next_step: str
    risk_notice: list[str]
    evidence: list[dict[str, Any]]


class LatestPolicyService:
    DONGGUAN_EDU = OfficialSearchSite(
        site_id="769026",
        gdbs_division="441900",
        gdbs_org_num="007330133",
        service_area=769,
        label="东莞教育网站",
    )
    SONGSHANHU = OfficialSearchSite(
        site_id="769004",
        gdbs_division="441900",
        gdbs_org_num="441026978",
        service_area=769,
        label="松山湖教育频道",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        payload = json.loads(settings.latest_policy_fallback_path.read_text(encoding="utf-8"))
        self.fallback_payload = payload
        self.fallback_items = [
            PolicyItem(
                policy_year=int(item["policy_year"]),
                level=item["level"],
                title=item["title"],
                pub_date=item["pub_date"],
                source_url=item["source_url"],
                summary_points=list(item.get("summary_points", [])),
            )
            for item in payload.get("items", [])
        ]

    def answer(self, question: str) -> LatestPolicyDigest:
        today = date.today().isoformat()
        current_year = date.today().year
        dynamic_items = self.find_current_year_updates(current_year=current_year)
        merged_items = self.merge_items(dynamic_items)
        local_rule_found = any(
            item.policy_year == current_year and ("东莞市" in item.title or "松山湖" in item.title)
            for item in dynamic_items
        )

        lines: list[str] = []
        if local_rule_found:
            lines.append(f"截至 {today}，我已经检索到今年与招生入学相关的官方更新。简单说：")
        else:
            lines.append(
                f"截至 {today}，我暂未检索到 {current_year} 年东莞或松山湖招生入学实施细则已公开发布；"
                "目前能确认的最新官方口径可以先这样理解："
            )

        for index, item in enumerate(merged_items[:3], start=1):
            bullet = "；".join(item.summary_points[:2]) or "请以原文为准。"
            lines.append(f"{index}. {item.level}（{item.pub_date}）：{item.title}。{bullet}。")

        if not local_rule_found:
            lines.append(
                f"如果你问的是 {current_year} 年松山湖具体报名时间、分类、材料和平台安排，"
                "目前还不能把 2025 年执行口径直接当作 2026 年最终版本。"
            )

        consultation_advice = (
            "如果你只是想先把今年的政策方向搞清楚，可以先按上面的官方口径理解；"
            "如果你接下来要判断自己能不能报、报哪一类，再把孩子户籍、父母户籍、园区工作和房产情况补充给我。"
        )
        cannot_confirm_reason = (
            self.fallback_payload.get("current_year_local_policy_not_found_note", "")
            if not local_rule_found
            else f"截至 {today}，我已检索到今年的相关官方更新，但园区或学校层面的补充公告仍可能继续发布。"
        )
        next_step = (
            "如果你要，我可以继续把“最新上位政策”和“东莞最近一次已公开实施口径”拆成报名资格、材料、时间安排三块讲给你。"
        )
        risk_notice = [
            "本回答优先依据官方实时来源；如今年实施细则尚未公开，不能把上一年度执行口径直接视为今年最终版本。",
            f"回答时间：{today}",
        ]

        evidence = [
            {
                "source_id": f"official-{item.policy_year}-{index}",
                "file_name": item.title,
                "source_tier": 1,
                "citation": item.pub_date,
                "snippet": "；".join(item.summary_points[:3]),
                "score": None,
                "source_url": item.source_url,
            }
            for index, item in enumerate(merged_items[:3], start=1)
        ]

        return LatestPolicyDigest(
            conclusion="\n".join(lines),
            consultation_advice=consultation_advice,
            cannot_confirm_reason=cannot_confirm_reason,
            next_step=next_step,
            risk_notice=risk_notice,
            evidence=evidence,
        )

    def merge_items(self, dynamic_items: list[PolicyItem]) -> list[PolicyItem]:
        merged: list[PolicyItem] = []
        seen: set[str] = set()
        for item in [*dynamic_items, *self.fallback_items]:
            key = item.source_url or item.title
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        merged.sort(key=lambda item: (item.pub_date, item.policy_year), reverse=True)
        return merged

    def find_current_year_updates(self, *, current_year: int) -> list[PolicyItem]:
        items: list[PolicyItem] = []
        items.extend(
            self.search_and_build(
                site=self.DONGGUAN_EDU,
                queries=[
                    f"{current_year}年 普通中小学 招生 入学",
                    f"{current_year}年 义务教育 招生 入学",
                ],
                matcher=self.is_relevant_city_policy,
                limit=2,
            )
        )
        items.extend(
            self.search_and_build(
                site=self.SONGSHANHU,
                queries=[
                    f"{current_year}年 松山湖 入学 申请 指南",
                    f"{current_year}年 松山湖 秋季 招生",
                    f"{current_year}年 松山湖 学位",
                ],
                matcher=self.is_relevant_songshanhu_policy,
                limit=2,
            )
        )
        return items

    def search_and_build(
        self,
        *,
        site: OfficialSearchSite,
        queries: list[str],
        matcher,
        limit: int,
    ) -> list[PolicyItem]:
        items: list[PolicyItem] = []
        seen: set[str] = set()
        for query in queries:
            for hit in self.search_site(site=site, keywords=query):
                if hit["url"] in seen:
                    continue
                if not matcher(hit):
                    continue
                item = self.hit_to_policy_item(hit=hit, site=site)
                if item is None:
                    continue
                seen.add(hit["url"])
                items.append(item)
                if len(items) >= limit:
                    return items
        return items

    def search_site(self, *, site: OfficialSearchSite, keywords: str) -> list[dict[str, Any]]:
        payload = {
            "keywords": keywords,
            "sort": "time",
            "site_id": site.site_id,
            "range": "site",
            "position": "title",
            "page": 1,
            "recommand": 1,
            "gdbsDivision": site.gdbs_division,
            "gdbsOrgNum": site.gdbs_org_num,
            "service_area": site.service_area,
        }
        try:
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                response = client.post(OFFICIAL_SEARCH_API, json=payload)
                response.raise_for_status()
                data = response.json().get("data", {})
                return list(data.get("list", []))
        except Exception:
            return []

    def hit_to_policy_item(self, *, hit: dict[str, Any], site: OfficialSearchSite) -> PolicyItem | None:
        title = self.clean_markup(hit.get("title", ""))
        pub_date = (hit.get("pub_time") or "")[:10]
        url = hit.get("post_url") or hit.get("url") or ""
        if not title or not pub_date or not url:
            return None

        article = self.fetch_article(url)
        summary_points = self.summary_points_for(title=article["title"] or title, content=article["content"], fallback=hit.get("content", ""))
        return PolicyItem(
            policy_year=self.extract_year(pub_date, title),
            level=self.level_for(site=site, title=title),
            title=article["title"] or title,
            pub_date=article["pub_date"] or pub_date,
            source_url=url,
            summary_points=summary_points,
        )

    def level_for(self, *, site: OfficialSearchSite, title: str) -> str:
        if site == self.SONGSHANHU:
            return "松山湖最新相关公开信息"
        if "广东省教育厅" in title:
            return "省级最新上位政策"
        return "东莞市当年相关公开信息"

    def fetch_article(self, url: str) -> dict[str, str]:
        try:
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                text = client.get(url).text
        except Exception:
            return {"title": "", "pub_date": "", "content": ""}
        title_match = ARTICLE_TITLE_RE.search(text)
        date_match = PUB_DATE_RE.search(text)
        content_match = ZOOMCON_RE.search(text)
        content = self.clean_markup(content_match.group(1) if content_match else "")
        return {
            "title": unescape(title_match.group(1)) if title_match else "",
            "pub_date": (date_match.group(1)[:10] if date_match else ""),
            "content": content,
        }

    def summary_points_for(self, *, title: str, content: str, fallback: str) -> list[str]:
        if "进一步规范普通中小学招生入学工作的指导意见" in title:
            return [
                "坚持义务教育免试就近入学",
                "严禁以考试、竞赛、面试、证书等作为招生依据",
                "民办义务教育学校纳入审批地统一管理，与公办学校同步招生",
            ]
        if "义务教育阶段学校招生入学工作指导意见" in title:
            return [
                "保障适龄儿童少年接受义务教育的权利",
                "小学一年级对象为 2019 年 8 月 31 日及以前出生的适龄儿童",
                "公办民办学校同步招生，报名超计划的实行电脑随机录取",
            ]
        if "政府购买民办学校学位服务公开遴选" in title:
            return [
                "松山湖计划通过政府购买民办学校学位补充园区公办学位不足",
                "公告明确了申报时间、材料和遴选要求",
                "这属于补充学位安排，不等同于完整招生实施细则",
            ]
        snippet = compact_snippet(content or self.clean_markup(fallback), limit=180)
        if not snippet:
            return ["请以官方原文为准。"]
        parts = [piece.strip("；。 ") for piece in re.split(r"[；。]", snippet) if piece.strip("；。 ")]
        return parts[:3] or ["请以官方原文为准。"]

    def is_relevant_city_policy(self, hit: dict[str, Any]) -> bool:
        title = self.clean_markup(hit.get("title", ""))
        if "招生" in title and "入学" in title:
            return True
        return "普通中小学" in title and "指导意见" in title

    def is_relevant_songshanhu_policy(self, hit: dict[str, Any]) -> bool:
        title = self.clean_markup(hit.get("title", ""))
        return "松山湖" in title and any(keyword in title for keyword in ("入学", "招生", "学位"))

    def extract_year(self, pub_date: str, title: str) -> int:
        for source in (title, pub_date):
            match = re.search(r"(20\d{2})", source)
            if match:
                return int(match.group(1))
        return date.today().year

    def clean_markup(self, value: str) -> str:
        text = TAG_RE.sub("", value or "")
        text = unescape(text).replace("&nbsp;", " ")
        return SPACE_RE.sub(" ", text).strip()
