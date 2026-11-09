# Verify Phase 4c: the approvals and escalations commands

Spec: `docs/phases/phase-04c-approvals-and-escalations-commands.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py` on your own report.

The coder created `conductor.decisions` (critical), added the `approvals` and `escalations` command groups to `conductor.cli.main` and `decided_by` to the settings, added `decisions.py` to the critical modules, copied three given test files (33 tests), and wrote `tests/unit/test_decisions_more.py` and `tests/e2e/test_cli_approvals_more.py`.

## 1. Gates

N is `378`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 411 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `decisions.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/decisions.py,*/conductor/cli/main.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_decisions.py tests/e2e/test_cli_approvals.py tests/e2e/test_cli_escalations.py --no-cov` | exactly `33 passed` |
| `grep -n "^## Phase 4c: the approvals and escalations commands (" docs/progress.md` | one line |
| `.venv/bin/python scripts/check_reports.py` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- tests/unit tests/e2e/test_cli_doctor.py tests/e2e/test_cli_runs.py tests/support.py src/conductor/policy.py src/conductor/store.py src/conductor/contracts` | no output |

A missing progress entry is a finding, as in Phase 4b.

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/decisions.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|collections\.abc|typing|conductor\.contracts\.approvals|conductor\.policy|conductor\.registry|conductor\.store|conductor import clock)( |$)"`
2. `git grep --untracked -n -E "apply_decision|record_decision|\.answer\(|ApprovalDecision\(|EscalationAnswer\(" -- src/conductor/cli`
3. `git grep --untracked -n -E "from conductor\.domains import DOMAINS" -- src/conductor/cli`

## 2. Scope paths

`git status --short` lists only: `src/conductor/decisions.py`, `src/conductor/cli/main.py`, `src/conductor/config.py`, `scripts/critical_modules.txt`, `docs/testing.md`, the three given test files, `tests/unit/test_decisions_more.py`, `tests/e2e/test_cli_approvals_more.py`, `docs/progress.md`. The given files equal the spec's blocks. `git diff HEAD -- src/conductor/cli/main.py` adds the two groups and leaves `doctor` and `runs` unchanged.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_a_decided_request_is_refused_before_the_policy`, `test_an_unknown_request`, `test_a_note_that_is_too_long`; the coder's 500-character and note-first tests | pass |
| R2 | `test_an_approval_is_checked_then_recorded`, `test_an_edit_and_a_rejection`, `test_a_refused_edit_records_nothing`; the coder's store-race and `NotRegistered` tests; probe "an edit is recorded exactly when the action accepts it" | pass; ok |
| R3 | `test_an_escalation_is_answered_once`, `test_cancel_does_not_ask`; the coder's unknown and clock tests | pass |
| R4 | search 1; read `decide_approval`: the only store write comes after `apply_decision` | no output; the same |
| R5 | searches 2 and 3; `test_an_action_that_is_not_registered`; probe "every recorded decision is from the terminal, by the configured label" | no output; pass; ok |
| R6 | `test_the_pending_list`, `test_show_a_pending_request`, `test_show_a_decided_request`, `test_the_open_escalations`, `test_show_an_escalation`; the coder's `--json` answer test; probe "the JSON list round-trips into requests" | pass; ok |
| R7 | `test_approve_asks_first`, `test_approve_can_be_declined`, `test_approve_with_yes_and_reject_do_not_ask`, `test_an_edit_shows_the_new_arguments_before_asking`, `test_retry_asks_first`; the coder's declined-retry test; probes "a declined prompt never records", "declined retries stay open, cancels close" | pass; ok |
| R8 | `test_edit_arguments_must_be_a_json_object`; the coder's `Infinity` and `{}` tests | pass |
| R9 | `test_errors`, `test_an_edit_that_does_not_fit`; the coder's settings test; probe "errors go to stderr as one Error line, with no traceback" | pass; ok |
| R10 | `test_who_decides_is_a_setting`, `test_a_bad_label_is_refused` | pass |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It sets `CONDUCTOR_DATA_DIR` to its own temporary folder and drives the commands through `CliRunner`.

