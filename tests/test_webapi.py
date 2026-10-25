"""Pure logic for the toolkit web API: clamping, request normalization, result shaping."""

from webfetch.webapi import (
    DEFAULT_MAX_CHARS,
    DEFAULT_TIMEOUT,
    MAX_CHARS_RANGE,
    TIMEOUT_RANGE,
    build_test_result,
    clamp_int,
    collect_blocked_hosts,
    collect_tools,
    normalize_test_request,
)


class FakeTool:
    def __init__(self, name, active=True, module="astrbot_plugin_agent_toolkit.webfetch.tool"):
        self.name = name
        self.active = active
        self.handler_module_path = module
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}


def test_clamp_int_below_low() -> None:
    assert clamp_int(1, 1000, 50000, DEFAULT_MAX_CHARS) == 1000


def test_clamp_int_above_high() -> None:
    assert clamp_int(99999, 1000, 50000, DEFAULT_MAX_CHARS) == 50000


def test_clamp_int_non_numeric() -> None:
    assert clamp_int("abc", 5, 120, DEFAULT_TIMEOUT) == DEFAULT_TIMEOUT
    assert clamp_int(None, 5, 120, DEFAULT_TIMEOUT) == DEFAULT_TIMEOUT


def test_normalize_empty_url() -> None:
    assert normalize_test_request({"url": "   "}) is None
    assert normalize_test_request({}) is None


def test_normalize_defaults() -> None:
    assert normalize_test_request({"url": "https://example.com"}) == (
        "https://example.com",
        DEFAULT_MAX_CHARS,
        DEFAULT_TIMEOUT,
    )


def test_normalize_clamps_out_of_range() -> None:
    url, max_chars, timeout = normalize_test_request({"url": "https://example.com", "max_chars": 999999, "timeout": 1})
    assert max_chars == MAX_CHARS_RANGE[1]
    assert timeout == TIMEOUT_RANGE[0]


def test_build_test_result_normal() -> None:
    output = "# Title\n\nbody\n\n---\nURL: https://example.com/"
    result = build_test_result(output, 420.4)
    assert result == {
        "ok": True,
        "output": output,
        "elapsed_ms": 420,
        "chars": len(output),
        "truncated": False,
        "final_url": "https://example.com/",
    }


def test_build_test_result_error_output() -> None:
    result = build_test_result("Error: HTTP 404.", 12)
    assert result["ok"] is False
    assert result["final_url"] == ""


def test_build_test_result_truncated() -> None:
    output = "body\n\n---\nURL: https://example.com/a\n[Content truncated: showed 50 of 156 characters.]"
    result = build_test_result(output, 30)
    assert result["truncated"] is True
    assert result["final_url"] == "https://example.com/a"


def test_collect_tools_filters_other_plugins() -> None:
    tools = [
        FakeTool("web_fetch"),
        FakeTool("other_tool", module="other_plugin.tool"),
        FakeTool("no_module", module=None),
    ]
    names = [tool["name"] for tool in collect_tools(tools, "astrbot_plugin_agent_toolkit")]
    assert names == ["web_fetch"]


def test_collect_tools_sorted_by_name() -> None:
    tools = [FakeTool("zeta"), FakeTool("alpha"), FakeTool("mid")]
    names = [tool["name"] for tool in collect_tools(tools, "astrbot_plugin_agent_toolkit")]
    assert names == ["alpha", "mid", "zeta"]


def test_collect_tools_maps_fields() -> None:
    tool = collect_tools([FakeTool("web_fetch")], "astrbot_plugin_agent_toolkit")[0]
    assert tool["active"] is True
    assert tool["description"] == "web_fetch tool"
    assert tool["parameters"] == {"type": "object", "properties": {}}


def test_collect_blocked_hosts_returns_clean_list() -> None:
    assert collect_blocked_hosts({"blocked_hosts": ["a.com", " b.com ", ""]}) == ["a.com", "b.com"]


def test_collect_blocked_hosts_handles_invalid_config() -> None:
    assert collect_blocked_hosts({}) == []
    assert collect_blocked_hosts({"blocked_hosts": None}) == []
    assert collect_blocked_hosts({"blocked_hosts": "a.com"}) == []
    assert collect_blocked_hosts(None) == []
