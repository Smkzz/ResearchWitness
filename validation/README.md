# Validation assets

- `screening-15.json` — frozen 15-corrigendum coverage screen created before the MVP verifier expansion.
- `mvp_real/` — executable end-to-end MVP replay cases for the elliptic-curve and modular fixed-point corrigenda.

The historical screen is intentionally kept frozen so verifier coverage can be compared without changing the corpus after implementation.

After the 0.2.0 MVP expansion, the qualitative screen is:

- fully/faithfully encoded mechanism: **2/15** (network reliability, elliptic curve);
- important mechanism or theorem conclusion encoded but not all premises: **2/15** (QTT-Tucker, modular fixed point);
- partial only: **1/15** (log-concavity);
- unsupported: **10/15**.

These categories are coverage labels, not accuracy estimates. ResearchWitness still needs more verifier families before it can be described as broadly applicable to mathematical corrigenda.
