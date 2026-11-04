"""Fetch one web page for the add-job-by-URL feature, refusing local and private addresses."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

SCHEME_REASON = "Only http and https links are supported."
INVALID_REASON = "That is not a valid web address."
OWN_NETWORK_REASON = "This address is on your own network or computer, so it was not fetched."
NOT_FOUND_REASON = "The page was not found (404)."
BLOCKED_REASON = "The site blocked the request."
TIMEOUT_REASON = "The page did not load in time."
FAILED_REASON = "The page could not be fetched."

MAX_REDIRECTS = 5


@dataclass
class FetchResult:
    url: str
    status: int
    html: str
    truncated: bool


class FetchError(Exception):
    """A page could not be fetched; ``reason`` is a plain-language message."""

    def __init__(self, reason: str, refused: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.refused = refused


def _is_private(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return True
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified
            or ip.is_multicast or ip.is_reserved or not ip.is_global)


def check_url(url: str, *, resolver=socket.getaddrinfo) -> str | None:
    """Return None when the URL may be fetched, otherwise the plain reason it is refused."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return INVALID_REASON
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return SCHEME_REASON
    if not host:
        return INVALID_REASON
    if host == "localhost" or host.endswith(".localhost"):
        return OWN_NETWORK_REASON
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    if literal:
        return OWN_NETWORK_REASON if _is_private(host) else None
    try:
        infos = resolver(host, port or (443 if scheme == "https" else 80))
    except OSError:
        return None  # the fetch itself reports a name that does not resolve
    for info in infos:
        if _is_private(str(info[4][0])):
            return OWN_NETWORK_REASON
    return None


def _status_error(status: int) -> FetchError:
    if status == 404:
        return FetchError(NOT_FOUND_REASON)
    if status in (403, 429):
        return FetchError(BLOCKED_REASON)
    return FetchError(FAILED_REASON)


def fetch_page(url: str, *, transport: httpx.BaseTransport | None = None, resolver=socket.getaddrinfo,
               timeout: float = 15.0, max_bytes: int = 2_000_000) -> FetchResult:
    """GET a page, checking the address of the URL and of every redirect before any body is read."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; HireEmber)", "Accept": "text/html,*/*;q=0.8"}
    current = url
    try:
        with httpx.Client(transport=transport, timeout=timeout, follow_redirects=False,
                          headers=headers) as client:
            for _ in range(MAX_REDIRECTS + 1):
                refusal = check_url(current, resolver=resolver)
                if refusal:
                    raise FetchError(refusal, refused=True)
                with client.stream("GET", current) as response:
                    status = response.status_code
                    if 300 <= status < 400:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError(FAILED_REASON)
                        current = urljoin(current, location)
                        continue
                    if status >= 400:
                        raise _status_error(status)
                    body = bytearray()
                    truncated = False
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            del body[max_bytes:]
                            truncated = True
                            break
                    encoding = response.charset_encoding or "utf-8"
                    try:
                        html = bytes(body).decode(encoding, errors="replace")
                    except LookupError:
                        html = bytes(body).decode("utf-8", errors="replace")
                    return FetchResult(url=current, status=status, html=html, truncated=truncated)
    except FetchError:
        raise
    except httpx.TimeoutException:
        raise FetchError(TIMEOUT_REASON) from None
    except httpx.HTTPError:
        raise FetchError(FAILED_REASON) from None
    raise FetchError(FAILED_REASON)
