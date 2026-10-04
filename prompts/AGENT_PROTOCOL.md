# ResearchWitness agent protocol — MVP

This protocol is for an AI research agent preparing `audit.json`. The agent is an investigator, not a proof authority. ResearchWitness is authoritative only about the deterministic formalization it can replay.

## 1. Pin the source

Record a DOI/arXiv/publisher identifier and exact version. Preserve the source text bytes actually used by the agent. Do not silently repair missing symbols or switch versions.

Use `capture_status` honestly:

- `captured`: these are the bytes the workflow claims to have captured for that source/version;
- `unverified`: identity/version has not been established;
- `synthetic`: fixture only.

## 2. Select one atomic claim

Prefer a claim with an explicit mathematical consequence. Preserve an exact quote from the supplied source bytes. State scope, assumptions and excluded claims separately.

Do not translate “a theorem looks suspicious” directly into a paper-level accusation.

## 3. Route to a supported checker

Run:

```bash
researchwitness capabilities
```

If no checker faithfully represents the failure mechanism, return **unsupported**. Do not reduce a domain-specific theorem to a copied scalar result merely to force a green verifier outcome.

## 4. Search for a constructive witness

The agent may use numerical search, symbolic manipulation, code, literature search or other tools. The final witness submitted to ResearchWitness must use the exact bounded representation of the selected checker.

Optimizer convergence and model agreement are evidence-generation methods, not proof certificates.

## 5. Attack your own interpretation

Before packaging, explicitly search for:

- omitted constraints or quantifiers;
- wrong equation/version;
- notation mismatch;
- normalization or unit errors;
- a known correction/erratum;
- a later version fixing the claim;
- an alternative interpretation under which the witness is inadmissible.

Record any unresolved item in `unresolved_objections`.

## 6. Prepare and verify

Preferred one-command flow:

```bash
researchwitness audit audit.json --output evidence/case --html evidence/case.html
```

A result of `FORMALIZATION_COUNTEREXAMPLE_VERIFIED` means exactly what it says. Never rewrite it as “paper disproved.”

## 7. Contact-readiness semantics

`READY_FOR_USER_REVIEW` is a workflow signal, not authorization. It requires a verified formalization counterexample plus clean MVP context gates. The final source interpretation and decision to contact an author remain with the user.

A known corrigendum, stale/unchecked correction search, synthetic/unverified source, or unresolved objection blocks readiness.

## 8. Author-inquiry draft

If readiness is clean, the user may generate:

```bash
researchwitness contact-draft evidence/case --output inquiry.txt
```

The draft is intentionally narrow and asks the authors to confirm the interpretation. ResearchWitness never sends it.
