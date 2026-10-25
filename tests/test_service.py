"""Service orchestration must map every failure to a model-readable string."""

import asyncio

import pytest

from webfetch import service
from webfetch.errors import FetchError
from webfetch.fetch import FetchedPage


def run(url: str = "https://example.com/", **kwargs) -> str:
    return asyncio.run(service.run_fetch(url, **kwargs))


def test_missing_url_reports_error() -> None:
    assert run("").startswith("Error: url is required.")


def test_html_page_returns_title_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(url: str, **kwargs) -> FetchedPage:
        return FetchedPage(
            url=url,
            content_type="text/html",
            text="<html><head><title>T</title></head><body><p>正文内容足够长以便被识别为主要内容。</p></body></html>",
        )

    monkeypatch.setattr(service, "fetch_page", fake)
    result = run()
    assert result.startswith("# T")
    assert "正文内容足够长" in result


def test_non_html_page_is_returned_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(url: str, **kwargs) -> FetchedPage:
        return FetchedPage(url=url, content_type="application/json", text='{"a": 1}')

    monkeypatch.setattr(service, "fetch_page", fake)
    assert '{"a": 1}' in run()


def test_empty_extraction_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(url: str, **kwargs) -> FetchedPage:
        return FetchedPage(url=url, content_type="text/html", text="<html><body></body></html>")

    monkeypatch.setattr(service, "fetch_page", fake)
    assert run() == "Error: no readable content found in this page."


def test_fetch_error_is_prefixed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(url: str, **kwargs) -> FetchedPage:
        raise FetchError("HTTP 404.")

    monkeypatch.setattr(service, "fetch_page", fake)
    assert run() == "Error: HTTP 404."


def test_unsupported_format_falls_back_to_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    async def fake(url: str, **kwargs) -> FetchedPage:
        seen.update(kwargs)
        return FetchedPage(url=url, content_type="text/plain", text="x")

    monkeypatch.setattr(service, "fetch_page", fake)
    run(fmt="html")
    assert seen["fmt"] == "markdown"


def test_negative_start_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(url: str, **kwargs) -> FetchedPage:
        return FetchedPage(url=url, content_type="text/plain", text="abcdef")

    monkeypatch.setattr(service, "fetch_page", fake)
    assert "abcdef" in run(start=-5)


def test_unexpected_exception_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(url: str, **kwargs) -> FetchedPage:
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "fetch_page", fake)
    assert run() == "Error: request failed: boom"
