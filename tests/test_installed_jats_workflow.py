"""End-to-end installed JATS source audit and integrity contracts."""
from __future__ import annotations

from decimal import DefaultContext, Inexact
import json
from pathlib import Path
import subprocess
import sys
from unittest import mock

import pytest

from researchwitness import _jats_parser, jats_product
from researchwitness._jats_math import percentage_recalculation

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "examples/synthetic-jats/article.xml"


def cli(*args: str, cwd: Path = ROOT):
    return subprocess.run([sys.executable, "-m", "researchwitness", *map(str, args)],
                          cwd=cwd, capture_output=True, text=True, timeout=40, check=False)


def test_source_to_review_and_replay(tmp_path):
    output = tmp_path / "review"
    run = cli("audit-jats", SYNTHETIC, "--output-dir", output, "--document-id", "synthetic")
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["summary"] == {
        "arithmetic_matches": 1, "mismatch_candidates": 1, "abstentions": 1,
    }
    report = json.loads((output / "report.json").read_bytes())
    assert report["paper_error_established"] is False
    assert report["external_actions"] == "OUT_OF_SCOPE"
    assert all(f["review_state"] == "unreviewed" for f in report["findings"])
    verify = cli("replay-jats", output, "--expected-manifest-sha256", data["manifest_sha256"])
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["findings_replayed"] == 3


def test_cli_from_non_checkout_directory(tmp_path):
    result = cli("audit-jats", SYNTHETIC, "--output-dir", tmp_path / "review",
                 "--document-id", "synthetic", cwd=tmp_path)
    assert result.returncode == 0, result.stderr


def test_expected_source_hash_rejected_before_output(tmp_path):
    output = tmp_path / "review"
    result = cli("audit-jats", SYNTHETIC, "--output-dir", output,
                 "--document-id", "synthetic", "--expected-source-sha256", "f" * 64)
    assert result.returncode == 2
    assert not output.exists()


@pytest.mark.parametrize("name", ["source.xml", "report.json", "report.html", "manifest.json"])
def test_tampered_payload_fails_replay(tmp_path, name):
    output = tmp_path / "review"
    jats_product.audit_source(SYNTHETIC, output, "synthetic")
    (output / name).write_bytes((output / name).read_bytes() + b"tamper")
    with pytest.raises(ValueError):
        jats_product.replay_bundle(output)


def test_external_manifest_pin(tmp_path):
    output = tmp_path / "review"
    jats_product.audit_source(SYNTHETIC, output, "synthetic")
    with pytest.raises(ValueError):
        jats_product.replay_bundle(output, "f" * 64)


def test_no_output_overwrite(tmp_path):
    output = tmp_path / "review"
    jats_product.audit_source(SYNTHETIC, output, "synthetic")
    before = (output / "report.json").read_bytes()
    with pytest.raises(ValueError):
        jats_product.audit_source(SYNTHETIC, output, "synthetic")
    assert (output / "report.json").read_bytes() == before


def test_independent_decimal_context():
    saved = DefaultContext.copy()
    try:
        DefaultContext.prec = 3
        DefaultContext.traps[Inexact] = True
        assert percentage_recalculation(4, 50, "8.00", 2)["arithmetic_matches"]
        assert not percentage_recalculation(4, 50, "8.10", 2)["arithmetic_matches"]
    finally:
        DefaultContext.prec = saved.prec
        DefaultContext.traps = saved.traps.copy()


def test_legacy_module_is_aliased_for_monkeypatch():
    import tools.jats_percentage_audit as legacy
    assert legacy is _jats_parser
    with mock.patch("tools.jats_percentage_audit._text", wraps=_jats_parser._text) as spy:
        legacy.audit_jats_percentage_tables(SYNTHETIC.read_bytes())
        assert spy.call_count > 0


def test_legacy_direct_invocation():
    result = subprocess.run([sys.executable, "-m", "tools.jats_percentage_audit",
                             str(SYNTHETIC)], cwd=ROOT, capture_output=True,
                            text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["percentage_cells_reviewed"] == 3


def test_source_symlink_rejected(tmp_path):
    link = tmp_path / "linked.xml"
    try:
        link.symlink_to(SYNTHETIC)
    except (OSError, NotImplementedError):
        pytest.skip("No symlink support")
    with pytest.raises((ValueError, OSError)):
        jats_product.audit_source(link, tmp_path / "result", "synthetic")


def test_duplicate_manifest_key_rejected(tmp_path):
    root = tmp_path / "review"
    jats_product.audit_source(SYNTHETIC, root, "synthetic")
    manifest = root / "manifest.json"
    manifest.write_bytes(manifest.read_bytes().replace(
        b'"document_id":', b'"document_id": "duplicate", "document_id":', 1))
    with pytest.raises(ValueError):
        jats_product.replay_bundle(root)


def test_html_escapes_untrusted_text(tmp_path):
    source = tmp_path / "source.xml"
    source.write_text(
        "<article><body><table-wrap id='t'><caption>N=50</caption>"
        "<table><tbody><tr><td>&lt;script&gt;4 (8.10%)&lt;/script&gt;</td>"
        "</tr></tbody></table></table-wrap></body></article>",
        encoding="utf-8",
    )
    root = tmp_path / "review"
    jats_product.audit_source(source, root, "synthetic")
    assert "<script>" not in (root / "report.html").read_text(encoding="utf-8")


def test_source_with_external_entity_fails_closed(tmp_path):
    source = tmp_path / "source.xml"
    source.write_bytes(b'<!DOCTYPE a [ <!ENTITY x SYSTEM "file:///etc/passwd"> ]><article>&x;</article>')
    root = tmp_path / "review"
    with pytest.raises(ValueError):
        jats_product.audit_source(source, root, "synthetic")
    assert not root.exists()