```python
"""Independent probe for Phase 4c. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from typer.testing import CliRunner

from conductor import domains
from conductor.cli.main import app
from conductor.contracts import Escalation
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.domains import demo
from conductor.store import Store

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


folder = Path(tempfile.mkdtemp())
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = str(folder)
domains.DOMAINS = (demo.DOMAIN,)
db = Store(folder / "conductor.db")
runner = CliRunner()
rng = random.Random(6)


def cli(*args: str, input: str | None = None):
    return runner.invoke(app, list(args), input=input)


def add(i: int) -> str:
    step = PlannedStep(
        number=1, action="demo.note", effect="write", args={"title": f"T{i}"}
    )
    db.add_request(
        ApprovalRequest(
            approval_id=f"{i:032x}",
            run_id="c" * 32,
            stage="step",
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 8, 9, i % 60, tzinfo=UTC),
        )
    )
    return f"{i:032x}"


ids = [add(i) for i in range(1, 61)]
listed = json.loads(cli("approvals", "list", "--json").stdout)
check(
    "the JSON list round-trips into requests",
    [
        ApprovalRequest.model_validate_json(json.dumps(e), strict=True).approval_id
        for e in listed
    ]
    == sorted(ids, key=lambda i: (int(i, 16) % 60, i)),
)

declined = [cli("approvals", "approve", i, input="n\n") for i in ids[:10]]
check(
    "a declined prompt never records",
    all(r.exit_code == 0 for r in declined)
    and all(db.approval(i).decision is None for i in ids[:10]),
)

titles = ["", "ok", "x" * 81, 3, None, "Fine title"]
agree = True
for approval_id in ids[10:40]:
    title = rng.choice(titles)
    result = cli(
        "approvals",
        "edit",
        approval_id,
        "--args",
        json.dumps({"title": title}),
        "--yes",
    )
    try:
        demo.NoteArgs.from_json(json.dumps({"title": title}))
        valid = True
    except ValidationError:
        valid = False
    recorded = db.approval(approval_id).decision is not None
    agree = agree and recorded == valid and (result.exit_code == 0) == valid
check("an edit is recorded exactly when the action accepts it", agree)

verdicts = []
for approval_id in ids[40:]:
    first = rng.choice([("approve", "--yes"), ("reject",)])
    second = rng.choice(
        [("approve", "--yes"), ("reject",), ("edit", "--args", "{}", "--yes")]
    )
    one = cli("approvals", first[0], approval_id, *first[1:])
    two = cli("approvals", second[0], approval_id, *second[1:])
    kept = db.approval(approval_id).decision.verdict
    verdicts.append(one.exit_code == 0 and two.exit_code == 1 and kept == first[0])
check("the first decision stays; every second one fails", all(verdicts))

errors = [
    cli("approvals", "show", "f" * 32),
    cli("approvals", "edit", ids[0], "--args", "[]", "--yes"),
    cli("escalations", "show", "f" * 32),
]
check(
    "errors go to stderr as one Error line, with no traceback",
    all(
        r.exit_code == 1
        and r.stderr.startswith("Error: ")
        and "Traceback" not in r.stderr
        for r in errors
    ),
)

for _ in range(5):
    db.add_escalation(
        Escalation(
            kind="model_unavailable",
            detail="model unavailable: timeout",
            run_id="c" * 32,
        )
    )
opened = [e.escalation_id for e in db.open_escalations()]
for escalation_id in opened[:2]:
    cli("escalations", "retry", escalation_id, input="n\n")
for escalation_id in opened[2:]:
    cli("escalations", "cancel", escalation_id)
check(
    "declined retries stay open, cancels close",
    [e.escalation_id for e in db.open_escalations()] == opened[:2],
)

recorded = [db.approval(i).decision for i in ids if db.approval(i).decision is not None]
check(
    "every recorded decision is from the terminal, by the configured label",
    all(d.channel == "terminal" and d.decided_by == "owner" for d in recorded),
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_decisions_more.py` and `tests/e2e/test_cli_approvals_more.py` cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `store.record_decision` called before `apply_decision` (`decide_approval`) | `test_a_refused_edit_records_nothing` | decision `None` | recorded |
| 2 | the already-decided check left to the store (`decide_approval`) | `test_a_decided_request_is_refused_before_the_policy` | `AlreadyDecided` | `DecisionRefused` |
| 3 | the note checked after the store is read (`decide_approval`) | `test_errors`, the 501-character note on a decided request | the note's message | `already decided` |
| 4 | `answer_escalation` builds the answer before checking (`clock.now` read first) | `test_cancel_does_not_ask`, the second `retry` | `already answered` | `StopIteration` |
| 5 | `approve` never asks | `test_approve_asks_first` | the block and `Approve? [y/N]` | `Approved` at once |
| 6 | `reject` asks | `test_approve_with_yes_and_reject_do_not_ask` | `Rejected ...` | aborted |
| 7 | `json.loads` without `parse_constant` (`edit`) | `test_edit_arguments_must_be_a_json_object`, `NaN` | the `--args` error | a `ValidationError` from the decision contract |
| 8 | the registry built from `DOMAINS` imported by name at module load | `test_approve_with_yes_and_reject_do_not_ask` | `Approved` | `no action demo.note` |
| 9 | the `edited args:` line left out of the request block | `test_show_a_decided_request` | the pinned text | without it |

Reasonable variations that are correct: private helpers that render the blocks; one `_fail(error)` that prints a refused edit's problems; `typer.Option` declarations with `Annotated`; `--json` output built from `model_dump(mode="json")` in a helper.

## 6. Project rules

- Searches 1 to 3: the commands never build or record decisions themselves.
- `cli/main.py` contains no verdict logic: no comparison of verdicts, digests, or effects.
- Every error is one `Error:` line on stderr (plus a refused edit's `loc: code` lines), exit 1.

## 7. Out of scope

Each must be absent: resuming threads, leases in the commands, events, the approvals page, an editor, `--args-file`, bulk approval, listing decided requests, answers other than retry and cancel, changes to `policy.py`, `store.py`, the contracts, or the existing commands.

## 8. Progress log

The entry exists, headed `## Phase 4c: the approvals and escalations commands (...)`, with `Tests: 378 -> <passed> (given 33)`, and each deviation it lists is real and justified.
