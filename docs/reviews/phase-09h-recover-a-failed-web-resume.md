# Review: Phase 9h

- Verdict: PASS
- Passed: 1271
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

G1: All checks passed, 1271 passed (cli 109, core 1132, scripts 30), 0 failed
G2: TOTAL 100%
G3: 43 passed
G4: FAILURES 0
G5: empty
G5b: tests/e2e/test_web_resume.py | 2 +-
G6: empty
G7: 1
G8: Reports OK.
S1 fails: AssertionError: assert extra error event
S2 fails: AssertionError: 'SYNTHETIC-SECRET' == 'RuntimeError'
S3 fails: AssertionError: assert [{'error': 'resume_failed', 'type': 'KeyboardInterrupt'}] == []
S4 fails: OSError: disk full
S5 fails: AssertionError: assert True is False
S6 fails: AssertionError: assert True is False
S7 fails: Failed: DID NOT RAISE StoreError
S8 fails: assert (True, True, True) == (False, False, False)
S9 fails: AssertionError: assert [run_id] == []
S10 fails: page shows the resume failed (RuntimeError)
S11 fails: AssertionError: assert 'The last resume failed' not in page
S12 fails: AssertionError: assert (303, '') == (403, 'Bad form token')
searches: silent
