# Verify Phase 3b: the Ollama client and the scripted model

Spec: `docs/phases/phase-03b-ollama-client-and-scripted-model.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py` on your own report.

The coder created `conductor.llm.model`, `conductor.llm.ollama`, and `conductor.llm.scripted`, added the `model_timeout` setting to `conductor.config`, replaced `tests/support.py` with the given version, copied three given test files (32 tests), and wrote `tests/unit/test_ollama_more.py`.

## 1. Gates

N is `242`. Sections: core, cli.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first core,cli` | last line `All checks passed.`; the summary lists `tests (core,cli): passed`; at least 274 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/llm/model.py,*/conductor/llm/ollama.py,*/conductor/llm/scripted.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_ollama.py tests/unit/test_scripted.py tests/unit/test_config_timeout.py --no-cov` | exactly `32 passed` |
| `.venv/bin/python scripts/check_reports.py` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/llm/tags.py src/conductor/llm/points.py src/conductor/llm/prompts.py src/conductor/contracts tests/unit tests/e2e tests/conftest.py` | no output |

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/llm/model.py src/conductor/llm/ollama.py src/conductor/llm/scripted.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (__future__|dataclasses|http\.client|json|re|typing|collections\.abc|urllib\.error|urllib\.request|conductor\.llm\.model|conductor\.llm\.points)( |$)"`
2. `git grep --untracked -n -E "^(from|import) (ollama|httpx|requests)|os\.environ|getenv|keep_alive" -- src/conductor`

## 2. Scope paths

`git status --short` lists only: `src/conductor/llm/model.py`, `src/conductor/llm/ollama.py`, `src/conductor/llm/scripted.py`, `src/conductor/config.py`, `tests/support.py`, the three given test files, `tests/unit/test_ollama_more.py`, `docs/progress.md`. `tests/support.py` and the given tests equal the spec's blocks. `git diff HEAD -- src/conductor/config.py` adds only the field, the property, the message constant, and the one check.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_tags_with_an_http_error`, `test_a_model_that_is_not_installed`; read `model.py` against the Design | pass; the same fields and defaults |
| R2 | `test_the_chat_request`; the coder's UTF-8 body test; probe "model_info asks the given host every time, whatever OLLAMA_HOST says" | pass; ok |
| R3 | `test_a_chat_http_error`, `test_nothing_listening`, `test_a_silent_server_times_out`; the coder's tags-404, connect-timeout, reset, and `IncompleteRead` tests; probe "HTTP errors carry only the code and status" | pass; ok |
| R4 | `test_the_model_info_is_read_from_the_tags`, `test_a_model_that_is_not_installed`, `test_tags_that_do_not_fit`; probe "an untagged name finds :latest, a tagged one itself" | pass; ok |
| R5 | `test_a_chat_answer_becomes_a_reply`, `test_a_short_chat_answer_gets_defaults`, `test_a_chat_answer_that_does_not_fit`; the coder's `true`/`-1`/`null`/`7` tests; probe "any reply text comes back as it was sent" | pass; ok |
| R6 | `test_tags_that_do_not_fit[not json]`; the coder's `b"\xff"` test; probe "every cut of a good answer is bad_answer" | pass; ok |
| R7 | `test_replies_come_in_order`, `test_a_reply_for_another_point`, `test_no_reply_left`, `test_a_scripted_failure_is_raised_in_its_turn`; probe "a long script plays in order and then runs out" | pass; ok |
| R8 | `test_the_model_info`; the coder's copy and `remaining` tests | pass |
| R9 | `test_config_timeout.py`; probe "exactly 1 to 3600 are accepted" | pass; ok |
| R10 | searches 1 and 2 | no output |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It starts its own server on 127.0.0.1 and sets `OLLAMA_HOST` and `HTTP_PROXY` to a closed port to show that neither is used.

