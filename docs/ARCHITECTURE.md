# Architecture

ResearchWitness separates untrusted discovery and source interpretation from
bounded deterministic verification. [PROJECT_STATUS.md](PROJECT_STATUS.md) says
what is integrated; [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) says what is planned.
[AGENTS.md](../AGENTS.md) governs implementation, not the mathematical verdict.

## Current implementation

```text
source / paper
    -> research agent: claim, source/version, proposed witness, objections
    -> intake.py: bounded reads, byte anchors, canonical witness and manifest
    -> private evidence bundle
    -> capsule.py + checkers.py: bounded deterministic verification
    -> product.py: JSON/HTML presentation, readiness and local inquiry draft
```

The trusted verification path is deliberately small: `strict.py`, `arithmetic.py`,
`checkers.py` and `capsule.py`. It contains no network client, LLM, optimizer,
arbitrary source-code execution or paper-code runner. It evaluates only supported
structured inputs under explicit work budgets.

`intake.py` prepares bundles; it is not a source-authentication authority. Quote
positions are zero-based byte offsets into supplied source bytes, not character
indices. Its metadata, path and aggregate artifact validation must stay consistent
with verification/export. `product.py` formats results and applies workflow policy
without changing the mathematical verdict.

## Rich source-bound JATS table projection (RW-01D)

The installed JATS audit can optionally emit a typed PaperDocument table model
using the unchanged original-byte parser. It records header identity, spans,
footnotes, raw numeric lexemes and detector denominator proposals. Population,
method and result applicability remain unknown without independent source
evidence. See [source model contract](JATS_TABLE_PROJECTION.md).

## Installed core and source-checkout tools

The wheel installs `researchwitness*`, packaged schemas and capability data with
no external runtime dependencies. `tools/` runs from a checkout after
`python -m pip install -e '.[dev]'`; schema validation uses `jsonschema`.

- `tools.research_audit` provides bounded JATS/PDF reports and source-bound comparisons.
  Findings stay unreviewed candidates; integrity is not source authenticity.
- JATS aids retain operands, groups and anchors. Unsupported weighting/missingness
  or denominator scope requires abstention; conditionals do not assert a guess.
- Metadata discovery is networked but separately restricted by managed proxy,
  host/rate/redirect controls. Windows ACL ownership is not yet qualified.
- PDF extraction needs a reviewed pinned image and real Docker isolation evidence.
  No host Poppler fallback exists. Mock tests do not qualify the runtime boundary.

The separate #6-#12 stack is not installed merely because #13 merged. RW-01 must
reconcile its `paper_audit` architecture and tests; #12 custody needs a separate
security/authority review. See [OFFLINE_RESEARCH_AUDIT.md](OFFLINE_RESEARCH_AUDIT.md)
and [SECURITY.md](../SECURITY.md).

## Target architecture - planned, not implemented

```text
permitted acquisition -> immutable source/version evidence
    -> source adapters + candidate claim compiler (untrusted proposals)
    -> competing interpretations + bounded witness search (untrusted proposals)
    -> explicit intake / certificate contract
    -> small offline deterministic verifier
    -> source-correspondence review + scoped evidence report
```

A separate benchmark/custody plane freezes versions, holds labels, controls exposure
and evaluates the stages. It must not share protected identities with development
agents. The coordinator controls tasks and receipts, not scientific truth. Reuse
existing adapters/contracts; add no monolithic multi-agent platform to the core.

Keep three fields of judgment distinct: certificate validity, source correspondence,
and scientific/empirical applicability. Existing report semantics remain unchanged
until an explicitly versioned implementation is reviewed. `paper_error_established`
must not turn true because two agents agree or an experiment returned a number.

## Verifier plugins

`checkers.KINDS` is the allowlist. Every checker needs bounded structured input,
deterministic semantics, explicit proof scope/exclusions, resource limits and
rejection of unsupported inputs. No case-supplied code may be imported or executed.

Finite-field and finite-PMF engines are exact bounded checks, not an AI judge.
A finite PMF does not validate an empirical population. A rational AST is evaluated
at a supplied point, not proved globally. A modular certificate checks the encoded
system, not its interpretation. [PROTOCOL.md](PROTOCOL.md), [EXPRESSION_DSL.md](EXPRESSION_DSL.md)
and runtime `capabilities` define the actual contracts. New solver/proof-assistant
adapters remain outside the core unless separately justified and bounded.

## Runtime, agent authority and contact semantics

Exit 0 means evaluation completed; it can report `NO_REFUTATION_AT_WITNESS`.
Inspect verdict, source correspondence and readiness separately. The legacy
`READY_FOR_USER_REVIEW` string is a draft-readiness result, not permission to send.
Known corrections, unsupported capture, stale evidence and objections still block
readiness. A local inquiry draft can be prepared autonomously; sending remains
outside scope and requires a separate safety decision. No runtime flag grants it.

AI agents can review engineering and source-supported arithmetic without routine
human approval. This is not an independent human audit, actual custody isolation,
security certification or proof of scientific applicability. Keep evidence of
those distinct properties separate from task completion.
