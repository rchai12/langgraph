# Docs

- [architecture.md](architecture.md): goal, principles, the supervisor graph, contracts, domains, model client, storage, the event log, the coding pipeline, approvals, evaluation, layout, the privacy boundary
- [roadmap.md](roadmap.md): all phases, their status, and the Backlog
- [testing.md](testing.md): test layers, rules, critical modules
- [phase-conventions.md](phase-conventions.md): what every phase spec and verification guide assume (starting checks, rules, acceptance, the progress entry, the verdict)
- [ai-workflow.md](ai-workflow.md): development roles, clean baselines, isolation, evidence, stops and correction handoffs for Claude and Codex
- [phases/](phases/): detailed specs, one per phase
- `verification/`: one guide per phase, for the second agent that checks the implementation against the spec
- [progress.md](progress.md): log the coding agent appends to after each phase
- `reviews/`: the verifier's report for each phase, with its verdict

## Workflow

1. Commit the spec, its verification guide, its given files and its probe, so `git status` is clean. Then give the coding agent one phase at a time, in a fresh session:

   > /phase-coder NNx

2. Give a second agent, in another fresh session:

   > /phase-verifier NNx

   The verifier writes its report to `reviews/`, named as the spec is. A FAIL goes back to the coding agent with the verifier's findings.
3. Commit.
4. The architect writes or adjusts the next phase spec and its verification guide based on what was actually built.

Use `phase-architect`, `phase-coder`, and `phase-verifier` for the respective
assignments. Codex discovers them in `.agents/skills/`; Claude discovers them in
`.claude/skills/`. The shared instructions are local to this repository and adapt
the `finances` and `tasking` workflows to Conductor's rules. No sibling skill or
script is an implicit prerequisite. Committing and pushing require the owner's
authorization.
