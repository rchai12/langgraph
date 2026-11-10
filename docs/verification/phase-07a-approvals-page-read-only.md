# Verify Phase 7a: the approvals page, read-only

Spec: `docs/phases/phase-07a-approvals-page-read-only.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 7a` on your own report.

The coder added `fastapi` and `jinja2` and installed them, added `web_port` to the settings, moved the terminal's block lines into `conductor.views`, created `conductor.web.app` (critical) and its templates, added `conductor web`, copied two test files (26 tests), and wrote two of their own.

## 1. Gates

N is `664`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 690 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `web/app.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/web/*.py,*/conductor/views.py,*/conductor/config.py,*/conductor/cli/main.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/e2e/test_web_pages.py tests/e2e/test_cli_web.py --no-cov` | exactly `26 passed` |
| `.venv/bin/python -c "import importlib.metadata as m; print(m.version('fastapi'), m.version('jinja2'), m.version('starlette'))"` | `0.162.x 3.1.x 1.10.0` |
| `.venv/bin/python scripts/check_reports.py --phase 7a` (before writing your report) | `Reports OK.` |
| `git diff HEAD -- pyproject.toml` | the two dependency lines and the template line, nothing else |
| `git diff --stat HEAD -- src/conductor/store.py src/conductor/decisions.py src/conductor/runtime.py src/conductor/graph tests/e2e/test_cli_approvals.py tests/e2e/test_cli_escalations.py tests/e2e/test_cli_approvals_more.py tests/e2e/test_cli_ask.py tests/support.py` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) conductor" -- src/conductor/web | grep -v -E ":(from conductor\.config|from conductor\.store|from conductor\.views) import "`
2. `git grep --untracked -n -i -E "<script|\bon[a-z]+=|https?://" -- src/conductor/web/templates`
3. `git grep --untracked -n -E "0\.0\.0\.0|host=\"(::|localhost)\"" -- src`
4. `git grep --untracked -n -E "add_request|record_decision|\.answer\(|add_escalation|acquire\(" -- src/conductor/web`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks; `docs/testing.md` and `scripts/critical_modules.txt` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_the_default_port`, `test_a_bad_port_setting` (3 cases) | pass |
| R2 | the coder's `test_views.py`; every earlier CLI test, unchanged, in the full check; read `cli/main.py`: no block code left there | pass; the same |
| R3 | `test_only_this_server_by_name_is_answered` (3 cases), `test_localhost_by_port_is_answered`; the coder's two-headers test; probe "only two Host values are answered" | pass; ok |
| R4 | `test_every_answer_carries_the_security_headers` (2 cases), `test_the_headers`; the coder's 405 and 503 tests; probe "every answer carries the security headers" | pass; ok |
| R5 | `test_an_empty_home_page`, `test_the_home_page_lists_what_waits_oldest_first`, `test_a_pending_approval`, `test_a_decided_approval_shows_who_decided_and_the_edit`, `test_an_escalation_and_its_answer`, `test_nothing_else_is_served` (3 cases); the coder's plan and two-escalation tests | pass |
| R6 | `test_text_from_a_request_is_escaped`; the coder's note, detail, and actions tests; search 2; probe "no stored text becomes markup" | pass; no output; ok |
| R7 | `test_what_is_not_there` (3 cases), `test_a_store_that_cannot_be_read`; the coder's capitals test | pass |
| R8 | `test_the_web_command_serves_on_this_machine_only`, `test_a_port_in_use_is_refused`; probe "the real server answers on 127.0.0.1 with no server header"; search 3 | pass; ok; no output |
| R9 | searches 1 and 4 | no output |
| R10 | the coverage gate and `critical coverage` | as in the Gates |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It stores 40 requests and 10 escalations whose texts mix script tags, event attributes, quotes, entities, a right-to-left mark, and template syntax, checks every page, tries 21 `Host` values, and starts the real server with uvicorn on a free 127.0.0.1 port in a thread to fetch the home page over a real connection. Its page reader checks itself on known text first; a stop at those `assert` lines is the probe's fault: report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 7a. Run from the repository root with .venv/bin/python."""

import http.client
import os
import random
import socket
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from conductor.config import get_settings
from conductor.contracts import Escalation, FieldProblem
from conductor.contracts.approvals import ApprovalRequest, PlannedStep, steps_digest
from conductor.store import Store
from conductor.web.app import SECURITY_HEADERS, create_app

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(71)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
folder = Path(tempfile.mkdtemp())
os.environ["CONDUCTOR_DATA_DIR"] = str(folder / "data")
probe = socket.socket()
probe.bind(("127.0.0.1", 0))
PORT = probe.getsockname()[1]
probe.close()
os.environ["CONDUCTOR_WEB_PORT"] = str(PORT)
db = Store(folder / "data" / "conductor.db")
NASTY = ["<script>", "<img src=x onerror=1>", "&amp;", '"', "'", "é", "\u202e", "{{ 7*7 }}"]
RAW = ("<script>", "<img src=x onerror=1>")


def unsafe(text: str) -> bool:
    """The probe's own reading of a page: an injected payload appears as markup."""
    return any(payload in text for payload in RAW)


assert unsafe("<p><script>x</p>")
assert not unsafe("<p>&lt;script&gt;</p>")

ids = []
for i in range(40):
    text = "".join(rng.choice(NASTY + ["a", " ", "b"]) for _ in range(rng.randint(1, 8)))
    step = PlannedStep(
        number=1, action="demo.note", effect="write", args={"title": text[:80] or "x"}
    )
    approval_id = f"{i + 1:032x}"
    db.add_request(
        ApprovalRequest(
            approval_id=approval_id,
            run_id="a" * 32,
            stage="step",
            steps=(step,),
            args_sha256=steps_digest((step,)),
            requested_at=datetime(2026, 11, 9, 9, i % 60, tzinfo=UTC),
        )
    )
    ids.append(approval_id)
    if i % 4 == 0:
        db.add_escalation(
            Escalation(
                kind="invalid_plan",
                detail=(text or "x")[:500],
                run_id="a" * 32,
                problems=(
                    FieldProblem(loc=f"steps.0.{rng.choice(['a', 'b'])}", code="value_error"),
                ),
            )
        )
client = TestClient(create_app(get_settings()), base_url=f"http://127.0.0.1:{PORT}")

# 1. no stored text becomes markup
pages = [client.get("/")] + [client.get(f"/approvals/{i}") for i in ids]
pages += [client.get(f"/escalations/{s.escalation_id}") for s in db.open_escalations()]
check(
    f"no stored text becomes markup on {len(pages)} pages",
    all(p.status_code == 200 and not unsafe(p.text) for p in pages),
)

# 2. every answer carries the headers, whatever the request
answers = pages + [client.get("/approvals/zz"), client.post("/"), client.get("/docs")]
answers.append(TestClient(create_app(get_settings()), base_url="http://evil.example").get("/"))
check(
    "every answer carries the security headers",
    all(all(a.headers.get(n) == v for n, v in SECURITY_HEADERS.items()) for a in answers),
)

# 3. only the two names with this port are answered
names = ["127.0.0.1", "localhost", "evil.example", "127.0.0.2", "[::1]", "0.0.0.0", "LOCALHOST"]
ports = [str(PORT), str(PORT + 1), ""]
answered = set()
for name in names:
    for port in ports:
        host = f"{name}:{port}" if port else name
        status = (
            TestClient(create_app(get_settings()), base_url=f"http://{host}").get("/").status_code
        )
        if status == 200:
            answered.add(host)
check(
    f"only two Host values are answered ({sorted(answered)})",
    answered == {f"127.0.0.1:{PORT}", f"localhost:{PORT}"},
)

# 4. the real server, started as conductor web starts it
server = uvicorn.Server(
    uvicorn.Config(
        create_app(get_settings()),
        host="127.0.0.1",
        port=PORT,
        server_header=False,
        proxy_headers=False,
        log_level="warning",
    )
)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
for _ in range(50):
    if server.started:
        break
    time.sleep(0.1)
connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
connection.request("GET", "/")
response = connection.getresponse()
body = response.read().decode()
headers = {k.lower(): v for k, v in response.getheaders()}
server.should_exit = True
thread.join(timeout=5)
check(
    "the real server answers on 127.0.0.1 with no server header",
    response.status == 200 and "server" not in headers and "No open escalations." not in body,
)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The two new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate. Write down what the broken run printed; a different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | the host check accepts any port of `localhost` (compares the name only) | `test_only_this_server_by_name_is_answered`, `localhost` | `400 Bad host` | `200` |
| 2 | the security headers added only to responses of the app, not to the host check's refusal | `test_only_this_server_by_name_is_answered`, `evil.example` | `x-frame-options: DENY` | no such header |
| 3 | autoescape turned off for the templates | `test_text_from_a_request_is_escaped` | `&lt;script&gt;` | `<script>` |
| 4 | the id pattern check removed, so any id reaches the store (`/approvals/<id>`) | the coder's R7 capitals test (`"A" * 32`, with `Store` replaced by one that fails) | `404 Not found`, the store never opened | the failing store is opened |
| 5 | `StoreError` not caught (`/`) | `test_a_store_that_cannot_be_read` | `503` | `500` or an exception |
| 6 | `docs_url` left at its default | `test_nothing_else_is_served`, `/docs` | `404` | `200` |
| 7 | `server_header=False` left out (`conductor web`) | `test_the_web_command_serves_on_this_machine_only` | `False` | missing key |
| 8 | the port check left out (`conductor web`) | `test_a_port_in_use_is_refused` | `Error: port <n> is taken` | `Serving on ...` |

Reasonable variations that are correct: the host check as Starlette `TrustedHostMiddleware` only if it also carries the headers on its refusal and checks the port (it does not by itself, so a pure ASGI wrapper as in `finances` is the expected shape); one base template with blocks; `HTMLResponse` built from `Jinja2Templates`; the store opened through a small dependency function.

## 6. Project rules

- Searches 1 to 4.
- The page binds and answers only 127.0.0.1 and `localhost` with its port; it never writes the store.
- No script, event attribute, or outside URL in any template or page; every stored text is escaped.
- No test or probe opens a connection beyond 127.0.0.1.

## 7. Out of scope

Each must be absent: forms, `POST` routes, decisions, resuming, a login or sessions, runs and events on the page, refreshing, static files, CSS, scripts, images, fonts, a CDN, changes to what the terminal prints, changes to the store, `decisions`, the runtime, or the graph.

## 8. Progress log

The entry exists, headed `## Phase 7a: the approvals page, read-only (...)`, with `Tests: 664 -> <passed> (given 26)`, and each deviation it lists is real and justified.
