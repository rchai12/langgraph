# Review: Phase 9i

- Verdict: PASS
- Passed: 1309
- Findings: 0
- Approved deviations: store._prepare stays a one-line call to private.ensure_file.
- For the architect: None

## Findings

None

Parts that needed a repair: none

Built beyond the spec: none

G1: All checks passed, 1309 passed (cli 117, core 1162, scripts 30), 0 failed
G2: TOTAL 100%
G3: 30 passed
G4: FAILURES 0
G5: empty
G6: empty
G7: empty
G8: 1
G9: Reports OK.
S1 fails: PermissionError
S2 fails: assert [493, 493, 448] == [448, 448, 448]
S3 fails: assert (448, 448) == (493, 448)
S4 fails: FileExistsError
S5 fails: Failed: DID NOT RAISE NotADirectoryError
S6 fails: AssertionError: assert (448, 256, b'one\n') == (448, 384, b'one\n')
S7 fails: FileExistsError
S8 fails: AssertionError: assert (['raced'], 384, b'other') == (['raced'], 420, b'other')
S9 fails: Failed: DID NOT RAISE FileExistsError
S10 fails: ok data folder line instead of FAIL open to other users
S11 fails: FileNotFoundError
searches: silent
