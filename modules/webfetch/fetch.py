"""URL validation, SSRF protection, and bounded HTTP fetching."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from .errors import FetchError

MAX_URL_LENGTH = 2048
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}

PRIVATE_ADDRESS_ERROR = "refusing to fetch a private or reserved address."
BLOCKED_HOST_ERROR = "blocked by plugin config."

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CHALLENGE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)

ACCEPT_HEADERS = {
    "markdown": "text/markdown;q=1.0, text/x-markdown;q=0.9, text/plain;q=0.8, text/html;q=0.7, */*;q=0.1",
    "text": "text/plain;q=1.0, text/markdown;q=0.9, text/html;q=0.8, */*;q=0.1",
}

_ADDRESS = ipaddress.IPv4Address | ipaddress.IPv6Address
_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([\w.:-]+)", re.IGNORECASE)

# ``is_global`` alone lets multicast and NAT64 through, so the explicit ranges
# are checked first and act as the authoritative deny list.
BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("2002::/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)


@dataclass(frozen=True)
class FetchedPage:
    """A decoded response body together with its content type."""

    url: str
    content_type: str
    text: str


def mime_of(content_type: str) -> str:
    """Return the lowercased MIME type without parameters."""
    return content_type.split(";", 1)[0].strip().lower()


def is_textual(content_type: str) -> bool:
    """Report whether a content type can be handed to the model as text."""
    mime = mime_of(content_type)
    if not mime or mime.startswith("text/"):
        return True
    if mime.startswith("image/"):
        return False
    if mime.endswith("+json") or mime.endswith("+xml"):
        return True
    return mime in {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-javascript",
    }


def is_html(content_type: str) -> bool:
    """Report whether a content type should go through HTML extraction."""
    return mime_of(content_type) in {"text/html", "application/xhtml+xml"}


def decode_body(body: bytes, content_type: str) -> str:
    """Decode a response body using the declared charset, then common fallbacks.

    A page that declares one encoding but contains a few invalid bytes must stay
    readable: after the strict attempts fail, the declared charset is retried
    with replacement instead of switching to a different encoding.

    Args:
        body: Raw response bytes.
        content_type: Response content type, possibly carrying a charset.

    Returns:
        The decoded text; invalid bytes are replaced rather than raised.
    """
    match = _CHARSET_RE.search(content_type)
    declared = match.group(1) if match else None

    strict = [declared] if declared else []
    strict.extend(("utf-8", "gb18030"))
    for encoding in strict:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    for encoding in (declared, "gb18030", "utf-8"):
        if not encoding:
            continue
        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


def _validate_shape(url: str) -> str:
    """Return the host of a well-formed http(s) URL.

    Args:
        url: URL to validate.

    Returns:
        The URL host.

    Raises:
        FetchError: If the URL is too long or lacks a usable scheme or host.
    """
    if len(url) > MAX_URL_LENGTH:
        raise FetchError("URL is too long.")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise FetchError("only http and https URLs are supported.")
    if not parts.hostname:
        raise FetchError("URL has no host.")
    return parts.hostname


def _parse_host(value: str) -> _ADDRESS | None:
    """Parse an IP literal, tolerating IPv6 zone suffixes."""
    try:
        return ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None


def _unwrap_mapped(address: _ADDRESS) -> _ADDRESS:
    """Return the embedded IPv4 address for IPv4-mapped IPv6 literals."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _is_blocked_address(value: str) -> bool:
    """Report whether a resolved address must not be contacted."""
    address = _parse_host(value)
    if address is None:
        return True
    address = _unwrap_mapped(address)
    for network in BLOCKED_NETWORKS:
        if address.version == network.version and address in network:
            return True
    return not address.is_global


def _configured_host(value: str) -> str:
    """Normalize a configured host entry, dropping any port."""
    raw = value.strip().lower()
    if not raw:
        return ""
    if "//" in raw:
        return (urlsplit(raw).hostname or "").lower()
    return (urlsplit("//" + raw).hostname or "").lower()


