# Phase 3c: decide()

## Goal

The one function through which the agent asks a model anything, and the end of Phase 3:

- `conductor.llm.decide` (critical): `decide(point, inputs, ...)` builds the request (3a), reads the model's digest and capabilities (3b), asks for thinking only when both the point and the model want it, logs the full request, calls the model, logs the raw reply and its reasoning, and returns the output parsed strictly into the point's contract, or raises;
- two errors and nothing in between: `InvalidModelOutput` (a cut-off reply, or one that does not fit the contract: problem codes only, never values) and `ModelUnavailable` (3b, passed on after it is logged). Neither is retried;
- `escalation_for(error, run_id)`: the `Escalation` (2a) for either error, ready for the graph (Phase 5), with the new kind `model_unavailable`.

Decided with the owner (2026-11-08): escalations are built here; a point that asks for thinking on a model without the `thinking` capability **runs without it and the log says so** (model agnostic); no command to try a point against the real model yet (`conductor ask`, Phase 5, is the first real run).

## Read first

- `docs/phase-conventions.md`, `AGENTS.md`, `docs/architecture.md` ("Model client", "Determinism")
- `src/conductor/llm/points.py` (3a), `src/conductor/llm/model.py` and `scripted.py` (3b), `src/conductor/events.py` (`EventLog`, `EventKind`), `src/conductor/contracts/escalations.py` (`Escalation`, `FieldProblem`, `problems_from`)

## Starting state

Phase 3b is built and committed: N is `282`. **Sections: core.** No `decide.py` exists. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/llm/decide.py` | `INVALID_OUTPUT_MESSAGE`, `RETRY_HINT`, `InvalidModelOutput`, `Decision`, `decide`, `escalation_for` (critical) |
| `src/conductor/contracts/escalations.py` | append `"model_unavailable"` as the last value of `EscalationKind` |
| `tests/unit/test_contracts_tasks.py` | given edit: add the line `"model_unavailable",` after `"rejected",` in `test_the_closed_sets` (the only change) |
| `scripts/critical_modules.txt` | add the line `llm/decide.py` after `plancheck.py` |
| `docs/testing.md` | under "Critical modules", add `` - `llm/decide.py` (every model call: validation and its record; Phase 3c) `` after the `plancheck.py` line |
| `tests/unit/test_decide.py` | given |
| `tests/unit/test_decide_more.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- Retrying anything, repairing a reply, or falling back to another model.
- The graph, routing or planning points, `conductor ask`, any command (Phase 5).
- Reading settings inside `decide` (the caller passes the model and its name); building an `OllamaModel` from settings.
- A new `EventKind`, or any other change to `conductor.events`; a success event after the reply (the reply event is the record).
- Changes to `points.py`, `prompts.py`, `model.py`, `ollama.py`, `scripted.py`, or to any contract besides the one `EscalationKind` value.

## Dependencies

None new.

## Design

```python
# conductor/llm/decide.py
INVALID_OUTPUT_MESSAGE = "the model's reply does not fit the decision point"
RETRY_HINT = "retry when Ollama answers"

class InvalidModelOutput(Exception):
    def __init__(self, decision_id: str, problems: tuple[FieldProblem, ...]) -> None: ...
    decision_id: str
    problems: tuple[FieldProblem, ...]
    # str() is INVALID_OUTPUT_MESSAGE

@dataclass(frozen=True)
class Decision:
    decision_id: str           # goes into Route.decision_id and the like (Phase 5)
    output: Contract           # an instance of point.output

def decide(
    point: DecisionPoint,
    inputs: Contract,
    *,
    fields: Mapping[str, str],
    model: Model,
    model_name: str,
    log: EventLog,
    run_id: str,
    node: str | None = None,
) -> Decision: ...

def escalation_for(error: InvalidModelOutput | ModelUnavailable, run_id: str) -> Escalation: ...
```

The events, each appended with `node=node` (payload keys exactly these):

| When | Kind | Payload |
|---|---|---|
| before the chat | `MODEL_REQUEST` | `decision_id`, `point`, `template`, `template_sha256`, `model` (the name asked for), `model_listed_as` (`ModelInfo.name`), `digest`, `think_requested` (`point.think`), `think` (what was sent), `body` (`request.body()` as sent) |
| after the chat | `MODEL_REPLY` | `decision_id`, `content`, `thinking`, `done_reason`, and the six counts and durations of `ModelReply` under their field names |
| a reply that does not fit | `ERROR` | `decision_id`, `point`, `error` = `"invalid_model_output"`, `problems` = a list of `{"loc", "code"}` |
| `ModelUnavailable` from either call | `ERROR` | `decision_id`, `point`, `error` = `"model_unavailable"`, `code`, `status` |

### Facts (from a spike: Pydantic 2.14, the demo point)

