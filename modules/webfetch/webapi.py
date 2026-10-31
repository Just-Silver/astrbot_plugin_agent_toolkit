"""Web API for the toolkit view: pure helpers plus platform handlers."""

from __future__ import annotations

import re
import time
from functools import partial

from .service import run_fetch

DEFAULT_MAX_CHARS = 8000
DEFAULT_TIMEOUT = 30
MAX_CHARS_RANGE = (1000, 50000)
TIMEOUT_RANGE = (5, 120)

_FINAL_URL_RE = re.compile(r"^URL: (.+)$", re.MULTILINE)
_TRUNCATED_MARK = "Content truncated"


def clamp_int(value: object, low: int, high: int, default: int) -> int:
    """Clamp a user-provided number into a range.

    Args:
        value: Raw value from the request.
        low: Inclusive lower bound.
        high: Inclusive upper bound.
        default: Value used when ``value`` is not an integer.

    Returns:
        The clamped integer, or ``default`` when parsing fails.
    """
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def normalize_test_request(payload: dict) -> tuple[str, int, int] | None:
    """Normalize a test-bench request body.

    Args:
        payload: Parsed JSON body.

    Returns:
        ``(url, max_chars, timeout)``, or ``None`` when the URL is empty.
    """
    url = str(payload.get("url") or "").strip()
    if not url:
        return None
    max_chars = clamp_int(payload.get("max_chars"), *MAX_CHARS_RANGE, default=DEFAULT_MAX_CHARS)
    timeout = clamp_int(payload.get("timeout"), *TIMEOUT_RANGE, default=DEFAULT_TIMEOUT)
    return url, max_chars, timeout


def build_test_result(output: str, elapsed_ms: float) -> dict:
    """Shape one fetch result for the dashboard.

    Args:
        output: Raw ``run_fetch`` return value.
        elapsed_ms: Wall-clock duration in milliseconds.

    Returns:
        The response body described by the spec.
    """
    match = _FINAL_URL_RE.search(output)
    return {
        "ok": not output.startswith("Error:"),
        "output": output,
        "elapsed_ms": round(elapsed_ms),
        "chars": len(output),
        "truncated": _TRUNCATED_MARK in output,
        "final_url": match.group(1).strip() if match else "",
    }


def collect_blocked_hosts(config: object) -> list[str]:
    """Read the configured host block list.

    Args:
        config: Plugin config mapping, possibly malformed.

    Returns:
        Non-empty host strings, or an empty list when the config is unusable.
    """
    if not isinstance(config, dict):
        return []
    raw = config.get("blocked_hosts", [])
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def collect_tools(func_list, package_prefix: str) -> list[dict]:
    """List the tools registered by this plugin.

    Args:
        func_list: Tool objects from the AstrBot tool manager.
        package_prefix: Module prefix owned by this plugin.

    Returns:
        Tool descriptors sorted by name.
    """
    tools: list[dict] = []
    for tool in func_list:
        module_path = str(getattr(tool, "handler_module_path", "") or "")
        if not module_path.startswith(package_prefix):
            continue
        tools.append(
            {
                "name": tool.name,
                "active": bool(getattr(tool, "active", True)),
                "description": getattr(tool, "description", ""),
                "parameters": getattr(tool, "parameters", {}),
            }
        )
    return sorted(tools, key=lambda item: item["name"])


async def list_tools(plugin) -> dict:
    """Return the tools this plugin registered.

    Args:
        plugin: The plugin instance, used for the module prefix and tool manager.

    Returns:
        A JSON response containing the tool descriptors.
    """
    from astrbot.api.web import json_response

    package_prefix = plugin.__class__.__module__.rsplit(".", 1)[0]
    func_list = plugin.context.get_llm_tool_manager().func_list
    return json_response({"tools": collect_tools(func_list, package_prefix)})


async def test_web_fetch(plugin) -> dict:
    """Run one fetch for the dashboard test bench.

    Args:
        plugin: The plugin instance. Reserved for future per-plugin defaults.

    Returns:
        A JSON response with the shaped result, or a 400 error response.
    """
    from astrbot.api.web import error_response, json_response, request

    payload = await request.json(default={})
    normalized = normalize_test_request(payload if isinstance(payload, dict) else {})
    if normalized is None:
        return error_response("url is required", status_code=400)

    url, max_chars, timeout = normalized
    started = time.perf_counter()
    output = await run_fetch(
        url,
        max_chars=max_chars,
        timeout=timeout,
        blocked_hosts=collect_blocked_hosts(plugin.config),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    return json_response(build_test_result(output, elapsed_ms))


def register_routes(context, plugin, plugin_name: str) -> None:
    """Register the toolkit view endpoints under the plugin prefix.

    Args:
        context: Plugin context providing ``register_web_api``.
        plugin: The plugin instance passed to the handlers.
        plugin_name: Plugin package name used as the route prefix.
    """
    context.register_web_api(
        f"/{plugin_name}/tools",
        partial(list_tools, plugin),
        ["GET"],
        "List plugin tools",
    )
    context.register_web_api(
        f"/{plugin_name}/tools/web_fetch/test",
        partial(test_web_fetch, plugin),
        ["POST"],
        "Run one web_fetch call",
    )
