import types
from pathlib import Path

import modules.hotfix.runtime as runtime_module
from modules.hotfix.repo import RepoUpdate
from modules.hotfix.runtime import HotfixRuntime


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, message, *args):
        self.infos.append(message % args if args else message)

    def warning(self, message, *args):
        self.warnings.append(message % args if args else message)


def make_spec(name="demo", astrbot=""):
    return types.SimpleNamespace(
        name=name,
        astrbot=astrbot,
        targets=(),
        description="",
        file_display=f"patches/{name}/x.py",
        file=Path(f"/tmp/{name}.py"),
        import_as=f"pkg.hotfix_{name}",
    )


def make_runtime(tmp_path, monkeypatch, enabled=True, patches=None, selected=None):
    calls = []

    def fake_update(self, repo_url, ref=""):
        calls.append(repo_url)
        return RepoUpdate(True, "abc1234", "2026-10-31T00:00:00+00:00", "")

    monkeypatch.setattr(runtime_module.RepoCache, "update", fake_update)
    monkeypatch.setattr(runtime_module, "load_manifest", lambda root: (patches or [], []))
    monkeypatch.setattr(runtime_module, "astrbot_version", lambda: "4.29.4")
    config = {"hotfix": {"enabled": enabled, "repo": "https://github.com/o/r", "ref": ""}}
    runtime = HotfixRuntime(config, FakeLogger(), data_root=tmp_path)
    # The runtime only reads the manifest from an existing checkout; the fake
    # update never creates one, so stand in for a completed clone.
    runtime._repo.directory("https://github.com/o/r").mkdir(parents=True, exist_ok=True)
    if selected is not None:
        runtime.set_selection(selected)
    return runtime, calls


def test_disabled_does_not_touch_git(tmp_path, monkeypatch):
    runtime, calls = make_runtime(tmp_path, monkeypatch, enabled=False)
    runtime.apply()
    assert calls == []


def test_unselected_patches_are_not_loaded(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.apply()
    assert runtime.status()["patches"][0]["state"] == "disabled"


def test_unselected_incompatible_patch_stays_disabled(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec(astrbot=">=5")])
    runtime.apply()
    assert runtime.status()["patches"][0]["state"] == "disabled"


def test_selected_incompatible_patch_is_reported(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec(astrbot=">=5")], selected=["demo"])
    runtime.apply()
    assert runtime.status()["patches"][0]["state"] == "incompatible"


def test_unknown_selection_names_are_ignored(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.set_selection(["ghost"])
    assert runtime.status()["patches"][0]["state"] == "disabled"


def test_loader_failure_is_reported_as_failed(tmp_path, monkeypatch):
    spec = make_spec()
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[spec], selected=["demo"])

    def boom(self, patch):
        raise RuntimeError("inject boom")

    monkeypatch.setattr(runtime_module.PatchLoader, "load", boom)
    runtime.apply()
    status = runtime.status()
    assert status["patches"][0]["state"] == "failed"
    assert "inject boom" in status["patches"][0]["reason"]


def test_writes_hotfix_log_lines(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.apply()
    lines = runtime._logger.infos + runtime._logger.warnings
    assert any("[hotfix]" in line for line in lines)


def test_disabled_logs_nothing(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, enabled=False)
    runtime.apply()
    assert not any("[hotfix]" in line for line in runtime._logger.infos + runtime._logger.warnings)


def test_disabled_status_uses_cache_without_git(tmp_path, monkeypatch):
    runtime, calls = make_runtime(tmp_path, monkeypatch, enabled=False, patches=[make_spec()])
    runtime.apply()
    assert calls == []
    assert runtime.status()["patches"][0]["name"] == "demo"


def test_selection_does_not_touch_git(tmp_path, monkeypatch):
    runtime, calls = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.apply()
    calls.clear()

    runtime.set_selection(["demo"])

    assert calls == []


def test_failed_update_with_cache_sets_error(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime._repo.directory("https://github.com/o/r").mkdir(parents=True, exist_ok=True)

    def failing_update(self, repo_url, ref=""):
        return RepoUpdate(False, "abc1234", "2026-10-31T00:00:00+00:00", "offline")

    monkeypatch.setattr(runtime_module.RepoCache, "update", failing_update)
    runtime.apply()

    status = runtime.status()
    assert status["error"] == "offline"
    assert status["patches"][0]["name"] == "demo"


def test_logs_each_patch_failure(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()], selected=["demo"])
    runtime.apply()
    lines = runtime._logger.infos + runtime._logger.warnings
    assert any("[hotfix] failed: demo" in line for line in lines)


def test_unselected_patch_is_never_loaded(tmp_path, monkeypatch):
    loaded = []

    def spy(self, spec):
        loaded.append(spec.name)

    monkeypatch.setattr(runtime_module.PatchLoader, "load", spy)
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.apply()

    assert loaded == []


def test_corrupt_state_does_not_break_apply(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.apply()
    assert runtime.status()["patches"][0]["state"] == "disabled"
