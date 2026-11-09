# Review: Phase 5a

- Verdict: PASS
- Passed: 472
- Findings: 0
- Approved deviations: None
- For the architect: the Phase 5a probe stores phrase words from str.split as lists, so its keyword matcher never matches; the same probe with tuples of tuples reports FAILURES 0

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

## Gates

`.venv/bin/python scripts/check.py --first cli,core` exited 0. Last lines:

```
Summary:
  lint: passed
  format: passed
  tests (cli,core): passed
  tests: passed
  critical coverage: passed
All checks passed.
```

The `tests` step reported `472 passed` in 18.69s. No skipped, xfailed, or warnings summary. Sections, each with 0 failed:

```
Sections:
  cli            51 passed    0 failed    0 skipped
  core          421 passed    0 failed    0 skipped
```

```
Sections:
  scripts         0 passed    0 failed    0 skipped
  cli            51 passed    0 failed    0 skipped
  core          421 passed    0 failed    0 skipped
```

`.venv/bin/python -m coverage report --include="*/conductor/routing/*.py,*/conductor/reports.py,*/conductor/registry.py,*/conductor/diagnostics.py,*/conductor/llm/tags.py" --fail-under=100` exited 0. TOTAL is 100%.

`.venv/bin/python -m pytest tests/unit/test_rules.py tests/unit/test_route.py tests/unit/test_reports_phase.py tests/e2e/test_check_reports_phase.py tests/e2e/test_cli_doctor_digest.py --no-cov` reported `37 passed`.

`.venv/bin/python scripts/check_reports.py --phase 5a`, before this review, printed `Reports OK.` `.venv/bin/python scripts/check_reports.py --phase 5b` printed the two expected problems and exited 1.

The protected diff printed nothing. The given prompt and the five given test files match the spec's blocks. The demo, support, and doctor diffs are the given edits. `docs/testing.md`, `scripts/critical_modules.txt`, and `docs/phase-conventions.md` carry the spec's edits. Searches 1 to 4 printed nothing. `git status --short` lists 23 paths, matching the progress entry.

## Progress entry

```
## Phase 5a: routing (2026-11-09)
- Tests: 423 -> 472 (given 37)
- New public names: `registry`: `RESERVED_DOMAIN`, `PREFIX_RULE`, `MAX_PHRASES`, `Rule`, `Domain.rules`; `routing.rules`: `RuleRoute`, `RuleConflict`, `words`, `match_rules`; `routing.route`: `REQUEST_MESSAGE`, `NO_DOMAINS_MESSAGE`, `CONFLICT_MESSAGE`, `EMPTY_MESSAGE`, `NO_FIT_MESSAGE`, `ROUTE_REPLY_TOKENS`, `RouteInputs`, `Routed`, `route_output`, `route_point`, `route_fields`, `route_request`; `reports`: `PHASE_MESSAGE`; `llm.tags`: `fetch_models`
- Changed files: 23
- Deviations:
  - None
- Follow-ups:
  - The verification probe compares phrase words from `str.split` (lists) to tuples, so its matcher never matches; with those words made tuples the same probe reports FAILURES 0.
```

The heading and tests line match section 8. The follow-up is what the probe run showed.

## Coder tests

Each bullet of "Tests to write" has a deciding assertion:

- R1 a duplicate name, 21 phrases, a 65-letter word, seven words, and a bad action named before a bad rule: `test_a_bad_rule_is_named_after_a_bad_action`
- R2 `words("ÉCHO café_2")`: `test_words_keep_only_ascii_letters_and_digits`
- R3 `demo:` with an empty rest, `unknown: x`, and a 33-letter name: `test_an_empty_prefix_routes_and_an_unknown_name_does_not`
- R4 a conflict lists every matching rule in order: `test_a_conflict_lists_every_matching_rule_in_registry_order`
- R5 one domain's enum and registry order: `test_one_domain_enumerates_itself_and_lists_domains_in_order`
- R6 a 2000-character request and 20 of 21 conflict problems: `test_a_request_of_2000_characters_routes_and_a_wide_conflict_keeps_20`
- R7 `escalation_for`, `model_info` unavailable, and a `ScriptError`: `test_a_failed_reply_is_the_escalation_and_a_script_error_passes`
- R9 neither spec nor entry, phase `5`, `""`, and a malformed entry: `test_neither_spec_nor_entry_names_the_spec_first`, `test_phase_5_matches_a_zero_padded_spec`, `test_an_empty_phase_id_is_refused`, `test_a_malformed_entry_is_also_a_missing_entry`
- R10 a missing, numeric, or uppercase digest, and a `:latest` name: `test_a_bad_digest_is_missing_and_a_latest_tag_is_shown`

`route_request` calls `decide` once and catches only `InvalidModelOutput` and `ModelUnavailable`. No `# pragma: no cover` was added.

## Probe

The guide's probe, saved outside the repo, run once, then deleted:

```
ok   a registered prefix routes to its domain and is stripped (300 requests)
FAIL keyword rules agree with an independent matcher (2000 requests, {'route': 0, 'conflict': 0, 'none': 2000})
ok   a rule route or a rule conflict never asks the model
ok   the classifier routes only to registered domains; anything else escalates
ok   with no domains every request escalates without the model
ok   check_reports --phase names a missing spec and a missing entry (21 phases)
ok   the doctor shows a valid digest's first 12 characters and fails without one
FAILURES 1
```

The keyword line compares a tuple of words with a list from `str.split`, so the independent matcher records no matches. The same script with `tuple(tuple(p.split(" ")) for p in rule.phrases)`, also outside the repo and then deleted, reported `FAILURES 0`, including `keyword rules agree with an independent matcher (2000 requests, {'route': 988, 'conflict': 435, 'none': 577})`.

## Spot checks

Each change was made with `PYTHONDONTWRITEBYTECODE=1`, the deciding test failed, and the reverse edit restored the file. `__pycache__` directories under `src`, `tests`, and `scripts` were removed afterwards.

| # | Deciding result |
|---|---|
| 1 | `echoes of the past` routed to `demo.echo` |
| 2 | `write it down` routed to `demo.note` |
| 3 | `LAB:` did not produce `lab.prefix` |
| 4 | `lab: echo and note` did not produce `lab.prefix` |
| 5 | the two-domain request returned `demo.echo` instead of `RuleConflict` |
| 6 | `test_no_domains_escalate_without_asking` raised `AssertionError: the model was asked` |
| 7 | `unknown` came back as `Routed` |
| 8 | `test_the_route_point_and_its_prompt` lost the pinned schema |
| 9 | `(True, False)` returned `[]` instead of the missing-entry problem |
| 10 | `sha256:` plus 64 a's was shown as a passing model line |
