# Verify Phase 9c: the finance proposals

Spec: `docs/phases/phase-09c-finance-proposals.md`. Follow `docs/phase-conventions.md` ("For the verifier") for the procedure and the verdict, including running `scripts/check_reports.py --phase 9c` on your own report.

**First, check that the coder ran.** If `git status --short` lists neither `tests/unit/test_finance_proposals_more.py` nor a changed `src/conductor/domains/finance.py`, stop. Report under "For the architect" that there is no implementation to verify, and write no review file, because a FAIL review without a progress entry breaks `check_reports.py` on `main`.

The coder:
- copied the given head, `_propose`, and tail into `finance.py`, wrote the 11 contracts of the spec's table, and renamed the read tuple `READS`;
- replaced the saved schemas and the fake server, and changed four given lines in two 9b test files;
- copied two given test files (50 tests), and wrote `tests/unit/test_finance_proposals_more.py` and `tests/integration/test_finance_proposals_more.py`.

## 1. Gates

N is `908`. Sections: cli, core.

| Command | Expected |
|---|---|
| `.venv/bin/python scripts/check.py --first cli,core` | last line `All checks passed.`; the summary lists `tests (cli,core): passed`; at least 958 passed, 0 failed, 0 skipped, 0 xfailed, no warnings summary; 0 failed on every line of the `Sections:` table |
| `.venv/bin/python -m coverage report --include="*/conductor/domains/finance.py" --fail-under=100` (right after the check) | exit 0, `TOTAL` at `100%` |
| `.venv/bin/python -m pytest tests/unit/test_finance_proposals.py tests/integration/test_finance_proposal_steps.py --no-cov` | exactly `50 passed` |
| `grep -c "^## Phase 9c: " docs/progress.md` | `1` |
| `.venv/bin/python scripts/check_reports.py --phase 9c` (before writing your report) | `Reports OK.` |
| `git diff --stat HEAD -- src/conductor/mcp_client src/conductor/runtime.py src/conductor/graph src/conductor/store.py src/conductor/policy.py src/conductor/decisions.py src/conductor/web src/conductor/evals src/conductor/prompts src/conductor/llm src/conductor/planning src/conductor/routing src/conductor/domains/__init__.py src/conductor/domains/demo.py src/conductor/config.py src/conductor/diagnostics.py tests/support.py tests/conftest.py tests/mcp_fake_server.py tests/integration` | no output |
| `git diff --stat HEAD -- tests` | exactly the four files `tests/fake_finances_server.py`, `tests/finances_tools.json`, `tests/unit/test_finance_domain.py`, `tests/unit/test_finance_more.py` |
| `git diff -U0 HEAD -- tests/unit/test_finance_domain.py tests/unit/test_finance_more.py \| grep -E "^[-+][^-+]"` | exactly the four removed and four added lines of the spec's table |

Searches, each with no output:

1. `git grep --untracked -n -E "\"(write|implement)\"" -- src/conductor/domains/finance.py`
2. `git grep --untracked -n -E "Projects/finances|finances/(data|\.venv)|bin/fin([^a-z_]|$)" -- tests src`

## 2. Scope paths and the given parts

`git status --short` lists only the paths of the spec's Scope table. The given files equal the spec's blocks: `tests/finances_tools.json`, the fake server, and the two given test files.

The given parts of `finance.py` are in the file exactly. Save each of the spec's three blocks (the head, `_propose`, and the tail) to a file outside the repository, then run, for each:

`.venv/bin/python -c "import sys, pathlib; print(pathlib.Path(sys.argv[1]).read_text() in pathlib.Path('src/conductor/domains/finance.py').read_text())" <saved block>`

Each prints `True`. Then check that `READS` equals the 9b tuple: `git show HEAD:src/conductor/domains/finance.py` holds the same 20 `_read(...)` entries, word for word, under the name `ACTIONS`.

## 3. Requirement checklist

