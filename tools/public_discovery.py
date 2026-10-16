"""Read-only public-source candidate discovery with strict source boundaries.

This module discovers metadata candidates. It does not decide whether a paper
contains an error, whether a correction applies to the same population, or
whether a candidate is eligible for blinded evaluation.
"""
from __future__ import annotations

import errno
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import tempfile
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    HTTPSHandler,
    ProxyHandler,
    build_opener,
    getproxies,
    proxy_bypass,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None


REGISTRY_VERSION = 1
MAX_REGISTRY_CANDIDATES = 250
MAX_REGISTRY_SEARCHES = 500
MAX_REGISTRY_INPUT_BYTES = 8 * 1024 * 1024
ALLOWED_SOURCE_HOSTS = frozenset({
    "api.crossref.org",
    "www.ebi.ac.uk",
    "eutils.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
})
DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_MIN_INTERVAL_SECONDS = 1.0
MAX_QUERY_CHARS = 1000
DEFAULT_EUROPE_PMC_QUERY = (
    '(TITLE:correction OR TITLE:erratum OR TITLE:corrigendum) AND '
    '(TITLE_ABS:count OR TITLE_ABS:percentage OR TITLE_ABS:"sample size" '
    'OR TITLE_ABS:denominator OR TITLE_ABS:total)'
)
DEFAULT_CROSSREF_QUERY = (
    "correction erratum corrigendum count percentage denominator sample size table"
)
_PMCID_RE = re.compile(r"^(?:PMC)?([0-9]+)$", re.IGNORECASE)
_CORRECTION_TITLE_RE = re.compile(r"\b(correction|corrigendum|erratum)\b", re.IGNORECASE)


class SourceBoundaryError(ValueError):
    """The requested or redirected source is outside the approved host set."""


class SourceAccessError(RuntimeError):
    """A source request failed; callers must not retry or switch routes silently."""

    def __init__(
        self, host: str, reason: str, status_code: int | None = None,
        request_url: str | None = None, transport_error_class: str | None = None,
    ):
        self.host = host
        self.reason = reason
        self.status_code = status_code
        self.request_url = request_url
        # Fixed, low-sensitivity diagnostic metadata. Raw transport exception
        # messages can contain proxy details, so they are never copied here.
        self.transport_error_class = transport_error_class
        status = f" HTTP {status_code}" if status_code is not None else ""
        diagnostic = f" ({transport_error_class})" if transport_error_class else ""
        super().__init__(f"Public source access failed for {host}{status}: {reason}{diagnostic}")


class InvalidSourceResponse(ValueError):
    """An HTTP response arrived, but its body was not a valid provider result."""

    def __init__(self, provider: str, response: Mapping[str, Any], reason: str):
        self.provider = provider
        self.response = response
        self.reason = reason
        super().__init__(f"{provider} returned an invalid response: {reason}")


def failed_search_record(provider: str, query: str, error: SourceAccessError) -> dict[str, Any]:
    """Record a failed attempt without inventing a response hash or result count."""
    provider_hosts = {
        "europe_pmc": "www.ebi.ac.uk",
        "crossref": "api.crossref.org",
        "pubmed": "eutils.ncbi.nlm.nih.gov",
        "pmc": "pmc.ncbi.nlm.nih.gov",
    }
    if provider not in provider_hosts or provider_hosts[provider] != error.host:
        raise ValueError("Unknown public metadata provider")
    if error.reason.startswith("source boundary rejected"):
        status = "blocked"
        failure_code = "SOURCE_BOUNDARY_REJECTED"
    elif error.reason == "approved host is excluded from the managed proxy route":
        status = "blocked"
        failure_code = "MANAGED_PROXY_BYPASS_REJECTED"
    elif error.status_code == 200:
        status = "response_rejected"
        failure_code = "RESPONSE_TOO_LARGE"
    elif error.status_code is None:
        status = "transport_failed_before_http_response"
        failure_code = "TRANSPORT_UNAVAILABLE"
    elif error.status_code in {401, 403, 407, 423, 429, 451}:
        status = "blocked"
        failure_code = f"HTTP_{error.status_code}"
    elif 500 <= error.status_code <= 599:
        status = "provider_error"
        failure_code = f"HTTP_{error.status_code}"
    else:
        status = "http_error"
        failure_code = f"HTTP_{error.status_code}"
    return {
        "provider": provider,
        "host": error.host,
        "request_url": error.request_url,
        "query": query,
        "retrieved_at_utc": None,
        "response_sha256": None,
        "response_bytes": None,
        "record_count": None,
        "status": status,
        "failure_code": failure_code,
    }
def invalid_response_search_record(
    provider: str, query: str, error: InvalidSourceResponse
) -> dict[str, Any]:
    """Preserve response integrity metadata while keeping malformed result counts unknown."""
    provider_hosts = {
        "europe_pmc": "www.ebi.ac.uk",
        "crossref": "api.crossref.org",
        "pubmed": "eutils.ncbi.nlm.nih.gov",
        "pmc": "pmc.ncbi.nlm.nih.gov",
    }
    if provider_hosts.get(provider) != error.response.get("host"):
        raise ValueError("Unknown public metadata provider")
    return {
        "provider": provider,
        "host": error.response["host"],
        "request_url": error.response["url"],
        "query": query,
        "retrieved_at_utc": error.response["retrieved_at_utc"],
        "response_sha256": error.response["sha256"],
        "response_bytes": error.response["byte_count"],
        "record_count": None,
        "status": "invalid_response",
        "failure_code": "INVALID_PROVIDER_RESPONSE",
    }


