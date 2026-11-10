# Phase 8b: saved and compared evaluation reports

## Goal

The second half of the evaluation harness: every `conductor eval run` saves a report, and compares it with the one before it, so a change in the model's decisions can be traced to a model, prompt, or case change.

- **run ids** (`conductor.evals.run`): each `CaseResult` keeps the ids of its runs;
- **reports** (`conductor.evals.report`): the numbers of every case, plus a **fingerprint** (the model name, every model digest and prompt template hash its runs' requests logged, and each case file's hash), saved as JSON under `data/evals/reports/`;
- **comparison**: what changed in the fingerprint, each case whose shares moved, and the cases added or removed, printed after the overall line.

Decided with the owner (2026-11-10): reports live in **`data/evals/reports/`** (gitignored, rule 6); a report records **the digests, the template hashes, and the case files' hashes**; `eval run` compares with **the latest report, as shares**, so a different `--runs` still compares; the exit code is **always 0** for a finished evaluation, since the comparison is for the owner to read.

Decided by the architect, within those answers: the digests and template hashes come from the runs' `MODEL_REQUEST` events, so nothing new is asked of the model; a report's file name is its time in UTC, so the newest name is the latest report; latency is recorded but not compared, since it varies from run to run; the previous report is read before any run, so an unreadable one stops the evaluation before it spends model time.

## Read first

- `docs/phase-conventions.md`, `AGENTS.md` (rules 5 and 6), `docs/architecture.md` ("Evaluation harness")
- `src/conductor/evals/run.py`, `src/conductor/llm/decide.py` (the `MODEL_REQUEST` payload), `src/conductor/events.py` (`EventLog.read`), `src/conductor/contracts/base.py` (`Contract`), `src/conductor/cli/main.py` (`eval_run`)

## Starting state

Phase 8a is built; its first verification failed on a spot-check row of the guide, not on the code, and it is verified again before this phase starts: N is `788`. **Sections: cli, core.** No `conductor/evals/report.py` exists. No new dependency.

## Scope

| Path | What |
|---|---|
| `src/conductor/evals/run.py` | `CaseResult.run_ids` (Part 1) |
| `src/conductor/evals/report.py` | new: `CaseNumbers`, `Report`, `ReportError`, `build_report`, `save_report`, `latest_report`, `compare_lines` (Parts 2 and 3) |
| `src/conductor/cli/main.py` | `conductor eval run` saves and compares (Part 4) |
| `tests/unit/test_eval_report.py`, `tests/e2e/test_cli_eval_report.py` | given |
| `tests/e2e/test_cli_eval.py` | given edit: line 54 compares the first three lines (`splitlines()[:3]`), since a report line now follows them |
| `tests/unit/test_eval_more_reports.py` | new: the coder's tests |
| `docs/progress.md` | one new entry |

## Out of scope

- A separate compare command, listing or deleting reports, comparing with any report but the latest.
- An exit code that depends on the comparison; comparing latency.
- Committing reports, or saving them anywhere but `data/evals/reports/`.
- Any change to the case files, `run_case`'s numbers, `case_line`, `overall_line`, routing, planning, or `decide`.

## Dependencies

None new.

## Design

```python
# conductor/evals/run.py: one new field, last, left out of equality
@dataclass(frozen=True)
class CaseResult:
    ...                                                   # the 8a fields, unchanged
    run_ids: tuple[str, ...] = field(default=(), compare=False)   # each run's id, in run order
```

```python
# conductor/evals/report.py
class CaseNumbers(Contract):
    id: str
    runs: int
    consistent: int
    route_ok: int
    plan_ok: int
    args_ok: int | None
    valid: int
    escalated: int
    unavailable: int
    seconds: list[float]
    run_ids: list[str]

class Report(Contract):
    version: Literal[1]
    created: AwareDatetime
    model: str                          # the model name the evaluation asked for
    digests: list[str]                  # sorted, each once
    templates: dict[str, list[str]]     # decision point name -> its template hashes, sorted, each once
    case_files: dict[str, str]          # case file name -> SHA-256 of its bytes
    runs: int                           # the --runs value
    cases: list[CaseNumbers]            # in run order

class ReportError(Exception): ...       # str(): "<file name> is not a report"

def build_report(results: Sequence[CaseResult], *, files: Sequence[Path], model_name: str, runs: int, log: EventLog) -> Report: ...
def save_report(report: Report, folder: Path) -> Path: ...
def latest_report(folder: Path) -> tuple[str, Report] | None: ...
def compare_lines(previous: Report, current: Report) -> list[str]: ...
```