| Id | How | Pass when |
|---|---|---|
| R1 | the given-part checks; `test_eleven_proposal_actions_after_the_reads`; `test_twenty_read_actions_on_one_server`; `test_every_action_fits_the_real_read_tools`; probe check 0 | `True`; pass; ok |
| R2 | `test_the_required_fields_and_the_defaults` (11 cases), `test_arguments_at_their_bounds_are_sent` (8), `test_arguments_past_their_bounds_are_refused` (17); read each contract against the spec's table, field order included; the coder's unit tests; probe check 1 | pass; equal; ok |
| R3 | `test_the_fake_server_returns_a_result_each_proposal_accepts`; probe check 2 | pass; ok |
| R4 | search 1; `test_eleven_proposal_actions_after_the_reads`; probe checks 0 and 5 | no output; pass; ok |
| R5 | the given-file comparison; the `git diff -U0` gate; `test_the_fake_lists_the_real_read_tools`; probe check 4 | equal; as in the Gates; pass; ok |
| R6 | the four tests of `tests/integration/test_finance_proposal_steps.py` (6 cases); the coder's integration tests; probe check 5 | pass; ok |
| R7 | the protected diffs and `git status` | as in the Gates |
| R8 | search 2; read the coder's two test files for any path into `finances` or a run of `fin` | no output; none |
| R9 | the coverage gate | as in the Gates |

The rule `finance.proposals` is checked by `test_proposal_words_route_by_rule` (5 cases), `test_a_proposal_word_and_a_demo_word_conflict`, and probe check 3.

## 4. Probe

Save the probe outside the repository, run it from the repository root with `.venv/bin/python <path>`, then delete it. It takes about 30 seconds. Every line must start with `ok`, and the last must be `FAILURES 0`.

It checks:
- 0: the 11 actions after the 20 reads are the proposal tools, in order, each with effect `propose`.
- 1: 3000 random argument sets: a valid set with at most one field changed, dropped, or added. Each is compared with the probe's own table of every field's kind and bound, including whitespace at either end and line breaks.
- 2: 1000 random results: the top field dropped, a list, a string, an extra top field, a `NaN` inside, or new nested fields.
- 3: 2000 random requests of proposal words, near misses (`proposed`, `categorized`, `pro-pose`), and demo words, compared with its own phrase matcher.
- 4: the tool check against the fake server: 31 tools, 31 actions, no problem.
- 5: 40 random runs through the runtime and the fake, with random plans of reads and proposals and random decisions (approve, edit, reject). Every run must make exactly the tool calls the decisions allow, with the decided arguments, and ask its first approval before its first call.

A stop at its `assert` lines is the probe's fault. Report it under "For the architect", not as a finding.

