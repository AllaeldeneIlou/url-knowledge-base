from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from posixpath import normpath
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


class InvalidURLError(ValueError):
    """Raised when an input value cannot be treated as a supported URL."""


@dataclass(frozen=True)
class NormalizedURL:
    original_url: str
    canonical_url: str
    domain: str
    url_hash: str


def normalize_url(raw_url: str) -> NormalizedURL:
    """Normalize a single HTTP(S) URL into a deterministic canonical form."""
    original_url = raw_url
    candidate = raw_url.strip()

    if not candidate:
        raise InvalidURLError("URL is empty")

    parsed = urlsplit(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise InvalidURLError("URL must use http or https")

    if not parsed.hostname:
        raise InvalidURLError("URL is missing a host")

    host = parsed.hostname.lower().rstrip(".")
    if not host or " " in host:
        raise InvalidURLError("URL host is invalid")

    netloc = _normalize_netloc(scheme, host, parsed.port)
    path = _normalize_path(parsed.path)
    query = _normalize_query(parsed.query)

    canonical_url = urlunsplit((scheme, netloc, path, query, ""))
    return NormalizedURL(
        original_url=original_url,
        canonical_url=canonical_url,
        domain=host,
        url_hash=sha256(canonical_url.encode("utf-8")).hexdigest(),
    )


def _normalize_netloc(scheme: str, host: str, port: int | None) -> str:
    if port is None:
        return host
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return host
    return f"{host}:{port}"


def _normalize_path(path: str) -> str:
    if not path:
        return "/"

    normalized = normpath(path)
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if path.endswith("/") and not normalized.endswith("/"):
        normalized = f"{normalized}/"

    return quote(normalized, safe="/~:@!$&'()*+,;=")


def _normalize_query(query: str) -> str:
    if not query:
        return ""

    pairs = parse_qsl(query, keep_blank_values=True)
    pairs.sort()
    return urlencode(pairs, doseq=True)
