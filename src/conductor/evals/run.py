import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from conductor import ids
from conductor.config import Settings
from conductor.contracts import Escalation
from conductor.events import EventKind, EventLog, RunNotFound
from conductor.llm.model import Model
from conductor.llm.ollama import OllamaModel
from conductor.planning.plan import Planned, plan_request
from conductor.registry import Registry
from conductor.routing.route import Routed, route_request

from .cases import EvalCase

MAX_RUNS = 100
RUNS_MESSAGE = "runs must be 1 to 100"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    runs: int
    consistent: int
    route_ok: int
    plan_ok: int
    args_ok: int | None
    valid: int
    escalated: int
    unavailable: int
    seconds: tuple[float, ...]
    run_ids: tuple[str, ...] = field(default=(), compare=False)


def model_for(settings: Settings) -> Model:
    return OllamaModel(settings.ollama_host, timeout=settings.model_timeout_seconds)


def run_case(
    case: EvalCase,
    registry: Registry,
    *,
    model: Model,
    model_name: str,
    log: EventLog,
    runs: int,
) -> CaseResult:
    if not 1 <= runs <= MAX_RUNS:
        raise ValueError(RUNS_MESSAGE)
    outcomes: list[str] = []
    route_ok = plan_ok = valid = escalated = unavailable = 0
    args_ok: int | None = 0 if case.args is not None else None
    taken: list[float] = []
    run_ids: list[str] = []
    for _ in range(runs):
        run_id = ids.new_id()
        run_ids.append(run_id)
        routed = route_request(
            case.request,
            registry,
            model=model,
            model_name=model_name,
            log=log,
            run_id=run_id,
        )
        planned: Planned | Escalation | None = None
        if isinstance(routed, Routed):
            planned = plan_request(
                routed,
                registry,
                model=model,
                model_name=model_name,
                log=log,
                run_id=run_id,
            )
        outcomes.append(json.dumps(_outcome(routed, planned), sort_keys=True))
        route_right = _route_right(case, routed)
        plan_right = _plan_right(case, planned, route_right)
        route_ok += int(route_right)
        plan_ok += int(plan_right)
        wanted = case.args
        if wanted is not None and plan_right:
            steps = planned.plan.steps
            if len(steps) == len(wanted) and all(
                all(step.args.get(key) == value for key, value in table.items())
                for step, table in zip(steps, wanted, strict=True)
            ):
                args_ok += 1
        kinds = _kinds(routed, planned)
        valid += int("invalid_model_output" not in kinds)
        escalated += int(bool(kinds))
        unavailable += int("model_unavailable" in kinds)
        taken.append(_seconds(log, run_id))
    return CaseResult(
        case.id,
        runs,
        Counter(outcomes).most_common(1)[0][1],
        route_ok,
        plan_ok,
        args_ok,
        valid,
        escalated,
        unavailable,
        tuple(taken),
        tuple(run_ids),
    )


def case_line(result: CaseResult) -> str:
    args = "-" if result.args_ok is None else f"{result.args_ok}/{result.runs}"
    return (
        f"{result.case_id}  consistent {result.consistent}/{result.runs}"
        f"  route {result.route_ok}/{result.runs}  plan {result.plan_ok}/{result.runs}"
        f"  args {args}  valid {result.valid}/{result.runs}"
        f"  escalated {result.escalated}/{result.runs}"
        f"  p50 {_percentile(result.seconds, 0.5):.2f}s"
        f"  p95 {_percentile(result.seconds, 0.95):.2f}s"
    )


def overall_line(results: Sequence[CaseResult]) -> str:
    total = sum(result.runs for result in results)
    with_args = [result for result in results if result.args_ok is not None]
    if with_args:
        counted = [result.args_ok for result in with_args]
        args_runs = sum(result.runs for result in with_args)
        args = f"{sum(counted)}/{args_runs}"
    else:
        args = "-"
    seconds = [second for result in results for second in result.seconds]
    consistent = sum(result.consistent for result in results)
    route = sum(result.route_ok for result in results)
    plan = sum(result.plan_ok for result in results)
    valid = sum(result.valid for result in results)
    escalated = sum(result.escalated for result in results)
    return (
        f"overall  {len(results)} cases  consistent {consistent}/{total}"
        f"  route {route}/{total}  plan {plan}/{total}  args {args}"
        f"  valid {valid}/{total}  escalated {escalated}/{total}"
        f"  p50 {_percentile(seconds, 0.5):.2f}s  p95 {_percentile(seconds, 0.95):.2f}s"
    )


def _outcome(
    routed: Routed | Escalation, planned: Planned | Escalation | None
) -> dict[str, object]:
    if isinstance(routed, Escalation):
        return {"route": f"escalate:{routed.kind}"}
    domain = routed.route.domain
    if isinstance(planned, Escalation):
        return {"route": domain, "plan": f"escalate:{planned.kind}"}
    steps = [[step.action.split(".", 1)[1], step.args] for step in planned.plan.steps]
    return {"route": domain, "plan": steps}


def _route_right(case: EvalCase, routed: Routed | Escalation) -> bool:
    if case.route == "escalate":
        return isinstance(routed, Escalation) and routed.kind == "unknown_route"
    return isinstance(routed, Routed) and routed.route.domain == case.route


def _plan_right(case: EvalCase, planned: Planned | Escalation | None, route_right: bool) -> bool:
    if case.route == "escalate":
        return route_right
    if case.plan == "escalate":
        return route_right and isinstance(planned, Escalation) and planned.kind == "invalid_plan"
    if not route_right or not isinstance(planned, Planned):
        return False
    names = [step.action.split(".", 1)[1] for step in planned.plan.steps]
    return names == list(case.plan)  # type: ignore[arg-type]


def _kinds(routed: Routed | Escalation, planned: Planned | Escalation | None) -> set[str]:
    found: set[str] = set()
    if isinstance(routed, Escalation):
        found.add(routed.kind)
    if isinstance(planned, Escalation):
        found.add(planned.kind)
    return found


def _seconds(log: EventLog, run_id: str) -> float:
    try:
        events = log.read(run_id)
    except RunNotFound:
        return 0.0
    total = 0
    for event in events:
        if event.kind is EventKind.MODEL_REPLY:
            total += int(event.payload["total_ns"])
    return total / 1_000_000_000


def _percentile(values: Sequence[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(share * len(ordered))) - 1]
