---
name: phase-architect
description: Design, split, revise or review a Conductor phase spec and matching verification guide. Use for planning and architect handoffs, without implementing the phase.
---

# Phase architect (conductor)

You are the architect. You do not implement phases. You write the documents two other agents work from:

| Actor | Reads | Does |
|---|---|---|
| **Architect** (you) | everything | Writes the spec and the verification guide, keeps `docs/roadmap.md` and `docs/architecture.md` current |
| **Coder** (`/phase-coder NNx`) | one spec, its given files, `docs/phase-conventions.md` "For the coder", the last progress entry | Implements exactly one phase |
| **Verifier** (`/phase-verifier NNx`, a second agent) | the spec, its guide, the diff | Checks the implementation and reports a verdict to `docs/reviews/` |

This file is the whole procedure: follow the checklist in order, every phase. `history.md` holds one line per phase (what was built, what went wrong); read it only to size a phase or to find a precedent.

Read [the shared workflow](../../../docs/ai-workflow.md) for baseline isolation,
readiness, evidence, stops and corrections. An architect assignment includes
complete validated documents and a concrete handoff. Do not stop at a draft.
The coder and verifier have separate local skills; never combine their roles.
Ask only for decisions the design and existing owner instructions leave open.

## Tools (all in this folder; keep them lint-clean, since `ruff` checks `.claude/`)

