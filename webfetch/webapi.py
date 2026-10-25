"""Web API for the toolkit view: pure helpers plus platform handlers."""

from __future__ import annotations

import re

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
