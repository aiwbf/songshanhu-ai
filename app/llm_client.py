from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.models import AnswerStatus, StudentFacts
from app.rules import find_json_object


class SynthesizedPayload(BaseModel):
    status: Literal["answered", "need_info", "handoff"]
    question_type: str
    initial_conclusion: str
    eligibility_or_issue: str
    judgement_basis: list[str] = Field(default_factory=list)
    required_materials: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    risk_alerts: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


@dataclass
class LLMSynthesizer:
    settings: Settings
    system_prompt: str

    def synthesize(
        self,
        *,
        question: str,
        question_type: str,
        facts: StudentFacts,
        draft_answer: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> SynthesizedPayload | None:
        if not self.settings.llm_enabled:
            return None

        evidence_payload = []
        for index, item in enumerate(evidence, start=1):
            evidence_id = f"EV{index}"
            evidence_payload.append(
                {
                    "evidence_id": evidence_id,
                    "source_id": item["source_id"],
                    "file_name": item["file_name"],
                    "source_tier": item["source_tier"],
                    "citation": item["citation"],
                    "snippet": item["snippet"],
                }
            )

        user_prompt = json.dumps(
            {
                "question": question,
                "question_type": question_type,
                "knowledge_year": self.settings.knowledge_year,
                "facts": facts.model_dump(mode="json"),
                "draft_answer": draft_answer,
                "evidence": evidence_payload,
            },
            ensure_ascii=False,
            indent=2,
        )

        text = self._request_completion(user_prompt=user_prompt)
        if not text:
            return None

        try:
            payload = json.loads(find_json_object(text))
            parsed = SynthesizedPayload.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            return None

        valid_ids = {item["evidence_id"] for item in evidence_payload}
        if any(evidence_id not in valid_ids for evidence_id in parsed.evidence_ids):
            return None

        expected_status = draft_answer.get("status")
        if expected_status and parsed.status != expected_status:
            return None

        return self._normalize(parsed, fallback_status=expected_status)

    def _request_completion(self, *, user_prompt: str) -> str:
        payload = {
            "model": self.settings.default_model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": (
                        "请把下面这次招生咨询改写成更自然、直接、可追溯的客服回答草案。"
                        "只能使用给定 evidence，不能新增任何未被证据支持的事实。"
                        "输出必须是 JSON，并且字段必须严格对应 system prompt 里的要求。\n"
                        f"{user_prompt}"
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 1400,
        }
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.settings.llm_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        choices = body.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "".join(parts).strip()
        return str(content or "").strip()

    def _normalize(
        self,
        payload: SynthesizedPayload,
        *,
        fallback_status: str | None,
    ) -> SynthesizedPayload:
        status = payload.status
        if fallback_status in {item.value for item in AnswerStatus} and status != fallback_status:
            status = fallback_status  # pragma: no cover

        judgement_basis = [item.strip() for item in payload.judgement_basis if item and item.strip()][:4]
        required_materials = [item.strip() for item in payload.required_materials if item and item.strip()][:5]
        next_actions = [item.strip() for item in payload.next_actions if item and item.strip()][:4]
        risk_alerts = [item.strip() for item in payload.risk_alerts if item and item.strip()][:4]
        follow_up_questions = [item.strip() for item in payload.follow_up_questions if item and item.strip()][:3]

        if status != "need_info":
            follow_up_questions = []
        if status == "need_info" and not follow_up_questions:
            return payload.model_copy(update={"status": "need_info", "follow_up_questions": []})

        return payload.model_copy(
            update={
                "status": status,
                "question_type": payload.question_type.strip() or "招生咨询",
                "initial_conclusion": payload.initial_conclusion.strip(),
                "eligibility_or_issue": payload.eligibility_or_issue.strip(),
                "judgement_basis": judgement_basis,
                "required_materials": required_materials,
                "next_actions": next_actions,
                "risk_alerts": risk_alerts,
                "follow_up_questions": follow_up_questions,
                "evidence_ids": payload.evidence_ids[:4],
            }
        )
