"""Web endpoints for the hotfix management view."""

from __future__ import annotations

from functools import partial
from typing import Any

from .runtime import HotfixRuntime


def normalize_selection(payload: object) -> list[str] | None:
    """Return deduplicated patch names, or ``None`` for a malformed request."""

    return normalize_names(payload, "selected")


def normalize_names(payload: object, field: str) -> list[str] | None:
    if not isinstance(payload, dict):
        return None
    selected = payload.get(field)
    if not isinstance(selected, list):
        return None
    names: list[str] = []
    seen: set[str] = set()
    for item in selected:
        if not isinstance(item, str):
            return None
        if item and item not in seen:
            seen.add(item)
            names.append(item)
    return names


def build_status(runtime: HotfixRuntime) -> dict[str, Any]:
    return runtime.status()


async def handle_status(plugin: Any) -> Any:
    from astrbot.api.web import error_response, json_response

    runtime = getattr(plugin, "_hotfix", None)
    if runtime is None:
        return error_response("hotfix runtime unavailable", status_code=503)
    return json_response(build_status(runtime))


async def handle_selection(plugin: Any) -> Any:
    from astrbot.api.web import error_response, json_response, request

    runtime = getattr(plugin, "_hotfix", None)
    if runtime is None:
        return error_response("hotfix runtime unavailable", status_code=503)
    if not runtime.status()["enabled"]:
        return error_response("hotfix is disabled", status_code=400)
    payload = await request.json(default=None)
    selected = normalize_selection(payload)
    if selected is None:
        return error_response("selected must be a list of strings", status_code=400)
    return json_response(runtime.set_selection(selected))


async def handle_refresh(plugin: Any) -> Any:
    from astrbot.api.web import error_response, json_response

    runtime = getattr(plugin, "_hotfix", None)
    if runtime is None:
        return error_response("hotfix runtime unavailable", status_code=503)
    if not runtime.status()["enabled"]:
        return error_response("hotfix is disabled", status_code=400)
    return json_response(runtime.refresh())


async def handle_update(plugin: Any) -> Any:
    from astrbot.api.web import error_response, json_response, request

    runtime = getattr(plugin, "_hotfix", None)
    if runtime is None:
        return error_response("hotfix runtime unavailable", status_code=503)
    if not runtime.status()["enabled"]:
        return error_response("hotfix is disabled", status_code=400)
    payload = await request.json(default=None)
    names = normalize_names(payload, "names")
    if names is None:
        return error_response("names must be a list of strings", status_code=400)
    return json_response(runtime.update(names))


def register_hotfix_routes(context: Any, plugin: Any, plugin_name: str) -> None:
    """Register status, selection and refresh endpoints under the plugin prefix."""

    context.register_web_api(
        f"/{plugin_name}/hotfix/status",
        partial(handle_status, plugin),
        ["GET"],
        "Hotfix status",
    )
    context.register_web_api(
        f"/{plugin_name}/hotfix/selection",
        partial(handle_selection, plugin),
        ["POST"],
        "Save hotfix selection",
    )
    context.register_web_api(
        f"/{plugin_name}/hotfix/refresh",
        partial(handle_refresh, plugin),
        ["POST"],
        "Refresh hotfix repository",
    )
    context.register_web_api(
        f"/{plugin_name}/hotfix/update",
        partial(handle_update, plugin),
        ["POST"],
        "Adopt the latest version of selected patches",
    )
