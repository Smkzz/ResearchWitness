"""Offline custody policy and input validation. All development fixtures are synthetic."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

IMPORT_VERSION = "rw-custody-import/2"
REVIEW_VERSION = "rw-custody-review/5"
SEAL_VERSION = "rw-custody-seal/3"
SUMMARY_VERSION = "rw-custody-summary/3"
PUBLIC_SUMMARY_VERSION = "rw-custody-public-summary/2"
MARKER = "RESEARCHWITNESS_SYNTHETIC_ONLY_V1\n"
PRODUCTION_ROOT = Path(r"C:\ResearchWitness-Custody")
DEV_PARENT = Path(tempfile.gettempdir()) / "rw-custody-synthetic-only"
MAX_JSON_BYTES = 1_000_000
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_ITEMS = 128
MAX_ANCHOR_CHARS = 240
MAX_EVIDENCE_SPAN_BYTES = 2_000
ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,63}$", re.ASCII)
HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$", re.ASCII)
DECIMAL_RE = re.compile(r"^(0|[1-9][0-9]{0,8})(?:\.[0-9]{1,4})?$", re.ASCII)
DOI_RE = re.compile(r"^10\.[0-9]{4,9}/[^\s<>\x00?#]+$", re.IGNORECASE | re.ASCII)
APPROVED_PUBLIC_HOSTS = frozenset({
    "api.crossref.org", "www.ebi.ac.uk", "eutils.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
})
UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", re.ASCII)


class CustodyError(Exception):
    """A public error code, never private source content or path."""


def reject(code: str) -> None:
    raise CustodyError(code)


def id_valid(value: object) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        reject("INVALID_ID")
    return value


def hash_valid(value: object) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        reject("INVALID_SHA256")
    return value


def normalize_doi(value: object) -> str:
    """Return one stable article-family key; unsupported IDs cannot count as papers."""
    if not isinstance(value, str) or not 1 <= len(value) <= 240 or "\x00" in value:
        reject("INVALID_DOCUMENT_ID")
    raw = value.strip()
    folded = raw.casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if folded.startswith(prefix):
            raw = raw[len(prefix):]
            break
    raw = unquote(raw).strip().casefold()
    if not DOI_RE.fullmatch(raw):
        reject("CANONICAL_DOI_REQUIRED")
    return "doi:" + raw


def normalize_source_id(value: object) -> str:
    """Normalize a source identifier while keeping the article family separate."""
    if not isinstance(value, str) or not 1 <= len(value) <= 240 or "\x00" in value:
        reject("INVALID_SOURCE_ID")
    raw = value.strip()
    folded = raw.casefold()
    if folded.startswith(("https://doi.org/", "http://doi.org/", "doi:")):
        return normalize_doi(raw)
    if re.fullmatch(r"(?i)pmcid:\s*PMC[0-9]+", raw):
        return "pmcid:" + re.sub(r"(?i)^pmcid:\s*", "", raw).upper()
    if re.fullmatch(r"(?i)pmid:\s*[0-9]+", raw):
        return "pmid:" + re.sub(r"(?i)^pmid:\s*", "", raw)
    reject("UNSUPPORTED_SOURCE_ID")


def validate_span(source: bytes, value: object) -> tuple[str, int, int]:
    """Validate a UTF-8 source excerpt against exact byte offsets in a pinned file."""
    span = require_keys(value, {"start", "end", "text"})
    start = bounded_int(span["start"], maximum=len(source))
    end = bounded_int(span["end"], minimum=1, maximum=len(source))
    text = span["text"]
    if (start >= end or end - start > MAX_EVIDENCE_SPAN_BYTES
        or not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_EVIDENCE_SPAN_BYTES
        or "\x00" in text):
        reject("INVALID_SOURCE_SPAN")
    try:
        actual = source[start:end].decode("utf-8", errors="strict")
    except UnicodeError:
        reject("SOURCE_SPAN_NOT_UTF8")
    if actual != text:
        reject("SOURCE_SPAN_MISMATCH")
    return actual, start, end


def require_nested_span(outer: tuple[str, int, int], inner: tuple[str, int, int]) -> None:
    if inner[1] < outer[1] or inner[2] > outer[2]:
        reject("SOURCE_SPAN_OUTSIDE_RELATION")


def parse_count_span(raw: str, *, explicit_denominator: bool = False) -> int:
    grouped = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,3}(?: [0-9]{3})+|[0-9]{1,9})"
    pattern = (r"(?i)\s*n\s*=\s*(?P<number>" + grouped + r")\s*"
               if explicit_denominator else r"\s*(?P<number>" + grouped + r")\s*")
    match = re.fullmatch(pattern, raw, re.ASCII)
    if not match:
        reject("SOURCE_COUNT_NOT_EXPLICIT")
    number = int(match.group("number").replace(",", "").replace(" ", ""))
    return bounded_int(number, maximum=1_000_000_000)


def parse_percent_span(raw: str) -> tuple[str, int]:
    match = re.fullmatch(r"\s*(?P<value>0|[1-9][0-9]{0,8}(?:\.[0-9]{1,4})?)\s*%\s*", raw, re.ASCII)
    if not match:
        reject("SOURCE_PERCENT_NOT_EXPLICIT")
    value = match.group("value")
    parsed = decimal_value(value)
    return format(parsed, "f"), (len(value.partition(".")[2]) if "." in value else 0)


def source_name(value: object) -> str:
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        reject("UNSAFE_FILENAME")
    if value in (".", "..") or value.endswith(".") or value.endswith(" "):
        reject("UNSAFE_FILENAME")
    stem = value.split(".")[0].casefold()
    if stem in {"con", "prn", "aux", "nul"} or re.fullmatch(r"(com|lpt)[1-9]", stem):
        reject("UNSAFE_FILENAME")
    if "." not in value or value.rsplit(".", 1)[-1].casefold() not in {
        "txt", "md", "xml", "pdf", "csv", "tsv", "json"
    }:
        reject("UNSUPPORTED_SOURCE_FORMAT")
    return value


def require_keys(data: object, keys: set[str]) -> dict:
    if not isinstance(data, dict) or set(data) != keys:
        reject("INVALID_SCHEMA_KEYS")
    return data


def validate_utc_timestamp(value: object) -> str:
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value):
        reject("INVALID_UTC_TIMESTAMP")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        reject("INVALID_UTC_TIMESTAMP")
    return value


def validate_source_provenance(value: object, *, synthetic_only: bool) -> dict:
    provenance = require_keys(value, {
        "method", "source_url", "retrieved_at_utc", "license_notice",
        "public_use_status",
    })
    method = provenance["method"]
    source_url = provenance["source_url"]
    notice = provenance["license_notice"]
    if not isinstance(method, str):
        reject("INVALID_ACQUISITION_METHOD")
    if not isinstance(source_url, str) or not 1 <= len(source_url) <= 2048:
        reject("INVALID_SOURCE_URL")
    if not isinstance(notice, str) or not 1 <= len(notice) <= 512 or "\x00" in notice:
        reject("INVALID_LICENSE_NOTICE")
    validate_utc_timestamp(provenance["retrieved_at_utc"])
    if method == "SYNTHETIC_FIXTURE":
        if not synthetic_only:
            reject("SYNTHETIC_SOURCE_FORBIDDEN_IN_PRODUCTION")
        if (not source_url.startswith("synthetic://fixture/")
            or provenance["public_use_status"] != "NOT_APPLICABLE_SYNTHETIC"):
            reject("INVALID_SYNTHETIC_PROVENANCE")
        return provenance

    if synthetic_only:
        reject("REAL_SOURCE_FORBIDDEN_IN_SYNTHETIC_MODE")
    if method not in {"APPROVED_PUBLIC_PROVIDER", "HASH_PINNED_HANDOFF"}:
        reject("INVALID_ACQUISITION_METHOD")
    if provenance["public_use_status"] != "CUSTODIAN_CONFIRMED_PUBLIC_USE":
        reject("PUBLIC_USE_NOT_CONFIRMED")
    if any(ord(char) < 0x21 or char == "\\" for char in source_url):
        reject("INVALID_SOURCE_URL")
    try:
        parsed = urlsplit(source_url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        reject("INVALID_SOURCE_URL")
    allowed_authorities = APPROVED_PUBLIC_HOSTS | frozenset(host_name + ":443" for host_name in APPROVED_PUBLIC_HOSTS)
    if (parsed.scheme != "https" or host not in APPROVED_PUBLIC_HOSTS
        or parsed.netloc not in allowed_authorities
        or parsed.username is not None or parsed.password is not None
        or port not in (None, 443) or parsed.fragment):
        reject("SOURCE_HOST_NOT_APPROVED")
    return provenance


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def bounded_int(value: object, *, minimum: int = 0, maximum: int = 1_000_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        reject("INVALID_INTEGER")
    return value


def decimal_value(raw: object) -> Decimal:
    if not isinstance(raw, str) or not DECIMAL_RE.fullmatch(raw):
        reject("INVALID_DECIMAL")
    try:
        result = Decimal(raw)
    except InvalidOperation:
        reject("INVALID_DECIMAL")
    if not result.is_finite() or result > 100:
        reject("INVALID_DECIMAL")
    return result


def computed_percent(numerator: object, denominator: object, printed: object, decimals: object) -> dict:
    n = bounded_int(numerator, maximum=1_000_000_000)
    d = bounded_int(denominator, minimum=1, maximum=1_000_000_000)
    places = bounded_int(decimals, maximum=4)
    p = decimal_value(printed)
    actual_digits = len(printed.partition(".")[2]) if "." in printed else 0
    if actual_digits != places:
        reject("PRINTED_PRECISION_MISMATCH")
    if n > d:
        reject("OUTSIDE_PROPORTION_DOMAIN")
    # Decimal arithmetic is exact and reproducible. No floating-point inputs.
    value = (Decimal(n) * Decimal(100)) / Decimal(d)
    q = Decimal(1).scaleb(-places)
    rounded = value.quantize(q, rounding=ROUND_HALF_UP)
    return {
        "matches": rounded == p,
        "recomputed": format(rounded, f".{places}f"),
        "printed": format(p, "f"),
        "rounding": "ROUND_HALF_UP",
    }


def unique_pairs(pairs: list[tuple[str, object]]) -> None:
    # JSON values may be dictionaries or lists; only object keys are unique.
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        reject("DUPLICATE_ENTRY")


def strict_json_bytes(data: bytes) -> object:
    if len(data) > MAX_JSON_BYTES:
        reject("JSON_TOO_LARGE")

    def pairs_hook(pairs):
        unique_pairs(pairs)
        return dict(pairs)

    def bad_float(_):
        reject("JSON_FLOAT_NOT_ALLOWED")

    def bad_constant(_):
        reject("INVALID_JSON_CONSTANT")

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs_hook,
                          parse_float=bad_float, parse_constant=bad_constant)
    except CustodyError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        reject("INVALID_JSON")


def canonical_bytes(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guarded_stat(path: Path, *, file: bool | None = None) -> os.stat_result:
    # Check every component *within* the dedicated custody store, including
    # its root. On AppContainer, ancestors such as C:\Users cannot be lstat'ed
    # even when the sandbox-private directory below them is accessible.
    # Production is fixed to C:\ResearchWitness-Custody (directly below the
    # volume root); development is limited to synthetic TEMP fixtures.
    path = Path(os.path.abspath(path))
    if within(path, PRODUCTION_ROOT):
        boundary = PRODUCTION_ROOT
    elif within(path, DEV_PARENT):
        boundary = DEV_PARENT
    else:
        reject("PATH_OUTSIDE_ALLOWED_ROOT")
    chain = []
    part = path
    while part != boundary:
        chain.append(part)
        if part == part.parent:
            reject("PATH_OUTSIDE_ALLOWED_ROOT")
        part = part.parent
    chain.append(boundary)
    for part in reversed(chain):
        try:
            s = os.lstat(part)
        except (OSError, ValueError):
            reject("PATH_UNAVAILABLE")
        if stat.S_ISLNK(s.st_mode) or (getattr(s, "st_file_attributes", 0) &
                                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            reject("REPARSE_POINT_REJECTED")
    s = os.lstat(path)
    if file is True:
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
            reject("UNSAFE_FILE_TYPE_OR_HARDLINK")
    elif file is False and not stat.S_ISDIR(s.st_mode):
        reject("DIRECTORY_REQUIRED")
    return s


def within(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(os.path.abspath(path)),
                                   os.path.normcase(os.path.abspath(parent))]) == os.path.normcase(os.path.abspath(parent))
    except ValueError:
        return False


def under_root(path: Path, root: Path, *, file: bool | None = None) -> Path:
    if not within(path, root) or Path(os.path.abspath(path)) == Path(os.path.abspath(root)):
        reject("PATH_OUTSIDE_STORE")
    guarded_stat(root, file=False)
    guarded_stat(path, file=file)
    return path


def safe_source_file(path: Path, incoming: Path) -> Path:
    if path.parent != incoming or not within(path, incoming):
        reject("PATH_OUTSIDE_INCOMING")
    return under_root(path, incoming, file=True)


def checked_read(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    guarded_stat(path, file=True)
    if os.lstat(path).st_size > max_bytes:
        reject("FILE_TOO_LARGE")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                reject("UNSAFE_FILE_TYPE_OR_HARDLINK")
            data = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
    except CustodyError:
        raise
    except OSError:
        reject("READ_FAILED")
    if len(data) > max_bytes:
        reject("FILE_TOO_LARGE")
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
        reject("SOURCE_MUTATED")
    return data


def read_json(path: Path) -> object:
    return strict_json_bytes(checked_read(path))


def _windows_user() -> str:
    buf = ctypes.create_unicode_buffer(256)
    length = ctypes.c_ulong(len(buf))
    if not ctypes.windll.advapi32.GetUserNameW(buf, ctypes.byref(length)):
        reject("WINDOWS_IDENTITY_UNAVAILABLE")
    return buf.value


def _acl_guard(root: Path) -> None:
    # Installed production files must have a protected DACL with only custodian
    # and SYSTEM grants. Resolve principals to SIDs to avoid locale-specific names.
    script = r"""