A report holds ids, counts, times, and hashes only, never a request, a reply, or an argument value.

`build_report` calls `clock.now()` once, for `created`. Each case's numbers are its `CaseResult`'s, with lists for tuples. The fingerprint comes from the `MODEL_REQUEST` events logged under the results' run ids, and only those (`log.read(run_id)`; a run with no file has none): `digests` from each payload's `digest`, `templates` from each payload's `point` and `template_sha256`. A run whose model was down before its request logs none, so it adds nothing. `case_files` maps each file's `name` to `hashlib.sha256` of its bytes.

`save_report` makes `folder` with mode 0700 if it is missing (as `EventLog` does) and writes `report.model_dump_json(indent=2)` and a newline to `<created in UTC as %Y%m%dT%H%M%S%fZ>.json`, opened with `os.O_CREAT | os.O_EXCL` and mode 0600, so an existing name raises `FileExistsError` and is never overwritten. It returns the path.

`latest_report` returns `None` when `folder` does not exist or holds no file whose name fully matches `\d{8}T\d{12}Z\.json`; otherwise it reads the greatest such name and returns `(name, Report.from_json(its bytes))`. A file that does not validate raises `ReportError(name)`: its text, and Pydantic's error, are never shown.

`compare_lines(previous, current)` gives these lines, in this order, or `["no change"]` when there are none:

1. `changed: model` when the models differ; `changed: digest` when the digest lists differ;
2. `changed: template <point>` for each point in either report, in sorted order, whose lists differ (a missing point counts as an empty list);
3. `changed: case file <name>` for each name in either report, in sorted order, whose hashes differ or that one report lacks;
4. for each case of `current`, in its order, that `previous` also has, when any of its six numbers moved: `<id>` followed by `  <label> <before> -> <after>` for each one that moved, in the order of the labels `consistent`, `route`, `plan`, `args`, `valid`, `escalated` (from `consistent`, `route_ok`, `plan_ok`, `args_ok`, `valid`, `escalated`). A number moved when its shares differ: `a/n` and `b/m` are the same share when `a × m == b × n`; `args` with `None` on one side is the same only when both are `None`. Each side is shown as `<count>/<runs>`, or `-` for `None`;
5. `added: case <id>` for each case of `current` that `previous` lacks, in `current`'s order;
6. `removed: case <id>` for each case of `previous` that `current` lacks, in `previous`'s order.

`created` and `runs` are never compared; nor are `unavailable` and `seconds`.

**The command** keeps 8a's order and adds three steps. After every case file is loaded and before the model or the log is made, it calls `report.latest_report(settings.data_dir / "evals" / "reports")` (a `ReportError`: `Error: <its text>`, exit 1, no run made). After the overall line it builds the report (`files` the loaded case files, `model_name` `settings.model`, `runs` the `--runs` value, the same log), saves it to that folder, and prints `report <file name>`. When there was a previous report, it then prints `previous <its file name>` and each line of `compare_lines(previous, current)`. It exits 0.

```text
say-hi  consistent 2/2  route 2/2  ...
weather  consistent 2/2  route 2/2  ...
overall  2 cases  consistent 4/4  ...
report 20261110T100000000000Z.json
previous 20261110T090000000000Z.json
weather  plan 2/2 -> 0/2  escalated 2/2 -> 0/2
```

## Facts

