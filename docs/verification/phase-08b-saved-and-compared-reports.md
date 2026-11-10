# Verify Phase 8b: saved and compared evaluation reports

Spec: `docs/phases/phase-08b-saved-and-compared-reports.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 8b` on your own report.

The coder added `CaseResult.run_ids`, created `conductor.evals.report`, made `conductor eval run` save and compare reports, copied the two given test files (31 tests) and the one-line edit to `tests/e2e/test_cli_eval.py`, and wrote `tests/unit/test_eval_more_reports.py`.

## 1. Gates

N is `788`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 819 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/evals/*.py,*/conductor/cli/main.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_eval_report.py tests/e2e/test_cli_eval_report.py tests/e2e/test_cli_eval.py --no-cov` | exactly `37 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 8b` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/routing src/conductor/planning src/conductor/llm src/conductor/graph src/conductor/web src/conductor/runtime.py src/conductor/evals/cases.py tests/unit tests/support.py evals` | no output |
| `git diff HEAD -- tests/e2e/test_cli_eval.py` | only line 54: `splitlines()` became `splitlines()[:3]` |
| `git diff HEAD -- src/conductor/evals/run.py` | only the `run_ids` field (with its `field` import) and the lines that fill it |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/evals | grep -v -E ":from conductor(\.config|\.contracts|\.events|\.llm\.model|\.llm\.ollama|\.planning\.plan|\.registry|\.routing\.route)? import "`
2. `git grep --untracked -n -E "eval" -- scripts/check.py`
3. `git grep --untracked -n -E "datetime\.now|time\.time|from conductor\.clock" -- src/conductor/evals`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks, the edited `tests/e2e/test_cli_eval.py` included.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_each_run_keeps_its_id_in_order`; every 8a test in the check; the coder's one-run test; probe "60 logs ..." | pass; ok |
| R2 | `test_a_report_holds_the_numbers_and_the_fingerprint`, `test_a_bad_report_is_refused` (6 cases); read the two classes against the Design | pass; the fields and types match |
| R3 | `test_a_report_holds_the_numbers_and_the_fingerprint`; the coder's two-files and two-results tests | pass |
| R4 | `test_the_fingerprint_reads_only_these_runs`, `test_a_model_that_is_down_leaves_no_fingerprint`; the coder's two-digests test; probe "60 logs ..." | pass; ok |
| R5 | `test_a_saved_report_reads_back`, `test_the_name_is_the_time_in_utc`, `test_a_report_name_is_never_reused` | pass |
| R6 | `test_no_report_yet`, `test_the_newest_name_wins`, `test_a_bad_report_is_refused` (6 cases); the coder's not-UTF-8 test; probe "30 folders ..." | pass; ok |
| R7 | `test_a_changed_fingerprint_is_named` (6 cases), `test_every_kind_of_change_in_order` | pass |
| R8 | `test_nothing_changed`, `test_the_same_shares_from_more_runs_are_no_change`, `test_a_case_whose_shares_moved`, `test_shares_compare_across_run_counts`, `test_every_kind_of_change_in_order`; the coder's removed-only and escalated-only tests; probe "1000 random report pairs ..." | pass; ok |
| R9 | the five tests of `tests/e2e/test_cli_eval_report.py`; the coder's `notes.json` and `--runs 0` tests | pass |
| R10 | searches 1 and 3; the coverage gate | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It compares 1000 random pairs of reports with its own reading of the Design, saves 30 folders of six reports in random order and reads back the newest, and checks the fingerprint of 60 logs (random digests, some models down, a foreign run in each log) against the events their runs logged. A stop at its `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 8b. Run from the repository root with .venv/bin/python."""

import os
import random
import tempfile
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path

from conductor.domains import demo
from conductor.evals.cases import EvalCase
from conductor.evals.report import (
    CaseNumbers,
    Report,
    build_report,
    compare_lines,
    latest_report,
    save_report,
)
from conductor.evals.run import run_case
from conductor.events import EventKind, EventLog
from conductor.llm.model import ModelInfo, ModelReply, ModelUnavailable
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(84)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
folder = Path(tempfile.mkdtemp())
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
METRICS = ("consistent", "route_ok", "plan_ok", "args_ok", "valid", "escalated")
SHOWN = ("consistent", "route", "plan", "args", "valid", "escalated")


def shown(value: int | None, runs: int) -> str:
    return "-" if value is None else f"{value}/{runs}"


def same(a: int | None, n: int, b: int | None, m: int) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return Fraction(a, n) == Fraction(b, m)


def oracle(old: Report, new: Report) -> list[str]:
    lines = []
    if old.model != new.model:
        lines.append("changed: model")
    if old.digests != new.digests:
        lines.append("changed: digest")
    for point in sorted(set(old.templates) | set(new.templates)):
        if old.templates.get(point, []) != new.templates.get(point, []):
            lines.append(f"changed: template {point}")
    for name in sorted(set(old.case_files) | set(new.case_files)):
        if old.case_files.get(name) != new.case_files.get(name):
            lines.append(f"changed: case file {name}")
    before = {case.id: case for case in old.cases}
    for case in new.cases:
        if case.id not in before:
            continue
        was = before[case.id]
        parts = [
            f"{label} {shown(getattr(was, m), was.runs)} -> {shown(getattr(case, m), case.runs)}"
            for m, label in zip(METRICS, SHOWN, strict=True)
            if not same(getattr(was, m), was.runs, getattr(case, m), case.runs)
        ]
        if parts:
            lines.append("  ".join([case.id, *parts]))
    now_ids = {case.id for case in new.cases}
    lines += [f"added: case {case.id}" for case in new.cases if case.id not in before]
    lines += [f"removed: case {case.id}" for case in old.cases if case.id not in now_ids]
    return lines or ["no change"]


def numbers(case_id: str, runs: int, counts: list[int | None]) -> CaseNumbers:
    return CaseNumbers(
        id=case_id,
        runs=runs,
        **dict(zip(METRICS, counts, strict=True)),
        unavailable=0,
        seconds=[0.5] * runs,
        run_ids=["b" * 32] * runs,
    )


def random_report(created: datetime) -> Report:
    cases = []
    for case_id in rng.sample(["a", "b", "c", "d", "e"], rng.randint(1, 5)):
        runs = rng.choice([1, 2, 4, 5])
        counts = [rng.randint(0, runs) for _ in METRICS]
        if rng.random() < 0.4:
            counts[3] = None
        cases.append(numbers(case_id, runs, counts))
    return Report(
        version=1,
        created=created,
        model=rng.choice(["m:1b", "m:7b"]),
        digests=sorted(rng.sample(["1" * 64, "2" * 64], rng.randint(0, 2))),
        templates={p: [rng.choice(["3" * 64, "4" * 64])] for p in rng.sample(["plan", "route"], 2)},
        case_files={
            n: rng.choice(["5" * 64, "6" * 64]) for n in rng.sample(["x.toml", "y.toml"], 1)
        },
        runs=5,
        cases=cases,
    )


# the oracle on known pairs
_base = Report(
    version=1,
    created=NOW,
    model="m:1b",
    digests=["1" * 64],
    templates={"route": ["3" * 64]},
    case_files={"x.toml": "5" * 64},
    runs=5,
    cases=[numbers("a", 5, [5, 5, 5, None, 5, 0])],
)
assert oracle(_base, _base) == ["no change"]
_double = _base.model_copy(update={"cases": [numbers("a", 10, [10, 10, 10, None, 10, 0])]})
assert oracle(_base, _double) == ["no change"]
_moved = _base.model_copy(
    update={
        "model": "m:7b",
        "cases": [numbers("a", 4, [3, 4, 4, 1, 4, 1]), numbers("b", 1, [1] * 6)],
    }
)
assert oracle(_base, _moved) == [
    "changed: model",
    "a  consistent 5/5 -> 3/4  args - -> 1/4  escalated 0/5 -> 1/4",
    "added: case b",
]

# 1. random pairs of reports
agree = True
for _ in range(1000):
    old, new = random_report(NOW), random_report(NOW + timedelta(hours=1))
    agree &= compare_lines(old, new) == oracle(old, new)
    agree &= compare_lines(new, new) == ["no change"]
check("1000 random report pairs compare as the probe computes", agree)

# 2. saving in a random order, the newest is read back
agree = True
for trial in range(30):
    reports_dir = folder / f"reports{trial}"
    moments = [NOW + timedelta(minutes=rng.randint(0, 10**6), microseconds=i) for i in range(6)]
    made = [random_report(moment) for moment in moments]
    for report in rng.sample(made, len(made)):
        save_report(report, reports_dir)
    newest = max(made, key=lambda report: report.created)
    found = latest_report(reports_dir)
    agree &= found == (newest.created.strftime("%Y%m%dT%H%M%S%fZ") + ".json", newest)
check("30 folders of 6 reports saved in random order give back the newest", agree)

# 3. the fingerprint against what the runs logged
registry = Registry((demo.DOMAIN,))
case = EvalCase("p", "Say hi back to me", "demo", ("echo",), None)
agree = True
for trial in range(60):
    log = EventLog(folder / f"runs{trial}")
    results = []
    for _ in range(rng.randint(1, 3)):
        runs = rng.randint(1, 4)
        digest = rng.choice(["7" * 64, "8" * 64])
        info: ModelInfo | ModelUnavailable = ModelInfo("x", digest, ("completion",))
        if rng.random() < 0.2:
            info = ModelUnavailable("timeout")
        replies = []
        for _ in range(runs):
            replies.append(ScriptedReply("route", ModelReply(content='{"domain": "demo"}')))
            replies.append(
                ScriptedReply(
                    "plan",
                    ModelReply(content='{"steps": [{"action": "echo", "args": {"text": "a"}}]}'),
                )
            )
        result = run_case(
            case,
            registry,
            model=ScriptedModel(replies, info=info),
            model_name="x",
            log=log,
            runs=runs,
        )
        agree &= len(result.run_ids) == runs == len(set(result.run_ids))
        results.append(result)
    log.append(
        "c" * 32,
        EventKind.MODEL_REQUEST,
        payload={"point": "zzz", "template_sha256": "9", "digest": "9"},
    )
    built = build_report(results, files=[], model_name="x", runs=1, log=log)
    seen_digests, seen_templates = set(), {}
    for result in results:
        for run_id in result.run_ids:
            for event in log.read(run_id):
                if event.kind is EventKind.MODEL_REQUEST:
                    seen_digests.add(event.payload["digest"])
                    seen_templates.setdefault(event.payload["point"], set()).add(
                        event.payload["template_sha256"]
                    )
    agree &= built.digests == sorted(seen_digests)
    agree &= built.templates == {p: sorted(v) for p, v in seen_templates.items()}
    agree &= [c.run_ids for c in built.cases] == [list(r.run_ids) for r in results]
check("60 logs give the digests and templates their runs requested, and no others", agree)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The new test file covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `run_ids` compared (`compare=True`, `CaseResult`) | `test_each_run_keeps_its_id_in_order` | pass | the `result == CaseResult(...)` assertion fails |
| 2 | the fingerprint read from every run of `log.runs()` instead of the results' run ids (`build_report`) | `test_the_fingerprint_reads_only_these_runs` | `["0" * 64]` | the digests also hold `"d" * 64` |
| 3 | the name made from `created` without turning it into UTC (`save_report`) | `test_the_name_is_the_time_in_utc` | `20261110T093015250000Z.json` | `20261110T043015250000Z.json` |
| 4 | the smallest name read instead of the greatest (`latest_report`) | `test_the_newest_name_wins` | the `20261110...` report | the `20261109...` report (`model` `old:1b`) |
| 5 | every `*.json` name read, not only the given form (`latest_report`) | `test_the_newest_name_wins` | the `20261110...` report | `ReportError: zzz.json is not a report` |
| 6 | counts compared instead of shares (`compare_lines`) | `test_the_same_shares_from_more_runs_are_no_change` | `["no change"]` | a line for each case |
| 7 | `args` with `None` on one side counted as the same (`compare_lines`) | `test_shares_compare_across_run_counts` | `weather  route 5/5 -> 9/10  args - -> 2/10` | the line without `args - -> 2/10` |
| 8 | the `added` lines left out (`compare_lines`) | `test_every_kind_of_change_in_order` | ends with two `added` lines and `removed: case say-hi` | ends `removed: case say-hi` after `weather  valid 5/5 -> 4/5` |
| 9 | the previous report read after the runs (`eval_run`) | `test_a_bad_previous_report_stops_before_any_run` | exit 1, stdout empty | stdout holds the `say-hi` line (the `weather` case finds no scripted reply left), or the runs folder exists: record which |

Reasonable variations that are correct: the fingerprint gathered in a private helper; the share test with `fractions.Fraction`; `latest_report` sorting names or taking `max`; the command printing the comparison through a loop over `compare_lines`.

## 6. Project rules

- Searches 1 to 3.
- A report holds ids, counts, times, and hashes only (read `CaseNumbers` and `Report`); it is written only under `data/evals/reports/`, mode 0600.
- An unreadable report's message is its file name only.
- No test opens a connection; the model in tests is `ScriptedModel`.

## 7. Out of scope

Each must be absent: a compare command, listing or deleting reports, comparing with an older report than the latest, an exit code from the comparison, comparing latency, any change to `case_line`, `overall_line`, the case files, routing, planning, or `decide`.

## 8. Progress log

The entry exists, headed `## Phase 8b: saved and compared evaluation reports (...)`, with `Tests: 788 -> <passed> (given 31)`, and each deviation it lists is real and justified.
