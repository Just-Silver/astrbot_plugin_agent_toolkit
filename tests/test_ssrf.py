"""URL validation must reject every non-public destination."""

import asyncio
import socket

import pytest

from modules.webfetch import fetch
from modules.webfetch.errors import FetchError


def _check(url: str, blocked: tuple[str, ...] = ()) -> None:
    asyncio.run(fetch.ensure_public_url(url, blocked))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:6185/",
        "http://10.0.0.5/",
        "http://172.17.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
        "http://224.0.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[ff02::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[64:ff9b::1]/",
    ],
)
def test_rejects_non_public_addresses(url: str) -> None:
    with pytest.raises(FetchError, match="private or reserved"):
        _check(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x/", "gopher://x/"])
def test_rejects_unsupported_scheme(url: str) -> None:
    with pytest.raises(FetchError, match="only http and https"):
        _check(url)


def test_rejects_url_without_host() -> None:
    with pytest.raises(FetchError, match="no host"):
        _check("http:///path")


def test_rejects_overlong_url() -> None:
    with pytest.raises(FetchError, match="too long"):
        _check("https://example.com/" + "a" * 3000)


def test_rejects_domain_resolving_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))],
    )
    with pytest.raises(FetchError, match="private or reserved"):
        _check("http://internal.example/")


def test_rejects_when_any_resolved_address_is_private(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ],
    )
    with pytest.raises(FetchError, match="private or reserved"):
        _check("http://mixed.example/")


def test_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr(fetch.socket, "getaddrinfo", boom)
    with pytest.raises(FetchError, match="cannot resolve"):
        _check("http://nowhere.invalid/")


def test_rejects_blocked_host_and_subdomain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    with pytest.raises(FetchError, match="blocked"):
        _check("https://internal.corp/x", ("internal.corp",))
    with pytest.raises(FetchError, match="blocked"):
        _check("https://a.internal.corp/x", ("internal.corp",))


def test_does_not_match_blocked_host_suffix_without_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    _check("https://evil-internal.corp/x", ("internal.corp",))


def test_blocked_host_ignores_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    with pytest.raises(FetchError, match="blocked"):
        _check("https://internal.corp:8080/x", ("internal.corp:8080",))


def test_allows_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetch.socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    _check("https://example.com/page")
