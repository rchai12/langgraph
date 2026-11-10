# Verify Phase 7b: deciding on the page

Spec: `docs/phases/phase-07b-deciding-on-the-page.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 7b` on your own report.

The coder added `decisions.parse_json_object` (the terminal now uses it), the forms, the `POST` routes, and the run page to `conductor.web.app`, created `conductor.web.jobs.Resumer` (critical), copied two test files (30 tests), and wrote two of their own.

## 1. Gates

N is `704`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 734 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `web/jobs.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/web/*.py,*/conductor/decisions.py,*/conductor/cli/main.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/e2e/test_web_decide.py tests/e2e/test_web_runs.py --no-cov` | exactly `30 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 7b` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/store.py src/conductor/policy.py src/conductor/runtime.py src/conductor/graph tests/e2e/test_web_pages.py tests/e2e/test_cli_approvals.py tests/e2e/test_cli_ask.py tests/support.py` | no output |
| `git diff HEAD -- src/conductor/decisions.py` | only `parse_json_object` added |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/web | grep -v -E ":from conductor(\.config|\.decisions|\.graph\.supervisor|\.mcp_client\.check|\.policy|\.registry|\.store|\.views)? import "`
2. `git grep --untracked -n -E "add_request|record_decision|\.answer\(|add_escalation|apply_decision|start_run|resume_run" -- src/conductor/web`
3. `git grep --untracked -n -i -E "<script|\bon[a-z]+=|https?://" -- src/conductor/web/templates`
4. `git grep --untracked -n -E "daemon=True" -- src/conductor/web`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | the coder's `parse_json_object` test; the 4c `edit --args` tests unchanged in the full check | pass |
| R2 | `test_a_pending_step_has_its_forms` (the cookie and its flags), the `token` helper in every given test; the coder's valid-cookie test | pass |
| R3 | `test_a_pending_step_has_its_forms`, `test_a_plan_cannot_be_edited_and_a_decided_request_has_no_forms`, `test_an_escalation_is_answered_from_the_web` (2 cases) | pass |
| R4 | `test_a_form_without_its_token_is_refused` (3 cases), `test_a_token_without_its_cookie_is_refused`, `test_the_origin_of_a_form` (4 cases), `test_deciding_what_is_not_there` (3 cases); the coder's no-store test; probe "a decision is recorded exactly when origin, cookie, and token all fit" | pass; ok |
| R5 | `test_approve_records_from_the_web_and_resumes`, `test_an_edit_carries_its_note_and_arguments`; search 2 | pass; no output |
| R6 | `test_edited_arguments_must_be_a_json_object` (3 cases), `test_an_edit_the_action_refuses_lists_its_problems`, `test_a_second_decision_is_refused`, `test_a_note_too_long_is_refused`; the coder's `NotRegistered`, `503`, and link tests; probe "of two decisions sent at once ..." | pass; ok |
| R7 | `test_a_waiting_run_links_to_what_it_waits_for`, `test_a_busy_run_refreshes_itself`, `test_the_last_resume_error_is_shown`, `test_a_run_that_is_not_there` (2 cases); the coder's four status tests | pass |
| R8 | `test_a_decision_resumes_the_run_in_the_background`, `test_a_resume_that_fails_is_recorded_not_raised`; the coder's resumer tests; search 4; probe "three plans approved on the page resume in the background" | pass; no output; ok |
| R9 | `test_approve_records_from_the_web_and_resumes`, `test_a_second_decision_is_refused` (`started == [RUN]`); the coder's no-resume tests | pass |
| R10 | search 1 | no output |
| R11 | the coverage gate and `critical coverage` | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It sends 72 forms covering every combination of cookie (the page's, none, another), token (the same, none, another, too short), and origin (none, both of this server's, another site, `null`, the `finances` port), races approve against reject on one request ten times, and approves three real plans whose runs then resume in the background. Its reading of the form rules checks itself on known cases first; a stop at those `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 7b. Run from the repository root with .venv/bin/python."""

import itertools
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from conductor import runtime
from conductor.config import get_settings
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.store import Store
from conductor.web.app import FORM_COOKIE, create_app
from conductor.web.jobs import Resumer

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = str(Path(tempfile.mkdtemp()) / "data")
os.environ["CONDUCTOR_DEMO"] = "true"
os.environ["CONDUCTOR_OLLAMA_HOST"] = "http://127.0.0.1:9"
BASE = "http://127.0.0.1:8766"
db = Store(get_settings().db_path)


class Quiet:
    def start(self, run_id):
        pass

    def running(self, run_id):
        return False

    def error(self, run_id):
        return None


counter = itertools.count(1)


def add() -> str:
    approval_id = f"{next(counter):032x}"
    step = PlannedStep(number=1, action="demo.note", effect="write", args={"title": "Milk"})
    db.add_request(
        ApprovalRequest(
            approval_id=approval_id,
            run_id="a" * 32,
            stage="step",
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
        )
    )
    return approval_id


def accepted(cookie: str, token: str, origin: str | None) -> bool:
    """The probe's own reading of the form rules."""
    good_origin = origin in (None, BASE, "http://localhost:8766")
    return good_origin and len(cookie) == 64 and cookie == token


assert accepted("a" * 64, "a" * 64, None)
assert not accepted("a" * 64, "b" * 64, BASE)
assert not accepted("", "", BASE)
assert not accepted("a" * 64, "a" * 64, "http://evil.example")

# 1. every combination of cookie, token, and origin
agree = True
real = None
for cookie_kind, token_kind, origin in itertools.product(
    ["real", "none", "other"],
    ["same", "none", "other", "short"],
    [None, BASE, "http://localhost:8766", "http://evil.example", "null", "http://127.0.0.1:8765"],
):
    approval_id = add()
    page = TestClient(create_app(get_settings(), resumer=Quiet()), base_url=BASE)
    text = page.get(f"/approvals/{approval_id}").text
    real = re.search(r'name="token" value="([0-9a-f]{64})"', text).group(1)
    cookie = {"real": real, "none": "", "other": "c" * 64}[cookie_kind]
    page.cookies.clear()
    if cookie:
        page.cookies.set(FORM_COOKIE, cookie)
    token = {"same": cookie or real, "none": "", "other": "d" * 64, "short": "e"}[token_kind]
    form = {"token": token} if token else {}
    headers = {} if origin is None else {"origin": origin}
    response = page.post(
        f"/approvals/{approval_id}/approve", data=form, headers=headers, follow_redirects=False
    )
    recorded = db.approval(approval_id).decision is not None
    expected = accepted(cookie, token, origin)
    agree &= recorded == expected and response.status_code == (303 if expected else 403)
check("a decision is recorded exactly when origin, cookie, and token all fit (72 forms)", agree)

# 2. two decisions on one request at once
ok_race = True
for _ in range(10):
    approval_id = add()
    page = TestClient(create_app(get_settings(), resumer=Quiet()), base_url=BASE)
    text = page.get(f"/approvals/{approval_id}").text
    token = re.search(r'name="token" value="([0-9a-f]{64})"', text).group(1)
    codes = []
    barrier = threading.Barrier(2)

    def send(
        verdict: str, barrier=barrier, page=page, approval_id=approval_id, token=token, codes=codes
    ) -> None:
        barrier.wait()
        r = page.post(
            f"/approvals/{approval_id}/{verdict}",
            data={"token": token},
            headers={"origin": BASE},
            follow_redirects=False,
        )
        codes.append(r.status_code)

    threads = [threading.Thread(target=send, args=(v,)) for v in ("approve", "reject")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ok_race &= sorted(codes) == [303, 409] and db.approval(approval_id).decision is not None
check("of two decisions sent at once, one is recorded and one gets 409 (10 races)", ok_race)

# 3. real background resumes
plan = '{"steps": [{"action": "note", "args": {"title": "Milk"}}]}'
resumer = Resumer(get_settings())
page = TestClient(create_app(get_settings(), resumer=resumer), base_url=BASE)
ok_bg = True
for _ in range(3):
    with runtime.open_runtime(
        get_settings(), model=ScriptedModel([ScriptedReply("plan", ModelReply(content=plan))])
    ) as opened:
        state = runtime.ask(opened, "demo: note Milk")
    text = page.get(f"/approvals/{state.approval_id}").text
    token = re.search(r'name="token" value="([0-9a-f]{64})"', text).group(1)
    page.post(
        f"/approvals/{state.approval_id}/approve",
        data={"token": token},
        headers={"origin": BASE},
        follow_redirects=False,
    )
    resumer.join(state.run_id, timeout=30)
    with runtime.open_runtime(get_settings()) as opened:
        after = runtime.state(opened, state.run_id)
    ok_bg &= after.status == "waiting" and after.approval_id not in (None, state.approval_id)
    ok_bg &= resumer.error(state.run_id) is None
check("three plans approved on the page resume in the background to their step approval", ok_bg)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The two new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the token compared only when a cookie is present (a missing cookie passes) | `test_a_token_without_its_cookie_is_refused` | `403 Bad form token` | `303` |
| 2 | the token check accepts any 64-hex token (no comparison with the cookie) | `test_a_form_without_its_token_is_refused`, `"0" * 64` | `403` | `303` |
| 3 | the origin check removed | `test_the_origin_of_a_form`, `http://evil.example` | `403 Bad origin` | `303` |
| 4 | a missing `Origin` refused | `test_the_origin_of_a_form`, `None` | `303` | `403` |
| 5 | the decision recorded with `channel="terminal"` | `test_approve_records_from_the_web_and_resumes` | `web` | `terminal` |
| 6 | `resumer.start` called before the decision (also when it is refused) | `test_a_second_decision_is_refused` | `started == [RUN]` | `[RUN, RUN]` |
| 7 | the edit form shown for a plan request | `test_a_plan_cannot_be_edited_and_a_decided_request_has_no_forms` | no `/edit` form | an `/edit` form |
| 8 | the refresh tag on every run page | `test_a_waiting_run_links_to_what_it_waits_for` | no `refresh` | `refresh` |
| 9 | the resumer's thread lets a `RunError` out instead of keeping it | `test_a_resume_that_fails_is_recorded_not_raised` | `no run 9999...` | `None` |

Reasonable variations that are correct: the five `POST` routes sharing one private "check, decide, answer" helper; `Form()` parameters or `await request.form()`; the token made in a dependency; the run page's table as one template with conditions; the resumer's threads in a dictionary under its lock.

## 6. Project rules

- Searches 1 to 4.
- A decision is recorded only through `conductor.decisions`, after the origin and token checks.
- No script, event attribute, or outside URL in any template or page; every stored text is escaped.
- No test or probe opens a connection beyond 127.0.0.1.

## 7. Out of scope

Each must be absent: a login or sessions, a confirmation page, per-field edit forms, bulk decisions, stopping a run, a runs list, scripts, changes to `decisions`' rules, the store, the policy, the runtime, or what the terminal prints.

## 8. Progress log

The entry exists, headed `## Phase 7b: deciding on the page (...)`, with `Tests: 704 -> <passed> (given 30)`, and each deviation it lists is real and justified.
