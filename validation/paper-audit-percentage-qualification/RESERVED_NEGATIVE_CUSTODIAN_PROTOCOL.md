# Reserved negative source-only custody protocol

Status: frozen before assigning any source from the metadata expansion batches.

This protocol may be used only to estimate whether a future reserved negative
pool has enough source-first eligible correct relations. It does not authorize
running ResearchWitness on reserved documents in this wave.

1. Apply the frozen DOI hash split to the complete metadata batch before
   retrieving any article body. A source assigned `RESERVED` is never moved.
2. A separate source-only custodian may retrieve the original JATS bytes and
   review all reserved sources in metadata order. The custodian receives no
   detector code, DEVELOPMENT replay, or report outputs.
3. The custodian may determine relation eligibility and arithmetic truth
   directly from each pinned source. The custodian must not run ResearchWitness
   or join any detector result to a reserved source or relation.
4. Keep the source files and relation-level labels in a separate private
   directory that is never passed to the development runner. Hash-bind the
   complete source-only record. Return only the aggregate counts of correct
   eligible relations, tables, and documents, the record SHA-256, and whether
   the source-only review is complete. Do not return relation IDs, anchors,
   operands, reported values, or document identifiers.
5. If the custodian cannot keep reserved source evidence outside all runner
   inputs, do not retrieve those bodies and report the reserve pool as
   unqualified.

This yields a sealed source-only reserve capacity estimate, not an evaluation
result. No reserved detector output is inspected or scored in this wave.
