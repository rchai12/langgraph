# Review: Phase 6a

- Verdict: PASS
- Passed: 600
- Findings: 0
- Approved deviations: None
- For the architect: spot 3 ended with code closed; spot 5 left __cause__ as a nested ExceptionGroup whose leaf is MCPError

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first core` ended with `All checks passed.` The tests step passed 600, with 0 failed, 0 skipped, 0 xfailed, and no warnings summary. `critical coverage` passed.

```
Sections:
  core          532 passed    0 failed    0 skipped
```

```
Summary:
  lint: passed
  format: passed
  tests (core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

`.venv/bin/python -m coverage report --include="*/conductor/mcp_client/*.py,*/conductor/registry.py,*/conductor/config.py" --fail-under=100` exited 0. TOTAL 340 statements, 112 branches, 100%.

`.venv/bin/python -m pytest tests/unit/test_mcp_declarations.py tests/integration/test_mcp_client.py --no-cov` printed `24 passed`. `mcp` is `2.3.0`. `opentelemetry.sdk` is `None`. `scripts/check_reports.py --phase 6a`, run before this report, printed `Reports OK.`

`git diff HEAD -- pyproject.toml` is the one line `"mcp>=2.3,<2.4",`. The protected diff is empty. `pgrep -f mcp_fake_server` printed nothing after the check and after the spots. All four searches printed nothing.

The three given files equal the spec fences. `docs/testing.md` and `scripts/critical_modules.txt` add the `mcp_client/client.py` line after `runtime.py`.

## Requirements

- R1: `test_the_declarations`. The full check passed, including the earlier registry tests.
- R2: `test_server_declarations_are_checked`; `test_a_long_environment_name_is_refused_before_an_action`; `test_a_domain_without_servers_keeps_tool_actions`. Probe: `ok   the registry accepts exactly the declarations the rules allow (400 sets)`.
- R3: `test_the_mcp_settings`; `test_bad_mcp_settings`; `test_bad_server_names_follow_the_timeout_in_sorted_order`; `test_a_quoted_command_keeps_a_path_with_spaces`.
- R4: `test_a_call_and_a_failed_call`; `test_a_server_that_takes_too_long_is_ended`; `test_two_calls_start_two_processes_and_a_thread_can_call`. `McpClient._run` calls `asyncio.run` for each request and keeps no session. Probe: `ok   four calls at once all succeed` and `ok   no server process is left behind`.
- R5: `test_the_server_sees_only_safe_and_declared_variables`; `test_a_declared_variable_that_is_unset_stays_unset`. Probe: `ok   the server sees exactly the declared variables (16 set, 6 declared)`.
- R6: `test_the_server_log_is_private_and_appended`; `test_an_existing_log_folder_keeps_its_mode`.
- R7: `test_the_tools_of_a_server`; `test_a_call_and_a_failed_call`; `test_a_string_result_is_structured`.
- R8: `test_a_server_without_a_command_line`; `test_a_command_that_cannot_start`; `test_a_server_that_stops`; `test_a_server_that_takes_too_long_is_ended`; `test_a_program_that_is_not_executable_fails_to_start`; `test_an_unexpected_session_error_passes_through`. `test_a_bare_connection_error_is_closed` and `test_a_closed_connection_and_a_mixed_group` cover the bare `MCPError` and the mixed group. Probe: `ok   bad commands give start_failed, closed, or timeout`.
- R9: the four searches printed nothing; `test_the_sdk_and_no_telemetry`. Probe: `ok   no OpenTelemetry SDK was loaded`.
- R10: the coverage gate and `critical coverage`.

## Probe

Saved outside the repository, run with `.venv/bin/python`, then deleted. `FAILURES 0`.

```
ok   the server sees exactly the declared variables (16 set, 6 declared)
ok   four calls at once all succeed (['t0', 't1', 't2', 't3'])
ok   bad commands give start_failed, closed, or timeout ({'missing': 'start_failed', 'exits': 'closed', 'fails': 'closed', 'not executable': 'start_failed'})
ok   no server process is left behind
ok   the registry accepts exactly the declarations the rules allow (400 sets)
ok   no OpenTelemetry SDK was loaded
FAILURES 0
```

## Spot checks

Each deciding test failed. `client.py`, `registry.py`, and `config.py` matched their pre-check text afterwards.

1. `env=None`. `FAKE_PASSED` was `<unset>`.
2. `os.environ` copied whole. The other two values were `no` and `owner`.
3. `fail_after` replaced by `if True`. The code was `closed`.
4. The group handler re-raised. The failure was an `ExceptionGroup` whose leaf is `MCPError: Connection closed`.
5. The closed raises used `from error`. `__cause__` was `ExceptionGroup('unhandled errors in a TaskGroup', [ExceptionGroup(..., [MCPError(...)])])`.
6. Missing annotations stored `read_only=False`. The pair was `(False, False)`.
7. The log file was left to `open()`. Its mode was `0o644` (420 against 384).
8. The `CONDUCTOR_` check was removed. `RegistryError` was not raised.
9. `ValidationError` was re-raised. The message was `Input should be a valid string [type=string_type, input_value=1, input_type=int]`.

## Progress

`## Phase 6a: MCP servers and the client (2026-11-09)` with `Tests: 564 -> 600 (given 24)`. The new public names match the registry, settings, and client. Changed files: 12, the current `git status --short` count. Deviations: None. Follow-ups: None.
