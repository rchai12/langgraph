# Verify Phase 5a: routing

Spec: `docs/phases/phase-05a-routing.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 5a` on your own report (this phase adds the option and edits that line of the conventions).

The coder added `Rule` and `Domain.rules` to `conductor.registry`, created `conductor.routing.rules` and `conductor.routing.route` (both critical), added `--phase` to the report checker and the digest to `conductor doctor`, made the given edits to `demo.py`, `tests/support.py`, and `tests/e2e/test_cli_doctor.py`, copied the given prompt template and five test files (37 tests), and wrote four test files of their own.

## 1. Gates

N is `423`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 460 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table; `critical coverage` passed (it now includes `routing/rules.py` and `routing/route.py`) |
| `.venv/bin/python -m coverage report --include="*/conductor/routing/*.py,*/conductor/reports.py,*/conductor/registry.py,*/conductor/diagnostics.py,*/conductor/llm/tags.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_rules.py tests/unit/test_route.py tests/unit/test_reports_phase.py tests/e2e/test_check_reports_phase.py tests/e2e/test_cli_doctor_digest.py --no-cov` | exactly `37 passed` |
| `.venv/bin/python scripts/check_reports.py --phase 5a` (before writing your report) | `Reports OK.` |
| `.venv/bin/python scripts/check_reports.py --phase 5b` | `docs/phases:1: no spec for Phase 5b`, `docs/progress.md:1: no progress entry for Phase 5b`, `2 problems.`, exit 1 (the option works on the real repository) |
| `git diff --stat HEAD -- src/conductor/contracts src/conductor/llm/decide.py src/conductor/llm/points.py src/conductor/events.py src/conductor/domains/__init__.py tests/unit/test_registry.py tests/unit/test_registry_more.py tests/unit/test_reports.py tests/e2e/test_check_reports_script.py` | no output |

A missing progress entry is a finding.

Searches, each with no output:

1. `git grep --untracked -n -E "^(from|import) " -- src/conductor/routing/rules.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (re|dataclasses|conductor\.contracts|conductor\.registry)( |$)"`
2. `git grep --untracked -n -E "^(from|import) " -- src/conductor/routing/route.py | grep -v -E "^[^:]+:[0-9]+:(from|import) (dataclasses|typing|pydantic|conductor\.contracts|conductor\.events|conductor\.llm\.decide|conductor\.llm\.model|conductor\.llm\.points|conductor\.registry|conductor\.routing\.rules)( |$)"`
3. `git grep --untracked -n -E "get_settings|clock|new_id|OllamaModel|urllib" -- src/conductor/routing`
4. `git grep --untracked -n -E "langgraph|langchain" -- src pyproject.toml`

## 2. Scope paths

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks; `git diff HEAD -- src/conductor/domains/demo.py tests/support.py tests/e2e/test_cli_doctor.py` shows exactly the given edits; `docs/testing.md`, `scripts/critical_modules.txt`, and `docs/phase-conventions.md` carry exactly the spec's edits.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | `test_rule_declarations_are_checked`, `test_the_demo_rules`; the coder's duplicate, 21-phrase, long-phrase, and order tests | pass |
| R2 | `test_words`, `test_phrases_match_whole_words_in_order`; the coder's non-ASCII test; probe "keyword rules agree with an independent matcher" | pass; ok |
| R3 | `test_a_prefix_routes_and_is_stripped`, `test_a_prefix_wins_over_keyword_rules`, `test_only_a_registered_name_and_a_colon_make_a_prefix`; probe "a registered prefix routes ..." | pass; ok |
| R4 | `test_a_keyword_rule_routes_and_keeps_the_request`, `test_the_first_rule_of_the_domain_decides`, `test_rules_of_two_domains_conflict`, `test_no_domains_no_rules`; the probe's matcher check | pass; ok |
| R5 | `test_the_route_point_and_its_prompt`; the coder's one-domain test | pass |
| R6 | `test_a_rule_route_asks_no_model`, `test_rules_of_two_domains_escalate`, `test_nothing_after_the_prefix_escalates`, `test_no_domains_escalate_without_asking`, `test_a_request_must_have_1_to_2000_characters`; probes "a rule route or a rule conflict never asks the model", "with no domains ..." | pass; ok |
| R7 | `test_the_classifier_picks_a_domain`, `test_unknown_escalates`, `test_a_failed_decision_escalates`; the coder's `model_info` and `ScriptError` tests; probe "the classifier routes only to registered domains" | pass; ok |
| R8 | searches 1 to 3 | no output |
| R9 | `test_a_phase_needs_its_spec_and_its_entry`, `test_a_phase_id_is_checked`, `test_the_phase_option`; the two `--phase` gates; probe "check_reports --phase ..." | pass; the same; ok |
| R10 | `test_a_model_listed_without_a_valid_digest`, the edited doctor tests; the coder's `fetch_models` test; probe "the doctor shows ..." | pass; ok |

