# Invented source-capture/lineage demonstration

RW-01K's regressions use the already committed fictional
[denominator JATS fixture](../synthetic-jats/denominator-trace.xml). They
construct metadata for four invented source records: an initial article, a
revision/correction and supplement grouped in the same family, plus a
different article family. The test alters original XML bytes for each version.

The [source-capture tests](../../tests/test_source_capture_manifest.py)
check source-hash binding, manifest/replay, non-open rights, explicit exposure,
correction-parent relationships, duplicate/crossfamily content, missing
parents, cycles, chronology, malformed JSON and symlinks. These are software
behavior cases, **not** independently checked real publication histories.

The [protocol](../../docs/SOURCE_CAPTURE_LINEAGE.md) documents how to
capture real source metadata privately. Do not commit actual copyrighted
papers, private acquisition URLs, reviewer records or protected material to
this public example directory.
