"""Content extraction and result formatting."""

from __future__ import annotations

import re

import trafilatura

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")


def _collapse(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def html_title(html: str) -> str:
    """Return the normalized document title, or an empty string.

    Args:
        html: Raw HTML.

    Returns:
        The collapsed ``<title>`` text, or ``""`` when absent.
    """
    match = _TITLE_RE.search(html)
    if not match:
        return ""
    return _collapse(_TAG_RE.sub("", match.group(1)))


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
