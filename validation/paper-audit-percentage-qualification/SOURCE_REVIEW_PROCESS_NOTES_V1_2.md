# Source review process notes, v1.2

The source-first negative labels in this wave were recorded before their
detector-output join. One reviewer later disclosed that, while preparing a
new source-only batch review, they accidentally opened the development
positive-eligibility artifact. It disclosed correction-positive source
mappings and replay observations, but no scored negative-corpus results.
The reviewer stopped before retrieving or opening any source body in the new
batch. No RESERVED body, detector implementation, report, candidate output,
or negative-score artifact was accessed.

The previously completed batch 3/4 source-only review preceded this exposure.
Because no new batch source body had been opened, those source labels were not
revised. The new batch review was reassigned to a reviewer who had not seen the
positive-eligibility artifact; their source review and lock-bound ledger are
reported separately. This process note does not treat the event as evidence
about arithmetic labels.

The batch 7 lock check was also independently repeated using the frozen
canonicalization rule: UTF-8 JSON, sorted keys, compact separators,
`ensure_ascii=False`, and omission of `split_lock_sha256`. The earlier
discrepancy came from checking with Python's default ASCII escaping. Both
batch 6 and batch 7 lock hashes then matched. No source body was opened while
that discrepancy was unresolved.