- `MODEL_REQUEST` payloads (3c) carry `point`, `template_sha256`, and `digest`; a `ScriptedModel`'s digest is `"0" * 64`. A rule route makes no model request, so a prefix-routed case's report has only the `plan` template.
- `Contract.from_json` validates strictly (checked with Pydantic as installed): a time without an offset (`timezone_aware`), `"1"` for an int, an extra key, and a version other than `1` are refused, and a time written as `...Z` reads back equal to the `datetime` saved.
- `EventLog(folder)` makes no folder until its first append, so reading the previous report first leaves `data/evals/runs/` untouched when it fails.

## Requirements

### Part 1: run ids

- **R1.** `CaseResult.run_ids` holds each run's id in run order, as under Design, and is left out of equality, so every 8a test passes unchanged.

### Part 2: reports

- **R2.** `CaseNumbers`, `Report`, and `ReportError` are as under Design.
- **R3.** `build_report` takes `created` from one `clock.now()`, copies each case's numbers, and hashes each case file by name.
- **R4.** `digests` and `templates` come from the `MODEL_REQUEST` events of the results' run ids only, sorted and each once.
- **R5.** `save_report` writes the file as under Design: the UTC time as its name, mode 0600 in a 0700 folder, never over an existing file.
- **R6.** `latest_report` returns `None`, or the newest report by name among names of the given form; a file that does not validate raises `ReportError` with only its name.

### Part 3: comparing

- **R7.** `compare_lines` names the changes in the fingerprint as under Design, items 1 to 3.
- **R8.** `compare_lines` prints the cases whose shares moved, the cases added and removed, in that order, as under Design, items 4 to 6, and `no change` when nothing differs.

### Part 4: the command

- **R9.** `conductor eval run` reads the previous report before any run, saves the new one, and prints `report`, `previous`, and the comparison as under Design; an unreadable previous report is one `Error:` line and exit 1; a finished evaluation exits 0.

### Part 5: the rules

- **R10.** `conductor/evals/` imports from the project only what 8a allowed plus `conductor.clock` (`from conductor import clock, ids`); time comes only from `clock.now()` through the module; `evals/report.py`, `evals/run.py`, and `cli/main.py` reach 100% of lines and branches.

## Given tests

31 tests in two files (counting each parameter set), and the one-line edit to `tests/e2e/test_cli_eval.py`. Do not change them; if one fails, the code is wrong.

`tests/unit/test_eval_report.py` (26 tests)