```python
"""Independent probe for Phase 9c. Run from the repository root with .venv/bin/python."""

import json
import os
import random
import re
import shlex
import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from conductor import domains
from conductor.config import get_settings
from conductor.decisions import decide_approval
from conductor.domains import demo, finance
from conductor.events import EventKind
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.mcp_client.check import check_servers
from conductor.registry import Registry
from conductor.routing.rules import RuleConflict, RuleRoute, match_rules
from conductor.runtime import ask, open_runtime, resume

failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("ok   " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


rng = random.Random(93)
for key in list(os.environ):
    if key.startswith("CONDUCTOR_"):
        del os.environ[key]
os.environ["CONDUCTOR_DATA_DIR"] = tempfile.mkdtemp()
REAL = json.loads(Path("tests/finances_tools.json").read_text())
PROPOSALS = {action.name: action for action in finance.DOMAIN.actions[20:]}

# The oracle's own table: field -> (kind, required, bound).
ID, REASON, NAME, OPTNAME, BOOL, PRIO, OPTPRIO, MATCH, OPTMATCH = (
    "id", "reason", "name", "name|null", "bool", "prio", "prio|null", "match", "match|null"
)
LABEL, MONTH, FINDING, STATUS, KIND, TEXT = "label", "month", "finding", "status", "kind", "text"
TABLE = {
    "propose_category": {"transaction_id": ID, "category": NAME, "reason": REASON},
    "propose_transfer": {"out_id": ID, "in_id": ID, "reason": REASON},
    "propose_not_transfer": {"out_id": ID, "in_id": ID, "reason": REASON},
    "propose_rule": {"example_id": ID, "pattern": NAME, "category": NAME, "reason": REASON,
                     "match": MATCH, "priority": PRIO},
    "propose_merchant_alias": {"example_id": ID, "target": NAME, "reason": REASON},
    "propose_group": {"name": NAME, "example_id": ID, "reason": REASON, "kind": KIND,
                      "sensitive": BOOL},
    "propose_new_category": {"name": NAME, "group": NAME, "example_id": ID, "reason": REASON,
                             "tax": BOOL},
    "propose_rule_change": {"rule_id": ID, "reason": REASON, "delete": BOOL,
                            "pattern": OPTNAME, "match": OPTMATCH, "priority": OPTPRIO,
                            "category": OPTNAME},
    "propose_category_change": {"name": NAME, "reason": REASON, "rename_to": OPTNAME,
                                "delete": BOOL, "move_to": OPTNAME},
    "propose_finding_status": {"type": FINDING, "status": STATUS, "reason": REASON,
                               "about": LABEL, "month": MONTH},
    "log_advice": {"text": TEXT, "subject": LABEL},
}
REQUIRED = {ID, REASON, NAME, FINDING, STATUS, TEXT}
FINDINGS = {"spike", "frequent_small", "subscription_overlap", "price_increase", "interest",
            "fees", "over_budget", "duplicate", "large_first_charge"}
SPACE = " \t\n\r"


def trimmed(value: str, high: int, lines: bool) -> bool:
    if not 1 <= len(value) <= high or value[0] in SPACE or value[-1] in SPACE:
        return False
    return lines or not ("\n" in value or "\r" in value)


def field_ok(kind: str, value: object) -> bool:
    if kind.endswith("|null") and value is None:
        return True
    kind = kind.removesuffix("|null")
    if kind == ID:
        return type(value) is int and value >= 1
    if kind == PRIO:
        return type(value) is int and -1000 <= value <= 1000
    if kind == BOOL:
        return type(value) is bool
    if not isinstance(value, str):
        return False
    if kind == REASON:
        return trimmed(value, 200, lines=False)
    if kind == NAME:
        return trimmed(value, 100, lines=False)
    if kind == TEXT:
        return trimmed(value, 1000, lines=True)
    if kind == LABEL:
        return len(value) <= 100
    if kind == MONTH:
        found = re.fullmatch(r"([0-9]{4})-([0-9]{2})", value)
        return value == "" or (found is not None and 1 <= int(found.group(2)) <= 12)
    choices = {MATCH: {"contains", "starts_with", "equals"}, FINDING: FINDINGS,
               STATUS: {"handled", "ignored"}, KIND: {"spending", "transfer", "income"}}
    return value in choices[kind]


def random_text() -> str:
    body = "".join(rng.choice("ab é𝄞" + SPACE) for _ in range(rng.choice([0, 1, 3, 30])))
    head = rng.choice(["", " ", "\t", "x"])
    tail = rng.choice(["", " ", "\n", "y"])
    return (head + body + tail) * rng.choice([1, 1, 1, 7, 40])


def random_value(kind: str) -> object:
    base = kind.removesuffix("|null")
    pool: list[object] = [None, True, "7", 2.0, random_text()]
    if base in (ID, PRIO):
        low, high = (1, 10**6) if base == ID else (-1000, 1000)
        pool += [low - 1, low, high, high + 1, rng.randint(low, high)]
    elif base == MONTH:
        pool += ["", "2026-10", "2026-13", "2026-1", "202610"]
    elif base in (MATCH, FINDING, STATUS, KIND):
        pool += ["contains", "regex", "spike", "handled", "open", "income", "fees", ""]
    elif base == BOOL:
        pool += [False, 0]
    else:
        pool += ["x" * 100, "x" * 101, "x" * 200, "x" * 201, "a\nb" * 300, "Groceries"]
    return rng.choice(pool)


def valid_value(kind: str) -> object:
    return {ID: 5, REASON: "ok", NAME: "Food", OPTNAME: None, BOOL: True, PRIO: -3,
            OPTPRIO: 9, MATCH: "equals", OPTMATCH: None, LABEL: "", MONTH: "2026-02",
            FINDING: "fees", STATUS: "ignored", KIND: "income", TEXT: "ok"}[kind]


# the oracle on known cases
assert all(field_ok(kind, valid_value(kind)) for kind in (
    ID, REASON, NAME, OPTNAME, BOOL, PRIO, OPTPRIO, MATCH, OPTMATCH, LABEL, MONTH, FINDING,
    STATUS, KIND, TEXT))
assert set(TABLE) == {n for n, item in REAL.items() if not item["read_only"]}
for name, fields in TABLE.items():
    required = sorted(f for f, kind in fields.items() if kind in REQUIRED)
    assert required == sorted(REAL[name]["input_schema"]["required"]), name
    assert set(fields) == set(REAL[name]["input_schema"]["properties"]), name
assert field_ok(REASON, "x" * 200) and not field_ok(REASON, "x" * 201)
assert not field_ok(REASON, " x") and not field_ok(REASON, "a\nb") and field_ok(TEXT, "a\nb")
assert field_ok(OPTPRIO, None) and not field_ok(PRIO, None) and not field_ok(ID, True)
assert field_ok(MONTH, "") and not field_ok(MONTH, "2026-13") and field_ok(LABEL, "")

# 0. the actions
check("the 11 actions after the 20 reads are the proposal tools, each with effect propose",
      [(a.name, a.effect, a.target, a.server) for a in finance.DOMAIN.actions[20:]]
      == [(name, "propose", name, "finances") for name in TABLE]
      and all(a.effect == "read" for a in finance.DOMAIN.actions[:20]))

# 1. arguments: a valid set, then at most one field changed, dropped, or added
agree = True
for _ in range(3000):
    name = rng.choice(sorted(TABLE))
    fields = TABLE[name]
    sent = {f: valid_value(k) for f, k in fields.items() if k in REQUIRED or rng.random() < 0.5}
    change = rng.choice(["value", "value", "value", "drop", "extra", "none"])
    if change == "value":
        field = rng.choice(list(fields))
        sent[field] = random_value(fields[field])
    elif change == "drop":
        sent.pop(rng.choice(list(sent)))
    elif change == "extra":
        sent["amount_cents"] = 1
    want = set(sent) <= set(fields) and all(
        field in sent for field, kind in fields.items() if kind in REQUIRED
    ) and all(field_ok(fields[field], value) for field, value in sent.items() if field in fields)
    try:
        PROPOSALS[name].args.from_json(json.dumps(sent))
        got = True
    except ValidationError:
        got = False
    agree &= got == want
check("3000 random proposal argument sets are accepted exactly when every field fits", agree)

# 2. results
TOP = {name: "advice" if name == "log_advice" else "proposal" for name in TABLE}
agree = True
for _ in range(1000):
    name = rng.choice(sorted(TOP))
    body: dict = {TOP[name]: {"id": 7, "kind": "rule", "rule": {"deep": [1, None, "x"]}}}
    change = rng.choice(["none", "drop", "extra", "list", "nan", "text", "nested"])
    want = change in ("none", "nested")
    if change == "drop":
        body = {}
    elif change == "extra":
        body["new_top_field"] = 1
    elif change == "list":
        body[TOP[name]] = [body[TOP[name]]]
    elif change == "nan":
        body[TOP[name]]["amount"] = float("nan")
    elif change == "text":
        body[TOP[name]] = "proposal 7"
    else:
        body[TOP[name]]["new"] = {"deeper": [{"x": True}]}
    try:
        PROPOSALS[name].result.from_json(json.dumps(body))
        got = True
    except ValidationError:
        got = False
    agree &= got == want
check("1000 random proposal results are accepted exactly when the top field is an object", agree)

# 3. rules, against the oracle's own phrase list
FIN = {"spending": ["spending", "spent"], "budgets": ["budget", "budgets"],
       "balances": ["balance", "balances", "net worth"],
       "transactions": ["transactions", "uncategorized"],
       "bills": ["bills", "subscriptions", "recurring"], "transfers": ["transfers"],
       "proposals": ["propose", "proposal", "proposals", "categorize", "recategorize"]}
DEMO = {"echo": ["echo", "repeat after me"], "note": ["note", "write down"]}
FILLER = ["proposed", "categorized", "categories", "transaction", "Propose!", "RECATEGORIZE,",
          "pro-pose", "the", "for", "101", "note", "write", "down", "spent", "category"]


def oracle_route(text: str) -> object:
    tokens = re.findall(r"[a-z0-9]+", text.lower())

    def has(phrase: str) -> bool:
        want = phrase.split(" ")
        return any(tokens[i : i + len(want)] == want for i in range(len(tokens)))

    matched = [f"finance.{n}" for n, ps in FIN.items() if any(has(p) for p in ps)]
    matched += [f"demo.{n}" for n, ps in DEMO.items() if any(has(p) for p in ps)]
    if not matched:
        return None
    if len({m.split(".")[0] for m in matched}) > 1:
        return ("conflict", tuple(matched))
    return ("route", matched[0])


assert oracle_route("Propose Groceries") == ("route", "finance.proposals")
assert oracle_route("categorize the uncategorized") == ("route", "finance.transactions")
assert oracle_route("propose a note") == ("conflict", ("finance.proposals", "demo.note"))
assert oracle_route("proposed categories") is None
registry = Registry((finance.DOMAIN, demo.DOMAIN))
agree = True
for _ in range(2000):
    words = rng.choices(FILLER + FIN["proposals"] + ["uncategorized", "budget"],
                        k=rng.randint(1, 7))
    text = " ".join(words)
    found = match_rules(text, registry)
    want = oracle_route(text)
    if want is None:
        agree &= found is None
    elif want[0] == "conflict":
        agree &= found == RuleConflict(want[1])
    else:
        agree &= isinstance(found, RuleRoute) and found.route.rule_id == want[1]
check("2000 random requests route as the phrase list says", agree)

# 4. the tool check against the fake server
fake = Path("tests/fake_finances_server.py").resolve()
os.environ["CONDUCTOR_MCP__FINANCES"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(fake))}"
os.environ["CONDUCTOR_MCP_TIMEOUT"] = "10"
found = check_servers(Registry(domains.registered(get_settings())), get_settings())
check("the tool check finds 31 tools, 31 actions, no problems on the fake",
      [(item.server, item.tools, item.actions, item.problems) for item in found]
      == [("finances", 31, 31, ())])

# 5. random runs: every call happens exactly as the decisions allow
MENU = [
    ("list_uncategorized", {"limit": 3}),
    ("get_balances", {}),
    ("propose_category", {"transaction_id": 101, "category": "Groceries", "reason": "Food"}),
    ("propose_transfer", {"out_id": 205, "in_id": 318, "reason": "Same amount"}),
    ("log_advice", {"text": "Check the bills\nin December.", "subject": "Bills"}),
    ("propose_rule_change", {"rule_id": 1, "reason": "Old rule", "delete": True}),
]
EDITS = {
    "propose_category": {"transaction_id": 102, "category": "Dining", "reason": "A cafe"},
    "propose_transfer": {"out_id": 206, "in_id": 319, "reason": "Edited"},
    "log_advice": {"text": "Edited note."},
    "propose_rule_change": {"rule_id": 2, "reason": "Edited", "pattern": "CAFE"},
}
FULL = {name: action for name, action in ((a.name, a) for a in finance.DOMAIN.actions)}


def full_args(name: str, given: dict) -> dict:
    return FULL[name].args.from_json(json.dumps(given)).model_dump(mode="json")


agree = True
for run in range(40):
    try:
        steps = rng.choices(MENU, k=rng.randint(1, 3))
        if run < 4:
            steps = [MENU[2 + run]]
        has_proposal = any(name in TABLE for name, _ in steps)
        choices = [rng.choice(["approve", "approve", "edit", "reject"]) for _ in range(len(steps) + 1)]
        want_calls, status = [], "done"
        if has_proposal and choices[0] == "reject":
            status = "rejected"
        else:
            for number, (name, given) in enumerate(steps, start=1):
                sent = full_args(name, given)
                if name in TABLE:
                    choice = choices[number]
                    if choice == "reject":
                        status = "rejected"
                        break
                    if choice == "edit":
                        sent = full_args(name, EDITS[name])
                want_calls.append((number, f"finance.{name}", sent))
        plan = json.dumps({"steps": [{"action": n, "args": a} for n, a in steps]})
        replies = [ScriptedReply("plan", ModelReply(content=plan))]
        if status == "done":
            replies.append(ScriptedReply("answer", ModelReply(content='{"reply": "Done."}')))
        with open_runtime(get_settings(), model=ScriptedModel(replies)) as runtime:
            state = ask(runtime, "finance: propose")
            while state.status == "waiting":
                request = runtime.store.approval(state.approval_id).request
                if request.stage == "plan":
                    verdict = "reject" if choices[0] == "reject" else "approve"
                    edited = None
                else:
                    verdict = choices[request.steps[0].number]
                    edited = None
                    if verdict == "edit":
                        edited = EDITS[request.steps[0].action.split(".", 1)[1]]
                decide_approval(runtime.store, runtime.registry, state.approval_id, verdict,
                                channel="terminal", decided_by="probe", edited_args=edited)
                state = resume(runtime, state.run_id)
            calls = [(e.payload["step"], e.payload["action"], e.payload["args"])
                     for e in runtime.log.read(state.run_id) if e.kind == EventKind.TOOL_CALL]
            kinds = [e.kind for e in runtime.log.read(state.run_id)]
        ok = state.status == status and calls == want_calls
        if has_proposal and ok:
            first_call = kinds.index(EventKind.TOOL_CALL) if EventKind.TOOL_CALL in kinds else None
            first_ask = kinds.index(EventKind.APPROVAL_REQUESTED)
            ok = first_call is None or first_ask < first_call
        if not ok:
            print("     run", run, steps, choices, state.status, calls)
        agree &= ok
    except Exception as error:  # noqa: BLE001
        print("     run", run, "raised", type(error).__name__)
        agree = False
check("40 random runs call each step only as the plan and step decisions allow", agree)

print(f"FAILURES {failures}")
```

