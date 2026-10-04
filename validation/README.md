# Validation assets

- `screening-15.json` — frozen 15-corrigendum coverage screen created before the MVP verifier expansion.
- `mvp_real/` — executable end-to-end MVP replay cases for the elliptic-curve and modular fixed-point corrigenda.
- `verifier-wave/screening-15-review.json` — post-wave mechanism-level representability review plus the three committed historical fixture replays.
- `verifier-wave/performance.json` — representative bounded checker timings; not a discovery benchmark.

The historical screen is intentionally kept frozen so verifier coverage can be compared without changing the corpus after implementation.

After the 0.2.0 MVP expansion, the qualitative screen is:

- fully/faithfully encoded mechanism: **2/15** (network reliability, elliptic curve);
- important mechanism or theorem conclusion encoded but not all premises: **2/15** (QTT-Tucker, modular fixed point);
- partial only: **1/15** (log-concavity);
- unsupported: **10/15**.

These categories are coverage labels, not accuracy estimates. ResearchWitness still needs more verifier families before it can be described as broadly applicable to mathematical corrigenda.

The verifier-wave review preserves the original JSON and its SHA-256. It reclassifies the already-supported elliptic and finite-map mechanisms while retaining the overall 2/15 fully representable, 2/15 mechanism-only, 1/15 partial, and 10/15 unsupported counts. Only two unique screen entries have committed runnable fixtures (three fixture runs total). The network-reliability K3 and QTT-Tucker results recorded in older prose have no runnable source bundles or tests in this tree; the review treats them as capability-fit assessments, not fresh reproductions. No sealed holdout is present or claimed.