```python
import hashlib
import json
import stat
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from conductor import clock
from conductor.domains import demo
from conductor.evals.cases import EvalCase
from conductor.evals.report import (
    CaseNumbers,
    Report,
    ReportError,
    build_report,
    compare_lines,
    latest_report,
    save_report,
)
from conductor.evals.run import CaseResult, run_case
from conductor.events import EventKind, EventLog
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.prompts import load_template
from conductor.llm.scripted import SCRIPTED_INFO, ScriptedModel, ScriptedReply
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
ECHO = EvalCase(
    id="say-hi",
    request="Say hi back to me",
    route="demo",
    plan=("echo",),
    args=({"text": "hi"},),
)
ROUTE = '{"domain": "demo"}'
PLAN = json.dumps({"steps": [{"action": "echo", "args": {"text": "hi"}}]})
EMPTY = json.dumps({"steps": []})
NOW = datetime(2026, 11, 10, 9, 30, 15, 250000, tzinfo=UTC)
NAME = "20261110T093015250000Z.json"


@pytest.fixture(autouse=True)
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def scripted(*plans: str) -> ScriptedModel:
    replies = []
    for content in plans:
        replies.append(ScriptedReply("route", ModelReply(content=ROUTE, total_ns=10**9)))
        replies.append(ScriptedReply("plan", ModelReply(content=content, total_ns=2 * 10**9)))
    return ScriptedModel(replies)


def run(tmp_path: Path, model: ScriptedModel, runs: int) -> CaseResult:
    return run_case(
        ECHO,
        REGISTRY,
        model=model,
        model_name="test-model:1b",
        log=EventLog(tmp_path / "runs"),
        runs=runs,
    )


def build(tmp_path: Path, result: CaseResult) -> Report:
    cases = tmp_path / "demo.toml"
    cases.write_bytes(b"# synthetic cases\n")
    return build_report(
        [result],
        files=[cases],
        model_name="test-model:1b",
        runs=result.runs,
        log=EventLog(tmp_path / "runs"),
    )


# run ids


def test_each_run_keeps_its_id_in_order(tmp_path: Path) -> None:
    result = run(tmp_path, scripted(PLAN, EMPTY), 2)
    log = EventLog(tmp_path / "runs")
    contents = [
        [
            event.payload["content"]
            for event in log.read(run_id)
            if event.kind is EventKind.MODEL_REPLY
        ]
        for run_id in result.run_ids
    ]
    assert contents == [[ROUTE, PLAN], [ROUTE, EMPTY]]
    assert result == CaseResult("say-hi", 2, 1, 2, 1, 1, 2, 1, 0, (3.0, 3.0))


# building


def test_a_report_holds_the_numbers_and_the_fingerprint(tmp_path: Path) -> None:
    result = run(tmp_path, scripted(PLAN, PLAN), 2)
    assert build(tmp_path, result) == Report(
        version=1,
        created=NOW,
        model="test-model:1b",
        digests=[SCRIPTED_INFO.digest],
        templates={
            "plan": [load_template("plan.v1").sha256],
            "route": [load_template("route.v1").sha256],
        },
        case_files={"demo.toml": hashlib.sha256(b"# synthetic cases\n").hexdigest()},
        runs=2,
        cases=[
            CaseNumbers(
                id="say-hi",
                runs=2,
                consistent=2,
                route_ok=2,
                plan_ok=2,
                args_ok=2,
                valid=2,
                escalated=0,
                unavailable=0,
                seconds=[3.0, 3.0],
                run_ids=list(result.run_ids),
            )
        ],
    )


def test_the_fingerprint_reads_only_these_runs(tmp_path: Path) -> None:
    EventLog(tmp_path / "runs").append(
        "f" * 32,
        EventKind.MODEL_REQUEST,
        payload={"point": "answer", "template_sha256": "e" * 64, "digest": "d" * 64},
    )
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    assert (built.digests, sorted(built.templates)) == ([SCRIPTED_INFO.digest], ["plan", "route"])


def test_a_model_that_is_down_leaves_no_fingerprint(tmp_path: Path) -> None:
    model = ScriptedModel([], info=ModelUnavailable("timeout"))
    built = build(tmp_path, run(tmp_path, model, 1))
    assert (built.digests, built.templates, built.cases[0].unavailable) == ([], {}, 1)
    assert built.cases[0].seconds == [0.0]


# saving and reading


def test_a_saved_report_reads_back(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    folder = tmp_path / "reports"
    path = save_report(built, folder)
    assert path == folder / NAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert Report.from_json(path.read_bytes()) == built
    assert latest_report(folder) == (NAME, built)


def test_the_name_is_the_time_in_utc(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    elsewhere = NOW.astimezone(timezone(timedelta(hours=-5)))
    path = save_report(built.model_copy(update={"created": elsewhere}), tmp_path / "reports")
    assert path.name == NAME


def test_a_report_name_is_never_reused(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    path = save_report(built, tmp_path / "reports")
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_report(built.model_copy(update={"runs": 9}), tmp_path / "reports")
    assert path.read_bytes() == before


def test_no_report_yet(tmp_path: Path) -> None:
    assert latest_report(tmp_path / "missing") is None
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "notes.json").write_text("{}", encoding="utf-8")
    (folder / "20261110T093015250000Z.txt").write_text("{}", encoding="utf-8")
    assert latest_report(folder) is None


def test_the_newest_name_wins(tmp_path: Path) -> None:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    folder = tmp_path / "reports"
    older = built.model_copy(update={"created": NOW - timedelta(days=1), "model": "old:1b"})
    save_report(older, folder)
    save_report(built, folder)
    (folder / "zzz.json").write_text("not a report", encoding="utf-8")
    assert latest_report(folder) == (NAME, built)


def good_report(tmp_path: Path) -> dict:
    built = build(tmp_path, run(tmp_path, scripted(PLAN), 1))
    return json.loads(built.model_dump_json())


@pytest.mark.parametrize(
    "change",
    [
        "SYNTHETIC-SECRET is not JSON",
        {"version": 2},
        {"colour": "SYNTHETIC-SECRET"},
        {"created": "2026-11-10T09:30:15"},
        {"runs": "1"},
        {"cases": None},
    ],
    ids=["not-json", "version", "extra-key", "naive-time", "text-runs", "no-cases"],
)
def test_a_bad_report_is_refused(tmp_path: Path, change: str | dict) -> None:
    folder = tmp_path / "reports"
    folder.mkdir()
    if isinstance(change, str):
        text = change
    else:
        base = good_report(tmp_path)
        text = json.dumps(
            {key: value for key, value in {**base, **change}.items() if value is not None}
        )
    (folder / NAME).write_text(text, encoding="utf-8")
    with pytest.raises(ReportError) as raised:
        latest_report(folder)
    assert str(raised.value) == f"{NAME} is not a report"


# comparing


def numbers(case_id: str, runs: int, *counts: int | None) -> CaseNumbers:
    consistent, route, plan, args, valid, escalated = counts
    return CaseNumbers(
        id=case_id,
        runs=runs,
        consistent=consistent,
        route_ok=route,
        plan_ok=plan,
        args_ok=args,
        valid=valid,
        escalated=escalated,
        unavailable=0,
        seconds=[1.0] * runs,
        run_ids=["a" * 32] * runs,
    )


BASE = Report(
    version=1,
    created=NOW,
    model="test-model:1b",
    digests=["1" * 64],
    templates={"plan": ["2" * 64], "route": ["3" * 64]},
    case_files={"demo.toml": "4" * 64},
    runs=5,
    cases=[numbers("say-hi", 5, 5, 5, 5, 5, 5, 0), numbers("weather", 5, 5, 5, 5, None, 5, 5)],
)


def test_nothing_changed() -> None:
    later = BASE.model_copy(update={"created": NOW + timedelta(hours=1)})
    assert compare_lines(BASE, later) == ["no change"]


def test_the_same_shares_from_more_runs_are_no_change() -> None:
    doubled = [
        numbers("say-hi", 10, 10, 10, 10, 10, 10, 0),
        numbers("weather", 10, 10, 10, 10, None, 10, 10),
    ]
    assert compare_lines(BASE, BASE.model_copy(update={"runs": 10, "cases": doubled})) == [
        "no change"
    ]


@pytest.mark.parametrize(
    ("update", "line"),
    [
        ({"model": "other:7b"}, "changed: model"),
        ({"digests": ["5" * 64]}, "changed: digest"),
        ({"templates": {**BASE.templates, "plan": ["6" * 64]}}, "changed: template plan"),
        ({"templates": {**BASE.templates, "answer": ["7" * 64]}}, "changed: template answer"),
        ({"case_files": {"demo.toml": "8" * 64}}, "changed: case file demo.toml"),
        (
            {"case_files": {**BASE.case_files, "more.toml": "9" * 64}},
            "changed: case file more.toml",
        ),
    ],
    ids=["model", "digest", "template", "new-template", "case-file", "new-case-file"],
)
def test_a_changed_fingerprint_is_named(update: dict, line: str) -> None:
    assert compare_lines(BASE, BASE.model_copy(update=update)) == [line]


def test_a_case_whose_shares_moved() -> None:
    moved = [numbers("say-hi", 5, 4, 5, 3, 3, 5, 1), BASE.cases[1]]
    assert compare_lines(BASE, BASE.model_copy(update={"cases": moved})) == [
        "say-hi  consistent 5/5 -> 4/5  plan 5/5 -> 3/5  args 5/5 -> 3/5  escalated 0/5 -> 1/5"
    ]


def test_shares_compare_across_run_counts() -> None:
    moved = [BASE.cases[0], numbers("weather", 10, 10, 9, 10, 2, 10, 10)]
    assert compare_lines(BASE, BASE.model_copy(update={"cases": moved})) == [
        "weather  route 5/5 -> 9/10  args - -> 2/10"
    ]


def test_every_kind_of_change_in_order() -> None:
    current = BASE.model_copy(
        update={
            "model": "other:7b",
            "digests": ["5" * 64],
            "templates": {"answer": ["7" * 64], "route": ["3" * 64]},
            "case_files": {"demo.toml": "8" * 64, "more.toml": "9" * 64},
            "cases": [
                numbers("new-one", 5, 5, 5, 5, None, 5, 0),
                numbers("weather", 5, 5, 5, 5, None, 4, 5),
                numbers("other-new", 5, 5, 5, 5, None, 5, 0),
            ],
        }
    )
    assert compare_lines(BASE, current) == [
        "changed: model",
        "changed: digest",
        "changed: template answer",
        "changed: template plan",
        "changed: case file demo.toml",
        "changed: case file more.toml",
        "weather  valid 5/5 -> 4/5",
        "added: case new-one",
        "added: case other-new",
        "removed: case say-hi",
    ]
```

