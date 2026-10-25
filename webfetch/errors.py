"""Errors that are safe to report back to the agent."""


class FetchError(Exception):
    """A fetch failure whose message can be shown to the model as-is."""