`PickOutput.from_json` (strict) gives, through `problems_from`: `{"action": "send"}` and `{"action": null}` → `action` `literal_error`; `not json`, `""`, and `{"action": "echo"} trailing` → `""` `json_invalid`; `["echo"]` → `""` `model_type`; an extra key `extra` → `extra` `extra_forbidden`; `{}` → `action` `missing`. A trailing newline after valid JSON is accepted.

## Requirements

- **R1.** `decide` first calls `build_request(point, inputs, model=model_name, fields=fields)`; a `PromptError` passes through before any id is made or anything is logged.
- **R2.** It then takes `decision_id = ids.new_id()` (through the module) and calls `model.model_info(model_name)` once, on every call (no cache).
- **R3.** `think` is `point.think and "thinking" in info.capabilities`; the request sent is the built one with `think` replaced (`dataclasses.replace`). The `MODEL_REQUEST` event is appended before `model.chat` is called, with `body` from the request actually sent.
- **R4.** After `model.chat` returns, the `MODEL_REPLY` event is appended before the reply is checked, so a reply that later fails is still on record whole.
- **R5.** A `done_reason` other than `"stop"` gives the single problem `FieldProblem(loc="reply", code="cut_off")`, without parsing. Otherwise the content is parsed with `point.output.from_json(reply.content)`; a `ValidationError` gives `problems_from(error)`. Either way the `ERROR` event is appended and `InvalidModelOutput(decision_id, problems)` raised; `str()` of it is `INVALID_OUTPUT_MESSAGE`.
- **R6.** A `ModelUnavailable` from `model_info` or from `chat` is logged as its `ERROR` event and raised again, the very object. Any other exception (a `ScriptError`, a failing log) passes through unlogged.
- **R7.** With no problem, `decide` returns `Decision(decision_id, output)`. Nothing is retried, repaired, or defaulted anywhere: one `chat` per `decide`.
- **R8.** `escalation_for` returns, for `InvalidModelOutput`, `Escalation(kind="invalid_model_output", detail=f"decision {decision_id}: {INVALID_OUTPUT_MESSAGE}", run_id=run_id, problems=error.problems)`; for `ModelUnavailable`, `Escalation(kind="model_unavailable", detail=f"{error}; {RETRY_HINT}", run_id=run_id)`. `EscalationKind` ends with `"model_unavailable"`.
- **R9.** No message, problem, or `ERROR` event holds anything from the reply's content or thinking, the inputs, or `str()` of a `ValidationError`. The reply and the request are logged only in their own events (R3, R4).
- **R10.** `decide.py` imports only the standard library, `pydantic` (for `ValidationError`), `conductor.contracts`, `conductor.events`, `conductor.ids` (as `from conductor import ids`), and `conductor.llm` modules; it never reads settings, the clock, or the environment, and never calls `model_validate`.

## Given tests

19 tests in `tests/unit/test_decide.py` (counting each parameter set), plus the one-line given edit to `tests/unit/test_contracts_tasks.py`. Do not change them; if one fails, the code is wrong.

