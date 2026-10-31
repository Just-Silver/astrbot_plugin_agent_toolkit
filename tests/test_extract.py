"""Content extraction and result formatting."""

import time

from modules.webfetch.extract import build_result, extract_content, html_title

ARTICLE = """
<html><head><title> demo 页面 </title></head><body>
<nav>首页 产品 关于我们</nav>
<article><h1>正文标题</h1>
<p>这是第一段正文，讲的是 AstrBot 的整体定位和使用方式，内容足够长。</p>
<p>这是第二段正文，继续补充细节，让正文有足够长度。</p></article>
<footer>版权所有 联系方式</footer></body></html>
"""


def test_title_is_normalized() -> None:
    assert html_title(ARTICLE) == "demo 页面"


def test_title_missing_returns_empty() -> None:
    assert html_title("<html><body>hi</body></html>") == ""


def test_extract_keeps_body_and_drops_navigation() -> None:
    content = extract_content(ARTICLE, "markdown")
    assert "正文标题" in content
    assert "这是第一段正文" in content
    assert "首页 产品 关于我们" not in content
    assert "版权所有" not in content


def test_extract_keeps_short_page() -> None:
    assert "只有一个短句" in extract_content("<html><body><p>只有一个短句</p></body></html>", "markdown")


def test_extract_returns_empty_when_no_text_nodes() -> None:
    assert extract_content("<html><body><div id='app'></div></body></html>", "markdown") == ""
    assert extract_content("<html><body><img src='a.jpg'></body></html>", "markdown") == ""
    assert extract_content("", "markdown") == ""


def test_extract_text_format_has_no_markdown_syntax() -> None:
    content = extract_content(ARTICLE, "text")
    assert "正文标题" in content
    assert "# " not in content


def test_result_includes_title_and_source() -> None:
    result = build_result(url="https://example.com/a", title="标题", content="正文", start=0, max_chars=8000)
    assert result.startswith("# 标题")
    assert "正文" in result
    assert "URL: https://example.com/a" in result
    assert "truncated" not in result


def test_result_truncates_and_points_to_next_start() -> None:
    result = build_result(url="https://example.com/a", title="", content="x" * 100, start=0, max_chars=40)
    assert "x" * 40 in result
    assert "showed 40 of 100 characters" in result
    assert "start=40" in result


def test_result_continues_from_start() -> None:
    result = build_result(url="https://example.com/a", title="", content="a" * 50 + "b" * 50, start=50, max_chars=40)
    assert "a" * 40 not in result
    assert "b" * 40 in result
    assert "start=90" in result


def test_result_reports_end_of_content() -> None:
    result = build_result(url="https://example.com/a", title="", content="short", start=10, max_chars=40)
    assert "(no content)" in result
    assert "beyond the end" in result
    assert "total length is 5 characters" in result


def test_result_with_large_max_chars_still_reports_exact_totals() -> None:
    content = "y" * 12000
    result = build_result(url="u", title="", content=content, start=0, max_chars=50000)
    assert "truncated" not in result
    assert content in result


def test_title_extraction_stays_fast_on_malformed_html() -> None:
    html = "<title>" * 8000 + "<p>正文</p>"
    started = time.perf_counter()
    html_title(html)
    assert time.perf_counter() - started < 0.1


def test_title_is_bounded() -> None:
    assert len(html_title("<title>" + "T" * 1_000_000 + "</title>")) <= 200
