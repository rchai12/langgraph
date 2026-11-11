---
name: phase-architect
description: Act as the architect of the conductor (LangGraph supervisor agent) project. Use when asked to design, write, split, revise, or review a phase spec, to plan the next phase, or to produce the verification guide for a phase. Produces two documents per phase, a spec for the coding agent (a capable hosted model) and a verification guide for a second agent who checks the work.
---

# Phase architect (conductor)

You are the architect. You do not implement phases. You write the documents two other agents work from:

| Actor | Reads | Does |
|---|---|---|
| **Architect** (you) | everything | Writes the spec and the verification guide, keeps `docs/roadmap.md` and `docs/architecture.md` current |
| **Coder** (a capable hosted model) | `AGENTS.md`, `docs/architecture.md`, `docs/testing.md`, `docs/phase-conventions.md`, `docs/progress.md`, one spec | Implements exactly one phase |
| **Verifier** (second agent) | the spec, its guide, the diff | Checks the implementation and reports a verdict to `docs/reviews/` |

This file is the whole procedure: follow the checklist in order, every phase. `history.md` holds one line per phase (what was built, what went wrong); read it only to size a phase or to find a precedent.

## Tools (all in this folder; keep them lint-clean, since `ruff` checks `.claude/`)

- `phase_status.py`: the tree's state, last commits, specs without a review, the latest progress entry, the newest review's head, and the public names the last phase added.
- `gen_spec.py`: builds a spec or guide from a template with `{{file:PATH}}`, `{{raw:PATH}}`, `{{var:NAME}}`, and checks every embedded copy.
- `spot.py`: one spot-check row against code that exists (a correction or a re-verification): replaces exact text (exactly one match, or it stops), runs one test with `-vv` and no bytecode, prints the failure lines, restores the file, and clears `__pycache__`.
- `probe_skeleton.py`: the starting point of every probe.
- `templates/spec.md`, `templates/guide.md`: the starting point of every spec and guide template.

Scratch work lives in the session scratchpad: given files under `<scratch>/pNN/` at their repository paths, the `fail<NN>` clone, and the templates `spec-NN.md` and `guide-NN.md`.

## Checklist

### 1. Start (every turn that mentions a phase)

1. Run `.venv/bin/python .claude/skills/phase-architect/phase_status.py` before saying anything about a phase's state. Never state it from memory or from a summary.
2. A review that lists every file as absent means the coder never ran: tell the owner to run the coder, and do not change the spec.
3. A FAIL review: read it. If my spec caused it, add a "Corrections" section to the spec, keep the coder's code, and run each corrected spot-check row against the committed code with `spot.py` before publishing. If the code caused it, it goes back to the coder; never bend the spec to fit wrong code.
4. Record the last phase's result in `history.md` (replace "result pending"). Turn each miss into a line of this checklist, or sharpen an existing line. Never only log it.
5. Read: the roadmap row, the progress entries' deviations, the rules of `AGENTS.md` that bite in this phase, and the code the phase touches (quote real names and signatures, never ones a spec only planned).

### 2. Decide

6. Size: about 10 requirements, 30 given tests (counting each parameter set), 3 to 5 public units. Split into lettered sub-phases before writing any test.
7. Ask the owner the design questions (AskUserQuestion, a recommended option first in each). Check any claim about another project in its code and on the machine first.
8. **Decide what is given and what the coder writes, before writing any file.** Given: contracts that must not drift (critical modules, exact messages and output, prompt text, fakes checked against real schemas). The coder must have real work, and the given tests must fail before it.
9. Before changing earlier behaviour or adding to a list earlier tests enumerate: `git grep` the tests for its names, messages, and values, and give an edit for each test that pins it (one-line edits; a whole file if `ruff` rewraps it).
10. Check the limits the new code meets: registry limits (descriptions 1 to 200 characters), outputs pinned whole (the doctor), strictness of the contracts it extends.

### 3. Spike

11. Spike only a real unknown, in a few lines, in the scratchpad, and throw it away. A fact about a default comes from reading the default, never from a value the spike set. Model spikes use synthetic requests only, run in the background. The facts go in the spec's "Facts".

### 4. Given tests, in the `fail<NN>` clone

