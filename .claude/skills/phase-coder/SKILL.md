---
name: phase-coder
description: Implement one named Conductor phase from its finalized spec and report acceptance evidence. Use for coder assignments with a separate independent verifier.
---

# Conductor phase coder

Implement only the phase the owner names. Read `AGENTS.md`,
`docs/architecture.md`, `docs/phase-conventions.md`, then the spec including its
Corrections section. Read `docs/testing.md`, the relevant progress entry and all
given tests in full before coding. Inspect source where the contract depends on it.

Follow [the shared workflow](../../../docs/ai-workflow.md) for baseline isolation,
evidence, corrections and stops. Require a committed executable spec and clean
baseline in the actual implementation checkout. Preserve unrelated work through
isolation. Do not read verification guides or review reports for a standard coder
assignment; use the findings handed back by the owner.

Change only Scope paths. Copy embedded given files exactly and write the named
coder behavior tests. Use `.venv/bin/python` and the existing environment. Build
only assigned behavior; choose the simplest permitted interpretation of an open
detail and record it. Stop for contradictory or impossible requirements, a broken
given contract or an unlisted dependency.

Run focused sections while working, then every acceptance command in order,
including the full `scripts/check.py --first <sections>` check. Consume coverage
immediately after its producer. Never use tasking-only flags or scripts.

Write the exact phase progress entry, including any stop, and run
`.venv/bin/python scripts/check_reports.py --phase <id>`. Report actual gate
evidence and requirement-to-test mapping as the conventions require. Hand the
completed implementation to the independent verifier. Do not commit, push,
delegate or start the next phase without an assignment.
