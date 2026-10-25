"""Business orchestration for the web_fetch tool."""

from __future__ import annotations

from collections.abc import Sequence

from .errors import FetchError
from .extract import build_result, extract_content, html_title
from .fetch import fetch_page, is_html

SUPPORTED_FORMATS = ("markdown", "text")


async def run_fetch(
    url: str,
    *,
    fmt: str = "markdown",
    start: int = 0,
    max_chars: int = 8000,
    timeout: int = 30,
    blocked_hosts: Sequence[str] = (),
) -> str:
    """Fetch one page and render it for the model.

    Args:
        url: Target URL.
        fmt: ``markdown`` or ``text``; anything else falls back to markdown.
        start: Character offset for continuation reads.
        max_chars: Maximum characters to return.
        timeout: Read timeout in seconds.
        blocked_hosts: Extra hosts refused by the SSRF guard.

    Returns:
        The rendered result, or an ``Error: ...`` line describing the failure.
    """
    if not url.strip():
        return "Error: url is required."
    if fmt not in SUPPORTED_FORMATS:
        fmt = "markdown"
    start = max(0, start)

    try:
        page = await fetch_page(url, timeout=timeout, fmt=fmt, blocked_hosts=blocked_hosts)
    except FetchError as exc:
        return f"Error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: request failed: {exc}"

    if is_html(page.content_type):
        content = extract_content(page.text, fmt)
        if not content:
            return "Error: no readable content found in this page."
        title = html_title(page.text)
    else:
        content = page.text.strip()
        title = ""

    return build_result(
        url=page.url,
        title=title,
        content=content,
        start=start,
        max_chars=max_chars,
    )
