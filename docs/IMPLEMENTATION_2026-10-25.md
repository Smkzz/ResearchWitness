# Source-bound execution implementation - 2026-10-25

Plan `RW-PLAN-2026-10-24`; input main
`b2d4863d28e037d35bd8052997e6b02318977771` (PR #20).
This records RW-01B/RW-04B slices, not full completion of RW-01/RW-04.
Exact candidate, merge and hosted CI receipts belong to the containing PR.
No future check result is asserted here.

## Implemented behavior

Preserved the canonical `paper_document.py` model byte-for-byte from PR #11
(blob `4a000cb423de3d45811f64ed942b0d9425f373ef`). Added a bridge from the current
main JATS detector to source anchors and numeric assertions, retaining original
XML element byte ranges, complete normalized quotes, unknown context, denominator
rules, abstentions and conditional calculations. Component and relation identities
are separate. Exact Fraction/integer rounding replay is not an AI judgment.

Added a fixed registered execution path and a runnable entirely synthetic example.
Registration precedes source access; code is copied into a committed private snapshot;
labels and targets do not enter the worker; outputs/time are bounded; all scheduled
works receive receipts or remain recoverably interrupted. Failed certificates and
invalid siblings cannot erase known negative-case alarms. Recovery is read-only,
checks artifact/journal/registration bindings and never retries a hidden experiment.
See [JATS_DEVELOPMENT_RUNNER.md](JATS_DEVELOPMENT_RUNNER.md) for commands and limits.

The existing receipt scorer and JATS detector are reused unchanged. No legacy
normalizing parser, PDF worker, custody worker, frozen corpus, checker family,
provider call, workflow change, permissions or paid service is introduced.
A full installed source-to-report product and full rich table-model consolidation
remain outstanding; this path is a checkout-only development tool.

## Review and validation modality

A separate read-only Codex sub-agent reviewed the supplied design and then supplied
implementation/control-flow excerpts. It did not inspect a current local checkout
or execute the code. Its comments led to distinct component/relation IDs, snapshot
imports, bounded pipes, durable emission accounting, explicit target matching and
interruption-aware recovery. Its requested OS-boundary clarifications are explicit:
this fixed Python worker is not a security sandbox or proof of source authenticity.
This is scoped AI-assisted review, not independent human/scientific certification.

The container could not obtain a full checkout through its network route. Selected
public baseline modules were reconstructed and their Git blob identities checked.
Thirty-nine isolated tests passed locally for arithmetic, model behavior, path rules,
actual subprocess pipe caps/timeouts and environment stripping. Additional integrated
fixtures exercise the actual repository parser/worker/scorer, malformed outputs,
missing targets, conditional scope, interruption and demo CLI in hosted CI. Do not
claim those full-tree tests passed merely from this local checkpoint: inspect the
containing PR's exact-head checks and post-merge main runs.

The baseline source checksum manifest was reconstructed and verified against blob
`30b069201fef58be0722c718f6c52a074a2a4d05` before adding the new/changed paths.
Existing runtime algorithms, schemas and frozen study records are unchanged.

## Remaining work and ownership

RW-01: reconcile rich JATS/table and denominator-provenance contracts, migrate their
source-mapped detector regressions, and expose one documented installed audit path.
Do not mark the whole stack integrated or close legacy PRs based on this bridge.
RW-04: add actual comparative baseline adapters, formal registration schemas,
source-reviewed labels and the predeclared statistical design. This is an engineering
execution demonstration, not evidence of better scientific discovery accuracy.
RW-03 remains blocked on separately qualified real PDF/Windows/custody environments;
no native qualification was attempted or protection weakened in this slice.

The coordinator releases the bounded session claim after delivering this slice;
[EXECUTION_STATE.json](EXECUTION_STATE.json) leaves the next tasks ready and unowned.
No background agent scheduler or new spending authorization was created.