```python
"""Independent probe for Phase 3b. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer

from conductor.config import SettingsError, get_settings
from conductor.domains import demo
from conductor.llm.model import ModelReply, ModelUnavailable
from conductor.llm.ollama import OllamaModel
from conductor.llm.points import build_request
from conductor.llm.scripted import ScriptedModel, ScriptedReply, ScriptError

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


class State:
    status = 200
    body = b"{}"
    gets = 0


class Handler(BaseHTTPRequestHandler):
    def _send(self) -> None:
        self.send_response(State.status)
        self.send_header("Content-Length", str(len(State.body)))
        self.end_headers()
        self.wfile.write(State.body)

    def do_GET(self) -> None:
        State.gets += 1
        self._send()

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self._send()

    def log_message(self, *args: object) -> None:
        pass


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
host = f"http://127.0.0.1:{server.server_address[1]}"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"
os.environ["HTTP_PROXY"] = os.environ["http_proxy"] = "http://127.0.0.1:9"
model = OllamaModel(host, timeout=5)
request = build_request(
    demo.PICK,
    demo.PickInputs(request="probe"),
    model="probe:1b",
    fields=demo.pick_fields(),
)


def outcome(call):
    try:
        return call()
    except ModelUnavailable as error:
        return error


rng = random.Random(5)
alphabet = 'a "\\\n{}é漢 '
contents = [
    "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40))) for _ in range(40)
]
same = True
for content in contents:
    State.status, State.body = (
        200,
        json.dumps(
            {"done": True, "done_reason": "stop", "message": {"content": content}}
        ).encode(),
    )
    same = same and model.chat(request) == ModelReply(content=content)
check("any reply text comes back as it was sent", same)

good = json.dumps(
    {"done": True, "done_reason": "stop", "message": {"content": "{}"}, "eval_count": 3}
).encode()
cuts = []
for end in range(len(good)):
    State.body = good[:end]
    cuts.append(outcome(lambda: model.chat(request)))
check(
    "every cut of a good answer is bad_answer",
    all(isinstance(c, ModelUnavailable) and c.code == "bad_answer" for c in cuts),
)

texts = []
State.body = b'{"error": "SECRET model text"}'
for status in (400, 401, 403, 405, 409, 429, 500, 502, 503):
    State.status = status
    texts.append(str(outcome(lambda: model.chat(request))))
State.status = 404
texts.append(str(outcome(lambda: model.chat(request))))
check(
    "HTTP errors carry only the code and status",
    texts[:-1]
    == [
        f"model unavailable: http_error {s}"
        for s in (400, 401, 403, 405, 409, 429, 500, 502, 503)
    ]
    and texts[-1] == "model unavailable: not_installed",
)

entries = [
    {"name": f"m{i}:{tag}", "digest": f"{i:064x}"}
    for i in range(10)
    for tag in ("latest", "7b")
]
State.status, State.body, State.gets = 200, json.dumps({"models": entries}).encode(), 0
names = [model.model_info(f"m{i}").name for i in range(10)]
tagged = [model.model_info(f"m{i}:7b").digest for i in range(10)]
check(
    "an untagged name finds :latest, a tagged one itself",
    names == [f"m{i}:latest" for i in range(10)]
    and tagged == [f"{i:064x}" for i in range(10)],
)
check(
    "model_info asks the given host every time, whatever OLLAMA_HOST says",
    State.gets == 20,
)

points = [rng.choice(["a", "b", "c"]) for _ in range(200)]
replies = [ModelReply(content=str(i)) for i in range(200)]
scripted = ScriptedModel(
    [ScriptedReply(p, r) for p, r in zip(points, replies, strict=True)]
)
handed = [scripted.chat(replace(request, point=p)) for p in points]
try:
    scripted.chat(request)
    ran_out = False
except ScriptError:
    ran_out = True
check(
    "a long script plays in order and then runs out",
    all(h is r for h, r in zip(handed, replies, strict=True)) and ran_out,
)

accepted = []
for value in [str(n) for n in range(4001)] + [
    "",
    " 1",
    "1 ",
    "+5",
    "05",
    "1e3",
    "٣",
]:
    os.environ["CONDUCTOR_MODEL_TIMEOUT"] = value
    try:
        accepted.append(get_settings().model_timeout_seconds)
    except SettingsError:
        pass
del os.environ["CONDUCTOR_MODEL_TIMEOUT"]
check("exactly 1 to 3600 are accepted", accepted == list(range(1, 3601)))

server.shutdown()
print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

`tests/unit/test_ollama_more.py` covers each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `except OSError` placed before the timeout clause (`OllamaModel`'s request helper) | `test_a_silent_server_times_out` | `timeout` | `unreachable` |
| 2 | `urllib.request.urlopen` instead of the proxy-free opener | `test_the_chat_request`, `HTTP_PROXY` set to port 9 | the fake gets the post | `unreachable` |
| 3 | the `:latest` fallback removed (`model_info`) | `test_the_model_info_is_read_from_the_tags`, `"plain"` | `plain:latest` | `not_installed` |
| 4 | capabilities kept in Ollama's order (`model_info`) | `test_the_model_info_is_read_from_the_tags` | `("completion", "thinking")` | `("thinking", "completion")` |
| 5 | the tags answer cached on the client (`model_info`) | `test_the_model_info_is_read_from_the_tags` | two `/api/tags` | one |
| 6 | 404 mapped to `not_installed` for `/api/tags` too | the coder's tags-404 test | `http_error 404` | `not_installed` |
| 7 | the point check removed (`ScriptedModel.chat`) | `test_a_reply_for_another_point` | `ScriptError` | `NOTE` returned |
| 8 | the timeout parsed with `int(value.strip())` and a range check (`get_settings`) | `test_a_timeout_out_of_range_or_not_whole`, `" 30 "` | refused | accepted |
| 9 | `json.dumps(request.body())` with the default `ensure_ascii` (`chat`) | the coder's UTF-8 body test, `"Résumé"` | `R\xc3\xa9sum\xc3\xa9` | `R\\u00e9sum\\u00e9` |
| 10 | `bool` accepted for counts (`chat`) | the coder's `eval_count: true` test | `bad_answer` | accepted |

Reasonable variations that are correct: a private Pydantic model with `extra="ignore"` for the answers, as long as no `ValidationError` text escapes; one private request helper shared by both calls; `ScriptedModel` keeping a `deque` or an index; `ModelUnavailable` storing `status` only for `http_error`.

## 6. Project rules

- Searches 1 and 2; no header besides `Content-Type` in `ollama.py`.
- Every `ModelUnavailable` and `ScriptError` message is one of the spec's: codes, HTTP status, point names, and positions only.
- No retry and no sleep anywhere in `ollama.py`.

## 7. Out of scope

Each must be absent: `decide`, choosing `think` from capabilities, checking `done_reason`, validating reply content against a point's output, event logging, escalations, retries, caching, streaming, `keep_alive`, `/api/show` or `/api/ps`, changes to `tags.py`, the doctor, `points.py`, `prompts.py`, or `conductor.contracts`.

## 8. Progress log

The entry exists, headed `## Phase 3b: the Ollama client and the scripted model (...)`, with `Tests: 242 -> <passed> (given 32)`, and each deviation it lists is real and justified.