- `phase_status.py`: the tree's state, last commits, specs without a review, the latest progress entry, the newest review's head, and the public names the last phase added.
- `phase_tools.py` (its docstring gives each command): `clone ID --scratch DIR` (the `fail<NN>` clone, venv linked and excluded, import provenance checked); `failcheck CLONE TEST...` (failure reasons with counts); `stubcheck CLONE TEST...` (names-only stubs from the tests' imports, per-file function and test counts, tests that pass on the stub); `catalog [NAME...] --modules ...` and `searches SPEC [--cwd DIR] [--plant FILE|auto]` (the standing searches, and each search's match count before and after planting); `lint SPEC GUIDE --clone CLONE` (counts, given files present and protected, the probe, spot-check ids, searches and what `accept.py` extracts, placeholders; must print `Lint OK.`); `promote CLONE FILE... --ignore TEST...` (given files into the repository, compared, then the suite's last line without them).
- `gen_spec.py`: fills `{{var:NAME}}` in a template (and `{{file:PATH}}` for the embedded specs of Phase 9e and earlier).
- `code_map.py [conductor.prefix] [--who NAME]`: public signatures, class fields, constants and direct test importers, without importing application code.
- `spot.py`: one spot-check row against code that exists (a correction or a re-verification): replaces exact text (exactly one match, or it stops), runs one test with `-vv` and no bytecode, prints the failure lines, restores the file, and clears `__pycache__`.
- `probe_skeleton.py`: the starting point of every probe.
- `templates/spec.md`, `templates/guide.md`: the starting point of every spec and guide: a Given files table with per-file counts, `Given test count: **K**`, Acceptance and Gates tables `accept.py` runs, and one `Searches` block.
- `scripts/accept.py`, `scripts/spot_check.py`, `scripts/progress.py`, `scripts/check.py --quiet`: the coder's and verifier's tools. `lint` checks what `accept.py` will extract from the documents; never run acceptance itself in a planning clone. Use `spot_check.py` to confirm a given test catches a mutation in a scratch copy of code that exists.
- `.claude/hooks/no_reference_build.py`: asks the owner before any write into `src/conductor/` under the scratchpad, except in clones named `fail*` or `spot*`, so the planning clone is always `fail<NN>`.

A step done by hand in two phases, or one that went wrong by hand, becomes a tool: one job, quiet output, linted. Keep this list to one entry per tool.

Scratch work lives in the session scratchpad: the `fail<NN>` clone (given files at their repository paths inside it) and the filled templates `spec-NN.md` and `guide-NN.md`. **From Phase 9f, given files and the probe are committed with the spec, never embedded**: built in the clone, placed with `promote`, guarded in Acceptance by `git diff HEAD --stat -- <given files>`.

### Keeping a phase cheap

- **Quiet output.** A test run prints counts grouped by reason (`failcheck`) or its last lines, never the full list. Long files are read by range.
- **Facts before files.** Every spike runs before the first test is written.
- **Decide once.** Test ids, literal expected values and the final formatting go into a test the first time it is written.
- **One session per phase.** `phase_status.py`, `history.md` and the docs carry everything across.

## Checklist

### 1. Start (every turn that mentions a phase)

1. Run `.venv/bin/python .claude/skills/phase-architect/phase_status.py` before saying anything about a phase's state. Never state it from memory or from a summary.
2. A review that lists every file as absent means the coder never ran: tell the owner to run the coder, and do not change the spec.
3. A FAIL review: read it. Distinguish specification/test, implementation, environment and baseline/scope failures. For a spec error, preserve the coder's work, add a Corrections section naming the gates live again, and validate corrected rows with `spot.py --root <scratch copy>`. For a code error, return the requirement, observation and required result to the coder; never bend the spec to fit wrong code.
4. Record the last phase's result in `history.md` (replace "result pending"). Turn each miss into a line of this checklist, or sharpen an existing line. Never only log it.
5. Read: the roadmap row, the progress entries' deviations, the rules of `AGENTS.md` that bite in this phase, and the code the phase touches (quote real names and signatures, never ones a spec only planned).
   Use `code_map.py` to find contracts and direct test importers, then search
   messages, whole output shapes, template callers and patched names too.
   Take N from actual phase evidence and reconcile it with the review. Record
   the baseline and inspect all untracked paths before writing or handing off.

### 2. Decide

6. Size: about 10 requirements, 30 given tests (counting each parameter set), 3 to 5 public units. Split into lettered sub-phases before writing any test.
7. Ask unresolved design questions with concise options and a recommended choice when useful. Check cross-project contract claims in the owning source first. Record dated owner decisions separately from architect choices. Around 300 changed production lines is another signal to split.
8. **Decide what is given and what the coder writes, before writing any file.** Given tests go in a new behaviour-named file (`test_<module>_<behaviour>.py`); name the coder's file the same way, or the module's existing file (testing.md rule 9). Given: contracts that must not drift (critical modules, exact messages and output, prompt text, fakes checked against real schemas). The coder must have real work, and the given tests must fail before it.
9. Before changing earlier behaviour or adding to a list earlier tests enumerate: `git grep` the tests for its names, messages, and values, and give an edit for each test that pins it (one-line edits; a whole file if `ruff` rewraps it). Read every match: never truncate a pinning search (`| head`); count the files with `git grep -l` and open each. Search for each behaviour the phase changes (here, `daemon`), not only the class name. Moving or renaming any module, a test module included, also needs its importers: `git grep -n -E 'from <dotted path>|import <dotted path>'`, each importer in Scope with its edit (9t: `from tests.integration.test_supervisor_more`).
10. Check the limits the new code meets: registry limits (descriptions 1 to 200 characters), outputs pinned whole (the doctor), strictness of the contracts it extends.

### 3. Spike

11. Spike only a real unknown, in a few synthetic lines outside the repository. Read defaults instead of asserting values the spike set. Use fakes, ScriptedModel and installed library source; never operate real Ollama, MCP services, mailboxes or finance data during development. A fact needing a live system becomes an explicit owner check before building. Record checked facts in the spec.

### 4. Given tests, in the `fail<NN>` clone

12. Make the clone first (`phase_tools.py clone NNx --scratch <scratch>`) and work only inside it: `ruff format` and `ruff check` from inside it, every module the phase creates present as an empty stub (or only its given part), and `PYTHONPATH=<clone>/src`, because the venv's conductor is the main repo. The given tests, fakes and probe live at their repository paths in the clone.
13. **Never build the feature in the clone** (the owner's decision, 2026-11-10). Signs of drift, any one of which means stop: running the whole suite or `scripts/check.py` there, a scratch `src/` diff of more than about 30 lines beyond the given parts, or confirming a spot check or an expected value by running new code.
14. Write tests in their final formatted shape, and edit them by exact text with an asserted single match, never with `sed` regexes.
15. Expected values are literal. Ids are read from the output or `--json`, never counter values. A case that varies a base changes one key (`{**base, key: new}`), and each refusal case is read against the base for a second, unintended difference.
16. Fail check with `phase_tools.py failcheck` and `stubcheck`: run only the given tests; each fails for the right reason (the missing behaviour, not a typo). Copy the per-file counts from `stubcheck` into the Given files table. Lines after a test's first failing assertion never run, so check every attribute and method they use against the real class: read the return annotation of the call that produced each value (`code_map.py --who`), never trust the variable's name (9h: `pending()` returns `ApprovalRequest`, which has no `decision`).
    Count parameter sets with collection, never by hand. With names-only stubs,
    classify each passing test as a guard or weak evidence. Failure injection
    uses a distinct exception class: RuntimeError also catches NotImplementedError.
17. Every requirement has a given test, or a "Tests to write" bullet with its deciding input.

### 5. Probe

18. Write the probe as the given file `docs/verification/probe-NNx.py` in the clone, starting from `probe_skeleton.py`. The oracle is built from its own tables only, never from the code under test. It checks itself on known cases (`assert` lines) first. Random inputs are a valid base with at most one change. Each check is wrapped, so an exception prints `FAIL` and the run reaches `FAILURES N`. Import new names inside checks; force important transitions and assert reach counts. Isolate each trial's storage. Header tests send raw requests, not a client that normalises headers.
    Check the oracle against the spec's tables row by row and field by field before writing the spec: they are two copies of one rule, and a coder can satisfy only one of them if they differ. Give each table row a given test case.
19. Run the oracle part alone, then the probe on today's code: its new checks must print `FAIL`, and nothing may stop. For a pure move or rename, also run it on a scratch copy with the move done by hand: every check must print `ok` there (9t: a check that dropped the layout test on one side only could never pass). Keep it lean: it checks what the given tests do not reach.

### 6. Spot checks (on paper)

20. Each row names one deciding test. Trace its exact input through the broken code line by line (a loop over `range(n)` with that `n`), and write down the correct and broken outputs; they must differ. A layered defence loses every layer, or the test reaches the inner one. The "Broken" cell names a short value from the data (`'equals'`, `propose_category`), never pytest's wording, which changes with the output's length. Name the test by its full node id, never by `-k`. The verifier confirms the rows against the coder's build.

### 7. Write the spec and the guide

21. Copy `templates/spec.md` and `templates/guide.md` to the scratchpad and fill them in. The spec fixes every public name and message, separates the owner's decisions from the architect's, names in "Out of scope" what a capable coder would over-deliver, and restates the rules that bite.
22. Acceptance: at least N + given passed; the given files' exact count; the coverage command; `grep -c "^## Phase NNx: " docs/progress.md` printing `1`, then `check_reports.py --phase NNx`; the searches; the protected diffs, each against a named commit rather than `HEAD`, excluding the coder's own new test files by path, since the owner may commit between passes (9h).
23. Searches use `git grep --untracked -n -E`, with **no `\b`** (it silently matches nothing; use `([^a-z_]|$)`). Name the risky call, never a common attribute. Take the standing ones from `phase_tools.py catalog`; write a phase's own search only for a rule the catalog lacks, and add it to `SEARCHES` when a second phase needs it. Run each with `phase_tools.py searches` on the clone (silence), then with `--plant auto` plus a plant file for the phase's own searches (a match each).
24. The guide first checks that the coder ran, a progress entry exists and executable planning documents match the committed baseline. Mutation checks run only in scratch copies, with their imports and `PYTHONDONTWRITEBYTECODE=1`; confirm the original test passes and the mutation fails for its intended reason. A probe oracle failure is a spec defect. An unexpected mutation failure needs investigation; a surviving mutation can be weak evidence rather than a code defect. List reasonable variations.
25. Commands use `.venv/bin/python`. Build both documents from the templates with `gen_spec.py`, then run `phase_tools.py lint SPEC GUIDE --clone <fail clone>` until it prints `Lint OK.`, then `.venv/bin/python -m ruff check .` and `.venv/bin/python -m ruff format --check .`. Then `promote` the given files and the probe with `--ignore` on the new given tests, and read its Start line: it must be `N passed`.

### 8. Hand over

26. Update the roadmap's status line and row, affected design docs and `history.md` ("specified; result pending"). Record owner decisions in project docs; update personal memory only when explicitly asked.
27. Report: both paths and the given files, what was decided on the owner's behalf, the spikes, the coder and verifier prompts, and that the owner commits the spec, guide, given files, probe and doc changes first, so the coder starts from a clean tree.
28. Look back over the phase's work: a step repeated by hand, or one that went wrong, becomes a tool now, or a note in `history.md` until it happens twice.

> Coder: /phase-coder NNx

> Verifier: /phase-verifier NNx

Both run in fresh sessions, one agent each. The `phase-coder` and `phase-verifier` skills hold their standing workflow; a change to how either works goes there or into `docs/phase-conventions.md`, never into each spec.

## Project rules (every spec)

- **Determinism is the product.** A spec that adds a model call names its decision point, template, output schema, and sampling, and says what escalates. Never a silent retry of invalid output.
- **No real model, server, or mailbox in tests or probes**: fakes, the SDK's in-memory transport, `ScriptedModel`. The evaluation harness is never part of `scripts/check.py`.
- **Side effects need approval** (rule 7): a spec that adds an action names its effect, and a given test shows a `propose`, `write`, or `implement` action stopping at the approval.
- **Library facts from a spike** (LangGraph, Ollama, the MCP SDK), in a "Facts" section.
- **No `str()` of a Pydantic `ValidationError`** in any message, log line, or escalation: pin a constant, or use `problems_from`.
- **`ruff format --check .` reads Markdown outside `docs/`**, and formats Python code blocks in it.
