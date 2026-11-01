# Synthetic source claim examples

These deliberately constructed examples demonstrate the narrow
[RW-MATH-02 grammar](../../docs/SOURCE_CLAIM_COMPILER.md). They are not copied
from research articles or presented as new scientific findings.

- `bilinear.txt` + `bilinear-hints.json`: the source-block claim that
  `max xy <= 1/4` with `x+y=1`, using an explicit product variable.
- `linear.txt` + `linear-hints.json`: `max (3x+2y+5) <=11` on the stated
  bounded-real allocation domain; the source includes all exact assumptions.
- `refutable.txt` + `refutable-point.json`: deliberately false upper bound
  `max x <= 1/2` for `0<=x<=1` with exact feasible point `x=1`.
- `unsupported.txt`: unmarked, approximately weighted prose. The v1 compiler
  refuses to infer its missing weighting and tolerance assumptions.

The source compiler requires an externally retained exact source SHA-256 pin.
Use `sha256sum` or `Get-FileHash` to calculate the intended file's bytes and
retain the digest separately; never treat a hash inside a supplied bundle as a
publisher or rights attestation. See the linked documentation for `compile`,
`verify` and `refute` usage.
