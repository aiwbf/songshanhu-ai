from __future__ import annotations

from app.models import (
    AnswerPayload,
    AnswerStatus,
    ChannelMode,
    CitationRef,
    EscalationDecision,
)


def _bullet_list(items: list[str], *, limit: int, fallback: str | None = None) -> list[str]:
    values = [item.strip() for item in items if item and item.strip()][:limit]
    if values:
        return [f"- {item}" for item in values]
    if fallback:
        return [fallback]
    return []


def _citation_lines(citations: list[CitationRef], *, limit: int) -> list[str]:
    if not citations:
        return ["- 暂无可直接引用的条文片段"]
    lines: list[str] = []
    for item in citations[:limit]:
        page = f" / {item.page}" if item.page else ""
        snippet = _clip(item.quote_snippet, 72)
        lines.append(f"- [{item.source_id}] {item.title}{page} / {item.chunk_id}：{snippet}")
    return lines


def _section(title: str, lines: list[str]) -> list[str]:
    values = [line for line in lines if line]
    if not values:
        return []
    return [title, *values, ""]


def _clip(text: str, limit: int) -> str:
    value = text.strip()
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _message_score(text: str) -> float:
    if not text or not text.strip():
        return 10_000

    value = text.strip()
    score = len(value) / 20
    evidence_markers = ("提到：", "（第 ", "申请指南", "/ 42", "第 ", "页）")
    if any(marker in value for marker in evidence_markers):
        score += 100
    if value.startswith("当前问题命中"):
        score += 8
    if value.startswith("信息补齐前"):
        score += 5
    return score


def _primary_message(answer: AnswerPayload) -> str:
    candidates = [answer.initial_conclusion, answer.eligibility_or_issue]
    usable = [item.strip() for item in candidates if item and item.strip()]
    if not usable:
        return ""
    return min(usable, key=_message_score)


def _secondary_message(answer: AnswerPayload, primary: str) -> str:
    candidates = [answer.initial_conclusion, answer.eligibility_or_issue]
    usable = [item.strip() for item in candidates if item and item.strip() and item.strip() != primary.strip()]
    if not usable:
        return ""
    return min(usable, key=_message_score)


def _conclusion_line(answer: AnswerPayload) -> str:
    if answer.status == AnswerStatus.NEED_INFO:
        return _clip(
            answer.initial_conclusion or "现在还不能直接给出资格结论，需要先补充关键信息。",
            90,
        )
    if answer.status == AnswerStatus.HANDOFF:
        return _clip(answer.initial_conclusion or "这类问题建议转人工复核，系统不做强答。", 90)
    if answer.status == AnswerStatus.OUT_OF_SCOPE:
        return _clip(answer.initial_conclusion or "这个问题不在当前招生咨询机器人的处理范围内。", 90)
    primary = _primary_message(answer)
    return _clip(primary or "已根据当前资料给出克制判断。", 90)


def _status_note(answer: AnswerPayload, escalation: EscalationDecision) -> str:
    if answer.status == AnswerStatus.NEED_INFO:
        return "信息还没补齐前，我不会直接判断 A/B/C 或给出确定资格结论。"
    if answer.status == AnswerStatus.HANDOFF:
        return escalation.summary or "这类问题存在较高不确定性，建议人工复核。"
    if answer.status == AnswerStatus.OUT_OF_SCOPE:
        return escalation.summary or "建议改问招生范围内问题，或直接转人工。"
    primary = _conclusion_line(answer)
    secondary = _secondary_message(answer, primary)
    if secondary and _message_score(secondary) < 80:
        return _clip(secondary, 100)
    return "如果要落到你自己的情况，还要结合户籍、房产、工作、学段和平台审核结果继续核验。"


def _next_step_lines(answer: AnswerPayload) -> list[str]:
    if answer.next_actions:
        return _bullet_list(answer.next_actions, limit=3)
    return [f"- {answer.human_support}"]


