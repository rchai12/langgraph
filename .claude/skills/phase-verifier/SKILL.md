---
name: phase-verifier
description: Independently verify one named Conductor phase against its spec and guide, audit scope and evidence, and write only the review report.
---

# Conductor phase verifier

Read `AGENTS.md`, `docs/architecture.md`, `docs/phase-conventions.md`, the named
spec with Corrections, `docs/testing.md`, its guide and phase progress entry.
Inspect `git status --short --untracked-files=all`, `git diff HEAD`, and untracked
files. The only repository artifact you write is `docs/reviews/<spec filename>`.

Follow [the shared workflow](../../../docs/ai-workflow.md) for baseline isolation,
stopped coders and permitted evidence reuse. Check that the coder ran before
expensive gates. No implementation and no progress entry means report the missing
handoff without creating an orphan review. Do not create a coder's progress entry.

Run guide gates exactly, beginning with its `scripts/check.py --first ...` check,
unless the owner explicitly narrows the reassessment. Audit Scope and equality of
embedded given files, every requirement and named coder test, searches, critical
coverage and meaningful assertions. Separate environment and baseline failures
from code defects; do not waive a literal gate yourself.

Save the embedded probe outside the repository, run it from the root, then remove
only that temporary artifact. Execute spot checks in an isolated copy using that
copy's imports. Confirm the unmodified deciding test passes, the mutation fails
for its intended reason and the reviewed tree is unchanged. A collection error
does not demonstrate a caught mutation. Trace surviving mutations through schema
constraints, fake clocks and later reads to distinguish weak tests from defects.

Write the exact verdict format from the conventions, with one requirement,
location, expected result and observation per finding. Include concise gate,
section and spot-check evidence; label reused evidence. Run
`.venv/bin/python scripts/check_reports.py --phase <id>` after writing the report.
For FAIL, hand back requirement, observation and required result; do not prescribe
an implementation. Never repair code, rewrite the spec, commit or push.