## 5. The coder's tests and spot checks

The coder's two test files cover each bullet of the spec's "Tests to write" with its deciding input. Name the test for each bullet, and report a missing one as a finding.

Spot checks: make each change in the named line of `finance.py`, run the deciding test, see it fail, and restore. The rows name the given aliases and the table's contracts. If the coder wrote a contract differently but correctly, make the same change in the coder's form. Run them with `PYTHONDONTWRITEBYTECODE=1` and `-vv`. Restore with the reverse edit, not by copying a saved file back. Afterwards, run `find src tests scripts -name __pycache__ -prune -exec rm -rf {} +` before any further gate.

Write down what each broken run printed. A different failure than the "Broken" column is not a finding (note it for the architect), but a test that still passes is.

| # | Change | Deciding test, input | Correct | Broken |
|---|---|---|---|---|
| 1 | `Reason` without its `pattern` | `test_arguments_past_their_bounds_are_refused[reason-two-lines]` | `ValidationError` | `Failed: DID NOT RAISE` |
| 2 | `Id` with `ge=0` | `test_arguments_past_their_bounds_are_refused[id-0]` | `ValidationError` | `Failed: DID NOT RAISE` |
| 3 | `"read"` instead of `"propose"` in `_propose` | `test_eleven_proposal_actions_after_the_reads` | effect `propose` | the sets differ: `('tool', True, 'read', 'finances')` on the left |
| 4 | `"categorize"` removed from the `proposals` rule | `test_proposal_words_route_by_rule[categorize]` | `rule_id='finance.proposals'` | `assert None == RuleRoute(...)` |
| 5 | `ACTIONS = (*PROPOSALS, *READS)` | `test_eleven_proposal_actions_after_the_reads` | the reads first | "At index 0 diff": `propose_category` against `list_accounts` |
| 6 | `priority: int \| None = None` in `RuleChangeProposalArgs` | `test_arguments_past_their_bounds_are_refused[change-priority]` | `ValidationError` | `Failed: DID NOT RAISE` |
| 7 | `NoteArgs.text` without its `pattern` | `test_arguments_past_their_bounds_are_refused[text-blank]` | `ValidationError` | `Failed: DID NOT RAISE` |
| 8 | `match: Match = "equals"` in `RuleProposalArgs` | `test_the_required_fields_and_the_defaults[propose_rule]` | `'match': 'contains'` | "Differing items": `{'match': 'equals'} != {'match': 'contains'}` |

Reasonable variations that are correct: the 11 contracts in another place between the read contracts and `_read`, a named alias for the advice text, and `TransferProposalArgs` shared by both transfer tools (as the given tail requires).

## 6. Project rules

- Searches 1 and 2.
- Every new action has effect `propose`, and every earlier action keeps effect `read`.
- No test starts `fin` or reads from the `finances` project. The fake's results and the coder's tests use invented data only.
- No test opens a connection other than the fake server's stdio; the model in tests is `ScriptedModel`.

## 7. Out of scope

Each must be absent:
- planning after the reads, or arguments that refer to an earlier step's result;
- a change to the policy, the graph, the runtime, the store, the decisions, the web pages, the MCP client, the tool check, the templates, `plan_point`, or `registered`;
- reading a refused tool's text, or a new escalation kind or cause code;
- finance evaluation cases or prompt tuning.

## 8. Progress log

The entry exists, headed `## Phase 9c: the finance proposals (...)`, with `Tests: 908 -> <passed> (given 50)`, and each deviation it lists is real and justified.
