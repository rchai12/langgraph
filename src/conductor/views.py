import json
from datetime import datetime

from conductor.store import StoredApproval, StoredEscalation

_WHEN = "%Y-%m-%dT%H:%M:%SZ"


def _when(moment: datetime) -> str:
    return moment.strftime(_WHEN)


def _args(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def request_lines(stored: StoredApproval) -> tuple[str, ...]:
    request = stored.request
    decision = stored.decision
    if decision is None:
        status = "pending"
    else:
        word = {"approve": "approved", "reject": "rejected", "edit": "edited"}[decision.verdict]
        status = (
            f"{word} by {decision.decided_by} ({decision.channel}) at {_when(decision.decided_at)}"
        )
    lines = [
        f"approval {request.approval_id}  {request.stage}  {status}",
        f"run {request.run_id}  requested {_when(request.requested_at)}",
    ]
    for step in request.steps:
        lines.append(f"  {step.number}. {step.action}  {step.effect}  {_args(step.args)}")
    if decision is not None and decision.verdict == "edit":
        lines.append(f"edited args: {_args(decision.edited_args)}")
    if decision is not None and decision.note:
        lines.append(f"note: {decision.note}")
    return tuple(lines)


def escalation_lines(stored: StoredEscalation) -> tuple[str, ...]:
    escalation = stored.escalation
    answer = stored.answer
    if answer is None:
        status = "open"
    else:
        status = (
            f"{answer.answer} by {answer.decided_by} ({answer.channel})"
            f" at {_when(answer.answered_at)}"
        )
    lines = [
        f"escalation {stored.escalation_id}  {escalation.kind}  {status}",
        f"run {escalation.run_id}  raised {_when(stored.raised_at)}",
        escalation.detail,
    ]
    for problem in escalation.problems:
        lines.append(f"  {problem.loc}: {problem.code}")
    if answer is not None and answer.note:
        lines.append(f"note: {answer.note}")
    return tuple(lines)
