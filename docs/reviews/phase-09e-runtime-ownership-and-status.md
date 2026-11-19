# Review: Phase 9e

- Verdict: PASS
- Passed: 1096
- Findings: 0
- Approved deviations: None
- For the architect: S2 omitted the start append and failed with RunNotFound on the empty supplied log, before the kind assertion. S4 and S5 printed DID NOT RAISE, which is version 99 and the uppercase id being accepted.

## Findings

None

Parts that needed a repair: None

Built beyond the spec: None

## Gates

Reviewed commit `ba87ad4` against planning baseline `ee98701`. The spec and guide are unchanged from that baseline. `scripts/check.py --first cli,core` ended with `All checks passed.` 1096 passed in 53.95s. Sections: scripts 0, cli 98, core 998. Summary: lint passed, format passed, tests (cli,core) passed, tests passed, critical coverage passed. No failed, skipped, xfailed, or warnings summary. The coverage gate measures all four modules, 805 statements, TOTAL 100% (`status.py` 170, `supervisor.py` 240, `runtime.py` 188, `app.py` 207). The four given test files passed 30. `git diff --check` and `git diff --check ee98701 HEAD` are empty. The protected path diff is empty on HEAD and across the phase commit. `grep -c '^## Phase 9e: '` is 1. `scripts/check_reports.py --phase 9e` printed `Reports OK.` before this report.

## Scope

`ba87ad4` changes the 19 scope paths and nothing else. The four given test files equal the spec fences. The five predecessor test edits, `scripts/critical_modules.txt`, and `docs/testing.md` match the given patch. Both searches are empty. `read_state` opens `as_uri() + "?mode=ro"`, runs `BEGIN` before `get_tuple`, sets `is_setup = True`, and does not use `immutable=1`. It constructs no graph, model, registry, store, or event log. `RunStateUnavailable` on GET is 503 with `The run state is not available`; a missing run stays 404. There is no `_SERVICES` or weak-map owner.

## Probe

`--oracle-only` printed `FAILURES 0`. The runtime probe printed:

```
ok   20 closed runtimes release their graphs and models
ok   10 restart cycles retain two approvals and read-only status
FAILURES 0
```

## Spots

The seven deciding tests passed unmodified in a scratch copy. Each mutation then failed, and the copy was restored from the saved bytes. The reviewed tree stayed clean.

1. `globals()['_SPOT_OWNER'] = services` before `build_graph` returns. The weak reference still held `Services` after collection.
2. The supplied-log `RUN_STARTED` append was omitted. `supplied.read` raised `RunNotFound: no run aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`.
3. Interrupts were taken before completed pending output. The result was `waiting` with the old approval, against `stopped` at `ask_step`.
4. The version inequality was disabled (`version != 4` replaced by `False`). `[version]` printed `Failed: DID NOT RAISE RunStateUnavailable`.
5. The interrupt id pattern also accepted `A-F`. `[invalid-id]` printed `Failed: DID NOT RAISE RunStateUnavailable`.
6. `open_runtime(settings).__enter__()` was inserted before the read. The test raised `status read constructed execution services`.
7. The unavailable response code was changed from 503 to 404. The assertion was `(404, 'The run state is not available')` against `(503, 'The run state is not available')`.

## Coder tests

- Missing tuple, invalid ids, one-field refusals, null-task bookkeeping, start-to-route pending output, opaque errors, and cleared terminal references: `tests/unit/test_checkpoint_status_cases.py`.
- Saved format-4 statuses, pending output beside an old interrupt, lease and reserved-path reads, corrupt blobs, `BEGIN` before both selects, a live WAL, and no extra `RUN_STARTED` on a bad start: `tests/integration/test_run_status_cases.py`.
- Resume of a malformed run does not look up a decision or invoke: `test_resume_of_a_malformed_run_does_not_look_up_or_invoke`.
- Stored malformed state is a generic 503, a done page escapes and does not decide, and busy refresh stays: `tests/e2e/test_web_run_status_cases.py`.

## Requirements

- R1: `test_services_are_released_with_the_graph`, `test_many_graphs_do_not_retain_services`, and the probe's 20 closed runtimes.
- R2: `test_start_records_through_the_explicit_log` and `test_a_bad_start_adds_no_run_and_ask_records_the_start_first`.
- R3: the 14 `test_checkpoint_status.py` cases and `test_one_bad_field_is_refused`.
- R4: `test_stopped_status_matches_the_execution_reader` and `test_resume_of_a_malformed_run_does_not_look_up_or_invoke`.
- R5: the 9 `test_run_status.py` cases, the coder SQLite cases, and the probe's 10 restart cycles.
- R6: the 4 `test_web_run_status.py` cases and `test_a_done_page_escapes_and_a_get_does_not_decide`.
- R7: the 19-file commit, the exact given files, and the exact migration patch.
- R8: the four-module coverage gate at 100%, and the progress entry `1006 -> 1096 (given 30)`.
