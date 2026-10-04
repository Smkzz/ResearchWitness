## Summary

Describe the change and the problem it solves.

## Verification

- [ ] `python -m pytest -q`
- [ ] `python benchmarks/run_synthetic.py`
- [ ] `python validation/mvp_real/run_validation.py`
- [ ] `python tools/quality_gate.py` (required for trusted-core / release-path changes)

## Scope / safety

- [ ] The change does not turn agent judgment into a trusted-core proof primitive.
- [ ] Positive-result wording is narrow and states what is *not* proved.
- [ ] New or changed verifier work is explicitly bounded.
- [ ] No private paper data, credentials, correspondence, or private QEH evidence is included.
- [ ] Documentation and validation assets were updated where behavior changed.
