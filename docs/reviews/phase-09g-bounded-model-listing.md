# Review: Phase 9g

- Verdict: FAIL
- Passed: 1222
- Findings: 1
- Approved deviations: None
- For the architect: G6 and G7 are empty because 935a263 is already committed; the four existing-test diffs against its parent match the spec. S2, S3 and S4 one-line digests were truncated; -vv matched Broken.

## Findings

R4 | src/conductor/llm/tags.py:113 | expected capabilities () when the digest does not match | found a valid capabilities list is kept

Parts that needed a repair: the no_digest capabilities result

Built beyond the spec: none

G1: All checks passed, 1222 passed (scripts 30, cli 109, core 1083)
G2: TOTAL 261 stmts 100% (diagnostics 82, ollama 91, tags 88)
G3: 34 passed
G4: FAILURES 0
G5: empty
G6: empty
G7: empty
G8: 1
G9: Reports OK.
searches: silent
S1 fails: OllamaBadAnswer: unexpected answer
S2 fails: first Listed kept, problem None
S3 fails: uppercase digest kept, problem None
S4 fails: problem bad_capabilities
S5 fails: assert 'plain:latest' == 'plain'
S6 fails: DID NOT RAISE TooLarge
S7 fails: TooLarge: answer too large
S8 fails: 'bad_answer' vs 'too_large'
S9 fails: DID NOT RAISE ModelUnavailable
S10 fails: assert [] == ['FAIL  ollama...']
S11 fails: FAIL not pulled vs ok digest
