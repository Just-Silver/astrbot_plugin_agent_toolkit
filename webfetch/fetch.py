"""URL validation and SSRF protection."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Sequence
from urllib.parse import urlsplit

from .errors import FetchError

MAX_URL_LENGTH = 2048
PRIVATE_ADDRESS_ERROR = "refusing to fetch a private or reserved address."
BLOCKED_HOST_ERROR = "blocked by plugin config."

_Address = ipaddress.IPv4Address | ipaddress.IPv6Address

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


def _parse_host(value: str) -> _Address | None:
    """Parse an IP literal, tolerating IPv6 zone suffixes."""
    try:
        return ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None


def _unwrap_mapped(address: _Address) -> _Address:
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
