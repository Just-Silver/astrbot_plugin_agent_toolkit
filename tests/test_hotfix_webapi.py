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
        self.updated = None

    def status(self):
        return {"enabled": self.enabled, "patches": [], "error": ""}

    def set_selection(self, names):
        self.saved = names
        return self.status()

    def refresh(self):
        return self.status()

    def update(self, names):
        self.updated = names
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
    for handler in (webapi.handle_status, webapi.handle_selection, webapi.handle_refresh, webapi.handle_update):
        result = asyncio.run(handler(plugin))
        assert result[0] == "error"
        assert result[2] == 503


def test_normalize_selection_accepts_string_list():
    assert webapi.normalize_selection({"selected": ["a", "b", "b"]}) == ["a", "b"]


def test_normalize_selection_rejects_non_object():
    assert webapi.normalize_selection([]) is None


def test_normalize_selection_rejects_non_string_items():
    assert webapi.normalize_selection({"selected": ["a", 1]}) is None


def test_normalize_names_reads_update_field():
    assert webapi.normalize_names({"names": ["a", "b", "b"]}, "names") == ["a", "b"]


def test_normalize_names_rejects_wrong_field():
    assert webapi.normalize_names({"selected": ["a"]}, "names") is None


def test_handle_update_accepts_names(monkeypatch):
    install_fake_web(monkeypatch, payload={"names": ["demo"]})
    runtime = FakeRuntime()
    result = asyncio.run(webapi.handle_update(plugin_with(runtime)))
    assert result[0] == "json"
    assert runtime.updated == ["demo"]


def test_handle_update_rejects_bad_body(monkeypatch):
    install_fake_web(monkeypatch, payload={"names": [1]})
    result = asyncio.run(webapi.handle_update(plugin_with(FakeRuntime())))
    assert result[0] == "error"
    assert result[2] == 400


def test_handle_update_rejected_when_disabled(monkeypatch):
    install_fake_web(monkeypatch)
    result = asyncio.run(webapi.handle_update(plugin_with(FakeRuntime(enabled=False))))
    assert result[0] == "error"
    assert result[2] == 400