`tests/e2e/test_cli_eval_report.py` (5 tests)

```python
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor import clock
from conductor.evals import run as evals_run
from conductor.evals.report import Report
from conductor.llm.model import ModelReply
from conductor.llm.prompts import load_template
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from tests.support import run

CASES = """[[case]]
id = "say-hi"
request = "demo: say hi"
route = "demo"
plan = ["echo"]
args = [{ text = "hi" }]

[[case]]
id = "weather"
request = "demo: what is the weather"
route = "demo"
plan = "escalate"
"""
MORE = """
[[case]]
id = "say-bye"
request = "demo: say bye"
route = "demo"
plan = ["echo"]
"""
FIRST = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
SECOND = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
ECHO = [{"action": "echo", "args": {"text": "hi"}}]


@pytest.fixture
def cases(tmp_path: Path) -> Path:
    path = tmp_path / "cases"
    path.mkdir()
    (path / "demo.toml").write_text(CASES, encoding="utf-8")
    return path


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> list[ScriptedReply]:
    replies: list[ScriptedReply] = []
    monkeypatch.setattr(evals_run, "model_for", lambda settings: ScriptedModel(replies))
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    return replies


def plan_reply(steps: list) -> ScriptedReply:
    content = json.dumps({"steps": steps})
    return ScriptedReply("plan", ModelReply(content=content, total_ns=10**9))


def eval_at(monkeypatch, moment: datetime, cases: Path, model: list, plans: list, *args: str):
    monkeypatch.setattr(clock, "now", lambda: moment)
    model[:] = [plan_reply(steps) for steps in plans]
    result = run("eval", "run", "--cases", cases, *args)
    assert (result.exit_code, result.stderr) == (0, "")
    return result.stdout.splitlines()


def test_the_first_run_saves_a_report(
    monkeypatch, cases: Path, model: list, tmp_path: Path
) -> None:
    lines = eval_at(monkeypatch, FIRST, cases, model, [ECHO, ECHO, [], []], "--runs", "2")
    assert len(lines) == 4
    assert lines[3] == "report 20261110T090000000000Z.json"
    saved = tmp_path / "data" / "evals" / "reports" / "20261110T090000000000Z.json"
    report = Report.from_json(saved.read_bytes())
    assert [case.id for case in report.cases] == ["say-hi", "weather"]
    assert (report.runs, report.created, report.digests) == (2, FIRST, ["0" * 64])
    assert report.templates == {"plan": [load_template("plan.v1").sha256]}
    assert report.case_files == {"demo.toml": hashlib.sha256(CASES.encode()).hexdigest()}


def test_a_second_run_names_what_moved(monkeypatch, cases: Path, model: list) -> None:
    eval_at(monkeypatch, FIRST, cases, model, [ECHO, ECHO, [], []], "--runs", "2")
    lines = eval_at(monkeypatch, SECOND, cases, model, [ECHO, ECHO, ECHO, ECHO], "--runs", "2")
    assert lines[3:] == [
        "report 20261110T100000000000Z.json",
        "previous 20261110T090000000000Z.json",
        "weather  plan 2/2 -> 0/2  escalated 2/2 -> 0/2",
    ]


def test_an_unchanged_second_run(monkeypatch, cases: Path, model: list) -> None:
    eval_at(monkeypatch, FIRST, cases, model, [ECHO, []], "--runs", "1")
    lines = eval_at(monkeypatch, SECOND, cases, model, [ECHO, []], "--runs", "1")
    assert lines[3:] == [
        "report 20261110T100000000000Z.json",
        "previous 20261110T090000000000Z.json",
        "no change",
    ]


def test_an_edited_case_file_is_named(monkeypatch, cases: Path, model: list) -> None:
    eval_at(monkeypatch, FIRST, cases, model, [ECHO, []], "--runs", "1")
    with (cases / "demo.toml").open("a", encoding="utf-8") as handle:
        handle.write(MORE)
    lines = eval_at(monkeypatch, SECOND, cases, model, [ECHO, [], ECHO], "--runs", "1")
    assert lines[4:] == [
        "report 20261110T100000000000Z.json",
        "previous 20261110T090000000000Z.json",
        "changed: case file demo.toml",
        "added: case say-bye",
    ]


def test_a_bad_previous_report_stops_before_any_run(
    cases: Path, model: list, tmp_path: Path
) -> None:
    folder = tmp_path / "data" / "evals" / "reports"
    folder.mkdir(parents=True)
    (folder / "20261109T000000000000Z.json").write_text("SYNTHETIC-SECRET", encoding="utf-8")
    model.append(plan_reply(ECHO))
    result = run("eval", "run", "--cases", cases, "--runs", "1")
    assert (result.exit_code, result.stdout) == (1, "")
    assert result.stderr == "Error: 20261109T000000000000Z.json is not a report\n"
    assert not (tmp_path / "data" / "evals" / "runs").exists()
```