def _private_sections(
    *,
    answer: AnswerPayload,
    citations: list[CitationRef],
    escalation: EscalationDecision,
) -> list[str]:
    lines: list[str] = []
    lines.extend(_section("【结论】", [_conclusion_line(answer)]))
    lines.extend(_section("【当前判断】", [_status_note(answer, escalation)]))

    if answer.status == AnswerStatus.NEED_INFO:
        lines.extend(
            _section(
                "【还需要你补充】",
                _bullet_list(
                    answer.follow_up_questions,
                    limit=3,
                    fallback="- 请先补充个案关键信息后再继续判断。",
                ),
            )
        )
    elif answer.status == AnswerStatus.HANDOFF:
        lines.extend(
            _section(
                "【建议处理方式】",
                _bullet_list(
                    answer.next_actions,
                    limit=3,
                    fallback="- 这类问题建议直接由人工客服继续跟进。",
                ),
            )
        )
    elif answer.status == AnswerStatus.OUT_OF_SCOPE:
        lines.extend(
            _section(
                "【你可以这样做】",
                _bullet_list(
                    answer.next_actions,
                    limit=3,
                    fallback="- 请改问报名资格、材料、平台操作、审核流程等招生相关问题。",
                ),
            )
        )
    else:
        lines.extend(_section("【下一步】", _next_step_lines(answer)))

    lines.extend(
        _section(
            "【判断依据】",
            _bullet_list(
                [_clip(item, 140) for item in answer.judgement_basis],
                limit=3,
                fallback="- 当前未提取到可展示的判断依据。",
            ),
        )
    )

    if answer.required_materials:
        lines.extend(_section("【材料清单】", _bullet_list(answer.required_materials, limit=4)))

    if answer.status == AnswerStatus.NEED_INFO and answer.next_actions:
        lines.extend(_section("【下一步】", _next_step_lines(answer)))

    risk_lines = _bullet_list(answer.risk_alerts, limit=3)
    if answer.status in {AnswerStatus.HANDOFF, AnswerStatus.OUT_OF_SCOPE} and escalation.summary:
        risk_lines = [f"- {escalation.summary}", *risk_lines][:3]
    if risk_lines:
        lines.extend(_section("【风险提醒】", risk_lines))

    lines.extend(_section("【人工协助】", [answer.human_support]))
    lines.extend(_section("【引用】", _citation_lines(citations, limit=3)))
    return lines


def _group_sections(answer: AnswerPayload, escalation: EscalationDecision) -> list[str]:
    lines: list[str] = []
    lines.extend(_section("【结论】", [_conclusion_line(answer)]))

    if answer.status == AnswerStatus.NEED_INFO:
        lines.extend(
            _section(
                "【请私聊补充】",
                _bullet_list(
                    answer.follow_up_questions,
                    limit=3,
                    fallback="- 请补充孩子户籍、家长工作地、房产情况。",
                ),
            )
        )
    elif answer.status == AnswerStatus.HANDOFF:
        lines.extend(_section("【原因】", [escalation.summary or "这类问题建议人工复核。"]))
    elif answer.status == AnswerStatus.OUT_OF_SCOPE:
        lines.extend(_section("【说明】", [escalation.summary or "当前群聊只处理招生咨询相关问题。"]))
    else:
        lines.extend(
            _section(
                "【下一步】",
                [answer.next_actions[0]] if answer.next_actions else [answer.human_support],
            )
        )

    lines.extend(_section("【人工】", [answer.human_support]))
    return lines


def _admin_sections(
    *,
    trace_id: str,
    answer: AnswerPayload,
    citations: list[CitationRef],
    escalation: EscalationDecision,
) -> list[str]:
    lines: list[str] = []
    lines.extend(
        _section(
            "【会话信息】",
            [
                f"- Trace ID：{trace_id}",
                f"- 状态：{answer.status.value}",
                f"- 问题类型：{answer.question_type}",
                f"- 置信度：{escalation.confidence:.2f}",
                f"- 转接动作：{escalation.action.value}",
            ],
        )
    )
    lines.extend(_section("【结论】", [_conclusion_line(answer)]))
    lines.extend(_section("【当前判断】", [_status_note(answer, escalation)]))
    lines.extend(
        _section(
            "【判断依据】",
            _bullet_list(
                [_clip(item, 160) for item in answer.judgement_basis],
                limit=4,
                fallback="- 暂无可展示依据",
            ),
        )
    )
    lines.extend(_section("【引用】", _citation_lines(citations, limit=4)))
    lines.extend(
        _section(
            "【转接原因】",
            _bullet_list(escalation.reasons, limit=4, fallback="- 无"),
        )
    )
    lines.extend(_section("【人工协助】", [answer.human_support]))
    return lines


def render_answer_for_channel(
    *,
    trace_id: str,
    answer: AnswerPayload,
    citations: list[CitationRef],
    escalation: EscalationDecision,
    mode: ChannelMode,
) -> str:
    if mode == ChannelMode.GROUP:
        sections = _group_sections(answer, escalation)
    elif mode == ChannelMode.ADMIN:
        sections = _admin_sections(
            trace_id=trace_id,
            answer=answer,
            citations=citations,
            escalation=escalation,
        )
    else:
        sections = _private_sections(
            answer=answer,
            citations=citations,
            escalation=escalation,
        )

    while sections and not sections[-1]:
        sections.pop()
    return "\n".join(sections)
