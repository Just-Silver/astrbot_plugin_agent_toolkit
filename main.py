"""Register the web_fetch tool for AstrBot agents."""

from __future__ import annotations

from astrbot.api import AstrBotConfig, logger, star

from .modules.webfetch.tool import WebFetchTool
from .modules.webfetch.webapi import register_routes

PLUGIN_NAME = "astrbot_plugin_agent_toolkit"
DEFAULT_MAX_CHARS = 8000
DEFAULT_TIMEOUT = 30


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class Main(star.Star):
    """Plugin entry point."""

    def __init__(self, context: star.Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context, config)
        self.config = config or {}
        # The view must stay reachable even when the tool is disabled, so routes
        # are registered before the enabled check.
        register_routes(self.context, self, PLUGIN_NAME)
        if not self.config.get("enabled", True):
            logger.info("web_fetch is disabled by plugin config.")
            return
        self.context.add_llm_tools(
            WebFetchTool(
                max_chars=_positive_int(self.config.get("max_chars"), DEFAULT_MAX_CHARS),
                timeout=_positive_int(self.config.get("timeout"), DEFAULT_TIMEOUT),
                blocked_hosts=[str(item) for item in self.config.get("blocked_hosts", []) if str(item).strip()],
            )
        )

    async def terminate(self) -> None:
        """Release resources. The tool holds none."""
