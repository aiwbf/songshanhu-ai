from __future__ import annotations

import subprocess

from app.config import Settings
from app.models import AskResponse, ChannelMode, OpenClawMessageRequest, OpenClawMessageResponse
from app.openclaw_security import OpenClawSecurityPolicy
from apps.api.channel_output import render_answer_for_channel


def infer_channel_mode(request: OpenClawMessageRequest) -> ChannelMode:
    if request.channel_mode:
        return request.channel_mode
    return ChannelMode.PRIVATE


def format_answer_as_text(answer: AskResponse, mode: ChannelMode) -> str:
    if answer.answer_payload and answer.escalation_decision:
        return render_answer_for_channel(
            trace_id=answer.trace_id or "",
            answer=answer.answer_payload,
            citations=answer.citations,
            escalation=answer.escalation_decision,
            mode=mode,
        )
    return answer.customer_reply or answer.conclusion


class OpenClawBridge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.script_path = settings.root_dir / "scripts" / "run_openclaw_action.ps1"
        self.policy = OpenClawSecurityPolicy.from_path(settings.openclaw_policy_path)

    def build_command_preview(self, request: OpenClawMessageRequest, reply_text: str) -> str:
        escaped = reply_text.replace("`", "``").replace('"', '`"').replace("\n", "`n")
        return (
            f'powershell -ExecutionPolicy Bypass -File "{self.script_path}" '
            f'-Action send-message -Channel "{request.channel}" -Target "{request.target}" '
            f'-Message "{escaped}" -Json'
        )

    def maybe_send(self, request: OpenClawMessageRequest, reply_text: str, *, delivery_allowed: bool) -> None:
        if request.dry_run or not self.settings.openclaw_enabled or not delivery_allowed:
            return
        subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script_path),
                "-Action",
                "send-message",
                "-Channel",
                request.channel,
                "-Target",
                request.target,
                "-Message",
                reply_text,
                "-Json",
            ],
            check=True,
            cwd=str(self.settings.root_dir),
        )

    def build_response(
        self,
        *,
        request: OpenClawMessageRequest,
        answer: AskResponse,
        conversation_id: str,
    ) -> OpenClawMessageResponse:
        assessment = self.policy.assess_request(request)
        reply_text = format_answer_as_text(answer, infer_channel_mode(request))
        command_preview = self.build_command_preview(request=request, reply_text=reply_text)
        self.maybe_send(
            request=request,
            reply_text=reply_text,
            delivery_allowed=assessment.delivery_allowed,
        )
        answer.command_preview = command_preview
        return OpenClawMessageResponse(
            channel=request.channel,
            target=request.target,
            conversation_id=conversation_id,
            dry_run=request.dry_run,
            reply_text=reply_text,
            command_preview=command_preview,
            answer=answer,
            routing_key=assessment.routing_key,
            delivery_allowed=assessment.delivery_allowed,
            security_findings=[f"{item.status}: {item.title} - {item.detail}" for item in assessment.findings],
        )