$p = 'C:\ResearchWitness-Custody'
$a = Get-Acl -LiteralPath $p -ErrorAction Stop
$u = Get-LocalUser -Name 'rw-custodian' -ErrorAction Stop
$ownerAccount = New-Object System.Security.Principal.NTAccount($a.Owner)
$ownerSid = $ownerAccount.Translate([Security.Principal.SecurityIdentifier]).Value
$o = [pscustomobject]@{
  Protected = $a.AreAccessRulesProtected
  CustodianSID = $u.SID.Value
  OwnerSID = $ownerSid
  Entries = @($a.Access | ForEach-Object {
    [pscustomobject]@{
      SID = $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
      Type = [string]$_.AccessControlType
      Rights = [long]$_.FileSystemRights
      Inherited = [bool]$_.IsInherited
    }
  })
}
$o | ConvertTo-Json -Depth 5 -Compress
"""
    shell = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    try:
        result = subprocess.run([shell, "-NoLogo", "-NoProfile", "-NonInteractive",
                                 "-Command", script], timeout=15,
                                capture_output=True, check=True, text=True)
        acl = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        reject("ACL_VERIFICATION_UNAVAILABLE")
    if not isinstance(acl, dict) or acl.get("Protected") is not True:
        reject("ACL_NOT_PROTECTED")
    entries = acl.get("Entries", [])
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or not entries:
        reject("ACL_INVALID")
    custodian_sid = acl.get("CustodianSID")
    if (not isinstance(custodian_sid, str)
        or not re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", custodian_sid)):
        reject("ACL_CUSTODIAN_SID_INVALID")
    if len(entries) != 2 or {x.get("SID") for x in entries} != {"S-1-5-18", custodian_sid}:
        reject("ACL_UNEXPECTED_PRINCIPAL")
    full_control = 0x1F01FF
    for ace in entries:
        if ace.get("Type") != "Allow" or ace.get("Inherited") is not False:
            reject("ACL_UNEXPECTED_ACE")
        rights = ace.get("Rights")
        if type(rights) is not int or (rights & full_control) != full_control:
            reject("ACL_RIGHTS_INSUFFICIENT")
    if acl.get("OwnerSID") not in ("S-1-5-18", acl.get("CustodianSID")):
        reject("ACL_OWNER_NOT_CUSTODIAN_OR_SYSTEM")


def preflight(*, dev_root: Path | None = None) -> Path:
    if dev_root is not None:
        # Synthetic fixtures live in the sandbox user's private TEMP area.
        # The custodian identity must never run in a development mode.
        if os.name == "nt" and _windows_user().casefold() == "rw-custodian":
            reject("DEV_MODE_FORBIDDEN_FOR_CUSTODIAN")
        root = Path(os.path.abspath(dev_root))
        if within(root, PRODUCTION_ROOT):
            reject("DEV_ROOT_NOT_SYNTHETIC")
        if not within(root, DEV_PARENT) or root == DEV_PARENT:
            reject("DEV_ROOT_NOT_SYNTHETIC")
        guarded_stat(root, file=False)
        marker = checked_read(root / ".synthetic-only", max_bytes=100)
        if marker.decode("ascii", errors="replace") != MARKER:
            reject("DEV_MARKER_INVALID")
        return root
    if os.name != "nt" or _windows_user().casefold() != "rw-custodian":
        reject("WRONG_CUSTODIAN_IDENTITY")
    guarded_stat(PRODUCTION_ROOT, file=False)
    _acl_guard(PRODUCTION_ROOT)
    return PRODUCTION_ROOT


def authorize_store_root(root: Path) -> Path:
    """Repeat identity, ACL, or synthetic-marker checks at every storage API boundary."""
    requested = Path(os.path.abspath(root))
    if within(requested, DEV_PARENT) and requested != Path(os.path.abspath(DEV_PARENT)):
        return preflight(dev_root=requested)
    authorized = preflight()
    if Path(os.path.abspath(authorized)) != requested:
        reject("UNAUTHORIZED_STORE_ROOT")
    return authorized