```python
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock, ids
from conductor.contracts import Escalation, FieldProblem
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.llm.decide import (
    INVALID_OUTPUT_MESSAGE,
    Decision,
    InvalidModelOutput,
    decide,
    escalation_for,
)
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.points import build_request
from conductor.llm.prompts import PromptError, load_template
from conductor.llm.scripted import SCRIPTED_INFO, ScriptedModel, ScriptedReply

RUN = "a" * 32
DECISION = "d" * 32
MODEL = "test-model:1b"
PLAIN = ModelInfo(name="plain:latest", digest="b" * 64, capabilities=("completion",))


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 8, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: DECISION)


def run(model, log: EventLog, *, point=demo.PICK, node: str | None = "route"):
    return decide(
        point,
        demo.PickInputs(request="Please repeat: hello"),
        fields=demo.pick_fields(),
        model=model,
        model_name=MODEL,
        log=log,
        run_id=RUN,
        node=node,
    )


def body(think: bool) -> dict[str, object]:
    built = build_request(
        demo.PICK,
        demo.PickInputs(request="Please repeat: hello"),
        model=MODEL,
        fields=demo.pick_fields(),
    )
    return replace(built, think=think).body()


def scripted(content: str, **reply: object) -> ScriptedModel:
    return ScriptedModel([ScriptedReply("demo_pick", ModelReply(content=content, **reply))])


def test_a_decision(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    model = scripted('{"action": "echo"}', thinking="It asks to repeat.")
    decision = run(model, log)
    assert decision == Decision(decision_id=DECISION, output=demo.PickOutput(action="echo"))
    assert [request.think for request in model.requests] == [True]
    events = log.read(RUN)
    assert [(event.kind, event.node) for event in events] == [
        (EventKind.MODEL_REQUEST, "route"),
        (EventKind.MODEL_REPLY, "route"),
    ]
    assert events[0].payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "template": "demo_pick.v1",
        "template_sha256": load_template("demo_pick.v1").sha256,
        "model": MODEL,
        "model_listed_as": MODEL,
        "digest": SCRIPTED_INFO.digest,
        "think_requested": True,
        "think": True,
        "body": body(True),
    }
    assert events[1].payload == {
        "decision_id": DECISION,
        "content": '{"action": "echo"}',
        "thinking": "It asks to repeat.",
        "done_reason": "stop",
        "total_ns": 0,
        "load_ns": 0,
        "prompt_tokens": 0,
        "prompt_ns": 0,
        "reply_tokens": 0,
        "reply_ns": 0,
    }


@pytest.mark.parametrize(
    ("wanted", "capabilities", "sent"),
    [
        (True, ("completion", "thinking"), True),
        (True, ("completion",), False),
        (False, ("completion", "thinking"), False),
        (False, (), False),
    ],
)
def test_thinking_needs_the_point_and_the_model(
    tmp_path: Path, wanted: bool, capabilities: tuple[str, ...], sent: bool
) -> None:
    log = EventLog(tmp_path)
    info = replace(PLAIN, capabilities=capabilities)
    model = ScriptedModel(
        [ScriptedReply("demo_pick", ModelReply(content='{"action": "none"}'))], info=info
    )
    run(model, log, point=replace(demo.PICK, think=wanted))
    assert model.requests[0].think is sent
    payload = log.read(RUN)[0].payload
    assert (payload["think_requested"], payload["think"]) == (wanted, sent)
    assert (payload["model_listed_as"], payload["digest"]) == ("plain:latest", "b" * 64)


@pytest.mark.parametrize(
    ("content", "done_reason", "problems"),
    [
        ('{"action": "send"}', "stop", [("action", "literal_error")]),
        ("not json", "stop", [("", "json_invalid")]),
        ('["echo"]', "stop", [("", "model_type")]),
        ('{"action": "echo", "extra": 1}', "stop", [("extra", "extra_forbidden")]),
        ("{}", "stop", [("action", "missing")]),
        ('{"action": "echo"}', "length", [("reply", "cut_off")]),
    ],
)
def test_a_reply_that_does_not_fit_raises(
    tmp_path: Path, content: str, done_reason: str, problems: list[tuple[str, str]]
) -> None:
    log = EventLog(tmp_path)
    with pytest.raises(InvalidModelOutput) as raised:
        run(scripted(content, done_reason=done_reason), log)
    expected = tuple(FieldProblem(loc=loc, code=code) for loc, code in problems)
    assert (raised.value.decision_id, raised.value.problems) == (DECISION, expected)
    assert str(raised.value) == INVALID_OUTPUT_MESSAGE
    events = log.read(RUN)
    assert [event.kind for event in events] == [
        EventKind.MODEL_REQUEST,
        EventKind.MODEL_REPLY,
        EventKind.ERROR,
    ]
    assert events[1].payload["content"] == content
    assert events[2].payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "error": "invalid_model_output",
        "problems": [{"loc": loc, "code": code} for loc, code in problems],
    }


def test_no_reply_value_reaches_the_error(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    with pytest.raises(InvalidModelOutput) as raised:
        run(scripted('{"action": "SYNTHETIC-SECRET"}'), log)
    assert "SYNTHETIC-SECRET" not in str(raised.value)
    assert "SYNTHETIC-SECRET" not in repr(raised.value.problems)
    assert "SYNTHETIC-SECRET" not in repr(log.read(RUN)[-1].payload)


def test_a_model_that_is_not_installed(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    missing = ModelUnavailable("not_installed")
    with pytest.raises(ModelUnavailable) as raised:
        run(ScriptedModel([], info=missing), log, node=None)
    assert raised.value is missing
    [event] = log.read(RUN)
    assert (event.kind, event.node) == (EventKind.ERROR, None)
    assert event.payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "error": "model_unavailable",
        "code": "not_installed",
        "status": None,
    }


def test_a_model_that_fails_while_answering(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    down = ModelUnavailable("http_error", 500)
    with pytest.raises(ModelUnavailable) as raised:
        run(ScriptedModel([ScriptedReply("demo_pick", down)]), log)
    assert raised.value is down
    events = log.read(RUN)
    assert [event.kind for event in events] == [EventKind.MODEL_REQUEST, EventKind.ERROR]
    assert events[1].payload == {
        "decision_id": DECISION,
        "point": "demo_pick",
        "error": "model_unavailable",
        "code": "http_error",
        "status": 500,
    }


class SwappedModel:
    """Lists a new digest each time it is asked, as if the model were pulled again."""

    def __init__(self) -> None:
        self.digests = iter(["1" * 64, "2" * 64])

    def model_info(self, name: str) -> ModelInfo:
        return ModelInfo(name=name, digest=next(self.digests), capabilities=())

    def chat(self, request) -> ModelReply:
        return ModelReply(content='{"action": "note"}')


def test_the_digest_is_read_for_every_decision(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    model = SwappedModel()
    run(model, log)
    run(model, log)
    requests = [event for event in log.read(RUN) if event.kind == EventKind.MODEL_REQUEST]
    assert [event.payload["digest"] for event in requests] == ["1" * 64, "2" * 64]


def test_a_prompt_error_is_raised_before_anything_is_logged(tmp_path: Path) -> None:
    log = EventLog(tmp_path)
    with pytest.raises(PromptError):
        decide(
            demo.PICK,
            demo.PickInputs(request="x"),
            fields={},
            model=scripted('{"action": "echo"}'),
            model_name=MODEL,
            log=log,
            run_id=RUN,
        )
    assert log.runs() == []


def test_an_escalation_for_invalid_output() -> None:
    problems = (FieldProblem(loc="action", code="literal_error"),)
    escalation = escalation_for(InvalidModelOutput(DECISION, problems), RUN)
    assert escalation == Escalation(
        kind="invalid_model_output",
        detail=f"decision {DECISION}: {INVALID_OUTPUT_MESSAGE}",
        run_id=RUN,
        problems=problems,
    )


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (
            ModelUnavailable("unreachable"),
            "model unavailable: unreachable; retry when Ollama answers",
        ),
        (
            ModelUnavailable("http_error", 503),
            "model unavailable: http_error 503; retry when Ollama answers",
        ),
    ],
)
def test_an_escalation_for_a_model_that_is_unavailable(
    error: ModelUnavailable, detail: str
) -> None:
    assert escalation_for(error, RUN) == Escalation(
        kind="model_unavailable", detail=detail, run_id=RUN
    )
```

