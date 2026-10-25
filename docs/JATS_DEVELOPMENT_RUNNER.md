# Registered JATS development execution

**Scope:** RW-01B / RW-04B under [the plan](DEVELOPMENT_PLAN.md). This is an
executable source-to-report development path, not a completed scientific benchmark,
an installed paper-audit product, or a new trusted certificate family.

## Run the synthetic example

From a checkout with the documented development environment, use a fresh output
path whose parent exists:

```text
python -m tools.jats_demo --output-dir work-jats-demo
python -m tools.registered_jats_run recover --run-dir work-jats-demo/run
```

The demonstration writes three explicitly constructed sources and their registry,
protocol, source map and pins, then executes the fixed adapter in subprocesses.
It contains `4/50 = 8.00%`, a printed `8.10%` mismatch, and an unspecified-denominator
case. Expected: one replayed mismatch, one arithmetic match and one abstention.
The execution ledger is complete, but scoring coverage remains incomplete because
of the abstention. These closely related invented examples are not independent
papers or measurements of scientific precision/recall. No network/provider call
is needed. Existing outputs are never overwritten or automatically retried.

## Canonical evidence bridge

`researchwitness/paper_document.py` preserves the immutable upstream model from
PR #11, blob `4a000cb423de3d45811f64ed942b0d9425f373ef`. The new checkout adapter
uses its `SourceAnchor` and `NumericAssertion`; it does **not** claim full migration
of the rich `PaperDocument` table/parser stack.

`tools.jats_source_adapter` wraps the current bounded JATS detector without changing
its denominator or abstention rules. A second bounded parse indexes original XML
elements. Canonical anchors bind source hash, element path, exact original-byte
start/end and the complete normalized element text. The raw range includes XML
markup: it is an **element span**, never a literal quote offset suitable for direct
copying into the verifier's intake quote field. Normalization is the existing
detector's whitespace/block-text rule; component positions index Python Unicode
characters in that normalized string, not original source bytes.

The detector's shorter excerpts are retained separately. Referenced ranges/excerpts,
component positions and numeric operands are checked against the captured source.
A component ID binds source bytes and component position. A separate relation ID
also binds numerator, denominator, scope, denominator evidence and conditional
assumptions. Unknown population, group, outcome, timepoint and adjustment context
remain null. The adapter does not invent them or independently adjudicate them.

Exact Fraction/integer HALF_UP arithmetic is replayed separately from extraction.
A resolved detector result receives an arithmetic replay certificate only when
the expected rounding and verdict agree. A disagreement rejects the certificate
without erasing the detector alarm. Conditional calculations remain conditional;
they do not clear scope/rounding abstentions. Original detector results, all
candidates and ambiguity records remain in the bounded report. This checks supplied
source-mapped operands, not the scientific conclusion or source authenticity.

## Register a development run

The existing [receipt scorer](DEVELOPMENT_RECEIPT_SCORER.md) contracts remain
unchanged. Supply externally held registry/protocol SHA-256 commitments before
outcomes, using the documented sorted compact ASCII JSON plus LF encoding. Hashes
bind bytes and declarations, not trustworthy chronology or scientific truth.

```text
python -m tools.registered_jats_run identity
python -m tools.registered_jats_run run --registry registry.json --protocol protocol.json --sources sources.json --source-root permitted-sources --output-dir new-run --expected-registry-sha256 REGISTRY_HASH --expected-protocol-sha256 PROTOCOL_HASH
```

The uppercase hash tokens are placeholders. The runner's identity command computes
an environment-specific implementation commitment. Include that exact digest in
`protocol.implementation_sha256`; a different code/interpreter environment requires
a deliberately new registration, not silently replacing an existing pin.

The source map is `{"schema_version":"rw-jats-sources.v1","paths":{"work-id":"relative.xml"}}`.
Its keys must exactly match registered works; a null path means unavailable source.
Paths must be portable relative paths under the trusted root. Source bytes must
match each work's registered hash. Each interpretation hash must equal the adapter's
published `interpretation_sha256()` contract. Labels, family classifications and
eligible targets remain separately supplied development assertions.

Only `synthetic` and `developer_exposed` registries are accepted. Cost and provider
call limits must be zero. The runner validates the full registration, source map,
interpretation and actual implementation identity before creating run outputs.
No protected/confirmatory mode, plugin path, arbitrary command or solver is allowed.

## Execution and recording

The complete schedule is fsynced in `registration.json` before source reads.
Each case gets a sequenced, hash-chained `attempt_started` record before reading
its source or starting the worker. The fixed worker receives captured source bytes
only; registered labels/targets are never its inputs. Target matching takes place
after detection and independent arithmetic replay. A different verified finding
cannot stand in for a missing registered target.

Bounded worker output is retained and its alarm declarations journaled before
semantic validation. An invalid sibling, duplicate identity, rejected certificate
or other validation failure does not make a previously emitted negative-case alarm
disappear. Unparseable/truncated output is a failed, incomplete observation, never
a clean negative. Every scheduled work stays in the denominator, including source
failures, timeouts, exclusions and an unattempted budget-exhausted tail. No retries.

`case-NNNN.json` stores the actual bounded report, and the terminal journal record
binds its hash. `summary.json` contains actual receipts and the existing scorer's
qualified result. `finished.json` is written only after all terminal records,
artifact writes, snapshot cleanup and journal closure succeed. Coverage and durable
completion are distinct: a finished run can have incomplete scientific coverage.

Read-only recovery verifies the chain, order, source registration, report hashes
and completion bindings. A partial trailing record is ignored and flagged. Missing
completion markers remain interrupted; an emitted alarm in an unfinished work is
recovered as failed/incomplete evidence without re-execution. This protects against
accidental inconsistency, not a malicious local owner rewriting all artifacts.

## Bounded resources and remaining trust

The fixed limits are 64 works, 8 MiB/source, 64 MiB total captured sources, 4 MiB
stdout and 4 KiB stderr per worker, 32 MiB retained-output envelope (1 MiB reserved
for control records), at most 30 seconds per worker and a 120-second absolute
execution deadline with a 5-second cleanup/finalization reserve. Both output pipes
are capped while produced; overflow/timeout kills and reaps the owned child.
Local OS file I/O and process creation are not hard real-time bounded. No general
memory quota or adversarial process-tree/OS-isolation guarantee is claimed.

The executor copies a static allowlist of actual transitive project code into a
private temporary snapshot. Its identity binds those bytes, Python executable
bytes, version and platform. Worker startup uses `-I -S -B`, controlled imports
and a minimal environment without inherited credentials, proxies or PYTHONPATH.
The interpreter's standard library/DLLs, kernel, process implementation and caller's
quiescent filesystem remain trusted. This is **not an OS security sandbox**, and
none of it qualifies native PDF execution, Windows metadata ACLs or sealed custody.
The worker code has no acquisition/provider operation; it is not granted a claim
of OS-enforced network denial merely because it does not call the network.

For a work with any extracted abstention (or no extracted relationships), this
initial runner conservatively reports `abstained` even when it emitted a candidate.
Negative alarms still count. Positive detection credit can consequently be lower
than relation-level detection; no complete reference relationship census exists.
The unchanged scorer still labels its own inputs as supplied declarations; the
outer execution report adds narrowly scoped source mapping and arithmetic replay,
not independent label/family validation. Frozen statistical design, comparison
adapters, scientific curation and sealed evaluation remain outstanding.