def validate_source_url(url: str) -> str:
    """Accept HTTPS URLs on the exact approved host list, with no user info."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise SourceBoundaryError("Malformed source URL") from exc
    if parsed.scheme.lower() != "https" or host not in ALLOWED_SOURCE_HOSTS:
        raise SourceBoundaryError("Source URL is outside the approved HTTPS host list")
    if parsed.username is not None or parsed.password is not None:
        raise SourceBoundaryError("Credentials are not permitted in source URLs")
    if port not in (None, 443):
        raise SourceBoundaryError("Nonstandard source ports are not permitted")
    if parsed.fragment:
        raise SourceBoundaryError("Source URL fragments are not permitted")
    return host


class _ApprovedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, original_host: str):
        super().__init__()
        self.original_host = original_host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirect_host = validate_source_url(newurl)
        if redirect_host != self.original_host:
            raise SourceBoundaryError("Cross-host redirects are not permitted")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _private_rate_state_directory(
    temp_root: Path | None = None, *, host: str = "rate-limit-state"
) -> Path:
    """Return a verified per-user directory for persistent rate-limit state."""
    getuid = getattr(os, "getuid", None)
    if not callable(getuid):
        raise SourceAccessError(host, "private rate-limit state ownership cannot be verified on this platform")
    user_scope = str(getuid())
    token = sha256(user_scope.encode("utf-8")).hexdigest()[:24]
    directory = (temp_root or Path(tempfile.gettempdir())) / f"researchwitness-public-rate-{token}"
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError:
        raise SourceAccessError(host, "could not create a private rate-limit state directory") from None

    try:
        info = directory.lstat()
    except OSError:
        raise SourceAccessError(host, "could not inspect the rate-limit state directory") from None
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise SourceAccessError(host, "rate-limit state path is not a directory")
    if hasattr(os, "getuid") and (
        info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise SourceAccessError(host, "rate-limit state directory is not private to the current user")
    return directory


def _shared_rate_state_path(host: str) -> Path:
    host_token = sha256(host.encode("utf-8")).hexdigest()[:24]
    return _private_rate_state_directory(host=host) / f"{host_token}.lock"


def _lock_rate_file(fd: int) -> int:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return 0
    import msvcrt  # pragma: no cover - exercised on Windows

    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
    while True:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            return 1
        except OSError:
            time.sleep(0.05)


def _unlock_rate_file(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    import msvcrt  # pragma: no cover - exercised on Windows

    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


_TLS_HANDSHAKE_REASONS = frozenset({
    "SSLV3_ALERT_HANDSHAKE_FAILURE",
    "TLSV1_ALERT_HANDSHAKE_FAILURE",
    "TLSV1_ALERT_PROTOCOL_VERSION",
    "NO_SHARED_CIPHER",
    "WRONG_VERSION_NUMBER",
})


def _transport_exception_chain(error: BaseException) -> list[BaseException]:
    """Return known wrapped exceptions without rendering their messages."""
    pending: list[BaseException] = [error]
    result: list[BaseException] = []
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        result.append(current)
        if isinstance(current, URLError):
            reason = current.reason
            if isinstance(reason, BaseException):
                pending.append(reason)
        if isinstance(current.__cause__, BaseException):
            pending.append(current.__cause__)
        if isinstance(current.__context__, BaseException):
            pending.append(current.__context__)
    return result


def _classify_transport_error(error: BaseException, *, phase: str) -> str:
    """Classify only exception shapes that identify a transport failure layer.

    The output is an enum-like constant and intentionally excludes exception
    text, proxy addresses, credentials, request paths, and authentication data.
    """
    chain = _transport_exception_chain(error)
    if any(isinstance(item, socket.gaierror) for item in chain):
        return "dns_resolution"
    if any(isinstance(item, (TimeoutError, socket.timeout)) for item in chain):
        return "timeout"
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return "tls_certificate"

    for item in chain:
        if not isinstance(item, ssl.SSLError):
            continue
        reason = getattr(item, "reason", None)
        candidates = [reason] if isinstance(reason, str) else []
        candidates.extend(part for part in item.args if isinstance(part, str))
        if any(
            token in candidate.upper()
            for token in _TLS_HANDSHAKE_REASONS
            for candidate in candidates
        ):
            return "tls_handshake"

    if any(
        isinstance(item, PermissionError)
        or isinstance(item, OSError) and item.errno in {errno.EACCES, errno.EPERM}
        for item in chain
    ):
        return "local_socket_permission_denied"

    if any(isinstance(item, ConnectionRefusedError) for item in chain):
        # The approved-host bypass check has already failed closed and this
        # request is explicitly routed through the configured proxy.
        return "proxy_connection" if phase == "opening" else "tcp_connection"
    network_errnos = {
        errno.ECONNABORTED,
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.EHOSTUNREACH,
        errno.ENETUNREACH,
        errno.EPIPE,
    }
    for item in chain:
        if not isinstance(item, OSError) or item.errno not in network_errnos:
            continue
        if item.errno == errno.ECONNREFUSED and phase == "opening":
            return "proxy_connection"
        return "tcp_connection"
    if any(isinstance(item, ssl.SSLError) for item in chain):
        return "other"
    if any(isinstance(item, BaseException) for item in chain[1:]):
        return "other"
    return "unknown"


def _reserve_shared_rate_slot(
    host: str,
    interval_seconds: float,
    sleep: Callable[[float], None],
    *,
    state_path: Path | None = None,
    wall_clock: Callable[[], float] = time.time,
) -> None:
    """Serialize starts across client instances and CLI processes on this host."""
    path = state_path or _shared_rate_state_path(host)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        raise SourceAccessError(host, "could not enforce the shared per-host request interval") from None
    locked = False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SourceAccessError(host, "shared rate-limit state is not a regular file")
        if hasattr(os, "getuid") and (
            info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise SourceAccessError(host, "shared rate-limit state is not private to the current user")
        state_offset = _lock_rate_file(fd)
        locked = True
        os.lseek(fd, state_offset, os.SEEK_SET)
        raw_previous = os.read(fd, 64).strip()
        if raw_previous:
            try:
                previous = float(raw_previous.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                raise SourceAccessError(host, "shared rate-limit state is invalid") from None
            if not math.isfinite(previous) or previous < 0:
                raise SourceAccessError(host, "shared rate-limit state is invalid")
            delay = interval_seconds - (wall_clock() - previous)
            if delay > 0:
                sleep(delay)
        started_at = wall_clock()
        if not math.isfinite(started_at) or started_at < 0:
            raise SourceAccessError(host, "system clock cannot enforce the shared request interval")
        encoded = f"{started_at:.9f}".encode("ascii")
        os.lseek(fd, state_offset, os.SEEK_SET)
        os.ftruncate(fd, state_offset)
        os.write(fd, encoded)
        os.fsync(fd)
    except OSError:
        raise SourceAccessError(host, "could not enforce the shared per-host request interval") from None
    finally:
        try:
            if locked:
                _unlock_rate_file(fd)
        finally:
            os.close(fd)


def _default_transport(
    url: str, headers: Mapping[str, str], timeout: float, max_bytes: int
) -> tuple[int, bytes, str]:
    host = validate_source_url(url)
    proxies = getproxies()
    https_proxy = proxies.get("https") or proxies.get("all")
    if not https_proxy:
        raise SourceAccessError(host, "managed HTTPS proxy is not configured", request_url=url)
    if proxy_bypass(host):
        raise SourceAccessError(host, "approved host is excluded from the managed proxy route", request_url=url)
    # urllib's ProxyHandler selects by URL scheme and does not itself use the
    # generic "all" entry for HTTPS requests.
    proxies = dict(proxies)
    proxies["https"] = https_proxy
    opener = build_opener(
        _ApprovedRedirectHandler(host),
        # Preserve the inherited proxy and the platform's default CA validation.
        ProxyHandler(proxies),
        HTTPSHandler(context=ssl.create_default_context()),
    )
    request = Request(url, headers=dict(headers), method="GET")
    phase = "opening"
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            validate_source_url(final_url)
            phase = "reading_response_body"
            body = response.read(max_bytes + 1)
            return response.status, body, final_url
    except SourceBoundaryError:
        raise SourceAccessError(
            host, "source boundary rejected a redirect", request_url=url
        ) from None
    except HTTPError as exc:
        raise SourceAccessError(host, "provider returned an error", exc.code, url) from None
    except URLError as exc:
        failure_class = _classify_transport_error(exc, phase=phase)
        raise SourceAccessError(
            host, "managed transport or proxy unavailable", request_url=url,
            transport_error_class=failure_class,
        ) from None
    except OSError as exc:
        # Some urllib handlers propagate socket/SSL errors directly instead
        # of wrapping them in URLError. Normalize them through the same safe
        # classifier without preserving their possibly sensitive message.
        failure_class = _classify_transport_error(exc, phase=phase)
        raise SourceAccessError(
            host, "managed transport or proxy unavailable", request_url=url,
            transport_error_class=failure_class,
        ) from None


class PublicSourceClient:
    """Small GET-only client with exact-host checks, rate limits, and size caps."""

    def __init__(
        self,
        *,
        transport: Callable[[str, Mapping[str, str], float, int], tuple[int, bytes, str]] | None = None,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if min_interval_seconds < DEFAULT_MIN_INTERVAL_SECONDS:
            raise ValueError("Provider interval must be at least one second")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("Timeout and response limit must be positive")
        self._transport = transport or _default_transport
        self._uses_managed_transport = transport is None
        self._min_interval = min_interval_seconds
        self._timeout = timeout_seconds
        self._max_bytes = max_response_bytes
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request: dict[str, float] = {}

    def get(self, url: str) -> dict[str, Any]:
        host = validate_source_url(url)
        now = self._monotonic()
        previous = self._last_request.get(host)
        if previous is not None:
            delay = self._min_interval - (now - previous)
            if delay > 0:
                self._sleep(delay)
        if self._uses_managed_transport:
            try:
                _reserve_shared_rate_slot(host, self._min_interval, self._sleep)
            except SourceAccessError as exc:
                exc.request_url = url
                raise
        self._last_request[host] = self._monotonic()
        headers = {
            "Accept": "application/json, application/xml;q=0.8",
            "User-Agent": "ResearchWitness-public-discovery/0.1 (+https://github.com/Smkzz/ResearchWitness)",
        }
        status, body, final_url = self._transport(
            url, headers, self._timeout, self._max_bytes
        )
        final_host = validate_source_url(final_url)
        if final_host != host:
            raise SourceBoundaryError("Cross-host redirects are not permitted")
        if status != 200:
            raise SourceAccessError(host, "provider returned a non-success response", status, url)
        if len(body) > self._max_bytes:
            raise SourceAccessError(
                host, "response exceeded the configured size limit", 200, url
            )
        return {
            "url": url,
            "host": host,
            "retrieved_at_utc": utc_now(),
            "sha256": sha256(body).hexdigest(),
            "byte_count": len(body),
            "body": body,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    result = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if result.lower().startswith(prefix):
            result = result[len(prefix):].strip()
            break
    if not result or any(ch.isspace() for ch in result):
        return None
    return result.lower()


def normalize_pmcid(value: str | None) -> str | None:
    if not value:
        return None
    match = _PMCID_RE.fullmatch(value.strip())
    return f"PMC{match.group(1)}" if match else None


def canonical_work_key(identifiers: Mapping[str, str | None]) -> str | None:
    doi = normalize_doi(identifiers.get("doi"))
    if doi:
        return f"doi:{doi}"
    pmcid = normalize_pmcid(identifiers.get("pmcid"))
    if pmcid:
        return f"pmcid:{pmcid}"
    pmid = identifiers.get("pmid")
    if pmid and pmid.isdigit():
        return f"pmid:{pmid}"
    return None


def percentage_recalculation(
    numerator: int, denominator: int, reported_percent: str, display_precision: int
) -> dict[str, str | bool]:
    """Recompute an explicit n/N percentage under the v1.3 display rule.

    This only checks arithmetic. It does not establish population scope or
    source eligibility. Decimal ROUND_HALF_UP matches the current ratio checker.
    """
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

    if (not isinstance(numerator, int) or isinstance(numerator, bool)
            or not isinstance(denominator, int) or isinstance(denominator, bool)):
        raise ValueError("Boolean operands are not valid counts")
    if (numerator < 0 or denominator <= 0 or numerator > denominator
            or numerator > 999_999_999 or denominator > 999_999_999):
        raise ValueError("Operands are outside the supported proportion domain")
    if not isinstance(display_precision, int) or isinstance(display_precision, bool) or not 0 <= display_precision <= 6:
        raise ValueError("Display precision must be between 0 and 6")
    if not isinstance(reported_percent, str):
        raise ValueError("Reported percentage must be supplied as source text")
    try:
        reported = Decimal(reported_percent)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Reported percentage must be a decimal number") from exc
    if not reported.is_finite() or reported < 0 or reported > 100:
        raise ValueError("Reported percentage is outside 0–100")
    if max(0, -reported.as_tuple().exponent) != display_precision:
        raise ValueError("Display precision must match the printed percentage")
    quantum = Decimal(1).scaleb(-display_precision)
    with localcontext() as context:
        context.prec = 50
        exact = Decimal(numerator) * Decimal(100) / Decimal(denominator)
        rounded = exact.quantize(quantum, rounding=ROUND_HALF_UP)
    return {
        "exact_ratio_percent": f"{numerator * 100}/{denominator}",
        "unrounded_decimal_percent": format(exact, "f"),
        "rounded_percent": format(rounded, "f"),
        "reported_percent": format(reported, "f"),
        "display_precision": str(display_precision),
        "arithmetic_matches": reported == rounded,
    }


def _metadata_candidate(
    *,
    provider: str,
    kind: str,
    title: str,
    identifiers: Mapping[str, str | None],
    api_record: Mapping[str, Any],
    search: Mapping[str, Any],
) -> dict[str, Any]:
    ids = {
        "doi": normalize_doi(identifiers.get("doi")),
        "pmid": (identifiers.get("pmid")
                 if isinstance(identifiers.get("pmid"), str)
                 and identifiers.get("pmid", "").isdigit() else None),
        "pmcid": normalize_pmcid(identifiers.get("pmcid")),
    }
    work_key = canonical_work_key(ids)
    if work_key:
        identity_key = work_key
    else:
        # Identifierless rows must remain distinct even when title strings match.
        identity_key = "record:" + ":".join((
            provider,
            str(search.get("response_sha256") or "no-response-hash"),
            str(api_record.get("_record_ordinal") or "unknown-ordinal"),
        ))
    license_value = api_record.get("license")
    if license_value is not None and not isinstance(license_value, str):
        license_value = json.dumps(license_value, ensure_ascii=False, sort_keys=True)
    source_record = {
        "provider": provider,
        "api_url": search["request_url"],
        "response_sha256": search["response_sha256"],
        "record_ordinal": api_record.get("_record_ordinal"),
        "reported_identifiers": ids,
        "record_content_sha256": None,
        "captured_source_version": None,
        "license": license_value,
    }
    correction = kind == "correction_notice"
    return {
        "candidate_id": sha256(identity_key.encode("utf-8")).hexdigest()[:24],
        "candidate_kinds": [kind],
        "title": title.strip()[:1000],
        "identifiers": ids,
        "work_family": {
            "key": work_key,
            "independent_status": "unresolved",
            "duplicate_relationships": [],
        },
        "source_records": [source_record],
        "original_source": {
            "identifier": ids["doi"] or ids["pmcid"] or ids["pmid"],
            "version": "unverified",
            "content_sha256": None,
            "retrieval_status": "metadata_only",
            "license_status": "not_assessed",
        } if not correction else None,
        "correction_source": {
            "identifier": ids["doi"] or ids["pmcid"] or ids["pmid"],
            "version": "unverified",
            "content_sha256": None,
            "retrieval_status": "metadata_only",
            "license_status": "not_assessed",
        } if correction else None,
        "mathematical_relationship": {
            "status": "not_assessed",
            "numerator": None,
            "denominator": None,
            "reported_percent": None,
            "corrected_values": None,
            "scope": None,
        },
        "preliminary_eligibility_v1_3": "unknown",
        "independent_review_status": "not_started",
        "exposure_status": "developer_exposed",
        "holdout_eligible": False,
        "blockers": [
            "original source version and content have not been captured",
            "correction scope and exact numerical relationship have not been independently verified",
            "candidate was discovered by the development workflow and is not untouched",
        ],
    }


def _europe_pmc_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    result_list = payload.get("resultList")
    if not isinstance(result_list, dict):
        raise ValueError("Europe PMC response did not contain a resultList object")
    results = result_list.get("result")
    if not isinstance(results, list):
        raise ValueError("Europe PMC response did not contain a result list")
    records = []
    for ordinal, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            raise ValueError("Europe PMC result rows must be objects")
        rec = dict(item)
        rec["_record_ordinal"] = ordinal
        records.append(rec)
    return records


def _crossref_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Crossref response did not contain a message object")
    records = message.get("items")
    if not isinstance(records, list):
        raise ValueError("Crossref response did not contain a work list")
    result = []
    for ordinal, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            raise ValueError("Crossref work rows must be objects")
        rec = dict(item)
        rec["_record_ordinal"] = ordinal
        result.append(rec)
    return result


def _crossref_title(item: Mapping[str, Any]) -> str:
    value = item.get("title") or []
    return str(value[0]) if isinstance(value, list) and value else str(value or "")


def _crossref_is_correction(item: Mapping[str, Any]) -> bool:
    if _CORRECTION_TITLE_RE.search(_crossref_title(item)):
        return True
    if str(item.get("type", "")).lower() in {"correction", "erratum", "corrigendum"}:
        return True
    relation = item.get("relation") or {}
    if isinstance(relation, dict) and any(
        word in key.lower() for key in relation
        for word in ("correction", "corrigendum", "erratum", "update")
    ):
        return True
    return any(
        str(entry.get("type", "")).lower() in {"correction", "erratum", "corrigendum"}
        for entry in (item.get("update-to") or []) if isinstance(entry, dict)
    )


def _crossref_relations(item: Mapping[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    relation = item.get("relation") or {}
    if isinstance(relation, dict):
        for relation_type, values in relation.items():
            values = values if isinstance(values, list) else [values]
            for value in values:
                if isinstance(value, dict) and value.get("id"):
                    result.append({"type": str(relation_type), "identifier": str(value["id"])})
    updates = item.get("update-to") or []
    if isinstance(updates, list):
        for value in updates:
            if isinstance(value, dict) and value.get("DOI"):
                result.append({
                    "type": str(value.get("type", "update-to")),
                    "identifier": str(value["DOI"]),
                })
    return result


def _build_candidates(
    provider: str,
    kind: str,
    records: list[dict[str, Any]],
    search: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    for record in records:
        title = (
            _crossref_title(record) if provider == "crossref"
            else str(record.get("title") or "")
        )
        actual_kind = "correction_notice" if (
            kind == "correction_notice" or
            (provider == "crossref" and _crossref_is_correction(record)) or
            _CORRECTION_TITLE_RE.search(title)
        ) else kind
        identifiers = {
            "doi": record.get("DOI") or record.get("doi"),
            "pmid": record.get("pmid"),
            "pmcid": record.get("pmcid"),
        }
        candidate = _metadata_candidate(
            provider=provider,
            kind=actual_kind,
            title=title,
            identifiers=identifiers,
            api_record=record,
            search=search,
        )
        candidate["source_records"][0]["record_ordinal"] = record.get("_record_ordinal")
        candidate["source_records"][0]["related_identifiers"] = (
            _crossref_relations(record) if provider == "crossref" else []
        )
        candidates.append(candidate)
    return candidates


def _search_run(provider: str, query: str, response: Mapping[str, Any], record_count: int) -> dict[str, Any]:
    return {
        "provider": provider,
        "host": response["host"],
        "request_url": response["url"],
        "query": query,
        "retrieved_at_utc": response["retrieved_at_utc"],
        "response_sha256": response["sha256"],
        "response_bytes": response["byte_count"],
        "record_count": record_count,
        "status": "completed",
    }


def _validate_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Search query must contain 1–{MAX_QUERY_CHARS} characters")


def search_europe_pmc(
    client: PublicSourceClient, query: str = DEFAULT_EUROPE_PMC_QUERY, limit: int = 25
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _validate_query(query)
    if not 1 <= limit <= 100:
        raise ValueError("Europe PMC page size must be between 1 and 100")
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode({
        "query": query, "format": "json", "pageSize": str(limit), "resultType": "core",
    })
    response = client.get(url)
    try:
        payload = json.loads(response["body"])
        if not isinstance(payload, dict):
            raise ValueError("top-level response must be an object")
        records = _europe_pmc_records(payload)
        search = _search_run("europe_pmc", query, response, len(records))
        candidates = _build_candidates("europe_pmc", "article_for_review", records, search)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, AttributeError, RecursionError) as exc:
        raise InvalidSourceResponse("europe_pmc", response, str(exc)) from exc
    return candidates, search


def search_crossref(
    client: PublicSourceClient, query: str = DEFAULT_CROSSREF_QUERY, limit: int = 25
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _validate_query(query)
    if not 1 <= limit <= 100:
        raise ValueError("Crossref rows must be between 1 and 100")
    url = "https://api.crossref.org/works?" + urlencode({
        "query.bibliographic": query, "rows": str(limit),
    })
    response = client.get(url)
    try:
        payload = json.loads(response["body"])
        if not isinstance(payload, dict):
            raise ValueError("top-level response must be an object")
        records = _crossref_records(payload)
        search = _search_run("crossref", query, response, len(records))
        candidates = _build_candidates("crossref", "article_for_review", records, search)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, AttributeError, RecursionError) as exc:
        raise InvalidSourceResponse("crossref", response, str(exc)) from exc
    return candidates, search


def merge_candidates(*candidate_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge on any shared ID, but preserve conflicting DOI aliases as unresolved."""
    candidate_count = sum(len(group) for group in candidate_groups)
    if candidate_count > MAX_REGISTRY_CANDIDATES:
        raise ValueError(f"Candidate registry exceeds the {MAX_REGISTRY_CANDIDATES}-candidate limit")
    candidates = [
        json.loads(json.dumps(candidate))
        for group in candidate_groups for candidate in group
    ]
    candidates.sort(key=lambda item: item["candidate_id"])
    ids = [
        {
            "doi": normalize_doi(item.get("identifiers", {}).get("doi")),
            "pmcid": normalize_pmcid(item.get("identifiers", {}).get("pmcid")),
            "pmid": (item.get("identifiers", {}).get("pmid")
                     if str(item.get("identifiers", {}).get("pmid") or "").isdigit() else None),
        }
        for item in candidates
    ]

    # A DOI-less record linked to different DOI families through any identifier
    # is ambiguous; do not attach it based on identifier priority or row order.
    ambiguous_identifierless: set[int] = set()
    for index, current in enumerate(ids):
        if current["doi"]:
            continue
        linked_dois: set[str] = set()
        for id_type in ("pmcid", "pmid"):
            value = current[id_type]
            if value:
                linked_dois.update(
                    other["doi"] for other in ids
                    if other["doi"] and other[id_type] == value
                )
        if len(linked_dois) > 1:
            ambiguous_identifierless.add(index)

    parents = list(range(len(candidates)))
    members = {index: [index] for index in range(len(candidates))}

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def note_unresolved(left: int, right: int, reason: str) -> None:
        left_ref = f"{reason}:{candidates[right]['candidate_id']}"
        right_ref = f"{reason}:{candidates[left]['candidate_id']}"
        for index, reference in ((left, left_ref), (right, right_ref)):
            relationships = candidates[index].setdefault("work_family", {}).setdefault(
                "duplicate_relationships", []
            )
            if reference not in relationships:
                relationships.append(reference)
            candidates[index]["work_family"]["independent_status"] = "unresolved"

    edges: list[tuple[int, int, int, str, str]] = []
    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            shared = [
                kind for kind in ("doi", "pmcid", "pmid")
                if ids[left][kind] and ids[left][kind] == ids[right][kind]
            ]
            if not shared:
                continue
            if ids[left]["doi"] and ids[right]["doi"] and ids[left]["doi"] != ids[right]["doi"]:
                note_unresolved(left, right, "conflicting_doi")
                continue
            if ((left in ambiguous_identifierless and ids[right]["doi"])
                    or (right in ambiguous_identifierless and ids[left]["doi"])):
                note_unresolved(left, right, "ambiguous_identifier_overlap")
                continue
            strongest = shared[0]
            priority = {"doi": 0, "pmcid": 1, "pmid": 2}[strongest]
            edges.append((priority, left, right, strongest, ids[left][strongest]))

    for _, left, right, shared_type, shared_value in sorted(edges):
        left_root, right_root = root(left), root(right)
        if left_root == right_root:
            continue
        left_dois = {ids[index]["doi"] for index in members[left_root] if ids[index]["doi"]}
        right_dois = {ids[index]["doi"] for index in members[right_root] if ids[index]["doi"]}
        if left_dois and right_dois and left_dois != right_dois:
            note_unresolved(left, right, "conflicting_doi")
            continue
        left_is_ambiguous = any(index in ambiguous_identifierless for index in members[left_root])
        right_is_ambiguous = any(index in ambiguous_identifierless for index in members[right_root])
        if ((left_is_ambiguous and right_dois)
                or (right_is_ambiguous and left_dois)):
            note_unresolved(left, right, "ambiguous_identifier_overlap")
            continue
        # Keep union order stable, independent of input-group ordering.
        first, second = sorted((left_root, right_root))
        parents[second] = first
        members[first] = members[first] + members.pop(second)

    groups: dict[int, list[int]] = {}
    for index in range(len(candidates)):
        groups.setdefault(root(index), []).append(index)

    result = []
    for group_indices in groups.values():
        combined = candidates[group_indices[0]]
        source_groups = [
            source
            for index in group_indices
            for source in candidates[index].get("source_records", [])
        ]
        combined["source_records"] = []
        seen_sources: set[tuple[Any, ...]] = set()
        for index in group_indices:
            candidate = candidates[index]
            for kind in candidate.get("candidate_kinds", []):
                if kind not in combined["candidate_kinds"]:
                    combined["candidate_kinds"].append(kind)
            if not combined.get("title") and candidate.get("title"):
                combined["title"] = candidate["title"]
            for id_type, value in candidate.get("identifiers", {}).items():
                if value and not combined["identifiers"].get(id_type):
                    combined["identifiers"][id_type] = value
            combined["blockers"] = list(dict.fromkeys(
                combined.get("blockers", []) + candidate.get("blockers", [])
            ))
            for relationship in candidate.get("work_family", {}).get("duplicate_relationships", []):
                if relationship not in combined["work_family"]["duplicate_relationships"]:
                    combined["work_family"]["duplicate_relationships"].append(relationship)
        for source in source_groups:
            identity = (
                source.get("provider"), source.get("api_url"),
                source.get("response_sha256"), source.get("record_ordinal"),
            )
            if identity not in seen_sources:
                seen_sources.add(identity)
                combined["source_records"].append(source)
        combined["work_family"]["key"] = canonical_work_key(combined["identifiers"])
        result.append(combined)
    return sorted(result, key=lambda item: item["candidate_id"])


