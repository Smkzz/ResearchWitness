# Fictional source-scope demonstration

This uses the already published synthetic
[JATS denominator fixture](../synthetic-jats/denominator-trace.xml).
It is invented, exposed development data, not a publisher-verified article or
an independently reviewed denominator label. Its three relationships include
a locally indicated base, a direct cell ratio, and a missing-base case.

Compute and externally retain the fixture SHA-256; run the checkout-only
preparation command in
[the protocol](../../docs/DENOMINATOR_SCOPE_REVIEW.md) to generate a
private review-packet envelope. The in-memory test fixtures in
[tests/test_denominator_scope_review.py](../../tests/test_denominator_scope_review.py)
generate two fictional reviewers, disagreeing reviewers, missing data,
copied-record and competing-base cases. No source licence or real reviewer
independence is implied by these demonstrations.

Do not upload any actual licensed paper to this demo directory, and do not
repurpose these test labels as a sealed holdout or a scientific accuracy score.