`tests/e2e/test_cli_eval.py` (given edit; the whole file after it)

```python
import json
from pathlib import Path

import pytest

from conductor.evals import run as evals_run
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from tests.support import run

CASES = """[[case]]
id = "say-hi"
request = "demo: say hi"
route = "demo"
plan = ["echo"]
args = [{ text = "hi" }]

[[case]]
id = "weather"
request = "demo: what is the weather"
route = "demo"
plan = "escalate"
"""


@pytest.fixture
def cases(tmp_path: Path) -> Path:
    path = tmp_path / "cases"
    path.mkdir()
    (path / "demo.toml").write_text(CASES, encoding="utf-8")
    return path


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> list[ScriptedReply]:
    replies: list[ScriptedReply] = []
    monkeypatch.setattr(evals_run, "model_for", lambda settings: ScriptedModel(replies))
    monkeypatch.setenv("CONDUCTOR_DEMO", "true")
    return replies


def plan_reply(steps: list, seconds: float) -> ScriptedReply:
    content = json.dumps({"steps": steps})
    return ScriptedReply("plan", ModelReply(content=content, total_ns=int(seconds * 1e9)))


def test_eval_run_prints_a_line_per_case_and_overall(cases: Path, model: list) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend(
        [plan_reply(echo, 1.0), plan_reply(echo, 1.0), plan_reply([], 2.0), plan_reply([], 2.0)]
    )
    result = run("eval", "run", "--cases", cases, "--runs", "2")
    assert (result.exit_code, result.stderr) == (0, "")
    assert result.stdout.splitlines()[:3] == [
        "say-hi  consistent 2/2  route 2/2  plan 2/2  args 2/2  valid 2/2  escalated 0/2"
        "  p50 1.00s  p95 1.00s",
        "weather  consistent 2/2  route 2/2  plan 2/2  args -  valid 2/2  escalated 2/2"
        "  p50 2.00s  p95 2.00s",
        "overall  2 cases  consistent 4/4  route 4/4  plan 4/4  args 2/2  valid 4/4"
        "  escalated 2/4  p50 1.00s  p95 2.00s",
    ]


def test_five_runs_by_default_from_one_file(cases: Path, model: list) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend([plan_reply(echo, 1.0)] * 5)
    single = cases / "only.toml"
    single.write_text(CASES.split("\n\n")[0] + "\n", encoding="utf-8")
    result = run("eval", "run", "--cases", single)
    assert result.stdout.splitlines()[0].startswith("say-hi  consistent 5/5")


def test_runs_are_logged_under_the_data_folder(cases: Path, model: list, tmp_path: Path) -> None:
    echo = [{"action": "echo", "args": {"text": "hi"}}]
    model.extend([plan_reply(echo, 1.0), plan_reply([], 1.0)])
    run("eval", "run", "--cases", cases, "--runs", "1")
    assert len(list((tmp_path / "data" / "evals" / "runs").glob("*.jsonl"))) == 2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--runs", "0"), "Error: --runs must be 1 to 100\n"),
        (("--cases", "nowhere"), "Error: no case files at nowhere\n"),
    ],
)
def test_errors(cases: Path, model: list, args: tuple[str, ...], message: str) -> None:
    result = run("eval", "run", *args)
    assert (result.exit_code, result.stdout, result.stderr) == (1, "", message)


def test_a_bad_case_file_names_itself(cases: Path, model: list) -> None:
    bad = cases / "bad.toml"
    bad.write_text('[[case]]\nid = "x"\nrequest = "hi"\nroute = "travel"\n', encoding="utf-8")
    result = run("eval", "run", "--cases", cases)
    assert (result.exit_code, result.stdout) == (1, "")
    assert result.stderr == f"Error: {bad}: case 1: route must be a registered domain or escalate\n"
```

