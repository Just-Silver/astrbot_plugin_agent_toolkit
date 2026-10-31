import asyncio
import sys
import types

from modules.hotfix import webapi


def install_fake_web(monkeypatch, payload=None):
    web = types.ModuleType("astrbot.api.web")
    web.json_response = lambda data: ("json", data)
    web.error_response = lambda message, status_code=500: ("error", message, status_code)

    async def _json(default=None):
        return payload if payload is not None else default

    web.request = types.SimpleNamespace(json=_json)
    api = types.ModuleType("astrbot.api")
    api.web = web
    astrbot = types.ModuleType("astrbot")
    astrbot.api = api
    monkeypatch.setitem(sys.modules, "astrbot", astrbot)
    monkeypatch.setitem(sys.modules, "astrbot.api", api)
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)


class FakeRuntime:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.saved = None

    def status(self):
        return {"enabled": self.enabled, "patches": [], "error": ""}

    def set_selection(self, names):
        self.saved = names
        return self.status()

    def refresh(self):
        return self.status()


def plugin_with(runtime):
    return types.SimpleNamespace(_hotfix=runtime)


def test_handle_selection_rejected_when_disabled(monkeypatch):
    install_fake_web(monkeypatch)
    result = asyncio.run(webapi.handle_selection(plugin_with(FakeRuntime(enabled=False))))
    assert result[0] == "error"
    assert result[2] == 400


def test_handle_selection_accepts_list(monkeypatch):
    install_fake_web(monkeypatch, payload={"selected": ["a"]})
    runtime = FakeRuntime()
    result = asyncio.run(webapi.handle_selection(plugin_with(runtime)))
    assert result[0] == "json"
    assert runtime.saved == ["a"]


def test_handle_selection_rejects_bad_body(monkeypatch):
    install_fake_web(monkeypatch, payload={"selected": [1]})
    result = asyncio.run(webapi.handle_selection(plugin_with(FakeRuntime())))
    assert result[0] == "error"
    assert result[2] == 400


def test_handlers_survive_missing_runtime(monkeypatch):
    install_fake_web(monkeypatch)
    plugin = types.SimpleNamespace(_hotfix=None)
    for handler in (webapi.handle_status, webapi.handle_selection, webapi.handle_refresh):
        result = asyncio.run(handler(plugin))
        assert result[0] == "error"
        assert result[2] == 503
