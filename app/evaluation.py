from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.assistant import AdmissionsAssistant
from app.config import get_settings
from app.knowledge import KnowledgeStore
from app.models import AskRequest, AskResponse, OpenClawMessageRequest
from app.openclaw_bridge import OpenClawBridge
from app.openclaw_security import OpenClawSecurityPolicy
from app.rules import RuleEngine
from scripts.build_knowledge import build_knowledge


DIRECTNESS_RANK = {
    "out_of_scope": 0,
    "handoff": 1,
    "need_info": 2,
    "answered": 3,
}


def build_assistant() -> AdmissionsAssistant:
    settings = get_settings()
    if not settings.knowledge_path.exists():
        build_knowledge(root=settings.root_dir, output_path=settings.knowledge_path)
    return AdmissionsAssistant(
        settings=settings,
        rules=RuleEngine.from_path(settings.rules_path),
        knowledge=KnowledgeStore.from_path(settings.knowledge_path),
        synthesizer=None,
    )


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("cases", []))


def load_failure_modes(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("failure_modes", [])
    return {item["id"]: item for item in items}


def evaluate_dataset(
    *,
    dataset_path: Path,
    failure_modes_path: Path,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    assistant = build_assistant()
    cases = load_cases(dataset_path)
    failure_mode_library = load_failure_modes(failure_modes_path)
    results = [evaluate_case(assistant=assistant, case=case) for case in cases]
    summary = summarize_results(
        dataset_path=dataset_path,
        results=results,
        failure_mode_library=failure_mode_library,
        policy_path=policy_path,
    )
    return summary


def evaluate_case(*, assistant: AdmissionsAssistant, case: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    mode = case.get("request_mode", "ask")
    transport: dict[str, Any] = {}
    if mode == "openclaw":
        openclaw_request = OpenClawMessageRequest(
            channel=case.get("channel", "feishu"),
            target=case.get("target", "oc_test"),
            message=case["question"],
            facts=case.get("facts") or {},
            prefer_llm=bool(case.get("prefer_llm", False)),
            dry_run=bool(case.get("dry_run", True)),
            conversation_id=case.get("conversation_id"),
            source_session_id=case.get("source_session_id"),
            channel_mode=case.get("channel_mode", "private"),
            sender_id=case.get("sender_id"),
            thread_id=case.get("thread_id"),
            mentioned=bool(case.get("mentioned", False)),
            paired=bool(case.get("paired", False)),
            is_group=bool(case.get("is_group", False)),
        )
        response = assistant.answer(
            AskRequest(
                question=openclaw_request.message,
                facts=openclaw_request.facts,
                prefer_llm=openclaw_request.prefer_llm,
                top_k=int(case.get("top_k", 5)),
                channel=openclaw_request.channel,
                channel_mode=openclaw_request.channel_mode,
                entry_point="eval_openclaw",
                source_session_id=openclaw_request.source_session_id,
                source_target=openclaw_request.target,
                is_openclaw=True,
            )
        )
        bridge = OpenClawBridge(settings)
        bridge_response = bridge.build_response(
            request=openclaw_request,
            answer=response,
            conversation_id=openclaw_request.conversation_id or "eval-openclaw",
        )
        transport = {
            "delivery_allowed": bridge_response.delivery_allowed,
            "routing_key": bridge_response.routing_key or "",
            "security_findings": list(bridge_response.security_findings),
        }
    else:
        request = AskRequest(
            question=case["question"],
            facts=case.get("facts") or {},
            prefer_llm=bool(case.get("prefer_llm", False)),
            top_k=int(case.get("top_k", 5)),
        )
        response = assistant.answer(request)
    expectation = case.get("expect", {})
    combined_text = join_response_text(response)
    evidence_files = [item.file_name for item in response.evidence]
    evidence_citations = [item.citation for item in response.evidence]
    evidence_tiers = [item.source_tier for item in response.evidence]

    checks: dict[str, bool] = {}
    failed_checks: list[str] = []

    allowed_statuses = expectation.get("allowed_statuses", [])
    if allowed_statuses:
        checks["status"] = response.status.value in allowed_statuses
        if not checks["status"]:
            failed_checks.append(f"status expected one of {allowed_statuses}, got {response.status.value}")

    expected_question_type = expectation.get("question_type")
    if expected_question_type:
        checks["question_type"] = response.question_type == expected_question_type
        if not checks["question_type"]:
            failed_checks.append(f"question_type expected {expected_question_type}, got {response.question_type}")

    expected_labels = expectation.get("expected_labels", [])
    if expected_labels:
        missing = [label for label in expected_labels if label not in combined_text]
        checks["expected_labels"] = not missing
        if missing:
            failed_checks.append(f"missing expected labels: {missing}")

    forbidden_labels = expectation.get("forbidden_labels", [])
    if forbidden_labels:
        present = [label for label in forbidden_labels if label in combined_text]
        checks["forbidden_labels"] = not present
        if present:
            failed_checks.append(f"forbidden labels present: {present}")

    required_terms = expectation.get("required_terms", [])
    if required_terms:
        missing = [term for term in required_terms if term not in combined_text]
        checks["required_terms"] = not missing
        if missing:
            failed_checks.append(f"missing required terms: {missing}")

    forbidden_terms = expectation.get("forbidden_terms", [])
    if forbidden_terms:
        present = [term for term in forbidden_terms if term in combined_text]
        checks["forbidden_terms"] = not present
        if present:
            failed_checks.append(f"forbidden terms present: {present}")

    forbidden_patterns = expectation.get("forbidden_patterns", [])
    if forbidden_patterns:
        matched = [pattern for pattern in forbidden_patterns if re.search(pattern, combined_text)]
        checks["forbidden_patterns"] = not matched
        if matched:
            failed_checks.append(f"forbidden patterns matched: {matched}")

    required_missing_fields = expectation.get("required_missing_fields", [])
    if required_missing_fields:
        missing = [field for field in required_missing_fields if field not in response.missing_fields]
        checks["required_missing_fields"] = not missing
        if missing:
            failed_checks.append(f"missing follow-up fields: {missing}")

    if "expect_any_evidence" in expectation:
        expected = bool(expectation["expect_any_evidence"])
        checks["expect_any_evidence"] = bool(response.evidence) == expected
        if not checks["expect_any_evidence"]:
            failed_checks.append(f"expect_any_evidence expected {expected}, got {bool(response.evidence)}")

    expected_evidence_files = expectation.get("expected_evidence_file_terms", [])
    if expected_evidence_files:
        missing = [
            term for term in expected_evidence_files
            if not any(term in file_name for file_name in evidence_files)
        ]
        checks["expected_evidence_file_terms"] = not missing
        if missing:
            failed_checks.append(f"evidence file terms not found: {missing}")

    expected_citations = expectation.get("expected_citation_terms", [])
    if expected_citations:
        missing = [
            term for term in expected_citations
            if not any(term in citation for citation in evidence_citations)
        ]
        checks["expected_citation_terms"] = not missing
        if missing:
            failed_checks.append(f"citation terms not found: {missing}")

    max_source_tier = expectation.get("max_source_tier")
    if max_source_tier is not None:
        checks["max_source_tier"] = bool(evidence_tiers) and max(evidence_tiers) <= int(max_source_tier)
        if not checks["max_source_tier"]:
            failed_checks.append(f"source tier exceeds max {max_source_tier}: {evidence_tiers}")

    expected_delivery_allowed = expectation.get("delivery_allowed")
    if expected_delivery_allowed is not None:
        checks["delivery_allowed"] = transport.get("delivery_allowed") == bool(expected_delivery_allowed)
        if not checks["delivery_allowed"]:
            failed_checks.append(
                f"delivery_allowed expected {bool(expected_delivery_allowed)}, got {transport.get('delivery_allowed')}"
            )

    required_security_terms = expectation.get("required_security_terms", [])
    if required_security_terms:
        joined_findings = "\n".join(transport.get("security_findings", []))
        missing = [term for term in required_security_terms if term not in joined_findings]
        checks["required_security_terms"] = not missing
        if missing:
            failed_checks.append(f"security findings missing: {missing}")

    required_routing_key_terms = expectation.get("required_routing_key_terms", [])
    if required_routing_key_terms:
        routing_key = transport.get("routing_key", "")
        missing = [term for term in required_routing_key_terms if term not in routing_key]
        checks["required_routing_key_terms"] = not missing
        if missing:
            failed_checks.append(f"routing key terms missing: {missing}")

    followup_expected = bool(expectation.get("followup_expected", False) or required_missing_fields)
    followup_pass = True
    if followup_expected:
        followup_pass = response.status.value == "need_info" and checks.get("required_missing_fields", True)
        if not followup_pass:
            failed_checks.append("necessary follow-up not triggered correctly")

    handoff_expected = bool(expectation.get("handoff_expected", False))
    handoff_pass = True
    if handoff_expected:
        handoff_pass = response.status.value == "handoff"
        if not handoff_pass:
            failed_checks.append("expected handoff but response did not hand off")

    timeliness_expected = bool(expectation.get("timeliness_guard_expected", False))
    timeliness_pass = True
    if timeliness_expected:
        timeliness_pass = has_timeliness_guard(response)
        if not timeliness_pass:
            failed_checks.append("timeliness guard missing")

    hallucination_reasons = detect_hallucination(case=case, response=response, combined_text=combined_text)

    classification_considered = bool(
        expected_question_type or expected_labels or forbidden_labels or allowed_statuses
    )
    classification_pass = all(
        checks.get(name, True)
        for name in ("status", "question_type", "expected_labels", "forbidden_labels")
        if name in checks
    )
    citation_considered = bool(
        "expect_any_evidence" in expectation
        or expected_evidence_files
        or expected_citations
        or max_source_tier is not None
    )
    citation_pass = all(
        checks.get(name, True)
        for name in (
            "expect_any_evidence",
            "expected_evidence_file_terms",
            "expected_citation_terms",
            "max_source_tier",
            "delivery_allowed",
            "required_security_terms",
            "required_routing_key_terms",
        )
        if name in checks
    )

    overall_pass = not failed_checks and not hallucination_reasons
    return {
        "id": case["id"],
        "suite": case.get("suite", "regression"),
        "topic": case.get("topic", ""),
        "coverage_tags": case.get("coverage_tags", []),
        "release_blocker": bool(case.get("release_blocker", False)),
        "failure_mode_ids": case.get("failure_mode_ids", []),
        "question": case["question"],
        "response": response.model_dump(mode="json"),
        "transport": transport,
        "checks": checks,
        "failed_checks": failed_checks,
        "classification_considered": classification_considered,
        "classification_pass": classification_pass,
        "followup_considered": followup_expected,
        "followup_pass": followup_pass,
        "citation_considered": citation_considered,
        "citation_pass": citation_pass,
        "timeliness_considered": timeliness_expected,
        "timeliness_pass": timeliness_pass,
        "handoff_considered": handoff_expected,
        "handoff_pass": handoff_pass,
        "hallucination": bool(hallucination_reasons),
        "hallucination_reasons": hallucination_reasons,
        "overall_pass": overall_pass,
    }


def summarize_results(
    *,
    dataset_path: Path,
    results: list[dict[str, Any]],
    failure_mode_library: dict[str, dict[str, Any]],
    policy_path: Path | None,
) -> dict[str, Any]:
    total = len(results)
    overall_pass = sum(1 for item in results if item["overall_pass"])
    classification_cases = [item for item in results if item["classification_considered"]]
    followup_cases = [item for item in results if item["followup_considered"]]
    citation_cases = [item for item in results if item["citation_considered"]]
    timeliness_cases = [item for item in results if item["timeliness_considered"]]
    handoff_cases = [item for item in results if item["handoff_considered"]]
    hallucination_cases = [item for item in results if item["overall_pass"] or item["hallucination"] or item["failed_checks"]]

    release_blockers = [item for item in results if item["release_blocker"] and not item["overall_pass"]]
    failure_mode_counts: dict[str, int] = {}
    for item in results:
        if item["overall_pass"]:
            continue
        for failure_mode_id in item["failure_mode_ids"]:
            failure_mode_counts[failure_mode_id] = failure_mode_counts.get(failure_mode_id, 0) + 1

    ranked_failure_modes = [
        {
            "id": failure_mode_id,
            "title": failure_mode_library.get(failure_mode_id, {}).get("title", failure_mode_id),
            "count": count,
        }
        for failure_mode_id, count in sorted(
            failure_mode_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    policy_audit = None
    if policy_path is not None and policy_path.exists():
        policy = OpenClawSecurityPolicy.from_path(policy_path)
        policy_audit = [item.__dict__ for item in policy.audit()]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path),
        "total_cases": total,
        "overall_pass_rate": ratio(overall_pass, total),
        "metrics": {
            "classification_accuracy": ratio(sum(1 for item in classification_cases if item["classification_pass"]), len(classification_cases)),
            "necessary_followup_accuracy": ratio(sum(1 for item in followup_cases if item["followup_pass"]), len(followup_cases)),
            "citation_correctness": ratio(sum(1 for item in citation_cases if item["citation_pass"]), len(citation_cases)),
            "hallucination_rate": ratio(sum(1 for item in hallucination_cases if item["hallucination"]), len(hallucination_cases)),
            "timeliness_risk_miss_rate": ratio(sum(1 for item in timeliness_cases if not item["timeliness_pass"]), len(timeliness_cases)),
            "handoff_miss_rate": ratio(sum(1 for item in handoff_cases if not item["handoff_pass"]), len(handoff_cases)),
        },
        "release_blockers": release_blockers,
        "top_failure_modes": ranked_failure_modes[:10],
        "policy_audit": policy_audit,
        "results": results,
    }


def write_report(summary: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")


def render_markdown(summary: dict[str, Any]) -> str:
    metrics = summary["metrics"]
    lines = [
        "# Eval Report",
        "",
        f"- Generated at: {summary['generated_at']}",
        f"- Dataset: `{summary['dataset_path']}`",
        f"- Total cases: {summary['total_cases']}",
        f"- Overall pass rate: {format_pct(summary['overall_pass_rate'])}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| 分类准确率 | {format_pct(metrics['classification_accuracy'])} |",
        f"| 必要追问准确率 | {format_pct(metrics['necessary_followup_accuracy'])} |",
        f"| 引用正确率 | {format_pct(metrics['citation_correctness'])} |",
        f"| 幻觉率 | {format_pct(metrics['hallucination_rate'])} |",
        f"| 时效风险漏报率 | {format_pct(metrics['timeliness_risk_miss_rate'])} |",
        f"| 人工转接漏判率 | {format_pct(metrics['handoff_miss_rate'])} |",
        "",
        "## Release Blockers",
        "",
    ]

    blockers = summary.get("release_blockers", [])
    if blockers:
        for item in blockers:
            lines.append(
                f"- `{item['id']}` [{item['response']['status']}] failed: {', '.join(item['failed_checks'] or item['hallucination_reasons'])}"
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Failure Modes",
            "",
        ]
    )
    failure_modes = summary.get("top_failure_modes", [])
    if failure_modes:
        for item in failure_modes:
            lines.append(f"- `{item['id']}` {item['title']} ({item['count']})")
    else:
        lines.append("- None")

    policy_audit = summary.get("policy_audit")
    if policy_audit is not None:
        lines.extend(
            [
                "",
                "## OpenClaw Security Audit",
                "",
                "| Check | Status | Detail |",
                "| --- | --- | --- |",
            ]
        )
        for item in policy_audit:
            lines.append(f"| {item['title']} | {item['status']} | {item['detail']} |")

    lines.extend(
        [
            "",
            "## Case Details",
            "",
            "| Case | Topic | Status | Pass | Notes |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in summary["results"]:
        notes = "; ".join(item["failed_checks"] or item["hallucination_reasons"]) or "ok"
        lines.append(
            f"| `{item['id']}` | {item['topic'] or '-'} | {item['response']['status']} | {'pass' if item['overall_pass'] else 'fail'} | {notes} |"
        )
    lines.append("")
    return "\n".join(lines)


def detect_hallucination(*, case: dict[str, Any], response: AskResponse, combined_text: str) -> list[str]:
    expectation = case.get("expect", {})
    reasons: list[str] = []

    max_safe_status = expectation.get("hallucination_safe_max_status")
    if max_safe_status:
        actual_rank = DIRECTNESS_RANK.get(response.status.value, -1)
        allowed_rank = DIRECTNESS_RANK.get(max_safe_status, -1)
        if actual_rank > allowed_rank:
            reasons.append(f"response too assertive: allowed <= {max_safe_status}, got {response.status.value}")

    forbidden_terms = expectation.get("hallucination_forbidden_terms", [])
    matched_terms = [term for term in forbidden_terms if term in combined_text]
    if matched_terms:
        reasons.append(f"hallucination forbidden terms present: {matched_terms}")

    if expectation.get("expect_any_evidence") and response.status.value == "answered" and not response.evidence:
        reasons.append("answered without evidence")

    return reasons


def has_timeliness_guard(response: AskResponse) -> bool:
    text = join_response_text(response)
    markers = ("2024", "2025", "2026", "最新政策", "当前", "时效", "不能把 2024", "无法确认")
    return any(marker in text for marker in markers)


def join_response_text(response: AskResponse) -> str:
    parts = [
        response.status.value,
        response.question_type,
        response.conclusion,
        response.consultation_advice,
        response.cannot_confirm_reason,
        response.next_step,
        response.customer_reply,
        response.handoff_message,
        *response.missing_fields,
        *response.risk_notice,
        *[item.file_name for item in response.evidence],
        *[item.citation for item in response.evidence],
        *[item.snippet for item in response.evidence],
    ]
    return "\n".join(str(item) for item in parts if item)


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"
