"""Content extraction and result formatting."""

from __future__ import annotations

import re
from html import unescape

import trafilatura

_HEAD_LIMIT = 65536
_TITLE_LIMIT = 200
_TITLE_OPEN_RE = re.compile(r"<title[^>]*>", re.IGNORECASE)
_TITLE_CLOSE = "</title>"
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def html_title(html: str) -> str:
    """Return the normalized document title, or an empty string.

    The lookup is linear and bounded: a page with thousands of unclosed
    ``<title>`` tags must not turn title extraction into quadratic work on the
    event loop.

    Args:
        html: Raw HTML.

    Returns:
        The collapsed ``<title>`` text truncated to 200 characters, or ``""``.
    """
    window = html[:_HEAD_LIMIT]
    match = _TITLE_OPEN_RE.search(window)
    if not match:
        return ""
    end = window.lower().find(_TITLE_CLOSE, match.end())
    if end == -1:
        return ""
    raw = window[match.end() : end]
    return _collapse(unescape(_TAG_RE.sub("", raw)))[:_TITLE_LIMIT]


def extract_content(html: str, fmt: str) -> str:
    """Extract the readable part of an HTML page.

    Args:
        html: Raw HTML.
        fmt: Either ``markdown`` or ``text``.

    Returns:
        The extracted content, or ``""`` when the page has no readable text.

    Raises:
        ImportError: If ``trafilatura`` is unavailable at import time.
    """
    output_format = "markdown" if fmt == "markdown" else "txt"
    result = trafilatura.extract(
        html,
        output_format=output_format,
        include_links=fmt == "markdown",
        include_tables=True,
        favor_precision=True,
    )
    return result.strip() if result else ""


def build_result(*, url: str, title: str, content: str, start: int, max_chars: int) -> str:
    """Format the tool result with a source header and continuation hint.

    Args:
        url: Final page URL.
        title: Page title, or an empty string.
        content: Extracted content.
        start: Requested character offset.
        max_chars: Maximum characters to return.

    Returns:
        The formatted tool result.
    """
    total = len(content)
    chunk = content[start : start + max_chars] if start < total else ""
    has_more = start + len(chunk) < total

    sections: list[str] = []
    if title:
        sections.append(f"# {title}")
    sections.append(chunk or "(no content)")

    footer = [f"URL: {url}"]
    if has_more:
        footer.append(
            f"[Content truncated: showed {len(chunk)} of {total} characters. "
            f"Call web_fetch with start={start + len(chunk)} to continue.]"
        )
    elif not chunk and total:
        footer.append(f"[start={start} is beyond the end; total length is {total} characters.]")
    return "\n\n".join(sections) + "\n\n---\n" + "\n".join(footer)
