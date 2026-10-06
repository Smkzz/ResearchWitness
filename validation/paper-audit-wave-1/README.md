# Paper-audit development wave 1

This is a small, source-pinned development set for the `paper-audit` screens. It is intended to find implementation failures and false-positive mechanisms. The labels and corrections were visible during development, so this is **not** a blind benchmark or holdout.

## Corpus

`cases.json` records nine original papers retrieved from Europe PMC `fullTextXML` on 2026-10-05, exact SHA-256 hashes, DOI/PMCID, article title/authors/journal, license metadata, and the chosen benchmark role.

- Four `development_positive` cases have published corrections with arithmetic or flow changes.
- Five `development_negative` cases were chosen for legitimate changes in cohort, stage, repeated-measure, and row-denominator scope. A targeted correction search surfaced no corresponding correction for these controls; that search is not proof no correction exists.
- The weekly and daily Egilsson studies are related and should not be treated as independent evidence.
- The Spittal correction identifies an annualization error in adjusted rates. The source paper does not provide enough information to reproduce that adjustment, so the current screens are expected to leave it unsupported.

Full papers and PDFs are not committed. `ATTRIBUTION.md` provides citations and source-license notes. The manifest also pins three open correction notices and records the fourth correction notice as metadata/hash only because the captured JATS license says “CC-BY License” without specifying a version. JSON results preserve short source anchors; they do not contain full paper text.

## Reproduce

The fetcher writes source XML to a temporary cache and refuses to write a download whose bytes do not match the pinned hash. Network access is needed only when a source snapshot is missing:

```bash
python tools/fetch_paper_audit_wave.py \
  --cache /tmp/researchwitness-paper-audit-wave-1 \
  --download --include-corrections
```

Then run the actual CLI twice per paper and save the compact reports/metrics:

```bash
python tools/run_paper_audit_wave.py \
  --source-dir /tmp/researchwitness-paper-audit-wave-1 \
  --output /tmp/researchwitness-paper-audit-wave-1-results
```

The runner checks each source hash, renders JATS deterministically with `tools/render_pmc_jats.py`, invokes `python -m researchwitness paper-audit`, validates each report against the published schema, compares JSON and HTML output across two runs, and keeps only `report.json` plus a per-case evaluation record. Its temporary working directories, Markdown captures, and HTML outputs are removed after the run.

The checked-in `results/` directory contains the run used in the validation report. Re-running the corpus does not mutate those results; choose a new empty output directory.

## Scoring rules

The metrics are applied at candidate-item and paper levels:

1. A positive issue is rediscovered only when all expected target values/operands appear in a candidate of the expected type.
2. Candidate precision counts each surfaced candidate item that maps to the stated published correction. The vitiligo correction affects two table cells, so it contributes two candidate items from one correction-backed issue.
3. A negative-control paper is a false-positive paper if any candidate is emitted. False-positive candidates per paper is the total candidate count over the five selected controls divided by five.
4. Scope/denominator notes are reported separately; they are not counted as candidates or error findings. Their own precision was not systematically scored.
5. An unsupported positive is a correction-backed issue that none of the current screens can recompute from the original paper. Spittal is one such case.
6. A reproducible arithmetic result is not automatically a verified paper error. This wave promotes zero candidates to `verified_findings`.
7. Repeatability compares the exact JSON and HTML report bytes for two CLI runs over the same rendered Markdown source.

These rules were taken from the development task, but no timestamped preregistration was made before source selection or baseline inspection. Report the values as exploratory.

## Results

| Metric | Result |
|---|---:|
| Positive cases | 4 |
| Correction-backed issues rediscovered | 3/4 (75%) |
| Candidate items | 4 |
| Candidate items matching correction targets | 4/4 |
| Candidate precision on this selected set | 100% |
| Negative controls | 5 |
| Negative-control papers with candidates | 0/5 |
| False-positive candidates per negative paper | 0.00 |
| Possible scope/denominator notes | 17 |
| Positive issues unsupported by current screens | 1/4 (25%) |
| Candidates promoted to verified paper errors | 0 |
| Repeated runs with byte-identical JSON and HTML | 9/9 |
| Markdown/JATS input extraction failures | 0/9 |
| Sealed holdout | Not run |

The pre-wave marker-only detector rediscovered none of the four correction-backed issues and emitted candidates on all five selected negative controls. The current screens detect J-EINSTEIN's 2/71 percentage, the depressive-symptoms exclusion-flow arithmetic mismatch, and two corrected vitiligo percentages. They do not reconstruct the Spittal adjusted-rate annualization. The current set supports only the claim that these three chosen mechanisms are representable and that the five selected controls did not produce candidates under this exact rendered-text pipeline.

## Boundaries

- All reports keep `paper_error_established: false` and `verified_findings: []`.
- The positives were discovered through public corrections and then used for detector iteration; they are development data.
- The controls are selected clinical papers, not random samples or certified error-free publications.
- Four of five controls have one or more possible-scope notes, but those notes have not been exhaustively adjudicated.
- All inputs to the corpus runner are deterministic JATS-derived Markdown. This does not measure PDF extraction accuracy on real publisher PDFs.
- The 15-paper verifier representability screen is a separate historic artifact, not this paper-audit corpus.
- No result here estimates arbitrary-paper correctness, misconduct, researcher quality, or general cross-disciplinary precision/recall.