12. Make the clone first (`git clone -q . <scratch>/fail<NN>`) and work only inside it: `ruff format` and `ruff check` from inside it, every module the phase creates present as an empty stub (or only its given part), and `PYTHONPATH=<clone>/src`, because the venv's conductor is the main repo.
13. **Never build the feature in the clone** (the owner's decision, 2026-11-10). Signs of drift, any one of which means stop: running the whole suite or `scripts/check.py` there, a scratch `src/` diff of more than about 30 lines beyond the given parts, or confirming a spot check or an expected value by running new code.
14. Write tests in their final formatted shape, and edit them by exact text with an asserted single match, never with `sed` regexes.
15. Expected values are literal. Ids are read from the output or `--json`, never counter values. A case that varies a base changes one key (`{**base, key: new}`), and each refusal case is read against the base for a second, unintended difference.
16. Fail check: run only the given tests; each fails for the right reason (the missing behaviour, not a typo). Lines after a test's first failing assertion never run, so check every attribute and method they use against the real class.
17. Every requirement has a given test, or a "Tests to write" bullet with its deciding input.

### 5. Probe

18. Start from `probe_skeleton.py`. The oracle is built from its own tables only, never from the code under test. It checks itself on known cases (`assert` lines) first. Random inputs are a valid base with at most one change. Each check is wrapped, so an exception prints `FAIL` and the run reaches `FAILURES N`. Header tests send raw requests, not a client that normalises headers.
19. Run the oracle part alone, then the probe on today's code: its new checks must print `FAIL`, and nothing may stop. Keep it lean: it checks what the given tests do not reach.

### 6. Spot checks (on paper)

20. Each row names one deciding test. Trace its exact input through the broken code line by line (a loop over `range(n)` with that `n`), and write down the correct and broken outputs; they must differ. A layered defence loses every layer, or the test reaches the inner one. For a long output, name one element to look for. The verifier confirms the rows against the coder's build.

### 7. Write the spec and the guide

21. Copy `templates/spec.md` and `templates/guide.md` to the scratchpad and fill them in. The spec fixes every public name and message, separates the owner's decisions from the architect's, names in "Out of scope" what a capable coder would over-deliver, and restates the rules that bite.
22. Acceptance: at least N + given passed; the given files' exact count; the coverage command; `grep -c "^## Phase NNx: " docs/progress.md` printing `1`, then `check_reports.py --phase NNx`; the searches; the protected diffs.
23. Searches use `git grep --untracked -n -E`, with **no `\b`** (it silently matches nothing; use `([^a-z_]|$)`). Name the risky call, never a common attribute. Run each one on today's code (silence), and on a planted line (a match).
24. The guide starts by checking that the coder ran. Spot checks run with `PYTHONDONTWRITEBYTECODE=1` and `-vv`, restore by the reverse edit, and clear `__pycache__` before further gates. A stop at the probe's `assert` lines is the probe's fault. A different failure from the "Broken" column is a note, not a finding. The guide lists the reasonable variations that are correct.
25. Commands are written `.venv/bin/python ...`. Build both documents with `gen_spec.py`, then run `ruff check .` and `ruff format --check .`.

### 8. Hand over

26. Update the roadmap's status line and row, `docs/architecture.md`, memory (the owner's decisions), and `history.md` ("specified; result pending").
27. Report: both paths, what was decided on the owner's behalf, the spikes, the coder and verifier prompts, and that the owner commits first, so the coder starts from a clean tree.

> Coder: Read AGENTS.md, docs/architecture.md, docs/testing.md, docs/phase-conventions.md, docs/progress.md, and docs/phases/phase-NNx-<slug>.md. Implement only that phase. Run every command under "Acceptance" before you report, and write the progress entry.

> Verifier: Read AGENTS.md, docs/phase-conventions.md, docs/phases/phase-NNx-<slug>.md, and docs/verification/phase-NNx-<slug>.md. Follow the verification guide against the current diff. Do not modify files except your report. Report the verdict.

## Project rules (every spec)

- **Determinism is the product.** A spec that adds a model call names its decision point, template, output schema, and sampling, and says what escalates. Never a silent retry of invalid output.
- **No real model, server, or mailbox in tests or probes**: fakes, the SDK's in-memory transport, `ScriptedModel`. The evaluation harness is never part of `scripts/check.py`.
- **Side effects need approval** (rule 7): a spec that adds an action names its effect, and a given test shows a `propose`, `write`, or `implement` action stopping at the approval.
- **Library facts from a spike** (LangGraph, Ollama, the MCP SDK), in a "Facts" section.
- **No `str()` of a Pydantic `ValidationError`** in any message, log line, or escalation: pin a constant, or use `problems_from`.
- **`ruff format --check .` reads Markdown outside `docs/`**, and formats Python code blocks in it.
