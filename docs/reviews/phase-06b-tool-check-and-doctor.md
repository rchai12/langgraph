# Review: Phase 6b

- Verdict: PASS
- Passed: 641
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first cli,core` ended with `All checks passed.` The tests step passed 641, with 0 failed, 0 skipped, 0 xfailed, and no warnings summary. `critical coverage` passed.

```
Sections:
  cli            81 passed    0 failed    0 skipped
  core          560 passed    0 failed    0 skipped
```

```
Summary:
  lint: passed
  format: passed
  tests (cli,core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

`.venv/bin/python -m coverage report --include="*/conductor/mcp_client/*.py,*/conductor/runtime.py,*/conductor/cli/main.py,*/conductor/diagnostics.py,*/conductor/domains/__init__.py" --fail-under=100` exited 0. TOTAL 710 statements, 182 branches, 100%.

`.venv/bin/python -m pytest tests/unit/test_tool_check.py tests/e2e/test_cli_tool_check.py --no-cov` printed `26 passed`. The two given files equal the spec fences. `scripts/check_reports.py --phase 6b`, run before this report, printed `Reports OK.`

The phase code is committed at `19cc501`. `git diff HEAD` of `runtime.py` and of the protected paths is empty. Against the parent `ec1fa40`, `open_runtime(settings, *, model=None)` is unchanged, the registry is `domains.registered(settings)`, `settings` stays on `Runtime`, and `check_tools` is called at the start of `ask` and `resume`. `pgrep -f mcp_fake_server` printed nothing. All three searches printed nothing.

## Requirements

- R1: `test_the_json_types_of_a_field`; `test_nested_anyof_a_ref_to_anyof_and_a_repeated_type`.
- R2: `test_a_domain_that_fits_its_server`; `test_a_registry_without_servers_starts_nothing`; `test_problems_come_in_declaration_order`; `test_two_domains_are_listed_and_an_idle_server_has_no_problem`.
- R3: `test_what_the_check_refuses`; `test_a_write_action_may_use_a_read_only_tool`; `test_a_missing_tool_stops_before_the_read_only_rule`; `test_two_type_problems_stay_in_field_order`; `test_an_output_schema_without_properties_passes`. Probe: both input and read-only lines `ok`.
- R4: `test_a_server_that_cannot_be_reached_is_one_problem`; `test_the_next_server_is_checked_after_one_cannot_be_reached`.
- R5: `test_a_secret_in_a_schema_title_stays_out_of_the_message`. The messages in `check.py` are the Design texts with names, types, and codes.
- R6: `test_the_check_passes_when_the_tools_fit`; `test_a_run_is_refused_when_the_tools_do_not_fit`; `test_a_server_without_a_command_line_refuses_a_resume`; `test_registered_appends_the_demo_domain_only_when_asked`; `test_open_runtime_starts_nothing_and_ask_lists_tools_once`. Probe: `ok   the runtime opens exactly when no action has a problem`.
- R7: `test_ask_prints_every_problem`; `test_recording_without_resuming_skips_the_check`; `test_resume_and_retry_print_the_failed_check`; `test_cancel_without_resuming_starts_no_server`.
- R8: `test_the_doctor_checks_each_server`; `test_an_unset_command_fails_the_doctor`; `test_two_problems_count_as_two_failed_checks`; `test_a_server_with_no_tool_action_reports_zero_actions`. `test_one_tool_and_one_action_use_the_singular` covers the singular wording.
- R9: searches 1 and 2 printed nothing. `check.py` calls `list_tools` only.
- R10: the coverage gate and `critical coverage`. `docs/testing.md` and `scripts/critical_modules.txt` add `mcp_client/check.py` after `mcp_client/client.py`.

## Probe

Saved outside the repository, run with `.venv/bin/python`, then deleted. `FAILURES 0`.

```
ok   input problems match the probe's reading of the rules (600 pairs)
ok   only a read action on a tool not marked read-only is refused (9 cases)
ok   the runtime opens exactly when no action has a problem (6 sets, a real server)
FAILURES 0
```

## Spot checks

Each deciding test failed. `check.py`, `runtime.py`, and `diagnostics.py` matched their pre-check text afterwards.

1. Rule 5 refused only `read_only is False`. The `read_only=None` case returned `[]`.
2. The `effect == "read"` condition was removed. The fit test reported `action finance.note: a read action needs a tool marked read-only`.
3. `anyOf` was ignored. The date-or-null case returned `('any',)`.
4. Rule 4 walked no required names. The `by` case returned `[]`.
5. Rules 7 to 9 ran with missing properties treated as empty. The open-schema test reported `the tool does not promise result field note_id`.
6. `resume` did not call `check_tools`. The failure was `RunError: no run 33333333333333333333333333333333`.
7. `open_runtime` called `check_tools` before yielding. The `--no-resume` command exited 1 with empty stdout.
8. Server `FAIL` lines were left out of the summary. The tail ended `All checks passed.`

## Progress

`## Phase 6b: the tool check and the doctor (2026-11-09)` with `Tests: 600 -> 641 (given 26)`. Changed files: 15. Deviations: None. The follow-up names the skill file, the spec, and the verification guide. The uncommitted edits now are that guide's corrected spot rows and the skill note.
