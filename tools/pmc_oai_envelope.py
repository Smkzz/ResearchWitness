"""Offline PMC GetRecord envelope-to-JATS derivation with exact byte provenance.

Developer-exposed inputs only. A response file and transfer record are supplied
by the operator; this module never acquires content or authenticates provenance,
licences, provider status, timestamps, research labels or reviewer independence.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re
import sys
from typing import Any
from xml.parsers import expat
from xml.sax.saxutils import quoteattr

from researchwitness import _jats_parser as jats
from tools import source_capture_manifest as capture
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

TRANSFER_VERSION = "rw-pmc-oai-transfer-declaration.v1"
RECEIPT_VERSION = "rw-pmc-oai-derivation.v1"
PROFILE = "getrecord-exact-article-span-namespace-injection.v1"
ENDPOINT = "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
OAI = "http://www.openarchives.org/OAI/2.0/}"
XINCLUDE = "http://www.w3.org/2001/XInclude}"
MAX_ENVELOPE_BYTES = jats.MAX_SOURCE_BYTES + 2 * 1024 * 1024
MAX_TRANSFER_BYTES = 32 * 1024
MAX_RECEIPT_BYTES = 32 * 1024
MAX_NODES = jats.MAX_XML_NODES
MAX_DEPTH = jats.MAX_XML_DEPTH
OAI_ID = re.compile(r"oai:pubmedcentral\.nih\.gov:([1-9][0-9]{0,11})\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
DECLARATION = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.I)
LICENCE_HREF = {
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
}


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    start: int
    tag_end: int
    end: int = 0
    parent: "Node | None" = field(default=None, repr=False)
    children: list["Node"] = field(default_factory=list)
    parts: list["str | Node"] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)
    local_ns: set[str] = field(default_factory=set)


def require(ok: bool, code: str) -> None:
    vb.require(ok, code)


def one(nodes: list[Node], code: str) -> Node:
    require(len(nodes) == 1, code)
    return nodes[0]


def children(node: Node, name: str) -> list[Node]:
    return [child for child in node.children if child.tag == name]


def text_only(node: Node, code: str) -> str:
    require(all(isinstance(part, str) for part in node.parts), code)
    return "".join(node.parts).strip()


def parse_envelope(raw: bytes) -> Node:
    require(type(raw) is bytes and 0 < len(raw) <= MAX_ENVELOPE_BYTES,
            "ENVELOPE_BYTE_LIMIT")
    require(b"\x00" not in raw and not raw.startswith((b"\xff\xfe", b"\xfe\xff")),
            "ENVELOPE_NOT_UTF8")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise vb.BenchmarkError("ENVELOPE_NOT_UTF8") from exc
    require(DECLARATION.search(raw) is None, "ENVELOPE_DTD_OR_ENTITY")
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    stack: list[Node] = []
    pending_ns: dict[str, str | None] = {}
    roots: list[Node] = []
    count = 0

    def reject(*_args: Any) -> None:
        raise vb.BenchmarkError("ENVELOPE_UNSUPPORTED_XML_CONSTRUCT")

    def namespace(prefix: str | None, uri: str | None) -> None:
        pending_ns[prefix or ""] = uri

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal count
        count += 1
        require(count <= MAX_NODES, "ENVELOPE_NODE_LIMIT")
        require(len(stack) < MAX_DEPTH, "ENVELOPE_DEPTH_LIMIT")
        require(not name.startswith(XINCLUDE), "ENVELOPE_XINCLUDE_FORBIDDEN")
        inherited = stack[-1].namespaces.copy() if stack else {}
        for prefix, uri in pending_ns.items():
            if uri is None:
                inherited.pop(prefix, None)
            else:
                inherited[prefix] = uri
        index = parser.CurrentByteIndex
        node = Node(name, dict(attrs), index, jats._tag_end(raw, index),
                    parent=stack[-1] if stack else None,
                    namespaces=inherited, local_ns=set(pending_ns))
        pending_ns.clear()
        if stack:
            stack[-1].children.append(node)
            stack[-1].parts.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def end(_name: str) -> None:
        node = stack.pop()
        index = parser.CurrentByteIndex
        node.end = (jats._tag_end(raw, index) if raw[index:index + 2] == b"</"
                    else node.tag_end)

    def character(value: str) -> None:
        if stack:
            stack[-1].parts.append(value)

    parser.StartNamespaceDeclHandler = namespace
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = character
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ProcessingInstructionHandler = reject
    parser.ExternalEntityRefHandler = lambda *_args: 0
    try:
        parser.Parse(raw, True)
    except vb.BenchmarkError:
        raise
    except (expat.ExpatError, jats.JATSSourceError) as exc:
        raise vb.BenchmarkError("ENVELOPE_MALFORMED_XML") from exc
    require(not stack and len(roots) == 1, "ENVELOPE_ROOT_COUNT")
    root = roots[0]
    require(root.tag == OAI + "OAI-PMH", "ENVELOPE_NOT_OAI_PMH")
    return root


def validate_transfer(transfer: dict[str, Any], raw: bytes) -> str:
    capture.fields(transfer, "schema_version endpoint verb metadata_prefix requested_identifier "
                             "http_status body_stage expected_body_sha256 captured_at_utc "
                             "provider_response_id declared_license_id rights_evidence_uri",
                   "TRANSFER_FIELDS")
    require(transfer["schema_version"] == TRANSFER_VERSION, "TRANSFER_VERSION")
    require(transfer["endpoint"] == ENDPOINT and transfer["verb"] == "GetRecord"
            and transfer["metadata_prefix"] == "pmc", "TRANSFER_REQUEST")
    requested = transfer["requested_identifier"]
    require(type(requested) is str and OAI_ID.fullmatch(requested) is not None,
            "TRANSFER_IDENTIFIER")
    require(type(transfer["http_status"]) is int and transfer["http_status"] == 200,
            "PROVIDER_RESPONSE_NOT_SUCCESSFUL")
    require(transfer["body_stage"] == "decoded_http_entity", "TRANSFER_BODY_STAGE")
    require(capture.digest(transfer["expected_body_sha256"]) == sha256(raw).hexdigest(),
            "TRANSFER_BODY_HASH_MISMATCH")
    capture.utc_timestamp(transfer["captured_at_utc"])
    response_id = transfer["provider_response_id"]
    require(response_id is None or (type(response_id) is str
            and SAFE_ID.fullmatch(response_id) is not None), "PROVIDER_RESPONSE_ID")
    license_id = transfer["declared_license_id"]
    require(type(license_id) is str and license_id in LICENCE_HREF,
            "TRANSFER_DECLARED_LICENSE")
    capture.https_uri(transfer["rights_evidence_uri"])
    return requested


def _semantic_equal(left: Node, right: jats._Node) -> bool:
    """Compare expanded XML names/attrs and Expat-normalized content, not bytes."""
    todo: list[tuple[Node, jats._Node]] = [(left, right)]
    while todo:
        original, derived = todo.pop()
        if original.tag != derived.tag or original.attrs != derived.attrs:
            return False
        def normalized(parts: list[str | Any]) -> list[str | Any]:
            items: list[str | Any] = []
            for part in parts:
                if isinstance(part, str):
                    if items and isinstance(items[-1], str):
                        items[-1] += part
                    else:
                        items.append(part)
                else:
                    items.append(part)
            return items
        a, b = normalized(original.parts), normalized(derived.parts)
        if len(a) != len(b):
            return False
        for old, new in zip(a, b):
            if isinstance(old, str) or isinstance(new, str):
                if type(old) is not str or type(new) is not str or old != new:
                    return False
            else:
                todo.append((old, new))
    return True


def _derive(raw: bytes, article: Node) -> tuple[bytes, int]:
    require(article.tag in ("article", "http://jats.nlm.nih.gov}article"),
            "ARTICLE_NAMESPACE_UNSUPPORTED")
    embedded = raw[article.start:article.end]
    require(embedded and embedded[-1:] == b">" and article.tag_end < article.end,
            "ARTICLE_SPAN_INVALID")
    start_tag = raw[article.start:article.tag_end]
    require(start_tag.endswith(b">") and not start_tag.endswith(b"/>"),
            "ARTICLE_START_TAG_UNSUPPORTED")
    inherited = {p: uri for p, uri in article.namespaces.items()
                 if p not in article.local_ns and p != "xml"}
    injections: list[bytes] = []
    for prefix, uri in sorted(inherited.items()):
        require(prefix == "" or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", prefix)
                is not None, "INHERITED_NAMESPACE_PREFIX_UNSUPPORTED")
        name = "xmlns" + (":" + prefix if prefix else "")
        injections.append((" " + name + "=" + quoteattr(uri)).encode("utf-8"))
    result = (start_tag[:-1] + b"".join(injections) + b">"
              + raw[article.tag_end:article.end])
    require(len(result) <= jats.MAX_SOURCE_BYTES, "DERIVED_SOURCE_BYTE_LIMIT")
    try:
        reparsed = jats._parse_jats(result)
    except ValueError as exc:
        raise vb.BenchmarkError("DERIVED_JATS_NOT_SUPPORTED") from exc
    require(_semantic_equal(article, reparsed), "DERIVED_JATS_SEMANTICS_CHANGED")
    return result, len(injections)


def derive(raw: bytes, transfer: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    requested = validate_transfer(transfer, raw)
    root = parse_envelope(raw)
    response_date = text_only(one(children(root, OAI + "responseDate"),
                                  "RESPONSE_DATE_COUNT"), "RESPONSE_DATE_NOT_TEXT")
    capture.utc_timestamp(response_date)
    request = one(children(root, OAI + "request"), "OAI_REQUEST_COUNT")
    require(request.attrs == {"verb": "GetRecord", "metadataPrefix": "pmc",
                               "identifier": requested}, "OAI_REQUEST_MISMATCH")
    require(text_only(request, "OAI_REQUEST_NOT_TEXT") == ENDPOINT,
            "OAI_ENDPOINT_MISMATCH")
    require(not children(root, OAI + "error"), "OAI_PROVIDER_ERROR")
    get_record = one(children(root, OAI + "GetRecord"), "OAI_GETRECORD_COUNT")
    record = one(children(get_record, OAI + "record"), "OAI_RECORD_COUNT")
    header = one(children(record, OAI + "header"), "OAI_HEADER_COUNT")
    require("status" not in header.attrs, "OAI_DELETED_RECORD")
    identifier = text_only(one(children(header, OAI + "identifier"),
                               "OAI_IDENTIFIER_COUNT"), "OAI_IDENTIFIER_NOT_TEXT")
    require(identifier == requested, "OAI_IDENTIFIER_MISMATCH")
    datestamp = text_only(one(children(header, OAI + "datestamp"),
                              "OAI_DATESTAMP_COUNT"), "OAI_DATESTAMP_NOT_TEXT")
    try:
        stamp_format = "%Y-%m-%dT%H:%M:%SZ" if "T" in datestamp else "%Y-%m-%d"
        parsed_stamp = datetime.strptime(datestamp, stamp_format)
        require(parsed_stamp.strftime(stamp_format) == datestamp, "OAI_DATESTAMP_INVALID")
    except ValueError as exc:
        raise vb.BenchmarkError("OAI_DATESTAMP_INVALID") from exc
    metadata = one(children(record, OAI + "metadata"), "OAI_METADATA_COUNT")
    article = one([c for c in metadata.children if jats._local_name(c.tag) == "article"],
                  "OAI_ARTICLE_COUNT")
    require(len(metadata.children) == 1, "OAI_AMBIGUOUS_METADATA")
    require(article.attrs.get("article-type") in {"research-article", "brief-report"},
            "ARTICLE_KIND_UNSUPPORTED")
    ns = article.tag[:-len("article")]
    front = one(children(article, ns + "front"), "ARTICLE_FRONT_COUNT")
    article_meta = one(children(front, ns + "article-meta"), "ARTICLE_META_COUNT")
    pmc_ids = [x for x in children(article_meta, ns + "article-id")
               if x.attrs.get("pub-id-type") == "pmc"]
    article_id = text_only(one(pmc_ids, "ARTICLE_PMC_ID_COUNT"), "ARTICLE_PMC_ID_NOT_TEXT")
    numeric = OAI_ID.fullmatch(requested).group(1)
    require(article_id in (numeric, "PMC" + numeric), "ARTICLE_PMC_ID_MISMATCH")
    permissions = one(children(article_meta, ns + "permissions"), "ARTICLE_PERMISSIONS_COUNT")
    license_node = one(children(permissions, ns + "license"), "ARTICLE_LICENSE_COUNT")
    href = [value for key, value in license_node.attrs.items()
            if jats._local_name(key) == "href"]
    require(len(href) == 1
            and href[0] == LICENCE_HREF[transfer["declared_license_id"]],
            "ARTICLE_LICENSE_UNCLEAR")
    source, injections = _derive(raw, article)
    span = raw[article.start:article.end]
    receipt = {
        "schema_version": RECEIPT_VERSION,
        "profile": PROFILE,
        "transfer_declaration_sha256": vb.commitment(transfer),
        "raw_envelope_sha256": sha256(raw).hexdigest(),
        "raw_envelope_bytes": len(raw),
        "original_article_span": {
            "byte_start": article.start,
            "byte_end_exclusive": article.end,
            "sha256": sha256(span).hexdigest(),
        },
        "derived_jats_sha256": sha256(source).hexdigest(),
        "derived_jats_bytes": len(source),
        "namespace_declarations_inserted": injections,
        "derived_is_full_provider_response": False,
        "derived_equals_original_article_span": source == span,
        "requested_identifier": requested,
        "oai_response_date_utc": response_date,
        "oai_record_datestamp": datestamp,
        "declared_license_id": transfer["declared_license_id"],
        "status": "OFFLINE_DEVELOPMENT_DERIVATION_ONLY",
        "publisher_authenticity_verified": False,
        "license_rights_verified_by_tool": False,
        "operator_retrieval_verified": False,
        "scientific_labels_established": False,
        "protected_custody_qualified": False,
    }
    require(len(vb.canonical_bytes(receipt)) <= MAX_RECEIPT_BYTES,
            "DERIVATION_RECEIPT_LIMIT")
    return source, receipt


def receipt_envelope(receipt: dict[str, Any]) -> dict[str, Any]:
    return {"receipt": receipt, "receipt_sha256": vb.commitment(receipt)}


def replay(raw: bytes, transfer: dict[str, Any], source: bytes,
           supplied: dict[str, Any], *, expected_receipt_sha256: str) -> dict[str, Any]:
    capture.fields(supplied, "receipt receipt_sha256", "DERIVATION_RECEIPT_FIELDS")
    require(capture.digest(expected_receipt_sha256)
            == capture.digest(supplied["receipt_sha256"])
            == vb.commitment(supplied["receipt"]), "DERIVATION_EXTERNAL_PIN_MISMATCH")
    regenerated_source, regenerated_receipt = derive(raw, transfer)
    require(source == regenerated_source and supplied["receipt"] == regenerated_receipt,
            "DERIVATION_REPLAY_MISMATCH")
    return {
        "status": "RAW_SPAN_AND_DERIVED_JATS_REPLAYED",
        "receipt_sha256": expected_receipt_sha256,
        "raw_envelope_sha256": regenerated_receipt["raw_envelope_sha256"],
        "derived_jats_sha256": regenerated_receipt["derived_jats_sha256"],
        "publisher_authenticity_verified": False,
        "license_rights_verified_by_tool": False,
        "scientific_labels_established": False,
    }


def _private_create(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("extract", "replay"), required=True)
    parser.add_argument("--raw-envelope", type=Path, required=True)
    parser.add_argument("--transfer", type=Path, required=True)
    parser.add_argument("--output-source", type=Path)
    parser.add_argument("--derived-source", type=Path)
    parser.add_argument("--receipt-envelope", type=Path)
    parser.add_argument("--expected-receipt-sha256")
    args = parser.parse_args(argv)
    try:
        raw = read_regular(args.raw_envelope, MAX_ENVELOPE_BYTES)
        transfer = vb.parse_document(read_regular(args.transfer, MAX_TRANSFER_BYTES))
        if args.action == "extract":
            require(args.output_source is not None and args.derived_source is None
                    and args.receipt_envelope is None
                    and args.expected_receipt_sha256 is None, "DERIVATION_ARGUMENTS")
            source, receipt = derive(raw, transfer)
            _private_create(args.output_source, source)
            output = receipt_envelope(receipt)
        else:
            require(args.output_source is None and args.derived_source is not None
                    and args.receipt_envelope is not None
                    and args.expected_receipt_sha256 is not None,
                    "DERIVATION_ARGUMENTS")
            source = read_regular(args.derived_source, jats.MAX_SOURCE_BYTES)
            supplied = vb.parse_document(read_regular(args.receipt_envelope,
                                                     MAX_RECEIPT_BYTES))
            output = replay(raw, transfer, source, supplied,
                            expected_receipt_sha256=args.expected_receipt_sha256)
        sys.stdout.buffer.write(vb.canonical_bytes(output))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