## 4. Probe

Save outside the repository, run from the repository root with `.venv/bin/python <path>`, then delete it. Every line must start with `ok` and the last must be `FAILURES 0`. It builds its own two-domain registry, plays 2000 random keyword requests against its own matcher, runs the report script on a temporary repository of 21 phases, and serves its own `/api/tags` on 127.0.0.1 for the doctor.

```python
"""Independent probe for Phase 5a. Run from the repository root with .venv/bin/python."""

import hashlib
import json
import os
import random
import string
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from typer.testing import CliRunner

from conductor.cli.main import app
from conductor.contracts import Contract, Escalation
from conductor.domains import demo
from conductor.events import EventLog
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Action, Domain, Registry, Rule
from conductor.routing.route import Routed, route_request
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


class Args(Contract):
    target: str


class Result(Contract):
    ok: bool


ACTION = Action("ping", "Check a host.", "tool", "ping", "read", Args, Result)
VOCAB = [
    "echo",
    "note",
    "write",
    "down",
    "ping",
    "trace",
    "route",
    "me",
    "after",
    "repeat",
    "x",
]
LAB = Domain(
    "lab",
    "Lab checks.",
    (ACTION,),
    (Rule("ping", ("ping",)), Rule("trace", ("trace route",))),
)
REGISTRY = Registry((demo.DOMAIN, LAB))
RULES = [
    (
        domain.name,
        f"{domain.name}.{rule.name}",
        tuple(p.split(" ") for p in rule.phrases),
    )
    for domain in (demo.DOMAIN, LAB)
    for rule in domain.rules
]
rng = random.Random(5)
folder = Path(tempfile.mkdtemp())
RUN = "a" * 32


class NoModel:
    asked = 0

    def model_info(self, name):
        NoModel.asked += 1
        raise AssertionError("asked")

    def chat(self, request):
        NoModel.asked += 1
        raise AssertionError("asked")


def occurs(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return any(tuple(tokens[i : i + n]) == phrase for i in range(len(tokens) - n + 1))


def noisy(tokens: list[str]) -> str:
    out = []
    for token in tokens:
        token = token.upper() if rng.random() < 0.3 else token
        out.append(token + rng.choice([" ", "  ", ", ", "! ", "\n", "-"]))
    return "".join(out)


# 1. prefixes
ok = True
for _ in range(300):
    name = rng.choice(["demo", "lab"])
    shown = "".join(c.upper() if rng.random() < 0.5 else c for c in name)
    rest = "".join(
        rng.choice(string.ascii_letters + " :") for _ in range(rng.randint(1, 30))
    )
    text = rng.choice(["", " ", "\n "]) + shown + ":" + rest
    found = match_rules(text, REGISTRY)
    ok &= isinstance(found, RuleRoute) and found.request == rest.strip()
    ok &= (found.route.domain, found.route.rule_id) == (name, f"{name}.prefix")
check("a registered prefix routes to its domain and is stripped (300 requests)", ok)

# 2. keyword rules against an independent matcher
ok = True
counts = {"route": 0, "conflict": 0, "none": 0}
for _ in range(2000):
    tokens = [rng.choice(VOCAB) for _ in range(rng.randint(1, 8))]
    matched = [
        rule_id
        for _, rule_id, phrases in RULES
        if any(occurs(tokens, p) for p in phrases)
    ]
    domains_hit = {rule_id.split(".")[0] for rule_id in matched}
    found = match_rules(noisy(tokens), REGISTRY)
    if not matched:
        ok &= found is None
        counts["none"] += 1
    elif len(domains_hit) == 1:
        ok &= isinstance(found, RuleRoute) and found.route.rule_id == matched[0]
        counts["route"] += 1
    else:
        ok &= found == RuleConflict(tuple(matched))
        counts["conflict"] += 1
check(f"keyword rules agree with an independent matcher (2000 requests, {counts})", ok)

# 3. no model for rule routes and conflicts
ok = True
NoModel.asked = 0
for _ in range(300):
    tokens = [rng.choice(VOCAB[:-1]) for _ in range(rng.randint(1, 6))]
    text = noisy(tokens)
    if match_rules(text, REGISTRY) is None:
        continue
    found = route_request(
        text,
        REGISTRY,
        model=NoModel(),
        model_name="m",
        log=EventLog(folder),
        run_id=RUN,
    )
    ok &= isinstance(found, Routed | Escalation)
    if isinstance(found, Escalation):
        ok &= found.kind == "unknown_route" and all(
            p.code == "matched" for p in found.problems
        )
check("a rule route or a rule conflict never asks the model", ok and NoModel.asked == 0)

# 4. the classifier: only registered domains route
ok = True
for i in range(200):
    answer = rng.choice(["demo", "lab", "unknown", "travel", "Demo", ""])
    model = ScriptedModel(
        [ScriptedReply("route", ModelReply(content=json.dumps({"domain": answer})))]
    )
    found = route_request(
        f"Is the printer {i} up?",
        REGISTRY,
        model=model,
        model_name="m",
        log=EventLog(folder),
        run_id=f"{i + 1:032x}",
    )
    if answer in ("demo", "lab"):
        ok &= isinstance(found, Routed) and found.route.domain == answer
        ok &= found.route.decided_by == "model" and found.decision_id is not None
    elif answer == "unknown":
        ok &= isinstance(found, Escalation) and found.kind == "unknown_route"
    else:
        ok &= isinstance(found, Escalation) and found.kind == "invalid_model_output"
    ok &= model.remaining == 0
    schema = model.requests[0].schema
    ok &= schema["properties"]["domain"]["enum"] == ["demo", "lab", "unknown"]
check("the classifier routes only to registered domains; anything else escalates", ok)

# 5. no domains
NoModel.asked = 0
found = route_request(
    "demo: echo",
    Registry(()),
    model=NoModel(),
    model_name="m",
    log=EventLog(folder),
    run_id=RUN,
)
check(
    "with no domains every request escalates without the model",
    isinstance(found, Escalation)
    and found.kind == "unknown_route"
    and NoModel.asked == 0,
)

# 6. check_reports --phase
ok = True
root = Path(tempfile.mkdtemp())
(root / "docs" / "phases").mkdir(parents=True)
entries = []
for number in range(1, 7):
    for letter in ("", "a", "b"):
        phase = f"{number}{letter}"
        (root / "docs" / "phases" / f"phase-{number:02d}{letter}-x.md").write_text(
            "# x\n"
        )
        if rng.random() < 0.5:
            entries.append(phase)
text = "# Progress\n\n" + "".join(
    f"## Phase {p}: x (2026-11-09)\n- Tests: 1 -> 2 (given 1)\n- New public names: None\n"
    "- Changed files: 1\n- Deviations:\n  - None\n- Follow-ups:\n  - None\n\n"
    for p in entries
)
(root / "docs" / "progress.md").write_text(text)
script = Path("scripts/check_reports.py").resolve()
for number in range(1, 8):
    for letter in ("", "a", "b"):
        phase = f"{number}{letter}"
        done = subprocess.run(
            [sys.executable, str(script), "--root", str(root), "--phase", phase],
            capture_output=True,
            text=True,
            check=False,
        )
        expected = []
        if number == 7:
            expected.append(f"docs/phases:1: no spec for Phase {phase}")
        if phase not in entries:
            expected.append(f"docs/progress.md:1: no progress entry for Phase {phase}")
        if expected:
            tail = "1 problem." if len(expected) == 1 else f"{len(expected)} problems."
            ok &= (done.stdout, done.returncode) == (
                "\n".join([*expected, tail]) + "\n",
                1,
            )
        else:
            ok &= (done.stdout, done.returncode) == ("Reports OK.\n", 0)
check("check_reports --phase names a missing spec and a missing entry (21 phases)", ok)

# 7. the doctor's digest
listing: dict[str, object] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(listing).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = str(folder / "data")
os.environ["CONDUCTOR_OLLAMA_HOST"] = f"http://127.0.0.1:{server.server_address[1]}"
os.environ["CONDUCTOR_MODEL"] = "probe-model:7b"
ok = True
for i in range(20):
    digest = hashlib.sha256(str(i).encode()).hexdigest()
    shown = rng.choice([digest, digest.upper(), digest[:63], None])
    entry = {"name": "probe-model:7b"} | ({} if shown is None else {"digest": shown})
    listing = {"models": [entry]}
    result = CliRunner().invoke(app, ["doctor"])
    line = [x for x in result.stdout.splitlines() if " model " in x][0]
    if shown == digest:
        ok &= line == f"ok    model probe-model:7b: digest {digest[:12]}"
    else:
        ok &= line == "FAIL  model probe-model:7b: listed without a valid digest"
        ok &= result.exit_code == 1
server.shutdown()
check("the doctor shows a valid digest's first 12 characters and fails without one", ok)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The four new test files cover each bullet of the spec's "Tests to write" with its deciding input; name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named function, run the deciding test, see it fail, restore. **Run them with `PYTHONDONTWRITEBYTECODE=1`, restore with the reverse edit (not by copying a saved file back), and afterwards run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate.** In Phase 4c, a spot check that only reordered lines kept the file's size, the restore kept its time, and Python went on running the broken bytecode on `main`.

| # | Change (function) | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | phrases matched as substrings of the text (`match_rules`) | `test_phrases_match_whole_words_in_order`, `echoes of the past` | `None` | `demo.echo` |
| 2 | phrase words matched in any order, or not adjacent | the same, `write it down` | `None` | `demo.note` |
| 3 | the prefix name compared without lowercasing | `test_a_prefix_routes_and_is_stripped`, `LAB:` | `lab.prefix` | no prefix route |
| 4 | keyword rules checked before the prefix | `test_a_prefix_wins_over_keyword_rules` | `lab.prefix` | `demo.echo` |
| 5 | the first matching rule across all domains wins (no conflict check) | `test_rules_of_two_domains_conflict` | `RuleConflict` | `demo.echo` |
| 6 | the classifier asked when no domain is registered (`route_request`) | `test_no_domains_escalate_without_asking` | the escalation | `AssertionError("the model was asked")` |
| 7 | `unknown` returned as a route (`route_request`) | `test_unknown_escalates` | `unknown_route` | `Routed` with domain `unknown` |
| 8 | the output's enum built from a fixed list, not the registry (`route_output`) | `test_the_route_point_and_its_prompt` | the pinned schema | another |
| 9 | the entry checked only for phases that have a review (`check_reports`) | `test_a_phase_needs_its_spec_and_its_entry`, `(True, False)` | the entry problem | `[]` |
| 10 | a digest shown without checking its form (`check_ollama`) | `test_a_model_listed_without_a_valid_digest`, `sha256:` | `FAIL` | `ok ... digest sha256:aaaa` |

Reasonable variations that are correct: `match_rules` built from private helpers for the prefix and the keywords; the phrase test as a slice comparison over `words`; `route_output` cached per tuple of names; `fetch_model_names` written as `sorted(fetch_models(...))`; the script's `ValueError` caught around `check_reports` only.

## 6. Project rules

- Searches 1 to 4.
- `route_request` calls `decide` at most once and never catches anything but `InvalidModelOutput` and `ModelUnavailable`.
- Every escalation's `detail` is one of the Design's texts plus a domain name or a decision id; no request text appears in any message, problem, or escalation.
- No real data: tests and the probe build their own registries, repositories, and listings.

## 7. Out of scope

Each must be absent: planning, LangGraph or any new dependency, a node or graph, new event or escalation kinds, contract changes, regular-expression rules, settings read in `conductor.routing`, `conductor ask`, a domain added to `DOMAINS`, other changes to the report checker or the doctor.

## 8. Progress log

The entry exists, headed `## Phase 5a: routing (...)`, with `Tests: 423 -> <passed> (given 37)`, and each deviation it lists is real and justified.