## Tests to write

In `tests/unit/test_eval_more_reports.py`, each with its deciding input:

- R1: `--runs 1` gives one run id, and that run's log file exists.
- R3: two case files give two hashes by name; two results give their cases in the order given.
- R4: two cases run against models with different digests give both digests, sorted.
- R6: a report file that is not UTF-8 is refused as not a report.
- R8: a case that only `previous` has, with the rest unchanged, gives only its `removed` line; a case whose `escalated` alone moved names only `escalated`.
- R9: a report folder holding only `notes.json` gives no `previous` line; `--runs 0` with an unreadable report in the folder gives the `--runs` error.

## Rules for this phase

- **No side effects** (as in 8a): `conductor.evals` imports only the modules R10 allows; a report is written only under `data/evals/reports/`.
- **Synthetic data only** (`AGENTS.md` rule 5), and **`data/` is never committed** (rule 6): a report holds no request text.
- **Time** only through `clock.now()`, called through the module.
- Earlier tests stay unchanged, except the given edit.

## Acceptance

The standard table of `docs/phase-conventions.md`, with:

- the check: `.venv/bin/python scripts/check.py --first cli,core`; at least N + 31 = 819 passed;
- the given files: `.venv/bin/python -m pytest tests/unit/test_eval_report.py tests/e2e/test_cli_eval_report.py tests/e2e/test_cli_eval.py --no-cov`, exactly `37 passed`;
- the coverage command: `.venv/bin/python -m coverage report --include="*/conductor/evals/*.py,*/conductor/cli/main.py" --fail-under=100`;
- `.venv/bin/python scripts/check_reports.py --phase 8b`, after the progress entry: `Reports OK.`;
- the searches, each with no output:
  - `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/evals | grep -v -E ":from conductor(\.config|\.contracts|\.events|\.llm\.model|\.llm\.ollama|\.planning\.plan|\.registry|\.routing\.route)? import "`
  - `git grep --untracked -n -E "eval" -- scripts/check.py`
  - `git grep --untracked -n -E "datetime\.now|time\.time|from conductor\.clock" -- src/conductor/evals`
- `git diff --stat HEAD -- src/conductor/routing src/conductor/planning src/conductor/llm src/conductor/graph src/conductor/web src/conductor/runtime.py src/conductor/evals/cases.py tests/unit tests/support.py evals` prints nothing (the new test files are untracked, so they do not show).

## Report

As in `docs/phase-conventions.md`, headed `## Phase 8b: saved and compared evaluation reports (YYYY-MM-DD)`, with `Tests: 788 -> <passed> (given 31)`.
