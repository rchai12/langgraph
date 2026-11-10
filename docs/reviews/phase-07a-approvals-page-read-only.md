# Review: Phase 7a

- Verdict: PASS
- Passed: 704
- Findings: 0
- Approved deviations: None
- For the architect: The probe counts LOCALHOST:<port> as answered because TestClient lowercases that Host before the app sees it; a raw Host of LOCALHOST:<port> is 400.

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first cli,core` ended with `All checks passed.` The tests step passed 704, with 0 failed, 0 skipped, 0 xfailed, and no warnings summary. `critical coverage` passed, including `web/app.py`.

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            87 passed    0 failed    0 skipped
  core          617 passed    0 failed    0 skipped
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

`.venv/bin/python -m coverage report --include="*/conductor/web/*.py,*/conductor/views.py,*/conductor/config.py,*/conductor/cli/main.py" --fail-under=100` exited 0 with `TOTAL` at 100% (473 statements, 116 branches). `.venv/bin/python -m pytest tests/e2e/test_web_pages.py tests/e2e/test_cli_web.py --no-cov` printed `26 passed`. Versions printed `0.162.2 3.1.6 1.10.0`. `.venv/bin/python scripts/check_reports.py --phase 7a`, run before this report, printed `Reports OK.` `git diff HEAD -- pyproject.toml` is the two dependency lines and the template package-data line. The protected diff printed nothing. All four searches printed nothing.

## Scope

Before this report, `git status --short` listed the 12 scope paths and nothing else. Both given files equal the spec fences. `docs/testing.md` and `scripts/critical_modules.txt` add only the `web/app.py` line after `mcp_client/check.py`.

## Requirements

- R1: `test_the_default_port` and `test_a_bad_port_setting` (80, 65536, 87a5). The check sits after the MCP timeout problem and before the `CONDUCTOR_MCP__` problems.
- R2: `test_a_pending_request`, `test_a_rejected_request_with_a_note`, `test_an_edited_request`, `test_an_open_escalation_with_two_problems`, and `test_an_answered_escalation`, each with the block text written out. `cli/main.py` prints through `request_lines` and `escalation_lines`. The earlier CLI tests passed in the full check.
- R3: `test_only_this_server_by_name_is_answered` (3 cases), `test_localhost_by_port_is_answered`, and `test_two_host_headers_are_refused_and_localhost_is_answered`.
- R4: `test_every_answer_carries_the_security_headers` (2 cases), `test_the_headers`, and `test_post_and_a_broken_store_carry_every_header`.
- R5: `test_an_empty_home_page`, `test_the_home_page_lists_what_waits_oldest_first`, `test_a_pending_approval`, `test_a_decided_approval_shows_who_decided_and_the_edit`, `test_an_escalation_and_its_answer`, `test_nothing_else_is_served` (3 cases), and `test_a_plan_shows_both_steps_and_escalations_are_oldest_first`.
- R6: `test_text_from_a_request_is_escaped` and `test_a_note_a_detail_and_an_action_are_escaped`. Search 2 printed nothing.
- R7: `test_what_is_not_there` (3 cases), `test_a_store_that_cannot_be_read`, and `test_a_capital_id_is_not_found_without_opening_the_store` (`"A" * 32`, a `Store` that fails).
- R8: `test_the_web_command_serves_on_this_machine_only` and `test_a_port_in_use_is_refused`. Search 3 printed nothing.
- R9: searches 1 and 4 printed nothing. `web/` imports only `conductor.config`, `conductor.store`, and `conductor.views`.
- R10: the coverage gate, as above.

## Probe

The script was saved outside the repository, run from the repository root, and deleted.

```
ok   no stored text becomes markup on 51 pages
ok   every answer carries the security headers
FAIL only two Host values are answered (['127.0.0.1:61292', 'LOCALHOST:61292', 'localhost:61292'])
ok   the real server answers on 127.0.0.1 with no server header
FAILURES 1
```

A direct ASGI request with `Host: LOCALHOST:8766` is `400`. The same URL through `TestClient` is `200`, and a direct `Host: localhost:8766` is `200`. The app's set is the two exact values.

## Spot checks

Each deciding test failed. The edits were reversed and both files matched their text from before the spots. `__pycache__` under `src`, `tests`, and `scripts` was removed before each pytest and again at the end.

| # | Printed failure |
|---|---|
| 1 | `(200, '<!DOCTYPE ...')` against `(400, 'Bad host')` for `localhost` |
| 2 | `KeyError: 'x-frame-options'` for `evil.example` |
| 3 | `assert '<script>' not in` the page |
| 4 | `AssertionError: the store was opened` for `/approvals/` plus 32 capitals |
| 5 | `StoreError: conductor.db: not a database` |
| 6 | `assert 200 in (404, 405)` for `/docs` |
| 7 | `KeyError: 'server_header'` |
| 8 | `(0, 'Serving on http://127.0.0.1:<port>/\n', '')` against the taken-port error |

## Progress

`## Phase 7a: the approvals page, read-only (2026-11-09)` has `Tests: 664 -> 704 (given 26)`, `Changed files: 12`, and no deviations.
