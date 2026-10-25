"""HTTP fetching: bounded reads, MIME gating, redirects, and error mapping."""

import asyncio

import httpx
import pytest

from webfetch import fetch
from webfetch.errors import FetchError
from webfetch.fetch import fetch_page


@pytest.fixture
def allow_public(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(url: str, blocked_hosts=()) -> None:
        return None

    monkeypatch.setattr(fetch, "ensure_public_url", _noop)


def run_fetch(handler, *, url: str = "https://example.com/", timeout: int = 30, fmt: str = "markdown"):
    async def _run() -> fetch.FetchedPage:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_page(url, timeout=timeout, fmt=fmt, client=client)

    return asyncio.run(_run())


def test_returns_decoded_html(allow_public: None) -> None:
    page = run_fetch(
        lambda r: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><p>你好 world</p></body></html>",
        )
    )
    assert "你好 world" in page.text
    assert page.url == "https://example.com/"


def test_rejects_image_content_type(allow_public: None) -> None:
    with pytest.raises(FetchError, match="unsupported content type: image/png"):
        run_fetch(lambda r: httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG"))


def test_rejects_declared_oversize(allow_public: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "MAX_BYTES", 100)

    with pytest.raises(FetchError, match="exceeds 5 MB limit"):
        run_fetch(
            lambda r: httpx.Response(
                200,
                headers={"content-type": "text/plain", "content-length": "1000"},
                content=b"x",
            )
        )


def test_rejects_streamed_oversize(allow_public: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "MAX_BYTES", 10)

    with pytest.raises(FetchError, match="exceeds 5 MB limit"):
        run_fetch(
            lambda r: httpx.Response(
                200,
                headers={"content-type": "text/plain", "content-length": "5"},
                content=b"0123456789ABCDEF",
            )
        )


def test_maps_http_error(allow_public: None) -> None:
    with pytest.raises(FetchError, match="HTTP 404"):
        run_fetch(lambda r: httpx.Response(404, headers={"content-type": "text/html"}, text="missing"))


def test_follows_redirect(allow_public: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="done")

    page = run_fetch(handler, url="https://example.com/start")
    assert page.url == "https://example.com/final"
    assert page.text == "done"


def test_rejects_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    async def guard(url: str, blocked_hosts=()) -> None:
        if "internal" in url:
            raise FetchError(fetch.PRIVATE_ADDRESS_ERROR)

    monkeypatch.setattr(fetch, "ensure_public_url", guard)

    with pytest.raises(FetchError, match="private or reserved"):
        run_fetch(lambda r: httpx.Response(302, headers={"location": "http://internal.local/admin"}))


def test_limits_redirect_count(allow_public: None) -> None:
    with pytest.raises(FetchError, match="too many redirects"):
        run_fetch(lambda r: httpx.Response(302, headers={"location": "/loop"}))


def test_retries_cloudflare_challenge(allow_public: None) -> None:
    agents: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        agents.append(request.headers.get("user-agent", ""))
        if len(agents) == 1:
            return httpx.Response(403, headers={"cf-mitigated": "challenge"})
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="ok")

    assert run_fetch(handler).text == "ok"
    assert len(agents) == 2
    assert agents[0] != agents[1]


def test_maps_timeout(allow_public: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchError, match="timed out after 30s"):
        run_fetch(handler)


def test_decodes_gbk(allow_public: None) -> None:
    page = run_fetch(
        lambda r: httpx.Response(
            200,
            headers={"content-type": "text/plain; charset=gbk"},
            content="中文内容".encode("gbk"),
        )
    )
    assert page.text == "中文内容"


def test_accepts_text_without_content_type(allow_public: None) -> None:
    assert run_fetch(lambda r: httpx.Response(200, content=b"raw body")).text == "raw body"