def empty_registry() -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_VERSION,
        "updated_utc": utc_now(),
        "workflow_status": "not_run",
        "scope": "developer_exposed_public_source_candidates_only",
        "searches": [],
        "candidates": [],
    }


def registry_with_search(
    candidates: list[dict[str, Any]], searches: list[dict[str, Any]], *, updated_utc: str | None = None
) -> dict[str, Any]:
    if len(searches) > MAX_REGISTRY_SEARCHES:
        raise ValueError(f"Candidate registry exceeds the {MAX_REGISTRY_SEARCHES}-search limit")
    if not searches and candidates:
        raise ValueError("Candidates cannot be recorded without a source search")
    return {
        "schema_version": REGISTRY_VERSION,
        "updated_utc": updated_utc or utc_now(),
        "workflow_status": (
            "not_run" if not searches else
            "completed" if all(s.get("status") == "completed" for s in searches) else "incomplete"
        ),
        "scope": "developer_exposed_public_source_candidates_only",
        "searches": searches,
        "candidates": merge_candidates(candidates),
    }


def validate_registry_document(registry: Mapping[str, Any]) -> None:
    """Validate the public registry schema and its cross-field safety rules."""
    if not isinstance(registry, Mapping):
        raise ValueError("Registry must be an object")

    def fields(value: Any, required: set[str], allowed: set[str], label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{label} must be an object")
        missing = required - set(value)
        if missing:
            raise ValueError(f"{label} is missing required fields: {', '.join(sorted(missing))}")
        if set(value) - allowed:
            raise ValueError(f"{label} contains an unsupported field")
        return value

    def text_or_none(value: Any, label: str) -> None:
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{label} must be a string or null")

    def timestamp(value: Any, label: str, *, nullable: bool = False) -> None:
        if value is None and nullable:
            return
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a date-time string")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{label} must be a date-time string") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{label} must include a timezone")

    def digest(value: Any, label: str, *, nullable: bool = False) -> None:
        if value is None and nullable:
            return
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")

    def nonnegative_integer(value: Any, label: str, *, nullable: bool = False) -> None:
        if value is None and nullable:
            return
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{label} must be a nonnegative integer")

    registry_keys = {"schema_version", "updated_utc", "workflow_status", "scope", "searches", "candidates"}
    fields(registry, registry_keys, registry_keys, "Registry")
    if type(registry["schema_version"]) is not int or registry["schema_version"] != REGISTRY_VERSION:
        raise ValueError("Unsupported candidate registry schema version")
    timestamp(registry["updated_utc"], "Registry updated_utc")
    if registry["scope"] != "developer_exposed_public_source_candidates_only":
        raise ValueError("Candidate registry scope is missing or unsafe")
    workflow_status = registry["workflow_status"]
    if not isinstance(workflow_status, str) or workflow_status not in {
        "not_run", "completed", "incomplete", "blocked_before_source_response",
    }:
        raise ValueError("Invalid candidate registry workflow status")
    searches = registry["searches"]
    candidates = registry["candidates"]
    if not isinstance(searches, list) or not isinstance(candidates, list):
        raise ValueError("Candidate registry lists are malformed")
    if len(searches) > MAX_REGISTRY_SEARCHES:
        raise ValueError(f"Candidate registry exceeds the {MAX_REGISTRY_SEARCHES}-search limit")
    if len(candidates) > MAX_REGISTRY_CANDIDATES:
        raise ValueError(f"Candidate registry exceeds the {MAX_REGISTRY_CANDIDATES}-candidate limit")

    provider_hosts = {
        "europe_pmc": "www.ebi.ac.uk",
        "crossref": "api.crossref.org",
        "pubmed": "eutils.ncbi.nlm.nih.gov",
        "pmc": "pmc.ncbi.nlm.nih.gov",
    }
    search_keys = {
        "provider", "host", "request_url", "query", "retrieved_at_utc",
        "response_sha256", "response_bytes", "record_count", "status", "failure_code",
    }
    search_required = {"provider", "host", "status", "response_sha256", "record_count"}
    allowed_search_statuses = {
        "completed", "transport_failed_before_http_response", "blocked", "provider_error",
        "http_error", "response_rejected", "invalid_response",
    }
    for index, search in enumerate(searches):
        label = f"Search record {index}"
        fields(search, search_required, search_keys, label)
        if (not isinstance(search["provider"], str)
                or search["provider"] not in provider_hosts
                or not isinstance(search["host"], str)
                or provider_hosts[search["provider"]] != search["host"]):
            raise ValueError("Search provider and host do not match")
        if search["host"] not in ALLOWED_SOURCE_HOSTS:
            raise ValueError("Search record is outside the approved host list")
        if not isinstance(search["status"], str) or search["status"] not in allowed_search_statuses:
            raise ValueError("Invalid search status")
        request_url = search.get("request_url")
        text_or_none(request_url, f"{label} request_url")
        if request_url is not None and validate_source_url(request_url) != search["host"]:
            raise ValueError("Search URL and recorded host do not match")
        text_or_none(search.get("query"), f"{label} query")
        timestamp(search.get("retrieved_at_utc"), f"{label} retrieved_at_utc", nullable=True)
        text_or_none(search.get("failure_code"), f"{label} failure_code")
        status = search["status"]
        if status == "completed":
            if request_url is None:
                raise ValueError("Completed search must record its request URL")
            timestamp(search.get("retrieved_at_utc"), f"{label} retrieved_at_utc")
            digest(search["response_sha256"], f"{label} response_sha256")
            nonnegative_integer(search.get("response_bytes"), f"{label} response_bytes")
            nonnegative_integer(search["record_count"], f"{label} record_count")
        elif status == "invalid_response":
            if request_url is None:
                raise ValueError("Invalid response must retain its source URL")
            timestamp(search.get("retrieved_at_utc"), f"{label} retrieved_at_utc")
            digest(search["response_sha256"], f"{label} response_sha256")
            nonnegative_integer(search.get("response_bytes"), f"{label} response_bytes")
            if search["record_count"] is not None:
                raise ValueError("Invalid response cannot claim a result count")
        else:
            if (search["response_sha256"] is not None
                    or search.get("response_bytes") is not None
                    or search["record_count"] is not None):
                raise ValueError("Failed search cannot claim response content or a result count")
            if not isinstance(search.get("failure_code"), str) or not search["failure_code"]:
                raise ValueError("Failed search must identify its failure code")

    if workflow_status == "not_run":
        if searches or candidates:
            raise ValueError("A not_run registry cannot contain searches or candidates")
    elif not searches:
        raise ValueError("A registry with searches or candidates must include a search record")
    elif workflow_status == "completed" and any(item["status"] != "completed" for item in searches):
        raise ValueError("Completed workflow cannot contain a failed or invalid search")
    elif workflow_status == "incomplete" and all(item["status"] == "completed" for item in searches):
        raise ValueError("Incomplete workflow must contain a failed or invalid search")
    elif workflow_status == "blocked_before_source_response":
        if candidates or any(item["status"] != "transport_failed_before_http_response" for item in searches):
            raise ValueError("Blocked-before-response workflow must contain only transport failures")

    candidate_keys = {
        "candidate_id", "candidate_kinds", "title", "identifiers", "work_family",
        "source_records", "original_source", "correction_source", "mathematical_relationship",
        "preliminary_eligibility_v1_3", "independent_review_status", "exposure_status",
        "holdout_eligible", "blockers",
    }
    candidate_required = candidate_keys - {"original_source", "correction_source"}
    source_record_keys = {
        "provider", "api_url", "response_sha256", "record_ordinal",
        "record_content_sha256", "captured_source_version", "license",
        "related_identifiers", "reported_identifiers",
    }
    evidence_keys = {"identifier", "version", "content_sha256", "retrieval_status", "license_status"}
    for index, candidate in enumerate(candidates):
        label = f"Candidate {index}"
        fields(candidate, candidate_required, candidate_keys, label)
        if not isinstance(candidate["candidate_id"], str) or not re.fullmatch(r"[0-9a-f]{24}", candidate["candidate_id"]):
            raise ValueError(f"{label} candidate_id is malformed")
        kinds = candidate["candidate_kinds"]
        valid_kinds = {"correction_notice", "article_for_review", "ratio_relationship"}
        if (not isinstance(kinds, list)
                or any(not isinstance(item, str) or item not in valid_kinds for item in kinds)
                or len(kinds) != len(set(kinds))):
            raise ValueError(f"{label} candidate_kinds are malformed")
        if not isinstance(candidate["title"], str) or len(candidate["title"]) > 1000:
            raise ValueError(f"{label} title is malformed")
        identifiers = fields(candidate["identifiers"], set(), {"doi", "pmid", "pmcid"}, f"{label} identifiers")
        for identifier_type, identifier in identifiers.items():
            text_or_none(identifier, f"{label} {identifier_type}")
        family = fields(
            candidate["work_family"], {"key", "independent_status", "duplicate_relationships"},
            {"key", "independent_status", "duplicate_relationships"}, f"{label} work_family",
        )
        text_or_none(family["key"], f"{label} work_family.key")
        if (not isinstance(family["independent_status"], str)
                or family["independent_status"] not in {"unresolved", "confirmed_duplicate", "confirmed_distinct"}):
            raise ValueError(f"{label} work-family status is invalid")
        if (not isinstance(family["duplicate_relationships"], list)
                or any(not isinstance(item, str) for item in family["duplicate_relationships"])):
            raise ValueError(f"{label} duplicate relationships are malformed")
        if not isinstance(candidate["source_records"], list):
            raise ValueError(f"{label} source_records must be a list")
        for source_index, source in enumerate(candidate["source_records"]):
            source_label = f"{label} source record {source_index}"
            fields(source, {"provider", "api_url", "response_sha256", "record_ordinal"}, source_record_keys, source_label)
            if not isinstance(source["provider"], str) or source["provider"] not in provider_hosts:
                raise ValueError(f"{source_label} provider is invalid")
            if not isinstance(source["api_url"], str):
                raise ValueError(f"{source_label} api_url is required")
            if validate_source_url(source["api_url"]) != provider_hosts[source["provider"]]:
                raise ValueError(f"{source_label} provider and URL host do not match")
            digest(source["response_sha256"], f"{source_label} response_sha256")
            if (not isinstance(source["record_ordinal"], int)
                    or isinstance(source["record_ordinal"], bool)
                    or source["record_ordinal"] < 1):
                raise ValueError(f"{source_label} record_ordinal is invalid")
            if source.get("record_content_sha256") is not None:
                raise ValueError("Metadata search must not claim a full source content hash")
            text_or_none(source.get("captured_source_version"), f"{source_label} captured_source_version")
            text_or_none(source.get("license"), f"{source_label} license")
            reported = source.get("reported_identifiers")
            if reported is not None:
                reported = fields(reported, set(), {"doi", "pmid", "pmcid"}, f"{source_label} reported_identifiers")
                for identifier_type, identifier in reported.items():
                    text_or_none(identifier, f"{source_label} reported {identifier_type}")
            relations = source.get("related_identifiers")
            if relations is not None:
                if not isinstance(relations, list):
                    raise ValueError(f"{source_label} related_identifiers must be a list")
                for relation_index, relation in enumerate(relations):
                    relation_label = f"{source_label} related identifier {relation_index}"
                    relation = fields(relation, {"type", "identifier"}, {"type", "identifier"}, relation_label)
                    if not isinstance(relation["type"], str) or not isinstance(relation["identifier"], str):
                        raise ValueError(f"{relation_label} values must be strings")

        for evidence_name in ("original_source", "correction_source"):
            if evidence_name not in candidate or candidate[evidence_name] is None:
                continue
            evidence = fields(candidate[evidence_name], evidence_keys, evidence_keys, f"{label} {evidence_name}")
            text_or_none(evidence["identifier"], f"{label} {evidence_name} identifier")
            if not isinstance(evidence["version"], str):
                raise ValueError(f"{label} {evidence_name} version is required")
            digest(evidence["content_sha256"], f"{label} {evidence_name} content_sha256", nullable=True)
            if (not isinstance(evidence["retrieval_status"], str)
                    or evidence["retrieval_status"] not in {"not_retrieved", "metadata_only", "captured"}):
                raise ValueError(f"{label} {evidence_name} retrieval_status is invalid")
            if (not isinstance(evidence["license_status"], str)
                    or evidence["license_status"] not in {"not_assessed", "allowed", "restricted"}):
                raise ValueError(f"{label} {evidence_name} license_status is invalid")

        relation = fields(
            candidate["mathematical_relationship"],
            {"status", "numerator", "denominator", "reported_percent", "corrected_values", "scope"},
            {"status", "numerator", "denominator", "reported_percent", "corrected_values", "scope"},
            f"{label} mathematical_relationship",
        )
        if (not isinstance(relation["status"], str)
                or relation["status"] not in {"not_assessed", "arithmetic_match", "arithmetic_mismatch", "scope_ambiguous", "reproduced"}):
            raise ValueError(f"{label} mathematical status is invalid")
        for key in ("numerator", "denominator", "reported_percent", "scope"):
            text_or_none(relation[key], f"{label} mathematical_relationship.{key}")
        if relation["corrected_values"] is not None and not isinstance(relation["corrected_values"], Mapping):
            raise ValueError(f"{label} corrected_values must be an object or null")
        if relation["status"] == "reproduced":
            for key in ("numerator", "denominator", "reported_percent", "scope"):
                if not isinstance(relation[key], str) or not relation[key].strip():
                    raise ValueError(f"{label} reproduced relationship requires {key}")

            def require_captured_source(evidence_name: str) -> None:
                evidence = candidate.get(evidence_name)
                if (not isinstance(evidence, Mapping)
                        or evidence.get("retrieval_status") != "captured"
                        or not isinstance(evidence.get("version"), str)
                        or not evidence["version"].strip()
                        or evidence["version"] == "unverified"
                        or not isinstance(evidence.get("content_sha256"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", evidence["content_sha256"])):
                    raise ValueError(f"{label} reproduced relationship requires captured {evidence_name} evidence")

            require_captured_source("original_source")
            if "correction_notice" in kinds:
                if not isinstance(relation["corrected_values"], Mapping) or not relation["corrected_values"]:
                    raise ValueError(f"{label} reproduced correction requires corrected_values")
                require_captured_source("correction_source")
        if (not isinstance(candidate["preliminary_eligibility_v1_3"], str)
                or candidate["preliminary_eligibility_v1_3"] not in {"unknown", "ineligible", "pending_independent_review"}):
            raise ValueError(f"{label} preliminary eligibility is invalid")
        if not isinstance(candidate["independent_review_status"], str) or candidate["independent_review_status"] not in {
            "not_started", "pending", "rejected_for_development", "accepted_for_development_only",
        }:
            raise ValueError(f"{label} review status crosses the public registry boundary")
        if candidate["exposure_status"] != "developer_exposed" or candidate["holdout_eligible"] is not False:
            raise ValueError("Developer-discovered candidates cannot be marked untouched")
        if not isinstance(candidate["blockers"], list) or any(not isinstance(item, str) for item in candidate["blockers"]):
            raise ValueError(f"{label} blockers must be a string list")


def summarize_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    validate_registry_document(registry)
    candidates = registry.get("candidates") or []
    searches = registry.get("searches") or []
    return {
        "workflow_status": registry.get("workflow_status", "unknown"),
        "metadata_candidates": len(candidates),
        "all_recorded_search_responses_valid": bool(searches) and all(
            item.get("status") == "completed" for item in searches
        ),
        "correction_notice_candidates": sum(
            "correction_notice" in item.get("candidate_kinds", []) for item in candidates
        ),
        "source_verified_arithmetic_positives": 0,
        "independently_accepted_positives_in_this_registry": 0,
        "proposed_negative_relationships": 0,
        "independently_accepted_negative_relationships_in_this_registry": 0,
        "confirmed_independent_work_families_in_this_registry": 0,
        "untouched_holdout_cases_in_this_registry": 0,
        "limits": [
            "metadata discovery is not source verification",
            "candidate count includes only stored response records; a blocked or invalid search does not imply zero matches, and each request is page-limited",
            "all candidates found by this development workflow are exposed and cannot count as untouched holdout evidence",
            "qualification acceptance is maintained by the independent custodian, not this registry",
        ],
    }

