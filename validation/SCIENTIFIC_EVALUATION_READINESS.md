> **Historical snapshot — 2026-10-14.** The record below is preserved unchanged.
> Its local branch, missing dependencies and access failures describe that run,
> not the current engineering state. See [project status](../docs/PROJECT_STATUS.md)
> for merged capabilities and the separate, still-unfinished scientific gates.

# Scientific evaluation readiness — 2026-10-14

## Decision

**NOT READY for a scientific evaluation wave.** No Wave 3 was run. This assessment uses public repository state and the latest public aggregate ledger available during this run; it does not inspect or replace the private custodian record.

## Live repository reconciliation

- Local checkout before this work was clean at `main` / `65c814c02ec3e3b8f427ad095986a258470b8f80`, tree `7d84a2bc778f93be9a3e38f873625b18d3a68e4e`.
- PR #12 remains open, draft, and unmerged at `78b26e2d9a31a1eafcc9a0f668b19f09283ce5e9`; its base is PR #11 at `6843593ff443d4a44c48d15a76949b323d0951ca`.
- A fresh read-only GitHub API view confirmed PR #12 is still open/draft/unmerged, with current head `78b26e2d9a31a1eafcc9a0f668b19f09283ce5e9`. Its description reports the current-head CI and CodeQL runs passed; the combined-status endpoint returned no status entries during this check.
- PRs #5–#11 also remain open and draft. The repository release list is empty.
- The new discovery work is isolated on local branch `codex/public-source-discovery`, based on the clean `main` snapshot. It does not modify PR #12, merge a pull request, or start a hosted CI run.

## Gate status

| Gate | Current finding | Status |
|---|---|---|
| Untouched correction-backed positive | The latest public aggregate ledger says no untouched eligible correction-backed positive is confirmed. This run retrieved no new source evidence. | **0 confirmed** |
| Correct negative relationships | The latest public ledger says the required 50 source-verified relationships across 15 independent works are not established. It does not publish a current accepted count. | **Unknown; gate unmet** |
| Independent work diversity | No current accepted family count is public in the ledger. Earlier supplied history reported 363 relationships across five works; that historical relationship count is not independent acceptance evidence. | **Unknown; gate unmet** |
| Candidate discovery this run | Two approved Europe PMC metadata attempts and one separate Crossref request failed before an HTTP response (`MANAGED_PROXY_UNAVAILABLE`, then `TRANSPORT_UNAVAILABLE`). No article, correction, or metadata response was retrieved. | **Blocked; result count unknown** |
| Detector-on-reserved-papers run | None. | **Not run** |
| Blinding and custody | No private custody data, reserved identifiers, or labels were accessed. This cloud agent did not verify the Windows custody bridge or private isolation. | **Not independently verified here** |
| Public security disposition | The latest public aggregate ledger still marks incident disposition and independent security review blocked. | **Open** |
| Wave 3 | Not executed. | **Not run** |

The user-provided historical screen figures (88 candidates, 61 false positives, 15 unrelated arithmetic findings, 12 unresolved) are preserved as historical context only; they were not re-adjudicated in this run. They do not establish current positive or negative gate counts.

## Code and verification work

The read-only Crossref / Europe PMC metadata collector is isolated under `tools/`, outside the trusted `researchwitness` package. It applies the exact approved-host list, requires the inherited HTTPS proxy, fails closed when `NO_PROXY` would bypass it, and rejects cross-host redirects before following them. It caps response sizes, enforces a one-second per-host request-start interval across collector processes using a private per-user directory and permission-checked state file, does not retry denials, and hashes returned metadata responses. Malformed provider payloads retain their response hash and byte count with an unknown record count; they cannot become successful zero-result searches. DOI, PMCID, and PMID overlaps are deduplicated conservatively, while conflicting DOI aliases and ambiguous identifierless rows remain unresolved with record provenance preserved. The registry validator and JSON Schema both reject a `reproduced` relationship without numeric scope fields and captured, hashed original-source evidence; correction candidates also require explicit corrected values and captured, hashed correction-source evidence. Every discovered candidate stays developer-exposed and holdout-ineligible. Percentage recomputation remains arithmetic only.

- The offline adversarial suite in `tests/test_public_discovery_unittest.py` passes **29 tests** using synthetic responses. It covers proxy routing and bypass, redirect rejection, malformed and deeply nested responses, CLI failure recording, identifier conflicts and ambiguous aliases, shared request spacing and private state permissions, source-capture requirements for reproduced claims, provenance, registry consistency, and percentage boundaries.
- `compileall`, JSON parsing, CLI registry summarization, and JSON Schema Draft 2020-12 validation succeeded for the recorded blocked registry and a synthetic completed registry.
- The existing full pytest suite remains unavailable in this runtime (`No module named pytest`). No dependencies were installed because the managed network route was unavailable.
- `validation/public-candidate-registry.json` records two approved Europe PMC attempts and one Crossref request as transport failures before an HTTP response, with candidate count unknown. Request URLs are retained where available. No further source request was made after both provider routes failed. `docs/SCIENTIFIC_CANDIDATE_REVIEW.md` contains the reviewer workflow.
- No scientific detector was tuned: no article or correction response was retrieved, so the run produced no source-grounded detector failure to correct. Synthetic checks establish engineering behavior only.

## Shortest defensible next action

Restore the approved managed proxy route for the already authorized public hosts, then rerun the metadata search from this branch. Have an independent reviewer verify any returned original/correction source pair and denominator scope. The independent custodian must separately report sanitized v1.3 acceptance aggregates; public discovery candidates are developer-exposed and cannot supply untouched holdout cases.