def _host_matches(host: str, blocked_hosts: Sequence[str]) -> bool:
    """Report whether a host matches the configured block list.

    A match is an exact host or a subdomain; ``evil-internal.corp`` must not
    match ``internal.corp``.
    """
    candidate = host.lower().rstrip(".")
    for value in blocked_hosts:
        blocked = _configured_host(value)
        if not blocked:
            continue
        if candidate == blocked or candidate.endswith("." + blocked):
            return True
    return False


async def _resolve(host: str) -> list[str]:
    """Resolve a host to all of its addresses.

    Args:
        host: Hostname to resolve.

    Returns:
        The resolved address strings.

    Raises:
        FetchError: If resolution fails or returns nothing.
    """
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError("cannot resolve host.") from exc
    addresses = [str(info[4][0]).split("%", 1)[0] for info in infos]
    if not addresses:
        raise FetchError("cannot resolve host.")
    return addresses


async def ensure_public_url(url: str, blocked_hosts: Sequence[str] = ()) -> None:
    """Reject URLs that point at private, reserved, or configured-blocked hosts.

    Args:
        url: Target URL to validate.
        blocked_hosts: Extra hostnames or host suffixes to refuse.

    Raises:
        FetchError: If the scheme is unsupported, the host is blocked, the host
            cannot be resolved, or any resolved address is not globally routable.
    """
    host = _validate_shape(url)
    if blocked_hosts and _host_matches(host, blocked_hosts):
        raise FetchError(BLOCKED_HOST_ERROR)

    literal = _parse_host(host)
    addresses = [str(literal)] if literal is not None else await _resolve(host)
    for address in addresses:
        if _is_blocked_address(address):
            raise FetchError(PRIVATE_ADDRESS_ERROR)


async def fetch_page(
    url: str,
    *,
    timeout: int,
    fmt: str,
    blocked_hosts: Sequence[str] = (),
    client: httpx.AsyncClient | None = None,
) -> FetchedPage:
    """Fetch a URL and return its decoded body.

    Args:
        url: Target URL.
        timeout: Read timeout in seconds.
        fmt: Output format, used to pick the Accept header.
        blocked_hosts: Extra hostnames or host suffixes to refuse.
        client: Optional preconfigured client, mainly for tests.

    Returns:
        The final URL, content type, and decoded text.

    Raises:
        FetchError: On validation, network, size, status, or content type failures.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": ACCEPT_HEADERS.get(fmt, ACCEPT_HEADERS["markdown"]),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }
    request_timeout = httpx.Timeout(10.0, read=float(timeout), write=10.0, pool=10.0)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(trust_env=True, follow_redirects=False)

    try:
        redirects = 0
        challenge_retried = False
        current = url
        while True:
            await ensure_public_url(current, blocked_hosts)
            try:
                async with client.stream("GET", current, headers=headers, timeout=request_timeout) as response:
                    location = response.headers.get("location")
                    if response.status_code in REDIRECT_STATUSES and location:
                        redirects += 1
                        if redirects > MAX_REDIRECTS:
                            raise FetchError("too many redirects.")
                        current = urljoin(current, location)
                        continue
                    if (
                        response.status_code == 403
                        and response.headers.get("cf-mitigated") == "challenge"
                        and not challenge_retried
                    ):
                        challenge_retried = True
                        headers = {**headers, "User-Agent": CHALLENGE_USER_AGENT}
                        continue
                    if response.status_code >= 400:
                        raise FetchError(f"HTTP {response.status_code}.")

                    declared = response.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > MAX_BYTES:
                        raise FetchError("response exceeds 5 MB limit.")

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise FetchError("response exceeds 5 MB limit.")
                        chunks.append(chunk)

                    body = b"".join(chunks)
                    content_type = response.headers.get("content-type", "")
                    if not is_textual(content_type):
                        raise FetchError(f"unsupported content type: {mime_of(content_type) or 'unknown'}.")
                    return FetchedPage(
                        url=str(response.url),
                        content_type=content_type,
                        text=decode_body(body, content_type),
                    )
            except httpx.TimeoutException as exc:
                raise FetchError(f"request timed out after {timeout}s.") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"request failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()
