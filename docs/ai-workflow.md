# AI development workflow

This repository uses the phase workflow from the sibling `finances` and `tasking`
projects, adapted to Conductor. These are development roles. The runtime coding
adapters described for Phase 10 remain governed by their phase spec.

## Roles and entry points

| Role | Assignment | Deliverable |
|---|---|---|
| `phase-architect` | Plan, split, or revise a phase | Executable spec and matching verification guide; affected design docs |
| `phase-coder` | Implement one named phase | Scoped implementation, acceptance evidence, progress entry |
| `phase-verifier` | Independently review one named phase | Review report only |

Codex discovers entry points in `.agents/skills/`. Claude discovers the same roles
in `.claude/skills/`. The Codex entry points link to the shared instructions in
`.claude/skills/` so the two clients follow one maintained procedure. Read the
selected role's instructions before acting. Implementation and verification are
separate assignments. A role assignment does not itself
authorize delegation, commits, pushes, or starting another phase.

Read `AGENTS.md`, `docs/architecture.md`, and `docs/phase-conventions.md` in that
order, then the assigned spec. Read `docs/testing.md` before implementation or
review. The spec's explicit rules take precedence over shared phase defaults.

## Baseline and handoff

Before implementation, identify the full baseline commit and inspect
`git status --short --untracked-files=all`. The finalized spec and guide must be
committed and unchanged; inspect `git diff HEAD -- <spec> <guide>`, as well as
whether those paths are tracked. Given files embedded in Conductor specs are
copied exactly by the coder; do not switch to tasking's committed-given-file scheme.

Use a clean checkout for implementation. When unrelated work exists, prepare a
fresh local clone in a writable temporary directory from the intended committed
baseline. Preserve the original work. Never stash, reset, clean, or commit
unrelated paths to manufacture a clean tree. If finalized planning documents are
not committed, finish and validate them before handing off; request a commit only
when the owner has not already authorized it.

Link the existing `.venv` into the clone and exclude that symlink through the
clone's `.git/info/exclude`. Do not install packages or change tracked ignore
rules. Set `PYTHONPATH=<clone>/src` on Python commands and verify import provenance
with `.venv/bin/python -c 'import conductor; print(conductor.__file__)'` from the
clone. It must resolve inside that clone.

For a review of changes already mixed with unrelated work, copy only the phase's
explicit paths into an isolated clone, including explicit deletions and its
progress entry. Compare bytes and inventory untracked paths too. Inspect shared
documents for overlapping edits rather than copying unrelated changes. Record
the reviewed baseline and changed paths. Before returning a review to the original
workspace, confirm the implementation still matches the reviewed bytes.
Isolation establishes reviewable scope; it does not prove an originally clean start.

## Evidence and corrections

Use `.venv/bin/python scripts/check.py --section <section>` while developing and
the spec's `--first <sections>` command for final acceptance. Run the full suite
and coverage consumers sequentially: they share `.coverage`. Consume coverage
immediately after the producing check, before another coverage run.

Capture output and actual exit codes in temporary logs. Show concise failures,
the required `Sections:` table and summary, and retain the full logs. Do not let
a `tail` or other pipeline hide a failing command's exit code. No `--quiet`,
`scripts/accept.py`, `scripts/progress.py`, or `scripts/spot_check.py` is provided
here; tasking's implementations depend on `docket` and different report formats.

Classify a failure as implementation, specification/test, baseline/scope, or
environment. Never weaken a test for a sandbox restriction or rewrite a spec to
approve incorrect behavior. A spec correction states which gates are live again
and why. Reuse earlier evidence only if the owner or guide permits the narrowed
review and the relevant source, tests, dependencies, configuration and environment
are unchanged; identify reused evidence explicitly.

The verifier writes only `docs/reviews/<spec filename>`. Execute mutation checks
in an isolated scratch copy with its own imports, then compare the reviewed tree
to its starting state. `spot.py` replaces one exact match and restores it; run it
with `--root <scratch copy>`. An assertion failure is useful evidence; collection
errors, missing dependencies, and no tests collected are not successful mutations.
Read the output as well as the exit code.

Probes are embedded in guides, saved outside the repository and run from its root.
Keep their independent oracle distinct from the feature. A failing oracle
self-check is a specification defect. A mutation that survives can expose weak
tests; trace the deciding input through every defense before assigning blame.

## Stops and completion

An implementation ends with the phase's progress entry, including a genuine stop.
Keep the exact schema in `docs/phase-conventions.md`; the first Follow-ups item for
a stop is `Stopped: <requirement/command> | <observation> | <what allows completion>`.
Use actual counts from completed commands; retain the last measured count and
explain any unrun final gate in the stop. Preserve earlier phase history.

A verifier with no implementation and no phase progress entry reports that fact
to the owner without creating an orphan review: the existing report checker
requires a progress entry for every review. If the coder stopped and an entry
exists, record the unmet requirements and unrun gates in a FAIL review; do not
repair the implementation. Run `scripts/check_reports.py --phase <id>` after a
phase entry or review is written; it must print `Reports OK.`.

Workflow maintenance is not an application phase. Record its scope and validation
in the handoff or maintenance record rather than inventing a phase id or inserting
a non-phase heading into the machine-parsed `docs/progress.md`.

An architect assignment includes validated given tests, exact collection counts,
scope, acceptance, guide and concrete handoff. A draft is intermediate work.
Report real blockers and finish independent work. Keep the architect's scratch
work to names-only stubs, given artifacts and small synthetic spikes; do not
implement the feature or run a full acceptance suite in a planning clone.

## Conductor boundaries

Carry `AGENTS.md` into each role: local Ollama only through `llm/decide.py`, no
telemetry, closed schemas and registry enumerations, invalid output escalates,
approval for every side effect, synthetic offline tests, time and ids through
their modules, configuration through `get_settings()`, and thin CLI/web layers.
Development never operates a real model, MCP service, mailbox or finance dataset.
Do not import finances' no-model rule or tasking's calendar/Keychain policies.

## Maintenance record

- 2026-11-17: added the three development roles for both clients, baseline and
  correction handoffs, and the AST code map adapted from finances. Retained
  Conductor's embedded given files, external probes and existing report schema.
  Existing audit and handoff artifacts are outside this maintenance assignment.
  Validation: all six skill entry points and their links validated; the code map
  passed synthetic signature, field, constant, importer and filter checks without
  executing source. `scripts/check.py` ended with `All checks passed.`: 1006 tests,
  100% coverage, lint, format and critical coverage passed. `check_reports.py`
  printed `Reports OK.`. Tests required permission for their own loopback servers.
