# RW-01S: conditional JATS section denominator proposals (development only)

**Status:** New optional, offline *hypothesis* detector; not part of `audit-jats`
by default and never changes an existing finding, score or replay. This is a
post-exposure implementation motivated by the 28 October 2026 J-EINSTEIN result.
The baseline source-derived experiment and its zero optional gain remain frozen.

## Problem and narrow response

A JATS table can include several population subgroups, each introduced by a row
whose first cell names a population and whose remaining cells explicitly print
`N = ...`. Earlier static column headers may belong to a different population.
In J-EINSTEIN Table 3, an old combined-group header says `N = 43` while the
later `DVT and PE patients` subsection says `N = 71`. The existing percentage
auditor abstained; it did not apply the local section denominator to the cell
`2 (2.9)` labeled `Unchanged, n (%)`.

`researchwitness.jats_section_proposals` uses the same bounded, entity-rejecting,
original-byte-anchored JATS parser and exact percentage arithmetic as the
installed audit, but produces a **separate conditional-review report**.
For a rectangular, unsupported-span-free table, it requires an explicit
multi-column population section row (`DVT and PE patients | N = 20 | N = 51 |
N = 71 | N = 19`, for example) and a later row explicitly marked `n (%)`.
It does not infer a denominator from arbitrary nearby values, scientific
context, a computed match or a previous table. A malformed section row, mixed
cell spans, adjusted percentages, or a rounding notice leads to exclusion or
abstention. Both the printed section and any competing old header Ns are kept
with source element byte spans.

**Output:** `conditional_match` or `conditional_mismatch`, expressly conditional
on the printed section N being the applicable base. The system does not prove
that assumption. There is no automatic promotion to a scientific error,
publication correction, benchmark success, human adjudication or author contact.
The source origin and licensed version are not authenticated by a checksum.

## Run without network, retaining an external source hash

```sh
python -m researchwitness.jats_section_proposals PATH/TO/EXISTING.xml \
  --expected-source-sha256 YOUR_EXTERNALLY_RECORDED_SOURCE_SHA256 > PRIVATE-output.json
```

The CLI reads only the pinned regular file, writes nothing itself, fetches
nothing, and fails closed on a mismatched pin, XML declaration/entity, or
source/parser limit. Protect the output and full text according to source rights.
The module is a source-analysis aid, **not** part of the trusted mathematical
verification core. It is not enabled in the main `audit-jats` CLI or its signed
bundle replay; its output is separate, and independent scientific review is
still required.

## Retrospective, exposed developmental check — 2026-10-28

The module was run locally against the *already exposed* `provider_rendered_pre_text_utf8`
Europe PMC display derivatives, not historical or raw HTTP response originals.
This test occurred after inspection of the paper and known correction.

| Source-derived article | SHA-256 prefix | Sections | Conditional pairs | Conditional mismatches |
|---|---|---:|---:|---:|
| J-EINSTEIN, PMC4339301 | `4bc9c4672fbf` | 2 | 21 | **1** |
| Vitiligo, PMC11845954 | `594ea878750c` | 0 | 0 | **0** |

The one J-EINSTEIN proposal is Table 3 `2 (2.9)` conditional on section
`N = 71`: rounded arithmetic is **2.8%**, corresponding to the already
published correction. The static competing N=43 remains visible in evidence.
This is a known-case recovery, not a new independent discovery. The installed
percentage audit and the frozen two-arm results were not
changed. The other 20 conditional relationships in this example matched their
section denominators at printed precision; they are not proof of full-table
coverage or of scientifically correct denominators.

For source context, see:
- [J-EINSTEIN primary article](https://pmc.ncbi.nlm.nih.gov/articles/PMC4339301/)
- [Published correction](https://link.springer.com/article/10.1186/s12959-016-0085-1)
- [Frozen prior diagnostic](REAL_SOURCE_ACQUISITION_2026-10-28.md)

## Qualification and next experimental gate

Synthetic tests cover competing old headers, switching sections, invalid
population headers, malformed sections, unsupported cell spans, adjusted or
rounded material, unsupported XML, input SHA mismatch, and local file symlinks.
They demonstrate intended engineering behavior, not scientific accuracy.

Future work must acquire and license authentic original research sources,
preselect genuinely untouched work families, and obtain independently
adjudicated denominator/scope labels. Prespecify source inclusion,
negative-family harms and review rules before evaluation. Do **not** count
this exposed paper or its published correction in a sealed confirmatory set.
No historical original recovery (`0/13`), original PMC response receipt,
independent evaluation or superiority claim is resolved by this module.
