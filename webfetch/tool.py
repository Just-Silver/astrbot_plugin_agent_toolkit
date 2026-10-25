"""The web_fetch agent tool."""

from __future__ import annotations

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from .service import SUPPORTED_FORMATS, run_fetch


@dataclass
class WebFetchTool(FunctionTool[AstrAgentContext]):
    """Fetch a web page and return its readable content."""

    name: str = "web_fetch"
    description: str = (
        "Read the main content of a web page and return it as Markdown or plain text. "
        "Use it when the user shares a link or asks about a specific page. "
        "Only http and https are supported. "
        "Long pages are truncated; call again with `start` to continue."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The http:// or https:// URL to read.",
                },
                "format": {
                    "type": "string",
                    "enum": list(SUPPORTED_FORMATS),
                    "description": "Output format. Defaults to markdown.",
                },
                "start": {
                    "type": "integer",
                    "description": "Character offset to start reading from. Defaults to 0.",
                },
            },
            "required": ["url"],
        }
    )
    max_chars: int = 8000
    timeout: int = 30
    blocked_hosts: list[str] = Field(default_factory=list)

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        """Fetch and extract one web page.

        Args:
            context: Current agent execution context.
            **kwargs: ``url`` (required), ``format``, and ``start``.

        Returns:
            Extracted content, or an ``Error: ...`` line describing the failure.
        """
        url = str(kwargs.get("url") or "").strip()
        fmt = str(kwargs.get("format") or "markdown").strip().lower()
        try:
            start = max(0, int(kwargs.get("start") or 0))
        except (TypeError, ValueError):
            start = 0
        return await run_fetch(
            url,
            fmt=fmt,
            start=start,
            max_chars=self.max_chars,
            timeout=self.timeout,
            blocked_hosts=self.blocked_hosts,
        )
