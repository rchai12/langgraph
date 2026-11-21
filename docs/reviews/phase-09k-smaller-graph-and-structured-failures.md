# Review: Phase 9k

- Verdict: PASS
- Passed: 1381
- Findings: 0
- Approved deviations: None
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

G1: All checks passed, 1381 passed (core 1234, cli 117, scripts 30), 0 failed
G2: TOTAL 100%
G3: 32 passed
G4: FAILURES 0
G5: empty
G6: empty
G7: empty
G8: 1
G9: Reports OK.
S1 fails: AssertionError: unknown_outcome True == False
S2 fails: AssertionError: unknown_outcome False == True
S3 fails: AssertionError: unknown_outcome False == True
S4 fails: AssertionError: code None == invalid_result
S5 fails: detail 'the step failed' == 'the step failed (timeout)'
S6 fails: assert 9 names == 10 names
S7 fails: assert [True, True, ..., False, True] == [True, True, True, True, True]
searches: silent
