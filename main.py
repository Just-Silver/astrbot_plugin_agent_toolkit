from astrbot.api import logger, star


class Main(star.Star):
    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        logger.info("astrbot_plugin_agent_toolkit loaded")