## Tests to write

In `tests/unit/test_decide_more.py`, each with its deciding input:

- R3: the `MODEL_REQUEST` event is on disk when `chat` is called (a model whose `chat` reads the log and finds the request event, then answers).
- R4: a `ScriptError` from `chat` (an empty script with an info that has `thinking`) passes through, and the log holds only the request event.
- R5: `done_reason` `"length"` with content that is not JSON still gives only `reply` `cut_off` (no parsing); a `done_reason` of `"load"` gives `cut_off` too.
- R5: a reply valid except for two fields of a point with two required fields gives both problems in field order (declare a small point in the test whose output has two `int` fields, using the `demo_pick.v1` template, and a reply `{"a": "1", "b": "2"}`).
- R6: `ModelUnavailable("timeout")` from `chat` is logged with `status` `None`.
- R7: a model that counts its `chat` calls is called exactly once for a reply that fails.
- R8: the `escalation_for` detail for every `UnavailableCode` is at most 500 characters and round-trips through `Escalation.from_json`.

`decide.py` reaches 100% of lines and branches (critical).

## Rules for this phase

- **Critical module**: `llm/decide.py` joins `scripts/critical_modules.txt` and `docs/testing.md` in this phase.
- **Invalid output escalates** (`AGENTS.md`): no second `chat`, no repair, no default; the error carries codes only.
- **Every model call goes through `decide()`** from now on; nothing else calls `chat`.
- **Ids through the module**: `ids.new_id()`, so tests replace it; the event log reads the clock itself.
- Earlier tests stay unchanged except the one given line.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first core`; at least N + 19 = 301 passed; `critical coverage` passed (it now includes `llm/decide.py`);
- the given file: `.venv/bin/python -m pytest tests/unit/test_decide.py --no-cov`, exactly `19 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/llm/decide.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py`: `Reports OK.` after the progress entry;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) " -- src/conductor/llm/decide.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|dataclasses|typing|collections\.abc|pydantic|conductor\.contracts|conductor\.events|conductor\.llm\.[a-z_]+|conductor import ids)( |$)"`
  - `git grep --untracked -n -E "model_validate\(|get_settings|clock\.|os\.environ|getenv|import ids as|from conductor\.ids import" -- src/conductor/llm/decide.py`
  - `git grep --untracked -n -E "\.chat\(" -- src/conductor | grep -v -E "^src/conductor/llm/decide\.py:"`
- `git diff HEAD -- tests` shows only the one added line in `tests/unit/test_contracts_tasks.py`; `git diff HEAD -- src/conductor/contracts` only the one added value.

## Report

As in `docs/phase-conventions.md`, headed `## Phase 3c: decide() (YYYY-MM-DD)`, with `Tests: 282 -> <passed> (given 19)`.
